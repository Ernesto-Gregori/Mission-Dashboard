# Implementation Plan: Fase 1 — Quick wins (Alma, Planificador, Salud)

## Overview
Sumar valor en FastAPI + HTMX (`web/`) reutilizando Groq, Google Calendar/Fit y las tablas de hábitos/agenda/salud. Streamlit no se toca. Fase 2 queda en pausa hasta confirmación.

## Architecture Decisions
- Páginas nuevas en el shell existente (`layout_app.html` + `_sidebar.html`), no módulos Coach: `/app/asistente` y `/app/planificador` siempre visibles post-onboarding.
- Contexto de Alma **opt-in**: ninguna categoría se envía a Groq si el checkbox está apagado.
- Bloques del planificador se guardan en `eventos_calendario` con `fuente='local'` **sin** sync a Google (a diferencia de Agenda).
- Rachas de Salud usan un objetivo por usuario (ejercicio / pasos / sueño), no la racha semanal ya existente en Agenda.
- Schema nuevo: `CREATE TABLE IF NOT EXISTS` en `app/db/schema.py` + `ensure_*` al arranque (mismo patrón que `coach_insights`).

## Assumptions
1. "Estilo Alma" = asistente personal en español, cálida y concreta; no un nuevo proveedor de IA.
2. "Tareas pendientes" = hábitos incompletos de hoy + eventos locales próximos + `pendientes_soltar` de bitácora (no hay módulo de tareas).
3. Semana configurable = lunes o domingo como primer día, persistido por usuario.
4. Gráfico de progreso = barras CSS (sin librería JS), semanal y mensual.

## Task List

### 1.1 Asistente Alma
- [ ] Schema + CRUD + contexto opt-in
- [ ] Rutas HTMX + template + nav
- [ ] Tests (página, prefs, historial, contexto vacío por defecto)

### Checkpoint 1.1
- [ ] `pytest -q tests/`

### 1.2 Planificador semanal
- [ ] Semana lun–dom (inicio configurable) + fetch Google + bloques locales
- [ ] Diferenciar visualmente Calendar vs dashboard
- [ ] Tests (página, bloque local, mock Google)

### Checkpoint 1.2
- [ ] `pytest -q tests/`

### 1.3 Rachas y progreso Salud
- [ ] Objetivo + racha diaria + barras 7/30 días en Salud
- [ ] Tests (objetivo, racha, UI)

### Checkpoint Fase 1
- [ ] Suite completa verde
- [ ] `/health`, login y `/stripe/webhook` intactos
- [ ] No pasar a Fase 2 sin confirmación

## Risks
| Risk | Mitigation |
|------|------------|
| Groq en tests | Mock `chat_simple` / `api_key_configurada` como el resto de la suite |
| `guardar_evento` sincroniza a Google | Nuevo flag `sync_google=False` para bloques del planificador |
| Datos de salud/hábitos al LLM | Default off + recorte de tamaño + no loguear contenido |
