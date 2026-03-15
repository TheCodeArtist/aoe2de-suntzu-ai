from __future__ import annotations

import json
import logging
import random
import re
import threading
from collections import deque
from pathlib import Path
from typing import Optional

from openai import OpenAI, OpenAIError

from backend.config_manager import TWO_STAGE_PRESET_NAME, AppConfig
from backend.exceptions import AIError
from backend.models import GameState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jaccard similarity helper
# ---------------------------------------------------------------------------

_NON_WORD = re.compile(r"[^\w\s]")


def _tokenize(text: str) -> frozenset[str]:
    """Lowercase, strip punctuation, return unique word tokens."""
    return frozenset(_NON_WORD.sub("", text.lower()).split())


def jaccard_similarity(a: str, b: str) -> float:
    """Return Jaccard similarity in [0, 1] between the word sets of *a* and *b*.

    Returns 0.0 when both strings are empty (no false positives).
    """
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a and not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


_QUOTES_PATH = Path(__file__).parent.parent / "references" / "sun-tzu-quotes.json"

# Loaded once on first use; None means the file is unavailable.
_ALL_QUOTES: list[str] | None = None
_QUOTES_LOCK = threading.Lock()


def _load_quotes() -> list[str]:
    """Return all Sun Tzu quote texts, loading from disk on first call."""
    global _ALL_QUOTES
    with _QUOTES_LOCK:
        if _ALL_QUOTES is None:
            try:
                data = json.loads(_QUOTES_PATH.read_text(encoding="utf-8"))
                _ALL_QUOTES = [
                    q["text"]
                    for chapter in data.get("chapters", [])
                    for q in chapter.get("quotes", [])
                    if q.get("text")
                ]
                logger.info("Loaded %d Sun Tzu quotes from %s.", len(_ALL_QUOTES), _QUOTES_PATH)
            except Exception as exc:
                logger.warning("Could not load Sun Tzu quotes: %s", exc)
                _ALL_QUOTES = []
        return _ALL_QUOTES


# ---------------------------------------------------------------------------
# Two-stage pipeline helpers (used by "Sun Tzu Art of War ONLY" preset)
# ---------------------------------------------------------------------------

_STAGE1_SYSTEM = (
    "You are an expert Age of Empires II analyst. "
    "Describe, in 2-3 concise sentences, the strategic situation visible in the screenshot: "
    "economy state, military composition, idle units, resource surplus or deficit, age, "
    "and any obvious tactical opportunities or mistakes. Be factual and specific."
)

_STAGE2_SYSTEM = (
    "You are Sun Tzu. You have been given a description of a live Age of Empires II game "
    "and a selection of your actual writings from The Art of War. "
    "Choose the single most fitting quote from the list provided and adapt it minimally "
    "so it feels directly relevant to the described game situation. "
    "Do not invent new quotes. Output only the final adapted quote, under 30 words, nothing else."
)

_CANDIDATE_POOL_SIZE = 10


def _call_llm(
    client: OpenAI,
    config: AppConfig,
    messages: list[dict],
) -> str:
    """Shared thin wrapper for a single chat completions call."""
    extra_body: dict = {}
    if not config.enable_thinking:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        response = client.chat.completions.create(
            model=config.model_name,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=config.max_tokens,
            temperature=0.9,
            extra_body=extra_body or None,
        )
    except OpenAIError as exc:
        raise AIError(f"LLM request failed: {exc}") from exc
    except Exception as exc:
        raise AIError(f"Unexpected LLM error: {exc}") from exc

    if not response.choices:
        raise AIError("LLM returned a response with no choices.")
    return response.choices[0].message.content or ""


