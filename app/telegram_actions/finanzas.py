"""Gastos por Telegram."""
from __future__ import annotations

import re

from app.telegram_actions.base import Accion, Contexto, Respuesta

_NUM = r"(?P<num>\d{1,7}(?:[.,]\d{1,2})?)(?![\d.,]*\d)"
_CUR = r"(?:\s*(?:usd|d[oó]lares?|\$))?"
_GASTO_VERB = r"(?:gast[eé]|pagu[eé]|compr[eé])"
# Monto al inicio («35 en super», «gasté 8 en café»), al final de una descripción corta
# («café 8») o con $ en cualquier lugar. Nunca un número suelto en medio de la frase.
AMOUNT_START_RE = re.compile(
    rf"^\s*(?:{_GASTO_VERB}\s+)?\$?\s*{_NUM}{_CUR}\s+(?:(?:en|de)\s+)?(?P<desc>\S.*)$", re.I
)
AMOUNT_END_RE = re.compile(rf"^\s*(?:{_GASTO_VERB}\s+)?(?P<desc>[^\d$]+?)\s+\$?\s*{_NUM}{_CUR}\s*$", re.I)
AMOUNT_DOLLAR_RE = re.compile(rf"\$\s*{_NUM}", re.I)
AMOUNT_MAX_DESC_WORDS = 3
NOT_A_DESC_RE = re.compile(r"^(?:pesos|mxn|am|pm|hs|h|horas?|min|minutos?)\b", re.I)
MONTO_CONFIRMAR = 200.0
USO = "Usá un monto. Ejemplo: /gasto 35 super  (o «35 en supermercado»)."


def _match_amount(text: str) -> tuple[float, str] | None:
    raw = (text or "").strip()
    m = AMOUNT_START_RE.match(raw)
    if m and not NOT_A_DESC_RE.match(m.group("desc")):
        return float(m.group("num").replace(",", ".")), m.group("desc")
    m = AMOUNT_END_RE.match(raw)
    if m and len(m.group("desc").split()) <= AMOUNT_MAX_DESC_WORDS:
        return float(m.group("num").replace(",", ".")), m.group("desc")
    m = AMOUNT_DOLLAR_RE.search(raw)
    if m:
        desc = (raw[: m.start()] + " " + raw[m.end() :]).strip()
        desc = re.sub(rf"^{_GASTO_VERB}\s+|^(?:en|de)\s+|\s+(?:en|de)$", "", desc, flags=re.I)
        return float(m.group("num").replace(",", ".")), desc
    return None


def heuristic_gasto(text: str) -> dict:
    hit = _match_amount(text)
    if not hit or hit[0] <= 0:
        return {"intent": "unknown"}
    monto, desc = hit
    desc = " ".join(desc.split())[:80] or "gasto"
    cat = "necesidades"
    low = text.lower()
    if any(w in low for w in ("cafe", "cine", " ocio", "gusto", "netflix")):
        cat = "deseos"
    if any(w in low for w in ("ahorro", "inver")):
        cat = "ahorro"
    return {"intent": "gasto", "monto": monto, "categoria": cat, "descripcion": desc}


def _validar(data: dict) -> dict | None:
    from app.presupuesto import CATEGORIA_A_SOBRE

    if not isinstance(data, dict) or data.get("intent") not in ("gasto", None):
        return None
    try:
        monto = float(str(data.get("monto") or "0").replace(",", "."))
    except (TypeError, ValueError):
        return None
    if monto <= 0:
        return None
    cat = str(data.get("categoria") or "necesidades")
    if cat not in CATEGORIA_A_SOBRE:
        cat = "necesidades"
    desc = str(data.get("descripcion") or "").strip()[:120]
    return {"intent": "gasto", "monto": monto, "categoria": cat, "descripcion": desc}


def _ejecutar(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.database import agregar_gasto_sobre
    from app.db.schema import GASTO_ORIGEN_TELEGRAM
    from app.presupuesto import CATEGORIA_A_SOBRE
    from app.timezone_config import hoy

    monto = float(datos["monto"])
    sobre, sub = CATEGORIA_A_SOBRE[datos["categoria"]]
    desc = str(datos.get("descripcion") or datos.get("_texto") or "").strip()[:120] or "Gasto Telegram"
    gid = agregar_gasto_sobre(str(hoy()), sobre, sub, desc, monto, origen=GASTO_ORIGEN_TELEGRAM)
    return Respuesta(
        f"Anoté ${monto:.2f} en «{desc}» → sobre {sobre}.",
        entidad_id=int(gid),
        resumen=f"gasto ${monto:.2f} «{desc}»",
    )


def _confirmar(_ctx: Contexto, datos: dict) -> str | None:
    monto = float(datos["monto"])
    if monto < MONTO_CONFIRMAR:
        return None
    desc = str(datos.get("descripcion") or datos.get("_texto") or "").strip()[:60]
    return f"Vas a anotar ${monto:.2f} en «{desc}». Es un monto alto."


def _deshacer(_ctx: Contexto, gasto_id: int) -> bool:
    from app.db.finanzas import eliminar_gasto_sobre

    return bool(eliminar_gasto_sobre(int(gasto_id)))


GASTO = Accion(
    clave="gasto",
    comandos=("/gasto",),
    ejecutar=_ejecutar,
    confirmar=_confirmar,
    deshacer=_deshacer,
    uso=USO,
    llm_campos="monto (número), categoria (necesidades|deseos|ahorro), descripcion (texto corto)",
    parse=lambda args: _validar(heuristic_gasto(args)),
    validar=_validar,
    heuristica=lambda text: _validar(heuristic_gasto(text)),
)
