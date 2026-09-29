"""Hoy muestra el día: una acción, un aviso, sin repetir el menú."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "hoy_pagina.db"
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
        data={"username": "hoy_ui", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas"]},
        follow_redirects=False,
    )


def test_hoy_es_el_dia_y_no_repite_el_menu(web_client):
    _onboard(web_client)
    r = web_client.get("/app")
    assert r.status_code == 200
    body = r.content
    assert b"hub-card" not in body
    assert "Tus áreas".encode() not in body
    assert "áreas activas".encode() not in body
    assert b">Anotar</button>" in body
    assert b"Guardar ritual" not in body
    assert b"Agenda de hoy" in body
    assert b'id="ritual-gratitud"' in body
    assert b"Dinero" in body


def test_hoy_muestra_un_solo_aviso(web_client):
    _onboard(web_client)
    malo = web_client.post(
        "/app/completar",
        data={"kind": "no", "ref": "x"},
        follow_redirects=False,
    )
    assert malo.status_code == 303
    r = web_client.get("/app?onboarded=1")
    assert r.status_code == 200
    assert "Eso no se marca desde Hoy." in r.text
    assert "Tu sistema quedó configurado con el Coach." not in r.text
    assert r.text.count('class="flash-') == 1


def test_el_coach_en_hoy_cabe_en_una_linea(web_client, monkeypatch):
    monkeypatch.setattr("app.coach_insights._llamar_llm_briefing", lambda signals: None)
    _onboard(web_client)
    r = web_client.post("/app/coach/briefing", follow_redirects=False)
    assert r.status_code in (303, 307)
    pagina = web_client.get("/app")
    assert b"Del Coach" in pagina.content
    assert b"<h2>Del Coach</h2>" not in pagina.content
    assert "Ver briefing completo" not in pagina.text
    assert pagina.text.count("<h2>Del Coach</h2>") == 0
