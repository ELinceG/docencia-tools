"""Derivación y reconciliación de labels a partir del estado persistente."""

from __future__ import annotations


MANAGED_PREFIXES = ("entrega:", "revision:", "replica:", "error:")


def desired_labels(state: dict[str, object]) -> set[str]:
    labels: set[str] = set()
    punctuality = state.get("punctuality")
    reviewable = bool(state.get("reviewable"))
    if punctuality == "late":
        labels.add("entrega:tarde")
        labels.add("revision:profesor" if reviewable else "revision:no-revisable")
    elif punctuality == "on_time":
        labels.add("entrega:a-tiempo")
        labels.add("revision:pendiente" if reviewable else "revision:no-revisable")
    elif not reviewable:
        labels.add("revision:no-revisable")
    for error in state.get("current_errors", []):
        if isinstance(error, str) and error.startswith("error:"):
            labels.add(error)
    review = state.get("review")
    if isinstance(review, dict) and review.get("complete"):
        labels.discard("revision:pendiente")
        labels.discard("revision:asignada")
        labels.add("revision:completa")
        labels.add("replica:completa" if state.get("reply_complete") else "replica:pendiente")
    elif state.get("assignment"):
        labels.discard("revision:pendiente")
        labels.add("revision:asignada")
    return labels


def reconcile_labels(current: set[str], desired: set[str]) -> tuple[set[str], set[str]]:
    managed_current = {label for label in current if label.startswith(MANAGED_PREFIXES)}
    return desired - current, managed_current - desired
