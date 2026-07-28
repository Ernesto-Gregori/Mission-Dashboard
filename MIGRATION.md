# Migración Streamlit → FastAPI + HTMX

Streamlit **sigue vivo** en `Mission_Dashboard.py` / `pages/` hasta completar parity.
La app nueva vive en `web/` y reutiliza `app/` (db, billing, audit, AI, Google).

## Fase 0 — Esqueleto (esta PR) ✅
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
- `TURSO_URL`, `TURSO_TOKEN`
- `SESSION_SECRET` (largo, aleatorio)
- `GROQ_API_KEY`
- `APP_URL` (URL pública Railway)
- `STRIPE_*` + `STRIPE_WEBHOOK_SECRET`
- `MISSION_HTTPS=1` cuando tengas HTTPS

Health: `GET /health`

## Fase 1 — Auth + Coach HTMX ✅
- [x] Pantalla Coach (perfil → sugerencia → activar módulos)
- [x] Respetar cupo Free / Premium en UI
- [x] Redirect a `/app/coach` si falta onboarding
- [x] Reconfig Premium / paywall Free
- [ ] Refrescar sesión tras Stripe (`?checkout=success`) — parcial en Streamlit; pendiente banner web

## Fase 2 — Portar módulos (orden sugerido)
1. [x] Finanzas (ingreso, sobres, gastos, consejo IA) — `web/routers/finanzas.py`
2. [x] Agenda / bitácora — `web/routers/agenda.py` + `app/db/agenda.py`
3. [x] Salud (+ Google OAuth callbacks en FastAPI) — `web/routers/salud.py`, `web/routers/oauth_google.py`
4. [x] Deep Work — `web/routers/deep_work.py` + `app/db/deep_work.py`
5. [x] Teología — `web/routers/teologia.py` + `app/db/teologia.py`
6. [x] Biblioteca (MVP catálogo/progreso/resaltados; PDF/ISBN IA sigue en Streamlit) — `web/routers/biblioteca.py`
7. [x] Matrimonio (citas, notas, hábitos; IA consejero / chart historial siguen en Streamlit) — `web/routers/matrimonio.py`
8. [x] Sandbox (ideas, snippets, sesiones, mentor IA) — `web/routers/sandbox.py`
9. [x] Usuarios (plan propio + admin: crear, set plan, backup, auditoría) — `web/routers/usuarios.py`

**Groq en FastAPI:** la clave de Streamlit Cloud no se comparte sola.
Usa `GROQ_API_KEY` en el entorno, `.env`, o `.streamlit/secrets.toml` (leído por `app/secrets.py`).

## Fase 3 — Cortar Streamlit
- [ ] Parity funcional mínima
- [ ] Apuntar dominio al servicio FastAPI
- [ ] Apagar Streamlit Cloud + keep-awake
- [ ] Archivar `pages/` o dejar solo como referencia

## Notas
- No reescribas lógica de negocio en templates: vive en `app/`.
- El webhook viejo (`webhook/`) puede seguir o deprecarse; la ruta canónica es `web` → `/stripe/webhook`.
- Tests: `pytest -q tests/` (incluye `test_web_smoke.py`).
