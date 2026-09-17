# Mission Dashboard
Sistema de gestión de vida personal — uso privado.

## Stack
- **FastAPI + HTMX** en `web/`
- **Turso** (producción) · **Groq** IA · Google Fit/Calendar OAuth2 · Lemon Squeezy / Stripe

## Setup local
1. Copia `.env.example` → `.env` y rellena al menos `SESSION_SECRET` y `GROQ_API_KEY`
2. `pip install -r requirements.txt`
3. Arranque:
```bash
MISSION_ALLOW_SQLITE=1 SESSION_SECRET=dev uvicorn web.app:app --reload --port 8000
```
4. Abre http://127.0.0.1:8000 → setup (primer admin) o login

Producción local con Turso: quita `MISSION_ALLOW_SQLITE` y define `TURSO_URL` / `TURSO_TOKEN`.

## Deploy (Railway)
- Start: `uvicorn web.app:app --host 0.0.0.0 --port $PORT` (`railway.json` / `Procfile`)
- Health: `/health`
- Variables: ver `.env.example` + checklist en [CUTOVER.md](./CUTOVER.md)
- Verificar: `python scripts/verify_deploy.py https://TU-APP`

## Google Fit + Calendar
Cliente OAuth tipo **Aplicación web**. Redirect canónico:

`https://TU-DOMINIO/oauth/google/callback`

Variables: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`.

En la app: **Salud** → Conectar con Google.

## Cobros
- Lemon Squeezy (preferido) o Stripe desde `/app/billing`
- Webhooks: `POST /lemon/webhook` o `POST /stripe/webhook`
- Retorno: `/app/billing?checkout=success|cancel`

## Seguridad
- Login usuario + contraseña (PBKDF2)
- Rate-limit de login
- Admin: `/app/usuarios`

## Tests
```bash
pip install -r requirements.txt
pytest -q tests/
```
