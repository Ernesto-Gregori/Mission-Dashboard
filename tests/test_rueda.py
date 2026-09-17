"""Rueda de la vida — puntuaciones 0–10 y dibujo SVG."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "rueda_test.db"
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


def _onboard(client: TestClient) -> None:
    r = client.post(
        "/setup",
        data={"username": "rueda_user", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda"]},
        follow_redirects=False,
    )


def test_rueda_pagina_y_guarda(web_client):
    _onboard(web_client)
    r = web_client.get("/app/rueda")
    assert r.status_code == 200
    assert b"Rueda de la vida" in r.content
    assert b"rueda-svg" in r.content
    assert b'id="rueda-fe"' in r.content
    assert b'id="rueda-salud"' in r.content
    r = web_client.post(
        "/app/rueda",
        data={
            "fe": "8",
            "matrimonio": "7",
            "salud": "6",
            "finanzas": "5",
            "trabajo": "7",
            "relaciones": "6",
            "descanso": "4",
            "proposito": "9",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert 'id="rueda-fe"' in body
    assert 'value="8"' in body
    assert 'value="9"' in body
    assert "rueda-fill" in body


def test_rueda_rechaza_fuera_de_rango(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/rueda",
        data={
            "fe": "11",
            "matrimonio": "7",
            "salud": "6",
            "finanzas": "5",
            "trabajo": "7",
            "relaciones": "6",
            "descanso": "4",
            "proposito": "9",
        },
    )
    assert r.status_code == 400
    assert b"0" in r.content and b"10" in r.content
