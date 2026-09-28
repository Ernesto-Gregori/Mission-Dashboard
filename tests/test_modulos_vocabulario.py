"""Un solo nombre por área y módulos que se pueden apagar sin perder datos."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user
from app.timezone_config import hoy as _hoy


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "vocabulario_test.db"
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


def _onboard(client: TestClient, username: str, mods: list[str]) -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post("/app/coach/activar", data={"modulos": mods}, follow_redirects=False)


def _sidebar(html: str) -> str:
    m = re.search(r'<aside class="sidebar"[^>]*>(.*?)</aside>', html, re.S)
    assert m, "sidebar missing"
    return m.group(1)


def _h1(html: str) -> str:
    m = re.search(r"<h1>(.*?)</h1>", html, re.S)
    assert m, "h1 missing"
    return m.group(1).strip()


def _etiqueta_menu(sidebar: str, hub_id: str) -> str:
    m = re.search(rf'data-hub="{hub_id}"[^>]*>(.*?)</a>', sidebar, re.S)
    assert m, f"hub {hub_id} missing from sidebar"
    return m.group(1).strip()


TODAS = ["teologia", "matrimonio", "sandbox", "biblioteca", "deep_work", "finanzas", "salud", "agenda"]


def test_el_menu_y_el_titulo_dicen_lo_mismo(web_client):
    """Un área tiene un solo nombre: el del menú es el del encabezado de su página."""
    from web.nav import _HUB_HREF, _HUB_SPECS
    from app.templates import MODULE_TEMPLATES

    _onboard(web_client, "coherente", TODAS)
    sidebar = _sidebar(web_client.get("/app").text)
    vistos = 0
    for hub in _HUB_SPECS:
        mods = [m for m in hub.get("modules") or () if m in MODULE_TEMPLATES]
        if len(mods) != 1:
            continue
        pagina = web_client.get(_HUB_HREF[hub["id"]])
        assert pagina.status_code == 200
        nombre = MODULE_TEMPLATES[mods[0]]["nombre"]
        assert _h1(pagina.text) == nombre
        assert _etiqueta_menu(sidebar, hub["id"]) == nombre
        vistos += 1
    assert vistos >= 6


def test_ningun_nombre_de_la_cuenta_original_sobrevive(web_client):
    _onboard(web_client, "nuevo", TODAS)
    viejos = (
        "Teología / Devocional",
        "Matrimonio / Pareja",
        "Salud & Energía",
        "Deep Work",
        "Sandbox",
        ">Fe</a>",
        ">Pareja</a>",
        ">Biblioteca</a>",
    )
    for ruta in ("/app", "/app/m/teologia", "/app/m/matrimonio", "/app/configuracion"):
        cuerpo = web_client.get(ruta).text
        for viejo in viejos:
            assert viejo not in cuerpo, f"{viejo} sigue en {ruta}"


def test_una_cuenta_con_alias_heredados_vuelve_al_nombre_comun(web_client):
    from app.db.core import ejecutar
    from app.onboarding import MIGRACION_VOCABULARIO, migrar_vocabulario_unico, nombre_visible

    ejecutar("DELETE FROM _migrations WHERE id = ?", [MIGRACION_VOCABULARIO])
    ejecutar(
        """
        INSERT INTO usuarios (username, password_hash, salt, rol, onboarding_completo)
        VALUES ('legacy', 'x', 'y', 'admin', 1)
        """
    )
    legacy = ejecutar(
        "SELECT id FROM usuarios WHERE username = 'legacy'", fetchall=True
    )[0]["id"]
    for clave, alias in (("teologia", "Teología / Devocional"), ("deep_work", "Deep Work")):
        ejecutar(
            """
            INSERT INTO user_modulos (user_id, modulo, activo, config_json, alias)
            VALUES (?, ?, 1, '{}', ?)
            """,
            [legacy, clave, alias],
        )
    migrar_vocabulario_unico()

    assert nombre_visible("teologia") == "Espiritualidad"
    assert nombre_visible("deep_work") == "Enfoque"
    quedan = ejecutar(
        "SELECT COUNT(*) AS n FROM user_modulos WHERE alias IS NOT NULL",
        fetchall=True,
    )[0]["n"]
    assert int(quedan) == 0


def test_apagar_modulo_oculta_y_no_borra(web_client):
    _onboard(web_client, "foco_user", ["agenda"])
    from app.db.core import ejecutar

    uid = ejecutar(
        "SELECT id FROM usuarios WHERE username = 'foco_user'", fetchall=True
    )[0]["id"]
    ejecutar(
        """
        INSERT INTO matrimonio_citas (user_id, fecha, titulo)
        VALUES (?, ?, 'Cena secreta fase1')
        """,
        [uid, str(_hoy())],
    )
    assert b"Cena secreta fase1" not in web_client.get("/app").content

    ejecutar(
        "UPDATE user_modulos SET activo = 1 WHERE user_id = ? AND modulo = 'matrimonio'",
        [uid],
    )
    assert b"Cena secreta fase1" in web_client.get("/app").content

    ejecutar(
        "UPDATE user_modulos SET activo = 0 WHERE user_id = ? AND modulo = 'matrimonio'",
        [uid],
    )
    assert b"Cena secreta fase1" not in web_client.get("/app").content
    queda = ejecutar(
        "SELECT COUNT(*) AS n FROM matrimonio_citas WHERE user_id = ?",
        [uid],
        fetchall=True,
    )[0]["n"]
    assert int(queda) == 1


def test_ritual_y_alma_se_apagan_sin_perder_el_resto(web_client):
    _onboard(web_client, "shell_user", ["finanzas"])
    from app.db.core import ejecutar

    uid = ejecutar(
        "SELECT id FROM usuarios WHERE username = 'shell_user'", fetchall=True
    )[0]["id"]
    assert b'id="ritual-gratitud"' in web_client.get("/app").content
    assert b'href="/app/asistente"' in web_client.get("/app").content

    for clave in ("ritual", "alma", "rueda"):
        ejecutar(
            """
            INSERT INTO user_modulos (user_id, modulo, activo, config_json)
            VALUES (?, ?, 0, '{}')
            """,
            [uid, clave],
        )
    hoy = web_client.get("/app").content
    assert b'id="ritual-gratitud"' not in hoy
    assert b"Dinero" in hoy
    side = web_client.get("/app/usuarios").content
    assert b'href="/app/asistente"' not in side
    revision = web_client.get("/app/revision").content
    assert b"rueda-svg" not in revision
    assert b"Devocionales" not in revision
