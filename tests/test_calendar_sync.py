"""Sync Calendar — conflictos, persistencia y Foco del Día."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.tenant import as_user, clear_current_user


@pytest.fixture()
def db_ready(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "calendar_sync.db"
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

    from app.billing import ensure_billing_schema
    from app.calendar_sync import ensure_calendar_sync_schema
    from app.database import autenticar_usuario, crear_usuario
    from app.db.schema import init_database
    from app.multiuser import migrate_multiuser
    from app.tenant import set_current_user

    init_database()
    migrate_multiuser()
    ensure_billing_schema()
    ensure_calendar_sync_schema()

    ok, _ = crear_usuario("cal_user", "password1", rol="usuario", plan="premium")
    assert ok
    user = autenticar_usuario("cal_user", "password1")
    assert user
    set_current_user(user)
    yield user
    clear_current_user()


def test_newer_side_newest_wins():
    from app.calendar_sync import newer_side

    assert newer_side("2026-09-17T10:00:00+00:00", "2026-09-17T09:00:00Z") == "local"
    assert newer_side("2026-09-17T09:00:00Z", "2026-09-17T10:00:00+00:00") == "google"
    assert newer_side("2026-09-17T10:00:00Z", "2026-09-17T10:00:00+00:00") == "equal"
    assert newer_side("2026-09-17T10:00:00", None) == "local"
    assert newer_side(None, "2026-09-17T10:00:00Z") == "google"


def test_pull_inserts_and_cancelled_deletes(db_ready):
    from app.calendar_sync import pull_range
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    dia = _hoy()
    gid = "g-keep"
    cancelled = "g-gone"

    def list_events(inicio, fin):
        return [
            {
                "google_id": gid,
                "fecha": dia.isoformat(),
                "hora_inicio": "09:00",
                "hora_fin": "10:00",
                "titulo": "Standup",
                "descripcion": "",
                "tipo": "Personal",
                "color": "#5484ed",
                "updated": "2026-09-17T12:00:00Z",
                "status": "confirmed",
            },
            {
                "google_id": cancelled,
                "fecha": dia.isoformat(),
                "hora_inicio": "11:00",
                "hora_fin": "12:00",
                "titulo": "Viejo",
                "descripcion": "",
                "updated": "2026-09-17T12:05:00Z",
                "status": "cancelled",
            },
        ]

    uid = int(db_ready["id"])
    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, google_id, fuente,
             actualizado_en, google_updated)
        VALUES (?, ?, '11:00', '12:00', 'Viejo', ?, 'google_calendar',
                '2026-09-16T10:00:00Z', '2026-09-16T10:00:00Z')
        """,
        [uid, dia.isoformat(), cancelled],
    )
    stats = pull_range(dia, dia, user_id=uid, force=True, list_events=list_events)
    assert stats["pulled"] == 1
    assert stats["deleted"] == 1
    rows = (
        ejecutar(
            "SELECT titulo, google_id FROM eventos_calendario WHERE user_id = ?",
            [uid],
            fetchall=True,
        )
        or []
    )
    titles = {r["titulo"] for r in rows}
    assert "Standup" in titles
    assert "Viejo" not in titles


