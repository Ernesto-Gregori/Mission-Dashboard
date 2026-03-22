"""
📅 Agenda — Calendario unificado + Bitácora semanal + Rachas
"""

import streamlit as st
from datetime import date, datetime, timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
from app.ai_client import chat_simple, api_key_configurada
import sqlite3
from app.google_calendar import (
    obtener_eventos_google,
    crear_evento_google,
    eliminar_evento_google,
    calendar_disponible,
    sincronizar_bloques_semana,
)

st.set_page_config(
    page_title="Agenda | Mission Dashboard",
    page_icon="📅",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
SEMAFOROS   = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}

SYSTEM_AGENDA = """Eres un asistente de planificación semanal cristiano.
Ayudas a revisar victorias, planificar la semana y reflexionar.
Eres práctico, motivador y consideras el balance vida-fe-familia.
Máximo 120 palabras."""

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — BITÁCORA
# ═══════════════════════════════════════════════════════════════

def obtener_lunes_semana(fecha=None):
    """Retorna el lunes de la semana de la fecha dada."""
    f = fecha or date.today()
    return f - timedelta(days=f.weekday())

def guardar_bitacora(datos: dict):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO bitacora_semanal (
                semana_inicio, victoria_1, victoria_2, victoria_3,
                ingreso_actual, sobre_supervivencia, aporte_transicion,
                presupuesto_cita, semaforo_superv, semaforo_ahorros,
                semaforo_extras, gasto_pausado,
                actividad_cita, costo_cita,
                libro_actual, pagina_actual, frase_favorita,
                pendientes_soltar, reflexion_semana, estado,
                actualizado_en
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'abierta',?
            )
            ON CONFLICT(semana_inicio) DO UPDATE SET
                victoria_1          = excluded.victoria_1,
                victoria_2          = excluded.victoria_2,
                victoria_3          = excluded.victoria_3,
                ingreso_actual      = excluded.ingreso_actual,
                sobre_supervivencia = excluded.sobre_supervivencia,
                aporte_transicion   = excluded.aporte_transicion,
                presupuesto_cita    = excluded.presupuesto_cita,
                semaforo_superv     = excluded.semaforo_superv,
                semaforo_ahorros    = excluded.semaforo_ahorros,
                semaforo_extras     = excluded.semaforo_extras,
                gasto_pausado       = excluded.gasto_pausado,
                actividad_cita      = excluded.actividad_cita,
                costo_cita          = excluded.costo_cita,
                libro_actual        = excluded.libro_actual,
                pagina_actual       = excluded.pagina_actual,
                frase_favorita      = excluded.frase_favorita,
                pendientes_soltar   = excluded.pendientes_soltar,
                reflexion_semana    = excluded.reflexion_semana,
                actualizado_en      = excluded.actualizado_en
        """, (
            datos['semana_inicio'],
            datos.get('victoria_1',''),
            datos.get('victoria_2',''),
            datos.get('victoria_3',''),
            datos.get('ingreso_actual', 0),
            datos.get('sobre_supervivencia', 0),
            datos.get('aporte_transicion', 0),
            datos.get('presupuesto_cita', 0),
            datos.get('semaforo_superv','verde'),
            datos.get('semaforo_ahorros','verde'),
            datos.get('semaforo_extras','verde'),
            datos.get('gasto_pausado',''),
            datos.get('actividad_cita',''),
            datos.get('costo_cita', 0),
            datos.get('libro_actual',''),
            datos.get('pagina_actual', 0),
            datos.get('frase_favorita',''),
            datos.get('pendientes_soltar',''),
            datos.get('reflexion_semana',''),
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    finally:
        conn.close()

def obtener_bitacora(semana_inicio: str):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM bitacora_semanal WHERE semana_inicio = ?",
        (semana_inicio,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def obtener_bitacoras_recientes(limite=10):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM bitacora_semanal
        ORDER BY semana_inicio DESC LIMIT ?
    """, (limite,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — DATOS DE OTROS MÓDULOS
# ═══════════════════════════════════════════════════════════════

def obtener_eventos_semana(lunes: date, domingo: date):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Citas matrimoniales
    cursor.execute("""
        SELECT fecha, hora as hora_inicio, titulo,
               tipo_cita as tipo, estado_planificacion,
               COALESCE(ambito, 'Matrimonio') as ambito,
               '#a371f7' as color, NULL as google_id
        FROM matrimonio_citas
        WHERE fecha >= ? AND fecha <= ?
        ORDER BY fecha, hora
    """, (lunes.isoformat(), domingo.isoformat()))
    citas = [dict(r) for r in cursor.fetchall()]
    
    # Eventos locales
    cursor.execute("""
        SELECT fecha, hora_inicio, titulo, tipo,
               '' as estado_planificacion,
               tipo as ambito, color, google_id
        FROM eventos_calendario
        WHERE fecha >= ? AND fecha <= ?
        ORDER BY fecha, hora_inicio
    """, (lunes.isoformat(), domingo.isoformat()))
    locales = [dict(r) for r in cursor.fetchall()]
    
    # Obtener nombres de bloques fijos para filtrar duplicados
    cursor.execute("SELECT nombre FROM bloques_fijos WHERE activo = 1")
    nombres_bloques = {row['nombre'] for row in cursor.fetchall()}
    
    conn.close()
    
    # IDs de Google ya sincronizados localmente
    google_ids_sincronizados = {
        e['google_id'] for e in locales if e.get('google_id')
    }
    
    # Eventos de Google Calendar
    # Excluir: los ya sincronizados localmente Y los que son bloques Deep Work
    google_eventos = []
    if calendar_disponible():
        eventos_gc = obtener_eventos_google(lunes, domingo)
        google_eventos = [
            e for e in eventos_gc
            if e.get('google_id') not in google_ids_sincronizados
            and e.get('titulo') not in nombres_bloques  # ← filtro nuevo
        ]
    
    todos = citas + locales + google_eventos
    
    def sort_key(e):
        hora = e.get('hora_inicio') or '23:59'
        return (e.get('fecha', ''), hora)
    
    todos.sort(key=sort_key)
    return todos

def obtener_deepwork_semana(lunes: date, domingo: date):
    """Trae bloques programados de la semana con su estado si existe."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    resultado = []
    
    # Iterar cada día de la semana
    for i in range(7):
        dia = lunes + timedelta(days=i)
        dia_iso = dia.isoformat()
        dia_numero = dia.weekday() + 1  # 1=Lunes ... 7=Domingo
        
        # Obtener bloques que aplican a este día
        cursor.execute("""
            SELECT b.id, b.nombre, b.color, b.tipo,
                   b.hora_inicio, b.hora_fin, b.dias_semana,
                   s.estado, s.duracion_real, s.notas
            FROM bloques_fijos b
            LEFT JOIN sesiones_completadas s 
                ON s.bloque_fijo_id = b.id AND s.fecha = ?
            WHERE b.activo = 1
        """, (dia_iso,))
        
        bloques = cursor.fetchall()
        
        for b in bloques:
            dias = json.loads(b['dias_semana'])
            if dia_numero not in dias:
                continue  # Este bloque no aplica hoy
            
            estado = b['estado'] or 'Pendiente'
            completado = 1 if estado == 'Completado' else 0
            
            resultado.append({
                'fecha': dia_iso,
                'bloque_nombre': b['nombre'],
                'color': b['color'],
                'tipo': b['tipo'],
                'hora_inicio': b['hora_inicio'],
                'duracion_real': b['duracion_real'],
                'estado': estado,
                'completado': completado,
                'notas': b['notas'],
            })
    
    conn.close()
    resultado.sort(key=lambda x: (x['fecha'], x.get('hora_inicio') or ''))
    return resultado

def obtener_devocionales_semana(lunes: date, domingo: date):
    """Trae devocionales de la semana."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fecha, pasaje_referencia, duracion_minutos
        FROM devocionales
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha
    """, (lunes.isoformat(), domingo.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def obtener_salud_semana(lunes: date, domingo: date):
    """Trae registros de salud de la semana."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fecha, horas_sueno, energia_manana as nivel_energia,
               hizo_ejercicio, productividad_percibida
        FROM registros_salud
        WHERE fecha BETWEEN ? AND ?
        ORDER BY fecha
    """, (lunes.isoformat(), domingo.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def obtener_libro_activo():
    """Trae el libro en lectura activa de Biblioteca."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT titulo, autor, pagina_actual, total_paginas
        FROM libros
        WHERE estado = 'leyendo'
        ORDER BY actualizado_en DESC LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ═══════════════════════════════════════════════════════════════
# FUNCIONES — RACHAS
# ═══════════════════════════════════════════════════════════════

def calcular_racha_devocional():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fecha FROM devocionales
        ORDER BY fecha DESC LIMIT 30
    """)
    fechas = [
        datetime.strptime(r['fecha'], '%Y-%m-%d').date()
        for r in cursor.fetchall()
    ]
    conn.close()
    racha = 0
    hoy   = date.today()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha

def calcular_racha_ejercicio():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fecha FROM registros_salud
        WHERE hizo_ejercicio = 1
        ORDER BY fecha DESC LIMIT 30
    """)
    fechas = [
        datetime.strptime(r['fecha'], '%Y-%m-%d').date()
        for r in cursor.fetchall()
    ]
    conn.close()
    if not fechas:
        return 0
    # Racha de ejercicio: contar semanas consecutivas con ≥1 sesión
    racha   = 0
    semanas = set()
    for f in fechas:
        lun = f - timedelta(days=f.weekday())
        semanas.add(lun)
    hoy_lun = date.today() - timedelta(days=date.today().weekday())
    for i in range(52):
        sem = hoy_lun - timedelta(weeks=i)
        if sem in semanas:
            racha += 1
        else:
            break
    return racha

