# Cutover completo — solo FastAPI

Streamlit fue eliminado del repo (`Mission_Dashboard.py`, `pages/`, dependencia y keep-awake).
La app canónica es FastAPI + HTMX en Railway.

## 1. Railway (si aún no está)

1. Servicio con root = repo, start = `uvicorn web.app:app --host 0.0.0.0 --port $PORT`.
2. Variables (ver `.env.example`):

```
MISSION_WEB=1
MISSION_HTTPS=1
TURSO_URL=…
TURSO_TOKEN=…
SESSION_SECRET=…   # largo, aleatorio
GROQ_API_KEY=…
APP_URL=https://TU-DOMINIO-O-RAILWAY
GOOGLE_OAUTH_CLIENT_ID=…
GOOGLE_OAUTH_CLIENT_SECRET=…
GOOGLE_OAUTH_REDIRECT_URI=https://TU-DOMINIO/oauth/google/callback
# Lemon y/o Stripe según uses
# WhatsApp Cloud API (opcional, plan Premium/Familia)
WHATSAPP_APP_SECRET=…
WHATSAPP_VERIFY_TOKEN=…
WHATSAPP_TOKEN=…
WHATSAPP_PHONE_NUMBER_ID=…
```

3. Health: `GET /health` → ok.
4. Webhooks Lemon/Stripe/WhatsApp al dominio FastAPI (`/lemon/webhook`, `/stripe/webhook`, `/whatsapp/webhook`).
5. Google Cloud → redirect URI exacto al callback FastAPI.
6. Meta App → callback `https://TU-DOMINIO/whatsapp/webhook` + verify token. Cron opcional: `python scripts/run_whatsapp_reminders.py`.

## 2. Dominio

1. DNS / custom domain de Railway al servicio FastAPI.
2. Actualizar `APP_URL` y OAuth/Lemon/Stripe URLs.
3. Probar login, un módulo, checkout test, OAuth Salud.

## 3. Apagar Streamlit Cloud (humano — obligatorio)

1. [share.streamlit.io](https://share.streamlit.io) → tu app → **Stop** o **Delete**.
2. En GitHub → Settings → Secrets and variables → Actions: borrar `STREAMLIT_APP_URL` si existe.
3. En Google Cloud Console → OAuth client: quitar URIs `*.streamlit.app` si ya no los usas; deja solo el de Railway/FastAPI.
4. Si tenías secrets solo en el panel de Streamlit Cloud, confírmalos ya en Railway (`GROQ_API_KEY`, Turso, OAuth, etc.).

## 4. Post-cutover

- [ ] Backup JSON desde `/app/usuarios` (admin)
- [ ] Confirmar Turso escribe tras un gasto / cita
- [ ] Monitorear logs Railway
- [ ] Re-vincular Google Fit si el token quedó en la app Streamlit vieja
