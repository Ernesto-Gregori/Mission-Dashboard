"""Almacenamiento privado de videos de ejercicio (galería → disco local)."""
from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

from app.db.core import DB_PATH
from app.ffmpeg_bin import parse_ffmpeg_duration, resolve_ffmpeg, resolve_ffprobe
from app.logging_config import get_logger

log = get_logger("exercise_uploads")

ALLOWED_EXT = {".mp4", ".mov"}
ALLOWED_MIME = {
    "video/mp4",
    "video/quicktime",
    "video/x-quicktime",
    "application/octet-stream",
    "",
}
DEFAULT_MAX_MB = 100
DEFAULT_MAX_SECONDS = 60
HARD_MAX_SECONDS = 90


class VideoUploadError(ValueError):
    """Error de validación de video (mensaje seguro para el usuario)."""


def max_video_bytes() -> int:
    raw = os.getenv("EXERCISE_VIDEO_MAX_MB", str(DEFAULT_MAX_MB))
    try:
        mb = float(raw)
    except ValueError:
        mb = DEFAULT_MAX_MB
    if mb <= 0:
        mb = DEFAULT_MAX_MB
    return max(1, int(mb * 1024 * 1024))


def max_video_seconds() -> int:
    raw = os.getenv("EXERCISE_VIDEO_MAX_SECONDS", str(DEFAULT_MAX_SECONDS))
    try:
        return max(5, int(float(raw)))
    except ValueError:
        return DEFAULT_MAX_SECONDS


def hard_max_video_seconds() -> int:
    raw = os.getenv("EXERCISE_VIDEO_HARD_MAX_SECONDS", str(HARD_MAX_SECONDS))
    try:
        return max(max_video_seconds(), int(float(raw)))
    except ValueError:
        return max(HARD_MAX_SECONDS, max_video_seconds())


def uploads_root() -> Path:
    override = (os.getenv("EXERCISE_STORAGE_DIR") or "").strip()
    root = Path(override) if override else (DB_PATH.parent / "uploads" / "exercises")
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_dir(user_id: int) -> Path:
    d = uploads_root() / str(int(user_id))
    d.mkdir(parents=True, exist_ok=True)
    return d


def looks_like_mp4_or_mov(data: bytes) -> bool:
    """ISO BMFF / QuickTime: 'ftyp' en offset 4."""
    return len(data) >= 12 and data[4:8] == b"ftyp"


def normalize_ext(filename: str | None) -> str:
    name = (filename or "").strip().lower()
    ext = Path(name).suffix
    return ext if ext in ALLOWED_EXT else ""


def validate_filename_and_mime(filename: str | None, content_type: str | None) -> str:
    ext = normalize_ext(filename)
    if not ext:
        raise VideoUploadError("Formato no aceptado. Usa un video .mp4 o .mov de tu galería.")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_MIME:
        raise VideoUploadError("Formato no aceptado. Usa un video .mp4 o .mov de tu galería.")
    return ext


def probe_video_duration(path: Path) -> float | None:
    """Duración en segundos vía ffprobe o ffmpeg -i. None si no se puede leer."""
    ffprobe = resolve_ffprobe()
    if ffprobe:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning({"event": "exercise_ffprobe_failed", "error": type(e).__name__})
        else:
            raw = (proc.stdout or "").strip()
            try:
                dur = float(raw)
            except ValueError:
                dur = None
            if dur is not None and dur > 0 and dur == dur:
                return dur

    try:
        ffmpeg = resolve_ffmpeg()
    except FileNotFoundError as e:
        log.warning({"event": "exercise_ffprobe_failed", "error": type(e).__name__})
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning({"event": "exercise_ffprobe_failed", "error": type(e).__name__})
        return None
    return parse_ffmpeg_duration((proc.stderr or "") + "\n" + (proc.stdout or ""))


def save_exercise_video(
    user_id: int,
    raw: bytes,
    filename: str | None,
    content_type: str | None = None,
) -> tuple[str, float | None]:
    """
    Valida y guarda. Retorna (ruta relativa, duración o None).
    No es una URL pública.
    """
    if not raw:
        raise VideoUploadError("El archivo está vacío.")
    ext = validate_filename_and_mime(filename, content_type)
    max_b = max_video_bytes()
    if len(raw) > max_b:
        mb = max_b // (1024 * 1024)
        raise VideoUploadError(f"El video supera el límite de {mb} MB.")
    if not looks_like_mp4_or_mov(raw[:64] if len(raw) > 64 else raw):
        raise VideoUploadError("El archivo no parece un video mp4/mov válido.")

    name = f"{uuid.uuid4().hex}{ext}"
    dest = user_dir(user_id) / name
    dest.write_bytes(raw)

    duration = probe_video_duration(dest)
    hard = hard_max_video_seconds()
    suggested = max_video_seconds()
    if duration is not None and duration > hard:
        dest.unlink(missing_ok=True)
        raise VideoUploadError(
            f"El video dura {duration:.0f} s. Sube un clip de un solo ejercicio "
            f"(máximo {hard} s; lo ideal es {suggested} s o menos)."
        )
    rel = f"data/uploads/exercises/{int(user_id)}/{name}"
    log.info(
        {
            "event": "exercise_video_saved",
            "user_id": int(user_id),
            "bytes": len(raw),
            "duration_s": round(duration, 1) if duration is not None else None,
        }
    )
    return rel, duration


def resolve_exercise_video_path(rel_path: str, user_id: int) -> Path | None:
    """Solo archivos del propio usuario bajo uploads/exercises/{uid}/."""
    if not rel_path:
        return None
    rel = rel_path.replace("\\", "/").lstrip("/")
    m = re.match(
        rf"^(?:data/)?uploads/exercises/{int(user_id)}/([A-Za-z0-9._-]+)$",
        rel,
    )
    if not m:
        return None
    name = m.group(1)
    full = (user_dir(user_id) / name).resolve()
    root = user_dir(user_id).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return None
    if not full.is_file():
        return None
    return full
