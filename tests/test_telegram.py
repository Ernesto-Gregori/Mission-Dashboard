"""Telegram Bot API — vínculo, intenciones y webhook con secret_token."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import limpiar_todo
from app.tenant import clear_current_user


SECRET = "tg-test-secret"


def _payload(chat_id: int, text: str = "", *, update_id: int = 1, voice_id: str = ""):
    msg = {
        "message_id": update_id,
        "from": {"id": chat_id, "username": "tester"},
        "chat": {"id": chat_id, "type": "private"},
        "text": text,
    }
    if voice_id:
        msg.pop("text", None)
        msg["voice"] = {"file_id": voice_id}
    return {"update_id": update_id, "message": msg}


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "telegram_test.db"
    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "mission_test_bot")
    monkeypatch.setenv("APP_URL", "http://127.0.0.1:8000")
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
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)
    limpiar_todo()
    from web.app import create_app

    with TestClient(create_app()) as client:
        yield client
    clear_current_user()
    limpiar_todo()


def _onboard(client: TestClient, username: str = "tg_admin") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "salud"]},
        follow_redirects=False,
    )


def test_webhook_rejects_missing_header(web_client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    r = web_client.post(
        "/telegram/webhook",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    # SESSION_SECRET alcanza para derivar el secret; sin header → 403
    assert r.status_code == 403


def test_public_base_url_prefers_https_app_url(monkeypatch):
    from app.telegram import public_base_url

    monkeypatch.setenv("APP_URL", "https://mission.example")
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    assert public_base_url() == "https://mission.example"


def test_public_base_url_uses_railway_domain(monkeypatch):
    from app.telegram import public_base_url

    monkeypatch.setenv("APP_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "foo.up.railway.app")
    assert public_base_url() == "https://foo.up.railway.app"


def test_webhook_fail_closed_without_any_secret(web_client, monkeypatch):
    monkeypatch.setattr("web.routers.telegram.webhook_secret", lambda: "")
    r = web_client.post(
        "/telegram/webhook",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 500


def test_webhook_rejects_bad_secret(web_client):
    raw = json.dumps(_payload(99, "hola")).encode()
    r = web_client.post(
        "/telegram/webhook",
        content=raw,
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope", "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_whatsapp_routes_gone(web_client):
    r = web_client.post("/whatsapp/webhook", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 404
    r = web_client.get("/app/usuarios?tab=whatsapp")
    assert r.status_code == 200
    assert b"wa-phone" not in r.content


def test_unlinked_never_creates_gasto(web_client, monkeypatch):
    _onboard(web_client)
    sent = []
    monkeypatch.setattr("app.telegram.send_text", lambda chat_id, body, send_fn=None: sent.append(body) or True)
    raw = json.dumps(_payload(111, "35 en supermercado", update_id=7)).encode()
    r = web_client.post(
        "/telegram/webhook",
        content=raw,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    from app.db.core import ejecutar

    rows = ejecutar("SELECT id FROM gastos_sobres", fetchall=True) or []
    assert rows == []
    assert sent and "vinculado" in sent[0].lower()


def test_link_briefing_gasto_tarea(web_client, monkeypatch):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.telegram import handle_inbound, start_link

    user = autenticar_usuario("tg_admin", "password1")
    uid = int(user["id"])
    ok, _, code = start_link(uid)
    assert ok and code

    sent = []
    monkeypatch.setattr(
        "app.telegram.parse_intent",
        lambda t: (
            {"intent": "gasto", "monto": 35, "categoria": "necesidades", "descripcion": "super"}
            if "35" in t
            else {
                "intent": "tarea",
                "titulo": "Llamar al banco",
                "fecha": "2026-09-18",
                "hora_inicio": "17:00",
                "hora_fin": "18:00",
            }
        ),
    )
    created = []
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: True)
    monkeypatch.setattr(
        "app.google_calendar.crear_evento_google",
        lambda datos: created.append(datos) or "gid-tg",
    )

    linked = handle_inbound("42", text=f"/start {code}", update_id="u1", send_fn=lambda c, b: sent.append(b))
    assert "vinculado" in linked.lower() or "Listo" in linked
    briefing = handle_inbound("42", text="briefing", update_id="b1", send_fn=lambda c, b: sent.append(b))
    assert "Foco" in briefing
    gasto = handle_inbound("42", text="35 en super", update_id="g1", send_fn=lambda c, b: sent.append(b))
    assert "35" in gasto
    from app.db.core import ejecutar

    rows = ejecutar("SELECT descripcion, origen, monto FROM gastos_sobres", fetchall=True) or []
    assert rows and float(rows[0]["monto"]) == 35
    assert rows[0]["origen"] == "telegram"
    tarea = handle_inbound(
        "42",
        text="mañana 5pm llamar al banco",
        update_id="t1",
        send_fn=lambda c, b: sent.append(b),
    )
    assert "Llamar al banco" in tarea or "banco" in tarea.lower()
    assert created and created[0]["titulo"]


def test_audio_transcribe_to_task(web_client, monkeypatch):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.telegram import handle_inbound, start_link

    user = autenticar_usuario("tg_admin", "password1")
    ok, _, code = start_link(int(user["id"]))
    assert ok
    handle_inbound("88", text=f"/start {code}", update_id="link", send_fn=lambda c, b: None)
    monkeypatch.setattr(
        "app.telegram.parse_intent",
        lambda t: {
            "intent": "tarea",
            "titulo": t,
            "fecha": "2026-09-19",
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
        },
    )
    sent = []
    out = handle_inbound(
        "88",
        voice_id="file-1",
        update_id="a1",
        send_fn=lambda c, b: sent.append(b),
        download_fn=lambda fid: b"fake-ogg",
        transcribe_fn=lambda data: "comprar pan",
    )
    assert "comprar pan" in out.lower() or "Tarea" in out


def test_reminders_fire(web_client):
    from app.telegram import schedule_reminder, send_due_reminders

    _onboard(web_client)
    from app.database import autenticar_usuario

    user = autenticar_usuario("tg_admin", "password1")
    past = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
    schedule_reminder(int(user["id"]), 1, "2099-01-01", "10:00", "X", "42")
    from app.db.core import ejecutar

    ejecutar("UPDATE telegram_reminders SET fire_at = ? WHERE titulo = 'X'", [past])
    sent = []
    n = send_due_reminders(now=datetime.now(), send_fn=lambda c, b: sent.append(b))
    assert n == 1
    assert sent


def test_usuarios_telegram_tab(web_client):
    _onboard(web_client)
    r = web_client.get("/app/usuarios?tab=telegram")
    assert r.status_code == 200
    assert b"Telegram" in r.content
    assert b"tg-link" in r.content or b"Generar c" in r.content
    r = web_client.post(
        "/app/usuarios/telegram/vincular",
        data={},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"t.me/mission_test_bot" in r.content
    assert b"tg-code" in r.content
