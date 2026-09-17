"""Scraper Walmart El Salvador (VTEX)."""
from __future__ import annotations

import os

from app.db.schema import SUPERMERCADO_WALMART
from app.scrapers.base import HttpClient
from app.scrapers.vtex import VtexCatalogScraper

DEFAULT_BASE = "https://www.walmart.com.sv"


class WalmartSvScraper(VtexCatalogScraper):
    key = SUPERMERCADO_WALMART

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
            or os.environ.get("WALMART_SV_BASE")
            or DEFAULT_BASE
        )
        super().__init__(
            http,
            max_pages=max_pages,
            page_size=page_size,
            base_url=base,
        )
