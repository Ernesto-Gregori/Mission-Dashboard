"""Finanzas HTMX — ingreso, sobres, gastos y escaneo de recibos."""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.database import (
    SOBRES_CONFIG,
    agregar_gasto_sobre,
    calcular_sobres,
    eliminar_gasto_sobre,
    guardar_ingreso,
    obtener_gastos_sobre,
)
from app.db import finanzas_receipts as fr
from app.db.schema import (
    DEFAULT_SOBRE_SCAN,
    DEFAULT_SUBCAT_SCAN,
    GASTO_ORIGEN_MANUAL,
    GASTO_ORIGEN_RECIBO,
    GASTO_ORIGEN_TRANSFERENCIA,
    OCR_ESTADO_CONFIRMADO,
    OCR_ESTADO_PENDIENTE,
    OCR_ESTADO_RECHAZADO,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.receipt_ocr import extract_from_image
from app.receipt_uploads import resolve_upload_path, save_receipt_image
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

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

SESSION_DRAFT_KEY = "finanzas_scan_draft"
MAX_SCAN_BYTES = 8 * 1024 * 1024


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
    if request.query_params.get("flash") == "escaneado" and not flash:
        flash = "Gasto escaneado guardado. Revisa el historial."
    resumen = calcular_sobres(mes, anio)
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=80)
    for g in gastos:
        g["sub_label"] = SUBCATEGORIAS_LABELS.get(g.get("subcategoria"), g.get("subcategoria"))
        g["origen_label"] = g.get("origen") or GASTO_ORIGEN_MANUAL
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
        "vision_ok": api_key_configurada(),
    }


def _confirm_ctx(request: Request, user: dict, draft: dict, *, error: str | None = None):
    mes, anio = _periodo(request)
    sobres_ui = []
    for key, data in SOBRES_CONFIG.items():
        sobres_ui.append({
            "key": key,
            "nombre": data["nombre"],
            "emoji": data["emoji"],
            "subs": [
                {"clave": s, "label": SUBCATEGORIAS_LABELS.get(s, s)}
                for s in data["subcategorias"]
            ],
        })
    img = draft.get("imagen_url") or ""
    img_name = img.rsplit("/", 1)[-1] if img else ""
    return {
        "title": "Confirmar escaneo",
        "user": user,
        "meta": MODULE_TEMPLATES["finanzas"],
        "modulos_nav": _nav(int(user["id"])),
        "mes": mes,
        "anio": anio,
        "hoy": str(_hoy()),
        "draft": draft,
        "sobres_ui": sobres_ui,
        "error": error,
        "img_name": img_name,
        "default_sobre": DEFAULT_SOBRE_SCAN,
        "default_sub": DEFAULT_SUBCAT_SCAN,
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
    if monto_raw not in (None, ""):
        try:
            monto = float(str(monto_raw).replace(",", ""))
            if monto < 0:
                raise ValueError("negativo")
            ok = guardar_ingreso(mes, anio, monto, notas)
            if not ok:
                return render(
                    request,
                    "modules/finanzas.html",
                    **_ctx(request, user, error="No se pudo guardar el ingreso."),
                )
        except Exception:
            return render(
                request,
                "modules/finanzas.html",
                **_ctx(request, user, error="Monto de ingreso inválido."),
            )
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
    ctx = _ctx(request, user)
    if not api_key_configurada():
        ctx["error"] = (
            "Coach/IA offline: configura GROQ_API_KEY en el entorno "
            "o en `.streamlit/secrets.toml` (FastAPI no lee solo secrets de Streamlit Cloud)."
        )
        return render(request, "modules/finanzas.html", **ctx)
    resumen = ctx["resumen"]
    mes, anio = ctx["mes"], ctx["anio"]
    prompt = (
        f"Mes {mes}/{anio}. Ingreso ${resumen.get('ingreso', 0):.0f}. "
        f"Gastado ${resumen.get('total_gastado', 0):.0f}. "
        f"Disponible ${resumen.get('total_disponible', 0):.0f}. "
        "Dame un consejo breve para este mes."
    )
    texto = chat_simple(prompt, contexto=SYSTEM_FINANZAS) or "No hubo respuesta de la IA."
    ctx["consejo"] = texto
    return render(request, "modules/finanzas.html", **ctx)


@router.post("/escanear", response_class=HTMLResponse)
async def escanear_recibo(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
    imagen: UploadFile = File(...),
):
    """Sube foto → OCR → pantalla de confirmación (aún no guarda el gasto)."""
    if not api_key_configurada():
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(
                request,
                user,
                error="Para escanear hace falta GROQ_API_KEY en el entorno.",
            ),
        )

    raw = await imagen.read()
    if not raw:
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(request, user, error="No se recibió ninguna imagen."),
        )
    if len(raw) > MAX_SCAN_BYTES:
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(
                request,
                user,
                error="La imagen supera 8 MB. Comprime o recorta la foto.",
            ),
        )

    try:
        rel = save_receipt_image(int(user["id"]), raw, imagen.filename)
    except Exception as e:
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(request, user, error=f"No se pudo guardar la imagen: {e}"),
        )

    result = extract_from_image(raw)
    if not result.ok:
        request.session.pop(SESSION_DRAFT_KEY, None)
        return render(
            request,
            "modules/finanzas.html",
            status_code=422,
            **_ctx(
                request,
                user,
                error=result.error
                or "No se pudo leer el comprobante. Reintenta con otra foto.",
            ),
        )

    origen = (
        GASTO_ORIGEN_TRANSFERENCIA
        if result.tipo == "transferencia"
        else GASTO_ORIGEN_RECIBO
    )
    desc = (result.comercio or result.tipo or "Gasto escaneado").strip()
    draft: dict[str, Any] = {
        "imagen_url": rel,
        "tipo": result.tipo,
        "origen": origen,
        "comercio": result.comercio,
        "fecha": result.fecha or str(_hoy()),
        "monto_total": result.monto_total,
        "metodo_pago": result.metodo_pago,
        "descripcion": desc,
        "sobre": DEFAULT_SOBRE_SCAN,
        "subcategoria": DEFAULT_SUBCAT_SCAN,
        "lineas": [
            {
                "nombre": it.nombre,
                "cantidad": it.cantidad,
                "precio_unitario": it.precio_unitario,
                "precio_total": it.precio_total,
            }
            for it in result.items
        ],
        "warnings": list(result.warnings),
        "raw_ocr_data": json.dumps(result.raw or {}, ensure_ascii=False),
        "ocr_estado": OCR_ESTADO_PENDIENTE,
    }
    request.session[SESSION_DRAFT_KEY] = draft
    return render(
        request,
        "modules/finanzas_escanear_confirm.html",
        **_confirm_ctx(request, user, draft),
    )


