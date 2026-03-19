"""
✝️ Bitácora Teológica - Devocionales 05:45 am
"""

import streamlit as st
from datetime import date, datetime, timedelta
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
import sqlite3

st.set_page_config(
    page_title="Teología | Mission Dashboard",
    page_icon="✝️",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .devocional-card {
        background: #161b22;
        border-left: 4px solid #a371f7;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .pasaje-box {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 1rem;
        font-family: Georgia, serif;
        font-style: italic;
        color: #f0f6fc;
        line-height: 1.6;
    }
    .reflexion-section {
        background: #21262d;
        border-radius: 8px;
        padding: 1rem;
        margin-top: 0.75rem;
    }
    .streak-badge {
        background: linear-gradient(90deg, #e3b341, #f778ba);
        color: #0d1117;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# FUNCIONES
# ═══════════════════════════════════════════════════════════════

def guardar_devocional(fecha, pasaje_ref, pasaje_texto, observacion, interpretacion, 
                     aplicacion, conexion_inst, conexion_sit, oracion, duracion, version_bib="NVI"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO devocionales (
            fecha, pasaje_referencia, pasaje_texto, version_biblia,
            observacion, interpretacion, aplicacion,
            conexion_instituto, conexion_situacion, oracion_escrita, duracion_minutos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, pasaje_ref, pasaje_texto, version_bib, observacion, interpretacion,
          aplicacion, conexion_inst, conexion_sit, oracion, duracion))
    conn.commit()
    conn.close()

def obtener_devocional(fecha):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devocionales WHERE fecha = ?", (fecha,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def obtener_devocionales_recientes(limite=7):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM devocionales ORDER BY fecha DESC LIMIT ?
    """, (limite,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def calcular_racha():
    """Calcula días consecutivos con devocionales"""
    devocionales = obtener_devocionales_recientes(30)
    if not devocionales:
        return 0
    
    fechas = [datetime.strptime(d['fecha'], '%Y-%m-%d').date() for d in devocionales]
    fechas.sort(reverse=True)
    
    racha = 0
    hoy = date.today()
    
    for i, fecha in enumerate(fechas):
        esperada = hoy - timedelta(days=i)
        if fecha == esperada:
            racha += 1
        else:
            break
    
    return racha

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("✝️ Bitácora Teológica")
st.caption("Devocionales 05:45 am • Método de estudio inductivo")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR - RACHA Y ESTADÍSTICAS
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔥 Tu racha")
    racha_actual = calcular_racha()
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0;">
        <div class="streak-badge">🔥 {racha_actual} días consecutivos</div>
    </div>
    """, unsafe_allow_html=True)
    
    if racha_actual == 0:
        st.info("📖 Hoy es un buen día para comenzar")
    elif racha_actual < 7:
        st.success(f"¡Vas bien! Llevas {racha_actual} días")
    else:
        st.success(f"¡Excelente disciplina! {racha_actual} días 🔥")
    
    st.divider()
    
    # Devocional de ayer para referencia
    ayer = date.today() - timedelta(days=1)
    dev_ayer = obtener_devocional(ayer)
    if dev_ayer:
        st.markdown("**📅 Ayer:**")
        st.caption(f"{dev_ayer['pasaje_referencia']}")
        with st.expander("Ver reflexión"):
            st.write(dev_ayer['aplicacion'][:100] + "..." if dev_ayer['aplicacion'] else "Sin aplicación")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_historial, tab_metodo = st.tabs(["📖 Hoy", "📚 Historial", "📖 Método"])

# ═══════════════════════════════════════════════════════════════
# TAB 1: HOY - Entrada de devocional
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    fecha_hoy = date.today()
    devocional_existente = obtener_devocional(fecha_hoy)
    
    if devocional_existente:
        st.success(f"✅ Devocional de hoy completado: **{devocional_existente['pasaje_referencia']}**")
        
        col_edit, col_ver = st.columns(2)
        with col_edit:
            if st.button("✏️ Editar entrada", use_container_width=True):
                st.session_state['editar_devocional'] = True
                st.rerun()
        with col_ver:
                with st.expander("Ver completo", expanded=True):
                    # PASAJE
                    pasaje_texto = devocional_existente['pasaje_texto'] or ''
                    version_biblia = devocional_existente['version_biblia'] or 'NVI'
                    
                    st.markdown(f"### ✝️ {devocional_existente['pasaje_referencia']}")
                    
                    if pasaje_texto.strip():
                        # Usar st.info para el pasaje con estilo especial
                        st.info(f"*{pasaje_texto}*\n\n— {version_biblia}")
                    else:
                        st.warning("📝 Texto del pasaje no guardado. Edita para agregarlo.")
                    
                    # SECCIONES DE REFLEXIÓN CON EXPANDERS NATIVOS
                    if devocional_existente['observacion']:
                        with st.expander("🔍 Observación", expanded=True):
                            st.write(devocional_existente['observacion'])
                    
                    if devocional_existente['interpretacion']:
                        with st.expander("💡 Interpretación", expanded=True):
                            st.write(devocional_existente['interpretacion'])
                    
                    if devocional_existente['aplicacion']:
                        with st.expander("🎯 Aplicación", expanded=True):
                            st.write(devocional_existente['aplicacion'])
                    
                    if devocional_existente['conexion_instituto']:
                        with st.expander("🏫 Conexión Instituto"):
                            st.write(devocional_existente['conexion_instituto'])
                    
                    if devocional_existente['conexion_situacion']:
                        with st.expander("🌍 Situación actual"):
                            st.write(devocional_existente['conexion_situacion'])
                    
                    if devocional_existente['oracion_escrita']:
                        with st.expander("🙏 Oración"):
                            st.write(f"*{devocional_existente['oracion_escrita']}*")
    else:
        st.info("🌅 Buenos días. Tiempo para tu devocional de las 05:45")
    
    # Mostrar formulario si no existe o si se quiere editar
    if not devocional_existente or st.session_state.get('editar_devocional'):
        if st.session_state.get('editar_devocional'):
            datos = devocional_existente
            st.session_state['editar_devocional'] = False
        else:
            datos = {}
        
        with st.form("devocional_form", clear_on_submit=not devocional_existente):
            st.markdown("### 📝 Tu devocional de hoy")
            
            col_pasaje, col_version = st.columns([3, 1])
            with col_pasaje:
                pasaje_ref = st.text_input(
                    "Pasaje bíblico *",
                    value=datos.get('pasaje_referencia', ''),
                    placeholder="Ej: Salmo 23:1-6, Juan 3:16, Romanos 8:28"
                )
            with col_version:
                version_bib = st.selectbox(
                    "Versión",
                    ["NVI", "RVR1960", "NLT", "ESV", "Otra"],
                    index=["NVI", "RVR1960", "NLT", "ESV", "Otra"].index(datos.get('version_biblia', 'NVI')) if datos.get('version_biblia') in ["NVI", "RVR1960", "NLT", "ESV", "Otra"] else 0
                )
            
            pasaje_texto = st.text_area(
                "Texto del pasaje (opcional, puedes copiarlo aquí)",
                value=datos.get('pasaje_texto', ''),
                height=100,
                placeholder="El Señor es mi pastor, nada me falta..."
            )
            
            st.divider()
            st.markdown("**Método de estudio inductivo**")
            
            observacion = st.text_area(
                "🔍 Observación: ¿Qué dice el texto? (Hechos, personajes, acciones)",
                value=datos.get('observacion', ''),
                height=80
            )
            
            interpretacion = st.text_area(
                "💡 Interpretación: ¿Qué significa? (Contexto, enseñanza principal)",
                value=datos.get('interpretacion', ''),
                height=80
            )
            
            aplicacion = st.text_area(
                "🎯 Aplicación: ¿Cómo aplica a mi vida hoy?",
                value=datos.get('aplicacion', ''),
                height=80
            )
            
            st.divider()
            st.markdown("**Conexiones personales**")
            
            col_inst, col_sit = st.columns(2)
            with col_inst:
                conexion_inst = st.text_area(
                    "🏫 Instituto: ¿Relación con clases actuales?",
                    value=datos.get('conexion_instituto', ''),
                    height=60,
                    placeholder="Ej: Hermenéutica, Teología Sistemática..."
                )
            with col_sit:
                conexion_sit = st.text_area(
                    "🌍 Situación actual: ¿Qué estoy viviendo?",
                    value=datos.get('conexion_situacion', ''),
                    height=60,
                    placeholder="Ej: Preparando examen, decisión importante..."
                )
            
            oracion = st.text_area(
                "🙏 Oración (escribe tu oración basada en este pasaje)",
                value=datos.get('oracion_escrita', ''),
                height=100
            )
            
            col_dur, col_guardar = st.columns([1, 2])
            with col_dur:
                duracion = st.number_input("Minutos", min_value=5, max_value=120, value=datos.get('duracion_minutos', 30))
            
            with col_guardar:
                submitted = st.form_submit_button("💾 Guardar devocional", use_container_width=True, type="primary")
            
            if submitted:
                if not pasaje_ref:
                    st.error("⚠️ El pasaje bíblico es obligatorio")
                else:
                    guardar_devocional(
                        fecha_hoy, pasaje_ref, pasaje_texto, observacion,
                        interpretacion, aplicacion, conexion_inst, conexion_sit,
                        oracion, duracion, version_bib
                    )
                    st.success("✅ Devocional guardado. ¡Día {0} completado!".format(racha_actual + 1))
                    st.balloons()
                    st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: HISTORIAL
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.subheader("Devocionales recientes")
    
    devocionales = obtener_devocionales_recientes(14)
    
    if not devocionales:
        st.info("📖 Aún no tienes devocionales registrados. Comienza hoy.")
    else:
        for dev in devocionales:
            fecha_dev = datetime.strptime(dev['fecha'], '%Y-%m-%d').strftime('%d/%m/%Y')
            
            with st.container():
                col_fecha, col_contenido = st.columns([1, 4])
                
                with col_fecha:
                    st.markdown(f"""
                    <div style="text-align: center; padding: 0.5rem;">
                        <div style="font-size: 0.875rem; color: #8b949e;">{fecha_dev}</div>
                        <div style="font-size: 1.5rem;">✅</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_contenido:
                    st.markdown(f"""
                    <div class="devocional-card" style="margin-bottom: 0.5rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: #a371f7; font-weight: 600;">{dev['pasaje_referencia']}</span>
                            <span style="font-size: 0.75rem; color: #8b949e;">{dev['duracion_minutos']} min</span>
                        </div>
                        <div style="color: #8b949e; font-size: 0.875rem; margin-top: 0.25rem;">
                            {dev['aplicacion'][:120] + '...' if dev['aplicacion'] and len(dev['aplicacion']) > 120 else (dev['aplicacion'] or 'Sin aplicación registrada')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# TAB 3: MÉTODO
# ═══════════════════════════════════════════════════════════════

with tab_metodo:
    st.subheader("Método de estudio inductivo")
    
    st.markdown("""
    ### 📖 Las 3 preguntas fundamentales
    
    | Paso | Pregunta | Enfoque |
    |------|----------|---------|
    | **1. Observación** | ¿Qué dice el texto? | Hechos, datos, lo que está explícito |
    | **2. Interpretación** | ¿Qué significa el texto? | Contexto, enseñanza, teología |
    | **3. Aplicación** | ¿Cómo aplica a mi vida? | Respuesta personal, compromiso |
    
    ### 🎯 Conexiones intencionales
    
    Tu devocional no es aislado. Conecta con:
    
    - **🏫 Instituto Bíblico**: ¿Cómo se relaciona con lo que estás estudiando?
    - **🌍 Situación actual**: ¿Qué estás viviendo hoy que ilumina este pasaje?
    - **💑 Matrimonio**: ¿Hay una aplicación para tu relación?
    - **💻 Programación**: ¿Alguna analogía o principio transferible?
    
    ### ⏰ La hora 05:45
    
    > *"La mañana es el momento en que la mente está más fresca para recibir verdad eterna."*
    
    - Preparar todo la noche anterior (Biblia, cuaderno, café)
    - Levantarse sin revisar el teléfono
    - 5 minutos de silencio antes de abrir la Biblia
    - Orar: *"Señor, habla hoy"*
    """)
    
    st.divider()
    st.caption("Basado en el método inductive de Kay Arthur y J.O. Sanders")

st.divider()
st.caption("✝️ Bitácora Teológica • Devocionales 05:45 am")