"""Nombres neutros, alias de cuentas ya existentes y módulos que se pueden apagar."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user
from app.timezone_config import hoy as _hoy


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "alias_test.db"
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


def test_usuario_nuevo_ve_nombres_neutros(web_client):
    _onboard(web_client, "nuevo", ["teologia", "matrimonio", "sandbox", "biblioteca", "deep_work"])
    teo = web_client.get("/app/m/teologia")
    assert teo.status_code == 200
    assert "Espiritualidad" in teo.text
    assert "Teología / Devocional" not in teo.text

    side = web_client.get("/app").content.decode()
    assert "Espiritualidad" in side
    assert "Relaciones" in side
    assert ">Fe</a>" not in side
    assert ">Pareja</a>" not in side

    assert b"Relaciones" in web_client.get("/app/m/matrimonio").content
    assert b"Ideas" in web_client.get("/app/m/sandbox").content
    assert b"Lectura" in web_client.get("/app/m/biblioteca").content
    assert b"Enfoque" in web_client.get("/app/m/deep_work").content


def test_cuenta_existente_conserva_sus_nombres(web_client):
    from app.db.core import ejecutar
    from app.onboarding import MIGRACION_ALIAS, etiqueta_nav, migrar_nombres_cuenta, nombre_visible

    ejecutar("DELETE FROM _migrations WHERE id = ?", [MIGRACION_ALIAS])
    ejecutar(
        """
        INSERT INTO usuarios (username, password_hash, salt, rol, onboarding_completo)
        VALUES ('legacy', 'x', 'y', 'admin', 1)
        """
    )
    legacy = ejecutar(
        "SELECT id FROM usuarios WHERE username = 'legacy'", fetchall=True
    )[0]["id"]
    for clave in ("teologia", "matrimonio", "deep_work", "sandbox", "biblioteca"):
        ejecutar(
            """
            INSERT INTO user_modulos (user_id, modulo, activo, config_json)
            VALUES (?, ?, 1, '{}')
            """,
            [legacy, clave],
        )
    migrar_nombres_cuenta()

    assert nombre_visible("teologia", legacy) == "Teología / Devocional"
    assert nombre_visible("matrimonio", legacy) == "Matrimonio / Pareja"
    assert nombre_visible("deep_work", legacy) == "Deep Work"
    assert nombre_visible("sandbox", legacy) == "Sandbox"
    assert nombre_visible("biblioteca", legacy) == "Biblioteca"
    assert etiqueta_nav("teologia", legacy) == "Fe"
    assert etiqueta_nav("matrimonio", legacy) == "Pareja"

    ejecutar(
        """
        INSERT INTO usuarios (username, password_hash, salt, rol, onboarding_completo)
        VALUES ('despues', 'x', 'y', 'usuario', 1)
        """
    )
    despues = ejecutar(
        "SELECT id FROM usuarios WHERE username = 'despues'", fetchall=True
    )[0]["id"]
    ejecutar(
        """
        INSERT INTO user_modulos (user_id, modulo, activo, config_json)
        VALUES (?, 'teologia', 1, '{}')
        """,
        [despues],
    )
    migrar_nombres_cuenta()
    assert nombre_visible("teologia", despues) == "Espiritualidad"
    assert nombre_visible("teologia", legacy) == "Teología / Devocional"


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
