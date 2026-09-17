"""Proveedor de IA multimodal + STT configurable por entorno (no hardcodeado)."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from app.logging_config import get_logger
from app.secrets import get_secret

log = get_logger("exercise_ai")

DEFAULT_PROVIDERS = {
    "groq": {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "stt_model": "whisper-large-v3",
    },
    "openai": {
        "model": "gpt-4o",
        "stt_model": "whisper-1",
    },
    "anthropic": {
        "model": "claude-sonnet-4-20250514",
        "stt_model": "",
    },
}


class ExerciseAIError(RuntimeError):
    """Fallo del proveedor de IA / STT."""


def ai_provider() -> str:
    raw = (os.getenv("EXERCISE_AI_PROVIDER") or "groq").strip().lower()
    return raw if raw in DEFAULT_PROVIDERS else "groq"


def stt_provider() -> str:
    raw = (os.getenv("EXERCISE_STT_PROVIDER") or ai_provider()).strip().lower()
    if raw in ("none", "off", "disabled"):
        return "none"
    return raw if raw in DEFAULT_PROVIDERS else "none"


def ai_model() -> str:
    override = (os.getenv("EXERCISE_AI_MODEL") or "").strip()
    if override:
        return override
    return DEFAULT_PROVIDERS[ai_provider()]["model"]


def stt_model() -> str:
    override = (os.getenv("EXERCISE_STT_MODEL") or "").strip()
    if override:
        return override
    return DEFAULT_PROVIDERS.get(stt_provider(), {}).get("stt_model") or "whisper-large-v3"


def _api_key_for(provider: str) -> str:
    if provider == "groq":
        return get_secret("GROQ_API_KEY", "")
    if provider == "openai":
        return get_secret("OPENAI_API_KEY", "")
    if provider == "anthropic":
        return get_secret("ANTHROPIC_API_KEY", "")
    return ""


def provider_ready(provider: str | None = None) -> bool:
    p = provider or ai_provider()
    key = _api_key_for(p)
    return bool(key) and len(key) > 12


def _b64_jpeg(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def complete_multimodal(
    system: str,
    user_text: str,
    frame_paths: list[Path],
    user_id: int | None = None,
) -> str:
    """Envía frames JPEG + texto al proveedor configurado. Retorna el texto crudo."""
    provider = ai_provider()
    if not provider_ready(provider):
        raise ExerciseAIError(
            f"Falta la API key del proveedor '{provider}'. "
            "Configura EXERCISE_AI_PROVIDER y la clave correspondiente."
        )
    frames = frame_paths[:10]
    if provider == "anthropic":
        text = _complete_anthropic(system, user_text, frames)
    elif provider == "openai":
        text = _complete_openai(system, user_text, frames)
    else:
        text = _complete_groq(system, user_text, frames)
    _meter_ia(user_id)
    return text


def transcribe_audio(audio_path: Path) -> str:
    """STT. Cadena vacía si no hay audio, no hay clave, o el proveedor es none."""
    provider = stt_provider()
    if provider == "none" or not audio_path.is_file():
        return ""
    if not provider_ready(provider):
        log.info({"event": "exercise_stt_skipped", "reason": "no_key", "provider": provider})
        return ""
    try:
        if provider == "openai":
            return _transcribe_openai(audio_path)
        if provider == "groq":
            return _transcribe_groq(audio_path)
    except Exception as e:
        log.warning({"event": "exercise_stt_failed", "provider": provider, "error": type(e).__name__})
        return ""
    return ""


def _complete_groq(system: str, user_text: str, frames: list[Path]) -> str:
    from groq import Groq

    content: list[dict] = [{"type": "text", "text": user_text}]
    for path in frames:
        b64 = _b64_jpeg(path)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    client = Groq(api_key=_api_key_for("groq"))
    resp = client.chat.completions.create(
        model=ai_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        max_tokens=1200,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def _complete_openai(system: str, user_text: str, frames: list[Path]) -> str:
    import httpx

    content: list[dict] = [{"type": "text", "text": user_text}]
    for path in frames:
        b64 = _b64_jpeg(path)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    payload = {
        "model": ai_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "max_tokens": 1200,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {_api_key_for('openai')}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=90) as client:
        r = client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


def _complete_anthropic(system: str, user_text: str, frames: list[Path]) -> str:
    import httpx

    content: list[dict] = []
    for path in frames:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": _b64_jpeg(path),
                },
            }
        )
    content.append({"type": "text", "text": user_text})
    payload = {
        "model": ai_model(),
        "max_tokens": 1200,
        "temperature": 0.2,
        "system": system,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": _api_key_for("anthropic"),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    with httpx.Client(timeout=90) as client:
        r = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    parts = data.get("content") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
    return "\n".join(texts).strip()


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


def _meter_ia(user_id: int | None = None) -> None:
    try:
        from app.billing import registrar_llamada_ia

        registrar_llamada_ia(user_id=user_id)
    except Exception:
        pass
