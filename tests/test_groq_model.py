"""Modelo Groq por defecto tras el retiro de llama-3.3-70b-versatile."""


def test_modelo_default_no_es_llama_retirado(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr(
        "app.secrets.get_secret",
        lambda name, default="": default,
    )
    from app.ai_client import MODELO, _modelo

    assert _modelo() == "openai/gpt-oss-120b"
    assert MODELO == "openai/gpt-oss-120b"
    assert "llama-3.3-70b-versatile" not in _modelo()


def test_groq_model_env_override(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    monkeypatch.setattr(
        "app.secrets.get_secret",
        lambda name, default="": default,
    )
    from app.ai_client import _modelo

    assert _modelo() == "qwen/qwen3.6-27b"
