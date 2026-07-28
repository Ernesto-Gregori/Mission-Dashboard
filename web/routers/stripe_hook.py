"""Stripe webhook — mismo contrato que webhook/main.py, integrado en FastAPI web."""
from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["stripe"])


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    import stripe

    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    whsec = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret or not whsec:
        raise HTTPException(500, "Faltan STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET")
    if not stripe_signature:
        raise HTTPException(400, "Falta Stripe-Signature")

    payload = await request.body()
    stripe.api_key = secret
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, whsec)
    except ValueError as e:
        raise HTTPException(400, f"Payload inválido: {e}") from e
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(400, f"Firma inválida: {e}") from e

    etype = event["type"]
    data = event["data"]["object"]

    from app.billing import (
        PLAN_PREMIUM,
        aplicar_cancelacion_subscription,
        aplicar_evento_checkout,
        ensure_billing_schema,
        plan_desde_price_id,
    )

    ensure_billing_schema()

    if etype == "checkout.session.completed":
        session = dict(data)
        meta = dict(session.get("metadata") or {})
        if not meta.get("plan"):
            try:
                full = stripe.checkout.Session.retrieve(
                    session["id"], expand=["line_items"]
                )
                items = (full.get("line_items") or {}).get("data") or []
                if items:
                    price = (items[0].get("price") or {}).get("id")
                    inferred = plan_desde_price_id(price)
                    if inferred:
                        meta["plan"] = inferred
                        meta["price_id"] = price
                        session["metadata"] = meta
            except Exception:
                meta.setdefault("plan", PLAN_PREMIUM)
                session["metadata"] = meta
        ok, msg = aplicar_evento_checkout(session)
        return JSONResponse({"handled": etype, "ok": ok, "detail": msg})

    if etype in ("customer.subscription.deleted", "customer.subscription.canceled"):
        ok, msg = aplicar_cancelacion_subscription(dict(data))
        return JSONResponse({"handled": etype, "ok": ok, "detail": msg})

    if etype == "customer.subscription.updated":
        sub = dict(data)
        status = (sub.get("status") or "").lower()
        if status in ("canceled", "unpaid", "incomplete_expired"):
            ok, msg = aplicar_cancelacion_subscription(sub)
            return JSONResponse({"handled": etype, "ok": ok, "detail": msg})
        return JSONResponse({"handled": etype, "ok": True, "detail": "ignored_active"})

    return JSONResponse({"handled": etype, "ok": True, "detail": "ignored"})
