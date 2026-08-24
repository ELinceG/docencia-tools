from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from docencia_tools.config import load_private
from docencia_tools.errors import InfrastructureError
from docencia_tools.private import policy_for_student


GENERAL_DEADLINE = datetime(2026, 8, 23, 23, 59, tzinfo=ZoneInfo("America/Mexico_City"))


def _policy(deadline):
    return policy_for_student(
        {
            "deadline_overrides": [
                {
                    "activity": "clase_04",
                    "student": "ana-perez",
                    "deadline": deadline,
                }
            ]
        },
        activity="clase_04",
        student="ana-perez",
        general_deadline=GENERAL_DEADLINE,
        timezone="America/Mexico_City",
    )


def test_private_deadline_and_exemptions_are_applied_without_reason():
    private = {
        "deadline_overrides": [
            {
                "activity": "clase_04",
                "student": "ana-perez",
                "deadline": "2026-08-25T23:59:00-06:00",
                "reason": "dato privado que no debe salir",
            }
        ],
        "exempt_from_reviewing": ["ana-perez"],
        "exempt_from_receiving_review": [],
    }
    policy = policy_for_student(
        private,
        activity="clase_04",
        student="ana-perez",
        general_deadline=GENERAL_DEADLINE,
        timezone="America/Mexico_City",
    )
    assert policy.exception_applied
    assert policy.exempt_from_reviewing
    assert not policy.exempt_from_receiving_review
    assert "reason" not in policy.public_summary()


def test_private_deadline_accepts_iso_string():
    policy = _policy("2026-08-24T00:05:00-06:00")

    assert policy.applied_deadline.isoformat() == "2026-08-24T00:05:00-06:00"


def test_private_deadline_accepts_native_aware_datetime_from_yaml(tmp_path: Path):
    path = tmp_path / "private.yml"
    path.write_text(
        """deadline_overrides:
  - activity: clase_04
    student: ana-perez
    deadline: 2026-08-24T00:05:00-06:00
""",
        encoding="utf-8",
    )
    private = load_private(path)
    native = private["deadline_overrides"][0]["deadline"]

    assert isinstance(native, datetime)
    policy = policy_for_student(
        private,
        activity="clase_04",
        student="ana-perez",
        general_deadline=GENERAL_DEADLINE,
        timezone="America/Mexico_City",
    )
    assert policy.applied_deadline.isoformat() == "2026-08-24T00:05:00-06:00"


def test_string_and_native_private_deadlines_are_equivalent():
    native = datetime(2026, 8, 24, 0, 5, tzinfo=timezone(timedelta(hours=-6)))

    assert _policy("2026-08-24T00:05:00-06:00").applied_deadline == _policy(native).applied_deadline


def test_naive_private_datetime_uses_activity_timezone():
    policy = _policy(datetime(2026, 8, 24, 0, 5))

    assert policy.applied_deadline.tzinfo == ZoneInfo("America/Mexico_City")
    assert policy.applied_deadline.isoformat() == "2026-08-24T00:05:00-06:00"


def test_private_date_without_time_is_rejected():
    with pytest.raises(InfrastructureError, match="timestamp ISO 8601"):
        _policy(date(2026, 8, 24))


def test_invalid_private_deadline_type_is_rejected():
    with pytest.raises(InfrastructureError, match="timestamp ISO 8601"):
        _policy(12345)
