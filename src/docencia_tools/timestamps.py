"""Conversión común de timestamps provenientes de YAML o JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .errors import InfrastructureError


def parse_iso_datetime(value: Any, *, name: str, timezone: str) -> datetime:
    """Acepta texto ISO o datetime nativo y lo normaliza a la zona indicada."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        if "T" not in value and " " not in value:
            raise InfrastructureError(f"{name} no es un timestamp ISO 8601 válido.")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InfrastructureError(f"{name} no es un timestamp ISO 8601 válido.") from exc
    else:
        raise InfrastructureError(f"{name} debe ser un timestamp ISO 8601.")
    zone = ZoneInfo(timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)
