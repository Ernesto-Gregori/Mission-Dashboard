"""
🧪 Sandbox - Laboratorio de ideas y experimentación técnica
Espacio para jugar con código fuera de cursos formales
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
    page_title="Sandbox | Mission Dashboard",  # ← page_title, no title
    page_icon="🧪",
    layout="wide"
)

init_database()

# ═════════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═════════════════════════════════════════════════════════════════

def obtener_ideas(estado=None, categoria=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM sandbox_ideas WHERE 1=1"
    params = []
    
    if estado:
        query += " AND estado = ?"
        params.append(estado)
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    
    query += " ORDER BY motivacion DESC, creado_en DESC"
    
    cursor.execute(query, params)
    ideas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return ideas

def guardar_idea(titulo, descripcion, categoria, tecnologias, complejidad, motivacion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sandbox_ideas (titulo, descripcion, categoria, tecnologias, complejidad, motivacion)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (titulo, descripcion, categoria, json.dumps(tecnologias), complejidad, motivacion))
    conn.commit()
    conn.close()

def obtener_snippets(lenguaje=None, tag=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM sandbox_snippets WHERE 1=1"
    params = []
    
    if lenguaje:
        query += " AND lenguaje = ?"
        params.append(lenguaje)
    if tag:
        query += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    
    query += " ORDER BY veces_usado DESC, creado_en DESC"
    
    cursor.execute(query, params)
    snippets = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return snippets

def guardar_sesion(fecha, duracion, tipo, proyecto_id, descripcion, codigo, satisfaccion):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sandbox_sesiones (fecha, duracion_minutos, tipo_actividad, proyecto_id, descripcion, codigo_producido, satisfaccion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (fecha, duracion, tipo, proyecto_id, descripcion, codigo, satisfaccion))
    conn.commit()
    conn.close()

# ═════════════════════════════════════════════════════════════════
# HEADER
# ═════════════════════════════════════════════════════════════════

st.title("🧪 Sandbox")
st.caption("Laboratorio de ideas • Experimentación sin presión • Aprendizaje jugando")

# ═════════════════════════════════════════════════════════════════
# SIDEBAR - ESTADÍSTICAS
# ═════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Tu laboratorio")
    
    ideas = obtener_ideas()
    ideas_activas = len([i for i in ideas if i['estado'] in ['Idea', 'Investigando', 'Prototipo']])
    ideas_completadas = len([i for i in ideas if i['estado'] == 'Completado'])
    
    col1, col2 = st.columns(2)
    col1.metric("Ideas activas", ideas_activas)
    col2.metric("Completadas", ideas_completadas)
    
    # Snippets más usados
    snippets = obtener_snippets()
    if snippets:
        st.divider()
        st.caption("🔥 Snippets más usados")
        for s in sorted(snippets, key=lambda x: x['veces_usado'], reverse=True)[:3]:
            st.markdown(f"- **{s['titulo']}** ({s['veces_usado']} usos)")

# ═════════════════════════════════════════════════════════════════
# TABS
# ═════════════════════════════════════════════════════════════════

tab_ideas, tab_snippets, tab_sesion, tab_ia = st.tabs([
    "💡 Ideas", "🧩 Snippets", "⏱️ Nueva Sesión", "🤖 IA Mentor"
])

# ═════════════════════════════════════════════════════════════════
# TAB 1: IDEAS DE PROYECTOS
# ═════════════════════════════════════════════════════════════════

with tab_ideas:
    col_filtros, col_lista = st.columns([1, 3])
    
    with col_filtros:
        st.markdown("### 🔍 Filtrar")
        filtro_estado = st.selectbox("Estado", ["Todos", "Idea", "Investigando", "Prototipo", "Completado"], key="filtro_estado_ideas")
        filtro_cat = st.selectbox("Categoría", ["Todas", "Script_Automatizacion", "Web_App", "Mobile", "Data_Science", "DevOps", "Seguridad"], key="filtro_cat_ideas")
        
        st.divider()
        st.markdown("### ➕ Nueva idea")
        with st.form("nueva_idea", clear_on_submit=True):
            titulo = st.text_input("Título", placeholder="Ej: Script para organizar PDFs")
            desc = st.text_area("Descripción", height=80)
            cat = st.selectbox("Categoría", ["Script_Automatizacion", "Web_App", "Mobile", "Data_Science", "DevOps", "Seguridad", "Otro"])
            tech = st.text_input("Tecnologías (separadas por coma)", placeholder="Python, Streamlit, SQLite")
            comp = st.slider("Complejidad", 1, 5, 2, help="1=fácil, 5=experto")
            motiv = st.slider("Motivación", 1, 10, 7)
            
            if st.form_submit_button("💾 Guardar idea"):
                guardar_idea(titulo, desc, cat, [t.strip() for t in tech.split(",") if t.strip()], comp, motiv)
                st.success("✅ Idea guardada")
                st.rerun()
    
    with col_lista:
        st.markdown("### 📋 Ideas registradas")
        
        estado_filtro = None if filtro_estado == "Todos" else filtro_estado
        cat_filtro = None if filtro_cat == "Todas" else filtro_cat
        
        ideas = obtener_ideas(estado_filtro, cat_filtro)
        
        if not ideas:
            st.info("📝 No hay ideas con estos filtros. ¡Agrega una nueva!")
        else:
            for idea in ideas:
                emoji_cat = {
                    'Script_Automatizacion': '🤖',
                    'Web_App': '🌐',
                    'Mobile': '📱',
                    'Data_Science': '📊',
                    'DevOps': '⚙️',
                    'Seguridad': '🔒',
                    'Otro': '💡'
                }.get(idea['categoria'], '💡')
                
                # Color según estado
                color_estado = {
                    'Idea': '#8b949e',
                    'Investigando': '#58a6ff',
                    'Prototipo': '#e3b341',
                    'Completado': '#3fb950',
                    'Abandonado': '#f85149'
                }.get(idea['estado'], '#8b949e')
                
                with st.container():
                    col_info, col_motiv = st.columns([4, 1])
                    
                    with col_info:
                        st.markdown(f"""
                        <div style="border-left: 4px solid {color_estado}; padding-left: 1rem; margin-bottom: 1rem;">
                            <h4 style="margin: 0;">{emoji_cat} {idea['titulo']}</h4>
                            <p style="color: #8b949e; margin: 0.25rem 0; font-size: 0.875rem;">
                                {idea['categoria'].replace('_', ' ')} • 
                                {'⭐' * idea['complejidad']}{'○' * (5-idea['complejidad'])} • 
                                <span style="color: {color_estado};">{idea['estado']}</span>
                            </p>
                            <p style="margin: 0.5rem 0;">{idea['descripcion'] or 'Sin descripción'}</p>
                            <p style="color: #8b949e; font-size: 0.75rem;">
                                Tech: {', '.join(json.loads(idea['tecnologias'])) if idea['tecnologias'] else 'Ninguna'}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col_motiv:
                        st.metric("Motivación", f"{idea['motivacion']}/10")
                        st.progress(idea['motivacion'] / 10)

