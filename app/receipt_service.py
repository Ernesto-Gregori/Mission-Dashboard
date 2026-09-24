"""Escaneo de recibos compartido por la web y, después, por Telegram.

La web sigue decidiendo la respuesta HTTP. Acá solo está el borrador y el guardado.
"""
from __future__ import annotations

import json
from typing import Any

from app.db.schema import (
    DEFAULT_SOBRE_SCAN,
    DEFAULT_SUBCAT_SCAN,
    GASTO_ORIGEN_RECIBO,
    GASTO_ORIGEN_TRANSFERENCIA,
    OCR_ESTADO_CONFIRMADO,
    OCR_ESTADO_PENDIENTE,
)
from app.receipt_ocr import extract_from_image
from app.receipt_uploads import save_receipt_image
from app.timezone_config import hoy

MAX_SCAN_BYTES = 8 * 1024 * 1024
TELEGRAM_MAX_PHOTO_BYTES = 5 * 1024 * 1024


class ScanError(Exception):
    """OCR o imagen que no se pudo leer. El llamador no guarda un gasto."""


def armar_borrador(user_id: int, raw: bytes, filename: str | None) -> dict:
    """Guarda la foto y arma el borrador. No escribe el gasto."""
    rel = save_receipt_image(int(user_id), raw, filename)
    result = extract_from_image(raw)
    if not result.ok:
        raise ScanError(result.error or "No se pudo leer el comprobante. Reintenta con otra foto.")
    origen = GASTO_ORIGEN_TRANSFERENCIA if result.tipo == "transferencia" else GASTO_ORIGEN_RECIBO
    desc = (result.comercio or result.tipo or "Gasto escaneado").strip()
    return {
        "imagen_url": rel,
        "tipo": result.tipo,
        "origen": origen,
        "comercio": result.comercio,
        "fecha": result.fecha or str(hoy()),
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


def _num(valor, default=None):
    if valor in (None, ""):
        return default
    return float(str(valor).replace(",", ""))


def lineas_desde_form(form) -> list[dict]:
    items: list[dict] = []
    i = 0
    while True:
        nombre = form.get(f"item_nombre_{i}")
        if nombre is None:
            break
        nombre_s = str(nombre).strip()
        if nombre_s:
            try:
                cant = float(str(form.get(f"item_cantidad_{i}") or "1").replace(",", ""))
            except Exception:
                cant = 1.0
            try:
                pu_f = _num(form.get(f"item_pu_{i}"))
            except Exception:
                pu_f = None
            try:
                pt_f = _num(form.get(f"item_pt_{i}"))
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
    return items


def guardar_confirmado(draft: dict, campos: dict[str, Any]) -> tuple[int, list[dict]]:
    """Persiste el gasto confirmado y los ítems. Lanza ValueError si monto o sobre no sirven."""
    from app.database import SOBRES_CONFIG, agregar_gasto_sobre
    from app.db import finanzas_receipts as fr
    from app.db.schema import GASTO_ORIGEN_MANUAL
    from app.price_matching import (
        load_catalog,
        match_item_against_catalog,
        normalize_product_name,
        persist_matches_for_receipt_item,
    )

    fecha = str(campos.get("fecha") or draft.get("fecha") or hoy())
    sobre = str(campos.get("sobre") or DEFAULT_SOBRE_SCAN)
    sub = str(campos.get("subcategoria") or DEFAULT_SUBCAT_SCAN)
    desc = str(campos.get("descripcion") or "").strip() or "Gasto escaneado"
    comercio = str(campos.get("comercio") or "").strip() or None
    metodo = str(campos.get("metodo_pago") or "").strip() or None
    origen = str(campos.get("origen") or draft.get("origen") or GASTO_ORIGEN_RECIBO)
    if origen not in (GASTO_ORIGEN_RECIBO, GASTO_ORIGEN_TRANSFERENCIA, GASTO_ORIGEN_MANUAL):
        origen = GASTO_ORIGEN_RECIBO
    monto = float(str(campos.get("monto_total") or "0").replace(",", ""))
    if sobre not in SOBRES_CONFIG:
        raise ValueError("sobre")
    if monto <= 0:
        raise ValueError("monto")
    items = list(campos.get("items") or [])
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
    return gid, match_summaries
