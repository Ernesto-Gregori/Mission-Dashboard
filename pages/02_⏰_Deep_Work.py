"""
⏰ Deep Work - Gestión de bloques de tiempo y productividad
"""

import streamlit as st
from datetime import datetime, date, timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
import sqlite3

st.set_page_config(
    page_title="Deep Work | Mission Dashboard",
    page_icon="⏰",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CSS PERSONALIZADO
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .bloque-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    .bloque-pendiente { border-left: 4px solid #8b949e; }
    .bloque-completado { border-left: 4px solid #3fb950; opacity: 0.8; }
    .bloque-parcial { border-left: 4px solid #e3b341; }
    .hora-badge {
        background: #21262d;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.875rem;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def obtener_bloques_fijos():
    """Obtiene bloques fijos con cache para evitar recargas"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bloques_fijos WHERE activo = 1 ORDER BY hora_inicio")
    bloques = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bloques

def obtener_estado_sesion(fecha: str, bloque_id: int):
    """Obtiene estado de una sesión específica"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT estado FROM sesiones_completadas 
        WHERE fecha = ? AND bloque_fijo_id = ?
    """, (fecha, bloque_id))
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else None

def registrar_sesion(fecha: str, bloque_id: int, estado: str, notas: str = ""):
    """Registra o actualiza una sesión"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sesiones_completadas 
        (fecha, bloque_fijo_id, estado, notas)
        VALUES (?, ?, ?, ?)
    """, (fecha, bloque_id, estado, notas))
    conn.commit()
    conn.close()
    # Limpiar cache para refrescar datos
    obtener_bloques_fijos.clear()

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("⏰ Deep Work")
st.caption("Bloques de tiempo para enfoque profundo")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📅 Fecha de trabajo")
    fecha_seleccionada = st.date_input("Seleccionar fecha", value=date.today(), key="fecha_deep_work")
    
    dia_semana = fecha_seleccionada.weekday()
    dias_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    st.info(f"**{dias_nombres[dia_semana]}** {fecha_seleccionada.strftime('%d/%m/%Y')}")
    
    if dia_semana in [1, 3]:  # Martes o Jueves
        st.success("📚 Hoy es día de Biblioteca")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_semana, tab_config = st.tabs(["📋 Mi Día", "📊 Semana", "⚙️ Configuración"])

# ═══════════════════════════════════════════════════════════════
# TAB 1: MI DÍA - SIN DUPLICACIONES (LÓGICA CORREGIDA)
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    st.subheader(f"Bloques para el {fecha_seleccionada.strftime('%d/%m/%Y')}")
    
    # Obtener datos
    bloques = obtener_bloques_fijos()
    fecha_str = fecha_seleccionada.isoformat()
    dia_numero = dia_semana + 1  # 1-7 para JSON
    
    # FILTRAR bloques que aplican a ESTE día específico
    bloques_hoy = []
    for bloque in bloques:
        dias_bloque = json.loads(bloque['dias_semana'])
        if dia_numero in dias_bloque:
            bloques_hoy.append(bloque)
    
    if not bloques_hoy:
        st.info("🌴 No hay bloques programados para este día.")
    else:
        # Renderizar UNO POR UNO, sin loops complejos de columnas
        for bloque in bloques_hoy:
            estado_actual = obtener_estado_sesion(fecha_str, bloque['id'])
            
            # Determinar estilo visual
            if estado_actual == 'Completado':
                clase_css = "bloque-completado"
                emoji = "✅"
            elif estado_actual == 'Parcial':
                clase_css = "bloque-parcial"
                emoji = "⏳"
            else:
                clase_css = "bloque-pendiente"
                emoji = "○"
            
            # Calcular duración
            h_inicio = datetime.strptime(bloque['hora_inicio'], '%H:%M')
            h_fin = datetime.strptime(bloque['hora_fin'], '%H:%M')
            duracion_min = int((h_fin - h_inicio).total_seconds() / 60)
            
            # CARD PRINCIPAL
            col_info, col_accion = st.columns([4, 1])
            
            with col_info:
                st.markdown(f"""
                <div class="bloque-card {clase_css}">
                    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                        <span style="font-size: 1.25rem;">{emoji}</span>
                        <span style="color: {bloque['color']}; font-weight: 600; font-size: 1.1rem;">
                            {bloque['nombre']}
                        </span>
                        <span class="hora-badge">{bloque['hora_inicio']} – {bloque['hora_fin']}</span>
                        <span style="color: #8b949e;">({duracion_min} min)</span>
                    </div>
                    <div style="color: #8b949e; font-size: 0.875rem;">
                        {bloque['tipo']} • {estado_actual or 'Pendiente'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col_accion:
                # POPOVER con key única
                with st.popover("⚡ Marcar", use_container_width=True):
                    st.markdown(f"**{bloque['nombre']}**")
                    
                    # KEY ÚNICA: combina ID del bloque + fecha
                    key_base = f"{bloque['id']}_{fecha_str}"
                    
                    nuevo_estado = st.selectbox(
                        "Estado",
                        ["Pendiente", "Completado", "Parcial", "No_realizado", "Postergado"],
                        index=["Pendiente", "Completado", "Parcial", "No_realizado", "Postergado"].index(estado_actual) if estado_actual else 0,
                        key=f"estado_{key_base}"
                    )
                    
                    notas = st.text_area(
                        "Notas de la sesión",
                        placeholder="¿Qué lograste? ¿Hubo distracciones?",
                        key=f"notas_{key_base}"
                    )
                    
                    if st.button("💾 Guardar", key=f"guardar_{key_base}", use_container_width=True):
                        registrar_sesion(fecha_str, bloque['id'], nuevo_estado, notas)
                        st.success("✅ Guardado")
                        st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: SEMANA (placeholder)
# ═══════════════════════════════════════════════════════════════

with tab_semana:
    st.subheader("Vista Semanal")
    st.info("🚧 Próximamente: Heatmap de productividad semanal")

# ═══════════════════════════════════════════════════════════════
# TAB 3: CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

with tab_config:
    st.subheader("Bloques Configurados")
    
    todos_bloques = obtener_bloques_fijos()
    for b in todos_bloques:
        dias = json.loads(b['dias_semana'])
        dias_txt = ", ".join(["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][d-1] for d in dias)
        
        st.markdown(f"""
        <div class="bloque-card">
            <div style="display: flex; justify-content: space-between;">
                <span style="color: {b['color']}; font-weight: 600;">{b['nombre']}</span>
                <span class="hora-badge">{b['hora_inicio']} – {b['hora_fin']}</span>
            </div>
            <div style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">
                Días: {dias_txt}
            </div>
        </div>
        """, unsafe_allow_html=True)

st.divider()
st.caption("⏰ Módulo Deep Work")