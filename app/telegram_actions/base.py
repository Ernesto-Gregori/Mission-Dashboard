"""Contrato de las acciones del bot de Telegram."""
from __future__ import annotations

from dataclasses import dataclass
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


def _nada(_arg) -> dict | None:
    return None


@dataclass
class Accion:
    """Una acción del bot.

    - ``parse(args)``: argumentos de un comando → datos, o ``None`` (se responde ``uso``).
    - ``patron(texto)``: coincidencia determinística de alta confianza para texto libre.
    - ``validar(json_llm)``: acepta la salida del LLM solo si cumple el esquema de la acción.
    - ``heuristica(texto)``: respaldo cuando el LLM no clasifica (o Groq está caído).
    """

    clave: str
    ejecutar: Callable[[Contexto, dict], Respuesta]
    comandos: tuple[str, ...] = ()
    alias: tuple[str, ...] = ()
    modulo: str | None = None
    confirmar: bool = False
    uso: str = ""
    llm_campos: str | None = None
    parse: Callable[[str], dict | None] = _nada
    patron: Callable[[str], dict | None] = _nada
    validar: Callable[[dict], dict | None] = _nada
    heuristica: Callable[[str], dict | None] = _nada
