"""
🧪 Sandbox - Laboratorio multi-dominio de ideas, snippets y sesiones
"""

import streamlit as st
from datetime import timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import (
    CATEGORIAS_DEFAULT_POR_DOMINIO,
    COLORES_ESTADO_SANDBOX as COLORES_ESTADO,
    DOMINIOS_SANDBOX as DOMINIOS,
    EMOJIS_DOMINIO,
    EMOJIS_LANG,
    ESTADOS_IDEA,
    LENGUAJES,
    SYSTEM_MENTOR,
    actualizar_idea,
    actualizar_snippet,
    eliminar_idea,
    eliminar_snippet,
    guardar_idea,
    guardar_sesion,
    guardar_snippet,
    incrementar_uso,
    obtener_categorias_dominio,
    obtener_ideas,
    obtener_sesiones_recientes,
    obtener_snippets,
)
from app.tenant import uid
from app.ai_client import chat_simple, api_key_configurada
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    iso_ahora,
)

st.set_page_config(
    page_title="Sandbox | Mission Dashboard",
    page_icon="🧪",
    layout="wide"
)

from app.auth import require_auth
from app.onboarding import require_onboarding, require_module
require_auth()
require_onboarding()
require_module("sandbox")
ensure_database()


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
                       if i["estado"] not in ["Completado","Abandonado"]])
    completadas = len([i for i in todas_ideas if i["estado"] == "Completado"])

    col1, col2 = st.columns(2)
    col1.metric("Ideas activas", activas)
    col2.metric("Completadas",   completadas)
    st.metric("Snippets totales", len(todos_snippets))

    if todas_ideas:
        st.divider()
        st.caption("📊 Ideas por dominio")
        por_dom: dict = {}
        for i in todas_ideas:
            d = i.get("dominio", "Otros")
            por_dom[d] = por_dom.get(d, 0) + 1
        for dom, cnt in sorted(por_dom.items(), key=lambda x: -x[1]):
            st.caption(f"{EMOJIS_DOMINIO.get(dom,'🌐')} {dom}: {cnt}")

    if todos_snippets:
        st.divider()
        st.caption("🔥 Snippets más usados")
        top = sorted(todos_snippets,
                     key=lambda x: x["veces_usado"], reverse=True)[:3]
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
# TAB 1: IDEAS
# ═══════════════════════════════════════════════════════════════

