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


# Palabra → (sobre, subcategoría). Sin match: Supervivencia / Otro y se ofrece cambiar.
_PALABRAS: tuple[tuple[str, str, str], ...] = (
    ("super", "Supervivencia", "Comida"),
    ("supermercado", "Supervivencia", "Comida"),
    ("comida", "Supervivencia", "Comida"),
    ("cafe", "Supervivencia", "Comida"),
    ("almuerzo", "Supervivencia", "Comida"),
    ("desayuno", "Supervivencia", "Comida"),
    ("cena", "Supervivencia", "Comida"),
    ("uber", "Supervivencia", "Transporte"),
    ("taxi", "Supervivencia", "Transporte"),
    ("bus", "Supervivencia", "Transporte"),
    ("gasolina", "Supervivencia", "Transporte"),
    ("luz", "Supervivencia", "Servicios"),
    ("agua", "Supervivencia", "Servicios"),
    ("internet", "Supervivencia", "Servicios"),
    ("deuda", "Supervivencia", "Deuda_Fija"),
    ("tarjeta", "Supervivencia", "Tarjeta_MSI"),
    ("libro", "Ministerio_Extras", "Libros_Cursos"),
    ("libros", "Ministerio_Extras", "Libros_Cursos"),
    ("curso", "Ministerio_Extras", "Libros_Cursos"),
    ("esposa", "Ministerio_Extras", "Cita_Esposa"),
    ("cita", "Ministerio_Extras", "Cita_Esposa"),
    ("ofrenda", "Ministerio_Extras", "Ofrenda_Diezmo"),
    ("diezmo", "Ministerio_Extras", "Ofrenda_Diezmo"),
    ("cine", "Ministerio_Extras", "Personal"),
    ("netflix", "Ministerio_Extras", "Personal"),
    ("ahorro", "Futuro_Hogar", "Ahorro_Emergencia"),
    ("emergencia", "Futuro_Hogar", "Ahorro_Emergencia"),
    ("renta", "Futuro_Hogar", "Fondo_Renta"),
    ("alquiler", "Futuro_Hogar", "Fondo_Renta"),
)
DEFAULT_SOBRE = "Supervivencia"
DEFAULT_SUB = "Otro_Supervivencia"


def catalogo() -> list[tuple[str, str]]:
    from app.db.schema import SOBRES_CONFIG

    return [(sobre, sub) for sobre, cfg in SOBRES_CONFIG.items() for sub in cfg["subcategorias"]]


def clasificar(texto: str) -> tuple[str, str, bool]:
    from app.telegram_actions.briefing import normalize

    palabras = set(normalize(texto).split())
    for palabra, sobre, sub in _PALABRAS:
        if palabra in palabras:
            return sobre, sub, True
    return DEFAULT_SOBRE, DEFAULT_SUB, False


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
    if not isinstance(data, dict) or data.get("intent") not in ("gasto", None):
        return None
    try:
        monto = float(str(data.get("monto") or "0").replace(",", "."))
    except (TypeError, ValueError):
        return None
    if monto <= 0:
        return None
    desc = str(data.get("descripcion") or "").strip()[:120]
    sobre, sub, seguro = clasificar(desc)
    return {
        "intent": "gasto",
        "monto": monto,
        "descripcion": desc,
        "sobre": sobre,
        "subcategoria": sub,
        "seguro": seguro,
    }


def _label(sub: str) -> str:
    from app.presupuesto import SUBCATEGORIAS_LABELS

    return SUBCATEGORIAS_LABELS.get(sub, sub)


def _ejecutar(ctx: Contexto, datos: dict) -> Respuesta:
    from app.database import agregar_gasto_sobre
    from app.db.schema import GASTO_ORIGEN_TELEGRAM
    from app.timezone_config import hoy

    monto = float(datos["monto"])
    sobre, sub = datos["sobre"], datos["subcategoria"]
    desc = str(datos.get("descripcion") or datos.get("_texto") or "").strip()[:120] or "Gasto Telegram"
    gid = int(
        agregar_gasto_sobre(
            str(hoy()),
            sobre,
            sub,
            desc,
            monto,
            origen=GASTO_ORIGEN_TELEGRAM,
            comercio=datos.get("comercio") or None,
            metodo_pago=datos.get("metodo_pago") or None,
        )
    )
    texto = f"Anoté ${monto:.2f} en «{desc}» → {_label(sub)} ({sobre})."
    botones: list[tuple[str, str]] = []
    if not datos.get("seguro"):
        texto += "\nNo estaba claro el rubro; usé el de por defecto. Tocá para cambiarlo."
        botones = [
            (_label(s)[:20], f"c:{gid}:{i}")
            for i, (_sobre, s) in enumerate(catalogo())
            if s != sub
        ]
    return Respuesta(
        texto,
        entidad_id=gid,
        resumen=f"gasto ${monto:.2f} «{desc}»",
        botones=botones,
    )


