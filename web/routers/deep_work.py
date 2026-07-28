"""Deep Work HTMX — bloques del día, semana y configuración."""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import (
    COLORES_DW,
    DIAS_LABELS_DW,
    DIAS_NOMBRES_DW,
    ESTADOS_SESION,
    SYSTEM_COACH_DW,
    actualizar_bloque,
    bloques_para_fecha,
    construir_resumen_semana,
    crear_bloque,
    desactivar_bloque,
    obtener_sesiones_semana,
    obtener_tipos_bloque,
    obtener_todos_bloques,
    parse_dias_bloque,
    reactivar_bloque,
    registrar_sesion,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/deep_work", tags=["deep_work"])

TABS = ("dia", "semana", "config", "coach")


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
    t = (request.query_params.get("tab") or request.session.get("dw_tab") or "dia").lower()
    if t not in TABS:
        t = "dia"
    request.session["dw_tab"] = t
    return t


def _fecha(request: Request) -> str:
    raw = request.query_params.get("fecha") or request.session.get("dw_fecha")
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
    consejo: str | None = None,
):
    from datetime import date as _date

    tab = _tab(request)
    fecha = _fecha(request)
    request.session["dw_fecha"] = fecha
    f = _date.fromisoformat(fecha)
    dia_nombre = DIAS_NOMBRES_DW[f.weekday()]

    bloques_dia = bloques_para_fecha(fecha, int(user["id"]))

    lunes = f - timedelta(days=f.weekday())
    domingo = lunes + timedelta(days=6)
    sesiones = obtener_sesiones_semana(lunes.isoformat(), domingo.isoformat())
    completados = len([s for s in sesiones if s.get("estado") == "Completado"])
    total_sem = len(sesiones)
    tasa = (completados / total_sem * 100) if total_sem else 0

    # Agrupar sesiones por fecha
    por_dia: dict[str, list] = {}
    for s in sesiones:
        por_dia.setdefault(s["fecha"], []).append(s)

    todos = obtener_todos_bloques()
    for b in todos:
        b["dias_list"] = parse_dias_bloque(b)
        b["dias_txt"] = ", ".join(
            DIAS_LABELS_DW[d - 1] for d in b["dias_list"] if 1 <= d <= 7
        )

    tipos = obtener_tipos_bloque() or ["Deep Work", "Estudio", "Código", "Otro"]
    color_labels = list(COLORES_DW.keys())

    return {
        "title": "Deep Work",
        "user": user,
        "meta": MODULE_TEMPLATES["deep_work"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "consejo": consejo,
        "modulos_nav": _nav(int(user["id"])),
        "fecha": fecha,
        "dia_nombre": dia_nombre,
        "hoy": str(_hoy()),
        "bloques_dia": bloques_dia,
        "estados": ESTADOS_SESION,
        "lunes": lunes,
        "domingo": domingo,
        "stats_semana": {
            "total": total_sem,
            "completados": completados,
            "tasa": tasa,
        },
        "sesiones_por_dia": por_dia,
        "dias_semana": [
            {
                "iso": (lunes + timedelta(days=i)).isoformat(),
                "label": DIAS_LABELS_DW[i],
                "fecha": lunes + timedelta(days=i),
                "sesiones": por_dia.get((lunes + timedelta(days=i)).isoformat(), []),
            }
            for i in range(7)
        ],
        "todos_bloques": todos,
        "tipos": tipos,
        "colores": COLORES_DW,
        "color_labels": color_labels,
        "dias_nombres": list(enumerate(DIAS_NOMBRES_DW, start=1)),
        "ia_ok": api_key_configurada(),
    }


def _redirect(tab: str = "dia", fecha: str | None = None) -> RedirectResponse:
    q = [f"tab={tab}"]
    if fecha:
        q.append(f"fecha={fecha}")
    return RedirectResponse(f"/app/m/deep_work?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def deep_work_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("deep_work", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Deep Work",
            user=user,
            meta=MODULE_TEMPLATES["deep_work"],
            clave="deep_work",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/deep_work.html", **_ctx(request, user))


@router.post("/fecha")
async def set_fecha(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    fecha = str(form.get("fecha") or _hoy())
    request.session["dw_fecha"] = fecha
    return _redirect("dia", fecha)


@router.post("/sesion")
async def save_sesion(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    fecha = str(form.get("fecha") or _fecha(request))
    try:
        bloque_id = int(form.get("bloque_id"))
    except Exception:
        return render(
            request,
            "modules/deep_work.html",
            status_code=400,
            **_ctx(request, user, error="Bloque inválido."),
        )
    estado = str(form.get("estado") or "Pendiente")
    notas = str(form.get("notas") or "")
    ok = registrar_sesion(fecha, bloque_id, estado, notas)
    if not ok:
        return render(
            request,
            "modules/deep_work.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar la sesión."),
        )
    return _redirect("dia", fecha)


@router.post("/bloque")
async def create_bloque(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    request.session["dw_tab"] = "config"
    nombre = str(form.get("nombre") or "").strip()
    if not nombre:
        return render(
            request,
            "modules/deep_work.html",
            status_code=400,
            **_ctx(request, user, error="El nombre del bloque es obligatorio."),
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
    if not dias:
        dias = [1, 2, 3, 4, 5]
    tipo = str(form.get("tipo") or "Deep Work").strip() or "Deep Work"
    color_label = str(form.get("color") or "Azul")
    color = COLORES_DW.get(color_label, COLORES_DW["Azul"])
    bid = crear_bloque(
        nombre,
        str(form.get("hora_inicio") or "06:00"),
        str(form.get("hora_fin") or "07:00"),
        dias,
        tipo,
        color,
    )
    if bid is None:
        return render(
            request,
            "modules/deep_work.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo crear el bloque."),
        )
    return _redirect("config")


@router.post("/bloque/{bloque_id}/actualizar")
async def update_bloque(
    bloque_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    request.session["dw_tab"] = "config"
    nombre = str(form.get("nombre") or "").strip()
    if not nombre:
        return _redirect("config")
    dias_raw = form.getlist("dias") if hasattr(form, "getlist") else []
    dias = []
    for d in dias_raw:
        try:
            n = int(d)
            if 1 <= n <= 7:
                dias.append(n)
        except Exception:
            pass
    if not dias:
        dias = parse_dias_bloque({"dias_semana": "[]"}) or [1, 2, 3, 4, 5]
    color_label = str(form.get("color") or "Azul")
    color = COLORES_DW.get(color_label, str(form.get("color_hex") or COLORES_DW["Azul"]))
    if color_label in COLORES_DW:
        color = COLORES_DW[color_label]
    activo = str(form.get("activo") or "1") in ("1", "on", "true", "True")
    actualizar_bloque(
        int(bloque_id),
        nombre,
        str(form.get("hora_inicio") or "06:00"),
        str(form.get("hora_fin") or "07:00"),
        dias,
        str(form.get("tipo") or "Deep Work"),
        color,
        activo,
    )
    return _redirect("config")


@router.post("/bloque/{bloque_id}/desactivar")
def deactivate_bloque(
    bloque_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    desactivar_bloque(int(bloque_id))
    return _redirect("config")


@router.post("/bloque/{bloque_id}/reactivar")
def reactivate_bloque(
    bloque_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    reactivar_bloque(int(bloque_id))
    return _redirect("config")


@router.post("/consejo")
async def consejo_ia(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["dw_tab"] = "coach"
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = "IA offline: configura GROQ_API_KEY."
        return render(request, "modules/deep_work.html", **ctx)
    resumen = construir_resumen_semana(
        obtener_sesiones_semana(ctx["lunes"].isoformat(), ctx["domingo"].isoformat())
    )
    prompt = (
        "Analiza mi semana de Deep Work y dame 2 acciones concretas "
        f"para mejorar consistencia:\n{resumen}"
    )
    texto = chat_simple(prompt, contexto=SYSTEM_COACH_DW) or "Sin respuesta de la IA."
    ctx["consejo"] = texto
    ctx["tab"] = "coach"
    return render(request, "modules/deep_work.html", **ctx)
