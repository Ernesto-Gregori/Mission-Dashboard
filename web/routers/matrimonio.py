"""Matrimonio HTMX — citas, notas y hábitos de conexión."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import (
    AMBITOS,
    CATEGORIAS_NOTA,
    COLORES_ESTADO,
    EMOJIS_NOTA,
    EMOJIS_TIPO,
    ESTADOS_CITA,
    INICIADO_POR,
    TIPOS_CITA,
    TIPOS_CONEXION,
    actualizar_cita,
    actualizar_nota,
    eliminar_cita,
    eliminar_nota,
    guardar_cita,
    guardar_nota,
    obtener_cita,
    obtener_citas,
    obtener_habitos_recientes,
    obtener_nota,
    obtener_notas,
    registrar_habito,
    verificar_alerta_20_30,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/matrimonio", tags=["matrimonio"])

TABS = ("citas", "nueva", "notas", "habitos")


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


def _tab(request: Request) -> str:
    t = (request.query_params.get("tab") or request.session.get("mat_tab") or "citas").lower()
    if t not in TABS:
        t = "citas"
    request.session["mat_tab"] = t
    return t


def _enrich_citas(citas: list) -> list:
    out = []
    for c in citas:
        item = dict(c)
        tipo = item.get("tipo_cita") or "Otra"
        item["emoji"] = EMOJIS_TIPO.get(tipo, "💑")
        item["color"] = COLORES_ESTADO.get(item.get("estado_planificacion") or "", "#8b949e")
        out.append(item)
    return out


def _enrich_notas(notas: list) -> list:
    out = []
    for n in notas:
        item = dict(n)
        cat = item.get("categoria") or "Otro"
        item["emoji"] = EMOJIS_NOTA.get(cat, "📝")
        out.append(item)
    return out


def _tipos_flat() -> list[str]:
    seen: list[str] = []
    for ambito in AMBITOS:
        for t in TIPOS_CITA.get(ambito, []):
            if t not in seen:
                seen.append(t)
    return seen


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    cita_edit: dict | None = None,
    nota_edit: dict | None = None,
):
    from datetime import timedelta

    tab = _tab(request)
    hoy = _hoy()
    alerta, proxima = verificar_alerta_20_30(hoy)

    filtro_estado = request.query_params.get("estado") or ""
    filtro_ambito = request.query_params.get("ambito") or ""
    filtro_cat = request.query_params.get("cat") or ""

    citas = _enrich_citas(
        obtener_citas(
            fecha_desde=(hoy - timedelta(days=60)).isoformat(),
            estado=filtro_estado or None,
            ambito=filtro_ambito or None,
        )
    )
    notas = _enrich_notas(
        obtener_notas(categoria=filtro_cat or None)
    )
    habitos = obtener_habitos_recientes(14)

    edit_id = request.query_params.get("edit")
    if edit_id and cita_edit is None and tab in ("citas", "nueva"):
        try:
            cita_edit = obtener_cita(int(edit_id))
        except Exception:
            cita_edit = None
    if edit_id and nota_edit is None and tab == "notas":
        try:
            nota_edit = obtener_nota(int(edit_id))
        except Exception:
            nota_edit = None

    return {
        "title": "Matrimonio",
        "user": user,
        "meta": MODULE_TEMPLATES["matrimonio"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "modulos_nav": _nav(int(user["id"])),
        "hoy": str(hoy),
        "alerta": alerta,
        "proxima": proxima,
        "citas": citas,
        "notas": notas,
        "habitos": habitos,
        "ambitos": AMBITOS,
        "tipos_cita": TIPOS_CITA,
        "tipos_flat": _tipos_flat(),
        "estados_cita": ESTADOS_CITA,
        "categorias_nota": CATEGORIAS_NOTA,
        "tipos_conexion": TIPOS_CONEXION,
        "iniciado_por": INICIADO_POR,
        "filtro_estado": filtro_estado,
        "filtro_ambito": filtro_ambito,
        "filtro_cat": filtro_cat,
        "cita_edit": cita_edit,
        "nota_edit": nota_edit,
        "emojis_tipo": EMOJIS_TIPO,
        "colores_estado": COLORES_ESTADO,
    }


def _redirect(tab: str = "citas", **extra) -> RedirectResponse:
    q = [f"tab={tab}"]
    for k, v in extra.items():
        if v is not None and v != "":
            q.append(f"{k}={v}")
    return RedirectResponse(f"/app/m/matrimonio?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def matrimonio_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("matrimonio", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Matrimonio",
            user=user,
            meta=MODULE_TEMPLATES["matrimonio"],
            clave="matrimonio",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/matrimonio.html", **_ctx(request, user))


@router.post("/cita")
async def create_cita(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/matrimonio.html",
            status_code=400,
            **_ctx(request, user, error="El título es obligatorio."),
        )
    ambito = str(form.get("ambito") or "Matrimonio")
    tipo = str(form.get("tipo_cita") or "Otra")
    try:
        presupuesto = float(form.get("presupuesto") or 0)
    except Exception:
        presupuesto = 0.0
    guardar_cita(
        fecha=str(form.get("fecha") or _hoy()),
        hora=str(form.get("hora") or "") or None,
        tipo=tipo,
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        lugar=str(form.get("lugar") or ""),
        presupuesto=presupuesto,
        ambito=ambito,
        preparacion=str(form.get("preparacion") or ""),
    )
    return _redirect("citas")


@router.post("/cita/{cita_id}/actualizar")
async def update_cita(
    cita_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/matrimonio.html",
            status_code=400,
            **_ctx(request, user, error="El título es obligatorio."),
        )
    try:
        presupuesto = float(form.get("presupuesto") or 0)
    except Exception:
        presupuesto = 0.0
    actualizar_cita(
        cita_id=cita_id,
        fecha=str(form.get("fecha") or _hoy()),
        hora=str(form.get("hora") or "") or None,
        tipo=str(form.get("tipo_cita") or "Otra"),
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        lugar=str(form.get("lugar") or ""),
        presupuesto=presupuesto,
        estado=str(form.get("estado") or "Planeando"),
        ambito=str(form.get("ambito") or "Matrimonio"),
        preparacion=str(form.get("preparacion") or ""),
    )
    return _redirect("citas")


@router.post("/cita/{cita_id}/eliminar")
async def delete_cita(
    cita_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_cita(cita_id)
    return _redirect("citas")


@router.post("/nota")
async def create_nota(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    contenido = str(form.get("contenido") or "").strip()
    if not contenido:
        return render(
            request,
            "modules/matrimonio.html",
            status_code=400,
            **_ctx(request, user, error="El contenido de la nota es obligatorio."),
        )
    try:
        urgencia = int(form.get("urgencia") or 1)
    except Exception:
        urgencia = 1
    urgencia = max(1, min(5, urgencia))
    guardar_nota(
        categoria=str(form.get("categoria") or "Otro"),
        contenido=contenido,
        contexto=str(form.get("contexto") or ""),
        fecha_mencion=str(form.get("fecha_mencion") or _hoy()),
        urgencia=urgencia,
    )
    return _redirect("notas")


@router.post("/nota/{nota_id}/actualizar")
async def update_nota(
    nota_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    contenido = str(form.get("contenido") or "").strip()
    if not contenido:
        return render(
            request,
            "modules/matrimonio.html",
            status_code=400,
            **_ctx(request, user, error="El contenido de la nota es obligatorio."),
        )
    try:
        urgencia = int(form.get("urgencia") or 1)
    except Exception:
        urgencia = 1
    urgencia = max(1, min(5, urgencia))
    actualizar_nota(
        nota_id=nota_id,
        categoria=str(form.get("categoria") or "Otro"),
        contenido=contenido,
        contexto=str(form.get("contexto") or ""),
        urgencia=urgencia,
    )
    return _redirect("notas")


@router.post("/nota/{nota_id}/eliminar")
async def delete_nota(
    nota_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_nota(nota_id)
    return _redirect("notas")


@router.post("/habito")
async def save_habito(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        minutos = int(form.get("minutos") or 0)
    except Exception:
        minutos = 0
    try:
        satisfaccion = int(form.get("satisfaccion") or 3)
    except Exception:
        satisfaccion = 3
    satisfaccion = max(1, min(5, satisfaccion))
    modo = 1 if form.get("modo_pareja") else 0
    registrar_habito(
        fecha=str(form.get("fecha") or _hoy()),
        minutos=max(0, minutos),
        tipo_conexion=str(form.get("tipo_conexion") or "Conversacion"),
        iniciado_por=str(form.get("iniciado_por") or "Ambos"),
        satisfaccion=satisfaccion,
        notas=str(form.get("notas") or ""),
        modo_pareja=modo,
    )
    return _redirect("habitos")
