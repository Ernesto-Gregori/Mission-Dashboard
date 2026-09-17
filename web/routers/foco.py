"""Foco del Día — Calendar sincronizado + tareas/hábitos locales."""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import PLAN_PREMIUM, plan_vigente, puede_google
from app.calendar_sync import items_foco, pull_range
from app.onboarding import listar_modulos_usuario
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/foco", tags=["foco"])


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


def _fecha(request: Request):
    raw = request.query_params.get("fecha") or request.session.get("foco_fecha")
    hoy = _hoy()
    if raw:
        try:
            from datetime import date as _date

            dia = _date.fromisoformat(str(raw)[:10])
        except Exception:
            dia = hoy
    else:
        dia = hoy
    request.session["foco_fecha"] = dia.isoformat()
    return dia


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    uid = int(user["id"])
    dia = _fecha(request)
    google_ok = False
    try:
        from app.google_calendar import calendar_disponible

        google_ok = bool(calendar_disponible())
    except Exception:
        google_ok = False
    if google_ok and puede_google(plan_vigente(user)):
        try:
            pull_range(dia, dia, user_id=uid)
        except Exception:
            pass
    items = items_foco(dia.isoformat(), user_id=uid)
    en_cal = [i for i in items if i.get("google_id") or i.get("origen") == "google"]
    solo_dash = [i for i in items if i not in en_cal]
    return {
        "title": "Foco del Día",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "fecha": dia,
        "hoy": _hoy(),
        "items": items,
        "en_cal": en_cal,
        "solo_dash": solo_dash,
        "google_ok": google_ok,
        "puede_google": puede_google(plan_vigente(user)),
        "plan_premium": PLAN_PREMIUM,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def foco_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "foco.html", **_ctx(request, user))


@router.post("/dia")
async def set_dia(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    action = str(form.get("action") or "hoy")
    actual = _fecha(request)
    if action == "prev":
        actual = actual - timedelta(days=1)
    elif action == "next":
        actual = actual + timedelta(days=1)
    else:
        actual = _hoy()
    request.session["foco_fecha"] = actual.isoformat()
    return RedirectResponse(f"/app/foco?fecha={actual.isoformat()}", status_code=303)


@router.post("/sync")
def sync_now(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    dia = _fecha(request)
    try:
        pull_range(dia, dia, user_id=int(user["id"]), force=True)
        flash = "Calendar sincronizado."
        error = None
    except Exception as e:
        flash = None
        error = str(e)[:160]
    return render(request, "foco.html", **_ctx(request, user, flash=flash, error=error))
