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
from app.ai_client import chat_simple, api_key_configurada
import sqlite3

st.set_page_config(
    page_title="Deep Work | Mission Dashboard",
    page_icon="⏰",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CSS
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bloques_fijos WHERE activo = 1 ORDER BY hora_inicio")
    bloques = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bloques

def obtener_estado_sesion(fecha: str, bloque_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT estado, notas FROM sesiones_completadas 
        WHERE fecha = ? AND bloque_fijo_id = ?
    """, (fecha, bloque_id))
    resultado = cursor.fetchone()
    conn.close()
    return (resultado[0], resultado[1]) if resultado else (None, None)

def registrar_sesion(fecha: str, bloque_id: int, estado: str, notas: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sesiones_completadas 
        (fecha, bloque_fijo_id, estado, notas)
        VALUES (?, ?, ?, ?)
    """, (fecha, bloque_id, estado, notas))
    conn.commit()
    conn.close()
    obtener_bloques_fijos.clear()

def obtener_sesiones_semana(fecha_inicio: str, fecha_fin: str):
    """Obtiene todas las sesiones de una semana para análisis."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sc.*, bf.nombre, bf.tipo, bf.hora_inicio, bf.hora_fin
        FROM sesiones_completadas sc
        JOIN bloques_fijos bf ON sc.bloque_fijo_id = bf.id
        WHERE sc.fecha BETWEEN ? AND ?
        ORDER BY sc.fecha, bf.hora_inicio
    """, (fecha_inicio, fecha_fin))
    sesiones = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sesiones

# ═══════════════════════════════════════════════════════════════
# HELPERS DE IA
# ═══════════════════════════════════════════════════════════════

SYSTEM_COACH = """Eres un coach de productividad cristiano para un estudiante de teología 
que también programa. Eres directo, práctico y motivador. Máximo 100 palabras por respuesta."""

def _construir_resumen_semana(sesiones: list) -> str:
    """Construye un resumen legible de la semana para enviarlo a la IA."""
    if not sesiones:
        return "Sin sesiones registradas esta semana."
    
    total = len(sesiones)
    completados = len([s for s in sesiones if s['estado'] == 'Completado'])
    parciales = len([s for s in sesiones if s['estado'] == 'Parcial'])
    no_realizados = len([s for s in sesiones if s['estado'] == 'No_realizado'])
    
    por_tipo = {}
    for s in sesiones:
        tipo = s['tipo']
        if tipo not in por_tipo:
            por_tipo[tipo] = {'total': 0, 'completados': 0}
        por_tipo[tipo]['total'] += 1
        if s['estado'] == 'Completado':
            por_tipo[tipo]['completados'] += 1
    
    resumen = f"Semana: {total} bloques. Completados: {completados}, Parciales: {parciales}, No realizados: {no_realizados}.\n"
    resumen += "Por tipo: " + ", ".join(
        f"{tipo}: {v['completados']}/{v['total']}" for tipo, v in por_tipo.items()
    )
    
    # Agregar notas relevantes
    notas = [s['notas'] for s in sesiones if s['notas'] and len(s['notas']) > 10]
    if notas:
        resumen += f"\nNotas del usuario: {' | '.join(notas[:3])}"
    
    return resumen

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
    
    if dia_semana in [1, 3]:
        st.success("📚 Hoy es día de Biblioteca")
    
    # Estado IA en sidebar
    st.divider()
    if api_key_configurada():
        st.success("🤖 Coach IA activo")
    else:
        st.caption("🤖 Coach IA en modo offline")

