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
    st.session_state.user_name = "Ernesto Gregori"

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS - HÁBITOS Y MÉTRICAS
# ═══════════════════════════════════════════════════════════════

import sqlite3
from datetime import timedelta

def get_habitos_config() -> list:
    """Lee el catálogo de hábitos desde BD."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM habitos_config
            WHERE activo = 1
            ORDER BY orden, id
        """)
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()

def get_habitos_hoy() -> dict:
    """Obtiene estado de hábitos de hoy desde habitos_diarios_v2."""
    hoy = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Inicializar registros para hábitos activos
        configs = get_habitos_config()
        for h in configs:
            cursor.execute("""
                INSERT OR IGNORE INTO habitos_diarios_v2
                    (fecha, habito_clave, completado)
                VALUES (?, ?, 0)
            """, (hoy, h['clave']))
        conn.commit()

        cursor.execute("""
            SELECT * FROM habitos_diarios_v2
            WHERE fecha = ?
        """, (hoy,))
        return {
            row['habito_clave']: dict(row)
            for row in cursor.fetchall()
        }
    except Exception:
        return {}
    finally:
        conn.close()

def toggle_habito(clave: str):
    """Alterna completado de un hábito."""
    hoy = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT completado FROM habitos_diarios_v2
            WHERE fecha = ? AND habito_clave = ?
        """, (hoy, clave))
        row      = cursor.fetchone()
        nuevo    = 0 if (row and row[0]) else 1
        hora_now = datetime.now().strftime('%H:%M') if nuevo else None
        cursor.execute("""
            INSERT INTO habitos_diarios_v2
                (fecha, habito_clave, completado, hora_completado)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fecha, habito_clave)
            DO UPDATE SET completado = ?, hora_completado = ?
        """, (hoy, clave, nuevo, hora_now, nuevo, hora_now))
        conn.commit()
    finally:
        conn.close()

def agregar_habito(label: str, emoji: str, hora: str) -> bool:
    """Crea un nuevo hábito en el catálogo."""
    clave = label.lower().strip().replace(' ', '_')[:20]
    conn  = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        # Calcular orden máximo
        cursor.execute("SELECT MAX(orden) FROM habitos_config")
        max_ord = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT OR IGNORE INTO habitos_config
                (clave, label, emoji, hora, activo, orden)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (clave, label.strip(), emoji or '⭐',
              hora or '—', max_ord + 1))
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        return False
    finally:
        conn.close()

def editar_habito(clave: str, label: str,
                  emoji: str, hora: str) -> bool:
    """Edita label/emoji/hora de un hábito."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE habitos_config
            SET label=?, emoji=?, hora=?
            WHERE clave=?
        """, (label, emoji, hora, clave))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def eliminar_habito(clave: str) -> bool:
    """Desactiva un hábito (no lo borra, preserva historial)."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE habitos_config
            SET activo = 0
            WHERE clave = ?
        """, (clave,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def restaurar_habitos_default():
    """Reactiva los 4 hábitos fijos si fueron desactivados."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        for clave in ['devocional','codigo','lectura','calistenia']:
            cursor.execute("""
                UPDATE habitos_config SET activo = 1
                WHERE clave = ?
            """, (clave,))
        conn.commit()
    finally:
        conn.close()

def get_habitos_custom():
    return st.session_state.get('habitos_custom', {})

def toggle_habito_custom(clave: str):
    custom = st.session_state.get('habitos_custom', {})
    if clave in custom:
        custom[clave]['completado'] = (
            0 if custom[clave]['completado'] else 1
        )
        st.session_state.habitos_custom = custom

def eliminar_habito_custom(clave: str):
    custom = st.session_state.get('habitos_custom', {})
    custom.pop(clave, None)
    st.session_state.habitos_custom = custom

