"""Transcripción de voz (STT) para las notas de audio que llegan por Telegram."""
from __future__ import annotations

import os
from pathlib import Path

from app.logging_config import get_logger
from app.secrets import get_secret

log = get_logger("stt")

STT_MODELS = {
    "groq": "whisper-large-v3",
    "openai": "whisper-1",
}


def _env(nombre: str) -> str:
    # EXERCISE_STT_* viene de la biblioteca de ejercicios que ya no existe; se
    # sigue leyendo para no romper los despliegues que la tienen configurada.
    return (os.getenv(nombre) or os.getenv(f"EXERCISE_{nombre}") or "").strip()


def stt_provider() -> str:
    raw = (_env("STT_PROVIDER") or "groq").lower()
    return raw if raw in STT_MODELS else "none"


def stt_model() -> str:
    return _env("STT_MODEL") or STT_MODELS.get(stt_provider(), "whisper-large-v3")


def _api_key_for(provider: str) -> str:
    if provider == "groq":
        from app.ai_client import _get_api_key

        return _get_api_key()
    if provider == "openai":
        return get_secret("OPENAI_API_KEY", "")
    return ""


def provider_ready(provider: str | None = None) -> bool:
    key = _api_key_for(provider or stt_provider())
    return bool(key) and len(key) > 12


def transcribe_audio(audio_path: Path) -> str:
    """STT. Cadena vacía si no hay audio, no hay clave, o el proveedor es none."""
    provider = stt_provider()
    if provider == "none" or not audio_path.is_file():
        return ""
    if not provider_ready(provider):
        log.info({"event": "stt_skipped", "reason": "no_key", "provider": provider})
        return ""
    try:
        if provider == "openai":
            return _transcribe_openai(audio_path)
        return _transcribe_groq(audio_path)
    except Exception as e:
        log.warning({"event": "stt_failed", "provider": provider, "error": type(e).__name__})
        return ""


def _transcribe_groq(audio_path: Path) -> str:
    from groq import Groq

    client = Groq(api_key=_api_key_for("groq"))
    with audio_path.open("rb") as fh:
        resp = client.audio.transcriptions.create(
            file=fh,
            model=stt_model(),
            language="es",
        )
    text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else "")
    return (text or "").strip()


def _transcribe_openai(audio_path: Path) -> str:
    import httpx

    headers = {"Authorization": f"Bearer {_api_key_for('openai')}"}
    with audio_path.open("rb") as fh, httpx.Client(timeout=90) as client:
        r = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files={"file": (audio_path.name, fh, "audio/wav")},
            data={"model": stt_model(), "language": "es"},
        )
        r.raise_for_status()
        data = r.json()
    return (data.get("text") or "").strip()
