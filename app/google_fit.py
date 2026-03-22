"""
google_fit.py - Integración con Google Fit API
Obtiene sueño, ejercicio, pasos y frecuencia cardíaca
"""

import os
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, List

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent.parent
CREDENTIALS_FILE = BASE_DIR / "credentials_fit.json"
TOKEN_FILE = BASE_DIR / "token_fit.json"

SCOPES = [
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/calendar",
]

# ═══════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════════

def _get_credentials():
    """Obtiene credenciales OAuth2, abriendo browser si es necesario."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    # Cargar token guardado
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Si no hay token válido, autenticar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guardar token para próximas veces
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def get_fit_service():
    """Retorna el servicio de Google Fit o None si no está configurado."""
    try:
        from googleapiclient.discovery import build
        creds = _get_credentials()
        if not creds:
            return None
        return build("fitness", "v1", credentials=creds)
    except Exception as e:
        print(f"[GoogleFit] Error inicializando servicio: {e}")
        return None


def fit_configurado() -> bool:
    """Verifica si Google Fit está configurado sin abrir browser."""
    return CREDENTIALS_FILE.exists()


def fit_autenticado() -> bool:
    """Verifica si ya hay un token guardado válido."""
    if not TOKEN_FILE.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        return creds.valid
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# HELPERS DE TIEMPO
# ═══════════════════════════════════════════════════════════════

def _fecha_a_nanos(fecha: date, fin_dia: bool = False) -> int:
    """Convierte fecha a nanosegundos epoch (formato Google Fit)."""
    if fin_dia:
        dt = datetime.combine(fecha, datetime.max.time())
    else:
        dt = datetime.combine(fecha, datetime.min.time())
    return int(dt.timestamp() * 1e9)


def _nanos_a_datetime(nanos: int) -> datetime:
    """Convierte nanosegundos epoch a datetime."""
    return datetime.fromtimestamp(nanos / 1e9)

# ═══════════════════════════════════════════════════════════════
# OBTENER DATOS DE SUEÑO
# ═══════════════════════════════════════════════════════════════

def obtener_sueno(fecha: date, service=None) -> Dict:
    """
    Obtiene datos de sueño de Google Fit para una fecha.
    Retorna: horas_sueno, calidad_sueno, hora_dormir, hora_despertar
    """
    resultado = {
        'horas_sueno': None,
        'calidad_sueno': None,
        'hora_dormir': None,
        'hora_despertar': None,
    }

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        # Buscar en ventana de 24h (día anterior + día actual para capturar sueño nocturno)
        fecha_inicio = fecha - timedelta(days=1)
        start_ns = _fecha_a_nanos(fecha_inicio)
        end_ns = _fecha_a_nanos(fecha, fin_dia=True)

        body = {
            "startTimeNanos": str(start_ns),
            "endTimeNanos": str(end_ns),
            "dataTypeName": "com.google.sleep.segment"
        }

        response = service.users().dataSources().datasets().get(
            userId="me",
            dataSourceId="derived:com.google.sleep.segment:com.google.android.gms:merged",
            datasetId=f"{start_ns}-{end_ns}"
        ).execute()

        puntos = response.get('point', [])

        if not puntos:
            return resultado

        # Calcular duración total de sueño
        total_segundos = 0
        inicio_sueno = None
        fin_sueno = None
        etapas = []

        for punto in puntos:
            inicio = _nanos_a_datetime(int(punto['startTimeNanos']))
            fin = _nanos_a_datetime(int(punto['endTimeNanos']))
            tipo = punto['value'][0]['intVal'] if punto.get('value') else 1

            # Tipos: 1=Despierto, 2=Sueño ligero, 3=Sueño profundo, 4=REM, 5=Dormido
            if tipo in [2, 3, 4, 5]:
                duracion = (fin - inicio).total_seconds()
                total_segundos += duracion
                etapas.append({'tipo': tipo, 'duracion': duracion})

            if inicio_sueno is None or inicio < inicio_sueno:
                inicio_sueno = inicio
            if fin_sueno is None or fin > fin_sueno:
                fin_sueno = fin

        horas = total_segundos / 3600

        # Calcular calidad basada en etapas de sueño
        # Más REM y sueño profundo = mejor calidad
        sueno_profundo = sum(e['duracion'] for e in etapas if e['tipo'] == 3)
        sueno_rem = sum(e['duracion'] for e in etapas if e['tipo'] == 4)
        pct_calidad = ((sueno_profundo + sueno_rem) / total_segundos) if total_segundos > 0 else 0
        calidad = min(10, max(1, int(pct_calidad * 15 + horas * 0.5)))

        resultado = {
            'horas_sueno': round(horas, 1),
            'calidad_sueno': calidad,
            'hora_dormir': inicio_sueno.strftime('%H:%M') if inicio_sueno else None,
            'hora_despertar': fin_sueno.strftime('%H:%M') if fin_sueno else None,
        }

    except Exception as e:
        print(f"[GoogleFit] Error obteniendo sueño: {e}")

    return resultado

# ═══════════════════════════════════════════════════════════════
# OBTENER DATOS DE EJERCICIO
# ═══════════════════════════════════════════════════════════════

def obtener_ejercicio(fecha: date, service=None) -> Dict:
    """
    Obtiene sesiones de ejercicio de Google Fit.
    Retorna: hizo_ejercicio, tipo_ejercicio, duracion_minutos, calorias, pasos
    """
    resultado = {
        'hizo_ejercicio': False,
        'tipo_ejercicio': None,
        'duracion_minutos': None,
        'calorias': None,
        'pasos': None,
        'sesiones': []
    }

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        start_ms = int(datetime.combine(fecha, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(fecha, datetime.max.time()).timestamp() * 1000)

        # Obtener sesiones de actividad
        sessions_response = service.users().sessions().list(
            userId="me",
            startTime=datetime.combine(fecha, datetime.min.time()).isoformat() + "Z",
            endTime=datetime.combine(fecha, datetime.max.time()).isoformat() + "Z",
        ).execute()

        sesiones = sessions_response.get('session', [])

        # Mapeo de tipos de actividad Google Fit → nombre legible
        ACTIVIDADES = {
            1: 'Aeróbicos', 7: 'Caminata', 8: 'Carrera',
            9: 'Bicicleta', 10: 'Bicicleta', 13: 'Calistenia',
            15: 'Cardio', 17: 'Escalada', 20: 'Entrenamiento fuerza',
            21: 'Fútbol', 29: 'Natación', 35: 'Fuerza',
            36: 'Pilates', 37: 'Yoga', 45: 'Entrenamiento funcional',
            93: 'Entrenamiento fuerza', 97: 'Pesas',
        }

        duracion_total = 0
        sesiones_info = []

        for sesion in sesiones:
            tipo_id = sesion.get('activityType', 0)
            tipo_nombre = ACTIVIDADES.get(tipo_id, f'Ejercicio ({tipo_id})')

            inicio = datetime.fromisoformat(
                sesion['startTimeMillis']
            ) if 'startTimeMillis' in sesion else None

            duracion_ms = int(sesion.get('endTimeMillis', 0)) - int(sesion.get('startTimeMillis', 0))
            duracion_min = duracion_ms / 60000

            duracion_total += duracion_min
            sesiones_info.append({
                'tipo': tipo_nombre,
                'duracion_min': round(duracion_min),
            })

        # Obtener pasos del día
        pasos_response = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.step_count.delta"}],
                "bucketByTime": {"durationMillis": 86400000},
                "startTimeMillis": str(start_ms),
                "endTimeMillis": str(end_ms),
            }
        ).execute()

        pasos_total = 0
        for bucket in pasos_response.get('bucket', []):
            for dataset in bucket.get('dataset', []):
                for point in dataset.get('point', []):
                    for val in point.get('value', []):
                        pasos_total += val.get('intVal', 0)

        # Obtener calorías
        calorias_response = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.calories.expended"}],
                "bucketByTime": {"durationMillis": 86400000},
                "startTimeMillis": str(start_ms),
                "endTimeMillis": str(end_ms),
            }
        ).execute()

        calorias_total = 0
        for bucket in calorias_response.get('bucket', []):
            for dataset in bucket.get('dataset', []):
                for point in dataset.get('point', []):
                    for val in point.get('value', []):
                        calorias_total += val.get('fpVal', 0)

        if sesiones_info:
            tipo_principal = sesiones_info[0]['tipo']
            resultado = {
                'hizo_ejercicio': True,
                'tipo_ejercicio': tipo_principal,
                'duracion_minutos': round(duracion_total),
                'calorias': round(calorias_total),
                'pasos': pasos_total,
                'sesiones': sesiones_info,
            }
        else:
            resultado['pasos'] = pasos_total
            resultado['calorias'] = round(calorias_total)

    except Exception as e:
        print(f"[GoogleFit] Error obteniendo ejercicio: {e}")

    return resultado

# ═══════════════════════════════════════════════════════════════
# OBTENER FRECUENCIA CARDÍACA
# ═══════════════════════════════════════════════════════════════

def obtener_frecuencia_cardiaca(fecha: date, service=None) -> Dict:
    """Obtiene frecuencia cardíaca promedio y máxima del día."""
    resultado = {'fc_promedio': None, 'fc_maxima': None}

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        start_ms = int(datetime.combine(fecha, datetime.min.time()).timestamp() * 1000)
        end_ms = int(datetime.combine(fecha, datetime.max.time()).timestamp() * 1000)

        response = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
                "bucketByTime": {"durationMillis": 86400000},
                "startTimeMillis": str(start_ms),
                "endTimeMillis": str(end_ms),
            }
        ).execute()

        for bucket in response.get('bucket', []):
            for dataset in bucket.get('dataset', []):
                for point in dataset.get('point', []):
                    vals = {v.get('key'): v.get('fpVal') for v in point.get('value', [])}
                    resultado['fc_promedio'] = round(vals.get('mean', 0)) or None
                    resultado['fc_maxima'] = round(vals.get('max', 0)) or None

    except Exception as e:
        print(f"[GoogleFit] Error obteniendo FC: {e}")

    return resultado

# ═══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — OBTENER TODO EL DÍA
# ═══════════════════════════════════════════════════════════════

def obtener_datos_dia(fecha: date) -> Dict:
    """
    Obtiene todos los datos de salud de Google Fit para una fecha.
    Retorna un dict compatible con el formulario del módulo Salud.
    """
    print(f"[GoogleFit] Obteniendo datos para {fecha}...")

    try:
        service = get_fit_service()
        if service is None:
            return {'error': 'Google Fit no configurado'}

        sueno = obtener_sueno(fecha, service)
        ejercicio = obtener_ejercicio(fecha, service)
        fc = obtener_frecuencia_cardiaca(fecha, service)

        return {
            # Sueño
            'horas_sueno': sueno['horas_sueno'],
            'calidad_sueno': sueno['calidad_sueno'],
            'hora_dormir': sueno['hora_dormir'],
            'hora_despertar': sueno['hora_despertar'],
            # Ejercicio
            'hizo_ejercicio': ejercicio['hizo_ejercicio'],
            'tipo_ejercicio': ejercicio['tipo_ejercicio'],
            'duracion_minutos': ejercicio['duracion_minutos'],
            'sesiones_fit': ejercicio['sesiones'],
            'calorias': ejercicio.get('calorias'),
            'pasos': ejercicio.get('pasos'),
            # Cardíaco
            'fc_promedio': fc['fc_promedio'],
            'fc_maxima': fc['fc_maxima'],
            # Estos siempre los llena el usuario manualmente
            'energia_manana': None,
            'energia_tarde': None,
            'energia_noche': None,
            'productividad_percibida': None,
            'zona_muscular': None,
            'notas_ejercicio': None,
        }

    except Exception as e:
        print(f"[GoogleFit] Error general: {e}")
        return {'error': str(e)}