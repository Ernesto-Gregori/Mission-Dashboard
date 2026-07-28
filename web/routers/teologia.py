"""Teología HTMX — devocional diario y pedidos de oración."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, sugerir_lectura_devocional
from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import (
    CATEGORIAS_PEDIDO,
    DIAS_ORACION_LABELS,
    ESTADOS_PEDIDO,
    URGENCIA_LABELS,
    VERSIONES_BIBLIA,
    actualizar_estado_pedido,
    agregar_pedido,
    calcular_racha_devocional,
    editar_pedido,
    eliminar_pedido,
    guardar_devocional,
    obtener_devocional,
    obtener_devocionales_recientes,
    obtener_pedidos,
    parse_dias_oracion,
    pedidos_para_hoy,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/teologia", tags=["teologia"])

TABS = ("hoy", "historial", "oracion", "metodo")


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
    t = (request.query_params.get("tab") or request.session.get("teo_tab") or "hoy").lower()
    if t not in TABS:
        t = "hoy"
    request.session["teo_tab"] = t
    return t


def _fecha(request: Request) -> str:
    raw = request.query_params.get("fecha") or request.session.get("teo_fecha")
    if raw:
        try:
            from datetime import date as _date

            return _date.fromisoformat(str(raw)).isoformat()
        except Exception:
            pass
    return str(_hoy())


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    sugerencia: str | None = None,
):
    tab = _tab(request)
    fecha = _fecha(request)
    request.session["teo_fecha"] = fecha
    dev = obtener_devocional(fecha) or {}
    historial = obtener_devocionales_recientes(14)
    pedidos = obtener_pedidos()
    for p in pedidos:
        dias = parse_dias_oracion(p)
        p["dias_list"] = dias
        p["dias_txt"] = (
            " · ".join(DIAS_ORACION_LABELS[d - 1] for d in dias if 1 <= d <= 7)
            if dias
            else "Todos los días"
        )
        p["urgencia_label"] = URGENCIA_LABELS.get(int(p.get("urgencia") or 1), "")

    filtro = request.query_params.get("estado") or ""
    pedidos_filtrados = (
        [p for p in pedidos if p.get("estado") == filtro] if filtro else pedidos
    )
    hoy_pedidos = pedidos_para_hoy([p for p in pedidos if p.get("estado") == "Activo"])

    form = {
        "pasaje_referencia": dev.get("pasaje_referencia") or "",
        "version_biblia": dev.get("version_biblia") or "NVI",
        "pasaje_texto": dev.get("pasaje_texto") or "",
        "observacion": dev.get("observacion") or "",
        "interpretacion": dev.get("interpretacion") or "",
        "aplicacion": dev.get("aplicacion") or "",
        "conexion_instituto": dev.get("conexion_instituto") or "",
        "conexion_situacion": dev.get("conexion_situacion") or "",
        "oracion_escrita": dev.get("oracion_escrita") or "",
        "duracion_minutos": dev.get("duracion_minutos") or 30,
    }

    return {
        "title": "Teología",
        "user": user,
        "meta": MODULE_TEMPLATES["teologia"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "sugerencia": sugerencia or request.session.pop("teo_sugerencia", None),
        "modulos_nav": _nav(int(user["id"])),
        "fecha": fecha,
        "hoy": str(_hoy()),
        "dev_existe": bool(dev),
        "form": form,
        "versiones": VERSIONES_BIBLIA,
        "historial": historial,
        "racha": calcular_racha_devocional(),
        "pedidos": pedidos_filtrados,
        "filtro_estado": filtro,
        "estados_pedido": ESTADOS_PEDIDO,
        "categorias": CATEGORIAS_PEDIDO,
        "dias_oracion": list(enumerate(DIAS_ORACION_LABELS, start=1)),
        "urgencia_labels": URGENCIA_LABELS,
        "hoy_pedidos": hoy_pedidos,
        "ia_ok": api_key_configurada(),
    }


def _redirect(tab: str = "hoy", fecha: str | None = None, **extra) -> RedirectResponse:
    q = [f"tab={tab}"]
    if fecha:
        q.append(f"fecha={fecha}")
    for k, v in extra.items():
        if v is not None and v != "":
            q.append(f"{k}={v}")
    return RedirectResponse(f"/app/m/teologia?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def teologia_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("teologia", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Teología",
            user=user,
            meta=MODULE_TEMPLATES["teologia"],
            clave="teologia",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/teologia.html", **_ctx(request, user))


@router.post("/devocional")
async def save_devocional(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    fecha = str(form.get("fecha") or _hoy())
    request.session["teo_fecha"] = fecha
    request.session["teo_tab"] = "hoy"
    pasaje = str(form.get("pasaje_referencia") or "").strip()
    if not pasaje:
        return render(
            request,
            "modules/teologia.html",
            status_code=400,
            **_ctx(request, user, error="La referencia del pasaje es obligatoria."),
        )
    try:
        duracion = int(form.get("duracion_minutos") or 30)
    except Exception:
        duracion = 30
    ok = guardar_devocional(
        fecha,
        pasaje,
        str(form.get("pasaje_texto") or ""),
        str(form.get("observacion") or ""),
        str(form.get("interpretacion") or ""),
        str(form.get("aplicacion") or ""),
        str(form.get("conexion_instituto") or ""),
        str(form.get("conexion_situacion") or ""),
        str(form.get("oracion_escrita") or ""),
        duracion,
        str(form.get("version_biblia") or "NVI"),
    )
    if not ok:
        return render(
            request,
            "modules/teologia.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar el devocional."),
        )
    return _redirect("hoy", fecha)


@router.post("/sugerir")
async def sugerir(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    request.session["teo_tab"] = "hoy"
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = "IA offline: configura GROQ_API_KEY."
        return render(request, "modules/teologia.html", **ctx)
    tema = str(form.get("tema") or "ánimo y fe").strip()
    texto = sugerir_lectura_devocional(tema) or "Sin sugerencia."
    request.session["teo_sugerencia"] = texto
    ctx["sugerencia"] = texto
    return render(request, "modules/teologia.html", **ctx)


@router.post("/pedido")
async def create_pedido(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    request.session["teo_tab"] = "oracion"
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/teologia.html",
            status_code=400,
            **_ctx(request, user, error="El título del pedido es obligatorio."),
        )
    dias_raw = form.getlist("dias") if hasattr(form, "getlist") else []
    dias = []
    for d in dias_raw:
        try:
            n = int(d)
            if 1 <= n <= 7:
                dias.append(n)
        except Exception:
            pass
    try:
        urgencia = int(form.get("urgencia") or 3)
    except Exception:
        urgencia = 3
    rid = agregar_pedido(
        titulo,
        str(form.get("descripcion") or ""),
        str(form.get("categoria") or "Personal"),
        urgencia,
        dias,
    )
    if rid is None:
        return render(
            request,
            "modules/teologia.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo crear el pedido."),
        )
    return _redirect("oracion")


@router.post("/pedido/{pedido_id}/estado")
async def pedido_estado(
    pedido_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    request.session["teo_tab"] = "oracion"
    estado = str(form.get("estado") or "Activo")
    nota = str(form.get("nota_respuesta") or "")
    actualizar_estado_pedido(int(pedido_id), estado, nota)
    return _redirect("oracion")


@router.post("/pedido/{pedido_id}/editar")
async def pedido_editar(
    pedido_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    request.session["teo_tab"] = "oracion"
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return _redirect("oracion")
    dias_raw = form.getlist("dias") if hasattr(form, "getlist") else []
    dias = []
    for d in dias_raw:
        try:
            n = int(d)
            if 1 <= n <= 7:
                dias.append(n)
        except Exception:
            pass
    try:
        urgencia = int(form.get("urgencia") or 3)
    except Exception:
        urgencia = 3
    editar_pedido(
        int(pedido_id),
        titulo,
        str(form.get("descripcion") or ""),
        str(form.get("categoria") or "Personal"),
        urgencia,
        dias,
    )
    return _redirect("oracion")


@router.post("/pedido/{pedido_id}/eliminar")
def pedido_eliminar(
    pedido_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_pedido(int(pedido_id))
    return _redirect("oracion")
