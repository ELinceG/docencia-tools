from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from docencia_tools import cli, render_peer_review_markdown
from docencia_tools.errors import InfrastructureError


SECRET_REASON = "motivo-confidencial-que-no-debe-publicarse"


def _class_02(activity):
    return replace(
        activity,
        activity="clase_02",
        deadlines=replace(
            activity.deadlines,
            review=datetime.fromisoformat("2026-08-18T18:59:00-06:00"),
        ),
    )


def _closure(*, activity: str = "clase_02") -> dict[str, object]:
    return {
        "schema_version": 1,
        "activity": activity,
        "generated_at": "2026-08-16T08:00:00-06:00",
        "general_deadline": "2026-08-15T23:59:00-06:00",
        "effective_closure_deadline": "2026-08-16T00:05:00-06:00",
        "seed": "semilla-privada-para-el-renderer",
        "students": {
            "aline-milan": {
                "pull_request": 12,
                "observed_pull_requests": [10, 12],
                "first_complete_at": {
                    "timestamp": "2026-08-15T22:00:00-06:00",
                    "sha": "sha-aline",
                },
                "private_note": SECRET_REASON,
            },
            "leonardo-aguirre": {
                "pull_request": 31,
                "observed_pull_requests": [29, 31],
                "first_complete_at": None,
            },
            "maria-jose": {
                "pull_request": 44,
                "observed_pull_requests": [44],
                "first_complete_at": None,
            },
            "fuera-secreta": {
                "pull_request": 55,
                "observed_pull_requests": [55],
                "first_complete_at": None,
            },
        },
        "eligible_participants": [
            "aline-milan",
            "leonardo-aguirre",
            "maria-jose",
        ],
        "excluded": [
            {
                "student": "fuera-secreta",
                "causes": ["late", "not_reviewable", SECRET_REASON],
            }
        ],
        "assignment": {
            "pairs": [
                {"reviewer": "maria-jose", "author": "aline-milan"},
                {"reviewer": "aline-milan", "author": "leonardo-aguirre"},
                {"reviewer": "leonardo-aguirre", "author": "maria-jose"},
            ],
            "avoided_pairs_used": [],
        },
        "private_extension": {"reason": SECRET_REASON},
    }


def test_basic_render_with_three_assignments_has_exact_public_markdown(activity):
    markdown = render_peer_review_markdown(_class_02(activity), _closure())

    assert markdown == """<!-- Generado automáticamente por docencia-tools. No editar manualmente. -->

# Revisión por pares — Clase 02

Fecha límite de revisión: **Martes 18 de agosto de 2026, 18:59**

| Revisor | Entrega a revisar | PR |
|---|---|---:|
| Aline Milan (`aline-milan`) | Leonardo Aguirre (`leonardo-aguirre`) | #31 |
| Leonardo Aguirre (`leonardo-aguirre`) | Maria Jose (`maria-jose`) | #44 |
| Maria Jose (`maria-jose`) | Aline Milan (`aline-milan`) | #12 |

## Entregas fuera de la asignación por pares

Las entregas que no forman parte de esta asignación serán gestionadas directamente por el profesor.
"""


def test_activity_title_is_not_hardcoded_to_class_02(activity):
    closure = _closure(activity="clase_04")

    markdown = render_peer_review_markdown(activity, closure)

    assert "# Revisión por pares — Clase 04" in markdown
    assert "Clase 02" not in markdown


def test_review_deadline_is_converted_to_activity_timezone(activity):
    config = replace(
        _class_02(activity),
        deadlines=replace(
            activity.deadlines,
            review=datetime.fromisoformat("2026-08-19T00:59:00+00:00"),
        ),
    )

    markdown = render_peer_review_markdown(config, _closure())

    assert "**Martes 18 de agosto de 2026, 18:59**" in markdown


def test_slug_humanization_keeps_exact_auditable_identity(activity):
    markdown = render_peer_review_markdown(_class_02(activity), _closure())

    assert "Leonardo Aguirre (`leonardo-aguirre`)" in markdown
    assert "Maria Jose (`maria-jose`)" in markdown


def test_author_uses_canonical_pull_request_only(activity):
    markdown = render_peer_review_markdown(_class_02(activity), _closure())

    assert "Leonardo Aguirre (`leonardo-aguirre`) | #31" in markdown
    assert "#29" not in markdown
    assert "observed_pull_requests" not in markdown


def test_renderer_does_not_publish_audit_private_or_exclusion_details(activity):
    markdown = render_peer_review_markdown(_class_02(activity), _closure())

    forbidden = (
        "fuera-secreta",
        "late",
        "not_reviewable",
        SECRET_REASON,
        "first_complete_at",
        "effective_closure_deadline",
        "semilla-privada-para-el-renderer",
        "sha-aline",
        "observed_pull_requests",
    )
    assert all(value not in markdown for value in forbidden)
    assert "Entregas fuera de la asignación por pares" in markdown


