"""Groq: visión (ejercicios/recibos) vs chat (GROQ_MODEL)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.groq_vision import (
    MAX_VISION_IMAGES,
    VISION_MODEL_DEFAULT,
    resolve_vision_model,
    vision_model,
    vision_models_to_try,
)


def _jpeg_bytes(size: int = 32) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (size, size), color=(20, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


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


def test_exercise_ai_model_defaults_to_shared_vision(monkeypatch):
    monkeypatch.delenv("EXERCISE_AI_MODEL", raising=False)
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")
    from app.exercise_ai import ai_model

    assert ai_model() == VISION_MODEL_DEFAULT


def test_complete_groq_sends_at_most_three_compressed_frames(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 40)
    monkeypatch.delenv("EXERCISE_AI_MODEL", raising=False)
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")

    captured: dict = {}

    class _Msg:
        content = '{"nombre_ejercicio":"Plancha"}'

    class _FakeCompletions:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=_Msg())])

    class _FakeClient:
        chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr("app.ai_client._get_api_key", lambda: "gsk_" + "x" * 40)
    monkeypatch.setattr("app.ai_client._hay_cuota", lambda: True)
    monkeypatch.setattr("app.ai_client._get_client", lambda: _FakeClient())
    monkeypatch.setattr("app.ai_client._registrar_llamada", lambda: None)
    monkeypatch.setattr("app.billing.cuota_ia_ok", lambda *a, **k: True)
    monkeypatch.setattr("app.billing.registrar_llamada_ia", lambda *a, **k: 1)

    frames = []
    for i in range(8):
        p = tmp_path / f"frame_{i:03d}.jpg"
        p.write_bytes(_jpeg_bytes(120))
        frames.append(p)

    from app.exercise_ai import complete_multimodal

    text = complete_multimodal("sys", "analiza", frames)
    assert "Plancha" in text
    assert captured["kwargs"]["model"] == VISION_MODEL_DEFAULT
    content = captured["kwargs"]["messages"][1]["content"]
    images = [c for c in content if c.get("type") == "image_url"]
    assert len(images) == MAX_VISION_IMAGES
    assert captured["kwargs"].get("response_format") == {"type": "json_object"}


def test_complete_groq_maps_missing_model_error(tmp_path, monkeypatch):
    p = tmp_path / "frame_001.jpg"
    p.write_bytes(_jpeg_bytes())

    class _Boom:
        def create(self, **kwargs):
            raise RuntimeError("Error code: 404 - model_not_found does not exist")

    class _FakeClient:
        chat = SimpleNamespace(completions=_Boom())

    monkeypatch.setattr("app.ai_client._get_api_key", lambda: "gsk_" + "x" * 40)
    monkeypatch.setattr("app.ai_client._hay_cuota", lambda: True)
    monkeypatch.setattr("app.ai_client._get_client", lambda: _FakeClient())
    monkeypatch.setattr("app.billing.cuota_ia_ok", lambda *a, **k: True)
    monkeypatch.delenv("EXERCISE_AI_MODEL", raising=False)

    from app.exercise_ai import ExerciseAIError, complete_multimodal

    with pytest.raises(ExerciseAIError, match="visión"):
        complete_multimodal("sys", "analiza", [p])
