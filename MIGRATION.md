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

## Fase 1 — Auth + Coach HTMX
- [ ] Pantalla Coach (perfil → sugerencia → activar módulos)
- [ ] Respetar cupo Free / Premium en UI
- [ ] Refrescar sesión tras Stripe (`?checkout=success`)

## Fase 2 — Portar módulos (orden sugerido)
1. Finanzas (más crítico / ya encapsulado en `app/db/finanzas.py`)
2. Agenda / bitácora
3. Salud (+ Google OAuth callbacks en FastAPI)
4. Deep Work
5. Teología
6. Biblioteca
7. Matrimonio
8. Sandbox
9. Usuarios (admin)

Cada módulo: template HTMX + rutas en `web/routers/` + reusar `ejecutar()` / helpers de `app/`.

## Fase 3 — Cortar Streamlit
- [ ] Parity funcional mínima
- [ ] Apuntar dominio al servicio FastAPI
- [ ] Apagar Streamlit Cloud + keep-awake
- [ ] Archivar `pages/` o dejar solo como referencia

## Notas
- No reescribas lógica de negocio en templates: vive en `app/`.
- El webhook viejo (`webhook/`) puede seguir o deprecarse; la ruta canónica es `web` → `/stripe/webhook`.
- Tests: `pytest -q tests/` (incluye `test_web_smoke.py`).
