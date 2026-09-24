"""Telegram v2 · Fase 0 — regresiones B1–B5, B7 (origen) y chats no privados."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest

from tests.test_telegram import SECRET, _link_admin, _onboard, _payload, web_client  # noqa: F401

UNKNOWN = lambda t: {"intent": "unknown"}  # noqa: E731 — Groq caído / sin match


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _say(chat: str, text: str, uid: str, parse_fn=UNKNOWN) -> str:
    from app.telegram import handle_inbound

    return handle_inbound(chat, text=text, update_id=uid, send_fn=lambda c, b: None, parse_fn=parse_fn)


@pytest.fixture()
def linked(web_client):  # noqa: F811
    _onboard(web_client)
    _link_admin("42")
    return web_client


# ── B1 · recordatorios en hora local ────────────────────────────────


def test_b1_reminder_not_sent_hours_early(linked):
    from app.telegram import schedule_reminder, send_due_reminders
    from app.timezone_config import ahora

    evento = ahora() + timedelta(hours=3)
    schedule_reminder(1, 1, evento.date().isoformat(), evento.strftime("%H:%M"), "Dentista", "42")
    sent = []
    assert send_due_reminders(send_fn=lambda c, b: sent.append(b)) == 0
    assert sent == []


def test_b1_reminder_fires_with_fixed_local_clock(linked, monkeypatch):
    from datetime import datetime

    from app.telegram import schedule_reminder, send_due_reminders

    schedule_reminder(1, 1, "2030-01-10", "10:00", "Dentista", "42")
    monkeypatch.setattr("app.timezone_config.ahora", lambda: datetime(2030, 1, 10, 9, 29))
    assert send_due_reminders(send_fn=lambda c, b: None) == 0
    monkeypatch.setattr("app.timezone_config.ahora", lambda: datetime(2030, 1, 10, 9, 30))
    sent = []
    assert send_due_reminders(send_fn=lambda c, b: sent.append(b)) == 1
    assert "Dentista" in sent[0]


# ── B2 · briefing por palabra completa ─────────────────────────────


def test_b2_agendar_creates_task_not_briefing(linked):
    out = _say("42", "agendar reunión con Juan mañana 5pm", "b2a")
    assert "Foco" not in out
    ev = _rows("eventos_calendario")
    assert len(ev) == 1
    assert ev[0]["hora_inicio"] == "17:00"
    assert "Juan" in ev[0]["titulo"]


def test_b2_resumen_inside_sentence_is_not_briefing(linked):
    out = _say("42", "leer el resumen del capítulo 3", "b2b")
    assert "Foco" not in out
    assert _rows("gastos_sobres") == []


@pytest.mark.parametrize("text", ["briefing", "agenda", "resumen", "hoy", "¿qué hay hoy?"])
def test_b2_short_briefing_phrases_still_work(linked, text):
    assert "Foco" in _say("42", text, f"b2-{text}")


# ── B3 · nada se crea por ambigüedad ───────────────────────────────


@pytest.mark.parametrize("text", ["hola", "gracias", "ok 👍", "comprar 2 libros"])
def test_b3_ambiguous_text_writes_nothing(linked, text):
    out = _say("42", text, f"b3-{text}")
    assert "no entendí" in out.lower()
    assert _rows("gastos_sobres") == []
    assert _rows("eventos_calendario") == []


# ── B4 · heurísticas ancladas ───────────────────────────────────────


def test_b4_time_is_not_an_amount(linked):
    _say("42", "reunión 5pm con Juan", "b4a")
    assert _rows("gastos_sobres") == []
    ev = _rows("eventos_calendario")
    assert len(ev) == 1 and ev[0]["hora_inicio"] == "17:00"


@pytest.mark.parametrize(
    "text,monto,desc",
    [
        ("35 en super", 35.0, "super"),
        ("$12.50 uber", 12.5, "uber"),
        ("gasté 8 en café", 8.0, "café"),
        ("café 8", 8.0, "café"),
        ("almuerzo $7,25", 7.25, "almuerzo"),
    ],
)
def test_b4_anchored_amounts(text, monto, desc):
    from app.telegram_actions.finanzas import heuristic_gasto as _heuristic_gasto

    g = _heuristic_gasto(text)
    assert g["intent"] == "gasto"
    assert g["monto"] == monto
    assert g["descripcion"] == desc


@pytest.mark.parametrize(
    "text",
    ["comprar 2 libros", "reunión 5pm con Juan", "leer el resumen del capítulo 3", "35 pesos en super"],
)
def test_b4_non_amounts(text):
    from app.telegram_actions.finanzas import heuristic_gasto as _heuristic_gasto

    assert _heuristic_gasto(text)["intent"] == "unknown"


@pytest.mark.parametrize(
    "text,hora",
    [
        ("mañana 5pm llamar al banco", "17:00"),
        ("dentista 16:30", "16:30"),
        ("llamar a mamá a las 8", "08:00"),
        ("junta 12am", "00:00"),
        ("comprar 2 libros", None),
    ],
)
def test_b4_explicit_time_only(text, hora):
    from app.telegram_actions.agenda import explicit_time as _explicit_time

    assert _explicit_time(text) == hora


# ── B5 · el webhook no bloquea el event loop ───────────────────────


def test_b5_webhook_runs_handler_off_event_loop(web_client, monkeypatch):  # noqa: F811
    seen = []

    def fake_handle(chat_id, **kw):
        try:
            asyncio.get_running_loop()
            seen.append("loop")
        except RuntimeError:
            seen.append("thread")
        return ""

    monkeypatch.setattr("web.routers.telegram.handle_inbound", fake_handle)
    r = web_client.post(
        "/telegram/webhook",
        content=json.dumps(_payload(5, "hola")).encode(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert seen == ["thread"]


# ── Solo chats privados ─────────────────────────────────────────────


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
def test_non_private_chats_are_ignored(chat_type):
    from app.telegram import extract_inbound

    payload = _payload(-100, "123456")
    payload["message"]["chat"]["type"] = chat_type
    assert extract_inbound(payload) == []


def test_group_cannot_link_with_code(web_client, monkeypatch):  # noqa: F811
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.telegram import find_link_by_chat, start_link

    ok, _, code = start_link(int(autenticar_usuario("tg_admin", "password1")["id"]))
    monkeypatch.setattr("app.telegram.send_text", lambda *a, **k: True)
    payload = _payload(-100123, f"/start {code}", update_id=900)
    payload["message"]["chat"]["type"] = "group"
    r = web_client.post(
        "/telegram/webhook",
        content=json.dumps(payload).encode(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert find_link_by_chat("-100123") is None


# ── B7 (parte 1) · origen telegram + respuesta ─────────────────────


def test_b7_origen_telegram_registered_and_reply(linked):
    from app.db.schema import GASTO_ORIGEN_TELEGRAM, GASTO_ORIGENES

    assert GASTO_ORIGEN_TELEGRAM == "telegram" and GASTO_ORIGEN_TELEGRAM in GASTO_ORIGENES
    out = _say("42", "35 en super", "b7")
    assert out.startswith("Anoté $35.00")
    assert "Gasté" not in out
    rows = _rows("gastos_sobres")
    assert len(rows) == 1 and rows[0]["origen"] == "telegram"
    linked.post("/app/coach/activar", data={"modulos": ["agenda", "salud", "finanzas"]})
    page = linked.get("/app/m/finanzas")
    assert page.status_code == 200
    assert b'<span class="badge">telegram</span>' in page.content
