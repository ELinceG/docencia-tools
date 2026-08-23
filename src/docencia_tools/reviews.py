"""Evaluación del ciclo review, réplica y segunda review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


VALID_STATES = {"APPROVED", "CHANGES_REQUESTED"}


@dataclass(frozen=True)
class Review:
    reviewer: str
    state: str
    submitted_at: datetime
    body: str
    commit_sha: str
    evidence: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Comment:
    author: str
    created_at: datetime
    body: str


@dataclass(frozen=True)
class Commit:
    sha: str
    committed_at: datetime


@dataclass(frozen=True)
class ReviewCycle:
    review_complete: bool
    review_late: bool
    reply_complete: bool
    reply_commits: tuple[str, ...]
    second_review: str | None
    extra: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "review_complete": self.review_complete,
            "review_late": self.review_late,
            "reply_complete": self.reply_complete,
            "reply_commits": list(self.reply_commits),
            "second_review": self.second_review,
            "extra": self.extra,
            "reason": self.reason,
        }


def analyze_review_cycle(
    *,
    assigned_reviewer: str,
    author: str,
    reviews: list[Review],
    comments: list[Comment],
    commits: list[Commit],
    review_deadline: datetime,
) -> ReviewCycle:
    candidates = sorted(
        (review for review in reviews if review.reviewer == assigned_reviewer and review.state in VALID_STATES),
        key=lambda review: review.submitted_at,
    )
    if not candidates:
        return ReviewCycle(False, False, False, (), None, False, "No existe una GitHub Pull Request Review válida del revisor asignado.")
    first = candidates[0]
    required_evidence = {"changes", "files", "tests", "observations"}
    if not first.body.strip() or not required_evidence <= set(first.evidence):
        return ReviewCycle(False, first.submitted_at > review_deadline, False, (), None, False, "La review no incluye evidencia breve de cambios, archivos, pruebas y observaciones.")
    replies = sorted(
        (comment for comment in comments if comment.author == author and comment.created_at > first.submitted_at and comment.body.strip()),
        key=lambda comment: comment.created_at,
    )
    reply_exists = bool(replies)
    later_commits = tuple(commit.sha for commit in sorted(commits, key=lambda commit: commit.committed_at) if commit.committed_at > first.submitted_at)
    reply_complete = reply_exists and (first.state == "APPROVED" or bool(later_commits))
    second: Review | None = None
    if first.state == "CHANGES_REQUESTED" and reply_complete:
        last_commit_time = max(commit.committed_at for commit in commits if commit.sha in later_commits)
        second = next((review for review in candidates[1:] if review.submitted_at > last_commit_time), None)
    return ReviewCycle(
        review_complete=True,
        review_late=first.submitted_at > review_deadline,
        reply_complete=reply_complete,
        reply_commits=later_commits,
        second_review=second.state if second else None,
        extra=second is not None,
        reason=(
            "Ciclo completo."
            if reply_complete
            else "Approve requiere respuesta del autor; Request changes requiere respuesta y al menos un commit posterior."
        ),
    )
