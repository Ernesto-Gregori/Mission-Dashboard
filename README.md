# Mission Dashboard
Sistema de gestión de vida personal — uso privado.

## Stack
- Streamlit + SQLite → Turso (opcional)
- Groq / Gemini IA
- Google Fit + Google Calendar OAuth2

## Setup local
1. Crear `.env` con `GROQ_API_KEY=` (y opcionalmente `TURSO_URL`, `TURSO_TOKEN`)
2. `pip install -r requirements.txt`
3. `streamlit run Mission_Dashboard.py`
4. En el primer arranque, crea tu usuario y contraseña (se guardan con hash en la BD)

## Seguridad
- Login con **usuario + contraseña** en todas las páginas
- Contraseñas con PBKDF2 (no texto plano)
- **Crear usuarios:** menú lateral → **Usuarios** (solo rol admin)
- Si ya tenías `APP_PASSWORD` en secrets y no hay usuarios, se crea `admin` automáticamente (entra con usuario `admin` + esa clave)

## Hosting
- Esta app es **Streamlit**. En Streamlit Cloud funciona tal cual.
- **NiceGUI / Flet no corren en Streamlit Cloud** — haría falta otro hosting y reescribir la UI. Ver `DIAGNOSTICO.md`.

## Estabilidad / recargas
- Los formularios (`st.form`) evitan recargar al escribir (Finanzas, Bitácora, Deep Work, hábitos, chat).
- La BD se inicializa una sola vez por sesión (`ensure_database`).
- Tras guardar se limpian caches para ver el cambio al instante.

## Persistencia (importante)
- Todas las escrituras (incluida **Finanzas**) pasan por `ejecutar()` → misma BD
- Con Turso configurado, los datos persisten en la nube
- Sin Turso, se usa `data/mission.db` (ignorado por git)

## Diagnóstico
Ver [DIAGNOSTICO.md](./DIAGNOSTICO.md) — por qué no hace falta Electron ahora, y qué se corrigió.
