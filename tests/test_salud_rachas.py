"""Rachas y progreso de Salud."""
from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import as_user, clear_current_user
from app.timezone_config import hoy as _hoy


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "salud_racha_test.db"

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


def _onboard(client: TestClient, username: str = "racha_user") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["salud"]},
        follow_redirects=False,
    )


def test_salud_muestra_racha_y_graficos(web_client):
    _onboard(web_client)
    r = web_client.get("/app/m/salud")
    assert r.status_code == 200
    assert b"Racha" in r.content
    assert b"streak-count" in r.content
    assert b"progress-chart" in r.content
    assert b'for="goal-type"' in r.content
    assert b"Semana" in r.content
    assert b"Mes" in r.content


def test_salud_guardar_objetivo_pasos(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/m/salud/objetivo",
        data={"tipo": "pasos", "valor": "9000"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Pasos" in r.content
    assert b"9000" in r.content


def test_racha_ejercicio_consecutiva(web_client):
    _onboard(web_client)
    from app.database import autenticar_usuario, guardar_registro_salud
    from app.db.salud import calcular_racha_objetivo

    user = autenticar_usuario("racha_user", "password1")
    hoy = _hoy()
    with as_user(user):
        for i in range(3):
            d = hoy - timedelta(days=i)
            guardar_registro_salud(
                d.isoformat(),
                {
                    "hizo_ejercicio": True,
                    "tipo_ejercicio": "Caminata",
                    "duracion_minutos": 30,
                    "fuente_datos": "manual",
                },
            )
        assert calcular_racha_objetivo(int(user["id"])) == 3
        # Un hueco rompe
        guardar_registro_salud(
            (hoy - timedelta(days=1)).isoformat(),
            {"hizo_ejercicio": False, "fuente_datos": "manual"},
        )
        assert calcular_racha_objetivo(int(user["id"])) == 1

    r = web_client.get("/app/m/salud")
    assert r.status_code == 200
    assert b"progress-bar is-met" in r.content or b"is-met" in r.content
