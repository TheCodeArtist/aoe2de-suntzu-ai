from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from backend.capture import (
    MAX_WIDTH,
    _resize_if_needed,
    capture_window,
    get_window_handle,
    image_to_base64,
    list_windows,
)
from backend.exceptions import CaptureError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_win32_window(hwnd: int = 12345) -> MagicMock:
    """Return a mock that mimics pygetwindow's Win32Window (has _hWnd)."""
    win = MagicMock()
    win._hWnd = hwnd
    return win


def _solid_image(width: int = 800, height: int = 600) -> Image.Image:
    return Image.new("RGB", (width, height), color=(120, 80, 40))


def _make_capture_mocks(hwnd: int = 12345, width: int = 1920, height: int = 1080):
    """Return a pre-wired set of GDI mocks for capture_window."""
    mock_win = _make_mock_win32_window(hwnd)

    # Fake bitmap that returns plausible bmpinfo/bmpstr
    bmp_info = {"bmWidth": width, "bmHeight": height}
    bmp_str = bytes(width * height * 4)  # BGRX, all zeros
    mock_bitmap = MagicMock()
    mock_bitmap.GetInfo.return_value = bmp_info
    mock_bitmap.GetBitmapBits.return_value = bmp_str
    mock_bitmap.GetHandle.return_value = 9999

    mock_mfc_dc = MagicMock()
    mock_save_dc = MagicMock()
    mock_save_dc.GetSafeHdc.return_value = 0xABCD
    mock_mfc_dc.CreateCompatibleDC.return_value = mock_save_dc

    return mock_win, mock_bitmap, mock_mfc_dc


# ---------------------------------------------------------------------------
# list_windows
# ---------------------------------------------------------------------------


class TestListWindows:
    def test_returns_list_of_non_empty_titles(self) -> None:
        with patch("backend.capture.gw.getAllTitles", return_value=["AoE2", "", "OBS"]):
            result = list_windows()
        assert result == ["AoE2", "OBS"]

    def test_returns_empty_list_when_no_windows(self) -> None:
        with patch("backend.capture.gw.getAllTitles", return_value=[]):
            result = list_windows()
        assert result == []

    def test_filters_whitespace_only_titles(self) -> None:
        with patch("backend.capture.gw.getAllTitles", return_value=["   ", "Valid"]):
            result = list_windows()
        assert result == ["Valid"]

    def test_returns_list_type(self) -> None:
        with patch("backend.capture.gw.getAllTitles", return_value=["Win"]):
            result = list_windows()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_window_handle
# ---------------------------------------------------------------------------


class TestGetWindowHandle:
    def test_returns_hwnd_integer(self) -> None:
        mock_win = _make_mock_win32_window(hwnd=42)
        with patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]):
            hwnd = get_window_handle("AoE2")
        assert hwnd == 42

    def test_raises_capture_error_when_not_found(self) -> None:
        with patch("backend.capture.gw.getWindowsWithTitle", return_value=[]):
            with pytest.raises(CaptureError, match="Window not found"):
                get_window_handle("Non-existent")

    def test_returns_first_match_hwnd(self) -> None:
        win1 = _make_mock_win32_window(hwnd=10)
        win2 = _make_mock_win32_window(hwnd=20)
        with patch("backend.capture.gw.getWindowsWithTitle", return_value=[win1, win2]):
            hwnd = get_window_handle("AoE2")
        assert hwnd == 10


# ---------------------------------------------------------------------------
# capture_window
# ---------------------------------------------------------------------------


