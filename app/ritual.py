"""Ritual de mañana — gratitud, intención y hábitos del día."""
from __future__ import annotations

import re
import unicodedata

from app.logging_config import get_logger
from app.timezone_config import hora_actual, hoy as _hoy

log = get_logger("ritual")

MAX_TEXTO = 800
MAX_LABEL = 40
_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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


def listar_habitos_config(user_id: int | None = None) -> list[dict]:
    """Todos los hábitos del usuario, activos primero (incluye archivados)."""
    from app.db.core import ejecutar

    return (
        ejecutar(
            """
            SELECT clave, label, emoji, hora, COALESCE(activo, 1) AS activo, orden
            FROM habitos_config
            WHERE user_id = ?
            ORDER BY COALESCE(activo, 1) DESC, orden, label
            """,
            [_uid(user_id)],
            fetchall=True,
        )
        or []
    )


def _clave_desde(label: str) -> str:
    base = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")[:20] or "habito"


def _limpiar(label: str, emoji: str, hora: str) -> tuple[str | None, dict]:
    label = (label or "").strip()[:MAX_LABEL]
    if not label:
        return "El hábito necesita un nombre.", {}
    hora = (hora or "").strip()[:5]
    if hora and not _HORA_RE.match(hora):
        return "La hora debe tener formato HH:MM.", {}
    return None, {
        "label": label,
        "emoji": (emoji or "").strip()[:4] or "⭐",
        "hora": hora or "—",
    }


def crear_habito(label: str, emoji: str = "", hora: str = "", user_id: int | None = None) -> tuple[bool, str]:
    from app.db.core import ejecutar, invalidate_data_caches

    error, datos = _limpiar(label, emoji, hora)
    if error:
        return False, error
    uid_i = _uid(user_id)
    existentes = listar_habitos_config(uid_i)
    usadas = {h["clave"] for h in existentes}
    if any(h["label"].lower() == datos["label"].lower() for h in existentes):
        return False, "Ya tienes un hábito con ese nombre (revisa los archivados)."
    base = clave = _clave_desde(datos["label"])
    n = 2
    while clave in usadas:
        clave = f"{base[:17]}_{n}"
        n += 1
    orden = max((int(h.get("orden") or 0) for h in existentes), default=0) + 1
    ejecutar(
        """
        INSERT INTO habitos_config (user_id, clave, label, emoji, hora, activo, orden)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        [uid_i, clave, datos["label"], datos["emoji"], datos["hora"], orden],
    )
    invalidate_data_caches()
    return True, f"Hábito «{datos['label']}» agregado."


def actualizar_habito(
    clave: str, label: str, emoji: str = "", hora: str = "", user_id: int | None = None
) -> tuple[bool, str]:
    from app.db.core import ejecutar, invalidate_data_caches

    error, datos = _limpiar(label, emoji, hora)
    if error:
        return False, error
    uid_i = _uid(user_id)
    if not any(h["clave"] == clave for h in listar_habitos_config(uid_i)):
        return False, "Hábito no encontrado."
    ejecutar(
        """
        UPDATE habitos_config SET label = ?, emoji = ?, hora = ?
        WHERE user_id = ? AND clave = ?
        """,
        [datos["label"], datos["emoji"], datos["hora"], uid_i, clave],
    )
    invalidate_data_caches()
    return True, "Hábito actualizado."


def set_habito_activo(clave: str, activo: bool, user_id: int | None = None) -> bool:
    """Archivar en lugar de borrar: el historial diario usa la clave."""
    from app.db.core import ejecutar, invalidate_data_caches

    ejecutar(
        "UPDATE habitos_config SET activo = ? WHERE user_id = ? AND clave = ?",
        [1 if activo else 0, _uid(user_id), clave],
    )
    invalidate_data_caches()
    return True


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
