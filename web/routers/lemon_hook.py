"""Lemon Squeezy webhooks — activa/cancela plan vía subscription_*."""
from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger
from app.secrets import get_secret

router = APIRouter(tags=["lemon"])
log = get_logger("lemon_webhook")

# Eventos que mutan plan (si fallan → 5xx para reintento)
MUTATING = {
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_expired",
    "subscription_paused",
    "subscription_unpaused",
    "subscription_payment_success",
    "subscription_payment_recovered",
}


@router.post("/lemon/webhook")
async def lemon_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    whsec = (get_secret("LEMON_SQUEEZY_WEBHOOK_SECRET") or "").strip()
    if not whsec:
        log.error("webhook lemon: falta LEMON_SQUEEZY_WEBHOOK_SECRET")
        raise HTTPException(500, "Falta LEMON_SQUEEZY_WEBHOOK_SECRET")

    raw = await request.body()
    from app.lemon_squeezy import aplicar_subscription_event, verify_webhook_signature

    if not verify_webhook_signature(raw, x_signature, whsec):
        log.warning("webhook lemon: firma inválida")
        raise HTTPException(400, "Firma inválida")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(400, f"JSON inválido: {e}") from e

    meta = payload.get("meta") or {}
    event_name = (meta.get("event_name") or "").strip()
    if not event_name:
        raise HTTPException(400, "Falta meta.event_name")

    if event_name not in MUTATING:
        return JSONResponse({"handled": event_name, "ok": True, "detail": "ignored"})

    try:
        from app.billing import ensure_billing_schema

        ensure_billing_schema()
        ok, msg = aplicar_subscription_event(event_name, payload)
        log.info("lemon %s ok=%s detail=%s", event_name, ok, msg)
        if not ok:
            # Reintento Lemon (hasta 3) si no pudimos aplicar el plan
            raise HTTPException(500, f"No se aplicó {event_name}: {msg}")
        return JSONResponse({"handled": event_name, "ok": True, "detail": msg})
    except HTTPException:
        raise
    except Exception as e:
        log.exception("lemon webhook falló (%s): %s", event_name, e)
        raise HTTPException(500, f"Error procesando {event_name}: {e}") from e
