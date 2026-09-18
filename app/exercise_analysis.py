"""Pipeline async: frames ffmpeg → STT → modelo multimodal → JSON → DB."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path

from app.db.exercises import (
    CONFIANZAS,
    NIVELES,
    TIPOS_MOVIMIENTO,
    apply_analysis,
    mark_failed,
    obtener_exercise,
)
from app.exercise_ai import ExerciseAIError, complete_multimodal, transcribe_audio
from app.exercise_uploads import probe_video_duration, resolve_exercise_video_path
from app.ffmpeg_bin import resolve_ffmpeg
from app.groq_vision import MAX_VISION_IMAGES
from app.logging_config import get_logger

log = get_logger("exercise_analysis")

ANALYSIS_SYSTEM = (
    "Eres un coach de fitness experto analizando un ejercicio a partir de una "
    "secuencia de fotogramas y su transcripción de audio."
)

ANALYSIS_JSON_SPEC = """
Analiza el movimiento y devuelve ÚNICAMENTE un JSON con esta estructura exacta:

{
  "nombre_ejercicio": "string, nombre claro del ejercicio",
  "grupos_musculares_primarios": ["lista de 1-3 músculos principales"],
  "grupos_musculares_secundarios": ["lista opcional"],
  "equipamiento_detectado": ["ej: banda elástica", "pesa rusa", "peso corporal"],
  "nivel_dificultad": "principiante | intermedio | avanzado",
  "tipo_movimiento": "fuerza | cardio | movilidad | core | pliométrico",
  "series_reps_mencionadas": "extrae si el audio las menciona explícitamente, si no, escribe null",
  "series_reps_sugeridas": "si no se mencionaron, sugiere un rango razonable basado en el tipo de movimiento y nivel",
  "cues_de_forma": ["2-3 puntos clave de ejecución correcta observados en los frames"],
  "duracion_estimada_segundos": número si aplica (ej. planchas, isométricos),
  "confianza_analisis": "alta | media | baja — qué tan seguro estás de la identificación"
}

