"""
🔐 Usuarios — Crear y gestionar accesos a Mission Dashboard
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import listar_usuarios, crear_usuario
from app.auth import require_auth, panel_gestion_usuarios, logout

st.set_page_config(
    page_title="Usuarios | Mission Dashboard",
    page_icon="🔐",
    layout="wide",
)

require_auth()
ensure_database()

st.title("🔐 Usuarios y seguridad")
st.caption(
    "Cada usuario tiene su propio sistema (finanzas, hábitos, salud, etc.). "
    "Las contraseñas se guardan con hash."
)

user = st.session_state.get("user") or {}
st.info(
    f"Sesión actual: **{user.get('username', '—')}** · rol **{user.get('rol', '—')}**"
)

if user.get("rol") != "admin":
    st.warning("Tu cuenta no es administrador. Pide a un admin que te dé acceso o cree usuarios.")
    st.stop()

panel_gestion_usuarios()

st.divider()
col1, col2 = st.columns(2)
with col1:
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        logout()
with col2:
    st.caption("Tip: esta página aparece en el menú lateral como **Usuarios**.")
