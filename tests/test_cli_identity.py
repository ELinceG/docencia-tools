from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from docencia_tools import cli
from docencia_tools.history import Observation


def test_cli_propagates_protocol_identity_to_history_state_and_technical_checks(
    activity,
    valid_body,
    tmp_path: Path,
    monkeypatch,
):
    config = replace(
        activity,
        activity="clase_02",
        branch_pattern="clase-02/{slug}",
        required_files=("entregas/{slug}/clase_02/actividad_clase_02.md",),
        allowed_files=("entregas/{slug}/clase_02/actividad_clase_02.md",),
    )
    canonical_file = "entregas/leonardo-aguirre/clase_02/actividad_clase_02.md"
    created_at = datetime(2026, 8, 23, 14, 5, tzinfo=ZoneInfo("America/Mexico_City"))
    event = {
        "number": 42,
        "title": "[clase_02] leonardo-aguirre (domingo,23,agosto 14:05)",
        "body": valid_body,
        "created_at": created_at.isoformat(),
        "base": {"ref": "main"},
        "head": {"ref": "origin/clase-02/leonardo-aguirre", "sha": "a" * 40},
    }
    event_path = tmp_path / "pr.json"
    event_path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "state.json"
    observed_slugs: list[str] = []

    monkeypatch.setattr(cli, "load_activity", lambda _path: config)
    monkeypatch.setattr(
        cli,
        "observe_diff",
        lambda *_args: ("b" * 40, [canonical_file], {canonical_file}),
    )
    monkeypatch.setattr(
        cli,
        "observations_from_git",
        lambda *_args: [
            Observation(
                "a" * 40,
                created_at + timedelta(minutes=1),
                frozenset({canonical_file}),
                "github_webhook",
            )
        ],
    )

    def technical_checks(_config, *, slug, head_root, trusted_root):
        observed_slugs.append(slug)
        return []

    monkeypatch.setattr(cli, "run_technical_checks", technical_checks)
    args = argparse.Namespace(
        config="trusted.yml",
        evento=str(event_path),
        repo_head=str(tmp_path),
        trusted_root=str(tmp_path),
        trusted_ref="trusted/main",
        salida=str(output_path),
    )

    assert cli._validate_pr(args) == 2
    state = json.loads(output_path.read_text(encoding="utf-8"))
    assert state["student"] == "leonardo-aguirre"
    assert state["first_complete_at"]["sha"] == "a" * 40
    assert state["safe_to_execute_student_code"] is True
    assert observed_slugs == ["leonardo-aguirre"]
