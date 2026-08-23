from datetime import datetime
from zoneinfo import ZoneInfo

from docencia_tools.private import policy_for_student


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
        general_deadline=datetime(2026, 8, 23, 23, 59, tzinfo=ZoneInfo("America/Mexico_City")),
        timezone="America/Mexico_City",
    )
    assert policy.exception_applied
    assert policy.exempt_from_reviewing
    assert not policy.exempt_from_receiving_review
    assert "reason" not in policy.public_summary()
