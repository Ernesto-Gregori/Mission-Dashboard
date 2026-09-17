# Implementation Plan: Finanzas — recibos por foto + precios SV

## Overview
Extensión experimental de Finanzas (rama `cursor/finanzas-receipts-prices-5638`)
para servidor casero / uso personal. **No merge a main** hasta validar.

## Architecture Decisions
- `gastos_sobres` sigue siendo el gasto canónico (sistema de 3 sobres).
- Satélites: `receipt_items`, `supermarket_products`, `price_matches`, `scrape_runs`.
- Fotos: filesystem local `data/uploads/receipts/{user_id}/` (`data/` ya está en `.gitignore`).
- Visión OCR: Groq vision (`qwen/qwen3.6-27b` u otro disponible) con `GROQ_API_KEY`.
- Default al escanear súper: sobre `Supervivencia` / subcat `Comida` (editable en confirmación).
- Scrapers: script + cron; empezar por Súper Selectos.
- Matching v1: fuzzy + umbral `PRICE_MATCH_SCORE_MIN = 0.78`.

## Phases
- [x] Fase 0: inventario del código actual
- [x] Fase 1: schema + CRUD satélite + tests
- [x] Fase 2a: extracción visión (prompt + parse) — pendiente OK humano antes de UI
- [x] Fase 2b: upload + confirmación HTMX + persistencia
- [x] Fase 3a: scraper Súper Selectos (HTML categorías + fallback Bitworks)
- [x] Fase 3b: Walmart SV + Despensa (API VTEX catalog_system)
- [ ] Fase 4: matching fuzzy + UI comparación

## Checkpoint Fase 3b
- [x] robots.txt VTEX: Disallow account/login/checkout (catálogo OK)
- [x] API `/api/catalog_system/pub/products/search` con Price
- [x] Scrapers `walmart_sv` (~23k) y `despensa_don_juan` (~13k)
- [x] Delays 2–4s + backoff por 429
- [x] Tests mock + dry-run 1 página