def test_pair_order_does_not_change_output(activity):
    config = _class_02(activity)
    closure = _closure()
    reversed_closure = copy.deepcopy(closure)
    reversed_closure["assignment"]["pairs"].reverse()

    assert render_peer_review_markdown(config, closure) == render_peer_review_markdown(
        config,
        reversed_closure,
    )


def test_different_activity_fails(activity):
    with pytest.raises(InfrastructureError, match="no coincide"):
        render_peer_review_markdown(activity, _closure())


def test_unknown_reviewer_fails(activity):
    closure = _closure()
    closure["assignment"]["pairs"][0]["reviewer"] = "persona-inexistente"

    with pytest.raises(InfrastructureError, match="revisor.*no existe"):
        render_peer_review_markdown(_class_02(activity), closure)


def test_unknown_author_fails(activity):
    closure = _closure()
    closure["assignment"]["pairs"][0]["author"] = "persona-inexistente"

    with pytest.raises(InfrastructureError, match="autor.*no existe"):
        render_peer_review_markdown(_class_02(activity), closure)


@pytest.mark.parametrize("pull_request", [0, -1, True, "31", None])
def test_invalid_author_pull_request_fails(activity, pull_request):
    closure = _closure()
    closure["students"]["aline-milan"]["pull_request"] = pull_request

    with pytest.raises(InfrastructureError, match="entero positivo"):
        render_peer_review_markdown(_class_02(activity), closure)


def test_self_review_fails(activity):
    closure = _closure()
    closure["assignment"]["pairs"][0] = {
        "reviewer": "aline-milan",
        "author": "aline-milan",
    }

    with pytest.raises(InfrastructureError, match="auto-revisión"):
        render_peer_review_markdown(_class_02(activity), closure)


def test_zero_assignments_has_message_without_empty_table(activity):
    closure = _closure()
    closure["assignment"]["pairs"] = []
    closure["excluded"] = []

    markdown = render_peer_review_markdown(_class_02(activity), closure)

    assert "No se generaron asignaciones de revisión por pares para esta actividad." in markdown
    assert "| Revisor |" not in markdown
    assert "Entregas fuera de la asignación" not in markdown


def test_zero_assignments_can_keep_generic_excluded_section(activity):
    closure = _closure()
    closure["assignment"]["pairs"] = []

    markdown = render_peer_review_markdown(_class_02(activity), closure)

    assert "Entregas fuera de la asignación por pares" in markdown
    assert "fuera-secreta" not in markdown


@pytest.mark.parametrize("closure", [[], None, "cierre"])
def test_closure_must_be_json_object(activity, closure):
    with pytest.raises(InfrastructureError, match="objeto JSON"):
        render_peer_review_markdown(_class_02(activity), closure)


@pytest.mark.parametrize("schema_version", [None, 0, 2, True, "1"])
def test_incompatible_closure_schema_fails(activity, schema_version):
    closure = _closure()
    closure["schema_version"] = schema_version

    with pytest.raises(InfrastructureError, match="schema_version"):
        render_peer_review_markdown(_class_02(activity), closure)


def test_missing_review_deadline_fails(activity):
    config = replace(
        _class_02(activity),
        deadlines=replace(activity.deadlines, review=None),
    )

    with pytest.raises(InfrastructureError, match="deadline de revisión"):
        render_peer_review_markdown(config, _closure())


@pytest.mark.parametrize(
    "assignment",
    [None, [], {}, {"pairs": None}, {"pairs": ["aline-milan"]}],
)
def test_invalid_assignment_pairs_structure_fails(activity, assignment):
    closure = _closure()
    closure["assignment"] = assignment

    with pytest.raises(InfrastructureError, match="assignment"):
        render_peer_review_markdown(_class_02(activity), closure)


def test_cli_writes_markdown_and_prints_only_brief_confirmation(
    config_path: Path,
    tmp_path: Path,
    capsys,
):
    closure_path = tmp_path / "cierre.json"
    closure_path.write_text(
        json.dumps(_closure(activity="clase_04"), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "asignaciones_revision.md"

    exit_code = cli.main(
        [
            "renderizar-asignaciones",
            "--config",
            str(config_path),
            "--cierre",
            str(closure_path),
            "--salida",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == f"Asignaciones de clase_04 guardadas en {output}."
    assert captured.err == ""
    assert output.read_text(encoding="utf-8").startswith(
        "<!-- Generado automáticamente por docencia-tools. No editar manualmente. -->"
    )
    assert "| Revisor | Entrega a revisar | PR |" in output.read_text(encoding="utf-8")


def test_cli_invalid_closure_does_not_write_output(
    config_path: Path,
    tmp_path: Path,
    capsys,
):
    closure_path = tmp_path / "cierre.json"
    closure_path.write_text("[]", encoding="utf-8")
    output = tmp_path / "asignaciones_revision.md"

    exit_code = cli.main(
        [
            "renderizar-asignaciones",
            "--config",
            str(config_path),
            "--cierre",
            str(closure_path),
            "--salida",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 10
    assert "[infrastructure_error]" in captured.err
    assert not output.exists()
