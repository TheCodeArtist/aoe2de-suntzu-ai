from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, call, patch

import pytest
from openai import APIConnectionError

from backend.ai_client import (
    ContextWindow,
    _call_llm,
    _extract_quote_text,
    _generate_quote_two_stage,
    _load_quotes,
    build_messages,
    generate_quote,
)
from backend.config_manager import AppConfig, TWO_STAGE_PRESET_NAME
from backend.exceptions import AIError
from backend.models import GameState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_config() -> AppConfig:
    return AppConfig(api_key="sk-test", model_name="gpt-4o")


@pytest.fixture()
def thinking_config() -> AppConfig:
    return AppConfig(api_key="sk-test", model_name="gpt-4o", enable_thinking=True)


@pytest.fixture()
def game_state() -> GameState:
    return GameState(screenshot_b64="abc123", window_title="AoE2")


@pytest.fixture()
def empty_context() -> ContextWindow:
    return ContextWindow(max_size=5)


def _mock_response(content: str) -> MagicMock:
    """Build a minimal mock that mimics an OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# ContextWindow
# ---------------------------------------------------------------------------


class TestContextWindow:
    def test_starts_empty(self) -> None:
        ctx = ContextWindow()
        assert ctx.get_recent() == []

    def test_add_single_quote(self) -> None:
        ctx = ContextWindow()
        ctx.add("Quote one")
        assert ctx.get_recent() == ["Quote one"]

    def test_fifo_eviction_at_max_size(self) -> None:
        ctx = ContextWindow(max_size=3)
        ctx.add("A")
        ctx.add("B")
        ctx.add("C")
        ctx.add("D")
        assert ctx.get_recent() == ["B", "C", "D"]

    def test_does_not_exceed_max_size(self) -> None:
        ctx = ContextWindow(max_size=5)
        for i in range(20):
            ctx.add(f"Quote {i}")
        assert len(ctx.get_recent()) == 5

    def test_get_recent_returns_copy(self) -> None:
        ctx = ContextWindow()
        ctx.add("original")
        result = ctx.get_recent()
        result.append("injected")
        assert ctx.get_recent() == ["original"]

    def test_clear_empties_all_quotes(self) -> None:
        ctx = ContextWindow()
        ctx.add("Q1")
        ctx.add("Q2")
        ctx.clear()
        assert ctx.get_recent() == []

    def test_max_size_property(self) -> None:
        ctx = ContextWindow(max_size=7)
        assert ctx.max_size == 7

    def test_thread_safety_no_race(self) -> None:
        ctx = ContextWindow(max_size=100)
        threads = [threading.Thread(target=lambda: ctx.add("x")) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(ctx.get_recent()) <= 100


# ---------------------------------------------------------------------------
# _load_quotes
# ---------------------------------------------------------------------------


class TestLoadQuotes:
    def test_loads_quotes_from_file(self) -> None:
        fake_data = {
            "chapters": [
                {"quotes": [{"text": "Quote A"}, {"text": "Quote B"}]},
                {"quotes": [{"text": "Quote C"}]},
            ]
        }
        import backend.ai_client as ai_mod

        original = ai_mod._ALL_QUOTES
        ai_mod._ALL_QUOTES = None  # force reload

        try:
            with patch(
                "backend.ai_client._QUOTES_PATH",
                new_callable=lambda: type(
                    "P", (), {"read_text": staticmethod(lambda **_: json.dumps(fake_data))}
                ),
            ):
                # Patch Path.read_text on the actual path object
                with patch("backend.ai_client._QUOTES_PATH") as mock_path:
                    mock_path.read_text.return_value = json.dumps(fake_data)
                    ai_mod._ALL_QUOTES = None
                    result = _load_quotes()
        finally:
            ai_mod._ALL_QUOTES = original

        assert "Quote A" in result
        assert "Quote B" in result
        assert "Quote C" in result

    def test_returns_empty_list_on_file_error(self) -> None:
        import backend.ai_client as ai_mod

        original = ai_mod._ALL_QUOTES
        ai_mod._ALL_QUOTES = None

        try:
            with patch("backend.ai_client._QUOTES_PATH") as mock_path:
                mock_path.read_text.side_effect = FileNotFoundError("missing")
                result = _load_quotes()
        finally:
            ai_mod._ALL_QUOTES = original

        assert result == []

    def test_cached_after_first_load(self) -> None:
        import backend.ai_client as ai_mod

        original = ai_mod._ALL_QUOTES
        ai_mod._ALL_QUOTES = ["cached"]

        try:
            result = _load_quotes()
        finally:
            ai_mod._ALL_QUOTES = original

        assert result == ["cached"]


# ---------------------------------------------------------------------------
# _call_llm
# ---------------------------------------------------------------------------


class TestCallLlm:
    def test_returns_content_on_success(self, default_config: AppConfig) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("The answer.")
        result = _call_llm(mock_client, default_config, [{"role": "user", "content": "hi"}])
        assert result == "The answer."

    def test_passes_extra_body_none_when_thinking_enabled(
        self, thinking_config: AppConfig
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        _call_llm(mock_client, thinking_config, [])
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] is None

    def test_passes_extra_body_with_thinking_disabled(
        self, default_config: AppConfig
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        _call_llm(mock_client, default_config, [])
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_raises_ai_error_on_openai_error(self, default_config: AppConfig) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )
        with pytest.raises(AIError, match="LLM request failed"):
            _call_llm(mock_client, default_config, [])

    def test_raises_ai_error_on_unexpected_exception(
        self, default_config: AppConfig
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")
        with pytest.raises(AIError, match="Unexpected LLM error"):
            _call_llm(mock_client, default_config, [])

    def test_raises_ai_error_on_empty_choices(self, default_config: AppConfig) -> None:
        mock_client = MagicMock()
        response = MagicMock()
        response.choices = []
        mock_client.chat.completions.create.return_value = response
        with pytest.raises(AIError, match="no choices"):
            _call_llm(mock_client, default_config, [])

    def test_returns_empty_string_when_content_is_none(
        self, default_config: AppConfig
    ) -> None:
        mock_client = MagicMock()
        message = MagicMock()
        message.content = None
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        mock_client.chat.completions.create.return_value = response
        result = _call_llm(mock_client, default_config, [])
        assert result == ""


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_returns_list_of_two_messages(self) -> None:
        msgs = build_messages("sys", "b64data", [])
        assert len(msgs) == 2

    def test_first_message_is_system_role(self) -> None:
        msgs = build_messages("You are Sun Tzu.", "b64data", [])
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are Sun Tzu."

    def test_second_message_is_user_role(self) -> None:
        msgs = build_messages("sys", "b64data", [])
        assert msgs[1]["role"] == "user"

    def test_user_content_has_text_and_image_parts(self) -> None:
        msgs = build_messages("sys", "b64data", [])
        user_content = msgs[1]["content"]
        types = [part["type"] for part in user_content]
        assert "text" in types
        assert "image_url" in types

    def test_image_url_contains_base64_data_uri(self) -> None:
        msgs = build_messages("sys", "mybase64==", [])
        image_part = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert "data:image/jpeg;base64,mybase64==" in image_part["image_url"]["url"]

    def test_recent_quotes_appear_in_text_part(self) -> None:
        msgs = build_messages("sys", "b64", ["Quote A", "Quote B"])
        text_part = next(p for p in msgs[1]["content"] if p["type"] == "text")
        assert "Quote A" in text_part["text"]
        assert "Quote B" in text_part["text"]

    def test_no_quotes_produces_placeholder_text(self) -> None:
        msgs = build_messages("sys", "b64", [])
        text_part = next(p for p in msgs[1]["content"] if p["type"] == "text")
        assert "No previous quotes" in text_part["text"]

    def test_no_think_suffix_appended_when_thinking_disabled(self) -> None:
        msgs = build_messages("sys", "b64", [], enable_thinking=False)
        text_part = next(p for p in msgs[1]["content"] if p["type"] == "text")
        assert "/no_think" in text_part["text"]

    def test_no_think_suffix_absent_when_thinking_enabled(self) -> None:
        msgs = build_messages("sys", "b64", [], enable_thinking=True)
        text_part = next(p for p in msgs[1]["content"] if p["type"] == "text")
        assert "/no_think" not in text_part["text"]


# ---------------------------------------------------------------------------
# _extract_quote_text
# ---------------------------------------------------------------------------


class TestExtractQuoteText:
    def test_extracts_from_json_dict(self) -> None:
        raw = json.dumps({"quote": "He who waits wins."})
        assert _extract_quote_text(raw) == "He who waits wins."

    def test_falls_back_to_plain_text(self) -> None:
        raw = "The supreme art of war is to subdue the enemy without fighting."
        assert _extract_quote_text(raw) == raw

    def test_strips_whitespace(self) -> None:
        raw = "  \n  A quote.  \n  "
        assert _extract_quote_text(raw) == "A quote."

    def test_handles_invalid_json_gracefully(self) -> None:
        raw = "{not valid json"
        assert _extract_quote_text(raw) == "{not valid json"

    def test_handles_json_without_quote_key(self) -> None:
        raw = json.dumps({"response": "something"})
        assert _extract_quote_text(raw) == raw.strip()

    def test_handles_empty_string(self) -> None:
        assert _extract_quote_text("") == ""

    def test_handles_json_with_non_string_quote(self) -> None:
        raw = json.dumps({"quote": 42})
        assert _extract_quote_text(raw) == "42"


# ---------------------------------------------------------------------------
# generate_quote — standard single-call path
# ---------------------------------------------------------------------------


class TestGenerateQuote:
    def test_returns_quote_string_on_success(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response(
            "Attack swiftly, but wisely."
        )
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            result = generate_quote(default_config, game_state, empty_context)
        assert result == "Attack swiftly, but wisely."

    def test_adds_quote_to_context(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response(
            "Idle villagers are idle swords."
        )
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            generate_quote(default_config, game_state, empty_context)
        assert "Idle villagers are idle swords." in empty_context.get_recent()

    def test_parses_json_response(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        json_content = json.dumps({"quote": "The wise farmer builds farms before battles."})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response(json_content)
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            result = generate_quote(default_config, game_state, empty_context)
        assert result == "The wise farmer builds farms before battles."

    def test_raises_ai_error_on_openai_exception(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            with pytest.raises(AIError, match="LLM request failed"):
                generate_quote(default_config, game_state, empty_context)

    def test_raises_ai_error_on_empty_response(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("")
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            with pytest.raises(AIError, match="empty response"):
                generate_quote(default_config, game_state, empty_context)

    def test_uses_correct_model_from_config(
        self, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        config = AppConfig(api_key="sk-x", model_name="llava")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("Knowledge is power.")
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            generate_quote(config, game_state, empty_context)
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "llava"

    def test_raises_ai_error_on_no_choices(
        self, default_config: AppConfig, game_state: GameState, empty_context: ContextWindow
    ) -> None:
        mock_client = MagicMock()
        response = MagicMock()
        response.choices = []
        mock_client.chat.completions.create.return_value = response
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            with pytest.raises(AIError, match="no choices"):
                generate_quote(default_config, game_state, empty_context)


# ---------------------------------------------------------------------------
# generate_quote — two-stage pipeline path
# ---------------------------------------------------------------------------


class TestGenerateQuoteTwoStage:
    @pytest.fixture()
    def two_stage_config(self) -> AppConfig:
        return AppConfig(
            api_key="sk-test",
            model_name="gpt-4o",
            system_prompt=TWO_STAGE_PRESET_NAME,
        )

    def _stub_two_stage(self, mock_client: MagicMock, stage1: str, stage2: str) -> None:
        """Wire mock_client so consecutive calls return stage1 then stage2 content."""
        mock_client.chat.completions.create.side_effect = [
            _mock_response(stage1),
            _mock_response(stage2),
        ]

    def test_two_stage_returns_quote(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        mock_client = MagicMock()
        self._stub_two_stage(
            mock_client,
            stage1="Player has 40 idle villagers and excess wood.",
            stage2="Disorder is born from order; idle hands waste both.",
        )
        fake_quotes = ["Quote X", "Quote Y", "Quote Z"]
        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=fake_quotes),
        ):
            result = generate_quote(two_stage_config, game_state, empty_context)
        assert result == "Disorder is born from order; idle hands waste both."

    def test_two_stage_adds_quote_to_context(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        mock_client = MagicMock()
        self._stub_two_stage(mock_client, "Description.", "The final quote.")
        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=["Q1", "Q2", "Q3"]),
        ):
            generate_quote(two_stage_config, game_state, empty_context)
        assert "The final quote." in empty_context.get_recent()

    def test_two_stage_raises_ai_error_when_quotes_unavailable(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("Some description.")
        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=[]),
        ):
            with pytest.raises(AIError, match="quotes file could not be loaded"):
                generate_quote(two_stage_config, game_state, empty_context)

    def test_two_stage_raises_ai_error_on_empty_stage1(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_response("")
        with patch("backend.ai_client.OpenAI", return_value=mock_client):
            with pytest.raises(AIError, match="empty description"):
                generate_quote(two_stage_config, game_state, empty_context)

    def test_two_stage_raises_ai_error_on_empty_final_quote(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        # Stage 1 returns a description, then all max_dedup_retries (default=3)
        # Stage 2 calls return empty strings.  The mock must supply enough
        # responses so it is never exhausted before the retry loop finishes.
        mock_client = MagicMock()
        max_retries = two_stage_config.max_dedup_retries  # 3 by default
        mock_client.chat.completions.create.side_effect = [
            _mock_response("Good description."),  # stage 1
            *[_mock_response("") for _ in range(max_retries)],  # all stage-2 retries
        ]
        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=["Q1", "Q2"]),
        ):
            with pytest.raises(AIError, match="empty quote"):
                generate_quote(two_stage_config, game_state, empty_context)

    def test_two_stage_excludes_recent_quotes_from_candidates(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
    ) -> None:
        """Recent quotes should be filtered from the candidate pool."""
        ctx = ContextWindow(max_size=5)
        ctx.add("Quote A")

        mock_client = MagicMock()
        all_quotes = ["Quote A", "Quote B", "Quote C"]
        captured_stage2_user: list[str] = []

        def capture_call(**kwargs):
            msgs = kwargs.get("messages", [])
            for m in msgs:
                if m.get("role") == "user" and isinstance(m.get("content"), str):
                    captured_stage2_user.append(m["content"])
            # First call returns description, second returns quote
            if len(captured_stage2_user) == 0:
                return _mock_response("Description.")
            return _mock_response("Quote B")

        mock_client.chat.completions.create.side_effect = [
            _mock_response("Description."),
            _mock_response("Quote B"),
        ]

        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=all_quotes),
        ):
            result = generate_quote(two_stage_config, game_state, ctx)

        assert result == "Quote B"

    def test_two_stage_no_think_suffix_in_stage1_when_disabled(
        self,
        two_stage_config: AppConfig,
        game_state: GameState,
        empty_context: ContextWindow,
    ) -> None:
        two_stage_config.enable_thinking = False
        mock_client = MagicMock()
        self._stub_two_stage(mock_client, "A description.", "A quote.")

        stage1_messages: list = []

        original_create = mock_client.chat.completions.create.side_effect

        def capture(**kwargs):
            stage1_messages.append(kwargs.get("messages", []))
            result = original_create[0] if stage1_messages else original_create[1]
            mock_client.chat.completions.create.side_effect = iter(
                [_mock_response("A description."), _mock_response("A quote.")]
            )
            return result

        with (
            patch("backend.ai_client.OpenAI", return_value=mock_client),
            patch("backend.ai_client._load_quotes", return_value=["Q1", "Q2", "Q3"]),
        ):
            generate_quote(two_stage_config, game_state, empty_context)

        first_call_messages = mock_client.chat.completions.create.call_args_list[0][1][
            "messages"
        ]
        user_content = first_call_messages[1]["content"]
        text_part = next(p for p in user_content if p["type"] == "text")
        assert "/no_think" in text_part["text"]
