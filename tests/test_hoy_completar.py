"""Marcar un ítem de la agenda de Hoy sin abrir otra página."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "hoy_completar.db"
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


def _onboard(client: TestClient, username: str = "hoy_user") -> None:
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


def _crear(client: TestClient, label: str) -> str:
    client.post(
        "/app/configuracion/habitos",
        data={"label": label, "emoji": "⭐", "hora": "07:00"},
        follow_redirects=False,
    )
    from app.database import autenticar_usuario
    from app.ritual import listar_habitos

    uid = int(autenticar_usuario("hoy_user", "password1")["id"])
    clave = next(h["clave"] for h in listar_habitos(uid) if h["label"] == label)
    return clave


def _hecho(clave: str, uid: int) -> int:
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    rows = ejecutar(
        """
        SELECT completado FROM habitos_diarios_v2
        WHERE user_id = ? AND habito_clave = ? AND fecha = ?
        """,
        [uid, clave, str(_hoy())],
        fetchall=True,
    )
    return int(rows[0]["completado"]) if rows else 0


def _formulario(html: str, clave: str) -> bool:
    return (
        'action="/app/completar"' in html
        and 'name="kind" value="habito"' in html
        and f'name="ref" value="{clave}"' in html
        and ">Hecho<" in html
    )


def test_marcar_habito_desde_hoy_conserva_el_otro(web_client):
    _onboard(web_client)
    pendiente = _crear(web_client, "Leer hoy")
    ya_hecho = _crear(web_client, "Orar hoy")
    from app.database import autenticar_usuario

    uid = int(autenticar_usuario("hoy_user", "password1")["id"])
    web_client.post("/app/ritual", data={"habito": [ya_hecho]}, follow_redirects=False)

    pagina = web_client.get("/app")
    assert pagina.status_code == 200
    assert _formulario(pagina.text, pendiente)
    assert f'name="ref" value="{ya_hecho}"' not in pagina.text
    assert f'id="hab-{ya_hecho}"' in pagina.text
    assert "checked" in pagina.text

    r = web_client.post(
        "/app/completar",
        data={"kind": "habito", "ref": pendiente},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    despues = web_client.get("/app")
    assert despues.status_code == 200
    assert "Listo." in despues.text
    assert f'name="ref" value="{pendiente}"' not in despues.text
    assert ">Hecho<" not in despues.text
    assert f'id="hab-{pendiente}"' in despues.text and "checked" in despues.text.split(f'id="hab-{pendiente}"', 1)[1][:80]
    assert f'id="hab-{ya_hecho}"' in despues.text
    assert _hecho(pendiente, uid) == 1
    assert _hecho(ya_hecho, uid) == 1


def test_evento_o_ref_desconocido_no_marca(web_client):
    _onboard(web_client)
    clave = _crear(web_client, "Caminar hoy")
    from app.database import autenticar_usuario

    uid = int(autenticar_usuario("hoy_user", "password1")["id"])
    for kind, ref in (("evento", "1"), ("habito", "no_existe")):
        r = web_client.post(
            "/app/completar",
            data={"kind": kind, "ref": ref},
            follow_redirects=False,
        )
        assert r.status_code == 303
        cuerpo = web_client.get("/app")
        assert cuerpo.status_code == 200
        assert _hecho(clave, uid) == 0
        assert _formulario(cuerpo.text, clave)


def test_otro_usuario_no_cambia_el_habito(web_client):
    _onboard(web_client)
    clave = _crear(web_client, "Privado hoy")
    from app.calendar_sync import completar_item
    from app.database import autenticar_usuario

    uid = int(autenticar_usuario("hoy_user", "password1")["id"])
    ok, _msg = completar_item("habito", clave, 999)
    assert ok is False
    assert _hecho(clave, uid) == 0


def test_enfoque_se_marca_y_el_evento_no(web_client):
    _onboard(web_client)
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "deep_work"]},
        follow_redirects=False,
    )
    from app.database import autenticar_usuario
    from app.db.core import ejecutar
    from app.db.deep_work import crear_bloque
    from app.tenant import set_current_user
    from app.timezone_config import hoy as _hoy

    user = autenticar_usuario("hoy_user", "password1")
    set_current_user(user)
    bid = crear_bloque(
        "EstudioHoy", "09:00", "11:00", [_hoy().weekday() + 1], "Estudio", "#58a6ff"
    )
    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, fuente)
        VALUES (?, ?, '08:00', '09:00', 'CitaLocal', 'local')
        """,
        [int(user["id"]), str(_hoy())],
    )
    pagina = web_client.get("/app")
    assert pagina.status_code == 200
    assert 'name="kind" value="enfoque"' in pagina.text
    assert f'name="ref" value="{bid}"' in pagina.text
    assert "CitaLocal" in pagina.text
    assert 'name="kind" value="evento"' not in pagina.text

    r = web_client.post(
        "/app/completar",
        data={"kind": "enfoque", "ref": str(bid)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    despues = web_client.get("/app")
    assert f'name="ref" value="{bid}"' not in despues.text
    assert "EstudioHoy" in despues.text
    assert "✓" in despues.text
    from app.db.deep_work import bloques_para_fecha

    set_current_user(user)
    estado = next(b["estado"] for b in bloques_para_fecha(str(_hoy()), int(user["id"])) if int(b["id"]) == int(bid))
    assert estado == "Completado"
