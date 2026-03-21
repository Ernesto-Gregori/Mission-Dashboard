"""
💑 Conexión Matrimonial - Calendario de citas y sistema de alertas 20:30
"""

import streamlit as st
from datetime import date, datetime, timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
from app.ai_client import generar_alerta_matrimonio, api_key_configurada, chat_simple
import sqlite3

st.set_page_config(
    page_title="Matrimonio | Mission Dashboard",
    page_icon="💑",
    layout="wide"
)

init_database()

# ═════════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═════════════════════════════════════════════════════════════════

def obtener_citas(fecha_desde=None, estado=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM matrimonio_citas WHERE 1=1"
    params = []
    
    if fecha_desde:
        query += " AND fecha >= ?"
        params.append(fecha_desde)
    if estado:
        query += " AND estado_planificacion = ?"
        params.append(estado)
    
    query += " ORDER BY fecha, hora"
    
    cursor.execute(query, params)
    citas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return citas

def guardar_cita(fecha, hora, tipo, titulo, descripcion, lugar, presupuesto):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO matrimonio_citas (fecha, hora, tipo_cita, titulo, descripcion, lugar, presupuesto_estimado, estado_planificacion)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Planeando')
    """, (fecha, hora, tipo, titulo, descripcion, lugar, presupuesto))
    conn.commit()
    conn.close()

def obtener_notas(categoria=None, urgencia_min=5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM matrimonio_notas WHERE urgencia >= ?"
    params = [urgencia_min]
    
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    
    query += " ORDER BY urgencia DESC, creado_en DESC"
    
    cursor.execute(query, params)
    notas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notas

def guardar_nota(categoria, contenido, contexto, fecha_mencion, urgencia):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO matrimonio_notas (categoria, contenido, contexto, fecha_mencion, urgencia)
        VALUES (?, ?, ?, ?, ?)
    """, (categoria, contenido, contexto, fecha_mencion, urgencia))
    conn.commit()
    conn.close()

def registrar_habito(fecha, minutos, tipo_conexion, iniciado_por, satisfaccion, notas, modo_pareja):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO matrimonio_habitos 
        (fecha, tiempo_calidad_minutos, tipo_conexion, iniciado_por, satisfaccion, notas, modo_pareja_activado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (fecha, minutos, tipo_conexion, iniciado_por, satisfaccion, notas, modo_pareja))
    conn.commit()
    conn.close()

def obtener_habitos_recientes(dias=14):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    fecha_desde = (date.today() - timedelta(days=dias)).isoformat()
    cursor.execute("""
        SELECT * FROM matrimonio_habitos 
        WHERE fecha >= ? 
        ORDER BY fecha DESC
    """, (fecha_desde,))
    
    habitos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return habitos

def verificar_alerta_20_30():
    """Verifica si hay cita mañana y debería mostrar alerta"""
    manana = (date.today() + timedelta(days=1)).isoformat()
    citas_manana = obtener_citas(fecha_desde=manana)
    
    # También verificar si hoy es día de cita
    hoy = date.today().isoformat()
    citas_hoy = obtener_citas(fecha_desde=hoy, estado='Confirmada')
    
    proxima_cita = citas_hoy[0] if citas_hoy else (citas_manana[0] if citas_manana else None)
    
    hora_actual = datetime.now().hour
    minuto_actual = datetime.now().minute
    
    # Alerta activa entre 20:30 y 21:00 si hay cita hoy
    alerta_activa = (
        proxima_cita and 
        proxima_cita['fecha'] == hoy and
        hora_actual == 20 and minuto_actual >= 30
    ) or (
        proxima_cita and 
        proxima_cita['fecha'] == hoy and
        hora_actual == 21 and minuto_actual <= 15
    )
    
    return alerta_activa, proxima_cita

# ═════════════════════════════════════════════════════════════════
# HEADER
# ═════════════════════════════════════════════════════════════════

