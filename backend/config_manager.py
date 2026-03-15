from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.exceptions import ConfigError

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are Sun Tzu, the ancient Chinese military strategist, brought forward in time to observe "
    "a game of Age of Empires II: Definitive Edition. Analyze the screenshot provided and deliver "
    "a single, witty, memorable line of commentary in Sun Tzu's voice. The comment should be "
    "relevant to what you observe in the game — idle villagers, floating resources, army "
    "composition, age, or strategic positioning. Keep it under 25 words. Output only the quote, "
    "nothing else."
)

TWO_STAGE_PRESET_NAME = "Sun Tzu Art of War ONLY"

PRESET_PROMPTS: dict[str, str] = {
    "The Serious Strategist": (
        "You are Sun Tzu, ancient master of war. Observe this Age of Empires II screenshot and "
        "deliver one timeless strategic truth — adapted to the game state you see. Draw from "
        "the Art of War. Speak with gravitas. Under 25 words. Output only the quote."
    ),
    "The Sarcastic Observer": (
        "You are Sun Tzu, but deeply unimpressed. Look at this Age of Empires II screenshot and "
        "roast what you see: idle villagers, floating wood, unspent gold, missed upgrades. "
        "Be witty and cutting but brief. Under 25 words. Output only the quote."
    ),
    "The Helpful Coach": (
        "You are Sun Tzu reincarnated as an AoE2 coach. Analyze this screenshot and give one "
        "specific, actionable piece of advice based on the visible game state — economy, "
        "military, timing, or positioning. Under 25 words. Output only the advice."
    ),
    TWO_STAGE_PRESET_NAME: TWO_STAGE_PRESET_NAME,
}


@dataclass
class AppConfig:
    """All persisted application settings.

    Stored as JSON in config.json at the project root. Every field has a
    sensible default so the app can run on first launch without user input.
    """

    window_title: str = "Age of Empires II: Definitive Edition"
    endpoint_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model_name: str = "gpt-4o"
    min_interval: int = 60
    max_interval: int = 180
    auto_trigger: bool = True
    hotkey: str = "ctrl+shift+t"
    system_prompt: str = field(default_factory=lambda: DEFAULT_SYSTEM_PROMPT)
    context_window_size: int = 5
    dedup_similarity_threshold: float = 0.5
    max_dedup_retries: int = 3
    server_port: int = 5000
    max_tokens: int = 5000
    enable_thinking: bool = False


def load_config(path: Path) -> AppConfig:
    """Load AppConfig from a JSON file, creating it with defaults if absent.

    Args:
        path: Path to the config.json file.

    Returns:
        A populated AppConfig instance.

    Raises:
        ConfigError: If the file exists but cannot be parsed as valid JSON.
    """
    if not path.exists():
        logger.info("Config file not found at %s — creating with defaults.", path)
        defaults = AppConfig()
        save_config(defaults, path)
        return defaults

    try:
        raw = path.read_text(encoding="utf-8")
        data: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config.json is not valid JSON: {exc}") from exc

    defaults = AppConfig()
    merged: dict = asdict(defaults)
    merged.update({k: v for k, v in data.items() if k in merged})
    return AppConfig(**merged)


def save_config(config: AppConfig, path: Path) -> None:
    """Persist an AppConfig to disk as formatted JSON.

    Args:
        config: The configuration to save.
        path:   Destination path (parent directory must exist).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    logger.info("Config saved to %s.", path)
