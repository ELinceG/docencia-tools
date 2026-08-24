"""Herramientas reusables para automatización docente."""

from .closure import ClosureResult, close_delivery
from .config import ActivityConfig, load_activity

__all__ = ["ActivityConfig", "ClosureResult", "close_delivery", "load_activity"]
__version__ = "0.1.2"
