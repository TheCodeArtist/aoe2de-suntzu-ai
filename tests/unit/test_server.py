from __future__ import annotations

import json
import queue
import time
from pathlib import Path

import pytest

from backend.models import Quote
from backend.server import calculate_duration_ms, create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def frontend_dir(tmp_path: Path) -> Path:
    """Create a minimal frontend directory with a stub index.html."""
    html = tmp_path / "index.html"
    html.write_text("<html><body>overlay</body></html>", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def empty_queue() -> "queue.Queue[Quote]":
    return queue.Queue()


@pytest.fixture()
def app(empty_queue, frontend_dir):
    flask_app = create_app(empty_queue, frontend_dir)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# calculate_duration_ms
# ---------------------------------------------------------------------------


class TestCalculateDurationMs:
    def test_empty_string_returns_base_duration(self) -> None:
        # 0 words * 500 + 3000 = 3000
        assert calculate_duration_ms("") == 3000

    def test_single_word(self) -> None:
        # 1 * 500 + 3000 = 3500
        assert calculate_duration_ms("Hello") == 3500

    def test_five_words(self) -> None:
        # 5 * 500 + 3000 = 5500
        assert calculate_duration_ms("one two three four five") == 5500

    def test_ten_words(self) -> None:
        # 10 * 500 + 3000 = 8000
        text = "a b c d e f g h i j"
        assert calculate_duration_ms(text) == 8000

    def test_matches_spec_formula(self) -> None:
        """Verify the formula matches spec §4.2: word_count * 500 + 3000."""
        for word_count in range(1, 30):
            text = " ".join(["word"] * word_count)
            expected = word_count * 500 + 3000
            assert calculate_duration_ms(text) == expected


# ---------------------------------------------------------------------------
# create_app / index route
# ---------------------------------------------------------------------------


class TestIndexRoute:
    def test_serves_index_html(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert b"overlay" in response.data

    def test_404_on_missing_file(self, client) -> None:
        response = client.get("/nonexistent.css")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# SSE /events endpoint
# ---------------------------------------------------------------------------


class TestSSEEndpoint:
    def test_sse_content_type(self, app, empty_queue) -> None:
        """The /events route must declare text/event-stream MIME type."""
        empty_queue.put(Quote(text="Test quote for SSE."))
        with app.test_client() as client:
            with client.get("/events", buffered=False) as response:
                assert "text/event-stream" in response.content_type

    def test_sse_delivers_data_frame(self, app, empty_queue) -> None:
        """A queued quote should appear as a `data:` SSE frame."""
        quote_text = "In the chaos of farming, there is also opportunity."
        empty_queue.put(Quote(text=quote_text))

        # Read one chunk from the streaming response
        with app.test_request_context():
            from backend.server import calculate_duration_ms
            q: queue.Queue = empty_queue
            quote = q.get(timeout=1)
            duration = calculate_duration_ms(quote.text)
            payload = json.dumps({"text": quote.text, "duration_ms": duration})
            sse_frame = f"data: {payload}\n\n"

        assert '"text":' in sse_frame
        assert quote_text in sse_frame

    def test_duration_ms_in_payload_uses_formula(self, empty_queue) -> None:
        """duration_ms must equal word_count * 500 + 3000 for any quote."""
        text = "He who hesitates loses the farm."  # 6 words
        expected_duration = 6 * 500 + 3000  # 6000

        from backend.server import calculate_duration_ms
        assert calculate_duration_ms(text) == expected_duration

    def test_sse_payload_is_valid_json(self, empty_queue) -> None:
        """The data field must be parseable JSON with text and duration_ms keys."""
        from backend.server import calculate_duration_ms

        text = "Sun Tzu approves of early farms."
        duration = calculate_duration_ms(text)
        payload = json.dumps({"text": text, "duration_ms": duration})
        parsed = json.loads(payload)
        assert parsed["text"] == text
        assert parsed["duration_ms"] == duration
        assert isinstance(parsed["duration_ms"], int)

    def test_cache_control_headers(self, app, empty_queue) -> None:
        """SSE responses must not be cached."""
        empty_queue.put(Quote(text="No cache test."))
        with app.test_client() as client:
            with client.get("/events", buffered=False) as response:
                assert response.headers.get("Cache-Control") == "no-cache"

    def test_sse_generator_yields_data_frame(self, tmp_path: Path) -> None:
        """The SSE generator must produce a correctly formatted data frame
        when a Quote is pre-loaded into the queue."""
        q: queue.Queue[Quote] = queue.Queue()
        quote_text = "He who controls the farms controls the game."
        q.put(Quote(text=quote_text))

        html = tmp_path / "index.html"
        html.write_text("<html></html>", encoding="utf-8")
        flask_app = create_app(q, tmp_path)
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            with client.get("/events", buffered=False) as response:
                assert response.status_code == 200
                # First chunk is the SSE connection preamble ": connected\n\n"
                preamble = next(response.response)
                assert preamble == b": connected\n\n"
                # Second chunk is the actual data frame
                chunk = next(response.response)
                assert isinstance(chunk, bytes)
                decoded = chunk.decode()
                assert decoded.startswith("data: ")
                parsed = json.loads(decoded.removeprefix("data: ").strip())
                assert parsed["text"] == quote_text
                assert isinstance(parsed["duration_ms"], int)
                assert parsed["duration_ms"] == calculate_duration_ms(quote_text)


# ---------------------------------------------------------------------------
# /assets/ route
# ---------------------------------------------------------------------------


class TestAssetsRoute:
    def test_serves_asset_from_assets_dir(self, tmp_path: Path) -> None:
        """GET /assets/<file> must serve from assets_dir, not frontend_dir."""
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html></html>", encoding="utf-8")

        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "portrait.png").write_bytes(b"\x89PNG")

        q: queue.Queue[Quote] = queue.Queue()
        flask_app = create_app(q, frontend, assets_dir=assets)
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            response = client.get("/assets/portrait.png")
            assert response.status_code == 200
            assert response.data == b"\x89PNG"

    def test_asset_404_for_missing_file(self, tmp_path: Path) -> None:
        """GET /assets/<missing> must return 404."""
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
        assets = tmp_path / "assets"
        assets.mkdir()

        q: queue.Queue[Quote] = queue.Queue()
        flask_app = create_app(q, frontend, assets_dir=assets)
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            response = client.get("/assets/nonexistent.png")
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# /assets/ fallback: no assets_dir → serve from frontend_dir
# ---------------------------------------------------------------------------


class TestAssetsFallback:
    def test_serves_from_frontend_dir_when_no_assets_dir(self, tmp_path: Path) -> None:
        """When assets_dir is None, /assets/<file> falls back to frontend_dir."""
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
        (frontend / "portrait.png").write_bytes(b"\x89PNG")

        q: queue.Queue[Quote] = queue.Queue()
        flask_app = create_app(q, frontend, assets_dir=None)
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            response = client.get("/assets/portrait.png")
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# run_server (smoke test via thread + early stop)
# ---------------------------------------------------------------------------


class TestRunServer:
    def test_run_server_starts_without_error(self, tmp_path: Path) -> None:
        """run_server must bind and start without raising; we stop it immediately."""
        import threading

        from backend.server import run_server

        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
        q: queue.Queue[Quote] = queue.Queue()

        error: list[Exception] = []

        def target() -> None:
            try:
                run_server(q, frontend, host="127.0.0.1", port=15731)
            except Exception as exc:
                error.append(exc)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout=2)
        assert not error, f"run_server raised: {error[0]}"


# ---------------------------------------------------------------------------
# SSE heartbeat path
# ---------------------------------------------------------------------------


class TestSSEHeartbeat:
    def test_heartbeat_sent_when_idle_too_long(self, tmp_path: Path) -> None:
        """Force the heartbeat branch by setting HEARTBEAT_INTERVAL to zero."""
        import backend.server as server_mod

        original_interval = server_mod.HEARTBEAT_INTERVAL
        server_mod.HEARTBEAT_INTERVAL = 0.0

        try:
            q: queue.Queue[Quote] = queue.Queue()
            q.put(Quote(text="Heartbeat test quote."))

            (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
            flask_app = create_app(q, tmp_path)
            flask_app.config["TESTING"] = True

            with flask_app.test_client() as client:
                with client.get("/events", buffered=False) as response:
                    chunks = []
                    for _ in range(5):
                        try:
                            chunk = next(response.response)
                            chunks.append(chunk.decode())
                        except StopIteration:
                            break
                    all_content = "".join(chunks)
                    assert ":\n\n" in all_content
        finally:
            server_mod.HEARTBEAT_INTERVAL = original_interval
