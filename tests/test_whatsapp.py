"""WhatsApp Cloud API — vínculo, intenciones y webhook firmado."""
from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.rate_limit import limpiar_todo
from app.tenant import clear_current_user


SECRET = "wa-test-secret"
VERIFY = "wa-verify"


def _sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _payload(phone: str, text: str = "", *, wamid: str = "wamid.1", audio_id: str = ""):
    msg = {"from": phone, "id": wamid, "type": "text", "text": {"body": text}}
    if audio_id:
        msg = {"from": phone, "id": wamid, "type": "audio", "audio": {"id": audio_id}}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [msg]}}]}],
    }


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "whatsapp_test.db"
    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY)
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


def _onboard(client: TestClient, username: str = "wa_admin") -> None:
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


def test_webhook_verify_challenge(web_client):
    r = web_client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "abc123"},
    )
    assert r.status_code == 200
    assert r.text == "abc123"


def test_webhook_rejects_bad_signature(web_client):
    raw = json.dumps(_payload("5215512345678", "hola")).encode()
    r = web_client.post(
        "/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_unlinked_never_creates_gasto(web_client, monkeypatch):
    _onboard(web_client)
    sent = []
    monkeypatch.setattr("app.whatsapp.send_text", lambda phone, body, send_fn=None: sent.append(body) or True)
    raw = json.dumps(_payload("5215511112222", "35 en supermercado", wamid="w1")).encode()
    r = web_client.post(
        "/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": _sign(raw), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    from app.db.core import ejecutar

    rows = ejecutar("SELECT id FROM gastos_sobres", fetchall=True) or []
    assert rows == []
    assert sent and "vinculado" in sent[0].lower()


def test_link_briefing_gasto_tarea(web_client, monkeypatch):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.whatsapp import confirm_link, handle_inbound, start_link

    user = autenticar_usuario("wa_admin", "password1")
    uid = int(user["id"])
    ok, _, code = start_link(uid, "5512345678")
    assert ok and code
    ok, msg = confirm_link(uid, code)
    assert ok

    sent = []
    monkeypatch.setattr(
        "app.whatsapp.parse_intent",
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
        lambda datos: created.append(datos) or "gid-wa",
    )

    briefing = handle_inbound("5215512345678", text="briefing", wamid="b1", send_fn=lambda p, b: sent.append(b))
    assert "Foco" in briefing
    gasto = handle_inbound("5215512345678", text="35 en super", wamid="g1", send_fn=lambda p, b: sent.append(b))
    assert "35" in gasto
    from app.db.core import ejecutar

    rows = ejecutar("SELECT descripcion, origen, monto FROM gastos_sobres", fetchall=True) or []
    assert rows and float(rows[0]["monto"]) == 35
    tarea = handle_inbound(
        "5215512345678",
        text="mañana 5pm llamar al banco",
        wamid="t1",
        send_fn=lambda p, b: sent.append(b),
    )
    assert "Llamar al banco" in tarea or "banco" in tarea.lower()
    assert created and created[0]["titulo"]


def test_audio_transcribe_to_task(web_client, monkeypatch):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.whatsapp import confirm_link, handle_inbound, start_link

    user = autenticar_usuario("wa_admin", "password1")
    ok, _, code = start_link(int(user["id"]), "5599998888")
    assert ok
    assert confirm_link(int(user["id"]), code)[0]
    monkeypatch.setattr(
        "app.whatsapp.parse_intent",
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
        "525599998888",
        audio_id="media-1",
        wamid="a1",
        send_fn=lambda p, b: sent.append(b),
        download_fn=lambda mid: b"fake-ogg",
        transcribe_fn=lambda data: "comprar pan",
    )
    assert "comprar pan" in out.lower() or "Tarea" in out


def test_reminders_fire(web_client):
    from app.whatsapp import schedule_reminder, send_due_reminders

    _onboard(web_client)
    from app.database import autenticar_usuario

    user = autenticar_usuario("wa_admin", "password1")
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec="seconds")
    # fire_at in the past via schedule then tweak
    schedule_reminder(int(user["id"]), 1, "2099-01-01", "10:00", "X", "52155")
    from app.db.core import ejecutar

    ejecutar(
        "UPDATE whatsapp_reminders SET fire_at = ? WHERE titulo = 'X'",
        [past],
    )
    sent = []
    n = send_due_reminders(now=datetime.utcnow(), send_fn=lambda p, b: sent.append(b))
    assert n == 1
    assert sent


def test_usuarios_whatsapp_tab(web_client):
    _onboard(web_client)
    r = web_client.get("/app/usuarios?tab=whatsapp")
    assert r.status_code == 200
    assert b"WhatsApp" in r.content
    assert b"wa-phone" in r.content
    r = web_client.post(
        "/app/usuarios/whatsapp/vincular",
        data={"phone": "5512340000"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"C" in r.content  # código
    assert b"wa-code" in r.content
