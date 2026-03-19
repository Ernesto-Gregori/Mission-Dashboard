"""
📚 Biblioteca Digital - Sistema con IA + Resaltados personales
Flujo: Subir → IA procesa → Revisar → Guardar → Agregar resaltados
"""

import streamlit as st
from datetime import date, datetime
import json
import hashlib
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, DB_PATH
import sqlite3

st.set_page_config(
    page_title="Biblioteca | Mission Dashboard",
    page_icon="📚",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .estado-por_procesar { border-left: 4px solid #8b949e; opacity: 0.7; }
    .estado-catalogado { border-left: 4px solid #58a6ff; }
    .estado-leyendo { border-left: 4px solid #e3b341; border: 1px solid #e3b341; }
    .estado-completado { border-left: 4px solid #3fb950; }
    
    .resaltado-amarillo { background: rgba(227, 179, 65, 0.15); border-left: 3px solid #e3b341; }
    .resaltado-verde { background: rgba(63, 185, 80, 0.15); border-left: 3px solid #3fb950; }
    .resaltado-azul { background: rgba(88, 166, 255, 0.15); border-left: 3px solid #58a6ff; }
    .resaltado-rosa { background: rgba(247, 120, 186, 0.15); border-left: 3px solid #f778ba; }
    .resaltado-morado { background: rgba(163, 113, 247, 0.15); border-left: 3px solid #a371f7; }
    
    .libro-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    .progreso-paginas {
        background: #21262d;
        border-radius: 6px;
        height: 8px;
    }
    .progreso-fill {
        background: linear-gradient(90deg, #58a6ff, #3fb950);
        height: 100%;
        border-radius: 6px;
    }
    
    .badge-color {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def agregar_libro_por_procesar(nombre_archivo, ruta, tamano, formato, hash_archivo):
    """Paso 1: Subir archivo, estado 'por_procesar'"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Usar nombre_archivo como título temporal (limpio)
    titulo_temp = nombre_archivo.replace(f'.{formato.lower()}', '').replace('_', ' ').title()
    
    cursor.execute("""
        INSERT INTO libros (titulo, nombre_archivo, ruta_archivo, tamano_mb, formato, hash_archivo, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'por_procesar')
    """, (titulo_temp, nombre_archivo, ruta, tamano, formato, hash_archivo))
    
    libro_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return libro_id

def obtener_libro(libro_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM libros WHERE id = ?", (libro_id,))
    row = cursor.fetchone()
    libro = dict(row) if row else None
    conn.close()
    return libro

def obtener_libros_por_estado(estado=None, categoria=None, color=None, busqueda=""):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM libros WHERE 1=1"
    params = []
    
    if estado:
        query += " AND estado = ?"
        params.append(estado)
    if categoria:
        query += " AND categoria_principal = ?"
        params.append(categoria)
    if color:
        query += " AND color_liquidtext = ?"
        params.append(color)
    if busqueda:
        query += " AND (titulo LIKE ? OR autor LIKE ? OR descripcion LIKE ?)"
        params.extend([f"%{busqueda}%"] * 3)
    
    query += " ORDER BY creado_en DESC"
    
    cursor.execute(query, params)
    libros = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return libros

def guardar_metadatos_ia(libro_id, metadatos):
    """Paso 3: Guardar metadatos revisados (después de previsualización)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Campos que actualizamos explícitamente
    campos_actualizar = {
        'titulo': metadatos.get('titulo'),
        'autor': metadatos.get('autor'),
        'isbn': metadatos.get('isbn'),
        'editorial': metadatos.get('editorial'),
        'anio_publicacion': metadatos.get('anio_publicacion'),
        'categoria_principal': metadatos.get('categoria_principal'),
        'total_paginas': metadatos.get('total_paginas'),
        'descripcion': metadatos.get('descripcion'),
        'indice': metadatos.get('indice'),
        'subcategorias': metadatos.get('subcategorias', json.dumps([])),
        'temas_clave': metadatos.get('temas_clave', json.dumps([])),
        'autores_adicionales': metadatos.get('autores_adicionales', json.dumps([])),
        'notas_bibliotecaria': metadatos.get('notas_bibliotecaria', ''),
        'fuente_metadatos': metadatos.get('fuente_metadatos', 'IA'),
        'confianza_ia': metadatos.get('confianza_ia', 5),
        'estado': 'catalogado',
        'revisado_manual': 1,
        'actualizado_en': datetime.now().isoformat()
    }
    
    # Construir query dinámicamente
    set_clause = ", ".join(f"{k} = ?" for k in campos_actualizar.keys())
    valores = list(campos_actualizar.values())
    
    cursor.execute(
        f"UPDATE libros SET {set_clause} WHERE id = ?",
        valores + [libro_id]
    )
    
    conn.commit()
    conn.close()

def actualizar_progreso(libro_id, pagina_actual, estado=None):
    """Actualiza la página actual y opcionalmente el estado del libro"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if estado:
        cursor.execute("""
            UPDATE libros 
            SET pagina_actual = ?, estado = ?, actualizado_en = ?
            WHERE id = ?
        """, (pagina_actual, estado, datetime.now().isoformat(), libro_id))
    else:
        cursor.execute("""
            UPDATE libros 
            SET pagina_actual = ?, actualizado_en = ?
            WHERE id = ?
        """, (pagina_actual, datetime.now().isoformat(), libro_id))
    
    conn.commit()
    conn.close()

def agregar_resaltado(libro_id, pagina, texto_resaltado, color_etiqueta, nota_personal="", texto_contexto=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO resaltados (libro_id, pagina, texto_resaltado, color_etiqueta, nota_personal, texto_contexto)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (libro_id, pagina, texto_resaltado, color_etiqueta, nota_personal, texto_contexto))
    resaltado_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return resaltado_id

def obtener_resaltados(libro_id, color=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if color:
        cursor.execute("""
            SELECT * FROM resaltados WHERE libro_id = ? AND color_etiqueta = ?
            ORDER BY pagina, creado_en
        """, (libro_id, color))
    else:
        cursor.execute("""
            SELECT * FROM resaltados WHERE libro_id = ?
            ORDER BY pagina, creado_en
        """, (libro_id,))
    
    resaltados = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return resaltados

# ═══════════════════════════════════════════════════════════════
# SIMULACIÓN DE IA
# ═══════════════════════════════════════════════════════════════

def simular_extraccion_ia(nombre_archivo, formato):
    """SIMULACIÓN: En producción, esto llamaría a Gemini Vision/PDF"""
    if "python" in nombre_archivo.lower() or "programming" in nombre_archivo.lower():
        return {
            'titulo': 'Python Crash Course',
            'subtitulo': 'A Hands-On, Project-Based Introduction to Programming',
            'autor': 'Eric Matthes',
            'autores_adicionales': json.dumps([]),
            'editorial': 'No Starch Press',
            'anio_publicacion': 2019,
            'edicion': '2nd Edition',
            'idioma': 'en',
            'categoria_principal': 'Programacion',
            'subcategorias': json.dumps(['Python', 'Desarrollo Web', 'Ciencia de Datos']),
            'temas_clave': json.dumps(['Python 3', 'Django', 'Matplotlib', 'Pygame']),
            'descripcion': 'Libro práctico para aprender Python desde cero con proyectos reales incluyendo visualización de datos, desarrollo web y videojuegos.',
            'indice': '1. Basics\n2. Lists and Dictionaries\n3. if Statements\n4. Dictionaries\n5. User Input and while Loops\n6. Functions\n7. Classes\n8. Files and Exceptions\n9. Testing Your Code\n10. Project: Alien Invasion\n11. Project: Data Visualization\n12. Project: Web Applications',
            'notas_bibliotecaria': 'Excelente para principiantes. Proyectos prácticos bien estructurados.',
            'total_paginas': 544,
            'fuente_metadatos': 'IA',
            'confianza_ia': 8,
            'isbn': '978-1593279288'
        }
    elif "theology" in nombre_archivo.lower() or "grudem" in nombre_archivo.lower():
        return {
            'titulo': 'Systematic Theology',
            'subtitulo': 'An Introduction to Biblical Doctrine',
            'autor': 'Wayne A. Grudem',
            'autores_adicionales': json.dumps([]),
            'editorial': 'Zondervan',
            'anio_publicacion': 1994,
            'edicion': '1st Edition',
            'idioma': 'en',
            'categoria_principal': 'Teologia',
            'subcategorias': json.dumps(['Teologia Sistematica', 'Doctrina Biblica', 'Presbiteriana']),
            'temas_clave': json.dumps(['Dios', 'Creacion', 'Pecado', 'Cristo', 'Salvacion', 'Iglesia', 'Escatologia']),
            'descripcion': 'Obra magistral de teología sistemática que aborda todas las doctrinas principales desde una perspectiva bíblica y evangélica.',
            'indice': 'Part 1: The Doctrine of the Word of God\nPart 2: The Doctrine of God\nPart 3: The Doctrine of Man\nPart 4: The Doctrines of Christ and the Holy Spirit\nPart 5: The Doctrine of the Application of Redemption\nPart 6: The Doctrine of the Church\nPart 7: The Doctrine of the Future',
            'notas_bibliotecaria': 'Texto estándar en seminarios. Requiere lectura cuidadosa. Recomendado para Instituto Bíblico.',
            'total_paginas': 1291,
            'fuente_metadatos': 'IA',
            'confianza_ia': 9,
            'isbn': '978-0310286707'
        }
    else:
        return {
            'titulo': nombre_archivo.replace(f'.{formato}', '').replace('_', ' ').title(),
            'subtitulo': None,
            'autor': 'Desconocido',
            'autores_adicionales': json.dumps([]),
            'editorial': None,
            'anio_publicacion': None,
            'edicion': None,
            'idioma': 'es',
            'categoria_principal': 'Otros',
            'subcategorias': json.dumps([]),
            'temas_clave': json.dumps([]),
            'descripcion': 'No se pudo extraer descripción automáticamente. Por favor completar manualmente.',
            'indice': None,
            'notas_bibliotecaria': 'Metadatos incompletos. Requiere revisión manual.',
            'total_paginas': None,
            'fuente_metadatos': 'IA',
            'confianza_ia': 3,
            'isbn': None
        }

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("📚 Biblioteca Digital")
st.caption("Catalogación con IA + Sistema de resaltados personal")

# ═══════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN
# ═══════════════════════════════════════════════════════════════

if 'libro_en_proceso' not in st.session_state:
    st.session_state.libro_en_proceso = None
if 'metadatos_propuestos' not in st.session_state:
    st.session_state.metadatos_propuestos = None
if 'libro_para_resaltar' not in st.session_state:
    st.session_state.libro_para_resaltar = None

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Estadísticas")
    
    todos = obtener_libros_por_estado()
    por_procesar = len([l for l in todos if l['estado'] == 'por_procesar'])
    catalogados = len([l for l in todos if l['estado'] == 'catalogado'])
    leyendo = len([l for l in todos if l['estado'] == 'leyendo'])
    completados = len([l for l in todos if l['estado'] == 'completado'])
    
    col1, col2 = st.columns(2)
    col1.metric("Total", len(todos))
    col2.metric("Por procesar", por_procesar)
    
    st.metric("En lectura", leyendo)
    st.metric("Completados", completados)
    
    st.divider()
    st.caption("🤖 Integración Gemini: Próximamente")

# ═══════════════════════════════════════════════════════════════
# TABS PRINCIPALES
# ═══════════════════════════════════════════════════════════════

tab_cargar, tab_catalogo, tab_leyendo, tab_resaltados = st.tabs([
    "➕ Cargar Nuevo", "📚 Catálogo", "🔥 En Lectura", "🎨 Mis Resaltados"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: CARGAR NUEVO
# ═══════════════════════════════════════════════════════════════

with tab_cargar:
    st.subheader("Cargar nuevo libro")
    
    if not st.session_state.libro_en_proceso:
        st.markdown("### Paso 1: Seleccionar archivo")
        
        metodo = st.radio("Método de entrada", ["Subir PDF", "ISBN (próximamente)", "Manual"], horizontal=True)
        
        if metodo == "Subir PDF":
            archivo = st.file_uploader("Seleccionar archivo", type=['pdf', 'epub', 'mobi'])
            
            if archivo:
                contenido = archivo.getvalue()
                hash_archivo = hashlib.md5(contenido).hexdigest()[:16]
                
                existentes = obtener_libros_por_estado()
                duplicado = next((l for l in existentes if l['hash_archivo'] == hash_archivo), None)
                
                if duplicado:
                    st.error(f"⚠️ Este archivo ya existe: **{duplicado['titulo'] or duplicado['nombre_archivo']}**")
                else:
                    extension = archivo.name.split('.')[-1].upper()
                    tamano = len(contenido) / (1024 * 1024)
                    ruta_temp = f"./biblioteca_temp/{archivo.name}"
                    
                    libro_id = agregar_libro_por_procesar(
                        archivo.name, ruta_temp, round(tamano, 2), extension, hash_archivo
                    )
                    
                    st.session_state.libro_en_proceso = libro_id
                    st.rerun()
        
        elif metodo == "Manual":
            with st.form("manual_entry"):
                titulo = st.text_input("Título *", placeholder="Nombre del libro")
                autor = st.text_input("Autor", placeholder="Autor principal")
                col_cat, col_pag = st.columns(2)
                with col_cat:
                    categoria = st.selectbox("Categoría", ["Teologia", "Programacion", "Matrimonio", "Filosofia", "Liderazgo", "Historia", "Otros"])
                with col_pag:
                    paginas = st.number_input("Total páginas", min_value=1, value=200)
                
                descripcion = st.text_area("Descripción / Sinopsis")
                
                submitted = st.form_submit_button("💾 Guardar básico", use_container_width=True)
                
                if submitted and titulo:
                    metadatos = {
                        'titulo': titulo,
                        'autor': autor or 'Desconocido',
                        'categoria_principal': categoria,
                        'descripcion': descripcion,
                        'total_paginas': paginas,
                        'fuente_metadatos': 'Manual',
                        'confianza_ia': 10,
                        'subcategorias': json.dumps([]),
                        'temas_clave': json.dumps([]),
                        'autores_adicionales': json.dumps([]),
                        'notas_bibliotecaria': 'Ingresado manualmente'
                    }
                    libro_id = agregar_libro_por_procesar(f"{titulo}.manual", "manual", 0, "Otro", "manual")
                    guardar_metadatos_ia(libro_id, metadatos)
                    st.success("✅ Libro guardado")
                    st.rerun()
    
    elif st.session_state.libro_en_proceso and not st.session_state.metadatos_propuestos:
        st.markdown("### Paso 2: Bibliotecaria IA analizando...")
        
        libro = obtener_libro(st.session_state.libro_en_proceso)
        
        with st.spinner("🔍 Extrayendo metadatos con IA..."):
            import time
            time.sleep(1.5)
            
            metadatos = simular_extraccion_ia(libro['nombre_archivo'], libro['formato'])
            st.session_state.metadatos_propuestos = metadatos
            st.rerun()
    
    elif st.session_state.metadatos_propuestos:
        st.markdown("### Paso 3: Revisar y confirmar")
        
        meta = st.session_state.metadatos_propuestos
        
        confianza = meta.get('confianza_ia', 5)
        color_conf = "#3fb950" if confianza >= 7 else "#e3b341" if confianza >= 5 else "#f85149"
        
        st.markdown(f"""
        <div style="background: #161b22; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span>🤖 Confianza de la IA:</span>
                <span style="color: {color_conf}; font-weight: bold;">{confianza}/10</span>
            </div>
            <div style="background: #21262d; height: 6px; border-radius: 3px; margin-top: 0.5rem;">
                <div style="background: {color_conf}; width: {confianza * 10}%; height: 100%; border-radius: 3px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("revisar_metadatos"):
            col1, col2 = st.columns(2)
            
            with col1:
                titulo_final = st.text_input("Título *", value=meta.get('titulo', ''))
                autor_final = st.text_input("Autor", value=meta.get('autor', ''))
                isbn_final = st.text_input("ISBN", value=meta.get('isbn', '') or '')
                editorial_final = st.text_input("Editorial", value=meta.get('editorial', '') or '')
            
            with col2:
                categoria_final = st.selectbox(
                    "Categoría principal",
                    ["Teologia", "Programacion", "Matrimonio", "Filosofia", "Liderazgo", "Historia", "Otros"],
                    index=["Teologia", "Programacion", "Matrimonio", "Filosofia", "Liderazgo", "Historia", "Otros"].index(meta.get('categoria_principal', 'Otros')) if meta.get('categoria_principal') in ["Teologia", "Programacion", "Matrimonio", "Filosofia", "Liderazgo", "Historia", "Otros"] else 6
                )
                anio_final = st.number_input("Año", min_value=1000, max_value=2030, value=meta.get('anio_publicacion') or 2020)
                paginas_final = st.number_input("Total páginas", min_value=1, value=meta.get('total_paginas') or 100)
            
            descripcion_final = st.text_area("Descripción / Sinopsis", value=meta.get('descripcion', ''), height=100)
            
            with st.expander("Ver índice detectado"):
                indice_final = st.text_area("Índice", value=meta.get('indice', '') or '', height=150)
            
            col_guardar, col_cancelar = st.columns(2)
            
            with col_guardar:
                guardar = st.form_submit_button("✅ Guardar en biblioteca", use_container_width=True, type="primary")
            
            with col_cancelar:
                cancelar = st.form_submit_button("❌ Cancelar", use_container_width=True)
            
            if guardar:
                metadatos_finales = {
                    'titulo': titulo_final,
                    'autor': autor_final,
                    'isbn': isbn_final,
                    'editorial': editorial_final,
                    'anio_publicacion': anio_final,
                    'categoria_principal': categoria_final,
                    'total_paginas': paginas_final,
                    'descripcion': descripcion_final,
                    'indice': indice_final,
                    **{k: v for k, v in meta.items() if k not in ['titulo', 'autor', 'isbn', 'editorial', 'anio_publicacion', 'categoria_principal', 'total_paginas', 'descripcion', 'indice']}
                }
                
                guardar_metadatos_ia(st.session_state.libro_en_proceso, metadatos_finales)
                
                st.session_state.libro_en_proceso = None
                st.session_state.metadatos_propuestos = None
                
                st.success("✅ Libro catalogado correctamente")
                st.rerun()
            
            if cancelar:
                st.session_state.libro_en_proceso = None
                st.session_state.metadatos_propuestos = None
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: CATÁLOGO - SIN HTML, SOLO COMPONENTES NATIVOS
# ═══════════════════════════════════════════════════════════════

with tab_catalogo:
    st.subheader("Todos los libros")
    
    # FILTROS
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_estado = st.selectbox("Filtrar por estado", ["Todos", "por_procesar", "catalogado", "leyendo", "completado", "pausado"], key="filtro_estado_cat")
    with col_f2:
        filtro_categoria = st.selectbox("Categoría", ["Todas", "Teologia", "Programacion", "Matrimonio", "Filosofia", "Liderazgo", "Historia", "Otros"], key="filtro_categoria_cat")
    with col_f3:
        filtro_color = st.selectbox("Color LiquidText", ["Todos", "Ninguno", "Amarillo", "Verde", "Morado", "Rosa", "Azul"], key="filtro_color_cat")
    
    busqueda = st.text_input("Buscar", placeholder="Título, autor, descripción...", key="busqueda_cat")
    
    # Aplicar filtros
    estado_filtro = None if filtro_estado == "Todos" else filtro_estado
    categoria_filtro = None if filtro_categoria == "Todas" else filtro_categoria
    color_filtro = None if filtro_color == "Todos" else filtro_color
    
    libros = obtener_libros_por_estado(estado_filtro, categoria_filtro, color_filtro, busqueda)
    
    if not libros:
        st.info("📭 No se encontraron libros con estos filtros")
    else:
        st.write(f"**{len(libros)} libros encontrados**")
        
        for libro in libros:
            # Emoji según estado
            emoji_estado = {
                'por_procesar': '⏳',
                'catalogado': '📚',
                'leyendo': '🔥',
                'pausado': '⏸️',
                'completado': '✅',
                'abandonado': '🗑️'
            }.get(libro['estado'], '📖')
            
            # Calcular progreso
            pag_actual = libro['pagina_actual'] or 0
            total = libro['total_paginas'] or 0
            progreso_pct = min(100, int(pag_actual / total * 100)) if total > 0 else 0
            
            # CARD NATIVA DE STREAMLIT
            with st.container():
                # Header con emoji, título y estado
                col_header, col_estado = st.columns([6, 1])
                with col_header:
                    st.markdown(f"### {emoji_estado} {libro['titulo'] or 'Sin título'}")
                with col_estado:
                    st.caption(libro['estado'].replace('_', ' '))
                
                # Info del libro
                st.caption(f"**{libro['autor'] or 'Autor desconocido'}** • {libro['categoria_principal'] or 'Sin categoría'}")
                
                # Descripción
                descripcion = libro['descripcion'] or 'Sin descripción'
                if len(descripcion) > 120:
                    descripcion = descripcion[:120] + '...'
                st.write(descripcion)
                
                # Barra de progreso nativa de Streamlit
                st.progress(progreso_pct / 100, text=f"{pag_actual} / {total if total > 0 else '?'} páginas ({progreso_pct}%)")
                
                # Botón de acción
                if libro['estado'] in ['catalogado', 'leyendo', 'pausado']:
                    with st.expander("▶️ Actualizar progreso"):
                        key_base = f"cat_{libro['id']}"
                        
                        nueva_pagina = st.number_input(
                            "Página actual",
                            min_value=0,
                            max_value=total or 9999,
                            value=pag_actual,
                            key=f"pag_{key_base}"
                        )
                        
                        nuevo_estado = st.selectbox(
                            "Estado",
                            ['leyendo', 'pausado', 'completado', 'abandonado'],
                            index=['leyendo', 'pausado', 'completado', 'abandonado'].index(libro['estado']) if libro['estado'] in ['leyendo', 'pausado', 'completado', 'abandonado'] else 0,
                            key=f"est_{key_base}"
                        )
                        
                        if st.button("💾 Guardar", key=f"upd_{key_base}"):
                            actualizar_progreso(libro['id'], nueva_pagina, nuevo_estado)
                            st.success("✅ Progreso guardado")
                            st.rerun()
                
                st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 3: EN LECTURA - SIN HTML
# ═══════════════════════════════════════════════════════════════

with tab_leyendo:
    st.subheader("Lectura activa")
    
    libros_leyendo = obtener_libros_por_estado("leyendo")
    
    if not libros_leyendo:
        st.info("🔥 No hay libros en lectura activa. Marca uno como 'leyendo' desde el catálogo.")
    else:
        for libro in libros_leyendo:
            pag_actual = libro['pagina_actual'] or 0
            total = libro['total_paginas'] or 1
            progreso = min(100, int(pag_actual / total * 100))
            
            pag_restantes = total - pag_actual
            dias_estimados = max(1, pag_restantes // 20)
            
            # Layout de 3 columnas
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                st.metric("Progreso", f"{progreso}%")
                st.metric("Página", f"{pag_actual}/{total}")
                st.caption(f"~{dias_estimados} días a 20 pág/día")
            
            with col2:
                st.markdown(f"### 🔥 {libro['titulo'] or 'Sin título'}")
                st.caption(f"*{libro['autor'] or 'Autor desconocido'}*")
                st.progress(progreso / 100, text=f"{pag_actual} / {total} páginas")
            
            with col3:
                if st.button("✏️ Agregar resaltado", key=f"res_{libro['id']}", use_container_width=True):
                    st.session_state['libro_para_resaltar'] = libro['id']
                    st.rerun()
            
            st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 4: MIS RESALTADOS
# ═══════════════════════════════════════════════════════════════

with tab_resaltados:
    st.subheader("Sistema de resaltados")
    
    libros_disponibles = obtener_libros_por_estado()
    libros_con_id = [(l['id'], f"{l['titulo'] or 'Sin título'} - {l['autor'] or 'Desconocido'}") for l in libros_disponibles if l['estado'] != 'por_procesar']
    
    if not libros_con_id:
        st.info("📚 Primero debes catalogar libros para agregar resaltados")
    else:
        default_index = 0
        if 'libro_para_resaltar' in st.session_state and st.session_state['libro_para_resaltar']:
            idx = next((i for i, (lid, _) in enumerate(libros_con_id) if lid == st.session_state['libro_para_resaltar']), 0)
            default_index = idx
            st.session_state['libro_para_resaltar'] = None
        
        libro_seleccionado = st.selectbox(
            "Seleccionar libro",
            options=[l[0] for l in libros_con_id],
            format_func=lambda x: next(l[1] for l in libros_con_id if l[0] == x),
            index=default_index,
            key="sel_libro_res"
        )
        
        libro_actual = obtener_libro(libro_seleccionado)
        
        col_form, col_lista = st.columns([1, 2])
        
        with col_form:
            st.markdown("### ➕ Nuevo resaltado")
            
            with st.form("nuevo_resaltado", clear_on_submit=True):
                pagina_res = st.number_input(
                    "Página",
                    min_value=1,
                    max_value=libro_actual['total_paginas'] or 9999,
                    value=libro_actual['pagina_actual'] or 1
                )
                
                color_res = st.selectbox(
                    "Color / Tipo",
                    [
                        ("Amarillo", "🟡 Concepto clave"),
                        ("Verde", "🟢 Aplicación práctica"),
                        ("Azul", "🔵 Duda / Investigar"),
                        ("Rosa", "🩷 Cita importante"),
                        ("Morado", "🟣 Idea propia")
                    ],
                    format_func=lambda x: x[1],
                    key="color_res"
                )[0]
                
                texto_res = st.text_area(
                    "Texto resaltado *",
                    placeholder="Copia aquí el texto que resaltaste...",
                    height=100
                )
                
                contexto_res = st.text_area(
                    "Contexto (opcional)",
                    placeholder="Párrafo completo para recordar el contexto...",
                    height=80
                )
                
                nota_res = st.text_area(
                    "Tu nota personal",
                    placeholder="¿Por qué es importante? ¿Qué conexión hiciste?",
                    height=80
                )
                
                submitted = st.form_submit_button("💾 Guardar resaltado", use_container_width=True)
                
                if submitted and texto_res.strip():
                    agregar_resaltado(
                        libro_seleccionado,
                        pagina_res,
                        texto_res.strip(),
                        color_res,
                        nota_res,
                        contexto_res
                    )
                    st.success("✅ Resaltado guardado")
                    st.rerun()
        
        with col_lista:
            st.markdown(f"### 📑 Resaltados de: **{libro_actual['titulo'] or 'Sin título'}**")
            
            filtro_color_res = st.selectbox(
                "Filtrar por color",
                ["Todos", "Amarillo", "Verde", "Azul", "Rosa", "Morado"],
                key="filtro_res"
            )
            
            color_filtro = None if filtro_color_res == "Todos" else filtro_color_res
            resaltados = obtener_resaltados(libro_seleccionado, color_filtro)
            
            if not resaltados:
                st.info("📝 Aún no tienes resaltados en este libro")
            else:
                por_color = {}
                for r in resaltados:
                    por_color[r['color_etiqueta']] = por_color.get(r['color_etiqueta'], 0) + 1
                
                cols_stat = st.columns(len(por_color) if por_color else 1)
                for (color, cantidad), col in zip(por_color.items(), cols_stat):
                    emoji_color = {"Amarillo":"🟡","Verde":"🟢","Azul":"🔵","Rosa":"🩷","Morado":"🟣"}.get(color, "⚪")
                    col.metric(f"{emoji_color} {color}", cantidad)
                
                st.divider()
                
                for res in resaltados:
                    clase_css = f"resaltado-{res['color_etiqueta'].lower()}"
                    emoji = {"Amarillo":"🟡","Verde":"🟢","Azul":"🔵","Rosa":"🩷","Morado":"🟣"}.get(res['color_etiqueta'], "⚪")
                    
                    st.markdown(f"""
                    <div class="{clase_css}" style="padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem;">
                        <div style="font-size: 0.75rem; color: #58a6ff; margin-bottom: 0.25rem;">
                            📚 {libro_actual['titulo']} • Pág. {res['pagina']}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <span>{emoji} <strong>Pág. {res['pagina']}</strong></span>
                            <span style="font-size: 0.75rem; color: #8b949e;">{res['fecha_resaltado']}</span>
                        </div>
                        <div style="color: #f0f6fc; font-style: italic; margin-bottom: 0.5rem;">
                            "{res['texto_resaltado'][:200]}{'...' if len(res['texto_resaltado']) > 200 else ''}"
                        </div>
                        {f'<div style="color: #8b949e; font-size: 0.875rem; margin-top: 0.5rem;">📝 {res["nota_personal"]}</div>' if res['nota_personal'] else ''}
                    </div>
                    """, unsafe_allow_html=True)

st.divider()
st.caption("📚 Biblioteca Digital • IA + Resaltados personales")