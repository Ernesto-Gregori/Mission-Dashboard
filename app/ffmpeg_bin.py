"""Localiza ffmpeg/ffprobe: FFMPEG_PATH → PATH → binario embebido de imageio-ffmpeg."""
from __future__ import annotations

import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

from app.logging_config import get_logger

log = get_logger("ffmpeg_bin")

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def reset_ffmpeg_cache() -> None:
    resolve_ffmpeg.cache_clear()
    resolve_ffprobe.cache_clear()


def parse_ffmpeg_duration(stderr: str) -> float | None:
    m = _DURATION_RE.search(stderr or "")
    if not m:
        return None
    hours, minutes, seconds = int(m.group(1)), int(m.group(2)), float(m.group(3))
    dur = hours * 3600 + minutes * 60 + seconds
    if dur <= 0 or dur != dur:
        return None
    return dur


def _is_file(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def _imageio_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        log.warning({"event": "imageio_ffmpeg_failed", "error": type(e).__name__})
        return None
    if exe and _is_file(exe):
        return exe
    return None


@lru_cache(maxsize=1)
def resolve_ffmpeg() -> str:
    env = (os.getenv("FFMPEG_PATH") or "").strip()
    if _is_file(env):
        return env
    which = shutil.which("ffmpeg")
    if which:
        return which
    bundled = _imageio_ffmpeg_exe()
    if bundled:
        log.info({"event": "ffmpeg_using_imageio", "path": bundled})
        return bundled
    raise FileNotFoundError(
        "ffmpeg no está disponible (PATH, FFMPEG_PATH ni imageio-ffmpeg)"
    )


@lru_cache(maxsize=1)
def resolve_ffprobe() -> str | None:
    env = (os.getenv("FFPROBE_PATH") or "").strip()
    if _is_file(env):
        return env
    which = shutil.which("ffprobe")
    if which:
        return which
    try:
        ffmpeg = resolve_ffmpeg()
    except FileNotFoundError:
        return None
    sibling = str(Path(ffmpeg).parent / "ffprobe")
    if _is_file(sibling):
        return sibling
    return None
