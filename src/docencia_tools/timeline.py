"""El cron aporta la hora; Python decide la fase desde YAML."""

from __future__ import annotations

from datetime import datetime

from .config import ActivityConfig
from .errors import InfrastructureError


def academic_phase(config: ActivityConfig, now: datetime) -> str:
    if not config.enabled:
        return "disabled"
    delivery = config.deadlines.delivery
    review = config.deadlines.review
    reply = config.deadlines.reply
    if delivery is None or review is None or reply is None:
        raise InfrastructureError("Una actividad habilitada necesita todos sus deadlines.")
    local_now = now.astimezone(delivery.tzinfo)
    if local_now <= delivery:
        return "delivery"
    if local_now <= review:
        return "review"
    if local_now <= reply:
        return "reply"
    return "closed"
