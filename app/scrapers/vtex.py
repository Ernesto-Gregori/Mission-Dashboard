"""
Cliente compartido para storefronts VTEX (Walmart SV, Despensa, etc.).

API pública (preferida sobre HTML):
  GET /api/catalog_system/pub/products/search?_from=0&_to=49

robots.txt permite el catálogo; Disallow solo account/login/checkout/etc.
Header `resources: 0-49/TOTAL` indica el tamaño del catálogo.
Rate-limit agresivo (429 frecuente): delays altos + backoff del HttpClient.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterator

from app.scrapers.base import (
    HttpClient,
    NormalizedProduct,
    SupermarketScraper,
    normalize_name,
)

log = logging.getLogger("scrapers.vtex")

# VTEX suele limitar ~50 ítems por request
PAGE_SIZE_DEFAULT = 50


def _price_from_product(product: dict[str, Any]) -> tuple[float | None, str | None, bool]:
    """Retorna (precio, unidad, disponible)."""
    items = product.get("items") or []
    if not items:
        return None, None, False
    item = items[0]
    unidad = item.get("measurementUnit") or None
    sellers = item.get("sellers") or []
    if not sellers:
        return None, unidad, False
    offer = sellers[0].get("commertialOffer") or {}
    available = bool(offer.get("IsAvailable", True))
    price = offer.get("Price")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None
    return price_f, unidad, available


def _categoria_from_product(product: dict[str, Any]) -> str | None:
    cats = product.get("categories") or []
    if not cats:
        return None
    # Ej: "/Abarrotes/Lácteos/Leche/" → "Leche"
    parts = [p for p in str(cats[0]).split("/") if p]
    return parts[-1] if parts else None


def parse_vtex_product(
    product: dict[str, Any],
    *,
    supermercado: str,
    base_url: str,
) -> NormalizedProduct | None:
    sku = str(product.get("productId") or "").strip()
    nombre = (product.get("productName") or "").strip()
    if not sku or not nombre:
        return None
    precio, unidad, available = _price_from_product(product)
    link = product.get("link")
    if not link:
        slug = product.get("linkText") or sku
        link = f"{base_url.rstrip('/')}/{slug}/p"
    return NormalizedProduct(
        supermercado=supermercado,
        nombre=nombre,
        nombre_normalizado=normalize_name(nombre),
        categoria=_categoria_from_product(product),
        precio=precio if available or (precio and precio > 0) else precio,
        unidad=unidad,
        sku_o_id_externo=sku,
        url_producto=link,
        meta={
            "source": "vtex_catalog_search",
            "brand": product.get("brand"),
            "categoryId": product.get("categoryId"),
            "available": available,
        },
    )


def parse_resources_total(resources_header: str | None) -> int | None:
    """'0-49/23720' → 23720"""
    if not resources_header:
        return None
    m = re.search(r"/(\d+)\s*$", resources_header.strip())
    return int(m.group(1)) if m else None


class VtexCatalogScraper(SupermarketScraper):
    """Paginación completa (o limitada) del search público VTEX."""

    key: str = "vtex"
    base_url: str = ""
    page_size: int = PAGE_SIZE_DEFAULT

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        max_pages: int | None = None,
        page_size: int | None = None,
        base_url: str | None = None,
    ):
        # Delays más altos: VTEX responde 429 con facilidad
        self.http = http or HttpClient(min_delay_s=2.0, max_delay_s=4.0, max_retries=5)
        if base_url:
            self.base_url = base_url.rstrip("/")
        env_max = os.environ.get("VTEX_MAX_PAGES", "").strip()
        if max_pages is not None:
            self.max_pages = max_pages
        elif env_max:
            self.max_pages = int(env_max)
        else:
            self.max_pages = None  # sin límite (cron diario)
        if page_size is not None:
            self.page_size = page_size

    def _search_page(self, start: int, end: int) -> tuple[list[dict], int | None]:
        url = f"{self.base_url}/api/catalog_system/pub/products/search"
        resp = self.http.get(
            url,
            params={"_from": start, "_to": end},
            accept="application/json",
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"VTEX search HTTP {resp.status_code} en {url}")
        total = parse_resources_total(
            resp.headers.get("resources") or resp.headers.get("Resources")
        )
        data = resp.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Respuesta VTEX inesperada: {type(data)}")
        return data, total

    def iter_products(self) -> Iterator[NormalizedProduct]:
        page = 0
        start = 0
        total: int | None = None
        seen: set[str] = set()
        while True:
            if self.max_pages is not None and page >= self.max_pages:
                log.info("%s: tope max_pages=%s", self.key, self.max_pages)
                break
            end = start + self.page_size - 1
            log.info("%s: fetch _from=%s _to=%s", self.key, start, end)
            try:
                rows, page_total = self._search_page(start, end)
            except Exception as e:
                log.error("%s: error página start=%s: %s", self.key, start, e)
                break
            if page_total is not None:
                total = page_total
            if not rows:
                break
            for raw in rows:
                prod = parse_vtex_product(
                    raw, supermercado=self.key, base_url=self.base_url
                )
                if not prod or prod.sku_o_id_externo in seen:
                    continue
                seen.add(prod.sku_o_id_externo)
                yield prod
            page += 1
            start = end + 1
            if total is not None:
                if start >= total:
                    break
            elif len(rows) < self.page_size:
                # sin header resources: fin si página incompleta
                break
        log.info("%s: emitidos %s productos únicos", self.key, len(seen))
