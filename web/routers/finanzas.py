"""Finanzas HTMX — ingreso, sobres, gastos, escaneo y precios SV."""
from __future__ import annotations

import json
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada
from app.database import (
    SOBRES_CONFIG,
    agregar_gasto_sobre,
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
    SUPERMERCADO_LABELS,
    SUPERMERCADOS,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.presupuesto import (
    PRESETS,
    SOBRES,
    SUBCATEGORIAS_LABELS,
    TIPOS_RECURRENTES,
    agregar_recurrente,
    calendario_vencimientos,
    eliminar_recurrente,
    guardar_ratios,
    resumen_mes,
)
from app.receipt_ocr import extract_from_image
from app.receipt_uploads import resolve_upload_path, save_receipt_image
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/m/finanzas", tags=["finanzas"])

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

SESSION_DRAFT_KEY = "finanzas_scan_draft"
SESSION_MATCHES_KEY = "finanzas_last_matches"
SESSION_FLASH_KEY = "finanzas_flash"
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


def _flash(request: Request, flash: str | None = None) -> str | None:
    if not flash:
        flash = request.session.pop(SESSION_FLASH_KEY, None)
    flash_q = request.query_params.get("flash") or ""
    if not flash and flash_q == "escaneado":
        flash = "Gasto escaneado guardado. Revisa el historial."
    elif not flash and flash_q == "catalogo":
        flash = "Catálogo de supermercados actualizado."
    return flash


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    mes, anio = _periodo(request)
    flash = _flash(request, flash)
    resumen = resumen_mes(mes, anio, user_id=int(user["id"]))
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=80)
    for g in gastos:
        g["sub_label"] = SUBCATEGORIAS_LABELS.get(g.get("subcategoria"), g.get("subcategoria"))
        g["origen_label"] = g.get("origen") or GASTO_ORIGEN_MANUAL
    sobres_ui = [
        {
            **data,
            "subs": [
                {"clave": s, "label": SUBCATEGORIAS_LABELS.get(s, s)}
                for s in data["subcategorias"]
            ],
        }
        for data in resumen["sobres"].values()
    ]
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
        "presets": PRESETS,
        "gastos": gastos,
        "hoy": str(_hoy()),
        "flash": flash,
        "error": error,
        "modulos_nav": _nav(int(user["id"])),
        "vision_ok": api_key_configurada(),
        "price_matches": request.session.pop(SESSION_MATCHES_KEY, None),
        "finanzas_section": "sobres",
    }


def _vencimientos_ctx(request: Request, user: dict, *, error: str | None = None):
    mes, anio = _periodo(request)
    return {
        "title": "Vencimientos",
        "user": user,
        "meta": MODULE_TEMPLATES["finanzas"],
        "mes": mes,
        "anio": anio,
        "meses": list(enumerate(MESES, start=1)),
        "error": error,
        "cal": calendario_vencimientos(mes, anio, user_id=int(user["id"])),
        "tipos_rec": TIPOS_RECURRENTES,
    }


def _paywall(request: Request, user: dict):
    from app.billing import PLAN_FREE, limites, plan_vigente

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


