"""
google_calendar.py - Sincronización bidireccional con Google Calendar
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from app.logging_config import get_logger

# Reutiliza las credenciales de Google Fit
from app.google_fit import _get_credentials

log = get_logger("google_calendar")

_ultimo_error: str = ""

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

# ID del calendario a usar — 'primary' = calendario principal
CALENDAR_ID = "primary"

# Colores Google Calendar → hex local
COLORES_GOOGLE = {
    "1": "#a4bdfc",  # Lavanda
    "2": "#7ae7bf",  # Salvia
    "3": "#dbadff",  # Uva
    "4": "#ff887c",  # Flamingo
    "5": "#fbd75b",  # Plátano
    "6": "#ffb878",  # Mandarina
    "7": "#46d6db",  # Pavo real
    "8": "#e1e1e1",  # Grafito
    "9": "#5484ed",  # Arándano
    "10": "#51b749", # Salvia
    "11": "#dc2127", # Tomate
}

# Mapeo tipo local → color Google Calendar
TIPO_A_COLOR_GOOGLE = {
    "Lectura":    "5",  # Plátano/amarillo
    "Personal":   "9",  # Azul
    "Ministerio": "3",  # Uva/morado
    "Salud":      "10", # Verde
    "Estudio":    "6",  # Mandarina
    "Matrimonio": "4",  # Flamingo/rosa
    "Otro":       "8",  # Grafito
}

# ═══════════════════════════════════════════════════════════════
# SERVICIO
# ═══════════════════════════════════════════════════════════════

def get_calendar_service():
    """Retorna el servicio de Google Calendar."""
    try:
        from googleapiclient.discovery import build
        creds = _get_credentials()
        if not creds:
            return None
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        log.warning("[Calendar] Error inicializando: %s", e)
        _set_error(str(e))
        return None


def _set_error(msg: str) -> None:
    global _ultimo_error
    _ultimo_error = (msg or "")[:300]


def calendar_disponible() -> bool:
    """Mismo token y scopes que Google Fit (incluye calendar).

    Un 403 u otro fallo de la API Calendar no se decide acá: queda en
    calendar_sync_state.last_error y en estado_google_calendar().
    """
    try:
        from app.google_fit import fit_autenticado
        return fit_autenticado()
    except Exception as e:
        log.warning("[Calendar] calendar_disponible: %s", e)
        _set_error(str(e))
        return False


def estado_google_calendar(user_id: int | None = None) -> dict:
    """Estado para la UI. `error` es el mensaje real, no solo «no conectado»."""
    from app.calendar_sync import leer_last_error
    from app.google_fit import get_ultimo_error_auth

    try:
        disponible = bool(calendar_disponible())
    except Exception as e:
        log.warning("[Calendar] estado: %s", e)
        disponible = False
        _set_error(str(e))
    auth = "" if disponible else (
        get_ultimo_error_auth() or _ultimo_error or "Sin vincular Google Calendar."
    )
    try:
        last = leer_last_error(user_id) or ""
    except Exception as e:
        log.warning("[Calendar] last_error: %s", e)
        last = ""
    visible = ""
    if not disponible:
        visible = auth
    if last and last != "calendar_unavailable":
        visible = last if not visible else f"{visible} — {last}"
    elif last == "calendar_unavailable" and not visible:
        visible = auth or "Google Calendar no está disponible."
    elif not visible and _ultimo_error and disponible:
        visible = _ultimo_error
    return {
        "disponible": disponible,
        "error": (visible or "")[:300],
        "last_error": last,
    }
    
# ═══════════════════════════════════════════════════════════════
# SINCRONIZAR BLOQUES DEEP WORK → GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════

# Mapeo tipo bloque → color Google Calendar
TIPO_BLOQUE_COLOR = {
    'Instituto':    '3',  # Uva/morado
    'Programacion': '10', # Verde
    'Biblioteca':   '5',  # Amarillo
    'Personal':     '9',  # Azul
}

def sincronizar_bloques_semana(lunes: date, domingo: date) -> int:
    """
    Crea eventos en Google Calendar para los bloques Deep Work
    de la semana indicada (solo del usuario en sesión).
    Retorna el número de eventos creados.
    """
    import json
    from app.database import ejecutar
    from app.tenant import try_uid

    try:
        service = get_calendar_service()
        if not service:
            return 0

        user_id = try_uid()
        if user_id is None:
            return 0

        # Obtener bloques existentes en Google Calendar esta semana
        time_min = datetime.combine(lunes, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(domingo, datetime.max.time()).isoformat() + "Z"

        eventos_gc = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            maxResults=200,
        ).execute()

        # Índice de eventos ya existentes por título+fecha
        existentes = set()
        for e in eventos_gc.get('items', []):
            start = e.get('start', {})
            fecha_e = ''
            if 'dateTime' in start:
                fecha_e = start['dateTime'][:10]
            elif 'date' in start:
                fecha_e = start['date']
            existentes.add(f"{e.get('summary','')}_{fecha_e}")

        bloques = ejecutar("""
            SELECT nombre, hora_inicio, hora_fin,
                   dias_semana, tipo, color
            FROM bloques_fijos
            WHERE activo = 1 AND user_id = ?
        """, [user_id], fetchall=True) or []

        creados = 0

        # Iterar cada día de la semana
        for i in range(7):
            dia = lunes + timedelta(days=i)
            dia_numero = dia.weekday() + 1  # 1=Lunes...7=Domingo

            for bloque in bloques:
                dias = json.loads(bloque['dias_semana'])
                if dia_numero not in dias:
                    continue

                titulo    = bloque['nombre']
                fecha_str = dia.isoformat()
                clave     = f"{titulo}_{fecha_str}"

                # Saltar si ya existe
                if clave in existentes:
                    continue

                color_id = TIPO_BLOQUE_COLOR.get(bloque['tipo'], '9')

                evento_body = {
                    "summary": titulo,
                    "description": f"Bloque Deep Work — Mission Dashboard\nTipo: {bloque['tipo']}",
                    "colorId": color_id,
                    "start": {
                        "dateTime": f"{fecha_str}T{bloque['hora_inicio']}:00",
                        "timeZone": "America/Mexico_City",
                    },
                    "end": {
                        "dateTime": f"{fecha_str}T{bloque['hora_fin']}:00",
                        "timeZone": "America/Mexico_City",
                    },
                }

                try:
                    service.events().insert(
                        calendarId=CALENDAR_ID,
                        body=evento_body
                    ).execute()
                    creados += 1
                    print(f"[Calendar] Bloque creado: {titulo} {fecha_str}")
                except Exception as e:
                    log.warning("[Calendar] Error creando bloque %s: %s", titulo, e)
                    _set_error(str(e))

        return creados

    except Exception as e:
        log.warning("[Calendar] Error en sincronizar_bloques_semana: %s", e)
        _set_error(str(e))
        return 0

# ═══════════════════════════════════════════════════════════════
# LEER EVENTOS DE GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════
def obtener_eventos_google(
    fecha_inicio: date,
    fecha_fin: date,
    *,
    include_deleted: bool = False,
    max_results: int = 250,
) -> List[Dict]:
    """
    Obtiene eventos de Google Calendar para un rango de fechas.
    Retorna lista compatible con eventos_calendario local.
    """
    resultado = []
    
    try:
        service = get_calendar_service()
        if not service:
            err = _ultimo_error or "Google Calendar no disponible."
            _set_error(err)
            raise RuntimeError(err)
        
        # Formato RFC3339
        time_min = datetime.combine(fecha_inicio, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(fecha_fin, datetime.max.time()).isoformat() + "Z"
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
            showDeleted=bool(include_deleted),
        ).execute()
        
        eventos = events_result.get("items", [])
        
        for evento in eventos:
            # Ignorar eventos del sistema (cumpleaños, etc.)
            if evento.get("eventType") not in [None, "default"]:
                continue
            
            # Extraer fecha y hora
            start = evento.get("start", {})
            end   = evento.get("end", {})
            
            if "dateTime" in start:
                # Evento con hora específica
                dt_start = datetime.fromisoformat(
                    start["dateTime"].replace("Z", "+00:00")
                )
                dt_end = datetime.fromisoformat(
                    end["dateTime"].replace("Z", "+00:00")
                )
                fecha_ev    = dt_start.date().isoformat()
                hora_inicio = dt_start.strftime("%H:%M")
                hora_fin    = dt_end.strftime("%H:%M")
                todo_el_dia = False
            else:
                # Evento de todo el día
                fecha_ev    = start.get("date", "")
                hora_inicio = None
                hora_fin    = None
                todo_el_dia = True
            
            # Color del evento
            color_id = evento.get("colorId", "9")
            color    = COLORES_GOOGLE.get(color_id, "#58a6ff")
            
            resultado.append({
                "google_id":    evento["id"],
                "fecha":        fecha_ev,
                "hora_inicio":  hora_inicio,
                "hora_fin":     hora_fin,
                "titulo":       evento.get("summary", "Sin título"),
                "descripcion":  evento.get("description", ""),
                "tipo":         "Personal",
                "ambito":       "Personal",
                "color":        color,
                "todo_el_dia":  todo_el_dia,
                "fuente":       "google_calendar",
                "updated":      evento.get("updated") or "",
                "status":       evento.get("status") or "confirmed",
            })
        _set_error("")

    except Exception as e:
        log.warning("[Calendar] Error obteniendo eventos: %s", e)
        _set_error(str(e))
        raise

    return resultado

# ═══════════════════════════════════════════════════════════════
# CREAR EVENTO EN GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════

def crear_evento_google(datos: Dict) -> Optional[str]:
    """
    Crea un evento en Google Calendar.
    Retorna el google_id del evento creado, o None si falla.
    """
    try:
        service = get_calendar_service()
        if not service:
            return None
        
        color_id = TIPO_A_COLOR_GOOGLE.get(datos.get("tipo", "Personal"), "9")
        
        # Construir evento
        if datos.get("hora_inicio"):
            # Evento con hora
            fecha = datos["fecha"]
            hi    = datos["hora_inicio"]
            hf    = datos.get("hora_fin", hi)
            
            evento_body = {
                "summary":     datos["titulo"],
                "description": datos.get("descripcion", ""),
                "colorId":     color_id,
                "start": {
                    "dateTime": f"{fecha}T{hi}:00",
                    "timeZone": "America/Mexico_City",
                },
                "end": {
                    "dateTime": f"{fecha}T{hf}:00",
                    "timeZone": "America/Mexico_City",
                },
            }
        else:
            # Evento de todo el día
            evento_body = {
                "summary":     datos["titulo"],
                "description": datos.get("descripcion", ""),
                "colorId":     color_id,
                "start": {"date": datos["fecha"]},
                "end":   {"date": datos["fecha"]},
            }
        
        resultado = service.events().insert(
            calendarId=CALENDAR_ID,
            body=evento_body
        ).execute()
        
        google_id = resultado.get("id")
        print(f"[Calendar] Evento creado: {datos['titulo']} → {google_id}")
        return google_id
    
    except Exception as e:
        log.warning("[Calendar] Error creando evento: %s", e)
        _set_error(str(e))
        return None

# ═══════════════════════════════════════════════════════════════
# ELIMINAR EVENTO EN GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════

def eliminar_evento_google(google_id: str) -> bool:
    """Elimina un evento de Google Calendar por su ID."""
    try:
        service = get_calendar_service()
        if not service:
            return False
        
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=google_id
        ).execute()
        
        print(f"[Calendar] Evento eliminado: {google_id}")
        return True
    
    except Exception as e:
        log.warning("[Calendar] Error eliminando evento: %s", e)
        _set_error(str(e))
        return False

# ═══════════════════════════════════════════════════════════════
# ACTUALIZAR EVENTO EN GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════

def actualizar_evento_google(google_id: str, datos: Dict) -> bool:
    """Actualiza un evento existente en Google Calendar."""
    try:
        service = get_calendar_service()
        if not service:
            return False
        
        color_id = TIPO_A_COLOR_GOOGLE.get(datos.get("tipo", "Personal"), "9")
        
        evento_body = {
            "summary":     datos["titulo"],
            "description": datos.get("descripcion", ""),
            "colorId":     color_id,
            "start": {
                "dateTime": f"{datos['fecha']}T{datos['hora_inicio']}:00",
                "timeZone": "America/Mexico_City",
            },
            "end": {
                "dateTime": f"{datos['fecha']}T{datos.get('hora_fin', datos['hora_inicio'])}:00",
                "timeZone": "America/Mexico_City",
            },
        }
        
        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=google_id,
            body=evento_body
        ).execute()
        
        return True
    
    except Exception as e:
        log.warning("[Calendar] Error actualizando evento: %s", e)
        _set_error(str(e))
        return False