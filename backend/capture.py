from __future__ import annotations

import base64
import io
import logging

import pygetwindow as gw
from PIL import Image

# New imports for background capture
import win32gui
import win32ui
import win32con
from ctypes import windll

from backend.exceptions import CaptureError

logger = logging.getLogger(__name__)

MAX_WIDTH = 1280
JPEG_QUALITY = 85


def list_windows() -> list[str]:
    """Return titles of all currently open, non-empty windows.

    Used to populate the Window Selector dropdown in the GUI.
    """
    return [title for title in gw.getAllTitles() if title.strip()]


def get_window_handle(title: str) -> int:
    """Return the window handle (HWND) for the named window.

    Args:
        title: Exact window title string (or partial match if pygetwindow supports it).

    Returns:
        The HWND as an integer.

    Raises:
        CaptureError: If no window with the given title is found.
    """
    matches = gw.getWindowsWithTitle(title)
    if not matches:
        raise CaptureError(f"Window not found: '{title}'")
    
    # pygetwindow returns Win32Window objects on Windows which have _hWnd
    return matches[0]._hWnd


def capture_window(title: str) -> Image.Image:
    """Capture the client area of the named window and return a PIL Image.

    Uses Windows GDI (PrintWindow) to capture the window content even if it
    is obscured or minimized (though minimized windows might need restoring).

    Args:
        title: Exact window title string.

    Returns:
        A PIL Image in RGB mode.

    Raises:
        CaptureError: If the window cannot be found or the screenshot fails.
    """
    hwnd = get_window_handle(title)

    # Get window dimensions
    # GetWindowRect gives the full window size including borders
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top
    except Exception as e:
        raise CaptureError(f"Failed to get window rect for '{title}': {e}")

    if width <= 0 or height <= 0:
         raise CaptureError(f"Window '{title}' has invalid dimensions: {width}x{height}")

    saveBitMap = None
    saveDC = None
    mfcDC = None
    hwndDC = None

    try:
        # Create device context
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()

        # Create bitmap object
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)

        # Select bitmap into saveDC
        saveDC.SelectObject(saveBitMap)

        # Print window content
        # PW_RENDERFULLCONTENT = 0x00000002 (Windows 8.1+)
        # If 2 fails or not supported, we can try 0.
        # Note: Some applications might return black screen with PrintWindow.
        result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        if result == 0:
             # Fallback to standard PrintWindow
             result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)

        if result == 0:
            raise CaptureError(f"PrintWindow failed for '{title}'")

        # Convert to PIL Image
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        
        img = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1)

    except Exception as exc:
        raise CaptureError(f"Screenshot failed for '{title}': {exc}") from exc
    finally:
        # Cleanup
        try:
            if saveBitMap: win32gui.DeleteObject(saveBitMap.GetHandle())
            if saveDC: saveDC.DeleteDC()
            if mfcDC: mfcDC.DeleteDC()
            if hwndDC: win32gui.ReleaseDC(hwnd, hwndDC)
        except Exception:
            pass # Ignore cleanup errors

    img = _resize_if_needed(img)
    logger.debug("Captured window '%s' at %dx%d.", title, img.width, img.height)
    return img


def _resize_if_needed(img: Image.Image) -> Image.Image:
    """Downscale the image to MAX_WIDTH if it exceeds that width.

    Preserves aspect ratio. Keeps the image unmodified if already within bounds.
    """
    if img.width <= MAX_WIDTH:
        return img
    ratio = MAX_WIDTH / img.width
    new_height = int(img.height * ratio)
    return img.resize((MAX_WIDTH, new_height), Image.LANCZOS)


def image_to_base64(img: Image.Image) -> str:
    """Encode a PIL Image as a JPEG base64 string for the OpenAI vision API.

    Args:
        img: Any PIL Image; will be converted to RGB before encoding.

    Returns:
        A plain base64 string (no data-URI prefix).
    """
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
