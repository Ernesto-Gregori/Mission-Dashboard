# Implementation Plan: Fase 2 — Presupuesto, vencimientos, familia

## Overview
Vistas derivadas de una sola carga. FastAPI + HTMX (`web/`). Streamlit no se toca. Fase 3 queda en pausa.

## Architecture Decisions
- `/app/presupuesto` y `/app/familia` siempre visibles post-onboarding (no módulos Coach).
- 50/30/20 lee `ingreso_mensual` + `gastos_sobres`. Mapeo: Supervivencia→necesidades, Ministerio_Extras→deseos, Futuro_Hogar→ahorro.
- Ratios en `presupuesto_config`; vencimientos en `presupuesto_recurrentes`. Escrituras vía `guardar_ingreso` / `agregar_gasto_sobre`.
- Familia es admin-only; cada miembro se consulta con `as_user` + `user_id` explícito.

## Assumptions
1. Los sobres 65/20/15 siguen siendo el almacén; 50/30/20 es una vista con ratios propios.
2. Un recurrente de día 31 en meses cortos cae en el último día.
3. “Tareas” en familia = hábitos de hoy incompletos + eventos locales próximos.

## Task List

### 2.1 Presupuesto 50/30/20
- [x] Schema + resumen vs gasto real + gráfico
- [x] Rutas HTMX + template + nav
- [x] Tests (página, ingreso compartido con Finanzas, ratios)

### Checkpoint 2.1
- [x] `pytest -q tests/`

### 2.2 Calendario de vencimientos
- [x] CRUD recurrentes coloreados por tipo
- [x] Tests (suscripción / factura / ingreso en el mes)

### Checkpoint 2.2
- [x] `pytest -q tests/`

### 2.3 Vista familiar
- [x] Comparativa admin + filtro por miembro
- [x] Tests (comparativa, 403 no-admin)

### Checkpoint Fase 2
- [x] Suite completa verde
- [x] `/health`, login y `/stripe/webhook` intactos
- [ ] No pasar a Fase 3 sin confirmación

## Risks
| Risk | Mitigation |
|------|------------|
| Duplicar finanzas | Reusar ingreso/gastos; no segunda caja |
| Fuga entre miembros | `as_user` + filtro `user_id`; 403 si no es admin |
| Ratios inválidos | Rechazo 400 si no suman 100 |
