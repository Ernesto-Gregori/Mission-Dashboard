"""
runtime.py — App web (Turso). SQLite solo para tests / override explícito.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.logging_config import get_logger

log = get_logger("runtime")


def es_entorno_cloud() -> bool:
    if os.getenv("MISSION_WEB", "").strip() in ("1", "true", "yes"):
        return True
    if os.getenv("STREAMLIT_SHARING_MODE"):
        return True
    # Streamlit Community Cloud mount
    if Path("/mount/src").exists():
        return True
    # Railway / Fly / Render típicos
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("FLY_APP_NAME") or os.getenv("RENDER"):
        return True
    return False


def permitir_sqlite() -> bool:
    """Tests y desarrollo local forzado."""
    if os.getenv("MISSION_ALLOW_SQLITE", "").strip() in ("1", "true", "yes"):
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return False


def require_turso_web() -> None:
    """
    En despliegue web exige Turso. No aplica en pytest ni con MISSION_ALLOW_SQLITE=1.
    """
    if permitir_sqlite():
        return
    if not es_entorno_cloud():
        # Dev local: avisar pero no bloquear (migración gradual)
        return
    try:
        from app.db.core import usar_turso

        if usar_turso():
            return
    except Exception as e:
        log.warning("require_turso_web check: %s", e)

    try:
        import streamlit as st

        st.error(
            "**Mission Dashboard es una app web.** "
            "Configura `TURSO_URL` y `TURSO_TOKEN` en secrets para persistir datos. "
            "El SQLite local del contenedor se borra en cada redeploy."
        )
        st.caption(
            "Si estás migrando, añade los secrets y reinicia. "
            "Para forzar SQLite (no recomendado): `MISSION_ALLOW_SQLITE=1`."
        )
        st.stop()
    except Exception:
        raise RuntimeError(
            "App web requiere TURSO_URL y TURSO_TOKEN en el entorno de producción."
        )
