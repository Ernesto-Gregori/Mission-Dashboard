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

## Google Fit (importante en Streamlit Cloud)
Al dormir la app, el disco se borra. El token OAuth se guarda en la tabla `oauth_tokens` (Turso/SQLite).

1. En local: coloca `credentials_fit.json`, abre Salud → Conectar OAuth  
2. O pega el JSON de `token_fit.json` en Salud → «Pegar token JSON»  
3. Confirma que diga **token en BD**  
4. Opcional: copia también el token a `.streamlit/secrets.toml` bajo `[google_fit_token]`

Si Google Cloud OAuth está en modo **Testing**, el refresh_token puede expirar ~7 días: publica la app o re-vincula.

## Seguridad
- Login con **usuario + contraseña** en todas las páginas
- Contraseñas con PBKDF2 (no texto plano)
- **Crear usuarios:** menú lateral → **Usuarios** (solo rol admin)
- Si ya tenías `APP_PASSWORD` en secrets y no hay usuarios, se crea `admin` automáticamente (entra con usuario `admin` + esa clave)

## Hosting
- Esta app es **Streamlit**. En Streamlit Cloud funciona tal cual.
- **NiceGUI / Flet no corren en Streamlit Cloud** — haría falta otro hosting y reescribir la UI. Ver `DIAGNOSTICO.md`.

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

## Diagnóstico
Ver [DIAGNOSTICO.md](./DIAGNOSTICO.md) — por qué no hace falta Electron ahora, y qué se corrigió.
