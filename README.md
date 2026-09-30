# Mission Dashboard

App web de áreas de vida. La aplicación es FastAPI + HTMX en `web/`. La lógica está en `app/`.

## Áreas

El menú muestra las áreas activas. Se prenden en **Configuración → Áreas**.

| Menú | Qué abre |
| --- | --- |
| Hoy | El día: agenda, hábitos y ritual |
| Semana | Planificador, Enfoque (si está activo) y Revisión |
| Dinero | Gasto, Mes, Historial, Vencimientos y Precios |
| Cuerpo | Hoy, Rutina, Historial y Racha |
| Espiritualidad | Práctica, historial, oración y método |
| Lectura | Catálogo, alta, en lectura y resaltados |
| Relaciones | Citas, notas y hábitos de conexión |
| Alma | Conversación |
| Cuenta | Mi sistema, Configuración, Plan y cobros. Comparativa solo para admin |

## Stack

- **FastAPI + HTMX** en `web/`
- **Turso** en producción. SQLite local con `MISSION_ALLOW_SQLITE=1`
- **Groq** para la IA
- Google Fit y Calendar (OAuth2)
- Cobros con Lemon Squeezy o Stripe
- Bot de Telegram (plan Premium)

## Setup local

1. Copia `.env.example` → `.env` y rellena al menos `SESSION_SECRET` y `GROQ_API_KEY`.
2. `pip install -r requirements.txt`
3. Arranque:

```bash
MISSION_ALLOW_SQLITE=1 SESSION_SECRET=dev uvicorn web.app:app --reload --port 8000
```

4. Abre http://127.0.0.1:8000 → setup (primer admin) o login.

Con Turso, quita `MISSION_ALLOW_SQLITE` y define `TURSO_URL` / `TURSO_TOKEN`.

## Deploy (Railway)

- Start: `uvicorn web.app:app --host 0.0.0.0 --port $PORT` (`railway.json` / `Procfile`)
- Health: `GET /health`
- Variables y checklist: `.env.example` y [CUTOVER.md](./CUTOVER.md)
- Verificar: `python scripts/verify_deploy.py https://TU-APP`

## Google Fit + Calendar

Cliente OAuth tipo **Aplicación web**. Redirect:

`https://TU-DOMINIO/oauth/google/callback`

Variables: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`.

En la app: **Configuración → Conexiones**.

## Cobros

- Lemon Squeezy o Stripe, desde **Cuenta → Plan y cobros** (`/app/billing`).
- Webhooks en esta misma app: `POST /lemon/webhook` y `POST /stripe/webhook`.
- Retorno: `/app/billing?checkout=success|cancel`.
- Planes: `free` y `premium`. Quien tenía el plan `familia` queda en `premium`.

## Cuenta

- **Configuración** (`/app/configuracion`): Áreas, Día, Dinero, Rueda, Conexiones, Datos. **Usuarios** solo si eres admin.
- El backup de tablas y la auditoría están en **Usuarios**. La copia personal y borrar la cuenta están en **Datos**.
- `GET /app/usuarios` redirige a `/app/configuracion?tab=usuarios`.
- **Comparativa** (admin): `/app/familia`.

## Telegram (Premium)

- Bot API (BotFather). Callback: `POST /telegram/webhook`.
- Vincular en **Configuración → Conexiones** (código y `t.me/bot?start=…`). `GET /app/usuarios?tab=telegram` redirige ahí.
- Intenciones: briefing, gasto, tarea (sync Calendar), nota de voz.
- Comandos: `/briefing` `/habitos` `/hecho` `/gasto` `/ingreso` `/saldo` `/gastos` `/borrar` `/vencimientos` `/tarea` `/agenda` `/mover` `/cancelar` `/ayuda`.
- `/agenda` lista el día, mañana o la semana. No es un alias de `/briefing`.
- Salud: `/sueno`, `/energia`, `/ejercicio`, `/salud`. Guardar un dato no borra el resto del día.
- `/enfoque` muestra los bloques de hoy y los marca Completado, Parcial o Postergado.
- `/briefing` arma secciones según los módulos activos. Fe, pareja y salud no salen salvo opt-in (`briefing_extra`).
- El briefing de la mañana viene apagado. Se activa en **Configuración → Conexiones**. El proceso web lo manda cada 15 min cuando llega la hora local (`app/telegram_jobs.py`). `/silencio` lo pausa. Una vez por usuario y día. `scripts/run_telegram_briefings.py` sirve si hay un cron aparte.
- Teclado: Briefing, Saldo (si Dinero está activo), Hábitos, Ayuda.
- `/alma` usa el mismo historial que la web y no prende categorías. `/coach` respeta el cupo. `/semana` resume.
- `/leyendo` y `/leer` actualizan la página del libro.
- `/orar`, `/oraciones` y `/respondida` usan Espiritualidad. `/nota` y `/conexion` usan Relaciones. `/rutina` resume el ejercicio. No hay devocional por el bot.
- Una foto (máximo 5 MB) se lee como recibo si hay cupo de IA. No se guarda hasta confirmar. Los documentos no.
- `/precio` muestra los 3 más baratos del catálogo. `/estado` resume plan, módulos, Google y llamadas de IA del mes.
- El menú `/` tiene 10 comandos. El resto sale con `/ayuda` y el área (`/ayuda finanzas`). Si el área está apagada, no lista esos comandos.
- Acciones en `app/telegram_actions/` (una por área). El router: comando → botón → patrón → Groq (solo áreas activas) → heurística.
- Solo chats privados. Texto ambiguo responde «no entendí» y no guarda nada.
- Confirmación con botones (o «sí» / «no») para gastos ≥ $200; vence en 10 min (`telegram_pending`). `/deshacer` revierte la última acción del chat, hasta 30 min. El webhook pide `message` y `callback_query` (se re-registra al arrancar).
- Texto libre: gasto si el monto va al inicio, al final o con `$`. Tarea si hay hora explícita o empieza con «agendar» / «recordame».
- Recordatorios: `python scripts/run_telegram_reminders.py` (cron). Para todo evento con hora, 30 min antes por defecto. Se cambia o se apaga en **Configuración → Conexiones**. Hora local (`app.timezone_config`).
- Variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_BOT_USERNAME` (opcional).

## Seguridad

- Login con usuario y contraseña (PBKDF2).
- Rate-limit de login.

## Tests

```bash
pip install -r requirements.txt
MISSION_ALLOW_SQLITE=1 SESSION_SECRET=dev pytest -q tests/
```

En CI, `TURSO_URL` y `TURSO_TOKEN` van vacíos y el comando es `pytest -q tests/`.
