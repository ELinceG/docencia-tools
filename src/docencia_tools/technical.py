"""Validaciones técnicas ejecutadas solo después de validar la frontera de confianza."""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from .config import ActivityConfig, TechnicalCheck
from .errors import FailureKind, InfrastructureError, Issue


def _safe_path(root: Path, configured: str, *, slug: str, activity: str) -> Path:
    rendered = configured.format(slug=slug, activity=activity)
    candidate = (root / rendered).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise InfrastructureError(f"La ruta técnica sale del árbol autorizado: {rendered}.") from exc
    return candidate


def run_technical_checks(config: ActivityConfig, *, slug: str, head_root: str | Path, trusted_root: str | Path) -> list[Issue]:
    """Ejecuta checks declarados por configuración confiable, nunca por el PR."""

    verify_dependencies(config)
    head = Path(head_root).resolve()
    trusted = Path(trusted_root).resolve()
    issues: list[Issue] = []
    for check in config.technical.checks:
        issue = _run_check(check, config, slug, head, trusted)
        if issue is not None:
            issues.append(issue)
    return issues


def verify_dependencies(config: ActivityConfig) -> None:
    """Convierte una dependencia confiable ausente en fallo de infraestructura."""

    missing: list[str] = []
    for requirement in config.technical.dependencies:
        distribution = re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0]
        try:
            metadata.version(distribution)
        except metadata.PackageNotFoundError:
            missing.append(requirement)
    if missing:
        raise InfrastructureError(
            "El workflow no preparó dependencias confiables requeridas: " + ", ".join(missing) + "."
        )


def _run_check(check: TechnicalCheck, config: ActivityConfig, slug: str, head: Path, trusted: Path) -> Issue | None:
    if check.type in {"python_compile", "forbidden_pattern"} and not check.path:
        raise InfrastructureError(f"El check '{check.type}' no declaró path.")
    if check.type == "python_compile":
        target = _safe_path(head, check.path or "", slug=slug, activity=config.activity)
        result = subprocess.run([sys.executable, "-m", "py_compile", str(target)], text=True, capture_output=True, check=False)
        if result.returncode:
            return Issue("error:tests", FailureKind.IMPLEMENTATION, f"El archivo Python no compila: {result.stderr.strip()}", "student")
        return None
    if check.type == "forbidden_pattern":
        target = _safe_path(head, check.path or "", slug=slug, activity=config.activity)
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as exc:
            return Issue("error:tests", FailureKind.IMPLEMENTATION, f"No se pudo leer el archivo entregado: {exc}", "student")
        if check.pattern is None:
            raise InfrastructureError("El check forbidden_pattern no declaró pattern.")
        try:
            found = re.search(check.pattern, content, flags=re.MULTILINE)
        except re.error as exc:
            raise InfrastructureError(f"Patrón técnico inválido en configuración confiable: {exc}") from exc
        if found:
            return Issue("error:tests", FailureKind.IMPLEMENTATION, f"El archivo conserva contenido incompleto que coincide con {check.pattern!r}.", "student")
        return None
    if check.type == "command":
        replacements = {
            "{head}": str(head),
            "{trusted}": str(trusted),
            "{slug}": slug,
            "{activity}": config.activity,
            "{python}": sys.executable,
        }
        command = []
        for argument in check.command:
            for marker, value in replacements.items():
                argument = argument.replace(marker, value)
            command.append(argument)
        result = subprocess.run(command, cwd=head, text=True, capture_output=True, check=False)
        if result.returncode:
            detail = (result.stdout + "\n" + result.stderr).strip()
            return Issue("error:tests", FailureKind.ACADEMIC_VALIDATION, f"La validación académica falló: {detail}", "student")
        return None
    raise InfrastructureError(f"Check técnico desconocido: {check.type}.")


def write_requirements(config: ActivityConfig, output: str | Path) -> None:
    """Materializa dependencias desde configuración confiable para que el workflow las instale."""

    allowed = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!-]+)*)?$")
    invalid = [dependency for dependency in config.technical.dependencies if not allowed.fullmatch(dependency)]
    if invalid:
        raise InfrastructureError(f"Dependencias inválidas en configuración confiable: {invalid!r}.")
    Path(output).write_text("\n".join(config.technical.dependencies) + ("\n" if config.technical.dependencies else ""), encoding="utf-8")
