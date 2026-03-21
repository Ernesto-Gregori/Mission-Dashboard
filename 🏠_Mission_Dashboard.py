"""
🏠 Mission Dashboard - Control de Mando Personal
Sistema de gestión integral: Teología, Programación, Finanzas y Matrimonio
"""

import streamlit as st
from datetime import datetime, date
import pandas as pd
import sqlite3
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CORRECCIÓN: Agregar app al path ANTES de imports
# ═══════════════════════════════════════════════════════════════

# Obtener ruta del proyecto (donde está este archivo)
BASE_DIR = Path(__file__).parent.resolve()

# Agregar app al path (corregido para Windows)
sys.path.insert(0, str(BASE_DIR / "app"))

# Ahora importar
from app.database import init_database, DB_PATH
from app.ai_client import (      # ← nombre nuevo del archivo
    generar_alerta_matrimonio,
    chat_simple,
    api_key_configurada,
    estado_gemini,
    verificar_conexion,
)

# ═══════════════════════════════════════════════════════════════
# NUEVO: Cache de estado Gemini — se evalúa UNA vez cada 5 min
# ═══════════════════════════════════════════════════════════════

@st.cache_resource(ttl=300)
def _init_gemini():
    """
    Se ejecuta solo al arrancar (o tras 5 min).
    Hace la única llamada real a la API.
    """
    verificar_conexion()   # Calienta el cache interno de gemini_client
    return True

# Llamar al inicio — solo consume 1 llamada real, luego usa cache
_init_gemini()

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN GLOBAL
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Mission Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inicializar base de datos
init_database()

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
# ESTADO DE SESIÓN
# ═══════════════════════════════════════════════════════════════

if 'user_name' not in st.session_state:
    st.session_state.user_name = "Misionero"

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS - HÁBITOS Y MÉTRICAS
# ═══════════════════════════════════════════════════════════════

import sqlite3
from datetime import timedelta

def get_habitos_hoy():
    """Obtiene y/o inicializa hábitos del día actual"""
    hoy = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Inicializar los 4 hábitos si no existen hoy
    for habito in ['devocional', 'codigo', 'lectura', 'calistenia']:
        cursor.execute("""
            INSERT OR IGNORE INTO habitos_diarios (fecha, habito, completado)
            VALUES (?, ?, 0)
        """, (hoy, habito))
    conn.commit()
    
    cursor.execute("SELECT * FROM habitos_diarios WHERE fecha = ?", (hoy,))
    habitos = {row['habito']: dict(row) for row in cursor.fetchall()}
    conn.close()
    return habitos

