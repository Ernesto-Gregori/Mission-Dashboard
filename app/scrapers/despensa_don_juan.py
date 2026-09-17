"""Scraper La Despensa de Don Juan (VTEX — misma familia que Walmart SV)."""
from __future__ import annotations

import os

from app.db.schema import SUPERMERCADO_DESPENSA
from app.scrapers.base import HttpClient
from app.scrapers.vtex import VtexCatalogScraper

DEFAULT_BASE = "https://www.ladespensadedonjuan.com.sv"


class DespensaDonJuanScraper(VtexCatalogScraper):
    key = SUPERMERCADO_DESPENSA

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        max_pages: int | None = None,
        page_size: int | None = None,
        base_url: str | None = None,
    ):
        base = (
            base_url
            or os.environ.get("DESPENSA_BASE")
            or DEFAULT_BASE
        )
        super().__init__(
            http,
            max_pages=max_pages,
            page_size=page_size,
            base_url=base,
        )
