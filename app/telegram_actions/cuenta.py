"""Precio de catálogo y estado de la cuenta."""
from __future__ import annotations

from app.telegram_actions.base import Accion, Contexto, Respuesta


def _precio(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.finanzas_receipts import buscar_productos
    from app.db.schema import SUPERMERCADO_LABELS

    q = str(datos["q"])
    if not buscar_productos("", limit=1):
        return Respuesta("El catálogo de precios está vacío. No hay nada que comparar.")
    filas = buscar_productos(q, limit=40)
    if not filas:
        return Respuesta(f"No encontré «{q}» en el catálogo.")
    baratos = sorted(filas, key=lambda r: float(r.get("precio") or 0))[:3]
    lineas = [f"Más baratos para «{q}»"]
    for row in baratos:
        tienda = SUPERMERCADO_LABELS.get(row.get("supermercado"), row.get("supermercado") or "tienda")
        fecha = str(row.get("fecha_actualizacion") or "")[:10]
        lineas.append(f"· ${float(row['precio']):.2f} · {tienda} · {fecha} · {row.get('nombre')}")
    return Respuesta("\n".join(lineas))


def _estado(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.billing import llamadas_ia_mes, plan_vigente
    from app.google_calendar import calendar_disponible
    from app.onboarding import modulos_activos

    plan = plan_vigente(ctx.user)
    mods = ", ".join(sorted(modulos_activos(ctx.user_id))) or "ninguno"
    google = "vinculado" if calendar_disponible() else "sin vincular"
    return Respuesta(
        "\n".join(
            [
                f"Plan: {plan}",
                f"Módulos: {mods}",
                f"Google: {google}",
                f"Llamadas de IA este mes: {llamadas_ia_mes(ctx.user_id)}",
            ]
        )
    )


PRECIO = Accion(
    clave="precio",
    comandos=("/precio",),
    modulo="finanzas",
    ejecutar=_precio,
    uso="Decime el producto. Ejemplo: /precio leche",
    parse=lambda args: {"q": args.strip()[:80]} if args.strip() else None,
)

ESTADO = Accion(
    clave="estado",
    comandos=("/estado",),
    ejecutar=_estado,
    parse=lambda _args: {},
)
