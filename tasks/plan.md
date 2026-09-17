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
- [ ] Fase 3b: Walmart SV / Despensa (mismo patrón)
- [ ] Fase 4: matching fuzzy + UI comparación

## Checkpoint Fase 3a
- [x] Inspección: API ecom-products sin precio; HTML storefront con `strong.precio`
- [x] www CF 403 desde cloud → fallback `selectospp.bitworks.com.sv`
- [x] `pytest -q tests/test_scraper_super_selectos.py`
- [x] dry-run real categoría 012
- Frecuencia recomendada: **1 corrida/día** (`scripts/run_supermarket_scrape.py`), delays 1.2–2.8s

