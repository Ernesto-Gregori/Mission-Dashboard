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

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    if hasattr(dbmod.usar_turso, "cache_clear"):
        dbmod.usar_turso.cache_clear()
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    # secrets may still set turso — force False
    monkeypatch.setattr(dbmod, "usar_turso", lambda: False)

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
