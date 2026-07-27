"""Motor SQLite/Turso: ejecutar, caches, ensure_database."""
from __future__ import annotations

import functools
import os
import sqlite3
from pathlib import Path

try:
    import libsql
except ImportError:
    libsql = None

try:
    import streamlit as st
except ImportError:  # webhook / scripts sin Streamlit
    st = None

from app.db.adapters import *  # noqa: F401,F403

# app/db/core.py -> parents: db, app, repo
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mission.db"


@functools.lru_cache(maxsize=1)
def _get_turso_config():
    """
    Lee secrets UNA SOLA VEZ y cachea el resultado.
    lru_cache(maxsize=1) = singleton — nunca vuelve a leer secrets.
    """
    url = None
    token = None
    if st is not None:
        try:
            url = st.secrets.get("TURSO_URL")
            token = st.secrets.get("TURSO_TOKEN")
        except Exception:
            pass
    if not url or not token:
        from dotenv import load_dotenv

        load_dotenv()
        url = os.getenv("TURSO_URL")
        token = os.getenv("TURSO_TOKEN")
    return url, token


@functools.lru_cache(maxsize=1)
def usar_turso() -> bool:
    """Cacheado — evalúa UNA SOLA VEZ si Turso está disponible."""
    if libsql is None:
        return False
    url, token = _get_turso_config()
    return bool(url and token)


# Conexión global a Turso — se crea una vez, se reutiliza siempre
_turso_conn = None

def _get_turso_conn():
    """
    Retorna la conexión global a Turso.
    La crea solo la primera vez (patrón singleton).
    """
    global _turso_conn
    if _turso_conn is None:
        url, token = _get_turso_config()
        _turso_conn = libsql.connect(url, auth_token=token)
    return _turso_conn


def ejecutar(sql: str, params: list = None, fetchall: bool = False):
    """
    Wrapper unificado optimizado.
    - Turso: reutiliza conexión persistente (no abre una nueva cada vez)
    - SQLite: igual que antes
    """
    if usar_turso():
        try:
            conn   = _get_turso_conn()          # ← conexión ya abierta
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            if fetchall:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            # Si la conexión murió, resetear y reintentar una vez
            global _turso_conn
            _turso_conn = None
            conn   = _get_turso_conn()
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            if fetchall:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or [])
            if fetchall:
                return [dict(r) for r in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()



def _ejecutar_cached_impl(sql: str, params: tuple = ()) -> list:
    return ejecutar(sql, list(params), fetchall=True) or []


if st is not None:
    ejecutar_cached = st.cache_data(ttl=30)(_ejecutar_cached_impl)
else:
    ejecutar_cached = _ejecutar_cached_impl


def invalidate_data_caches() -> None:
    """Limpia caches de lectura para que los guardados se vean al instante."""
    try:
        ejecutar_cached.clear()
    except Exception:
        pass
    try:
        from app.db import finanzas as _fin
        _fin._calcular_sobres_cached.clear()
    except Exception:
        pass


def ensure_database() -> None:
    """
    init_database() + migración multi-usuario + billing, una vez por sesión.
    En cloud web exige Turso.
    """
    from app.db.schema import init_database
    from app.runtime import require_turso_web

    require_turso_web()

    ready = False
    if st is not None:
        try:
            ready = bool(st.session_state.get("_db_ready"))
        except Exception:
            ready = False
    if ready:
        return

    try:
        init_database()
        try:
            from app.multiuser import migrate_multiuser
            migrate_multiuser()
        except Exception as e:
            print(f"[ensure_database] migrate_multiuser: {e}")
        try:
            from app.billing import ensure_billing_schema
            ensure_billing_schema()
        except Exception as e:
            print(f"[ensure_database] billing: {e}")
        if st is not None:
            try:
                st.session_state["_db_ready"] = True
            except Exception:
                pass
    except Exception:
        init_database()
        try:
            from app.multiuser import migrate_multiuser
            migrate_multiuser()
        except Exception as e:
            print(f"[ensure_database] migrate_multiuser: {e}")
        try:
            from app.billing import ensure_billing_schema
            ensure_billing_schema()
        except Exception as e:
            print(f"[ensure_database] billing: {e}")


def ensure_remote_schema():
    """
    Crea en Turso (o SQLite vía ejecutar) las tablas críticas
    que Finanzas y Auth necesitan, si aún no existen.
    """
    if not usar_turso():
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS ingreso_mensual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            monto_total REAL NOT NULL DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mes, anio)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gastos_sobres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            sobre TEXT NOT NULL,
            subcategoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            es_fijo BOOLEAN DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'admin',
            activo BOOLEAN DEFAULT 1,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider TEXT PRIMARY KEY,
            token_json TEXT NOT NULL,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            accion TEXT NOT NULL,
            entidad TEXT,
            entidad_id TEXT,
            detalle TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS uso_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            llamadas INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, anio, mes)
        )
        """,
    ]
    for sql in statements:
        try:
            ejecutar(sql)
        except Exception as e:
            print(f"ensure_remote_schema: {e}")

    for sql in (
        "ALTER TABLE usuarios ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE usuarios ADD COLUMN plan_expira_en TEXT",
        "ALTER TABLE usuarios ADD COLUMN coach_ia_usado INTEGER DEFAULT 0",
        "ALTER TABLE usuarios ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE usuarios ADD COLUMN stripe_subscription_id TEXT",
    ):
        try:
            ejecutar(sql)
        except Exception:
            pass

    # También en SQLite local (por si ensure_database ya corrió antes del ALTER)
    try:
        ejecutar("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                provider TEXT PRIMARY KEY,
                token_json TEXT NOT NULL,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass
