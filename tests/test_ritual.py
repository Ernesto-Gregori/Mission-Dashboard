"""Ritual de mañana — gratitud, intención y hábitos compartidos."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user
from app.timezone_config import hoy as _hoy


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "ritual_test.db"
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
    clear_current_user()


def _onboard(client: TestClient, username: str = "ritual_user") -> None:
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


def test_ritual_requiere_login(web_client):
    r = web_client.get("/app/ritual", follow_redirects=False)
    assert r.status_code in (303, 307)


def test_ritual_pagina_y_guarda_habito(web_client):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.db.core import ejecutar

    user = autenticar_usuario("ritual_user", "password1")
    ejecutar(
        """
        INSERT OR IGNORE INTO habitos_config
            (user_id, clave, label, emoji, hora, activo, orden)
        VALUES (?, 'oracion_ritual', 'OracionRitual', '🙏', '05:45', 1, 1)
        """,
        [int(user["id"])],
    )
    r = web_client.get("/app/ritual", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    r = web_client.get("/app")
    assert r.status_code == 200
    assert b'id="ritual-gratitud"' in r.content
    assert b'id="ritual-intencion"' in r.content
    assert b"OracionRitual" in r.content

    r = web_client.post(
        "/app/ritual",
        data={
            "gratitud": "CafeConEsposa",
            "intencion": "TerminarElCapitulo",
            "habito": ["oracion_ritual"],
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"CafeConEsposa" in r.content
    assert b"TerminarElCapitulo" in r.content
    assert b"Registrado hoy" in r.content
    rows = ejecutar(
        """
        SELECT completado FROM habitos_diarios_v2
        WHERE user_id = ? AND habito_clave = ? AND fecha = ?
        """,
        [int(user["id"]), "oracion_ritual", str(_hoy())],
        fetchall=True,
    )
    assert rows and int(rows[0]["completado"]) == 1
