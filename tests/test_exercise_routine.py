"""Armador de rutinas: parseo IA, persistencia, equipamiento y UI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.exercises import (
    guardar_routine,
    listar_equipment,
    obtener_routine,
)
from app.exercise_routine import RoutineError, parse_routine_payload
from app.tenant import as_user


@pytest.fixture()
def web_client(monkeypatch):
    import tempfile

    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

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


def _setup_salud(client: TestClient, username: str = "rt_user") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "prueba",
            "objetivos": "ejercicio",
            "tiempo": "20",
            "notas": "",
            "areas": ["salud"],
        },
        follow_redirects=False,
    )
    client.post(
        "/app/coach/activar",
        data={"modulos": ["salud"]},
        follow_redirects=False,
    )


SAMPLE_PLAN = {
    "nombre": "Fuerza 3 días",
    "objetivo": "fuerza",
    "notas_coach": "Empuje, jalón y piernas. Cuando completes el rango alto, sube carga.",
    "dias": [
        {
            "nombre": "Día 1 · Empuje",
            "enfoque": "pecho y hombros",
            "duracion_min": 40,
            "calentamiento": ["Círculos de hombro 2 min"],
            "bloques": [
                {
                    "nombre": "Swing con pesa rusa",
                    "series": 3,
                    "reps": "10-12",
                    "descanso_seg": 90,
                    "notas": "Bisagra de cadera",
                },
                {
                    "nombre": "Flexiones",
                    "series": 3,
                    "reps": "8-12",
                    "descanso_seg": 60,
                    "notas": "Cuerpo en línea",
                },
            ],
            "cierre": ["Estiramiento de pecho"],
        },
        {
            "nombre": "Día 2 · Jalón",
            "enfoque": "espalda",
            "duracion_min": 40,
            "calentamiento": ["Gato-camello"],
            "bloques": [
                {
                    "nombre": "Remo con banda",
                    "series": 4,
                    "reps": "10",
                    "descanso_seg": 75,
                    "notas": "",
                }
            ],
            "cierre": [],
        },
        {
            "nombre": "Día 3 · Piernas",
            "enfoque": "cuádriceps y glúteos",
            "duracion_min": 40,
            "calentamiento": ["Sentadilla al aire 8 reps"],
            "bloques": [
                {
                    "nombre": "Sentadilla goblet",
                    "series": 3,
                    "reps": "8-10",
                    "descanso_seg": 90,
                    "notas": "Rodillas afuera",
                }
            ],
            "cierre": ["Estiramiento de cadera"],
        },
    ],
}


def test_schema_creates_routine_table(web_client):
    import app.db.core as core

    tables = {
        r["name"]
        for r in (core.ejecutar("SELECT name FROM sqlite_master WHERE type='table'", fetchall=True) or [])
    }
    assert "exercise_routines" in tables


def test_la_biblioteca_de_videos_ya_no_se_crea(web_client):
    """La subida de video se retiró: el esquema nuevo no vuelve a crear la tabla."""
    import app.db.core as core

    tables = {
        r["name"]
        for r in (core.ejecutar("SELECT name FROM sqlite_master WHERE type='table'", fetchall=True) or [])
    }
    assert "exercises" not in tables
    assert "user_equipment" in tables


def test_parse_routine_reads_the_coach_json():
    raw = json.dumps(SAMPLE_PLAN, ensure_ascii=False)
    parsed = parse_routine_payload(f"```json\n{raw}\n```", expected_days=3, minutos=40)
    assert parsed["nombre"] == "Fuerza 3 días"
    assert len(parsed["dias"]) == 3
    bloque = parsed["dias"][0]["bloques"][0]
    assert bloque["nombre"] == "Swing con pesa rusa"
    assert bloque["series"] == 3
    assert bloque["reps"] == "10-12"
    assert "exercise_id" not in bloque


def test_parse_routine_rejects_empty_days():
    with pytest.raises(RoutineError):
        parse_routine_payload(
            json.dumps({"nombre": "x", "dias": []}),
            expected_days=3,
            minutos=40,
        )


def test_parse_routine_rejects_non_json():
    with pytest.raises(RoutineError):
        parse_routine_payload("el coach se fue de tema", expected_days=3, minutos=40)


def test_rutina_tab_shows_builder_form(web_client):
    _setup_salud(web_client, "rt_tab")
    r = web_client.get("/app/m/salud?tab=rutina")
    assert r.status_code == 200
    assert "Armar mi rutina".encode() in r.content
    assert b'name="dias_semana"' in r.content
    assert b'name="minutos_sesion"' in r.content
    assert b'name="equipo"' in r.content
    assert b"/app/m/salud/rutina/generar" in r.content
    assert b'href="/app/m/salud?tab=rutina"' in web_client.get("/app/m/salud").content


def test_salud_ya_no_ofrece_subir_video(web_client):
    """La pestaña de biblioteca y su formulario de subida desaparecieron."""
    _setup_salud(web_client, "rt_novideo")
    cuerpo = web_client.get("/app/m/salud").content
    assert b"tab=ejercicios" not in cuerpo
    assert "Agregar ejercicio desde video".encode() not in cuerpo
    assert b'type="file"' not in cuerpo

    # Un tab desconocido cae en Hoy, no en una pantalla vacía.
    r = web_client.get("/app/m/salud?tab=ejercicios")
    assert r.status_code == 200
    assert "Registro del día".encode() in r.content
    assert web_client.post(
        "/app/m/salud/ejercicios/subir", follow_redirects=False
    ).status_code == 404


def test_el_equipamiento_se_administra_en_la_pestana_rutina(web_client):
    _setup_salud(web_client, "rt_equip")
    r = web_client.post(
        "/app/m/salud/equipamiento",
        data={"equipment_name": "pesa rusa"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "tab=rutina" in r.headers["location"]

    r = web_client.get("/app/m/salud?tab=rutina")
    assert "Equipamiento disponible".encode() in r.content
    assert b"pesa rusa" in r.content

    eq_id = int(listar_equipment(1)[0]["id"])
    r = web_client.post(
        f"/app/m/salud/equipamiento/{eq_id}/borrar",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "tab=rutina" in r.headers["location"]
    assert listar_equipment(1) == []


def test_generate_and_improve_routine(web_client, monkeypatch):
    _setup_salud(web_client, "rt_ok")

    monkeypatch.setattr(
        "web.routers.rutina.generate_routine",
        lambda **kwargs: parse_routine_payload(
            json.dumps(SAMPLE_PLAN, ensure_ascii=False),
            expected_days=int(kwargs["dias"]),
            minutos=int(kwargs["minutos"]),
        ),
    )

    r = web_client.post(
        "/app/m/salud/rutina/generar",
        data={
            "dias_semana": "3",
            "minutos_sesion": "40",
            "equipo": ["pesa rusa", "peso corporal"],
            "notas": "quiero fuerza",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Fuerza 3 días".encode() in r.content
    assert "Día 1".encode() in r.content
    assert b"10-12" in r.content
    assert "Swing con pesa rusa".encode() in r.content
    assert "Flexiones".encode() in r.content
    assert "Mejorar rutina".encode() in r.content

    row = obtener_routine(1)
    assert row is not None
    assert row["dias_semana"] == 3
    assert row["minutos_sesion"] == 40
    assert "pesa rusa" in row["equipamiento"]

    plan2 = json.loads(json.dumps(SAMPLE_PLAN))
    plan2["nombre"] = "Fuerza 3 días v2"
    plan2["dias"][0]["bloques"][0]["series"] = 4
    monkeypatch.setattr(
        "web.routers.rutina.generate_routine",
        lambda **kwargs: parse_routine_payload(
            json.dumps(plan2, ensure_ascii=False),
            expected_days=3,
            minutos=40,
        ),
    )
    r = web_client.post(
        "/app/m/salud/rutina/mejorar",
        data={"notas": "más series en el swing"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Fuerza 3 días v2".encode() in r.content
    assert obtener_routine(1)["plan"]["dias"][0]["bloques"][0]["series"] == 4


def test_routine_isolated_by_user(web_client):
    _setup_salud(web_client, "rt_iso")
    guardar_routine(
        1,
        3,
        40,
        ["peso corporal"],
        SAMPLE_PLAN,
        notas_coach="solo user 1",
    )
    from app.database import crear_usuario

    crear_usuario("otro_rt", "password1", rol="usuario")
    with as_user({"id": 2, "username": "otro_rt"}):
        assert obtener_routine(2) is None
        guardar_routine(2, 2, 30, ["banda"], {"nombre": "Otra", "dias": []}, notas_coach="u2")

    assert obtener_routine(1)["plan"]["nombre"] == "Fuerza 3 días"
    assert obtener_routine(2)["plan"]["nombre"] == "Otra"
    r = web_client.get("/app/m/salud?tab=rutina")
    assert "Fuerza 3 días".encode() in r.content
    assert ">Otra<".encode() not in r.content


def test_delete_routine(web_client):
    _setup_salud(web_client, "rt_del")
    guardar_routine(1, 3, 40, ["peso corporal"], SAMPLE_PLAN)
    r = web_client.post("/app/m/salud/rutina/eliminar", follow_redirects=True)
    assert r.status_code == 200
    assert obtener_routine(1) is None
    assert "Armar mi rutina".encode() in r.content