def _precios_ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    mes, anio = _periodo(request)
    flash = _flash(request, flash)
    q_precios = (request.query_params.get("q_precios") or "").strip()
    filtro_super = (request.query_params.get("super") or "").strip() or None
    if filtro_super and filtro_super not in SUPERMERCADOS:
        filtro_super = None
    catalogo_sv = fr.resumen_catalogo_sv()
    productos_sv = (
        fr.buscar_productos(q_precios, supermercado=filtro_super, limit=40)
        if q_precios or filtro_super
        else fr.buscar_productos("", limit=24)
    )
    for p in productos_sv:
        p["label"] = SUPERMERCADO_LABELS.get(p.get("supermercado"), p.get("supermercado"))
    return {
        "title": "Precios supermercados",
        "user": user,
        "meta": MODULE_TEMPLATES["finanzas"],
        "mes": mes,
        "anio": anio,
        "meses": list(enumerate(MESES, start=1)),
        "flash": flash,
        "error": error,
        "modulos_nav": _nav(int(user["id"])),
        "catalogo_sv": catalogo_sv,
        "productos_sv": productos_sv,
        "q_precios": q_precios,
        "filtro_super": filtro_super or "",
        "total_productos_sv": sum(int(c.get("productos") or 0) for c in catalogo_sv),
        "finanzas_section": "precios",
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
    if not modulo_activo("finanzas", int(user["id"])):
        return _paywall(request, user)
    return render(request, "modules/finanzas.html", **_ctx(request, user))


@router.get("/precios", response_class=HTMLResponse)
def finanzas_precios_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("finanzas", int(user["id"])):
        return _paywall(request, user)
    return render(request, "modules/finanzas_precios.html", **_precios_ctx(request, user))


@router.get("/vencimientos", response_class=HTMLResponse)
def finanzas_vencimientos_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("finanzas", int(user["id"])):
        return _paywall(request, user)
    return render(request, "modules/finanzas_vencimientos.html", **_vencimientos_ctx(request, user))


@router.post("/vencimientos")
async def add_vencimiento(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
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
            "modules/finanzas_vencimientos.html",
            status_code=400,
            **_vencimientos_ctx(request, user, error=msg),
        )
    return RedirectResponse("/app/m/finanzas/vencimientos", status_code=303)


@router.post("/vencimientos/{rec_id}/eliminar")
def del_vencimiento(
    rec_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_recurrente(int(rec_id), user_id=int(user["id"]))
    return RedirectResponse("/app/m/finanzas/vencimientos", status_code=303)


@router.post("/reparto")
async def set_reparto(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    preset = str(form.get("preset") or "")
    if preset in PRESETS:
        ratios = PRESETS[preset]["ratios"]
    else:
        ratios = {s: form.get(f"pct_{s}") for s in SOBRES}
    ok, msg = guardar_ratios(ratios, user_id=int(user["id"]))
    if not ok:
        return render(
            request,
            "modules/finanzas.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    mes, anio = _periodo(request)
    return RedirectResponse(f"/app/m/finanzas?mes={mes}&anio={anio}", status_code=303)


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
        from app.price_matching import (
            load_catalog,
            match_item_against_catalog,
            normalize_product_name,
            persist_matches_for_receipt_item,
        )

        catalog = load_catalog() if items else []
        match_summaries: list[dict] = []
        for idx, it in enumerate(items):
            rid = fr.agregar_receipt_item(
                gasto_id=gid,
                nombre_original=it["nombre"],
                nombre_normalizado=normalize_product_name(it["nombre"]),
                cantidad=float(it["cantidad"] or 1),
                precio_unitario=it.get("precio_unitario"),
                precio_total=it.get("precio_total"),
                orden=idx,
            )
            match = match_item_against_catalog(it["nombre"], catalog)
            persist_matches_for_receipt_item(rid, match)
            match_summaries.append(
                {
                    "nombre": it["nombre"],
                    "resumen": match.resumen_precios(),
                    "sin_coincidencia_clara": match.sin_coincidencia_clara,
                    "hits": [
                        {
                            "supermercado": h.supermercado,
                            "nombre": h.nombre,
                            "precio": h.precio,
                            "score": round(h.score, 3),
                        }
                        for h in match.hits
                    ],
                }
            )
        if match_summaries:
            request.session[SESSION_MATCHES_KEY] = match_summaries
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


def _scrape_ui_env_defaults() -> dict[str, str]:
    """Límites cortos para no colgar la petición HTTP del home server."""
    defaults: dict[str, str] = {}
    if not os.environ.get("VTEX_MAX_PAGES", "").strip():
        defaults["VTEX_MAX_PAGES"] = "2"
    if not os.environ.get("SELECTOS_CATEGORIES", "").strip():
        # Un par de categorías típicas (comida) — scrape completo vía CLI/cron.
        defaults["SELECTOS_CATEGORIES"] = "01,02"
    return defaults


@router.post("/precios/actualizar")
async def actualizar_catalogo_sv(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
    supermercado: Annotated[str, Form(...)],
):
    """Dispara scrape de una tienda y vuelve a la sección de precios."""
    from app.scrapers import SCRAPERS, run_scraper

    mes, anio = _periodo(request)
    key = (supermercado or "").strip()
    if key not in SCRAPERS:
        return render(
            request,
            "modules/finanzas_precios.html",
            **_precios_ctx(
                request,
                user,
                error=f"Supermercado desconocido: {key}",
            ),
        )

    applied = _scrape_ui_env_defaults()
    prev = {k: os.environ.get(k) for k in applied}
    try:
        for k, v in applied.items():
            os.environ[k] = v
        result = run_scraper(key)
    except Exception as e:
        return render(
            request,
            "modules/finanzas_precios.html",
            **_precios_ctx(
                request,
                user,
                error=f"No se pudo actualizar {SUPERMERCADO_LABELS.get(key, key)}: {e}",
            ),
        )
    finally:
        for k, old in prev.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old

    label = SUPERMERCADO_LABELS.get(key, key)
    request.session[SESSION_FLASH_KEY] = (
        f"{label}: {result.upserted} productos nuevos/actualizados"
        f" ({len(result.products)} leídos)."
    )
    return RedirectResponse(
        f"/app/m/finanzas/precios?mes={mes}&anio={anio}&flash=catalogo",
        status_code=303,
    )
