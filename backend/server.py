from __future__ import annotations

import json
import logging
import queue
import time
from pathlib import Path
from queue import Empty

from flask import Flask, Response, jsonify, send_from_directory

from backend.models import Quote

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15.0
SSE_POLL_TIMEOUT = 1.0


def calculate_duration_ms(text: str) -> int:
    """Calculate display duration for a quote based on word count.

    Formula from spec §4.2: word_count * 500ms + 3000ms base.

    Args:
        text: The quote string.

    Returns:
        Duration in milliseconds.
    """
    word_count = len(text.split())
    return word_count * 500 + 3000


def create_app(
    quote_queue: "queue.Queue[Quote]",
    frontend_dir: Path,
    assets_dir: Path | None = None,
) -> Flask:
    """Create and configure the Flask application.

    Serves the frontend overlay files as static content and exposes
    an SSE endpoint that pushes new quotes to connected OBS Browser Sources.

    Args:
        quote_queue:  Thread-safe queue where Worker Threads deposit new quotes.
        frontend_dir: Path to the frontend/ directory containing index.html.
        assets_dir:   Path to the assets/ directory containing overlay images.
                      When provided, images are served at /assets/<filename>.

    Returns:
        A configured Flask app instance (not yet running).
    """
    app = Flask(__name__, static_folder=None)
    app.config["quote_queue"] = quote_queue
    app.config["frontend_dir"] = frontend_dir
    app.config["assets_dir"] = assets_dir

    @app.route("/")
    def index() -> Response:
        """Serve the OBS overlay HTML page."""
        return send_from_directory(str(frontend_dir), "index.html")

    @app.route("/assets/<path:filename>")
    def asset_files(filename: str) -> Response:
        """Serve overlay image assets (portrait, parchment, frame)."""
        dir_: Path = app.config["assets_dir"] or frontend_dir
        return send_from_directory(str(dir_), filename)

    @app.route("/fonts-list")
    def fonts_list() -> Response:
        """Return a JSON list of font files found in frontend/fonts/.

        Each entry has the filename and the stem (filename without extension),
        used by font-calibration.html to auto-discover fonts without a hard-coded list.
        """
        fonts_dir = frontend_dir / "fonts"
        entries = []
        if fonts_dir.is_dir():
            for p in sorted(fonts_dir.iterdir()):
                if p.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}:
                    entries.append({"filename": p.name, "stem": p.stem})
        return jsonify(entries)

    @app.route("/<path:filename>")
    def static_files(filename: str) -> Response:
        """Serve any static file (CSS, JS) from the frontend directory."""
        return send_from_directory(str(frontend_dir), filename)

    @app.route("/events")
    def sse_stream() -> Response:
        """Server-Sent Events endpoint consumed by the OBS Browser Source.

        Streams quotes from quote_queue as SSE data frames.
        Sends a heartbeat comment every HEARTBEAT_INTERVAL seconds to
        keep the connection alive through proxies and OBS's CEF browser.
        """
        q: "queue.Queue[Quote]" = app.config["quote_queue"]

        def generate():
            yield ": connected\n\n"  # Force headers to be sent immediately
            last_heartbeat = time.monotonic()
            while True:
                now = time.monotonic()

                # Send heartbeat if idle too long
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    yield ":\n\n"  # SSE comment — keeps connection alive
                    last_heartbeat = time.monotonic()

                try:
                    quote: Quote = q.get(timeout=SSE_POLL_TIMEOUT)
                    duration_ms = calculate_duration_ms(quote.text)
                    payload = json.dumps({"text": quote.text, "duration_ms": duration_ms})
                    logger.info("SSE: pushing quote (duration=%dms): %s", duration_ms, quote.text[:40])
                    yield f"data: {payload}\n\n"
                    last_heartbeat = time.monotonic()
                except Empty:
                    pass

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app


def run_server(
    quote_queue: "queue.Queue[Quote]",
    frontend_dir: Path,
    assets_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 5000,
) -> None:
    """Start the Flask development server in the current thread.

    Intended to be called from a daemon thread. Werkzeug manages its own
    shutdown lifecycle when the process exits.

    Args:
        quote_queue:  Shared queue of pending quotes.
        frontend_dir: Path to frontend files.
        assets_dir:   Path to assets/ directory; served at /assets/<filename>.
        host:         Bind address (default: localhost only).
        port:         TCP port (default: 5000).
    """
    app = create_app(quote_queue, frontend_dir, assets_dir)
    logger.info("Starting overlay server on http://%s:%d", host, port)
    app.run(host=host, port=port, threaded=True, use_reloader=False)
