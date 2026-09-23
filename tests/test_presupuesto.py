"""Reparto del ingreso en sobres (presets 3 sobres / 50/30/20 / personalizado) y vencimientos."""
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


def test_url_503020_redirige_a_finanzas(web_client):
    _onboard(web_client)
    r = web_client.get("/app/presupuesto?mes=9&anio=2026", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app/m/finanzas?mes=9&anio=2026"


def test_reparto_por_defecto_es_3_sobres(web_client):
    _onboard(web_client)
    web_client.post(
        "/app/m/finanzas/periodo",
        data={"mes": "9", "anio": "2026", "monto": "1000"},
    )
    web_client.post(
        "/app/m/finanzas/gasto",
        data={
            "fecha": "2026-09-10",
            "sobre": "Supervivencia",
            "subcategoria": "Comida",
            "descripcion": "SuperTest",
            "monto": "200",
        },
    )
    r = web_client.get("/app/m/finanzas?mes=9&anio=2026")
    assert r.status_code == 200
    body = r.content.decode()
    assert "3 sobres" in body
    assert "50/30/20" in body
    assert "SUPERVIVENCIA</strong> · 65%" in body
    assert "$200 / $650" in body
    assert "Disponible: $450" in body
    assert 'id="pct-Supervivencia"' in body
    assert "spend-chart" in body


def test_preset_503020_reusa_los_mismos_gastos(web_client):
    _onboard(web_client)
    web_client.post(
        "/app/m/finanzas/periodo",
        data={"mes": "9", "anio": "2026", "monto": "1000"},
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
    )
    r = web_client.post(
        "/app/m/finanzas/reparto",
        data={"preset": "503020"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert "SUPERVIVENCIA</strong> · 50%" in body
    assert "MINISTERIO Y EXTRAS</strong> · 30%" in body
    assert "$50 / $300" in body
    assert 'aria-pressed="true"' in body


def test_reparto_personalizado_y_rechazo_si_no_suma_100(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/m/finanzas/reparto",
        data={
            "pct_Supervivencia": "40",
            "pct_Futuro_Hogar": "40",
            "pct_Ministerio_Extras": "20",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert "Reparto personalizado" in body
    assert 'value="40"' in body

    r = web_client.post(
        "/app/m/finanzas/reparto",
        data={
            "pct_Supervivencia": "50",
            "pct_Futuro_Hogar": "50",
            "pct_Ministerio_Extras": "50",
        },
    )
    assert r.status_code == 400
    assert b"100" in r.content


def test_ratios_unit(monkeypatch):
    from app.presupuesto import PRESETS, preset_de, validar_ratios

    assert preset_de(PRESETS["sobres"]["ratios"]) == "sobres"
    assert preset_de({"Supervivencia": 40, "Futuro_Hogar": 40, "Ministerio_Extras": 20}) is None
    ok, _, _ = validar_ratios({"Supervivencia": 70, "Futuro_Hogar": 20, "Ministerio_Extras": 10})
    assert ok
    ok, msg, _ = validar_ratios({"Supervivencia": "x"})
    assert not ok and msg


def test_calendario_vencimientos_colorea_por_tipo(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/m/finanzas/vencimientos",
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
    assert b"chip-suscripcion" in r.content

    for titulo, tipo, dia in (("LuzFactura", "factura", "5"), ("SueldoIngreso", "ingreso", "1")):
        web_client.post(
            "/app/m/finanzas/vencimientos",
            data={"titulo": titulo, "tipo": tipo, "monto": "40", "dia": dia},
        )
    body = web_client.get("/app/m/finanzas/vencimientos").content.decode()
    assert "LuzFactura" in body
    assert "SueldoIngreso" in body
    assert "due-factura" in body
    assert "due-ingreso" in body
    assert "Deuda" in body

    r = web_client.post(
        "/app/m/finanzas/vencimientos",
        data={"titulo": "Mal", "tipo": "otro", "monto": "1", "dia": "1"},
    )
    assert r.status_code == 400


def test_ingreso_sugerido_desde_vencimientos(web_client):
    _onboard(web_client)
    for titulo, monto in (("Sueldo", "1200"), ("Freelance", "300")):
        web_client.post(
            "/app/m/finanzas/vencimientos",
            data={"titulo": titulo, "tipo": "ingreso", "monto": monto, "dia": "1"},
        )
    web_client.post(
        "/app/m/finanzas/vencimientos",
        data={"titulo": "Luz", "tipo": "factura", "monto": "40", "dia": "5"},
    )
    body = web_client.get("/app/m/finanzas?mes=10&anio=2026").content.decode()
    assert 'value="1500.00"' in body
    assert "Sugerido desde tus vencimientos de ingreso (Freelance, Sueldo)" in body
    # Solo se prellena: el mes sigue sin ingreso hasta que el usuario lo guarda.
    assert "Sin ingreso este mes" in body

    web_client.post("/app/m/finanzas/periodo", data={"mes": "10", "anio": "2026", "monto": "1400"})
    body = web_client.get("/app/m/finanzas?mes=10&anio=2026").content.decode()
    assert 'value="1400.00"' in body
    assert "Sugerido desde" not in body
