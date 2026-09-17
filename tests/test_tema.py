"""Tema claro/oscuro persistido."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "tema_test.db"
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
        data={"username": "tema_user", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda"]},
        follow_redirects=False,
    )


def test_tema_default_oscuro(web_client):
    _onboard(web_client)
    r = web_client.get("/app")
    assert r.status_code == 200
    assert b'data-theme="dark"' in r.content
    assert b"Tema claro" in r.content or b"theme" in r.content.lower()


def test_tema_claro_persiste(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/tema",
        data={"theme": "light", "next": "/app"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b'data-theme="light"' in r.content
    r = web_client.get("/app/ritual")
    assert r.status_code == 200
    assert b'data-theme="light"' in r.content
    r = web_client.post(
        "/app/tema",
        data={"theme": "dark", "next": "/app/rueda"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app/rueda" in r.headers.get("location", "")
    r = web_client.get("/app/rueda")
    assert b'data-theme="dark"' in r.content
