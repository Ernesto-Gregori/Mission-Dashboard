"""Planificador — timeline día/semana/mes + sync Calendar."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.asistente import guardar_week_start, obtener_week_start
from app.billing import PLAN_PREMIUM, plan_vigente, puede_google
from app.calendar_sync import pull_range
from app.database import (
    COLORES_TIPO,
    TIPOS_EVENTO,
    actualizar_evento,
    eliminar_evento,
    guardar_evento,
    obtener_eventos_semana,
)
from app.db.agenda import etiquetas_semana, inicio_semana
from app.onboarding import listar_modulos_usuario
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/planificador", tags=["planificador"])

VISTAS = ("dia", "semana", "mes")
HOUR_START = 6
HOUR_END = 22
PX_PER_HOUR = 56


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


def _day_offset(request: Request) -> int:
    try:
        off = int(request.query_params.get("d") or request.session.get("plan_d") or 0)
    except Exception:
        off = 0
    off = max(-366, min(366, off))
    request.session["plan_d"] = off
    return off


def _month_offset(request: Request) -> int:
    try:
        off = int(request.query_params.get("m") or request.session.get("plan_m") or 0)
    except Exception:
        off = 0
    off = max(-24, min(24, off))
    request.session["plan_m"] = off
    return off


def _vista(request: Request) -> str:
    raw = str(request.query_params.get("vista") or request.session.get("plan_vista") or "semana")
    if raw not in VISTAS:
        raw = "semana"
    request.session["plan_vista"] = raw
    return raw


def _origen(evento: dict) -> str:
    fuente = str(evento.get("fuente") or "").lower()
    if fuente in ("google_calendar", "google"):
        return "google"
    if fuente == "matrimonio":
        return "matrimonio"
    if evento.get("google_id") and not evento.get("id"):
        return "google"
    return "local"


def _mins(hora: str | None) -> int | None:
    if not hora:
        return None
    parts = str(hora).split(":")
    try:
        return int(parts[0]) * 60 + int((parts[1] if len(parts) > 1 else "0")[:2])
    except Exception:
        return None


def _fmt_mins(total: int) -> str:
    total = max(0, min(23 * 60 + 45, int(total)))
    return f"{total // 60:02d}:{total % 60:02d}"


def _decorate(evento: dict) -> dict:
    item = dict(evento)
    item["origen"] = _origen(item)
    start = _mins(item.get("hora_inicio"))
    end = _mins(item.get("hora_fin"))
    item["todo_el_dia"] = start is None
    if start is None:
        item["style"] = ""
        item["draggable"] = bool(item.get("id"))
        return item
    if end is None or end <= start:
        end = start + 60
    top = ((start - HOUR_START * 60) / 60.0) * PX_PER_HOUR
    height = max(PX_PER_HOUR / 4.0, ((end - start) / 60.0) * PX_PER_HOUR)
    item["style"] = f"top:{top:.1f}px;height:{height:.1f}px"
    item["draggable"] = bool(item.get("id"))
    return item


def _month_cells(year: int, month: int, week_start: str, por_dia: dict[str, list]) -> list[dict]:
    first = date(year, month, 1)
    _, n_days = monthrange(year, month)
    last = date(year, month, n_days)
    pad = (first.weekday() + 1) % 7 if week_start == "dom" else first.weekday()
    cells = []
    for _ in range(pad):
        cells.append({"fecha": None, "iso": "", "eventos": [], "fuera": True})
    hoy = _hoy()
    cursor = first
    while cursor <= last:
        iso = cursor.isoformat()
        cells.append(
            {
                "fecha": cursor,
                "iso": iso,
                "eventos": por_dia.get(iso) or [],
                "es_hoy": cursor == hoy,
                "fuera": False,
            }
        )
        cursor += timedelta(days=1)
    while len(cells) % 7:
        cells.append({"fecha": None, "iso": "", "eventos": [], "fuera": True})
    return cells


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    uid = int(user["id"])
    vista = _vista(request)
    week_start = obtener_week_start(uid)
    labels = etiquetas_semana(week_start)
    hoy = _hoy()

    google_ok = False
    google_error = None
    try:
        from app.google_calendar import calendar_disponible

        google_ok = bool(calendar_disponible())
    except Exception as e:
        google_error = str(e)[:160]

    puede = puede_google(plan_vigente(user))
    off_w = _week_offset(request)
    off_d = _day_offset(request)
    off_m = _month_offset(request)

    if vista == "dia":
        dia = hoy + timedelta(days=off_d)
        inicio = fin = dia
        titulo_rango = dia.strftime("%A %d/%m/%Y")
    elif vista == "mes":
        mes_ref = date(hoy.year, hoy.month, 1)
        # shift months
        year = mes_ref.year
        month = mes_ref.month + off_m
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        inicio = date(year, month, 1)
        fin = date(year, month, monthrange(year, month)[1])
        titulo_rango = inicio.strftime("%B %Y")
        dia = hoy if inicio <= hoy <= fin else inicio
    else:
        inicio = inicio_semana(hoy, week_start) + timedelta(weeks=off_w)
        fin = inicio + timedelta(days=6)
        titulo_rango = f"{inicio.strftime('%d/%m')} — {fin.strftime('%d/%m/%Y')}"
        dia = hoy if inicio <= hoy <= fin else inicio

    if google_ok and puede:
        try:
            pull_range(inicio, fin, user_id=uid)
        except Exception as e:
            google_error = str(e)[:160]

    eventos = obtener_eventos_semana(inicio, fin)
    por_dia: dict[str, list] = {}
    for e in eventos:
        item = _decorate(e)
        por_dia.setdefault(str(item.get("fecha") or ""), []).append(item)

    dias = []
    span = (fin - inicio).days + 1
    for i in range(span if vista != "mes" else 0):
        d = inicio + timedelta(days=i)
        iso = d.isoformat()
        items = sorted(
            por_dia.get(iso) or [],
            key=lambda x: (x.get("hora_inicio") or "99:99", x.get("titulo") or ""),
        )
        timed = [x for x in items if not x.get("todo_el_dia")]
        allday = [x for x in items if x.get("todo_el_dia")]
        label = labels[i] if vista == "semana" and i < len(labels) else d.strftime("%a")
        dias.append(
            {
                "label": label,
                "fecha": d,
                "iso": iso,
                "es_hoy": d == hoy,
                "eventos": items,
                "timed": timed,
                "allday": allday,
            }
        )

    month_cells = _month_cells(inicio.year, inicio.month, week_start, por_dia) if vista == "mes" else []
    horas = list(range(HOUR_START, HOUR_END))
    locales = [e for e in eventos if _origen(e) == "local" and e.get("id")]
    return {
        "title": "Planificador",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "vista": vista,
        "offset": off_w,
        "week_start": week_start,
        "inicio": inicio,
        "fin": fin,
        "dia": dia,
        "dias": dias,
        "month_cells": month_cells,
        "hoy": str(hoy),
        "titulo_rango": titulo_rango,
        "tipos_evento": TIPOS_EVENTO,
        "google_ok": google_ok,
        "google_error": google_error,
        "puede_google": puede,
        "plan_premium": PLAN_PREMIUM,
        "locales": locales[:12],
        "horas": horas,
        "hour_start": HOUR_START,
        "hour_end": HOUR_END,
        "px_per_hour": PX_PER_HOUR,
        "weekday_labels": labels,
    }


def _redirect(request: Request, w: int | None = None) -> RedirectResponse:
    vista = _vista(request)
    q = [f"vista={vista}"]
    if vista == "semana":
        q.append(f"w={w if w is not None else _week_offset(request)}")
    elif vista == "dia":
        q.append(f"d={_day_offset(request)}")
    else:
        q.append(f"m={_month_offset(request)}")
    return RedirectResponse(f"/app/planificador?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def planificador_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "planificador.html", **_ctx(request, user))


@router.post("/semana")
async def set_semana(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    action = str(form.get("action") or "hoy")
    vista = _vista(request)
    if vista == "dia":
        off = int(request.session.get("plan_d") or 0)
        if action == "prev":
            off -= 1
        elif action == "next":
            off += 1
        else:
            off = 0
        request.session["plan_d"] = max(-366, min(366, off))
    elif vista == "mes":
        off = int(request.session.get("plan_m") or 0)
        if action == "prev":
            off -= 1
        elif action == "next":
            off += 1
        else:
            off = 0
        request.session["plan_m"] = max(-24, min(24, off))
    else:
        off = int(request.session.get("plan_w") or 0)
        if action == "prev":
            off -= 1
        elif action == "next":
            off += 1
        else:
            off = 0
        request.session["plan_w"] = max(-52, min(52, off))
    return _redirect(request)


@router.post("/inicio")
async def set_inicio(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    guardar_week_start(str(form.get("week_start") or "lun"), user_id=int(user["id"]))
    return _redirect(request)


@router.get("/vista/{nombre}")
def set_vista(
    nombre: str,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    if nombre not in VISTAS:
        nombre = "semana"
    request.session["plan_vista"] = nombre
    return _redirect(request)


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
    solo_local = str(form.get("solo_local") or "") in ("1", "on", "true")
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
        sync_google=not solo_local,
    )
    return _redirect(request)


@router.post("/bloque/{evento_id}/eliminar")
def del_bloque(
    evento_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_evento(int(evento_id))
    return _redirect(request)


@router.post("/mover")
async def mover_bloque(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        evento_id = int(form.get("evento_id") or 0)
    except Exception:
        evento_id = 0
    if not evento_id:
        return _redirect(request)
    fecha = str(form.get("fecha") or "")
    hora_inicio = str(form.get("hora_inicio") or "")
    hora_fin = str(form.get("hora_fin") or "")
    datos: dict = {}
    if fecha:
        datos["fecha"] = fecha
    if hora_inicio:
        datos["hora_inicio"] = hora_inicio[:5]
        start = _mins(hora_inicio)
        prev_end = _mins(hora_fin) if hora_fin else None
        if start is not None:
            dur = 60
            if prev_end is not None and prev_end > start:
                dur = prev_end - start
            datos["hora_fin"] = hora_fin[:5] if hora_fin else _fmt_mins(start + dur)
    actualizar_evento(evento_id, datos, sync_google=True)
    return _redirect(request)


@router.post("/sync")
def sync_now(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    ctx = _ctx(request, user)
    try:
        pull_range(ctx["inicio"], ctx["fin"], user_id=int(user["id"]), force=True)
        flash = "Calendar sincronizado."
    except Exception as e:
        flash = None
        return render(
            request,
            "planificador.html",
            **_ctx(request, user, error=str(e)[:160]),
        )
    return render(request, "planificador.html", **_ctx(request, user, flash=flash))
