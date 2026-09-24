"""Telegram v2 · agenda: fechas relativas, /agenda, /mover y /cancelar."""
from __future__ import annotations

from datetime import datetime

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows() -> list:
    from app.db.core import ejecutar

    return ejecutar("SELECT * FROM eventos_calendario", fetchall=True) or []


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound(
        "42",
        text=text,
        update_id=uid,
        send_fn=lambda c, b: None,
        parse_fn=lambda t: {"intent": "unknown"},
    )


def _setup(client, monkeypatch):
    _onboard(client)
    _link_admin("42")
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: False)
    monkeypatch.setattr("app.timezone_config.ahora", lambda: datetime(2026, 9, 24, 9, 0))
    monkeypatch.setattr("app.timezone_config.hoy", lambda: datetime(2026, 9, 24).date())


def test_tarea_fecha_relativa_y_duracion(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    out = _say("/tarea pasado mañana 5pm llamar al banco 30 min", "a1")
    assert out.startswith("📅 Sáb 26 sep 17:00–17:30 · llamar al banco")
    row = _rows()[0]
    assert row["fecha"] == "2026-09-26" and row["hora_inicio"] == "17:00" and row["hora_fin"] == "17:30"


def test_en_dos_horas_y_el_dia(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    out = _say("en 2 horas llamar al banco", "a2")
    assert "11:00–12:00" in out and _rows()[0]["fecha"] == "2026-09-24"
    out = _say("/tarea el 15 pagar luz", "a3")
    assert "Jue 15 oct" in out
    assert _rows()[1]["fecha"] == "2026-10-15" and _rows()[1]["hora_inicio"] == "09:00"


def test_lunes(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    out = _say("/tarea lunes 9:30 dentista", "a4")
    assert out.startswith("📅 Lun 28 sep 09:30–10:30")


def test_agenda_deja_de_ser_briefing(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    _say("/tarea hoy 5pm banco", "a5")
    out = _say("/agenda", "a6")
    assert "Foco" not in out and "banco" in out and out.startswith("Agenda de hoy")
    assert "Agenda de mañana" in _say("/agenda mañana", "a7")
    semana = _say("agenda de la semana", "a8")
    assert semana.startswith("Agenda de la semana") and "banco" in semana


def test_mover_y_cancelar_piden_confirmacion(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    _say("/tarea hoy 5pm banco", "a9")
    _say("/agenda", "a10")
    assert "¿Muevo el 1 a las 18:00?" in _say("/mover 1 18:00", "a11")
    assert _rows()[0]["hora_inicio"] == "17:00"
    assert "Moví" in _say("sí", "a12")
    assert _rows()[0]["hora_inicio"] == "18:00"
    _say("/agenda", "a13")
    assert "¿Cancelo el 1?" in _say("/cancelar 1", "a14")
    assert "Cancelé" in _say("sí", "a15")
    assert _rows() == []


def test_agenda_apagada_no_escribe(web_client, monkeypatch):
    _setup(web_client, monkeypatch)
    web_client.post("/app/coach/activar", data={"modulos": ["finanzas"]})
    out = _say("/tarea mañana 5pm banco", "a16")
    assert "apagado" in out and _rows() == []
