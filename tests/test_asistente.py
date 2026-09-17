"""Asistente Alma — contexto opt-in e historial por usuario."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "asistente_test.db"

    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("MISSION_WEB", raising=False)

    import app.db.core as core

    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setattr(core, "usar_turso", lambda: False)
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client
    from app.tenant import clear_current_user

    clear_current_user()


def _onboard(client: TestClient, username: str = "alma_user") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "salud"]},
        follow_redirects=False,
    )


def test_asistente_requiere_login(web_client):
    r = web_client.get("/app/asistente", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "") or "/setup" in r.headers.get("location", "")


def test_asistente_pagina_y_permisos(web_client):
    _onboard(web_client)
    r = web_client.get("/app/asistente")
    assert r.status_code == 200
    assert b"Alma" in r.content
    assert b"share_habitos" in r.content
    assert b"share_tareas" in r.content
    assert b"share_salud" in r.content
    assert b"share_calendario" in r.content
    assert b'for="alma-mensaje"' in r.content
    assert b"Nada del dashboard se comparte" in r.content or b"nada" in r.content.lower()

    r = web_client.post(
        "/app/asistente/permisos",
        data={"share_habitos": "1", "share_salud": "1"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert 'id="share-habitos"' in body
    assert 'checked' in body


def test_asistente_guarda_historial_sin_llamar_groq_real(web_client, monkeypatch):
    _onboard(web_client)
    captured: dict = {}

    def fake_chat(mensaje, contexto="", historial=None, max_tokens=700):
        captured["mensaje"] = mensaje
        captured["contexto"] = contexto
        return "Priorizá el descanso esta tarde."

    monkeypatch.setattr("app.ai_client.chat_con_historial", fake_chat)

    r = web_client.post(
        "/app/asistente/mensaje",
        data={"mensaje": "¿Qué hago esta tarde?"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Qué hago esta tarde".encode() in r.content or b"tarde" in r.content
    assert b"Prioriz" in r.content
    assert "no autoriz" in captured["contexto"].lower() or "no asumas" in captured["contexto"].lower()
    assert "H\u00e1bitos (7" not in captured["contexto"]


def test_asistente_contexto_opt_in(web_client, monkeypatch):
    _onboard(web_client)
    from app.db.core import ejecutar
    from app.database import autenticar_usuario
    from app.timezone_config import hoy as _hoy

    user = autenticar_usuario("alma_user", "password1")
    uid = int(user["id"])
    ejecutar(
        """
        INSERT OR IGNORE INTO habitos_config
            (user_id, clave, label, emoji, hora, activo, orden)
        VALUES (?, 'oracion_test', 'OracionTestAlma', '🙏', '06:00', 1, 1)
        """,
        [uid],
    )
    ejecutar(
        """
        INSERT OR IGNORE INTO habitos_diarios_v2
            (user_id, fecha, habito_clave, completado)
        VALUES (?, ?, 'oracion_test', 1)
        """,
        [uid, str(_hoy())],
    )

    captured: dict = {}

    def fake_chat(mensaje, contexto="", historial=None, max_tokens=700):
        captured.setdefault("sistemas", []).append(contexto)
        return "Recibido."

    monkeypatch.setattr("app.ai_client.chat_con_historial", fake_chat)

    web_client.post(
        "/app/asistente/mensaje",
        data={"mensaje": "Hola sin datos"},
        follow_redirects=True,
    )
    assert captured["sistemas"]
    assert "OracionTestAlma" not in captured["sistemas"][0]

    web_client.post(
        "/app/asistente/mensaje",
        data={"mensaje": "Hola con habitos", "share_habitos": "1"},
        follow_redirects=True,
    )
    assert "OracionTestAlma" in captured["sistemas"][-1]


def test_asistente_mensaje_vacio(web_client):
    _onboard(web_client)
    r = web_client.post("/app/asistente/mensaje", data={"mensaje": "  "})
    assert r.status_code == 400
    assert b"mensaje" in r.content.lower()


def test_asistente_borrar_historial(web_client, monkeypatch):
    _onboard(web_client)
    monkeypatch.setattr(
        "app.ai_client.chat_con_historial",
        lambda *a, **k: "ok",
    )
    web_client.post(
        "/app/asistente/mensaje",
        data={"mensaje": "MensajeParaBorrar"},
        follow_redirects=True,
    )
    r = web_client.get("/app/asistente")
    assert b"MensajeParaBorrar" in r.content
    web_client.post("/app/asistente/borrar", follow_redirects=True)
    r = web_client.get("/app/asistente")
    assert b"MensajeParaBorrar" not in r.content