def _generate_quote_two_stage(
    config: AppConfig,
    game_state: GameState,
    context: ContextWindow,
) -> str:
    """Two-stage pipeline: describe screenshot first, then pick & adapt a real quote.

    Stage 1 — Vision call: send only the screenshot; ask for a plain-text
    strategic description. This isolates the visual-understanding task.

    Stage 2 — Text call: send the description plus a random sample of real
    Sun Tzu quotes; ask the LLM to select the most apt one and adapt it to
    the game moment. No image is sent, so any text-capable model works here.

    The Stage-1 description is reused across all retry attempts so that only
    Stage 2 is repeated when a duplicate quote is detected.
    """
    client = OpenAI(base_url=config.endpoint_url, api_key=config.api_key)

    # Stage 1 — describe the game state from the screenshot (done once)
    no_think_suffix = " /no_think" if not config.enable_thinking else ""
    stage1_messages: list[dict] = [
        {"role": "system", "content": _STAGE1_SYSTEM},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Describe the strategic situation in this AoE2 screenshot.{no_think_suffix}",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{game_state.screenshot_b64}",
                        "detail": "low",
                    },
                },
            ],
        },
    ]
    logger.debug("Two-stage: Stage 1 — describing screenshot.")
    game_description = _extract_quote_text(_call_llm(client, config, stage1_messages))
    if not game_description:
        raise AIError("Stage 1 returned an empty description.")
    logger.debug("Two-stage: Stage 1 result: %s", game_description[:120])

    # Stage 2 — pick and adapt a real Sun Tzu quote (retried on duplicate)
    all_quotes = _load_quotes()
    if not all_quotes:
        raise AIError("Sun Tzu quotes file could not be loaded — cannot run two-stage pipeline.")

    max_retries = max(1, config.max_dedup_retries)
    last_quote = ""

    for attempt in range(1, max_retries + 1):
        recent_quotes = context.get_recent()
        available = [q for q in all_quotes if q not in recent_quotes] or all_quotes
        candidates = random.sample(available, min(_CANDIDATE_POOL_SIZE, len(available)))
        candidate_block = "\n".join(f"- {q}" for q in candidates)

        recent_context = (
            "Previously shown (do NOT repeat): " + " | ".join(recent_quotes)
            if recent_quotes
            else ""
        )

        stage2_user = (
            f"Game situation:\n{game_description}\n\n"
            f"Candidate Sun Tzu quotes from The Art of War:\n{candidate_block}\n\n"
            f"{recent_context}\n\n"
            "Select and minimally adapt the most fitting quote. Output only the final quote."
            f"{no_think_suffix}"
        ).strip()

        stage2_messages: list[dict] = [
            {"role": "system", "content": _STAGE2_SYSTEM},
            {"role": "user", "content": stage2_user},
        ]
        logger.debug("Two-stage: Stage 2 attempt %d/%d.", attempt, max_retries)
        raw = _call_llm(client, config, stage2_messages)
        last_quote = _extract_quote_text(raw)

        if not last_quote:
            logger.warning("Two-stage attempt %d returned empty quote, retrying.", attempt)
            continue

        if context.is_duplicate(last_quote):
            logger.info(
                "Two-stage attempt %d/%d: duplicate detected, retrying. Quote: %s",
                attempt,
                max_retries,
                last_quote[:60],
            )
            continue

        return last_quote

    logger.warning(
        "All %d two-stage attempts produced duplicates; using last result anyway.", max_retries
    )
    return last_quote


