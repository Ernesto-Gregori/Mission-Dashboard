"""
🧪 Sandbox - Laboratorio multi-dominio de ideas, snippets y sesiones
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

st.set_page_config(
    page_title="Sandbox | Mission Dashboard",
    page_icon="🧪",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CONSTANTES MULTI-DOMINIO
# ═══════════════════════════════════════════════════════════════

DOMINIOS = [
    "Estudio", "Programacion", "Trabajo", "Familia",
    "Personal", "Ministerio", "Matrimonio", "Otros"
]

EMOJIS_DOMINIO = {
    "Estudio":      "📚",
    "Programacion": "💻",
    "Trabajo":      "💼",
    "Familia":      "👨‍👩‍👧",
    "Personal":     "👤",
    "Ministerio":   "⛪",
    "Matrimonio":   "💑",
    "Otros":        "🌐"
}

CATEGORIAS_DEFAULT_POR_DOMINIO = {
    "Estudio":      ["Teología", "Hermenéutica", "Idiomas",
                     "Filosofía", "Historia", "Investigación"],
    "Programacion": ["Script", "Web_App", "Mobile", "Data",
                     "DevOps", "IA", "Automatización"],
    "Trabajo":      ["Proyecto", "Proceso", "Mejora",
                     "Reunión", "Propuesta"],
    "Familia":      ["Salida", "Vacaciones", "Actividad",
                     "Conversación", "Celebración", "Apoyo"],
    "Personal":     ["Hábito", "Meta", "Reflexión",
                     "Lectura", "Salud"],
    "Ministerio":   ["Predicación", "Discipulado", "Servicio",
                     "Oración", "Estudio Bíblico"],
    "Matrimonio":   ["Cita", "Conversación", "Plan",
                     "Mejora", "Celebración", "Vacaciones"],
    "Otros":        ["General", "Idea", "Proyecto"]
}

def obtener_categorias_dominio(dominio: str) -> list:
    """Combina defaults con categorías ya usadas en BD."""
    defaults = CATEGORIAS_DEFAULT_POR_DOMINIO.get(dominio, ["General"])
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT categoria FROM sandbox_ideas
            WHERE dominio = ? AND categoria IS NOT NULL
            ORDER BY categoria
        """, (dominio,))
        en_bd = [row[0] for row in cursor.fetchall()]
        conn.close()
        # Unir sin duplicar, manteniendo orden
        todos = list(dict.fromkeys(defaults + en_bd))
        return todos
    except Exception:
        return defaults

ESTADOS_IDEA = [
    "Idea", "Investigando", "En_proceso",
    "Completado", "Pausado", "Abandonado"
]

COLORES_ESTADO = {
    "Idea":         "#8b949e",
    "Investigando": "#58a6ff",
    "En_proceso":   "#e3b341",
    "Completado":   "#3fb950",
    "Pausado":      "#f0883e",
    "Abandonado":   "#f85149"
}

LENGUAJES = [
    "Python", "JavaScript", "TypeScript", "HTML_CSS",
    "SQL", "Bash", "Markdown", "Otro"
]

EMOJIS_LANG = {
    "Python": "🐍", "JavaScript": "⚡", "TypeScript": "📘",
    "HTML_CSS": "🎨", "SQL": "🗄️", "Bash": "💻",
    "Markdown": "📝", "Otro": "🔧"
}

SYSTEM_MENTOR = """Eres un mentor versátil y sabio para un estudiante cristiano de teología 
que también programa. Puedes orientar en:
- Programación (Python, web, scripts, IA)
- Estudio académico (teología, hermenéutica, investigación)
- Vida personal (hábitos, metas, disciplina)
- Familia y matrimonio (comunicación, planes, relaciones)
- Ministerio (predicación, discipulado, servicio)
- Trabajo y proyectos (planificación, ejecución)
Eres práctico, alentador y sabio. Máximo 150 palabras por respuesta."""

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — IDEAS
# ═══════════════════════════════════════════════════════════════

def obtener_ideas(estado=None, dominio=None, busqueda=""):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query  = "SELECT * FROM sandbox_ideas WHERE 1=1"
    params = []
    if estado:
        query += " AND estado = ?"
        params.append(estado)
    if dominio:
        query += " AND dominio = ?"
        params.append(dominio)
    if busqueda:
        query += " AND (titulo LIKE ? OR descripcion LIKE ? OR etiquetas LIKE ?)"
        params.extend([f"%{busqueda}%"] * 3)
    query += " ORDER BY prioridad DESC, motivacion DESC, creado_en DESC"
    cursor.execute(query, params)
    ideas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return ideas

