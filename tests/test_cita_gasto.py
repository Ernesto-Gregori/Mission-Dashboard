"""El costo de una cita completada se registra una vez, como gasto en Finanzas."""
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


def _onboard(client, mods):
    client.post(
        "/setup",
        data={"username": "cita_user", "password": "password1", "password2": "password1"},
    )
    client.post("/app/coach/activar", data={"modulos": mods})


def _crear_cita(client, estado: str) -> int:
    from app.database import autenticar_usuario
    from app.db.matrimonio import obtener_citas
    from app.tenant import as_user

    datos = {
        "titulo": "Cena aniversario",
        "fecha": _hoy().isoformat(),
        "tipo_cita": "Cena_Romantica",
        "presupuesto": "45",
        "ambito": "Matrimonio",
    }
    client.post("/app/m/matrimonio/cita", data=datos)
    user = autenticar_usuario("cita_user", "password1")
    with as_user(user):
        cid = int(obtener_citas()[-1]["id"])
    client.post(f"/app/m/matrimonio/cita/{cid}/actualizar", data={**datos, "estado": estado})
    return cid


def test_cita_completada_se_registra_como_gasto_una_vez(web_client):
    _onboard(web_client, ["matrimonio", "finanzas"])
    cid = _crear_cita(web_client, "Planeando")
    body = web_client.get("/app/m/matrimonio?tab=citas").content.decode()
    assert "Registrar como gasto" not in body
    r = web_client.post(f"/app/m/matrimonio/cita/{cid}/gasto", data={"monto": "45"}, follow_redirects=True)
    assert "Solo las citas completadas" in r.content.decode()

    cid = _crear_cita(web_client, "Completada")
    body = web_client.get("/app/m/matrimonio?tab=citas").content.decode()
    assert f'id="cita-costo-{cid}"' in body
    assert 'value="45.00"' in body

    r = web_client.post(f"/app/m/matrimonio/cita/{cid}/gasto", data={"monto": "52.5"}, follow_redirects=True)
    body = r.content.decode()
    assert "Gasto de $52.50 registrado" in body
    assert "Costo registrado en Finanzas" in body
    assert f'id="cita-costo-{cid}"' not in body

    fin = web_client.get(f"/app/m/finanzas?mes={_hoy().month}&anio={_hoy().year}").content.decode()
    assert "Cita: Cena aniversario" in fin
    assert "Cita con Esposa" in fin
    assert "$52.50" in fin

    r = web_client.post(f"/app/m/matrimonio/cita/{cid}/gasto", data={"monto": "10"}, follow_redirects=True)
    assert "ya tiene su gasto" in r.content.decode()

    from app.database import autenticar_usuario
    from app.db.core import ejecutar

    uid = int(autenticar_usuario("cita_user", "password1")["id"])
    gid = ejecutar(
        "SELECT gasto_id FROM matrimonio_citas WHERE id = ? AND user_id = ?", [cid, uid], fetchall=True
    )[0]["gasto_id"]
    web_client.post(f"/app/m/finanzas/gasto/{gid}/eliminar")
    body = web_client.get("/app/m/matrimonio?tab=citas").content.decode()
    assert f'id="cita-costo-{cid}"' in body


def test_sin_modulo_finanzas_no_ofrece_gasto(web_client):
    _onboard(web_client, ["matrimonio"])
    _crear_cita(web_client, "Completada")
    body = web_client.get("/app/m/matrimonio?tab=citas").content.decode()
    assert "Registrar como gasto" not in body
