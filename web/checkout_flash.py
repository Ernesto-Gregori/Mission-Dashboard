"""Helpers de retorno Stripe Checkout (?checkout=success|cancel)."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import obtener_usuario_activo
from web.deps import login_user


def pop_checkout_flash(request: Request) -> dict | None:
    """Lee y limpia el flash de checkout guardado en sesión."""
    flash = request.session.pop("checkout_flash", None)
    return flash if isinstance(flash, dict) else None


def consume_checkout_query(
    request: Request,
    user: dict,
    *,
    clean_path: str = "/app/billing",
) -> tuple[dict, RedirectResponse | None]:
    """
    Si hay ?checkout=success|cancel:
    - refresca el usuario desde BD (plan tras webhook)
    - guarda banner en sesión
    - redirige a clean_path sin query (PRG)
    """
    checkout = (request.query_params.get("checkout") or "").strip().lower()
    if checkout not in ("success", "cancel"):
        return user, None

    plan_hint = (request.query_params.get("plan") or "").strip().lower() or None
    fresh = None
    try:
        fresh = obtener_usuario_activo(int(user["id"]))
    except Exception:
        fresh = None
    if fresh:
        login_user(request, fresh)
        user = fresh

    plan = plan_vigente(user)
    plan_label = limites(plan)["nombre"]

    if checkout == "success":
        if plan != PLAN_FREE:
            msg = f"Pago recibido. Plan activo: {plan_label}."
        else:
            hint = f" ({plan_hint})" if plan_hint else ""
            msg = (
                f"Pago recibido{hint}. Si tu plan aún aparece Free, espera unos "
                "segundos y recarga — el webhook de Stripe actualiza Turso."
            )
        request.session["checkout_flash"] = {
            "kind": "ok",
            "message": msg,
            "plan": plan,
            "plan_hint": plan_hint,
        }
    else:
        request.session["checkout_flash"] = {
            "kind": "info",
            "message": "Checkout cancelado. Puedes intentarlo cuando quieras.",
            "plan": plan,
            "plan_hint": None,
        }

    return user, RedirectResponse(clean_path, status_code=303)
