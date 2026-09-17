"""Tests — Lemon Squeezy checkout helpers + webhook."""
from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "lemon_test.db"
    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setenv("APP_URL", "https://app.example.com")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("LEMON_SQUEEZY_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    import app.db.core as core

    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setattr(core, "usar_turso", lambda: False)
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)

    from web.app import create_app

    with TestClient(create_app()) as client:
        yield client


def _setup(client: TestClient):
    client.post(
        "/setup",
        data={
            "username": "lemon_admin",
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
    client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "finanzas"]},
        follow_redirects=False,
    )


def test_verify_signature():
    from app.lemon_squeezy import verify_webhook_signature

    body = b'{"meta":{"event_name":"subscription_created"}}'
    secret = "whsec_test"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, sig, secret) is True
    assert verify_webhook_signature(body, "bad", secret) is False


def test_checkout_prefers_lemon_buy_link(web_client, monkeypatch):
    monkeypatch.setenv("LEMON_SQUEEZY_API_KEY", "key_test")
    monkeypatch.setenv("LEMON_SQUEEZY_STORE_ID", "1")
    monkeypatch.setenv(
        "LEMON_SQUEEZY_CHECKOUT_PREMIUM",
        "https://store.lemonsqueezy.com/checkout/buy/abc",
    )
    # Sin variant → buy link
    monkeypatch.delenv("LEMON_SQUEEZY_VARIANT_PREMIUM", raising=False)

    from app.billing import crear_checkout_session, payment_provider

    assert payment_provider() == "lemon"
    url, err = crear_checkout_session("premium", 7, username="neto")
    assert err is None
    assert url and "lemonsqueezy.com" in url
    assert "checkout[custom][user_id]=7" in url
    assert "checkout[custom][plan]=premium" in url


def test_webhook_activa_plan(web_client, monkeypatch):
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "secret123")
    _setup(web_client)

    # user id del admin setup = 1 normalmente
    payload = {
        "meta": {
            "event_name": "subscription_created",
            "custom_data": {"user_id": "1", "plan": "premium"},
        },
        "data": {
            "type": "subscriptions",
            "id": "99",
            "attributes": {
                "customer_id": 55,
                "variant_id": 10,
                "status": "active",
            },
        },
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"secret123", raw, hashlib.sha256).hexdigest()
    r = web_client.post(
        "/lemon/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": sig,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    from app.db.core import ejecutar

    rows = ejecutar("SELECT plan, lemon_subscription_id FROM usuarios WHERE id = 1", fetchall=True)
    assert rows[0]["plan"] == "premium"
    assert str(rows[0]["lemon_subscription_id"]) == "99"


def test_webhook_fail_sin_user_devuelve_500(web_client, monkeypatch):
    monkeypatch.setenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "secret123")
    payload = {
        "meta": {"event_name": "subscription_created", "custom_data": {}},
        "data": {"type": "subscriptions", "id": "1", "attributes": {"status": "active"}},
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"secret123", raw, hashlib.sha256).hexdigest()
    r = web_client.post(
        "/lemon/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert r.status_code == 500
