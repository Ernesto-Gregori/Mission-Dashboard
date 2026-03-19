"""
🏠 Mission Dashboard - Control de Mando Personal
Sistema de gestión integral: Teología, Programación, Finanzas y Matrimonio
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN GLOBAL DE LA PÁGINA
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Mission Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Mission Dashboard v1.0 - Sistema de Gestión Integral"
    }
)

# ═══════════════════════════════════════════════════════════════
# CSS PERSONALIZADO - DARK MODE
# ═══════════════════════════════════════════════════════════════

def load_css():
    """Inyecta CSS personalizado para el tema oscuro"""
    dark_css = """
    <style>
        /* Variables de color */
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --accent-gold: #e3b341;
            --accent-blue: #58a6ff;
            --accent-green: #3fb950;
            --accent-purple: #a371f7;
            --accent-red: #f85149;
        }
        
        /* Fondo general */
        .stApp {
            background-color: var(--bg-primary);
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--bg-tertiary);
        }
        
        /* Headers */
        h1, h2, h3 {
            color: var(--text-primary) !important;
            font-weight: 600 !important;
        }
        
        /* Cards personalizadas */
        .mission-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--bg-tertiary);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: border-color 0.2s ease;
        }
        
        .mission-card:hover {
            border-color: var(--accent-blue);
        }
        
        .card-title {
            color: var(--accent-gold);
            font-size: 0.875rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }
        
        .card-value {
            color: var(--text-primary);
            font-size: 2rem;
            font-weight: 700;
        }
        
        /* Widget de hábitos */
        .habit-complete {
            color: var(--accent-green);
        }
        
        .habit-pending {
            color: var(--text-secondary);
        }
        
        /* Botones */
        .stButton > button {
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--bg-tertiary);
            border-radius: 8px;
        }
        
        .stButton > button:hover {
            border-color: var(--accent-blue);
        }
        
        /* Métricas */
        [data-testid="stMetricValue"] {
            color: var(--accent-gold) !important;
        }
        
        [data-testid="stMetricLabel"] {
            color: var(--text-secondary) !important;
        }
    </style>
    """
    st.markdown(dark_css, unsafe_allow_html=True)

# Cargar estilos
load_css()

# ═══════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN (Simulado por ahora)
# ═══════════════════════════════════════════════════════════════

if 'user_name' not in st.session_state:
    st.session_state.user_name = "Misionero"

# ═══════════════════════════════════════════════════════════════
# SIDEBAR - NAVEGACIÓN Y PERFIL
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    # Logo/Header
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <h1 style="color: #e3b341; margin: 0;">🎯 MISSION</h1>
        <p style="color: #8b949e; font-size: 0.75rem; margin: 0;">SISTEMA DE GESTIÓN INTEGRAL</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Perfil rápido
    st.markdown(f"""
    <div style="padding: 0.5rem;">
        <p style="color: #f0f6fc; margin: 0; font-weight: 600;">👤 {st.session_state.user_name}</p>
        <p style="color: #8b949e; margin: 0; font-size: 0.75rem;">{datetime.now().strftime('%A, %d de %B')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Navegación (Streamlit maneja esto automáticamente con pages/)
    st.markdown("""
    <p style="color: #8b949e; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">
        Navegación
    </p>
    """, unsafe_allow_html=True)
    
    # Info de versión
    st.divider()
    st.caption("v1.0 • Python + Streamlit")

# ═══════════════════════════════════════════════════════════════
# HEADER PRINCIPAL
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<h1 style="margin-bottom: 0.25rem;">Control de Mando</h1>
<p style="color: #8b949e; margin-top: 0;">Dashboard integral de vida</p>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# WIDGETS PRINCIPALES (Grid de 4 columnas)
# ═══════════════════════════════════════════════════════════════

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="mission-card">
        <div class="card-title">📖 Devocional</div>
        <div class="card-value" style="color: #3fb950;">✓</div>
        <p style="color: #8b949e; font-size: 0.875rem; margin: 0;">05:45 • Salmo 23</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="mission-card">
        <div class="card-title">💻 Código</div>
        <div class="card-value habit-pending">○</div>
        <p style="color: #8b949e; font-size: 0.875rem; margin: 0;">06:15 • Deep Work</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="mission-card">
        <div class="card-title">📚 Lectura</div>
        <div class="card-value habit-pending">○</div>
        <p style="color: #8b949e; font-size: 0.875rem; margin: 0;">Martes 19:30 • Biblioteca</p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="mission-card">
        <div class="card-title">💪 Calistenia</div>
        <div class="card-value habit-pending">○</div>
        <p style="color: #8b949e; font-size: 0.875rem; margin: 0;">Miércoles 16:30</p>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECCIÓN: RESUMEN DE MÓDULOS
# ═══════════════════════════════════════════════════════════════

st.subheader("🗂️ Módulos del Sistema")

# Grid de 2x3 para los módulos
mod_col1, mod_col2 = st.columns(2)

with mod_col1:
    # Finanzas
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">💰 Finanzas Personales</span>
                <span style="color: #3fb950; font-size: 0.875rem;">$12,450 MXN</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Presupuesto mensual • 67% utilizado
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Deep Work
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">⏰ Deep Work</span>
                <span style="color: #58a6ff; font-size: 0.875rem;">3/4 bloques</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Instituto 08:00-12:30 • Código 06:15-07:15
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Teología
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">✝️ Bitácora Teológica</span>
                <span style="color: #a371f7; font-size: 0.875rem;">7 entradas</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Devocionales 05:45 am • Último: Salmo 23
            </p>
        </div>
        """, unsafe_allow_html=True)

with mod_col2:
    # Biblioteca
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">📚 Biblioteca</span>
                <span style="color: #e3b341; font-size: 0.875rem;">487/500 libros</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Leyendo: "Systematic Theology" • 23%
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Salud
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">💪 Salud y Energía</span>
                <span style="color: #f85149; font-size: 0.875rem;">Energía: 7/10</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Calistenia ayer • Correlación: +15% focus
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # Matrimonio
    with st.container():
        st.markdown("""
        <div class="mission-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f0f6fc; font-weight: 600;">💑 Conexión Matrimonial</span>
                <span style="color: #ff69b4; font-size: 0.875rem;">Alerta: 20:30</span>
            </div>
            <p style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Próxima cita: Viernes 21:00 • Nota: Flores
            </p>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SECCIÓN: SECRETARIA IA (Preview)
# ═══════════════════════════════════════════════════════════════

st.divider()
st.subheader("🤖 Secretaria IA — Gemini")

ia_col1, ia_col2 = st.columns([2, 1])

with ia_col1:
    st.info("""
    **Próxima integración:** Google Gemini actuará como tu secretaria personal.
    
    Funciones planificadas:
    - Recordatorios contextuales (20:30 para modo pareja)
    - Análisis de correlación ejercicio-productividad
    - Resumen semanal de victorias los domingos 18:00
    - Sugerencias de lectura basadas en tus devocionales
    """)

with ia_col2:
    st.metric(
        label="Estado de conexión",
        value="OFFLINE",
        delta="Configurar API key"
    )

# ═══════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════

st.divider()
st.caption("Mission Dashboard • Construido con ❤️ y disciplina • Paso 1 completado")