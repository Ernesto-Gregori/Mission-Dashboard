"""
Lemon Squeezy — Merchant of Record (checkout + webhooks).

Preferido frente a Stripe cuando la cuenta del vendedor no puede
completar onboarding por país. Fees típicos ~5%+$0.50; LS es MoR
(impuestos/VAT los maneja ellos).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib import error, request

from app.logging_config import get_logger

log = get_logger("lemon_squeezy")

API_BASE = "https://api.lemonsqueezy.com/v1"


def _secret(name: str, default: str = "") -> str:
    from app.secrets import get_secret

    return (get_secret(name, default) or "").strip()


def lemon_configured() -> bool:
    return bool(
        _secret("LEMON_SQUEEZY_API_KEY")
        and _secret("LEMON_SQUEEZY_STORE_ID")
        and (
            _secret("LEMON_SQUEEZY_VARIANT_PREMIUM")
            or _secret("LEMON_SQUEEZY_CHECKOUT_PREMIUM")
            or _secret("LEMON_SQUEEZY_VARIANT_FAMILIA")
            or _secret("LEMON_SQUEEZY_CHECKOUT_FAMILIA")
        )
    )


def variant_id_for_plan(plan: str) -> str:
    from app.billing import PLAN_FAMILIA, PLAN_PREMIUM, normalizar_plan

    plan = normalizar_plan(plan)
    key = {
        PLAN_PREMIUM: "LEMON_SQUEEZY_VARIANT_PREMIUM",
        PLAN_FAMILIA: "LEMON_SQUEEZY_VARIANT_FAMILIA",
    }.get(plan, "")
    return _secret(key) if key else ""


def checkout_link_for_plan(plan: str) -> str:
    """Buy link estático (Share → Checkout) como fallback sin API checkout."""
    from app.billing import PLAN_FAMILIA, PLAN_PREMIUM, normalizar_plan

    plan = normalizar_plan(plan)
    key = {
        PLAN_PREMIUM: "LEMON_SQUEEZY_CHECKOUT_PREMIUM",
        PLAN_FAMILIA: "LEMON_SQUEEZY_CHECKOUT_FAMILIA",
    }.get(plan, "")
    return _secret(key) if key else ""


def plan_desde_variant_id(variant_id: str | int | None) -> str | None:
    from app.billing import PLAN_FAMILIA, PLAN_PREMIUM

    if variant_id is None or variant_id == "":
        return None
    vid = str(variant_id).strip()
    if vid and vid == variant_id_for_plan(PLAN_PREMIUM):
        return PLAN_PREMIUM
    if vid and vid == variant_id_for_plan(PLAN_FAMILIA):
        return PLAN_FAMILIA
    return None


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(digest, signature.strip())
    except Exception:
        return False


def _api_post(path: str, payload: dict) -> dict[str, Any]:
    api_key = _secret("LEMON_SQUEEZY_API_KEY")
    if not api_key:
        raise RuntimeError("Falta LEMON_SQUEEZY_API_KEY")
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{API_BASE}{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Lemon API {e.code}: {detail}") from e


def crear_checkout(
    plan_destino: str,
    user_id: int,
    *,
    username: str | None = None,
    email: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Crea checkout Lemon Squeezy (subscription variant).
    Retorna (url, error).
    """
    from app.billing import PLAN_FREE, app_base_url, checkout_return_urls, normalizar_plan

    plan_destino = normalizar_plan(plan_destino)
    if plan_destino == PLAN_FREE:
        return None, "Plan Free no requiere pago"

    store_id = _secret("LEMON_SQUEEZY_STORE_ID")
    variant = variant_id_for_plan(plan_destino)
    if not store_id:
        return None, "Falta LEMON_SQUEEZY_STORE_ID"
    if not variant:
        link = checkout_link_for_plan(plan_destino)
        if link:
            # Buy link + custom data en query
            sep = "&" if "?" in link else "?"
            q = (
                f"checkout[custom][user_id]={int(user_id)}"
                f"&checkout[custom][plan]={plan_destino}"
            )
            if username:
                from urllib.parse import quote

                q += f"&checkout[custom][username]={quote(str(username)[:64])}"
            return f"{link}{sep}{q}", None
        return None, f"Falta LEMON_SQUEEZY_VARIANT_{plan_destino.upper()}"

    if not _secret("LEMON_SQUEEZY_API_KEY"):
        return None, "Falta LEMON_SQUEEZY_API_KEY"

    success, _cancel = checkout_return_urls(plan_destino)
    # Lemon usa redirect_url post-pago (no cancel URL nativa en API checkout)
    redirect = success
    if not app_base_url():
        log.warning("APP_URL vacío — redirect Lemon puede fallar")

    custom: dict[str, Any] = {
        "user_id": str(int(user_id)),
        "plan": plan_destino,
    }
    if username:
        custom["username"] = str(username)[:64]

    checkout_data: dict[str, Any] = {"custom": custom}
    if email:
        checkout_data["email"] = str(email)

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": checkout_data,
                "product_options": {
                    "redirect_url": redirect,
                    "receipt_button_text": "Volver a Mission Dashboard",
                    "receipt_link_url": redirect,
                },
                "checkout_options": {
                    "embed": False,
                    "media": False,
                    "logo": True,
                    "desc": True,
                    "discount": True,
                    "subscription_preview": True,
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(store_id)}},
                "variant": {"data": {"type": "variants", "id": str(variant)}},
            },
        }
    }

    try:
        resp = _api_post("/checkouts", payload)
        url = ((resp.get("data") or {}).get("attributes") or {}).get("url")
        if not url:
            return None, "Lemon no devolvió URL de checkout"
        return str(url), None
    except Exception as e:
        log.exception("crear_checkout lemon: %s", e)
        return None, str(e)[:200]