# ═══════════════════════════════════════════════════════════════
# TABS — agregamos "🤖 Coach IA"
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_semana, tab_ia, tab_config = st.tabs([
    "📋 Mi Día", "📊 Semana", "🤖 Coach IA", "⚙️ Configuración"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: MI DÍA
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    st.subheader(f"Bloques para el {fecha_seleccionada.strftime('%d/%m/%Y')}")
    
    bloques = obtener_bloques_fijos()
    fecha_str = fecha_seleccionada.isoformat()
    dia_numero = dia_semana + 1
    
    bloques_hoy = [b for b in bloques if dia_numero in json.loads(b['dias_semana'])]
    
    if not bloques_hoy:
        st.info("🌴 No hay bloques programados para este día.")
    else:
        for bloque in bloques_hoy:
            estado_actual, notas_actuales = obtener_estado_sesion(fecha_str, bloque['id'])
            
            if estado_actual == 'Completado':
                clase_css, emoji = "bloque-completado", "✅"
            elif estado_actual == 'Parcial':
                clase_css, emoji = "bloque-parcial", "⏳"
            else:
                clase_css, emoji = "bloque-pendiente", "○"
            
            h_inicio = datetime.strptime(bloque['hora_inicio'], '%H:%M')
            h_fin = datetime.strptime(bloque['hora_fin'], '%H:%M')
            duracion_min = int((h_fin - h_inicio).total_seconds() / 60)
            
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
                with st.popover("⚡ Marcar", use_container_width=True):
                    st.markdown(f"**{bloque['nombre']}**")
                    key_base = f"{bloque['id']}_{fecha_str}"
                    
                    nuevo_estado = st.selectbox(
                        "Estado",
                        ["Pendiente", "Completado", "Parcial", "No_realizado", "Postergado"],
                        index=["Pendiente", "Completado", "Parcial", "No_realizado", "Postergado"].index(estado_actual) if estado_actual else 0,
                        key=f"estado_{key_base}"
                    )
                    
                    notas = st.text_area(
                        "Notas de la sesión",
                        value=notas_actuales or "",
                        placeholder="¿Qué lograste? ¿Hubo distracciones?",
                        key=f"notas_{key_base}"
                    )
                    
                    if st.button("💾 Guardar", key=f"guardar_{key_base}", use_container_width=True):
                        registrar_sesion(fecha_str, bloque['id'], nuevo_estado, notas)
                        st.success("✅ Guardado")
                        st.rerun()
                    
                    # ── COACH DE SESIÓN ──────────────────────
                    st.divider()
                    st.caption("🤖 Coach IA")
                    
                    tipo_ayuda_coach = st.selectbox(
                        "Tipo",
                        ["Motivación para iniciar", "Estrategia de enfoque", "Resumen de lo logrado"],
                        key=f"tipo_coach_{key_base}"
                    )
                    
                    if st.button("✨ Pedir consejo", key=f"coach_{key_base}", use_container_width=True):
                        contexto_bloque = (
                            f"Bloque: {bloque['nombre']} ({bloque['tipo']}), "
                            f"{bloque['hora_inicio']}–{bloque['hora_fin']} ({duracion_min} min). "
                            f"Estado: {estado_actual or 'Pendiente'}. "
                            f"Notas: {notas or 'Sin notas'}."
                        )
                        
                        prompts = {
                            "Motivación para iniciar": f"Dame una motivación breve y práctica para iniciar este bloque ahora mismo. {contexto_bloque}",
                            "Estrategia de enfoque": f"Sugiere una estrategia concreta para maximizar este bloque. {contexto_bloque}",
                            "Resumen de lo logrado": f"Ayúdame a reflexionar sobre lo logrado en este bloque. {contexto_bloque}",
                        }
                        
                        with st.spinner("Coach pensando..."):
                            respuesta = chat_simple(
                                prompts[tipo_ayuda_coach],
                                contexto=SYSTEM_COACH
                            )
                            st.info(respuesta)

# ═══════════════════════════════════════════════════════════════
# TAB 2: SEMANA
# ═══════════════════════════════════════════════════════════════

with tab_semana:
    st.subheader("Vista Semanal")
    
    # Calcular lunes y domingo de la semana seleccionada
    lunes = fecha_seleccionada - timedelta(days=fecha_seleccionada.weekday())
    domingo = lunes + timedelta(days=6)
    
    sesiones_semana = obtener_sesiones_semana(lunes.isoformat(), domingo.isoformat())
    
    st.caption(f"Semana del {lunes.strftime('%d/%m')} al {domingo.strftime('%d/%m/%Y')}")
    
    if not sesiones_semana:
        st.info("📊 Sin sesiones registradas esta semana.")
    else:
        # Métricas rápidas
        total = len(sesiones_semana)
        completados = len([s for s in sesiones_semana if s['estado'] == 'Completado'])
        tasa = int(completados / total * 100) if total > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total bloques", total)
        col2.metric("Completados", completados)
        col3.metric("Tasa de éxito", f"{tasa}%")
        
        st.progress(tasa / 100, text=f"{tasa}% de bloques completados")
        
        # Tabla por día
        st.divider()
        for dia_offset in range(7):
            dia = lunes + timedelta(days=dia_offset)
            sesiones_dia = [s for s in sesiones_semana if s['fecha'] == dia.isoformat()]
            
            if sesiones_dia:
                completados_dia = len([s for s in sesiones_dia if s['estado'] == 'Completado'])
                emoji_dia = "✅" if completados_dia == len(sesiones_dia) else "⚡" if completados_dia > 0 else "○"
                
                with st.expander(f"{emoji_dia} {dias_nombres[dia_offset]} {dia.strftime('%d/%m')} — {completados_dia}/{len(sesiones_dia)} completados"):
                    for s in sesiones_dia:
                        color = "#3fb950" if s['estado'] == 'Completado' else "#e3b341" if s['estado'] == 'Parcial' else "#8b949e"
                        st.markdown(f"- <span style='color:{color}'>{s['nombre']}</span> ({s['hora_inicio']}–{s['hora_fin']}) • {s['estado']}", unsafe_allow_html=True)
                        if s['notas']:
                            st.caption(f"  📝 {s['notas']}")

# ═══════════════════════════════════════════════════════════════
# TAB 3: COACH IA — ANÁLISIS DE PRODUCTIVIDAD
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Coach de Productividad")
    
    if not api_key_configurada():
        st.warning("⚠️ Coach IA en modo offline — respuestas predefinidas disponibles.")
    
    # Selector de semana a analizar
    lunes_ia = fecha_seleccionada - timedelta(days=fecha_seleccionada.weekday())
    domingo_ia = lunes_ia + timedelta(days=6)
    sesiones_ia = obtener_sesiones_semana(lunes_ia.isoformat(), domingo_ia.isoformat())
    resumen_semana = _construir_resumen_semana(sesiones_ia)
    
    st.caption(f"Analizando semana: {lunes_ia.strftime('%d/%m')} – {domingo_ia.strftime('%d/%m/%Y')}")
    
    col_datos, col_chat = st.columns([1, 2])
    
    with col_datos:
        st.markdown("**📊 Datos de la semana**")
        
        if sesiones_ia:
            total = len(sesiones_ia)
            completados = len([s for s in sesiones_ia if s['estado'] == 'Completado'])
            st.metric("Completados", f"{completados}/{total}")
            st.progress(completados / total if total > 0 else 0)
            
            # Desglose por tipo
            por_tipo = {}
            for s in sesiones_ia:
                t = s['tipo']
                por_tipo[t] = por_tipo.get(t, 0) + (1 if s['estado'] == 'Completado' else 0)
            
            for tipo, count in por_tipo.items():
                st.caption(f"• {tipo}: {count} completados")
        else:
            st.info("Sin datos esta semana.")
        
        st.divider()
        tipo_analisis = st.selectbox(
            "Tipo de análisis",
            [
                "Análisis general de la semana",
                "¿Por qué fallé en algunos bloques?",
                "Cómo mejorar la semana que viene",
                "Correlación descanso-productividad",
                "Qué bloque priorizar mañana",
            ]
        )
        
        contexto_adicional = st.text_area(
            "Contexto extra (opcional)",
            placeholder="Ej: Esta semana tuve exámenes en el instituto...",
            height=80
        )
    
    with col_chat:
        st.markdown("**💬 Análisis con IA**")
        
        if st.button("🚀 Analizar mi semana", use_container_width=True, type="primary"):
            prompt = f"""
{tipo_analisis}

Datos de productividad:
{resumen_semana}

{f'Contexto del usuario: {contexto_adicional}' if contexto_adicional else ''}

Sé específico con los datos. Da 2-3 observaciones concretas y 1 acción para esta semana.
"""
            with st.spinner("Analizando tu semana..."):
                respuesta = chat_simple(prompt, contexto=SYSTEM_COACH)
                st.info(respuesta)
        
        st.divider()
        
        # Chat libre con el coach
        st.markdown("**💬 Pregunta libre al coach**")
        pregunta_libre = st.text_input(
            "Tu pregunta",
            placeholder="Ej: ¿Cómo protejo el bloque de código de las 06:15?"
        )
        
        if pregunta_libre:
            with st.spinner("Coach pensando..."):
                respuesta_libre = chat_simple(
                    f"Contexto semanal: {resumen_semana}\n\nPregunta: {pregunta_libre}",
                    contexto=SYSTEM_COACH
                )
                st.info(respuesta_libre)

# ═══════════════════════════════════════════════════════════════
# TAB 4: CONFIGURACIÓN
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