class ContextWindow:
    """FIFO queue of the last N generated quotes with similarity-based deduplication.

    Passed to the LLM with each request so it avoids repeating itself.
    Thread-safe: accessed from the Worker Thread while the GUI may read it.

    Persistence: if *history_path* is provided the queue is loaded from disk on
    construction and written back on every :meth:`add` call, so the dedup
    window survives application restarts.
    """

    def __init__(
        self,
        max_size: int = 5,
        similarity_threshold: float = 0.5,
        history_path: Optional[Path] = None,
    ) -> None:
        self._max_size = max_size
        self._similarity_threshold = similarity_threshold
        self._history_path = history_path
        self._quotes: deque[str] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        if history_path:
            self._load_from_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Populate the deque from the history file (best-effort)."""
        assert self._history_path is not None
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            quotes: list[str] = data.get("recent_quotes", [])
            # Keep only the last max_size entries in case the file is stale
            for q in quotes[-self._max_size :]:
                self._quotes.append(q)
            logger.info("Loaded %d quote(s) from history at %s.", len(self._quotes), self._history_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Could not load quote history: %s", exc)

    def _save_to_disk(self) -> None:
        """Persist the current deque to disk (called under lock, best-effort)."""
        if self._history_path is None:
            return
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps({"recent_quotes": list(self._quotes)}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Could not save quote history: %s", exc)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_duplicate(self, quote: str) -> bool:
        """Return True if *quote* is too similar to any quote in the window.

        Similarity is measured with Jaccard coefficient on word sets.
        A quote that is an exact match (after normalisation) always returns True.
        """
        with self._lock:
            for stored in self._quotes:
                sim = jaccard_similarity(quote, stored)
                if sim >= self._similarity_threshold:
                    logger.debug(
                        "Duplicate detected (Jaccard=%.2f >= %.2f): %s",
                        sim,
                        self._similarity_threshold,
                        quote[:60],
                    )
                    return True
        return False

    def add(self, quote: str) -> None:
        """Append a new quote, evicting the oldest if at capacity, then persist.

        Args:
            quote: The raw text of the generated quote.
        """
        with self._lock:
            self._quotes.append(quote)
            self._save_to_disk()

    def get_recent(self) -> list[str]:
        """Return a snapshot of recent quotes (oldest first).

        Returns:
            A list of up to max_size quote strings.
        """
        with self._lock:
            return list(self._quotes)

    def clear(self) -> None:
        """Remove all stored quotes (e.g. on session reset)."""
        with self._lock:
            self._quotes.clear()
            self._save_to_disk()

    @property
    def max_size(self) -> int:
        """Maximum number of quotes retained."""
        return self._max_size

    @property
    def similarity_threshold(self) -> float:
        """Jaccard threshold above which a new quote is considered a duplicate."""
        return self._similarity_threshold


def build_messages(
    system_prompt: str,
    screenshot_b64: str,
    recent_quotes: list[str],
    enable_thinking: bool = False,
) -> list[dict]:
    """Construct the OpenAI-compatible messages payload.

    Follows the multipart vision format from spec §5.2:
    - system: the user-configured personality prompt
    - user: text context (recent quotes) + base64 image

    Args:
        system_prompt:   The personality/instruction prompt.
        screenshot_b64:  Base64-encoded JPEG string (no data-URI prefix).
        recent_quotes:   List of recently generated quotes for context.
        enable_thinking: When False, appends the Qwen3 soft-switch suffix
                         ``/no_think`` to the user text, suppressing the
                         chain-of-thought phase entirely.

    Returns:
        A list of message dicts ready for the chat completions API.
    """
    recent_context = (
        "Recent quotes (do NOT repeat these): " + " | ".join(recent_quotes)
        if recent_quotes
        else "No previous quotes yet."
    )

    user_text = f"Current Game State Screenshot. {recent_context}"
    if not enable_thinking:
        user_text += " /no_think"

    user_content: list[dict] = [
        {
            "type": "text",
            "text": user_text,
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{screenshot_b64}",
                "detail": "low",
            },
        },
    ]

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _extract_quote_text(raw_content: str) -> str:
    """Parse the LLM response content into a plain quote string.

    Attempts JSON parsing first (expected format: {"quote": "..."}),
    then falls back to using the raw string as-is.

    Args:
        raw_content: The .content field from the LLM's message response.

    Returns:
        The cleaned quote text.
    """
    stripped = raw_content.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and "quote" in parsed:
            return str(parsed["quote"]).strip()
    except (json.JSONDecodeError, ValueError):
        pass
    return stripped


def generate_quote(
    config: AppConfig,
    game_state: GameState,
    context: ContextWindow,
) -> str:
    """Call the LLM endpoint and return a Sun Tzu quote string.

    When ``config.system_prompt`` is the ``TWO_STAGE_PRESET_NAME`` sentinel,
    runs the two-stage pipeline (vision description → quote selection from the
    real Art of War text).  Otherwise falls back to the standard single-call
    pipeline.

    Both pipelines retry up to ``config.max_dedup_retries`` times when the
    generated quote is flagged as a duplicate by :class:`ContextWindow`.  If
    all retries fail the last generated quote is used rather than returning
    nothing — the overlay should always receive something.

    Args:
        config:     Full application config (endpoint, key, model, prompt).
        game_state: Contains the base64 screenshot and metadata.
        context:    Recent quotes for de-duplication context.

    Returns:
        The generated quote as a plain string.

    Raises:
        AIError: If the API call fails for any reason (network, auth, rate limit).
    """
    if config.system_prompt == TWO_STAGE_PRESET_NAME:
        logger.info("Two-stage pipeline selected.")
        quote = _generate_quote_two_stage(config, game_state, context)
        if not quote:
            raise AIError("Two-stage pipeline returned an empty quote.")
        context.add(quote)
        logger.info("Quote generated (two-stage): %s", quote[:60])
        return quote

    # Standard single-call pipeline with retry on duplicate
    client = OpenAI(base_url=config.endpoint_url, api_key=config.api_key)
    max_retries = max(1, config.max_dedup_retries)
    last_quote = ""

    for attempt in range(1, max_retries + 1):
        messages = build_messages(
            system_prompt=config.system_prompt,
            screenshot_b64=game_state.screenshot_b64,
            recent_quotes=context.get_recent(),
            enable_thinking=config.enable_thinking,
        )

        logger.debug(
            "Calling LLM (attempt %d/%d): endpoint=%s model=%s context_quotes=%d thinking=%s",
            attempt,
            max_retries,
            config.endpoint_url,
            config.model_name,
            len(context.get_recent()),
            config.enable_thinking,
        )

        raw_content = _call_llm(client, config, messages)
        quote = _extract_quote_text(raw_content)

        if not quote:
            logger.warning("LLM returned empty quote on attempt %d, retrying.", attempt)
            continue

        if context.is_duplicate(quote):
            logger.info(
                "Attempt %d/%d: duplicate detected, retrying. Quote: %s",
                attempt,
                max_retries,
                quote[:60],
            )
            last_quote = quote
            continue

        context.add(quote)
        logger.info("Quote generated: %s", quote[:60])
        return quote

    # All retries exhausted — use last result to avoid an empty overlay
    if not last_quote:
        raise AIError("LLM returned an empty response.")
    logger.warning(
        "All %d attempts produced duplicates; using last result anyway.", max_retries
    )
    context.add(last_quote)
    logger.info("Quote generated (fallback after dedup exhaustion): %s", last_quote[:60])
    return last_quote
