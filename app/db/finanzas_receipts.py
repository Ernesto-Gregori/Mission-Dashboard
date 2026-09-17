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


def contar_productos_activos(supermercado: str | None = None) -> int:
    if supermercado:
        rows = (
            ejecutar(
                """
                SELECT COUNT(*) AS n FROM supermarket_products
                WHERE activo = 1 AND supermercado = ?
                """,
                [supermercado],
                fetchall=True,
            )
            or []
        )
    else:
        rows = (
            ejecutar(
                """
                SELECT COUNT(*) AS n FROM supermarket_products WHERE activo = 1
                """,
                fetchall=True,
            )
            or []
        )
    return int((rows[0] if rows else {}).get("n") or 0)


def ultimo_scrape_run(supermercado: str) -> dict | None:
    rows = (
        ejecutar(
            """
            SELECT * FROM scrape_runs
            WHERE supermercado = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            [supermercado],
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def resumen_catalogo_sv() -> list[dict]:
    """Estado por tienda para la UI de Finanzas."""
    from app.db.schema import SUPERMERCADO_LABELS, SUPERMERCADOS

    out: list[dict] = []
    for key in SUPERMERCADOS:
        last = ultimo_scrape_run(key)
        out.append(
            {
                "key": key,
                "label": SUPERMERCADO_LABELS.get(key, key),
                "productos": contar_productos_activos(key),
                "ultimo_status": (last or {}).get("status"),
                "ultimo_finished_at": (last or {}).get("finished_at"),
                "ultimo_upserted": int((last or {}).get("products_upserted") or 0),
                "ultimo_error": (last or {}).get("error_message"),
            }
        )
    return out


def buscar_productos(
    q: str = "",
    *,
    supermercado: str | None = None,
    limit: int = 40,
) -> list[dict]:
    limit = max(1, min(100, int(limit)))
    q = (q or "").strip()
    params: list[Any] = []
    where = ["activo = 1"]
    if supermercado:
        where.append("supermercado = ?")
        params.append(supermercado)
    if q:
        where.append("(nombre LIKE ? OR COALESCE(nombre_normalizado,'') LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    params.append(limit)
    sql = f"""
        SELECT id, supermercado, nombre, precio, unidad, categoria,
               url_producto, fecha_actualizacion
        FROM supermarket_products
        WHERE {' AND '.join(where)}
        ORDER BY nombre ASC
        LIMIT ?
    """
    return ejecutar(sql, params, fetchall=True) or []
