"""
auth.py - Autenticación centralizada para Mission Dashboard

- Primer arranque: crea el usuario admin (hash PBKDF2 en BD)
- Login con usuario + contraseña en TODAS las páginas
- Panel opcional para crear más usuarios (rol admin)
"""
import streamlit as st

from app.database import (
    ensure_database,
    contar_usuarios,
    crear_usuario,
    autenticar_usuario,
    listar_usuarios,
    obtener_usuario_activo,
)
from app.multiuser import provision_user_defaults
from app.stability import invalidate_data_caches
from app.rate_limit import segundos_bloqueo, registrar_fallo, registrar_exito
from app.logging_config import get_logger

log = get_logger("auth")


def _ocultar_chrome():
    st.markdown("""
        <style>
            [data-testid="stSidebar"] {display: none !important;}
            [data-testid="collapsedControl"] {display: none !important;}
            section[data-testid="stSidebarNav"] {display: none !important;}
        </style>
    """, unsafe_allow_html=True)


def _bootstrap_desde_secrets() -> bool:
    """
    Si no hay usuarios y existe APP_PASSWORD en secrets,
    crea automáticamente el usuario 'admin' con esa clave.
    Así no se rompe un deploy que ya tenía solo secrets.
    """
    try:
        pwd = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        pwd = ""
    if not pwd:
        return False
    ok, _ = crear_usuario("admin", pwd, rol="admin")
    return ok


def _pantalla_setup():
    """Primer arranque: crear el usuario administrador."""
    _ocultar_chrome()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🏠 Mission Dashboard")
        st.markdown("### Primer acceso — crea tu usuario")
        st.caption("Esta contraseña se guarda cifrada (hash). Mínimo 8 caracteres. No se almacena en texto plano.")
        with st.form("setup_admin"):
            username = st.text_input("Usuario", value="admin")
            password = st.text_input("Contraseña", type="password")
            password2 = st.text_input("Repetir contraseña", type="password")
            submitted = st.form_submit_button(
                "Crear usuario y entrar",
                use_container_width=True,
                type="primary",
            )
            if submitted:
                if password != password2:
                    st.error("Las contraseñas no coinciden")
                else:
                    ok, msg = crear_usuario(username, password, rol="admin")
                    if ok:
                        user = autenticar_usuario(username, password)
                        if user:
                            # Sin módulos: el Coach arma el sistema en el primer login
                            provision_user_defaults(int(user["id"]), seed_modules=False)
                        st.session_state.authenticated = True
                        st.session_state.user = user
                        st.session_state.user_name = user["username"]
                        st.rerun()
                    else:
                        st.error(msg)
    st.stop()


def _pantalla_login():
    _ocultar_chrome()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🏠 Mission Dashboard")
        st.markdown("Acceso privado — solo usuarios autorizados")
        st.caption(
            "Si venías de la contraseña antigua en secrets, prueba usuario **admin** "
            "y esa misma contraseña (`APP_PASSWORD`)."
        )
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="admin")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button(
                "Entrar", use_container_width=True, type="primary"
            )
            if submitted:
                bloqueo = segundos_bloqueo(username)
                if bloqueo > 0:
                    st.error(
                        f"Demasiados intentos fallidos. Espera {bloqueo}s "
                        "antes de volver a intentar."
                    )
                else:
                    user = autenticar_usuario(username, password)
                    if user:
                        registrar_exito(username)
                        st.session_state.authenticated = True
                        st.session_state.user = user
                        st.session_state.user_name = user["username"]
                        st.rerun()
                    else:
                        lock = registrar_fallo(username)
                        log.warning("Login fallido user=%s", (username or "").strip().lower())
                        if lock > 0:
                            st.error(
                                f"❌ Credenciales incorrectas. "
                                f"Cuenta bloqueada temporalmente ({lock}s)."
                            )
                        else:
                            st.error("❌ Usuario o contraseña incorrectos")
        st.markdown("---")
        st.caption(
            "¿Primera vez y no hay usuarios? Reinicia la app sin usuarios en BD "
            "para ver la pantalla de creación. Luego usa el menú **Usuarios**."
        )
    st.stop()


def require_auth():
    """
    Llamar en CADA página justo después de st.set_page_config().
    Bloquea el acceso si no hay sesión autenticada.
    Revalida contra BD (usuario desactivado / borrado).
    """
    ensure_database()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.authenticated and st.session_state.user:
        raw = st.session_state.user
        uid_sess = raw.get("id") if isinstance(raw, dict) else None
        if uid_sess is not None:
            fresh = obtener_usuario_activo(int(uid_sess))
            if fresh:
                st.session_state.user = fresh
                st.session_state.user_name = fresh.get("username") or st.session_state.get("user_name")
                return fresh
        st.session_state.authenticated = False
        st.session_state.user = None

    n = contar_usuarios()
    if n == 0:
        # Intento de migración suave desde APP_PASSWORD legacy
        if _bootstrap_desde_secrets():
            st.info("Se creó el usuario **admin** desde APP_PASSWORD. Inicia sesión.")
            _pantalla_login()
        _pantalla_setup()

    _pantalla_login()


def check_password():
    """Alias legacy — preferir require_auth()."""
    return require_auth()


def logout():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.rerun()


def panel_gestion_usuarios():
    """UI para que un admin cree más usuarios. Usar en el dashboard o settings."""
    user = st.session_state.get("user") or {}
    if user.get("rol") != "admin":
        st.warning("Solo el administrador puede gestionar usuarios.")
        return

    st.subheader("👥 Usuarios registrados")
    usuarios = listar_usuarios()
    if usuarios:
        for u in usuarios:
            estado = "✅ activo" if u.get("activo") else "⏸️ inactivo"
            st.markdown(
                f"- **{u['username']}** · rol `{u.get('rol', 'usuario')}` · {estado}"
            )
    else:
        st.caption("No hay usuarios registrados.")

    st.divider()
    st.subheader("➕ Crear usuario nuevo")
    st.caption("Mínimo 3 caracteres en el usuario (a-z, 0-9, _) y 8 en la contraseña.")
    with st.form("crear_usuario_form", clear_on_submit=True):
        nuevo_user = st.text_input("Usuario nuevo", placeholder="ej: esposa")
        nueva_pwd = st.text_input("Contraseña", type="password")
        nueva_pwd2 = st.text_input("Repetir contraseña", type="password")
        rol = st.selectbox("Rol", ["usuario", "admin"])
        if st.form_submit_button("Crear usuario", type="primary", use_container_width=True):
            if nueva_pwd != nueva_pwd2:
                st.error("Las contraseñas no coinciden")
            else:
                ok, msg = crear_usuario(nuevo_user, nueva_pwd, rol=rol)
                if ok:
                    # Usuario nuevo: sin módulos; verá el Coach IA en el primer login
                    rows = __import__("app.database", fromlist=["ejecutar"]).ejecutar(
                        "SELECT id FROM usuarios WHERE username = ?",
                        [nuevo_user.strip().lower()], fetchall=True,
                    ) or []
                    if rows:
                        provision_user_defaults(int(rows[0]["id"]), seed_modules=False)
                    invalidate_data_caches()
                    st.success(
                        f"✅ {msg}: **{nuevo_user.strip().lower()}** "
                        "(al entrar verá el Coach para armar su sistema)"
                    )
                    st.rerun()
                else:
                    st.error(msg)
