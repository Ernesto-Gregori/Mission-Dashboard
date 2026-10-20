"""Hora local en la que cada persona quiere Fit y el catálogo de precios."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.logging_config import get_logger

log = get_logger("sync_horario")

HORA_FIT = 22
HORA_PRECIOS = 3
VENTANA_MIN = 90


def ensure_sync_schema() -> None:
    from app.db.core import ejecutar

    try:
        ejecutar(
            """
            CREATE TABLE IF NOT EXISTS sync_horario (
                user_id INTEGER PRIMARY KEY,
                hora_fit INTEGER NOT NULL DEFAULT 22,
                hora_precios INTEGER NOT NULL DEFAULT 3,
                fit_activo INTEGER NOT NULL DEFAULT 1,
                precios_activo INTEGER NOT NULL DEFAULT 1,
                ultimo_fit TEXT,
                ultimo_precios TEXT
            )
            """
        )
    except Exception as e:
        log.warning("ensure_sync_schema: %s", e)


def _hora(valor, default: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return default
    if 0 <= n <= 23:
        return n
    return default


def leer(user_id: int) -> dict:
    from app.db.core import ejecutar

    ensure_sync_schema()
    rows = (
        ejecutar(
            """
            SELECT hora_fit, hora_precios, fit_activo, precios_activo,
                   ultimo_fit, ultimo_precios
            FROM sync_horario WHERE user_id = ?
            """,
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return {
            "hora_fit": HORA_FIT,
            "hora_precios": HORA_PRECIOS,
            "fit_activo": 1,
            "precios_activo": 1,
            "ultimo_fit": None,
            "ultimo_precios": None,
        }
    row = rows[0]
    return {
        "hora_fit": _hora(row.get("hora_fit"), HORA_FIT),
        "hora_precios": _hora(row.get("hora_precios"), HORA_PRECIOS),
        "fit_activo": 1 if int(row.get("fit_activo") if row.get("fit_activo") is not None else 1) else 0,
        "precios_activo": 1 if int(row.get("precios_activo") if row.get("precios_activo") is not None else 1) else 0,
        "ultimo_fit": row.get("ultimo_fit"),
        "ultimo_precios": row.get("ultimo_precios"),
    }


def guardar(
    user_id: int,
    *,
    hora_fit: int,
    hora_precios: int,
    fit_activo: bool = True,
    precios_activo: bool = True,
) -> dict:
    from app.db.core import ejecutar

    ensure_sync_schema()
    actual = leer(user_id)
    ejecutar(
        """
        INSERT INTO sync_horario
            (user_id, hora_fit, hora_precios, fit_activo, precios_activo,
             ultimo_fit, ultimo_precios)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            hora_fit = excluded.hora_fit,
            hora_precios = excluded.hora_precios,
            fit_activo = excluded.fit_activo,
            precios_activo = excluded.precios_activo
        """,
        [
            int(user_id),
            _hora(hora_fit, HORA_FIT),
            _hora(hora_precios, HORA_PRECIOS),
            1 if fit_activo else 0,
            1 if precios_activo else 0,
            actual.get("ultimo_fit"),
            actual.get("ultimo_precios"),
        ],
    )
    return leer(user_id)


def marcar(user_id: int, campo: str, cuando: str) -> None:
    from app.db.core import ejecutar

    if campo not in ("ultimo_fit", "ultimo_precios"):
        return
    ensure_sync_schema()
    actual = leer(int(user_id))
    ultimo_fit = cuando if campo == "ultimo_fit" else actual.get("ultimo_fit")
    ultimo_precios = cuando if campo == "ultimo_precios" else actual.get("ultimo_precios")
    ejecutar(
        """
        INSERT INTO sync_horario
            (user_id, hora_fit, hora_precios, fit_activo, precios_activo,
             ultimo_fit, ultimo_precios)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            ultimo_fit = excluded.ultimo_fit,
            ultimo_precios = excluded.ultimo_precios
        """,
        [
            int(user_id),
            actual["hora_fit"],
            actual["hora_precios"],
            actual["fit_activo"],
            actual["precios_activo"],
            ultimo_fit,
            ultimo_precios,
        ],
    )


def en_ventana(hora_objetivo: int, ahora: datetime, ultimo: str | None) -> bool:
    """True si toca correr y hoy todavía no corrió, dentro de 90 min de la hora."""
    if ultimo:
        try:
            hecho = datetime.fromisoformat(str(ultimo)[:19])
        except ValueError:
            hecho = None
        if hecho is not None and hecho.date() == ahora.date():
            return False
    inicio = ahora.replace(hour=int(hora_objetivo), minute=0, second=0, microsecond=0)
    return inicio <= ahora < inicio + timedelta(minutes=VENTANA_MIN)
