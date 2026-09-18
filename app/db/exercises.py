"""Biblioteca personal de ejercicios (video + análisis IA) y equipamiento."""
from __future__ import annotations

import json
from typing import Any

from app.db.core import ejecutar, invalidate_data_caches

PLATFORMS = ("instagram", "tiktok", "youtube", "facebook", "otro")
STATUSES = ("processing", "ready", "failed")
STALE_PROCESSING_SECONDS = 150
STALE_PROCESSING_MSG = (
    "El análisis se interrumpió (el servidor se reinició o Groq tardó demasiado). "
    "Reintenta en un minuto."
)
NIVELES = ("principiante", "intermedio", "avanzado")
TIPOS_MOVIMIENTO = ("fuerza", "cardio", "movilidad", "core", "pliométrico")
CONFIANZAS = ("alta", "media", "baja")

JSON_LIST_FIELDS = (
    "grupos_musculares_primarios",
    "grupos_musculares_secundarios",
    "equipamiento_detectado",
    "cues_de_forma",
)

EXERCISES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source_video_url TEXT NOT NULL,
    source_platform TEXT CHECK(source_platform IN (
        'instagram', 'tiktok', 'youtube', 'facebook', 'otro'
    )),
    nombre_ejercicio TEXT,
    grupos_musculares_primarios TEXT NOT NULL DEFAULT '[]',
    grupos_musculares_secundarios TEXT NOT NULL DEFAULT '[]',
    equipamiento_detectado TEXT NOT NULL DEFAULT '[]',
    nivel_dificultad TEXT CHECK(nivel_dificultad IN (
        'principiante', 'intermedio', 'avanzado'
    )),
    tipo_movimiento TEXT CHECK(tipo_movimiento IN (
        'fuerza', 'cardio', 'movilidad', 'core', 'pliométrico'
    )),
    series_reps_mencionadas TEXT,
    series_reps_sugeridas TEXT,
    cues_de_forma TEXT NOT NULL DEFAULT '[]',
    duracion_estimada_segundos INTEGER,
    confianza_analisis TEXT CHECK(confianza_analisis IN (
        'alta', 'media', 'baja'
    )),
    status TEXT NOT NULL DEFAULT 'processing' CHECK(status IN (
        'processing', 'ready', 'failed'
    )),
    error_message TEXT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

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
    "CREATE INDEX IF NOT EXISTS idx_exercises_user_status "
    "ON exercises(user_id, status, creado_en DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_equipment_user "
    "ON user_equipment(user_id)",
)


def init_exercise_library(cursor) -> None:
    cursor.execute(EXERCISES_TABLE_SQL)
    cursor.execute(USER_EQUIPMENT_TABLE_SQL)
    for sql in EXERCISE_INDEXES:
        cursor.execute(sql)


def ensure_exercise_tables() -> None:
    ejecutar(EXERCISES_TABLE_SQL)
    ejecutar(USER_EQUIPMENT_TABLE_SQL)
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


def decode_exercise(row: dict) -> dict:
    out = dict(row)
    for key in JSON_LIST_FIELDS:
        out[key] = _as_list(out.get(key))
    return out


