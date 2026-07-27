# Mission Dashboard
Sistema de gestión de vida personal — uso privado.

## Stack
- Streamlit + SQLite → Turso (opcional)
- **Groq** IA (`llama-3.3-70b-versatile`)
- Google Fit + Google Calendar OAuth2

## Setup local
1. Crear `.env` con `GROQ_API_KEY=` (y opcionalmente `TURSO_URL`, `TURSO_TOKEN`)
2. `pip install -r requirements.txt`
3. `streamlit run Mission_Dashboard.py`
4. En el primer arranque, crea tu usuario y contraseña (se guardan con hash en la BD)

## Google Fit + Calendar (OAuth por usuario)
Cada usuario vincula **su** Google. El token vive en `oauth_tokens` (Turso/SQLite) y sirve para Fit y Calendar.

### Opción A — OAuth web en Streamlit Cloud (recomendado)
1. Google Cloud Console → APIs: activa **Fitness API** y **Google Calendar API**
2. Credenciales → Crear cliente OAuth → tipo **Aplicación web**
3. Authorized redirect URIs: `https://TU-APP.streamlit.app/` (exacto, con `/` final si así lo pones)
4. En Streamlit Cloud → Secrets:

```toml
[google_oauth]
client_id = "xxxxx.apps.googleusercontent.com"
client_secret = "xxxxx"
redirect_uri = "https://TU-APP.streamlit.app/"
```

5. Entra a la app → **Salud** → **Conectar con Google** → autoriza
6. Debe decir «token en BD»

Si OAuth está en modo **Testing**, el refresh puede caducar ~7 días: añade tu Gmail como test user o publica la app.

### Opción B — Local / pegar JSON (respaldo)
1. `credentials_fit.json` (Desktop) en local → Salud → OAuth local  
2. O pega el JSON en Salud → «Pegar token JSON»

## Seguridad
- Login con **usuario + contraseña** en todas las páginas
- Contraseñas con PBKDF2 (no texto plano)
- Rate-limit de login (bloqueo temporal tras fallos)
- **Crear usuarios:** menú lateral → **Usuarios** (solo rol admin)
- Backup JSON desde Usuarios (admin)
- Si ya tenías `APP_PASSWORD` en secrets y no hay usuarios, se crea `admin` automáticamente (entra con usuario `admin` + esa clave)

## Tests
```bash
pip install -r requirements.txt
pytest -q tests/
```

## Hosting
- Esta app es **Streamlit**. En Streamlit Cloud funciona tal cual.
- **NiceGUI / Flet no corren en Streamlit Cloud** — haría falta otro hosting y reescribir la UI. Ver `DIAGNOSTICO.md`.

### App que se “duerme” (Streamlit Community Cloud)
Es normal en el plan gratis: sin tráfico la app hiberna y el siguiente acceso tarda en despertar.

**Mitigación gratis (recomendada):** GitHub Action `Keep Streamlit Awake` (cada 6 h con Playwright).

1. Copia la URL de tu app (`https://….streamlit.app`)
2. En GitHub → **Settings → Secrets and variables → Actions**
3. Crea el secret `STREAMLIT_APP_URL` con esa URL
4. **Actions → Keep Streamlit Awake → Run workflow** (probar una vez)

**Si quieres cero sueño de verdad:** mover a hosting always-on (Railway, Render, Fly.io, VPS). Ver `DIAGNOSTICO.md`.

## Multi-usuario
Cada cuenta tiene **sus propios datos** (finanzas, hábitos, salud, etc.).
Los datos antiguos se asignan al primer admin en la migración automática.

## Coach IA + plantillas
En el **primer login** de un usuario nuevo, un coach (Groq) pregunta perfil y sugiere
módulos/plantillas (Agenda, Finanzas, Deep Work, etc.) y hábitos iniciales.
- Solo se muestran los módulos activos de esa cuenta
- Se puede reconfigurar desde el dashboard → «Coach — reconfigurar mi sistema»
- Sin `GROQ_API_KEY`, el coach usa reglas locales (fallback)

## Estabilidad Streamlit
- Los formularios (`st.form`) evitan recargar al escribir (Finanzas, Bitácora, Deep Work, hábitos, chat).
- La BD se inicializa una sola vez por sesión (`ensure_database`).
- Tras guardar se limpian caches para ver el cambio al instante.

## Persistencia (importante)
- Todas las escrituras (incluida **Finanzas**) pasan por `ejecutar()` → misma BD
- Con Turso configurado, los datos persisten en la nube
- Sin Turso, se usa `data/mission.db` (ignorado por git)
- **Producción web:** exige `TURSO_URL` + `TURSO_TOKEN` en secrets

## Planes + Stripe
Planes: **Free** / **Premium ($7)** / **Familia ($14)**.

### Secrets en Streamlit Cloud
```toml
TURSO_URL = "libsql://…"
TURSO_TOKEN = "…"
GROQ_API_KEY = "…"
APP_URL = "https://TU-APP.streamlit.app"

STRIPE_SECRET_KEY = "sk_live_… o sk_test_…"
STRIPE_PRICE_PREMIUM = "price_…"
STRIPE_PRICE_FAMILIA = "price_…"   # opcional
# Alternativa sin Checkout Session API:
# STRIPE_LINK_PREMIUM = "https://buy.stripe.com/…"
```

### Webhook (obligatorio para activar el plan tras pagar)
Streamlit no recibe webhooks. Despliega `webhook/` en Railway/Render:

```bash
# En el servicio webhook:
STRIPE_SECRET_KEY=…
STRIPE_WEBHOOK_SECRET=whsec_…   # del endpoint en Stripe Dashboard
TURSO_URL=…
TURSO_TOKEN=…
STRIPE_PRICE_PREMIUM=price_…
STRIPE_PRICE_FAMILIA=price_…
```

Stripe Dashboard → Developers → Webhooks → URL:
`https://TU-WEBHOOK/stripe/webhook`  
Eventos: `checkout.session.completed`, `customer.subscription.deleted`

Docker: `webhook/Dockerfile` (raíz del repo como context).

## Diagnóstico
Ver [DIAGNOSTICO.md](./DIAGNOSTICO.md) — por qué no hace falta Electron ahora, y qué se corrigió.
