# Deploy — FastAPI en Railway

La app que se despliega es `uvicorn web.app:app`. El webhook de Stripe es `POST /stripe/webhook` en ese mismo servicio.

## 1. Railway

1. Servicio con root = repo. Start: `uvicorn web.app:app --host 0.0.0.0 --port $PORT`.
2. Variables (ver `.env.example`):

```
MISSION_WEB=1
MISSION_HTTPS=1
TURSO_URL=…
TURSO_TOKEN=…
SESSION_SECRET=…   # largo, aleatorio
GROQ_API_KEY=…
APP_URL=https://TU-DOMINIO
GOOGLE_OAUTH_CLIENT_ID=…
GOOGLE_OAUTH_CLIENT_SECRET=…
GOOGLE_OAUTH_REDIRECT_URI=https://TU-DOMINIO/oauth/google/callback
# Lemon y/o Stripe
# Telegram (opcional, plan Premium)
TELEGRAM_BOT_TOKEN=…
TELEGRAM_WEBHOOK_SECRET=…
# TELEGRAM_BOT_USERNAME=tu_bot
```

3. `GET /health` responde ok.
4. Webhooks al dominio de esta app: `/lemon/webhook`, `/stripe/webhook`, `/telegram/webhook`.
5. Google Cloud: el redirect URI es el callback de arriba, exacto.
6. `APP_URL=https://TU-DOMINIO` registra el webhook de Telegram al arrancar. El proceso web manda recordatorios y el briefing de la mañana (apagado hasta activarlo en **Configuración → Conexiones**). `scripts/run_telegram_reminders.py` y `scripts/run_telegram_briefings.py` hacen lo mismo si usas un cron aparte.

## 2. Dominio

1. DNS o dominio propio de Railway a este servicio.
2. Actualizar `APP_URL` y las URLs de OAuth, Lemon y Stripe.
3. Probar login, un área, un checkout de prueba y OAuth en **Configuración → Conexiones**.

## 3. Si Streamlit Cloud sigue encendido

Streamlit ya no está en el repo. Si el hosting viejo sigue vivo:

1. [share.streamlit.io](https://share.streamlit.io) → la app → **Stop** o **Delete**.
2. GitHub → Settings → Secrets → borrar `STREAMLIT_APP_URL` si existe.
3. Google Cloud → OAuth: quitar URIs `*.streamlit.app`. Deja el de Railway.
4. Confirma que `GROQ_API_KEY`, Turso y OAuth están en Railway, no solo en el panel viejo.

## 4. Después del deploy

- [ ] Backup JSON en **Configuración → Usuarios** (admin)
- [ ] Un gasto o una cita se escribe en Turso
- [ ] Logs de Railway
- [ ] Volver a vincular Google si el token quedó en el hosting viejo
