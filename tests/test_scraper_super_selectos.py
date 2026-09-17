"""Tests scraper Súper Selectos — parse HTML + persistencia (HTTP mock)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.scrapers.base import HttpClient, persist_products
from app.scrapers.super_selectos import (
    SuperSelectosScraper,
    parse_category_html,
)


SAMPLE_HTML = """
<html><body>
<div class="producto-box">
  <a href="/products?category=012&amp;productId=5630"></a>
  <div class="precios"><strong class="precio">$1.55</strong>
    <span class="antes" data-label="Antes:">$1.60</span>
    <span class="ahorro" data-label="Ahorro:">$0.05</span>
  </div>
  <h5 class="prod-nombre"><a href="/products?category=012&amp;productId=5630">Chocolate Snickers 52.7 g Barra</a></h5>
  <div class="cat"><a href="/products?category=0311127">Chocolate</a></div>
</div>
<div class="producto-box">
  <a href="/products?category=012&amp;productId=4803"></a>
  <div class="precios"><strong class="precio">$0.85</strong></div>
  <h5 class="prod-nombre"><a href="/x">Apio lb/454 g</a></h5>
  <div class="cat"><a href="/c">Verduras</a></div>
</div>
</body></html>
"""


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


def test_parse_category_html_extrae_precio_actual_no_ahorro():
    products = parse_category_html(
        SAMPLE_HTML, category_id="012", base_url="https://example.test"
    )
    assert len(products) == 2
    by_sku = {p.sku_o_id_externo: p for p in products}
    assert by_sku["5630"].nombre.startswith("Chocolate Snickers")
    assert by_sku["5630"].precio == pytest.approx(1.55)
    assert by_sku["5630"].categoria == "Chocolate"
    assert by_sku["4803"].precio == pytest.approx(0.85)
    assert "ahorro" not in (by_sku["5630"].nombre.lower())


def test_scraper_usa_fallback_si_primary_403(isolated_db):
    http = MagicMock(spec=HttpClient)

    def fake_get(url, *, headers=None, params=None, accept=None):
        resp = MagicMock()
        if "www.superselectos.com" in url:
            resp.status_code = 403
            resp.text = "blocked"
            return resp
        resp.status_code = 200
        resp.text = SAMPLE_HTML
        return resp

    http.get.side_effect = fake_get
    scraper = SuperSelectosScraper(
        http=http,
        categories=["012"],
        store_bases=[
            "https://www.superselectos.com",
            "https://selectospp.bitworks.com.sv",
        ],
    )
    products = list(scraper.iter_products())
    assert len(products) == 2
    assert products[0].supermercado == "super_selectos"


def test_persist_products_upsert_idempotente(isolated_db):
    products = parse_category_html(
        SAMPLE_HTML, category_id="012", base_url="https://example.test"
    )
    from app.scrapers.base import ScrapeResult

    r1 = persist_products(ScrapeResult(products=list(products)))
    assert r1.upserted == 2
    assert r1.unchanged == 0
    r2 = persist_products(ScrapeResult(products=list(products)))
    assert r2.unchanged == 2
    assert r2.upserted == 0
    rows = isolated_db.ejecutar(
        "SELECT * FROM supermarket_products WHERE supermercado='super_selectos'",
        fetchall=True,
    )
    assert len(rows) == 2


def test_run_scraper_registra_scrape_run(isolated_db, monkeypatch):
    from app.scrapers import run_scraper
    from app.scrapers.base import ScrapeResult
    from app.scrapers.super_selectos import parse_category_html

    products = parse_category_html(
        SAMPLE_HTML, category_id="012", base_url="https://example.test"
    )

    class Fake:
        key = "super_selectos"

        def scrape(self):
            return ScrapeResult(products=products, meta={"fake": True})

    monkeypatch.setitem(
        __import__("app.scrapers.runner", fromlist=["SCRAPERS"]).SCRAPERS,
        "super_selectos",
        Fake,
    )
    # Also patch package-level dict
    import app.scrapers as pkg
    import app.scrapers.runner as runner

    monkeypatch.setitem(runner.SCRAPERS, "super_selectos", Fake)
    monkeypatch.setitem(pkg.SCRAPERS, "super_selectos", Fake)

    result = run_scraper("super_selectos")
    assert result.upserted == 2
    runs = isolated_db.ejecutar(
        "SELECT * FROM scrape_runs WHERE supermercado='super_selectos'",
        fetchall=True,
    )
    assert len(runs) == 1
    assert runs[0]["status"] == "ok"
    assert runs[0]["products_upserted"] == 2
