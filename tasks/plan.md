# Implementation Plan: Fase 4 — Sync Calendar + timeline

## Overview

Pasar el planificador de “mostrar eventos de Google” a sync bidireccional persistido,
con Foco del Día y una vista de línea de tiempo arrastrable. Fases 1–3 no se reimplementan.
Fase 5 (WhatsApp) queda fuera hasta confirmación.

## Architecture Decisions

- **Inbound = polling, no Calendar watch.** Railway es FastAPI request-driven; no hay worker
  persistente. Watch exige webhook público + renovar el canal cada ~7 días (igual haría falta
  un cron). Volumen: un dashboard privado de pocos usuarios. Ya se listan eventos en cada
  carga de página. Polling: pull al abrir Foco/Planificador/Agenda (throttle ~45s) +
  `scripts/run_calendar_sync.py` opcional para cron.
- **Outbound = inmediato** en create/update/delete de `eventos_calendario` con fecha/hora,
  salvo checkbox “Solo en el dashboard”.
- **Entidad de sync:** `eventos_calendario.google_id` (ya existe). Columnas nuevas:
  `actualizado_en`, `google_updated`. Tabla `calendar_sync_state` (último poll por usuario).
- **Conflictos:** gana el timestamp más reciente (`actualizado_en` vs Google `updated`).
  Si empatan, gana local (eco de un push). Borrados de Google solo si `status=cancelled`
  (no por ausencia en la ventana, para no borrar eventos que se movieron de día).
- Hábitos con hora y el check de entrenamiento del día entran en **Foco** como ítems locales;
  no se spamea Calendar con un evento diario por hábito.
- Timeline: HTMX/forms existentes + JS vanilla (pointer events), sin frameworks nuevos.

## Task List

### Foundation
- [ ] Task 1: Schema Fase 4 + motor de sync + tests de conflicto
- [ ] Task 2: Push/pull cableado a Agenda y Planificador (`actualizar_evento`)

### Checkpoint: Foundation
- [ ] pytest de sync verde; `/health` intacto

### Producto
- [ ] Task 3: Foco del Día
- [ ] Task 4: Planificador día/semana/mes + drag & drop que dispara sync

### Checkpoint: Complete
- [ ] `pytest -q tests/`
- [ ] No Fase 5

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Duplicar eventos Google ya listados en vivo | Med | Persistir y filtrar por `google_id` (ya hay filtro) |
| Watch vs polling mal elegido | Med | Polling documentado; watch queda para si el cron no alcanza |
| DnD inaccesible | Med | Formulario fecha/hora nativo además del drag |

## Open Questions

- Fase 5 WhatsApp: no empezar hasta confirmación explícita.
