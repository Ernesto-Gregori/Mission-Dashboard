"""Bloques de enfoque del día. Requiere el módulo deep_work."""
from __future__ import annotations

from app.telegram_actions.base import Accion, Contexto, Respuesta

_ESTADO = {"c": "Completado", "p": "Parcial", "o": "Postergado"}


def _bloques():
    from app.db.deep_work import bloques_para_fecha
    from app.timezone_config import hoy

    return bloques_para_fecha(str(hoy()))


def _listar(_ctx: Contexto, _datos: dict) -> Respuesta:
    bloques = _bloques()
    if not bloques:
        return Respuesta("Hoy no tenés bloques de enfoque. Se arman en la app → Enfoque.")
    lineas = ["Enfoque de hoy"]
    botones = []
    for b in bloques:
        hora = str(b.get("hora_inicio") or "")[:5]
        lineas.append(f"{hora} {b.get('nombre')} · {b.get('estado')}")
        nombre = str(b.get("nombre") or "Bloque")[:12]
        bid = int(b["id"])
        botones.append((f"{nombre} ✓", f"e:{bid}:c"))
        botones.append((f"{nombre} ~", f"e:{bid}:p"))
        botones.append((f"{nombre} →", f"e:{bid}:o"))
    lineas.append("✓ Completado · ~ Parcial · → Postergado")
    return Respuesta("\n".join(lineas), botones=botones)


def marcar_bloque(bloque_id: int, codigo: str) -> Respuesta:
    from app.db.deep_work import registrar_sesion
    from app.timezone_config import hoy

    estado = _ESTADO.get(codigo)
    if estado is None:
        return Respuesta("Ese botón ya no sirve. No cambié nada.", accion="enfoque")
    bloque = next((b for b in _bloques() if int(b["id"]) == int(bloque_id)), None)
    if bloque is None:
        return Respuesta("Ese bloque no es de hoy. No cambié nada.", accion="enfoque")
    if not registrar_sesion(str(hoy()), int(bloque_id), estado):
        return Respuesta("No pude guardar el estado.", accion="enfoque")
    return Respuesta(f"{bloque.get('nombre')}: {estado}.", accion="enfoque")


ENFOQUE = Accion(
    clave="enfoque",
    comandos=("/enfoque",),
    modulo="deep_work",
    ejecutar=_listar,
    parse=lambda _args: {},
)
