"""Briefing del día, armado con los módulos activos."""
from __future__ import annotations

import re
import unicodedata

from app.telegram_actions.base import Accion, Contexto, Respuesta

# Mensaje completo (sin acentos ni signos), no subcadena: «agendar…» no es briefing.
BRIEFING_PHRASES = frozenset(
    {
        "briefing", "briefing de hoy",
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
    """Secciones según módulos activos. Fe, pareja y salud solo con opt-in."""
    from app.db.telegram_state import briefing_extra
    from app.onboarding import modulo_activo
    from app.timezone_config import hoy as hoy_fn

    dia = hoy_fn()
    extra = briefing_extra(user_id)
    lineas = [f"Foco {dia.isoformat()}"]
    if modulo_activo("agenda", user_id):
        lineas.append(_linea_agenda(user_id, dia))
    lineas.append(_linea_habitos(user_id, dia))
    if modulo_activo("deep_work", user_id):
        lineas.append(_linea_enfoque(dia))
    if modulo_activo("finanzas", user_id):
        lineas.append(_linea_vencimientos(dia))
        lineas.append(_linea_sobre())
    if "salud" in extra and modulo_activo("salud", user_id):
        lineas.append(_linea_salud(user_id))
    if "teologia" in extra and modulo_activo("teologia", user_id):
        lineas.append(_linea_oracion())
    if "matrimonio" in extra and modulo_activo("matrimonio", user_id):
        lineas.append(_linea_pareja(dia))
    return "\n".join(linea for linea in lineas if linea)[:1500]


def _linea_agenda(user_id: int, dia) -> str:
    from app.calendar_sync import items_foco

    evs = [i for i in items_foco(str(dia), user_id=user_id) if i.get("kind") == "evento"]
    if not evs:
        return "Agenda: sin eventos."
    bits = [f"{(e.get('hora_inicio') or '—')[:5]} {e.get('titulo')}" for e in evs[:6]]
    return "Agenda: " + "; ".join(bits)


def _linea_habitos(user_id: int, dia) -> str:
    from app.ritual import habitos_hoy, listar_habitos

    hechos = habitos_hoy(user_id, str(dia))
    pendientes = [h["label"] for h in listar_habitos(user_id) if not hechos.get(h["clave"])]
    if not pendientes:
        return "Hábitos: al día."
    return "Hábitos pendientes: " + "; ".join(pendientes[:6])


def _linea_enfoque(dia) -> str:
    from app.db.deep_work import bloques_para_fecha

    bloques = bloques_para_fecha(str(dia))
    if not bloques:
        return "Enfoque: sin bloques hoy."
    bits = [f"{str(b.get('hora_inicio') or '')[:5]} {b.get('nombre')} ({b.get('estado')})" for b in bloques[:4]]
    return "Enfoque: " + "; ".join(bits)


def _linea_vencimientos(dia) -> str:
    from datetime import timedelta

    from app.presupuesto import listar_recurrentes

    proximos = []
    for i in range(3):
        fecha = dia + timedelta(days=i)
        for r in listar_recurrentes():
            if int(r.get("dia") or 0) == fecha.day:
                proximos.append(f"{r.get('titulo')} {fecha.strftime('%d/%m')}")
    if not proximos:
        return "Vencimientos: ninguno en 3 días."
    return "Vencimientos: " + "; ".join(proximos[:4])


def _linea_sobre() -> str:
    from app.presupuesto import resumen_mes
    from app.revision import semaforo
    from app.timezone_config import hoy

    dia = hoy()
    sobres = (resumen_mes(dia.month, dia.year).get("sobres") or {}).values()
    con_presupuesto = [s for s in sobres if float(s.get("presupuesto") or 0) > 0]
    if not con_presupuesto:
        return ""
    peor = max(con_presupuesto, key=lambda s: float(s.get("pct_usado") or 0))
    luz = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}[semaforo(float(peor.get("pct_usado") or 0))]
    return f"Sobre más justo: {luz} {peor.get('nombre')} ${float(peor.get('disponible') or 0):.0f}"


def _linea_salud(user_id: int) -> str:
    from app.db.exercises import obtener_routine
    from app.db.salud import obtener_registro_salud
    from app.timezone_config import hoy

    partes = []
    reg = obtener_registro_salud(str(hoy())) or {}
    if reg.get("horas_sueno") is not None:
        partes.append(f"sueño {float(reg['horas_sueno']):g} h")
    rutina = obtener_routine(user_id)
    if rutina:
        partes.append(f"rutina {rutina.get('dias_semana') or '?'} días")
    return "Salud: " + (", ".join(partes) if partes else "sin registro hoy.")


def _linea_oracion() -> str:
    from app.db.teologia import pedidos_para_hoy

    pedidos = pedidos_para_hoy()
    if not pedidos:
        return "Oración: nada para hoy."
    return "Oración: " + "; ".join(str(p.get("titulo")) for p in pedidos[:3])


def _linea_pareja(dia) -> str:
    from app.db.core import ejecutar
    from app.tenant import uid

    rows = ejecutar(
        "SELECT hora, titulo FROM matrimonio_citas WHERE user_id = ? AND fecha = ? ORDER BY hora LIMIT 2",
        [uid(), str(dia)],
        fetchall=True,
    ) or []
    if not rows:
        return "Pareja: sin cita hoy."
    return "Pareja: " + "; ".join(f"{str(r.get('hora') or '')[:5]} {r.get('titulo')}" for r in rows)


def _ejecutar(ctx: Contexto, _datos: dict) -> Respuesta:
    return Respuesta(build_briefing(ctx.user_id))


def _parse_silencio(args: str) -> dict | None:
    raw = (args or "").strip()
    if raw == "":
        return {"dias": 1}
    if re.fullmatch(r"\d{1,2}", raw) and int(raw) <= 30:
        return {"dias": int(raw)}
    return None


def _ejecutar_silencio(ctx: Contexto, datos: dict) -> Respuesta:
    from datetime import timedelta

    from app.db.telegram_state import poner_silencio
    from app.timezone_config import hoy

    dias = int(datos["dias"])
    if dias == 0:
        poner_silencio(ctx.user_id, "")
        return Respuesta("Listo: el briefing de la mañana vuelve cuando le toque.")
    hasta = hoy() + timedelta(days=dias - 1)
    poner_silencio(ctx.user_id, hasta.isoformat())
    return Respuesta(f"Silencio hasta el {hasta.isoformat()} inclusive. /silencio 0 lo reanuda.")


SILENCIO = Accion(
    clave="silencio",
    comandos=("/silencio",),
    ejecutar=_ejecutar_silencio,
    uso="Usá /silencio, /silencio 3 o /silencio 0 para reanudar.",
    parse=_parse_silencio,
)


BRIEFING = Accion(
    clave="briefing",
    comandos=("/briefing", "/hoy"),
    ejecutar=_ejecutar,
    llm_campos="sin campos (el usuario pide el resumen o la agenda del día)",
    parse=lambda args: {},
    patron=lambda text: {} if is_briefing_request(text) else None,
    validar=lambda data: {} if data.get("intent") == "briefing" else None,
)
