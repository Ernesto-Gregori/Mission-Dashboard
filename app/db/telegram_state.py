"""Estado corto del bot de Telegram: confirmaciones pendientes y última acción (para /deshacer).

Tablas creadas en ``app.telegram.ensure_telegram_schema``. Todo se filtra por chat_id + user_id:
una confirmación o un /deshacer nunca cruza de chat ni de usuario.
"""
from __future__ import annotations

import json
from datetime import timedelta

from app.db.core import ejecutar

PENDING_TTL_MIN = 10
DESHACER_TTL_MIN = 30


def _stamp(dt) -> str:
    return dt.isoformat(timespec="seconds")


def crear_pendiente(user_id: int, chat_id: str, accion: str, payload: dict) -> int:
    from app.timezone_config import ahora

    now = ahora()
    ejecutar("DELETE FROM telegram_pending WHERE chat_id = ?", [str(chat_id)])
    return int(
        ejecutar(
            """
            INSERT INTO telegram_pending (user_id, chat_id, accion, payload_json, expira_en, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                int(user_id),
                str(chat_id),
                accion,
                json.dumps(payload, ensure_ascii=False, default=str),
                _stamp(now + timedelta(minutes=PENDING_TTL_MIN)),
                _stamp(now),
            ],
        )
    )


def tomar_pendiente(user_id: int, chat_id: str, pending_id: int | None = None) -> tuple[str, dict | None] | None:
    """Consume (borra) la confirmación. Devuelve ``(accion, payload)``; payload ``None`` si venció.

    Sin ``pending_id`` toma la última del chat (respuesta «sí/no» por texto).
    """
    from app.timezone_config import ahora

    sql = "SELECT * FROM telegram_pending WHERE chat_id = ? AND user_id = ?"
    params: list = [str(chat_id), int(user_id)]
    if pending_id is not None:
        sql += " AND id = ?"
        params.append(int(pending_id))
    rows = ejecutar(sql + " ORDER BY id DESC LIMIT 1", params, fetchall=True) or []
    if not rows:
        return None
    row = rows[0]
    ejecutar("DELETE FROM telegram_pending WHERE id = ?", [int(row["id"])])
    if str(row["expira_en"]) < _stamp(ahora()):
        return row["accion"], None
    return row["accion"], json.loads(row["payload_json"] or "{}")


def hay_pendiente(user_id: int, chat_id: str) -> bool:
    rows = ejecutar(
        "SELECT 1 FROM telegram_pending WHERE chat_id = ? AND user_id = ? LIMIT 1",
        [str(chat_id), int(user_id)],
        fetchall=True,
    )
    return bool(rows)


def registrar_ultima(user_id: int, chat_id: str, accion: str, entidad_id: int, resumen: str) -> None:
    from app.timezone_config import ahora

    now = ahora()
    ejecutar("DELETE FROM telegram_last_action WHERE chat_id = ?", [str(chat_id)])
    ejecutar(
        """
        INSERT INTO telegram_last_action (chat_id, user_id, accion, entidad_id, resumen, expira_en, creado_en)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            str(chat_id),
            int(user_id),
            accion,
            int(entidad_id),
            resumen[:200],
            _stamp(now + timedelta(minutes=DESHACER_TTL_MIN)),
            _stamp(now),
        ],
    )


def tomar_ultima(user_id: int, chat_id: str) -> dict | None:
    """Consume la última acción del chat si no venció."""
    from app.timezone_config import ahora

    rows = ejecutar(
        "SELECT * FROM telegram_last_action WHERE chat_id = ? AND user_id = ?",
        [str(chat_id), int(user_id)],
        fetchall=True,
    ) or []
    ejecutar(
        "DELETE FROM telegram_last_action WHERE chat_id = ? AND user_id = ?",
        [str(chat_id), int(user_id)],
    )
    if not rows or str(rows[0]["expira_en"]) < _stamp(ahora()):
        return None
    return rows[0]
