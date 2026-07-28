# Migración Streamlit → FastAPI + HTMX

Streamlit queda como **legado** (`Mission_Dashboard.py` / `pages/`).
La app canónica vive en `web/` y reutiliza `app/` (db, billing, audit, AI, Google).

Cutover operativo: **[CUTOVER.md](./CUTOVER.md)**.

## Fase 0 — Esqueleto ✅
- [x] FastAPI app (`web/app.py`)
- [x] Sesión cookie + login / setup / logout
- [x] Dashboard + nav de módulos
- [x] Stubs por módulo + paywall por plan
- [x] Billing page + Checkout
- [x] Stripe webhook en la misma app (`POST /stripe/webhook`)
- [x] `app/tenant.py` con contextvars (Streamlit + FastAPI)

### Arranque local
```bash
pip install -r requirements.txt
# Copia la misma GROQ_API_KEY de Streamlit a .env o .streamlit/secrets.toml
echo 'GROQ_API_KEY=gsk_...' >> .env
MISSION_ALLOW_SQLITE=1 SESSION_SECRET=dev uvicorn web.app:app --reload --port 8000
```
Abre http://127.0.0.1:8000 → setup o login.

### Producción (Railway)
Variables:
- `MISSION_WEB=1`, `MISSION_HTTPS=1`
- `TURSO_URL`, `TURSO_TOKEN`
- `SESSION_SECRET` (largo, aleatorio)
- `GROQ_API_KEY`
- `APP_URL` (URL pública Railway / dominio)
- `STRIPE_*` + `STRIPE_WEBHOOK_SECRET`
- Google OAuth (`GOOGLE_OAUTH_*`) si usas Salud

Health: `GET /health` — también `python scripts/verify_deploy.py $APP_URL`

## Fase 1 — Auth + Coach HTMX ✅
- [x] Pantalla Coach (perfil → sugerencia → activar módulos)
- [x] Respetar cupo Free / Premium en UI
- [x] Redirect a `/app/coach` si falta onboarding
- [x] Reconfig Premium / paywall Free
- [x] Refrescar sesión tras Stripe (`?checkout=success`) — banner web en `/app/billing` + URLs de retorno FastAPI

## Fase 2 — Portar módulos ✅
1. [x] Finanzas — `web/routers/finanzas.py`
2. [x] Agenda / bitácora — `web/routers/agenda.py` + `app/db/agenda.py`
3. [x] Salud (+ Google OAuth) — `web/routers/salud.py`, `web/routers/oauth_google.py`
4. [x] Deep Work — `web/routers/deep_work.py` + `app/db/deep_work.py`
5. [x] Teología — `web/routers/teologia.py` + `app/db/teologia.py`
6. [x] Biblioteca (MVP; PDF/ISBN IA sigue en Streamlit) — `web/routers/biblioteca.py`
7. [x] Matrimonio (MVP; IA/chart siguen en Streamlit) — `web/routers/matrimonio.py`
8. [x] Sandbox — `web/routers/sandbox.py`
9. [x] Usuarios (admin) — `web/routers/usuarios.py`

**Groq en FastAPI:** usa `GROQ_API_KEY` en el entorno, `.env`, o `.streamlit/secrets.toml` (`app/secrets.py`).

## Fase 3 — Cortar Streamlit
- [x] Parity funcional mínima documentada (MVP aceptado; ver CUTOVER.md)
- [x] Deploy config lista (`Procfile`, `railway.json`, `scripts/verify_deploy.py`)
- [x] Keep-awake Streamlit desactivado por defecto
- [x] `pages/` marcado como legado
- [ ] **Humano:** merge PRs → Railway + `APP_URL` / Stripe / Google
- [ ] **Humano:** apuntar dominio al servicio FastAPI
- [ ] **Humano:** apagar Streamlit Cloud + quitar `STREAMLIT_APP_URL`
- [ ] (Opcional) borrar `pages/` tras estabilizar

## Notas
- No reescribas lógica de negocio en templates: vive en `app/`.
- El webhook viejo (`webhook/`) puede seguir o deprecarse; la ruta canónica es `web` → `/stripe/webhook`.
- Tests: `pytest -q tests/` (incluye `test_web_smoke.py`).
