"""Infra común de scrapers de supermercados (rate limit, retries, logging)."""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import requests

log = logging.getLogger("scrapers")

DEFAULT_UA = (
    "MissionDashboardBot/0.1 (+personal home-server; "
    "contacto: local; respetuoso con rate-limits)"
)


@dataclass
class NormalizedProduct:
    supermercado: str
    nombre: str
    nombre_normalizado: str
    categoria: str | None
    precio: float | None
    unidad: str | None
    sku_o_id_externo: str
    url_producto: str | None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    products: list[NormalizedProduct]
    upserted: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def normalize_name(text: str) -> str:
    import unicodedata

    t = (text or "").strip().lower()
    t = "".join(
        c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)
    )
    t = " ".join(t.split())
    return t


class HttpClient:
    """GET con User-Agent, delays y backoff exponencial."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        min_delay_s: float = 1.0,
        max_delay_s: float = 2.5,
        max_retries: int = 4,
        timeout_s: float = 45.0,
        session: requests.Session | None = None,
    ):
        self.user_agent = user_agent
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = random.uniform(self.min_delay_s, self.max_delay_s)
        elapsed = now - self._last_request_at
        if elapsed < wait:
            time.sleep(wait - elapsed)

    def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        params: dict | None = None,
        accept: str = "text/html,application/json;q=0.9,*/*;q=0.8",
    ) -> requests.Response:
        hdrs = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Language": "es-SV,es;q=0.9,en;q=0.8",
        }
        if headers:
            hdrs.update(headers)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                self._last_request_at = time.monotonic()
                resp = self.session.get(
                    url, headers=hdrs, params=params, timeout=self.timeout_s
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    delay = (2**attempt) + random.uniform(0, 0.5)
                    log.warning(
                        "HTTP %s en %s — retry en %.1fs (intento %s)",
                        resp.status_code,
                        url,
                        delay,
                        attempt + 1,
                    )
                    time.sleep(delay)
                    continue
                return resp
            except requests.RequestException as e:
                last_exc = e
                delay = (2**attempt) + random.uniform(0, 0.5)
                log.warning(
                    "Error red %s — retry en %.1fs (intento %s)",
                    e,
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)
        raise RuntimeError(f"Falló GET {url}: {last_exc}")


class SupermarketScraper(ABC):
    key: str  # valor en supermarket_products.supermercado

    @abstractmethod
    def iter_products(self) -> Iterator[NormalizedProduct]:
        ...

    def scrape(self) -> ScrapeResult:
        products = list(self.iter_products())
        return ScrapeResult(products=products, meta={"count": len(products)})


def persist_products(result: ScrapeResult) -> ScrapeResult:
    """Upsert en supermarket_products; cuenta upserted vs unchanged."""
    from app.db import finanzas_receipts as fr
    from app.db.core import ejecutar

    upserted = 0
    unchanged = 0
    for p in result.products:
        existing = (
            ejecutar(
                """
                SELECT id, nombre, precio, categoria, unidad, url_producto, activo
                FROM supermarket_products
                WHERE supermercado = ? AND sku_o_id_externo = ?
                """,
                [p.supermercado, p.sku_o_id_externo],
                fetchall=True,
            )
            or []
        )
        same = False
        if existing:
            row = existing[0]
            same = (
                (row.get("nombre") or "") == p.nombre
                and (
                    row.get("precio") is None
                    and p.precio is None
                    or (
                        row.get("precio") is not None
                        and p.precio is not None
                        and abs(float(row["precio"]) - float(p.precio)) < 0.001
                    )
                )
                and (row.get("categoria") or None) == (p.categoria or None)
                and (row.get("unidad") or None) == (p.unidad or None)
                and (row.get("url_producto") or None) == (p.url_producto or None)
                and int(row.get("activo") or 0) == 1
            )
        fr.upsert_supermarket_product(
            supermercado=p.supermercado,
            nombre=p.nombre,
            nombre_normalizado=p.nombre_normalizado or normalize_name(p.nombre),
            categoria=p.categoria,
            precio=p.precio,
            unidad=p.unidad,
            sku_o_id_externo=p.sku_o_id_externo,
            url_producto=p.url_producto,
            activo=True,
        )
        if same:
            unchanged += 1
        else:
            upserted += 1
    result.upserted = upserted
    result.unchanged = unchanged
    return result
