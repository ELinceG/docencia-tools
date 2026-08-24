"""Renderizado público de asignaciones de revisión por pares."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .closure import CLOSURE_SCHEMA_VERSION
from .config import ActivityConfig
from .errors import InfrastructureError


GENERATED_NOTICE = "<!-- Generado automáticamente por docencia-tools. No editar manualmente. -->"
STUDENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _activity_title(activity: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[_-]+", activity))


def _student_label(slug: str) -> str:
    display_name = " ".join(part.capitalize() for part in slug.split("-"))
    return f"{display_name} (`{slug}`)"


def _review_deadline(config: ActivityConfig) -> str:
    review = config.deadlines.review
    if review is None:
        raise InfrastructureError(
            f"La actividad '{config.activity}' no tiene deadline de revisión."
        )
    local = review.astimezone(ZoneInfo(config.timezone))
    weekday = WEEKDAYS[local.weekday()].capitalize()
    month = MONTHS[local.month - 1]
    return f"{weekday} {local.day} de {month} de {local.year}, {local:%H:%M}"


def _slug(value: object, *, pair_index: int, role: str) -> str:
    if not isinstance(value, str) or not STUDENT_RE.fullmatch(value):
        raise InfrastructureError(
            f"assignment.pairs[{pair_index}].{role} no contiene un slug válido."
        )
    return value


def _validated_rows(
    closure: dict[str, Any],
) -> tuple[list[tuple[str, str, int]], bool]:
    students = closure.get("students")
    if not isinstance(students, dict):
        raise InfrastructureError("'closure.students' debe ser un objeto JSON.")
    assignment = closure.get("assignment")
    if not isinstance(assignment, dict):
        raise InfrastructureError("'closure.assignment' debe ser un objeto JSON.")
    pairs = assignment.get("pairs")
    if not isinstance(pairs, list):
        raise InfrastructureError("'closure.assignment.pairs' debe ser una lista.")
    excluded = closure.get("excluded")
    if not isinstance(excluded, list):
        raise InfrastructureError("'closure.excluded' debe ser una lista.")

    rows: list[tuple[str, str, int]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            raise InfrastructureError(
                f"assignment.pairs[{index}] debe ser un objeto JSON."
            )
        reviewer = _slug(pair.get("reviewer"), pair_index=index, role="reviewer")
        author = _slug(pair.get("author"), pair_index=index, role="author")
        if reviewer == author:
            raise InfrastructureError(
                f"assignment.pairs[{index}] contiene una auto-revisión."
            )
        if reviewer not in students:
            raise InfrastructureError(
                f"El revisor '{reviewer}' no existe en closure.students."
            )
        if author not in students:
            raise InfrastructureError(
                f"El autor '{author}' no existe en closure.students."
            )
        reviewer_state = students[reviewer]
        author_state = students[author]
        if not isinstance(reviewer_state, dict) or not isinstance(author_state, dict):
            raise InfrastructureError(
                "Los estudiantes asignados deben tener un estado público válido."
            )
        pull_request = author_state.get("pull_request")
        if (
            isinstance(pull_request, bool)
            or not isinstance(pull_request, int)
            or pull_request < 1
        ):
            raise InfrastructureError(
                f"El autor '{author}' no tiene un pull_request entero positivo."
            )
        rows.append((reviewer, author, pull_request))

    return sorted(rows, key=lambda row: (row[0], row[1], row[2])), bool(excluded)


def render_peer_review_markdown(
    config: ActivityConfig,
    closure: object,
) -> str:
    """Construye Markdown público sin recalcular las decisiones del cierre."""

    if not isinstance(closure, dict):
        raise InfrastructureError("El cierre debe ser un objeto JSON.")
    schema_version = closure.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != CLOSURE_SCHEMA_VERSION
    ):
        raise InfrastructureError(
            f"Solo se admite schema_version de cierre: {CLOSURE_SCHEMA_VERSION}."
        )
    if closure.get("activity") != config.activity:
        raise InfrastructureError(
            "La actividad del cierre no coincide con la configuración confiable."
        )

    deadline = _review_deadline(config)
    rows, has_excluded = _validated_rows(closure)
    lines = [
        GENERATED_NOTICE,
        "",
        f"# Revisión por pares — {_activity_title(config.activity)}",
        "",
        f"Fecha límite de revisión: **{deadline}**",
        "",
    ]
    if rows:
        lines.extend(
            [
                "| Revisor | Entrega a revisar | PR |",
                "|---|---|---:|",
                *(
                    f"| {_student_label(reviewer)} | {_student_label(author)} | #{pull_request} |"
                    for reviewer, author, pull_request in rows
                ),
            ]
        )
    else:
        lines.append(
            "No se generaron asignaciones de revisión por pares para esta actividad."
        )

    if has_excluded:
        lines.extend(
            [
                "",
                "## Entregas fuera de la asignación por pares",
                "",
                "Las entregas que no forman parte de esta asignación serán gestionadas directamente por el profesor.",
            ]
        )
    return "\n".join(lines) + "\n"


def load_closure(path: str | Path) -> dict[str, Any]:
    """Carga un cierre público sin interpretar campos ajenos al renderer."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InfrastructureError(f"No se pudo cargar el cierre público: {exc}") from exc
    if not isinstance(value, dict):
        raise InfrastructureError("El cierre debe ser un objeto JSON.")
    return value


def write_peer_review_markdown(path: str | Path, markdown: str) -> None:
    """Escribe un Markdown ya construido."""

    try:
        Path(path).write_text(markdown, encoding="utf-8")
    except OSError as exc:
        raise InfrastructureError(f"No se pudo escribir el Markdown público: {exc}") from exc
