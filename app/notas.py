"""Notas e ideas, con tareas pendientes del mismo cuaderno."""
from __future__ import annotations

from app.logging_config import get_logger

log = get_logger("notas")

TIPOS = ("nota", "tarea")
ESTADOS = ("abierta", "hecha")
MAX_TITULO = 160
MAX_CUERPO = 4000


def ensure_notas_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS notas_usuario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'nota',
            titulo TEXT NOT NULL,
            cuerpo TEXT,
            estado TEXT NOT NULL DEFAULT 'abierta',
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notas_usuario
        ON notas_usuario(user_id, tipo, estado, actualizado_en DESC)
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.warning("ensure_notas_schema: %s", e)


def _uid(user_id: int | None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def _tipo(valor: str | None) -> str:
    t = (valor or "nota").strip().lower()
    return t if t in TIPOS else "nota"


def _estado(valor: str | None) -> str:
    e = (valor or "abierta").strip().lower()
    return e if e in ESTADOS else "abierta"


def listar(user_id: int | None = None, tipo: str | None = None) -> list[dict]:
    from app.db.core import ejecutar

    ensure_notas_schema()
    uid_i = _uid(user_id)
    if tipo and _tipo(tipo) == tipo:
        return (
            ejecutar(
                """
                SELECT id, tipo, titulo, cuerpo, estado, creado_en, actualizado_en
                FROM notas_usuario
                WHERE user_id = ? AND tipo = ?
                ORDER BY CASE estado WHEN 'abierta' THEN 0 ELSE 1 END,
                         actualizado_en DESC, id DESC
                """,
                [uid_i, tipo],
                fetchall=True,
            )
            or []
        )
    return (
        ejecutar(
            """
            SELECT id, tipo, titulo, cuerpo, estado, creado_en, actualizado_en
            FROM notas_usuario
            WHERE user_id = ?
            ORDER BY CASE estado WHEN 'abierta' THEN 0 ELSE 1 END,
                     actualizado_en DESC, id DESC
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )


def crear(
    titulo: str,
    cuerpo: str = "",
    tipo: str = "nota",
    user_id: int | None = None,
) -> tuple[bool, str]:
    from app.db.core import ejecutar

    ensure_notas_schema()
    titulo = (titulo or "").strip()[:MAX_TITULO]
    if not titulo:
        return False, "Escribe un título."
    ejecutar(
        """
        INSERT INTO notas_usuario (user_id, tipo, titulo, cuerpo, estado)
        VALUES (?, ?, ?, ?, 'abierta')
        """,
        [_uid(user_id), _tipo(tipo), titulo, (cuerpo or "").strip()[:MAX_CUERPO]],
    )
    return True, "Guardado."


def actualizar(
    nota_id: int,
    titulo: str,
    cuerpo: str = "",
    estado: str | None = None,
    user_id: int | None = None,
) -> tuple[bool, str]:
    from app.db.core import ejecutar

    ensure_notas_schema()
    titulo = (titulo or "").strip()[:MAX_TITULO]
    if not titulo:
        return False, "Escribe un título."
    uid_i = _uid(user_id)
    rows = (
        ejecutar(
            "SELECT id FROM notas_usuario WHERE id = ? AND user_id = ?",
            [int(nota_id), uid_i],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return False, "No encontré esa nota."
    ejecutar(
        """
        UPDATE notas_usuario
        SET titulo = ?, cuerpo = ?, estado = ?, actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        [
            titulo,
            (cuerpo or "").strip()[:MAX_CUERPO],
            _estado(estado),
            int(nota_id),
            uid_i,
        ],
    )
    return True, "Nota actualizada."


def marcar(nota_id: int, hecha: bool, user_id: int | None = None) -> bool:
    from app.db.core import ejecutar

    ensure_notas_schema()
    estado = "hecha" if hecha else "abierta"
    ejecutar(
        """
        UPDATE notas_usuario
        SET estado = ?, actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        [estado, int(nota_id), _uid(user_id)],
    )
    return True


def eliminar(nota_id: int, user_id: int | None = None) -> bool:
    from app.db.core import ejecutar

    ensure_notas_schema()
    uid_i = _uid(user_id)
    antes = (
        ejecutar(
            "SELECT id FROM notas_usuario WHERE id = ? AND user_id = ?",
            [int(nota_id), uid_i],
            fetchall=True,
        )
        or []
    )
    if not antes:
        return False
    ejecutar(
        "DELETE FROM notas_usuario WHERE id = ? AND user_id = ?",
        [int(nota_id), uid_i],
    )
    return True
