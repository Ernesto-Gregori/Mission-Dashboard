"""
💪 Salud y Energía - Correlación ejercicio-productividad
"""

import streamlit as st
from datetime import date, datetime, timedelta
import sys
import json  
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
from app.ai_client import chat_simple, api_key_configurada
import sqlite3
from app.google_fit import (
    obtener_datos_dia, fit_configurado, fit_autenticado
)

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
    
    # Serializar listas a JSON
    zonas = datos.get('zonas_musculares', [])
    sesiones = datos.get('sesiones_json', [])
    
    campos = [
        'fecha', 'horas_sueno', 'calidad_sueno', 'hora_dormir', 'hora_despertar',
        'energia_manana', 'energia_tarde', 'energia_noche',
        'hizo_ejercicio', 'tipo_ejercicio', 'duracion_minutos', 'intensidad',
        'notas_ejercicio', 'zonas_musculares', 'sesiones_json',
        'calorias_fit', 'pasos_fit', 'fc_promedio_fit', 'fc_maxima_fit',
        'fuente_datos', 'productividad_percibida'
    ]
    
    valores = [
        datos.get('horas_sueno'),
        datos.get('calidad_sueno'),
        datos.get('hora_dormir'),
        datos.get('hora_despertar'),
        datos.get('energia_manana'),
        datos.get('energia_tarde'),
        datos.get('energia_noche'),
        datos.get('hizo_ejercicio'),
        datos.get('tipo_ejercicio'),
        datos.get('duracion_minutos'),
        datos.get('intensidad'),
        datos.get('notas_ejercicio'),
        json.dumps(zonas) if isinstance(zonas, list) else zonas,
        json.dumps(sesiones) if isinstance(sesiones, list) else sesiones,
        datos.get('calorias_fit'),
        datos.get('pasos_fit'),
        datos.get('fc_promedio_fit'),
        datos.get('fc_maxima_fit'),
        datos.get('fuente_datos', 'manual'),
        datos.get('productividad_percibida'),
    ]
    
    cursor.execute(f"""
        INSERT OR REPLACE INTO registros_salud 
        ({', '.join(campos)})
        VALUES (?, {', '.join(['?'] * len(valores))})
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
    dias_nombres = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    
    st.subheader(f"{dias_nombres[dia_semana]} {fecha_hoy.strftime('%d/%m/%Y')}")
    
    if dia_semana == 2:
        st.info("🏋️ **Miércoles de Calistenia** • 16:30 - 18:30")
    
    # ── GOOGLE FIT — Importar datos ──────────────────────────
    if not fit_configurado():
        st.warning("⚠️ Google Fit no configurado")
    elif not fit_autenticado():
        st.info("🔑 Primera vez: necesitas autenticar con Google Fit")
        if st.button("🔗 Conectar Google Fit", type="primary"):
            with st.spinner("Abriendo navegador..."):
                obtener_datos_dia(fecha_hoy)
                st.rerun()
    else:
        col_fit1, col_fit2 = st.columns([3, 1])
        with col_fit1:
            st.success("✅ Google Fit conectado")
        with col_fit2:
            if st.button("🔄 Importar hoy", use_container_width=True):
                with st.spinner("Obteniendo datos de Google Fit..."):
                    datos_importados = obtener_datos_dia(fecha_hoy)
                    st.session_state['datos_fit_hoy'] = datos_importados
                    st.session_state['fit_fecha'] = fecha_hoy.isoformat()
                    st.rerun()
    
    # Mostrar métricas si hay datos importados para HOY
    fit = {}
    if (st.session_state.get('fit_fecha') == fecha_hoy.isoformat()
            and 'datos_fit_hoy' in st.session_state):
        fit = st.session_state['datos_fit_hoy']
        if 'error' not in fit:
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("😴 Sueño", f"{fit.get('horas_sueno') or '-'}h")
            col_b.metric("🏋️ Ejercicio", f"{fit.get('duracion_minutos') or 0} min")
            col_c.metric("👟 Pasos", f"{fit.get('pasos') or 0:,}")
            col_d.metric("❤️ FC prom.", f"{fit.get('fc_promedio') or '-'} bpm")
            
            sesiones = fit.get('sesiones_fit', [])
            if sesiones:
                st.caption("Sesiones detectadas: " +
                    " • ".join(f"{s['tipo']} ({s['duracion_min']} min)"
                               for s in sesiones))
    
    st.divider()
    st.markdown("### ✏️ Editar y completar registro")
    st.caption("Los datos de Google Fit se pre-rellenan — edita lo que necesites y agrega energía/productividad")
    
    # ── Cargar registro existente en BD ──────────────────────
    reg = obtener_registro_salud(fecha_hoy) or {}
    
    # Prioridad: BD > Google Fit > default
    def val(campo, default):
        if reg.get(campo) is not None:
            return reg[campo]
        if fit.get(campo) is not None:
            return fit[campo]
        return default
    
    # ── SUEÑO ────────────────────────────────────────────────
    with st.expander("😴 Sueño", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            hora_dormir_str = val('hora_dormir', '22:00')
            if not isinstance(hora_dormir_str, str):
                hora_dormir_str = '22:00'
            hora_dormir = st.time_input("Hora de dormir",
                value=datetime.strptime(hora_dormir_str, "%H:%M").time(),
                key="td_dormir")

            hora_despertar_str = val('hora_despertar', '05:30')
            if not isinstance(hora_despertar_str, str):
                hora_despertar_str = '05:30'
            hora_despertar = st.time_input("Hora de despertar",
                value=datetime.strptime(hora_despertar_str, "%H:%M").time(),
                key="td_despertar")

            # SIEMPRE usar horas de Google Fit si existen
            # Los time_input son solo para edición manual
            horas_fit = val('horas_sueno', None)
            if horas_fit:
                # Google Fit tiene el dato real — ignorar cálculo de time_input
                horas_sueno = horas_fit
                st.metric("Horas dormidas (Google Fit)", f"{horas_sueno:.1f}h")
                st.caption("⚡ Dato real de Google Fit — edita las horas arriba solo si hay error")
            else:
                # Sin Google Fit — calcular desde los time_input
                dormir = datetime.combine(date.today(), hora_dormir)
                despertar = datetime.combine(date.today() + timedelta(days=1), hora_despertar)
                horas_sueno = (despertar - dormir).total_seconds() / 3600
                st.metric("Horas dormidas (calculado)", f"{horas_sueno:.1f}h")
        
        with col2:
            calidad_sueno = st.slider("Calidad del sueño", 1, 10,
                int(val('calidad_sueno', 7)),
                help="Google Fit calcula esto con etapas REM y sueño profundo",
                key="sl_calidad_sueno")
    
    # ── ENERGÍA ──────────────────────────────────────────────
    with st.expander("⚡ Energía del día", expanded=True):
        st.caption("Solo tú puedes registrar esto — Google Fit no lo mide")
        col3, col4, col5 = st.columns(3)
        with col3:
            energia_manana = st.slider("Mañana (05:45)", 1, 10,
                int(val('energia_manana', 7)), key="sl_e_man")
        with col4:
            energia_tarde = st.slider("Tarde (14:00)", 1, 10,
                int(val('energia_tarde', 6)), key="sl_e_tar")
        with col5:
            energia_noche = st.slider("Noche (21:00)", 1, 10,
                int(val('energia_noche', 5)), key="sl_e_noc")
    
    # ── EJERCICIO — Soporte múltiples sesiones ───────────────
    with st.expander("🏋️ Ejercicio", expanded=True):
        
        hizo_ejercicio = st.checkbox("¿Hiciste ejercicio hoy?",
            value=bool(val('hizo_ejercicio', dia_semana == 2)),
            key="cb_ejercicio")
        
        sesiones_ejercicio = []
        
        if hizo_ejercicio:
            # Detectar cuántas sesiones hay (de Google Fit o BD)
            sesiones_fit = fit.get('sesiones_fit', [])
            
            # Si Google Fit detectó sesiones, usarlas como base
            # Si no, iniciar con 1 sesión vacía
            n_sesiones_default = max(1, len(sesiones_fit))
            
            if 'n_sesiones' not in st.session_state:
                st.session_state.n_sesiones = n_sesiones_default
            
            col_ns1, col_ns2, col_ns3 = st.columns([2, 1, 1])
            with col_ns1:
                st.caption(f"Sesiones de ejercicio: {st.session_state.n_sesiones}")
            with col_ns2:
                if st.button("➕ Agregar sesión", key="btn_add_sesion"):
                    st.session_state.n_sesiones += 1
                    st.rerun()
            with col_ns3:
                if st.session_state.n_sesiones > 1:
                    if st.button("➖ Quitar", key="btn_rm_sesion"):
                        st.session_state.n_sesiones -= 1
                        st.rerun()
            
            TIPOS_EJERCICIO = ["Calistenia", "Caminata", "Carrera",
                               "Gimnasio", "Entrenamiento fuerza",
                               "Yoga", "Ciclismo", "Natación", "Otro"]
            ZONAS = ["Pecho", "Espalda", "Hombros", "Bíceps", "Tríceps",
                     "Core/Abdomen", "Piernas", "Glúteos", "Cuerpo completo"]
            
            for i in range(st.session_state.n_sesiones):
                st.markdown(f"**Sesión {i + 1}**")
                
                # Pre-rellenar desde Google Fit si existe esa sesión
                fit_sesion = sesiones_fit[i] if i < len(sesiones_fit) else {}
                
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    tipo_default = fit_sesion.get('tipo', 'Calistenia')
                    idx_tipo = TIPOS_EJERCICIO.index(tipo_default) \
                        if tipo_default in TIPOS_EJERCICIO else 0
                    tipo = st.selectbox(f"Tipo", TIPOS_EJERCICIO,
                        index=idx_tipo, key=f"tipo_s{i}")
                    
                    duracion = st.number_input(f"Duración (min)",
                        min_value=5, max_value=240,
                        value=int(fit_sesion.get('duracion_min', 60)),
                        step=5, key=f"dur_s{i}")
                    
                    intensidad = st.slider(f"Intensidad", 1, 10, 5,
                        key=f"int_s{i}")
                
                with col_s2:
                    zonas = st.multiselect(f"Zona muscular",
                        ZONAS, default=[], key=f"zona_s{i}")
                    
                    notas_s = st.text_area(f"Notas de la sesión",
                        placeholder="Series, reps, sensaciones...",
                        height=100, key=f"notas_s{i}")
                
                sesiones_ejercicio.append({
                    'tipo': tipo,
                    'duracion': duracion,
                    'intensidad': intensidad,
                    'zonas': zonas,
                    'notas': notas_s,
                })
                
                if i < st.session_state.n_sesiones - 1:
                    st.divider()
            
            # Mostrar datos extra de Google Fit
            if fit.get('calorias'):
                st.caption(f"🔥 Calorías (Google Fit): {fit['calorias']} kcal")
            if fit.get('fc_maxima'):
                st.caption(f"❤️ FC máxima (Google Fit): {fit['fc_maxima']} bpm")
            if fit.get('pasos'):
                st.caption(f"👟 Pasos (Google Fit): {fit['pasos']:,}")
    
    # ── PRODUCTIVIDAD ─────────────────────────────────────────
    with st.expander("📈 Productividad", expanded=True):
        productividad = st.slider("Productividad percibida hoy", 1, 10,
            int(val('productividad_percibida', 6)), key="sl_prod")
        st.caption("💡 Este dato se correlaciona con tu sueño y ejercicio")
    
    # ── GUARDAR ───────────────────────────────────────────────
    st.divider()
    if st.button("💾 Guardar registro del día", use_container_width=True, type="primary"):
    
        if hizo_ejercicio and sesiones_ejercicio:
            tipo_principal = sesiones_ejercicio[0]['tipo']
            duracion_total = sum(s['duracion'] for s in sesiones_ejercicio)
            intensidad_promedio = round(
                sum(s['intensidad'] for s in sesiones_ejercicio) / len(sesiones_ejercicio)
            )
            # Todas las zonas únicas de todas las sesiones
            todas_zonas = list(set(
                zona for s in sesiones_ejercicio for zona in s['zonas']
            ))
            notas_partes = []
            for i, s in enumerate(sesiones_ejercicio, 1):
                parte = f"Sesión {i}: {s['tipo']} {s['duracion']}min"
                if s['zonas']:
                    parte += f" | Zonas: {', '.join(s['zonas'])}"
                if s['notas']:
                    parte += f" | {s['notas']}"
                notas_partes.append(parte)
            notas_consolidadas = " || ".join(notas_partes)
        else:
            tipo_principal = None
            duracion_total = None
            intensidad_promedio = None
            todas_zonas = []
            notas_consolidadas = ""
        
        # Determinar fuente de datos
        fuente = 'mixto' if fit else 'manual'
        
        datos_guardar = {
            'horas_sueno': round(horas_sueno, 1),
            'calidad_sueno': calidad_sueno,
            'hora_dormir': hora_dormir.strftime('%H:%M'),
            'hora_despertar': hora_despertar.strftime('%H:%M'),
            'energia_manana': energia_manana,
            'energia_tarde': energia_tarde,
            'energia_noche': energia_noche,
            'hizo_ejercicio': 1 if hizo_ejercicio else 0,
            'tipo_ejercicio': tipo_principal,
            'duracion_minutos': duracion_total,
            'intensidad': intensidad_promedio,
            'notas_ejercicio': notas_consolidadas,
            # Campos nuevos
            'zonas_musculares': todas_zonas,
            'sesiones_json': sesiones_ejercicio,
            'calorias_fit': fit.get('calorias') if fit else None,
            'pasos_fit': fit.get('pasos') if fit else None,
            'fc_promedio_fit': fit.get('fc_promedio') if fit else None,
            'fc_maxima_fit': fit.get('fc_maxima') if fit else None,
            'fuente_datos': fuente,
            'productividad_percibida': productividad,
        }
        
        guardar_registro_salud(fecha_hoy, datos_guardar)
        
        if 'n_sesiones' in st.session_state:
            del st.session_state['n_sesiones']
        
        st.success("✅ Registro guardado. ¡Tu cuerpo es templo del Espíritu!")
        st.balloons()

# ═══════════════════════════════════════════════════════════════
# TAB 2: HISTORIAL MEJORADO
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.subheader("📈 Historial de salud")
    
    # ── Filtros ──────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        dias_historial = st.selectbox("Período", [7, 14, 30, 60],
            format_func=lambda x: f"Últimos {x} días", index=1)
    with col_f2:
        filtro_ejercicio = st.selectbox("Ejercicio",
            ["Todos", "Con ejercicio", "Sin ejercicio"])
    with col_f3:
        filtro_zona = st.selectbox("Zona muscular",
            ["Todas", "Pecho", "Espalda", "Hombros", "Bíceps",
             "Tríceps", "Core/Abdomen", "Piernas", "Glúteos",
             "Cuerpo completo"])
    
    registros = obtener_registros_rango(dias_historial)
    
    # Aplicar filtros
    if filtro_ejercicio == "Con ejercicio":
        registros = [r for r in registros if r['hizo_ejercicio']]
    elif filtro_ejercicio == "Sin ejercicio":
        registros = [r for r in registros if not r['hizo_ejercicio']]
    if filtro_zona != "Todas":
        registros = [r for r in registros
                     if r.get('notas_ejercicio') and
                     filtro_zona in (r.get('notas_ejercicio') or '')]
    
    if not registros:
        st.info("📭 No hay registros con estos filtros.")
    else:
        # ── Gráficas de tendencia ────────────────────────────
        st.markdown("### 📊 Tendencias")
        
        import pandas as pd
        
        df = pd.DataFrame([{
            'Fecha': r['fecha'],
            'Sueño (h)': r['horas_sueno'] or 0,
            'Energía mañana': r['energia_manana'] or 0,
            'Energía tarde': r['energia_tarde'] or 0,
            'Productividad': r['productividad_percibida'] or 0,
            'Ejercicio': 10 if r['hizo_ejercicio'] else 0,
        } for r in reversed(registros)])
        
        tab_graf1, tab_graf2, tab_graf3 = st.tabs([
            "😴 Sueño", "⚡ Energía", "📈 Productividad"
        ])
        
        with tab_graf1:
            st.line_chart(df.set_index('Fecha')[['Sueño (h)']])
            promedio_sueno = df['Sueño (h)'].mean()
            color = "🟢" if promedio_sueno >= 7 else "🟡" if promedio_sueno >= 6 else "🔴"
            st.caption(f"{color} Promedio: {promedio_sueno:.1f}h — "
                      f"{'Óptimo' if promedio_sueno >= 7 else 'Mejorable' if promedio_sueno >= 6 else 'Insuficiente'}")
        
        with tab_graf2:
            st.line_chart(df.set_index('Fecha')[
                ['Energía mañana', 'Energía tarde']
            ])
        
        with tab_graf3:
            st.line_chart(df.set_index('Fecha')[['Productividad']])
            # Marcar días con ejercicio
            dias_ej = [r['fecha'] for r in registros if r['hizo_ejercicio']]
            if dias_ej:
                st.caption(f"🏋️ Días con ejercicio: {', '.join(dias_ej[-5:])}")
        
        st.divider()
        
        # ── Lista detallada ──────────────────────────────────
        st.markdown("### 📋 Detalle por día")
        
        for reg in registros:
            fecha_reg = datetime.strptime(reg['fecha'], '%Y-%m-%d').date()
            dia_nombre = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][fecha_reg.weekday()]
            tiene_notas = bool(reg.get('notas_ejercicio'))
            
            # Header compacto
            col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns([1,2,2,2,2])
            with col_d1:
                st.markdown(f"**{dia_nombre}**  \n{fecha_reg.strftime('%d/%m')}",)
            with col_d2:
                st.metric("Ejercicio", "🏋️" if reg['hizo_ejercicio'] else "❌")
            with col_d3:
                sueno = reg['horas_sueno']
                color_s = "🟢" if sueno and sueno >= 7 else "🟡" if sueno and sueno >= 6 else "🔴"
                st.metric("Sueño", f"{color_s} {sueno:.1f}h" if sueno else "-")
            with col_d4:
                st.metric("Energía", f"{reg['energia_manana'] or '-'}/10")
            with col_d5:
                st.metric("Productividad", f"{reg['productividad_percibida'] or '-'}/10")
            
            # Expandible con detalle completo
            if tiene_notas or reg['hizo_ejercicio']:
                with st.expander("Ver detalle"):
                    col_det1, col_det2 = st.columns(2)
                    
                    with col_det1:
                        if reg['hizo_ejercicio']:
                            st.markdown("**🏋️ Ejercicio:**")
                            st.write(f"Tipo: {reg.get('tipo_ejercicio') or '-'}")
                            st.write(f"Duración total: {reg.get('duracion_minutos') or '-'} min")
                            st.write(f"Intensidad: {reg.get('intensidad') or '-'}/10")
                            
                            # Parsear sesiones de las notas
                            notas = reg.get('notas_ejercicio', '') or ''
                            if '||' in notas:
                                sesiones = notas.split('||')
                                st.markdown("**Sesiones:**")
                                for s in sesiones:
                                    st.caption(f"• {s.strip()}")
                            elif notas:
                                st.caption(f"📝 {notas}")
                    
                    with col_det2:
                        st.markdown("**😴 Sueño:**")
                        st.write(f"Horas: {reg.get('horas_sueno') or '-'}h")
                        st.write(f"Calidad: {reg.get('calidad_sueno') or '-'}/10")
                        st.write(f"Dormir: {reg.get('hora_dormir') or '-'}")
                        st.write(f"Despertar: {reg.get('hora_despertar') or '-'}")
                        
                        st.markdown("**⚡ Energía:**")
                        st.write(f"Mañana: {reg.get('energia_manana') or '-'}/10")
                        st.write(f"Tarde: {reg.get('energia_tarde') or '-'}/10")
                        st.write(f"Noche: {reg.get('energia_noche') or '-'}/10")
            
            st.divider()


# ═══════════════════════════════════════════════════════════════
# TAB 3: ANÁLISIS MEJORADO
# ═══════════════════════════════════════════════════════════════

with tab_analisis:
    st.subheader("🔬 Análisis de patrones de salud")
    
    registros_30 = obtener_registros_rango(30)
    
    if len(registros_30) < 4:
        st.info("📊 Necesitas al menos 4 días de datos para ver análisis.")
    else:
        import pandas as pd
        
        df_an = pd.DataFrame([{
            'fecha': r['fecha'],
            'dia_semana': datetime.strptime(r['fecha'], '%Y-%m-%d').weekday(),
            'horas_sueno': r['horas_sueno'] or 0,
            'calidad_sueno': r['calidad_sueno'] or 0,
            'energia_manana': r['energia_manana'] or 0,
            'energia_tarde': r['energia_tarde'] or 0,
            'productividad': r['productividad_percibida'] or 0,
            'hizo_ejercicio': bool(r['hizo_ejercicio']),
            'duracion_ejercicio': r['duracion_minutos'] or 0,
            'notas': r.get('notas_ejercicio', '') or '',
        } for r in registros_30])
        
        # ── 1. Correlación ejercicio → productividad ─────────
        st.markdown("### 🏋️ Correlación ejercicio → productividad")
        resultado, error = analizar_correlacion_simple(registros_30)
        
        if error:
            st.warning(f"⚠️ {error}")
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
                    <div style="font-size:0.875rem;color:#8b949e;">impacto en productividad</div>
                </div>
                """, unsafe_allow_html=True)
            
            if resultado['diferencia'] > 1:
                st.success(f"✅ Confirmado: ejercicio mejora tu productividad {resultado['pct_mejora']:.0f}%")
            elif resultado['diferencia'] > 0:
                st.info(f"📈 Tendencia positiva — sigue registrando para confirmar")
            else:
                st.warning("⚠️ Sin mejora detectada aún — ¿estás durmiendo suficiente?")
        
        st.divider()
        
        # ── 2. Correlación sueño → energía ───────────────────
        st.markdown("### 😴 Correlación sueño → energía mañana")
        
        df_sueno = df_an[df_an['horas_sueno'] > 0].copy()
        if len(df_sueno) >= 4:
            sueno_bueno = df_sueno[df_sueno['horas_sueno'] >= 7]['energia_manana'].mean()
            sueno_malo = df_sueno[df_sueno['horas_sueno'] < 7]['energia_manana'].mean()
            
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("Energía con ≥7h sueño",
                f"{sueno_bueno:.1f}/10" if not pd.isna(sueno_bueno) else "Sin datos")
            col_s2.metric("Energía con <7h sueño",
                f"{sueno_malo:.1f}/10" if not pd.isna(sueno_malo) else "Sin datos")
            
            if not pd.isna(sueno_bueno) and not pd.isna(sueno_malo):
                diferencia_sueno = sueno_bueno - sueno_malo
                col_s3.metric("Diferencia",
                    f"{diferencia_sueno:+.1f} pts",
                    delta_color="normal" if diferencia_sueno > 0 else "inverse")
                
                # Gráfico sueño vs energía
                df_sueno['categoria_sueno'] = df_sueno['horas_sueno'].apply(
                    lambda x: '≥7h (óptimo)' if x >= 7 else '<7h (insuficiente)'
                )
                chart_data = df_sueno.groupby('categoria_sueno')['energia_manana'].mean()
                st.bar_chart(chart_data)
        else:
            st.info("Necesitas más datos de sueño para este análisis.")
        
        st.divider()
        
        # ── 3. Patrón por día de la semana ───────────────────
        st.markdown("### 📅 Patrón semanal — ¿Qué día tienes más energía?")
        
        dias_nombres_cortos = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
        patron_semanal = df_an.groupby('dia_semana').agg({
            'energia_manana': 'mean',
            'productividad': 'mean',
            'horas_sueno': 'mean',
        }).round(1)
        
        patron_semanal.index = [dias_nombres_cortos[i]
                                for i in patron_semanal.index]
        
        col_pat1, col_pat2 = st.columns(2)
        with col_pat1:
            st.markdown("**Energía por día:**")
            st.bar_chart(patron_semanal['energia_manana'])
        with col_pat2:
            st.markdown("**Productividad por día:**")
            st.bar_chart(patron_semanal['productividad'])
        
        # Día con más energía
        if not patron_semanal.empty:
            mejor_dia_idx = patron_semanal['energia_manana'].idxmax()
            peor_dia_idx = patron_semanal['energia_manana'].idxmin()
            st.success(f"🌟 Mejor día: **{mejor_dia_idx}** "
                      f"({patron_semanal.loc[mejor_dia_idx, 'energia_manana']:.1f}/10)")
            st.warning(f"⚠️ Peor día: **{peor_dia_idx}** "
                      f"({patron_semanal.loc[peor_dia_idx, 'energia_manana']:.1f}/10) — "
                      f"¿Qué pasa ese día?")
        
        st.divider()
        
        # ── 4. Análisis de zonas musculares ──────────────────
        st.markdown("### 💪 Zonas musculares más trabajadas")
        
        ZONAS_LISTA = ["Pecho","Espalda","Hombros","Bíceps","Tríceps",
                       "Core/Abdomen","Piernas","Glúteos","Cuerpo completo"]
        
        conteo_zonas = {z: 0 for z in ZONAS_LISTA}
        for r in registros_30:
            notas = r.get('notas_ejercicio', '') or ''
            for zona in ZONAS_LISTA:
                if zona in notas:
                    conteo_zonas[zona] += 1
        
        zonas_trabajadas = {k: v for k, v in conteo_zonas.items() if v > 0}
        
        if zonas_trabajadas:
            df_zonas = pd.DataFrame(
                list(zonas_trabajadas.items()),
                columns=['Zona', 'Sesiones']
            ).sort_values('Sesiones', ascending=False)
            
            st.bar_chart(df_zonas.set_index('Zona'))
            
            zona_mas = df_zonas.iloc[0]['Zona']
            zona_menos = df_zonas.iloc[-1]['Zona'] if len(df_zonas) > 1 else None
            
            st.success(f"💪 Zona más trabajada: **{zona_mas}**")
            if zona_menos and zona_menos != zona_mas:
                st.info(f"⚖️ Zona menos trabajada: **{zona_menos}** — "
                       f"considera balancear tu rutina")
            
            # Detectar zonas sin trabajar
            sin_trabajar = [z for z in ZONAS_LISTA
                           if z not in zonas_trabajadas and z != 'Cuerpo completo']
            if sin_trabajar:
                st.warning(f"🔴 Sin trabajar este mes: {', '.join(sin_trabajar)}")
        else:
            st.info("📝 Registra zonas musculares en tus sesiones para ver este análisis.")
        
        st.divider()
        
        # ── 5. Tendencia de productividad ────────────────────
        st.markdown("### 📈 Tendencia de productividad")
        
        df_prod = df_an[df_an['productividad'] > 0].copy()
        if len(df_prod) >= 3:
            df_prod_chart = df_prod.set_index('fecha')[['productividad']]
            st.line_chart(df_prod_chart)
            
            # Semana actual vs anterior
            hoy = date.today()
            inicio_semana = hoy - timedelta(days=hoy.weekday())
            inicio_semana_ant = inicio_semana - timedelta(days=7)
            
            prod_semana_actual = df_an[
                df_an['fecha'] >= inicio_semana.isoformat()
            ]['productividad'].mean()
            
            prod_semana_ant = df_an[
                (df_an['fecha'] >= inicio_semana_ant.isoformat()) &
                (df_an['fecha'] < inicio_semana.isoformat())
            ]['productividad'].mean()
            
            if not pd.isna(prod_semana_actual) and not pd.isna(prod_semana_ant):
                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric("Esta semana",
                    f"{prod_semana_actual:.1f}/10")
                col_p2.metric("Semana anterior",
                    f"{prod_semana_ant:.1f}/10")
                delta = prod_semana_actual - prod_semana_ant
                col_p3.metric("Cambio",
                    f"{delta:+.1f}",
                    delta_color="normal" if delta >= 0 else "inverse")


