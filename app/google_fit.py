"""
google_fit.py - Integración con Google Fit API
Obtiene sueño, ejercicio, pasos y frecuencia cardíaca.

Tokens OAuth se persisten en BD (Turso/SQLite) para sobrevivir
cuando Streamlit Cloud se duerme o redeploya (el disco se borra).
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
PROVIDER = "google_fit"

SCOPES = [
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/calendar",
]

# Último error de auth (para mostrar en UI)
_ultimo_error_auth: str = ""


def get_ultimo_error_auth() -> str:
    return _ultimo_error_auth or ""


# ═══════════════════════════════════════════════════════════════
# PERSISTENCIA DE TOKENS (BD → secrets → disco)
# ═══════════════════════════════════════════════════════════════

def _normalize_scopes(scopes) -> list:
    if not scopes:
        return list(SCOPES)
    if isinstance(scopes, str):
        s = scopes.strip()
        if s.startswith("["):
            try:
                return list(json.loads(s))
            except Exception:
                pass
        return [x.strip() for x in s.replace(",", " ").split() if x.strip()]
    return list(scopes)


def _token_dict_from_mapping(raw) -> dict:
    """Convierte secrets AttrDict / dict / JSON str a dict plano."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    try:
        return dict(raw)
    except Exception:
        return {k: raw[k] for k in raw}


def _creds_from_token_dict(token_data: dict):
    from google.oauth2.credentials import Credentials
    data = _token_dict_from_mapping(token_data)
    if not data:
        return None
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=_normalize_scopes(data.get("scopes")),
    )


def _ensure_oauth_table():
    try:
        from app.database import ejecutar
        ejecutar("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                user_id INTEGER NOT NULL DEFAULT 0,
                provider TEXT NOT NULL,
                token_json TEXT NOT NULL,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, provider)
            )
        """)
    except Exception as e:
        print(f"[GoogleFit] No se pudo asegurar tabla oauth_tokens: {e}")


def _load_token_from_db() -> Optional[dict]:
    try:
        from app.database import ejecutar
        from app.tenant import try_uid
        _ensure_oauth_table()
        user_id = try_uid()
        if user_id is None:
            return None
        rows = ejecutar(
            "SELECT token_json FROM oauth_tokens WHERE provider = ? AND user_id = ?",
            [PROVIDER, user_id],
            fetchall=True,
        ) or []
        if not rows:
            # Legacy: token sin user_id (migración)
            rows = ejecutar(
                "SELECT token_json FROM oauth_tokens WHERE provider = ? AND (user_id IS NULL OR user_id = ?)",
                [PROVIDER, user_id],
                fetchall=True,
            ) or []
        if not rows:
            return None
        return json.loads(rows[0]["token_json"])
    except Exception as e:
        print(f"[GoogleFit] Error leyendo token BD: {e}")
        return None


def _save_token_dict(token_data: dict) -> bool:
    """Guarda token en BD por usuario (sobrevive sleep) y en disco si es posible."""
    global _ultimo_error_auth
    try:
        from app.database import ejecutar
        from app.tenant import try_uid
        _ensure_oauth_table()
        user_id = try_uid()
        if user_id is None:
            _ultimo_error_auth = "Debes iniciar sesión para guardar el token de Google Fit"
            return False
        payload = json.dumps(token_data)
        # Asegurar columna user_id
        try:
            ejecutar("ALTER TABLE oauth_tokens ADD COLUMN user_id INTEGER")
        except Exception:
            pass
        ejecutar("""
            INSERT INTO oauth_tokens (user_id, provider, token_json, actualizado_en)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, provider) DO UPDATE SET
                token_json = excluded.token_json,
                actualizado_en = CURRENT_TIMESTAMP
        """, [user_id, PROVIDER, payload])
    except Exception as e:
        # Fallback sin PK compuesto (tabla vieja)
        try:
            from app.database import ejecutar
            from app.tenant import try_uid
            user_id = try_uid()
            payload = json.dumps(token_data)
            ejecutar("DELETE FROM oauth_tokens WHERE provider = ? AND (user_id = ? OR user_id IS NULL)", [PROVIDER, user_id])
            ejecutar("""
                INSERT INTO oauth_tokens (user_id, provider, token_json, actualizado_en)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, [user_id, PROVIDER, payload])
        except Exception as e2:
            print(f"[GoogleFit] Error guardando token en BD: {e} / {e2}")
            _ultimo_error_auth = f"No se pudo guardar token en BD: {e2}"
            return False

    try:
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    except Exception as e:
        # En Streamlit Cloud el disco puede fallar; BD basta
        print(f"[GoogleFit] Disco no escribible (ok si hay BD): {e}")
    return True


