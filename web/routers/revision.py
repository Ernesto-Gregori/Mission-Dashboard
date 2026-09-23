"""Revisión semanal — bitácora, métricas de la semana, rueda y briefing."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import plan_vigente
from app.coach_insights import resumen_cuota_briefing, ultimo_briefing
from app.db.agenda import (
    guardar_bitacora,
    obtener_bitacora,
    obtener_bitacoras_recientes,
    obtener_lunes_semana,
)
from app.onboarding import modulo_activo
from app.revision import CAMPOS_BITACORA, resumen_semana
from app.rueda import AREAS, geometria, obtener_scores
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/revision", tags=["revision"])

SESSION_SEMANA = "revision_semana"


def _lunes(request: Request) -> date:
    raw = request.query_params.get("semana") or request.session.get(SESSION_SEMANA)
    lunes = obtener_lunes_semana()
    if raw:
        try:
            lunes = obtener_lunes_semana(date.fromisoformat(str(raw)[:10]))
        except ValueError:
            pass
    request.session[SESSION_SEMANA] = lunes.isoformat()
    return lunes


def revision_ctx(
    request: Request,
    user: dict,
    *,
    error: str | None = None,
    rueda_scores: dict | None = None,
) -> dict:
    uid = int(user["id"])
    lunes = _lunes(request)
    bit = obtener_bitacora(lunes.isoformat()) or {}
    scores = rueda_scores if rueda_scores is not None else obtener_scores(uid)
    return {
        "title": "Revisión semanal",
        "user": user,
        "error": error,
        "flash": request.session.pop("revision_flash", None),
        "briefing_flash": request.session.pop("coach_briefing_flash", None),
        "semana": resumen_semana(lunes, uid),
        "bitacora_activa": modulo_activo("agenda", uid),
        "bit": {k: bit.get(k) or "" for k in CAMPOS_BITACORA},
        "bit_existe": bool(bit),
        "historial": obtener_bitacoras_recientes(8),
        "geo": geometria(scores),
        "areas": AREAS,
        "scores": scores,
        "briefing": ultimo_briefing(uid),
        "briefing_cuota": resumen_cuota_briefing(uid, plan_vigente(user)),
        "plan": plan_vigente(user),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def revision_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "revision.html", **revision_ctx(request, user))


@router.post("/semana")
async def set_semana(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        lunes = obtener_lunes_semana(date.fromisoformat(str(form.get("fecha") or "")))
    except ValueError:
        lunes = obtener_lunes_semana()
    return RedirectResponse(f"/app/revision?semana={lunes.isoformat()}", status_code=303)


@router.post("/bitacora")
async def save_bitacora(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("agenda", int(user["id"])):
        return RedirectResponse("/app/revision", status_code=303)
    form = await request.form()
    semana = str(form.get("semana_inicio") or _lunes(request).isoformat())
    # Conserva las columnas que ya no se piden (ingreso, semáforos, cita…) en el historial.
    datos = dict(obtener_bitacora(semana) or {})
    datos.update({k: str(form.get(k) or "") for k in CAMPOS_BITACORA})
    datos["semana_inicio"] = semana
    if not guardar_bitacora(datos):
        return render(
            request,
            "revision.html",
            status_code=400,
            **revision_ctx(request, user, error="No se pudo guardar la bitácora."),
        )
    request.session["revision_flash"] = "Bitácora guardada."
    return RedirectResponse(f"/app/revision?semana={semana}", status_code=303)
