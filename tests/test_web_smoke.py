"""Smoke tests — esqueleto FastAPI + HTMX."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

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

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


def test_health(web_client):
    r = web_client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["framework"] == "fastapi+htmx"


def test_setup_login_dashboard(web_client):
    # Sin usuarios → setup
    r = web_client.get("/login", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/setup" in r.headers.get("location", "")

    r = web_client.post(
        "/setup",
        data={
            "username": "admin_web",
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app" in r.headers.get("location", "")

    r = web_client.get("/app")
    assert r.status_code == 200
    assert b"Control de mando" in r.content
    assert b"admin_web" in r.content

    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    # sin onboarding completo + sin módulos → stub o warn coach path
    assert b"Finanzas" in r.content or b"finanzas" in r.content.lower()


def test_require_auth_redirect(web_client):
    r = web_client.get("/app", follow_redirects=False)
    # sin cookie de sesión
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")