def guardar_idea(titulo, descripcion, dominio, categoria,
                 etiquetas, prioridad, motivacion, notas=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sandbox_ideas
                (titulo, descripcion, dominio, categoria,
                 etiquetas, prioridad, motivacion, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (titulo, descripcion, dominio, categoria,
              json.dumps(etiquetas), prioridad, motivacion, notas))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def actualizar_idea(idea_id, titulo, descripcion, dominio,
                    categoria, etiquetas, estado, prioridad,
                    motivacion, notas):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE sandbox_ideas
            SET titulo=?, descripcion=?, dominio=?, categoria=?,
                etiquetas=?, estado=?, prioridad=?,
                motivacion=?, notas=?, actualizado_en=?
            WHERE id=?
        """, (titulo, descripcion, dominio, categoria,
              json.dumps(etiquetas), estado, prioridad,
              motivacion, notas,
              datetime.now().isoformat(), idea_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def eliminar_idea(idea_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM sandbox_ideas WHERE id=?", (idea_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — SNIPPETS
# ═══════════════════════════════════════════════════════════════

def obtener_snippets(lenguaje=None, dominio=None, busqueda=""):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query  = "SELECT * FROM sandbox_snippets WHERE 1=1"
    params = []
    if lenguaje:
        query += " AND lenguaje = ?"
        params.append(lenguaje)
    if dominio:
        query += " AND dominio = ?"
        params.append(dominio)
    if busqueda:
        query += " AND (titulo LIKE ? OR descripcion LIKE ? OR tags LIKE ?)"
        params.extend([f"%{busqueda}%"] * 3)
    query += " ORDER BY veces_usado DESC, creado_en DESC"
    cursor.execute(query, params)
    snippets = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return snippets

def guardar_snippet(titulo, descripcion, lenguaje,
                    codigo, tags, dominio):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sandbox_snippets
                (titulo, descripcion, lenguaje, codigo, tags, dominio)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (titulo, descripcion, lenguaje,
              codigo, json.dumps(tags), dominio))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def actualizar_snippet(snip_id, titulo, descripcion,
                       lenguaje, codigo, tags, dominio):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE sandbox_snippets
            SET titulo=?, descripcion=?, lenguaje=?,
                codigo=?, tags=?, dominio=?, actualizado_en=?
            WHERE id=?
        """, (titulo, descripcion, lenguaje, codigo,
              json.dumps(tags), dominio,
              datetime.now().isoformat(), snip_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def eliminar_snippet(snip_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM sandbox_snippets WHERE id=?", (snip_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def incrementar_uso(snip_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE sandbox_snippets
            SET veces_usado = veces_usado + 1
            WHERE id=?
        """, (snip_id,))
        conn.commit()
    finally:
        conn.close()

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — SESIONES
# ═══════════════════════════════════════════════════════════════

def guardar_sesion(fecha, duracion, tipo, dominio,
                   proyecto_id, descripcion, codigo, satisfaccion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sandbox_sesiones
                (fecha, duracion_minutos, tipo_actividad, dominio,
                 proyecto_id, descripcion, codigo_producido, satisfaccion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha, duracion, tipo, dominio,
              proyecto_id, descripcion, codigo, satisfaccion))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def obtener_sesiones_recientes(limite=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ss.*, si.titulo as proyecto_titulo
        FROM sandbox_sesiones ss
        LEFT JOIN sandbox_ideas si ON ss.proyecto_id = si.id
        ORDER BY ss.fecha DESC, ss.creado_en DESC
        LIMIT ?
    """, (limite,))
    sesiones = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sesiones

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("🧪 Sandbox")
st.caption("Laboratorio multi-dominio • Ideas · Snippets · Sesiones · Mentor IA")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Tu laboratorio")

    todas_ideas    = obtener_ideas()
    todos_snippets = obtener_snippets()

    activas     = len([i for i in todas_ideas
                       if i['estado'] not in ['Completado','Abandonado']])
    completadas = len([i for i in todas_ideas
                       if i['estado'] == 'Completado'])

    col1, col2 = st.columns(2)
    col1.metric("Ideas activas",   activas)
    col2.metric("Completadas",     completadas)
    st.metric("Snippets totales",  len(todos_snippets))

    # Distribución por dominio
    if todas_ideas:
        st.divider()
        st.caption("📊 Ideas por dominio")
        por_dominio = {}
        for i in todas_ideas:
            d = i.get('dominio', 'Otros')
            por_dominio[d] = por_dominio.get(d, 0) + 1
        for dom, cnt in sorted(por_dominio.items(),
                               key=lambda x: -x[1]):
            emoji = EMOJIS_DOMINIO.get(dom, '🌐')
            st.caption(f"{emoji} {dom}: {cnt}")

    # Snippets más usados
    if todos_snippets:
        st.divider()
        st.caption("🔥 Snippets más usados")
        top = sorted(todos_snippets,
                     key=lambda x: x['veces_usado'], reverse=True)[:3]
        for s in top:
            st.caption(f"• **{s['titulo']}** ({s['veces_usado']}x)")

    st.divider()
    if api_key_configurada():
        st.success("🤖 Mentor IA activo")
    else:
        st.caption("🤖 Mentor IA offline")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_ideas, tab_snippets, tab_sesion, tab_ia = st.tabs([
    "💡 Ideas", "🧩 Snippets", "⏱️ Sesiones", "🤖 Mentor IA"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: IDEAS MULTI-DOMINIO
# ═══════════════════════════════════════════════════════════════

with tab_ideas:

    # ── Session state ──────────────────────────────────────────
    if 'idea_editando'      not in st.session_state:
        st.session_state.idea_editando      = None
    if 'mostrar_form_idea'  not in st.session_state:
        st.session_state.mostrar_form_idea  = False

    # ── Filtros + botón nuevo ──────────────────────────────────
    col_f1, col_f2, col_f3, col_f4, col_btn = st.columns([2,2,2,2,1])
    with col_f1:
        f_dominio = st.selectbox(
            "Dominio", ["Todos"] + DOMINIOS, key="f_dom_ideas"
        )
    with col_f2:
        f_estado = st.selectbox(
            "Estado", ["Todos"] + ESTADOS_IDEA, key="f_est_ideas"
        )
    with col_f3:
        f_busqueda = st.text_input(
            "Buscar", placeholder="Título, descripción...",
            key="f_bus_ideas"
        )
    with col_f4:
        f_orden = st.selectbox(
            "Ordenar por",
            ["Prioridad", "Motivación", "Más recientes"],
            key="f_ord_ideas"
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nueva", use_container_width=True,
                     type="primary"):
            st.session_state.mostrar_form_idea = True
            st.session_state.idea_editando     = None

    # ── FORMULARIO: Nueva idea ─────────────────────────────────
    if st.session_state.mostrar_form_idea:
        st.divider()
        st.markdown("### ➕ Nueva idea")

        # ── Dominio FUERA del form para reactividad ────────────
        n_dominio = st.selectbox(
            "Dominio *", DOMINIOS, key="n_dominio_fuera"
        )

        # Categorías se actualizan al cambiar dominio
        cats_disponibles = obtener_categorias_dominio(n_dominio)

        col_cat, col_cat_new = st.columns([2, 1])
        with col_cat:
            n_cat_sel = st.selectbox(
                "Categoría",
                options=cats_disponibles + ["✏️ Nueva categoría..."],
                key=f"n_cat_sel_{n_dominio}"  # ← key cambia con dominio
            )
        with col_cat_new:
            n_cat_custom = st.text_input(
                "Nueva categoría",
                placeholder="Ej: Vacaciones",
                key="n_cat_custom"
            )

        # Resolver categoría final ANTES del form
        n_categoria = (
            n_cat_custom.strip()
            if n_cat_sel == "✏️ Nueva categoría..."
               and n_cat_custom.strip()
            else n_cat_sel
            if n_cat_sel != "✏️ Nueva categoría..."
            else ""
        )

        # ── Form solo para el resto de campos ─────────────────
        with st.form("form_nueva_idea", clear_on_submit=True):
            col_n1, col_n2 = st.columns(2)
            with col_n1:
                n_titulo = st.text_input(
                    "Título *",
                    placeholder="Ej: Salida familiar al lago"
                )
            with col_n2:
                n_estado = st.selectbox(
                    "Estado inicial", ESTADOS_IDEA
                )

            n_desc = st.text_area(
                "Descripción",
                placeholder="¿Qué es esta idea? ¿Por qué te interesa?",
                height=80
            )

            col_n3, col_n4, col_n5 = st.columns(3)
            with col_n3:
                n_prioridad = st.select_slider(
                    "Prioridad", options=[1,2,3,4,5], value=3,
                    format_func=lambda x: {
                        1:'⚪ Baja',   2:'🔵 Normal',
                        3:'🟡 Media',  4:'🟠 Alta',
                        5:'🔴 Urgente'
                    }[x]
                )
            with col_n4:
                n_motivacion = st.slider("Motivación", 1, 10, 7)
            with col_n5:
                n_etiquetas_str = st.text_input(
                    "Etiquetas (comas)",
                    placeholder="Ej: urgente, largo plazo"
                )

            n_notas = st.text_area(
                "Notas adicionales",
                placeholder="Recursos, pasos iniciales...",
                height=60
            )

            col_sg, col_sc = st.columns(2)
            with col_sg:
                submit_idea = st.form_submit_button(
                    "💾 Guardar idea",
                    use_container_width=True,
                    type="primary"
                )
            with col_sc:
                cancel_idea = st.form_submit_button(
                    "✖ Cancelar",
                    use_container_width=True
                )

            if cancel_idea:
                st.session_state.mostrar_form_idea = False
                st.rerun()

            if submit_idea:
                if not n_titulo.strip():
                    st.error("⚠️ El título es obligatorio")
                elif n_cat_sel == "✏️ Nueva categoría..." \
                        and not n_cat_custom.strip():
                    st.error("⚠️ Escribe el nombre de la nueva categoría")
                else:
                    tags = [
                        t.strip() for t in
                        n_etiquetas_str.split(',') if t.strip()
                    ]
                    guardar_idea(
                        n_titulo.strip(), n_desc,
                        n_dominio,        # ← viene de fuera del form
                        n_categoria,      # ← viene de fuera del form
                        tags, n_prioridad,
                        n_motivacion, n_notas
                    )
                    st.success(f"✅ '{n_titulo}' guardada")
                    st.session_state.mostrar_form_idea = False
                    st.rerun()

    st.divider()

    # ── Lista de ideas ─────────────────────────────────────────
    dom_f  = None if f_dominio == "Todos" else f_dominio
    est_f  = None if f_estado  == "Todos" else f_estado

    ideas = obtener_ideas(est_f, dom_f, f_busqueda)

    # Ordenar
    if f_orden == "Motivación":
        ideas.sort(key=lambda x: x['motivacion'], reverse=True)
    elif f_orden == "Más recientes":
        ideas.sort(key=lambda x: x['creado_en'], reverse=True)

    if not ideas:
        st.info("📝 No hay ideas con estos filtros. ¡Agrega la primera!")
    else:
        st.caption(f"**{len(ideas)} ideas encontradas**")

        for idea in ideas:
            emoji_dom   = EMOJIS_DOMINIO.get(idea.get('dominio','Otros'), '🌐')
            color_est   = COLORES_ESTADO.get(idea['estado'], '#8b949e')
            estado_txt  = idea['estado'].replace('_', ' ')
            prioridad   = idea.get('prioridad', 3)
            motivacion  = idea.get('motivacion', 5)

            try:
                etiquetas = json.loads(idea.get('etiquetas') or '[]')
            except Exception:
                etiquetas = []

            # Badges de etiquetas
            badges_html = " ".join(
                f"<span style='background:#21262d; color:#58a6ff; "
                f"border:1px solid #30363d; border-radius:12px; "
                f"padding:0.1rem 0.5rem; font-size:0.7rem;'>"
                f"{tag}</span>"
                for tag in etiquetas[:5]
            )

            desc_txt  = (idea.get('descripcion') or '')[:120]
            dom_txt   = idea.get('dominio', 'Otros')
            cat_txt   = idea.get('categoria', '')
            notas_txt = idea.get('notas', '') or ''

            col_card, col_acc = st.columns([5, 1])

            with col_card:
                st.html(f"""
<div style="background:#161b22; border:1px solid #30363d;
            border-left:4px solid {color_est};
            border-radius:10px; padding:0.85rem 1.25rem;
            margin-bottom:0.4rem;">
    <div style="display:flex; justify-content:space-between;
                align-items:center;">
        <span style="font-weight:700; color:#f0f6fc; font-size:1rem;">
            {emoji_dom} {idea['titulo']}
        </span>
        <span style="font-size:0.72rem; color:#8b949e;">
            <span style="color:{color_est};">● {estado_txt}</span>
            &nbsp;·&nbsp; ⭐ {prioridad}/5
            &nbsp;·&nbsp; 💪 {motivacion}/10
        </span>
    </div>
    <div style="color:#8b949e; font-size:0.78rem; margin-top:0.25rem;">
        {emoji_dom} {dom_txt}
        {f'&nbsp;·&nbsp; {cat_txt}' if cat_txt else ''}
    </div>
    {f'<div style="color:#c9d1d9; font-size:0.85rem; margin-top:0.4rem;">{desc_txt}{"..." if len(idea.get("descripcion") or "") > 120 else ""}</div>' if desc_txt else ''}
    {f'<div style="margin-top:0.4rem;">{badges_html}</div>' if badges_html else ''}
    {f'<div style="color:#8b949e; font-size:0.75rem; margin-top:0.3rem;">📝 {notas_txt[:60]}{"..." if len(notas_txt) > 60 else ""}</div>' if notas_txt else ''}
</div>""")

            with col_acc:
                if st.button("✏️", key=f"ei_{idea['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.idea_editando     = idea['id']
                    st.session_state.mostrar_form_idea = False

                if st.button("🗑️", key=f"di_{idea['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f'del_idea_{idea["id"]}'] = True

            # ── Confirmar eliminación ──────────────────────────
            if st.session_state.get(f'del_idea_{idea["id"]}'):
                c1, c2, c3 = st.columns([2,1,1])
                with c1:
                    st.warning(f"⚠️ ¿Eliminar *{idea['titulo']}*?")
                with c2:
                    if st.button("🗑️ Sí", key=f"cdi_{idea['id']}",
                                 use_container_width=True):
                        eliminar_idea(idea['id'])
                        st.session_state[
                            f'del_idea_{idea["id"]}'
                        ] = False
                        st.rerun()
                with c3:
                    if st.button("✖", key=f"cni_{idea['id']}",
                                 use_container_width=True):
                        st.session_state[
                            f'del_idea_{idea["id"]}'
                        ] = False
                        st.rerun()

            # ── Formulario edición inline ──────────────────────
            if st.session_state.idea_editando == idea['id']:
                try:
                    etiq_act = json.loads(idea.get('etiquetas') or '[]')
                except Exception:
                    etiq_act = []

                # ── Dominio FUERA del form ─────────────────────
                edom = st.selectbox(
                    "Dominio", DOMINIOS,
                    index=DOMINIOS.index(idea.get('dominio','Personal'))
                    if idea.get('dominio') in DOMINIOS else 0,
                    key=f"edom_fuera_{idea['id']}"
                )

                cats_edit   = obtener_categorias_dominio(edom)
                cat_actual  = idea.get('categoria', '')

                col_ec, col_ec_new = st.columns([2, 1])
                with col_ec:
                    ecat_sel = st.selectbox(
                        "Categoría",
                        options=cats_edit + ["✏️ Nueva categoría..."],
                        index=cats_edit.index(cat_actual)
                              if cat_actual in cats_edit else 0,
                        key=f"ecat_fuera_{idea['id']}_{edom}"
                    )
                with col_ec_new:
                    ecat_custom = st.text_input(
                        "Nueva categoría",
                        placeholder="Ej: Vacaciones",
                        value=cat_actual
                              if cat_actual not in cats_edit else "",
                        key=f"ecat_new_{idea['id']}"
                    )

                # Resolver categoría ANTES del form
                ecat = (
                    ecat_custom.strip()
                    if ecat_sel == "✏️ Nueva categoría..."
                       and ecat_custom.strip()
                    else ecat_sel
                    if ecat_sel != "✏️ Nueva categoría..."
                    else cat_actual
                )

                # ── Form solo para el resto ────────────────────
                with st.form(f"form_edit_idea_{idea['id']}"):
                    st.markdown(f"#### ✏️ Editando: {idea['titulo']}")

                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        et = st.text_input(
                            "Título", value=idea['titulo']
                        )
                    with col_e2:
                        eest = st.selectbox(
                            "Estado", ESTADOS_IDEA,
                            index=ESTADOS_IDEA.index(idea['estado'])
                            if idea['estado'] in ESTADOS_IDEA else 0
                        )

                    edesc = st.text_area(
                        "Descripción",
                        value=idea.get('descripcion','') or '',
                        height=80
                    )

                    col_e3, col_e4, col_e5 = st.columns(3)
                    with col_e3:
                        epri = st.select_slider(
                            "Prioridad", options=[1,2,3,4,5],
                            value=idea.get('prioridad', 3),
                            format_func=lambda x: {
                                1:'⚪ Baja',   2:'🔵 Normal',
                                3:'🟡 Media',  4:'🟠 Alta',
                                5:'🔴 Urgente'
                            }[x]
                        )
                    with col_e4:
                        emot = st.slider(
                            "Motivación", 1, 10,
                            value=idea.get('motivacion', 7)
                        )
                    with col_e5:
                        etags_str = st.text_input(
                            "Etiquetas",
                            value=", ".join(etiq_act)
                        )

                    enotas = st.text_area(
                        "Notas",
                        value=idea.get('notas','') or '',
                        height=60
                    )

                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button(
                            "💾 Guardar",
                            use_container_width=True,
                            type="primary"
                        ):
                            if not et.strip():
                                st.error("⚠️ Título obligatorio")
                            else:
                                new_tags = [
                                    t.strip() for t in
                                    etags_str.split(',') if t.strip()
                                ]
                                actualizar_idea(
                                    idea['id'], et.strip(), edesc,
                                    edom,   # ← viene de fuera
                                    ecat,   # ← viene de fuera
                                    new_tags, eest, epri, emot, enotas
                                )
                                st.session_state.idea_editando = None
                                st.success("✅ Idea actualizada")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button(
                            "✖ Cancelar",
                            use_container_width=True
                        ):
                            st.session_state.idea_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: SNIPPETS MULTI-DOMINIO
# ═══════════════════════════════════════════════════════════════

with tab_snippets:

    if 'snip_editando'     not in st.session_state:
        st.session_state.snip_editando     = None
    if 'mostrar_form_snip' not in st.session_state:
        st.session_state.mostrar_form_snip = False

    # ── Filtros ────────────────────────────────────────────────
    col_sf1, col_sf2, col_sf3, col_sbtn = st.columns([2,2,3,1])
    with col_sf1:
        sf_lang = st.selectbox(
            "Lenguaje", ["Todos"] + LENGUAJES, key="sf_lang"
        )
    with col_sf2:
        sf_dom = st.selectbox(
            "Dominio", ["Todos"] + DOMINIOS, key="sf_dom"
        )
    with col_sf3:
        sf_bus = st.text_input(
            "Buscar snippet",
            placeholder="Título, descripción, tags...",
            key="sf_bus"
        )
    with col_sbtn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nuevo", use_container_width=True,
                     type="primary", key="btn_new_snip"):
            st.session_state.mostrar_form_snip = True
            st.session_state.snip_editando     = None

    # ── FORMULARIO: Nuevo snippet ──────────────────────────────
    if st.session_state.mostrar_form_snip:
        st.divider()
        st.markdown("### ➕ Nuevo snippet")
        with st.form("form_nuevo_snip", clear_on_submit=True):
            col_sn1, col_sn2 = st.columns(2)
            with col_sn1:
                sn_titulo = st.text_input(
                    "Título *",
                    placeholder="Ej: Leer PDF recursivamente"
                )
                sn_lang = st.selectbox("Lenguaje", LENGUAJES)
            with col_sn2:
                sn_dom = st.selectbox("Dominio", DOMINIOS)
                sn_tags_str = st.text_input(
                    "Tags (comas)",
                    placeholder="Ej: pdf, pathlib, automatización"
                )

            sn_codigo = st.text_area(
                "Código *",
                height=180,
                placeholder="# Tu código aquí..."
            )
            sn_desc = st.text_area(
                "Descripción / Uso",
                height=60,
                placeholder="¿Para qué sirve? ¿Cómo usarlo?"
            )

            col_sg2, col_sc2 = st.columns(2)
            with col_sg2:
                submit_snip = st.form_submit_button(
                    "💾 Guardar snippet",
                    use_container_width=True, type="primary"
                )
            with col_sc2:
                cancel_snip = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_snip:
                st.session_state.mostrar_form_snip = False
                st.rerun()

            if submit_snip:
                if not sn_titulo.strip() or not sn_codigo.strip():
                    st.error("⚠️ Título y código son obligatorios")
                else:
                    sn_tags = [
                        t.strip() for t in
                        sn_tags_str.split(',') if t.strip()
                    ]
                    guardar_snippet(
                        sn_titulo.strip(), sn_desc,
                        sn_lang, sn_codigo, sn_tags, sn_dom
                    )
                    st.success(f"✅ '{sn_titulo}' guardado")
                    st.session_state.mostrar_form_snip = False
                    st.rerun()

    st.divider()

    # ── Lista de snippets ──────────────────────────────────────
    lang_f = None if sf_lang == "Todos" else sf_lang
    dom_sf = None if sf_dom  == "Todos" else sf_dom
    snippets = obtener_snippets(lang_f, dom_sf, sf_bus)

    if not snippets:
        st.info("📝 No hay snippets. ¡Agrega el primero!")
    else:
        st.caption(f"**{len(snippets)} snippets encontrados**")

        for s in snippets:
            emoji_l = EMOJIS_LANG.get(s['lenguaje'], '🔧')
            emoji_d = EMOJIS_DOMINIO.get(s.get('dominio','Otros'), '🌐')

            try:
                tags_s = json.loads(s.get('tags') or '[]')
            except Exception:
                tags_s = []

            tags_txt = " · ".join(f"#{t}" for t in tags_s[:5])

            col_snip, col_sacc = st.columns([5, 1])

            with col_snip:
                with st.expander(
                    f"{emoji_l} {s['titulo']} "
                    f"— {emoji_d} {s.get('dominio','')} "
                    f"· {s['veces_usado']} usos"
                ):
                    lang_code = (
                        s['lenguaje'].lower()
                        .replace('_css','')
                        .replace('html_','')
                        .replace('otro','text')
                    )
                    st.code(s['codigo'], language=lang_code)

                    if s.get('descripcion'):
                        st.caption(f"📝 {s['descripcion']}")
                    if tags_txt:
                        st.caption(f"🏷️ {tags_txt}")

                    col_uso, _ = st.columns([1, 3])
                    with col_uso:
                        if st.button(
                            "✅ Marcar como usado",
                            key=f"uso_{s['id']}",
                            use_container_width=True
                        ):
                            incrementar_uso(s['id'])
                            st.success(f"✅ {s['veces_usado']+1} usos")
                            st.rerun()

            with col_sacc:
                if st.button("✏️", key=f"es_{s['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.snip_editando     = s['id']
                    st.session_state.mostrar_form_snip = False

                if st.button("🗑️", key=f"ds_{s['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f'del_snip_{s["id"]}'] = True

            # ── Confirmar eliminación snippet ──────────────────
            if st.session_state.get(f'del_snip_{s["id"]}'):
                c1, c2, c3 = st.columns([2,1,1])
                with c1:
                    st.warning(f"⚠️ ¿Eliminar *{s['titulo']}*?")
                with c2:
                    if st.button("🗑️ Sí", key=f"cds_{s['id']}",
                                 use_container_width=True):
                        eliminar_snippet(s['id'])
                        st.session_state[
                            f'del_snip_{s["id"]}'
                        ] = False
                        st.rerun()
                with c3:
                    if st.button("✖", key=f"cns_{s['id']}",
                                 use_container_width=True):
                        st.session_state[
                            f'del_snip_{s["id"]}'
                        ] = False
                        st.rerun()

            # ── Edición inline snippet ─────────────────────────
            if st.session_state.snip_editando == s['id']:
                try:
                    tags_act = json.loads(s.get('tags') or '[]')
                except Exception:
                    tags_act = []

                with st.form(f"form_edit_snip_{s['id']}"):
                    st.markdown(f"#### ✏️ Editando: {s['titulo']}")

                    col_se1, col_se2 = st.columns(2)
                    with col_se1:
                        set_ = st.text_input("Título", value=s['titulo'])
                        sel  = st.selectbox(
                            "Lenguaje", LENGUAJES,
                            index=LENGUAJES.index(s['lenguaje'])
                            if s['lenguaje'] in LENGUAJES else 0
                        )
                    with col_se2:
                        sed = st.selectbox(
                            "Dominio", DOMINIOS,
                            index=DOMINIOS.index(s.get('dominio','Personal'))
                            if s.get('dominio') in DOMINIOS else 0
                        )
                        set_tags = st.text_input(
                            "Tags", value=", ".join(tags_act)
                        )

                    sec = st.text_area(
                        "Código", value=s.get('codigo',''),
                        height=180
                    )
                    sed2 = st.text_area(
                        "Descripción",
                        value=s.get('descripcion','') or '',
                        height=60
                    )

                    col_sg3, col_sc3 = st.columns(2)
                    with col_sg3:
                        if st.form_submit_button(
                            "💾 Guardar",
                            use_container_width=True,
                            type="primary"
                        ):
                            if not set_.strip() or not sec.strip():
                                st.error("⚠️ Título y código obligatorios")
                            else:
                                new_tags_s = [
                                    t.strip() for t in
                                    set_tags.split(',') if t.strip()
                                ]
                                actualizar_snippet(
                                    s['id'], set_.strip(), sed2,
                                    sel, sec, new_tags_s, sed
                                )
                                st.session_state.snip_editando = None
                                st.success("✅ Snippet actualizado")
                                st.rerun()
                    with col_sc3:
                        if st.form_submit_button(
                            "✖ Cancelar",
                            use_container_width=True
                        ):
                            st.session_state.snip_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 3: SESIONES
# ═══════════════════════════════════════════════════════════════

with tab_sesion:
    col_form, col_hist = st.columns([1, 1])

    with col_form:
        st.markdown("### ⏱️ Registrar sesión")

        fecha_s     = st.date_input("Fecha", value=date.today(),
                                     key="fecha_sesion")
        dom_sesion  = st.selectbox("Dominio de la sesión",
                                    DOMINIOS, key="dom_ses")
        duracion_s  = st.slider("Duración (min)", 15, 240, 60,
                                 step=15, key="dur_ses")
        tipo_act    = st.selectbox(
            "Tipo de actividad",
            ["Investigando","Codificando","Estudiando","Planificando",
             "Leyendo","Reflexionando","Prototipando","Documentando"],
            key="tipo_ses"
        )

        # Relacionar con idea
        todas_ideas_s = obtener_ideas()
        opciones_proy = (
            [(None, "Sin proyecto específico")] +
            [(i['id'],
              f"{EMOJIS_DOMINIO.get(i.get('dominio',''),'🌐')} "
              f"{i['titulo']}")
             for i in todas_ideas_s]
        )
        proy_id = st.selectbox(
            "Idea/Proyecto relacionado",
            options=[p[0] for p in opciones_proy],
            format_func=lambda x: next(
                p[1] for p in opciones_proy if p[0] == x
            ),
            key="proy_ses"
        )

        desc_s = st.text_area(
            "¿Qué hiciste?",
            height=100,
            placeholder="Describe lo que exploraste, aprendiste o avanzaste...",
            key="desc_ses"
        )
        codigo_s = st.text_area(
            "Código / notas producidas (opcional)",
            height=100,
            placeholder="Pega código, apuntes, reflexiones clave...",
            key="cod_ses"
        )
        satisf_s = st.slider("Satisfacción", 1, 10, 7,
                              key="sat_ses")

        if st.button("💾 Guardar sesión",
                     use_container_width=True, type="primary",
                     key="btn_guardar_ses"):
            if not desc_s.strip():
                st.error("⚠️ Describe qué hiciste en la sesión")
            else:
                guardar_sesion(
                    fecha_s, duracion_s, tipo_act, dom_sesion,
                    proy_id, desc_s, codigo_s, satisf_s
                )
                st.success("✅ Sesión registrada")
                st.balloons()
                st.rerun()

    with col_hist:
        st.markdown("### 📋 Sesiones recientes")
        sesiones = obtener_sesiones_recientes(10)

        if not sesiones:
            st.info("📝 Sin sesiones registradas aún")
        else:
            for ses in sesiones:
                emoji_d = EMOJIS_DOMINIO.get(
                    ses.get('dominio','Otros'), '🌐'
                )
                proy_txt = (
                    f" · {ses['proyecto_titulo']}"
                    if ses.get('proyecto_titulo') else ""
                )
                with st.expander(
                    f"{emoji_d} {ses['fecha']} — "
                    f"{ses['tipo_actividad']} "
                    f"{ses['duracion_minutos']}min{proy_txt} "
                    f"· ⭐{ses['satisfaccion']}/10"
                ):
                    st.write(ses.get('descripcion',''))
                    if ses.get('codigo_producido'):
                        st.code(ses['codigo_producido'])

# ═══════════════════════════════════════════════════════════════
# TAB 4: MENTOR IA MULTI-DOMINIO
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.markdown("### 🤖 Mentor IA Multi-dominio")

    if not api_key_configurada():
        st.warning("⚠️ IA offline — configura GROQ_API_KEY")

    col_ctx, col_chat = st.columns([1, 2])

    with col_ctx:
        st.markdown("**🎯 Contexto**")

        # Dominio de consulta
        dominio_ia = st.selectbox(
            "Área de consulta", DOMINIOS, key="dom_ia"
        )

        # Idea relacionada (opcional)
        ideas_dom = obtener_ideas(dominio=dominio_ia)
        if ideas_dom:
            usar_idea = st.checkbox(
                "Consultar sobre una idea específica",
                key="cb_usar_idea"
            )
            if usar_idea:
                idea_ia_id = st.selectbox(
                    "Seleccionar idea",
                    options=[i['id'] for i in ideas_dom],
                    format_func=lambda x: next(
                        i['titulo'] for i in ideas_dom if i['id'] == x
                    ),
                    key="sel_idea_ia"
                )
                idea_ia = next(
                    i for i in ideas_dom if i['id'] == idea_ia_id
                )
                contexto_idea = (
                    f"Idea: {idea_ia['titulo']}. "
                    f"Descripción: {idea_ia.get('descripcion','')}. "
                    f"Estado: {idea_ia['estado']}. "
                    f"Dominio: {idea_ia.get('dominio','')}."
                )
            else:
                contexto_idea = f"Dominio: {dominio_ia}"
        else:
            contexto_idea = f"Dominio: {dominio_ia}"
            st.caption(f"Sin ideas en {dominio_ia} aún")

        # Tipo de ayuda según dominio
        tipos_ayuda = {
            "Programacion": [
                "Planificar pasos del proyecto",
                "Sugerir librerías / herramientas",
                "Revisar enfoque técnico",
                "Ayuda para depurar",
                "Inspiración para nuevo proyecto"
            ],
            "Estudio": [
                "Plan de estudio para este tema",
                "Recursos y bibliografía",
                "Conexión con otros temas",
                "Preguntas de comprensión",
                "Resumen del concepto"
            ],
            "Personal": [
                "Plan de acción para esta meta",
                "Hábitos relacionados",
                "Obstáculos comunes y cómo superarlos",
                "Reflexión bíblica sobre el tema",
                "Próximo paso concreto"
            ],
            "Familia": [
                "Ideas para fortalecer esta área",
                "Conversaciones importantes",
                "Actividades juntos",
                "Reflexión cristiana",
                "Cómo priorizar esto"
            ],
            "Ministerio": [
                "Cómo desarrollar este proyecto",
                "Recursos bíblicos relevantes",
                "Plan de implementación",
                "Cómo involucrar a otros",
                "Reflexión sobre el impacto"
            ],
        }
        opciones_ayuda = tipos_ayuda.get(dominio_ia, [
            "Plan de acción",
            "Recursos útiles",
            "Próximo paso",
            "Reflexión bíblica",
            "Cómo priorizar"
        ])

        tipo_ayuda_ia = st.selectbox(
            "Tipo de ayuda", opciones_ayuda, key="tipo_ayuda_ia"
        )

        # Estadísticas del dominio para contexto
        ideas_total = obtener_ideas(dominio=dominio_ia)
        if ideas_total:
            st.divider()
            st.caption(f"📊 {len(ideas_total)} ideas en {dominio_ia}")
            activas_dom = [
                i for i in ideas_total
                if i['estado'] not in ['Completado','Abandonado']
            ]
            st.caption(f"🔄 {len(activas_dom)} activas")

    with col_chat:
        st.markdown("**💬 Chat con mentor**")

        prompt_usuario_ia = st.text_area(
            "Tu pregunta o contexto adicional",
            height=100,
            placeholder=(
                "Ej: No sé por dónde empezar con este proyecto... "
                "/ ¿Cómo equilibro esto con mis otras responsabilidades?"
            ),
            key="prompt_ia"
        )

        if st.button("🚀 Consultar al mentor",
                     use_container_width=True,
                     type="primary", key="btn_mentor"):

            prompt_completo = f"""
Área: {dominio_ia}
Tipo de ayuda solicitada: {tipo_ayuda_ia}
Contexto: {contexto_idea}

Pregunta del usuario: {prompt_usuario_ia or 'Ver contexto arriba'}

Da una respuesta práctica, alentadora y concreta.
Si aplica, incluye un principio bíblico relevante.
"""
            with st.spinner("Mentor pensando..."):
                respuesta = chat_simple(
                    prompt_completo,
                    contexto=SYSTEM_MENTOR
                )
                st.info(respuesta)

        st.divider()

        # Chat libre
        st.markdown("**💬 Pregunta libre**")
        pregunta_libre_ia = st.text_input(
            "Cualquier pregunta",
            placeholder="Ej: ¿Cómo equilibro el estudio con la familia?",
            key="libre_ia"
        )
        if pregunta_libre_ia:
            with st.spinner("Pensando..."):
                st.info(chat_simple(
                    f"Contexto: {contexto_idea}\n"
                    f"Pregunta: {pregunta_libre_ia}",
                    contexto=SYSTEM_MENTOR
                ))

st.divider()
st.caption("🧪 Sandbox • Experimentar, fallar, aprender, repetir")