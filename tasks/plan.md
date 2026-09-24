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

---

# Implementation Plan: Fase 6 — Telegram v2

## Overview
El bot pasa de 4 acciones a ser el canal rápido de **captura y consulta** de todo el sistema
(finanzas, hábitos, agenda, salud, enfoque, ideas, oración, lectura) más un briefing proactivo
opt-in. Sigue sin ser un chat libre: **cero escrituras por ambigüedad**, confirmación para lo
destructivo, `/deshacer` y respeto estricto de módulos activos, plan y tenant.

## Architecture Decisions
- **Transporte vs. acciones.** `app/telegram.py` conserva transporte, vínculo, seguridad y despacho.
  Las acciones viven en `app/telegram_actions/` (un archivo por área) como `Accion`
  (`clave, comandos, alias, modulo, confirmar, parse, ejecutar`). Los nombres que parchean los tests
  (`handle_inbound`, `parse_intent`, `send_text`, `BOT_COMMANDS`, `schedule_reminder`,
  `send_due_reminders`, `start_link`, `public_base_url`, `extract_inbound`, `verify_webhook_secret`,
  `webhook_secret`) siguen importables desde `app.telegram`.
- **Router en 5 pasos:** comando `/x` → botón del teclado → patrones determinísticos anclados →
  LLM (una llamada, `max_tokens` bajo, prompt generado desde el registro con solo acciones de
  módulos activos + fecha y día de la semana) → desconocido = «no entendí» + sugerencias, **sin escribir**.
  La salida del LLM se valida contra el esquema de la acción; el texto de fallback de
  `chat_simple` («Modo offline…») se trata como `unknown`. `parse_fn` sigue inyectable.
- **Confirmaciones:** tabla `telegram_pending` (`id, user_id, chat_id, accion, payload_json,
  expira_en, creado_en`), TTL 10 min. `callback_data = "p:<id>:<si|no>"` (< 64 bytes).
  También se acepta «sí/no» por texto. `allowed_updates = ["message", "callback_query"]`
  (se re-registra solo al arrancar) y `answerCallbackQuery` siempre.
- **Deshacer:** tabla `telegram_last_action` (una fila por chat: `accion, entidad, entidad_id,
  payload_json, expira_en`). `/deshacer` revierte solo la última acción, con TTL.
- **Referencias cortas por chat:** tabla `telegram_refs` (`chat_id, tipo, n, entidad_id, creado_en`)
  para `/borrar 2`, `/mover 3 …`, `/respondida 1`. Se regenera en cada listado; nunca se acepta
  un id de BD desde el texto.
- **Prefs del bot:** tabla `telegram_prefs` (`user_id, briefing_hora, briefing_secciones_json,
  silencio_hasta, recordatorio_min, ultimo_briefing`) editable en `/app/usuarios?tab=telegram`.
- **Webhook asíncrono:** el router responde 200 enseguida y procesa con `BackgroundTasks`
  (Telegram reintenta si tarda; el dedupe por `update_id` ya existe). `TestClient` ejecuta
  las background tasks sincrónicamente, así que los tests actuales siguen valiendo.
- **Solo chats privados:** `extract_inbound` descarta `chat.type != "private"` (grupos, supergrupos, canales).
- **Reutilizar, no duplicar:** toda escritura pasa por las funciones existentes de `app/db/*`,
  `app/ritual.py`, `app/presupuesto.py`, etc. Lo que falte se agrega en su módulo con test
  (p. ej. escritura parcial de salud). Fechas siempre con `app.timezone_config`.
- **Moneda:** mismo formato que la web: `$12.50` para ítems, `$1234` para totales (ver pregunta 2).
- **Observabilidad:** logger `telegram`, una línea por mensaje: `chat=<últimos 4> accion=… ok=… ms=…`.
  Sin texto del usuario, montos ni nombres en logs. Auditoría con `app.audit.registrar`.
- **Límites de entrada:** texto ≤ 1000 caracteres, audio ≤ 6 MB / 120 s, foto ≤ 5 MB.

## PRs (uno por fase lógica; rama `cursor/telegram-v2-<fase>-8925`, base `main`)

Nota: el brief numera Fase 0 = PR 1-2 y Fase 1 = PR 3-5. Para no mezclar refactor con
features, propongo partir la Fase 0 en 4 PRs (bugs, refactor, confirmaciones, recordatorios).

### Fase 0 — bugs y cimientos

**PR 1 · `telegram-v2-bugs`** — B1, B2, B3, B4, B5, solo chats privados, `origen="telegram"`.
- B1: `schedule_reminder` y `send_due_reminders` usan `ahora()`; test con reloj fijo que falla hoy.
- B2: palabras de briefing por palabra completa/frase corta; «agendar reunión…» y
  «leer el resumen del capítulo 3» no disparan briefing.
- B3: `unknown` sin monto → «no entendí» + sugerencias; «hola»/«gracias» no crean nada.
- B4: monto solo con `$` o al inicio/fin del mensaje; hora solo con `am/pm`, `HH:MM` o «a las N».
  Quitar `pesos/mxn` de `AMOUNT_RE`.