def cambiar_subcategoria(ctx: Contexto, gasto_id: int, indice: int) -> Respuesta:
    from app.db.finanzas import actualizar_gasto_sobre

    opciones = catalogo()
    if not 0 <= indice < len(opciones):
        return Respuesta("Ese rubro no existe. No cambié nada.", accion="gasto")
    sobre, sub = opciones[indice]
    ok = actualizar_gasto_sobre(int(gasto_id), sobre=sobre, subcategoria=sub)
    if not ok:
        return Respuesta("No encontré ese gasto. No cambié nada.", accion="gasto")
    return Respuesta(f"Listo: ahora está en {_label(sub)} ({sobre}).", accion="gasto")


def _deja_negativo(monto: float, sobre: str) -> bool:
    from app.presupuesto import resumen_mes
    from app.timezone_config import hoy

    dia = hoy()
    sobre_ui = (resumen_mes(dia.month, dia.year).get("sobres") or {}).get(sobre) or {}
    if float(sobre_ui.get("presupuesto") or 0) <= 0:
        return False
    return float(sobre_ui.get("disponible") or 0) - monto < 0


def _confirmar(_ctx: Contexto, datos: dict) -> str | None:
    monto = float(datos["monto"])
    desc = str(datos.get("descripcion") or datos.get("_texto") or "").strip()[:60]
    if monto >= MONTO_CONFIRMAR:
        return f"Vas a anotar ${monto:.2f} en «{desc}». Es un monto alto."
    if _deja_negativo(monto, str(datos.get("sobre") or DEFAULT_SOBRE)):
        return f"Vas a anotar ${monto:.2f} en «{desc}». Deja el sobre en negativo."
    return None


def _deshacer(_ctx: Contexto, gasto_id: int, _resumen: str = "") -> bool:
    from app.db.finanzas import eliminar_gasto_sobre

    return bool(eliminar_gasto_sobre(int(gasto_id)))


GASTO = Accion(
    clave="gasto",
    comandos=("/gasto",),
    modulo="finanzas",
    ejecutar=_ejecutar,
    confirmar=_confirmar,
    deshacer=_deshacer,
    uso=USO,
    llm_campos="monto (número), categoria (necesidades|deseos|ahorro), descripcion (texto corto)",
    parse=lambda args: _validar(heuristic_gasto(args)),
    validar=_validar,
    heuristica=lambda text: _validar(heuristic_gasto(text)),
)


def _parse_monto(args: str) -> float | None:
    m = re.match(r"^\s*\$?\s*(\d{1,7}(?:[.,]\d{1,2})?)\s*$", args or "")
    if not m:
        return None
    monto = float(m.group(1).replace(",", "."))
    return monto if monto > 0 else None


