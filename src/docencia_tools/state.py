"""Formato persistente público y separación de hechos históricos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_SCHEMA_VERSION = 1


def build_state(
    *,
    activity: str,
    student: str | None,
    pr_number: int,
    head_sha: str,
    merge_base: str,
    trusted_ref: str,
    first_complete: dict[str, object] | None,
    general_deadline: str | None,
    applied_deadline: str | None,
    punctuality: str,
    reviewable: bool,
    current_errors: list[str],
    historical_facts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "activity": activity,
        "student": student,
        "pull_request": pr_number,
        "head_sha": head_sha,
        "merge_base": merge_base,
        "trusted_ref": trusted_ref,
        "first_complete_at": first_complete,
        "general_deadline": general_deadline,
        "applied_deadline": applied_deadline,
        "punctuality": punctuality,
        "reviewable": reviewable,
        "current_errors": sorted(set(current_errors)),
        "historical_facts": sorted(set(historical_facts or [])),
        "exception": None,
        "assignment": None,
        "seed": None,
        "review": None,
        "review_timestamp": None,
        "reply_complete": False,
        "reply_commits": [],
        "second_review": None,
        "extra": False,
    }


def write_state(path: str | Path, state: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
