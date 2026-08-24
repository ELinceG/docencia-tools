"""Herramientas reusables para automatización docente."""

from .closure import ClosureResult, close_delivery, consolidate_equivalent_states
from .config import ActivityConfig, load_activity
from .render import render_peer_review_markdown

__all__ = [
    "ActivityConfig",
    "ClosureResult",
    "close_delivery",
    "consolidate_equivalent_states",
    "load_activity",
    "render_peer_review_markdown",
]
__version__ = "0.1.4"