def test_pull_google_newer_overwrites_local(db_ready):
    from app.calendar_sync import pull_range
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    dia = _hoy()
    uid = int(db_ready["id"])
    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, google_id, fuente,
             actualizado_en, google_updated)
        VALUES (?, ?, '09:00', '10:00', 'Local viejo', 'g-1', 'local',
                '2026-09-17T08:00:00Z', '2026-09-17T08:00:00Z')
        """,
        [uid, dia.isoformat()],
    )

    def list_events(inicio, fin):
        return [
            {
                "google_id": "g-1",
                "fecha": dia.isoformat(),
                "hora_inicio": "15:00",
                "hora_fin": "16:00",
                "titulo": "Google gana",
                "updated": "2026-09-17T18:00:00Z",
                "status": "confirmed",
                "color": "#5484ed",
            }
        ]

    stats = pull_range(dia, dia, user_id=uid, force=True, list_events=list_events)
    assert stats["updated"] == 1
    row = ejecutar(
        "SELECT titulo, hora_inicio FROM eventos_calendario WHERE google_id = 'g-1'",
        fetchall=True,
    )[0]
    assert row["titulo"] == "Google gana"
    assert str(row["hora_inicio"]).startswith("15:00")


def test_pull_local_newer_pushes(db_ready):
    from app.calendar_sync import pull_range
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    dia = _hoy()
    uid = int(db_ready["id"])
    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, google_id, fuente,
             actualizado_en, google_updated)
        VALUES (?, ?, '09:00', '10:00', 'Local nuevo', 'g-2', 'local',
                '2026-09-17T20:00:00Z', '2026-09-17T08:00:00Z')
        """,
        [uid, dia.isoformat()],
    )
    pushed = []

    def list_events(inicio, fin):
        return [
            {
                "google_id": "g-2",
                "fecha": dia.isoformat(),
                "hora_inicio": "09:00",
                "hora_fin": "10:00",
                "titulo": "Google viejo",
                "updated": "2026-09-17T08:00:00Z",
                "status": "confirmed",
            }
        ]

    def push_event(local):
        pushed.append(local["titulo"])

    stats = pull_range(
        dia, dia, user_id=uid, force=True, list_events=list_events, push_event=push_event
    )
    assert stats["pushed"] == 1
    assert pushed == ["Local nuevo"]


def test_items_foco_mezcla_habito_y_evento(db_ready):
    from app.calendar_sync import items_foco
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    uid = int(db_ready["id"])
    dia = str(_hoy())
    with as_user(db_ready):
        ejecutar(
            """
            INSERT INTO eventos_calendario
                (user_id, fecha, hora_inicio, hora_fin, titulo, fuente, google_id)
            VALUES (?, ?, '08:00', '09:00', 'BloqueFoco', 'local', NULL)
            """,
            [uid, dia],
        )
        ejecutar(
            """
            INSERT OR IGNORE INTO habitos_config
                (user_id, clave, label, emoji, hora, activo, orden)
            VALUES (?, 'oracion_foco', 'OracionFoco', '🙏', '05:45', 1, 1)
            """,
            [uid],
        )
        ejecutar(
            """
            INSERT INTO registros_salud (user_id, fecha, hizo_ejercicio)
            VALUES (?, ?, 1)
            """,
            [uid, dia],
        )
        items = items_foco(dia, user_id=uid)
    kinds = {i["kind"] for i in items}
    titles = [i["titulo"] for i in items]
    assert "evento" in kinds
    assert "habito" in kinds
    assert "entrenamiento" in kinds
    assert "BloqueFoco" in titles
    assert any("OracionFoco" in t for t in titles)
    assert any("Entrenamiento" in t for t in titles)
    clear_current_user()


def test_pull_list_error_queda_visible(db_ready, monkeypatch):
    from app.calendar_sync import leer_last_error, pull_range
    from app.google_calendar import estado_google_calendar
    from app.timezone_config import hoy as _hoy

    uid = int(db_ready["id"])
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: True)
    monkeypatch.setattr(
        "app.google_fit.get_ultimo_error_auth",
        lambda: "",
    )

    def list_events(inicio, fin):
        raise RuntimeError("calendar 403 forbidden")

    dia = _hoy()
    stats = pull_range(dia, dia, user_id=uid, force=True, list_events=list_events)
    assert stats["reason"] == "list_error"
    assert "403" in leer_last_error(uid)
    estado = estado_google_calendar(uid)
    assert estado["disponible"] is True
    assert "403" in estado["error"]


def test_pull_unavailable_muestra_error_de_auth(db_ready, monkeypatch):
    from app.calendar_sync import pull_range
    from app.google_calendar import estado_google_calendar
    from app.timezone_config import hoy as _hoy

    uid = int(db_ready["id"])
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: False)
    monkeypatch.setattr(
        "app.google_fit.get_ultimo_error_auth",
        lambda: "Google revocó el refresh_token (app en modo Testing expira ~7 días).",
    )
    dia = _hoy()
    stats = pull_range(dia, dia, user_id=uid, force=True)
    assert stats["reason"] == "unavailable"
    estado = estado_google_calendar(uid)
    assert estado["disponible"] is False
    assert "Testing" in estado["error"]
    assert "calendar_unavailable" not in estado["error"]
