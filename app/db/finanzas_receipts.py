"""
CRUD satélite de Finanzas: receipt_items, catálogo SV, price_matches, scrape_runs.

Rama experimental (servidor casero). El gasto canónico sigue en gastos_sobres.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.db.core import ejecutar, invalidate_data_caches


def agregar_receipt_item(
    *,
    gasto_id: int,
    nombre_original: str,
    nombre_normalizado: str = "",
    cantidad: float = 1.0,
    precio_unitario: Optional[float] = None,
    precio_total: Optional[float] = None,
    orden: int = 0,
) -> int:
    from app.tenant import uid

    rid = ejecutar(
        """
        INSERT INTO receipt_items
            (user_id, gasto_id, nombre_original, nombre_normalizado,
             cantidad, precio_unitario, precio_total, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            gasto_id,
            nombre_original,
            nombre_normalizado or None,
            cantidad,
            precio_unitario,
            precio_total,
            orden,
        ],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return rid


def listar_receipt_items(gasto_id: int) -> list[dict]:
    from app.tenant import uid

    return (
        ejecutar(
            """
            SELECT * FROM receipt_items
            WHERE gasto_id = ? AND user_id = ?
            ORDER BY orden ASC, id ASC
            """,
            [gasto_id, uid()],
            fetchall=True,
        )
        or []
    )


def upsert_supermarket_product(
    *,
    supermercado: str,
    nombre: str,
    nombre_normalizado: str = "",
    categoria: str | None = None,
    precio: float | None = None,
    unidad: str | None = None,
    sku_o_id_externo: str | None = None,
    url_producto: str | None = None,
    activo: bool = True,
) -> int:
    """Inserta o actualiza por (supermercado, sku_o_id_externo)."""
    if not sku_o_id_externo:
        # Sin SKU: insert simple (no upsert estable)
        return ejecutar(
            """
            INSERT INTO supermarket_products
                (supermercado, nombre, nombre_normalizado, categoria,
                 precio, unidad, sku_o_id_externo, url_producto, activo,
                 fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                supermercado,
                nombre,
                nombre_normalizado or None,
                categoria,
                precio,
                unidad,
                url_producto,
                1 if activo else 0,
            ],
        )

    existing = (
        ejecutar(
            """
            SELECT id FROM supermarket_products
            WHERE supermercado = ? AND sku_o_id_externo = ?
            """,
            [supermercado, sku_o_id_externo],
            fetchall=True,
        )
        or []
    )
    if existing:
        pid = int(existing[0]["id"])
        ejecutar(
            """
            UPDATE supermarket_products SET
                nombre = ?,
                nombre_normalizado = ?,
                categoria = ?,
                precio = ?,
                unidad = ?,
                url_producto = ?,
                activo = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [
                nombre,
                nombre_normalizado or None,
                categoria,
                precio,
                unidad,
                url_producto,
                1 if activo else 0,
                pid,
            ],
        )
        return pid

    return ejecutar(
        """
        INSERT INTO supermarket_products
            (supermercado, nombre, nombre_normalizado, categoria,
             precio, unidad, sku_o_id_externo, url_producto, activo,
             fecha_actualizacion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [
            supermercado,
            nombre,
            nombre_normalizado or None,
            categoria,
            precio,
            unidad,
            sku_o_id_externo,
            url_producto,
            1 if activo else 0,
        ],
    )


def guardar_price_match(
    *,
    receipt_item_id: int,
    supermarket_product_id: int,
    score: float,
    metodo: str = "fuzzy",
    es_mejor_precio: bool = False,
) -> int:
    from app.tenant import uid

    mid = ejecutar(
        """
        INSERT INTO price_matches
            (user_id, receipt_item_id, supermarket_product_id,
             score, metodo, es_mejor_precio)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            receipt_item_id,
            supermarket_product_id,
            score,
            metodo,
            1 if es_mejor_precio else 0,
        ],
    )
    return mid


def listar_price_matches(receipt_item_id: int) -> list[dict]:
    from app.tenant import uid

    return (
        ejecutar(
            """
            SELECT * FROM price_matches
            WHERE receipt_item_id = ? AND user_id = ?
            ORDER BY score DESC, id ASC
            """,
            [receipt_item_id, uid()],
            fetchall=True,
        )
        or []
    )


def iniciar_scrape_run(supermercado: str) -> int:
    return ejecutar(
        """
        INSERT INTO scrape_runs (supermercado, status)
        VALUES (?, 'running')
        """,
        [supermercado],
    )


def finalizar_scrape_run(
    run_id: int,
    *,
    status: str,
    products_upserted: int = 0,
    products_unchanged: int = 0,
    error_message: str | None = None,
    meta: Any = None,
) -> None:
    meta_json = json.dumps(meta, ensure_ascii=False) if meta is not None else None
    ejecutar(
        """
        UPDATE scrape_runs SET
            finished_at = CURRENT_TIMESTAMP,
            status = ?,
            products_upserted = ?,
            products_unchanged = ?,
            error_message = ?,
            meta_json = ?
        WHERE id = ?
        """,
        [
            status,
            products_upserted,
            products_unchanged,
            error_message,
            meta_json,
            run_id,
        ],
    )
