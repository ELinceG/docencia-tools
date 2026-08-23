from pathlib import Path

import pytest

from docencia_tools.config import load_activity
from docencia_tools.errors import InfrastructureError
from docencia_tools.technical import write_requirements


def test_loads_valid_config(activity):
    assert activity.activity == "clase_04"
    assert activity.deadlines.delivery.isoformat() == "2026-08-23T23:59:00-06:00"


def test_enabled_activity_requires_deadlines(config_path: Path):
    text = config_path.read_text(encoding="utf-8").replace("2026-08-23T23:59:00-06:00", "PENDIENTE")
    config_path.write_text(text, encoding="utf-8")
    with pytest.raises(InfrastructureError, match="obligatorio"):
        load_activity(config_path)


def test_requirements_are_materialized_from_trusted_config(activity, tmp_path: Path):
    object.__setattr__(activity.technical, "dependencies", ("numpy>=2", "PyYAML>=6,<7"))
    output = tmp_path / "requirements.txt"
    write_requirements(activity, output)
    assert output.read_text(encoding="utf-8") == "numpy>=2\nPyYAML>=6,<7\n"


def test_requirements_reject_shell_syntax(activity, tmp_path: Path):
    object.__setattr__(activity.technical, "dependencies", ("numpy; touch /tmp/x",))
    with pytest.raises(InfrastructureError, match="Dependencias inválidas"):
        write_requirements(activity, tmp_path / "requirements.txt")
