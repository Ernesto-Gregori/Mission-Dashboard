"""Planificador semanal — Calendar + bloques locales."""
from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "planificador_test.db"

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


def _onboard(client: TestClient, username: str = "plan_user") -> None:
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


def test_planificador_pagina(web_client):
    _onboard(web_client)
    r = web_client.get("/app/planificador")
    assert r.status_code == 200
    assert b"Planificador" in r.content
    assert b"week-start" in r.content
    assert b"chip-google" in r.content
    assert b"chip-local" in r.content
    assert b'for="plan-title"' in r.content
    assert b"solo_local" in r.content
    assert b"data-planner-grid" in r.content
    assert b"/app/planificador/vista/dia" in r.content


def test_planificador_muestra_error_real_de_calendar(web_client, monkeypatch):
    _onboard(web_client)
    monkeypatch.setattr("web.routers.planificador.puede_google", lambda plan: True)
    monkeypatch.setattr(
        "web.routers.planificador.pull_range",
        lambda *a, **k: {"skipped": False, "pulled": 0, "updated": 0, "deleted": 0},
    )
    monkeypatch.setattr(
        "app.google_calendar.estado_google_calendar",
        lambda user_id=None: {
            "disponible": True,
            "error": "calendar 403 forbidden",
            "last_error": "calendar 403 forbidden",
        },
    )
    r = web_client.get("/app/planificador")
    assert r.status_code == 200
    assert b"calendar 403 forbidden" in r.content
    assert b'role="alert"' in r.content


def test_planificador_bloque_local_no_sync_google(web_client, monkeypatch):
    _onboard(web_client)
    created = []
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: True)
    monkeypatch.setattr(
        "app.google_calendar.crear_evento_google",
        lambda datos: created.append(datos) or "gid-should-not-run",
    )
    from app.timezone_config import hoy as _hoy

    r = web_client.post(
        "/app/planificador/bloque",
        data={
            "fecha": str(_hoy()),
            "titulo": "BloqueLocalTest",
            "tipo": "Personal",
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
            "solo_local": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"BloqueLocalTest" in r.content
    assert b"chip-local" in r.content
    assert created == []


def test_planificador_mezcla_google(web_client, monkeypatch):
    _onboard(web_client)
    from app.db.agenda import inicio_semana
    from app.timezone_config import hoy as _hoy

    lunes = inicio_semana(_hoy(), "lun")

    def fake_events(inicio, fin, **kwargs):
        return [
            {
                "google_id": "gcal-1",
                "fecha": lunes.isoformat(),
                "hora_inicio": "15:00",
                "hora_fin": "16:00",
                "titulo": "ReunionGoogleTest",
                "descripcion": "",
                "tipo": "Personal",
                "color": "#5484ed",
                "fuente": "google_calendar",
                "updated": "2026-09-17T12:00:00Z",
                "status": "confirmed",
            }
        ]

    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: True)
    monkeypatch.setattr("app.google_calendar.obtener_eventos_google", fake_events)

    r = web_client.get("/app/planificador")
    assert r.status_code == 200
    assert b"ReunionGoogleTest" in r.content
    assert b"chip-google" in r.content


def test_planificador_semana_domingo(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/planificador/inicio",
        data={"week_start": "dom"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    # El primer encabezado de d\u00eda debe ser domingo
    assert b"<strong>Dom</strong>" in r.content
    idx_dom = r.content.find(b"<strong>Dom</strong>")
    idx_lun = r.content.find(b"<strong>Lun</strong>")
    assert idx_dom != -1 and idx_lun != -1
    assert idx_dom < idx_lun


def test_planificador_bloque_default_sync_google(web_client, monkeypatch):
    _onboard(web_client)
    created = []
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: True)
    monkeypatch.setattr(
        "app.google_calendar.crear_evento_google",
        lambda datos: created.append(datos) or "gid-sync",
    )
    from app.timezone_config import hoy as _hoy

    r = web_client.post(
        "/app/planificador/bloque",
        data={
            "fecha": str(_hoy()),
            "titulo": "BloqueSyncTest",
            "tipo": "Personal",
            "hora_inicio": "11:00",
            "hora_fin": "12:00",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert created and created[0]["titulo"] == "BloqueSyncTest"
    assert b"BloqueSyncTest" in r.content


def test_planificador_vista_dia_y_mover(web_client):
    _onboard(web_client)
    from app.timezone_config import hoy as _hoy

    r = web_client.get("/app/planificador/vista/dia", follow_redirects=True)
    assert r.status_code == 200
    assert b"data-planner-grid" in r.content
    assert b"vista-dia" in r.content

    r = web_client.post(
        "/app/planificador/bloque",
        data={
            "fecha": str(_hoy()),
            "titulo": "MoverTest",
            "tipo": "Personal",
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
            "solo_local": "1",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    from app.db.core import ejecutar

    row = ejecutar(
        "SELECT id FROM eventos_calendario WHERE titulo = 'MoverTest'",
        fetchall=True,
    )[0]
    r = web_client.post(
        "/app/planificador/mover",
        data={
            "evento_id": str(row["id"]),
            "fecha": str(_hoy()),
            "hora_inicio": "14:00",
            "hora_fin": "15:00",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"14:00" in r.content
    assert b"MoverTest" in r.content


def test_bloques_deep_work_en_planificador_y_hoy(web_client):
    _onboard(web_client, "dw_plan_user")
    web_client.post("/app/coach/activar", data={"modulos": ["agenda", "deep_work"]})
    r = web_client.post(
        "/app/m/deep_work/bloque",
        data={
            "nombre": "BloqueEnfoqueTest",
            "hora_inicio": "07:00",
            "hora_fin": "08:30",
            "dias": ["1", "2", "3", "4", "5", "6", "7"],
            "tipo": "Deep Work",
            "color": "Azul",
        },
    )
    assert r.status_code in (200, 303)

    r = web_client.get("/app/planificador?vista=semana&w=0")
    assert r.status_code == 200
    body = r.content.decode()
    assert body.count("BloqueEnfoqueTest") == 7
    assert "origen-enfoque" in body
    # Los bloques se editan en Enfoque: no se arrastran ni borran desde el calendario.
    assert 'data-event-id="None"' not in body

    r = web_client.get("/app")
    assert "BloqueEnfoqueTest" in r.content.decode()
    assert "chip-dw" in r.content.decode()

    from app.database import autenticar_usuario
    from app.db.deep_work import bloques_en_rango
    from app.tenant import as_user
    from app.timezone_config import hoy as _hoy

    user = autenticar_usuario("dw_plan_user", "password1")
    with as_user(user):
        bloque_id = bloques_en_rango(_hoy(), _hoy())[0]["id"]
    web_client.post(
        "/app/m/deep_work/sesion",
        data={"fecha": _hoy().isoformat(), "bloque_id": str(bloque_id), "estado": "Completado"},
    )
    with as_user(user):
        semana = bloques_en_rango(_hoy() - timedelta(days=3), _hoy() + timedelta(days=3))
    assert len(semana) == 7
    assert [b["estado"] for b in semana if b["fecha"] == _hoy().isoformat()] == ["Completado"]
    assert "BloqueEnfoqueTest ✓" in web_client.get("/app").content.decode()
