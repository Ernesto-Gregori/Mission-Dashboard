"""
✝️ Bitácora Teológica - Devocionales 05:45 am
"""

import streamlit as st
from datetime import timedelta
import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import ejecutar, ejecutar_cached
from app.ai_client import chat_simple, api_key_configurada, sugerir_lectura_devocional
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    ahora as _ahora,
    iso_ahora,
)

st.set_page_config(
    page_title="Teología | Mission Dashboard",
    page_icon="✝️",
    layout="wide"
)

from app.auth import require_auth
require_auth()
ensure_database()

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
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

DIAS_SEMANA        = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
CATEGORIAS_ORACION = [
    'Personal', 'Familia', 'Matrimonio',
    'Instituto', 'Ministerio', 'Otros'
]
EMOJIS_CAT = {
    'Personal': '👤', 'Familia': '👨‍👩‍👧',
    'Matrimonio': '💑', 'Instituto': '🏫',
    'Ministerio': '⛪', 'Otros': '🌐',
}
EMOJIS_ESTADO = {
    'Activo': '🔴', 'En_espera': '🟡',
    'Respondido': '✅', 'Archivado': '🗄️',
}
URGENCIA_LABELS = {
    1: '⚪ Baja', 2: '🔵 Normal', 3: '🟡 Media',
    4: '🟠 Alta', 5: '🔴 Urgente',
}

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — DEVOCIONALES
# ═══════════════════════════════════════════════════════════════

