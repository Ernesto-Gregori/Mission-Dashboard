"""Planificador semanal — Google Calendar + bloques locales del dashboard."""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.asistente import guardar_week_start, obtener_week_start
from app.billing import PLAN_PREMIUM, plan_vigente, puede_google
from app.database import (
    COLORES_TIPO,
    TIPOS_EVENTO,
    eliminar_evento,
    guardar_evento,
    obtener_eventos_semana,
)
from app.db.agenda import etiquetas_semana, inicio_semana
from app.onboarding import listar_modulos_usuario
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/planificador", tags=["planificador"])


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


def _week_offset(request: Request) -> int:
    try:
        off = int(request.query_params.get("w") or request.session.get("plan_w") or 0)
    except Exception:
        off = 0
    off = max(-52, min(52, off))
    request.session["plan_w"] = off
    return off


def _origen(evento: dict) -> str:
    fuente = str(evento.get("fuente") or "").lower()
    if fuente in ("google_calendar", "google"):
        return "google"
    if fuente == "matrimonio":
        return "matrimonio"
    if evento.get("google_id") and not evento.get("id"):
        return "google"
    return "local"


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    uid = int(user["id"])
    off = _week_offset(request)
    week_start = obtener_week_start(uid)
    inicio = inicio_semana(_hoy(), week_start) + timedelta(weeks=off)
    fin = inicio + timedelta(days=6)
    labels = etiquetas_semana(week_start)
    hoy = _hoy()

    google_ok = False
    google_error = None
    try:
        from app.google_calendar import calendar_disponible

        google_ok = bool(calendar_disponible())
    except Exception as e:
        google_error = str(e)[:160]

    eventos = obtener_eventos_semana(inicio, fin)
    por_dia: dict[str, list] = {}
    for e in eventos:
        item = dict(e)
        item["origen"] = _origen(item)
        por_dia.setdefault(str(item.get("fecha") or ""), []).append(item)

    dias = []
    for i in range(7):
        dia = inicio + timedelta(days=i)
        iso = dia.isoformat()
        items = sorted(
            por_dia.get(iso) or [],
            key=lambda x: (x.get("hora_inicio") or "99:99", x.get("titulo") or ""),
        )
        dias.append(
            {
                "label": labels[i],
                "fecha": dia,
                "iso": iso,
                "es_hoy": dia == hoy,
                "eventos": items,
            }
        )

    locales = [e for e in eventos if _origen(e) == "local" and e.get("id")]
    return {
        "title": "Semana",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "offset": off,
        "week_start": week_start,
        "inicio": inicio,
        "fin": fin,
        "dias": dias,
        "hoy": str(hoy),
        "tipos_evento": TIPOS_EVENTO,
        "google_ok": google_ok,
        "google_error": google_error,
        "puede_google": puede_google(plan_vigente(user)),
        "plan_premium": PLAN_PREMIUM,
        "locales": locales[:12],
    }


def _redirect(w: int | None = None) -> RedirectResponse:
    q = f"?w={w}" if w is not None else ""
    return RedirectResponse(f"/app/planificador{q}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def planificador_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "planificador.html", **_ctx(request, user))


@router.post("/semana")
async def set_semana(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    action = str(form.get("action") or "hoy")
    off = int(request.session.get("plan_w") or 0)
    if action == "prev":
        off -= 1
    elif action == "next":
        off += 1
    else:
        off = 0
    request.session["plan_w"] = max(-52, min(52, off))
    return _redirect(off)


@router.post("/inicio")
async def set_inicio(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    guardar_week_start(str(form.get("week_start") or "lun"), user_id=int(user["id"]))
    return _redirect(_week_offset(request))


@router.post("/bloque")
async def add_bloque(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "planificador.html",
            status_code=400,
            **_ctx(request, user, error="El título del bloque es obligatorio."),
        )
    tipo = str(form.get("tipo") or "Personal")
    if tipo not in COLORES_TIPO:
        tipo = "Personal"
    guardar_evento(
        {
            "fecha": str(form.get("fecha") or _hoy()),
            "hora_inicio": str(form.get("hora_inicio") or "09:00"),
            "hora_fin": str(form.get("hora_fin") or "10:00"),
            "titulo": titulo,
            "descripcion": str(form.get("descripcion") or ""),
            "tipo": tipo,
            "color": COLORES_TIPO.get(tipo, "#58a6ff"),
            "fuente": "local",
        },
        sync_google=False,
    )
    return _redirect(_week_offset(request))


@router.post("/bloque/{evento_id}/eliminar")
def del_bloque(
    evento_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_evento(int(evento_id))
    return _redirect(_week_offset(request))
