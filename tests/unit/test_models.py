from __future__ import annotations

"""Tests for backend/models.py and backend/exceptions.py."""

import pytest

from backend.exceptions import AIError, CaptureError, ConfigError
from backend.models import GameState, Quote, TriggerSource


# ---------------------------------------------------------------------------
# TriggerSource enum
# ---------------------------------------------------------------------------


class TestTriggerSource:
    def test_timer_value(self) -> None:
        assert TriggerSource.TIMER.value == "timer"

    def test_hotkey_value(self) -> None:
        assert TriggerSource.HOTKEY.value == "hotkey"

    def test_manual_value(self) -> None:
        assert TriggerSource.MANUAL.value == "manual"

    def test_all_members_present(self) -> None:
        members = {m.value for m in TriggerSource}
        assert members == {"timer", "hotkey", "manual"}


# ---------------------------------------------------------------------------
# GameState dataclass
# ---------------------------------------------------------------------------


class TestGameState:
    def test_required_fields(self) -> None:
        gs = GameState(screenshot_b64="b64data", window_title="AoE2")
        assert gs.screenshot_b64 == "b64data"
        assert gs.window_title == "AoE2"

    def test_equality_on_same_values(self) -> None:
        gs1 = GameState(screenshot_b64="x", window_title="Win")
        gs2 = GameState(screenshot_b64="x", window_title="Win")
        assert gs1 == gs2

    def test_inequality_on_different_values(self) -> None:
        gs1 = GameState(screenshot_b64="x", window_title="Win")
        gs2 = GameState(screenshot_b64="y", window_title="Win")
        assert gs1 != gs2


# ---------------------------------------------------------------------------
# Quote dataclass
# ---------------------------------------------------------------------------


class TestQuote:
    def test_required_field(self) -> None:
        q = Quote(text="Know thy enemy.")
        assert q.text == "Know thy enemy."

    def test_equality_on_same_text(self) -> None:
        q1 = Quote(text="Same text.")
        q2 = Quote(text="Same text.")
        assert q1 == q2

    def test_inequality_on_different_text(self) -> None:
        q1 = Quote(text="Text A")
        q2 = Quote(text="Text B")
        assert q1 != q2


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_capture_error_is_exception(self) -> None:
        exc = CaptureError("window not found")
        assert isinstance(exc, Exception)
        assert str(exc) == "window not found"

    def test_ai_error_is_exception(self) -> None:
        exc = AIError("api failed")
        assert isinstance(exc, Exception)
        assert str(exc) == "api failed"

    def test_config_error_is_exception(self) -> None:
        exc = ConfigError("bad json")
        assert isinstance(exc, Exception)
        assert str(exc) == "bad json"

    def test_capture_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(CaptureError, match="window not found"):
            raise CaptureError("window not found")

    def test_ai_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(AIError, match="api failed"):
            raise AIError("api failed")

    def test_config_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(ConfigError, match="bad json"):
            raise ConfigError("bad json")

    def test_exceptions_are_distinct_types(self) -> None:
        assert CaptureError is not AIError
        assert AIError is not ConfigError
        assert CaptureError is not ConfigError
