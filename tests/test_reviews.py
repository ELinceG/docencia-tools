from datetime import datetime, timedelta, timezone

from docencia_tools.reviews import Comment, Commit, Review, analyze_review_cycle


NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
EVIDENCE = frozenset({"changes", "files", "tests", "observations"})


def review(state="APPROVED", when=NOW):
    return Review("revisor", state, when, "Revisé cambios, archivos, pruebas y observaciones.", "a", EVIDENCE)


def test_approve_requires_reply_but_not_commit():
    without_reply = analyze_review_cycle(
        assigned_reviewer="revisor", author="autor", reviews=[review()], comments=[], commits=[], review_deadline=NOW + timedelta(hours=1)
    )
    with_reply = analyze_review_cycle(
        assigned_reviewer="revisor",
        author="autor",
        reviews=[review()],
        comments=[Comment("autor", NOW + timedelta(minutes=5), "Gracias, revisado.")],
        commits=[],
        review_deadline=NOW + timedelta(hours=1),
    )
    assert not without_reply.reply_complete
    assert with_reply.reply_complete


def test_request_changes_requires_reply_and_later_commit():
    result = analyze_review_cycle(
        assigned_reviewer="revisor",
        author="autor",
        reviews=[review("CHANGES_REQUESTED")],
        comments=[Comment("autor", NOW + timedelta(minutes=5), "Corregido.")],
        commits=[Commit("b", NOW + timedelta(minutes=6))],
        review_deadline=NOW + timedelta(hours=1),
    )
    assert result.reply_complete
    assert result.reply_commits == ("b",)


def test_second_review_after_reply_commit_counts_as_extra():
    result = analyze_review_cycle(
        assigned_reviewer="revisor",
        author="autor",
        reviews=[review("CHANGES_REQUESTED"), review("CHANGES_REQUESTED", NOW + timedelta(minutes=10))],
        comments=[Comment("autor", NOW + timedelta(minutes=5), "Corregido.")],
        commits=[Commit("b", NOW + timedelta(minutes=6))],
        review_deadline=NOW + timedelta(hours=1),
    )
    assert result.second_review == "CHANGES_REQUESTED"
    assert result.extra


def test_normal_comment_does_not_replace_review():
    result = analyze_review_cycle(
        assigned_reviewer="revisor",
        author="autor",
        reviews=[],
        comments=[Comment("revisor", NOW, "Todo bien")],
        commits=[],
        review_deadline=NOW + timedelta(hours=1),
    )
    assert not result.review_complete
