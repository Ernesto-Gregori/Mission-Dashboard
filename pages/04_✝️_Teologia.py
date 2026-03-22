"""
✝️ Bitácora Teológica - Devocionales 05:45 am
"""

import streamlit as st
from datetime import date, datetime, timedelta
import sys
import json  
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
# FUNCIONES — PEDIDOS DE ORACIÓN
# ═══════════════════════════════════════════════════════════════

def agregar_pedido(titulo, descripcion, categoria, urgencia, dias_oracion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pedidos_oracion
                (titulo, descripcion, categoria, urgencia, dias_oracion)
            VALUES (?, ?, ?, ?, ?)
        """, (titulo, descripcion, categoria, urgencia,
              json.dumps(dias_oracion)))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def obtener_pedidos(estado=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if estado:
        cursor.execute("""
            SELECT * FROM pedidos_oracion
            WHERE estado = ?
            ORDER BY urgencia DESC, creado_en DESC
        """, (estado,))
    else:
        cursor.execute("""
            SELECT * FROM pedidos_oracion
            ORDER BY
                CASE estado
                    WHEN 'Activo'     THEN 1
                    WHEN 'En_espera'  THEN 2
                    WHEN 'Respondido' THEN 3
                    WHEN 'Archivado'  THEN 4
                END,
                urgencia DESC,
                creado_en DESC
        """)
    pedidos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return pedidos

def actualizar_estado_pedido(pedido_id, nuevo_estado,
                              nota_respuesta="", fecha_respuesta=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE pedidos_oracion
            SET estado          = ?,
                nota_respuesta  = ?,
                fecha_respuesta = ?,
                actualizado_en  = ?
            WHERE id = ?
        """, (
            nuevo_estado,
            nota_respuesta,
            fecha_respuesta or (
                date.today().isoformat()
                if nuevo_estado == 'Respondido' else None
            ),
            datetime.now().isoformat(),
            pedido_id
        ))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def eliminar_pedido(pedido_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM pedidos_oracion WHERE id = ?",
            (pedido_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def editar_pedido(pedido_id, titulo, descripcion,
                  categoria, urgencia, dias_oracion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE pedidos_oracion
            SET titulo         = ?,
                descripcion    = ?,
                categoria      = ?,
                urgencia       = ?,
                dias_oracion   = ?,
                actualizado_en = ?
            WHERE id = ?
        """, (titulo, descripcion, categoria, urgencia,
              json.dumps(dias_oracion),
              datetime.now().isoformat(), pedido_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

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

tab_hoy, tab_historial, tab_oracion, tab_metodo = st.tabs(["📖 Hoy", "📚 Historial", "🙏 Pedidos de Oración", "📖 Método"])

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
# TAB 3: PEDIDOS DE ORACIÓN
# ═══════════════════════════════════════════════════════════════

with tab_oracion:

    DIAS_SEMANA     = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    CATEGORIAS_ORACION = [
        'Personal', 'Familia', 'Matrimonio',
        'Instituto', 'Ministerio', 'Otros'
    ]
    EMOJIS_CAT = {
        'Personal':   '👤', 'Familia':    '👨‍👩‍👧',
        'Matrimonio': '💑', 'Instituto':  '🏫',
        'Ministerio': '⛪', 'Otros':      '🌐'
    }
    EMOJIS_ESTADO = {
        'Activo': '🔴', 'En_espera': '🟡',
        'Respondido': '✅', 'Archivado': '🗄️'
    }
    URGENCIA_LABELS = {
        1: '⚪ Baja',   2: '🔵 Normal', 3: '🟡 Media',
        4: '🟠 Alta',  5: '🔴 Urgente'
    }

    if 'pedido_editando' not in st.session_state:
        st.session_state.pedido_editando     = None
    if 'mostrar_form_pedido' not in st.session_state:
        st.session_state.mostrar_form_pedido = False

    # ── Header ─────────────────────────────────────────────────
    col_tit, col_btn = st.columns([3, 1])
    with col_tit:
        st.subheader("🙏 Lista de Oración")
        st.caption("Ora por cada pedido después de tu devocional")
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nuevo pedido",
                     use_container_width=True, type="primary"):
            st.session_state.mostrar_form_pedido = True
            st.session_state.pedido_editando     = None

    # ── Métricas ───────────────────────────────────────────────
    todos_pedidos = obtener_pedidos()
    activos       = [p for p in todos_pedidos if p['estado'] == 'Activo']
    en_espera     = [p for p in todos_pedidos if p['estado'] == 'En_espera']
    respondidos   = [p for p in todos_pedidos if p['estado'] == 'Respondido']

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("🔴 Activos",     len(activos))
    col_m2.metric("🟡 En espera",   len(en_espera))
    col_m3.metric("✅ Respondidos", len(respondidos))
    col_m4.metric("📋 Total",       len(todos_pedidos))
    st.divider()

    # ── Helper: widget días ────────────────────────────────────
    def _selector_dias(key_prefix, defaults=None):
        """Retorna lista de días seleccionados [1..7]"""
        defaults = defaults or []
        st.markdown("**📅 Días para orar por este pedido:**")
        cols_d = st.columns(7)
        seleccionados = []
        for i, dia in enumerate(DIAS_SEMANA):
            with cols_d[i]:
                if st.checkbox(dia, key=f"{key_prefix}_d{i}",
                               value=(i + 1) in defaults):
                    seleccionados.append(i + 1)
        return seleccionados

    # ── FORMULARIO: Nuevo pedido ───────────────────────────────
    if st.session_state.mostrar_form_pedido:
        st.markdown("### ➕ Nuevo pedido de oración")
        with st.form("form_nuevo_pedido", clear_on_submit=True):
            titulo_p = st.text_input(
                "Título *",
                placeholder="Ej: Sabiduría para examen final"
            )
            descripcion_p = st.text_area(
                "Descripción / Detalles",
                placeholder="Contexto específico...",
                height=70
            )
            col_cat, col_urg = st.columns(2)
            with col_cat:
                categoria_p = st.selectbox("Categoría", CATEGORIAS_ORACION)
            with col_urg:
                urgencia_p = st.select_slider(
                    "Urgencia", options=[1,2,3,4,5],
                    value=3, format_func=lambda x: URGENCIA_LABELS[x]
                )

            # Días dentro del form
            st.markdown("**📅 Días para orar:**")
            cols_nd = st.columns(7)
            nuevos_dias = []
            for i, dia in enumerate(DIAS_SEMANA):
                with cols_nd[i]:
                    if st.checkbox(dia, key=f"nuevo_dia_{i}",
                                   value=i < 5):
                        nuevos_dias.append(i + 1)

            col_g, col_c = st.columns(2)
            with col_g:
                submit_p = st.form_submit_button(
                    "🙏 Agregar", use_container_width=True, type="primary"
                )
            with col_c:
                cancel_p = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_p:
                st.session_state.mostrar_form_pedido = False
                st.rerun()
            if submit_p:
                if not titulo_p.strip():
                    st.error("⚠️ El título es obligatorio")
                else:
                    agregar_pedido(titulo_p.strip(), descripcion_p,
                                   categoria_p, urgencia_p, nuevos_dias)
                    st.success(f"✅ '{titulo_p}' agregado")
                    st.session_state.mostrar_form_pedido = False
                    st.rerun()

    # ── Filtro ─────────────────────────────────────────────────
    filtro_est = st.segmented_control(
        "Mostrar",
        options=["Todos","Activo","En_espera","Respondido","Archivado"],
        default="Todos", key="filtro_pedidos"
    )
    pedidos_filtrados = (
        todos_pedidos if filtro_est == "Todos"
        else [p for p in todos_pedidos if p['estado'] == filtro_est]
    )

    # ── Lista de pedidos ───────────────────────────────────────
    if not pedidos_filtrados:
        st.info("🙏 No hay pedidos en esta categoría")

    for p in pedidos_filtrados:
        emoji_cat   = EMOJIS_CAT.get(p['categoria'], '🌐')
        emoji_est   = EMOJIS_ESTADO.get(p['estado'], '○')
        urg_label   = URGENCIA_LABELS.get(p['urgencia'], '⚪ Normal')
        es_respond  = p['estado'] == 'Respondido'
        color_borde = {1:'#30363d', 2:'#58a6ff', 3:'#e3b341',
                       4:'#f0883e', 5:'#f85149'}.get(p['urgencia'],'#30363d')
        opacidad    = '0.6' if p['estado'] != 'Activo' else '1'
        estado_txt  = p['estado'].replace('_', ' ')
        desc_txt    = p.get('descripcion') or ''
        nota_txt    = p.get('nota_respuesta') or ''

        try:
            dias_orando = (
                date.today() -
                datetime.strptime(p['fecha_inicio'], '%Y-%m-%d').date()
            ).days
        except Exception:
            dias_orando = 0

        # Días de oración guardados
        try:
            dias_or = json.loads(p.get('dias_oracion') or '[]')
        except Exception:
            dias_or = []
        dias_or_txt = (
            " · ".join(DIAS_SEMANA[d-1] for d in dias_or)
            if dias_or else "Sin días asignados"
        )

        desc_html = (
            f"<div style='color:#8b949e; font-size:0.85rem; "
            f"margin-top:0.4rem;'>{desc_txt}</div>"
        ) if desc_txt else ""

        nota_html = (
            f"<div style='color:#3fb950; font-size:0.8rem; "
            f"margin-top:0.5rem;'>✅ {nota_txt}</div>"
        ) if (es_respond and nota_txt) else ""

        # ── Card + botones en misma fila ───────────────────────
        col_card, col_acc = st.columns([5, 1])

        with col_card:
            st.html(f"""
<div style="background:#161b22;
            border:1px solid #30363d;
            border-left:4px solid {color_borde};
            border-radius:10px;
            padding:0.85rem 1.25rem;
            opacity:{opacidad};">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-weight:700; color:#f0f6fc; font-size:1rem;">
            {emoji_cat} {p['titulo']}
        </span>
        <span style="font-size:0.72rem; color:#8b949e;">
            {emoji_est} {estado_txt} · {urg_label}
        </span>
    </div>
    {desc_html}
    <div style="color:#8b949e; font-size:0.75rem; margin-top:0.5rem;">
        📅 {p['fecha_inicio']}
        &nbsp;·&nbsp; 🙏 {dias_orando} días
        &nbsp;·&nbsp; 🏷️ {p['categoria']}
        &nbsp;·&nbsp; 📆 Ora: {dias_or_txt}
    </div>
    {nota_html}
</div>""")

        # ── Botones compactos sin espacio extra ────────────────
        with col_acc:
            # Usar una sola fila de botones sin markdown entre ellos
            if st.button("✏️", key=f"e_{p['id']}",
                         help="Editar", use_container_width=True):
                st.session_state.pedido_editando     = p['id']
                st.session_state.mostrar_form_pedido = False

            if p['estado'] == 'Activo':
                if st.button("✅", key=f"r_{p['id']}",
                             help="Respondido", use_container_width=True):
                    st.session_state[f'resp_{p["id"]}'] = True

            if p['estado'] != 'Archivado':
                if st.button("🗄️", key=f"a_{p['id']}",
                             help="Archivar", use_container_width=True):
                    actualizar_estado_pedido(p['id'], 'Archivado')
                    st.rerun()

            if st.button("🗑️", key=f"d_{p['id']}",
                         help="Eliminar", use_container_width=True):
                st.session_state[f'del_{p["id"]}'] = True

        # ── Confirmar respondido ───────────────────────────────
        if st.session_state.get(f'resp_{p["id"]}'):
            with st.form(f"fr_{p['id']}"):
                st.markdown(f"#### ✅ ¿Cómo respondió Dios a: *{p['titulo']}*?")
                nota_r = st.text_area("Describe la respuesta", height=70)
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("✅ Confirmar",
                                             use_container_width=True,
                                             type="primary"):
                        actualizar_estado_pedido(p['id'], 'Respondido', nota_r)
                        st.session_state[f'resp_{p["id"]}'] = False
                        st.success("🙌 ¡Gloria a Dios!")
                        st.rerun()
                with c2:
                    if st.form_submit_button("✖ Cancelar",
                                             use_container_width=True):
                        st.session_state[f'resp_{p["id"]}'] = False
                        st.rerun()

        # ── Confirmar eliminación ──────────────────────────────
        if st.session_state.get(f'del_{p["id"]}'):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.warning(f"⚠️ ¿Eliminar *{p['titulo']}*?")
            with c2:
                if st.button("🗑️ Sí", key=f"cd_{p['id']}",
                             use_container_width=True):
                    eliminar_pedido(p['id'])
                    st.session_state[f'del_{p["id"]}'] = False
                    st.rerun()
            with c3:
                if st.button("✖", key=f"cn_{p['id']}",
                             use_container_width=True):
                    st.session_state[f'del_{p["id"]}'] = False
                    st.rerun()

        # ── Edición inline ─────────────────────────────────────
        if st.session_state.pedido_editando == p['id']:
            with st.form(f"fe_{p['id']}"):
                st.markdown(f"#### ✏️ Editando: {p['titulo']}")
                et = st.text_input("Título", value=p['titulo'])
                ed = st.text_area("Descripción",
                                  value=p.get('descripcion') or "",
                                  height=70)
                ec, eu = st.columns(2)
                with ec:
                    ecat = st.selectbox(
                        "Categoría", CATEGORIAS_ORACION,
                        index=CATEGORIAS_ORACION.index(p['categoria'])
                        if p['categoria'] in CATEGORIAS_ORACION else 0
                    )
                with eu:
                    eurg = st.select_slider(
                        "Urgencia", options=[1,2,3,4,5],
                        value=p['urgencia'],
                        format_func=lambda x: URGENCIA_LABELS[x]
                    )

                eest = st.selectbox(
                    "Estado",
                    ['Activo','En_espera','Respondido','Archivado'],
                    index=['Activo','En_espera','Respondido','Archivado']
                    .index(p['estado'])
                    if p['estado'] in
                       ['Activo','En_espera','Respondido','Archivado']
                    else 0
                )

                # Días dentro del form de edición
                st.markdown("**📅 Días para orar:**")
                cols_ed = st.columns(7)
                edit_dias = []
                for i, dia in enumerate(DIAS_SEMANA):
                    with cols_ed[i]:
                        if st.checkbox(dia, key=f"ed_d{i}_{p['id']}",
                                       value=(i+1) in dias_or):
                            edit_dias.append(i + 1)

                s1, s2 = st.columns(2)
                with s1:
                    if st.form_submit_button("💾 Guardar",
                                             use_container_width=True,
                                             type="primary"):
                        if not et.strip():
                            st.error("⚠️ Título obligatorio")
                        else:
                            editar_pedido(p['id'], et.strip(),
                                          ed, ecat, eurg, edit_dias)
                            actualizar_estado_pedido(p['id'], eest)
                            st.session_state.pedido_editando = None
                            st.success("✅ Actualizado")
                            st.rerun()
                with s2:
                    if st.form_submit_button("✖ Cancelar",
                                             use_container_width=True):
                        st.session_state.pedido_editando = None
                        st.rerun()

    # ── Lista para orar ────────────────────────────────────────
    if activos:
        st.divider()
        st.markdown("### 📋 Lista para orar ahora")
        st.caption("Pedidos activos para después de tu devocional")

        dia_hoy     = date.today().weekday() + 1  # 1=Lun..7=Dom
        hoy_activos = []
        otros       = []

        for p in activos:
            try:
                dias_p = json.loads(p.get('dias_oracion') or '[]')
            except Exception:
                dias_p = []
            if dia_hoy in dias_p or not dias_p:
                hoy_activos.append(p)
            else:
                otros.append(p)

        # Pedidos de HOY
        if hoy_activos:
            st.markdown(f"**🗓️ Para orar HOY ({DIAS_SEMANA[dia_hoy-1]}):**")
            for i, p in enumerate(hoy_activos):
                emoji_c = EMOJIS_CAT.get(p['categoria'], '🌐')
                urg_c   = URGENCIA_LABELS.get(p['urgencia'], '')
                desc_c  = f"\n   ↳ {p['descripcion'][:80]}" \
                          if p.get('descripcion') else ""
                st.html(f"""
<div style="background:#0d2818; border-left:3px solid #3fb950;
            border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.4rem;">
    <span style="color:#f0f6fc; font-weight:600;">
        {i+1}. {emoji_c} {p['titulo']}
    </span>
    <span style="color:#8b949e; font-size:0.75rem; margin-left:0.5rem;">
        · {urg_c} · {p['categoria']}
    </span>
    {'<div style="color:#8b949e;font-size:0.8rem;margin-top:0.2rem;">↳ ' +
     p['descripcion'][:80] + '</div>'
     if p.get('descripcion') else ''}
</div>""")

        # Otros días
        if otros:
            with st.expander(
                f"📋 Otros {len(otros)} pedidos (días distintos)"
            ):
                for p in otros:
                    try:
                        dias_p = json.loads(p.get('dias_oracion') or '[]')
                    except Exception:
                        dias_p = []
                    dias_txt = ", ".join(
                        DIAS_SEMANA[d-1] for d in dias_p
                    ) if dias_p else "Sin días"
                    emoji_c  = EMOJIS_CAT.get(p['categoria'], '🌐')
                    st.caption(
                        f"🙏 {emoji_c} **{p['titulo']}** "
                        f"— Ora: {dias_txt}"
                    )

        st.caption(
            f"📊 {len(hoy_activos)} para orar hoy · "
            f"{len(activos)} activos en total"
        )

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