# ═════════════════════════════════════════════════════════════════
# TAB 2: SNIPPETS DE CÓDIGO
# ═════════════════════════════════════════════════════════════════

with tab_snippets:
    col_filtros, col_codigo = st.columns([1, 3])
    
    with col_filtros:
        st.markdown("### 🔍 Filtrar")
        filtro_lang = st.selectbox("Lenguaje", ["Todos", "Python", "JavaScript", "HTML_CSS", "SQL", "Bash"], key="filtro_lang_snip")
        
        st.divider()
        st.markdown("### ➕ Nuevo snippet")
        with st.form("nuevo_snippet", clear_on_submit=True):
            titulo = st.text_input("Título", placeholder="Ej: Leer PDFs recursivamente")
            lang = st.selectbox("Lenguaje", ["Python", "JavaScript", "HTML_CSS", "SQL", "Bash", "Markdown"])
            codigo = st.text_area("Código", height=150, placeholder="# Tu código aquí...")
            desc = st.text_area("Descripción", height=60)
            tags = st.text_input("Tags (separados por coma)", placeholder="pandas, pathlib, pdf")
            
            if st.form_submit_button("💾 Guardar snippet"):
                # Aquí guardarías en BD
                st.success("✅ Snippet guardado")
    
    with col_codigo:
        st.markdown("### 🧩 Tu biblioteca de código")
        
        lang_filtro = None if filtro_lang == "Todos" else filtro_lang
        snippets = obtener_snippets(lang_filtro)
        
        if not snippets:
            st.info("📝 No hay snippets. ¡Agrega el primero!")
        else:
            for s in snippets:
                emoji_lang = {
                    'Python': '🐍',
                    'JavaScript': '⚡',
                    'HTML_CSS': '🎨',
                    'SQL': '🗄️',
                    'Bash': '💻',
                    'Markdown': '📝'
                }.get(s['lenguaje'], '💻')
                
                with st.expander(f"{emoji_lang} {s['titulo']} ({s['veces_usado']} usos)"):
                    st.code(s['codigo'], language=s['lenguaje'].lower().replace('_', ''))
                    st.caption(s['descripcion'] or 'Sin descripción')
                    if s['tags']:
                        st.caption(f"Tags: {', '.join(json.loads(s['tags']))}")

# ═════════════════════════════════════════════════════════════════
# TAB 3: REGISTRAR SESIÓN DE EXPERIMENTACIÓN
# ═════════════════════════════════════════════════════════════════

