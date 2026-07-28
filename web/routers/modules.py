from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.billing import PLAN_FREE, limites, plan_vigente, puede_google
from app.onboarding import listar_modulos_usuario, modulo_activo, usuario_onboarding_completo
from app.templates import MODULE_TEMPLATES
from web.deps import require_user, render

router = APIRouter(prefix="/app/m", tags=["modules"])

MODULE_STATUS = {k: "stub" for k in MODULE_TEMPLATES}


def _nav(user_id: int) -> list[dict]:
    rows = listar_modulos_usuario(user_id)
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    out = []
    for key, meta in MODULE_TEMPLATES.items():
        out.append({
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        })
    return out


@router.get("/{clave}", response_class=HTMLResponse)
def module_page(
    clave: str,
    request: Request,
    user: Annotated[dict, Depends(require_user)],
):
    meta = MODULE_TEMPLATES.get(clave)
    if not meta:
        return render(
            request,
            "error.html",
            title="Módulo",
            error="Módulo desconocido.",
            user=user,
            status_code=404,
        )

    uid = int(user["id"])
    onboarded = usuario_onboarding_completo(uid)
    activo = modulo_activo(clave, uid) if onboarded else False
    plan = plan_vigente(user)
    nav = _nav(uid)

    if onboarded and not activo:
        return render(
            request,
            "paywall.html",
            title=meta["nombre"],
            user=user,
            meta=meta,
            clave=clave,
            plan=plan,
            plan_free=plan == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=nav,
        )

    specific = Path(__file__).resolve().parent.parent / "templates" / "modules" / f"{clave}.html"
    template = f"modules/{clave}.html" if specific.exists() else "modules/_stub.html"

    return render(
        request,
        template,
        title=meta["nombre"],
        user=user,
        meta=meta,
        clave=clave,
        plan=plan,
        status=MODULE_STATUS.get(clave, "stub"),
        puede_google=puede_google(plan),
        onboarded=onboarded,
        modulos_nav=nav,
    )