def toggle_habito(habito: str):
    """Alterna completado/pendiente de un hábito"""
    hoy = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT completado FROM habitos_diarios 
        WHERE fecha = ? AND habito = ?
    """, (hoy, habito))
    
    row = cursor.fetchone()
    nuevo_estado = 0 if (row and row[0]) else 1
    hora_actual = datetime.now().strftime('%H:%M') if nuevo_estado else None
    
    cursor.execute("""
        INSERT INTO habitos_diarios (fecha, habito, completado, hora_completado)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(fecha, habito)
        DO UPDATE SET completado = ?, hora_completado = ?
    """, (hoy, habito, nuevo_estado, hora_actual, nuevo_estado, hora_actual))
    
    conn.commit()
    conn.close()

def get_metricas_modulos():
    """Lee datos reales de todos los módulos desde SQLite"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    metricas = {}
    hoy = date.today()

    # ── FINANZAS ──────────────────────────────────────────────
    try:
        mes_actual = hoy.strftime('%Y-%m')
        cursor.execute("""
            SELECT COALESCE(SUM(monto), 0) as total
            FROM gastos WHERE strftime('%Y-%m', fecha) = ?
        """, (mes_actual,))
        total_gastos = cursor.fetchone()['total']

        cursor.execute("""
            SELECT COALESCE(SUM(limite), 0) as total
            FROM presupuestos WHERE mes = ? AND anio = ?
        """, (hoy.month, hoy.year))
        total_ppto = cursor.fetchone()['total']

        pct = int(total_gastos / total_ppto * 100) if total_ppto > 0 else 0
        metricas['finanzas'] = {
            'gastos': total_gastos,
            'presupuesto': total_ppto,
            'pct': pct,
            'semaforo': '🟢' if pct < 70 else '🟡' if pct < 90 else '🔴',
            'color': '#3fb950' if pct < 70 else '#e3b341' if pct < 90 else '#f85149'
        }
    except Exception:
        metricas['finanzas'] = {
            'gastos': 0, 'presupuesto': 0, 
            'pct': 0, 'semaforo': '⚪', 'color': '#8b949e'
        }

    # ── DEEP WORK ─────────────────────────────────────────────
    try:
        lunes = (hoy - timedelta(days=hoy.weekday())).isoformat()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN estado = 'Completado' THEN 1 ELSE 0 END) as completados
            FROM sesiones_completadas WHERE fecha >= ?
        """, (lunes,))
        row = cursor.fetchone()
        total_dw = row['total'] or 0
        comp_dw = row['completados'] or 0
        metricas['deep_work'] = {
            'completados': comp_dw,
            'total': total_dw,
            'pct': int(comp_dw / total_dw * 100) if total_dw > 0 else 0
        }
    except Exception:
        metricas['deep_work'] = {'completados': 0, 'total': 0, 'pct': 0}

    # ── BIBLIOTECA ────────────────────────────────────────────
    try:
        cursor.execute("SELECT COUNT(*) as total FROM libros")
        total_libros = cursor.fetchone()['total']

        cursor.execute("""
            SELECT titulo, pagina_actual, total_paginas
            FROM libros WHERE estado = 'leyendo'
            ORDER BY actualizado_en DESC LIMIT 1
        """)
        leyendo = cursor.fetchone()

        if leyendo and leyendo['total_paginas']:
            pct_libro = int(
                (leyendo['pagina_actual'] or 0) / leyendo['total_paginas'] * 100
            )
            libro_texto = f"{leyendo['titulo'][:28]}... • {pct_libro}%"
        else:
            libro_texto = "Sin libro activo"

        metricas['biblioteca'] = {
            'total': total_libros,
            'leyendo': libro_texto
        }
    except Exception:
        metricas['biblioteca'] = {'total': 0, 'leyendo': 'Sin datos'}

    # ── TEOLOGÍA ──────────────────────────────────────────────
    try:
        cursor.execute("""
            SELECT COUNT(*) as total, MAX(fecha) as ultimo
            FROM devocionales
        """)
        row = cursor.fetchone()
        total_teo = row['total'] or 0
        ultimo_teo = row['ultimo'] or '—'

        # Calcular racha
        cursor.execute("""
            SELECT fecha FROM devocionales ORDER BY fecha DESC
        """)
        fechas = [r['fecha'] for r in cursor.fetchall()]
        racha = 0
        check = hoy
        for f in fechas:
            if f == check.isoformat():
                racha += 1
                check -= timedelta(days=1)
            else:
                break

        metricas['teologia'] = {
            'total': total_teo,
            'ultimo': ultimo_teo,
            'racha': racha
        }
    except Exception:
        metricas['teologia'] = {'total': 0, 'ultimo': '—', 'racha': 0}

    # ── SALUD ─────────────────────────────────────────────────
    try:
        cursor.execute("""
            SELECT energia_manana, hizo_ejercicio, productividad_percibida
            FROM registros_salud WHERE fecha = ?
        """, (hoy.isoformat(),))
        salud = cursor.fetchone()

        metricas['salud'] = {
            'energia': salud['energia_manana'] or 0 if salud else 0,
            'ejercicio': bool(salud['hizo_ejercicio']) if salud else False,
            'productividad': salud['productividad_percibida'] or 0 if salud else 0,
            'registrado': salud is not None
        }
    except Exception:
        metricas['salud'] = {
            'energia': 0, 'ejercicio': False, 
            'productividad': 0, 'registrado': False
        }

    # ── MATRIMONIO ────────────────────────────────────────────
    try:
        cursor.execute("""
            SELECT titulo, fecha, hora
            FROM matrimonio_citas
            WHERE fecha >= ? 
              AND estado_planificacion NOT IN ('Cancelada', 'Completada')
            ORDER BY fecha, hora LIMIT 1
        """, (hoy.isoformat(),))
        proxima = cursor.fetchone()

        if proxima:
            dias = (
                datetime.strptime(proxima['fecha'], '%Y-%m-%d').date() - hoy
            ).days
            label = 'Hoy' if dias == 0 else f'En {dias}d'
            proxima_texto = f"{label}: {proxima['titulo'][:22]}"
        else:
            proxima_texto = "Sin citas próximas"

        cursor.execute("""
            SELECT COUNT(*) as total FROM matrimonio_citas
            WHERE strftime('%Y-%m', fecha) = ?
              AND estado_planificacion = 'Completada'
        """, (hoy.strftime('%Y-%m'),))
        citas_mes = cursor.fetchone()['total']

        metricas['matrimonio'] = {
            'proxima': proxima_texto,
            'citas_mes': citas_mes
        }
    except Exception:
        metricas['matrimonio'] = {'proxima': 'Sin datos', 'citas_mes': 0}

    # ── SANDBOX ───────────────────────────────────────────────
    try:
        cursor.execute("""
            SELECT COUNT(*) as total FROM sandbox_ideas
            WHERE estado NOT IN ('Completado', 'Abandonado')
        """)
        ideas_activas = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM sandbox_snippets")
        snippets = cursor.fetchone()['total']

        metricas['sandbox'] = {
            'ideas_activas': ideas_activas,
            'snippets': snippets
        }
    except Exception:
        metricas['sandbox'] = {'ideas_activas': 0, 'snippets': 0}

    conn.close()
    return metricas


# ═══════════════════════════════════════════════════════════════
# CARGAR DATOS
# ═══════════════════════════════════════════════════════════════

habitos = get_habitos_hoy()
metricas = get_metricas_modulos()

# ═══════════════════════════════════════════════════════════════
# HEADER PRINCIPAL
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<h1 style="margin-bottom: 0.25rem;">Control de Mando</h1>
<p style="color: #8b949e; margin-top: 0;">Dashboard integral de vida</p>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SECCIÓN 1: HÁBITOS DIARIOS (INTERACTIVOS)
# ═══════════════════════════════════════════════════════════════

st.subheader("📋 Hábitos del día")

HABITOS_CONFIG = {
    'devocional': {'emoji': '📖', 'label': 'Devocional',  'hora': '05:45'},
    'codigo':     {'emoji': '💻', 'label': 'Código',       'hora': '06:15'},
    'lectura':    {'emoji': '📚', 'label': 'Lectura',      'hora': '19:30'},
    'calistenia': {'emoji': '💪', 'label': 'Calistenia',   'hora': 'Mié 16:30'},
}

cols = st.columns(4)

for i, (key, cfg) in enumerate(HABITOS_CONFIG.items()):
    with cols[i]:
        completado = habitos.get(key, {}).get('completado', 0)
        hora_ok    = habitos.get(key, {}).get('hora_completado', '')

        color_borde = '#3fb950' if completado else '#30363d'
        color_fondo = '#0f2d0f' if completado else '#161b22'
        simbolo     = '✅' if completado else '○'
        color_sym   = '#3fb950' if completado else '#8b949e'

        st.markdown(f"""
        <div style="
            background: {color_fondo};
            border: 1px solid {color_borde};
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
            margin-bottom: 0.5rem;
        ">
            <div style="font-size: 1.5rem;">{cfg['emoji']}</div>
            <div style="color: #f0f6fc; font-weight: 600; font-size: 0.9rem;">
                {cfg['label']}
            </div>
            <div style="color: {color_sym}; font-size: 1.8rem; line-height: 1.2;">
                {simbolo}
            </div>
            <div style="color: #8b949e; font-size: 0.75rem;">{cfg['hora']}</div>
            {f'<div style="color:#3fb950;font-size:0.7rem;">✓ {hora_ok}</div>' 
              if hora_ok else ''}
        </div>
        """, unsafe_allow_html=True)

        label_btn = "✓ Hecho" if completado else "Marcar ✓"
        if st.button(
            label_btn,
            key=f"hab_{key}",
            use_container_width=True,
            type="secondary" if completado else "primary"
        ):
            toggle_habito(key)
            st.rerun()

# Barra de progreso diaria
completados_hoy = sum(
    1 for h in habitos.values() if h.get('completado')
)
st.progress(
    completados_hoy / 4,
    text=f"Hábitos completados hoy: {completados_hoy}/4"
)

st.divider()

# ═══════════════════════════════════════════════════════════════
# SECCIÓN 2: MÓDULOS CON DATOS REALES
# ═══════════════════════════════════════════════════════════════

st.subheader("🗂️ Módulos del Sistema")

mod_col1, mod_col2 = st.columns(2)

with mod_col1:
    # ── Finanzas ──────────────────────────────────────────────
    fin = metricas['finanzas']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">💰 Finanzas Personales</span>
            <span style="color:{fin['color']}; font-size:0.875rem;">
                {fin['semaforo']} {fin['pct']}% usado
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            Gastado: ${fin['gastos']:,.0f} / Presupuesto: ${fin['presupuesto']:,.0f}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Deep Work ─────────────────────────────────────────────
    dw = metricas['deep_work']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">⏰ Deep Work</span>
            <span style="color:#58a6ff; font-size:0.875rem;">
                {dw['completados']}/{dw['total']} bloques esta semana
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            Tasa de éxito: {dw['pct']}%
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Teología ──────────────────────────────────────────────
    teo = metricas['teologia']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">✝️ Bitácora Teológica</span>
            <span style="color:#a371f7; font-size:0.875rem;">
                {teo['total']} entradas · 🔥{teo['racha']} días
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            Último devocional: {teo['ultimo']}
        </p>
    </div>
    """, unsafe_allow_html=True)

