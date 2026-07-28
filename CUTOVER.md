# Fase 3 — Cutover Streamlit → FastAPI

Checklist operativo. El código de módulos HTMX vive en la pila de PRs
`#15`…`#25` (rama tip: `cursor/stripe-checkout-banner-8925` / `cursor/fase3-cutover-8925`).

## 0. Merge a `main` (humano)

Orden sugerido (cada PR apila sobre el anterior):

1. #15 tenant ContextVar  
2. #16 Agenda  
3. #17 Salud + OAuth  
4. #18 Admin Premium  
5. #19 Deep Work  
6. #20 Teología  
7. #21 Biblioteca  
8. #22 Matrimonio  
9. #23 Sandbox  
10. #24 Usuarios  
11. #25 Checkout banner  
12. Esta PR (Fase 3 prep)

Alternativa: mergear solo el tip (`cursor/fase3-cutover-8925`) si GitHub lo permite como un único squash/merge de la pila.

## 1. Parity mínima (aceptada para cortar)

| Área | Estado web |
|------|------------|
| Auth / setup / Coach | ✅ |
| Finanzas, Agenda, Salud+OAuth, Deep Work, Teología | ✅ |
| Biblioteca (catálogo/progreso/resaltados) | ✅ MVP (PDF/ISBN IA sigue en Streamlit) |
| Matrimonio (citas/notas/hábitos) | ✅ MVP (IA consejero / chart en Streamlit) |
| Sandbox + Mentor IA | ✅ |
| Usuarios admin / backup / auditoría | ✅ |
| Stripe Checkout + webhook + banner retorno | ✅ |

Gaps conscientes (no bloquean cutover): PDF/ISBN Biblioteca, charts/IA rica Matrimonio.

## 2. Railway (humano)

1. Servicio nuevo (o existente) con root = repo, start = `uvicorn web.app:app --host 0.0.0.0 --port $PORT` (`railway.json` / `Procfile`).
2. Variables (ver `.env.example`):

```
MISSION_WEB=1
MISSION_HTTPS=1
TURSO_URL=…
TURSO_TOKEN=…
SESSION_SECRET=…   # largo, aleatorio
GROQ_API_KEY=…
APP_URL=https://TU-DOMINIO-O-RAILWAY
STRIPE_SECRET_KEY=…
STRIPE_WEBHOOK_SECRET=…
STRIPE_PRICE_PREMIUM=…
STRIPE_PRICE_FAMILIA=…   # opcional
GOOGLE_OAUTH_CLIENT_ID=…
GOOGLE_OAUTH_CLIENT_SECRET=…
GOOGLE_OAUTH_REDIRECT_URI=https://TU-DOMINIO/oauth/google/callback
```

3. Health: `GET /health` → `{"ok": true, "framework": "fastapi+htmx"}`.
4. Stripe Dashboard → webhook endpoint: `https://TU-DOMINIO/stripe/webhook` (eventos `checkout.session.completed`, `customer.subscription.*`).
5. Google Cloud → redirect URI exacto al callback FastAPI.

Verificación local/CI:

```bash
python scripts/verify_deploy.py http://127.0.0.1:8000
```

## 3. Dominio

1. Apuntar DNS / custom domain de Railway al servicio FastAPI.
2. Actualizar `APP_URL` y OAuth/Stripe URLs al dominio final.
3. Probar login, un módulo, checkout test, OAuth Salud.

## 4. Apagar Streamlit Cloud

1. Streamlit Community Cloud → stop / delete la app (o dejarla offline).
2. Quitar secret `STREAMLIT_APP_URL` del repo (Actions) si ya no hace falta.
3. El workflow `keep-awake.yml` queda **desactivado por defecto** (solo `workflow_dispatch`).

## 5. Legado en el repo

- `Mission_Dashboard.py` + `pages/` = referencia / emergencia (ver `pages/README.md`).
- Webhook legacy `webhook/` = opcional; canónico = `POST /stripe/webhook` en FastAPI.
- No hace falta borrar aún: archivar es suficiente hasta estabilizar producción.

## 6. Post-cutover

- [ ] Backup JSON desde `/app/usuarios` (admin)
- [ ] Confirmar Turso escribe tras un gasto / cita
- [ ] Monitorear logs Railway 24–48 h
- [ ] (Opcional) borrar `pages/` en un PR posterior
