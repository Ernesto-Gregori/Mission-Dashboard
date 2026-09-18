"""Armador de rutinas: schema, parseo IA, persistencia y UI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.exercises import (
    apply_analysis,
    crear_exercise,
    guardar_routine,
    listar_exercises,
    obtener_routine,
)
from app.exercise_routine import RoutineError, parse_routine_payload
from app.tenant import as_user
from tests.test_exercise_library import SAMPLE_ANALYSIS, _setup_salud


@pytest.fixture()
def web_client(monkeypatch):
    import tempfile

    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setenv("EXERCISE_STORAGE_DIR", str(td / "ex_uploads"))
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
                    "exercise_id": 1,
                    "nombre": "Swing con pesa rusa",
                    "series": 3,
                    "reps": "10-12",
                    "descanso_seg": 90,
                    "notas": "Bisagra de cadera",
                },
                {
                    "exercise_id": None,
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
                    "exercise_id": None,
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
                    "exercise_id": None,
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


def test_parse_routine_strips_foreign_exercise_ids():
    raw = json.dumps(SAMPLE_PLAN, ensure_ascii=False)
    parsed = parse_routine_payload(
        f"```json\n{raw}\n```",
        allowed_ids={1},
        expected_days=3,
        minutos=40,
    )
    assert parsed["nombre"] == "Fuerza 3 días"
    assert len(parsed["dias"]) == 3
    assert parsed["dias"][0]["bloques"][0]["exercise_id"] == 1
    assert parsed["dias"][0]["bloques"][0]["series"] == 3
    assert parsed["dias"][0]["bloques"][0]["reps"] == "10-12"

    parsed2 = parse_routine_payload(
        raw,
        allowed_ids=set(),
        expected_days=3,
        minutos=40,
    )
    assert parsed2["dias"][0]["bloques"][0]["exercise_id"] is None


def test_parse_routine_rejects_empty_days():
    with pytest.raises(RoutineError):
        parse_routine_payload(
            json.dumps({"nombre": "x", "dias": []}),
            allowed_ids=set(),
            expected_days=3,
            minutos=40,
        )


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


def test_generate_and_improve_routine(web_client, monkeypatch):
    _setup_salud(web_client, "rt_ok")
    with as_user({"id": 1, "username": "rt_ok"}):
        eid = crear_exercise(1, "data/uploads/exercises/1/swing.mp4", "otro")
        apply_analysis(eid, 1, SAMPLE_ANALYSIS)

    plan = json.loads(json.dumps(SAMPLE_PLAN))
    plan["dias"][0]["bloques"][0]["exercise_id"] = listar_exercises(1)[0]["id"]

    monkeypatch.setattr(
        "web.routers.ejercicios.generate_routine",
        lambda **kwargs: parse_routine_payload(
            json.dumps(plan, ensure_ascii=False),
            allowed_ids={int(listar_exercises(1)[0]["id"])},
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

    plan2 = json.loads(json.dumps(plan))
    plan2["nombre"] = "Fuerza 3 días v2"
    plan2["dias"][0]["bloques"][0]["series"] = 4
    monkeypatch.setattr(
        "web.routers.ejercicios.generate_routine",
        lambda **kwargs: parse_routine_payload(
            json.dumps(plan2, ensure_ascii=False),
            allowed_ids={int(listar_exercises(1)[0]["id"])},
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
