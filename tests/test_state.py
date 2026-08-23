from docencia_tools.state import build_state


def test_state_contains_public_audit_fields_without_private_reason():
    state = build_state(
        activity="clase_04",
        student="ana-perez",
        pr_number=12,
        head_sha="a" * 40,
        merge_base="b" * 40,
        trusted_ref="trusted/main",
        first_complete={"timestamp": "2026-08-23T20:00:00-06:00", "sha": "a" * 40, "source": "github_webhook"},
        general_deadline="2026-08-23T23:59:00-06:00",
        applied_deadline="2026-08-24T23:59:00-06:00",
        punctuality="on_time",
        reviewable=True,
        current_errors=[],
    )
    expected = {
        "activity",
        "student",
        "pull_request",
        "first_complete_at",
        "general_deadline",
        "applied_deadline",
        "punctuality",
        "reviewable",
        "current_errors",
        "historical_facts",
        "exception",
        "assignment",
        "seed",
        "review",
        "review_timestamp",
        "reply_complete",
        "reply_commits",
        "second_review",
        "extra",
    }
    assert expected <= state.keys()
    assert "reason" not in state
