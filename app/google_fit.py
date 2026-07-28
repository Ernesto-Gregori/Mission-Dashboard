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
            return None
        return json.loads(rows[0]["token_json"])
    except Exception as e:
        print(f"[GoogleFit] Error leyendo token BD: {e}")
        return None


def _save_token_dict(token_data: dict, user_id: int | None = None) -> bool:
    """Guarda token en BD por usuario (sobrevive sleep). Sin archivo global compartido."""
    global _ultimo_error_auth
    try:
        from app.database import ejecutar
        from app.tenant import try_uid
        _ensure_oauth_table()
        if user_id is None:
            user_id = try_uid()
        if user_id is None:
            _ultimo_error_auth = "Debes iniciar sesión para guardar el token de Google Fit"
            return False
        user_id = int(user_id)
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
            if user_id is None:
                user_id = try_uid()
            payload = json.dumps(token_data)
            ejecutar(
                "DELETE FROM oauth_tokens WHERE provider = ? AND user_id = ?",
                [PROVIDER, user_id],
            )
            ejecutar("""
                INSERT INTO oauth_tokens (user_id, provider, token_json, actualizado_en)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, [user_id, PROVIDER, payload])
        except Exception as e2:
            print(f"[GoogleFit] Error guardando token en BD: {e} / {e2}")
            _ultimo_error_auth = f"No se pudo guardar token en BD: {e2}"
            return False

    # Disco opcional SOLO por usuario (evita compartir token entre cuentas)
    try:
        path = TOKEN_FILE.parent / f"token_fit_u{int(user_id)}.json"
        path.write_text(json.dumps(token_data, indent=2))
    except Exception as e:
        print(f"[GoogleFit] Disco no escribible (ok si hay BD): {e}")
    return True


def _oauth_client_bootstrap() -> dict:
    """Solo client_id / client_secret de la app OAuth — nunca refresh_token ajeno."""
    out: dict = {}
    # Preferido: env / secrets.toml / Streamlit (app.secrets, sin warnings en uvicorn)
    try:
        from app.secrets import get_secret, get_secret_section

        section = get_secret_section("google_oauth")
        if section.get("client_id"):
            out["client_id"] = section["client_id"]
        if section.get("client_secret"):
            out["client_secret"] = section["client_secret"]
        if section.get("token_uri"):
            out["token_uri"] = section["token_uri"]
        fit = get_secret_section("google_fit_token")
        out.setdefault("client_id", fit.get("client_id"))
        out.setdefault("client_secret", fit.get("client_secret"))
        out.setdefault("token_uri", fit.get("token_uri"))
        out.setdefault("client_id", get_secret("GOOGLE_OAUTH_CLIENT_ID"))
        out.setdefault("client_secret", get_secret("GOOGLE_OAUTH_CLIENT_SECRET"))
    except Exception:
        pass
    # Env directo (por si secrets no cargó dotenv)
    out.setdefault("client_id", os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""))
    out.setdefault("client_secret", os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""))
    if CREDENTIALS_FILE.exists():
        try:
            cred_file = json.loads(CREDENTIALS_FILE.read_text())
            # Preferir bloque "web" para redirect URI
            block = cred_file.get("web") or cred_file.get("installed") or {}
            out.setdefault("client_id", block.get("client_id"))
            out.setdefault("client_secret", block.get("client_secret"))
            out.setdefault(
                "token_uri",
                block.get("token_uri") or "https://oauth2.googleapis.com/token",
            )
        except Exception:
            pass
    out.setdefault("token_uri", "https://oauth2.googleapis.com/token")
    return {k: v for k, v in out.items() if v}


def guardar_token_desde_json(texto: str) -> tuple[bool, str]:
    """Importa un token OAuth pegado (JSON de token_fit.json)."""
    try:
        data = json.loads(texto.strip())
    except json.JSONDecodeError as e:
        return False, f"JSON inválido: {e}"
    if not data.get("refresh_token") and not data.get("token"):
        return False, "El JSON debe incluir refresh_token o token"
    # Completar solo client_id/secret de la app (no tokens de otros usuarios)
    if not data.get("client_id") or not data.get("client_secret"):
        bootstrap = _oauth_client_bootstrap()
        data.setdefault("client_id", bootstrap.get("client_id"))
        data.setdefault("client_secret", bootstrap.get("client_secret"))
        data.setdefault(
            "token_uri",
            bootstrap.get("token_uri") or "https://oauth2.googleapis.com/token",
        )
    if not data.get("client_id") or not data.get("client_secret"):
        return False, "Falta client_id/client_secret en el JSON (o en credentials_fit.json)"
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
    Credenciales OAuth2 solo del usuario en sesión (tabla oauth_tokens).
    No reutiliza secrets/disco compartidos (evita fuga entre cuentas).
    """
    global _ultimo_error_auth
    token_data = _load_token_from_db()
    if not token_data:
        _ultimo_error_auth = (
            "Sin token para tu usuario. Conecta Google Fit o pega el JSON del token."
        )
        return None

    creds = _creds_from_token_dict(token_data)
    if not creds:
        return None

    if creds.valid:
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


# ═══════════════════════════════════════════════════════════════
# OAUTH WEB (Streamlit Cloud — redirect URI, sin pegar JSON)
# ═══════════════════════════════════════════════════════════════

def get_oauth_redirect_uri() -> str:
    """URI de retorno. Debe coincidir EXACTO con Google Cloud Console."""
    # 1) Env explícito (FastAPI / Railway)
    env = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if env:
        return env
    # 2) secrets.toml / Streamlit [google_oauth].redirect_uri
    try:
        from app.secrets import get_secret, get_secret_section

        section = get_secret_section("google_oauth")
        uri = (section.get("redirect_uri") or "").strip()
        if uri:
            return uri
        uri = get_secret("GOOGLE_OAUTH_REDIRECT_URI").strip()
        if uri:
            return uri
    except Exception:
        pass
    # 3) APP_URL → callback FastAPI canónico
    app_url = (os.getenv("APP_URL") or "").rstrip("/")
    if app_url:
        return f"{app_url}/oauth/google/callback"
    # 4) Auto-detect en Streamlit Cloud
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        import streamlit as st

        if get_script_run_ctx() is not None:
            headers = getattr(st.context, "headers", None) or {}
            host = headers.get("Host") or headers.get("host") or ""
            proto = (
                headers.get("X-Forwarded-Proto")
                or headers.get("x-forwarded-proto")
                or "https"
            )
            if host:
                return f"{proto}://{host}/"
    except Exception:
        pass
    return ""


def oauth_web_disponible() -> bool:
    """True si hay client_id/secret para el flujo web."""
    c = _oauth_client_bootstrap()
    return bool(c.get("client_id") and c.get("client_secret"))


def _state_signing_key() -> bytes:
    key = os.getenv("OAUTH_STATE_SECRET") or os.getenv("GROQ_API_KEY") or ""
    try:
        from app.secrets import get_secret, get_secret_section

        if not key:
            key = get_secret("OAUTH_STATE_SECRET") or get_secret("GROQ_API_KEY") or ""
        if not key:
            key = get_secret_section("google_oauth").get("client_secret") or ""
    except Exception:
        pass
    if not key:
        key = "mission-dashboard-oauth-state"
    return str(key).encode("utf-8")


def _firmar_oauth_state(user_id: int) -> str:
    import base64
    import hashlib
    import hmac
    import secrets
    import time

    nonce = secrets.token_hex(8)
    ts = int(time.time())
    payload = f"{int(user_id)}:{ts}:{nonce}"
    sig = hmac.new(_state_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:20]
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _verificar_oauth_state(state: str, max_age_sec: int = 900) -> int | None:
    """Devuelve user_id si el state es válido; None si no."""
    import base64
    import hashlib
    import hmac
    import time

    if not state:
        return None
    try:
        pad = "=" * (-len(state) % 4)
        raw = base64.urlsafe_b64decode(state + pad).decode()
        parts = raw.split(":")
        if len(parts) != 4:
            return None
        user_s, ts_s, nonce, sig = parts
        payload = f"{user_s}:{ts_s}:{nonce}"
        expect = hmac.new(
            _state_signing_key(), payload.encode(), hashlib.sha256
        ).hexdigest()[:20]
        if not hmac.compare_digest(expect, sig):
            return None
        ts = int(ts_s)
        if abs(int(time.time()) - ts) > max_age_sec:
            return None
        return int(user_s)
    except Exception:
        return None


def _build_web_flow(redirect_uri: str):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return None, "Falta el paquete google-auth-oauthlib (pip install -r requirements.txt)"

    client = _oauth_client_bootstrap()
    if not client.get("client_id") or not client.get("client_secret"):
        return None, "Falta client_id/client_secret (secrets [google_oauth] o credentials_fit.json)"
    if not redirect_uri:
        return None, (
            "Falta redirect_uri. Añade en secrets: "
            '[google_oauth] redirect_uri = "https://TU-APP.streamlit.app/"'
        )
    client_config = {
        "web": {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": client.get("token_uri") or "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    # Cliente confidencial (web + client_secret): sin PKCE.
    # PKCE guardaría code_verifier en memoria; al volver de Google la sesión
    # de Streamlit a menudo se pierde → "Missing code verifier".
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        autogenerate_code_verifier=False,
    )
    flow.code_verifier = None
    flow.redirect_uri = redirect_uri
    return flow, ""


def crear_url_autorizacion_web(user_id: int | None = None) -> tuple[str | None, str]:
    """
    Genera la URL de Google OAuth (consentimiento).
    Retorna (url, error). url es None si falla.
    """
    from app.tenant import try_uid

    uid_ = user_id if user_id is not None else try_uid()
    if uid_ is None:
        return None, "Debes iniciar sesión antes de vincular Google"
    redirect_uri = get_oauth_redirect_uri()
    flow, err = _build_web_flow(redirect_uri)
    if not flow:
        return None, err
    state = _firmar_oauth_state(int(uid_))
    try:
        # offline + consent → refresh_token (necesario en Cloud)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
        )
        return auth_url, ""
    except Exception as e:
        return None, f"No se pudo crear URL OAuth: {e}"


def intercambiar_oauth_code(
    code: str,
    state: str,
    *,
    session_uid: int | None = None,
) -> tuple[bool, str]:
    """
    Intercambia ?code=&state= por tokens y los guarda en oauth_tokens.
    Agnóstico de Streamlit — usado por FastAPI y por procesar_oauth_callback.
    """
    global _ultimo_error_auth

    user_from_state = _verificar_oauth_state(str(state))
    if user_from_state is None:
        return False, "State OAuth inválido o expirado. Vuelve a pulsar Conectar con Google."

    if session_uid is not None and int(session_uid) != int(user_from_state):
        return False, (
            "La cuenta con la que iniciaste sesión no coincide con la que "
            "empezó el vínculo de Google. Entra con el mismo usuario e inténtalo de nuevo."
        )

    redirect_uri = get_oauth_redirect_uri()
    flow, err = _build_web_flow(redirect_uri)
    if not flow:
        return False, err

    try:
        flow.fetch_token(code=str(code))
        creds = flow.credentials
        data = json.loads(creds.to_json())
        bootstrap = _oauth_client_bootstrap()
        data.setdefault("client_id", bootstrap.get("client_id"))
        data.setdefault("client_secret", bootstrap.get("client_secret"))
        data["scopes"] = _normalize_scopes(data.get("scopes") or SCOPES)
        if not data.get("refresh_token"):
            existing = None
            try:
                from app.database import ejecutar

                rows = (
                    ejecutar(
                        "SELECT token_json FROM oauth_tokens WHERE user_id = ? AND provider = ?",
                        [user_from_state, PROVIDER],
                        fetchall=True,
                    )
                    or []
                )
                if rows:
                    existing = json.loads(rows[0]["token_json"])
            except Exception:
                pass
            if existing and existing.get("refresh_token"):
                data["refresh_token"] = existing["refresh_token"]
        if not _save_token_dict(data, user_id=user_from_state):
            return False, "OAuth ok pero no se pudo guardar el token en BD."
        _ultimo_error_auth = ""
        return True, "Google Fit/Calendar vinculados. Token guardado en tu cuenta (BD)."
    except Exception as e:
        _ultimo_error_auth = str(e)
        return False, f"Error al intercambiar el código OAuth: {e}"


def procesar_oauth_callback() -> tuple[bool, str] | None:
    """
    Si la URL trae ?code=&state= (vuelta de Google), intercambia el code
    y guarda el token en oauth_tokens del usuario del state.

    Returns:
      None — no hay callback que procesar
      (True, msg) / (False, msg) — resultado del intercambio
    """
    global _ultimo_error_auth
    try:
        import streamlit as st
    except Exception:
        return None

    try:
        params = st.query_params
        code = params.get("code")
        state = params.get("state")
        err = params.get("error")
    except Exception:
        return None

    if err:
        try:
            st.query_params.clear()
        except Exception:
            pass
        _ultimo_error_auth = f"Google OAuth: {err}"
        return False, f"Google denegó el acceso: {err}"

    if not code or not state:
        return None

    # Evitar procesar dos veces el mismo code en el mismo rerun loop
    if st.session_state.get("_oauth_code_done") == code:
        try:
            st.query_params.clear()
        except Exception:
            pass
        return None

    from app.tenant import try_uid

    session_uid = try_uid()
    ok, msg = intercambiar_oauth_code(
        str(code),
        str(state),
        session_uid=int(session_uid) if session_uid is not None else None,
    )
    try:
        st.query_params.clear()
    except Exception:
        pass
    if ok:
        st.session_state["_oauth_code_done"] = code
    return ok, msg


def manejar_oauth_retorno() -> None:
    """
    Procesa el retorno de Google (?code=&state=).

    Debe llamarse ANTES de require_auth(): al salir a Google y volver,
    Streamlit Cloud a menudo pierde la sesión — si esperamos al login,
    el code caduca y nunca se guarda el token.
    """
    try:
        import streamlit as st
    except Exception:
        return

    try:
        params = st.query_params
        if not (params.get("code") or params.get("error")):
            return
    except Exception:
        return

    # Asegurar BD aunque aún no haya sesión
    try:
        from app.database import ensure_database
        ensure_database()
    except Exception as e:
        print(f"[GoogleFit] ensure_database en oauth retorno: {e}")

    result = procesar_oauth_callback()
    if result is None:
        return
    ok, msg = result
    if ok:
        st.success(msg)
        st.info(
            "Google ya quedó vinculado a tu cuenta. "
            "Si te pide iniciar sesión otra vez, entra con tu usuario "
            "y abre **Salud** — debe decir «token en BD»."
        )
    else:
        st.error(msg)


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
    """True si el usuario tiene token en BD o hay cliente OAuth listo para vincular."""
    if _load_token_from_db():
        return True
    return oauth_web_disponible() or CREDENTIALS_FILE.exists()


def estado_google_fit() -> dict:
    """Resumen para la UI de Salud."""
    en_bd = bool(_load_token_from_db())
    ok = fit_autenticado()
    redirect = get_oauth_redirect_uri()
    return {
        "configurado": fit_configurado(),
        "autenticado": ok,
        "en_bd": en_bd,
        "en_secrets": False,  # ya no usamos refresh_token compartido
        "en_disco": False,
        "oauth_web": oauth_web_disponible(),
        "redirect_uri": redirect,
        "error": get_ultimo_error_auth(),
        "credentials_file": CREDENTIALS_FILE.exists(),
    }

# ═══════════════════════════════════════════════════════════════
# HELPERS DE TIEMPO (zona local de la app, no UTC del servidor)
# ═══════════════════════════════════════════════════════════════

def _tz_local():
    from app.timezone_config import TZ_LOCAL
    return TZ_LOCAL


def _rango_dia_ms(fecha: date) -> tuple[int, int]:
    """Inicio/fin del día en epoch ms, usando la zona de la app."""
    tz = _tz_local()
    start = datetime.combine(fecha, datetime.min.time()).replace(tzinfo=tz)
    end = datetime.combine(fecha, datetime.max.time()).replace(tzinfo=tz)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _rango_dia_ns(fecha: date) -> tuple[int, int]:
    start_ms, end_ms = _rango_dia_ms(fecha)
    return start_ms * 1_000_000, end_ms * 1_000_000


def _fecha_a_nanos(fecha: date, fin_dia: bool = False) -> int:
    """Convierte fecha a nanosegundos epoch (zona local de la app)."""
    start_ns, end_ns = _rango_dia_ns(fecha)
    return end_ns if fin_dia else start_ns


def _nanos_a_datetime(nanos: int) -> datetime:
    """Nanos epoch → datetime naive en zona local de la app."""
    tz = _tz_local()
    return datetime.fromtimestamp(int(nanos) / 1e9, tz=tz).replace(tzinfo=None)


def _ms_a_datetime(ms: int | str) -> datetime:
    tz = _tz_local()
    return datetime.fromtimestamp(int(ms) / 1000.0, tz=tz).replace(tzinfo=None)


def _rfc3339_rango(fecha: date, dias_antes: int = 0) -> tuple[str, str]:
    """Timestamps RFC3339 con offset local para sessions.list."""
    tz = _tz_local()
    inicio = datetime.combine(
        fecha - timedelta(days=dias_antes), datetime.min.time()
    ).replace(tzinfo=tz)
    fin = datetime.combine(fecha, datetime.max.time()).replace(tzinfo=tz)
    return inicio.isoformat(), fin.isoformat()


def _sum_aggregate_int(service, data_type: str, start_ms: int, end_ms: int) -> int:
    response = service.users().dataset().aggregate(
        userId="me",
        body={
            "aggregateBy": [{"dataTypeName": data_type}],
            "bucketByTime": {"durationMillis": 86400000},
            "startTimeMillis": str(start_ms),
            "endTimeMillis": str(end_ms),
        },
    ).execute()
    total = 0
    for bucket in response.get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for point in dataset.get("point", []):
                for val in point.get("value", []):
                    if "intVal" in val:
                        total += int(val.get("intVal") or 0)
                    elif "fpVal" in val:
                        total += int(val.get("fpVal") or 0)
    return total


def _sum_aggregate_float(service, data_type: str, start_ms: int, end_ms: int) -> float:
    response = service.users().dataset().aggregate(
        userId="me",
        body={
            "aggregateBy": [{"dataTypeName": data_type}],
            "bucketByTime": {"durationMillis": 86400000},
            "startTimeMillis": str(start_ms),
            "endTimeMillis": str(end_ms),
        },
    ).execute()
    total = 0.0
    for bucket in response.get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for point in dataset.get("point", []):
                for val in point.get("value", []):
                    if "fpVal" in val:
                        total += float(val.get("fpVal") or 0)
                    elif "intVal" in val:
                        total += float(val.get("intVal") or 0)
    return total


# ═══════════════════════════════════════════════════════════════
# OBTENER DATOS DE SUEÑO
# ═══════════════════════════════════════════════════════════════

def obtener_sueno(fecha: date, service=None) -> Dict:
    """
    Obtiene sueño de Google Fit para la noche que termina en `fecha`
    (despertar del día seleccionado).
    """
    resultado = {
        "horas_sueno": None,
        "calidad_sueno": None,
        "hora_dormir": None,
        "hora_despertar": None,
        "_fuente": None,
    }

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        # 1) Sesiones de sueño (activityType 72) — lo más fiable en Wear/Fitbit/Pixel
        try:
            start_rfc, end_rfc = _rfc3339_rango(fecha, dias_antes=1)
            sessions_response = service.users().sessions().list(
                userId="me",
                startTime=start_rfc,
                endTime=end_rfc,
                activityType=72,
            ).execute()
            for sesion in sessions_response.get("session", []) or []:
                if "startTimeMillis" not in sesion or "endTimeMillis" not in sesion:
                    continue
                inicio = _ms_a_datetime(sesion["startTimeMillis"])
                fin = _ms_a_datetime(sesion["endTimeMillis"])
                # Sueño de "hoy" = el que termina el día seleccionado (despertar)
                if fin.date() != fecha and inicio.date() != fecha:
                    continue
                horas = (fin - inicio).total_seconds() / 3600.0
                if horas < 1:
                    continue
                resultado = {
                    "horas_sueno": round(horas, 1),
                    "calidad_sueno": min(10, max(1, int(horas))),
                    "hora_dormir": inicio.strftime("%H:%M"),
                    "hora_despertar": fin.strftime("%H:%M"),
                    "_fuente": "sessions",
                }
                return resultado
        except Exception as e:
            print(f"[GoogleFit] Sueño sessions: {e}")

        # 2) Segmentos de sueño (varias data sources)
        fecha_inicio = fecha - timedelta(days=1)
        start_ns = _fecha_a_nanos(fecha_inicio)
        end_ns = _fecha_a_nanos(fecha, fin_dia=True)
        source_ids = [
            "derived:com.google.sleep.segment:com.google.android.gms:merged",
            "derived:com.google.sleep.segment:com.google.android.gms:merge_sleep_segments",
        ]
        try:
            sources = service.users().dataSources().list(
                userId="me",
                dataTypeName="com.google.sleep.segment",
            ).execute()
            for ds in sources.get("dataSource", []) or []:
                dsid = ds.get("dataStreamId")
                if dsid and dsid not in source_ids:
                    source_ids.append(dsid)
        except Exception as e:
            print(f"[GoogleFit] list sleep sources: {e}")

        puntos = []
        for dsid in source_ids:
            try:
                response = service.users().dataSources().datasets().get(
                    userId="me",
                    dataSourceId=dsid,
                    datasetId=f"{start_ns}-{end_ns}",
                ).execute()
                pts = response.get("point", []) or []
                if pts:
                    puntos = pts
                    resultado["_fuente"] = f"dataset:{dsid.split(':')[-1]}"
                    break
            except Exception as e:
                print(f"[GoogleFit] sleep dataset {dsid[-40:]}: {e}")

        if not puntos:
            return resultado

        total_segundos = 0
        inicio_sueno = None
        fin_sueno = None
        etapas = []

        for punto in puntos:
            inicio = _nanos_a_datetime(int(punto["startTimeNanos"]))
            fin = _nanos_a_datetime(int(punto["endTimeNanos"]))
            tipo = punto["value"][0]["intVal"] if punto.get("value") else 1
            # 1=awake 2=light 3=deep 4=rem 5=sleep(out)/generic
            if tipo in (2, 3, 4, 5):
                duracion = (fin - inicio).total_seconds()
                total_segundos += duracion
                etapas.append({"tipo": tipo, "duracion": duracion})
                if inicio_sueno is None or inicio < inicio_sueno:
                    inicio_sueno = inicio
                if fin_sueno is None or fin > fin_sueno:
                    fin_sueno = fin

        if total_segundos <= 0:
            return resultado

        horas = total_segundos / 3600
        sueno_profundo = sum(e["duracion"] for e in etapas if e["tipo"] == 3)
        sueno_rem = sum(e["duracion"] for e in etapas if e["tipo"] == 4)
        pct_calidad = (
            (sueno_profundo + sueno_rem) / total_segundos if total_segundos > 0 else 0
        )
        calidad = min(10, max(1, int(pct_calidad * 15 + horas * 0.5)))
        resultado.update({
            "horas_sueno": round(horas, 1),
            "calidad_sueno": calidad,
            "hora_dormir": inicio_sueno.strftime("%H:%M") if inicio_sueno else None,
            "hora_despertar": fin_sueno.strftime("%H:%M") if fin_sueno else None,
        })

    except Exception as e:
        print(f"[GoogleFit] Error obteniendo sueño: {e}")

    return resultado


# ═══════════════════════════════════════════════════════════════
# OBTENER DATOS DE EJERCICIO
# ═══════════════════════════════════════════════════════════════

def obtener_ejercicio(fecha: date, service=None) -> Dict:
    """
    Obtiene sesiones de ejercicio + pasos/calorías de Google Fit.
    """
    resultado = {
        "hizo_ejercicio": False,
        "tipo_ejercicio": None,
        "duracion_minutos": None,
        "calorias": None,
        "pasos": None,
        "sesiones": [],
    }

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        start_ms, end_ms = _rango_dia_ms(fecha)
        start_rfc, end_rfc = _rfc3339_rango(fecha)

        ACTIVIDADES = {
            1: "Aeróbicos", 7: "Caminata", 8: "Carrera",
            9: "Bicicleta", 10: "Bicicleta", 13: "Calistenia",
            15: "Cardio", 17: "Escalada", 20: "Entrenamiento fuerza",
            21: "Fútbol", 29: "Natación", 35: "Fuerza",
            36: "Pilates", 37: "Yoga", 45: "Entrenamiento funcional",
            72: "Sueño", 93: "Entrenamiento fuerza", 97: "Pesas",
        }

        sesiones_info = []
        duracion_total = 0.0

        try:
            sessions_response = service.users().sessions().list(
                userId="me",
                startTime=start_rfc,
                endTime=end_rfc,
            ).execute()
            for sesion in sessions_response.get("session", []) or []:
                tipo_id = int(sesion.get("activityType", 0) or 0)
                if tipo_id == 72:  # sueño no es ejercicio
                    continue
                if "startTimeMillis" not in sesion or "endTimeMillis" not in sesion:
                    continue
                duracion_ms = int(sesion["endTimeMillis"]) - int(sesion["startTimeMillis"])
                duracion_min = max(0, duracion_ms / 60000.0)
                if duracion_min < 1:
                    continue
                tipo_nombre = ACTIVIDADES.get(tipo_id, f"Ejercicio ({tipo_id})")
                duracion_total += duracion_min
                sesiones_info.append({
                    "tipo": tipo_nombre,
                    "duracion_min": round(duracion_min),
                })
        except Exception as e:
            print(f"[GoogleFit] sessions ejercicio: {e}")

        # Pasos / calorías (aggregate) — independientes de sesiones
        pasos_total = 0
        calorias_total = 0.0
        try:
            pasos_total = _sum_aggregate_int(
                service, "com.google.step_count.delta", start_ms, end_ms
            )
        except Exception as e:
            print(f"[GoogleFit] pasos: {e}")
        try:
            calorias_total = _sum_aggregate_float(
                service, "com.google.calories.expended", start_ms, end_ms
            )
        except Exception as e:
            print(f"[GoogleFit] calorias: {e}")

        # Si no hay sesiones pero hay muchos pasos, sugerir caminata
        if not sesiones_info and pasos_total >= 5000:
            # ~100 pasos/min caminando aprox. (heurística suave)
            estim_min = max(10, min(180, int(pasos_total / 100)))
            sesiones_info = [{"tipo": "Caminata", "duracion_min": estim_min}]
            duracion_total = estim_min

        if sesiones_info:
            resultado = {
                "hizo_ejercicio": True,
                "tipo_ejercicio": sesiones_info[0]["tipo"],
                "duracion_minutos": round(duracion_total),
                "calorias": round(calorias_total) if calorias_total else None,
                "pasos": pasos_total,
                "sesiones": sesiones_info,
            }
        else:
            resultado["pasos"] = pasos_total
            resultado["calorias"] = round(calorias_total) if calorias_total else None

    except Exception as e:
        print(f"[GoogleFit] Error obteniendo ejercicio: {e}")

    return resultado


# ═══════════════════════════════════════════════════════════════
# OBTENER FRECUENCIA CARDÍACA
# ═══════════════════════════════════════════════════════════════

def obtener_frecuencia_cardiaca(fecha: date, service=None) -> Dict:
    """Obtiene frecuencia cardíaca promedio y máxima del día."""
    resultado = {"fc_promedio": None, "fc_maxima": None}

    try:
        if service is None:
            service = get_fit_service()
        if service is None:
            return resultado

        start_ms, end_ms = _rango_dia_ms(fecha)
        samples: list[float] = []

        # 1) Resumen agregado
        try:
            response = service.users().dataset().aggregate(
                userId="me",
                body={
                    "aggregateBy": [{"dataTypeName": "com.google.heart_rate.summary"}],
                    "bucketByTime": {"durationMillis": 86400000},
                    "startTimeMillis": str(start_ms),
                    "endTimeMillis": str(end_ms),
                },
            ).execute()
            for bucket in response.get("bucket", []):
                for dataset in bucket.get("dataset", []):
                    for point in dataset.get("point", []):
                        vals = point.get("value", []) or []
                        # summary suele ser [avg, max, min] como fpVal
                        fps = [float(v["fpVal"]) for v in vals if "fpVal" in v]
                        if len(fps) >= 2:
                            resultado["fc_promedio"] = round(fps[0]) or None
                            resultado["fc_maxima"] = round(fps[1]) or None
                            return resultado
                        for v in vals:
                            # mapVal style
                            for m in v.get("mapVal", []) or []:
                                key = (m.get("key") or "").lower()
                                fp = m.get("value", {}).get("fpVal")
                                if fp is None:
                                    continue
                                if "average" in key or "mean" in key or key == "average":
                                    resultado["fc_promedio"] = round(fp) or None
                                if "max" in key:
                                    resultado["fc_maxima"] = round(fp) or None
        except Exception as e:
            print(f"[GoogleFit] HR summary: {e}")

        if resultado["fc_promedio"] or resultado["fc_maxima"]:
            return resultado

        # 2) Muestras bpm crudas → media / max
        try:
            response = service.users().dataset().aggregate(
                userId="me",
                body={
                    "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
                    "bucketByTime": {"durationMillis": 3600000},
                    "startTimeMillis": str(start_ms),
                    "endTimeMillis": str(end_ms),
                },
            ).execute()
            for bucket in response.get("bucket", []):
                for dataset in bucket.get("dataset", []):
                    for point in dataset.get("point", []):
                        for val in point.get("value", []) or []:
                            if "fpVal" in val:
                                samples.append(float(val["fpVal"]))
                            elif "intVal" in val:
                                samples.append(float(val["intVal"]))
                            # legacy key/mean style
                            if val.get("key") in ("mean", "average") and val.get("fpVal"):
                                samples.append(float(val["fpVal"]))
                            if val.get("key") == "max" and val.get("fpVal"):
                                resultado["fc_maxima"] = round(float(val["fpVal"])) or None
        except Exception as e:
            print(f"[GoogleFit] HR bpm: {e}")

        if samples:
            resultado["fc_promedio"] = round(sum(samples) / len(samples)) or None
            resultado["fc_maxima"] = round(max(samples)) or None

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
            return {"error": "Google Fit no configurado"}

        sueno = obtener_sueno(fecha, service)
        ejercicio = obtener_ejercicio(fecha, service)
        fc = obtener_frecuencia_cardiaca(fecha, service)

        avisos = []
        if sueno.get("horas_sueno") is None:
            avisos.append(
                "Sin sueño en Fit para esta fecha (¿el dispositivo guarda sueño en Google Fit?)."
            )
        if not ejercicio.get("hizo_ejercicio") and not (ejercicio.get("pasos") or 0):
            avisos.append("Sin actividad/pasos detectados.")
        if fc.get("fc_promedio") is None:
            avisos.append(
                "Sin frecuencia cardíaca (hace falta reloj/banda que escriba FC en Fit)."
            )

        return {
            # Sueño
            "horas_sueno": sueno["horas_sueno"],
            "calidad_sueno": sueno["calidad_sueno"],
            "hora_dormir": sueno["hora_dormir"],
            "hora_despertar": sueno["hora_despertar"],
            # Ejercicio
            "hizo_ejercicio": ejercicio["hizo_ejercicio"],
            "tipo_ejercicio": ejercicio["tipo_ejercicio"],
            "duracion_minutos": ejercicio["duracion_minutos"],
            "sesiones_fit": ejercicio["sesiones"],
            "calorias": ejercicio.get("calorias"),
            "pasos": ejercicio.get("pasos"),
            # Cardíaco
            "fc_promedio": fc["fc_promedio"],
            "fc_maxima": fc["fc_maxima"],
            # Manual
            "energia_manana": None,
            "energia_tarde": None,
            "energia_noche": None,
            "productividad_percibida": None,
            "notas_ejercicio": None,
            "avisos_fit": avisos,
            "fuente_sueno": sueno.get("_fuente"),
        }
    except Exception as e:
        print(f"[GoogleFit] Error obtener_datos_dia: {e}")
        return {"error": str(e)}
