from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import (
    PLAN_FAMILIA,
    PLAN_PREMIUM,
    crear_checkout_session,
    limites,
    payment_provider,
    payments_configured,
    plan_vigente,
)
from web.checkout_flash import consume_checkout_query, pop_checkout_flash
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/billing", tags=["billing"])


def _ctx(request: Request, user: dict, **extra):
    plan = plan_vigente(user)
    base = {
        "title": "Plan y cobros",
        "user": user,
        "plan": plan,
        "plan_label": limites(plan)["nombre"],
        "payments_ok": payments_configured(),
        "payment_provider": payment_provider(),
        "planes": [
            {"clave": PLAN_PREMIUM, **limites(PLAN_PREMIUM)},
            {"clave": PLAN_FAMILIA, **limites(PLAN_FAMILIA)},
        ],
        "error": None,
        "checkout_url": None,
        "checkout_flash": None,
    }
    base.update(extra)
    return base


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def billing_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    user, redirect = consume_checkout_query(request, user, clean_path="/app/billing")
    if redirect is not None:
        return redirect
    flash = pop_checkout_flash(request)
    return render(
        request,
        "billing.html",
        **_ctx(request, user, checkout_flash=flash),
    )


@router.post("/checkout/{plan}")
def start_checkout(
    plan: str,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    url, err = crear_checkout_session(
        plan, int(user["id"]), username=user.get("username")
    )
    if url:
        return RedirectResponse(url, status_code=303)
    return render(
        request,
        "billing.html",
        status_code=400,
        **_ctx(request, user, error=err or "No se pudo crear el checkout"),
    )
