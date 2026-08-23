from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from docencia_tools.config import load_activity, select_activity
from docencia_tools.errors import InfrastructureError
from docencia_tools.protocol import validate_protocol
from docencia_tools.technical import verify_dependencies


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / "src/docencia_tools/templates/validar_entrega.yml"


def test_workflow_prepares_each_job_before_validation():
    text = WORKFLOW.read_text(encoding="utf-8")
    setup = text.index("actions/setup-python@v6")
    install_tools = text.index("python -m pip install ./docencia-tools")
    install_declared = text.index("python -m pip install -r")
    validation = text.index("docencia-tools validar-pr")
    assert setup < install_tools < install_declared < validation
    assert "workflow_dispatch:" in text
    assert "pr_number:" in text
    assert "ref: v0.1.0" in text
    assert "--trusted-ref trusted/main" in text
    assert "repository: ${{ steps.pr.outputs.head_repo }}" in text


def test_validator_never_installs_dependencies():
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/docencia_tools").glob("*.py"))
    assert "pip install" not in source


def test_student_config_does_not_change_trusted_rules(config_path, valid_body, tmp_path):
    head = tmp_path / "head"
    (head / ".docencia").mkdir(parents=True)
    malicious = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    malicious["allowed_files"].append(".github/workflows/*")
    (head / ".docencia/activity.yml").write_text(yaml.safe_dump(malicious), encoding="utf-8")
    trusted = load_activity(config_path)
    result = validate_protocol(
        trusted,
        branch="clase-04/ana-perez",
        base="main",
        title="[clase_04] ana-perez (domingo,23,agosto 14:05)",
        body=valid_body,
        created_at=trusted.deadlines.delivery.replace(hour=14, minute=5),
        changed_files=["entregas/ana-perez/clase_04/actividad_clase_04.md", ".github/workflows/evil.yml"],
        head_files={"entregas/ana-perez/clase_04/actividad_clase_04.md", ".github/workflows/evil.yml"},
    )
    assert "error:archivos-extra" in result.current_error_labels
    assert not result.safe_to_execute


def test_selects_config_only_from_trusted_directory(config_path, tmp_path):
    directory = tmp_path / "activities"
    directory.mkdir()
    target = directory / "class.yml"
    target.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    assert select_activity(directory, "clase-04/ana-perez") == target


def test_clean_venv_can_run_config_validation(config_path, tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
    executable = venv / "bin/python"
    subprocess.run([str(executable), "-m", "pip", "install", "--no-deps", "-e", str(ROOT)], check=True, capture_output=True, text=True)
    result = subprocess.run([str(venv / "bin/docencia-tools"), "validar-config", "--config", str(config_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_missing_numpy_is_infrastructure_error(activity, monkeypatch):
    object.__setattr__(activity.technical, "dependencies", ("numpy",))

    def missing(_name):
        from importlib.metadata import PackageNotFoundError

        raise PackageNotFoundError

    monkeypatch.setattr("docencia_tools.technical.metadata.version", missing)
    with pytest.raises(InfrastructureError, match="workflow no preparó"):
        verify_dependencies(activity)