class TestCaptureWindow:
    def _setup_full_capture_patches(
        self,
        hwnd: int = 12345,
        width: int = 800,
        height: int = 600,
        print_result: int = 1,
    ):
        """Return a context manager stack that makes capture_window succeed."""
        mock_win, mock_bitmap, mock_mfc_dc = _make_capture_mocks(hwnd, width, height)
        mock_save_dc = mock_mfc_dc.CreateCompatibleDC.return_value

        patches = [
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, width, height)),
            patch("backend.capture.win32gui.GetWindowDC", return_value=0xBEEF),
            patch("backend.capture.win32ui.CreateDCFromHandle", return_value=mock_mfc_dc),
            patch("backend.capture.win32ui.CreateBitmap", return_value=mock_bitmap),
            patch("backend.capture.windll.user32.PrintWindow", return_value=print_result),
            patch("backend.capture.win32gui.DeleteObject"),
            patch("backend.capture.win32gui.ReleaseDC"),
        ]
        return patches

    def test_returns_pil_image(self) -> None:
        patches = self._setup_full_capture_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            img = capture_window("AoE2")
        assert isinstance(img, Image.Image)

    def test_image_not_wider_than_max_width(self) -> None:
        patches = self._setup_full_capture_patches(width=3840, height=2160)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
        ):
            img = capture_window("AoE2")
        assert img.width <= MAX_WIDTH

    def test_raises_capture_error_when_window_not_found(self) -> None:
        with patch("backend.capture.gw.getWindowsWithTitle", return_value=[]):
            with pytest.raises(CaptureError, match="Window not found"):
                capture_window("Missing")

    def test_raises_capture_error_on_invalid_dimensions(self) -> None:
        mock_win = _make_mock_win32_window()
        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, 0, 0)),
        ):
            with pytest.raises(CaptureError, match="invalid dimensions"):
                capture_window("AoE2")

    def test_raises_capture_error_on_zero_height(self) -> None:
        mock_win = _make_mock_win32_window()
        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, 1920, 0)),
        ):
            with pytest.raises(CaptureError, match="invalid dimensions"):
                capture_window("AoE2")

    def test_raises_capture_error_when_get_window_rect_fails(self) -> None:
        mock_win = _make_mock_win32_window()
        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", side_effect=OSError("access denied")),
        ):
            with pytest.raises(CaptureError, match="Failed to get window rect"):
                capture_window("AoE2")

    def test_fallback_print_window_used_on_first_failure(self) -> None:
        """PrintWindow(hwnd, hdc, 2) returns 0 → fallback to PrintWindow(hwnd, hdc, 0)."""
        mock_win = _make_mock_win32_window()
        mock_win2, mock_bitmap, mock_mfc_dc = _make_capture_mocks()
        # Return 0 first (PW_RENDERFULLCONTENT fails), then 1 (standard succeeds)
        side_effects = [0, 1]

        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, 800, 600)),
            patch("backend.capture.win32gui.GetWindowDC", return_value=0xBEEF),
            patch("backend.capture.win32ui.CreateDCFromHandle", return_value=mock_mfc_dc),
            patch("backend.capture.win32ui.CreateBitmap", return_value=mock_bitmap),
            patch("backend.capture.windll.user32.PrintWindow", side_effect=side_effects),
            patch("backend.capture.win32gui.DeleteObject"),
            patch("backend.capture.win32gui.ReleaseDC"),
        ):
            img = capture_window("AoE2")
        assert isinstance(img, Image.Image)

    def test_cleanup_error_is_silently_ignored(self) -> None:
        """If GDI cleanup raises, capture_window must still return an image."""
        mock_win = _make_mock_win32_window()
        _, mock_bitmap, mock_mfc_dc = _make_capture_mocks()

        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, 800, 600)),
            patch("backend.capture.win32gui.GetWindowDC", return_value=0xBEEF),
            patch("backend.capture.win32ui.CreateDCFromHandle", return_value=mock_mfc_dc),
            patch("backend.capture.win32ui.CreateBitmap", return_value=mock_bitmap),
            patch("backend.capture.windll.user32.PrintWindow", return_value=1),
            patch("backend.capture.win32gui.DeleteObject", side_effect=OSError("cleanup fail")),
            patch("backend.capture.win32gui.ReleaseDC"),
        ):
            img = capture_window("AoE2")
        assert isinstance(img, Image.Image)

    def test_raises_capture_error_when_both_print_window_fail(self) -> None:
        """Both PrintWindow attempts returning 0 must raise CaptureError."""
        mock_win = _make_mock_win32_window()
        mock_win2, mock_bitmap, mock_mfc_dc = _make_capture_mocks()

        with (
            patch("backend.capture.gw.getWindowsWithTitle", return_value=[mock_win]),
            patch("backend.capture.win32gui.GetWindowRect", return_value=(0, 0, 800, 600)),
            patch("backend.capture.win32gui.GetWindowDC", return_value=0xBEEF),
            patch("backend.capture.win32ui.CreateDCFromHandle", return_value=mock_mfc_dc),
            patch("backend.capture.win32ui.CreateBitmap", return_value=mock_bitmap),
            patch("backend.capture.windll.user32.PrintWindow", return_value=0),
            patch("backend.capture.win32gui.DeleteObject"),
            patch("backend.capture.win32gui.ReleaseDC"),
        ):
            with pytest.raises(CaptureError, match="PrintWindow failed"):
                capture_window("AoE2")


# ---------------------------------------------------------------------------
# _resize_if_needed
# ---------------------------------------------------------------------------


class TestResizeIfNeeded:
    def test_no_resize_when_within_limit(self) -> None:
        img = _solid_image(800, 600)
        result = _resize_if_needed(img)
        assert result.width == 800
        assert result.height == 600

    def test_resizes_wide_image(self) -> None:
        img = _solid_image(2560, 1440)
        result = _resize_if_needed(img)
        assert result.width == MAX_WIDTH

    def test_preserves_aspect_ratio(self) -> None:
        img = _solid_image(2560, 1440)
        result = _resize_if_needed(img)
        original_ratio = 2560 / 1440
        new_ratio = result.width / result.height
        assert abs(original_ratio - new_ratio) < 0.01

    def test_exact_max_width_not_resized(self) -> None:
        img = _solid_image(MAX_WIDTH, 720)
        result = _resize_if_needed(img)
        assert result.width == MAX_WIDTH
        assert result.height == 720

    def test_returns_same_object_when_no_resize_needed(self) -> None:
        img = _solid_image(640, 480)
        result = _resize_if_needed(img)
        assert result is img


# ---------------------------------------------------------------------------
# image_to_base64
# ---------------------------------------------------------------------------


class TestImageToBase64:
    def test_returns_valid_base64_string(self) -> None:
        img = _solid_image(100, 100)
        result = image_to_base64(img)
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_result_is_jpeg(self) -> None:
        img = _solid_image(100, 100)
        result = image_to_base64(img)
        decoded = base64.b64decode(result)
        assert decoded[:2] == b"\xff\xd8"

    def test_accepts_rgba_image(self) -> None:
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        result = image_to_base64(img)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_data_uri_prefix(self) -> None:
        """Result must be a plain base64 string, not a data: URI."""
        img = _solid_image(10, 10)
        result = image_to_base64(img)
        assert not result.startswith("data:")
