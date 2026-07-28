"""Smoke tests — esqueleto FastAPI + HTMX + Coach."""
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

    # Evitar llamadas reales a Groq en coach
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


def _setup_user(client: TestClient, username: str = "admin_web") -> None:
    r = client.post(
        "/setup",
        data={
            "username": username,
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)


def test_health(web_client):
    r = web_client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["framework"] == "fastapi+htmx"


def test_setup_redirects_to_coach(web_client):
    r = web_client.get("/login", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/setup" in r.headers.get("location", "")

    _setup_user(web_client)

    # Sin onboarding → /app redirige a coach
    r = web_client.get("/app", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/app/coach" in r.headers.get("location", "")

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"Coach" in r.content
    assert b"Cu" in r.content or b"llam" in r.content  # formulario perfil


def test_coach_flow_activa_modulos(web_client):
    _setup_user(web_client, "coach_user")

    r = web_client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "recien casado",
            "objetivos": "finanzas y pareja",
            "tiempo": "15-20 min",
            "notas": "",
            "areas": ["finanzas", "pareja"],
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app/coach" in r.headers.get("location", "")

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"sistema propuesto" in r.content.lower() or b"Activar" in r.content

    # Activar agenda + finanzas + matrimonio (Free admin es premium en setup)
    r = web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas", "matrimonio"]},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/app" in r.headers.get("location", "")

    r = web_client.get("/app")
    assert r.status_code == 200
    assert b"Control de mando" in r.content
    assert b"activo" in r.content

    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    assert b"Finanzas" in r.content


def test_require_auth_redirect(web_client):
    r = web_client.get("/app", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")
