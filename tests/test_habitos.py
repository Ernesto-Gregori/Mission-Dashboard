"""Editor de hábitos en Cuenta › Mi sistema."""
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
    db_path = td / "ritual_test.db"
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


def _onboard(client: TestClient, username: str = "ritual_user") -> None:
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


def _hoy_body(client) -> str:
    return client.get("/app").content.decode()


def test_crear_editar_archivar_reactivar(web_client):
    _onboard(web_client)
    r = web_client.post(
        "/app/coach/habitos",
        data={"label": "Oración matutina", "emoji": "🙏", "hora": "05:45"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert "Oración matutina» agregado" in body
    assert 'id="hab-label-oracion_matutina"' in body
    assert 'value="05:45"' in body
    assert 'id="hab-oracion_matutina"' in _hoy_body(web_client)

    r = web_client.post("/app/coach/habitos", data={"label": "oración matutina"}, follow_redirects=True)
    assert "Ya tienes un hábito con ese nombre" in r.content.decode()

    r = web_client.post("/app/coach/habitos", data={"label": "Correr", "hora": "25:00"}, follow_redirects=True)
    assert "HH:MM" in r.content.decode()

    r = web_client.post(
        "/app/coach/habitos/oracion_matutina/editar",
        data={"label": "Oración y lectura", "emoji": "📖", "hora": ""},
        follow_redirects=True,
    )
    assert "Hábito actualizado" in r.content.decode()
    assert "📖 Oración y lectura" in _hoy_body(web_client)

    web_client.post("/app/ritual", data={"habito": ["oracion_matutina"]})
    from app.database import autenticar_usuario
    from app.db.core import ejecutar

    uid = int(autenticar_usuario("ritual_user", "password1")["id"])

    r = web_client.post("/app/coach/habitos/oracion_matutina/archivar", follow_redirects=True)
    body = r.content.decode()
    assert "historial se conserva" in body
    assert "Archivados (1)" in body
    assert 'id="hab-oracion_matutina"' not in _hoy_body(web_client)
    rows = ejecutar(
        "SELECT completado FROM habitos_diarios_v2 WHERE user_id = ? AND habito_clave = ?",
        [uid, "oracion_matutina"],
        fetchall=True,
    )
    assert rows and int(rows[0]["completado"]) == 1

    web_client.post("/app/coach/habitos/oracion_matutina/reactivar")
    assert 'id="hab-oracion_matutina"' in _hoy_body(web_client)


def test_claves_unicas_y_aisladas_por_usuario():
    from app.ritual import _clave_desde

    assert _clave_desde("Oración matutina!") == "oracion_matutina"
    assert _clave_desde("¡¡!!") == "habito"


def test_no_edita_habitos_de_otro_usuario(web_client):
    _onboard(web_client)
    web_client.post("/app/coach/habitos", data={"label": "Privado"})
    from app.ritual import actualizar_habito, listar_habitos_config

    ok, msg = actualizar_habito("privado", "Hackeado", user_id=999)
    assert not ok and "no encontrado" in msg
    from app.database import autenticar_usuario

    uid = int(autenticar_usuario("ritual_user", "password1")["id"])
    assert [h["label"] for h in listar_habitos_config(uid)] == ["Privado"]
