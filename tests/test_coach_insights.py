"""Tests — briefing cruzado del Coach (señales + heurísticas + cupo)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def db_ready(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "coach_insights.db"
    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

    import app.db.core as core

    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setattr(core, "usar_turso", lambda: False)

    from app.db.schema import init_database
    from app.multiuser import migrate_multiuser
    from app.billing import ensure_billing_schema
    from app.coach_insights import ensure_coach_insights_schema

    init_database()
    migrate_multiuser()
    ensure_billing_schema()
    ensure_coach_insights_schema()

    from app.database import crear_usuario, autenticar_usuario
    from app.tenant import set_current_user

    ok, _ = crear_usuario("coach_user", "password1", rol="usuario", plan="free")
    assert ok
    user = autenticar_usuario("coach_user", "password1")
    assert user
    set_current_user(user)
    return user


def test_heuristicas_cruzan_extras_y_deep_work(db_ready, monkeypatch):
    from app.coach_insights import _insights_heuristicos

    signals = {
        "period_days": 21,
        "modulos": {
            "finanzas": {"extras_pct": 40.0, "gastos_total": 100, "extras_total": 40},
            "deep_work": {"sesiones": 10, "completadas": 3, "pct_completado": 30.0},
            "matrimonio": {"dias_sin_actividad": 3, "registros_habito": 2, "citas": 1},
            "salud": {"registros": 10, "sueno_promedio": 7.5, "dias_ejercicio": 3},
            "habitos": {"dias_con_registro": 10, "pct_dias_completos": 80},
        },
    }
    insights = _insights_heuristicos(signals)
    assert insights
    assert any("Deep Work" in i["titulo"] or "extras" in i["titulo"].lower() for i in insights)
    assert any("finanzas" in i["modulos"] and "deep_work" in i["modulos"] for i in insights)


def test_generar_briefing_respeta_cupo_free(db_ready, monkeypatch):
    from app.coach_insights import (
        generar_briefing,
        resumen_cuota_briefing,
    )

    monkeypatch.setattr(
        "app.coach_insights._llamar_llm_briefing",
        lambda signals: None,
    )

    uid = int(db_ready["id"])
    ok, msg, briefing = generar_briefing(uid, plan="free")
    assert ok, msg
    assert briefing and briefing["insights"]
    assert briefing["source"] == "heuristic"

    cuota = resumen_cuota_briefing(uid, "free")
    assert cuota["usados"] == 1
    assert cuota["limite"] == 1
    assert cuota["ok"] is False

    ok2, msg2, _ = generar_briefing(uid, plan="free")
    assert ok2 is False
    assert "Cupo" in msg2 or "agotado" in msg2.lower()


def test_agregar_senales_finanzas(db_ready):
    from datetime import date, timedelta

    from app.db.core import ejecutar
    from app.coach_insights import agregar_senales
    from app.tenant import uid

    user_id = int(uid())
    hoy = date.today()
    for i, monto in enumerate((20.0, 30.0, 10.0)):
        f = (hoy - timedelta(days=i)).isoformat()
        ejecutar(
            """
            INSERT INTO gastos_sobres
                (user_id, fecha, sobre, subcategoria, descripcion, monto, es_fijo)
            VALUES (?, ?, 'Ministerio_Extras', 'ocio', 'test', ?, 0)
            """,
            [user_id, f, monto],
        )
    signals = agregar_senales(user_id, dias=14)
    fin = signals["modulos"]["finanzas"]
    assert fin["extras_total"] == 60.0
    assert fin["extras_n"] == 3
