"""Cierre auditable de entregas y preparación de revisión por pares."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .assignment import (
    AssignmentImpossible,
    AssignmentResult,
    assign_reviews,
    constraints_from_private,
    eligible_participants,
)
from .config import ActivityConfig
from .errors import InfrastructureError
from .private import effective_closure_deadline, policy_for_student


CLOSURE_SCHEMA_VERSION = 1
STUDENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ClosurePending(InfrastructureError):
    """El cierre definitivo aún no corresponde por una ventana vigente."""


@dataclass(frozen=True)
class ClosureWindow:
    now: datetime
    general_deadline: datetime
    effective_deadline: datetime


@dataclass(frozen=True)
class StudentClosure:
    pull_request: int
    observed_pull_requests: tuple[int, ...]
    first_complete_at: dict[str, object] | None
    general_deadline: str
    applied_deadline: str
    punctuality: str
    reviewable: bool
    exception_applied: bool
    exempt_from_reviewing: bool
    exempt_from_receiving_review: bool
    eligible_for_peer_review: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "pull_request": self.pull_request,
            "observed_pull_requests": list(self.observed_pull_requests),
            "first_complete_at": self.first_complete_at,
            "general_deadline": self.general_deadline,
            "applied_deadline": self.applied_deadline,
            "punctuality": self.punctuality,
            "reviewable": self.reviewable,
            "exception_applied": self.exception_applied,
            "exempt_from_reviewing": self.exempt_from_reviewing,
            "exempt_from_receiving_review": self.exempt_from_receiving_review,
            "eligible_for_peer_review": self.eligible_for_peer_review,
        }


@dataclass(frozen=True)
class ClosureResult:
    schema_version: int
    activity: str
    generated_at: str
    general_deadline: str
    effective_closure_deadline: str
    seed: str
    students: dict[str, StudentClosure]
    eligible_participants: tuple[str, ...]
    excluded: tuple[dict[str, object], ...]
    assignment: AssignmentResult

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "activity": self.activity,
            "generated_at": self.generated_at,
            "general_deadline": self.general_deadline,
            "effective_closure_deadline": self.effective_closure_deadline,
            "seed": self.seed,
            "students": {
                student: closure.as_dict()
                for student, closure in sorted(self.students.items())
            },
            "eligible_participants": list(self.eligible_participants),
            "excluded": list(self.excluded),
            "assignment": {
                "pairs": [
                    {"reviewer": reviewer, "author": author}
                    for reviewer, author in self.assignment.pairs
                ],
                "avoided_pairs_used": [
                    {"reviewer": reviewer, "author": author}
                    for reviewer, author in self.assignment.avoided_pairs_used
                ],
            },
        }


def _normalize_datetime(value: datetime, timezone: str, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise InfrastructureError(f"'{name}' debe ser un datetime.")
    zone = ZoneInfo(timezone)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _first_complete(
    value: object,
    *,
    student: str,
    timezone: str,
) -> tuple[dict[str, object] | None, datetime | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise InfrastructureError(f"first_complete_at de '{student}' debe ser un objeto JSON o null.")
    timestamp = value.get("timestamp")
    if not isinstance(timestamp, str):
        raise InfrastructureError(f"first_complete_at.timestamp de '{student}' debe ser un timestamp ISO 8601.")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InfrastructureError(f"first_complete_at.timestamp de '{student}' no es válido.") from exc
    parsed = _normalize_datetime(parsed, timezone, f"first_complete_at.timestamp de {student}")
    normalized = dict(value)
    normalized["timestamp"] = parsed.isoformat()
    return normalized, parsed


def consolidate_equivalent_states(
    states: Iterable[dict[str, object]],
    *,
    activity: str,
    timezone: str,
) -> dict[str, dict[str, object]]:
    """Consolida observaciones del mismo contenido en una entrega lógica por alumno."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            raise InfrastructureError(f"El estado en la posición {index} debe ser un objeto JSON.")
        if state.get("activity") != activity:
            raise InfrastructureError(
                f"El estado en la posición {index} corresponde a {state.get('activity')!r}, no a '{activity}'."
            )
        student = state.get("student")
        if not isinstance(student, str) or not STUDENT_RE.fullmatch(student):
            raise InfrastructureError(f"El estado en la posición {index} no tiene un student válido.")
        pull_request = state.get("pull_request")
        if isinstance(pull_request, bool) or not isinstance(pull_request, int) or pull_request < 1:
            raise InfrastructureError(f"El estado de '{student}' no tiene un pull_request entero válido.")
        head_sha = state.get("head_sha")
        if not isinstance(head_sha, str) or not head_sha.strip():
            raise InfrastructureError(f"El estado de '{student}' no tiene un head_sha válido.")
        grouped.setdefault(student, []).append(state)

    consolidated: dict[str, dict[str, object]] = {}
    for student, group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda state: int(state["pull_request"]))
        pull_requests = [int(state["pull_request"]) for state in ordered]
        if len(pull_requests) != len(set(pull_requests)):
            raise InfrastructureError(
                f"Hay más de un estado para el mismo pull_request de '{student}'."
            )
        head_shas = {str(state["head_sha"]) for state in ordered}
        if len(head_shas) != 1:
            raise InfrastructureError(
                f"La entrega de '{student}' es ambigua: sus PR observados tienen head_sha distintos."
            )

        first_complete_candidates: list[
            tuple[datetime, int, dict[str, object]]
        ] = []
        for state in ordered:
            normalized, timestamp = _first_complete(
                state.get("first_complete_at"),
                student=student,
                timezone=timezone,
            )
            if normalized is not None and timestamp is not None:
                original = state["first_complete_at"]
                assert isinstance(original, dict)
                first_complete_candidates.append(
                    (timestamp, int(state["pull_request"]), dict(original))
                )

        canonical = dict(ordered[-1])
        canonical["first_complete_at"] = (
            min(first_complete_candidates, key=lambda item: (item[0], item[1]))[2]
            if first_complete_candidates
            else None
        )
        canonical["observed_pull_requests"] = pull_requests
        consolidated[student] = canonical
    return consolidated


