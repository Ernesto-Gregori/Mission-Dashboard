# Implementation Plan: Fase 5 — Telegram

## Overview
Canal Telegram para briefing, gastos, tareas (con sync Calendar de Fase 4) y notas de voz.
No es un chat libre: cuatro intenciones + vínculo de cuenta con código /start.

## Architecture Decisions
- **Proveedor: Telegram Bot API** (no WhatsApp/Meta, no Twilio).
  - Alta en minutos (@BotFather), gratis, opt-in (el bot no escribe a extraños).
  - secret_token en `X-Telegram-Bot-Api-Secret-Token`.
- Chats no vinculados: solo instrucciones. Nunca ejecutan acciones.
- Plan: Telegram = Premium/Familia (misma palanca que Google). Groq cuenta en `uso_ia`.
- Rate-limit propio por chat_id (no bypasea el de login).
- Recordatorios: fila `telegram_reminders` + `scripts/run_telegram_reminders.py` (cron), 30 min antes.

## Task List
- [x] Schema + webhook POST firmado + vínculo
- [x] Briefing / gasto / tarea / audio
- [x] Recordatorios cron
- [x] pytest
