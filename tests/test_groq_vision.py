"""Groq: visión (recibos) vs chat (GROQ_MODEL)."""
from __future__ import annotations

from types import SimpleNamespace

from app.groq_vision import (
    MAX_VISION_IMAGES,
    VISION_MODEL_DEFAULT,
    create_vision_completion,
    resolve_vision_model,
    vision_model,
    vision_models_to_try,
)


def _mensajes() -> list[dict]:
    return [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "analiza"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,AAAA"},
                },
            ],
        },
    ]


def _cliente_falso(monkeypatch, completions) -> None:
    class _FakeClient:
        chat = SimpleNamespace(completions=completions)

    monkeypatch.setattr("app.ai_client._get_api_key", lambda: "gsk_" + "x" * 40)
    monkeypatch.setattr("app.ai_client._hay_cuota", lambda: True)
    monkeypatch.setattr("app.ai_client._get_client", lambda: _FakeClient())
    monkeypatch.setattr("app.ai_client._registrar_llamada", lambda: None)
    monkeypatch.setattr("app.billing.cuota_ia_ok", lambda *a, **k: True)
    monkeypatch.setattr("app.billing.registrar_llamada_ia", lambda *a, **k: 1)


def test_vision_default_is_qwen_not_scout():
    assert VISION_MODEL_DEFAULT == "qwen/qwen3.6-27b"
    assert "llama-4-scout" not in VISION_MODEL_DEFAULT


def test_retired_scout_aliases_to_qwen():
    assert (
        resolve_vision_model("meta-llama/llama-4-scout-17b-16e-instruct")
        == VISION_MODEL_DEFAULT
    )


def test_chat_model_is_not_used_for_vision():
    assert resolve_vision_model("openai/gpt-oss-120b") == VISION_MODEL_DEFAULT


def test_vision_model_reads_env(monkeypatch):
    monkeypatch.setenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")
    assert vision_model() == "qwen/qwen3.8-27b"


def test_vision_models_to_try_includes_qwen_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")
    models = vision_models_to_try()
    assert models[0] == "qwen/qwen3.6-27b"
    assert "qwen/qwen3.8-27b" in models
    assert all("llama-4-scout" not in m for m in models)


def test_vision_pide_json_al_modelo_de_vision(monkeypatch):
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")
    captured: dict = {}

    class _Msg:
        content = '{"total":"12.50"}'

    class _FakeCompletions:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=_Msg())])

    _cliente_falso(monkeypatch, _FakeCompletions())

    text, err = create_vision_completion(_mensajes())
    assert err is None
    assert "12.50" in text
    assert captured["kwargs"]["model"] == VISION_MODEL_DEFAULT
    assert captured["kwargs"].get("response_format") == {"type": "json_object"}
    assert MAX_VISION_IMAGES == 3


def test_vision_maps_missing_model_error(monkeypatch):
    class _Boom:
        def create(self, **kwargs):
            raise RuntimeError("Error code: 404 - model_not_found does not exist")

    _cliente_falso(monkeypatch, _Boom())

    text, err = create_vision_completion(_mensajes())
    assert text is None
    assert "visión" in err


def test_vision_retries_after_429(monkeypatch):
    calls = {"n": 0}
    sleeps: list[float] = []

    class _Msg:
        content = '{"total":"9.00"}'

    class _Flaky:
        def create(self, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("Error code: 429 - rate_limit_exceeded")
            return SimpleNamespace(choices=[SimpleNamespace(message=_Msg())])

    monkeypatch.setattr("app.groq_vision.time.sleep", lambda s: sleeps.append(s))
    _cliente_falso(monkeypatch, _Flaky())

    text, err = create_vision_completion(_mensajes())
    assert err is None
    assert "9.00" in text
    assert calls["n"] == 3
    assert sleeps
