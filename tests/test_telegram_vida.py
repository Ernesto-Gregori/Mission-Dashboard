"""Telegram v2 · /alma, /coach y /semana."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None)


def _setup(client):
    _onboard(client)
    _link_admin("42")


def test_alma_sin_texto_no_llama(web_client, monkeypatch):
    _setup(web_client)
    called = []
    monkeypatch.setattr("app.asistente.responder", lambda *a, **k: called.append(1) or "hola")
    out = _say("/alma", "v1")
    assert "mensaje" in out.lower() and called == []


def test_alma_sin_categorias_explica(web_client, monkeypatch):
    _setup(web_client)
    monkeypatch.setattr("app.asistente.responder", lambda mensaje, flags, user_id=None: f"eco {mensaje}")
    out = _say("/alma cómo viene", "v2")
    assert out.startswith("eco cómo viene")
    assert "se activan en la app" in out.lower()


def test_coach_muestra_cupo(web_client, monkeypatch):
    _setup(web_client)
    monkeypatch.setattr(
        "app.coach_insights.generar_briefing",
        lambda user_id, plan=None, dias=7, force=False: (True, "ok", {"insights": [{"titulo": "Dormí poco"}]}),
    )
    monkeypatch.setattr(
        "app.coach_insights.resumen_cuota_briefing",
        lambda user_id, plan=None: {"usados": 1, "limite": 2, "restantes": 1, "ok": True},
    )
    out = _say("/coach", "v3")
    assert "Dormí poco" in out and "1/2" in out


def test_coach_sin_cupo_no_inventa(web_client, monkeypatch):
    _setup(web_client)
    monkeypatch.setattr(
        "app.coach_insights.generar_briefing",
        lambda *a, **k: (False, "Cupo de briefings de esta semana agotado (2/2).", None),
    )
    monkeypatch.setattr(
        "app.coach_insights.resumen_cuota_briefing",
        lambda *a, **k: {"usados": 2, "limite": 2, "restantes": 0, "ok": False},
    )
    out = _say("/coach", "v4")
    assert "agotado" in out and "2/2" in out


def test_semana_resume(web_client):
    _setup(web_client)
    out = _say("/semana", "v5")
    assert out.startswith("Semana del ") and "Enfoque:" in out and "Ejercicio:" in out
