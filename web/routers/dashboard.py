from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.billing import limites, plan_vigente, resumen_plan_ui
from app.onboarding import listar_modulos_usuario, usuario_onboarding_completo
from app.templates import MODULE_TEMPLATES
from web.deps import require_user, render

router = APIRouter(prefix="/app", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: Annotated[dict, Depends(require_user)]):
    rows = listar_modulos_usuario(int(user["id"]))
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    needs_coach = not usuario_onboarding_completo(int(user["id"]))
    mods = []
    for key, meta in MODULE_TEMPLATES.items():
        mods.append({
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        })
    plan = plan_vigente(user)
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
        needs_coach=needs_coach,
        activos_count=len(activos),
    )
