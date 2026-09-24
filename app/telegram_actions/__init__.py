"""Registro de acciones del bot de Telegram (una por área, en su archivo)."""
from __future__ import annotations

from app.telegram_actions.agenda import AGENDA, CANCELAR, MOVER, TAREA
from app.telegram_actions.base import Accion, Contexto, Respuesta
from app.telegram_actions.briefing import BRIEFING
from app.telegram_actions.enfoque import ENFOQUE
from app.telegram_actions.finanzas import BORRAR, GASTO, GASTOS, INGRESO, SALDO, VENCIMIENTOS
from app.telegram_actions.habitos import HABITOS, HECHO
from app.telegram_actions.salud import EJERCICIO, ENERGIA, SALUD, SUENO

# El orden importa: patrones y heurísticas se prueban en este orden.
REGISTRO: list[Accion] = [
    AGENDA, BRIEFING, GASTO, INGRESO, SALDO, GASTOS, VENCIMIENTOS, BORRAR,
    HABITOS, HECHO, SUENO, ENERGIA, EJERCICIO, SALUD, ENFOQUE, MOVER, CANCELAR, TAREA,
]


def por_comando(cmd: str) -> Accion | None:
    return next((a for a in REGISTRO if cmd in a.comandos or cmd in a.alias), None)


def por_clave(clave: str) -> Accion | None:
    return next((a for a in REGISTRO if a.clave == clave), None)


def disponible(accion: Accion, user_id: int | None = None) -> bool:
    if accion.modulo is None:
        return True
    from app.onboarding import modulo_activo

    return modulo_activo(accion.modulo, user_id)


def activas(user_id: int | None = None) -> list[Accion]:
    return [a for a in REGISTRO if disponible(a, user_id)]


__all__ = [
    "Accion",
    "Contexto",
    "REGISTRO",
    "Respuesta",
    "activas",
    "disponible",
    "por_clave",
    "por_comando",
]