with tab_sesion:
    st.markdown("### ⏱️ Registrar sesión de experimentación")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fecha = st.date_input("Fecha", value=date.today())
        hora_inicio = st.time_input("Hora inicio", value=datetime.now().time())
        duracion = st.slider("Duración (minutos)", 15, 180, 60, step=15)
        
        tipo_actividad = st.selectbox(
            "Tipo de actividad",
            ["Investigando", "Codificando", "Depurando", "Aprendiendo", "Documentando"]
        )
        
        # Seleccionar proyecto relacionado (opcional)
        ideas = obtener_ideas()
        proyecto_opciones = [(None, "Sin proyecto específico")] + [(i['id'], i['titulo']) for i in ideas]
        proyecto_id = st.selectbox(
            "Proyecto relacionado",
            options=[p[0] for p in proyecto_opciones],
            format_func=lambda x: next(p[1] for p in proyecto_opciones if p[0] == x)
        )
    
    with col2:
        descripcion = st.text_area(
            "¿Qué hiciste?",
            height=120,
            placeholder="Ej: Estuve investigando cómo leer metadatos de PDFs con PyPDF2. Encontré que..."
        )
        
        codigo_producido = st.text_area(
            "Código producido (opcional)",
            height=150,
            placeholder="# Pega aquí el código que salió de esta sesión..."
        )
        
        satisfaccion = st.slider("Satisfacción con la sesión", 1, 10, 7)
        
        if st.button("💾 Guardar sesión", use_container_width=True, type="primary"):
            guardar_sesion(fecha, duracion, tipo_actividad, proyecto_id, descripcion, codigo_producido, satisfaccion)
            st.success("✅ Sesión registrada. ¡Sigue experimentando!")
            st.balloons()

# ═════════════════════════════════════════════════════════════════
# TAB 4: IA MENTOR - Ayuda con proyectos
# ═════════════════════════════════════════════════════════════════

with tab_ia:
    st.markdown("### 🤖 IA Mentor para tus proyectos")
    
    if not api_key_configurada():
        st.warning("⚠️ IA no configurada. Usando modo offline.")
        st.info("Los prompts funcionarán con respuestas predefinidas útiles.")
    
    col_contexto, col_chat = st.columns([1, 2])
    
    with col_contexto:
        st.markdown("**🎯 Contexto del proyecto**")
        
        ideas = obtener_ideas()
        if ideas:
            idea_seleccionada = st.selectbox(
                "Seleccionar idea",
                options=[i['id'] for i in ideas],
                format_func=lambda x: next(i['titulo'] for i in ideas if i['id'] == x)
            )
            idea = next(i for i in ideas if i['id'] == idea_seleccionada)
            
            st.markdown(f"""
            **{idea['titulo']}**
            
            - Categoría: {idea['categoria'].replace('_', ' ')}
            - Complejidad: {'⭐' * idea['complejidad']}
            - Tecnologías: {', '.join(json.loads(idea['tecnologias'])) if idea['tecnologias'] else 'Ninguna'}
            """)
            
            contexto_ia = f"Proyecto: {idea['titulo']}. Descripción: {idea['descripcion']}. Tecnologías: {idea['tecnologias']}"
        else:
            st.info("Sin ideas registradas")
            contexto_ia = "General"
        
        tipo_ayuda = st.selectbox(
            "Tipo de ayuda",
            ["Planificar pasos", "Sugerir librerías", "Revisar enfoque", "Depurar error", "Inspiración"]
        )
    
    with col_chat:
        st.markdown("**💬 Chat con mentor IA**")
        
        prompt_base = {
            "Planificar pasos": f"Planifica los próximos 3 pasos concretos para avanzar en: {contexto_ia}",
            "Sugerir librerías": f"Sugiere 2-3 librerías Python específicas para: {contexto_ia}, con pros/contras breves",
            "Revisar enfoque": f"Revisa este enfoque técnico. ¿Hay alternativas más simples?: {contexto_ia}",
            "Depurar error": "Describe tu error y te ayudo a depurar",
            "Inspiración": f"Dame una idea creativa relacionada con: {contexto_ia}"
        }
        
        prompt_usuario = st.text_area(
            "Tu pregunta o contexto adicional",
            height=100,
            placeholder="Ej: No sé por dónde empezar con el script de PDFs..."
        )
        
        if st.button("🚀 Preguntar a mentor", use_container_width=True):
            prompt_completo = f"{prompt_base[tipo_ayuda]}\n\nContexto adicional del usuario: {prompt_usuario}"
            
            with st.spinner("Mentor pensando..."):
                respuesta = chat_simple(prompt_completo, contexto="Eres un mentor técnico experimentado en Python, desarrollo web y ciencia de datos. Das consejos prácticos, concretos y alentadores.")
                st.info(respuesta)

st.divider()
st.caption("🧪 Sandbox • Experimentar, fallar, aprender, repetir")