"""Salud HTMX — registro diario, historial y Google Fit."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.billing import PLAN_FREE, PLAN_PREMIUM, limites, plan_vigente, puede_google
from app.database import (
    SYSTEM_SALUD,
    TIPOS_EJERCICIO,
    ZONAS_LISTA,
    calcular_promedios,
    construir_contexto_salud,
    guardar_registro_salud,
    obtener_registro_salud,
    obtener_registros_rango,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/salud", tags=["salud"])

TABS = ("hoy", "historial", "coach")


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
    t = (request.query_params.get("tab") or request.session.get("salud_tab") or "hoy").lower()
    if t not in TABS:
        t = "hoy"
    request.session["salud_tab"] = t
    return t


def _fecha(request: Request) -> str:
    raw = request.query_params.get("fecha") or request.session.get("salud_fecha")
    if raw:
        try:
            from datetime import date as _date

            return _date.fromisoformat(str(raw)).isoformat()
        except Exception:
            pass
    return str(_hoy())


def _parse_zonas(form) -> list[str]:
    raw = form.getlist("zonas") if hasattr(form, "getlist") else form.get("zonas")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw in ZONAS_LISTA else []
    out = []
    for z in raw:
        if z in ZONAS_LISTA:
            out.append(z)
    return out


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    consejo: str | None = None,
    fit_preview: dict | None = None,
):
    tab = _tab(request)
    fecha = _fecha(request)
    request.session["salud_fecha"] = fecha
    reg = obtener_registro_salud(fecha) or {}
    if fit_preview:
        # Prefill from Fit without wiping manual energy if already saved
        for k, v in fit_preview.items():
            if v is None or k in ("error", "avisos_fit", "fuente_sueno", "sesiones_fit"):
                continue
            # map Fit keys → form keys
            mapping = {
                "calorias": "calorias_fit",
                "pasos": "pasos_fit",
                "fc_promedio": "fc_promedio_fit",
                "fc_maxima": "fc_maxima_fit",
            }
            key = mapping.get(k, k)
            if not reg.get(key) and v not in (None, ""):
                reg[key] = v
        if fit_preview.get("hizo_ejercicio"):
            reg["hizo_ejercicio"] = 1
        if fit_preview.get("sesiones_fit"):
            reg["sesiones_json"] = json.dumps(fit_preview["sesiones_fit"])

    zonas_sel = []
    try:
        zonas_sel = json.loads(reg.get("zonas_musculares") or "[]")
    except Exception:
        zonas_sel = []

    historial = obtener_registros_rango(14)
    stats = calcular_promedios(historial)
    stats7 = calcular_promedios(obtener_registros_rango(7))

    plan = plan_vigente(user)
    fit_estado = {
        "autenticado": False,
        "oauth_web": False,
        "redirect_uri": "",
        "error": "",
    }
    try:
        from app.google_fit import estado_google_fit

        fit_estado = estado_google_fit() or fit_estado
    except Exception as e:
        fit_estado["error"] = str(e)

    form = {
        "horas_sueno": reg.get("horas_sueno") or "",
        "calidad_sueno": reg.get("calidad_sueno") or 7,
        "hora_dormir": (reg.get("hora_dormir") or "22:30")[:5],
        "hora_despertar": (reg.get("hora_despertar") or "05:30")[:5],
        "energia_manana": reg.get("energia_manana") or 7,
        "energia_tarde": reg.get("energia_tarde") or 7,
        "energia_noche": reg.get("energia_noche") or 7,
        "hizo_ejercicio": bool(reg.get("hizo_ejercicio")),
        "tipo_ejercicio": reg.get("tipo_ejercicio") or "Calistenia",
        "duracion_minutos": reg.get("duracion_minutos") or 45,
        "intensidad": reg.get("intensidad") or 7,
        "notas_ejercicio": reg.get("notas_ejercicio") or "",
        "calorias_fit": reg.get("calorias_fit") or "",
        "pasos_fit": reg.get("pasos_fit") or "",
        "fc_promedio_fit": reg.get("fc_promedio_fit") or "",
        "fc_maxima_fit": reg.get("fc_maxima_fit") or "",
        "productividad_percibida": reg.get("productividad_percibida") or 7,
        "fuente_datos": reg.get("fuente_datos") or "manual",
    }

    return {
        "title": "Salud",
        "user": user,
        "meta": MODULE_TEMPLATES["salud"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "consejo": consejo,
        "modulos_nav": _nav(int(user["id"])),
        "fecha": fecha,
        "hoy": str(_hoy()),
        "form": form,
        "zonas_sel": zonas_sel,
        "zonas_lista": ZONAS_LISTA,
        "tipos_ejercicio": TIPOS_EJERCICIO,
        "historial": historial[:14],
        "stats": stats,
        "stats7": stats7,
        "ia_ok": api_key_configurada(),
        "plan": plan,
        "puede_google": puede_google(plan),
        "plan_premium": PLAN_PREMIUM,
        "fit": fit_estado,
        "fit_avisos": (fit_preview or {}).get("avisos_fit") or [],
        "fit_error": (fit_preview or {}).get("error"),
    }


def _redirect(tab: str = "hoy", fecha: str | None = None, **extra) -> RedirectResponse:
    q = [f"tab={tab}"]
    if fecha:
        q.append(f"fecha={fecha}")
    for k, v in extra.items():
        if v is not None:
            q.append(f"{k}={v}")
    return RedirectResponse(f"/app/m/salud?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def salud_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("salud", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Salud",
            user=user,
            meta=MODULE_TEMPLATES["salud"],
            clave="salud",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )

    flash = None
    error = None
    g = request.query_params.get("google")
    if g == "ok":
        flash = "Google Fit/Calendar vinculados."
    elif g == "err":
        error = request.query_params.get("msg") or "No se pudo vincular Google."
    elif g == "denied":
        error = "Google denegó el acceso."

    return render(request, "modules/salud.html", **_ctx(request, user, flash=flash, error=error))


@router.post("/guardar")
async def guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    fecha = str(form.get("fecha") or _hoy())
    request.session["salud_fecha"] = fecha
    request.session["salud_tab"] = "hoy"
    zonas = _parse_zonas(form)
    hizo = str(form.get("hizo_ejercicio") or "") in ("1", "on", "true", "True")

    def _num(name, cast=float, default=None):
        raw = form.get(name)
        if raw in (None, ""):
            return default
        try:
            return cast(str(raw).replace(",", ""))
        except Exception:
            return default

    datos = {
        "horas_sueno": _num("horas_sueno", float),
        "calidad_sueno": _num("calidad_sueno", int),
        "hora_dormir": str(form.get("hora_dormir") or ""),
        "hora_despertar": str(form.get("hora_despertar") or ""),
        "energia_manana": _num("energia_manana", int),
        "energia_tarde": _num("energia_tarde", int),
        "energia_noche": _num("energia_noche", int),
        "hizo_ejercicio": hizo,
        "tipo_ejercicio": str(form.get("tipo_ejercicio") or "") if hizo else "",
        "duracion_minutos": _num("duracion_minutos", int) if hizo else None,
        "intensidad": _num("intensidad", int) if hizo else None,
        "notas_ejercicio": str(form.get("notas_ejercicio") or ""),
        "zonas_musculares": zonas,
        "sesiones_json": [],
        "calorias_fit": _num("calorias_fit", float),
        "pasos_fit": _num("pasos_fit", int),
        "fc_promedio_fit": _num("fc_promedio_fit", int),
        "fc_maxima_fit": _num("fc_maxima_fit", int),
        "fuente_datos": str(form.get("fuente_datos") or "manual"),
        "productividad_percibida": _num("productividad_percibida", int),
    }
    ok = guardar_registro_salud(fecha, datos)
    if not ok:
        return render(
            request,
            "modules/salud.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar el registro."),
        )
    return _redirect("hoy", fecha)


@router.post("/fit/importar")
async def fit_importar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    fecha = str(form.get("fecha") or _fecha(request))
    request.session["salud_fecha"] = fecha
    request.session["salud_tab"] = "hoy"
    plan = plan_vigente(user)
    if not puede_google(plan):
        return render(
            request,
            "modules/salud.html",
            **_ctx(
                request,
                user,
                error="Google Fit requiere plan Premium o Familia.",
            ),
        )
    try:
        from datetime import date as _date

        from app.google_fit import obtener_datos_dia

        datos = obtener_datos_dia(_date.fromisoformat(fecha))
    except Exception as e:
        datos = {"error": str(e)}

    if datos.get("error"):
        return render(
            request,
            "modules/salud.html",
            **_ctx(request, user, error=f"Fit: {datos['error']}", fit_preview=datos),
        )

    # Merge Fit into saved/manual row and persist as mixto
    reg = obtener_registro_salud(fecha) or {}
    merged = {
        "horas_sueno": datos.get("horas_sueno") if datos.get("horas_sueno") is not None else reg.get("horas_sueno"),
        "calidad_sueno": datos.get("calidad_sueno") or reg.get("calidad_sueno"),
        "hora_dormir": datos.get("hora_dormir") or reg.get("hora_dormir"),
        "hora_despertar": datos.get("hora_despertar") or reg.get("hora_despertar"),
        "energia_manana": reg.get("energia_manana"),
        "energia_tarde": reg.get("energia_tarde"),
        "energia_noche": reg.get("energia_noche"),
        "hizo_ejercicio": datos.get("hizo_ejercicio") or reg.get("hizo_ejercicio"),
        "tipo_ejercicio": datos.get("tipo_ejercicio") or reg.get("tipo_ejercicio"),
        "duracion_minutos": datos.get("duracion_minutos") or reg.get("duracion_minutos"),
        "intensidad": reg.get("intensidad"),
        "notas_ejercicio": reg.get("notas_ejercicio"),
        "zonas_musculares": [],
        "sesiones_json": datos.get("sesiones_fit") or [],
        "calorias_fit": datos.get("calorias"),
        "pasos_fit": datos.get("pasos"),
        "fc_promedio_fit": datos.get("fc_promedio"),
        "fc_maxima_fit": datos.get("fc_maxima"),
        "fuente_datos": "mixto",
        "productividad_percibida": reg.get("productividad_percibida"),
    }
    try:
        z = json.loads(reg.get("zonas_musculares") or "[]")
        merged["zonas_musculares"] = z if isinstance(z, list) else []
    except Exception:
        pass
    guardar_registro_salud(fecha, merged)
    avisos = "; ".join(datos.get("avisos_fit") or [])
    flash = "Datos de Google Fit importados."
    if avisos:
        flash += f" ({avisos})"
    return render(
        request,
        "modules/salud.html",
        **_ctx(request, user, flash=flash, fit_preview=datos),
    )


@router.get("/oauth/start")
def oauth_start(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    plan = plan_vigente(user)
    if not puede_google(plan):
        return _redirect("hoy", google="err", msg="Premium%20requerido")
    from app.google_fit import crear_url_autorizacion_web

    url, err = crear_url_autorizacion_web(user_id=int(user["id"]))
    if not url:
        return _redirect("hoy", google="err", msg=(err or "oauth")[:120])
    return RedirectResponse(url, status_code=303)


@router.post("/token/paste")
async def token_paste(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    if not puede_google(plan_vigente(user)):
        return render(
            request,
            "modules/salud.html",
            **_ctx(request, user, error="Google Fit requiere Premium o Familia."),
        )
    from app.google_fit import guardar_token_desde_json

    ok, msg = guardar_token_desde_json(str(form.get("token_json") or ""))
    if ok:
        return render(request, "modules/salud.html", **_ctx(request, user, flash=msg))
    return render(request, "modules/salud.html", **_ctx(request, user, error=msg))


@router.post("/consejo")
async def consejo_ia(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["salud_tab"] = "coach"
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = "IA offline: configura GROQ_API_KEY."
        return render(request, "modules/salud.html", **ctx)
    registros = obtener_registros_rango(14)
    stats = calcular_promedios(registros)
    contexto = construir_contexto_salud(registros, stats)
    prompt = (
        "Dame un resumen breve de mi salud esta semana y 2 acciones concretas "
        f"para mejorar energía y consistencia.\n\n{contexto}"
    )
    texto = chat_simple(prompt, contexto=SYSTEM_SALUD) or "Sin respuesta de la IA."
    ctx["consejo"] = texto
    ctx["tab"] = "coach"
    return render(request, "modules/salud.html", **ctx)
