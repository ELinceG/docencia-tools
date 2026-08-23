"""Carga estricta de configuración pública y privada."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .errors import InfrastructureError


@dataclass(frozen=True)
class Deadlines:
    delivery: datetime | None
    review: datetime | None
    reply: datetime | None


@dataclass(frozen=True)
class PullRequestRules:
    title_tolerance_minutes: int = 5
    required_sections: tuple[str, ...] = ()
    checklist_items: int = 6


@dataclass(frozen=True)
class TechnicalCheck:
    type: str
    path: str | None = None
    pattern: str | None = None
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class TechnicalValidation:
    dependencies: tuple[str, ...] = ()
    checks: tuple[TechnicalCheck, ...] = ()


@dataclass(frozen=True)
class ActivityConfig:
    schema_version: int
    activity: str
    enabled: bool
    timezone: str
    expected_base: str
    branch_pattern: str
    required_files: tuple[str, ...]
    allowed_files: tuple[str, ...]
    reviewers_per_submission: int
    deadlines: Deadlines
    pr: PullRequestRules
    technical: TechnicalValidation = field(default_factory=TechnicalValidation)

    def render(self, value: str, slug: str) -> str:
        return value.format(slug=slug, activity=self.activity)

    def required_for(self, slug: str) -> tuple[str, ...]:
        return tuple(self.render(item, slug) for item in self.required_files)

    def allowed_for(self, slug: str) -> tuple[str, ...]:
        return tuple(self.render(item, slug) for item in self.allowed_files)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InfrastructureError(f"'{name}' debe ser un mapa YAML.")
    return value


def _strings(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise InfrastructureError(f"'{name}' debe ser una lista de cadenas no vacías.")
    return tuple(value)


def _datetime(value: Any, name: str, timezone: str, *, enabled: bool) -> datetime | None:
    if value in (None, "PENDIENTE"):
        if enabled:
            raise InfrastructureError(f"'{name}' es obligatorio cuando la actividad está habilitada.")
        return None
    if not isinstance(value, str):
        raise InfrastructureError(f"'{name}' debe ser un timestamp ISO 8601.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InfrastructureError(f"'{name}' no es un timestamp ISO 8601 válido.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed.astimezone(ZoneInfo(timezone))


def load_activity(path: str | Path) -> ActivityConfig:
    """Carga una actividad exclusivamente desde la ruta confiable indicada."""

    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InfrastructureError(f"No se pudo cargar la configuración confiable '{source}': {exc}") from exc
    data = _mapping(raw, "raíz")
    required_top = {
        "schema_version",
        "activity",
        "enabled",
        "timezone",
        "expected_base",
        "branch_pattern",
        "required_files",
        "allowed_files",
        "reviewers_per_submission",
        "deadlines",
        "pull_request",
    }
    missing = sorted(required_top - data.keys())
    if missing:
        raise InfrastructureError(f"Faltan claves obligatorias: {', '.join(missing)}.")
    if data["schema_version"] != 1:
        raise InfrastructureError("Solo se admite schema_version: 1.")
    if not isinstance(data["enabled"], bool):
        raise InfrastructureError("'enabled' debe ser booleano.")
    timezone = data["timezone"]
    if not isinstance(timezone, str):
        raise InfrastructureError("'timezone' debe ser una cadena.")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise InfrastructureError(f"Zona horaria desconocida: {timezone}.") from exc

    deadlines_raw = _mapping(data["deadlines"], "deadlines")
    deadlines = Deadlines(
        delivery=_datetime(deadlines_raw.get("delivery"), "deadlines.delivery", timezone, enabled=data["enabled"]),
        review=_datetime(deadlines_raw.get("review"), "deadlines.review", timezone, enabled=data["enabled"]),
        reply=_datetime(deadlines_raw.get("reply"), "deadlines.reply", timezone, enabled=data["enabled"]),
    )
    if all(value is not None for value in (deadlines.delivery, deadlines.review, deadlines.reply)):
        if not deadlines.delivery <= deadlines.review <= deadlines.reply:
            raise InfrastructureError("Los deadlines deben cumplir delivery <= review <= reply.")
    pr_raw = _mapping(data["pull_request"], "pull_request")
    sections = _strings(pr_raw.get("required_sections"), "pull_request.required_sections")
    tolerance = pr_raw.get("title_tolerance_minutes", 5)
    checklist_items = pr_raw.get("checklist_items", 6)
    if not isinstance(tolerance, int) or tolerance < 0:
        raise InfrastructureError("'title_tolerance_minutes' debe ser un entero no negativo.")
    if not isinstance(checklist_items, int) or checklist_items < 0:
        raise InfrastructureError("'checklist_items' debe ser un entero no negativo.")
    technical_raw = _mapping(data.get("technical_validation", {}), "technical_validation")
    dependencies = _strings(technical_raw.get("dependencies", []), "technical_validation.dependencies", allow_empty=True)
    checks: list[TechnicalCheck] = []
    checks_raw = technical_raw.get("checks", [])
    if not isinstance(checks_raw, list):
        raise InfrastructureError("'technical_validation.checks' debe ser una lista.")
    for index, raw_check in enumerate(checks_raw):
        check = _mapping(raw_check, f"technical_validation.checks[{index}]")
        check_type = check.get("type")
        if check_type not in {"python_compile", "forbidden_pattern", "command"}:
            raise InfrastructureError(f"Tipo de validación técnica desconocido: {check_type!r}.")
        command = _strings(check.get("command", []), f"checks[{index}].command", allow_empty=True)
        if check_type == "command" and not command:
            raise InfrastructureError("Una validación 'command' necesita argumentos explícitos.")
        checks.append(TechnicalCheck(type=check_type, path=check.get("path"), pattern=check.get("pattern"), command=command))

    activity = data["activity"]
    expected_base = data["expected_base"]
    branch_pattern = data["branch_pattern"]
    reviewers = data["reviewers_per_submission"]
    if not all(isinstance(item, str) and item for item in (activity, expected_base, branch_pattern)):
        raise InfrastructureError("'activity', 'expected_base' y 'branch_pattern' deben ser cadenas no vacías.")
    if not isinstance(reviewers, int) or reviewers < 1:
        raise InfrastructureError("'reviewers_per_submission' debe ser un entero positivo.")

    return ActivityConfig(
        schema_version=1,
        activity=activity,
        enabled=data["enabled"],
        timezone=timezone,
        expected_base=expected_base,
        branch_pattern=branch_pattern,
        required_files=_strings(data["required_files"], "required_files"),
        allowed_files=_strings(data["allowed_files"], "allowed_files"),
        reviewers_per_submission=reviewers,
        deadlines=deadlines,
        pr=PullRequestRules(tolerance, sections, checklist_items),
        technical=TechnicalValidation(dependencies, tuple(checks)),
    )


def load_private(path: str | Path | None) -> dict[str, Any]:
    """Carga excepciones privadas sin mezclarlas con el resultado público."""

    if path is None:
        return {}
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise InfrastructureError(f"No se pudo cargar la configuración privada: {exc}") from exc
    return _mapping(data, "configuración privada")


def select_activity(
    config_directory: str | Path,
    branch: str | None = None,
    changed_files: list[str] | None = None,
) -> Path:
    """Selecciona actividad por rutas observadas; usa la rama solo como respaldo."""

    directory = Path(config_directory)
    configs = [(path, load_activity(path)) for path in sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))]
    path_matches = [
        path
        for path, config in configs
        if any(file.startswith("entregas/") and f"/{config.activity}/" in file for file in (changed_files or []))
    ]
    if len(path_matches) == 1:
        return path_matches[0]
    if len(path_matches) > 1:
        raise InfrastructureError(f"Los archivos del PR coinciden con {len(path_matches)} actividades confiables; se esperaba exactamente una.")
    if branch is None:
        raise InfrastructureError("Los archivos del PR no permiten identificar una actividad confiable.")
    matches: list[Path] = []
    for path, config in configs:
        pattern = config.branch_pattern.replace("{activity}", config.activity)
        prefix, marker, suffix = pattern.partition("{slug}")
        if marker and branch.startswith(prefix) and branch.endswith(suffix):
            slug = branch[len(prefix) : len(branch) - len(suffix) if suffix else None]
            if slug:
                matches.append(path)
    if len(matches) != 1:
        raise InfrastructureError(f"La rama '{branch}' coincide con {len(matches)} actividades confiables; se esperaba exactamente una.")
    return matches[0]
