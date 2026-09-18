from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.billing import limites, plan_vigente, resumen_plan_ui
from app.calendar_sync import items_foco
from app.coach_insights import ultimo_briefing
from app.onboarding import listar_modulos_usuario
from app.ritual import habitos_hoy, listar_habitos, obtener_ritual
from app.rueda import geometria, obtener_scores
from app.templates import MODULE_TEMPLATES
from web.checkout_flash import consume_checkout_query, pop_checkout_flash
from web.deps import require_onboarded, render
from web.nav import dashboard_hubs

router = APIRouter(prefix="/app", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    # Compat: si Stripe (o un bookmark) aterriza en /app?checkout=…
    user, redirect = consume_checkout_query(request, user, clean_path="/app/billing")
    if redirect is not None:
        return redirect

    uid = int(user["id"])
    rows = listar_modulos_usuario(uid)
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
    briefing = ultimo_briefing(uid)
    insight_destacado = None
    if briefing and briefing.get("insights"):
        insight_destacado = briefing["insights"][0]

    ritual = obtener_ritual(uid)
    hechos = habitos_hoy(uid)
    habitos = [{**h, "hecho": bool(hechos.get(h["clave"]))} for h in listar_habitos(uid)]
    scores = obtener_scores(uid)
    geo = geometria(scores)
    try:
        foco_items = items_foco(user_id=uid)[:8]
    except Exception:
        foco_items = []

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
        insight_destacado=insight_destacado,
        ritual=ritual,
        habitos=habitos,
        geo=geo,
        foco_items=foco_items,
        life_hubs=dashboard_hubs(user),
    )