with mod_col2:
    # ── Biblioteca ────────────────────────────────────────────
    bib = metricas['biblioteca']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">📚 Biblioteca</span>
            <span style="color:#e3b341; font-size:0.875rem;">{bib['total']} libros</span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            📖 {bib['leyendo']}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Salud ─────────────────────────────────────────────────
    sal = metricas['salud']
    sal_texto = (
        f"Energía: {sal['energia']}/10 · "
        f"{'🏋️ Ejercicio ✓' if sal['ejercicio'] else '❌ Sin ejercicio'} · "
        f"Productividad: {sal['productividad']}/10"
        if sal['registrado'] else "Sin registro hoy — ve al módulo Salud"
    )
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">💪 Salud y Energía</span>
            <span style="color:#f85149; font-size:0.875rem;">
                Energía: {sal['energia']}/10
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            {sal_texto}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Matrimonio ────────────────────────────────────────────
    mat = metricas['matrimonio']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">💑 Conexión Matrimonial</span>
            <span style="color:#ff69b4; font-size:0.875rem;">
                {mat['citas_mes']} citas este mes
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            📅 {mat['proxima']}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Sandbox ───────────────────────────────────────────────
    sand = metricas['sandbox']
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">🧪 Sandbox</span>
            <span style="color:#58a6ff; font-size:0.875rem;">
                {sand['ideas_activas']} ideas activas
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            🧩 {sand['snippets']} snippets guardados
        </p>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SECRETARIA IA - WIDGET INTERACTIVO