def get_metricas_modulos():
    """Lee datos reales de todos los módulos desde SQLite"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    metricas = {}
    hoy = date.today()

     # ── FINANZAS — usa sistema de 3 sobres ────────────────────
    try:
        from app.database import calcular_sobres
        mes_actual = hoy.month
        anio_actual = hoy.year
        datos_sobres = calcular_sobres(mes_actual, anio_actual)

        total_gastado = datos_sobres['total_gastado']
        ingreso       = datos_sobres['ingreso']

        if ingreso > 0:
            pct = int(total_gastado / ingreso * 100)
        else:
            # Fallback: leer tabla presupuestos vieja
            cursor.execute("""
                SELECT COALESCE(SUM(limite), 0) as total
                FROM presupuestos WHERE mes = ? AND anio = ?
            """, (hoy.month, hoy.year))
            ppto_viejo = cursor.fetchone()['total']
            pct = int(total_gastado / ppto_viejo * 100) \
                  if ppto_viejo > 0 else 0
            ingreso = ppto_viejo  # mostrar algo

        metricas['finanzas'] = {
            'gastos':       total_gastado,
            'presupuesto':  ingreso,
            'pct':          pct,
            'semaforo':     '🟢' if pct < 70 else '🟡' if pct < 90 else '🔴',
            'color':        '#3fb950' if pct < 70 else
                            '#e3b341' if pct < 90 else '#f85149',
            'sin_ingreso':  datos_sobres['sin_ingreso']
        }
    except Exception as e:
        metricas['finanzas'] = {
            'gastos': 0, 'presupuesto': 0,
            'pct': 0, 'semaforo': '⚪', 'color': '#8b949e',
            'sin_ingreso': True
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
# SECCIÓN 1: HÁBITOS DIARIOS — CRUD COMPLETO
# ═══════════════════════════════════════════════════════════════

st.subheader("📋 Hábitos del día")

# Session state para gestión
if 'modo_gestion_hab'  not in st.session_state:
    st.session_state.modo_gestion_hab  = False
if 'hab_editando'      not in st.session_state:
    st.session_state.hab_editando      = None

# Cargar datos
configs_hab = get_habitos_config()
habitos     = get_habitos_hoy()

# ── Botón gestionar ────────────────────────────────────────────
col_tit_h, col_btn_h = st.columns([5, 1])
with col_btn_h:
    if st.button(
        "✖ Cerrar" if st.session_state.modo_gestion_hab
        else "⚙️ Gestionar",
        use_container_width=True,
        key="btn_gest_hab"
    ):
        st.session_state.modo_gestion_hab = (
            not st.session_state.modo_gestion_hab
        )
        st.session_state.hab_editando = None
        st.rerun()

# ── PANEL GESTIÓN ──────────────────────────────────────────────
if st.session_state.modo_gestion_hab:
    with st.container():
        st.markdown("#### ⚙️ Gestión de hábitos")

        # ── Agregar nuevo ──────────────────────────────────────
        st.markdown("**➕ Nuevo hábito**")
        col_n1, col_n2, col_n3, col_n4 = st.columns([3, 1, 2, 1])
        with col_n1:
            nh_label = st.text_input(
                "Nombre", placeholder="Ej: Meditación",
                key="nh_label"
            )
        with col_n2:
            nh_emoji = st.text_input(
                "Emoji", value="⭐", max_chars=2,
                key="nh_emoji"
            )
        with col_n3:
            nh_hora = st.text_input(
                "Hora", placeholder="07:00",
                key="nh_hora"
            )
        with col_n4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Agregar",
                         use_container_width=True,
                         key="btn_nh"):
                if not nh_label.strip():
                    st.error("⚠️ Nombre requerido")
                else:
                    ok = agregar_habito(
                        nh_label, nh_emoji, nh_hora
                    )
                    if ok:
                        st.success(f"✅ '{nh_label}' creado")
                        st.rerun()
                    else:
                        st.warning("Ya existe un hábito con ese nombre")

        st.divider()

        # ── Lista de todos los hábitos con editar/eliminar ─────
        st.markdown("**📋 Hábitos activos:**")

        # Cargar TODOS (activos) para gestión
        conn_g = sqlite3.connect(DB_PATH, timeout=30)
        conn_g.row_factory = sqlite3.Row
        cur_g  = conn_g.cursor()
        cur_g.execute("""
            SELECT * FROM habitos_config
            ORDER BY orden, id
        """)
        todos_configs = [dict(r) for r in cur_g.fetchall()]
        conn_g.close()

        for hc in todos_configs:
            col_e, col_em, col_lab, col_hor, col_est, col_ed, col_del = \
                st.columns([0.5, 0.5, 2, 1.5, 1, 0.8, 0.8])

            with col_e:
                st.caption(hc['emoji'])
            with col_em:
                activo_txt = "🟢" if hc['activo'] else "⚪"
                st.caption(activo_txt)
            with col_lab:
                st.caption(f"**{hc['label']}**")
            with col_hor:
                st.caption(hc['hora'])
            with col_est:
                st.caption(
                    "Activo" if hc['activo'] else "Inactivo"
                )
            with col_ed:
                if st.button(
                    "✏️", key=f"ed_h_{hc['clave']}",
                    use_container_width=True,
                    help="Editar"
                ):
                    st.session_state.hab_editando = hc['clave']
                    st.rerun()
            with col_del:
                if st.button(
                    "🗑️" if hc['activo'] else "♻️",
                    key=f"del_h_{hc['clave']}",
                    use_container_width=True,
                    help="Desactivar" if hc['activo']
                         else "Reactivar"
                ):
                    if hc['activo']:
                        st.session_state[
                            f'confirm_del_h_{hc["clave"]}'
                        ] = True
                    else:
                        # Reactivar
                        conn_r = sqlite3.connect(DB_PATH, timeout=30)
                        conn_r.execute("""
                            UPDATE habitos_config
                            SET activo=1 WHERE clave=?
                        """, (hc['clave'],))
                        conn_r.commit()
                        conn_r.close()
                        st.success(f"♻️ '{hc['label']}' reactivado")
                        st.rerun()

            # Confirmar eliminación
            if st.session_state.get(
                f'confirm_del_h_{hc["clave"]}'
            ):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.warning(
                        f"⚠️ ¿Desactivar *{hc['label']}*? "
                        f"(el historial se conserva)"
                    )
                with c2:
                    if st.button(
                        "🗑️ Sí",
                        key=f"cfd_h_{hc['clave']}",
                        use_container_width=True
                    ):
                        eliminar_habito(hc['clave'])
                        st.session_state[
                            f'confirm_del_h_{hc["clave"]}'
                        ] = False
                        st.success(
                            f"✅ '{hc['label']}' desactivado"
                        )
                        st.rerun()
                with c3:
                    if st.button(
                        "✖", key=f"cnf_h_{hc['clave']}",
                        use_container_width=True
                    ):
                        st.session_state[
                            f'confirm_del_h_{hc["clave"]}'
                        ] = False
                        st.rerun()

            # Formulario edición inline
            if st.session_state.hab_editando == hc['clave']:
                with st.form(f"form_edit_h_{hc['clave']}"):
                    st.markdown(f"#### ✏️ Editando: {hc['label']}")
                    col_f1, col_f2, col_f3 = st.columns([3, 1, 2])
                    with col_f1:
                        e_label = st.text_input(
                            "Nombre", value=hc['label']
                        )
                    with col_f2:
                        e_emoji = st.text_input(
                            "Emoji", value=hc['emoji'],
                            max_chars=2
                        )
                    with col_f3:
                        e_hora = st.text_input(
                            "Hora", value=hc['hora']
                        )
                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button(
                            "💾 Guardar",
                            use_container_width=True,
                            type="primary"
                        ):
                            if not e_label.strip():
                                st.error("⚠️ Nombre requerido")
                            else:
                                editar_habito(
                                    hc['clave'],
                                    e_label, e_emoji, e_hora
                                )
                                st.session_state.hab_editando = None
                                st.success("✅ Actualizado")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button(
                            "✖ Cancelar",
                            use_container_width=True
                        ):
                            st.session_state.hab_editando = None
                            st.rerun()

        # Botón restaurar defaults
        st.divider()
        if st.button(
            "♻️ Restaurar hábitos por defecto",
            use_container_width=False
        ):
            restaurar_habitos_default()
            st.success("✅ Hábitos por defecto restaurados")
            st.rerun()

    st.divider()

# ── TARJETAS DE HÁBITOS ────────────────────────────────────────
n_cols = min(len(configs_hab), 6) if configs_hab else 4
cols_h = st.columns(n_cols)

for i, cfg in enumerate(configs_hab):
    clave      = cfg['clave']
    completado = habitos.get(clave, {}).get('completado', 0)
    hora_ok    = habitos.get(clave, {}).get('hora_completado', '')

    color_b = '#3fb950' if completado else '#30363d'
    color_f = '#0f2d0f' if completado else '#161b22'
    simbolo = '✅'       if completado else '○'
    color_s = '#3fb950' if completado else '#8b949e'

    with cols_h[i % n_cols]:
        st.markdown(f"""
        <div style="background:{color_f}; border:1px solid {color_b};
                    border-radius:12px; padding:1rem;
                    text-align:center; margin-bottom:0.5rem;">
            <div style="font-size:1.5rem;">{cfg['emoji']}</div>
            <div style="color:#f0f6fc; font-weight:600;
                        font-size:0.9rem;">{cfg['label']}</div>
            <div style="color:{color_s}; font-size:1.8rem;
                        line-height:1.2;">{simbolo}</div>
            <div style="color:#8b949e; font-size:0.75rem;">
                {cfg['hora']}
            </div>
            {f'<div style="color:#3fb950; font-size:0.7rem;">✓ {hora_ok}</div>'
              if hora_ok else ''}
        </div>
        """, unsafe_allow_html=True)

        if st.button(
            "✓ Hecho" if completado else "Marcar ✓",
            key=f"hab_{clave}",
            use_container_width=True,
            type="secondary" if completado else "primary"
        ):
            toggle_habito(clave)
            st.rerun()

# ── Progreso ───────────────────────────────────────────────────
completados_hoy = sum(
    1 for cfg in configs_hab
    if habitos.get(cfg['clave'], {}).get('completado')
)
total_hoy = len(configs_hab)

st.progress(
    completados_hoy / total_hoy if total_hoy else 0,
    text=f"Hábitos completados: {completados_hoy}/{total_hoy}"
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
    sin_ingreso_txt = (
        " · ⚠️ Registra ingreso en Finanzas"
        if fin.get('sin_ingreso') else ""
    )
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex; justify-content:space-between;
                    align-items:center;">
            <span style="color:#f0f6fc; font-weight:600;">
                💰 Finanzas Personales
            </span>
            <span style="color:{fin['color']}; font-size:0.875rem;">
                {fin['semaforo']} {fin['pct']}% usado
            </span>
        </div>
        <p style="color:#8b949e; font-size:0.875rem; margin-top:0.5rem;">
            Gastado: ${fin['gastos']:,.0f} /
            Ingreso: ${fin['presupuesto']:,.0f}
            {sin_ingreso_txt}
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