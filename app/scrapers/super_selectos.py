"""
Scraper Súper Selectos (El Salvador).

Hallazgos (Fase 3 inspección):
- www.superselectos.com está detrás de Cloudflare (403 desde algunos ASN).
- Precios NO vienen en ecom-products (catálogo sin precio); el storefront
  Blazor los renderiza en HTML (`strong.precio`, `h5.prod-nombre`, productId).
- API pública de catálogo: https://ecom-products.superselectos.com
  accountId=selectos (útil para nombres/SKU; sin precio).
- Fallback HTML usable: https://selectospp.bitworks.com.sv (mismo front).
- robots.txt de www no legible desde IP bloqueada; limitamos ritmo y alcance.

Estrategia v1: scrape HTML por categoría (configurable), upsert por productId.
"""
from __future__ import annotations

import logging
import os
import re
from html import unescape
from typing import Iterator
from urllib.parse import urljoin

from app.db.schema import SUPERMERCADO_SELECTOS
from app.scrapers.base import (
    HttpClient,
    NormalizedProduct,
    SupermarketScraper,
    normalize_name,
)

log = logging.getLogger("scrapers.super_selectos")

PRIMARY_BASE = "https://www.superselectos.com"
FALLBACK_BASE = "https://selectospp.bitworks.com.sv"
API_BASE = "https://ecom-products.superselectos.com"
ACCOUNT_ID = "selectos"

# Categorías iniciales (ids usados en ?category=). Ampliables por env.
DEFAULT_CATEGORIES = (
    "012",  # Frutas y verduras
    "03",  # Abarrotes (prefijo amplio en tienda)
)

_PRODUCT_BOX_SPLIT = re.compile(r'<div class="producto-box">', re.I)
_PRODUCT_ID = re.compile(r"productId=(\d+)", re.I)
_PROD_NOMBRE = re.compile(
    r'<h5 class="prod-nombre"\s*>\s*<a[^>]*>([^<]+)</a>', re.I
)
_PRECIO = re.compile(r'<strong class="precio"[^>]*>\s*\$?\s*([0-9]+(?:\.[0-9]+)?)', re.I)
_CAT_LINK = re.compile(r'<div class="cat"[^>]*>\s*<a[^>]*>([^<]+)</a>', re.I)
_SVG = re.compile(r"<svg[\s\S]*?</svg>", re.I)


def _store_bases() -> list[str]:
    primary = (os.environ.get("SELECTOS_STORE_BASE") or PRIMARY_BASE).rstrip("/")
    fallback = (os.environ.get("SELECTOS_FALLBACK_BASE") or FALLBACK_BASE).rstrip("/")
    bases = [primary]
    if fallback and fallback != primary:
        bases.append(fallback)
    return bases


def _categories() -> list[str]:
    raw = os.environ.get("SELECTOS_CATEGORIES", "")
    if raw.strip():
        return [c.strip() for c in raw.split(",") if c.strip()]
    return list(DEFAULT_CATEGORIES)


def parse_category_html(html: str, *, category_id: str, base_url: str) -> list[NormalizedProduct]:
    """Extrae productos de una página de categoría del storefront Blazor."""
    out: list[NormalizedProduct] = []
    seen: set[str] = set()
    chunks = _PRODUCT_BOX_SPLIT.split(html)[1:]
    for raw in chunks:
        chunk = _SVG.sub("", raw[:8000])
        mid = _PRODUCT_ID.search(chunk)
        if not mid:
            continue
        sku = mid.group(1)
        if sku in seen:
            continue
        seen.add(sku)
        nm = _PROD_NOMBRE.search(chunk)
        nombre = unescape(nm.group(1)).strip() if nm else ""
        if not nombre:
            continue
        pm = _PRECIO.search(chunk)
        precio = float(pm.group(1)) if pm else None
        cm = _CAT_LINK.search(chunk)
        cat_label = unescape(cm.group(1)).strip() if cm else category_id
        url = urljoin(base_url + "/", f"products?category={category_id}&productId={sku}")
        out.append(
            NormalizedProduct(
                supermercado=SUPERMERCADO_SELECTOS,
                nombre=nombre,
                nombre_normalizado=normalize_name(nombre),
                categoria=cat_label,
                precio=precio,
                unidad=None,
                sku_o_id_externo=sku,
                url_producto=url,
                meta={"category_id": category_id, "source": "html_category"},
            )
        )
    return out


class SuperSelectosScraper(SupermarketScraper):
    key = SUPERMERCADO_SELECTOS

    def __init__(
        self,
        http: HttpClient | None = None,
        *,
        categories: list[str] | None = None,
        store_bases: list[str] | None = None,
    ):
        self.http = http or HttpClient(min_delay_s=1.2, max_delay_s=2.8)
        self.categories = categories if categories is not None else _categories()
        self.store_bases = store_bases if store_bases is not None else _store_bases()

    def _fetch_category(self, category_id: str) -> tuple[str, str]:
        """Retorna (html, base_usada). Prueba primary y fallback."""
        last_err = ""
        for base in self.store_bases:
            url = f"{base}/products"
            try:
                resp = self.http.get(
                    url,
                    params={"category": category_id},
                    accept="text/html,application/xhtml+xml",
                )
                if resp.status_code == 403:
                    last_err = f"403 en {base}"
                    log.warning("Selectos CF/bloqueo en %s — probando siguiente base", base)
                    continue
                if resp.status_code >= 400:
                    last_err = f"HTTP {resp.status_code} en {base}"
                    continue
                return resp.text, base
            except Exception as e:
                last_err = str(e)
                log.warning("Selectos error %s: %s", base, e)
        raise RuntimeError(
            f"No se pudo leer categoría {category_id} en ninguna base ({last_err})"
        )

    def iter_products(self) -> Iterator[NormalizedProduct]:
        for cat in self.categories:
            log.info("Selectos: categoría %s", cat)
            try:
                html, base = self._fetch_category(cat)
            except Exception as e:
                log.error("Selectos categoría %s falló: %s", cat, e)
                continue
            products = parse_category_html(html, category_id=cat, base_url=base)
            log.info("Selectos: categoría %s → %s productos", cat, len(products))
            yield from products

    def fetch_api_catalog_page(
        self, page: int = 1, item_per_page: int = 50
    ) -> list[NormalizedProduct]:
        """
        Catálogo API (sin precio). Útil como complemento / depuración.
        No es el camino principal de precios.
        """
        url = f"{API_BASE}/api/accounts/{ACCOUNT_ID}/products"
        resp = self.http.get(
            url,
            params={
                "Page": page,
                "ItemPerPage": item_per_page,
                "IsActive": "true",
            },
            accept="application/json",
        )
        resp.raise_for_status()
        data = resp.json()
        out: list[NormalizedProduct] = []
        for it in data.get("items") or []:
            sku = str(it.get("id") or "")
            desc = (it.get("description") or {}).get("name") or ""
            if not sku or not desc:
                continue
            dyn = {d.get("fieldName"): d.get("fieldValue") for d in (it.get("dynamicFields") or [])}
            out.append(
                NormalizedProduct(
                    supermercado=SUPERMERCADO_SELECTOS,
                    nombre=desc,
                    nombre_normalizado=normalize_name(desc),
                    categoria=str(dyn.get("TipoProducto") or "") or None,
                    precio=None,
                    unidad=None,
                    sku_o_id_externo=sku,
                    url_producto=f"{PRIMARY_BASE}/products?productId={sku}",
                    meta={"source": "ecom_products_api", "page": page},
                )
            )
        return out
