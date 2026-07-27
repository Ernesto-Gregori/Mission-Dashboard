"""
Tests de humo — auth, aislamiento multi-usuario, rate limit, plantillas.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_db(monkeypatch):
    """BD SQLite temporal sin Turso."""
    td = Path(tempfile.mkdtemp())
    db_path = td / "test.db"

    import app.database as dbmod
    import app.db.core as core

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(dbmod.usar_turso, "cache_clear"):
        dbmod.usar_turso.cache_clear()
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    # secrets may still set turso — force False
    monkeypatch.setattr(dbmod, "usar_turso", lambda: False)
    monkeypatch.setattr(core, "usar_turso", lambda: False)

    dbmod.init_database()
    from app.multiuser import migrate_multiuser

    migrate_multiuser()
    yield dbmod


def test_crear_y_autenticar(isolated_db):
    db = isolated_db
    ok, msg = db.crear_usuario("alice_test", "password1", rol="usuario")
    assert ok, msg
    user = db.autenticar_usuario("alice_test", "password1")
    assert user is not None
    assert user["username"] == "alice_test"
    assert db.autenticar_usuario("alice_test", "wrongpass") is None


def test_username_y_password_policy(isolated_db):
    db = isolated_db
    ok, _ = db.crear_usuario("ab", "password1")
    assert not ok
    ok, _ = db.crear_usuario("good_user", "short")
    assert not ok
    ok, _ = db.crear_usuario("Bad User!", "password1")
    assert not ok


def test_aislamiento_user_id(isolated_db):
    db = isolated_db
    from app.multiuser import provision_user_defaults
    from app.onboarding import aplicar_modulos, modulos_activos

    ok, _ = db.crear_usuario("alice_iso", "password1", rol="usuario")
    ok, _ = db.crear_usuario("bob_isolxx", "password1", rol="usuario")
    assert ok
    a = int(db.ejecutar("SELECT id FROM usuarios WHERE username='alice_iso'", fetchall=True)[0]["id"])
    b = int(db.ejecutar("SELECT id FROM usuarios WHERE username='bob_isolxx'", fetchall=True)[0]["id"])

    provision_user_defaults(a, seed_modules=False)
    provision_user_defaults(b, seed_modules=False)
    aplicar_modulos(["agenda", "finanzas"], user_id=a)
    aplicar_modulos(["salud"], user_id=b)

    assert "finanzas" in modulos_activos(a)
    assert "salud" not in modulos_activos(a)
    assert "salud" in modulos_activos(b)
    assert "finanzas" not in modulos_activos(b)

    db.ejecutar(
        "INSERT INTO gastos_sobres (user_id, fecha, sobre, subcategoria, descripcion, monto) VALUES (?,?,?,?,?,?)",
        [a, "2026-07-01", "Supervivencia", "Comida", "alice", 10.0],
    )
    rows_a = db.ejecutar(
        "SELECT * FROM gastos_sobres WHERE user_id=?", [a], fetchall=True
    ) or []
    rows_b = db.ejecutar(
        "SELECT * FROM gastos_sobres WHERE user_id=?", [b], fetchall=True
    ) or []
    assert len(rows_a) == 1
    assert len(rows_b) == 0


def test_audit_log_on_crear_usuario(isolated_db):
    from app.audit import listar_auditoria

    db = isolated_db
    ok, _ = db.crear_usuario("audit_user", "password1", rol="usuario")
    assert ok
    rows = listar_auditoria(limite=20, entidad="usuarios")
    assert any(r.get("accion") == "crear_usuario" for r in rows)


def test_rate_limit_login():
    from app.rate_limit import (
        limpiar_todo,
        registrar_fallo,
        registrar_exito,
        segundos_bloqueo,
        MAX_FAILS,
    )

    limpiar_todo()
    for _ in range(MAX_FAILS - 1):
        assert registrar_fallo("brute") == 0
    lock = registrar_fallo("brute")
    assert lock > 0
    assert segundos_bloqueo("brute") > 0
    registrar_exito("brute")
    assert segundos_bloqueo("brute") == 0


def test_coach_fallback_sin_api(isolated_db, monkeypatch):
    from app.onboarding import _sugerencia_fallback, sugerir_con_ia

    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)
    sug = sugerir_con_ia({
        "nombre": "Test",
        "areas": ["espiritual", "finanzas"],
        "objetivos": "disciplina",
        "situacion": "estudiante",
        "tiempo": "15-20 min",
        "notas": "",
    })
    assert sug["fuente"] == "fallback"
    assert "agenda" in sug["modulos"] or "teologia" in sug["modulos"]
    fb = _sugerencia_fallback({"areas": ["salud"]})
    assert "salud" in fb["modulos"]


def test_backup_export(isolated_db, tmp_path, monkeypatch):
    from app import backup as bak

    monkeypatch.setattr(bak, "BACKUP_DIR", tmp_path / "backups")
    path = bak.exportar_backup_json(tag="test")
    assert path is not None
    assert path.exists()
    data = path.read_text(encoding="utf-8")
    assert "usuarios" in data


def test_billing_planes_y_cuota(isolated_db, monkeypatch):
    from app import billing as bil
    from app.tenant import uid as _uid

    db = isolated_db
    bil.ensure_billing_schema()
    ok, _ = db.crear_usuario("free_user", "password1", rol="usuario", plan="free")
    assert ok
    uid = int(db.ejecutar(
        "SELECT id FROM usuarios WHERE username='free_user'", fetchall=True
    )[0]["id"])

    # Mock tenant + session plan
    monkeypatch.setattr("app.tenant.uid", lambda: uid)
    class _SS(dict):
        pass
    import streamlit as st
    st.session_state.user = {
        "id": uid, "username": "free_user", "rol": "usuario",
        "plan": "free", "coach_ia_usado": 0,
    }

    assert bil.plan_vigente() == "free"
    assert bil.modulos_max("free") == 3
    assert bil.puede_google("free") is False
    assert bil.puede_google("premium") is True
    assert bil.cuota_ia_ok(uid, "free") is True

    for _ in range(15):
        bil.registrar_llamada_ia(uid)
    assert bil.llamadas_ia_mes(uid) == 15
    assert bil.cuota_ia_ok(uid, "free") is False
    assert bil.cuota_ia_ok(uid, "premium") is True

    ok, _ = bil.set_plan(uid, "premium")
    assert ok
    row = db.ejecutar(
        "SELECT plan FROM usuarios WHERE id=?", [uid], fetchall=True
    )[0]
    assert row["plan"] == "premium"


def test_aplicar_modulos_respeta_cupo_free(isolated_db, monkeypatch):
    from app.onboarding import aplicar_modulos, listar_modulos_usuario
    import streamlit as st

    db = isolated_db
    ok, _ = db.crear_usuario("cupo_user", "password1", rol="usuario", plan="free")
    assert ok
    uid = int(db.ejecutar(
        "SELECT id FROM usuarios WHERE username='cupo_user'", fetchall=True
    )[0]["id"])
    monkeypatch.setattr("app.tenant.uid", lambda: uid)
    st.session_state.user = {
        "id": uid, "username": "cupo_user", "rol": "usuario", "plan": "free",
    }
    st.session_state.pop("_modulos_activos", None)

    aplicar_modulos(
        ["agenda", "finanzas", "salud", "teologia", "sandbox"],
        user_id=uid,
    )
    activos = {
        r["modulo"] for r in listar_modulos_usuario(uid) if int(r.get("activo") or 0) == 1
    }
    assert len(activos) == 3
    assert "agenda" in activos
