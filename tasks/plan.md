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
- [x] Fase 4: matching fuzzy + UI comparación al guardar escaneo
- [x] UI catálogo SV: sección Precios supermercados (estado + Actualizar + búsqueda)

## Checkpoint Fase 4
- [x] Normalización SV + fuzzy (difflib/tokens), umbral 0.78
- [x] Tests con nombres típicos de recibo
- [x] Al confirmar escaneo → `price_matches` + tarjeta “Comparación de precios”
- [x] Sección visible de Selectos / Walmart / Despensa en Finanzas