def calcular_racha_deepwork():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT fecha FROM sesiones_completadas
        WHERE estado = 'Completado'
        ORDER BY fecha DESC LIMIT 30
    """)
    fechas = [
        datetime.strptime(r['fecha'], '%Y-%m-%d').date()
        for r in cursor.fetchall()
    ]
    conn.close()
    racha = 0
    hoy = date.today()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha

def obtener_eventos_personalizados(fecha: str = None):
    """Obtiene eventos personalizados, opcionalmente filtrados por fecha."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if fecha:
        cursor.execute("""
            SELECT * FROM eventos_calendario 
            WHERE fecha = ? ORDER BY hora_inicio
        """, (fecha,))
    else:
        cursor.execute("""
            SELECT * FROM eventos_calendario 
            ORDER BY fecha DESC, hora_inicio LIMIT 50
        """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def guardar_evento(datos: dict) -> int:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    # Debug — ver qué pasa con Google Calendar
    google_id = None
    if calendar_disponible():
        google_id = crear_evento_google(datos)
    
    cursor.execute("""
        INSERT INTO eventos_calendario 
        (fecha, hora_inicio, hora_fin, titulo, descripcion, 
         tipo, color, google_id, fuente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datos['fecha'], datos.get('hora_inicio'),
        datos.get('hora_fin'), datos['titulo'],
        datos.get('descripcion', ''), datos.get('tipo', 'Personal'),
        datos.get('color', '#58a6ff'),
        google_id,
        'local'
    ))
    evento_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return evento_id

def eliminar_evento(evento_id: int) -> bool:
    """Elimina evento local y de Google Calendar."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Obtener google_id antes de eliminar
    cursor.execute(
        "SELECT google_id FROM eventos_calendario WHERE id = ?", 
        (evento_id,)
    )
    row = cursor.fetchone()
    google_id = row['google_id'] if row else None
    
    # Eliminar local
    cursor.execute("DELETE FROM eventos_calendario WHERE id = ?", (evento_id,))
    ok = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    # Eliminar de Google Calendar
    if ok and google_id and calendar_disponible():
        eliminar_evento_google(google_id)
    
    return ok

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("📅 Agenda")
st.caption(
    "Calendario unificado · Bitácora semanal · Rachas · "
    "Lunes 18:00 abrir · Domingo 20:30 vaciado mental"
)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — RACHAS + RESUMEN
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔥 Rachas activas")

    r_dev = calcular_racha_devocional()
    r_ej  = calcular_racha_ejercicio()
    r_dw  = calcular_racha_deepwork()

    # Devocional
    color_dev = "#3fb950" if r_dev >= 7 else "#e3b341" if r_dev >= 3 else "#f85149"
    st.html(f"""
<div style="background:#161b22; border:1px solid #30363d;
            border-radius:10px; padding:0.75rem 1rem;
            margin-bottom:0.5rem; text-align:center;">
    <div style="font-size:1.5rem;">✝️</div>
    <div style="font-weight:700; color:{color_dev};
                font-size:1.25rem;">{r_dev} días</div>
    <div style="color:#8b949e; font-size:0.75rem;">
        Racha devocional
    </div>
</div>""")

    # Ejercicio
    color_ej = "#3fb950" if r_ej >= 4 else "#e3b341" if r_ej >= 2 else "#f85149"
    st.html(f"""
<div style="background:#161b22; border:1px solid #30363d;
            border-radius:10px; padding:0.75rem 1rem;
            margin-bottom:0.5rem; text-align:center;">
    <div style="font-size:1.5rem;">💪</div>
    <div style="font-weight:700; color:{color_ej};
                font-size:1.25rem;">{r_ej} semanas</div>
    <div style="color:#8b949e; font-size:0.75rem;">
        Racha ejercicio
    </div>
</div>""")

    # Deep Work
    color_dw = "#3fb950" if r_dw >= 5 else "#e3b341" if r_dw >= 3 else "#f85149"
    st.html(f"""
<div style="background:#161b22; border:1px solid #30363d;
            border-radius:10px; padding:0.75rem 1rem;
            margin-bottom:0.5rem; text-align:center;">
    <div style="font-size:1.5rem;">⏱️</div>
    <div style="font-weight:700; color:{color_dw};
                font-size:1.25rem;">{r_dw} días</div>
    <div style="color:#8b949e; font-size:0.75rem;">
        Racha Deep Work
    </div>
</div>""")

    st.divider()

    # Alerta vaciado mental
    hora_actual = datetime.now().hour
    if hora_actual >= 20 and date.today().weekday() == 6:
        st.warning("🌙 Domingo 20:30 — Vaciado mental")

    if api_key_configurada():
        st.success("🤖 IA activa")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_cal, tab_bitacora, tab_historial_bit = st.tabs([
    "📅 Calendario", "📋 Bitácora Semanal", "🗂️ Historial"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: CALENDARIO UNIFICADO
# ═══════════════════════════════════════════════════════════════

with tab_cal:
    st.subheader("📅 Vista semanal unificada")

    # ── Navegación de semana ─────────────────────────────────
    col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
    with col_nav1:
        if st.button("◀ Anterior", use_container_width=True):
            st.session_state.cal_offset = st.session_state.get('cal_offset', 0) - 1
    with col_nav2:
        lunes_base = obtener_lunes_semana()
        lunes_sel  = lunes_base + timedelta(weeks=st.session_state.get('cal_offset', 0))
        domingo_sel = lunes_sel + timedelta(days=6)
        st.markdown(
            f"<h4 style='text-align:center;margin:0;'>"
            f"Semana del {lunes_sel.strftime('%d/%m')} "
            f"al {domingo_sel.strftime('%d/%m/%Y')}</h4>",
            unsafe_allow_html=True
        )
    with col_nav3:
        if st.button("Siguiente ▶", use_container_width=True):
            st.session_state.cal_offset = st.session_state.get('cal_offset', 0) + 1

    # ── Sincronización Deep Work → Google Calendar ───────────
    # Fuera de las columnas para no romper el layout
    clave_sync = f"sync_dw_{lunes_sel.isoformat()}"
    if calendar_disponible() and clave_sync not in st.session_state:
        with st.spinner("Sincronizando bloques con Google Calendar..."):
            creados = sincronizar_bloques_semana(lunes_sel, domingo_sel)
            st.session_state[clave_sync] = True
        if creados > 0:
            st.success(f"✅ {creados} bloques sincronizados con Google Calendar")

    col_hoy, col_nuevo, col_gcal = st.columns([1, 2, 1])
    with col_hoy:
        if st.button("📅 Hoy", use_container_width=True):
            st.session_state.cal_offset = 0
            st.rerun()
    with col_nuevo:
        if st.button("➕ Nuevo evento", use_container_width=True, type="primary"):
            st.session_state['mostrar_form_evento'] = True
    with col_gcal:
        if calendar_disponible():
            st.success("📅 Sincronizado")
        else:
            st.warning("⚠️ Sin Google Cal")

    # ── Formulario nuevo evento ──────────────────────────────
    if st.session_state.get('mostrar_form_evento'):
        with st.expander("➕ Agregar evento al calendario", expanded=True):
            with st.form("form_nuevo_evento", clear_on_submit=True):
                col_fe1, col_fe2 = st.columns(2)
                with col_fe1:
                    fecha_ev = st.date_input("Fecha", value=date.today(), key="ev_fecha")
                    titulo_ev = st.text_input("Título *", placeholder="Ej: Lectura biblioteca", key="ev_titulo")
                    tipo_ev = st.selectbox("Tipo", 
                        ["Lectura", "Personal", "Ministerio", "Salud", "Estudio", "Otro"],
                        key="ev_tipo")
                with col_fe2:
                    hora_ini = st.time_input("Hora inicio (opcional)", key="ev_hora_ini",
                        value=datetime.strptime("19:30", "%H:%M").time())
                    hora_fin = st.time_input("Hora fin (opcional)", key="ev_hora_fin",
                        value=datetime.strptime("21:00", "%H:%M").time())
                    
                    COLORES_TIPO = {
                        "Lectura": "#e3b341",
                        "Personal": "#58a6ff", 
                        "Ministerio": "#a371f7",
                        "Salud": "#3fb950",
                        "Estudio": "#f0883e",
                        "Otro": "#8b949e"
                    }
                
                desc_ev = st.text_area("Descripción (opcional)", height=60, key="ev_desc")
                
                col_guardar, col_cancelar = st.columns(2)
                with col_guardar:
                    if st.form_submit_button("💾 Guardar evento", use_container_width=True):
                        if titulo_ev:
                            guardar_evento({
                                'fecha': fecha_ev.isoformat(),
                                'hora_inicio': hora_ini.strftime('%H:%M'),
                                'hora_fin': hora_fin.strftime('%H:%M'),
                                'titulo': titulo_ev,
                                'descripcion': desc_ev,
                                'tipo': tipo_ev,
                                'color': COLORES_TIPO.get(tipo_ev, '#58a6ff')
                            })
                            st.session_state['mostrar_form_evento'] = False
                            st.success("✅ Evento guardado")
                            st.rerun()
                        else:
                            st.error("El título es obligatorio")
                with col_cancelar:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.session_state['mostrar_form_evento'] = False
                        st.rerun()

    st.divider()

    # Cargar datos de todos los módulos
    eventos    = obtener_eventos_semana(lunes_sel, domingo_sel)
    dw_ses     = obtener_deepwork_semana(lunes_sel, domingo_sel)
    devos      = obtener_devocionales_semana(lunes_sel, domingo_sel)
    salud_sem  = obtener_salud_semana(lunes_sel, domingo_sel)

    # Índices por fecha
    eventos_x_fecha = {}
    for e in eventos:
        eventos_x_fecha.setdefault(e['fecha'], []).append(e)

    dw_x_fecha = {}
    for s in dw_ses:
        dw_x_fecha.setdefault(s['fecha'], []).append(s)

    devo_x_fecha  = {d['fecha']: d for d in devos}
    salud_x_fecha = {s['fecha']: s for s in salud_sem}

    # Leyenda
    col_l1, col_l2, col_l3, col_l4, col_l5, col_l6 = st.columns(6)
    col_l1.caption("✝️ Devocional")
    col_l2.caption("⏱️ Deep Work")
    col_l3.caption("💑 Matrimonio")
    col_l4.caption("📚 Lectura")
    col_l5.caption("💪 Ejercicio")
    col_l6.caption("🔵 Personal")

    st.markdown("")

    # Renderizar 7 días
    cols_dias = st.columns(7)
    hoy = date.today()

    COLORES_AMBITO = {
        'Matrimonio':  ('#a371f7', '#1a1229', '💑'),
        'Lectura':     ('#e3b341', '#1f1a0d', '📚'),
        'Personal':    ('#58a6ff', '#0d1629', '🔵'),
        'Ministerio':  ('#a371f7', '#1a1229', '⛪'),
        'Salud':       ('#3fb950', '#0d2818', '💪'),
        'Estudio':     ('#f0883e', '#1f1209', '📖'),
        'Otro':        ('#8b949e', '#161b22', '📌'),
    }

    for i, col in enumerate(cols_dias):
        dia     = lunes_sel + timedelta(days=i)
        dia_iso = dia.isoformat()
        es_hoy  = dia == hoy
        nombre  = DIAS_SEMANA[i]

        bg_header = "#0d2818" if es_hoy else "#161b22"
        border_c  = "#3fb950" if es_hoy  else "#30363d"

        with col:
            # Encabezado
            st.html(f"""
<div style="background:{bg_header};border:1px solid {border_c};
            border-radius:8px 8px 0 0;padding:0.4rem;
            text-align:center;margin-bottom:2px;">
    <div style="font-weight:700;color:#f0f6fc;font-size:0.85rem;">{nombre}</div>
    <div style="color:{'#3fb950' if es_hoy else '#8b949e'};font-size:0.75rem;">
        {dia.strftime('%d/%m')}
    </div>
</div>""")

            # Devocional
            if dia_iso in devo_x_fecha:
                d = devo_x_fecha[dia_iso]
                st.html(f"""
<div style="background:#0d2818;border-left:3px solid #3fb950;
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#9be4a0;">
    ✝️ {(d.get('pasaje_referencia') or '')[:14]}
</div>""")

            # Deep Work
            if dia_iso in dw_x_fecha:
                for s in dw_x_fecha[dia_iso]:
                    color_dw = s.get('color') or '#58a6ff'
                    estado   = s.get('estado', '')
                    completado = s.get('completado', 0)
                    bg_dw = "#0d1f2d" if completado else "#161b22"
                    opacity = "1" if completado else "0.6"
                    check = "✓ " if completado else ""
                    st.html(f"""
<div style="background:{bg_dw};border-left:3px solid {color_dw};
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;
            color:#c9d1d9;opacity:{opacity};">
    ⏱️ {check}{(s.get('bloque_nombre') or s.get('tipo','DW'))[:12]}
</div>""")

            # Eventos (matrimonio + personalizados)
            if dia_iso in eventos_x_fecha:
                for e in eventos_x_fecha[dia_iso]:
                    ambito = e.get('ambito', 'Otro')
                    color_e, bg_e, icon_e = COLORES_AMBITO.get(
                        ambito, ('#8b949e', '#161b22', '📌')
                    )
                    hora_str = ""
                    if e.get('hora_inicio'):
                        hora_str = f" {e['hora_inicio'][:5]}"
                    st.html(f"""
<div style="background:{bg_e};border-left:3px solid {color_e};
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#c9d1d9;">
    {icon_e} {(e.get('titulo') or '')[:13]}{hora_str}
</div>""")

            # Ejercicio
            if dia_iso in salud_x_fecha:
                s_dia = salud_x_fecha[dia_iso]
                if s_dia.get('hizo_ejercicio'):
                    tipo_ej = s_dia.get('tipo_ejercicio', 'Ejercicio') or 'Ejercicio'
                    st.html(f"""
<div style="background:#0d2818;border-left:3px solid #f0883e;
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#f0883e;">
    💪 {tipo_ej[:14]}
</div>""")

                energia = s_dia.get('nivel_energia') or 0
                if energia:
                    color_en = (
                        "#3fb950" if energia >= 8 else
                        "#e3b341" if energia >= 5 else "#f85149"
                    )
                    st.html(f"""
<div style="background:#161b22;border-radius:4px;
            padding:0.2rem 0.4rem;font-size:0.65rem;
            color:{color_en};">⚡ {energia}/10</div>""")

    # ── Resumen + Gestionar eventos ──────────────────────────
    st.divider()
    
    col_res, col_gest = st.columns([2, 1])
    
    with col_res:
        st.markdown("### 📊 Resumen de la semana")
        col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
        col_r1.metric("✝️ Devocionales", f"{len(devos)}/7")
        col_r2.metric("⏱️ Deep Work",
            len([s for s in dw_ses if s.get('completado') == 1]))
        col_r3.metric("📅 Eventos", len(eventos))
        col_r4.metric("💪 Ejercicios",
            len([s for s in salud_sem if s.get('hizo_ejercicio')]))
        prom_energia = (
            sum(s.get('nivel_energia') or 0 for s in salud_sem) / len(salud_sem)
            if salud_sem else 0
        )
        col_r5.metric("⚡ Energía", f"{prom_energia:.1f}/10" if prom_energia else "—")
    
    with col_gest:
        st.markdown("### 🗑️ Gestionar eventos")
        eventos_pers = obtener_eventos_personalizados()
        if not eventos_pers:
            st.caption("Sin eventos personalizados aún")
        else:
            for ep in eventos_pers[:5]:
                col_ep1, col_ep2 = st.columns([3, 1])
                with col_ep1:
                    st.caption(f"📌 {ep['fecha']} — {ep['titulo'][:20]}")
                with col_ep2:
                    if st.button("🗑️", key=f"del_ev_{ep['id']}"):
                        eliminar_evento(ep['id'])
                        st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: BITÁCORA SEMANAL
# ═══════════════════════════════════════════════════════════════

with tab_bitacora:
    st.subheader("📋 Bitácora Semanal")
    st.caption(
        "Abrir domingo 19:00 · cierre de revision semanal · "
    )

    # Selector de semana para bitácora
    col_bs1, col_bs2 = st.columns([2, 1])
    with col_bs1:
        lunes_bit = obtener_lunes_semana()
        fecha_bit_sel = st.date_input(
            "Semana (selecciona cualquier día)",
            value=lunes_bit,
            key="fecha_bitacora"
        )
        lunes_bit_sel = obtener_lunes_semana(fecha_bit_sel)
        domingo_bit   = lunes_bit_sel + timedelta(days=6)
        st.caption(
            f"Semana: {lunes_bit_sel.strftime('%d/%m/%Y')} "
            f"— {domingo_bit.strftime('%d/%m/%Y')}"
        )
    with col_bs2:
        st.markdown("<br>", unsafe_allow_html=True)
        es_semana_actual = lunes_bit_sel == obtener_lunes_semana()
        if es_semana_actual:
            st.success("📅 Semana actual")
        else:
            st.caption("📁 Semana pasada")

    # Cargar bitácora existente
    bit = obtener_bitacora(lunes_bit_sel.isoformat()) or {}

    # ── Cargar datos automáticos de otros módulos ────────────────
    libro_activo = obtener_libro_activo()

    # 1. Ingreso del mes desde ingreso_mensual
    from app.database import obtener_ingreso, calcular_sobres
    mes_bit = lunes_bit_sel.month
    anio_bit = lunes_bit_sel.year
    ingreso_auto = obtener_ingreso(mes_bit, anio_bit)

    # 2. Semáforo financiero calculado desde gastos_sobres
    sobres_data = calcular_sobres(mes_bit, anio_bit)
    def _calcular_semaforo(sobre_key):
        if sobres_data['sin_ingreso']:
            return 'verde'
        pct = sobres_data['sobres'].get(sobre_key, {}).get('pct_usado', 0)
        if pct >= 100:
            return 'rojo'
        elif pct >= 80:
            return 'amarillo'
        return 'verde'

    semaforo_sup_auto  = _calcular_semaforo('Supervivencia')
    semaforo_aho_auto  = _calcular_semaforo('Futuro_Hogar')
    semaforo_ext_auto  = _calcular_semaforo('Ministerio_Extras')

    # 3. Presupuesto cita desde citas matrimoniales confirmadas esta semana
    eventos_bit_auto = obtener_eventos_semana(lunes_bit_sel, domingo_bit)
    citas_mat_auto = [
        e for e in eventos_bit_auto
        if e.get('ambito') == 'Matrimonio'
    ]
    presup_cita_auto = 0.0
    if citas_mat_auto:
        conn_tmp = sqlite3.connect(DB_PATH, timeout=30)
        cursor_tmp = conn_tmp.cursor()
        cursor_tmp.execute("""
            SELECT presupuesto_estimado FROM matrimonio_citas
            WHERE titulo = ? AND fecha = ?
        """, (citas_mat_auto[0]['titulo'], citas_mat_auto[0]['fecha']))
        row_tmp = cursor_tmp.fetchone()
        conn_tmp.close()
        presup_cita_auto = float(row_tmp[0]) if row_tmp and row_tmp[0] else 0.0

    # 4. Rachas
    racha_dev_auto = calcular_racha_devocional()
    racha_ej_auto  = calcular_racha_ejercicio()
    racha_dw_auto  = calcular_racha_deepwork()

    # ── SECCIÓN 1: 3 Victorias ─────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏆 1. Definición de Objetivos — Las 3 Victorias")
    st.caption(
        "Según el principio de las '3 Victorias' — "
        "¿Qué 3 cosas harían esta semana un éxito?"
    )

    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        v1 = st.text_area(
            "🥇 Victoria #1",
            value=bit.get('victoria_1',''),
            height=100,
            placeholder="Ej: Entregar proyecto de programación",
            key="bit_v1"
        )
    with col_v2:
        v2 = st.text_area(
            "🥈 Victoria #2",
            value=bit.get('victoria_2',''),
            height=100,
            placeholder="Ej: Completar capítulo de Hermenéutica",
            key="bit_v2"
        )
    with col_v3:
        v3 = st.text_area(
            "🥉 Victoria #3",
            value=bit.get('victoria_3',''),
            height=100,
            placeholder="Ej: Cita de calidad con esposa",
            key="bit_v3"
        )

    # ── SECCIÓN 2: Monitor Financiero ─────────────────────────
    st.markdown("---")
    st.markdown("### 💰 2. Monitor Financiero")
    st.caption("Sistema de Cascada, Cimiento y Propósito")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        ingreso_guardado = bit.get('ingreso_actual')
        ingreso_default = float(ingreso_guardado) if ingreso_guardado else float(ingreso_auto or 0)

        ingreso = st.number_input(
            "Ingreso actual $",
            min_value=0.0, step=100.0,
            value=ingreso_default,
            key="bit_ingreso"
        )
        sobre_sup = st.checkbox(
            "✅ Sobre de Supervivencia (60-70%) llenado",
            value=bool(bit.get('sobre_supervivencia', 0)),
            key="bit_sobre_sup"
        )
    with col_f2:
        aporte_trans = st.number_input(
            "Aporte Fondo Transición (Meta $400) $",
            min_value=0.0, step=50.0,
            value=float(bit.get('aporte_transicion') or 0),
            key="bit_aporte"
        )
        presup_cita = st.number_input(
            "Presupuesto cita con esposa $",
            min_value=0.0, step=50.0,
            value=float(bit.get('presupuesto_cita') or 0),
            key="bit_presup_cita"
        )
    with col_f3:
        gasto_pausado = st.text_input(
            "⚠️ Gasto/sobre a pausar esta semana (opcional)",
            value=bit.get('gasto_pausado',''),
            placeholder="Ej: Extras / Entretenimiento",
            key="bit_gasto_pausado"
        )

    # Semáforo financiero
    st.markdown("**🚦 Estado del Semáforo:**")
    col_sf1, col_sf2, col_sf3 = st.columns(3)
    with col_sf1:
        sem_sup = st.selectbox(
            "Supervivencia",
            ["verde","amarillo","rojo"],
            index=["verde","amarillo","rojo"].index(
                bit.get('semaforo_superv','verde')
            ),
            format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}",
            key="bit_sem_sup"
        )
    with col_sf2:
        sem_aho = st.selectbox(
            "Ahorros",
            ["verde","amarillo","rojo"],
            index=["verde","amarillo","rojo"].index(
                bit.get('semaforo_ahorros','verde')
            ),
            format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}",
            key="bit_sem_aho"
        )
    with col_sf3:
        sem_ext = st.selectbox(
            "Extras",
            ["verde","amarillo","rojo"],
            index=["verde","amarillo","rojo"].index(
                bit.get('semaforo_extras','verde')
            ),
            format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}",
            key="bit_sem_ext"
        )

    # ── SECCIÓN 3: Diseño de Cita ──────────────────────────────
    st.markdown("---")
    st.markdown("### 💑 3. Diseño de Cita y Conexión")
    st.caption("Calidad relacional sin importar el presupuesto")

    # Auto-cargar próxima cita matrimonial de la semana
    eventos_bit  = obtener_eventos_semana(lunes_bit_sel, domingo_bit)
    citas_mat    = [
        e for e in eventos_bit
        if e.get('ambito') == 'Matrimonio'
    ]

    if citas_mat and not bit.get('actividad_cita'):
        st.info(
            f"💡 Tienes programado: **{citas_mat[0]['titulo']}** "
            f"el {citas_mat[0]['fecha']}"
        )

    col_cit1, col_cit2 = st.columns(2)
    with col_cit1:
        act_cita = st.text_input(
            "Actividad elegida",
            value=bit.get('actividad_cita','') or
                  (citas_mat[0]['titulo'] if citas_mat else ''),
            placeholder="Cena en casa, salida al parque...",
            key="bit_act_cita"
        )
    with col_cit2:
        costo_cita = st.number_input(
            "Costo estimado $",
            min_value=0.0, step=50.0,
            value=float(bit.get('costo_cita') or 0),
            key="bit_costo_cita"
        )

    # Validación semáforo
    if sem_ext == 'rojo' and costo_cita > 0:
        st.warning(
            "⚠️ Semáforo extras en 🔴 — considera una cita en casa"
        )
    elif sem_ext == 'amarillo' and costo_cita > 200:
        st.warning(
            "🟡 Extras en amarillo — cita con presupuesto ajustado"
        )

    # ── SECCIÓN 4: Log de Lectura ──────────────────────────────
    st.markdown("---")
    st.markdown("### 📚 4. Log de Lectura y Conocimiento")
    st.caption("Basado en tu Sistema de Color y LiquidText — Protocolo 5 min")

    # Obtener TODOS los libros en lectura activa
    conn_lib = sqlite3.connect(DB_PATH, timeout=30)
    conn_lib.row_factory = sqlite3.Row
    cursor_lib = conn_lib.cursor()
    cursor_lib.execute("""
        SELECT titulo, autor, pagina_actual, total_paginas
        FROM libros WHERE estado = 'leyendo'
        ORDER BY actualizado_en DESC
    """)
    libros_leyendo = [dict(r) for r in cursor_lib.fetchall()]
    conn_lib.close()

    col_lib1, col_lib2 = st.columns(2)
    with col_lib1:
        if libros_leyendo:
            if len(libros_leyendo) > 1:
                libro_sel_idx = st.selectbox(
                    "📖 Seleccionar libro",
                    options=range(len(libros_leyendo)),
                    format_func=lambda i: (
                        f"{libros_leyendo[i]['titulo']} "
                        f"— pág. {libros_leyendo[i]['pagina_actual'] or 0}"
                    ),
                    key="bit_sel_libro"
                )
                libro_activo_sel = libros_leyendo[libro_sel_idx]
            else:
                libro_activo_sel = libros_leyendo[0]

            pag_default = libro_activo_sel.get('pagina_actual') or 0
            total_pag   = libro_activo_sel.get('total_paginas') or 0
            pct_libro   = int(pag_default / total_pag * 100) if total_pag > 0 else 0

            st.success(
                f"📖 **{libro_activo_sel['titulo']}** — "
                f"pág. {pag_default} / {total_pag} ({pct_libro}%)"
            )
            st.progress(pct_libro / 100)

            # Guardar título del libro seleccionado (sin campo de texto)
            libro_bit = f"{libro_activo_sel['titulo']} — {libro_activo_sel['autor'] or ''}"
        else:
            libro_bit     = bit.get('libro_actual', '')
            pag_default   = 0
            st.info("📚 No hay libros en lectura activa")
            # Solo mostrar campo manual si no hay libros activos
            libro_bit = st.text_input(
                "Libro actual",
                value=libro_bit,
                placeholder="Título del libro...",
                key="bit_libro"
            )

        pag_bit = st.number_input(
            "Página actual",
            min_value=0, step=1,
            value=int(bit.get('pagina_actual') or pag_default),
            key="bit_pag"
        )

    with col_lib2:
        frase_bit = st.text_area(
            "✨ Frase favorita de la semana",
            value=bit.get('frase_favorita',''),
            height=120,
            placeholder="La frase que más te impactó...",
            key="bit_frase"
        )

    # ── SECCIÓN 5: Vaciado Mental ──────────────────────────────
    st.markdown("---")
    st.markdown("### 🌙 5. Vaciado Mental y Fricción Cero")
    st.caption("Domingo 20:30 — Soltar antes de dormir y preparar el lunes")

    col_vm1, col_vm2 = st.columns(2)
    with col_vm1:
        pendientes = st.text_area(
            "📤 Pendientes para 'Soltar'",
            value=bit.get('pendientes_soltar',''),
            height=120,
            placeholder=(
                "Escribe todo lo que está en tu mente...\n"
                "Tareas, preocupaciones, ideas sueltas...\n"
                "Solo escríbelas para liberarlas."
            ),
            key="bit_pendientes"
        )
    with col_vm2:
        reflexion = st.text_area(
            "💭 Reflexión de la semana",
            value=bit.get('reflexion_semana',''),
            height=120,
            placeholder=(
                "¿Cómo fue la semana?\n"
                "¿Qué aprendiste?\n"
                "¿Por qué dar gracias?"
            ),
            key="bit_reflexion"
        )

    # ── DATOS AUTOMÁTICOS DE LA SEMANA ────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Datos automáticos de la semana")

    devos_bit  = obtener_devocionales_semana(lunes_bit_sel, domingo_bit)
    dw_bit     = obtener_deepwork_semana(lunes_bit_sel, domingo_bit)
    salud_bit  = obtener_salud_semana(lunes_bit_sel, domingo_bit)
    eventos_f  = obtener_eventos_semana(lunes_bit_sel, domingo_bit)

    # Fila 1 — métricas de la semana
    col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns(5)
    col_a1.metric("✝️ Devocionales", f"{len(devos_bit)}/7",
        delta="✅" if len(devos_bit) >= 5 else "⚠️")
    col_a2.metric("⏱️ Deep Work",
        len([s for s in dw_bit if s.get('completado') == 1]))
    col_a3.metric("💪 Ejercicios",
        len([s for s in salud_bit if s.get('hizo_ejercicio')]))
    col_a4.metric("💑 Eventos", len(eventos_f))
    prom_e = (
        sum(s.get('nivel_energia') or 0 for s in salud_bit) /
        len(salud_bit) if salud_bit else 0
    )
    col_a5.metric("⚡ Energía prom", f"{prom_e:.1f}/10" if prom_e else "—")

    # Fila 2 — rachas activas
    st.markdown("**🔥 Rachas activas esta semana:**")
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)

    color_rd = "#3fb950" if racha_dev_auto >= 7 else "#e3b341" if racha_dev_auto >= 3 else "#f85149"
    color_re = "#3fb950" if racha_ej_auto >= 4  else "#e3b341" if racha_ej_auto >= 2  else "#f85149"
    color_rw = "#3fb950" if racha_dw_auto >= 5  else "#e3b341" if racha_dw_auto >= 3  else "#f85149"

    col_r1.metric("✝️ Racha devocional", f"{racha_dev_auto} días")
    col_r2.metric("💪 Racha ejercicio",  f"{racha_ej_auto} semanas")
    col_r3.metric("⏱️ Racha Deep Work",  f"{racha_dw_auto} días")

    # Fila 3 — resumen financiero automático
    if not sobres_data['sin_ingreso']:
        st.markdown("**💰 Estado financiero automático:**")
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        col_f1.metric("Ingreso", f"${sobres_data['ingreso']:,.0f}")
        col_f2.metric("Gastado", f"${sobres_data['total_gastado']:,.0f}",
            f"{sobres_data['pct_global']:.0f}%")
        col_f3.metric("Supervivencia",
            f"{sobres_data['sobres']['Supervivencia']['pct_usado']:.0f}%",
            SEMAFOROS[semaforo_sup_auto])
        col_f4.metric("Disponible",
            f"${sobres_data['total_disponible']:,.0f}")

    # ── GUARDAR ────────────────────────────────────────────────
    st.markdown("---")
    col_gbtn, col_ia_btn = st.columns(2)

    with col_gbtn:
        if st.button(
            "💾 Guardar bitácora",
            use_container_width=True,
            type="primary",
            key="btn_guardar_bit"
        ):
            ok = guardar_bitacora({
                'semana_inicio':      lunes_bit_sel.isoformat(),
                'victoria_1':         v1,
                'victoria_2':         v2,
                'victoria_3':         v3,
                'ingreso_actual':     ingreso,
                'sobre_supervivencia': 1 if sobre_sup else 0,
                'aporte_transicion':  aporte_trans,
                'presupuesto_cita':   presup_cita,
                'semaforo_superv':    sem_sup,
                'semaforo_ahorros':   sem_aho,
                'semaforo_extras':    sem_ext,
                'gasto_pausado':      gasto_pausado,
                'actividad_cita':     act_cita,
                'costo_cita':         costo_cita,
                'libro_actual':       libro_bit,
                'pagina_actual':      pag_bit,
                'frase_favorita':     frase_bit,
                'pendientes_soltar':  pendientes,
                'reflexion_semana':   reflexion,
            })
            if ok:
                st.success("✅ Bitácora guardada correctamente")
                st.rerun()

    with col_ia_btn:
        if st.button(
            "🤖 Análisis completo IA",
            use_container_width=True,
            type="primary",
            key="btn_ia_completo"
        ):
            bitacoras_historial = obtener_bitacoras_recientes(8)
            dw_completados = len([s for s in dw_bit if s.get('completado') == 1])
            
            # Construir contexto completo
            victorias_txt = [v for v in [v1, v2, v3] if v]
            historial_txt = ""
            if len(bitacoras_historial) > 1:
                historial_txt = "\nHISTORIAL ÚLTIMAS SEMANAS:\n"
                for b in bitacoras_historial[1:4]:
                    vs = [b.get(f'victoria_{i}','') for i in range(1,4)]
                    historial_txt += (
                        f"  {b['semana_inicio']}: "
                        f"{len([v for v in vs if v])} victorias | "
                        f"Semáforo: {b.get('semaforo_superv','?')}/"
                        f"{b.get('semaforo_ahorros','?')}/"
                        f"{b.get('semaforo_extras','?')}\n"
                    )
                    if b.get('reflexion_semana'):
                        historial_txt += f"  Reflexión: {b['reflexion_semana'][:80]}\n"

            prompt = f"""
    Analiza esta bitácora semanal de forma completa:

    VICTORIAS PLANIFICADAS:
    {chr(10).join(f'{i+1}. {v}' for i,v in enumerate(victorias_txt)) or 'No definidas'}

    DATOS REALES:
    - Devocionales: {len(devos_bit)}/7
    - Deep Work completados: {dw_completados}
    - Ejercicios: {len([s for s in salud_bit if s.get('hizo_ejercicio')])}
    - Energía promedio: {prom_e:.1f}/10
    - Rachas: devocional {racha_dev_auto}d, ejercicio {racha_ej_auto}sem, DW {racha_dw_auto}d

    FINANZAS:
    - Ingreso: ${sobres_data['ingreso']:,.0f} | Gastado: ${sobres_data['total_gastado']:,.0f}
    - Semáforo: Sup {sem_sup} | Ahorros {sem_aho} | Extras {sem_ext}

    REFLEXIÓN: {reflexion or 'Sin reflexión aún'}
    {historial_txt}

    Responde en 4 secciones cortas (máx 200 palabras total):

    🏆 VICTORIAS: ¿Cuáles se lograron? ¿Qué faltó?
    🔍 PATRÓN: Una observación del historial (si hay datos)
    ⚖️ BALANCE: Lo más positivo y lo más preocupante
    🚀 PRÓXIMA SEMANA: 2 acciones concretas + versículo
    """
            with st.spinner("Analizando tu semana..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

# ═══════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL DE BITÁCORAS
# ═══════════════════════════════════════════════════════════════

with tab_historial_bit:
    st.subheader("🗂️ Historial de bitácoras")

    bitacoras = obtener_bitacoras_recientes(12)

    if not bitacoras:
        st.info("📭 Sin bitácoras registradas aún")
    else:
        # ── Selector de semana a analizar ────────────────────
        semanas_opciones = [b['semana_inicio'] for b in bitacoras]
        semana_sel = st.selectbox(
            "Seleccionar semana para análisis",
            options=semanas_opciones,
            format_func=lambda x: f"Semana del {x} al {(datetime.strptime(x,'%Y-%m-%d').date() + timedelta(days=6)).strftime('%d/%m/%Y')}",
            key="sel_semana_historial"
        )

        # Cargar bitácora seleccionada
        bit_sel = next((b for b in bitacoras if b['semana_inicio'] == semana_sel), None)

        if bit_sel:
            lun_sel = datetime.strptime(semana_sel, '%Y-%m-%d').date()
            dom_sel = lun_sel + timedelta(days=6)

            # Semáforos
            s_sup = SEMAFOROS.get(bit_sel.get('semaforo_superv','verde'),'🟢')
            s_aho = SEMAFOROS.get(bit_sel.get('semaforo_ahorros','verde'),'🟢')
            s_ext = SEMAFOROS.get(bit_sel.get('semaforo_extras','verde'),'🟢')

            victorias_sel = [
                bit_sel.get('victoria_1',''),
                bit_sel.get('victoria_2',''),
                bit_sel.get('victoria_3','')
            ]
            victorias_ok_sel = [v for v in victorias_sel if v]

            # ── Resumen de la bitácora ────────────────────────
            with st.expander("📋 Ver bitácora completa", expanded=False):
                col_hb1, col_hb2 = st.columns(2)
                with col_hb1:
                    st.markdown("**🏆 Victorias:**")
                    for i, v in enumerate(victorias_ok_sel, 1):
                        st.caption(f"{i}. {v}")

                    st.markdown("**💰 Financiero:**")
                    st.caption(
                        f"Ingreso: ${bit_sel.get('ingreso_actual') or 0:,.0f} · "
                        f"Sup: {s_sup} · Aho: {s_aho} · Ext: {s_ext}"
                    )
                    if bit_sel.get('actividad_cita'):
                        st.caption(f"💑 Cita: {bit_sel['actividad_cita']}")
                    if bit_sel.get('pendientes_soltar'):
                        st.markdown("**📤 Pendientes soltados:**")
                        st.caption(bit_sel['pendientes_soltar'][:200])

                with col_hb2:
                    if bit_sel.get('libro_actual'):
                        st.markdown("**📚 Lectura:**")
                        st.caption(
                            f"{bit_sel['libro_actual']} — "
                            f"pág. {bit_sel.get('pagina_actual') or 0}"
                        )
                    if bit_sel.get('frase_favorita'):
                        st.caption(f"✨ *{bit_sel['frase_favorita'][:150]}*")
                    if bit_sel.get('reflexion_semana'):
                        st.markdown("**💭 Reflexión:**")
                        st.caption(bit_sel['reflexion_semana'][:300])

            # ── Datos reales de esa semana ────────────────────
            devos_sel  = obtener_devocionales_semana(lun_sel, dom_sel)
            dw_sel     = obtener_deepwork_semana(lun_sel, dom_sel)
            salud_sel  = obtener_salud_semana(lun_sel, dom_sel)
            eventos_sel = obtener_eventos_semana(lun_sel, dom_sel)

            dw_comp_sel = len([s for s in dw_sel if s.get('completado') == 1])
            ej_sel = len([s for s in salud_sel if s.get('hizo_ejercicio')])
            prom_e_sel = (
                sum(s.get('nivel_energia') or 0 for s in salud_sel) / len(salud_sel)
                if salud_sel else 0
            )

            st.markdown("**📊 Datos reales de esa semana:**")
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            col_m1.metric("✝️ Devocionales", f"{len(devos_sel)}/7")
            col_m2.metric("⏱️ Deep Work", dw_comp_sel)
            col_m3.metric("💪 Ejercicios", ej_sel)
            col_m4.metric("💑 Eventos", len(eventos_sel))
            col_m5.metric("⚡ Energía", f"{prom_e_sel:.1f}/10" if prom_e_sel else "—")

            st.divider()

            # ── ANÁLISIS IA ───────────────────────────────────
            st.markdown("### 🤖 Análisis IA de esta semana")

            if not api_key_configurada():
                st.warning("⚠️ IA en modo offline")

            # Contexto de la semana seleccionada
            def _ctx_semana_sel():
                vs = "\n".join(
                    f"  {i+1}. {v}"
                    for i,v in enumerate(victorias_ok_sel)
                ) or "  No definidas"

                historial_txt = ""
                otras = [b for b in bitacoras if b['semana_inicio'] != semana_sel][:4]
                if otras:
                    historial_txt = "\nHISTORIAL OTRAS SEMANAS:\n"
                    for b in otras:
                        vs_b = [b.get(f'victoria_{i}','') for i in range(1,4)]
                        historial_txt += (
                            f"  {b['semana_inicio']}: "
                            f"{len([v for v in vs_b if v])} victorias | "
                            f"Semáforo {b.get('semaforo_superv','?')}/"
                            f"{b.get('semaforo_ahorros','?')}/"
                            f"{b.get('semaforo_extras','?')}\n"
                        )
                        if b.get('reflexion_semana'):
                            historial_txt += f"  → {b['reflexion_semana'][:80]}\n"

                return f"""
SEMANA: {semana_sel} — {dom_sel.strftime('%d/%m/%Y')}

VICTORIAS PLANIFICADAS:
{vs}

DATOS REALES:
- Devocionales: {len(devos_sel)}/7
- Deep Work completados: {dw_comp_sel}
- Ejercicios: {ej_sel}
- Energía promedio: {prom_e_sel:.1f}/10

FINANZAS:
- Ingreso: ${bit_sel.get('ingreso_actual') or 0:,.0f}
- Semáforo: Sup {bit_sel.get('semaforo_superv','?')} | Ahorros {bit_sel.get('semaforo_ahorros','?')} | Extras {bit_sel.get('semaforo_extras','?')}

REFLEXIÓN: {bit_sel.get('reflexion_semana') or 'Sin reflexión'}
{historial_txt}"""

            col_ia1, col_ia2 = st.columns(2)

            with col_ia1:
                if st.button("🏆 Victorias vs Resultados",
                              use_container_width=True,
                              key="btn_hist_victorias"):
                    prompt = f"""
Evalúa cada victoria planificada contra los datos reales:
{_ctx_semana_sel()}

Para cada victoria da: ✅ Lograda / ⚠️ Parcial / ❌ No lograda
Explica brevemente por qué. Máximo 120 palabras.
"""
                    with st.spinner("Analizando victorias..."):
                        st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

                if st.button("⚖️ Balance vida-fe-familia-finanzas",
                              use_container_width=True,
                              key="btn_hist_balance"):
                    citas_mat_sel = len([
                        e for e in eventos_sel
                        if e.get('ambito') == 'Matrimonio'
                    ])
                    prompt = f"""
Califica del 1-10 cada área:
✝️ FE: {len(devos_sel)}/7 devocionales
💪 CUERPO: {ej_sel} ejercicios, energía {prom_e_sel:.1f}/10
💑 FAMILIA: {citas_mat_sel} citas matrimoniales
💰 FINANZAS: Sup {bit_sel.get('semaforo_superv','?')} | Aho {bit_sel.get('semaforo_ahorros','?')} | Ext {bit_sel.get('semaforo_extras','?')}

¿Qué área necesitaba más atención esa semana?
Máximo 120 palabras.
"""
                    with st.spinner("Analizando balance..."):
                        st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

            with col_ia2:
                if st.button("🔍 Patrones históricos",
                              use_container_width=True,
                              key="btn_hist_patrones"):
                    if len(bitacoras) < 3:
                        st.warning("Necesitas al menos 3 semanas registradas.")
                    else:
                        prompt = f"""
Detecta patrones comparando esta semana con el historial:
{_ctx_semana_sel()}

1. ¿Qué funciona consistentemente?
2. ¿Qué falla de forma recurrente?
3. ¿Alguna correlación interesante entre áreas?
Máximo 120 palabras.
"""
                        with st.spinner("Detectando patrones..."):
                            st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

                if st.button("🚀 Sugerencias semana siguiente",
                              use_container_width=True,
                              key="btn_hist_siguiente"):
                    semana_sig = lun_sel + timedelta(weeks=1)
                    prompt = f"""
Basándote en esta semana, sugiere para la siguiente ({semana_sig.strftime('%d/%m/%Y')}):
{_ctx_semana_sel()}

1. Las 3 victorias sugeridas para la próxima semana
2. 1 hábito a reforzar y 1 área a mejorar
3. Alerta financiera si aplica
4. Versículo de dirección
Máximo 150 palabras.
"""
                    with st.spinner("Planificando semana siguiente..."):
                        st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

            st.divider()

            # ── Análisis completo ─────────────────────────────
            if st.button("🤖 Análisis completo integrado",
                          use_container_width=True,
                          type="primary",
                          key="btn_hist_completo"):
                prompt = f"""
Análisis ejecutivo completo:
{_ctx_semana_sel()}

Responde en 4 secciones (máx 200 palabras total):
🏆 VICTORIAS: ¿Cuáles se lograron?
🔍 PATRÓN: Una observación del historial
⚖️ BALANCE: Lo más positivo y lo más preocupante
🚀 PRÓXIMA SEMANA: 2 acciones + versículo
"""
                with st.spinner("Generando análisis completo..."):
                    st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

        st.divider()

        # ── Lista de todas las bitácoras ──────────────────────
        st.markdown("### 📋 Todas las semanas")
        for b in bitacoras:
            lun_b = datetime.strptime(b['semana_inicio'], '%Y-%m-%d').date()
            dom_b = lun_b + timedelta(days=6)
            s_sup = SEMAFOROS.get(b.get('semaforo_superv','verde'),'🟢')
            s_aho = SEMAFOROS.get(b.get('semaforo_ahorros','verde'),'🟢')
            s_ext = SEMAFOROS.get(b.get('semaforo_extras','verde'),'🟢')
            vs_ok = [v for v in [b.get(f'victoria_{i}','') for i in range(1,4)] if v]

            st.caption(
                f"📅 {lun_b.strftime('%d/%m')}—{dom_b.strftime('%d/%m/%Y')} · "
                f"💰 {s_sup}{s_aho}{s_ext} · "
                f"🏆 {len(vs_ok)} victorias · "
                f"{'📝 ' + b['reflexion_semana'][:60] + '...' if b.get('reflexion_semana') else '—'}"
            )

st.divider()
st.caption(
    "📅 Agenda · Calendario unificado · "
    "Bitácora semanal · Abrir lunes 18:00"
)