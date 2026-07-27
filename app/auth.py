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
)
from app.stability import invalidate_data_caches


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
        st.caption("Esta contraseña se guarda cifrada (hash). No se almacena en texto plano.")
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
                user = autenticar_usuario(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.session_state.user_name = user["username"]
                    st.rerun()
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
    """
    ensure_database()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.authenticated and st.session_state.user:
        return st.session_state.user

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
    st.caption("Mínimo 3 caracteres en el usuario y 6 en la contraseña.")
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
                    invalidate_data_caches()
                    st.success(f"✅ {msg}: **{nuevo_user.strip().lower()}**")
                    st.rerun()
                else:
                    st.error(msg)
