"""Agenda HTMX — calendario semanal, bitácora y eventos."""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.database import (
    COLORES_TIPO,
    DIAS_SEMANA,
    SEMAFOROS,
    SYSTEM_AGENDA,
    TIPOS_EVENTO,
    calcular_racha_deepwork,
    calcular_racha_devocional,
    calcular_racha_ejercicio,
    calcular_sobres,
    eliminar_evento,
    guardar_bitacora,
    guardar_evento,
    obtener_bitacora,
    obtener_bitacoras_recientes,
    obtener_deepwork_semana,
    obtener_devocionales_semana,
    obtener_eventos_personalizados,
    obtener_eventos_semana,
    obtener_ingreso,
    obtener_libros_leyendo,
    obtener_lunes_semana,
    obtener_salud_semana,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/agenda", tags=["agenda"])

TABS = ("calendario", "bitacora", "historial")


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
        off = int(request.query_params.get("w") or request.session.get("agenda_w") or 0)
    except Exception:
        off = 0
    off = max(-52, min(52, off))
    request.session["agenda_w"] = off
    return off


def _tab(request: Request) -> str:
    t = (request.query_params.get("tab") or request.session.get("agenda_tab") or "calendario").lower()
    if t not in TABS:
        t = "calendario"
    request.session["agenda_tab"] = t
    return t


def _bit_lunes(request: Request):
    raw = request.query_params.get("semana") or request.session.get("agenda_bit_semana")
    if raw:
        try:
            from datetime import date as _date

            return obtener_lunes_semana(_date.fromisoformat(str(raw)))
        except Exception:
            pass
    return obtener_lunes_semana()


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    consejo: str | None = None,
):
    off = _week_offset(request)
    tab = _tab(request)
    lunes = obtener_lunes_semana() + timedelta(weeks=off)
    domingo = lunes + timedelta(days=6)
    hoy = _hoy()

    eventos = obtener_eventos_semana(lunes, domingo)
    dw_ses = obtener_deepwork_semana(lunes, domingo)
    devos = obtener_devocionales_semana(lunes, domingo)
    salud_sem = obtener_salud_semana(lunes, domingo)

    eventos_x: dict[str, list] = {}
    for e in eventos:
        eventos_x.setdefault(e["fecha"], []).append(e)
    dw_x: dict[str, list] = {}
    for s in dw_ses:
        dw_x.setdefault(s["fecha"], []).append(s)
    devo_x = {d["fecha"]: d for d in devos}
    salud_x = {s["fecha"]: s for s in salud_sem}

    dias = []
    for i in range(7):
        dia = lunes + timedelta(days=i)
        dia_iso = dia.isoformat()
        dias.append(
            {
                "label": DIAS_SEMANA[i],
                "fecha": dia,
                "iso": dia_iso,
                "es_hoy": dia == hoy,
                "devocional": devo_x.get(dia_iso),
                "deepwork": dw_x.get(dia_iso) or [],
                "eventos": eventos_x.get(dia_iso) or [],
                "salud": salud_x.get(dia_iso),
            }
        )

    prom_energia = (
        sum((s.get("nivel_energia") or 0) for s in salud_sem) / len(salud_sem) if salud_sem else 0
    )

    # Bitácora
    lunes_bit = _bit_lunes(request)
    request.session["agenda_bit_semana"] = lunes_bit.isoformat()
    domingo_bit = lunes_bit + timedelta(days=6)
    bit = obtener_bitacora(lunes_bit.isoformat()) or {}
    mes_bit, anio_bit = lunes_bit.month, lunes_bit.year
    ingreso_auto = obtener_ingreso(mes_bit, anio_bit) or 0
    sobres_data = calcular_sobres(mes_bit, anio_bit)

    def _semaforo(sobre_key: str) -> str:
        if sobres_data.get("sin_ingreso"):
            return "verde"
        pct = sobres_data.get("sobres", {}).get(sobre_key, {}).get("pct_usado", 0)
        return "rojo" if pct >= 100 else "amarillo" if pct >= 80 else "verde"

    libros = obtener_libros_leyendo()
    libro_sugerido = ""
    if libros:
        libro_sugerido = f"{libros[0]['titulo']} — {libros[0].get('autor') or ''}".strip(" —")

    citas_mat = [e for e in obtener_eventos_semana(lunes_bit, domingo_bit) if e.get("ambito") == "Matrimonio"]
    bit_defaults = {
        "victoria_1": bit.get("victoria_1") or "",
        "victoria_2": bit.get("victoria_2") or "",
        "victoria_3": bit.get("victoria_3") or "",
        "ingreso_actual": float(bit.get("ingreso_actual") or ingreso_auto or 0),
        "sobre_supervivencia": bool(bit.get("sobre_supervivencia")),
        "aporte_transicion": float(bit.get("aporte_transicion") or 0),
        "presupuesto_cita": float(bit.get("presupuesto_cita") or 0),
        "gasto_pausado": bit.get("gasto_pausado") or "",
        "semaforo_superv": bit.get("semaforo_superv") or _semaforo("Supervivencia"),
        "semaforo_ahorros": bit.get("semaforo_ahorros") or _semaforo("Futuro_Hogar"),
        "semaforo_extras": bit.get("semaforo_extras") or _semaforo("Ministerio_Extras"),
        "actividad_cita": bit.get("actividad_cita")
        or (citas_mat[0]["titulo"] if citas_mat else ""),
        "costo_cita": float(bit.get("costo_cita") or 0),
        "libro_actual": bit.get("libro_actual") or libro_sugerido,
        "pagina_actual": int(bit.get("pagina_actual") or (libros[0].get("pagina_actual") if libros else 0) or 0),
        "frase_favorita": bit.get("frase_favorita") or "",
        "pendientes_soltar": bit.get("pendientes_soltar") or "",
        "reflexion_semana": bit.get("reflexion_semana") or "",
    }

    historial = obtener_bitacoras_recientes(12)
    hist_sel = request.query_params.get("hist") or (historial[0]["semana_inicio"] if historial else None)
    hist_bit = next((b for b in historial if b["semana_inicio"] == hist_sel), None) if hist_sel else None

    google_ok = False
    try:
        from app.google_calendar import calendar_disponible

        google_ok = bool(calendar_disponible())
    except Exception:
        google_ok = False

    return {
        "title": "Agenda",
        "user": user,
        "meta": MODULE_TEMPLATES["agenda"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "consejo": consejo,
        "modulos_nav": _nav(int(user["id"])),
        "ia_ok": api_key_configurada(),
        "google_ok": google_ok,
        "offset": off,
        "lunes": lunes,
        "domingo": domingo,
        "dias": dias,
        "dias_semana": DIAS_SEMANA,
        "resumen_cal": {
            "devos": len(devos),
            "dw": len([s for s in dw_ses if s.get("completado") == 1]),
            "eventos": len(eventos),
            "ejercicios": len([s for s in salud_sem if s.get("hizo_ejercicio")]),
            "energia": prom_energia,
        },
        "eventos_pers": obtener_eventos_personalizados()[:8],
        "tipos_evento": TIPOS_EVENTO,
        "colores_tipo": COLORES_TIPO,
        "hoy": str(hoy),
        "rachas": {
            "devocional": calcular_racha_devocional(),
            "ejercicio": calcular_racha_ejercicio(),
            "deepwork": calcular_racha_deepwork(),
        },
        "lunes_bit": lunes_bit,
        "domingo_bit": domingo_bit,
        "bit": bit_defaults,
        "bit_existe": bool(bit),
        "semaforos": SEMAFOROS,
        "opciones_sem": ["verde", "amarillo", "rojo"],
        "auto_semana": {
            "devos": len(obtener_devocionales_semana(lunes_bit, domingo_bit)),
            "dw": len(
                [s for s in obtener_deepwork_semana(lunes_bit, domingo_bit) if s.get("completado") == 1]
            ),
            "ejercicios": len(
                [s for s in obtener_salud_semana(lunes_bit, domingo_bit) if s.get("hizo_ejercicio")]
            ),
        },
        "historial": historial,
        "hist_sel": hist_sel,
        "hist_bit": hist_bit,
        "citas_hint": citas_mat[0] if citas_mat else None,
    }


def _redirect(tab: str = "calendario", w: int | None = None, semana: str | None = None) -> RedirectResponse:
    q = [f"tab={tab}"]
    if w is not None:
        q.append(f"w={w}")
    if semana:
        q.append(f"semana={semana}")
    return RedirectResponse(f"/app/m/agenda?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def agenda_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    from app.billing import PLAN_FREE, limites, plan_vigente

    if not modulo_activo("agenda", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Agenda",
            user=user,
            meta=MODULE_TEMPLATES["agenda"],
            clave="agenda",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/agenda.html", **_ctx(request, user))


@router.post("/semana")
async def set_semana(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    action = str(form.get("action") or "hoy")
    off = int(request.session.get("agenda_w") or 0)
    if action == "prev":
        off -= 1
    elif action == "next":
        off += 1
    else:
        off = 0
    request.session["agenda_w"] = max(-52, min(52, off))
    return _redirect("calendario", w=off)


@router.post("/evento")
async def add_evento(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    off = _week_offset(request)
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/agenda.html",
            status_code=400,
            **_ctx(request, user, error="El título del evento es obligatorio."),
        )
    tipo = str(form.get("tipo") or "Personal")
    if tipo not in COLORES_TIPO:
        tipo = "Personal"
    try:
        guardar_evento(
            {
                "fecha": str(form.get("fecha") or _hoy()),
                "hora_inicio": str(form.get("hora_inicio") or "09:00"),
                "hora_fin": str(form.get("hora_fin") or "10:00"),
                "titulo": titulo,
                "descripcion": str(form.get("descripcion") or ""),
                "tipo": tipo,
                "color": COLORES_TIPO.get(tipo, "#58a6ff"),
            }
        )
    except Exception:
        return render(
            request,
            "modules/agenda.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar el evento."),
        )
    return _redirect("calendario", w=off)


@router.post("/evento/{evento_id}/eliminar")
def del_evento(
    evento_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    off = _week_offset(request)
    eliminar_evento(int(evento_id))
    return _redirect("calendario", w=off)


@router.post("/bitacora")
async def save_bitacora(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    semana = str(form.get("semana_inicio") or _bit_lunes(request).isoformat())
    request.session["agenda_bit_semana"] = semana
    request.session["agenda_tab"] = "bitacora"

    def _f(name: str, default: float = 0.0) -> float:
        try:
            return float(str(form.get(name) or default).replace(",", ""))
        except Exception:
            return default

    ok = guardar_bitacora(
        {
            "semana_inicio": semana,
            "victoria_1": str(form.get("victoria_1") or ""),
            "victoria_2": str(form.get("victoria_2") or ""),
            "victoria_3": str(form.get("victoria_3") or ""),
            "ingreso_actual": _f("ingreso_actual"),
            "sobre_supervivencia": 1 if str(form.get("sobre_supervivencia") or "") in ("1", "on", "true") else 0,
            "aporte_transicion": _f("aporte_transicion"),
            "presupuesto_cita": _f("presupuesto_cita"),
            "semaforo_superv": str(form.get("semaforo_superv") or "verde"),
            "semaforo_ahorros": str(form.get("semaforo_ahorros") or "verde"),
            "semaforo_extras": str(form.get("semaforo_extras") or "verde"),
            "gasto_pausado": str(form.get("gasto_pausado") or ""),
            "actividad_cita": str(form.get("actividad_cita") or ""),
            "costo_cita": _f("costo_cita"),
            "libro_actual": str(form.get("libro_actual") or ""),
            "pagina_actual": int(_f("pagina_actual")),
            "frase_favorita": str(form.get("frase_favorita") or ""),
            "pendientes_soltar": str(form.get("pendientes_soltar") or ""),
            "reflexion_semana": str(form.get("reflexion_semana") or ""),
        }
    )
    if not ok:
        return render(
            request,
            "modules/agenda.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar la bitácora."),
        )
    return _redirect("bitacora", semana=semana)


@router.post("/bitacora/semana")
async def set_bit_semana(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    raw = str(form.get("fecha") or "")
    try:
        from datetime import date as _date

        lun = obtener_lunes_semana(_date.fromisoformat(raw))
    except Exception:
        lun = obtener_lunes_semana()
    request.session["agenda_bit_semana"] = lun.isoformat()
    return _redirect("bitacora", semana=lun.isoformat())


@router.post("/consejo")
async def consejo_ia(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["agenda_tab"] = "bitacora"
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = (
            "IA offline: configura GROQ_API_KEY en el entorno "
            "o en `.streamlit/secrets.toml`."
        )
        return render(request, "modules/agenda.html", **ctx)

    bit = ctx["bit"]
    auto = ctx["auto_semana"]
    rachas = ctx["rachas"]
    victorias = [v for v in [bit["victoria_1"], bit["victoria_2"], bit["victoria_3"]] if v]
    prompt = f"""
Analiza esta bitácora semanal:

VICTORIAS PLANIFICADAS:
{chr(10).join(f'{i+1}. {v}' for i, v in enumerate(victorias)) or 'No definidas'}

DATOS REALES:
- Devocionales: {auto['devos']}/7
- Deep Work: {auto['dw']}
- Ejercicios: {auto['ejercicios']}
- Rachas: devocional {rachas['devocional']}d, ejercicio {rachas['ejercicio']}sem, DW {rachas['deepwork']}d

SEMÁFORO: Sup {bit['semaforo_superv']} | Ahorros {bit['semaforo_ahorros']} | Extras {bit['semaforo_extras']}
REFLEXIÓN: {bit['reflexion_semana'] or 'Sin reflexión aún'}

Responde en 4 secciones breves:
🏆 VICTORIAS · 🔍 PATRÓN · ⚖️ BALANCE · 🚀 PRÓXIMA SEMANA (2 acciones + versículo)
"""
    texto = chat_simple(prompt, contexto=SYSTEM_AGENDA) or "No hubo respuesta de la IA."
    ctx["consejo"] = texto
    return render(request, "modules/agenda.html", **ctx)
