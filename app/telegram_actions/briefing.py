"""Briefing del día (agenda, hábitos, gastos recientes)."""
from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from app.telegram_actions.base import Accion, Contexto, Respuesta

# Mensaje completo (sin acentos ni signos), no subcadena: «agendar…» no es briefing.
BRIEFING_PHRASES = frozenset(
    {
        "briefing", "briefing de hoy", "agenda", "agenda de hoy", "mi agenda",
        "resumen", "resumen de hoy", "foco", "foco de hoy", "hoy", "hoy que",
        "que hay hoy", "que tengo hoy", "mi dia",
    }
)


def normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w\s]", " ", raw).split())


def is_briefing_request(text: str) -> bool:
    return normalize(text) in BRIEFING_PHRASES


def build_briefing(user_id: int) -> str:
    from app.calendar_sync import items_foco
    from app.db.core import ejecutar
    from app.timezone_config import hoy as hoy_fn

    dia = str(hoy_fn())
    items = items_foco(dia, user_id=user_id)
    lineas = [f"Foco {dia}"]
    hab = [i for i in items if i.get("kind") == "habito"]
    if hab:
        bits = []
        for h in hab[:8]:
            mark = "✓" if h.get("completado") else "·"
            bits.append(f"{mark} {h.get('titulo')}")
        lineas.append("Hábitos: " + "; ".join(bits))
    evs = [i for i in items if i.get("kind") in ("evento", "matrimonio", "enfoque")]
    if evs:
        bits = [f"{(e.get('hora_inicio') or '—')[:5]} {e.get('titulo')}" for e in evs[:8]]
        lineas.append("Agenda: " + "; ".join(bits))
    else:
        lineas.append("Agenda: sin eventos.")
    ent = next((i for i in items if i.get("kind") == "entrenamiento"), None)
    if ent:
        lineas.append(str(ent.get("titulo")))
    corte = (hoy_fn() - timedelta(days=7)).isoformat()
    gastos = (
        ejecutar(
            """
            SELECT descripcion, monto, sobre FROM gastos_sobres
            WHERE user_id = ? AND fecha >= ?
            ORDER BY fecha DESC, id DESC LIMIT 5
            """,
            [int(user_id), corte],
            fetchall=True,
        )
        or []
    )
    if gastos:
        bits = [f"{g.get('monto'):g} {g.get('descripcion')}" for g in gastos]
        lineas.append("Gastos 7d: " + "; ".join(bits))
    else:
        lineas.append("Gastos 7d: ninguno.")
    return "\n".join(lineas)[:1500]


def _ejecutar(ctx: Contexto, _datos: dict) -> Respuesta:
    return Respuesta(build_briefing(ctx.user_id))


BRIEFING = Accion(
    clave="briefing",
    comandos=("/briefing", "/hoy", "/agenda"),
    ejecutar=_ejecutar,
    llm_campos="sin campos (el usuario pide el resumen o la agenda del día)",
    parse=lambda args: {},
    patron=lambda text: {} if is_briefing_request(text) else None,
    validar=lambda data: {} if data.get("intent") == "briefing" else None,
)