def _ejecutar_ingreso(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.finanzas import guardar_ingreso
    from app.timezone_config import hoy

    dia = hoy()
    ok = guardar_ingreso(dia.month, dia.year, float(datos["monto"]), notas="telegram")
    if not ok:
        return Respuesta("No pude guardar el ingreso.")
    return Respuesta(f"Ingreso de {dia.strftime('%m/%Y')}: ${float(datos['monto']):.0f}.")


def _confirmar_ingreso(_ctx: Contexto, datos: dict) -> str | None:
    from app.db.finanzas import obtener_ingreso
    from app.timezone_config import hoy

    dia = hoy()
    actual = float(obtener_ingreso(dia.month, dia.year) or 0)
    nuevo = float(datos["monto"])
    if actual <= 0 or abs(actual - nuevo) < 0.01:
        return None
    return f"Este mes ya tiene un ingreso de ${actual:.0f}. ¿Lo reemplazo por ${nuevo:.0f}?"


INGRESO = Accion(
    clave="ingreso",
    comandos=("/ingreso",),
    modulo="finanzas",
    ejecutar=_ejecutar_ingreso,
    confirmar=_confirmar_ingreso,
    uso="Usá un monto. Ejemplo: /ingreso 800",
    parse=lambda args: {"monto": m} if (m := _parse_monto(args)) else None,
)


def _ejecutar_saldo(_ctx: Contexto, _datos: dict) -> Respuesta:
    from app.presupuesto import resumen_mes
    from app.revision import semaforo
    from app.timezone_config import hoy

    dia = hoy()
    res = resumen_mes(dia.month, dia.year)
    luz = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
    lineas = [
        f"Saldo {dia.strftime('%m/%Y')}",
        f"Ingreso ${float(res.get('ingreso') or 0):.0f}",
        f"Gastado ${float(res.get('total_gastado') or 0):.0f}",
        f"Disponible ${float(res.get('total_disponible') or 0):.0f}",
    ]
    for key, s in (res.get("sobres") or {}).items():
        mark = luz[semaforo(float(s.get("pct_usado") or 0))]
        lineas.append(
            f"{mark} {s.get('nombre')}: ${float(s.get('disponible') or 0):.0f} de ${float(s.get('presupuesto') or 0):.0f}"
        )
    return Respuesta("\n".join(lineas))


SALDO = Accion(
    clave="saldo",
    comandos=("/saldo",),
    modulo="finanzas",
    ejecutar=_ejecutar_saldo,
    parse=lambda _args: {},
)


def _ejecutar_gastos(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.finanzas import obtener_gastos_sobre
    from app.db.telegram_state import guardar_refs

    rows = obtener_gastos_sobre(limite=7)
    if not rows:
        return Respuesta("No hay gastos anotados.")
    guardar_refs(ctx.user_id, ctx.chat_id, "gasto", [int(g["id"]) for g in rows])
    lineas = ["Últimos gastos. /borrar <n>"]
    for i, g in enumerate(rows, start=1):
        lineas.append(f"{i}. ${float(g.get('monto') or 0):.2f} {g.get('descripcion')} · {g.get('fecha')}")
    return Respuesta("\n".join(lineas))


GASTOS = Accion(
    clave="gastos",
    comandos=("/gastos",),
    modulo="finanzas",
    ejecutar=_ejecutar_gastos,
    parse=lambda _args: {},
)


def _ejecutar_vencimientos(_ctx: Contexto, _datos: dict) -> Respuesta:
    from datetime import timedelta

    from app.presupuesto import listar_recurrentes
    from app.timezone_config import hoy

    dia = hoy()
    recs = listar_recurrentes()
    lineas = ["Vencimientos, próximos 7 días"]
    hay = False
    for i in range(7):
        fecha = dia + timedelta(days=i)
        for r in recs:
            if int(r.get("dia") or 0) != fecha.day:
                continue
            hay = True
            meta = r.get("meta") or {}
            lineas.append(
                f"{fecha.strftime('%d/%m')} {meta.get('emoji', '')} {r.get('titulo')} ${float(r.get('monto') or 0):.2f}"
            )
    if not hay:
        lineas.append("Nada en los próximos 7 días.")
    return Respuesta("\n".join(lineas))


VENCIMIENTOS = Accion(
    clave="vencimientos",
    comandos=("/vencimientos",),
    modulo="finanzas",
    ejecutar=_ejecutar_vencimientos,
    parse=lambda _args: {},
)


def _parse_borrar(args: str) -> dict | None:
    m = re.match(r"^\s*(\d{1,3})\s*$", args or "")
    return {"n": int(m.group(1))} if m else None


def _confirmar_borrar(ctx: Contexto, datos: dict) -> str | None:
    from app.db.telegram_state import buscar_ref

    if buscar_ref(ctx.user_id, ctx.chat_id, "gasto", int(datos["n"])) is None:
        return None
    return f"¿Borro el gasto {datos['n']}? No se puede deshacer."


def _ejecutar_borrar(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.finanzas import eliminar_gasto_sobre
    from app.db.telegram_state import buscar_ref

    gid = buscar_ref(ctx.user_id, ctx.chat_id, "gasto", int(datos["n"]))
    if gid is None:
        return Respuesta("No encuentro ese número. Mandá /gastos y usá el de la lista.")
    if not eliminar_gasto_sobre(gid):
        return Respuesta("No pude borrar ese gasto.")
    return Respuesta(f"Borré el gasto {datos['n']}.")


BORRAR = Accion(
    clave="borrar",
    comandos=("/borrar",),
    modulo="finanzas",
    ejecutar=_ejecutar_borrar,
    confirmar=_confirmar_borrar,
    uso="Primero /gastos, después /borrar 2.",
    parse=_parse_borrar,
)
