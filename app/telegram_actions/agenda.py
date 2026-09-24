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


def heuristic_tarea(text: str, *, require_signal: bool = True) -> dict:
    """Tarea por texto libre solo con hora explícita o verbo de agenda («agendar…», «recordame…»)."""
    from app.timezone_config import hoy

    verb = TAREA_VERB_RE.match(text or "")
    found = find_time(text)
    if require_signal and not (verb or found):
        return {"intent": "unknown"}
    fecha = hoy()
    low = text.lower()
    if "mañana" in low or "manana" in low:
        fecha = fecha + timedelta(days=1)
    titulo = text
    if found:
        start, end = found[1]
        titulo = titulo[:start] + " " + titulo[end:]
    titulo = TAREA_VERB_RE.sub("", titulo)
    titulo = re.sub(r"\bma[ñn]ana\b", "", titulo, flags=re.I)
    titulo = " ".join(titulo.split()).strip() or text[:80]
    return {
        "intent": "tarea",
        "titulo": titulo[:80],
        "fecha": fecha.isoformat(),
        "hora_inicio": found[0] if found else "09:00",
        "hora_fin": None,
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
        fin = _mas_minutos(hora, DURACION_MIN)
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
        f"Tarea creada: {titulo} el {fecha} a las {hora} (sync Calendar si está vinculado).",
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
