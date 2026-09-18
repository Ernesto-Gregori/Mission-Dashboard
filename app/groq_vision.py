"""Groq visión vs chat.

Chat (asistente, WhatsApp, coach) usa GROQ_MODEL (texto).
Visión (recibos + fotogramas de ejercicio) usa GROQ_VISION_MODEL.
Llama 4 Scout/Maverick ya no están en el plan free/dev de Groq.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

VISION_MODEL_DEFAULT = "qwen/qwen3.6-27b"
VISION_MODEL_FALLBACKS = (
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
)
# qwen3.8 admite 3; qwen3.6 admite 5. Usamos 3 para ambos.
MAX_VISION_IMAGES = 3
VISION_TIMEOUT_S = 90.0
_429_SLEEPS = (4.0, 12.0, 25.0)

_RETIRED_OR_TEXT_ONLY = {
    "meta-llama/llama-4-scout-17b-16e-instruct": VISION_MODEL_DEFAULT,
    "meta-llama/llama-4-maverick-17b-128e-instruct": VISION_MODEL_DEFAULT,
    "llama-3.2-11b-vision-preview": VISION_MODEL_DEFAULT,
    "llama-3.2-90b-vision-preview": VISION_MODEL_DEFAULT,
    "openai/gpt-oss-120b": VISION_MODEL_DEFAULT,
    "llama-3.3-70b-versatile": VISION_MODEL_DEFAULT,
    "qwen/qwen3-27b": VISION_MODEL_DEFAULT,
}


def resolve_vision_model(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return VISION_MODEL_DEFAULT
    return _RETIRED_OR_TEXT_ONLY.get(name, name)


def vision_model() -> str:
    from app.secrets import get_secret

    raw = (
        get_secret("GROQ_VISION_MODEL", "")
        or os.environ.get("GROQ_VISION_MODEL")
        or VISION_MODEL_DEFAULT
    ).strip()
    return resolve_vision_model(raw)


def vision_models_to_try() -> list[str]:
    primary = vision_model()
    out: list[str] = []
    for m in (primary, *VISION_MODEL_FALLBACKS):
        resolved = resolve_vision_model(m)
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def humanize_vision_error(err: str, *, model: str) -> str:
    low = (err or "").lower()
    if "model_not_found" in low or "does not exist" in low or "decommissioned" in low:
        return (
            f"El modelo de visión «{model}» no está disponible en Groq. "
            f"Usa GROQ_VISION_MODEL={VISION_MODEL_DEFAULT} "
            "(GROQ_MODEL es solo chat/texto)."
        )
    if "429" in err or "rate_limit" in low:
        return "Groq está limitando peticiones (429). Espera un minuto e intenta de nuevo."
    if "timeout" in low or "timed out" in low:
        return "Groq tardó demasiado en responder. Reintenta en un minuto."
    if "invalid_api_key" in low or "unauthorized" in low or "401" in err:
        return "GROQ_API_KEY inválida o revocada. Revisa la clave en el entorno."
    if "image" in low and ("too large" in low or "max" in low or "too many" in low):
        return "La imagen o la cantidad de fotogramas supera el límite de Groq."
    if "content" in low and "image" in low:
        return (
            f"«{model}» no acepta imágenes. "
            f"Configura GROQ_VISION_MODEL={VISION_MODEL_DEFAULT}."
        )
    short = (err or "error desconocido").strip().replace("\n", " ")
    if len(short) > 180:
        short = short[:177] + "…"
    return f"Error de visión Groq ({model}): {short}"


def _wait_rate_limit_lock(max_wait: float = 70.0) -> None:
    from app import ai_client

    until = float(ai_client._estado.get("bloqueado_hasta") or 0)
    wait = until - time.time()
    if 0 < wait <= max_wait:
        time.sleep(wait)


def _post_vision(client, create_kwargs: dict[str, Any]):
    kwargs = dict(create_kwargs)
    kwargs.setdefault("timeout", VISION_TIMEOUT_S)
    try:
        return client.chat.completions.create(**kwargs)
    except TypeError:
        kwargs.pop("timeout", None)
        kwargs.pop("reasoning_effort", None)
        if "max_completion_tokens" in kwargs:
            kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        err0 = str(e).lower()
        retried = False
        if "timeout" in err0:
            kwargs.pop("timeout", None)
            retried = True
        if "reasoning_effort" in err0:
            kwargs.pop("reasoning_effort", None)
            retried = True
        if "max_completion_tokens" in err0 and "max_completion_tokens" in kwargs:
            kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
            retried = True
        if not retried:
            raise
        return client.chat.completions.create(**kwargs)


def create_vision_completion(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 2048,
) -> tuple[Optional[str], Optional[str]]:
    """
    Llama a Groq con modelos de visión (JSON). Retorna (texto|None, error_humano|None).
    """
    from app import ai_client

    if not ai_client._get_api_key():
        return None, "Falta GROQ_API_KEY en el entorno (.env / secrets)."
    if not ai_client._hay_cuota():
        _wait_rate_limit_lock()
    if not ai_client._hay_cuota():
        return None, "Cuota diaria de IA agotada o bloqueada por rate-limit. Reintenta más tarde."
    try:
        from app.billing import cuota_ia_ok

        if not cuota_ia_ok():
            return None, (
                "Alcanzaste el límite mensual de IA del plan. "
                "Mejora el plan o espera al próximo mes."
            )
    except Exception:
        pass

    client = ai_client._get_client()
    if not client:
        return None, "No se pudo inicializar el cliente Groq. Revisa GROQ_API_KEY."

    last_err = ""
    last_model = vision_model()
    for model in vision_models_to_try():
        last_model = model
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
        }
        try:
            response = None
            last_err = ""
            for wait_s in (0.0, *_429_SLEEPS):
                if wait_s:
                    time.sleep(wait_s)
                try:
                    response = _post_vision(client, create_kwargs)
                    break
                except Exception as e:
                    err = str(e)
                    last_err = err
                    low = err.lower()
                    if "429" in err or "rate_limit" in low:
                        continue
                    raise
            else:
                ai_client._registrar_error_429(30)
                return None, humanize_vision_error(
                    last_err or "429", model=model
                )
            ai_client._registrar_llamada()
            try:
                from app.billing import registrar_llamada_ia

                registrar_llamada_ia()
            except Exception:
                pass
            ai_client._estado["conexion_ok"] = True
            content = response.choices[0].message.content
            if content:
                return content, None
            last_err = f"Respuesta vacía del modelo {model}."
        except Exception as e:
            err = str(e)
            last_err = err
            if "429" in err or "rate_limit" in err.lower():
                ai_client._registrar_error_429(65)
                return None, humanize_vision_error(err, model=model)
            low = err.lower()
            if (
                "model_not_found" in low
                or "does not exist" in low
                or "decommissioned" in low
            ):
                continue
            return None, humanize_vision_error(err, model=model)
    return None, humanize_vision_error(last_err or "sin respuesta", model=last_model)
