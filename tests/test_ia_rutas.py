"""Mapa de rutas: qué responde cada URL y qué enlaza a cada una.

Red de seguridad para la reorganización de la arquitectura de información.
Si una ola posterior mueve o fusiona pantallas, este archivo falla primero.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user

# URL -> código esperado con follow_redirects=False.
# 200 = pantalla propia · 303 = redirección (compatibilidad o gate).
RUTAS_PUBLICAS: dict[str, int] = {
    "/privacidad": 200,
    "/terminos": 200,
    "/health": 200,
}

RUTAS_CON_SESION: dict[str, int] = {
    "/": 303,
    "/login": 303,
    "/setup": 303,
    "/app": 200,
    "/app/planificador": 200,
    "/app/revision": 200,
    "/app/m/finanzas": 200,
    "/app/m/finanzas/vencimientos": 200,
    "/app/m/finanzas/precios": 200,
    "/app/m/salud": 200,
    "/app/m/teologia": 200,
    "/app/m/biblioteca": 200,
    "/app/m/matrimonio": 200,
    "/app/m/deep_work": 200,
    "/app/asistente": 200,
    "/app/coach": 200,
    "/app/configuracion": 200,
    "/app/billing": 200,
    "/app/usuarios": 200,
    "/app/familia": 200,
}

# Rutas que existen solo como endpoint de formulario o compatibilidad de URL:
# su GET redirige y ninguna pantalla debe enlazarlas.
RUTAS_SIN_PANTALLA: dict[str, str] = {
    "/app/foco": "/app",
    "/app/ritual": "/app",
    "/app/rueda": "/app/revision",
    "/app/m/agenda": "/app/",
    "/app/presupuesto": "/app/m/finanzas",
}

TODOS_LOS_MODULOS = [
    "agenda",
    "finanzas",
    "deep_work",
    "teologia",
    "biblioteca",
    "salud",
    "matrimonio",
]


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "ia_rutas.db"
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


def _onboard_completo(client: TestClient, username: str = "mapa") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": TODOS_LOS_MODULOS},
        follow_redirects=False,
    )


def _sidebar(html: bytes) -> str:
    m = re.search(r'<aside class="sidebar"[^>]*>(.*?)</aside>', html.decode(), re.S)
    assert m, "sidebar missing"
    return m.group(1)


def _enlaces_de_nav(sidebar: str) -> list[tuple[str, str]]:
    """[(href, etiqueta)] del menú principal."""
    nav = re.search(
        r'<nav[^>]*aria-label="Navegación principal"[^>]*>(.*?)</nav>', sidebar, re.S
    )
    assert nav, "primary nav missing"
    return [
        (href, re.sub(r"<[^>]+>", "", texto).strip())
        for href, texto in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', nav.group(1), re.S)
    ]


def test_rutas_publicas_responden_sin_sesion(web_client):
    for url, esperado in RUTAS_PUBLICAS.items():
        r = web_client.get(url, follow_redirects=False)
        assert r.status_code == esperado, f"{url} devolvió {r.status_code}"


def test_sin_sesion_la_app_manda_a_login(web_client):
    for url in ("/app", "/app/planificador", "/app/m/finanzas", "/app/configuracion"):
        r = web_client.get(url, follow_redirects=False)
        assert r.status_code == 303, f"{url} devolvió {r.status_code}"
        assert r.headers["location"] == "/login"


def test_sin_onboarding_todo_manda_al_coach(web_client):
    r = web_client.post(
        "/setup",
        data={"username": "pendiente", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    for url in ("/app", "/app/planificador", "/app/m/finanzas", "/app/configuracion"):
        r = web_client.get(url, follow_redirects=False)
        assert r.status_code == 303, f"{url} devolvió {r.status_code}"
        assert r.headers["location"] == "/app/coach"
    assert web_client.get("/app/coach").status_code == 200


def test_todas_las_pantallas_responden(web_client):
    _onboard_completo(web_client)
    for url, esperado in RUTAS_CON_SESION.items():
        r = web_client.get(url, follow_redirects=False)
        assert r.status_code == esperado, f"{url} devolvió {r.status_code}"


def test_rutas_sin_pantalla_redirigen_y_nadie_las_enlaza(web_client):
    _onboard_completo(web_client)
    for url, destino in RUTAS_SIN_PANTALLA.items():
        r = web_client.get(url, follow_redirects=False)
        assert r.status_code == 303, f"{url} devolvió {r.status_code}"
        assert r.headers["location"].startswith(destino), f"{url} → {r.headers['location']}"

    plantillas = Path(__file__).resolve().parent.parent / "web" / "templates"
    html = "\n".join(p.read_text(encoding="utf-8") for p in plantillas.rglob("*.html"))
    for url in RUTAS_SIN_PANTALLA:
        assert f'href="{url}"' not in html, f"{url} no debería tener enlaces"


def test_cada_pantalla_de_modulo_se_alcanza_desde_la_navegacion(web_client):
    """Ninguna área activa queda sin enlace en el sidebar o en las pestañas."""
    _onboard_completo(web_client)
    side = _sidebar(web_client.get("/app").content)
    hrefs = [href for href, _ in _enlaces_de_nav(side)]
    for clave in ("finanzas", "salud", "teologia", "biblioteca", "matrimonio"):
        assert any(h.startswith(f"/app/m/{clave}") for h in hrefs), f"{clave} sin enlace"
    # deep_work y revisión viven en las pestañas del hub Semana, no en el sidebar.
    semana = web_client.get("/app/planificador").content
    assert b'href="/app/m/deep_work' in semana
    assert b'href="/app/revision"' in semana


def test_la_navegacion_no_crece_sin_control(web_client):
    """El sidebar es una lista corta de trabajos, no un volcado de páginas."""
    _onboard_completo(web_client)
    side = _sidebar(web_client.get("/app").content)
    enlaces = _enlaces_de_nav(side)
    assert len(enlaces) <= 10, [e[1] for e in enlaces]
    assert "nav-group-label" in side
