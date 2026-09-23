"""Arquitectura de información: hubs, sidebar corta y páginas hermanas."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "nav_ia_test.db"
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


def _onboard(client: TestClient, username: str = "nav_user", mods=None) -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": mods or ["agenda", "finanzas", "matrimonio", "salud"]},
        follow_redirects=False,
    )


def _sidebar(html: bytes) -> str:
    text = html.decode()
    m = re.search(r'<aside class="sidebar">(.*?)</aside>', text, re.S)
    assert m, "sidebar missing"
    return m.group(1)


def _nav_hrefs(sidebar: str) -> list[str]:
    return re.findall(r'<nav[^>]*aria-label="Navegación principal"[^>]*>.*?</nav>', sidebar, re.S)


def _link_hrefs(sidebar: str) -> list[str]:
    nav = re.search(r'<nav[^>]*aria-label="Navegación principal"[^>]*>(.*?)</nav>', sidebar, re.S)
    assert nav, "primary nav missing"
    return re.findall(r'href="([^"]+)"', nav.group(1))


def test_sidebar_uses_hubs_not_page_dump(web_client):
    _onboard(web_client)
    r = web_client.get("/app")
    assert r.status_code == 200
    side = _sidebar(r.content)
    hrefs = _link_hrefs(side)

    assert "Hoy" in side
    assert "Alma" in side
    assert "Semana" in side
    assert "Dinero" in side
    assert "Cuenta" in side
    assert "nav-group-label" in side

    # Duplicados fuera del menú principal.
    assert "/app/ritual" not in hrefs
    assert "/app/rueda" not in hrefs
    assert "/app/foco" not in hrefs
    assert "/app/presupuesto" not in hrefs
    assert "/app/familia" not in hrefs
    assert "/app/billing" not in hrefs
    assert "/app/usuarios" not in hrefs
    assert "/app/coach" in hrefs
    assert "/app/m/agenda" not in hrefs
    assert "/app/m/finanzas" in hrefs or any(h.startswith("/app/m/finanzas") for h in hrefs)

    # Módulos inactivos no se listan uno a uno.
    assert "Biblioteca" not in side
    assert "Sandbox" not in side
    assert "Teología" not in side and "Teologia" not in side

    assert len(hrefs) <= 10


def test_inactive_module_hubs_hidden(web_client):
    _onboard(web_client, "slim_user", mods=["finanzas"])
    r = web_client.get("/app")
    side = _sidebar(r.content)
    assert "Cuerpo" not in side
    assert "Lectura" not in side
    assert "Ideas" not in side
    assert "Dinero" in side
    assert "Hoy" in side


def test_dashboard_joins_daily_surfaces(web_client):
    _onboard(web_client)
    r = web_client.get("/app")
    assert r.status_code == 200
    body = r.content
    assert b"id=\"ritual-gratitud\"" in body
    assert b"id=\"ritual-intencion\"" in body
    assert b"Foco" in body or b"Hoy" in body
    assert b"rueda-hoy" not in body
    assert b"hub-tabs" in body or b"data-hub=\"hoy\"" in body
    assert b"class=\"module-card" in body
    assert b"Dinero" in body
    assert b"Semana" in body


def test_alma_y_mi_sistema_separados(web_client):
    _onboard(web_client)
    r = web_client.get("/app/asistente")
    assert r.status_code == 200
    assert b"Alma" in r.content
    assert b'href="/app/coach"' in r.content
    assert b'href="/app/asistente"' in r.content
    assert b"Conversar" in r.content or b"Gu" in r.content

    r = web_client.get("/app/coach")
    assert r.status_code == 200
    assert b"Briefing cruzado" not in r.content
    assert b'href="/app/asistente"' in r.content


def test_dinero_tabs_mes_vencimientos_precios(web_client):
    _onboard(web_client)
    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    assert b'href="/app/m/finanzas/vencimientos' in r.content
    assert b'href="/app/m/finanzas/precios' in r.content
    assert b"Reparto del ingreso" in r.content
    assert b"/app/presupuesto" not in r.content


def test_semana_hub_links_planificador_enfoque_revision(web_client):
    _onboard(web_client, "week_user", mods=["agenda", "deep_work"])
    r = web_client.get("/app/planificador")
    assert r.status_code == 200
    assert b'href="/app/planificador"' in r.content
    assert b'href="/app/revision"' in r.content
    assert b'href="/app/m/deep_work' in r.content
    assert b'href="/app/m/agenda' not in r.content


def test_familia_vive_en_cuenta_admin(web_client):
    _onboard(web_client)
    r = web_client.get("/app/m/matrimonio")
    assert r.status_code == 200
    assert b'href="/app/familia"' not in r.content
    assert b'data-hub="pareja"' in r.content
    r = web_client.get("/app/familia")
    assert r.status_code == 200
    assert b'href="/app/coach"' in r.content
    assert b'href="/app/billing"' in r.content
    assert b'href="/app/familia"' in r.content


def test_cuenta_hub_covers_billing(web_client):
    _onboard(web_client)
    r = web_client.get("/app/usuarios")
    assert r.status_code == 200
    side = _sidebar(r.content)
    hrefs = _link_hrefs(side)
    assert "/app/coach" in hrefs
    assert "/app/billing" not in hrefs
    assert b'href="/app/billing"' in r.content
    assert b"Plan y cobros" in r.content
    assert b"tab=plan" not in r.content