def guardar_token_desde_json(texto: str) -> tuple[bool, str]:
    """Importa un token OAuth pegado (JSON de token_fit.json)."""
    try:
        data = json.loads(texto.strip())
    except json.JSONDecodeError as e:
        return False, f"JSON inválido: {e}"
    if not data.get("refresh_token") and not data.get("token"):
        return False, "El JSON debe incluir refresh_token o token"
    # Completar client_id/secret desde credentials o secrets si faltan
    if not data.get("client_id") or not data.get("client_secret"):
        bootstrap = _load_token_from_secrets() or {}
        data.setdefault("client_id", bootstrap.get("client_id"))
        data.setdefault("client_secret", bootstrap.get("client_secret"))
        data.setdefault("token_uri", bootstrap.get("token_uri")
                        or "https://oauth2.googleapis.com/token")
        if CREDENTIALS_FILE.exists():
            try:
                cred_file = json.loads(CREDENTIALS_FILE.read_text())
                installed = cred_file.get("installed") or cred_file.get("web") or {}
                data.setdefault("client_id", installed.get("client_id"))
                data.setdefault("client_secret", installed.get("client_secret"))
            except Exception:
                pass
    data["scopes"] = _normalize_scopes(data.get("scopes") or SCOPES)
    if _save_token_dict(data):
        return True, "Token guardado en la base de datos. Ya no deberías re-vincular tras cada sleep."
    return False, "No se pudo guardar el token"


def _load_token_from_secrets() -> Optional[dict]:
    try:
        import streamlit as st
        if "google_fit_token" not in st.secrets:
            return None
        return _token_dict_from_mapping(st.secrets["google_fit_token"])
    except Exception as e:
        print(f"[GoogleFit] Secrets no disponibles: {e}")
        return None


def _load_token_from_disk() -> Optional[dict]:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception as e:
        print(f"[GoogleFit] Error leyendo disco: {e}")
        return None


def _refresh_and_persist(creds):
    """Refresca access token y lo guarda en BD (clave para sobrevivir al sleep)."""
    global _ultimo_error_auth
    from google.auth.transport.requests import Request

    if creds.valid:
        return creds
    if not creds.refresh_token:
        _ultimo_error_auth = (
            "No hay refresh_token. Vuelve a vincular Google y guarda el JSON completo."
        )
        return None
    try:
        creds.refresh(Request())
        _save_token_dict(json.loads(creds.to_json()))
        _ultimo_error_auth = ""
        return creds
    except Exception as e:
        err = str(e)
        _ultimo_error_auth = err
        print(f"[GoogleFit] Refresh falló: {err}")
        # invalid_grant suele ser app en Testing (token ~7 días) o revocado
        if "invalid_grant" in err.lower():
            _ultimo_error_auth = (
                "Google revocó el refresh_token (app en modo Testing expira ~7 días, "
                "o se revocó el acceso). Re-vincula y guarda el nuevo token en BD."
            )
        return None


def _get_credentials():
    """
    Obtiene credenciales OAuth2.
    Orden: BD (Turso/SQLite) → Streamlit Secrets → token_fit.json
    Tras refrescar, siempre se persiste en BD.
    """
    global _ultimo_error_auth
    token_data = (
        _load_token_from_db()
        or _load_token_from_secrets()
        or _load_token_from_disk()
    )
    if not token_data:
        _ultimo_error_auth = "Sin token. Conecta Google Fit o pega el JSON del token."
        return None

    creds = _creds_from_token_dict(token_data)
    if not creds:
        return None

    if creds.valid:
        # Migrar a BD si solo estaba en secrets/disco
        if not _load_token_from_db():
            _save_token_dict(json.loads(creds.to_json()))
        return creds

    return _refresh_and_persist(creds)


def iniciar_oauth_local() -> tuple[bool, str]:
    """
    Flujo OAuth con navegador local (solo funciona en tu PC, no en Streamlit Cloud).
    Guarda el token en BD + disco.
    """
    global _ultimo_error_auth
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_FILE.exists():
        return False, (
            "Falta credentials_fit.json en la raíz del proyecto. "
            "Descárgalo desde Google Cloud Console (OAuth client Desktop)."
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=0)
        data = json.loads(creds.to_json())
        if _save_token_dict(data):
            return True, "Google conectado y token guardado en la base de datos."
        return False, "OAuth ok pero no se pudo persistir el token."
    except Exception as e:
        _ultimo_error_auth = str(e)
        return False, f"Error OAuth: {e}"


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


def fit_autenticado() -> bool:
    """True si hay refresh_token usable (BD, secrets o disco) o access token válido."""
    try:
        creds = _get_credentials()
        return bool(creds and creds.valid)
    except Exception as e:
        print(f"[GoogleFit] fit_autenticado error: {e}")
        return False


def fit_configurado() -> bool:
    """True si hay alguna fuente de credenciales (client o token)."""
    if _load_token_from_db() or _load_token_from_secrets() or _load_token_from_disk():
        return True
    try:
        import streamlit as st
        if "google_fit_token" in st.secrets:
            return True
    except Exception:
        pass
    return CREDENTIALS_FILE.exists()


def estado_google_fit() -> dict:
    """Resumen para la UI de Salud."""
    en_bd = bool(_load_token_from_db())
    en_secrets = bool(_load_token_from_secrets())
    en_disco = TOKEN_FILE.exists()
    ok = fit_autenticado()
    return {
        "configurado": fit_configurado(),
        "autenticado": ok,
        "en_bd": en_bd,
        "en_secrets": en_secrets,
        "en_disco": en_disco,
        "error": get_ultimo_error_auth(),
        "credentials_file": CREDENTIALS_FILE.exists(),
    }

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