Reglas:
- Si el equipamiento no es claramente visible en los frames, no lo inventes; usa "no detectado" en la lista.
- Si la transcripción no aporta información útil (silencio, música, otro idioma que no entiendes), básate solo en los frames.
- No agregues texto fuera del JSON.
""".strip()


class AnalysisError(RuntimeError):
    """Fallo controlado del pipeline (mensaje para el usuario)."""


def build_user_prompt(transcript: str, n_frames: int) -> str:
    texto = (transcript or "").strip() or "(sin transcripción útil)"
    if len(texto) > 4000:
        texto = texto[:4000]
    # El spec pide este bloque literal, con N real y la transcripción interpolada.
    return (
        f"FOTOGRAMAS: [se adjuntan {n_frames} imágenes en orden cronológico, "
        f"tomadas del video]\n"
        f'TRANSCRIPCIÓN DEL AUDIO: "{texto}"\n\n'
        f"{ANALYSIS_JSON_SPEC}"
    )


def _fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _norm_enum(val, allowed: tuple[str, ...]) -> str | None:
    if val is None:
        return None
    raw = str(val).strip()
    folded = _fold(raw)
    for item in allowed:
        if folded == _fold(item) or folded.split("—")[0].strip() == _fold(item):
            return item
    # "alta | media | baja — …" → tomar el primer token
    first = folded.split()[0] if folded else ""
    for item in allowed:
        if first == _fold(item):
            return item
    return None


def _as_str_list(val) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [p.strip() for p in re.split(r"[,;\n]", s) if p.strip()]
    return [str(val).strip()]


def extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise AnalysisError("La IA no devolvió contenido.")
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise AnalysisError("La IA no devolvió JSON.")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise AnalysisError("No se pudo interpretar el JSON de la IA.") from e
    if not isinstance(data, dict):
        raise AnalysisError("El JSON de la IA no es un objeto.")
    return data


def parse_analysis_payload(text: str) -> dict:
    data = extract_json_object(text)
    nombre = str(data.get("nombre_ejercicio") or "").strip()
    if not nombre:
        raise AnalysisError("La IA no identificó el nombre del ejercicio.")

    nivel = _norm_enum(data.get("nivel_dificultad"), NIVELES)
    tipo = _norm_enum(data.get("tipo_movimiento"), TIPOS_MOVIMIENTO)
    conf = _norm_enum(data.get("confianza_analisis"), CONFIANZAS)
    if not nivel or not tipo or not conf:
        raise AnalysisError("La IA devolvió valores fuera del esquema esperado.")

    mencionadas = data.get("series_reps_mencionadas")
    if mencionadas in ("", "null", "None", None):
        mencionadas = None
    else:
        mencionadas = str(mencionadas).strip() or None

    sugeridas = str(data.get("series_reps_sugeridas") or "").strip() or None

    dur = data.get("duracion_estimada_segundos")
    dur_int = None
    if dur not in (None, "", "null", "n/a", "N/A"):
        try:
            dur_int = int(float(dur))
            if dur_int < 0:
                dur_int = None
        except (TypeError, ValueError):
            dur_int = None

    equipo = _as_str_list(data.get("equipamiento_detectado"))
    if not equipo:
        equipo = ["no detectado"]

    return {
        "nombre_ejercicio": nombre[:160],
        "grupos_musculares_primarios": _as_str_list(data.get("grupos_musculares_primarios"))[:3],
        "grupos_musculares_secundarios": _as_str_list(data.get("grupos_musculares_secundarios"))[:6],
        "equipamiento_detectado": equipo[:8],
        "nivel_dificultad": nivel,
        "tipo_movimiento": tipo,
        "series_reps_mencionadas": mencionadas[:160] if mencionadas else None,
        "series_reps_sugeridas": (sugeridas[:200] if sugeridas else None),
        "cues_de_forma": _as_str_list(data.get("cues_de_forma"))[:5],
        "duracion_estimada_segundos": dur_int,
        "confianza_analisis": conf,
    }


def _stderr_snip(proc) -> str:
    raw = getattr(proc, "stderr", b"") or b""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", "replace")
    else:
        text = str(raw)
    return text.strip()[:800]


def extract_keyframes(video_path: Path, dest_dir: Path, duration: float | None = None) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg = resolve_ffmpeg()
    except FileNotFoundError as e:
        log.error({"event": "exercise_ffmpeg_missing", "error": str(e)[:160]})
        raise AnalysisError("No se pudieron extraer fotogramas del video.") from e

    dur = duration if duration and duration > 0 else probe_video_duration(video_path) or 2.0
    n = max(1, min(MAX_VISION_IMAGES, int(round(dur / 1.5)) or 1))
    fps = n / max(dur, 0.5)
    pattern = str(dest_dir / "frame_%03d.jpg")
    # fps+escala → fps solo → primer fotograma (HEVC/VFR a veces rompe fps=).
    attempts = (
        ["-vf", f"fps={fps:.4f},scale=-2:480", "-frames:v", str(n), "-q:v", "4", pattern],
        ["-vf", f"fps={fps:.4f}", "-frames:v", str(n), "-q:v", "4", pattern],
        ["-ss", "0", "-frames:v", "1", "-q:v", "4", pattern],
    )
    last_err: BaseException | None = None
    for extra in attempts:
        for old in dest_dir.glob("frame_*.jpg"):
            old.unlink(missing_ok=True)
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-an", "-i", str(video_path), *extra]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            last_err = e
            log.warning(
                {
                    "event": "exercise_ffmpeg_extract_failed",
                    "error": type(e).__name__,
                    "attempt": extra[0],
                }
            )
            continue
        frames = sorted(dest_dir.glob("frame_*.jpg"))
        if proc.returncode == 0 and frames:
            return frames[:MAX_VISION_IMAGES]
        log.warning(
            {
                "event": "exercise_ffmpeg_extract_failed",
                "returncode": proc.returncode,
                "stderr": _stderr_snip(proc),
            }
        )
        last_err = AnalysisError("No se pudieron extraer fotogramas del video.")
    raise AnalysisError("No se pudieron extraer fotogramas del video.") from last_err


def extract_audio_wav(video_path: Path, dest_wav: Path) -> Path | None:
    try:
        ffmpeg = resolve_ffmpeg()
    except FileNotFoundError:
        log.warning({"event": "exercise_ffmpeg_missing", "stage": "audio"})
        return None
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dest_wav),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning({"event": "exercise_ffmpeg_audio_failed", "error": type(e).__name__})
        return None
    if proc.returncode != 0 or not dest_wav.is_file() or dest_wav.stat().st_size < 64:
        log.warning(
            {
                "event": "exercise_ffmpeg_audio_failed",
                "returncode": getattr(proc, "returncode", None),
                "stderr": _stderr_snip(proc),
            }
        )
        return None
    return dest_wav


def run_exercise_analysis(exercise_id: int, user_id: int) -> None:
    """
    Procesa un ejercicio en background. Nunca lanza: marca failed si algo sale mal.
    Borra frames temporales al terminar.
    """
    started = time.monotonic()
    row = obtener_exercise(exercise_id, user_id)
    if not row:
        log.warning({"event": "exercise_analysis_missing", "exercise_id": exercise_id})
        return
    video = resolve_exercise_video_path(row.get("source_video_url") or "", user_id)
    if not video:
        mark_failed(exercise_id, user_id, "No se encontró el video subido.")
        return

    try:
        from app.billing import cuota_ia_ok

        if not cuota_ia_ok(user_id=user_id):
            mark_failed(exercise_id, user_id, "Cuota de IA agotada este mes.")
            return
    except Exception:
        pass

    tmp = tempfile.TemporaryDirectory(prefix="ex_frames_")
    try:
        from app.exercise_ai import ai_model

        log.info(
            {
                "event": "exercise_analysis_start",
                "exercise_id": exercise_id,
                "model": ai_model(),
            }
        )
        frame_dir = Path(tmp.name) / "frames"
        audio_path = Path(tmp.name) / "audio.wav"
        frames = extract_keyframes(video, frame_dir)
        wav = extract_audio_wav(video, audio_path)
        transcript = ""
        if wav is not None:
            transcript = transcribe_audio(wav) or ""
        prompt = build_user_prompt(transcript, len(frames))
        raw = complete_multimodal(ANALYSIS_SYSTEM, prompt, frames, user_id=user_id)
        parsed = parse_analysis_payload(raw)
        apply_analysis(exercise_id, user_id, parsed)
        log.info(
            {
                "event": "exercise_analysis_ready",
                "exercise_id": exercise_id,
                "frames": len(frames),
                "has_transcript": bool(transcript),
                "ms": int((time.monotonic() - started) * 1000),
            }
        )
    except (AnalysisError, ExerciseAIError) as e:
        log.warning(
            {
                "event": "exercise_analysis_failed",
                "exercise_id": exercise_id,
                "stage": "pipeline",
                "error": str(e)[:160],
            }
        )
        mark_failed(exercise_id, user_id, str(e))
    except Exception as e:
        log.exception(
            "exercise_analysis_error exercise_id=%s err=%s",
            exercise_id,
            type(e).__name__,
        )
        mark_failed(
            exercise_id,
            user_id,
            "No se pudo completar el análisis. Puedes reintentarlo.",
        )
    finally:
        tmp.cleanup()