def _custom_from_meta(meta: dict) -> dict[str, Any]:
    raw = meta.get("custom_data") or meta.get("custom") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def aplicar_subscription_event(event_name: str, payload: dict) -> tuple[bool, str]:
    """
    Aplica subscription_* de Lemon Squeezy → plan local.
    Retorna (ok, detail). ok=False debe mapearse a HTTP 5xx en el webhook.
    """
    from app.billing import PLAN_FREE, PLAN_PREMIUM, set_plan

    meta = payload.get("meta") or {}
    data = payload.get("data") or payload
    attrs = data.get("attributes") if isinstance(data, dict) else {}
    attrs = attrs or {}
    custom = _custom_from_meta(meta)

    user_id = custom.get("user_id")
    plan = (custom.get("plan") or "").strip().lower()
    variant_id = attrs.get("variant_id")
    if not plan:
        plan = plan_desde_variant_id(variant_id) or ""

    sub_id = data.get("id") if isinstance(data, dict) else None
    customer_id = attrs.get("customer_id")
    status = (attrs.get("status") or "").strip().lower()

    # Resolver user_id por subscription guardada si falta custom
    if not user_id and sub_id:
        from app.db.core import ejecutar

        rows = (
            ejecutar(
                "SELECT id FROM usuarios WHERE lemon_subscription_id = ?",
                [str(sub_id)],
                fetchall=True,
            )
            or []
        )
        if rows:
            user_id = rows[0]["id"]

    if not user_id:
        return False, "webhook sin user_id (custom_data) ni subscription conocida"

    try:
        user_id_i = int(user_id)
    except Exception:
        return False, f"user_id inválido: {user_id}"

    active_events = {
        "subscription_created",
        "subscription_resumed",
        "subscription_unpaused",
        "subscription_payment_success",
        "subscription_payment_recovered",
    }
    cancel_events = {
        "subscription_cancelled",
        "subscription_expired",
        "subscription_paused",
    }

    if event_name in cancel_events or status in (
        "cancelled",
        "expired",
        "paused",
        "unpaid",
    ):
        # cancelled con ends_at futuro a veces sigue activo hasta fin de periodo;
        # Lemon manda status=cancelled — bajamos a free (política simple).
        return set_plan(
            user_id_i,
            PLAN_FREE,
            lemon_customer_id=str(customer_id) if customer_id else None,
            lemon_subscription_id=str(sub_id) if sub_id else "",
        )

    if event_name == "subscription_updated":
        if status in ("active", "on_trial"):
            if not plan:
                plan = PLAN_PREMIUM
            return set_plan(
                user_id_i,
                plan,
                lemon_customer_id=str(customer_id) if customer_id else None,
                lemon_subscription_id=str(sub_id) if sub_id else None,
            )
        if status in ("cancelled", "expired", "paused", "unpaid"):
            return set_plan(
                user_id_i,
                PLAN_FREE,
                lemon_customer_id=str(customer_id) if customer_id else None,
                lemon_subscription_id=str(sub_id) if sub_id else "",
            )
        return True, f"ignored_status:{status or 'unknown'}"

    if event_name in active_events or status in ("active", "on_trial"):
        if not plan:
            plan = plan_desde_variant_id(variant_id) or PLAN_PREMIUM
        return set_plan(
            user_id_i,
            plan,
            lemon_customer_id=str(customer_id) if customer_id else None,
            lemon_subscription_id=str(sub_id) if sub_id else None,
        )

    return True, f"ignored_event:{event_name}"
