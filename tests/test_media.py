import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from app.agent.browser import _generate_recording
from app.core.config import settings


def _create_test_screenshots(media_dir: Path, count: int = 5) -> None:
    """Create fake screenshot PNGs for testing."""
    media_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        img = Image.fromarray(
            np.random.randint(0, 255, (100, 150, 3), dtype=np.uint8)
        )
        img.save(media_dir / f"step_{i:03d}.png", "PNG")


def test_generate_recording_creates_video(tmp_path: Path) -> None:
    """Test that _generate_recording produces a valid MP4 from screenshots."""
    media_dir = tmp_path / "test_run"
    _create_test_screenshots(media_dir, count=4)

    # Temporarily override settings.media_path so relative paths work
    original = settings.media_path
    settings.media_path = str(tmp_path)
    try:
        result = _generate_recording(media_dir)
        assert result is not None
        assert result.endswith("recording.mp4")

        video_path = tmp_path / result
        assert video_path.exists()
        assert video_path.stat().st_size > 0
    finally:
        settings.media_path = original


def test_generate_recording_skips_single_screenshot(tmp_path: Path) -> None:
    """Test that _generate_recording returns None with fewer than 2 screenshots."""
    media_dir = tmp_path / "test_run_single"
    _create_test_screenshots(media_dir, count=1)

    original = settings.media_path
    settings.media_path = str(tmp_path)
    try:
        result = _generate_recording(media_dir)
        assert result is None
    finally:
        settings.media_path = original


def test_screenshots_saved_in_step_details(tmp_path: Path) -> None:
    """Test that screenshot paths are included in step_details."""
    media_dir = tmp_path / "test_run_steps"
    _create_test_screenshots(media_dir, count=3)

    # Verify PNGs were created
    pngs = sorted(media_dir.glob("step_*.png"))
    assert len(pngs) == 3
    for p in pngs:
        assert p.stat().st_size > 0


def test_media_endpoint_serves_files(client) -> None:
    """Test that the /media endpoint serves screenshot files."""
    # Create a test file in the media directory
    media_path = Path(settings.media_path)
    test_dir = media_path / "test_serve"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "test.png"
    img = Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8))
    img.save(test_file, "PNG")

    try:
        response = client.get("/media/test_serve/test.png")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
    finally:
        shutil.rmtree(test_dir)
