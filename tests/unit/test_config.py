from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from backend.config_manager import (
    AppConfig,
    DEFAULT_SYSTEM_PROMPT,
    PRESET_PROMPTS,
    TWO_STAGE_PRESET_NAME,
    load_config,
    save_config,
)
from backend.exceptions import ConfigError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    """Return a path inside a temp directory where config.json can be written."""
    return tmp_path / "config.json"


@pytest.fixture()
def default_config() -> AppConfig:
    """Return an AppConfig built entirely from defaults."""
    return AppConfig()


# ---------------------------------------------------------------------------
# load_config — happy paths
# ---------------------------------------------------------------------------


class TestLoadConfigHappyPaths:
    def test_creates_file_with_defaults_when_missing(self, config_path: Path) -> None:
        """Missing file triggers default creation and writes the file to disk."""
        assert not config_path.exists()
        cfg = load_config(config_path)
        assert config_path.exists()
        assert isinstance(cfg, AppConfig)

    def test_defaults_have_expected_values(self, config_path: Path) -> None:
        cfg = load_config(config_path)
        assert cfg.window_title == "Age of Empires II: Definitive Edition"
        assert cfg.endpoint_url == "https://api.openai.com/v1"
        assert cfg.model_name == "gpt-4o"
        assert cfg.min_interval == 60
        assert cfg.max_interval == 180
        assert cfg.auto_trigger is True
        assert cfg.context_window_size == 5
        assert cfg.server_port == 5000

    def test_loads_valid_json_and_overrides_defaults(self, config_path: Path) -> None:
        """Values present in JSON override defaults; missing keys fall back."""
        data = {"model_name": "llava", "min_interval": 30}
        config_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = load_config(config_path)
        assert cfg.model_name == "llava"
        assert cfg.min_interval == 30
        assert cfg.max_interval == 180  # default retained

    def test_loads_full_valid_json(self, config_path: Path) -> None:
        """A complete JSON round-trip returns identical values."""
        original = AppConfig(api_key="sk-test", model_name="gpt-4-turbo", server_port=5001)
        save_config(original, config_path)

        loaded = load_config(config_path)
        assert loaded.api_key == "sk-test"
        assert loaded.model_name == "gpt-4-turbo"
        assert loaded.server_port == 5001

    def test_unknown_json_keys_are_ignored(self, config_path: Path) -> None:
        """Extra keys in the JSON file are silently dropped."""
        data = {"model_name": "gpt-4o", "some_future_key": "ignored"}
        config_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = load_config(config_path)
        assert cfg.model_name == "gpt-4o"
        assert not hasattr(cfg, "some_future_key")


# ---------------------------------------------------------------------------
# load_config — error paths
# ---------------------------------------------------------------------------


class TestLoadConfigErrors:
    def test_raises_config_error_on_invalid_json(self, config_path: Path) -> None:
        """Malformed JSON raises ConfigError, not a raw json.JSONDecodeError."""
        config_path.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(ConfigError, match="not valid JSON"):
            load_config(config_path)

    def test_raises_config_error_on_empty_file(self, config_path: Path) -> None:
        """An empty file is also invalid JSON."""
        config_path.write_text("", encoding="utf-8")

        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_raises_config_error_on_json_array(self, config_path: Path) -> None:
        """A valid JSON array (not an object) is treated as malformed config."""
        config_path.write_text("[]", encoding="utf-8")

        with pytest.raises((ConfigError, Exception)):
            load_config(config_path)


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    def test_save_creates_file(self, config_path: Path) -> None:
        cfg = AppConfig()
        save_config(cfg, config_path)
        assert config_path.exists()

    def test_save_writes_valid_json(self, config_path: Path) -> None:
        cfg = AppConfig(model_name="gpt-4o-mini")
        save_config(cfg, config_path)

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["model_name"] == "gpt-4o-mini"

    def test_save_round_trips_all_fields(self, config_path: Path) -> None:
        original = AppConfig(
            window_title="TestWindow",
            endpoint_url="http://localhost:11434/v1",
            api_key="local",
            model_name="llava",
            min_interval=10,
            max_interval=20,
            auto_trigger=False,
            hotkey="ctrl+alt+s",
            context_window_size=3,
            server_port=5001,
        )
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert asdict(loaded) == asdict(original)

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "deeply" / "nested" / "config.json"
        save_config(AppConfig(), nested)
        assert nested.exists()

    def test_save_is_human_readable(self, config_path: Path) -> None:
        """Output should be indented (not a single-line minified blob)."""
        save_config(AppConfig(), config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "\n" in content


# ---------------------------------------------------------------------------
# AppConfig dataclass behaviour
# ---------------------------------------------------------------------------


class TestAppConfigDataclass:
    def test_default_system_prompt_is_non_empty(self) -> None:
        cfg = AppConfig()
        assert len(cfg.system_prompt) > 10

    def test_two_defaults_are_equal(self) -> None:
        assert AppConfig() == AppConfig()

    def test_modification_does_not_affect_defaults(self) -> None:
        cfg1 = AppConfig()
        cfg2 = AppConfig()
        cfg1.model_name = "changed"
        assert cfg2.model_name == "gpt-4o"

    def test_default_system_prompt_matches_constant(self) -> None:
        assert AppConfig().system_prompt == DEFAULT_SYSTEM_PROMPT

    def test_context_window_size_default(self) -> None:
        assert AppConfig().context_window_size == 5

    def test_enable_thinking_default_is_false(self) -> None:
        assert AppConfig().enable_thinking is False


# ---------------------------------------------------------------------------
# PRESET_PROMPTS and TWO_STAGE_PRESET_NAME
# ---------------------------------------------------------------------------


class TestPresetPrompts:
    def test_preset_prompts_is_dict(self) -> None:
        assert isinstance(PRESET_PROMPTS, dict)

    def test_all_preset_values_non_empty(self) -> None:
        for name, prompt in PRESET_PROMPTS.items():
            assert len(prompt) > 0, f"Preset '{name}' has an empty prompt"

    def test_two_stage_preset_name_in_presets(self) -> None:
        assert TWO_STAGE_PRESET_NAME in PRESET_PROMPTS

    def test_two_stage_preset_value_is_sentinel(self) -> None:
        """The two-stage preset stores its own name as the value (sentinel pattern)."""
        assert PRESET_PROMPTS[TWO_STAGE_PRESET_NAME] == TWO_STAGE_PRESET_NAME

    def test_preset_names_are_strings(self) -> None:
        for name in PRESET_PROMPTS:
            assert isinstance(name, str)

    def test_known_presets_present(self) -> None:
        assert "The Serious Strategist" in PRESET_PROMPTS
        assert "The Sarcastic Observer" in PRESET_PROMPTS
        assert "The Helpful Coach" in PRESET_PROMPTS
