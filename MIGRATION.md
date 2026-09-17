# Migración Streamlit → FastAPI + HTMX

**Estado: completo.** Streamlit se eliminó del repositorio.

## Hecho en código

- [x] FastAPI + HTMX en `web/`
- [x] `app/tenant.py` solo ContextVar (sin session_state)
- [x] Secrets vía env / `.env` (`app/secrets.py`; lectura opcional de archivo `.streamlit/secrets.toml` por compat)
- [x] Borrado: `Mission_Dashboard.py`, `pages/`, `.streamlit/`, `app/auth.py` (UI Streamlit), workflow keep-awake
- [x] `streamlit` fuera de `requirements.txt` y CI

## Groq / secrets

Usa `GROQ_API_KEY` en el entorno Railway o en `.env` local. No hace falta el panel de Streamlit Cloud.

## Pendiente humano

Ver [CUTOVER.md](./CUTOVER.md) §3: apagar Streamlit Cloud, limpiar secret `STREAMLIT_APP_URL`, y URIs OAuth viejos.
