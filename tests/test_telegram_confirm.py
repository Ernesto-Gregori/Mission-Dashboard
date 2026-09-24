"""Telegram v2 · confirmaciones (botones inline + «sí/no»), expiración y /deshacer."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tests.test_telegram import SECRET, _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _say(text: str, uid: str, chat: str = "42", **kw) -> str:
    from app.telegram import handle_inbound

    kw.setdefault("parse_fn", lambda t: {"intent": "unknown"})
    return handle_inbound(chat, text=text, update_id=uid, send_fn=lambda c, b: None, **kw)


def _click(pending_id: int, answer: str, uid: str, chat: str = "42", answered: list | None = None) -> str:
    return _say(
        "",
        uid,
        chat=chat,
        callback_id=f"cb-{uid}",
        callback_data=f"p:{pending_id}:{answer}",
        answer_fn=(answered.append if answered is not None else lambda _id: None),
    )


def _pending_id() -> int:
    rows = _rows("telegram_pending")
    assert len(rows) == 1
    return int(rows[0]["id"])


def _shift_clock(monkeypatch, minutes: int) -> None:
    from app import timezone_config

    real = timezone_config.ahora
    base = real()
    monkeypatch.setattr("app.timezone_config.ahora", lambda: base + timedelta(minutes=minutes))


@pytest.fixture()
def linked(web_client):  # noqa: F811
    _onboard(web_client)
    _link_admin("42")
    return web_client


# ── Confirmación por monto alto ─────────────────────────────────────


def test_large_gasto_asks_and_writes_nothing(linked):
    out = _say("/gasto 250 televisor", "c1")
    assert "$250.00" in out and "«sí» / «no»" in out
    assert _rows("gastos_sobres") == []
    assert _pending_id()


def test_small_gasto_does_not_ask(linked):
    out = _say("/gasto 35 super", "c2")
    assert out.startswith("Anoté $35.00") and "/deshacer" in out
    assert _rows("telegram_pending") == []


def test_confirm_buttons_fit_callback_limit(linked):
    from app.database import autenticar_usuario
    from app.telegram import _route
    from app.telegram_actions import Contexto

    ctx = Contexto(user=autenticar_usuario("tg_admin", "password1"), chat_id="42", parse_fn=lambda t: {})
    resp = _route(ctx, "/gasto 999 laptop")
    assert [b[0] for b in resp.botones] == ["✅ Sí", "✖️ No"]
    assert all(len(data.encode()) <= 64 for _, data in resp.botones)


@pytest.mark.parametrize("answer", ["sí", "Si", "dale"])
def test_text_yes_confirms(linked, answer):
    _say("/gasto 250 televisor", "t1")
    out = _say(answer, "t2")
    assert out.startswith("Anoté $250.00")
    assert len(_rows("gastos_sobres")) == 1
    assert _rows("telegram_pending") == []


def test_text_no_cancels(linked):
    _say("/gasto 250 televisor", "t3")
    assert "Cancelado" in _say("no", "t4")
    assert _rows("gastos_sobres") == []
    assert _rows("telegram_pending") == []


def test_yes_without_pending_writes_nothing(linked):
    assert "no entendí" in _say("sí", "t5").lower()
    assert _rows("gastos_sobres") == []


def test_button_confirms_once_and_answers_callback(linked):
    _say("/gasto 250 televisor", "b1")
    pid = _pending_id()
    answered: list = []
    assert _click(pid, "si", "b2", answered=answered).startswith("Anoté $250.00")
    assert "ya no está disponible" in _click(pid, "si", "b3", answered=answered)
    assert len(_rows("gastos_sobres")) == 1
    assert answered == ["cb-b2", "cb-b3"]


def test_button_cancel(linked):
    _say("/gasto 250 televisor", "b4")
    assert "Cancelado" in _click(_pending_id(), "no", "b5")
    assert _rows("gastos_sobres") == []


def test_confirmation_expires(linked, monkeypatch):
    _say("/gasto 250 televisor", "e1")
    pid = _pending_id()
    _shift_clock(monkeypatch, 11)
    assert "venció" in _click(pid, "si", "e2")
    assert _rows("gastos_sobres") == []


def test_forged_callback_data_is_rejected(linked):
    _say("/gasto 250 televisor", "f1")
    out = _say("", "f2", callback_id="cb", callback_data="p:1:si; DROP", answer_fn=lambda _id: None)
    assert "no sirve" in out
    assert _rows("gastos_sobres") == []


def test_callback_needs_paid_plan(linked, monkeypatch):
    _say("/gasto 250 televisor", "p1")
    pid = _pending_id()
    monkeypatch.setattr("app.billing.puede_telegram", lambda plan=None: False)
    assert "Premium" in _click(pid, "si", "p2")
    assert _rows("gastos_sobres") == []


def test_callback_from_unlinked_chat_does_nothing(linked):
    _say("/gasto 250 televisor", "u1")
    out = _click(_pending_id(), "si", "u2", chat="999")
    assert "vincul" in out.lower()
    assert _rows("gastos_sobres") == []
    assert len(_rows("telegram_pending")) == 1


def test_familia_users_cannot_confirm_each_other(linked):
    from app.database import autenticar_usuario
    from app.db.usuarios import crear_usuario
    from app.telegram import handle_inbound, start_link

    ok, _ = crear_usuario("tg_familia", "password1", rol="usuario", plan="familia")
    assert ok
    ok, _, code = start_link(int(autenticar_usuario("tg_familia", "password1")["id"]))
    handle_inbound("43", text=f"/start {code}", update_id="fam-link", send_fn=lambda c, b: None)

    _say("/gasto 250 televisor", "fam1", chat="42")
    pid = _pending_id()
    assert "ya no está disponible" in _click(pid, "si", "fam2", chat="43")
    assert "no entendí" in _say("sí", "fam3", chat="43").lower()
    assert _rows("gastos_sobres") == []
    assert _click(pid, "si", "fam4", chat="42").startswith("Anoté $250.00")
    gastos = _rows("gastos_sobres")
    assert len(gastos) == 1
    assert int(gastos[0]["user_id"]) == int(autenticar_usuario("tg_admin", "password1")["id"])
    assert "nada para deshacer" in _say("/deshacer", "fam5", chat="43")
    assert len(_rows("gastos_sobres")) == 1


# ── /deshacer ───────────────────────────────────────────────────────


def test_deshacer_gasto_once(linked):
    _say("/gasto 35 super", "d1")
    assert len(_rows("gastos_sobres")) == 1
    out = _say("/deshacer", "d2")
    assert out == "Deshice: gasto $35.00 «super»."
    assert _rows("gastos_sobres") == []
    assert "nada para deshacer" in _say("/deshacer", "d3")
    audit = [r["accion"] for r in _rows("audit_log")]
    assert "telegram_gasto" in audit and "telegram_deshacer" in audit


def test_deshacer_only_last_action(linked):
    _say("/gasto 35 super", "d4")
    _say("/gasto 8 café", "d5")
    _say("/deshacer", "d6")
    rows = _rows("gastos_sobres")
    assert [float(r["monto"]) for r in rows] == [35.0]


def test_deshacer_tarea_removes_event_and_reminder(linked, monkeypatch):
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: False)
    out = _say("/tarea mañana 5pm llamar al banco", "d7")
    assert "/deshacer" in out
    assert len(_rows("eventos_calendario")) == 1 and len(_rows("telegram_reminders")) == 1
    assert "Deshice: tarea" in _say("/deshacer", "d8")
    assert _rows("eventos_calendario") == []
    assert _rows("telegram_reminders") == []


def test_deshacer_expires(linked, monkeypatch):
    _say("/gasto 35 super", "d9")
    _shift_clock(monkeypatch, 31)
    assert "nada para deshacer" in _say("/deshacer", "d10")
    assert len(_rows("gastos_sobres")) == 1


def test_briefing_is_not_undoable(linked):
    _say("/briefing", "d11")
    assert "nada para deshacer" in _say("/deshacer", "d12")


# ── Transporte: callback_query ──────────────────────────────────────


def _callback_payload(chat_type: str = "private") -> dict:
    return {
        "update_id": 555,
        "callback_query": {
            "id": "cbq-1",
            "from": {"id": 42, "username": "tester"},
            "message": {"message_id": 9, "chat": {"id": 42, "type": chat_type}},
            "data": "p:7:si",
        },
    }


def test_extract_inbound_callback():
    from app.telegram import extract_inbound

    [item] = extract_inbound(_callback_payload())
    assert item["chat_id"] == "42" and item["callback_id"] == "cbq-1"
    assert item["callback_data"] == "p:7:si" and item["text"] == ""
    assert extract_inbound(_callback_payload("group")) == []


def test_webhook_callback_answers_query(linked, monkeypatch):
    calls = []
    monkeypatch.setattr("app.telegram._api", lambda method, payload=None, **kw: calls.append(method) or {"ok": True})
    r = linked.post(
        "/telegram/webhook",
        content=json.dumps(_callback_payload()).encode(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert calls[0] == "answerCallbackQuery"
    assert "sendMessage" in calls


def test_register_webhook_allows_callback_query(monkeypatch):
    from app import telegram as tg

    calls = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(tg, "_api", lambda method, payload=None, **kw: calls.append((method, payload)) or {"ok": True})
    assert tg.register_webhook("https://mission.example") is True
    webhook = dict(calls)["setWebhook"]
    assert webhook["allowed_updates"] == ["message", "callback_query"]
