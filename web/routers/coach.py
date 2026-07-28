"""Coach HTMX — onboarding y reconfiguración de módulos."""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import (
    PLAN_FREE,
    PLAN_PREMIUM,
    limites,
    modulos_max,
    plan_vigente,
    puede_reconfigurar_coach,
    resumen_plan_ui,
    stripe_configured,
)
from app.onboarding import (
    aplicar_habitos_sugeridos,
    aplicar_modulos,
    listar_modulos_usuario,
    marcar_admins_existentes_como_onboarded,
    marcar_onboarding_completo,
    modulos_activos,
    sugerir_con_ia,
    usuario_onboarding_completo,
)
from app.templates import MODULE_TEMPLATES
from web.deps import require_user, render

router = APIRouter(prefix="/app/coach", tags=["coach"])

AREA_OPTIONS = [
    "espiritual",
    "finanzas",
    "estudio",
    "programacion",
    "lectura",
    "salud",
    "ejercicio",
    "pareja",
    "matrimonio",
    "proyectos",
    "ideas",
    "enfoque",
]


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


def _clamp_mods(mods: list[str], plan: str) -> list[str]:
    tope = modulos_max(plan)
    if tope is None or len(mods) <= int(tope):
        return mods
    if "agenda" in mods:
        resto = [m for m in mods if m != "agenda"]
        return ["agenda"] + resto[: max(0, int(tope) - 1)]
    return mods[: int(tope)]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def coach_home(request: Request, user: Annotated[dict, Depends(require_user)]):
    marcar_admins_existentes_como_onboarded()
    uid = int(user["id"])
    plan = plan_vigente(user)
    done = usuario_onboarding_completo(uid)
    force = request.query_params.get("reconfig") == "1"

    # Ya onboarded y no pidió reconfig → resumen
    if done and not force and not request.session.get("coach_reconfig"):
        activos = sorted(modulos_activos(uid))
        bloqueados = [k for k in MODULE_TEMPLATES if k not in activos]
        return render(
            request,
            "coach/status.html",
            title="Coach",
            user=user,
            plan=plan,
            plan_label=limites(plan)["nombre"],
            plan_resumen=resumen_plan_ui(user),
            activos=[{"clave": k, **MODULE_TEMPLATES[k]} for k in activos],
            bloqueados=[{"clave": k, **MODULE_TEMPLATES[k]} for k in bloqueados[:8]],
            puede_reconfig=puede_reconfigurar_coach(plan),
            stripe_ok=stripe_configured(),
            modulos_nav=_nav(uid),
            tope=modulos_max(plan),
        )

    # Reconfig Free bloqueado
    if done and (force or request.session.get("coach_reconfig")):
        if not puede_reconfigurar_coach(plan):
            request.session.pop("coach_reconfig", None)
            return render(
                request,
                "coach/status.html",
                title="Coach",
                user=user,
                plan=plan,
                plan_label=limites(plan)["nombre"],
                plan_resumen=resumen_plan_ui(user),
                activos=[
                    {"clave": k, **MODULE_TEMPLATES[k]}
                    for k in sorted(modulos_activos(uid))
                ],
                bloqueados=[],
                puede_reconfig=False,
                stripe_ok=stripe_configured(),
                modulos_nav=_nav(uid),
                tope=modulos_max(plan),
                error="Plan Free: el Coach IA de setup es una sola vez. Upgrade a Premium para reconfigurar.",
            )
        request.session["coach_reconfig"] = True

    # Si hay sugerencia en sesión → paso 2
    sug = request.session.get("coach_sugerencia")
    if sug:
        return _render_sugerencia(request, user, sug, plan)

    tope = modulos_max(plan)
    return render(
        request,
        "coach/perfil.html",
        title="Coach — cuéntame de ti",
        user=user,
        plan=plan,
        plan_label=limites(plan)["nombre"],
        plan_resumen=resumen_plan_ui(user),
        areas=AREA_OPTIONS,
        tope=tope,
        error=None,
        modulos_nav=_nav(uid) if done else [],
        hide_nav=not done,
    )


@router.post("/perfil", response_class=HTMLResponse)
async def coach_perfil_submit(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
):
    plan = plan_vigente(user)
    uid = int(user["id"])
    done = usuario_onboarding_completo(uid)
    if done and not puede_reconfigurar_coach(plan) and not request.session.get("coach_reconfig"):
        return RedirectResponse("/app/coach", status_code=303)

    form = await request.form()
    areas = [str(a) for a in form.getlist("areas")]
    perfil = {
        "nombre": str(form.get("nombre") or user.get("username") or "").strip(),
        "situacion": str(form.get("situacion") or "").strip(),
        "objetivos": str(form.get("objetivos") or "").strip(),
        "areas": areas,
        "tiempo": str(form.get("tiempo") or "15-20 min"),
        "notas": str(form.get("notas") or "").strip(),
    }
    sug = sugerir_con_ia(perfil)
    sug["modulos"] = _clamp_mods(list(sug.get("modulos") or ["agenda"]), plan)
    # Session cookie JSON: asegurar tipos simples
    request.session["coach_perfil"] = perfil
    request.session["coach_sugerencia"] = {
        "resumen": sug.get("resumen") or "",
        "modulos": list(sug.get("modulos") or []),
        "razones": {str(k): str(v) for k, v in (sug.get("razones") or {}).items()},
        "habitos": [
            {
                "clave": str(h.get("clave") or ""),
                "label": str(h.get("label") or ""),
                "emoji": str(h.get("emoji") or "⭐"),
                "hora": str(h.get("hora") or "—"),
            }
            for h in (sug.get("habitos") or [])[:6]
            if isinstance(h, dict)
        ],
        "fuente": str(sug.get("fuente") or "fallback"),
    }
    return RedirectResponse("/app/coach", status_code=303)


