# Fase 5 — TODOs

- [x] Telegram Bot API + secret_token `/telegram/webhook`
- [x] Tabla `telegram_links` y UI en `/app/usuarios?tab=telegram`
- [x] Chat no vinculado: instrucciones, sin acciones
- [x] Briefing / agenda
- [x] Gasto por texto → presupuesto
- [x] Tarea por texto → dashboard + Calendar
- [x] Audio Groq Whisper → tarea
- [x] Recordatorios 30 min antes
- [x] `pytest -q tests/`

# Fase 6 — Telegram v2 — TODOs

- [ ] OK del plan y respuestas a las preguntas abiertas (`tasks/plan.md`)

## Fase 0 — bugs y cimientos
- [ ] PR 1 `cursor/telegram-v2-bugs-8925`: B1 recordatorios con `ahora()` · B2 briefing por palabra completa · B3 «hola» no crea nada · B4 heurísticas ancladas · B5 webhook en background · solo chats privados · `origen="telegram"` + «Anoté $…»
- [ ] PR 2 `cursor/telegram-v2-registry-8925`: `app/telegram_actions/` + router en 5 pasos + split > 4096 (solo refactor)
- [ ] PR 3 `cursor/telegram-v2-confirm-8925`: `telegram_pending` / `telegram_last_action` / `telegram_refs` · `callback_query` · `/deshacer` · `/ayuda <módulo>`
- [ ] PR 4 `cursor/telegram-v2-reminders-8925`: B6 recordatorios desde `eventos_calendario`, sin duplicar, anticipación configurable
- [ ] Checkpoint: `pytest -q tests/` + `verify_deploy.py` + revisión

## Fase 1 — núcleo diario
- [ ] PR 5 `cursor/telegram-v2-finanzas-8925`: `/gasto` con subcategoría real (B7) · `/ingreso` · `/saldo` · `/gastos` · `/vencimientos` · `/borrar`
- [ ] PR 6 `cursor/telegram-v2-habitos-8925`: `/habitos` · `/hecho` difuso · fusión de `marcar_habitos` · teclado de 4 botones
- [ ] PR 7 `cursor/telegram-v2-agenda-8925`: `/tarea` con fechas relativas · `/agenda` · `/mover` · `/cancelar`
- [ ] Checkpoint: flujo diario en chat real

## Fase 2 — salud, enfoque y briefing proactivo
- [ ] PR 8 `cursor/telegram-v2-salud-8925`: `/sueno` · `/energia` · `/ejercicio` · `/salud` · escritura parcial en `app/db/salud.py`
- [ ] PR 9 `cursor/telegram-v2-enfoque-8925`: `/enfoque` con botones → `registrar_sesion`
- [ ] PR 10 `cursor/telegram-v2-briefing-8925`: briefing v2 por módulos activos
- [ ] PR 11 `cursor/telegram-v2-proactivo-8925`: `run_telegram_briefings.py` · prefs HTMX · `/silencio` · docs cron

## Fase 3 — Alma, coach y vida
- [ ] PR 12 `cursor/telegram-v2-alma-8925`: `/alma` · `/coach` · `/semana`
- [ ] PR 13 `cursor/telegram-v2-ideas-lectura-8925`: `/idea` · `/ideas` · `/leyendo` · `/leer`
- [ ] PR 14 `cursor/telegram-v2-fe-pareja-8925`: `/orar` · `/oraciones` · `/respondida` · `/nota` · `/conexion` · `/rutina`

## Fase 4 — recibos y precios
- [ ] PR 15 `cursor/telegram-v2-receipt-service-8925`: extraer servicio de escaneo (solo refactor)
- [ ] PR 16 `cursor/telegram-v2-recibos-8925`: foto de recibo → borrador → confirmar
- [ ] PR 17 `cursor/telegram-v2-precio-estado-8925`: `/precio` · `/estado`

## Por cada PR
- [ ] Tests primero (matriz del plan) · `pytest -q tests/` verde
- [ ] `definition-of-done.md` · `security-checklist.md` · `observability-checklist.md`
- [ ] `help_text` · `BOT_COMMANDS` · README (Telegram) · `tasks/*` · `.env.example` si aplica
