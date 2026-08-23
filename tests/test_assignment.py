import pytest

from docencia_tools.assignment import AssignmentConstraints, AssignmentImpossible, assign_reviews, eligible_participants


def test_assignment_is_reproducible_and_prevents_self_review():
    participants = ["ana", "beto", "carla", "diego"]
    first = assign_reviews(participants, "clase-04", AssignmentConstraints())
    second = assign_reviews(reversed(participants), "clase-04", AssignmentConstraints())
    assert first == second
    assert all(reviewer != author for reviewer, author in first.pairs)


def test_assignment_supports_multiple_reviewers_and_incompatibilities():
    constraints = AssignmentConstraints(
        reviewers_per_submission=2,
        incompatible_groups=(frozenset({"ana", "beto"}),),
        incompatible_pairs=frozenset({frozenset({"carla", "diego"})}),
    )
    result = assign_reviews(["ana", "beto", "carla", "diego", "elena"], 42, constraints)
    assert len(result.pairs) == 10
    assert ("ana", "beto") not in result.pairs
    assert ("carla", "diego") not in result.pairs


def test_avoid_is_not_used_when_another_solution_exists():
    constraints = AssignmentConstraints(avoid=frozenset({("ana", "beto")}))
    result = assign_reviews(["ana", "beto", "carla"], "seed", constraints)
    assert ("ana", "beto") not in result.pairs
    assert result.avoided_pairs_used == ()


def test_exemptions_for_reviewing_and_receiving_are_independent():
    constraints = AssignmentConstraints(
        exempt_reviewing=frozenset({"ana"}),
        exempt_receiving=frozenset({"beto"}),
    )
    result = assign_reviews(["ana", "beto", "carla", "diego"], "seed", constraints)
    assert all(reviewer != "ana" for reviewer, _ in result.pairs)
    assert all(author != "beto" for _, author in result.pairs)


def test_forced_assignment_conflicting_with_hard_rule_fails():
    constraints = AssignmentConstraints(
        incompatible_pairs=frozenset({frozenset({"ana", "beto"})}),
        forced=(("ana", "beto"),),
    )
    with pytest.raises(AssignmentImpossible, match="forzada") as error:
        assign_reviews(["ana", "beto", "carla"], 1, constraints)
    assert error.value.diagnostics["forced_conflicts"][0]["reason"] == "par incompatible"


def test_impossible_assignment_has_candidate_diagnostics():
    constraints = AssignmentConstraints(incompatible_groups=(frozenset({"ana", "beto"}),))
    with pytest.raises(AssignmentImpossible) as error:
        assign_reviews(["ana", "beto"], 1, constraints)
    assert "candidates" in error.value.diagnostics


def test_only_on_time_reviewable_deliveries_are_eligible():
    states = [
        {"student": "ana", "punctuality": "on_time", "reviewable": True},
        {"student": "beto", "punctuality": "late", "reviewable": True},
        {"student": "carla", "punctuality": "on_time", "reviewable": False},
    ]
    assert eligible_participants(states) == ["ana"]
