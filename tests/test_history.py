from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from docencia_tools.history import Observation, clamp_to_pr_creation, first_complete_at


TZ = ZoneInfo("America/Mexico_City")


def test_first_complete_uses_first_snapshot_with_all_required_files(activity):
    start = datetime(2026, 8, 23, 20, 0, tzinfo=TZ)
    required = "entregas/ana-perez/clase_04/actividad_clase_04.md"
    observations = [
        Observation("a" * 40, start, frozenset(), "github_webhook", False),
        Observation("b" * 40, start + timedelta(hours=4), frozenset({required}), "github_webhook", False),
        Observation("c" * 40, start + timedelta(hours=5), frozenset({required}), "github_webhook", False),
    ]
    result = first_complete_at(activity, "ana-perez", observations)
    assert result.sha == "b" * 40
    assert result.timestamp == start + timedelta(hours=4)
    assert not result.approximate


def test_delivery_can_be_late_even_if_pr_opened_early(activity):
    deadline = activity.deadlines.delivery
    required = "entregas/ana-perez/clase_04/actividad_clase_04.md"
    result = first_complete_at(
        activity,
        "ana-perez",
        [
            Observation("a", deadline - timedelta(hours=2), frozenset(), "github_webhook"),
            Observation("b", deadline + timedelta(minutes=11), frozenset({required}), "github_webhook"),
        ],
    )
    assert result.timestamp > deadline


def test_incomplete_history_returns_none(activity):
    assert first_complete_at(activity, "ana-perez", [Observation("a", activity.deadlines.delivery, frozenset(), "git")]) is None


def test_commit_before_pr_creation_is_clamped_to_pr_creation():
    created = datetime(2026, 8, 23, 20, 0, tzinfo=TZ)
    original = Observation("a", created - timedelta(days=1), frozenset({"x"}), "git_commit_committer_timestamp", True)
    adjusted = clamp_to_pr_creation([original], created)[0]
    assert adjusted.observed_at == created
    assert adjusted.source.endswith("clamped_to_pr_created_at")
