from dataclasses import replace
from pathlib import Path

from docencia_tools.config import TechnicalCheck, TechnicalValidation
from docencia_tools.errors import FailureKind
from docencia_tools.technical import run_technical_checks


def test_python_compile_is_implementation_error(activity, tmp_path: Path):
    target = tmp_path / "entregas/ana-perez/clase_04"
    target.mkdir(parents=True)
    (target / "actividad.py").write_text("def rota(:\n", encoding="utf-8")
    configured = replace(
        activity,
        technical=TechnicalValidation(checks=(TechnicalCheck("python_compile", path="entregas/{slug}/clase_04/actividad.py"),)),
    )
    issue = run_technical_checks(configured, slug="ana-perez", head_root=tmp_path, trusted_root=tmp_path)[0]
    assert issue.kind == FailureKind.IMPLEMENTATION


def test_declared_command_is_academic_validation_error(activity, tmp_path: Path):
    configured = replace(
        activity,
        technical=TechnicalValidation(checks=(TechnicalCheck("command", command=("{python}", "-c", "raise SystemExit(1)")),)),
    )
    issue = run_technical_checks(configured, slug="ana-perez", head_root=tmp_path, trusted_root=tmp_path)[0]
    assert issue.kind == FailureKind.ACADEMIC_VALIDATION
