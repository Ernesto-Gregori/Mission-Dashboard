"""Vista familiar — comparativa admin y aislamiento por miembro."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import as_user, clear_current_user
from app.timezone_config import hoy as _hoy


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "familia_test.db"

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


def _onboard_admin(client: TestClient, username: str = "fam_admin") -> None:
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


def test_familia_requiere_login(web_client):
    r = web_client.get("/app/familia", follow_redirects=False)
    assert r.status_code in (303, 307)


def test_familia_admin_compara_miembros(web_client):
    _onboard_admin(web_client)
    r = web_client.post(
        "/app/usuarios/crear",
        data={
            "username": "esposa_fam",
            "password": "password1",
            "password2": "password1",
            "rol": "usuario",
            "plan": "free",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200

    from app.database import autenticar_usuario, agregar_gasto_sobre, guardar_ingreso
    from app.db.core import ejecutar

    admin = autenticar_usuario("fam_admin", "password1")
    esposa = autenticar_usuario("esposa_fam", "password1")
    hoy = _hoy()

    with as_user(admin):
        guardar_ingreso(hoy.month, hoy.year, 3000, "admin")
        agregar_gasto_sobre(
            hoy.isoformat(), "Supervivencia", "Comida", "GastoAdminFam", 120, False
        )
    with as_user(esposa):
        guardar_ingreso(hoy.month, hoy.year, 800, "esposa")
        agregar_gasto_sobre(
            hoy.isoformat(), "Ministerio_Extras", "Personal", "GastoEsposaFam", 40, False
        )
        ejecutar(
            """
            INSERT OR IGNORE INTO habitos_config
                (user_id, clave, label, emoji, hora, activo, orden)
            VALUES (?, 'oracion_fam', 'OracionFam', '🙏', '06:00', 1, 1)
            """,
            [int(esposa["id"])],
        )
        ejecutar(
            """
            INSERT OR IGNORE INTO habitos_diarios_v2
                (user_id, fecha, habito_clave, completado)
            VALUES (?, ?, 'oracion_fam', 1)
            """,
            [int(esposa["id"]), str(hoy)],
        )

    r = web_client.get("/app/familia")
    assert r.status_code == 200
    body = r.content.decode()
    assert "esposa_fam" in body
    assert "fam_admin" in body
    assert "GastoAdminFam" in body or "120" in body
    assert 'for="fam-miembro"' in body

    r = web_client.get(f"/app/familia?miembro={int(esposa['id'])}")
    assert r.status_code == 200
    body = r.content.decode()
    assert "GastoEsposaFam" in body or "esposa_fam" in body
    assert "OracionFam" in body or "hábito" in body.lower() or "habito" in body.lower()


def test_familia_no_admin_no_ve_otros(web_client):
    _onboard_admin(web_client)
    web_client.post(
        "/app/usuarios/crear",
        data={
            "username": "hijo_fam",
            "password": "password1",
            "password2": "password1",
            "rol": "usuario",
            "plan": "free",
        },
        follow_redirects=True,
    )
    from app.database import autenticar_usuario

    admin = autenticar_usuario("fam_admin", "password1")
    web_client.post("/logout", follow_redirects=False)
    r = web_client.post(
        "/login",
        data={"username": "hijo_fam", "password": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303, 307)
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda"]},
        follow_redirects=False,
    )
    r = web_client.get("/app/familia", follow_redirects=False)
    assert r.status_code == 403
    assert b"Solo administradores" in r.content
    r = web_client.get(f"/app/familia?miembro={int(admin['id'])}", follow_redirects=False)
    assert r.status_code == 403
    assert b"GastoAdminFam" not in r.content