- B5: webhook con `BackgroundTasks`, 200 inmediato.
- Grupos/canales ignorados (test).
- B7 (parte 1): `GASTO_ORIGEN_TELEGRAM` en `GASTO_ORIGENES`; badge visible en `/app/m/finanzas`.
  Respuesta «Anoté $35.00 en …» en lugar de «Gasté 35».
- Link-code: `start_link` / `_find_pending_by_code` pasan de UTC a `ahora()` (hoy es coherente,
  pero rompe la regla de fechas; códigos en curso vencen como máximo 10 min antes).
- *Aceptación:* tests de regresión B1–B5 y grupo fallan antes y pasan después; `pytest -q tests/` verde.
- *Archivos:* `app/telegram.py`, `web/routers/telegram.py`, `app/db/schema.py`, `tests/test_telegram.py`.

**PR 2 · `telegram-v2-registry`** — C1 + C2 + C5, **refactor sin cambio de comportamiento**.
- `app/telegram_actions/{__init__,base,finanzas,agenda,briefing}.py` con `Accion` y registro.
- Router en 5 pasos; prompt del LLM generado desde el registro (solo módulos activos, fecha + día).
- Validación de JSON por acción; fallback offline = `unknown`.
- `send_text` parte mensajes > 4096 (hoy recorta a 3500); texto plano.
- *Aceptación:* los tests existentes pasan sin tocarlos (salvo imports); test de split y de prompt
  filtrado por módulos.

**PR 3 · `telegram-v2-confirm`** — C3 + C4.
- Tablas `telegram_pending`, `telegram_last_action`, `telegram_refs` en `ensure_telegram_schema()`.
- `callback_query` en `extract_inbound` y `allowed_updates`; `answerCallbackQuery`; «sí/no» por texto.
- `/deshacer` para las acciones existentes (gasto → `eliminar_gasto_sobre`, tarea → `eliminar_evento`).
- `/ayuda` y `/ayuda <módulo>` generados desde el registro, solo módulos activos; menú `/` ≤ 10.
- *Aceptación:* confirmar / cancelar / expirar / callback de otro chat rechazado / `/deshacer` vencido.

**PR 4 · `telegram-v2-reminders`** — B6.
- Recordatorios desde `eventos_calendario` (cualquier fuente) generados por el cron, únicos por
  (`evento_id`, `fire_at`) con índice único; si el evento se mueve, se recalcula.
- Anticipación en `telegram_prefs.recordatorio_min`, default 30. Solo eventos con hora.
- *Aceptación:* evento web o Google genera 1 recordatorio; correr el cron 2 veces no duplica.

### Checkpoint Fase 0
- [ ] `pytest -q tests/` verde · `verify_deploy.py` OK · revisión humana antes de Fase 1.

### Fase 1 — núcleo diario

**PR 5 · `telegram-v2-finanzas`** — `/gasto`, `/ingreso`, `/saldo`, `/gastos`, `/vencimientos`, `/borrar`; B7 (parte 2).
- Inferencia de sobre + subcategoría real de `SOBRES_CONFIG` (tabla de palabras clave por
  subcategoría, sin LLM); si no hay match → default, dicho en la respuesta + botón «Cambiar».
- Confirmación si el monto supera el umbral (pregunta 4) o si `/ingreso` pisa uno distinto.
- `/saldo` con `resumen_mes` + `semaforo`; `/gastos` últimos 7 con refs cortas.

**PR 6 · `telegram-v2-habitos`** — `/habitos`, `/hecho <hábito>`, «ya leí».
- Coincidencia difusa contra `listar_habitos`; > 1 candidato → botones.
- Fusión obligatoria `completos_de(habitos_hoy()) ∪ nuevos` (test que demuestra que no se desmarca nada).
- Teclado fijo: `📋 Briefing · 💸 Saldo · ✅ Hábitos · ❓ Ayuda` (Saldo solo si `finanzas` activo).

**PR 7 · `telegram-v2-agenda`** — `/tarea` con fechas relativas, `/agenda [hoy|mañana|semana]`, `/mover`, `/cancelar`.
- Parser de fechas relativas determinístico en `app/` (mañana, pasado mañana, lunes, «en 2 horas»,
  «el 15», duración). Respuesta «📅 Vie 26 sep 17:00–18:00 · Llamar al banco».
- `/agenda` deja de ser alias de `/briefing` (cambio visible, se documenta).
- `/mover` y `/cancelar` siempre con confirmación.

### Checkpoint Fase 1
- [ ] Flujo diario completo en un chat real (gasto → saldo → hábito → tarea → deshacer).

### Fase 2 — salud, enfoque y briefing proactivo

**PR 8 · `telegram-v2-salud`** — `/sueno`, `/energia`, `/ejercicio`, `/salud`.
- Nueva `actualizar_registro_salud_parcial(fecha, campos)` en `app/db/salud.py` (lee, fusiona,
  guarda) con test de que no borra columnas ajenas.

