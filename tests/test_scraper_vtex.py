"""Tests scrapers VTEX (Walmart SV / Despensa) — parse + paginación mock."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.scrapers.base import HttpClient, ScrapeResult, persist_products
from app.scrapers.despensa_don_juan import DespensaDonJuanScraper
from app.scrapers.vtex import parse_resources_total, parse_vtex_product
from app.scrapers.walmart_sv import WalmartSvScraper


SAMPLE_PRODUCT = {
    "productId": "4054688",
    "productName": "Tortilla Bimbo Harina Trigo Rapidita Clásicas 12 Uds - 312 g",
    "brand": "BIMBO",
    "categories": ["/Panadería y tortillería/Tortillería/Tortillas de Harina/"],
    "categoryId": 285,
    "link": "https://www.walmart.com.sv/tortil-bimbo/p",
    "linkText": "tortil-bimbo",
    "items": [
        {
            "measurementUnit": "un",
            "sellers": [
                {
                    "commertialOffer": {
                        "Price": 2.15,
                        "ListPrice": 2.15,
                        "IsAvailable": True,
                        "AvailableQuantity": 10,
                    }
                }
            ],
        }
    ],
}


@pytest.fixture()
def isolated_db(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "test.db"
    import app.database as dbmod
    import app.db.core as core

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    monkeypatch.setattr(core, "DB_PATH", db_path)
    for fn in (dbmod.usar_turso, core.usar_turso, core._get_turso_config):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setattr(dbmod, "usar_turso", lambda: False)
    monkeypatch.setattr(core, "usar_turso", lambda: False)
    dbmod.init_database()
    from app.multiuser import migrate_multiuser

    migrate_multiuser()
    yield dbmod


def test_parse_resources_total():
    assert parse_resources_total("0-49/23720") == 23720
    assert parse_resources_total("0-0/13651") == 13651
    assert parse_resources_total(None) is None


def test_parse_vtex_product_precio_y_categoria():
    p = parse_vtex_product(
        SAMPLE_PRODUCT,
        supermercado="walmart_sv",
        base_url="https://www.walmart.com.sv",
    )
    assert p is not None
    assert p.sku_o_id_externo == "4054688"
    assert p.precio == pytest.approx(2.15)
    assert p.unidad == "un"
    assert p.categoria == "Tortillas de Harina"
    assert "tortil" in (p.url_producto or "")


def test_walmart_scraper_paginacion_mock():
    http = MagicMock(spec=HttpClient)
    pages = {
        (0, 1): ([SAMPLE_PRODUCT], "0-1/3"),
        (2, 3): (
            [
                {
                    **SAMPLE_PRODUCT,
                    "productId": "999",
                    "productName": "Leche Entera 1L",
                    "link": "https://www.walmart.com.sv/leche/p",
                }
            ],
            "2-3/3",
        ),
    }

    def fake_get(url, *, headers=None, params=None, accept=None):
        start = int(params["_from"])
        end = int(params["_to"])
        rows, resources = pages[(start, end)]
        resp = MagicMock()
        resp.status_code = 206
        resp.headers = {"resources": resources}
        resp.json.return_value = rows
        return resp

    http.get.side_effect = fake_get
    scraper = WalmartSvScraper(http=http, page_size=2, max_pages=10)
    products = list(scraper.iter_products())
    assert len(products) == 2
    assert {p.sku_o_id_externo for p in products} == {"4054688", "999"}
    assert products[0].supermercado == "walmart_sv"


def test_despensa_persist(isolated_db):
    p = parse_vtex_product(
        {
            **SAMPLE_PRODUCT,
            "productId": "4063335",
            "productName": "Ajo Red 3 Unidades - 125 g",
            "link": "https://www.ladespensadedonjuan.com.sv/ajo/p",
        },
        supermercado="despensa_don_juan",
        base_url="https://www.ladespensadedonjuan.com.sv",
    )
    r = persist_products(ScrapeResult(products=[p]))
    assert r.upserted == 1
    rows = isolated_db.ejecutar(
        "SELECT * FROM supermarket_products WHERE supermercado='despensa_don_juan'",
        fetchall=True,
    )
    assert len(rows) == 1
    assert float(rows[0]["precio"]) == pytest.approx(2.15)


def test_runner_registra_walmart_y_despensa():
    from app.scrapers.runner import SCRAPERS

    assert "walmart_sv" in SCRAPERS
    assert "despensa_don_juan" in SCRAPERS
    assert "super_selectos" in SCRAPERS
