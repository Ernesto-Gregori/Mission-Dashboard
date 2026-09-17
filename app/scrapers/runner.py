"""Orquestación de scrapers + registro en scrape_runs."""
from __future__ import annotations

import logging
from typing import Callable

from app.db import finanzas_receipts as fr
from app.db.schema import (
    SUPERMERCADO_DESPENSA,
    SUPERMERCADO_SELECTOS,
    SUPERMERCADO_WALMART,
)
from app.scrapers.base import ScrapeResult, SupermarketScraper, persist_products
from app.scrapers.despensa_don_juan import DespensaDonJuanScraper
from app.scrapers.super_selectos import SuperSelectosScraper
from app.scrapers.walmart_sv import WalmartSvScraper

log = logging.getLogger("scrapers.runner")

SCRAPERS: dict[str, Callable[[], SupermarketScraper]] = {
    SUPERMERCADO_SELECTOS: SuperSelectosScraper,
    SUPERMERCADO_WALMART: WalmartSvScraper,
    SUPERMERCADO_DESPENSA: DespensaDonJuanScraper,
}


def run_scraper(key: str) -> ScrapeResult:
    if key not in SCRAPERS:
        raise KeyError(f"Scraper no registrado: {key}. Disponibles: {list(SCRAPERS)}")
    run_id = fr.iniciar_scrape_run(key)
    scraper = SCRAPERS[key]()
    try:
        result = scraper.scrape()
        persist_products(result)
        fr.finalizar_scrape_run(
            run_id,
            status="ok",
            products_upserted=result.upserted,
            products_unchanged=result.unchanged,
            meta={
                "count": len(result.products),
                **(result.meta or {}),
            },
        )
        log.info(
            "Scrape %s OK: %s productos, upserted=%s unchanged=%s",
            key,
            len(result.products),
            result.upserted,
            result.unchanged,
        )
        return result
    except Exception as e:
        log.exception("Scrape %s falló", key)
        fr.finalizar_scrape_run(
            run_id,
            status="error",
            error_message=str(e)[:500],
        )
        raise


def run_all_registered() -> dict[str, ScrapeResult]:
    out: dict[str, ScrapeResult] = {}
    for key in SCRAPERS:
        out[key] = run_scraper(key)
    return out
