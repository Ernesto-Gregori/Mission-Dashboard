"""Telegram v2 · B6: recordatorios de cualquier evento, sin duplicar, anticipación configurable."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _evento(titulo: str, fecha: str, hora: str, fuente: str = "local") -> int:
    from app.database import autenticar_usuario
    from app.db.agenda import guardar_evento
    from app.tenant import clear_current_user, set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    try:
        return int(
            guardar_evento(
                {
                    "fecha": fecha,
                    "hora_inicio": hora,
                    "hora_fin": "18:00",
                    "titulo": titulo,
                    "fuente": fuente,
                    "google_id": "g-1" if fuente == "google_calendar" else None,
                },
                sync_google=False,
            )
        )
    finally:
        clear_current_user()


@pytest.fixture()
def linked(web_client):  # noqa: F811
    _onboard(web_client)
    _link_admin("42")
    return web_client


def test_web_and_google_events_get_one_reminder(linked):
    from app.telegram import sync_event_reminders

    now = datetime(2030, 6, 1, 8, 0)
    _evento("Reunión web", "2030-06-01", "10:00")
    _evento("Cita Google", "2030-06-01", "15:00", fuente="google_calendar")
    _evento("Sin hora", "2030-06-01", "")
    assert sync_event_reminders(now=now) == 2
    assert sync_event_reminders(now=now) == 0
    rows = _rows("telegram_reminders")
    assert len(rows) == 2
    assert {r["titulo"] for r in rows} == {"Reunión web", "Cita Google"}
    assert {r["fire_at"] for r in rows} == {"2030-06-01T09:30:00", "2030-06-01T14:30:00"}


def test_moved_event_recalculates_fire_at(linked):
    from app.db.core import ejecutar
    from app.telegram import sync_event_reminders

    now = datetime(2030, 6, 1, 8, 0)
    eid = _evento("Dentista", "2030-06-01", "10:00")
    sync_event_reminders(now=now)
    ejecutar("UPDATE eventos_calendario SET hora_inicio = '12:00' WHERE id = ?", [eid])
    assert sync_event_reminders(now=now) == 1
    rows = _rows("telegram_reminders")
    assert len(rows) == 1 and rows[0]["fire_at"] == "2030-06-01T11:30:00"


def test_started_events_are_not_reminded(linked):
    from app.telegram import sync_event_reminders

    _evento("Ya pasó", "2030-06-01", "09:00")
    assert sync_event_reminders(now=datetime(2030, 6, 1, 9, 0)) == 0
    assert _rows("telegram_reminders") == []


def test_zero_lead_turns_reminders_off(linked):
    from app.database import autenticar_usuario
    from app.db.telegram_state import guardar_recordatorio_min
    from app.telegram import sync_event_reminders

    now = datetime(2030, 6, 1, 8, 0)
    _evento("Dentista", "2030-06-01", "10:00")
    sync_event_reminders(now=now)
    uid = int(autenticar_usuario("tg_admin", "password1")["id"])
    assert guardar_recordatorio_min(uid, 0) is True
    assert sync_event_reminders(now=now) == 0
    assert _rows("telegram_reminders") == []
    assert guardar_recordatorio_min(uid, 99) is False


def test_custom_lead_and_unlinked_or_free_skipped(linked, monkeypatch):
    from app.database import autenticar_usuario
    from app.db.telegram_state import guardar_recordatorio_min
    from app.telegram import sync_event_reminders

    uid = int(autenticar_usuario("tg_admin", "password1")["id"])
    guardar_recordatorio_min(uid, 10)
    _evento("Dentista", "2030-06-01", "10:00")
    now = datetime(2030, 6, 1, 8, 0)
    assert sync_event_reminders(now=now) == 1
    assert _rows("telegram_reminders")[0]["fire_at"] == "2030-06-01T09:50:00"

    monkeypatch.setattr("app.billing.puede_telegram", lambda plan=None: False)
    _evento("Otro", "2030-06-01", "11:00")
    assert sync_event_reminders(now=now) == 0
    assert len(_rows("telegram_reminders")) == 1


def test_deleted_event_drops_pending_reminder(linked):
    from app.db.core import ejecutar
    from app.telegram import sync_event_reminders

    now = datetime(2030, 6, 1, 8, 0)
    eid = _evento("Dentista", "2030-06-01", "10:00")
    sync_event_reminders(now=now)
    ejecutar("DELETE FROM eventos_calendario WHERE id = ?", [eid])
    assert sync_event_reminders(now=now) == 0
    assert _rows("telegram_reminders") == []


def test_usuarios_saves_lead(linked):
    r = linked.post(
        "/app/usuarios/telegram/recordatorios",
        data={"recordatorio_min": "15"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"15 min" in r.content
    assert b'selected' in r.content
    from app.database import autenticar_usuario
    from app.db.telegram_state import recordatorio_min

    uid = int(autenticar_usuario("tg_admin", "password1")["id"])
    assert recordatorio_min(uid) == 15
    bad = linked.post("/app/usuarios/telegram/recordatorios", data={"recordatorio_min": "7"})
    assert bad.status_code == 400
    assert recordatorio_min(uid) == 15


def test_message_uses_saved_time(linked):
    from app.telegram import schedule_reminder, send_due_reminders

    schedule_reminder(1, 1, "2030-01-10", "10:00", "Dentista", "42")
    sent = []
    assert send_due_reminders(now=datetime(2030, 1, 10, 9, 30), send_fn=lambda c, b: sent.append(b)) == 1
    assert sent == ["⏰ Recordatorio: 10:00 · Dentista."]
    assert send_due_reminders(now=datetime(2030, 1, 10, 9, 30), send_fn=lambda c, b: sent.append(b)) == 0