@router.get("/escanear/confirmar", response_class=HTMLResponse)
def escanear_confirm_get(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    draft = request.session.get(SESSION_DRAFT_KEY)
    if not draft:
        return RedirectResponse("/app/m/finanzas", status_code=303)
    return render(
        request,
        "modules/finanzas_escanear_confirm.html",
        **_confirm_ctx(request, user, draft),
    )


@router.post("/escanear/confirmar")
async def escanear_confirmar(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    draft = request.session.get(SESSION_DRAFT_KEY) or {}
    form = await request.form()
    mes, anio = _periodo(request)

    try:
        fecha = str(form.get("fecha") or draft.get("fecha") or _hoy())
        sobre = str(form.get("sobre") or DEFAULT_SOBRE_SCAN)
        sub = str(form.get("subcategoria") or DEFAULT_SUBCAT_SCAN)
        desc = str(form.get("descripcion") or "").strip() or "Gasto escaneado"
        comercio = str(form.get("comercio") or "").strip() or None
        metodo = str(form.get("metodo_pago") or "").strip() or None
        origen = str(form.get("origen") or draft.get("origen") or GASTO_ORIGEN_RECIBO)
        if origen not in (
            GASTO_ORIGEN_RECIBO,
            GASTO_ORIGEN_TRANSFERENCIA,
            GASTO_ORIGEN_MANUAL,
        ):
            origen = GASTO_ORIGEN_RECIBO
        monto = float(str(form.get("monto_total") or "0").replace(",", ""))
        if sobre not in SOBRES_CONFIG:
            raise ValueError("sobre")
        if monto <= 0:
            raise ValueError("monto")

        items: list[dict] = []
        i = 0
        while True:
            nombre = form.get(f"item_nombre_{i}")
            if nombre is None:
                break
            nombre_s = str(nombre).strip()
            if nombre_s:
                try:
                    cant = float(
                        str(form.get(f"item_cantidad_{i}") or "1").replace(",", "")
                    )
                except Exception:
                    cant = 1.0
                try:
                    pu = form.get(f"item_pu_{i}")
                    pu_f = (
                        float(str(pu).replace(",", "")) if pu not in (None, "") else None
                    )
                except Exception:
                    pu_f = None
                try:
                    pt = form.get(f"item_pt_{i}")
                    pt_f = (
                        float(str(pt).replace(",", "")) if pt not in (None, "") else None
                    )
                except Exception:
                    pt_f = None
                items.append(
                    {
                        "nombre": nombre_s,
                        "cantidad": cant,
                        "precio_unitario": pu_f,
                        "precio_total": pt_f,
                    }
                )
            i += 1
            if i > 200:
                break

        gid = agregar_gasto_sobre(
            fecha,
            sobre,
            sub,
            desc,
            monto,
            comercio=comercio,
            metodo_pago=metodo,
            origen=origen,
            imagen_url=draft.get("imagen_url"),
            raw_ocr_data=draft.get("raw_ocr_data"),
            ocr_estado=OCR_ESTADO_CONFIRMADO,
        )
        for idx, it in enumerate(items):
            fr.agregar_receipt_item(
                gasto_id=gid,
                nombre_original=it["nombre"],
                nombre_normalizado=it["nombre"].lower(),
                cantidad=float(it["cantidad"] or 1),
                precio_unitario=it.get("precio_unitario"),
                precio_total=it.get("precio_total"),
                orden=idx,
            )
    except Exception:
        return render(
            request,
            "modules/finanzas_escanear_confirm.html",
            status_code=400,
            **_confirm_ctx(
                request,
                user,
                draft or {"lineas": [], "warnings": []},
                error="No se pudo guardar. Revisa monto, sobre y fecha.",
            ),
        )

    request.session.pop(SESSION_DRAFT_KEY, None)
    return RedirectResponse(
        f"/app/m/finanzas?mes={mes}&anio={anio}&flash=escaneado",
        status_code=303,
    )


@router.post("/escanear/cancelar")
async def escanear_cancelar(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    request.session.pop(SESSION_DRAFT_KEY, None)
    _ = OCR_ESTADO_RECHAZADO
    mes, anio = _periodo(request)
    return RedirectResponse(f"/app/m/finanzas?mes={mes}&anio={anio}", status_code=303)


@router.get("/uploads/{filename}")
def servir_upload(
    filename: str,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    """Sirve una foto del usuario autenticado (anti path-traversal)."""
    rel = f"data/uploads/receipts/{int(user['id'])}/{filename}"
    path = resolve_upload_path(rel, int(user["id"]))
    if not path:
        return HTMLResponse("No encontrado", status_code=404)
    return FileResponse(path, media_type="image/jpeg")
