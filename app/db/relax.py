"""Quita CHECKs que fijan la vida de una sola cuenta (sobres y citas)."""
from __future__ import annotations

import re

_TABLAS = ("gastos_sobres", "matrimonio_citas", "matrimonio_notas", "matrimonio_habitos")
_IDENT = re.compile(r"^[a-z_]+$")


def relajar_cheques_personales() -> None:
    from app.db.core import ejecutar

    for nombre in _TABLAS:
        try:
            _reconstruir_sin_check(ejecutar, nombre)
        except Exception as e:
            print(f"[relax] {nombre}: {e}")


def _reconstruir_sin_check(ejecutar, nombre: str) -> None:
    if not _IDENT.match(nombre):
        return
    rows = ejecutar(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        [nombre],
        fetchall=True,
    ) or []
    sql = (rows[0].get("sql") or "") if rows else ""
    if "CHECK" not in sql.upper():
        return
    info = ejecutar(f"PRAGMA table_info({nombre})", fetchall=True) or []
    if not info:
        return
    cols = []
    defs = []
    for col in info:
        name = str(col.get("name") or "")
        if not _IDENT.match(name):
            return
        cols.append(name)
        if int(col.get("pk") or 0) == 1:
            defs.append(f"{name} INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        typ = str(col.get("type") or "TEXT") or "TEXT"
        nn = " NOT NULL" if int(col.get("notnull") or 0) else ""
        dflt = col.get("dflt_value")
        default = f" DEFAULT {dflt}" if dflt is not None else ""
        defs.append(f"{name} {typ}{nn}{default}")
    nuevo = f"{nombre}__new"
    antes = ejecutar(f"SELECT COUNT(*) AS n FROM {nombre}", fetchall=True) or [{"n": 0}]
    ejecutar("PRAGMA foreign_keys=OFF")
    ejecutar(f"DROP TABLE IF EXISTS {nuevo}")
    ejecutar(f"CREATE TABLE {nuevo} ({', '.join(defs)})")
    lista = ", ".join(cols)
    ejecutar(f"INSERT INTO {nuevo} ({lista}) SELECT {lista} FROM {nombre}")
    despues = ejecutar(f"SELECT COUNT(*) AS n FROM {nuevo}", fetchall=True) or [{"n": -1}]
    if int(antes[0].get("n") or 0) != int(despues[0].get("n") or 0):
        ejecutar(f"DROP TABLE IF EXISTS {nuevo}")
        ejecutar("PRAGMA foreign_keys=ON")
        raise RuntimeError(f"conteo distinto al relajar {nombre}")
    ejecutar(f"DROP TABLE {nombre}")
    ejecutar(f"ALTER TABLE {nuevo} RENAME TO {nombre}")
    ejecutar("PRAGMA foreign_keys=ON")
    if nombre == "gastos_sobres":
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_gastos_sobres_fecha ON gastos_sobres(fecha DESC)",
            "CREATE INDEX IF NOT EXISTS idx_gastos_user ON gastos_sobres(user_id, fecha DESC)",
        ):
            try:
                ejecutar(sql)
            except Exception:
                pass
