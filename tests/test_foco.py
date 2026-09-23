"""Foco del Día — Calendar + hábitos locales."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "foco_test.db"
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


def _onboard(client: TestClient, username: str = "foco_user") -> None:
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


def test_foco_requiere_login(web_client):
    r = web_client.get("/app/foco", follow_redirects=False)
    assert r.status_code in (303, 307)


def test_foco_vive_en_hoy_sin_duplicar_habitos(web_client):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    user = autenticar_usuario("foco_user", "password1")
    dia = str(_hoy())
    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, fuente)
        VALUES (?, ?, '08:00', '09:00', 'FocoBloqueLocal', 'local')
        """,
        [int(user["id"]), dia],
    )
    ejecutar(
        """
        INSERT OR IGNORE INTO habitos_config
            (user_id, clave, label, emoji, hora, activo, orden)
        VALUES (?, 'oracion_foco_p', 'OracionFocoPagina', '🙏', '05:45', 1, 1)
        """,
        [int(user["id"])],
    )
    r = web_client.get("/app/foco", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"

    r = web_client.get("/app")
    assert r.status_code == 200
    body = r.content
    assert b"Agenda de hoy" in body
    assert b"FocoBloqueLocal" in body
    # El hábito aparece una sola vez: en la checklist, no en la agenda.
    assert body.count(b"OracionFocoPagina") == 1
    assert b'id="hab-oracion_foco_p"' in body

    r = web_client.get("/app/foco?fecha=2020-01-01", follow_redirects=False)
    assert r.headers["location"].startswith("/app/planificador?vista=dia&d=-")
