"""Stripe webhook — mismo contrato que webhook/main.py, integrado en FastAPI web."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger
from app.secrets import get_secret

router = APIRouter(tags=["stripe"])
log = get_logger("stripe_webhook")


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    import stripe

    secret = (get_secret("STRIPE_SECRET_KEY") or "").strip()
    whsec = (get_secret("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret or not whsec:
        log.error(
            "webhook: faltan secrets secret=%s whsec=%s",
            bool(secret),
            bool(whsec),
        )
        raise HTTPException(
            500,
            "Faltan STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET en el entorno Railway",
        )
    if not stripe_signature:
        raise HTTPException(400, "Falta Stripe-Signature")

    payload = await request.body()
    stripe.api_key = secret
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, whsec)
    except ValueError as e:
        raise HTTPException(400, f"Payload inválido: {e}") from e
    except stripe.error.SignatureVerificationError as e:
        log.warning("webhook: firma inválida (¿whsec del endpoint correcto?)")
        raise HTTPException(400, f"Firma inválida: {e}") from e

    etype = event["type"]
    data = event["data"]["object"]

    try:
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
                except Exception as e:
                    log.warning("webhook: no se pudo inferir plan: %s", e)
                    meta.setdefault("plan", PLAN_PREMIUM)
                    session["metadata"] = meta
            ok, msg = aplicar_evento_checkout(session)
            log.info("checkout.session.completed ok=%s detail=%s", ok, msg)
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
    except HTTPException:
        raise
    except Exception as e:
        log.exception("webhook handler falló (%s): %s", etype, e)
        raise HTTPException(500, f"Error procesando {etype}: {e}") from e
