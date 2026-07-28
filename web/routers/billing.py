from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import (
    PLAN_FAMILIA,
    PLAN_PREMIUM,
    crear_checkout_session,
    limites,
    plan_vigente,
    stripe_configured,
)
from app.onboarding import listar_modulos_usuario
from app.templates import MODULE_TEMPLATES
from web.checkout_flash import consume_checkout_query, pop_checkout_flash
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/billing", tags=["billing"])


def _nav(user_id: int) -> list[dict]:
    rows = listar_modulos_usuario(user_id)
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    return [
        {
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        }
        for key, meta in MODULE_TEMPLATES.items()
    ]


def _ctx(request: Request, user: dict, **extra):
    plan = plan_vigente(user)
    base = {
        "title": "Plan y cobros",
        "user": user,
        "plan": plan,
        "plan_label": limites(plan)["nombre"],
        "stripe_ok": stripe_configured(),
        "planes": [
            {"clave": PLAN_PREMIUM, **limites(PLAN_PREMIUM)},
            {"clave": PLAN_FAMILIA, **limites(PLAN_FAMILIA)},
        ],
        "error": None,
        "checkout_url": None,
        "checkout_flash": None,
        "modulos_nav": _nav(int(user["id"])),
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
