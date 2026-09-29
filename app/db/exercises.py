"""Equipamiento del usuario y rutina semanal armada por el coach IA."""
from __future__ import annotations

import json
from typing import Any

from app.db.core import ejecutar, invalidate_data_caches

USER_EQUIPMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    equipment_name TEXT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, equipment_name)
)
"""

EXERCISE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_user_equipment_user "
    "ON user_equipment(user_id)",
)

ROUTINES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exercise_routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    dias_semana INTEGER NOT NULL,
    minutos_sesion INTEGER NOT NULL,
    equipamiento TEXT NOT NULL DEFAULT '[]',
    notas_usuario TEXT,
    plan_json TEXT NOT NULL,
    notas_coach TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def init_exercise_tables(cursor) -> None:
    cursor.execute(USER_EQUIPMENT_TABLE_SQL)
    cursor.execute(ROUTINES_TABLE_SQL)
    for sql in EXERCISE_INDEXES:
        cursor.execute(sql)


def ensure_exercise_tables() -> None:
    ejecutar(USER_EQUIPMENT_TABLE_SQL)
    ejecutar(ROUTINES_TABLE_SQL)
    for sql in EXERCISE_INDEXES:
        try:
            ejecutar(sql)
        except Exception:
            pass


def _as_list(val: Any) -> list[str]:
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    try:
        data = json.loads(val)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def listar_equipment(user_id: int) -> list[dict]:
    return (
        ejecutar(
            """
            SELECT * FROM user_equipment
            WHERE user_id = ?
            ORDER BY equipment_name COLLATE NOCASE
            """,
            [int(user_id)],
            fetchall=True,
        )
        or []
    )


def agregar_equipment(user_id: int, name: str) -> tuple[bool, str]:
    nombre = (name or "").strip()
    if not nombre:
        return False, "Escribe el nombre del equipamiento."
    if len(nombre) > 80:
        return False, "El nombre es demasiado largo."
    try:
        ejecutar(
            """
            INSERT INTO user_equipment (user_id, equipment_name)
            VALUES (?, ?)
            """,
            [int(user_id), nombre],
        )
    except Exception:
        return False, "Ese equipamiento ya está en tu lista."
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True, "Equipamiento guardado."


def borrar_equipment(equipment_id: int, user_id: int) -> bool:
    ejecutar(
        "DELETE FROM user_equipment WHERE id = ? AND user_id = ?",
        [int(equipment_id), int(user_id)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True


def decode_routine(row: dict) -> dict:
    out = dict(row)
    out["equipamiento"] = _as_list(out.get("equipamiento"))
    try:
        plan = json.loads(out.get("plan_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        plan = {}
    if not isinstance(plan, dict):
        plan = {}
    out["plan"] = plan
    return out


def obtener_routine(user_id: int) -> dict | None:
    rows = (
        ejecutar(
            "SELECT * FROM exercise_routines WHERE user_id = ?",
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    return decode_routine(rows[0]) if rows else None


def guardar_routine(
    user_id: int,
    dias_semana: int,
    minutos_sesion: int,
    equipamiento: list[str],
    plan: dict,
    notas_usuario: str | None = None,
    notas_coach: str | None = None,
) -> int:
    payload = json.dumps(plan, ensure_ascii=False)
    equipo = json.dumps(_as_list(equipamiento), ensure_ascii=False)
    notas_u = (notas_usuario or "").strip()[:500] or None
    notas_c = (notas_coach or plan.get("notas_coach") or "").strip()[:800] or None
    ejecutar(
        """
        INSERT INTO exercise_routines (
            user_id, dias_semana, minutos_sesion, equipamiento,
            notas_usuario, plan_json, notas_coach, actualizado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            dias_semana = excluded.dias_semana,
            minutos_sesion = excluded.minutos_sesion,
            equipamiento = excluded.equipamiento,
            notas_usuario = excluded.notas_usuario,
            plan_json = excluded.plan_json,
            notas_coach = excluded.notas_coach,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [
            int(user_id),
            int(dias_semana),
            int(minutos_sesion),
            equipo,
            notas_u,
            payload,
            notas_c,
        ],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    row = obtener_routine(user_id)
    return int(row["id"]) if row else 0


def borrar_routine(user_id: int) -> bool:
    if not obtener_routine(user_id):
        return False
    ejecutar(
        "DELETE FROM exercise_routines WHERE user_id = ?",
        [int(user_id)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True
