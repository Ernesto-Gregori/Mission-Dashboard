"""Ritual de mañana — gratitud, intención y hábitos del día."""
from __future__ import annotations

from app.logging_config import get_logger
from app.timezone_config import hora_actual, hoy as _hoy

log = get_logger("ritual")

MAX_TEXTO = 800


def ensure_ritual_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS ritual_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            gratitud TEXT,
            intencion TEXT,
            completado INTEGER NOT NULL DEFAULT 0,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, fecha)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ritual_user_fecha
        ON ritual_diario(user_id, fecha DESC)
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.warning("ensure_ritual_schema: %s", e)


def _uid(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def listar_habitos(user_id: int | None = None) -> list[dict]:
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    return (
        ejecutar(
            """
            SELECT clave, label, emoji, hora, COALESCE(activo, 1) AS activo, orden
            FROM habitos_config
            WHERE user_id = ? AND COALESCE(activo, 1) = 1
            ORDER BY orden, label
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )


def habitos_hoy(user_id: int | None = None, fecha: str | None = None) -> dict[str, bool]:
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    dia = fecha or str(_hoy())
    rows = (
        ejecutar(
            """
            SELECT habito_clave, completado
            FROM habitos_diarios_v2
            WHERE user_id = ? AND fecha = ?
            """,
            [uid_i, dia],
            fetchall=True,
        )
        or []
    )
    return {r["habito_clave"]: bool(int(r.get("completado") or 0)) for r in rows}


def marcar_habitos(
    claves: list[str],
    user_id: int | None = None,
    fecha: str | None = None,
) -> None:
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    dia = fecha or str(_hoy())
    permitidas = {h["clave"] for h in listar_habitos(uid_i)}
    hechos = {c for c in claves if c in permitidas}
    hora = hora_actual()
    for h in listar_habitos(uid_i):
        clave = h["clave"]
        done = 1 if clave in hechos else 0
        hora_c = hora if done else None
        rows = (
            ejecutar(
                """
                SELECT id FROM habitos_diarios_v2
                WHERE user_id = ? AND fecha = ? AND habito_clave = ?
                """,
                [uid_i, dia, clave],
                fetchall=True,
            )
            or []
        )
        if rows:
            ejecutar(
                """
                UPDATE habitos_diarios_v2
                SET completado = ?, hora_completado = ?
                WHERE id = ? AND user_id = ?
                """,
                [done, hora_c, rows[0]["id"], uid_i],
            )
        else:
            ejecutar(
                """
                INSERT INTO habitos_diarios_v2
                    (user_id, fecha, habito_clave, completado, hora_completado)
                VALUES (?, ?, ?, ?, ?)
                """,
                [uid_i, dia, clave, done, hora_c],
            )
    try:
        invalidate_data_caches()
    except Exception:
        pass


def obtener_ritual(user_id: int | None = None, fecha: str | None = None) -> dict:
    ensure_ritual_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    dia = fecha or str(_hoy())
    rows = (
        ejecutar(
            """
            SELECT gratitud, intencion, completado, fecha
            FROM ritual_diario
            WHERE user_id = ? AND fecha = ?
            """,
            [uid_i, dia],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return {
            "fecha": dia,
            "gratitud": "",
            "intencion": "",
            "completado": False,
        }
    r = rows[0]
    return {
        "fecha": r.get("fecha") or dia,
        "gratitud": r.get("gratitud") or "",
        "intencion": r.get("intencion") or "",
        "completado": bool(int(r.get("completado") or 0)),
    }


def guardar_ritual(
    gratitud: str,
    intencion: str,
    claves_habito: list[str],
    user_id: int | None = None,
    fecha: str | None = None,
) -> dict:
    ensure_ritual_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    dia = fecha or str(_hoy())
    grat = (gratitud or "").strip()[:MAX_TEXTO]
    inte = (intencion or "").strip()[:MAX_TEXTO]
    marcar_habitos(claves_habito, user_id=uid_i, fecha=dia)
    ejecutar(
        """
        INSERT INTO ritual_diario
            (user_id, fecha, gratitud, intencion, completado)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
            gratitud = excluded.gratitud,
            intencion = excluded.intencion,
            completado = 1
        """,
        [uid_i, dia, grat, inte],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    log.info("ritual.guardado user_id=%s fecha=%s", uid_i, dia)
    return obtener_ritual(uid_i, dia)
