from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.billing import limites, plan_vigente, resumen_plan_ui
from app.onboarding import listar_modulos_usuario
from app.templates import MODULE_TEMPLATES
from web.checkout_flash import consume_checkout_query, pop_checkout_flash
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    # Compat: si Stripe (o un bookmark) aterriza en /app?checkout=…
    user, redirect = consume_checkout_query(request, user, clean_path="/app/billing")
    if redirect is not None:
        return redirect

    rows = listar_modulos_usuario(int(user["id"]))
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    mods = []
    for key, meta in MODULE_TEMPLATES.items():
        mods.append({
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        })
    plan = plan_vigente(user)
    just = request.session.pop("coach_just_finished", None)
    onboarded_flash = request.query_params.get("onboarded") == "1"
    checkout_flash = pop_checkout_flash(request)
    return render(
        request,
        "dashboard.html",
        title="Control de mando",
        user=user,
        plan=plan,
        plan_label=limites(plan)["nombre"],
        plan_resumen=resumen_plan_ui(user),
        modulos=mods,
        modulos_nav=mods,
        needs_coach=False,
        activos_count=len(activos),
        just_finished=just,
        onboarded_flash=onboarded_flash,
        checkout_flash=checkout_flash,
    )
