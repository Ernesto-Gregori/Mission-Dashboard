"""
Stripe webhook — actualiza usuarios.plan en Turso.

Deploy (Railway / Render / Fly), NO dentro de Streamlit Cloud.

Env requeridas:
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
  TURSO_URL
  TURSO_TOKEN
  STRIPE_PRICE_PREMIUM   (price_xxx)
  STRIPE_PRICE_FAMILIA   (price_xxx)  opcional

Stripe Dashboard → Developers → Webhooks → Add endpoint:
  https://TU-WEBHOOK/stripe/webhook
  Events: checkout.session.completed, customer.subscription.deleted

Local test:
  stripe listen --forward-to localhost:8080/stripe/webhook
  uvicorn webhook.main:app --port 8080
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

# Repo root en PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

app = FastAPI(title="Mission Dashboard Stripe Webhook", version="1.0.0")


@app.get("/health")
def health():
    turso = bool(os.getenv("TURSO_URL") and os.getenv("TURSO_TOKEN"))
    stripe_ok = bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET"))
    return {
        "ok": True,
        "turso": turso,
        "stripe": stripe_ok,
    }


@app.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    import stripe

    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    whsec = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret or not whsec:
        raise HTTPException(500, "Faltan STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(400, "Falta Stripe-Signature")

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
        aplicar_cancelacion_subscription,
        aplicar_evento_checkout,
        ensure_billing_schema,
        plan_desde_price_id,
        PLAN_PREMIUM,
    )

    ensure_billing_schema()

    if etype == "checkout.session.completed":
        # Enriquecer metadata.plan desde line items si hace falta
        session = dict(data)
        meta = dict(session.get("metadata") or {})
        if not meta.get("plan"):
            # Intentar expandir line items via API
            try:
                full = stripe.checkout.Session.retrieve(
                    session["id"],
                    expand=["line_items"],
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
                if not meta.get("plan"):
                    meta["plan"] = PLAN_PREMIUM
                    session["metadata"] = meta
        ok, msg = aplicar_evento_checkout(session)
        return JSONResponse({"handled": etype, "ok": ok, "detail": msg})

    if etype in (
        "customer.subscription.deleted",
        "customer.subscription.canceled",
    ):
        ok, msg = aplicar_cancelacion_subscription(dict(data))
        return JSONResponse({"handled": etype, "ok": ok, "detail": msg})

    # subscription updated → sync plan from price if metadata present
    if etype == "customer.subscription.updated":
        sub = dict(data)
        status = (sub.get("status") or "").lower()
        if status in ("canceled", "unpaid", "incomplete_expired"):
            ok, msg = aplicar_cancelacion_subscription(sub)
            return JSONResponse({"handled": etype, "ok": ok, "detail": msg})
        return JSONResponse({"handled": etype, "ok": True, "detail": "ignored_active"})

    return JSONResponse({"handled": etype, "ok": True, "detail": "ignored"})
