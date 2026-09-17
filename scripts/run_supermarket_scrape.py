#!/usr/bin/env python3
"""
Cron / CLI: scrapea supermercados y hace upsert en supermarket_products.

Uso:
  MISSION_ALLOW_SQLITE=1 python3 scripts/run_supermarket_scrape.py
  python3 scripts/run_supermarket_scrape.py --only super_selectos
  SELECTOS_CATEGORIES=012,03 python3 scripts/run_supermarket_scrape.py

Frecuencia recomendada: 1 vez al día (cron), delays 1–3s entre requests.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("run_supermarket_scrape")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape catálogo supermercados SV")
    parser.add_argument(
        "--only",
        default="",
        help="Clave de scraper (ej. super_selectos). Vacío = todos los registrados.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo lista productos sin escribir BD.",
    )
    args = parser.parse_args()

    # Asegurar schema
    from app.db.schema import init_database
    from app.multiuser import migrate_multiuser

    init_database()
    try:
        migrate_multiuser()
    except Exception as e:
        log.warning("migrate_multiuser: %s", e)

    from app.scrapers import SCRAPERS, run_scraper
    from app.scrapers.base import persist_products

    keys = [args.only] if args.only else list(SCRAPERS.keys())
    for key in keys:
        if key not in SCRAPERS:
            log.error("Scraper desconocido: %s", key)
            return 2
        if args.dry_run:
            scraper = SCRAPERS[key]()
            products = list(scraper.iter_products())
            log.info("[dry-run] %s → %s productos", key, len(products))
            for p in products[:15]:
                log.info("  %s | $%s | %s", p.sku_o_id_externo, p.precio, p.nombre)
            if len(products) > 15:
                log.info("  … +%s más", len(products) - 15)
            continue
        result = run_scraper(key)
        log.info(
            "Done %s upserted=%s unchanged=%s total=%s",
            key,
            result.upserted,
            result.unchanged,
            len(result.products),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
