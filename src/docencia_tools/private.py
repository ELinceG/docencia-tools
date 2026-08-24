"""Aplicación local de excepciones privadas sin revelar sus motivos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .errors import InfrastructureError
from .timestamps import parse_iso_datetime


@dataclass(frozen=True)
class DeadlineOverride:
    student: str
    deadline: datetime


@dataclass(frozen=True)
class StudentPolicy:
    applied_deadline: datetime | None
    exception_applied: bool
    exempt_from_reviewing: bool
    exempt_from_receiving_review: bool

    def public_summary(self) -> dict[str, object]:
        return {
            "applied_deadline": self.applied_deadline.isoformat() if self.applied_deadline else None,
            "exception_applied": self.exception_applied,
            "exempt_from_reviewing": self.exempt_from_reviewing,
            "exempt_from_receiving_review": self.exempt_from_receiving_review,
        }


def deadline_overrides_for_activity(
    private: dict[str, Any],
    *,
    activity: str,
    timezone: str,
) -> tuple[DeadlineOverride, ...]:
    """Normaliza los overrides de una actividad sin conservar motivos privados."""

    raw_overrides = private.get("deadline_overrides", [])
    if not isinstance(raw_overrides, list):
        raise InfrastructureError("'deadline_overrides' privado debe ser una lista.")
    parsed: list[DeadlineOverride] = []
    students: set[str] = set()
    for item in raw_overrides:
        if not isinstance(item, dict) or item.get("activity") != activity:
            continue
        student = item.get("student")
        if not isinstance(student, str) or not student:
            raise InfrastructureError("Un deadline privado aplicable no tiene un student válido.")
        if student in students:
            raise InfrastructureError("Hay más de un deadline privado aplicable al mismo alumno y actividad.")
        students.add(student)
        parsed.append(
            DeadlineOverride(
                student=student,
                deadline=parse_iso_datetime(
                    item.get("deadline"),
                    name="El deadline privado",
                    timezone=timezone,
                ),
            )
        )
    return tuple(parsed)


def effective_closure_deadline(
    private: dict[str, Any],
    *,
    activity: str,
    general_deadline: datetime,
    timezone: str,
) -> datetime:
    """Devuelve el final de la última ventana válida de entrega."""

    overrides = deadline_overrides_for_activity(
        private,
        activity=activity,
        timezone=timezone,
    )
    return max((general_deadline, *(override.deadline for override in overrides)))


def policy_for_student(
    private: dict[str, Any],
    *,
    activity: str,
    student: str,
    general_deadline: datetime | None,
    timezone: str,
) -> StudentPolicy:
    """Resuelve prórroga o deadline individual; nunca devuelve el motivo."""

    applied = general_deadline
    exception_applied = False
    overrides = deadline_overrides_for_activity(
        private,
        activity=activity,
        timezone=timezone,
    )
    matching = [override for override in overrides if override.student == student]
    if matching:
        applied = matching[0].deadline
        exception_applied = True
    exempt_reviewing = student in set(map(str, private.get("exempt_from_reviewing", [])))
    exempt_receiving = student in set(map(str, private.get("exempt_from_receiving_review", [])))
    return StudentPolicy(applied, exception_applied, exempt_reviewing, exempt_receiving)
