"""Aplicación local de excepciones privadas sin revelar sus motivos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .errors import InfrastructureError


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
    overrides = private.get("deadline_overrides", [])
    if not isinstance(overrides, list):
        raise InfrastructureError("'deadline_overrides' privado debe ser una lista.")
    matching = [item for item in overrides if isinstance(item, dict) and item.get("student") == student and item.get("activity") == activity]
    if len(matching) > 1:
        raise InfrastructureError("Hay más de un deadline privado aplicable al mismo alumno y actividad.")
    if matching:
        value = matching[0].get("deadline")
        if not isinstance(value, str):
            raise InfrastructureError("El deadline privado debe ser un timestamp ISO 8601.")
        try:
            applied = datetime.fromisoformat(value)
        except ValueError as exc:
            raise InfrastructureError("El deadline privado no es un timestamp ISO 8601 válido.") from exc
        if applied.tzinfo is None:
            applied = applied.replace(tzinfo=ZoneInfo(timezone))
        applied = applied.astimezone(ZoneInfo(timezone))
        exception_applied = True
    exempt_reviewing = student in set(map(str, private.get("exempt_from_reviewing", [])))
    exempt_receiving = student in set(map(str, private.get("exempt_from_receiving_review", [])))
    return StudentPolicy(applied, exception_applied, exempt_reviewing, exempt_receiving)
