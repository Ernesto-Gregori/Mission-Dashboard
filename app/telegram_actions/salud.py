"""Sueño, energía y ejercicio por Telegram. Requiere el módulo salud."""
from __future__ import annotations

import re

from app.telegram_actions.base import Accion, Contexto, Respuesta

_HORAS = re.compile(r"^\s*(\d{1,2}(?:[.,]\d)?)\b")
_CALIDAD = re.compile(r"calidad\s+(\d)", re.I)
_MIN = re.compile(r"(\d{1,3})\s*(?:min|minutos)?", re.I)


def _guardar(campos: dict) -> bool:
    from app.db.salud import actualizar_registro_salud_parcial
    from app.timezone_config import hoy

    return actualizar_registro_salud_parcial(str(hoy()), campos)


def _parse_sueno(args: str) -> dict | None:
    m = _HORAS.match(args or "")
    if not m:
        return None
    horas = float(m.group(1).replace(",", "."))
    if not 0 < horas <= 24:
        return None
    datos = {"horas_sueno": horas}
    cal = _CALIDAD.search(args)
    if cal:
        calidad = int(cal.group(1))
        if not 1 <= calidad <= 5:
            return None
        datos["calidad_sueno"] = calidad
    return datos


def _ejecutar_sueno(_ctx: Contexto, datos: dict) -> Respuesta:
    if not _guardar(datos):
        return Respuesta("No pude anotar el sueño.")
    texto = f"Anoté {datos['horas_sueno']:g} h de sueño"
    if datos.get("calidad_sueno"):
        texto += f", calidad {datos['calidad_sueno']}/5"
    return Respuesta(texto + ". El resto del día quedó igual.")


SUENO = Accion(
    clave="sueno",
    comandos=("/sueno", "/sueño"),
    modulo="salud",
    ejecutar=_ejecutar_sueno,
    uso="Usá las horas. Ejemplo: /sueno 7.5 calidad 4",
    parse=_parse_sueno,
)


def _parse_energia(args: str) -> dict | None:
    m = re.match(r"^\s*(?:(manana|mañana|tarde|noche)\s+)?(\d)\s*$", args or "", re.I)
    if not m or not 1 <= int(m.group(2)) <= 5:
        return None
    momento = (m.group(1) or "manana").lower().replace("ñ", "n")
    return {f"energia_{momento}": int(m.group(2))}


def _ejecutar_energia(_ctx: Contexto, datos: dict) -> Respuesta:
    if not _guardar(datos):
        return Respuesta("No pude anotar la energía.")
    clave, valor = next(iter(datos.items()))
    return Respuesta(f"Anoté energía de {clave.removeprefix('energia_')} en {valor}/5.")


ENERGIA = Accion(
    clave="energia",
    comandos=("/energia",),
    modulo="salud",
    ejecutar=_ejecutar_energia,
    uso="Usá un número del 1 al 5. Ejemplo: /energia 4  o  /energia tarde 3",
    parse=_parse_energia,
)


def _parse_ejercicio(args: str) -> dict | None:
    raw = (args or "").strip()
    if not raw:
        return None
    mins = _MIN.search(raw)
    duracion = int(mins.group(1)) if mins else None
    if duracion is not None and not 1 <= duracion <= 300:
        return None
    tipo = _MIN.sub("", raw)
    tipo = re.sub(r"\b(min|minutos)\b", "", tipo, flags=re.I)
    tipo = " ".join(tipo.split())[:40]
    datos = {"hizo_ejercicio": True, "tipo_ejercicio": tipo or "Ejercicio"}
    if duracion:
        datos["duracion_minutos"] = duracion
    return datos


def _ejecutar_ejercicio(_ctx: Contexto, datos: dict) -> Respuesta:
    if not _guardar(datos):
        return Respuesta("No pude anotar el ejercicio.")
    texto = f"Anoté ejercicio: {datos['tipo_ejercicio']}"
    if datos.get("duracion_minutos"):
        texto += f", {datos['duracion_minutos']} min"
    return Respuesta(texto + ".")


EJERCICIO = Accion(
    clave="ejercicio",
    comandos=("/ejercicio",),
    modulo="salud",
    ejecutar=_ejecutar_ejercicio,
    uso="Decime qué hiciste. Ejemplo: /ejercicio pierna 45 min",
    parse=_parse_ejercicio,
)


def _ejecutar_resumen(_ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.salud import calcular_promedios, calcular_racha_objetivo, obtener_registros_rango

    regs = obtener_registros_rango(7)
    prom = calcular_promedios(regs)
    if not prom:
        return Respuesta("Todavía no hay registros de salud en los últimos 7 días.")
    return Respuesta(
        "\n".join(
            [
                f"Salud, últimos {prom['total_dias']} días con registro",
                f"Sueño {prom['avg_sueno']:.1f} h · calidad {prom['avg_calidad_sueno']:.1f}",
                f"Energía mañana {prom['avg_energia_manana']:.1f}/5",
                f"Ejercicio {prom['dias_ejercicio']} días",
                f"Racha del objetivo: {calcular_racha_objetivo()} días",
            ]
        )
    )


def _rutina(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.exercises import obtener_routine
    from app.timezone_config import hoy

    rutina = obtener_routine(ctx.user_id)
    if not rutina:
        return Respuesta("No tenés una rutina guardada. Se arma en la app, en Salud.")
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    hoy_nombre = dias[hoy().weekday()]
    plan = rutina.get("plan") or {}
    del_dia = plan.get(hoy_nombre) or plan.get(hoy_nombre.lower()) or plan.get(str(hoy().weekday()))
    lineas = [
        f"Rutina: {rutina.get('dias_semana')} días · {rutina.get('minutos_sesion')} min",
    ]
    if isinstance(del_dia, dict):
        lineas.append(str(del_dia.get("titulo") or del_dia.get("nombre") or "Sesión de hoy"))
    elif isinstance(del_dia, str) and del_dia.strip():
        lineas.append(del_dia.strip())
    elif isinstance(del_dia, list) and del_dia:
        lineas.append(", ".join(str(x) for x in del_dia[:4]))
    return Respuesta("\n".join(lineas))


RUTINA = Accion(
    clave="rutina",
    comandos=("/rutina",),
    modulo="salud",
    ejecutar=_rutina,
    parse=lambda _args: {},
)


SALUD = Accion(
    clave="salud",
    comandos=("/salud",),
    modulo="salud",
    ejecutar=_ejecutar_resumen,
    parse=lambda _args: {},
)