**PR 9 · `telegram-v2-enfoque`** — `/enfoque` con botones Completado / Parcial / Postergado → `registrar_sesion`.

**PR 10 · `telegram-v2-briefing`** — contenido del briefing v2 por módulos activos
(agenda, hábitos pendientes, enfoque, vencimientos ≤ 3 días, rutina, sobre más apretado;
fe/pareja/salud solo con opt-in en `telegram_prefs`).

**PR 11 · `telegram-v2-proactivo`** — `scripts/run_telegram_briefings.py`, prefs en
`/app/usuarios?tab=telegram` (HTMX + test), `/silencio [días]`. Apagado por defecto, idempotente
por usuario + día, solo chats verificados con plan vigente. Cron en README y `CUTOVER.md`.

### Fase 3 — Alma, coach y vida

**PR 12 · `telegram-v2-alma`** — `/alma`, `/coach` (cuota), `/semana`. Alma solo por comando explícito.

**PR 13 · `telegram-v2-ideas-lectura`** — `/idea [#dominio]`, `/ideas`, `/leyendo`, `/leer <libro> <página>`.

**PR 14 · `telegram-v2-fe-pareja`** — `/orar`, `/oraciones`, `/respondida <n>`, `/nota`, `/conexion`, `/rutina`.
Devocional solo si `guardar_devocional` no exige campos que habría que inventar.

### Fase 4 — recibos y precios

**PR 15 · `telegram-v2-receipt-service`** — refactor: extraer la lógica de escaneo de
`web/routers/finanzas.py` a `app/receipt_service.py`, sin cambio de comportamiento web.

**PR 16 · `telegram-v2-recibos`** — `photo` en `extract_inbound`; OCR con `cuota_ia_ok`; borrador
+ confirmación (`pendiente_confirmacion` → `confirmado`); límite 5 MB.

**PR 17 · `telegram-v2-precio-estado`** — `/precio <producto>` (3 más baratos) y `/estado`.

### Checkpoint final
- [ ] Todas las acciones con la matriz de tests de la sección «Pruebas» del brief.
- [x] README, `help_text`, `BOT_COMMANDS`, `.env.example`, `CUTOVER.md` al día.

## Matriz de tests por acción (`tests/test_telegram_<área>.py`)
Feliz · faltan argumentos · módulo inactivo · plan Free · chat sin vincular · confirmar/cancelar/expirar ·
idempotencia `update_id` · aislamiento Familia (2 usuarios) · Groq caído (`api_key_configurada → False`).

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Refactor del PR 2 rompe tests que parchean `app.telegram.*` | Med | Re-exportar nombres; PR solo refactor; tests sin cambios |
| `BackgroundTasks` oculta errores (Telegram no reintenta) | Med | Log `ok=false` + mensaje al usuario «no se guardó nada» |
| Recordatorios de todos los eventos = spam (Google trae muchos) | Med | Solo eventos con hora; `recordatorio_min=0` apaga; ver pregunta 7 |
| Coincidencia difusa marca el hábito equivocado | Med | Umbral alto; > 1 candidato → botones; `/deshacer` |
| LLM devuelve acción de módulo apagado | Low | Validación posterior contra registro + `modulo_activo` |
| Rate-limit en memoria (`_TG_HITS`) no escala a > 1 réplica | Low | Hoy Railway corre 1 instancia; documentado |
| Scrapers de El Salvador vs. `TZ_LOCAL` comentado como México | Low | Ambos UTC-6 sin horario de verano; no se cambia |

## Open Questions (default propuesto — espera OK)
1. **Hora del briefing proactivo / cierre nocturno.** Default: 07:00 hora local, apagado por defecto.
   Sin «cierre del día» en esta fase (queda en backlog para después del PR 11).
2. **Moneda y formato.** Default: USD con `$`, igual que la web: `$12.50` en ítems, `$1234` en totales.
   Se eliminan `pesos/mxn`; se aceptan `$`, `usd`, `dólares` como sufijo opcional.
3. **Texto libre no reconocido.** Default: «no entendí» + 2-3 sugerencias según módulos activos.
   Alma solo por `/alma`.
4. **Umbral de confirmación de gastos.** Default: pedir confirmación si el monto es ≥ $200
   o si deja el sobre en negativo.
5. **Fe y pareja en el briefing.** Default: no; opt-in por sección en `/app/usuarios?tab=telegram`.
   Salud tampoco por defecto.
6. **Orden de fases.** Default: 0 → 1 → 2 → 3 → 4, con los PRs en el orden de arriba.
7. **(nueva) Recordatorios para eventos no creados por Telegram (B6).** Default: activos para
   eventos con hora (30 min antes); se apagan con `recordatorio_min = 0` en la web.
8. **(nueva) `/agenda`.** Hoy es alias de `/briefing`; en el PR 7 pasa a listar agenda. Default: aceptar el cambio.
