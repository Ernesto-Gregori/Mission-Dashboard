# Implementation Plan: Fase 3 — Ritual, rueda, tema

## Overview
Cierre de quick-wins en FastAPI + HTMX. Streamlit no se toca.

## Architecture Decisions
- `/app/ritual` y `/app/rueda` siempre visibles post-onboarding.
- El ritual escribe `ritual_diario` y `habitos_diarios_v2` (misma carga que Agenda).
- La rueda es autoevaluación 0–10 en 8 áreas, dibujada en SVG.
- Tema claro/oscuro en `user_prefs.theme` + cookie + `html[data-theme]`.

## Task List
- [x] Ritual de mañana
- [x] Rueda de la vida
- [x] Tema claro/oscuro
- [x] `pytest -q tests/`
- [x] Merge a main
