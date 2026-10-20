"""Importa un día de Google Fit al registro de salud de la persona en sesión."""
from __future__ import annotations

import json
from datetime import date

from app.logging_config import get_logger

log = get_logger("fit_import")


def importar_dia(fecha: date) -> tuple[bool, str]:
    """Mezcla Fit con lo que ya hay ese día. Requiere uid() y plan con Google."""
    from app.billing import puede_google
    from app.db.salud import guardar_registro_salud, obtener_registro_salud
    from app.google_fit import obtener_datos_dia

    if not puede_google():
        return False, "Google Fit requiere plan Premium."
    datos = obtener_datos_dia(fecha)
    if datos.get("error") and datos.get("horas_sueno") is None and datos.get("pasos") is None:
        return False, str(datos.get("error"))[:180]
    iso = fecha.isoformat()
    reg = obtener_registro_salud(iso) or {}
    merged = {
        "horas_sueno": datos.get("horas_sueno")
        if datos.get("horas_sueno") is not None
        else reg.get("horas_sueno"),
        "calidad_sueno": datos.get("calidad_sueno") or reg.get("calidad_sueno"),
        "hora_dormir": datos.get("hora_dormir") or reg.get("hora_dormir"),
        "hora_despertar": datos.get("hora_despertar") or reg.get("hora_despertar"),
        "energia_manana": reg.get("energia_manana"),
        "energia_tarde": reg.get("energia_tarde"),
        "energia_noche": reg.get("energia_noche"),
        "hizo_ejercicio": datos.get("hizo_ejercicio") or reg.get("hizo_ejercicio"),
        "tipo_ejercicio": datos.get("tipo_ejercicio") or reg.get("tipo_ejercicio"),
        "duracion_minutos": datos.get("duracion_minutos") or reg.get("duracion_minutos"),
        "intensidad": reg.get("intensidad"),
        "notas_ejercicio": reg.get("notas_ejercicio"),
        "zonas_musculares": [],
        "sesiones_json": datos.get("sesiones_fit") or [],
        "calorias_fit": datos.get("calorias"),
        "pasos_fit": datos.get("pasos"),
        "fc_promedio_fit": datos.get("fc_promedio"),
        "fc_maxima_fit": datos.get("fc_maxima"),
        "fuente_datos": "mixto",
        "productividad_percibida": reg.get("productividad_percibida"),
    }
    try:
        z = json.loads(reg.get("zonas_musculares") or "[]")
        merged["zonas_musculares"] = z if isinstance(z, list) else []
    except Exception:
        pass
    guardar_registro_salud(iso, merged)
    avisos = "; ".join(datos.get("avisos_fit") or [])
    msg = "Datos de Google Fit importados."
    if avisos:
        msg += f" ({avisos})"
    log.info("fit importado fecha=%s", iso)
    return True, msg
