from __future__ import annotations

import logging
import queue
import random
import socket
import threading
import time
import tkinter as tk
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable

from backend.ai_client import ContextWindow, generate_quote
from backend.capture import capture_window, image_to_base64, list_windows
from backend.config_manager import (
    PRESET_PROMPTS,
    AppConfig,
    load_config,
    save_config,
)
from backend.exceptions import AIError, CaptureError, ConfigError
from backend.models import GameState, Quote, TriggerSource
from backend.server import run_server

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
ASSETS_DIR = PROJECT_ROOT / "assets"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
LOG_PATH = PROJECT_ROOT / "suntzu-overlay.log"

# ---------------------------------------------------------------------------
# Logging bootstrap  (called once before the GUI is created)
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    """Configure root logger with a rotating file handler and a console handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s")

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status colours used in the status bar label
# ---------------------------------------------------------------------------

STATUS_COLOUR = {
    "ok": "#2a7a3b",
    "processing": "#c47a00",
    "error": "#c0392b",
    "idle": "#555555",
}


# ===========================================================================
# Worker pipeline (runs in its own thread)
# ===========================================================================


def run_pipeline(
    config: AppConfig,
    context: ContextWindow,
    quote_queue: "queue.Queue[Quote]",
    status_queue: "queue.Queue[tuple[str, str]]",
    trigger_source: TriggerSource = TriggerSource.MANUAL,
) -> None:
    """Execute the full Capture → AI → Push pipeline once.

    Designed to be the target of a daemon thread. Communicates progress
    back to the GUI via status_queue tuples of (message, colour_key).

    Args:
        config:         Current application configuration.
        context:        Shared recent-quotes context window.
        quote_queue:    Output queue consumed by the Flask SSE server.
        status_queue:   Queue for status bar updates on the GUI thread.
        trigger_source: What caused this pipeline run.
    """
    logger.info("Pipeline triggered by %s.", trigger_source.value)

    def status(msg: str, colour: str = "processing") -> None:
        status_queue.put((msg, colour))

    try:
        status("Capturing game window...", "processing")
        img = capture_window(config.window_title)
        b64 = image_to_base64(img)
        game_state = GameState(screenshot_b64=b64, window_title=config.window_title)

        status("Thinking...", "processing")
        quote_text = generate_quote(config, game_state, context)

        quote_queue.put(Quote(text=quote_text))
        display = quote_text[:55] + ("…" if len(quote_text) > 55 else "")
        status(f'"{display}"', "ok")
        logger.info("Pipeline complete. Quote pushed to server.")

    except CaptureError as exc:
        logger.error("Capture error: %s", exc)
        status(f"Capture error: {exc}", "error")
    except AIError as exc:
        logger.error("AI error: %s", exc)
        status(f"AI error: {exc}", "error")
    except Exception as exc:
        logger.exception("Unexpected pipeline error.")
        status(f"Error: {exc}", "error")


# ===========================================================================
# Timer loop (runs in its own daemon thread)
# ===========================================================================


def start_timer_loop(
    config: AppConfig,
    trigger_callback: Callable[[], None],
    stop_event: threading.Event,
) -> None:
    """Sleep for a random interval then call trigger_callback. Repeats until stopped.

    Uses stop_event.wait() so the thread wakes immediately on shutdown
    rather than sleeping through the full interval.

    Args:
        config:           Config read at loop-start for interval values.
        trigger_callback: Callable invoked each time the timer fires.
        stop_event:       Set externally to break the loop.
    """
    logger.info(
        "Timer loop started (interval: %d–%ds).",
        config.min_interval,
        config.max_interval,
    )
    while not stop_event.is_set():
        interval = random.randint(config.min_interval, config.max_interval)
        logger.debug("Next trigger in %ds.", interval)
        fired = not stop_event.wait(timeout=interval)
        if fired and not stop_event.is_set():
            trigger_callback()
    logger.info("Timer loop stopped.")


# ===========================================================================
# Tkinter Application
# ===========================================================================


class SunTzuApp:
    """Main Tkinter application window.

    Hosts all configuration UI, wires the threading model, and manages
    the lifecycle of the Server and Worker threads.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sun Tzu AoE2 Commentary Overlay")
        self.root.resizable(False, False)

        # Running state flags
        self._running = False
        self._hotkey_registered = False

        # Load or create config (must come before any config-dependent init)
        try:
            self.config = load_config(CONFIG_PATH)
        except ConfigError as exc:
            messagebox.showerror("Configuration Error", str(exc))
            self.config = AppConfig()

        # Shared threading primitives
        self.quote_queue: queue.Queue[Quote] = queue.Queue()
        self.status_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.timer_stop_event = threading.Event()
        self.context = ContextWindow(
            max_size=self.config.context_window_size,
            similarity_threshold=self.config.dedup_similarity_threshold,
            history_path=PROJECT_ROOT / "quote_history.json",
        )

        self._build_ui()
        self._start_server_thread()
        self._validate_assets()

        # Start polling the status_queue every 100 ms
        self.root.after(100, self._poll_status)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("Application started.")

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct all widgets using a grid layout."""
        pad = {"padx": 8, "pady": 4}

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Tab: Connection ---
        conn_tab = ttk.Frame(notebook)
        notebook.add(conn_tab, text="Connection")
        self._build_connection_tab(conn_tab, pad)

        # --- Tab: Window ---
        win_tab = ttk.Frame(notebook)
        notebook.add(win_tab, text="Window")
        self._build_window_tab(win_tab, pad)

        # --- Tab: Timing ---
        timing_tab = ttk.Frame(notebook)
        notebook.add(timing_tab, text="Timing")
        self._build_timing_tab(timing_tab, pad)

        # --- Tab: Hotkey ---
        hotkey_tab = ttk.Frame(notebook)
        notebook.add(hotkey_tab, text="Hotkey")
        self._build_hotkey_tab(hotkey_tab, pad)

        # --- Tab: Personality ---
        personality_tab = ttk.Frame(notebook)
        notebook.add(personality_tab, text="Personality")
        self._build_personality_tab(personality_tab, pad)

        # --- Controls row ---
        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=10, pady=(0, 6))
        self._build_controls(controls)

        # --- Status bar ---
        self._status_var = tk.StringVar(value="Idle — press Start to begin.")
        self._status_label = tk.Label(
            self.root,
            textvariable=self._status_var,
            anchor="w",
            font=("Consolas", 9),
            fg=STATUS_COLOUR["idle"],
            bg="#f0f0f0",
            relief="sunken",
            bd=1,
        )
        self._status_label.pack(fill="x", padx=10, pady=(0, 8))

    def _build_connection_tab(self, parent: ttk.Frame, pad: dict) -> None:
        self._endpoint_var = tk.StringVar(value=self.config.endpoint_url)
        self._api_key_var = tk.StringVar(value=self.config.api_key)
        self._model_var = tk.StringVar(value=self.config.model_name)
        self._max_tokens_var = tk.IntVar(value=self.config.max_tokens)
        self._enable_thinking_var = tk.BooleanVar(value=self.config.enable_thinking)

        ttk.Label(parent, text="Endpoint URL:").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(parent, textvariable=self._endpoint_var, width=50).grid(row=0, column=1, **pad)

        ttk.Label(parent, text="API Key:").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(parent, textvariable=self._api_key_var, show="*", width=50).grid(row=1, column=1, **pad)

        ttk.Label(parent, text="Model Name:").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(parent, textvariable=self._model_var, width=50).grid(row=2, column=1, **pad)

        ttk.Label(parent, text="Max Tokens:").grid(row=3, column=0, sticky="e", **pad)
        ttk.Spinbox(parent, from_=64, to=32768, textvariable=self._max_tokens_var, width=10).grid(
            row=3, column=1, sticky="w", **pad
        )

        ttk.Checkbutton(
            parent,
            text="Enable Thinking (reasoning models — disable to skip chain-of-thought)",
            variable=self._enable_thinking_var,
        ).grid(row=4, column=1, sticky="w", **pad)

        ttk.Button(parent, text="Save", command=self._save_config).grid(row=5, column=1, sticky="e", **pad)

    def _build_window_tab(self, parent: ttk.Frame, pad: dict) -> None:
        self._window_var = tk.StringVar(value=self.config.window_title)

        ttk.Label(parent, text="Game Window:").grid(row=0, column=0, sticky="e", **pad)
        self._window_combo = ttk.Combobox(parent, textvariable=self._window_var, width=48)
        self._window_combo.grid(row=0, column=1, **pad)
        self._refresh_window_list()

        ttk.Button(parent, text="Refresh", command=self._refresh_window_list).grid(
            row=0, column=2, **pad
        )
        ttk.Button(parent, text="Save", command=self._save_config).grid(row=1, column=1, sticky="e", **pad)

    def _build_timing_tab(self, parent: ttk.Frame, pad: dict) -> None:
        self._min_interval_var = tk.IntVar(value=self.config.min_interval)
        self._max_interval_var = tk.IntVar(value=self.config.max_interval)
        self._auto_trigger_var = tk.BooleanVar(value=self.config.auto_trigger)
        self._context_window_size_var = tk.IntVar(value=self.config.context_window_size)
        self._dedup_similarity_var = tk.DoubleVar(value=self.config.dedup_similarity_threshold)
        self._max_dedup_retries_var = tk.IntVar(value=self.config.max_dedup_retries)

        ttk.Label(parent, text="Min Interval (s):").grid(row=0, column=0, sticky="e", **pad)
        ttk.Spinbox(parent, from_=5, to=3600, textvariable=self._min_interval_var, width=10).grid(
            row=0, column=1, sticky="w", **pad
        )

        ttk.Label(parent, text="Max Interval (s):").grid(row=1, column=0, sticky="e", **pad)
        ttk.Spinbox(parent, from_=5, to=3600, textvariable=self._max_interval_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Checkbutton(parent, text="Enable Auto-Trigger", variable=self._auto_trigger_var).grid(
            row=2, column=1, sticky="w", **pad
        )

        ttk.Separator(parent, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=6
        )

        ttk.Label(parent, text="No-Repeat History (N):").grid(row=4, column=0, sticky="e", **pad)
        ttk.Spinbox(
            parent, from_=1, to=50, textvariable=self._context_window_size_var, width=10
        ).grid(row=4, column=1, sticky="w", **pad)
        ttk.Label(parent, text="quotes remembered across sessions").grid(
            row=4, column=2, sticky="w", **pad
        )

        ttk.Label(parent, text="Similarity Threshold:").grid(row=5, column=0, sticky="e", **pad)
        ttk.Spinbox(
            parent,
            from_=0.1,
            to=1.0,
            increment=0.05,
            textvariable=self._dedup_similarity_var,
            width=10,
            format="%.2f",
        ).grid(row=5, column=1, sticky="w", **pad)
        ttk.Label(parent, text="Jaccard score to treat as duplicate (0.5 = 50% word overlap)").grid(
            row=5, column=2, sticky="w", **pad
        )

        ttk.Label(parent, text="Max Dedup Retries:").grid(row=6, column=0, sticky="e", **pad)
        ttk.Spinbox(
            parent, from_=1, to=10, textvariable=self._max_dedup_retries_var, width=10
        ).grid(row=6, column=1, sticky="w", **pad)
        ttk.Label(parent, text="LLM retry attempts before accepting a duplicate").grid(
            row=6, column=2, sticky="w", **pad
        )

        ttk.Button(parent, text="Save", command=self._save_config).grid(
            row=7, column=1, sticky="e", **pad
        )

    def _build_hotkey_tab(self, parent: ttk.Frame, pad: dict) -> None:
        self._hotkey_var = tk.StringVar(value=self.config.hotkey)
        self._capturing_hotkey = False

        ttk.Label(parent, text="Hotkey:").grid(row=0, column=0, sticky="e", **pad)
        self._hotkey_entry = ttk.Entry(parent, textvariable=self._hotkey_var, width=30, state="readonly")
        self._hotkey_entry.grid(row=0, column=1, **pad)

        self._capture_btn = ttk.Button(
            parent, text="Record Hotkey", command=self._start_hotkey_capture
        )
        self._capture_btn.grid(row=0, column=2, **pad)
        ttk.Button(parent, text="Save", command=self._save_config).grid(row=1, column=1, sticky="e", **pad)

    def _build_personality_tab(self, parent: ttk.Frame, pad: dict) -> None:
        preset_names = ["Custom"] + list(PRESET_PROMPTS.keys())
        self._preset_var = tk.StringVar(value="Custom")

        ttk.Label(parent, text="Preset:").grid(row=0, column=0, sticky="e", **pad)
        preset_combo = ttk.Combobox(
            parent, textvariable=self._preset_var, values=preset_names, state="readonly", width=30
        )
        preset_combo.grid(row=0, column=1, sticky="w", **pad)
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Label(parent, text="System Prompt:").grid(row=1, column=0, sticky="ne", **pad)
        self._prompt_text = scrolledtext.ScrolledText(parent, width=60, height=8, wrap="word")
        self._prompt_text.grid(row=1, column=1, columnspan=2, **pad)
        self._prompt_text.insert("1.0", self.config.system_prompt)

        ttk.Button(parent, text="Save", command=self._save_config).grid(row=2, column=1, sticky="e", **pad)

    def _build_controls(self, parent: ttk.Frame) -> None:
        self._start_btn = ttk.Button(parent, text="Start", command=self._on_start)
        self._start_btn.pack(side="left", padx=4)

        self._stop_btn = ttk.Button(parent, text="Stop", command=self._on_stop, state="disabled")
        self._stop_btn.pack(side="left", padx=4)

        ttk.Button(parent, text="Trigger Now", command=self._on_trigger_now).pack(side="left", padx=4)

        ttk.Button(parent, text="Test Overlay", command=self._on_test_overlay).pack(side="left", padx=4)

        # Clickable server URL label — opens the OBS browser source URL in the default browser
        self._server_status_var = tk.StringVar(value="Server: starting…")
        self._server_url_label = tk.Label(
            parent,
            textvariable=self._server_status_var,
            fg="#1a6aad",
            cursor="hand2",
        )
        self._server_url_label.pack(side="right", padx=8)
        self._server_url_label.bind("<Button-1>", self._on_server_url_click)

    # -----------------------------------------------------------------------
    # Widget event handlers
    # -----------------------------------------------------------------------

    def _on_preset_selected(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        preset = self._preset_var.get()
        if preset in PRESET_PROMPTS:
            self._prompt_text.delete("1.0", "end")
            self._prompt_text.insert("1.0", PRESET_PROMPTS[preset])

    def _refresh_window_list(self) -> None:
        titles = list_windows()
        self._window_combo["values"] = titles

    def _start_hotkey_capture(self) -> None:
        """Begin listening for a key combination to use as the hotkey."""
        if self._capturing_hotkey:
            return
        self._capturing_hotkey = True
        self._hotkey_var.set("Press a key combo…")
        self._capture_btn.configure(state="disabled")
        threading.Thread(target=self._capture_hotkey_blocking, daemon=True).start()

    def _capture_hotkey_blocking(self) -> None:
        """Block in a background thread until a hotkey combination is pressed."""
        try:
            import keyboard  # noqa: PLC0415

            combo = keyboard.read_hotkey(suppress=False)
            self.root.after(0, lambda: self._apply_captured_hotkey(combo))
        except Exception as exc:
            logger.error("Hotkey capture failed: %s", exc)
            self.root.after(0, lambda: self._apply_captured_hotkey(self.config.hotkey))

    def _apply_captured_hotkey(self, combo: str) -> None:
        self._hotkey_var.set(combo)
        self._capture_btn.configure(state="normal")
        self._capturing_hotkey = False

    def _save_config(self) -> None:
        """Read current widget values and persist to config.json."""
        self.config.endpoint_url = self._endpoint_var.get().strip()
        self.config.api_key = self._api_key_var.get().strip()
        self.config.model_name = self._model_var.get().strip()
        self.config.max_tokens = self._max_tokens_var.get()
        self.config.enable_thinking = self._enable_thinking_var.get()
        self.config.window_title = self._window_var.get().strip()
        self.config.min_interval = self._min_interval_var.get()
        self.config.max_interval = self._max_interval_var.get()
        self.config.auto_trigger = self._auto_trigger_var.get()
        self.config.hotkey = self._hotkey_var.get().strip()
        self.config.system_prompt = self._prompt_text.get("1.0", "end-1c").strip()
        self.config.context_window_size = self._context_window_size_var.get()
        self.config.dedup_similarity_threshold = round(self._dedup_similarity_var.get(), 2)
        self.config.max_dedup_retries = self._max_dedup_retries_var.get()

        if self.config.min_interval > self.config.max_interval:
            messagebox.showerror(
                "Validation Error",
                "Min Interval must be less than or equal to Max Interval.",
            )
            return

        try:
            save_config(self.config, CONFIG_PATH)
            self._set_status("Config saved.", "ok")
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)
            messagebox.showerror("Save Error", str(exc))

    # -----------------------------------------------------------------------
    # Start / Stop / Trigger
    # -----------------------------------------------------------------------

    def _on_start(self) -> None:
        if self._running:
            return
        self._save_config()
        self._running = True
        self.timer_stop_event.clear()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._set_status("Running.", "ok")

        # Register global hotkey
        self._register_hotkey()

        # Start timer loop if auto-trigger is enabled
        if self.config.auto_trigger:
            t = threading.Thread(
                target=start_timer_loop,
                args=(
                    self.config,
                    lambda: self._spawn_worker(TriggerSource.TIMER),
                    self.timer_stop_event,
                ),
                daemon=True,
            )
            t.start()

    def _on_stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self.timer_stop_event.set()
        self._unregister_hotkey()
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._set_status("Stopped.", "idle")

    def _on_trigger_now(self) -> None:
        """Fire the pipeline immediately regardless of running state."""
        self._save_config()
        self._spawn_worker(TriggerSource.MANUAL)

    def _on_test_overlay(self) -> None:
        """Push a canned test quote directly to quote_queue without capture or AI."""
        self.quote_queue.put(
            Quote(text="The supreme art of war is to subdue the enemy without fighting.")
        )
        self._set_status("Test quote sent to overlay.", "ok")

    def _on_server_url_click(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        """Open the OBS overlay URL in the default browser."""
        url = f"http://127.0.0.1:{self.config.server_port}"
        webbrowser.open(url)

    def _spawn_worker(self, source: TriggerSource = TriggerSource.MANUAL) -> None:
        """Spawn a Worker Thread to run the full capture → AI → push pipeline."""
        t = threading.Thread(
            target=run_pipeline,
            args=(
                self.config,
                self.context,
                self.quote_queue,
                self.status_queue,
                source,
            ),
            daemon=True,
        )
        t.start()

    # -----------------------------------------------------------------------
    # Hotkey management
    # -----------------------------------------------------------------------

    def _register_hotkey(self) -> None:
        if self._hotkey_registered:
            return
        try:
            import keyboard  # noqa: PLC0415

            # Use a thread-safe wrapper that schedules the action on the main thread
            keyboard.add_hotkey(self.config.hotkey, self._on_hotkey_press)
            self._hotkey_registered = True
            logger.info("Hotkey registered: %s", self.config.hotkey)
        except Exception as exc:
            logger.error("Failed to register hotkey '%s': %s", self.config.hotkey, exc)
            self._set_status(f"Hotkey error: {exc}", "error")

    def _on_hotkey_press(self) -> None:
        """Callback from keyboard thread. Schedule execution on main thread."""
        self.root.after(0, self._execute_hotkey_action)

    def _execute_hotkey_action(self) -> None:
        """Runs on main thread: saves config (syncing UI) then spawns worker."""
        # Behave like 'Trigger Now': save current UI state to config, then run.
        self._save_config()
        self._spawn_worker(TriggerSource.HOTKEY)

    def _unregister_hotkey(self) -> None:
        if not self._hotkey_registered:
            return
        try:
            import keyboard  # noqa: PLC0415

            keyboard.remove_hotkey(self.config.hotkey)
            self._hotkey_registered = False
            logger.info("Hotkey unregistered.")
        except Exception as exc:
            logger.warning("Failed to unregister hotkey: %s", exc)

    # -----------------------------------------------------------------------
    # Status bar
    # -----------------------------------------------------------------------

    def _set_status(self, message: str, colour_key: str = "idle") -> None:
        """Update the status bar text and colour. Must be called on the main thread."""
        self._status_var.set(message)
        self._status_label.configure(fg=STATUS_COLOUR.get(colour_key, STATUS_COLOUR["idle"]))

    def _poll_status(self) -> None:
        """Drain the status_queue and update the GUI. Re-schedules itself every 100 ms."""
        try:
            while True:
                message, colour = self.status_queue.get_nowait()
                self._set_status(message, colour)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_status)

    # -----------------------------------------------------------------------
    # Server thread
    # -----------------------------------------------------------------------

    def _start_server_thread(self) -> None:
        """Launch the Flask SSE server in a daemon thread."""
        port = self.config.server_port
        if not _is_port_free(port):
            messagebox.showwarning(
                "Port in Use",
                f"Port {port} is already in use.\n"
                "Another instance may be running. The server will not start.",
            )
            self._server_status_var.set(f"Server: port {port} occupied")
            return

        t = threading.Thread(
            target=run_server,
            args=(self.quote_queue, FRONTEND_DIR),
            kwargs={"assets_dir": ASSETS_DIR, "host": "127.0.0.1", "port": port},
            daemon=True,
        )
        t.start()

        # Brief delay to let Flask bind, then update status
        self.root.after(1200, lambda: self._server_status_var.set(f"Server: http://127.0.0.1:{port}"))
        logger.info("Server thread started on port %d.", port)

    # -----------------------------------------------------------------------
    # Asset validation
    # -----------------------------------------------------------------------

    def _validate_assets(self) -> None:
        """Warn the user if required overlay assets are missing."""
        required = ["sun-tzu-background.png"]
        missing = [name for name in required if not (ASSETS_DIR / name).exists()]
        if missing:
            messagebox.showwarning(
                "Missing Assets",
                "The following overlay assets were not found in assets/:\n"
                + "\n".join(f"  • {name}" for name in missing)
                + "\n\nThe overlay may not display correctly.",
            )

    # -----------------------------------------------------------------------
    # Shutdown
    # -----------------------------------------------------------------------

    def _on_close(self) -> None:
        """Clean shutdown: stop threads then destroy the window."""
        logger.info("Application closing.")
        self.timer_stop_event.set()
        self._unregister_hotkey()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if no process is listening on the given port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Application entry point."""
    _setup_logging()
    root = tk.Tk()
    app = SunTzuApp(root)  # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    main()
