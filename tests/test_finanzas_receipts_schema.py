"""
Fase 1 — schema de gastos por foto + catálogo de precios.
Rama experimental (servidor casero); no asume merge a main.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_db(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "test.db"

    import app.database as dbmod
    import app.db.core as core

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(dbmod.usar_turso, "cache_clear"):
        dbmod.usar_turso.cache_clear()
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setattr(dbmod, "usar_turso", lambda: False)
    monkeypatch.setattr(core, "usar_turso", lambda: False)

    dbmod.init_database()
    from app.multiuser import migrate_multiuser

    migrate_multiuser()
    yield dbmod


def _crear_usuario(db, username: str = "fin_user") -> int:
    ok, msg = db.crear_usuario(username, "password1", rol="usuario")
    assert ok, msg
    row = db.ejecutar(
        "SELECT id FROM usuarios WHERE username=?", [username], fetchall=True
    )[0]
    return int(row["id"])


def test_gastos_sobres_tiene_columnas_ocr(isolated_db):
    db = isolated_db
    cols = {
        r["name"]
        for r in db.ejecutar("PRAGMA table_info(gastos_sobres)", fetchall=True) or []
    }
    for col in (
        "comercio",
        "metodo_pago",
        "origen",
        "imagen_url",
        "raw_ocr_data",
        "ocr_estado",
    ):
        assert col in cols, f"falta columna {col}"


def test_tablas_satelite_existen(isolated_db):
    db = isolated_db
    tables = {
        r["name"]
        for r in db.ejecutar(
            "SELECT name FROM sqlite_master WHERE type='table'", fetchall=True
        )
        or []
    }
    for t in (
        "receipt_items",
        "supermarket_products",
        "price_matches",
        "scrape_runs",
    ):
        assert t in tables, f"falta tabla {t}"


def test_gasto_recibo_con_items_y_match(isolated_db, monkeypatch):
    """Flujo mínimo: gasto origen=recibo → items → producto catálogo → match."""
    db = isolated_db
    uid = _crear_usuario(db)
    monkeypatch.setattr("app.tenant.uid", lambda: uid)

    from app.db.schema import (
        DEFAULT_SOBRE_SCAN,
        DEFAULT_SUBCAT_SCAN,
        GASTO_ORIGEN_RECIBO,
        OCR_ESTADO_CONFIRMADO,
    )
    from app.database import agregar_gasto_sobre
    from app.db import finanzas_receipts as fr

    gid = agregar_gasto_sobre(
        "2026-09-01",
        DEFAULT_SOBRE_SCAN,
        DEFAULT_SUBCAT_SCAN,
        "Súper Selectos",
        12.5,
        comercio="Súper Selectos",
        metodo_pago="tarjeta",
        origen=GASTO_ORIGEN_RECIBO,
        imagen_url="data/uploads/receipts/1/demo.jpg",
        raw_ocr_data='{"tipo":"recibo"}',
        ocr_estado=OCR_ESTADO_CONFIRMADO,
    )
    assert gid

    gasto = db.ejecutar(
        "SELECT * FROM gastos_sobres WHERE id=? AND user_id=?",
        [gid, uid],
        fetchall=True,
    )[0]
    assert gasto["origen"] == GASTO_ORIGEN_RECIBO
    assert gasto["comercio"] == "Súper Selectos"
    assert gasto["sobre"] == DEFAULT_SOBRE_SCAN
    assert gasto["subcategoria"] == DEFAULT_SUBCAT_SCAN

    item_id = fr.agregar_receipt_item(
        gasto_id=gid,
        nombre_original="LECHE DESLAC 1L ALPINA",
        nombre_normalizado="leche deslactosada 1l alpina",
        cantidad=1,
        precio_unitario=2.5,
        precio_total=2.5,
        orden=0,
    )
    assert item_id

    prod_id = fr.upsert_supermarket_product(
        supermercado="super_selectos",
        nombre="Leche Deslactosada Alpina 1 Litro",
        nombre_normalizado="leche deslactosada alpina 1 litro",
        categoria="Lacteos",
        precio=2.35,
        unidad="L",
        sku_o_id_externo="SS-LECHE-001",
        url_producto="https://www.superselectos.com/products/demo",
    )
    assert prod_id

    match_id = fr.guardar_price_match(
        receipt_item_id=item_id,
        supermarket_product_id=prod_id,
        score=0.85,
        metodo="fuzzy",
        es_mejor_precio=True,
    )
    assert match_id

    items = fr.listar_receipt_items(gid)
    assert len(items) == 1
    matches = fr.listar_price_matches(item_id)
    assert len(matches) == 1
    assert matches[0]["score"] == pytest.approx(0.85)


def test_upsert_producto_no_duplica_sku(isolated_db):
    from app.db import finanzas_receipts as fr

    a = fr.upsert_supermarket_product(
        supermercado="super_selectos",
        nombre="Arroz",
        nombre_normalizado="arroz",
        categoria="Granos",
        precio=1.0,
        unidad="kg",
        sku_o_id_externo="ARROZ-1",
        url_producto=None,
    )
    b = fr.upsert_supermarket_product(
        supermercado="super_selectos",
        nombre="Arroz Blanco",
        nombre_normalizado="arroz blanco",
        categoria="Granos",
        precio=1.2,
        unidad="kg",
        sku_o_id_externo="ARROZ-1",
        url_producto=None,
    )
    assert a == b
    rows = isolated_db.ejecutar(
        "SELECT nombre, precio FROM supermarket_products WHERE sku_o_id_externo=?",
        ["ARROZ-1"],
        fetchall=True,
    )
    assert len(rows) == 1
    assert rows[0]["nombre"] == "Arroz Blanco"
    assert float(rows[0]["precio"]) == pytest.approx(1.2)


def test_scrape_run_se_registra(isolated_db):
    from app.db import finanzas_receipts as fr

    run_id = fr.iniciar_scrape_run("super_selectos")
    fr.finalizar_scrape_run(
        run_id,
        status="ok",
        products_upserted=3,
        products_unchanged=10,
        error_message=None,
        meta={"categorias": [1, 2]},
    )
    rows = isolated_db.ejecutar(
        "SELECT * FROM scrape_runs WHERE id=?", [run_id], fetchall=True
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["products_upserted"] == 3
