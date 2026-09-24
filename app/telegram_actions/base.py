"""Contrato de las acciones del bot de Telegram."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Contexto:
    user: dict
    chat_id: str
    parse_fn: Callable[[str], dict] | None = None

    @property
    def user_id(self) -> int:
        return int(self.user["id"])


@dataclass
class Respuesta:
    texto: str
    accion: str = ""
    teclado: bool = False
    botones: list[tuple[str, str]] = field(default_factory=list)
    # Si la acción escribió algo reversible: id de la entidad y resumen para /deshacer.
    entidad_id: int | None = None
    resumen: str = ""


def _nada(_arg) -> dict | None:
    return None


@dataclass
class Accion:
    """Una acción del bot.

    - ``parse(args)``: argumentos de un comando → datos, o ``None`` (se responde ``uso``).
    - ``patron(texto)``: coincidencia determinística de alta confianza para texto libre.
    - ``validar(json_llm)``: acepta la salida del LLM solo si cumple el esquema de la acción.
    - ``heuristica(texto)``: respaldo cuando el LLM no clasifica (o Groq está caído).
    - ``confirmar(ctx, datos)``: pregunta a mostrar antes de ejecutar, o ``None`` si no hace falta.
    - ``deshacer(ctx, entidad_id)``: revierte lo que ``ejecutar`` guardó (para /deshacer).
    """

    clave: str
    ejecutar: Callable[[Contexto, dict], Respuesta]
    comandos: tuple[str, ...] = ()
    alias: tuple[str, ...] = ()
    modulo: str | None = None
    confirmar: Callable[[Contexto, dict], str | None] | None = None
    deshacer: Callable[[Contexto, int], bool] | None = None
    uso: str = ""
    llm_campos: str | None = None
    parse: Callable[[str], dict | None] = _nada
    patron: Callable[[str], dict | None] = _nada
    validar: Callable[[dict], dict | None] = _nada
    heuristica: Callable[[str], dict | None] = _nada