def crear_exercise(
    user_id: int,
    source_video_url: str,
    source_platform: str | None = None,
) -> int:
    platform = source_platform if source_platform in PLATFORMS else None
    eid = ejecutar(
        """
        INSERT INTO exercises (user_id, source_video_url, source_platform, status)
        VALUES (?, ?, ?, 'processing')
        """,
        [int(user_id), source_video_url, platform],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return int(eid)


def obtener_exercise(exercise_id: int, user_id: int) -> dict | None:
    rows = (
        ejecutar(
            "SELECT * FROM exercises WHERE id = ? AND user_id = ?",
            [int(exercise_id), int(user_id)],
            fetchall=True,
        )
        or []
    )
    return decode_exercise(rows[0]) if rows else None


def listar_exercises(user_id: int, status: str | None = None) -> list[dict]:
    if status:
        rows = (
            ejecutar(
                """
                SELECT * FROM exercises
                WHERE user_id = ? AND status = ?
                ORDER BY creado_en DESC, id DESC
                """,
                [int(user_id), status],
                fetchall=True,
            )
            or []
        )
    else:
        rows = (
            ejecutar(
                """
                SELECT * FROM exercises
                WHERE user_id = ?
                ORDER BY creado_en DESC, id DESC
                """,
                [int(user_id)],
                fetchall=True,
            )
            or []
        )
    return [decode_exercise(r) for r in rows]


def apply_analysis(exercise_id: int, user_id: int, data: dict) -> None:
    ejecutar(
        """
        UPDATE exercises SET
            nombre_ejercicio = ?,
            grupos_musculares_primarios = ?,
            grupos_musculares_secundarios = ?,
            equipamiento_detectado = ?,
            nivel_dificultad = ?,
            tipo_movimiento = ?,
            series_reps_mencionadas = ?,
            series_reps_sugeridas = ?,
            cues_de_forma = ?,
            duracion_estimada_segundos = ?,
            confianza_analisis = ?,
            status = 'ready',
            error_message = NULL,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        [
            data.get("nombre_ejercicio"),
            json.dumps(data.get("grupos_musculares_primarios") or [], ensure_ascii=False),
            json.dumps(data.get("grupos_musculares_secundarios") or [], ensure_ascii=False),
            json.dumps(data.get("equipamiento_detectado") or [], ensure_ascii=False),
            data.get("nivel_dificultad"),
            data.get("tipo_movimiento"),
            data.get("series_reps_mencionadas"),
            data.get("series_reps_sugeridas"),
            json.dumps(data.get("cues_de_forma") or [], ensure_ascii=False),
            data.get("duracion_estimada_segundos"),
            data.get("confianza_analisis"),
            int(exercise_id),
            int(user_id),
        ],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass


def mark_failed(exercise_id: int, user_id: int, message: str) -> None:
    ejecutar(
        """
        UPDATE exercises SET
            status = 'failed',
            error_message = ?,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        [(message or "Análisis fallido")[:500], int(exercise_id), int(user_id)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass


def mark_processing(exercise_id: int, user_id: int) -> bool:
    row = obtener_exercise(exercise_id, user_id)
    if not row or row.get("status") != "failed":
        return False
    ejecutar(
        """
        UPDATE exercises SET
            status = 'processing',
            error_message = NULL,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        [int(exercise_id), int(user_id)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True


def fail_stale_processing(
    user_id: int,
    older_than_s: int = STALE_PROCESSING_SECONDS,
) -> int:
    """Marca como failed los análisis 'processing' colgados (deploy / timeout)."""
    from datetime import datetime, timezone

    rows = (
        ejecutar(
            """
            SELECT id, actualizado_en, creado_en FROM exercises
            WHERE user_id = ? AND status = 'processing'
            """,
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    now = datetime.now(timezone.utc)
    n = 0
    for row in rows:
        raw = row.get("actualizado_en") or row.get("creado_en")
        ts = _parse_exercise_ts(raw)
        if ts is None:
            continue
        if (now - ts).total_seconds() >= older_than_s:
            mark_failed(int(row["id"]), user_id, STALE_PROCESSING_MSG)
            n += 1
    return n


def _parse_exercise_ts(val):
    from datetime import datetime, timezone

    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip().replace("T", " ").replace("Z", "")
    if "." in s:
        s = s.split(".", 1)[0]
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def actualizar_exercise(exercise_id: int, user_id: int, campos: dict) -> bool:
    if not obtener_exercise(exercise_id, user_id):
        return False
    allowed = {
        "nombre_ejercicio",
        "grupos_musculares_primarios",
        "grupos_musculares_secundarios",
        "equipamiento_detectado",
        "nivel_dificultad",
        "tipo_movimiento",
        "series_reps_mencionadas",
        "series_reps_sugeridas",
        "cues_de_forma",
        "duracion_estimada_segundos",
        "confianza_analisis",
        "source_platform",
    }
    sets: list[str] = []
    vals: list[Any] = []
    for key, val in campos.items():
        if key not in allowed:
            continue
        if key in JSON_LIST_FIELDS:
            sets.append(f"{key} = ?")
            vals.append(json.dumps(_as_list(val), ensure_ascii=False))
        elif key == "duracion_estimada_segundos":
            sets.append(f"{key} = ?")
            if val in (None, ""):
                vals.append(None)
            else:
                vals.append(int(val))
        elif key == "source_platform":
            sets.append(f"{key} = ?")
            vals.append(val if val in PLATFORMS else None)
        elif key in ("nivel_dificultad", "tipo_movimiento", "confianza_analisis"):
            allowed_vals = {
                "nivel_dificultad": NIVELES,
                "tipo_movimiento": TIPOS_MOVIMIENTO,
                "confianza_analisis": CONFIANZAS,
            }[key]
            if val not in allowed_vals:
                continue
            sets.append(f"{key} = ?")
            vals.append(val)
        else:
            sets.append(f"{key} = ?")
            vals.append(val if val not in ("",) else None)
    if not sets:
        return True
    sets.append("actualizado_en = CURRENT_TIMESTAMP")
    vals.extend([int(exercise_id), int(user_id)])
    ejecutar(
        f"UPDATE exercises SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
        vals,
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True


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
