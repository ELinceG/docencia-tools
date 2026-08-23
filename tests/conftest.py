from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from docencia_tools.config import load_activity


SECTIONS = [
    "Descripción",
    "Archivos modificados",
    "Trabajo realizado",
    "Verificación realizada",
    "Dudas o dificultades",
    "Lista de verificación",
]


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    data = {
        "schema_version": 1,
        "activity": "clase_04",
        "enabled": True,
        "timezone": "America/Mexico_City",
        "expected_base": "main",
        "branch_pattern": "clase-04/{slug}",
        "required_files": ["entregas/{slug}/clase_04/actividad_clase_04.md"],
        "allowed_files": [
            "entregas/{slug}/clase_04/actividad_clase_04.md",
            "entregas/{slug}/clase_04/imgs/*.png",
        ],
        "reviewers_per_submission": 1,
        "deadlines": {
            "delivery": "2026-08-23T23:59:00-06:00",
            "review": "2026-08-25T23:59:00-06:00",
            "reply": "2026-08-27T23:59:00-06:00",
        },
        "pull_request": {
            "title_tolerance_minutes": 5,
            "checklist_items": 6,
            "required_sections": SECTIONS,
        },
        "technical_validation": {"dependencies": [], "checks": []},
    }
    path = tmp_path / "activity.yml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def activity(config_path: Path):
    return load_activity(config_path)


@pytest.fixture
def valid_body() -> str:
    paragraphs = [
        "## Descripción\n\nEntrega terminada.",
        "## Archivos modificados\n\nactividad_clase_04.md",
        "## Trabajo realizado\n\nResolví la actividad.",
        "## Verificación realizada\n\nRevisé el diff y las pruebas.",
        "## Dudas o dificultades\n\nNo tuve dificultades.",
        "## Lista de verificación\n\n" + "\n".join(f"- [x] Verificación {number}." for number in range(1, 7)),
    ]
    return "\n\n".join(paragraphs)