st.title("💑 Conexión Matrimonial")
st.caption("Calendario de citas • Alerta 20:30 • Modo pareja 21:00")

# ═════════════════════════════════════════════════════════════════
# ALERTA ESPECIAL 20:30 - SIEMPRE VISIBLE SI APLICA
# ═════════════════════════════════════════════════════════════════

alerta_activa, proxima_cita = verificar_alerta_20_30()

if alerta_activa and proxima_cita:
    st.error("⏰ **ALERTA 20:30 - MODO PAREJA ACTIVADO** ⏰")
    
    # Generar mensaje personalizado (con fallback si es necesario)
    contexto_cita = f"Cita hoy: {proxima_cita['titulo']} a las {proxima_cita['hora'] or '21:00'}"
    mensaje_alerta = generar_alerta_matrimonio(contexto_cita)
    
    st.markdown(f"""
    <div style="background: #3c1e1e; border: 2px solid #f85149; border-radius: 12px; padding: 1.5rem; margin: 1rem 0;">
        <h3 style="color: #f85149; margin: 0;">🚨 {mensaje_alerta}</h3>
        <p style="color: #f0f6fc; margin: 0.5rem 0 0 0;">
            <strong>Cita:</strong> {proxima_cita['titulo']}<br>
            <strong>Hora:</strong> {proxima_cita['hora'] or '21:00'}<br>
            <strong>Lugar:</strong> {proxima_cita['lugar'] or 'Por definir'}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Botón de confirmación
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("✅ Modo pareja activado", type="primary", use_container_width=True):
            registrar_habito(
                date.today().isoformat(),
                0,  # minutos, se actualizará después
                'Tiempo_Qualidad',
                'Yo',
                0,  # satisfacción, se actualizará después
                f"Inició modo pareja para: {proxima_cita['titulo']}",
                1  # modo pareja SÍ activado
            )
            st.success("💑 ¡Excelente! Disfruten su tiempo juntos.")
            st.balloons()

elif proxima_cita:
    # Mostrar próxima cita sin alerta de emergencia
    dias_hasta = (datetime.strptime(proxima_cita['fecha'], '%Y-%m-%d').date() - date.today()).days
    
    if dias_hasta == 0:
        st.info(f"📅 **Hoy** tienen cita: {proxima_cita['titulo']} a las {proxima_cita['hora'] or '21:00'}")
    elif dias_hasta == 1:
        st.warning(f"⏰ **Mañana** cita programada: {proxima_cita['titulo']}")
    else:
        st.caption(f"Próxima cita en {dias_hasta} días: {proxima_cita['titulo']}")

# ═════════════════════════════════════════════════════════════════
# SIDEBAR - ESTADÍSTICAS DE CONEXIÓN
# ═════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Conexión de pareja")
    
    habitos = obtener_habitos_recientes(30)
    
    if habitos:
        citas_30_dias = len(habitos)
        satisfaccion_promedio = sum(h['satisfaccion'] or 0 for h in habitos) / len(habitos)
        modo_pareja_respetado = sum(1 for h in habitos if h['modo_pareja_activado'])
        
        col1, col2 = st.columns(2)
        col1.metric("Citas/mes", citas_30_dias)
        col2.metric("Satisfacción", f"{satisfaccion_promedio:.1f}/10")
        
        st.progress(satisfaccion_promedio / 10, text="Calidad de conexión")
        
        st.metric("Modo 21:00 respetado", f"{modo_pareja_respetado}/{citas_30_dias}")
        
        if modo_pareja_respetado < citas_30_dias * 0.7:
            st.warning("⚠️ Menos del 70% de modo pareja respetado")
    else:
        st.info("📝 Sin registros aún. Comienza hoy.")
    
    # Notas urgentes
    notas_urgentes = obtener_notas(urgencia_min=8)
    if notas_urgentes:
        st.divider()
        st.caption("🔥 Notas urgentes")
        for n in notas_urgentes[:3]:
            emoji_cat = {
                'Preferencias_Esposa': '💝',
                'Ideas_Regalo': '🎁',
                'Frases_Recordar': '💬',
                'Momentos_Especiales': '✨',
                'Metas_Pareja': '🎯',
                'Conversaciones_Pendientes': '🗣️'
            }.get(n['categoria'], '📝')
            st.markdown(f"{emoji_cat} {n['contenido'][:50]}...")

# ═════════════════════════════════════════════════════════════════
# TABS
# ═════════════════════════════════════════════════════════════════

tab_citas, tab_notas, tab_historial, tab_ia = st.tabs([
    "📅 Calendario", "📝 Notas de Pareja", "📊 Historial", "🤖 IA Consejero"
])

# ═════════════════════════════════════════════════════════════════
# TAB 1: CALENDARIO DE CITAS
# ═════════════════════════════════════════════════════════════════

with tab_citas:
    col_cal, col_nueva = st.columns([2, 1])
    
    with col_cal:
        st.markdown("### 📅 Próximas citas")
        
        citas = obtener_citas(fecha_desde=date.today().isoformat())
        
        if not citas:
            st.info("📭 No hay citas programadas. ¡Planea la próxima!")
        else:
            for c in citas:
                fecha_cita = datetime.strptime(c['fecha'], '%Y-%m-%d')
                dias_faltan = (fecha_cita.date() - date.today()).days
                
                emoji_tipo = {
                    'Cena_Romantica': '🍷',
                    'Salida_Casual': '☕',
                    'Estadia_Casa': '🏠',
                    'Viaje_Corto': '🚗',
                    'Aniversario': '💍',
                    'Cumpleanos_Esposa': '🎂',
                    'Sorpresa': '🎉',
                    'Otra': '💑'
                }.get(c['tipo_cita'], '💑')
                
                color_estado = {
                    'Idea': '#8b949e',
                    'Planeando': '#58a6ff',
                    'Confirmada': '#3fb950',
                    'Completada': '#a371f7',
                    'Cancelada': '#f85149'
                }.get(c['estado_planificacion'], '#8b949e')
                
                with st.container():
                    col_info, col_estado = st.columns([4, 1])
                    
                    with col_info:
                        st.markdown(f"""
                        <div style="border-left: 4px solid {color_estado}; padding-left: 1rem; margin-bottom: 1rem;">
                            <h4 style="margin: 0;">{emoji_tipo} {c['titulo']}</h4>
                            <p style="color: #8b949e; margin: 0.25rem 0;">
                                {fecha_cita.strftime('%d/%m/%Y')} • 
                                {c['hora'] or 'Hora por definir'} • 
                                {c['lugar'] or 'Lugar por definir'}
                            </p>
                            <p style="margin: 0.5rem 0; font-size: 0.875rem;">{c['descripcion'] or ''}</p>
                            <p style="color: #8b949e; font-size: 0.75rem;">
                                💰 ${c['presupuesto_estimado'] or 0:,.0f} • 
                                Estado: <span style="color: {color_estado};">{c['estado_planificacion']}</span>
                            </p>
                            {f'<p style="color: #e3b341; font-size: 0.75rem;">📝 Preparar: {c["notas_preparacion"]}</p>' if c['notas_preparacion'] else ''}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col_estado:
                        st.caption(f"En {dias_faltan} días" if dias_faltan > 0 else "¡Hoy!")
                        
                        if c['estado_planificacion'] == 'Confirmada' and not c['recordatorio_20_30_enviado']:
                            st.success("✓ Alerta 20:30 activa")
    
    with col_nueva:
        st.markdown("### ➕ Nueva cita")
        
        with st.form("nueva_cita", clear_on_submit=True):
            titulo = st.text_input("Título *", placeholder="Ej: Cena de viernes tradicional")
            tipo = st.selectbox("Tipo", [
                "Cena_Romantica", "Salida_Casual", "Estadia_Casa", 
                "Viaje_Corto", "Aniversario", "Cumpleanos_Esposa", "Sorpresa", "Otra"
            ])
            
            col_fecha, col_hora = st.columns(2)
            with col_fecha:
                fecha = st.date_input("Fecha", value=date.today() + timedelta(days=7))
            with col_hora:
                hora = st.time_input("Hora (opcional)", value=None)
            
            lugar = st.text_input("Lugar", placeholder="Restaurante, casa, destino...")
            presupuesto = st.number_input("Presupuesto estimado", min_value=0, step=100, value=500)
            
            descripcion = st.text_area("Descripción/Plan", height=80)
            preparacion = st.text_area("¿Qué preparar?", height=60, 
                                       placeholder="Reservar, comprar flores, confirmar...")
            
            if st.form_submit_button("💾 Guardar cita", use_container_width=True):
                hora_str = hora.strftime('%H:%M') if hora else None
                guardar_cita(fecha.isoformat(), hora_str, tipo, titulo, descripcion, lugar, presupuesto)
                st.success("✅ Cita guardada")
                st.rerun()

# ═════════════════════════════════════════════════════════════════
# TAB 2: NOTAS DE PAREJA
# ═════════════════════════════════════════════════════════════════

with tab_notas:
    col_filtros, col_lista = st.columns([1, 2])
    
    with col_filtros:
        st.markdown("### 🔍 Filtrar")
        cat_filtro = st.selectbox("Categoría", [
            "Todas", "Preferencias_Esposa", "Ideas_Regalo", "Frases_Recordar",
            "Momentos_Especiales", "Metas_Pareja", "Conversaciones_Pendientes"
        ])
        
        st.divider()
        st.markdown("### ➕ Nueva nota")
        
        with st.form("nueva_nota", clear_on_submit=True):
            cat = st.selectbox("Categoría", [
                "Preferencias_Esposa", "Ideas_Regalo", "Frases_Recordar",
                "Momentos_Especiales", "Metas_Pareja", "Conversaciones_Pendientes"
            ])
            contenido = st.text_area("Contenido *", height=80, 
                                     placeholder="Ej: Le encanta el chocolate amargo...")
            contexto = st.text_input("¿Dónde/when se mencionó?", placeholder="Conversación en cena...")
            fecha_mencion = st.date_input("Fecha de la mención", value=date.today())
            urgencia = st.slider("Urgencia", 1, 10, 5, help="10 = hacer ASAP")
            
            if st.form_submit_button("💾 Guardar nota"):
                guardar_nota(cat, contenido, contexto, fecha_mencion.isoformat(), urgencia)
                st.success("✅ Nota guardada")
                st.rerun()
    
    with col_lista:
        st.markdown("### 📝 Tus notas de pareja")
        
        cat_filtro_db = None if cat_filtro == "Todas" else cat_filtro
        notas = obtener_notas(categoria=cat_filtro_db, urgencia_min=1)
        
        if not notas:
            st.info("📝 Sin notas. ¡Empieza a registrar detalles de tu esposa!")
        else:
            for n in notas:
                emoji_cat = {
                    'Preferencias_Esposa': '💝',
                    'Ideas_Regalo': '🎁',
                    'Frases_Recordar': '💬',
                    'Momentos_Especiales': '✨',
                    'Metas_Pareja': '🎯',
                    'Conversaciones_Pendientes': '🗣️'
                }.get(n['categoria'], '📝')
                
                color_urgencia = '#f85149' if n['urgencia'] >= 8 else '#e3b341' if n['urgencia'] >= 5 else '#8b949e'
                
                with st.expander(f"{emoji_cat} {n['categoria'].replace('_', ' ')} (Urgencia: {n['urgencia']}/10)"):
                    st.markdown(f"""
                    <div style="border-left: 3px solid {color_urgencia}; padding-left: 1rem;">
                        <p style="margin: 0; font-size: 1.1rem;">{n['contenido']}</p>
                        <p style="color: #8b949e; font-size: 0.875rem; margin: 0.5rem 0;">
                            Contexto: {n['contexto'] or 'No registrado'} • 
                            {n['fecha_mencion'] or 'Fecha desconocida'}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL Y ESTADÍSTICAS
# ═════════════════════════════════════════════════════════════════

with tab_historial:
    st.markdown("### 📊 Historial de conexión")
    
    habitos = obtener_habitos_recientes(90)  # Últimos 3 meses
    
    if not habitos:
        st.info("📊 Sin datos suficientes. Registra tus primeras citas.")
    else:
        # Métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total registros", len(habitos))
        col2.metric("Promedio satisfacción", f"{sum(h['satisfaccion'] or 0 for h in habitos)/len(habitos):.1f}/10")
        col3.metric("Modo 21:00 respetado", f"{sum(1 for h in habitos if h['modo_pareja_activado'])}/{len(habitos)}")
        col4.metric("Tiempo promedio", f"{sum(h['tiempo_calidad_minutos'] or 0 for h in habitos)/len(habitos):.0f} min")
        
        # Gráfico simple de barras con Streamlit nativo
        st.divider()
        st.markdown("### 📈 Satisfacción por fecha")
        
        datos_chart = {
            'Fecha': [h['fecha'] for h in habitos],
            'Satisfacción': [h['satisfaccion'] or 0 for h in habitos]
        }
        st.bar_chart(datos_chart, x='Fecha', y='Satisfacción')

# ═════════════════════════════════════════════════════════════════
# TAB 4: IA CONSEJERO MATRIMONIAL
# ═════════════════════════════════════════════════════════════════

with tab_ia:
    st.markdown("### 🤖 IA Consejero Matrimonial")
    
    if not api_key_configurada():
        st.warning("⚠️ IA en modo offline. Respuestas predefinidas disponibles.")
    
    col_contexto, col_chat = st.columns([1, 2])
    
    with col_contexto:
        st.markdown("**🎯 Situación actual**")
        
        # Contexto automático del sistema
        citas_recientes = obtener_citas(fecha_desde=(date.today() - timedelta(days=30)).isoformat())
        habitos_recientes = obtener_habitos_recientes(30)
        
        contexto_auto = f"""
        Último mes: {len(citas_recientes)} citas programadas, {len(habitos_recientes)} registradas.
        """
        
        st.caption(contexto_auto)
        
        tipo_ayuda = st.selectbox(
            "Tipo de consejo",
            [
                "Planificar cita sorpresa",
                "Resolver conflicto reciente",
                "Reconectar después de temporada ocupada",
                "Idea para aniversario",
                "Cómo mostrar aprecio diario"
            ]
        )
        
        detalle_situacion = st.text_area(
            "Describe tu situación",
            height=100,
            placeholder="Ej: Hemos estado muy ocupados con el instituto y el trabajo..."
        )
    
    with col_chat:
        st.markdown("**💬 Consejo personalizado**")
        
        if st.button("🚀 Obtener consejo", use_container_width=True, type="primary"):
            prompt = f"""
            Eres un consejero matrimonial cristiano con enfoque en:
            - Calidad de tiempo sobre cantidad
            - Intencionalidad en la relación
            - Balance entre ministerio/estudio y matrimonio
            
            Situación: {tipo_ayuda}
            Detalle: {detalle_situacion}
            Contexto: {contexto_auto}
            
            Da 2-3 sugerencias prácticas y concretas, máximo 150 palabras.
            """
            
            with st.spinner("Consejero reflexionando..."):
                respuesta = chat_simple(prompt, contexto="Consejero matrimonial cristiano, práctico y empático.")
                st.info(respuesta)

st.divider()
st.caption("💑 Conexión Matrimonial • El tiempo de calidad es inversión, no gasto")