def guardar_devocional(fecha, pasaje_ref, pasaje_texto, observacion,
                       interpretacion, aplicacion, conexion_inst,
                       conexion_sit, oracion, duracion,
                       version_bib="NVI") -> None:
    """
    FIX CRÍTICO: fecha se convierte a str ISO antes de enviar a Turso.
    Turso/libsql rechaza objetos date nativos de Python → ValueError.
    """
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha

    ejecutar("""
        INSERT OR REPLACE INTO devocionales (
            fecha, pasaje_referencia, pasaje_texto, version_biblia,
            observacion, interpretacion, aplicacion,
            conexion_instituto, conexion_situacion,
            oracion_escrita, duracion_minutos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        fecha_iso,       # ← str, no date object
        str(pasaje_ref or ""),
        str(pasaje_texto or ""),
        str(version_bib or "NVI"),
        str(observacion or ""),
        str(interpretacion or ""),
        str(aplicacion or ""),
        str(conexion_inst or ""),
        str(conexion_sit or ""),
        str(oracion or ""),
        int(duracion or 30),
    ])


def obtener_devocional(fecha) -> dict | None:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    rows = ejecutar(
        "SELECT * FROM devocionales WHERE fecha = ?",
        [fecha_iso], fetchall=True,
    )
    return rows[0] if rows else None


def obtener_devocionales_recientes(limite: int = 7) -> list:
    return ejecutar_cached("""
        SELECT * FROM devocionales ORDER BY fecha DESC LIMIT ?
    """, (limite,)) or []


def calcular_racha() -> int:
    devocionales = obtener_devocionales_recientes(30)
    if not devocionales:
        return 0
    fechas = [
        datetime.strptime(d["fecha"], "%Y-%m-%d").date()
        for d in devocionales
    ]
    fechas.sort(reverse=True)
    racha = 0
    hoy   = _hoy()          # ← zona horaria local
    for i, fecha in enumerate(fechas):
        if fecha == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha


# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — PEDIDOS DE ORACIÓN
# ═══════════════════════════════════════════════════════════════

def agregar_pedido(titulo: str, descripcion: str, categoria: str,
                   urgencia: int, dias_oracion: list) -> int:
    return ejecutar("""
        INSERT INTO pedidos_oracion
            (titulo, descripcion, categoria, urgencia, dias_oracion)
        VALUES (?, ?, ?, ?, ?)
    """, [titulo, descripcion, categoria, urgencia,
          json.dumps(dias_oracion)])


def obtener_pedidos(estado: str = None) -> list:
    if estado:
        return ejecutar("""
            SELECT * FROM pedidos_oracion
            WHERE estado = ?
            ORDER BY urgencia DESC, creado_en DESC
        """, [estado], fetchall=True) or []
    return ejecutar("""
        SELECT * FROM pedidos_oracion
        ORDER BY
            CASE estado
                WHEN 'Activo'     THEN 1
                WHEN 'En_espera'  THEN 2
                WHEN 'Respondido' THEN 3
                WHEN 'Archivado'  THEN 4
            END,
            urgencia DESC, creado_en DESC
    """, fetchall=True) or []


def actualizar_estado_pedido(pedido_id: int, nuevo_estado: str,
                              nota_respuesta: str = "",
                              fecha_respuesta=None) -> None:
    ejecutar("""
        UPDATE pedidos_oracion
        SET estado          = ?,
            nota_respuesta  = ?,
            fecha_respuesta = ?,
            actualizado_en  = ?
        WHERE id = ?
    """, [
        nuevo_estado,
        nota_respuesta,
        fecha_respuesta or (
            _hoy().isoformat()          # ← zona horaria local
            if nuevo_estado == "Respondido" else None
        ),
        iso_ahora(),                    # ← zona horaria local
        pedido_id,
    ])


def eliminar_pedido(pedido_id: int) -> None:
    ejecutar("DELETE FROM pedidos_oracion WHERE id = ?", [pedido_id])


def editar_pedido(pedido_id: int, titulo: str, descripcion: str,
                  categoria: str, urgencia: int,
                  dias_oracion: list) -> None:
    ejecutar("""
        UPDATE pedidos_oracion
        SET titulo         = ?,
            descripcion    = ?,
            categoria      = ?,
            urgencia       = ?,
            dias_oracion   = ?,
            actualizado_en = ?
        WHERE id = ?
    """, [
        titulo, descripcion, categoria, urgencia,
        json.dumps(dias_oracion),
        iso_ahora(),                    # ← zona horaria local
        pedido_id,
    ])


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("✝️ Bitácora Teológica")
st.caption("Devocionales 05:45 am • Método de estudio inductivo")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔥 Tu racha")
    racha_actual = calcular_racha()

    st.markdown(f"""
    <div style="text-align:center;padding:1rem 0;">
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
    if api_key_configurada():
        st.success("🤖 Groq activo")
        tema_ia = st.text_input("Tema para sugerir pasaje", placeholder="Ej: ansiedad, fe…", key="teo_tema_ia")
        if st.button("✨ Sugerir pasaje (Groq)", use_container_width=True):
            with st.spinner("Buscando pasaje..."):
                st.session_state["teo_sugerencia"] = sugerir_lectura_devocional(
                    tema=tema_ia or "disciplina espiritual"
                )
        if st.session_state.get("teo_sugerencia"):
            st.info(st.session_state["teo_sugerencia"])
    else:
        st.caption("🤖 Groq offline — configura GROQ_API_KEY")

    st.divider()

    ayer     = _hoy() - timedelta(days=1)   # ← zona horaria local
    dev_ayer = obtener_devocional(ayer)
    if dev_ayer:
        st.markdown("**📅 Ayer:**")
        st.caption(dev_ayer["pasaje_referencia"])
        with st.expander("Ver reflexión"):
            st.write(
                (dev_ayer["aplicacion"][:100] + "...")
                if dev_ayer["aplicacion"]
                else "Sin aplicación"
            )

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_historial, tab_oracion, tab_metodo = st.tabs([
    "📖 Hoy", "📚 Historial", "🙏 Pedidos de Oración", "📖 Método"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: HOY
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    fecha_hoy            = _hoy()              # ← zona horaria local
    devocional_existente = obtener_devocional(fecha_hoy)

    if devocional_existente:
        st.success(
            f"✅ Devocional de hoy completado: "
            f"**{devocional_existente['pasaje_referencia']}**"
        )
        col_edit, col_ver = st.columns(2)
        with col_edit:
            if st.button("✏️ Editar entrada", use_container_width=True):
                st.session_state["editar_devocional"] = True
                st.rerun()
        with col_ver:
            with st.expander("Ver completo", expanded=True):
                pasaje_texto   = devocional_existente["pasaje_texto"] or ""
                version_biblia = devocional_existente["version_biblia"] or "NVI"

                st.markdown(f"### ✝️ {devocional_existente['pasaje_referencia']}")
                if pasaje_texto.strip():
                    st.info(f"*{pasaje_texto}*\n\n— {version_biblia}")
                else:
                    st.warning("📝 Texto del pasaje no guardado.")

                for campo, label in [
                    ("observacion",        "🔍 Observación"),
                    ("interpretacion",     "💡 Interpretación"),
                    ("aplicacion",         "🎯 Aplicación"),
                    ("conexion_instituto", "🏫 Conexión Instituto"),
                    ("conexion_situacion", "🌍 Situación actual"),
                ]:
                    if devocional_existente.get(campo):
                        with st.expander(
                            label,
                            expanded=campo in ["observacion","interpretacion","aplicacion"]
                        ):
                            st.write(devocional_existente[campo])

                if devocional_existente.get("oracion_escrita"):
                    with st.expander("🙏 Oración"):
                        st.write(f"*{devocional_existente['oracion_escrita']}*")
    else:
        st.info("🌅 Buenos días. Tiempo para tu devocional de las 05:45")

    # ── Formulario nuevo / edición ────────────────────────────
    if not devocional_existente or st.session_state.get("editar_devocional"):
        datos = devocional_existente if st.session_state.get("editar_devocional") else {}
        if st.session_state.get("editar_devocional"):
            st.session_state["editar_devocional"] = False

        with st.form("devocional_form", clear_on_submit=not bool(devocional_existente)):
            st.markdown("### 📝 Tu devocional de hoy")

            col_pasaje, col_version = st.columns([3, 1])
            with col_pasaje:
                pasaje_ref = st.text_input(
                    "Pasaje bíblico *",
                    value=datos.get("pasaje_referencia", ""),
                    placeholder="Ej: Salmo 23:1-6, Juan 3:16"
                )
            with col_version:
                versiones   = ["NVI", "RVR1960", "NLT", "ESV", "Otra"]
                version_bib = st.selectbox(
                    "Versión", versiones,
                    index=versiones.index(datos.get("version_biblia", "NVI"))
                    if datos.get("version_biblia") in versiones else 0
                )

            pasaje_texto = st.text_area(
                "Texto del pasaje (opcional)",
                value=datos.get("pasaje_texto", ""),
                height=100,
                placeholder="El Señor es mi pastor, nada me falta..."
            )

            st.divider()
            st.markdown("**Método de estudio inductivo**")

            observacion = st.text_area(
                "🔍 Observación: ¿Qué dice el texto?",
                value=datos.get("observacion", ""), height=80
            )
            interpretacion = st.text_area(
                "💡 Interpretación: ¿Qué significa?",
                value=datos.get("interpretacion", ""), height=80
            )
            aplicacion = st.text_area(
                "🎯 Aplicación: ¿Cómo aplica a mi vida hoy?",
                value=datos.get("aplicacion", ""), height=80
            )

            st.divider()
            st.markdown("**Conexiones personales**")
            col_inst, col_sit = st.columns(2)
            with col_inst:
                conexion_inst = st.text_area(
                    "🏫 Instituto: ¿Relación con clases actuales?",
                    value=datos.get("conexion_instituto", ""),
                    height=60, placeholder="Ej: Hermenéutica..."
                )
            with col_sit:
                conexion_sit = st.text_area(
                    "🌍 Situación actual: ¿Qué estoy viviendo?",
                    value=datos.get("conexion_situacion", ""),
                    height=60, placeholder="Ej: Preparando examen..."
                )

            oracion = st.text_area(
                "🙏 Oración",
                value=datos.get("oracion_escrita", ""), height=100
            )

            col_dur, col_guardar = st.columns([1, 2])
            with col_dur:
                duracion = st.number_input(
                    "Minutos", min_value=5, max_value=120,
                    value=int(datos.get("duracion_minutos") or 30)
                )
            with col_guardar:
                submitted = st.form_submit_button(
                    "💾 Guardar devocional",
                    use_container_width=True, type="primary"
                )

            if submitted:
                if not pasaje_ref.strip():
                    st.error("⚠️ El pasaje bíblico es obligatorio")
                else:
                    guardar_devocional(
                        fecha_hoy,      # str ISO via fecha_iso interno
                        pasaje_ref, pasaje_texto,
                        observacion, interpretacion, aplicacion,
                        conexion_inst, conexion_sit, oracion,
                        duracion, version_bib
                    )
                    st.success(
                        f"✅ Devocional guardado. "
                        f"¡Día {racha_actual + 1} completado!"
                    )
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
            fecha_dev = datetime.strptime(
                dev["fecha"], "%Y-%m-%d"
            ).strftime("%d/%m/%Y")

            col_fecha, col_contenido = st.columns([1, 4])
            with col_fecha:
                st.markdown(f"""
<div style="text-align:center;padding:0.5rem;">
    <div style="font-size:0.875rem;color:#8b949e;">{fecha_dev}</div>
    <div style="font-size:1.5rem;">✅</div>
</div>
                """, unsafe_allow_html=True)
            with col_contenido:
                aplicacion_txt     = dev.get("aplicacion") or ""
                aplicacion_preview = (
                    aplicacion_txt[:120] + "..."
                    if len(aplicacion_txt) > 120
                    else aplicacion_txt or "Sin aplicación registrada"
                )
                st.markdown(f"""
<div class="devocional-card" style="margin-bottom:0.5rem;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="color:#a371f7;font-weight:600;">
            {dev['pasaje_referencia']}
        </span>
        <span style="font-size:0.75rem;color:#8b949e;">
            {dev['duracion_minutos']} min
        </span>
    </div>
    <div style="color:#8b949e;font-size:0.875rem;margin-top:0.25rem;">
        {aplicacion_preview}
    </div>
</div>
                """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# TAB 3: PEDIDOS DE ORACIÓN
# ═══════════════════════════════════════════════════════════════

with tab_oracion:

    if "pedido_editando" not in st.session_state:
        st.session_state.pedido_editando     = None
    if "mostrar_form_pedido" not in st.session_state:
        st.session_state.mostrar_form_pedido = False

    col_tit, col_btn = st.columns([3, 1])
    with col_tit:
        st.subheader("🙏 Lista de Oración")
        st.caption("Ora por cada pedido después de tu devocional")
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nuevo pedido", use_container_width=True, type="primary"):
            st.session_state.mostrar_form_pedido = True
            st.session_state.pedido_editando     = None

    todos_pedidos = obtener_pedidos()
    activos       = [p for p in todos_pedidos if p["estado"] == "Activo"]
    en_espera     = [p for p in todos_pedidos if p["estado"] == "En_espera"]
    respondidos   = [p for p in todos_pedidos if p["estado"] == "Respondido"]

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("🔴 Activos",     len(activos))
    col_m2.metric("🟡 En espera",   len(en_espera))
    col_m3.metric("✅ Respondidos", len(respondidos))
    col_m4.metric("📋 Total",       len(todos_pedidos))
    st.divider()

    # ── Formulario: Nuevo pedido ──────────────────────────────
    if st.session_state.mostrar_form_pedido:
        st.markdown("### ➕ Nuevo pedido de oración")
        with st.form("form_nuevo_pedido", clear_on_submit=True):
            titulo_p      = st.text_input("Título *",
                placeholder="Ej: Sabiduría para examen final")
            descripcion_p = st.text_area("Descripción / Detalles", height=70,
                placeholder="Contexto específico...")
            col_cat, col_urg = st.columns(2)
            with col_cat:
                categoria_p = st.selectbox("Categoría", CATEGORIAS_ORACION)
            with col_urg:
                urgencia_p = st.select_slider(
                    "Urgencia", options=[1, 2, 3, 4, 5],
                    value=3, format_func=lambda x: URGENCIA_LABELS[x]
                )

            st.markdown("**📅 Días para orar:**")
            cols_nd     = st.columns(7)
            nuevos_dias = []
            for i, dia in enumerate(DIAS_SEMANA):
                with cols_nd[i]:
                    if st.checkbox(dia, key=f"nuevo_dia_{i}", value=i < 5):
                        nuevos_dias.append(i + 1)

            col_g, col_c = st.columns(2)
            with col_g:
                submit_p = st.form_submit_button(
                    "🙏 Agregar", use_container_width=True, type="primary"
                )
            with col_c:
                cancel_p = st.form_submit_button("✖ Cancelar", use_container_width=True)

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

    # ── Filtro ────────────────────────────────────────────────
    filtro_est = st.segmented_control(
        "Mostrar",
        options=["Todos","Activo","En_espera","Respondido","Archivado"],
        default="Todos", key="filtro_pedidos"
    )
    pedidos_filtrados = (
        todos_pedidos if filtro_est == "Todos"
        else [p for p in todos_pedidos if p["estado"] == filtro_est]
    )

    if not pedidos_filtrados:
        st.info("🙏 No hay pedidos en esta categoría")

    hoy_local = _hoy()   # ← una sola vez

    for p in pedidos_filtrados:
        emoji_cat   = EMOJIS_CAT.get(p["categoria"], "🌐")
        emoji_est   = EMOJIS_ESTADO.get(p["estado"], "○")
        urg_label   = URGENCIA_LABELS.get(p["urgencia"], "⚪ Normal")
        es_respond  = p["estado"] == "Respondido"
        color_borde = {1:"#30363d",2:"#58a6ff",3:"#e3b341",
                       4:"#f0883e",5:"#f85149"}.get(p["urgencia"],"#30363d")
        opacidad    = "0.6" if p["estado"] != "Activo" else "1"
        estado_txt  = p["estado"].replace("_"," ")

        try:
            dias_orando = (
                hoy_local -                             # ← zona horaria local
                datetime.strptime(p["fecha_inicio"], "%Y-%m-%d").date()
            ).days
        except Exception:
            dias_orando = 0

        try:
            dias_or = json.loads(p.get("dias_oracion") or "[]")
        except Exception:
            dias_or = []
        dias_or_txt = (
            " · ".join(DIAS_SEMANA[d - 1] for d in dias_or)
            if dias_or else "Sin días asignados"
        )

        desc_html = (
            f"<div style='color:#8b949e;font-size:0.85rem;"
            f"margin-top:0.4rem;'>{p.get('descripcion','')}</div>"
        ) if p.get("descripcion") else ""

        nota_txt  = p.get("nota_respuesta") or ""
        nota_html = (
            f"<div style='color:#3fb950;font-size:0.8rem;"
            f"margin-top:0.5rem;'>✅ {nota_txt}</div>"
        ) if (es_respond and nota_txt) else ""

        col_card, col_acc = st.columns([5, 1])
        with col_card:
            st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-left:4px solid {color_borde};border-radius:10px;
            padding:0.85rem 1.25rem;opacity:{opacidad};">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:700;color:#f0f6fc;font-size:1rem;">
            {emoji_cat} {p['titulo']}
        </span>
        <span style="font-size:0.72rem;color:#8b949e;">
            {emoji_est} {estado_txt} · {urg_label}
        </span>
    </div>
    {desc_html}
    <div style="color:#8b949e;font-size:0.75rem;margin-top:0.5rem;">
        📅 {p['fecha_inicio']} &nbsp;·&nbsp; 🙏 {dias_orando} días
        &nbsp;·&nbsp; 🏷️ {p['categoria']}
        &nbsp;·&nbsp; 📆 Ora: {dias_or_txt}
    </div>
    {nota_html}
</div>""")

        with col_acc:
            if st.button("✏️", key=f"e_{p['id']}",
                         help="Editar", use_container_width=True):
                st.session_state.pedido_editando     = p["id"]
                st.session_state.mostrar_form_pedido = False

            if p["estado"] == "Activo":
                if st.button("✅", key=f"r_{p['id']}",
                             help="Respondido", use_container_width=True):
                    st.session_state[f"resp_{p['id']}"] = True

            if p["estado"] != "Archivado":
                if st.button("🗄️", key=f"a_{p['id']}",
                             help="Archivar", use_container_width=True):
                    actualizar_estado_pedido(p["id"], "Archivado")
                    st.rerun()

            if st.button("🗑️", key=f"d_{p['id']}",
                         help="Eliminar", use_container_width=True):
                st.session_state[f"del_{p['id']}"] = True

        # ── Confirmar respondido ──────────────────────────────
        if st.session_state.get(f"resp_{p['id']}"):
            with st.form(f"fr_{p['id']}"):
                st.markdown(f"#### ✅ ¿Cómo respondió Dios a: *{p['titulo']}*?")
                nota_r = st.text_area("Describe la respuesta", height=70)
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("✅ Confirmar",
                                             use_container_width=True,
                                             type="primary"):
                        actualizar_estado_pedido(p["id"], "Respondido", nota_r)
                        st.session_state[f"resp_{p['id']}"] = False
                        st.success("🙌 ¡Gloria a Dios!")
                        st.rerun()
                with c2:
                    if st.form_submit_button("✖ Cancelar", use_container_width=True):
                        st.session_state[f"resp_{p['id']}"] = False
                        st.rerun()

        # ── Confirmar eliminación ─────────────────────────────
        if st.session_state.get(f"del_{p['id']}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.warning(f"⚠️ ¿Eliminar *{p['titulo']}*?")
            with c2:
                if st.button("🗑️ Sí", key=f"cd_{p['id']}", use_container_width=True):
                    eliminar_pedido(p["id"])
                    st.session_state[f"del_{p['id']}"] = False
                    st.rerun()
            with c3:
                if st.button("✖", key=f"cn_{p['id']}", use_container_width=True):
                    st.session_state[f"del_{p['id']}"] = False
                    st.rerun()

        # ── Edición inline ────────────────────────────────────
        if st.session_state.pedido_editando == p["id"]:
            with st.form(f"fe_{p['id']}"):
                st.markdown(f"#### ✏️ Editando: {p['titulo']}")
                et = st.text_input("Título", value=p["titulo"])
                ed = st.text_area("Descripción",
                                  value=p.get("descripcion") or "", height=70)
                ec, eu = st.columns(2)
                with ec:
                    ecat = st.selectbox(
                        "Categoría", CATEGORIAS_ORACION,
                        index=CATEGORIAS_ORACION.index(p["categoria"])
                        if p["categoria"] in CATEGORIAS_ORACION else 0
                    )
                with eu:
                    eurg = st.select_slider(
                        "Urgencia", options=[1, 2, 3, 4, 5],
                        value=p["urgencia"],
                        format_func=lambda x: URGENCIA_LABELS[x]
                    )

                eest = st.selectbox(
                    "Estado",
                    ["Activo","En_espera","Respondido","Archivado"],
                    index=["Activo","En_espera","Respondido","Archivado"]
                    .index(p["estado"])
                    if p["estado"] in
                       ["Activo","En_espera","Respondido","Archivado"] else 0
                )

                st.markdown("**📅 Días para orar:**")
                cols_ed   = st.columns(7)
                edit_dias = []
                for i, dia in enumerate(DIAS_SEMANA):
                    with cols_ed[i]:
                        if st.checkbox(dia, key=f"ed_d{i}_{p['id']}",
                                       value=(i + 1) in dias_or):
                            edit_dias.append(i + 1)

                s1, s2 = st.columns(2)
                with s1:
                    if st.form_submit_button("💾 Guardar",
                                             use_container_width=True,
                                             type="primary"):
                        if not et.strip():
                            st.error("⚠️ Título obligatorio")
                        else:
                            editar_pedido(p["id"], et.strip(), ed,
                                          ecat, eurg, edit_dias)
                            actualizar_estado_pedido(p["id"], eest)
                            st.session_state.pedido_editando = None
                            st.success("✅ Actualizado")
                            st.rerun()
                with s2:
                    if st.form_submit_button("✖ Cancelar", use_container_width=True):
                        st.session_state.pedido_editando = None
                        st.rerun()

    # ── Lista para orar hoy ───────────────────────────────────
    if activos:
        st.divider()
        st.markdown("### 📋 Lista para orar ahora")
        st.caption("Pedidos activos para después de tu devocional")

        dia_hoy    = hoy_local.weekday() + 1   # ← zona horaria local
        hoy_active = []
        otros      = []

        for p in activos:
            try:
                dias_p = json.loads(p.get("dias_oracion") or "[]")
            except Exception:
                dias_p = []
            if dia_hoy in dias_p or not dias_p:
                hoy_active.append(p)
            else:
                otros.append(p)

        if hoy_active:
            st.markdown(f"**🗓️ Para orar HOY ({DIAS_SEMANA[dia_hoy-1]}):**")
            for i, p in enumerate(hoy_active):
                emoji_c  = EMOJIS_CAT.get(p["categoria"], "🌐")
                urg_c    = URGENCIA_LABELS.get(p["urgencia"], "")
                desc_div = (
                    f'<div style="color:#8b949e;font-size:0.8rem;'
                    f'margin-top:0.2rem;">↳ {p["descripcion"][:80]}</div>'
                    if p.get("descripcion") else ""
                )
                st.html(f"""
<div style="background:#0d2818;border-left:3px solid #3fb950;
            border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.4rem;">
    <span style="color:#f0f6fc;font-weight:600;">
        {i+1}. {emoji_c} {p['titulo']}
    </span>
    <span style="color:#8b949e;font-size:0.75rem;margin-left:0.5rem;">
        · {urg_c} · {p['categoria']}
    </span>
    {desc_div}
</div>""")

        if otros:
            with st.expander(f"📋 Otros {len(otros)} pedidos (días distintos)"):
                for p in otros:
                    try:
                        dias_p = json.loads(p.get("dias_oracion") or "[]")
                    except Exception:
                        dias_p = []
                    dias_txt = (
                        ", ".join(DIAS_SEMANA[d - 1] for d in dias_p)
                        if dias_p else "Sin días"
                    )
                    emoji_c = EMOJIS_CAT.get(p["categoria"], "🌐")
                    st.caption(f"🙏 {emoji_c} **{p['titulo']}** — Ora: {dias_txt}")

        st.caption(
            f"📊 {len(hoy_active)} para orar hoy · "
            f"{len(activos)} activos en total"
        )

# ═══════════════════════════════════════════════════════════════
# TAB 4: MÉTODO
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
    st.caption("Basado en el método inductivo de Kay Arthur y J.O. Sanders")

st.divider()
st.caption("✝️ Bitácora Teológica • Devocionales 05:45 am")