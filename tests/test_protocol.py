from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from docencia_tools.protocol import validate_description, validate_protocol, validate_title


TZ = ZoneInfo("America/Mexico_City")


def test_valid_title(activity):
    created = datetime(2026, 8, 23, 14, 5, tzinfo=TZ)
    assert validate_title(activity, "[clase_04] ana-perez (domingo,23,agosto 14:05)", "ana-perez", created) == []


def test_title_accepts_exactly_five_minutes(activity):
    created = datetime(2026, 8, 23, 14, 10, tzinfo=TZ)
    assert validate_title(activity, "[clase_04] ana-perez (domingo,23,agosto 14:05)", "ana-perez", created) == []


def test_title_rejects_more_than_five_minutes(activity):
    created = datetime(2026, 8, 23, 14, 11, tzinfo=TZ)
    assert validate_title(activity, "[clase_04] ana-perez (domingo,23,agosto 14:05)", "ana-perez", created)[0].code == "error:titulo"


def test_title_rejects_incoherent_weekday(activity):
    created = datetime(2026, 8, 23, 14, 5, tzinfo=TZ)
    issue = validate_title(activity, "[clase_04] ana-perez (lunes,23,agosto 14:05)", "ana-perez", created)[0]
    assert "semana" in issue.message


def test_description_accepts_no_difficulties(activity, valid_body):
    assert validate_description(activity, valid_body) == []


def test_description_rejects_placeholder_and_unchecked(activity, valid_body):
    body = valid_body.replace("Entrega terminada.", "Resume brevemente el propósito de este cambio.").replace("[x]", "[ ]", 1)
    assert validate_description(activity, body)[0].code == "error:descripcion"


def _validate(activity, valid_body, **changes):
    values = {
        "branch": "clase-04/ana-perez",
        "base": "main",
        "title": "[clase_04] ana-perez (domingo,23,agosto 14:05)",
        "body": valid_body,
        "created_at": datetime(2026, 8, 23, 14, 5, tzinfo=TZ),
        "changed_files": ["entregas/ana-perez/clase_04/actividad_clase_04.md"],
        "head_files": {"entregas/ana-perez/clase_04/actividad_clase_04.md"},
    }
    values.update(changes)
    return validate_protocol(activity, **values)


def test_protocol_error_does_not_block_review(activity, valid_body):
    result = _validate(activity, valid_body, branch="mal-formada", title="incorrecto")
    assert result.reviewable
    assert {issue.code for issue in result.issues} >= {"error:rama", "error:titulo"}


def test_wrong_base_blocks_review(activity, valid_body):
    result = _validate(activity, valid_body, base="develop")
    assert not result.reviewable
    assert "error:base" in result.current_error_labels


def test_missing_file_blocks_review(activity, valid_body):
    result = _validate(activity, valid_body, head_files=set())
    assert not result.reviewable
    assert not result.safe_to_execute


def test_extra_file_blocks_execution_but_not_review(activity, valid_body):
    result = _validate(activity, valid_body, changed_files=["entregas/ana-perez/clase_04/actividad_clase_04.md", ".github/workflows/evil.yml"])
    assert result.reviewable
    assert not result.safe_to_execute
    assert "error:archivos-extra" in result.current_error_labels


def test_image_pattern_does_not_allow_nested_directories(activity, valid_body):
    result = _validate(
        activity,
        valid_body,
        changed_files=[
            "entregas/ana-perez/clase_04/actividad_clase_04.md",
            "entregas/ana-perez/clase_04/imgs/subdirectorio/figura.png",
        ],
    )
    assert "error:archivos-extra" in result.current_error_labels


def _class02(activity):
    return replace(
        activity,
        activity="clase_02",
        branch_pattern="clase-02/{slug}",
        required_files=("entregas/{slug}/clase_02/actividad_clase_02.md",),
        allowed_files=("entregas/{slug}/clase_02/actividad_clase_02.md",),
    )


def _validate_class02(activity, valid_body, *, branch, changed_files=None, head_files=None):
    canonical_file = "entregas/leonardo-aguirre/clase_02/actividad_clase_02.md"
    return validate_protocol(
        _class02(activity),
        branch=branch,
        base="main",
        title="[clase_02] leonardo-aguirre (domingo,23,agosto 14:05)",
        body=valid_body,
        created_at=datetime(2026, 8, 23, 14, 5, tzinfo=TZ),
        changed_files=changed_files or [canonical_file],
        head_files=head_files or {canonical_file},
    )


def test_prefixed_branch_does_not_contaminate_identity(activity, valid_body):
    result = _validate_class02(activity, valid_body, branch="origin/clase-02/leonardo-aguirre")
    assert result.slug == "leonardo-aguirre"
    assert "error:rama" in result.current_error_labels
    assert "error:propietario" not in result.current_error_labels
    assert "error:archivos-faltantes" not in result.current_error_labels
    assert result.reviewable
    assert result.safe_to_execute


def test_uppercase_branch_uses_identity_from_unique_path(activity, valid_body):
    result = _validate_class02(activity, valid_body, branch="Clase-02/Leonardo-Aguirre")
    assert result.slug == "leonardo-aguirre"
    assert "error:rama" in result.current_error_labels
    assert "error:propietario" not in result.current_error_labels


def test_different_branch_slug_is_only_branch_error(activity, valid_body):
    result = _validate_class02(activity, valid_body, branch="clase-02/otra-persona")
    assert result.slug == "leonardo-aguirre"
    assert "error:rama" in result.current_error_labels
    assert "error:propietario" not in result.current_error_labels
    assert result.reviewable


def test_two_real_delivery_slugs_are_ambiguous_and_block_execution(activity, valid_body):
    leonardo = "entregas/leonardo-aguirre/clase_02/actividad_clase_02.md"
    another = "entregas/otra-persona/clase_02/actividad_clase_02.md"
    result = _validate_class02(
        activity,
        valid_body,
        branch="clase-02/leonardo-aguirre",
        changed_files=[leonardo, another],
        head_files={leonardo, another},
    )
    assert result.slug is None
    assert "error:propietario" in result.current_error_labels
    assert not result.reviewable
    assert not result.safe_to_execute


def test_single_invalid_path_slug_is_not_reported_as_owner_ambiguity(activity, valid_body):
    invalid = "entregas/Leonardo-Aguirre/clase_02/actividad_clase_02.md"
    result = _validate_class02(
        activity,
        valid_body,
        branch="clase-02/leonardo-aguirre",
        changed_files=[invalid],
        head_files={invalid},
    )
    assert result.slug is None
    assert "error:propietario" not in result.current_error_labels
    assert "error:archivos-faltantes" in result.current_error_labels
    assert not result.reviewable
    assert not result.safe_to_execute


def test_correct_branch_and_unique_path_keep_existing_behavior(activity, valid_body):
    result = _validate_class02(activity, valid_body, branch="clase-02/leonardo-aguirre")
    assert result.slug == "leonardo-aguirre"
    assert result.issues == ()
    assert result.reviewable
    assert result.safe_to_execute
