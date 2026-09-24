"""Notas y tiempo de conexión. Categoría y tipo usan valores que acepta la tabla."""
from __future__ import annotations

import re

from app.telegram_actions.base import Accion, Contexto, Respuesta

_MIN = re.compile(r"^(\d{1,3})$")
_CATEGORIA = "Conversaciones_Pendientes"


def _parse_min(args: str) -> dict | None:
    m = _MIN.match((args or "").strip())
    if not m:
        return None
    minutos = int(m.group(1))
    if not 1 <= minutos <= 600:
        return None
    return {"minutos": minutos}


def _nota(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.matrimonio import guardar_nota
    from app.timezone_config import hoy

    texto = str(datos["texto"])
    rid = guardar_nota(_CATEGORIA, texto, "", hoy().isoformat(), 3)
    return Respuesta(
        f"Anoté la nota: «{texto}».",
        entidad_id=int(rid),
        resumen=f"nota «{texto[:80]}»",
    )


def _deshacer_nota(_ctx: Contexto, entidad_id: int, _resumen: str = "") -> bool:
    from app.db.matrimonio import eliminar_nota, obtener_nota

    if obtener_nota(int(entidad_id)) is None:
        return False
    eliminar_nota(int(entidad_id))
    return True


def _conexion(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.matrimonio import registrar_habito
    from app.timezone_config import hoy

    minutos = int(datos["minutos"])
    registrar_habito(hoy().isoformat(), minutos, "Otro", "Yo", 3, "", 0)
    return Respuesta(f"Anoté {minutos} min de conexión.")


NOTA = Accion(
    clave="nota",
    comandos=("/nota",),
    modulo="matrimonio",
    ejecutar=_nota,
    deshacer=_deshacer_nota,
    uso="Escribí la nota. Ejemplo: /nota le gusta el café de la esquina",
    parse=lambda args: {"texto": args.strip()[:500]} if args.strip() else None,
)

CONEXION = Accion(
    clave="conexion",
    comandos=("/conexion",),
    alias=("/conexión",),
    modulo="matrimonio",
    ejecutar=_conexion,
    uso="Decime los minutos. Ejemplo: /conexion 30",
    parse=_parse_min,
)
