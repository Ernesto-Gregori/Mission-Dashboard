"""Tareas por Telegram (dashboard + Google Calendar)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.telegram_actions.base import Accion, Contexto, Respuesta

TIME_RE = re.compile(
    r"\ba\s+las?\s+(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>am|pm)?\b"
    r"|\b(?P<h2>\d{1,2}):(?P<m2>\d{2})\s*(?P<ap2>am|pm)?\b"
    r"|\b(?P<h3>\d{1,2})\s*(?P<ap3>am|pm)\b",
    re.I,
)
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TAREA_VERB_RE = re.compile(
    r"^\s*(?:agendar|agend[aá]|agend[aá]me|record[aá]me|recordarme|recu[eé]rdame)\b\s*", re.I
)
USO = "Usá un título y hora. Ejemplo: /tarea mañana 5pm llamar al banco."
DURACION_MIN = 60


def find_time(text: str) -> tuple[str, tuple[int, int]] | None:
    """Hora solo si es explícita: «5pm», «16:30», «a las 8». Un número suelto no es hora."""
    for m in TIME_RE.finditer(text or ""):
        idx = next(i for i in (1, 2, 3) if m.group(f"h{i}") is not None)
        h = int(m.group(f"h{idx}"))
        mi = int(m.group(f"m{idx}") or 0) if idx != 3 else 0
        ap = (m.group(f"ap{idx}") or "").lower()
        if ap and not 1 <= h <= 12:
            continue
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if h > 23 or mi > 59:
            continue
        return f"{h:02d}:{mi:02d}", m.span()
    return None


def explicit_time(text: str) -> str | None:
    found = find_time(text)
    return found[0] if found else None


_DIAS = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}
_MES = "ene feb mar abr may jun jul ago sep oct nov dic".split()


def _cuando(texto: str) -> tuple[date, str | None, int | None]:
    """Fecha, hora fija si «en N horas», y duración en minutos si se dijo."""
    from app.telegram_actions.briefing import normalize
    from app.timezone_config import ahora

    low = normalize(texto)
    ahora_dt = ahora()
    fecha = ahora_dt.date()
    hora_fija = None
    if "pasado manana" in low:
        fecha = fecha + timedelta(days=2)
    elif "manana" in low:
        fecha = fecha + timedelta(days=1)
    else:
        for nombre, idx in _DIAS.items():
            if re.search(rf"\b{nombre}\b", low):
                fecha = fecha + timedelta(days=(idx - fecha.weekday()) % 7)
                break
        else:
            dia = re.search(r"\bel (\d{1,2})\b", low)
            if dia and 1 <= int(dia.group(1)) <= 31:
                n = int(dia.group(1))
                try:
                    candidata = fecha.replace(day=n)
                except ValueError:
                    candidata = None
                if candidata is not None:
                    fecha = candidata if candidata >= fecha else candidata.replace(month=fecha.month % 12 + 1)
    horas = re.search(r"\ben (\d{1,2}) horas?\b", low)
    if horas:
        destino = ahora_dt + timedelta(hours=int(horas.group(1)))
        fecha, hora_fija = destino.date(), destino.strftime("%H:%M")
    duracion = None
    mins = re.search(r"\b(\d{1,3})\s*(?:min|minutos)\b", low)
    hs = re.search(r"\b(\d{1,2})\s*(?:h|hora|horas)\b", low)
    if mins:
        duracion = int(mins.group(1))
    elif hs and not horas:
        duracion = int(hs.group(1)) * 60
    return fecha, hora_fija, duracion


def formatear_cita(fecha: str, hora: str, fin: str, titulo: str) -> str:
    dia = date.fromisoformat(fecha)
    nombre = "Lun Mar Mié Jue Vie Sáb Dom".split()[dia.weekday()]
    return f"📅 {nombre} {dia.day} {_MES[dia.month - 1]} {hora}–{fin} · {titulo}"


def heuristic_tarea(text: str, *, require_signal: bool = True) -> dict:
    """Tarea por texto libre solo con hora explícita o verbo de agenda («agendar…», «recordame…»)."""
    verb = TAREA_VERB_RE.match(text or "")
    found = find_time(text)
    fecha, hora_fija, duracion = _cuando(text)
    if require_signal and not (verb or found or hora_fija):
        return {"intent": "unknown"}
    titulo = text
    if found:
        start, end = found[1]
        titulo = titulo[:start] + " " + titulo[end:]
    titulo = TAREA_VERB_RE.sub("", titulo)
    titulo = re.sub(
        r"\b(pasado\s+ma[ñn]ana|ma[ñn]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo"
        r"|en\s+\d{1,2}\s+horas?|el\s+\d{1,2}|\d{1,3}\s*(?:min|minutos)|\d{1,2}\s*(?:h|hora|horas))\b",
        "",
        titulo,
        flags=re.I,
    )
    titulo = " ".join(titulo.split()).strip(" -") or text[:80]
    return {
        "intent": "tarea",
        "titulo": titulo[:80],
        "fecha": fecha.isoformat(),
        "hora_inicio": hora_fija or (found[0] if found else "09:00"),
        "hora_fin": None,
        "duracion": duracion,
    }


def _mas_minutos(hora: str, minutos: int) -> str:
    total = min(int(hora[:2]) * 60 + int(hora[3:5]) + minutos, 23 * 60 + 59)
    return f"{total // 60:02d}:{total % 60:02d}"


def _validar(data: dict) -> dict | None:
    from app.timezone_config import hoy

    if not isinstance(data, dict) or data.get("intent") not in ("tarea", None):
        return None
    fecha = str(data.get("fecha") or hoy().isoformat())
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return None
    hora = str(data.get("hora_inicio") or "09:00")[:5]
    if not HHMM_RE.match(hora):
        return None
    fin = str(data.get("hora_fin") or "")[:5]
    if not HHMM_RE.match(fin) or fin <= hora:
        minutos = int(data.get("duracion") or DURACION_MIN)
        fin = _mas_minutos(hora, minutos)
    titulo = str(data.get("titulo") or "").strip()[:80]
    return {"intent": "tarea", "titulo": titulo, "fecha": fecha, "hora_inicio": hora, "hora_fin": fin}


def _ejecutar(ctx: Contexto, datos: dict) -> Respuesta:
    from app.database import COLORES_TIPO, guardar_evento
    from app.telegram import schedule_reminder

    titulo = (datos.get("titulo") or str(datos.get("_texto") or "").strip()[:80]) or "Tarea"
    fecha, hora = datos["fecha"], datos["hora_inicio"]
    eid = guardar_evento(
        {
            "fecha": fecha,
            "hora_inicio": hora,
            "hora_fin": datos["hora_fin"],
            "titulo": titulo,
            "descripcion": "vía Telegram",
            "tipo": "Personal",
            "color": COLORES_TIPO.get("Personal", "#58a6ff"),
            "fuente": "local",
        },
        sync_google=True,
    )
    schedule_reminder(ctx.user_id, eid, fecha, hora, titulo, ctx.chat_id)
    return Respuesta(
        formatear_cita(fecha, hora, datos["hora_fin"], titulo),
        entidad_id=int(eid),
        resumen=f"tarea «{titulo}» del {fecha} {hora}",
    )


def _deshacer(ctx: Contexto, evento_id: int, _resumen: str = "") -> bool:
    from app.db.agenda import eliminar_evento
    from app.telegram import cancel_reminders

    cancel_reminders(ctx.user_id, int(evento_id))
    return bool(eliminar_evento(int(evento_id)))


TAREA = Accion(
    clave="tarea",
    comandos=("/tarea",),
    modulo="agenda",
    ejecutar=_ejecutar,
    deshacer=_deshacer,
    uso=USO,
    llm_campos=(
        "titulo, fecha (YYYY-MM-DD o null), hora_inicio (HH:MM o null), hora_fin (HH:MM o null)"
    ),
    parse=lambda args: _validar(heuristic_tarea(args, require_signal=False)) if args.strip() else None,
    validar=_validar,
    heuristica=lambda text: _validar(heuristic_tarea(text)),
)


def _rango(args: str) -> tuple[date, date, str]:
    from app.telegram_actions.briefing import normalize
    from app.timezone_config import hoy

    dia = hoy()
    cual = normalize(args)
    if "semana" in cual:
        lunes = dia - timedelta(days=dia.weekday())
        return lunes, lunes + timedelta(days=6), "la semana"
    if "manana" in cual:
        return dia + timedelta(days=1), dia + timedelta(days=1), "mañana"
    return dia, dia, "hoy"


def _listar_agenda(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.agenda import obtener_eventos_semana
    from app.db.telegram_state import guardar_refs

    desde, hasta, etiqueta = _rango(str(datos.get("cuando") or ""))
    eventos = obtener_eventos_semana(desde, hasta)
    if not eventos:
        return Respuesta(f"Agenda de {etiqueta}: nada anotado.")
    guardar_refs(ctx.user_id, ctx.chat_id, "evento", [int(e["id"]) for e in eventos])
    lineas = [f"Agenda de {etiqueta}. /mover <n> o /cancelar <n>"]
    for i, e in enumerate(eventos, start=1):
        hora = str(e.get("hora_inicio") or "")[:5]
        fin = str(e.get("hora_fin") or "")[:5]
        tramo = f"{hora}–{fin}" if hora and fin else hora or "sin hora"
        lineas.append(f"{i}. {e.get('fecha')} {tramo} {e.get('titulo')}")
    return Respuesta("\n".join(lineas))


def _patron_agenda(texto: str) -> dict | None:
    from app.telegram_actions.briefing import normalize

    low = normalize(texto)
    if low in {"agenda", "mi agenda", "agenda de hoy"}:
        return {"cuando": "hoy"}
    if low in {"agenda de manana", "agenda manana"}:
        return {"cuando": "manana"}
    if low in {"agenda de la semana", "agenda semana"}:
        return {"cuando": "semana"}
    return None


AGENDA = Accion(
    clave="agenda",
    comandos=("/agenda",),
    modulo="agenda",
    ejecutar=_listar_agenda,
    parse=lambda args: {"cuando": args},
    patron=_patron_agenda,
)


def _evento_n(ctx: Contexto, n: int) -> int | None:
    from app.db.telegram_state import buscar_ref

    return buscar_ref(ctx.user_id, ctx.chat_id, "evento", n)


def _parse_mover(args: str) -> dict | None:
    m = re.match(r"^\s*(\d{1,3})\s+(.+)$", args or "")
    if not m:
        return None
    hora = explicit_time(m.group(2))
    if not hora:
        return None
    return {"n": int(m.group(1)), "hora": hora}


def _confirmar_mover(ctx: Contexto, datos: dict) -> str | None:
    if _evento_n(ctx, int(datos["n"])) is None:
        return None
    return f"¿Muevo el {datos['n']} a las {datos['hora']}?"


def _ejecutar_mover(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.agenda import actualizar_evento

    eid = _evento_n(ctx, int(datos["n"]))
    if eid is None:
        return Respuesta("No encuentro ese número. Mandá /agenda primero.")
    fin = _mas_minutos(datos["hora"], DURACION_MIN)
    if not actualizar_evento(eid, {"hora_inicio": datos["hora"], "hora_fin": fin}):
        return Respuesta("No pude mover ese evento.")
    return Respuesta(f"Moví el {datos['n']} a las {datos['hora']}.")


MOVER = Accion(
    clave="mover",
    comandos=("/mover",),
    modulo="agenda",
    ejecutar=_ejecutar_mover,
    confirmar=_confirmar_mover,
    uso="Primero /agenda, después /mover 2 18:00.",
    parse=_parse_mover,
)


def _parse_cancelar(args: str) -> dict | None:
    m = re.match(r"^\s*(\d{1,3})\s*$", args or "")
    return {"n": int(m.group(1))} if m else None


def _confirmar_cancelar(ctx: Contexto, datos: dict) -> str | None:
    if _evento_n(ctx, int(datos["n"])) is None:
        return None
    return f"¿Cancelo el {datos['n']}? También se borra en Google Calendar si estaba vinculado."


def _ejecutar_cancelar(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.agenda import eliminar_evento
    from app.telegram import cancel_reminders

    eid = _evento_n(ctx, int(datos["n"]))
    if eid is None:
        return Respuesta("No encuentro ese número. Mandá /agenda primero.")
    cancel_reminders(ctx.user_id, eid)
    if not eliminar_evento(eid):
        return Respuesta("No pude cancelar ese evento.")
    return Respuesta(f"Cancelé el {datos['n']}.")


CANCELAR = Accion(
    clave="cancelar",
    comandos=("/cancelar",),
    modulo="agenda",
    ejecutar=_ejecutar_cancelar,
    confirmar=_confirmar_cancelar,
    uso="Primero /agenda, después /cancelar 2.",
    parse=_parse_cancelar,
)
