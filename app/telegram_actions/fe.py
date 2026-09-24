"""Pedidos de oración. No hay comando de devocional: ese formulario se completa en la web."""
from __future__ import annotations

import re

from app.telegram_actions.base import Accion, Contexto, Respuesta

_N = re.compile(r"^(\d{1,3})$")


def _orar(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.teologia import agregar_pedido

    titulo = str(datos["titulo"])
    rid = agregar_pedido(titulo, "", "Personal", 3, [])
    if not rid:
        return Respuesta("No pude guardar el pedido. No escribí nada.")
    return Respuesta(
        f"Anoté el pedido «{titulo}».",
        entidad_id=int(rid),
        resumen=f"pedido «{titulo}»",
    )


def _deshacer_pedido(_ctx: Contexto, entidad_id: int, _resumen: str = "") -> bool:
    from app.db.teologia import eliminar_pedido

    return bool(eliminar_pedido(int(entidad_id)))


def _oraciones(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.telegram_state import guardar_refs
    from app.db.teologia import obtener_pedidos

    pedidos = [p for p in obtener_pedidos("Activo")][:8]
    if not pedidos:
        return Respuesta("No hay pedidos activos. Ejemplo: /orar salud de mamá")
    guardar_refs(ctx.user_id, ctx.chat_id, "pedido", [int(p["id"]) for p in pedidos])
    lineas = ["Oraciones"]
    for n, pedido in enumerate(pedidos, start=1):
        lineas.append(f"{n}. {pedido['titulo']}")
    lineas.append("Para cerrar uno: /respondida 1")
    return Respuesta("\n".join(lineas))


def _parse_n(args: str) -> dict | None:
    m = _N.match((args or "").strip())
    return {"n": int(m.group(1))} if m else None


def _confirmar(ctx: Contexto, datos: dict) -> str | None:
    from app.db.telegram_state import buscar_ref

    if buscar_ref(ctx.user_id, ctx.chat_id, "pedido", int(datos["n"])) is None:
        return None
    return f"¿Marco el pedido {datos['n']} como respondido?"


def _respondida(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.telegram_state import buscar_ref
    from app.db.teologia import actualizar_estado_pedido, obtener_pedidos

    n = int(datos["n"])
    pedido_id = buscar_ref(ctx.user_id, ctx.chat_id, "pedido", n)
    if pedido_id is None:
        return Respuesta("Ese número no está en la lista. Mirá /oraciones. No cambié nada.")
    titulo = next((p["titulo"] for p in obtener_pedidos() if int(p["id"]) == pedido_id), f"#{n}")
    if not actualizar_estado_pedido(pedido_id, "Respondido"):
        return Respuesta("No pude actualizar el pedido. No cambié nada.")
    return Respuesta(f"Marqué «{titulo}» como respondido.")


ORAR = Accion(
    clave="orar",
    comandos=("/orar",),
    modulo="teologia",
    ejecutar=_orar,
    deshacer=_deshacer_pedido,
    uso="Escribí el pedido. Ejemplo: /orar salud de mamá",
    parse=lambda args: {"titulo": args.strip()[:200]} if args.strip() else None,
)

ORACIONES = Accion(
    clave="oraciones",
    comandos=("/oraciones",),
    modulo="teologia",
    ejecutar=_oraciones,
    parse=lambda _args: {},
)

RESPONDIDA = Accion(
    clave="respondida",
    comandos=("/respondida",),
    modulo="teologia",
    ejecutar=_respondida,
    confirmar=_confirmar,
    uso="Primero /oraciones, después /respondida 1.",
    parse=_parse_n,
)
