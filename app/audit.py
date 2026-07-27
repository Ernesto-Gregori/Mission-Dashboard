"""
audit.py — Registro de acciones sensibles (quién cambió qué).
"""
from __future__ import annotations

import json
from typing import Any

from app.logging_config import get_logger

log = get_logger("audit")


def ensure_audit_table() -> None:
    """Crea audit_log si no existe (SQLite o Turso vía ejecutar)."""
    from app.db.core import ejecutar

    ejecutar(
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
        """
    )
    try:
        ejecutar(
            "CREATE INDEX IF NOT EXISTS idx_audit_creado ON audit_log(creado_en DESC)"
        )
    except Exception:
        pass


def _actor() -> tuple[int | None, str | None]:
    try:
        import streamlit as st

        user = st.session_state.get("user") or {}
        uid = user.get("id")
        return (int(uid) if uid is not None else None, user.get("username"))
    except Exception:
        pass
    try:
        from app.tenant import uid

        return uid(), None
    except Exception:
        return None, None


def registrar(
    accion: str,
    entidad: str | None = None,
    entidad_id: Any = None,
    detalle: dict | list | str | None = None,
    user_id: int | None = None,
    username: str | None = None,
) -> None:
    """
    Inserta una fila en audit_log. Nunca lanza: un fallo de auditoría
    no debe romper la operación de negocio.
    """
    try:
        ensure_audit_table()
        from app.db.core import ejecutar

        if user_id is None and username is None:
            user_id, username = _actor()

        if isinstance(detalle, (dict, list)):
            detalle_s = json.dumps(detalle, ensure_ascii=False, default=str)
        elif detalle is None:
            detalle_s = None
        else:
            detalle_s = str(detalle)

        eid = None if entidad_id is None else str(entidad_id)
        ejecutar(
            """
            INSERT INTO audit_log
                (user_id, username, accion, entidad, entidad_id, detalle)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [user_id, username, accion, entidad, eid, detalle_s],
        )
    except Exception as e:
        log.warning("audit.registrar falló (%s): %s", accion, e)


def listar_auditoria(limite: int = 100, entidad: str | None = None) -> list:
    from app.db.core import ejecutar

    ensure_audit_table()
    if entidad:
        return (
            ejecutar(
                """
                SELECT * FROM audit_log
                WHERE entidad = ?
                ORDER BY id DESC LIMIT ?
                """,
                [entidad, int(limite)],
                fetchall=True,
            )
            or []
        )
    return (
        ejecutar(
            """
            SELECT * FROM audit_log
            ORDER BY id DESC LIMIT ?
            """,
            [int(limite)],
            fetchall=True,
        )
        or []
    )
