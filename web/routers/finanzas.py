"""Finanzas HTMX — ingreso, sobres y gastos."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.database import (
    SOBRES_CONFIG,
    agregar_gasto_sobre,
    calcular_sobres,
    eliminar_gasto_sobre,
    guardar_ingreso,
    obtener_gastos_sobre,
    obtener_ingreso,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/finanzas", tags=["finanzas"])

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

SUBCATEGORIAS_LABELS = {
    "Tarjeta_MSI": "💳 Tarjeta MSI",
    "Deuda_Fija": "📋 Deuda Fija",
    "Comida": "🍽️ Comida",
    "Transporte": "🚌 Transporte",
    "Servicios": "💡 Servicios",
    "Otro_Supervivencia": "📦 Otro",
    "Ahorro_Emergencia": "🛡️ Ahorro Emergencia",
    "Fondo_Renta": "🏠 Fondo Renta",
    "Otro_Ahorro": "💾 Otro Ahorro",
    "Libros_Cursos": "📚 Libros / Cursos",
    "Cita_Esposa": "💑 Cita con Esposa",
    "Ofrenda_Diezmo": "⛪ Ofrenda / Diezmo",
    "Personal": "👤 Personal",
}

SYSTEM_FINANZAS = (
    "Eres un asesor financiero cristiano. Usa el Sistema de 3 Sobres: "
    "Supervivencia 65%, Futuro/Hogar 20%, Ministerio/Extras 15%. "
    "Responde en español, práctico, máx 120 palabras."
)


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
        mes = int(request.query_params.get("mes") or request.session.get("fin_mes") or hoy.month)
        anio = int(request.query_params.get("anio") or request.session.get("fin_anio") or hoy.year)
    except Exception:
        mes, anio = hoy.month, hoy.year
    mes = min(12, max(1, mes))
    anio = min(2035, max(2020, anio))
    request.session["fin_mes"] = mes
    request.session["fin_anio"] = anio
    return mes, anio


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    mes, anio = _periodo(request)
    resumen = calcular_sobres(mes, anio)
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=80)
    for g in gastos:
        g["sub_label"] = SUBCATEGORIAS_LABELS.get(g.get("subcategoria"), g.get("subcategoria"))
    sobres_ui = []
    for key, data in (resumen.get("sobres") or {}).items():
        sobres_ui.append({
            "key": key,
            **data,
            "subs": [
                {"clave": s, "label": SUBCATEGORIAS_LABELS.get(s, s)}
                for s in data.get("subcategorias", SOBRES_CONFIG[key]["subcategorias"])
            ],
        })
    return {
        "title": "Finanzas",
        "user": user,
        "meta": MODULE_TEMPLATES["finanzas"],
        "mes": mes,
        "anio": anio,
        "meses": list(enumerate(MESES, start=1)),
        "ingreso": resumen.get("ingreso") or 0,
        "resumen": resumen,
        "sobres_ui": sobres_ui,
        "gastos": gastos,
        "hoy": str(_hoy()),
        "flash": flash,
        "error": error,
        "modulos_nav": _nav(int(user["id"])),
        "ia_ok": api_key_configurada(),
        "consejo": None,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def finanzas_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    from app.billing import PLAN_FREE, limites, plan_vigente

    if not modulo_activo("finanzas", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Finanzas",
            user=user,
            meta=MODULE_TEMPLATES["finanzas"],
            clave="finanzas",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/finanzas.html", **_ctx(request, user))


@router.post("/periodo")
async def set_periodo(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    try:
        mes = int(form.get("mes") or _hoy().month)
        anio = int(form.get("anio") or _hoy().year)
    except Exception:
        mes, anio = _hoy().month, _hoy().year
    request.session["fin_mes"] = mes
    request.session["fin_anio"] = anio
    monto_raw = form.get("monto")
    notas = str(form.get("notas") or "")
    flash = None
    error = None
    if monto_raw not in (None, ""):
        try:
            monto = float(str(monto_raw).replace(",", ""))
            if monto < 0:
                raise ValueError("negativo")
            ok = guardar_ingreso(mes, anio, monto, notas)
            flash = "Ingreso guardado." if ok else None
            error = None if ok else "No se pudo guardar el ingreso."
        except Exception:
            error = "Monto de ingreso inválido."
    return RedirectResponse(f"/app/m/finanzas?mes={mes}&anio={anio}", status_code=303)


@router.post("/gasto")
async def add_gasto(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    mes, anio = _periodo(request)
    try:
        fecha = str(form.get("fecha") or _hoy())
        sobre = str(form.get("sobre") or "")
        sub = str(form.get("subcategoria") or "")
        desc = str(form.get("descripcion") or "").strip() or "Gasto"
        monto = float(str(form.get("monto") or "0").replace(",", ""))
        es_fijo = str(form.get("es_fijo") or "") in ("1", "on", "true", "True")
        if sobre not in SOBRES_CONFIG:
            raise ValueError("sobre")
        if monto <= 0:
            raise ValueError("monto")
        agregar_gasto_sobre(fecha, sobre, sub, desc, monto, es_fijo=es_fijo)
    except Exception:
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo agregar el gasto. Revisa los campos."),
        )
    return RedirectResponse(f"/app/m/finanzas?mes={mes}&anio={anio}", status_code=303)


@router.post("/gasto/{gasto_id}/eliminar")
def del_gasto(
    gasto_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    mes, anio = _periodo(request)
    eliminar_gasto_sobre(int(gasto_id))
    return RedirectResponse(f"/app/m/finanzas?mes={mes}&anio={anio}", status_code=303)


@router.post("/consejo")
async def consejo_ia(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    mes, anio = _periodo(request)
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = (
            "Coach/IA offline: configura GROQ_API_KEY en el entorno "
            "o en `.streamlit/secrets.toml` (FastAPI no lee solo secrets de Streamlit Cloud)."
        )
        return render(request, "modules/finanzas.html", **ctx)
    resumen = ctx["resumen"]
    prompt = (
        f"Mes {mes}/{anio}. Ingreso ${resumen.get('ingreso', 0):.0f}. "
        f"Gastado ${resumen.get('total_gastado', 0):.0f}. "
        f"Disponible ${resumen.get('total_disponible', 0):.0f}. "
        "Dame un consejo breve para este mes."
    )
    texto = chat_simple(prompt, contexto=SYSTEM_FINANZAS) or "No hubo respuesta de la IA."
    ctx["consejo"] = texto
    return render(request, "modules/finanzas.html", **ctx)
