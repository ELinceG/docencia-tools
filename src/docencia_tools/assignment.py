"""Asignación reproducible de revisiones con restricciones duras y blandas."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterable


class AssignmentImpossible(ValueError):
    def __init__(self, message: str, diagnostics: dict[str, object]):
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class AssignmentConstraints:
    reviewers_per_submission: int = 1
    exempt_reviewing: frozenset[str] = frozenset()
    exempt_receiving: frozenset[str] = frozenset()
    incompatible_groups: tuple[frozenset[str], ...] = ()
    incompatible_pairs: frozenset[frozenset[str]] = frozenset()
    directed_forbidden: frozenset[tuple[str, str]] = frozenset()
    avoid: frozenset[tuple[str, str]] = frozenset()
    forced: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AssignmentResult:
    seed: str
    pairs: tuple[tuple[str, str], ...]
    avoided_pairs_used: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "pairs": [{"reviewer": reviewer, "author": author} for reviewer, author in self.pairs],
            "avoided_pairs_used": [{"reviewer": reviewer, "author": author} for reviewer, author in self.avoided_pairs_used],
        }


def _stable_rank(seed: str, *values: str) -> str:
    return hashlib.sha256("\0".join((seed, *values)).encode()).hexdigest()


def _hard_reason(reviewer: str, author: str, constraints: AssignmentConstraints) -> str | None:
    if reviewer == author:
        return "auto-revisión"
    if frozenset((reviewer, author)) in constraints.incompatible_pairs:
        return "par incompatible"
    if (reviewer, author) in constraints.directed_forbidden:
        return "restricción dirigida"
    if any({reviewer, author} <= group for group in constraints.incompatible_groups):
        return "grupo incompatible"
    return None


def assign_reviews(participants: Iterable[str], seed: str | int, constraints: AssignmentConstraints) -> AssignmentResult:
    seed_text = str(seed)
    unique = sorted(set(participants))
    reviewers = [person for person in unique if person not in constraints.exempt_reviewing]
    authors = [person for person in unique if person not in constraints.exempt_receiving]
    if not reviewers or not authors:
        raise AssignmentImpossible("No hay revisores o autores elegibles.", {"reviewers": reviewers, "authors": authors})
    required = constraints.reviewers_per_submission
    if required < 1:
        raise AssignmentImpossible("El número de revisores debe ser positivo.", {"reviewers_per_submission": required})

    pairs: set[tuple[str, str]] = set()
    load = {reviewer: 0 for reviewer in reviewers}
    count_by_author = {author: 0 for author in authors}
    conflicts: list[dict[str, str]] = []
    for reviewer, author in constraints.forced:
        if reviewer not in reviewers or author not in authors:
            conflicts.append({"reviewer": reviewer, "author": author, "reason": "persona exenta o desconocida"})
            continue
        reason = _hard_reason(reviewer, author, constraints)
        if reason:
            conflicts.append({"reviewer": reviewer, "author": author, "reason": reason})
            continue
        if (reviewer, author) not in pairs:
            pairs.add((reviewer, author))
            load[reviewer] += 1
            count_by_author[author] += 1
    overfilled = [author for author, count in count_by_author.items() if count > required]
    if conflicts or overfilled:
        raise AssignmentImpossible(
            "Una asignación forzada contradice la configuración dura.",
            {"forced_conflicts": conflicts, "overfilled_authors": overfilled},
        )

    slots = [author for author in authors for _ in range(required - count_by_author[author])]
    slots.sort(key=lambda author: _stable_rank(seed_text, "slot", author, str(count_by_author[author])))
    candidate_map: dict[str, list[str]] = {}
    for author in authors:
        candidates = [
            reviewer
            for reviewer in reviewers
            if (reviewer, author) not in pairs and _hard_reason(reviewer, author, constraints) is None
        ]
        candidate_map[author] = candidates
        if len(candidates) + count_by_author[author] < required:
            raise AssignmentImpossible(
                "No existe una asignación que satisfaga las restricciones duras.",
                {
                    "authors_without_candidates": [author],
                    "candidates": {author: candidates},
                    "hard_restrictions": _restriction_summary(author, reviewers, constraints),
                },
            )

    solution: set[tuple[str, str]] | None = None

    def search(index: int, *, allow_avoids: bool) -> bool:
        nonlocal solution
        if index == len(slots):
            solution = set(pairs)
            return True
        author = slots[index]
        candidates = [
            reviewer
            for reviewer in candidate_map[author]
            if (reviewer, author) not in pairs
            and (allow_avoids or (reviewer, author) not in constraints.avoid)
        ]
        candidates.sort(
            key=lambda reviewer: (
                load[reviewer],
                _stable_rank(seed_text, reviewer, author, str(index)),
            )
        )
        for reviewer in candidates:
            pair = (reviewer, author)
            pairs.add(pair)
            load[reviewer] += 1
            if search(index + 1, allow_avoids=allow_avoids):
                return True
            load[reviewer] -= 1
            pairs.remove(pair)
        return False

    if not search(0, allow_avoids=False):
        search(0, allow_avoids=True)
    if solution is None:
        raise AssignmentImpossible(
            "No existe una asignación que satisfaga todas las restricciones.",
            {
                "candidates": candidate_map,
                "hard_restrictions": {author: _restriction_summary(author, reviewers, constraints) for author in authors},
            },
        )
    final_pairs = tuple(sorted(solution))
    avoided = tuple(pair for pair in final_pairs if pair in constraints.avoid)
    return AssignmentResult(seed_text, final_pairs, avoided)


def _restriction_summary(author: str, reviewers: list[str], constraints: AssignmentConstraints) -> dict[str, str]:
    return {
        reviewer: reason
        for reviewer in reviewers
        if (reason := _hard_reason(reviewer, author, constraints)) is not None
    }


def constraints_from_private(data: dict[str, object], reviewers_per_submission: int) -> AssignmentConstraints:
    def names(key: str) -> frozenset[str]:
        value = data.get(key, [])
        return frozenset(str(item) for item in value) if isinstance(value, list) else frozenset()

    def pairs(key: str, directed: bool) -> frozenset:
        value = data.get(key, [])
        parsed = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, list) and len(item) == 2:
                    parsed.append(tuple(map(str, item)) if directed else frozenset(map(str, item)))
        return frozenset(parsed)

    groups_raw = data.get("incompatible_groups", [])
    groups = tuple(frozenset(map(str, group)) for group in groups_raw if isinstance(group, list)) if isinstance(groups_raw, list) else ()
    forced_raw = data.get("forced_assignments", [])
    forced = tuple(tuple(map(str, pair)) for pair in forced_raw if isinstance(pair, list) and len(pair) == 2) if isinstance(forced_raw, list) else ()
    return AssignmentConstraints(
        reviewers_per_submission=reviewers_per_submission,
        exempt_reviewing=names("exempt_from_reviewing"),
        exempt_receiving=names("exempt_from_receiving_review"),
        incompatible_groups=groups,
        incompatible_pairs=pairs("incompatible_pairs", False),
        directed_forbidden=pairs("directed_forbidden", True),
        avoid=pairs("avoid", True),
        forced=forced,
    )


def eligible_participants(states: Iterable[dict[str, object]]) -> list[str]:
    """Incluye automáticamente solo entregas puntuales y revisables."""

    return sorted(
        {
            str(state["student"])
            for state in states
            if state.get("punctuality") == "on_time"
            and state.get("reviewable") is True
            and isinstance(state.get("student"), str)
        }
    )