def require_closure_due(
    config: ActivityConfig,
    *,
    private: dict[str, Any] | None,
    now: datetime,
) -> ClosureWindow:
    """Valida la frontera temporal y devuelve sus valores normalizados."""

    if not config.enabled:
        raise InfrastructureError(f"La actividad '{config.activity}' no está habilitada.")
    general_deadline = config.deadlines.delivery
    if general_deadline is None:
        raise InfrastructureError(f"La actividad '{config.activity}' no tiene delivery deadline.")
    now_local = _normalize_datetime(now, config.timezone, "now")
    closure_deadline = effective_closure_deadline(
        private or {},
        activity=config.activity,
        general_deadline=general_deadline,
        timezone=config.timezone,
    )
    if now_local <= closure_deadline:
        raise ClosurePending(
            f"No se puede cerrar '{config.activity}': todavía existe una ventana válida "
            f"de entrega hasta {closure_deadline.isoformat()} inclusive."
        )
    return ClosureWindow(now_local, general_deadline, closure_deadline)


def close_delivery(
    config: ActivityConfig,
    states: Iterable[dict[str, object]],
    *,
    private: dict[str, Any] | None = None,
    seed: str | int,
    now: datetime,
) -> ClosureResult:
    """Cierra una actividad desde estados públicos y políticas privadas."""

    private_data = private or {}
    window = require_closure_due(config, private=private_data, now=now)
    general_deadline = window.general_deadline

    observed = consolidate_equivalent_states(
        states,
        activity=config.activity,
        timezone=config.timezone,
    )

    student_results: dict[str, StudentClosure] = {}
    academic_states: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for student, state in sorted(observed.items()):
        policy = policy_for_student(
            private_data,
            activity=config.activity,
            student=student,
            general_deadline=general_deadline,
            timezone=config.timezone,
        )
        applied_deadline = policy.applied_deadline
        if applied_deadline is None:
            raise InfrastructureError(f"No se pudo determinar applied_deadline para '{student}'.")
        first_complete, first_timestamp = _first_complete(
            state.get("first_complete_at"),
            student=student,
            timezone=config.timezone,
        )
        if first_timestamp is None:
            punctuality = "incomplete"
        elif first_timestamp <= applied_deadline:
            punctuality = "on_time"
        else:
            punctuality = "late"
        reviewable = state.get("reviewable") is True
        eligible = punctuality == "on_time" and reviewable
        academic_states.append(
            {
                "student": student,
                "punctuality": punctuality,
                "reviewable": reviewable,
            }
        )
        causes: list[str] = []
        if punctuality == "late":
            causes.append("late")
        elif punctuality == "incomplete":
            causes.append("incomplete")
        if not reviewable:
            causes.append("not_reviewable")
        if causes:
            excluded.append({"student": student, "causes": causes})
        student_results[student] = StudentClosure(
            pull_request=int(state["pull_request"]),
            observed_pull_requests=tuple(state["observed_pull_requests"]),
            first_complete_at=first_complete,
            general_deadline=general_deadline.isoformat(),
            applied_deadline=applied_deadline.isoformat(),
            punctuality=punctuality,
            reviewable=reviewable,
            exception_applied=policy.exception_applied,
            exempt_from_reviewing=policy.exempt_from_reviewing,
            exempt_from_receiving_review=policy.exempt_from_receiving_review,
            eligible_for_peer_review=eligible,
        )

    eligible = tuple(eligible_participants(academic_states))
    constraints = constraints_from_private(private_data, config.reviewers_per_submission)
    if eligible:
        try:
            assignment = assign_reviews(eligible, seed, constraints)
        except AssignmentImpossible as exc:
            diagnostics = json.dumps(exc.diagnostics, ensure_ascii=False, sort_keys=True)
            raise InfrastructureError(
                f"No se pudo construir la asignación: {exc} Diagnóstico: {diagnostics}"
            ) from exc
    else:
        assignment = AssignmentResult(str(seed), (), ())

    return ClosureResult(
        schema_version=CLOSURE_SCHEMA_VERSION,
        activity=config.activity,
        generated_at=window.now.isoformat(),
        general_deadline=general_deadline.isoformat(),
        effective_closure_deadline=window.effective_deadline.isoformat(),
        seed=str(seed),
        students=student_results,
        eligible_participants=eligible,
        excluded=tuple(excluded),
        assignment=assignment,
    )


def load_public_states(paths: Iterable[str | Path]) -> list[dict[str, object]]:
    """Carga un objeto JSON por archivo desde archivos o directorios."""

    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            directory_files = sorted(path.glob("*.json"))
            if not directory_files:
                raise InfrastructureError(f"El directorio '{path}' no contiene archivos JSON.")
            files.extend(directory_files)
        elif path.is_file():
            files.append(path)
        else:
            raise InfrastructureError(f"No existe la ruta de estados '{path}'.")
    if not files:
        raise InfrastructureError("No se proporcionaron estados JSON.")

    states: list[dict[str, object]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InfrastructureError(f"No se pudo leer el estado '{path}': {exc}") from exc
        if not isinstance(data, dict):
            raise InfrastructureError(f"El estado '{path}' debe contener un objeto JSON.")
        states.append(data)
    return states


def write_closure(path: str | Path, result: ClosureResult) -> None:
    Path(path).write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