# ═══════════════════════════════════════════════════════════════
# TAB 4: COACH IA MEJORADO
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Coach de Salud IA")
    
    if not api_key_configurada():
        st.warning("⚠️ IA en modo offline — respuestas predefinidas disponibles.")
    
    # Cargar datos
    registros_ia = obtener_registros_rango(14)
    registros_semana_ant = obtener_registros_rango(14)
    stats_ia = calcular_promedios(registros_ia)
    resultado_corr, _ = analizar_correlacion_simple(obtener_registros_rango(30))
    
    # ── Contexto enriquecido con Google Fit y zonas ──────────
    def _construir_contexto_completo(registros, stats):
        if not registros or not stats:
            return "Sin datos registrados aún."
        
        # Contexto base
        lineas = [
            f"Período: últimos {stats['total_dias']} días",
            f"Ejercicio: {stats['dias_ejercicio']}/{stats['total_dias']} días ({stats['pct_ejercicio']:.0f}%)",
            f"Sueño promedio: {stats['avg_sueno']:.1f}h (calidad: {stats['avg_calidad_sueno']:.1f}/10)",
            f"Energía mañana: {stats['avg_energia_manana']:.1f}/10",
            f"Energía tarde: {stats['avg_energia_tarde']:.1f}/10",
            f"Productividad: {stats['avg_productividad']:.1f}/10",
        ]
        
        # Zonas musculares trabajadas
        ZONAS_LISTA = ["Pecho","Espalda","Hombros","Bíceps","Tríceps",
                      "Core/Abdomen","Piernas","Glúteos","Cuerpo completo"]
        conteo_zonas = {z: 0 for z in ZONAS_LISTA}
        for r in registros:
            notas = r.get('notas_ejercicio', '') or ''
            for zona in ZONAS_LISTA:
                if zona in notas:
                    conteo_zonas[zona] += 1
        
        zonas_activas = {k: v for k, v in conteo_zonas.items() if v > 0}
        if zonas_activas:
            zonas_str = ", ".join(f"{k}({v}x)" for k, v in
                sorted(zonas_activas.items(), key=lambda x: -x[1]))
            lineas.append(f"Zonas trabajadas: {zonas_str}")
            
            sin_trabajar = [z for z in ZONAS_LISTA
                           if z not in zonas_activas and z != 'Cuerpo completo']
            if sin_trabajar:
                lineas.append(f"Zonas sin trabajar: {', '.join(sin_trabajar)}")
        
        # Comparar semana actual vs anterior
        hoy = date.today()
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        inicio_ant = inicio_semana - timedelta(days=7)
        
        semana_actual = [r for r in registros
                        if r['fecha'] >= inicio_semana.isoformat()]
        semana_ant = [r for r in registros
                     if inicio_ant.isoformat() <= r['fecha'] < inicio_semana.isoformat()]
        
        if semana_actual and semana_ant:
            stats_act = calcular_promedios(semana_actual)
            stats_ant = calcular_promedios(semana_ant)
            delta_prod = stats_act['avg_productividad'] - stats_ant['avg_productividad']
            delta_sueno = stats_act['avg_sueno'] - stats_ant['avg_sueno']
            lineas.append(f"Semana actual vs anterior: "
                         f"productividad {delta_prod:+.1f}, "
                         f"sueño {delta_sueno:+.1f}h")
        
        # Patrón de sueño real
        suenos = [r['horas_sueno'] for r in registros if r['horas_sueno']]
        if suenos:
            noches_insuficientes = sum(1 for s in suenos if s < 7)
            lineas.append(f"Noches con <7h sueño: {noches_insuficientes}/{len(suenos)}")
        
        # Últimos 3 registros
        recientes = registros[:3]
        if recientes:
            lineas.append("Últimos registros:")
            for r in recientes:
                ej = f"✓ {r.get('tipo_ejercicio','ejercicio')} {r.get('duracion_minutos',0)}min" \
                     if r['hizo_ejercicio'] else "✗ sin ejercicio"
                notas = r.get('notas_ejercicio', '') or ''
                zonas_hoy = [z for z in ZONAS_LISTA if z in notas]
                zonas_str = f" [{', '.join(zonas_hoy)}]" if zonas_hoy else ""
                lineas.append(
                    f"  {r['fecha']}: {ej}{zonas_str}, "
                    f"sueño {r['horas_sueno'] or '-'}h, "
                    f"energía {r['energia_manana'] or '-'}/10, "
                    f"productividad {r['productividad_percibida'] or '-'}/10"
                )
        
        return "\n".join(lineas)
    
    contexto = _construir_contexto_completo(registros_ia, stats_ia)
    
    # ── Métricas rápidas ─────────────────────────────────────
    if stats_ia:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Ejercicios", f"{stats_ia['dias_ejercicio']}/{stats_ia['total_dias']}")
        col2.metric("Energía prom.", f"{stats_ia['avg_energia_manana']:.1f}/10")
        col3.metric("Sueño prom.", f"{stats_ia['avg_sueno']:.1f}h")
        col4.metric("Productividad", f"{stats_ia['avg_productividad']:.1f}/10")
    
    # ── Comparativa semana actual vs anterior ────────────────
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_ant = inicio_semana - timedelta(days=7)
    semana_act = [r for r in registros_ia if r['fecha'] >= inicio_semana.isoformat()]
    semana_ant_data = [r for r in registros_semana_ant
                       if inicio_ant.isoformat() <= r['fecha'] < inicio_semana.isoformat()]
    
    if semana_act and semana_ant_data:
        st.markdown("#### 📊 Esta semana vs semana anterior")
        stats_act = calcular_promedios(semana_act)
        stats_ant = calcular_promedios(semana_ant_data)
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.metric("Productividad",
            f"{stats_act['avg_productividad']:.1f}",
            f"{stats_act['avg_productividad'] - stats_ant['avg_productividad']:+.1f}")
        col_c2.metric("Sueño",
            f"{stats_act['avg_sueno']:.1f}h",
            f"{stats_act['avg_sueno'] - stats_ant['avg_sueno']:+.1f}h")
        col_c3.metric("Energía mañana",
            f"{stats_act['avg_energia_manana']:.1f}",
            f"{stats_act['avg_energia_manana'] - stats_ant['avg_energia_manana']:+.1f}")
        col_c4.metric("Ejercicios",
            f"{stats_act['dias_ejercicio']}",
            f"{stats_act['dias_ejercicio'] - stats_ant['dias_ejercicio']:+d}")
    
    st.divider()
    
    # ── 1. RESUMEN SEMANAL ───────────────────────────────────
    st.markdown("### 📊 Resumen semanal con insights")
    
    if st.button("🤖 Generar resumen semanal", key="btn_resumen",
                  use_container_width=True):
        prompt = f"""
Genera un resumen semanal de salud con insights accionables.

{contexto}

Incluye:
1. Victoria más importante de la semana
2. Área de mejora prioritaria con acción concreta
3. Observación sobre el patrón de zonas musculares (¿hay desequilibrio?)
4. Versículo motivador sobre el cuidado del cuerpo
"""
        with st.spinner("Generando resumen..."):
            st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 2. ANÁLISIS DE CORRELACIÓN ───────────────────────────
    st.markdown("### 🔬 Análisis de correlación con IA")
    
    col_corr1, col_corr2 = st.columns([1, 2])
    with col_corr1:
        tipo_correlacion = st.selectbox(
            "¿Qué correlación analizar?",
            [
                "Ejercicio → Productividad del día siguiente",
                "Sueño → Energía mañana",
                "Calidad sueño → Productividad",
                "Energía mañana → Productividad",
                "Patrón general de la semana",
                "Semana actual vs semana anterior",
            ],
            key="sel_correlacion"
        )
    with col_corr2:
        if st.button("🔬 Analizar correlación", key="btn_corr",
                      use_container_width=True):
            corr_extra = ""
            if resultado_corr:
                corr_extra = (
                    f"Correlación ejercicio-productividad calculada:\n"
                    f"- Con ejercicio: {resultado_corr['promedio_con_ejercicio']:.1f}/10\n"
                    f"- Sin ejercicio: {resultado_corr['promedio_sin_ejercicio']:.1f}/10\n"
                    f"- Impacto: {resultado_corr['pct_mejora']:+.0f}%"
                )
            prompt = f"""
Analiza: {tipo_correlacion}

Datos completos:
{contexto}

{corr_extra}

Da 2-3 observaciones concretas con números específicos 
y 1 recomendación accionable para esta semana.
"""
            with st.spinner("Analizando..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 3. RECUPERACIÓN Y ZONAS MUSCULARES ───────────────────
    st.markdown("### 💪 Recuperación y balance muscular")
    
    col_rec1, col_rec2 = st.columns([1, 2])
    with col_rec1:
        tipo_rec = st.selectbox(
            "¿Qué necesitas?",
            [
                "Plan de recuperación según zonas trabajadas",
                "¿Qué zona trabajar hoy para balancear?",
                "Señales de sobreentrenamiento",
                "Rutina de movilidad entre sesiones",
            ],
            key="sel_recuperacion"
        )
    with col_rec2:
        if st.button("💪 Consejo de recuperación", key="btn_rec",
                      use_container_width=True):
            prompt = f"""
Solicitud: {tipo_rec}

Historial de entrenamiento:
{contexto}

Considera el horario: calistenia miércoles 16:30, 
instituto lunes a viernes 08:00-12:30.
Da recomendaciones específicas para esta semana.
"""
            with st.spinner("Analizando recuperación..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 4. SUEÑO Y ENERGÍA ───────────────────────────────────
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
        
        # Mostrar dato real de sueño si existe
        if stats_ia.get('avg_sueno'):
            st.metric("Tu sueño real promedio",
                f"{stats_ia['avg_sueno']:.1f}h",
                "✓ Suficiente" if stats_ia['avg_sueno'] >= 7 else "⚠ Insuficiente")
    
    with col_sue2:
        if st.button("💡 Recomendaciones personalizadas", key="btn_sueno",
                      use_container_width=True):
            prompt = f"""
Situación: {problema_sueno}
Hora de dormir actual: {hora_actual_dormir.strftime('%H:%M')}
Meta: despertar 05:30 para devocional 05:45

Datos reales de sueño:
{contexto}

Da 3 recomendaciones específicas y prácticas basadas 
en los datos reales de Google Fit y el registro manual.
"""
            with st.spinner("Generando recomendaciones..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_SALUD))
    
    st.divider()
    
    # ── 5. COACH DE CALISTENIA ───────────────────────────────
    st.markdown("### 🏋️ Coach de calistenia")
    
    col_cal1, col_cal2 = st.columns([1, 2])
    with col_cal1:
        tipo_sesion = st.selectbox(
            "Tipo de ayuda",
            [
                "Planificar sesión de hoy",
                "Progresión para mi nivel actual",
                "Recuperación post-entrenamiento",
                "Motivación para no saltarme el miércoles",
                "Rutina corta (30 min)",
            ],
            key="sel_calistenia"
        )
        nivel = st.select_slider(
            "Tu nivel",
            options=["Principiante","Básico","Intermedio"],
            value="Básico", key="sl_nivel"
        )
        ultimo_ej = next((r for r in registros_ia if r['hizo_ejercicio']), None)
        if ultimo_ej:
            st.caption(f"Último entreno: {ultimo_ej['fecha']}")
    
    with col_cal2:
        if st.button("🏋️ Consejo del coach", key="btn_calistenia",
                      use_container_width=True):
            ultimo_info = ""
            if ultimo_ej:
                notas_ej = ultimo_ej.get('notas_ejercicio', '') or ''
                ultimo_info = (
                    f"Último entrenamiento: {ultimo_ej['fecha']}, "
                    f"{ultimo_ej.get('tipo_ejercicio','calistenia')} "
                    f"{ultimo_ej.get('duracion_minutos',0)}min, "
                    f"intensidad {ultimo_ej.get('intensidad','-')}/10"
                )
                if notas_ej:
                    ultimo_info += f"\nDetalle: {notas_ej[:200]}"
            
            prompt = f"""
Solicitud: {tipo_sesion}
Nivel: {nivel}
{ultimo_info}

Contexto de salud esta semana:
{contexto}

Da consejos específicos para calistenia en casa,
considerando el horario miércoles 16:30-18:30 y 
el balance muscular detectado en el historial.
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
                f"Contexto completo de salud:\n{contexto}\n\nPregunta: {pregunta_salud}",
                contexto=SYSTEM_SALUD
            ))

st.divider()
st.caption("💪 Módulo Salud • Google Fit + IA ")