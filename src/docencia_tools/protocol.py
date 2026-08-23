"""Validaciones del protocolo público de pull requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

from .config import ActivityConfig
from .errors import FailureKind, Issue


SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
SPANISH_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
TITLE_RE = re.compile(
    r"^\[(?P<activity>clase_\d{2})\] (?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*) "
    r"\((?P<weekday>[a-záéíóú]+),(?P<day>\d{1,2}),(?P<month>[a-z]+) "
    r"(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)\)$"
)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ProtocolResult:
    issues: tuple[Issue, ...]
    reviewable: bool
    safe_to_execute: bool

    @property
    def current_error_labels(self) -> tuple[str, ...]:
        return tuple(sorted({issue.code for issue in self.issues if issue.code.startswith("error:")}))


def _issue(code: str, message: str, *, blocks_review: bool = False, blocks_execution: bool = False) -> Issue:
    return Issue(code, FailureKind.PROTOCOL, message, "student", blocks_review, blocks_execution)


def validate_title(config: ActivityConfig, title: str, slug: str, created_at: datetime) -> list[Issue]:
    match = TITLE_RE.fullmatch(title)
    if not match:
        return [_issue("error:titulo", "El título no sigue exactamente el formato definido en CONTRIBUTING.md.")]
    values = match.groupdict()
    if values["activity"] != config.activity or values["slug"] != slug:
        return [_issue("error:titulo", "La clase o el nombre del título no coincide con la entrega.")]
    month = SPANISH_MONTHS.get(values["month"])
    if month is None:
        return [_issue("error:titulo", "El mes del título debe escribirse correctamente en español.")]
    timezone = ZoneInfo(config.timezone)
    created_local = created_at.astimezone(timezone)
    try:
        stated = datetime(
            created_local.year,
            month,
            int(values["day"]),
            int(values["hour"]),
            int(values["minute"]),
            tzinfo=timezone,
        )
    except ValueError:
        return [_issue("error:titulo", "La fecha escrita en el título no existe en el calendario.")]
    if SPANISH_WEEKDAYS[stated.weekday()] != values["weekday"]:
        return [_issue("error:titulo", "El día de la semana no corresponde a la fecha escrita.")]
    tolerance = timedelta(minutes=config.pr.title_tolerance_minutes)
    if abs(stated - created_local) > tolerance:
        return [_issue("error:titulo", "La hora del título difiere más de cinco minutos de la creación real del PR.")]
    return []


def validate_description(config: ActivityConfig, body: str) -> list[Issue]:
    body = body or ""
    if any(marker in body for marker in ("Resume brevemente", "Indica cuáles archivos", "Describe el trabajo", "Explica cómo revisaste", "[cumple", "<nombre")):
        return [_issue("error:descripcion", "La descripción conserva texto de relleno de la plantilla.")]
    positions: list[tuple[int, str]] = []
    for section in config.pr.required_sections:
        match = re.search(rf"(?m)^## {re.escape(section)}\s*$", body)
        if match is None:
            return [_issue("error:descripcion", f"Falta la sección '## {section}'.")]
        positions.append((match.start(), section))
    positions.sort()
    for index, (start, section) in enumerate(positions):
        heading_end = body.find("\n", start)
        end = positions[index + 1][0] if index + 1 < len(positions) else len(body)
        content = body[heading_end:end].strip()
        if not content:
            return [_issue("error:descripcion", f"La sección '{section}' está vacía.")]
    checked = len(re.findall(r"(?m)^\s*- \[[xX]\] ", body))
    unchecked = len(re.findall(r"(?m)^\s*- \[ \] ", body))
    if checked != config.pr.checklist_items or unchecked:
        return [_issue("error:descripcion", f"Deben estar marcadas exactamente {config.pr.checklist_items} casillas y no quedar casillas vacías.")]
    return []


def infer_slugs(changed_files: list[str], activity: str) -> set[str]:
    pattern = re.compile(rf"^entregas/([^/]+)/{re.escape(activity)}/")
    return {match.group(1) for path in changed_files if (match := pattern.match(path))}


def validate_protocol(
    config: ActivityConfig,
    *,
    branch: str,
    base: str,
    title: str,
    body: str,
    created_at: datetime,
    changed_files: list[str],
    head_files: set[str],
    slug: str | None = None,
) -> ProtocolResult:
    issues: list[Issue] = []
    inferred = infer_slugs(changed_files, config.activity)
    if slug is None:
        if len(inferred) == 1:
            slug = next(iter(inferred))
        else:
            slug = branch.split("/", 1)[1] if "/" in branch else ""
    if not SLUG_RE.fullmatch(slug):
        issues.append(_issue("error:rama", "El nombre debe usar minúsculas ASCII y guiones."))
    if len(inferred) > 1 or (inferred and slug not in inferred):
        issues.append(_issue("error:propietario", "La entrega contiene rutas de más de un alumno.", blocks_review=True, blocks_execution=True))
    expected_branch = config.branch_pattern.format(slug=slug, activity=config.activity)
    if branch != expected_branch:
        issues.append(_issue("error:rama", f"La rama esperada es '{expected_branch}'."))
    if base != config.expected_base:
        issues.append(_issue("error:base", f"La rama base debe ser '{config.expected_base}'.", blocks_review=True, blocks_execution=True))
    issues.extend(validate_title(config, title, slug, created_at))
    issues.extend(validate_description(config, body))

    required = set(config.required_for(slug))
    missing = sorted(required - head_files)
    if missing:
        issues.append(_issue("error:archivos-faltantes", f"Faltan archivos obligatorios: {', '.join(missing)}.", blocks_review=True, blocks_execution=True))
    allowed = config.allowed_for(slug)
    extras = sorted(path for path in changed_files if not any(PurePosixPath(path).match(pattern) for pattern in allowed))
    if extras:
        issues.append(_issue("error:archivos-extra", f"Hay archivos fuera del alcance permitido: {', '.join(extras)}.", blocks_execution=True))

    return ProtocolResult(
        issues=tuple(issues),
        reviewable=not any(issue.blocks_review for issue in issues),
        safe_to_execute=not any(issue.blocks_execution for issue in issues),
    )
