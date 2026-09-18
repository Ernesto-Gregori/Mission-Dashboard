# Implementation Plan: Fase 5 — WhatsApp

## Overview
Canal WhatsApp para briefing, gastos, tareas (con sync Calendar de Fase 4) y notas de voz.
No es un chat libre: cuatro intenciones + vínculo de número con verificación.

## Architecture Decisions
- **Proveedor: Meta Cloud API** (no Twilio/360dialog).
  - Alta más lenta (Business Manager), costo por mensaje más bajo, webhook HMAC nativo.
  - Twilio/Gupshup: sandbox en horas, markup por mensaje, otro vendor.
  - Volumen privado: el costo de Meta gana; el webhook es el mismo patrón que Lemon/Stripe.
- Números no vinculados: solo instrucciones de vínculo. Nunca ejecutan acciones.
- Plan: WhatsApp = Premium/Familia (misma palanca que Google). Groq cuenta en `uso_ia`.
- Rate-limit propio por teléfono (no bypasea el de login).
- Recordatorios: fila `whatsapp_reminders` + `scripts/run_whatsapp_reminders.py` (cron), 30 min antes.

## Task List
- [x] Schema + webhook GET/POST firmado + vínculo
- [x] Briefing / gasto / tarea / audio
- [x] Recordatorios cron
- [ ] pytest
