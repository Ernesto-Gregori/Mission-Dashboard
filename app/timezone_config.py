"""
app/timezone_config.py
Zona horaria centralizada — importa desde aquí en todas las páginas.
"""
from datetime import date, datetime, timezone, timedelta

# ── Ajusta según tu ubicación ─────────────────────────────────
# UTC-6  → México Centro (CST invierno)
# UTC-5  → México Centro (CDT verano) / Colombia / Perú
# UTC-3  → Argentina / Chile verano
# UTC+1  → España invierno
TZ_OFFSET = -6
TZ_NAME   = "CST"
TZ_LOCAL  = timezone(timedelta(hours=TZ_OFFSET))


# ── Funciones principales ─────────────────────────────────────

def ahora() -> datetime:
    """Equivalente a datetime.now() en tu zona horaria."""
    return datetime.now(tz=TZ_LOCAL).replace(tzinfo=None)


def hoy() -> date:
    """Equivalente a date.today() en tu zona horaria."""
    return ahora().date()


def iso_ahora() -> str:
    """datetime.now().isoformat() en tu zona horaria."""
    return ahora().isoformat(timespec="seconds")


def hora_actual() -> str:
    """HH:MM en tu zona horaria."""
    return ahora().strftime("%H:%M")


# ── Re-exportar para mantener compatibilidad ─────────────────
# Las páginas hacen: from app.timezone_config import date, datetime
# y siguen funcionando igual — solo date.today() y datetime.now()
# necesitan ser reemplazados por hoy() y ahora()
__all__ = [
    "date", "datetime", "timedelta",   # re-exportados
    "hoy", "ahora", "iso_ahora",       # zona horaria
    "hora_actual", "TZ_NAME", "TZ_LOCAL",
]