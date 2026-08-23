"""Interfaz de línea de comandos de docencia-tools."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .assignment import AssignmentImpossible, assign_reviews, constraints_from_private
from .config import load_activity, load_private, select_activity
from .errors import EXIT_CODES, FailureKind, InfrastructureError, Issue
from .git_observation import observe_diff
from .history import clamp_to_pr_creation, first_complete_at, observations_from_git
from .protocol import validate_protocol
from .state import build_state, write_state
from .technical import run_technical_checks, write_requirements


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docencia-tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config = subparsers.add_parser("validar-config", help="Valida una configuración pública confiable")
    config.add_argument("--config", required=True)

    dependencies = subparsers.add_parser("dependencias", help="Escribe requirements desde configuración confiable")
    dependencies.add_argument("--config", required=True)
    dependencies.add_argument("--salida", required=True)

    select = subparsers.add_parser("seleccionar-config", help="Selecciona configuración por la rama del PR")
    select.add_argument("--directorio", required=True)
    select.add_argument("--rama", required=True)

    validate = subparsers.add_parser("validar-pr", help="Valida un PR observado")
    validate.add_argument("--config", required=True)
    validate.add_argument("--evento", required=True, help="JSON de la API REST de un pull request")
    validate.add_argument("--repo-head", required=True)
    validate.add_argument("--trusted-root", required=True)
    validate.add_argument("--trusted-ref", required=True)
    validate.add_argument("--salida", required=True)

    assign = subparsers.add_parser("asignar", help="Construye asignaciones reproducibles")
    assign.add_argument("--participantes", required=True)
    assign.add_argument("--privada")
    assign.add_argument("--revisores", type=int, default=1)
    assign.add_argument("--semilla", required=True)
    assign.add_argument("--salida", required=True)
    return parser


def _read_json(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InfrastructureError(f"No se pudo leer el evento del PR: {exc}") from exc
    if not isinstance(data, dict):
        raise InfrastructureError("El evento del PR debe ser un objeto JSON.")
    return data


def _pr_payload(event: dict[str, Any]) -> dict[str, Any]:
    pr = event.get("pull_request", event)
    if not isinstance(pr, dict):
        raise InfrastructureError("El JSON no contiene un pull request.")
    try:
        return {
            "number": int(pr["number"]),
            "title": str(pr["title"]),
            "body": str(pr.get("body") or ""),
            "created_at": datetime.fromisoformat(str(pr["created_at"]).replace("Z", "+00:00")),
            "base_ref": str(pr["base"]["ref"]),
            "head_ref": str(pr["head"]["ref"]),
            "head_sha": str(pr["head"]["sha"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise InfrastructureError(f"El JSON del PR está incompleto: {exc}") from exc


def _slug(branch: str) -> str:
    return branch.split("/", 1)[1] if "/" in branch else ""


def _validate_pr(args: argparse.Namespace) -> int:
    config = load_activity(args.config)
    pr = _pr_payload(_read_json(args.evento))
    merge_base, changed, head_files = observe_diff(args.repo_head, args.trusted_ref, pr["head_sha"])
    slug = _slug(pr["head_ref"])
    protocol = validate_protocol(
        config,
        branch=pr["head_ref"],
        base=pr["base_ref"],
        title=pr["title"],
        body=pr["body"],
        created_at=pr["created_at"],
        changed_files=changed,
        head_files=head_files,
        slug=slug,
    )
    observations = clamp_to_pr_creation(
        observations_from_git(args.repo_head, merge_base, pr["head_sha"]),
        pr["created_at"],
    )
    first = first_complete_at(config, slug, observations)
    deadline = config.deadlines.delivery
    if first is None:
        punctuality = "incomplete"
    elif deadline is None:
        punctuality = "unknown"
    else:
        punctuality = "on_time" if first.timestamp <= deadline else "late"
    issues = list(protocol.issues)
    if protocol.safe_to_execute:
        try:
            issues.extend(run_technical_checks(config, slug=slug, head_root=args.repo_head, trusted_root=args.trusted_root))
        except InfrastructureError as exc:
            issues.append(Issue("infrastructure:environment", FailureKind.INFRASTRUCTURE, str(exc), "infrastructure"))
    state = build_state(
        activity=config.activity,
        student=slug,
        pr_number=pr["number"],
        head_sha=pr["head_sha"],
        merge_base=merge_base,
        trusted_ref=args.trusted_ref,
        first_complete=first.as_dict() if first else None,
        general_deadline=deadline.isoformat() if deadline else None,
        applied_deadline=deadline.isoformat() if deadline else None,
        punctuality=punctuality,
        reviewable=protocol.reviewable,
        current_errors=[issue.code for issue in issues],
        historical_facts=["entrega:tarde"] if punctuality == "late" else [],
    )
    state["failures"] = [issue.as_dict() for issue in issues]
    state["safe_to_execute_student_code"] = protocol.safe_to_execute
    write_state(args.salida, state)
    for issue in issues:
        print(f"[{issue.kind.value}] {issue.code}: {issue.message}", file=sys.stderr)
    if not issues:
        print(f"PR #{pr['number']} validado; estado guardado en {args.salida}.")
        return 0
    precedence = [FailureKind.INFRASTRUCTURE, FailureKind.ACADEMIC_VALIDATION, FailureKind.IMPLEMENTATION, FailureKind.PROTOCOL]
    present = {issue.kind for issue in issues}
    return next(EXIT_CODES[kind] for kind in precedence if kind in present)


def _assign(args: argparse.Namespace) -> int:
    try:
        raw = yaml.safe_load(Path(args.participantes).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InfrastructureError(f"No se pudieron cargar participantes: {exc}") from exc
    participants = raw.get("participants") if isinstance(raw, dict) else raw
    if not isinstance(participants, list) or not all(isinstance(item, str) for item in participants):
        raise InfrastructureError("Participantes debe ser una lista de identificadores.")
    private = load_private(args.privada)
    constraints = constraints_from_private(private, args.revisores)
    try:
        result = assign_reviews(participants, args.semilla, constraints)
    except AssignmentImpossible as exc:
        Path(args.salida).write_text(json.dumps({"error": str(exc), "diagnostics": exc.diagnostics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(str(exc), file=sys.stderr)
        return EXIT_CODES[FailureKind.INFRASTRUCTURE]
    Path(args.salida).write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validar-config":
            config = load_activity(args.config)
            print(f"Configuración válida: {config.activity} (enabled={str(config.enabled).lower()}).")
            return 0
        if args.command == "dependencias":
            write_requirements(load_activity(args.config), args.salida)
            print(f"Dependencias confiables escritas en {args.salida}.")
            return 0
        if args.command == "seleccionar-config":
            print(select_activity(args.directorio, args.rama))
            return 0
        if args.command == "validar-pr":
            return _validate_pr(args)
        if args.command == "asignar":
            return _assign(args)
    except InfrastructureError as exc:
        print(f"[infrastructure_error] {exc}", file=sys.stderr)
        return EXIT_CODES[FailureKind.INFRASTRUCTURE]
    raise AssertionError("Comando no alcanzable")
