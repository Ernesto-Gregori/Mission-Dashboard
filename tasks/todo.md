# Finanzas receipts / price compare — TODOs

## Fase 1 (esta PR)
- [x] Rama `cursor/finanzas-receipts-prices-5638`
- [x] Schema extendido + tablas satélite
- [x] CRUD `app/db/finanzas_receipts.py`
- [x] Tests schema
- [ ] Confirmar con humano antes de Fase 2

## Fase 2
- [x] Función extracción (prompt + parse) — `app/receipt_ocr.py`
- [x] Upload + resize + confirmación HTMX
- [x] Persistencia gasto + items
- [ ] Probar end-to-end con GROQ_API_KEY y foto real

## Fase 3
- [ ] Inspección Selectos (HTML vs API) + robots.txt
- [ ] Scraper Selectos + scrape_runs
- [ ] Replicar Walmart / Despensa

## Fase 4
- [ ] Normalización + fuzzy + tests con nombres reales
- [ ] Integrar al flujo de guardado
