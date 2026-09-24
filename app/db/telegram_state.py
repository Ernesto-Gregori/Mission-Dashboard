"""Estado corto del bot de Telegram: confirmaciones pendientes y última acción (para /deshacer).

Tablas creadas en ``app.telegram.ensure_telegram_schema``. Todo se filtra por chat_id + user_id:
una confirmación o un /deshacer nunca cruza de chat ni de usuario.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

from app.db.core import ejecutar

PENDING_TTL_MIN = 10
DESHACER_TTL_MIN = 30
RECORDATORIO_DEFAULT_MIN = 30
RECORDATORIO_OPCIONES = (0, 10, 15, 30, 60)


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


def recordatorio_min(user_id: int) -> int:
    """Minutos de anticipación de los recordatorios; 0 = apagados."""
    rows = ejecutar(
        "SELECT recordatorio_min FROM telegram_prefs WHERE user_id = ?",
        [int(user_id)],
        fetchall=True,
    ) or []
    if not rows or rows[0]["recordatorio_min"] is None:
        return RECORDATORIO_DEFAULT_MIN
    return int(rows[0]["recordatorio_min"])


def guardar_refs(user_id: int, chat_id: str, tipo: str, ids: list[int]) -> None:
    """Números cortos 1..N de este chat. Reemplaza la lista anterior del mismo tipo."""
    from app.timezone_config import ahora

    stamp = _stamp(ahora())
    ejecutar(
        "DELETE FROM telegram_refs WHERE chat_id = ? AND user_id = ? AND tipo = ?",
        [str(chat_id), int(user_id), tipo],
    )
    for n, eid in enumerate(ids, start=1):
        ejecutar(
            """
            INSERT INTO telegram_refs (chat_id, user_id, tipo, n, entidad_id, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [str(chat_id), int(user_id), tipo, n, int(eid), stamp],
        )


def buscar_ref(user_id: int, chat_id: str, tipo: str, n: int) -> int | None:
    rows = ejecutar(
        """
        SELECT entidad_id FROM telegram_refs
         WHERE chat_id = ? AND user_id = ? AND tipo = ? AND n = ?
        """,
        [str(chat_id), int(user_id), tipo, int(n)],
        fetchall=True,
    ) or []
    return int(rows[0]["entidad_id"]) if rows else None


BRIEFING_EXTRAS = ("salud", "teologia", "matrimonio")


def briefing_extra(user_id: int) -> set[str]:
    """Secciones sensibles del briefing. Vacío por defecto: fe, pareja y salud no salen."""
    rows = ejecutar(
        "SELECT briefing_extra FROM telegram_prefs WHERE user_id = ?",
        [int(user_id)],
        fetchall=True,
    ) or []
    if not rows or not rows[0].get("briefing_extra"):
        return set()
    pedidas = {p.strip() for p in str(rows[0]["briefing_extra"]).split(",") if p.strip()}
    return pedidas & set(BRIEFING_EXTRAS)


def guardar_briefing_extra(user_id: int, claves: list[str]) -> bool:
    limpias = [c for c in claves if c in BRIEFING_EXTRAS]
    if len(limpias) != len(claves):
        return False
    ejecutar(
        """
        INSERT INTO telegram_prefs (user_id, briefing_extra) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET briefing_extra = excluded.briefing_extra
        """,
        [int(user_id), ",".join(limpias)],
    )
    return True


def prefs_briefing(user_id: int) -> dict:
    rows = ejecutar(
        "SELECT briefing_activo, briefing_hora, briefing_extra, silencio_hasta, ultimo_briefing FROM telegram_prefs WHERE user_id = ?",
        [int(user_id)],
        fetchall=True,
    ) or []
    row = rows[0] if rows else {}
    return {
        "activo": bool(int(row.get("briefing_activo") or 0)),
        "hora": str(row.get("briefing_hora") or "07:00")[:5],
        "extra": briefing_extra(user_id),
        "silencio_hasta": str(row.get("silencio_hasta") or ""),
        "ultimo": str(row.get("ultimo_briefing") or ""),
    }


def guardar_prefs_briefing(user_id: int, *, activo: bool, hora: str, extra: list[str]) -> bool:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora or ""):
        return False
    if any(c not in BRIEFING_EXTRAS for c in extra):
        return False
    ejecutar(
        """
        INSERT INTO telegram_prefs (user_id, briefing_activo, briefing_hora, briefing_extra)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            briefing_activo = excluded.briefing_activo,
            briefing_hora = excluded.briefing_hora,
            briefing_extra = excluded.briefing_extra
        """,
        [int(user_id), 1 if activo else 0, hora, ",".join(extra)],
    )
    return True


def poner_silencio(user_id: int, hasta: str) -> None:
    """hasta = fecha ISO inclusive, o '' para reanudar."""
    ejecutar(
        """
        INSERT INTO telegram_prefs (user_id, silencio_hasta) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET silencio_hasta = excluded.silencio_hasta
        """,
        [int(user_id), hasta or None],
    )


def marcar_briefing_enviado(user_id: int, dia: str) -> None:
    ejecutar(
        """
        INSERT INTO telegram_prefs (user_id, ultimo_briefing) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET ultimo_briefing = excluded.ultimo_briefing
        """,
        [int(user_id), dia],
    )


def guardar_recordatorio_min(user_id: int, minutos: int) -> bool:
    if int(minutos) not in RECORDATORIO_OPCIONES:
        return False
    ejecutar(
        """
        INSERT INTO telegram_prefs (user_id, recordatorio_min) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET recordatorio_min = excluded.recordatorio_min
        """,
        [int(user_id), int(minutos)],
    )
    return True
