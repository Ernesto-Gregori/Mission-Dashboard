"""
auth.py - Autenticación centralizada para Mission Dashboard
"""
import streamlit as st

def check_password():
    """Verifica autenticación con contraseña."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        # Ocultar sidebar completamente
        st.markdown("""
            <style>
                [data-testid="stSidebar"] {display: none;}
                [data-testid="collapsedControl"] {display: none;}
            </style>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown("## 🏠 Mission Dashboard")
            st.markdown("Acceso privado — solo usuarios autorizados")
            st.markdown("<br>", unsafe_allow_html=True)
            pwd = st.text_input("Contraseña", type="password", key="pwd_input")
            if st.button("Entrar", use_container_width=True, type="primary"):
                try:
                    password_correcto = st.secrets.get("APP_PASSWORD", "")
                except Exception:
                    password_correcto = ""

                if pwd == password_correcto:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("❌ Contraseña incorrecta")
        st.stop()