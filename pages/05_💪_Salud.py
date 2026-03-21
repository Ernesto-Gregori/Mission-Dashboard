"""
💪 Salud y Energía - Correlación ejercicio-productividad
"""

import streamlit as st
from datetime import date, datetime, timedelta
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
from app.ai_client import chat_simple, api_key_configurada
import sqlite3

st.set_page_config(
    page_title="Salud | Mission Dashboard",
    page_icon="💪",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

SYSTEM_SALUD = """Eres un coach de salud cristiano para un estudiante de teología que 
también programa. Su rutina incluye: despertar 05:30, devocional 05:45, código 06:15, 
instituto 08:00-12:30, calistenia los miércoles 16:30. Eres práctico, motivador y 
consideras el cuerpo como templo del Espíritu Santo. Máximo 150 palabras."""

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def guardar_registro_salud(fecha, datos):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    campos = [
        'fecha', 'horas_sueno', 'calidad_sueno', 'hora_dormir', 'hora_despertar',
        'energia_manana', 'energia_tarde', 'energia_noche',
        'hizo_ejercicio', 'tipo_ejercicio', 'duracion_minutos', 'intensidad',
        'notas_ejercicio', 'productividad_percibida'
    ]
    valores = [datos.get(c) for c in campos[1:]]
    cursor.execute(f"""
        INSERT OR REPLACE INTO registros_salud 
        ({', '.join(campos)})
        VALUES (?, {', '.join(['?'] * len(campos[1:]))})
    """, [fecha] + valores)
    conn.commit()
    conn.close()

def obtener_registro_salud(fecha):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registros_salud WHERE fecha = ?", (fecha,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def obtener_registros_rango(dias=14):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    fecha_desde = (date.today() - timedelta(days=dias)).isoformat()
    cursor.execute("""
        SELECT * FROM registros_salud 
        WHERE fecha >= ? ORDER BY fecha DESC
    """, (fecha_desde,))
    registros = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return registros

def calcular_promedios(registros):
    if not registros:
        return {}
    def avg(key):
        vals = [r[key] for r in registros if r[key] is not None]
        return sum(vals) / len(vals) if vals else 0
    dias_ejercicio = sum(1 for r in registros if r['hizo_ejercicio'])
    return {
        'total_dias': len(registros),
        'dias_ejercicio': dias_ejercicio,
        'pct_ejercicio': dias_ejercicio / len(registros) * 100,
        'avg_energia_manana': avg('energia_manana'),
        'avg_energia_tarde': avg('energia_tarde'),
        'avg_energia_noche': avg('energia_noche'),
        'avg_sueno': avg('horas_sueno'),
        'avg_calidad_sueno': avg('calidad_sueno'),
        'avg_productividad': avg('productividad_percibida')
    }

def analizar_correlacion_simple(registros):
    if len(registros) < 4:
        return None, "Se necesitan al menos 4 días de datos"
    por_fecha = {r['fecha']: r for r in registros}
    ejercicio_si, ejercicio_no = [], []
    for r in registros:
        fecha = datetime.strptime(r['fecha'], '%Y-%m-%d').date()
        if fecha.weekday() == 2 and r['hizo_ejercicio']:
            jueves = (fecha + timedelta(days=1)).isoformat()
            if jueves in por_fecha and por_fecha[jueves]['productividad_percibida']:
                ejercicio_si.append(por_fecha[jueves]['productividad_percibida'])
        elif fecha.weekday() == 2 and not r['hizo_ejercicio']:
            jueves = (fecha + timedelta(days=1)).isoformat()
            if jueves in por_fecha and por_fecha[jueves]['productividad_percibida']:
                ejercicio_no.append(por_fecha[jueves]['productividad_percibida'])
    if not ejercicio_si or not ejercicio_no:
        return None, "Necesitas miércoles con y sin ejercicio para comparar"
    promedio_con = sum(ejercicio_si) / len(ejercicio_si)
    promedio_sin = sum(ejercicio_no) / len(ejercicio_no)
    diferencia = promedio_con - promedio_sin
    return {
        'promedio_con_ejercicio': promedio_con,
        'promedio_sin_ejercicio': promedio_sin,
        'diferencia': diferencia,
        'pct_mejora': (diferencia / promedio_sin * 100) if promedio_sin > 0 else 0,
        'muestras_con': len(ejercicio_si),
        'muestras_sin': len(ejercicio_no)
    }, None

# ═══════════════════════════════════════════════════════════════
# HELPERS DE IA
# ═══════════════════════════════════════════════════════════════

def _construir_contexto_salud(registros: list, stats: dict) -> str:
    """Construye resumen de salud para enviar a la IA."""
    if not registros or not stats:
        return "Sin datos de salud registrados aún."
    
    lineas = [
        f"Período: últimos {stats['total_dias']} días",
        f"Ejercicio: {stats['dias_ejercicio']}/{stats['total_dias']} días ({stats['pct_ejercicio']:.0f}%)",
        f"Energía mañana promedio: {stats['avg_energia_manana']:.1f}/10",
        f"Energía tarde promedio: {stats['avg_energia_tarde']:.1f}/10",
        f"Sueño promedio: {stats['avg_sueno']:.1f}h (calidad: {stats['avg_calidad_sueno']:.1f}/10)",
        f"Productividad promedio: {stats['avg_productividad']:.1f}/10",
    ]
    
    # Últimos 3 registros para contexto reciente
    recientes = registros[:3]
    if recientes:
        lineas.append("Últimos registros:")
        for r in recientes:
            ej = "✓ ejercicio" if r['hizo_ejercicio'] else "✗ sin ejercicio"
            lineas.append(
                f"  {r['fecha']}: {ej}, "
                f"energía {r['energia_manana'] or '-'}/10, "
                f"sueño {r['horas_sueno'] or '-'}h, "
                f"productividad {r['productividad_percibida'] or '-'}/10"
            )
    
    return "\n".join(lineas)

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("💪 Salud y Energía")
st.caption("Correlación ejercicio-productividad • Calistenia miércoles 16:30")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Tu semana")
    registros_semana = obtener_registros_rango(7)
    stats_semana = calcular_promedios(registros_semana)
    
    if stats_semana:
        col1, col2 = st.columns(2)
        col1.metric("Ejercicios", f"{stats_semana['dias_ejercicio']}/7")
        col2.metric("Energía mañana", f"{stats_semana['avg_energia_manana']:.1f}/10")
        st.progress(stats_semana['avg_energia_manana'] / 10, text="Energía promedio")
        st.metric("Sueño promedio", f"{stats_semana['avg_sueno']:.1f}h")
        st.metric("Productividad", f"{stats_semana['avg_productividad']:.1f}/10")
    else:
        st.info("📝 Comienza a registrar hoy")
    
    st.divider()
    if api_key_configurada():
        st.success("🤖 Coach IA activo")
    else:
        st.caption("🤖 Coach IA en modo offline")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_historial, tab_analisis, tab_ia = st.tabs([
    "📋 Hoy", "📈 Historial", "🔬 Análisis", "🤖 Coach IA"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: HOY
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    fecha_hoy = date.today()
    dia_semana = fecha_hoy.weekday()
    dias_nombres = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    
    st.subheader(f"{dias_nombres[dia_semana]} {fecha_hoy.strftime('%d/%m/%Y')}")
    
    if dia_semana == 2:
        st.info("🏋️ **Miércoles de Calistenia** • 16:30 - 18:30")
    
    registro_existente = obtener_registro_salud(fecha_hoy)
    
    with st.form("registro_salud", clear_on_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 😴 Sueño")
            hora_dormir = st.time_input("Hora de dormir",
                value=datetime.strptime("22:00", "%H:%M").time())
            hora_despertar = st.time_input("Hora de despertar",
                value=datetime.strptime("05:30", "%H:%M").time())
            dormir = datetime.combine(date.today(), hora_dormir)
            despertar = datetime.combine(date.today() + timedelta(days=1), hora_despertar)
            horas_sueno = (despertar - dormir).total_seconds() / 3600
            st.metric("Horas dormidas", f"{horas_sueno:.1f}h")
            calidad_sueno = st.slider("Calidad del sueño", 1, 10, 7)
        
        with col2:
            st.markdown("### ⚡ Energía")
            energia_manana = st.slider("Energía mañana (05:45)", 1, 10, 7)
            energia_tarde = st.slider("Energía tarde (14:00)", 1, 10, 6)
            energia_noche = st.slider("Energía noche (21:00)", 1, 10, 5)
        
        st.divider()
        col_ej1, col_ej2 = st.columns(2)
        
        with col_ej1:
            st.markdown("### 🏋️ Ejercicio")
            hizo_ejercicio = st.checkbox("¿Hiciste ejercicio hoy?",
                value=registro_existente['hizo_ejercicio'] if registro_existente else False)
            if hizo_ejercicio:
                tipo_ejercicio = st.selectbox("Tipo",
                    ["Calistenia", "Caminata", "Carrera", "Gimnasio", "Otro"],
                    index=0 if dia_semana == 2 else 1)
                duracion = st.number_input("Duración (min)", min_value=10, max_value=180, value=60, step=10)
                intensidad = st.slider("Intensidad", 1, 10, 5)
                notas_ej = st.text_area("Notas del entrenamiento",
                    placeholder="Series, repeticiones, sensaciones...")
            else:
                tipo_ejercicio, duracion, intensidad, notas_ej = None, None, None, ""
        
        with col_ej2:
            st.markdown("### 📈 Productividad")
            productividad = st.slider("Productividad percibida hoy", 1, 10, 6)
            st.caption("💡 Se correlacionará con tu ejercicio y sueño")
        
        if st.form_submit_button("💾 Guardar registro diario",
                                  use_container_width=True, type="primary"):
            datos = {
                'horas_sueno': horas_sueno,
                'calidad_sueno': calidad_sueno,
                'hora_dormir': hora_dormir.strftime('%H:%M'),
                'hora_despertar': hora_despertar.strftime('%H:%M'),
                'energia_manana': energia_manana,
                'energia_tarde': energia_tarde,
                'energia_noche': energia_noche,
                'hizo_ejercicio': 1 if hizo_ejercicio else 0,
                'tipo_ejercicio': tipo_ejercicio,
                'duracion_minutos': duracion,
                'intensidad': intensidad,
                'notas_ejercicio': notas_ej,
                'productividad_percibida': productividad
            }
            guardar_registro_salud(fecha_hoy, datos)
            st.success("✅ Registro guardado. ¡Tu cuerpo te lo agradecerá!")
            st.balloons()

# ═══════════════════════════════════════════════════════════════
# TAB 2: HISTORIAL
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.subheader("Últimos 14 días")
    registros = obtener_registros_rango(14)
    
    if not registros:
        st.info("📭 Aún no hay registros. Comienza hoy.")
    else:
        for reg in registros:
            fecha_reg = datetime.strptime(reg['fecha'], '%Y-%m-%d').date()
            dia_nombre = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][fecha_reg.weekday()]
            with st.container():
                cols = st.columns([1, 2, 2, 2, 2])
                with cols[0]:
                    st.markdown(f"**{dia_nombre}**<br>{fecha_reg.strftime('%d/%m')}",
                                unsafe_allow_html=True)
                with cols[1]:
                    st.metric("Ejercicio", "🏋️" if reg['hizo_ejercicio'] else "❌")
                with cols[2]:
                    st.metric("Energía", f"{reg['energia_manana'] or '-'}/10")
                with cols[3]:
                    st.metric("Sueño", f"{reg['horas_sueno']:.1f}h" if reg['horas_sueno'] else "-")
                with cols[4]:
                    st.metric("Productividad", f"{reg['productividad_percibida'] or '-'}/10")
                st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 3: ANÁLISIS
# ═══════════════════════════════════════════════════════════════

with tab_analisis:
    st.subheader("🔬 Correlación ejercicio-productividad")
    st.markdown("""
    ### Hipótesis en prueba:
    > *"Los miércoles de calistenia mejoran el enfoque en programación del jueves"*
    """)
    
    registros = obtener_registros_rango(30)
    resultado, error = analizar_correlacion_simple(registros)
    
    if error:
        st.warning(f"⚠️ {error}")
        st.info("💡 Registra tus miércoles durante 2-3 semanas para ver resultados.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Con ejercicio", f"{resultado['promedio_con_ejercicio']:.1f}/10")
        with col2:
            st.metric("Sin ejercicio", f"{resultado['promedio_sin_ejercicio']:.1f}/10")
        with col3:
            color = "#3fb950" if resultado['diferencia'] > 0 else "#f85149"
            st.markdown(f"""
            <div style="text-align:center;">
                <div style="font-size:2rem;color:{color};font-weight:bold;">
                    {resultado['pct_mejora']:+.0f}%
                </div>
                <div style="font-size:0.875rem;color:#8b949e;">de mejora</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        data_chart = {
            'Condición': ['Con ejercicio', 'Sin ejercicio'],
            'Productividad jueves': [
                resultado['promedio_con_ejercicio'],
                resultado['promedio_sin_ejercicio']
            ]
        }
        st.bar_chart(data_chart, x='Condición', y='Productividad jueves')
        
        st.divider()
        if resultado['diferencia'] > 1:
            st.success(f"✅ ¡Confirmado! El ejercicio mejora tu productividad en {resultado['pct_mejora']:.0f}%.")
        elif resultado['diferencia'] > 0:
            st.info(f"📈 Tendencia positiva (+{resultado['pct_mejora']:.0f}%), necesitas más datos.")
        else:
            st.warning("⚠️ No se detecta mejora aún. ¿Estás durmiendo lo suficiente?")
        
        st.caption(f"Basado en {resultado['muestras_con']} miércoles con ejercicio "
                   f"vs {resultado['muestras_sin']} sin ejercicio")

# ═══════════════════════════════════════════════════════════════
# TAB 4: COACH IA — Las 4 funciones
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Coach de Salud IA")
    
    if not api_key_configurada():
        st.warning("⚠️ IA en modo offline — respuestas predefinidas disponibles.")
    
    # Cargar datos una sola vez
    registros_ia = obtener_registros_rango(14)
    stats_ia = calcular_promedios(registros_ia)
    contexto = _construir_contexto_salud(registros_ia, stats_ia)
    resultado_corr, _ = analizar_correlacion_simple(obtener_registros_rango(30))
    
    # ── 1. RESUMEN SEMANAL CON INSIGHTS ─────────────────────
    st.markdown("### 📊 Resumen semanal con insights")
    
    if stats_ia:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Ejercicios", f"{stats_ia['dias_ejercicio']}/{stats_ia['total_dias']}")
        col2.metric("Energía prom.", f"{stats_ia['avg_energia_manana']:.1f}/10")
        col3.metric("Sueño prom.", f"{stats_ia['avg_sueno']:.1f}h")
        col4.metric("Productividad", f"{stats_ia['avg_productividad']:.1f}/10")
    
    if st.button("🤖 Generar resumen semanal con IA",
                  key="btn_resumen", use_container_width=True):
        prompt = f"""
Genera un resumen semanal de salud con insights accionables.

Datos de la semana:
{contexto}

Incluye: 1 victoria de la semana, 1 área de mejora prioritaria, 
1 versículo motivador relacionado con el cuidado del cuerpo.
"""
        with st.spinner("Generando resumen..."):
            st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 2. ANÁLISIS DE CORRELACIÓN CON IA ───────────────────
    st.markdown("### 🔬 Análisis de correlación con IA")
    
    col_corr1, col_corr2 = st.columns([1, 2])
    
    with col_corr1:
        tipo_correlacion = st.selectbox(
            "¿Qué correlación analizar?",
            [
                "Ejercicio → Productividad",
                "Sueño → Energía mañana",
                "Calidad sueño → Productividad",
                "Energía mañana → Productividad",
                "Patrón general de la semana",
            ],
            key="sel_correlacion"
        )
    
    with col_corr2:
        if st.button("🔬 Analizar correlación", key="btn_corr",
                      use_container_width=True):
            corr_extra = ""
            if resultado_corr:
                corr_extra = f"""
Correlación ejercicio-productividad calculada:
- Con ejercicio: {resultado_corr['promedio_con_ejercicio']:.1f}/10
- Sin ejercicio: {resultado_corr['promedio_sin_ejercicio']:.1f}/10
- Diferencia: {resultado_corr['pct_mejora']:+.0f}%
"""
            prompt = f"""
Analiza esta correlación específica: {tipo_correlacion}

Datos de salud:
{contexto}

{corr_extra}

Da 2-3 observaciones concretas basadas en los números 
y 1 recomendación accionable para esta semana.
"""
            with st.spinner("Analizando correlación..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 3. RECOMENDACIONES DE SUEÑO Y ENERGÍA ───────────────
    st.markdown("### 😴 Recomendaciones de sueño y energía")
    
    col_sue1, col_sue2 = st.columns([1, 2])
    
    with col_sue1:
        problema_sueno = st.selectbox(
            "¿Cuál es tu situación?",
            [
                "Me cuesta despertar a las 05:30",
                "Energía baja en la tarde",
                "Sueño de mala calidad",
                "Me duermo tarde (>23:00)",
                "Energía inconsistente durante la semana",
            ],
            key="sel_sueno"
        )
        
        hora_actual_dormir = st.time_input(
            "¿A qué hora te duermes normalmente?",
            value=datetime.strptime("22:30", "%H:%M").time(),
            key="ti_dormir"
        )
    
    with col_sue2:
        if st.button("💡 Obtener recomendaciones", key="btn_sueno",
                      use_container_width=True):
            prompt = f"""
Situación de sueño: {problema_sueno}
Hora actual de dormir: {hora_actual_dormir.strftime('%H:%M')}
Meta: despertar a las 05:30 para devocional a las 05:45

Datos recientes:
{contexto}

Da 3 recomendaciones específicas y prácticas para mejorar 
esta semana, considerando el horario de estudiante de teología.
"""
            with st.spinner("Generando recomendaciones..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 4. COACH DE CALISTENIA ───────────────────────────────
    st.markdown("### 🏋️ Coach de calistenia")
    
    col_cal1, col_cal2 = st.columns([1, 2])
    
    with col_cal1:
        tipo_sesion = st.selectbox(
            "Tipo de sesión",
            [
                "Planificar sesión de hoy",
                "Progresión para principiante",
                "Recuperación post-entrenamiento",
                "Motivación para no saltarme el miércoles",
                "Rutina corta (30 min) cuando hay poco tiempo",
            ],
            key="sel_calistenia"
        )
        
        nivel = st.select_slider(
            "Tu nivel actual",
            options=["Principiante", "Básico", "Intermedio"],
            value="Básico",
            key="sl_nivel"
        )
        
        # Último entrenamiento
        ultimo_ej = next(
            (r for r in registros_ia if r['hizo_ejercicio']), None
        )
        if ultimo_ej:
            st.caption(f"Último entreno: {ultimo_ej['fecha']}")
    
    with col_cal2:
        if st.button("🏋️ Consejo del coach", key="btn_calistenia",
                      use_container_width=True):
            ultimo_info = ""
            if ultimo_ej:
                ultimo_info = (
                    f"Último entrenamiento: {ultimo_ej['fecha']}, "
                    f"intensidad {ultimo_ej['intensidad'] or '-'}/10, "
                    f"duración {ultimo_ej['duracion_minutos'] or '-'} min. "
                    f"Notas: {ultimo_ej['notas_ejercicio'] or 'ninguna'}"
                )
            
            prompt = f"""
Solicitud: {tipo_sesion}
Nivel: {nivel}
{ultimo_info}

Energía actual: {stats_ia.get('avg_energia_manana', 0):.1f}/10
Días de ejercicio esta semana: {stats_ia.get('dias_ejercicio', 0)}

Da consejos específicos para calistenia en casa, 
considerando que el horario ideal es miércoles 16:30-18:30.
"""
            with st.spinner("Coach preparando tu plan..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── CHAT LIBRE ───────────────────────────────────────────
    st.markdown("### 💬 Pregunta libre al coach")
    
    pregunta_salud = st.text_input(
        "Tu pregunta",
        placeholder="Ej: ¿Cómo mantengo energía en el bloque de código de las 06:15?",
        key="txt_pregunta_salud"
    )
    
    if pregunta_salud:
        with st.spinner("Coach pensando..."):
            st.info(chat_simple(
                f"Contexto de salud:\n{contexto}\n\nPregunta: {pregunta_salud}",
                contexto=SYSTEM_SALUD
            ))

st.divider()
st.caption("💪 Módulo Salud • Calistenia miércoles 16:30 • Coach IA activo")