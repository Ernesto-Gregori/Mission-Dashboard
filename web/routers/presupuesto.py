"""Presupuesto 50/30/20 HTMX — ratios, gráfico y vencimientos."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import SOBRES_CONFIG, agregar_gasto_sobre, guardar_ingreso
from app.onboarding import listar_modulos_usuario
from app.presupuesto import (
    CATEGORIA_A_SOBRE,
    CATEGORIAS,
    TIPOS_RECURRENTES,
    agregar_recurrente,
    calendario_vencimientos,
    eliminar_recurrente,
    guardar_ratios,
    resumen_mes,
)
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/presupuesto", tags=["presupuesto"])

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


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


def _periodo(request: Request) -> tuple[int, int]:
    hoy = _hoy()
    try:
        mes = int(request.query_params.get("mes") or request.session.get("pre_mes") or hoy.month)
        anio = int(request.query_params.get("anio") or request.session.get("pre_anio") or hoy.year)
    except Exception:
        mes, anio = hoy.month, hoy.year
    mes = min(12, max(1, mes))
    anio = min(2035, max(2020, anio))
    request.session["pre_mes"] = mes
    request.session["pre_anio"] = anio
    return mes, anio


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    mes, anio = _periodo(request)
    uid = int(user["id"])
    resumen = resumen_mes(mes, anio, user_id=uid)
    cal = calendario_vencimientos(mes, anio, user_id=uid)
    return {
        "title": "Presupuesto",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "mes": mes,
        "anio": anio,
        "meses": list(enumerate(MESES, start=1)),
        "resumen": resumen,
        "ratios": resumen["ratios"],
        "cal": cal,
        "categorias": CATEGORIAS,
        "tipos_rec": TIPOS_RECURRENTES,
        "hoy": str(_hoy()),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def presupuesto_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "presupuesto.html", **_ctx(request, user))


@router.post("/periodo")
async def set_periodo(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        mes = int(form.get("mes") or _hoy().month)
        anio = int(form.get("anio") or _hoy().year)
    except Exception:
        mes, anio = _hoy().month, _hoy().year
    request.session["pre_mes"] = mes
    request.session["pre_anio"] = anio
    monto_raw = form.get("monto")
    notas = str(form.get("notas") or "")
    if monto_raw not in (None, ""):
        try:
            monto = float(str(monto_raw).replace(",", ""))
            if monto < 0:
                raise ValueError("negativo")
            ok = guardar_ingreso(mes, anio, monto, notas)
            if not ok:
                return render(
                    request,
                    "presupuesto.html",
                    status_code=400,
                    **_ctx(request, user, error="No se pudo guardar el ingreso."),
                )
        except Exception:
            return render(
                request,
                "presupuesto.html",
                status_code=400,
                **_ctx(request, user, error="Monto de ingreso inválido."),
            )
    return RedirectResponse(f"/app/presupuesto?mes={mes}&anio={anio}", status_code=303)


@router.post("/ratios")
async def set_ratios(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        n = int(form.get("pct_necesidades") or 50)
        d = int(form.get("pct_deseos") or 30)
        a = int(form.get("pct_ahorro") or 20)
    except Exception:
        return render(
            request,
            "presupuesto.html",
            status_code=400,
            **_ctx(request, user, error="Porcentajes inválidos."),
        )
    ok, msg = guardar_ratios(n, d, a, user_id=int(user["id"]))
    if not ok:
        return render(
            request,
            "presupuesto.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    mes, anio = _periodo(request)
    return RedirectResponse(f"/app/presupuesto?mes={mes}&anio={anio}", status_code=303)


@router.post("/gasto")
async def add_gasto(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    mes, anio = _periodo(request)
    try:
        fecha = str(form.get("fecha") or _hoy())
        cat = str(form.get("categoria") or "necesidades")
        if cat not in CATEGORIA_A_SOBRE:
            raise ValueError("categoria")
        sobre, sub = CATEGORIA_A_SOBRE[cat]
        desc = str(form.get("descripcion") or "").strip() or "Gasto"
        monto = float(str(form.get("monto") or "0").replace(",", ""))
        if monto <= 0:
            raise ValueError("monto")
        if sobre not in SOBRES_CONFIG:
            raise ValueError("sobre")
        agregar_gasto_sobre(fecha, sobre, sub, desc, monto)
    except Exception:
        return render(
            request,
            "presupuesto.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo agregar el gasto."),
        )
    return RedirectResponse(f"/app/presupuesto?mes={mes}&anio={anio}", status_code=303)


@router.post("/recurrente")
async def add_recurrente(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    mes, anio = _periodo(request)
    ok, msg = agregar_recurrente(
        titulo=str(form.get("titulo") or ""),
        tipo=str(form.get("tipo") or ""),
        monto=form.get("monto") or 0,
        dia=form.get("dia") or 1,
        notas=str(form.get("notas") or ""),
        user_id=int(user["id"]),
    )
    if not ok:
        return render(
            request,
            "presupuesto.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    return RedirectResponse(f"/app/presupuesto?mes={mes}&anio={anio}", status_code=303)


@router.post("/recurrente/{rec_id}/eliminar")
def del_recurrente(
    rec_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    mes, anio = _periodo(request)
    eliminar_recurrente(int(rec_id), user_id=int(user["id"]))
    return RedirectResponse(f"/app/presupuesto?mes={mes}&anio={anio}", status_code=303)