# ═══════════════════════════════════════════════════════════════

st.divider()
st.subheader("🤖 Secretaria IA")

from app.ai_client import chat_simple, verificar_conexion, api_key_configurada, estado_gemini

col_chat, col_alertas = st.columns([2, 1])

with col_chat:
    st.markdown("**💬 Chat rápido**")

    # Lee el estado ya calculado — NO vuelve a llamar a la API
    estado_actual = estado_gemini()
    key_ok = estado_actual.get('api_key_configurada')
    conectado = estado_actual.get('conectado')

    if not key_ok:
        st.warning("⚠️ Groq no configurada")
        st.info("Añade `GROQ_API_KEY=tu_key` al archivo `.env`")
    else:
        if not conectado:
            st.warning("⚠️ Modo offline — usando respuestas predefinidas")

        # El input funciona en ambos modos (online y offline)
        prompt_usuario = st.text_input(
            "Pregunta a tu secretaria:",
            placeholder="Ej: ¿Qué pasaje leer hoy?"
        )
        if prompt_usuario:
            # Contexto enriquecido con datos reales
            contexto_real = (
                f"Datos reales del usuario hoy ({date.today()}):\n"
                f"- Hábitos: {completados_hoy}/4 completados\n"
                f"- Finanzas: ${metricas['finanzas']['gastos']:,.0f} gastados "
                f"({metricas['finanzas']['pct']}% del presupuesto)\n"
                f"- Deep Work: {metricas['deep_work']['completados']}/"
                f"{metricas['deep_work']['total']} bloques esta semana\n"
                f"- Racha devocional: {metricas['teologia']['racha']} días\n"
                f"- Energía hoy: {metricas['salud']['energia']}/10\n"
                f"- Próxima cita: {metricas['matrimonio']['proxima']}"
            )
        if prompt_usuario:
            with st.spinner("Pensando..."):
                # chat_simple() ya tiene fallback interno
                respuesta = chat_simple(prompt_usuario)
                st.info(respuesta)

with col_alertas:
    st.markdown("**🔔 Alertas programadas**")
    
    hora_actual = datetime.now().hour
    minuto_actual = datetime.now().minute
    
    # Alertas con fallback automático
    if hora_actual == 5 and minuto_actual < 30:
        st.success("🌅 **05:00** - Tiempo de devocional. ¡Dios primero!")
    
    elif hora_actual == 6 and minuto_actual < 15:
        st.warning("⏰ **06:00** - Deep Work de código. ¡Modo foco!")
    
    elif hora_actual == 20 and minuto_actual >= 30:
        alerta = generar_alerta_matrimonio("día de trabajo normal")
        st.error(f"💑 **20:30** - {alerta}")

    elif completados_hoy == 4:
        st.success("🎉 ¡Todos los hábitos completados hoy!")

    elif completados_hoy >= 2:
        st.info(f"⚡ {completados_hoy}/4 hábitos completados")
    
    else:
        st.caption("Sin alertas activas en este momento")
        
    st.caption("Próximamente: Alertas reales con cron jobs")

# ═══════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════

st.divider()
st.caption(
    f"Mission Dashboard • {date.today().strftime('%d/%m/%Y')} • "
    f"Construido con ❤️ y disciplina • {completados_hoy}/4 hábitos hoy"
)