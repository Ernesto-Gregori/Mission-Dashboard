"""Presupuesto 50/30/20 — ratios, gasto real y vencimientos."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "presupuesto_test.db"

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


def _onboard(client: TestClient, username: str = "budget_user") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas", "agenda"]},
        follow_redirects=False,
    )


def test_presupuesto_requiere_login(web_client):
    r = web_client.get("/app/presupuesto", follow_redirects=False)
    assert r.status_code in (303, 307)
    loc = r.headers.get("location", "")
    assert "/login" in loc or "/setup" in loc


def test_presupuesto_pagina_503020_y_grafico(web_client):
    _onboard(web_client)
    r = web_client.get("/app/presupuesto")
    assert r.status_code == 200
    body = r.content.decode()
    assert "50/30/20" in body or "50 / 30 / 20" in body
    assert "Necesidades" in body
    assert "Deseos" in body
    assert "Ahorro" in body
    assert 'for="pct-necesidades"' in body
    assert 'for="pct-deseos"' in body
    assert 'for="pct-ahorro"' in body
    assert "spend-chart" in body
    assert "Vencimientos" in body
    assert b'href="/app/presupuesto"' in r.content


def test_ingreso_en_presupuesto_aparece_en_finanzas(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/presupuesto/periodo",
        data={"mes": "9", "anio": "2026", "monto": "2000", "notas": "sueldo test"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"2000" in r.content

    r = web_client.get("/app/m/finanzas?mes=9&anio=2026")
    assert r.status_code == 200
    assert b"2000" in r.content


def test_gasto_finanzas_actualiza_503020(web_client):
    _onboard(web_client)
    web_client.post(
        "/app/presupuesto/periodo",
        data={"mes": "9", "anio": "2026", "monto": "1000"},
        follow_redirects=True,
    )
    web_client.post(
        "/app/m/finanzas/gasto",
        data={
            "fecha": "2026-09-10",
            "sobre": "Supervivencia",
            "subcategoria": "Comida",
            "descripcion": "Super503020",
            "monto": "200",
        },
        follow_redirects=True,
    )
    web_client.post(
        "/app/m/finanzas/gasto",
        data={
            "fecha": "2026-09-11",
            "sobre": "Ministerio_Extras",
            "subcategoria": "Personal",
            "descripcion": "CafeDeseo",
            "monto": "50",
        },
        follow_redirects=True,
    )
    r = web_client.get("/app/presupuesto?mes=9&anio=2026")
    assert r.status_code == 200
    body = r.content.decode()
    assert "Super503020" in body or "Comida" in body
    assert "$200" in body or "200" in body
    assert "necesidades" in body.lower()
    # Meta 50% de 1000 = 500; gastado 200 → visible
    assert "500" in body


def test_ratios_personalizados_y_rechazo_si_no_suman_100(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/presupuesto/ratios",
        data={"pct_necesidades": "40", "pct_deseos": "40", "pct_ahorro": "20"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert 'value="40"' in body
    assert 'id="pct-necesidades"' in body

    r = web_client.post(
        "/app/presupuesto/ratios",
        data={"pct_necesidades": "50", "pct_deseos": "50", "pct_ahorro": "50"},
    )
    assert r.status_code == 400
    assert b"100" in r.content


def test_calendario_vencimientos_colorea_por_tipo(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/presupuesto/recurrente",
        data={
            "titulo": "NetflixTest",
            "tipo": "suscripcion",
            "monto": "12.99",
            "dia": "15",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"NetflixTest" in r.content
    assert b"chip-suscripcion" in r.content or b"due-suscripcion" in r.content

    web_client.post(
        "/app/presupuesto/recurrente",
        data={
            "titulo": "LuzFactura",
            "tipo": "factura",
            "monto": "40",
            "dia": "5",
        },
        follow_redirects=True,
    )
    web_client.post(
        "/app/presupuesto/recurrente",
        data={
            "titulo": "SueldoIngreso",
            "tipo": "ingreso",
            "monto": "1000",
            "dia": "1",
        },
        follow_redirects=True,
    )
    r = web_client.get("/app/presupuesto")
    body = r.content.decode()
    assert "LuzFactura" in body
    assert "SueldoIngreso" in body
    assert "chip-factura" in body or "due-factura" in body
    assert "chip-ingreso" in body or "due-ingreso" in body
    assert "chip-deuda" in body or "due-deuda" in body or "Deuda" in body
    assert "chip-ahorro" in body or "due-ahorro" in body or "Ahorro" in body