with tab_ideas:
    for key, default in [
        ("idea_editando",     None),
        ("mostrar_form_idea", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Filtros
    col_f1,col_f2,col_f3,col_f4,col_btn = st.columns([2,2,2,2,1])
    with col_f1:
        f_dominio  = st.selectbox("Dominio",  ["Todos"]+DOMINIOS,     key="f_dom_ideas")
    with col_f2:
        f_estado   = st.selectbox("Estado",   ["Todos"]+ESTADOS_IDEA, key="f_est_ideas")
    with col_f3:
        f_busqueda = st.text_input("Buscar",
            placeholder="Título, descripción...", key="f_bus_ideas")
    with col_f4:
        f_orden    = st.selectbox("Ordenar por",
            ["Prioridad","Motivación","Más recientes"], key="f_ord_ideas")
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nueva", use_container_width=True, type="primary"):
            st.session_state.mostrar_form_idea = True
            st.session_state.idea_editando     = None

    # ── Formulario: Nueva idea ────────────────────────────────
    if st.session_state.mostrar_form_idea:
        st.divider()
        st.markdown("### ➕ Nueva idea")

        n_dominio        = st.selectbox("Dominio *", DOMINIOS, key="n_dominio_fuera")
        cats_disponibles = obtener_categorias_dominio(n_dominio)

        col_cat, col_cat_new = st.columns([2, 1])
        with col_cat:
            n_cat_sel = st.selectbox(
                "Categoría",
                options=cats_disponibles + ["✏️ Nueva categoría..."],
                key=f"n_cat_sel_{n_dominio}"
            )
        with col_cat_new:
            n_cat_custom = st.text_input(
                "Nueva categoría",
                placeholder="Ej: Vacaciones", key="n_cat_custom"
            )

        n_categoria = (
            n_cat_custom.strip()
            if n_cat_sel == "✏️ Nueva categoría..." and n_cat_custom.strip()
            else n_cat_sel if n_cat_sel != "✏️ Nueva categoría..."
            else ""
        )

        with st.form("form_nueva_idea", clear_on_submit=True):
            col_n1, col_n2 = st.columns(2)
            with col_n1:
                n_titulo = st.text_input("Título *",
                    placeholder="Ej: Salida familiar al lago")
            with col_n2:
                n_estado = st.selectbox("Estado inicial", ESTADOS_IDEA)

            n_desc = st.text_area("Descripción",
                placeholder="¿Qué es esta idea? ¿Por qué te interesa?",
                height=80)

            col_n3, col_n4, col_n5 = st.columns(3)
            with col_n3:
                n_prioridad = st.select_slider(
                    "Prioridad", options=[1,2,3,4,5], value=3,
                    format_func=lambda x: {
                        1:"⚪ Baja",2:"🔵 Normal",3:"🟡 Media",
                        4:"🟠 Alta",5:"🔴 Urgente"}[x]
                )
            with col_n4:
                n_motivacion = st.slider("Motivación", 1, 10, 7)
            with col_n5:
                n_etiquetas_str = st.text_input("Etiquetas (comas)",
                    placeholder="Ej: urgente, largo plazo")

            n_notas = st.text_area("Notas adicionales",
                placeholder="Recursos, pasos iniciales...", height=60)

            col_sg, col_sc = st.columns(2)
            with col_sg:
                submit_idea = st.form_submit_button(
                    "💾 Guardar idea", use_container_width=True, type="primary"
                )
            with col_sc:
                cancel_idea = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_idea:
                st.session_state.mostrar_form_idea = False
                st.rerun()

            if submit_idea:
                if not n_titulo.strip():
                    st.error("⚠️ El título es obligatorio")
                elif n_cat_sel == "✏️ Nueva categoría..." and not n_cat_custom.strip():
                    st.error("⚠️ Escribe el nombre de la nueva categoría")
                else:
                    guardar_idea(
                        n_titulo.strip(), n_desc, n_dominio, n_categoria,
                        [t.strip() for t in n_etiquetas_str.split(",") if t.strip()],
                        n_prioridad, n_motivacion, n_notas
                    )
                    st.success(f"✅ '{n_titulo}' guardada")
                    st.session_state.mostrar_form_idea = False
                    st.rerun()

    st.divider()

    # ── Lista de ideas ────────────────────────────────────────
    ideas = obtener_ideas(
        None if f_estado  == "Todos" else f_estado,
        None if f_dominio == "Todos" else f_dominio,
        f_busqueda,
    )
    if f_orden == "Motivación":
        ideas.sort(key=lambda x: x["motivacion"], reverse=True)
    elif f_orden == "Más recientes":
        ideas.sort(key=lambda x: x["creado_en"], reverse=True)

    if not ideas:
        st.info("📝 No hay ideas con estos filtros. ¡Agrega la primera!")
    else:
        st.caption(f"**{len(ideas)} ideas encontradas**")

        for idea in ideas:
            emoji_dom  = EMOJIS_DOMINIO.get(idea.get("dominio","Otros"), "🌐")
            color_est  = COLORES_ESTADO.get(idea["estado"], "#8b949e")
            estado_txt = idea["estado"].replace("_"," ")
            try:
                etiquetas = json.loads(idea.get("etiquetas") or "[]")
            except Exception:
                etiquetas = []

            badges_html = " ".join(
                f"<span style='background:#21262d;color:#58a6ff;"
                f"border:1px solid #30363d;border-radius:12px;"
                f"padding:0.1rem 0.5rem;font-size:0.7rem;'>"
                f"{tag}</span>"
                for tag in etiquetas[:5]
            )
            desc_txt  = (idea.get("descripcion") or "")[:120]
            notas_txt = idea.get("notas") or ""
            cat_txt   = idea.get("categoria") or ""

            col_card, col_acc = st.columns([5, 1])
            with col_card:
                st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-left:4px solid {color_est};
            border-radius:10px;padding:0.85rem 1.25rem;
            margin-bottom:0.4rem;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:700;color:#f0f6fc;font-size:1rem;">
            {emoji_dom} {idea['titulo']}
        </span>
        <span style="font-size:0.72rem;color:#8b949e;">
            <span style="color:{color_est};">● {estado_txt}</span>
            &nbsp;·&nbsp; ⭐ {idea.get('prioridad',3)}/5
            &nbsp;·&nbsp; 💪 {idea.get('motivacion',5)}/10
        </span>
    </div>
    <div style="color:#8b949e;font-size:0.78rem;margin-top:0.25rem;">
        {emoji_dom} {idea.get('dominio','Otros')}
        {f'&nbsp;·&nbsp; {cat_txt}' if cat_txt else ''}
    </div>
    {f'<div style="color:#c9d1d9;font-size:0.85rem;margin-top:0.4rem;">{desc_txt}{"..." if len(idea.get("descripcion") or "") > 120 else ""}</div>' if desc_txt else ''}
    {f'<div style="margin-top:0.4rem;">{badges_html}</div>' if badges_html else ''}
    {f'<div style="color:#8b949e;font-size:0.75rem;margin-top:0.3rem;">📝 {notas_txt[:60]}{"..." if len(notas_txt)>60 else ""}</div>' if notas_txt else ''}
</div>""")

            with col_acc:
                if st.button("✏️", key=f"ei_{idea['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.idea_editando     = idea["id"]
                    st.session_state.mostrar_form_idea = False
                if st.button("🗑️", key=f"di_{idea['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f"del_idea_{idea['id']}"] = True

            # Confirmar eliminación
            if st.session_state.get(f"del_idea_{idea['id']}"):
                c1, c2, c3 = st.columns([2,1,1])
                with c1:
                    st.warning(f"⚠️ ¿Eliminar *{idea['titulo']}*?")
                with c2:
                    if st.button("🗑️ Sí", key=f"cdi_{idea['id']}",
                                 use_container_width=True):
                        eliminar_idea(idea["id"])
                        st.session_state[f"del_idea_{idea['id']}"] = False
                        st.rerun()
                with c3:
                    if st.button("✖", key=f"cni_{idea['id']}",
                                 use_container_width=True):
                        st.session_state[f"del_idea_{idea['id']}"] = False
                        st.rerun()

            # Edición inline
            if st.session_state.idea_editando == idea["id"]:
                try:
                    etiq_act = json.loads(idea.get("etiquetas") or "[]")
                except Exception:
                    etiq_act = []

                edom = st.selectbox(
                    "Dominio", DOMINIOS,
                    index=DOMINIOS.index(idea.get("dominio","Personal"))
                    if idea.get("dominio") in DOMINIOS else 0,
                    key=f"edom_fuera_{idea['id']}"
                )
                cats_edit  = obtener_categorias_dominio(edom)
                cat_actual = idea.get("categoria", "")

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
                        value=cat_actual if cat_actual not in cats_edit else "",
                        placeholder="Ej: Vacaciones",
                        key=f"ecat_new_{idea['id']}"
                    )

                ecat = (
                    ecat_custom.strip()
                    if ecat_sel == "✏️ Nueva categoría..." and ecat_custom.strip()
                    else ecat_sel if ecat_sel != "✏️ Nueva categoría..."
                    else cat_actual
                )

                with st.form(f"form_edit_idea_{idea['id']}"):
                    st.markdown(f"#### ✏️ Editando: {idea['titulo']}")
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        et = st.text_input("Título", value=idea["titulo"])
                    with col_e2:
                        eest = st.selectbox(
                            "Estado", ESTADOS_IDEA,
                            index=ESTADOS_IDEA.index(idea["estado"])
                            if idea["estado"] in ESTADOS_IDEA else 0
                        )

                    edesc = st.text_area("Descripción",
                        value=idea.get("descripcion","") or "", height=80)

                    col_e3, col_e4, col_e5 = st.columns(3)
                    with col_e3:
                        epri = st.select_slider(
                            "Prioridad", options=[1,2,3,4,5],
                            value=idea.get("prioridad",3),
                            format_func=lambda x: {
                                1:"⚪ Baja",2:"🔵 Normal",3:"🟡 Media",
                                4:"🟠 Alta",5:"🔴 Urgente"}[x]
                        )
                    with col_e4:
                        emot = st.slider("Motivación", 1, 10,
                            value=idea.get("motivacion",7))
                    with col_e5:
                        etags_str = st.text_input("Etiquetas",
                            value=", ".join(etiq_act))

                    enotas = st.text_area("Notas",
                        value=idea.get("notas","") or "", height=60)

                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button("💾 Guardar",
                                                 use_container_width=True,
                                                 type="primary"):
                            if not et.strip():
                                st.error("⚠️ Título obligatorio")
                            else:
                                actualizar_idea(
                                    idea["id"], et.strip(), edesc, edom, ecat,
                                    [t.strip() for t in etags_str.split(",")
                                     if t.strip()],
                                    eest, epri, emot, enotas
                                )
                                st.session_state.idea_editando = None
                                st.success("✅ Idea actualizada")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button("✖ Cancelar",
                                                 use_container_width=True):
                            st.session_state.idea_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: SNIPPETS
# ═══════════════════════════════════════════════════════════════

with tab_snippets:
    for key, default in [
        ("snip_editando",     None),
        ("mostrar_form_snip", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    col_sf1, col_sf2, col_sf3, col_sbtn = st.columns([2,2,3,1])
    with col_sf1:
        sf_lang = st.selectbox("Lenguaje", ["Todos"]+LENGUAJES, key="sf_lang")
    with col_sf2:
        sf_dom  = st.selectbox("Dominio",  ["Todos"]+DOMINIOS,  key="sf_dom")
    with col_sf3:
        sf_bus  = st.text_input("Buscar snippet",
            placeholder="Título, descripción, tags...", key="sf_bus")
    with col_sbtn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nuevo", use_container_width=True,
                     type="primary", key="btn_new_snip"):
            st.session_state.mostrar_form_snip = True
            st.session_state.snip_editando     = None

    # ── Formulario: Nuevo snippet ─────────────────────────────
    if st.session_state.mostrar_form_snip:
        st.divider()
        st.markdown("### ➕ Nuevo snippet")
        with st.form("form_nuevo_snip", clear_on_submit=True):
            col_sn1, col_sn2 = st.columns(2)
            with col_sn1:
                sn_titulo   = st.text_input("Título *",
                    placeholder="Ej: Leer PDF recursivamente")
                sn_lang     = st.selectbox("Lenguaje", LENGUAJES)
            with col_sn2:
                sn_dom      = st.selectbox("Dominio", DOMINIOS)
                sn_tags_str = st.text_input("Tags (comas)",
                    placeholder="Ej: pdf, pathlib")

            sn_codigo = st.text_area("Código *", height=180,
                placeholder="# Tu código aquí...")
            sn_desc   = st.text_area("Descripción / Uso", height=60,
                placeholder="¿Para qué sirve?")

            col_sg2, col_sc2 = st.columns(2)
            with col_sg2:
                submit_snip = st.form_submit_button(
                    "💾 Guardar snippet", use_container_width=True, type="primary"
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
                    guardar_snippet(
                        sn_titulo.strip(), sn_desc, sn_lang, sn_codigo,
                        [t.strip() for t in sn_tags_str.split(",") if t.strip()],
                        sn_dom
                    )
                    st.success(f"✅ '{sn_titulo}' guardado")
                    st.session_state.mostrar_form_snip = False
                    st.rerun()

    st.divider()

    snippets = obtener_snippets(
        None if sf_lang == "Todos" else sf_lang,
        None if sf_dom  == "Todos" else sf_dom,
        sf_bus,
    )

    if not snippets:
        st.info("📝 No hay snippets. ¡Agrega el primero!")
    else:
        st.caption(f"**{len(snippets)} snippets encontrados**")

        for s in snippets:
            emoji_l = EMOJIS_LANG.get(s["lenguaje"], "🔧")
            emoji_d = EMOJIS_DOMINIO.get(s.get("dominio","Otros"), "🌐")
            try:
                tags_s = json.loads(s.get("tags") or "[]")
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
                    lang_code = (s["lenguaje"].lower()
                                 .replace("_css","").replace("html_","")
                                 .replace("otro","text"))
                    st.code(s["codigo"], language=lang_code)
                    if s.get("descripcion"):
                        st.caption(f"📝 {s['descripcion']}")
                    if tags_txt:
                        st.caption(f"🏷️ {tags_txt}")
                    col_uso, _ = st.columns([1, 3])
                    with col_uso:
                        if st.button("✅ Marcar como usado",
                                     key=f"uso_{s['id']}",
                                     use_container_width=True):
                            incrementar_uso(s["id"])
                            st.success(f"✅ {s['veces_usado']+1} usos")
                            st.rerun()

            with col_sacc:
                if st.button("✏️", key=f"es_{s['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.snip_editando     = s["id"]
                    st.session_state.mostrar_form_snip = False
                if st.button("🗑️", key=f"ds_{s['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f"del_snip_{s['id']}"] = True

            if st.session_state.get(f"del_snip_{s['id']}"):
                c1, c2, c3 = st.columns([2,1,1])
                with c1:
                    st.warning(f"⚠️ ¿Eliminar *{s['titulo']}*?")
                with c2:
                    if st.button("🗑️ Sí", key=f"cds_{s['id']}",
                                 use_container_width=True):
                        eliminar_snippet(s["id"])
                        st.session_state[f"del_snip_{s['id']}"] = False
                        st.rerun()
                with c3:
                    if st.button("✖", key=f"cns_{s['id']}",
                                 use_container_width=True):
                        st.session_state[f"del_snip_{s['id']}"] = False
                        st.rerun()

            if st.session_state.snip_editando == s["id"]:
                try:
                    tags_act = json.loads(s.get("tags") or "[]")
                except Exception:
                    tags_act = []

                with st.form(f"form_edit_snip_{s['id']}"):
                    st.markdown(f"#### ✏️ Editando: {s['titulo']}")
                    col_se1, col_se2 = st.columns(2)
                    with col_se1:
                        set_  = st.text_input("Título", value=s["titulo"])
                        sel   = st.selectbox(
                            "Lenguaje", LENGUAJES,
                            index=LENGUAJES.index(s["lenguaje"])
                            if s["lenguaje"] in LENGUAJES else 0
                        )
                    with col_se2:
                        sed   = st.selectbox(
                            "Dominio", DOMINIOS,
                            index=DOMINIOS.index(s.get("dominio","Personal"))
                            if s.get("dominio") in DOMINIOS else 0
                        )
                        set_tags = st.text_input("Tags",
                            value=", ".join(tags_act))

                    sec  = st.text_area("Código",
                        value=s.get("codigo",""), height=180)
                    sed2 = st.text_area("Descripción",
                        value=s.get("descripcion","") or "", height=60)

                    col_sg3, col_sc3 = st.columns(2)
                    with col_sg3:
                        if st.form_submit_button("💾 Guardar",
                                                 use_container_width=True,
                                                 type="primary"):
                            if not set_.strip() or not sec.strip():
                                st.error("⚠️ Título y código obligatorios")
                            else:
                                actualizar_snippet(
                                    s["id"], set_.strip(), sed2, sel, sec,
                                    [t.strip() for t in set_tags.split(",")
                                     if t.strip()],
                                    sed
                                )
                                st.session_state.snip_editando = None
                                st.success("✅ Snippet actualizado")
                                st.rerun()
                    with col_sc3:
                        if st.form_submit_button("✖ Cancelar",
                                                 use_container_width=True):
                            st.session_state.snip_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 3: SESIONES
# ═══════════════════════════════════════════════════════════════

with tab_sesion:
    col_form, col_hist = st.columns([1, 1])

    with col_form:
        st.markdown("### ⏱️ Registrar sesión")
        fecha_s    = st.date_input("Fecha", value=_hoy(), key="fecha_sesion")  # ← local
        dom_sesion = st.selectbox("Dominio de la sesión", DOMINIOS, key="dom_ses")
        duracion_s = st.slider("Duración (min)", 15, 240, 60,
                               step=15, key="dur_ses")
        tipo_act   = st.selectbox("Tipo de actividad", [
            "Investigando","Codificando","Estudiando","Planificando",
            "Leyendo","Reflexionando","Prototipando","Documentando",
        ], key="tipo_ses")

        todas_ideas_s = obtener_ideas()
        opciones_proy = (
            [(None, "Sin proyecto específico")] +
            [(i["id"],
              f"{EMOJIS_DOMINIO.get(i.get('dominio',''),'🌐')} {i['titulo']}")
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
        desc_s   = st.text_area("¿Qué hiciste?", height=100,
            placeholder="Describe lo que exploraste, aprendiste o avanzaste...",
            key="desc_ses")
        codigo_s = st.text_area(
            "Código / notas producidas (opcional)", height=100,
            placeholder="Pega código, apuntes, reflexiones clave...",
            key="cod_ses")
        satisf_s = st.slider("Satisfacción", 1, 10, 7, key="sat_ses")

        if st.button("💾 Guardar sesión", use_container_width=True,
                     type="primary", key="btn_guardar_ses"):
            if not desc_s.strip():
                st.error("⚠️ Describe qué hiciste en la sesión")
            else:
                guardar_sesion(
                    fecha_s,          # str ISO via fecha_iso interno
                    duracion_s, tipo_act, dom_sesion,
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
                emoji_d  = EMOJIS_DOMINIO.get(ses.get("dominio","Otros"), "🌐")
                proy_txt = (f" · {ses['proyecto_titulo']}"
                            if ses.get("proyecto_titulo") else "")
                with st.expander(
                    f"{emoji_d} {ses['fecha']} — "
                    f"{ses['tipo_actividad']} "
                    f"{ses['duracion_minutos']}min{proy_txt} "
                    f"· ⭐{ses['satisfaccion']}/10"
                ):
                    st.write(ses.get("descripcion",""))
                    if ses.get("codigo_producido"):
                        st.code(ses["codigo_producido"])

# ═══════════════════════════════════════════════════════════════
# TAB 4: MENTOR IA
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.markdown("### 🤖 Mentor IA Multi-dominio")

    if not api_key_configurada():
        st.warning("⚠️ IA offline — configura GROQ_API_KEY")

    col_ctx, col_chat = st.columns([1, 2])

    with col_ctx:
        st.markdown("**🎯 Contexto**")
        dominio_ia    = st.selectbox("Área de consulta", DOMINIOS, key="dom_ia")
        ideas_dom     = obtener_ideas(dominio=dominio_ia)
        contexto_idea = f"Dominio: {dominio_ia}"

        if ideas_dom:
            usar_idea = st.checkbox(
                "Consultar sobre una idea específica", key="cb_usar_idea"
            )
            if usar_idea:
                idea_ia_id = st.selectbox(
                    "Seleccionar idea",
                    options=[i["id"] for i in ideas_dom],
                    format_func=lambda x: next(
                        i["titulo"] for i in ideas_dom if i["id"] == x
                    ),
                    key="sel_idea_ia"
                )
                idea_ia = next(i for i in ideas_dom if i["id"] == idea_ia_id)
                contexto_idea = (
                    f"Idea: {idea_ia['titulo']}. "
                    f"Descripción: {idea_ia.get('descripcion','')}. "
                    f"Estado: {idea_ia['estado']}. "
                    f"Dominio: {idea_ia.get('dominio','')}."
                )
        else:
            st.caption(f"Sin ideas en {dominio_ia} aún")

        tipos_ayuda = {
            "Programacion": [
                "Planificar pasos del proyecto",
                "Sugerir librerías / herramientas",
                "Revisar enfoque técnico",
                "Ayuda para depurar",
                "Inspiración para nuevo proyecto",
            ],
            "Estudio": [
                "Plan de estudio para este tema",
                "Recursos y bibliografía",
                "Conexión con otros temas",
                "Preguntas de comprensión",
                "Resumen del concepto",
            ],
            "Personal": [
                "Plan de acción para esta meta",
                "Hábitos relacionados",
                "Obstáculos comunes y cómo superarlos",
                "Reflexión bíblica sobre el tema",
                "Próximo paso concreto",
            ],
            "Familia": [
                "Ideas para fortalecer esta área",
                "Conversaciones importantes",
                "Actividades juntos",
                "Reflexión cristiana",
                "Cómo priorizar esto",
            ],
            "Ministerio": [
                "Cómo desarrollar este proyecto",
                "Recursos bíblicos relevantes",
                "Plan de implementación",
                "Cómo involucrar a otros",
                "Reflexión sobre el impacto",
            ],
        }
        opciones_ayuda = tipos_ayuda.get(dominio_ia, [
            "Plan de acción", "Recursos útiles", "Próximo paso",
            "Reflexión bíblica", "Cómo priorizar",
        ])
        tipo_ayuda_ia = st.selectbox(
            "Tipo de ayuda", opciones_ayuda, key="tipo_ayuda_ia"
        )

        ideas_total = obtener_ideas(dominio=dominio_ia)
        if ideas_total:
            st.divider()
            activas_dom = [i for i in ideas_total
                           if i["estado"] not in ["Completado","Abandonado"]]
            st.caption(
                f"📊 {len(ideas_total)} ideas en {dominio_ia} "
                f"· 🔄 {len(activas_dom)} activas"
            )

    with col_chat:
        st.markdown("**💬 Chat con mentor**")
        prompt_usuario_ia = st.text_area(
            "Tu pregunta o contexto adicional", height=100,
            placeholder="Ej: No sé por dónde empezar con este proyecto...",
            key="prompt_ia"
        )
        if st.button("🚀 Consultar al mentor", use_container_width=True,
                     type="primary", key="btn_mentor"):
            with st.spinner("Mentor pensando..."):
                st.info(chat_simple(
                    f"Área: {dominio_ia}\n"
                    f"Tipo de ayuda: {tipo_ayuda_ia}\n"
                    f"Contexto: {contexto_idea}\n\n"
                    f"Pregunta: {prompt_usuario_ia or 'Ver contexto arriba'}\n\n"
                    f"Da una respuesta práctica y concreta. "
                    f"Si aplica, incluye un principio bíblico relevante.",
                    contexto=SYSTEM_MENTOR
                ))

        st.divider()
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