def _render_sugerencia(request: Request, user: dict, sug: dict, plan: str):
    uid = int(user["id"])
    tope = modulos_max(plan)
    mods_ui = []
    selected = set(sug.get("modulos") or [])
    razones = sug.get("razones") or {}
    for key, meta in MODULE_TEMPLATES.items():
        mods_ui.append({
            **meta,
            "clave": key,
            "checked": key in selected,
            "razon": razones.get(key) or meta["descripcion"],
        })
    return render(
        request,
        "coach/sugerencia.html",
        title="Coach — tu sistema",
        user=user,
        plan=plan,
        plan_label=limites(plan)["nombre"],
        plan_resumen=resumen_plan_ui(user),
        sug=sug,
        mods_ui=mods_ui,
        tope=tope,
        error=None,
        modulos_nav=_nav(uid) if usuario_onboarding_completo(uid) else [],
        hide_nav=not usuario_onboarding_completo(uid),
        premium=PLAN_PREMIUM,
        free=PLAN_FREE,
        stripe_ok=stripe_configured(),
    )


@router.post("/atras")
def coach_atras(request: Request, user: Annotated[dict, Depends(require_user)]):
    request.session.pop("coach_sugerencia", None)
    return RedirectResponse("/app/coach", status_code=303)


@router.post("/activar", response_class=HTMLResponse)
async def coach_activar(request: Request, user: Annotated[dict, Depends(require_user)]):
    plan = plan_vigente(user)
    uid = int(user["id"])
    form = await request.form()
    seleccion = [str(v) for v in form.getlist("modulos") if str(v) in MODULE_TEMPLATES]
    sug = request.session.get("coach_sugerencia") or {}
    razones = sug.get("razones") or {}

    if not seleccion:
        sug = sug or {
            "resumen": "",
            "modulos": [],
            "habitos": [],
            "razones": {},
            "fuente": "fallback",
        }
        mods_ui = [
            {
                **meta,
                "clave": key,
                "checked": False,
                "razon": meta["descripcion"],
            }
            for key, meta in MODULE_TEMPLATES.items()
        ]
        return render(
            request,
            "coach/sugerencia.html",
            title="Coach — tu sistema",
            user=user,
            plan=plan,
            plan_label=limites(plan)["nombre"],
            plan_resumen=resumen_plan_ui(user),
            sug=sug,
            mods_ui=mods_ui,
            tope=modulos_max(plan),
            error="Elige al menos un módulo.",
            modulos_nav=[],
            hide_nav=True,
            premium=PLAN_PREMIUM,
            free=PLAN_FREE,
            stripe_ok=stripe_configured(),
            status_code=400,
        )

    tope = modulos_max(plan)
    if tope and len(seleccion) > int(tope):
        sug = sug or {
            "resumen": "",
            "modulos": seleccion,
            "habitos": [],
            "razones": {},
            "fuente": "manual",
        }
        mods_ui = [
            {
                **meta,
                "clave": key,
                "checked": key in seleccion,
                "razon": (sug.get("razones") or {}).get(key) or meta["descripcion"],
            }
            for key, meta in MODULE_TEMPLATES.items()
        ]
        return render(
            request,
            "coach/sugerencia.html",
            title="Coach — tu sistema",
            user=user,
            plan=plan,
            plan_label=limites(plan)["nombre"],
            plan_resumen=resumen_plan_ui(user),
            sug=sug,
            mods_ui=mods_ui,
            tope=tope,
            error=(
                f"Tu plan permite máximo {tope} módulos. "
                f"Desmarca {len(seleccion) - int(tope)} o pasa a Premium."
            ),
            modulos_nav=[],
            hide_nav=True,
            premium=PLAN_PREMIUM,
            free=PLAN_FREE,
            stripe_ok=stripe_configured(),
            status_code=400,
        )

    aplicar_modulos(seleccion, user_id=uid, razones=razones)
    aplicar_habitos_sugeridos(sug.get("habitos") or [], user_id=uid)
    marcar_onboarding_completo(uid, True)

    # Limpiar estado coach
    request.session.pop("coach_sugerencia", None)
    request.session.pop("coach_perfil", None)
    request.session.pop("coach_reconfig", None)

    # Upsell Free: módulos no elegidos
    resto = [k for k in MODULE_TEMPLATES if k not in seleccion]
    request.session["coach_just_finished"] = {
        "seleccion": seleccion,
        "resto": resto[:4] if plan == PLAN_FREE else [],
    }
    return RedirectResponse("/app?onboarded=1", status_code=303)


@router.post("/reconfigurar")
def coach_reconfigurar(request: Request, user: Annotated[dict, Depends(require_user)]):
    plan = plan_vigente(user)
    if not puede_reconfigurar_coach(plan):
        return RedirectResponse("/app/coach?reconfig=1", status_code=303)
    request.session["coach_reconfig"] = True
    request.session.pop("coach_sugerencia", None)
    request.session.pop("coach_perfil", None)
    return RedirectResponse("/app/coach", status_code=303)
