from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TriggerSource(Enum):
    """Indicates what caused the capture-AI pipeline to fire."""

    TIMER = "timer"
    HOTKEY = "hotkey"
    MANUAL = "manual"


@dataclass
class GameState:
    """Snapshot of the game at the moment of capture.

    Passed from capture.py into ai_client.py; never use raw dicts across
    module boundaries.
    """

    screenshot_b64: str
    window_title: str


@dataclass
class Quote:
    """A single Sun Tzu commentary line produced by the AI.

    Passed from ai_client.py → queue.Queue → server.py.
    """

    text: str
