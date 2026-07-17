"""Animated GIF recording validation and conversion helpers."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import time

from .annotation import CropRectangle


RECORDING_PREFIX = "grab-recording-"
RECORDING_SUFFIXES = frozenset({".mp4", ".webm"})
MAX_RECORDING_AGE = 24 * 60 * 60
GIF_FRAME_RATE = 15
GIF_MAX_DIMENSION = 1280


def validate_recording_path(path: Path, runtime_directory: Path) -> Path:
    """Return a safe recording path owned by Grab's runtime workflow."""
    if path.is_symlink():
        raise ValueError("The recording file is invalid.")
    path = path.resolve(strict=True)
    runtime_directory = runtime_directory.resolve(strict=True)
    if path.parent != runtime_directory:
        raise ValueError("The recording file is outside Grab's runtime directory.")
    if not path.name.startswith(RECORDING_PREFIX):
        raise ValueError("The recording filename is invalid.")
    if path.suffix.lower() not in RECORDING_SUFFIXES or not path.is_file():
        raise ValueError("The recording file is invalid.")
    return path


def cleanup_recordings(
    runtime_directory: Path,
    now: float | None = None,
    maximum_age: int = MAX_RECORDING_AGE,
) -> None:
    """Remove abandoned Grab recordings without touching unrelated files."""
    now = time.time() if now is None else now
    try:
        candidates = runtime_directory.glob(f"{RECORDING_PREFIX}*")
        for candidate in candidates:
            try:
                if (
                    candidate.suffix.lower() in RECORDING_SUFFIXES
                    and candidate.is_file()
                    and not candidate.is_symlink()
                ):
                    if now - candidate.stat().st_mtime > maximum_age:
                        candidate.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


def gif_filter(crop: CropRectangle) -> str:
    """Build the palette-based filter used for consistent, compact GIFs."""
    if crop.width <= 0 or crop.height <= 0 or crop.left < 0 or crop.top < 0:
        raise ValueError("The crop rectangle is invalid.")
    return (
        f"[0:v]fps={GIF_FRAME_RATE},"
        f"crop={crop.width}:{crop.height}:{crop.left}:{crop.top},"
        f"scale=w='min({GIF_MAX_DIMENSION},iw)':"
        f"h='min({GIF_MAX_DIMENSION},ih)':"
        "force_original_aspect_ratio=decrease:flags=lanczos,"
        "split[frames][palette_source];"
        "[palette_source]palettegen=stats_mode=diff[palette];"
        "[frames][palette]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
    )


def gif_command(source: Path, destination: Path, crop: CropRectangle) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        gif_filter(crop),
        "-an",
        "-loop",
        "0",
        str(destination),
    ]


def next_recording_name(when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"Screen Recording {when:%Y-%m-%d %H-%M-%S}.gif"


def atomic_replace(source: Path, destination: Path) -> None:
    """Move a completed GIF into place and make it user-readable."""
    os.chmod(source, 0o644)
    os.replace(source, destination)
