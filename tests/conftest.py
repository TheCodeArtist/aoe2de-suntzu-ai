"""Pytest configuration and shared fixtures for all test suites."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


TESTS_DIR = Path(__file__).parent


@pytest.fixture()
def sample_jpeg_path() -> Path:
    """Absolute path to the pre-generated 1×1 green JPEG in tests/assets/."""
    return TESTS_DIR / "assets" / "sample.jpg"


@pytest.fixture()
def sample_image() -> Image.Image:
    """A minimal 1×1 green RGB PIL Image for use in capture roundtrip tests."""
    return Image.new("RGB", (1, 1), color=(0, 128, 0))
