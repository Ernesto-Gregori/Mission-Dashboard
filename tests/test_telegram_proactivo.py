"""Telegram v2 · briefing de la mañana: opt-in, hora, silencio e idempotencia."""
from __future__ import annotations

from datetime import datetime, timedelta

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _uid() -> int:
    from app.database import autenticar_usuario

    return int(autenticar_usuario("tg_admin", "password1")["id"])


def _setup(client):
    _onboard(client)
    _link_admin("42")


def test_apagado_por_defecto_no_envia(web_client):
    _setup(web_client)
    from app.telegram import send_morning_briefings

    assert send_morning_briefings(now=datetime(2030, 1, 10, 8, 0), send_fn=lambda c, b: None) == 0


def test_envia_una_vez_al_llegar_la_hora(web_client):
    _setup(web_client)
    from app.db.telegram_state import guardar_prefs_briefing
    from app.telegram import send_morning_briefings

    assert guardar_prefs_briefing(_uid(), activo=True, hora="07:00", extra=[]) is True
    assert guardar_prefs_briefing(_uid(), activo=True, hora="7am", extra=[]) is False
    sent = []
    assert send_morning_briefings(now=datetime(2030, 1, 10, 6, 59), send_fn=lambda c, b: sent.append(b)) == 0
    assert send_morning_briefings(now=datetime(2030, 1, 10, 7, 0), send_fn=lambda c, b: sent.append(b)) == 1
    assert sent and sent[0].startswith("Foco ")
    assert send_morning_briefings(now=datetime(2030, 1, 10, 7, 15), send_fn=lambda c, b: sent.append(b)) == 0
    assert len(sent) == 1


def test_silencio_pausa_y_cero_reanuda(web_client):
    _setup(web_client)
    from app.db.telegram_state import guardar_prefs_briefing, prefs_briefing
    from app.telegram import handle_inbound, send_morning_briefings
    from app.timezone_config import hoy

    guardar_prefs_briefing(_uid(), activo=True, hora="07:00", extra=["salud"])
    out = handle_inbound("42", text="/silencio 2", update_id="p1", send_fn=lambda c, b: None)
    hasta = (hoy() + timedelta(days=1)).isoformat()
    assert hasta in out
    assert prefs_briefing(_uid())["silencio_hasta"] == hasta
    manana = datetime.combine(hoy() + timedelta(days=1), datetime.min.time()).replace(hour=8)
    assert send_morning_briefings(now=manana, send_fn=lambda c, b: None) == 0
    handle_inbound("42", text="/silencio 0", update_id="p2", send_fn=lambda c, b: None)
    assert prefs_briefing(_uid())["silencio_hasta"] == ""
    assert send_morning_briefings(now=manana, send_fn=lambda c, b: None) == 1


def test_plan_free_no_recibe(web_client, monkeypatch):
    _setup(web_client)
    from app.db.telegram_state import guardar_prefs_briefing
    from app.telegram import send_morning_briefings

    guardar_prefs_briefing(_uid(), activo=True, hora="07:00", extra=[])
    monkeypatch.setattr("app.billing.puede_telegram", lambda plan=None: False)
    assert send_morning_briefings(now=datetime(2030, 1, 10, 8, 0), send_fn=lambda c, b: None) == 0


def test_htmx_guarda_briefing(web_client):
    _setup(web_client)
    r = web_client.post(
        "/app/usuarios/telegram/briefing",
        data={"activo": "1", "hora": "08:30", "extra": "teologia"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    assert b'id="tg-briefing"' in r.content
    assert b'value="08:30"' in r.content
    assert b"checked" in r.content
    assert b"<html" not in r.content.lower()
    from app.db.telegram_state import prefs_briefing

    prefs = prefs_briefing(_uid())
    assert prefs["activo"] is True and prefs["hora"] == "08:30" and prefs["extra"] == {"teologia"}
