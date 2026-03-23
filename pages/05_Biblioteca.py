"""
📚 Biblioteca Digital - Sistema con IA + Resaltados personales
Flujo: Subir → IA procesa → Revisar → Guardar → Agregar resaltados
"""

import sys
from pathlib import Path
from datetime import date, datetime
import json
import hashlib
import sqlite3

# Agregar app al path PRIMERO
sys.path.append(str(Path(__file__).parent.parent))

# Imports de la aplicación
from app.database import init_database, DB_PATH
from app.ai_client import (
    extraer_metadatos_libro, 
    buscar_metadatos_isbn,
    verificar_conexion,
    estado_gemini,
    api_key_configurada
)

# Streamlit al final
import streamlit as st

# ═════════════════════════════════════════════════════════════════
# CONFIGURACIÓN STREAMLIT
# ═════════════════════════════════════════════════════════════════

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

def agregar_libro_por_procesar(nombre_archivo, ruta,
                                tamano, formato, hash_archivo):
    from app.database import ejecutar

    titulo_temp = (nombre_archivo
                   .replace(f'.{formato.lower()}', '')
                   .replace('_', ' ')
                   .title())

    libro_id = ejecutar("""
        INSERT INTO libros
            (titulo, nombre_archivo, ruta_archivo,
             tamano_mb, formato, hash_archivo, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'por_procesar')
    """, [titulo_temp, nombre_archivo, ruta,
          tamano, formato, hash_archivo])

    return libro_id

def obtener_libro(libro_id):
    from app.database import ejecutar
    rows = ejecutar(
        "SELECT * FROM libros WHERE id = ?",
        [libro_id], fetchall=True
    )
    return rows[0] if rows else None

def obtener_libros_por_estado(estado=None, categoria=None,
                               color=None, busqueda="",
                               pagina=1, por_pagina=10):
    from app.database import ejecutar

    # ── Construir WHERE dinámico ───────────────────────────
    conditions = ["1=1"]
    params     = []

    if estado:
        conditions.append("estado = ?")
        params.append(estado)
    if categoria:
        conditions.append("categoria_principal = ?")
        params.append(categoria)
    if color:
        conditions.append("color_liquidtext = ?")
        params.append(color)
    if busqueda:
        termino = f"%{busqueda}%"
        conditions.append("""(
            titulo        LIKE ? OR
            autor         LIKE ? OR
            descripcion   LIKE ? OR
            temas_clave   LIKE ? OR
            subcategorias LIKE ?
        )""")
        params.extend([termino] * 5)

    where = " AND ".join(conditions)

    # ── Total ──────────────────────────────────────────────
    total_rows = ejecutar(
        f"SELECT COUNT(*) as total FROM libros WHERE {where}",
        params, fetchall=True
    )
    total = total_rows[0]['total'] if total_rows else 0

    # ── Paginación ─────────────────────────────────────────
    offset = (pagina - 1) * por_pagina
    libros = ejecutar(
        f"""SELECT * FROM libros WHERE {where}
            ORDER BY creado_en DESC LIMIT ? OFFSET ?""",
        params + [por_pagina, offset],
        fetchall=True
    )

    return libros, total

def guardar_metadatos_ia(libro_id, metadatos):
    """Paso 3: Guardar metadatos revisados (después de previsualización)"""
    from app.database import ejecutar

    # ── Convertir listas a JSON string antes de guardar ─────
    for campo_lista in ['subcategorias', 'temas_clave', 'autores_adicionales']:
        valor = metadatos.get(campo_lista)
        if isinstance(valor, list):
            metadatos[campo_lista] = json.dumps(valor)
        elif valor is None:
            metadatos[campo_lista] = json.dumps([])

    # Campos que actualizamos explícitamente
    campos_actualizar = {
        'titulo':              metadatos.get('titulo'),
        'autor':               metadatos.get('autor'),
        'isbn':                metadatos.get('isbn'),
        'editorial':           metadatos.get('editorial'),
        'anio_publicacion':    metadatos.get('anio_publicacion'),
        'categoria_principal': metadatos.get('categoria_principal'),
        'total_paginas':       metadatos.get('total_paginas'),
        'descripcion':         metadatos.get('descripcion'),
        'subcategorias':       metadatos.get('subcategorias', json.dumps([])),
        'temas_clave':         metadatos.get('temas_clave', json.dumps([])),
        'autores_adicionales': metadatos.get('autores_adicionales', json.dumps([])),
        'notas_bibliotecaria': metadatos.get('notas_bibliotecaria', ''),
        'fuente_metadatos':    metadatos.get('fuente_metadatos', 'IA'),
        'confianza_ia':        metadatos.get('confianza_ia', 5),
        'estado':              'catalogado',
        'revisado_manual':     1,
        'actualizado_en':      datetime.now().isoformat()
    }

    # ── Construir query dinámicamente (igual que antes) ──────
    set_clause = ", ".join(f"{k} = ?" for k in campos_actualizar.keys())
    valores    = list(campos_actualizar.values())

    ejecutar(
        f"UPDATE libros SET {set_clause} WHERE id = ?",
        valores + [libro_id]
    )

def actualizar_progreso(libro_id, pagina_actual, estado=None):
    from app.database import ejecutar
    if estado:
        ejecutar("""
            UPDATE libros
            SET pagina_actual = ?, estado = ?, actualizado_en = ?
            WHERE id = ?
        """, [pagina_actual, estado, datetime.now().isoformat(), libro_id])
    else:
        ejecutar("""
            UPDATE libros
            SET pagina_actual = ?, actualizado_en = ?
            WHERE id = ?
        """, [pagina_actual, datetime.now().isoformat(), libro_id])

def parsear_lista(valor) -> list:
    """Convierte JSON string o lista a lista limpia."""
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    try:
        resultado = json.loads(valor)
        return [str(v) for v in resultado if v] if isinstance(resultado, list) else []
    except Exception:
        return []

def agregar_resaltado(libro_id, pagina, texto_resaltado,
                      color_etiqueta, nota_personal="",
                      texto_contexto=""):
    from app.database import ejecutar
    return ejecutar("""
        INSERT INTO resaltados
            (libro_id, pagina, texto_resaltado,
             color_etiqueta, nota_personal, texto_contexto)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [libro_id, pagina, texto_resaltado,
          color_etiqueta, nota_personal, texto_contexto])

def obtener_resaltados(libro_id, color=None):
    from app.database import ejecutar
    if color:
        return ejecutar("""
            SELECT * FROM resaltados
            WHERE libro_id = ? AND color_etiqueta = ?
            ORDER BY pagina, creado_en
        """, [libro_id, color], fetchall=True)
    return ejecutar("""
        SELECT * FROM resaltados
        WHERE libro_id = ?
        ORDER BY pagina, creado_en
    """, [libro_id], fetchall=True)

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
if '_ia_procesando'        not in st.session_state:  # ← NUEVO
    st.session_state._ia_procesando        = False

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Estadísticas")
    
    todos, _ = obtener_libros_por_estado()
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
    st.header("🤖 Bibliotecaria IA")
    estado = estado_gemini()
    col1, col2 = st.columns(2)
    if not estado['api_key_configurada']:
        st.error("❌ IA no configurada. Añade GROQ_API_KEY al archivo .env")
        st.info("Crea archivo .env en la carpeta raíz con: GROQ_API_KEY=tu_key_aqui")
    elif estado['modo'] == 'offline_sin_cuota':
        st.warning("⚠️ Groq: Sin cuota disponible (vuelve mañana)")
        st.info("🤖 Usando modo fallback con respuestas predefinidas")
    else:
        st.success(f"✅ Groq: {estado['modo']}")

    col1, col2 = st.columns(2)
    col1.metric("API Key", "✓" if estado['api_key_configurada'] else "✗")
    col2.metric("Consultas hoy", f"{estado['llamadas_hoy']}/{estado['max_llamadas']}")

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

    # ── Inicializar flags ──────────────────────────────────
    if 'libro_en_proceso'     not in st.session_state:
        st.session_state.libro_en_proceso     = None
    if 'metadatos_propuestos' not in st.session_state:
        st.session_state.metadatos_propuestos = None
    if '_ia_procesando'       not in st.session_state:
        st.session_state._ia_procesando       = False

    # ══════════════════════════════════════════════════════
    # PASO 1 — Sin libro en proceso
    # ══════════════════════════════════════════════════════
    if (not st.session_state.libro_en_proceso
            and not st.session_state.metadatos_propuestos):

        metodo = st.radio(
            "Método de entrada",
            ["Subir PDF", "ISBN", "Manual"],
            horizontal=True
        )

        # ── PDF ───────────────────────────────────────────
        if metodo == "Subir PDF":
            archivo = st.file_uploader(
                "Seleccionar archivo", type=['pdf', 'epub', 'mobi']
            )

            if archivo:
                contenido    = archivo.getvalue()
                hash_archivo = hashlib.md5(contenido).hexdigest()[:16]

                # Verificar duplicado via ejecutar()
                from app.database import ejecutar
                existentes = ejecutar(
                    "SELECT id, titulo, nombre_archivo, hash_archivo FROM libros",
                    [], fetchall=True
                ) or []

                duplicado = next(
                    (l for l in existentes
                     if l.get('hash_archivo') and
                     l['hash_archivo'] == hash_archivo),
                    None
                )

                if duplicado:
                    st.error(
                        f"⚠️ Este archivo ya existe: "
                        f"**{duplicado.get('titulo') or duplicado.get('nombre_archivo')}**"
                    )
                else:
                    extension = archivo.name.split('.')[-1].upper()
                    tamano    = len(contenido) / (1024 * 1024)

                    libro_id = agregar_libro_por_procesar(
                        archivo.name,
                        f"./biblioteca_temp/{archivo.name}",
                        round(tamano, 2),
                        extension,
                        hash_archivo
                    )

                    # Guardar PDF en session_state
                    st.session_state.pdf_contenido    = contenido
                    st.session_state.libro_en_proceso = libro_id
                    st.rerun()

        # ── ISBN ──────────────────────────────────────────
        elif metodo == "ISBN":
            st.markdown("### 📖 Buscar por ISBN")
            col_i1, col_i2 = st.columns([3, 1])
            with col_i1:
                isbn_input = st.text_input(
                    "ISBN (10 o 13 dígitos)",
                    placeholder="Ej: 9780802806529",
                    key="isbn_input"
                )
            with col_i2:
                st.markdown("<br>", unsafe_allow_html=True)
                buscar_isbn = st.button(
                    "🔍 Buscar",
                    use_container_width=True,
                    type="primary"
                )

            if buscar_isbn and isbn_input:
                isbn_limpio = isbn_input.replace('-','').replace(' ','').strip()
                if len(isbn_limpio) not in [10, 13]:
                    st.error("⚠️ El ISBN debe tener 10 o 13 dígitos")
                else:
                    with st.spinner("🔍 Buscando..."):
                        metadatos_isbn = buscar_metadatos_isbn(isbn_limpio)

                    if metadatos_isbn.get('titulo'):
                        libro_id = agregar_libro_por_procesar(
                            f"{metadatos_isbn['titulo']}.isbn",
                            f"isbn://{isbn_limpio}", 0, "Otro",
                            f"isbn_{isbn_limpio}"
                        )
                        st.session_state.libro_en_proceso     = libro_id
                        st.session_state.metadatos_propuestos = metadatos_isbn
                        st.rerun()
                    else:
                        st.error(f"❌ ISBN `{isbn_limpio}` no encontrado.")

        # ── Manual ────────────────────────────────────────
        elif metodo == "Manual":
            with st.form("manual_entry"):
                titulo    = st.text_input("Título *")
                autor     = st.text_input("Autor")
                col_c, col_p = st.columns(2)
                with col_c:
                    categoria = st.selectbox(
                        "Categoría",
                        ["Teologia","Programacion","Matrimonio",
                         "Filosofia","Liderazgo","Historia","Otros"]
                    )
                with col_p:
                    paginas = st.number_input(
                        "Total páginas", min_value=1, value=200
                    )
                descripcion = st.text_area("Descripción")
                submitted   = st.form_submit_button(
                    "💾 Guardar", use_container_width=True
                )

                if submitted and titulo.strip():
                    libro_id = agregar_libro_por_procesar(
                        f"{titulo}.manual", "manual", 0, "Otro", f"manual_{titulo[:10]}"
                    )
                    guardar_metadatos_ia(libro_id, {
                        'titulo':              titulo,
                        'autor':               autor or 'Desconocido',
                        'categoria_principal': categoria,
                        'descripcion':         descripcion,
                        'total_paginas':       paginas,
                        'fuente_metadatos':    'Manual',
                        'confianza_ia':        10,
                        'subcategorias':       [],
                        'temas_clave':         [],
                        'autores_adicionales': [],
                        'notas_bibliotecaria': 'Ingresado manualmente'
                    })
                    st.success("✅ Libro guardado")
                    st.rerun()

    # ══════════════════════════════════════════════════════
    # PASO 2 — Libro subido, IA analizando
    # ══════════════════════════════════════════════════════
    elif (st.session_state.libro_en_proceso
          and not st.session_state.metadatos_propuestos):

        st.markdown("### ⏳ Paso 2: Bibliotecaria IA analizando...")

        # Guard anti-bucle
        if st.session_state._ia_procesando:
            st.info("⏳ Análisis en curso, espera un momento...")
            st.stop()

        st.session_state._ia_procesando = True

        libro = obtener_libro(st.session_state.libro_en_proceso)

        if not libro:
            st.error("❌ Error cargando libro. Intenta de nuevo.")
            st.session_state.libro_en_proceso = None
            st.session_state._ia_procesando   = False
            st.rerun()
        else:
            with st.spinner("🔍 Analizando PDF con IA..."):
                try:
                    metadatos = extraer_metadatos_libro(
                        st.session_state.get('pdf_contenido', b""),
                        libro['nombre_archivo']
                    )
                except Exception as e:
                    st.warning(f"⚠️ Error en IA: {e}. Usando fallback.")
                    metadatos = {
                        'titulo': (libro['nombre_archivo']
                                   .replace('.pdf','')
                                   .replace('_',' ').title()),
                        'autor':               'Desconocido',
                        'categoria_principal': 'Otros',
                        'descripcion':         'Completa manualmente.',
                        'total_paginas':       0,
                        'confianza_ia':        1,
                        'fuente_metadatos':    'Manual_Fallback',
                        'temas_clave':         [],
                        'subcategorias':       [],
                    }

            st.session_state.metadatos_propuestos = metadatos
            st.session_state._ia_procesando        = False
            st.rerun()

    # ══════════════════════════════════════════════════════
    # PASO 3 — Revisar y confirmar metadatos
    # ══════════════════════════════════════════════════════
    elif st.session_state.metadatos_propuestos:

        st.markdown("### ✅ Paso 3: Revisar y confirmar")

        meta       = st.session_state.metadatos_propuestos
        confianza  = int(meta.get('confianza_ia') or
                         meta.get('confianza_extraccion') or 5)
        color_conf = ("#3fb950" if confianza >= 7 else
                      "#e3b341" if confianza >= 5 else "#f85149")

        # Preview etiquetas
        todas_tags = (parsear_lista(meta.get('temas_clave', [])) +
                      parsear_lista(meta.get('subcategorias', [])))
        if todas_tags:
            badges = " ".join(
                f"<span style='background:#0d1117; color:#e3b341; "
                f"border:1px solid #e3b341; border-radius:20px; "
                f"padding:0.15rem 0.6rem; font-size:0.75rem; "
                f"margin-right:0.3rem;'>✨ {t}</span>"
                for t in todas_tags[:10]
            )
            st.markdown("**🤖 Etiquetas sugeridas:**")
            st.markdown(badges, unsafe_allow_html=True)
            st.markdown("")

        # Barra confianza
        st.markdown(f"""
        <div style="background:#161b22; padding:1rem;
                    border-radius:8px; margin-bottom:1rem;">
            <span>🤖 Confianza IA: </span>
            <strong style="color:{color_conf};">{confianza}/10</strong>
            <div style="background:#21262d; height:6px;
                        border-radius:3px; margin-top:0.5rem;">
                <div style="background:{color_conf};
                            width:{confianza*10}%; height:100%;
                            border-radius:3px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── FORMULARIO ────────────────────────────────────
        with st.form("revisar_metadatos", clear_on_submit=False):

            col1, col2 = st.columns(2)
            with col1:
                titulo_f    = st.text_input(
                    "Título *", value=meta.get('titulo') or ''
                )
                autor_f     = st.text_input(
                    "Autor", value=meta.get('autor') or ''
                )
                isbn_f      = st.text_input(
                    "ISBN", value=meta.get('isbn') or ''
                )
                editorial_f = st.text_input(
                    "Editorial", value=meta.get('editorial') or ''
                )

            with col2:
                cats    = ["Teologia","Programacion","Matrimonio",
                           "Filosofia","Liderazgo","Historia","Otros"]
                cat_val = meta.get('categoria_principal','Otros')
                cat_idx = cats.index(cat_val) if cat_val in cats else 6

                categoria_f = st.selectbox(
                    "Categoría", cats, index=cat_idx
                )
                anio_f = st.number_input(
                    "Año", min_value=1000, max_value=2030,
                    value=int(meta.get('anio_publicacion') or 2020)
                )
                paginas_f = st.number_input(
                    "Total páginas", min_value=1,
                    value=int(meta.get('total_paginas') or 100)
                )

            desc_f = st.text_area(
                "Descripción",
                value=meta.get('descripcion') or '',
                height=100
            )

            st.markdown("**🏷️ Etiquetas**")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                temas_f = st.text_input(
                    "Temas clave (separados por coma)",
                    value=", ".join(
                        parsear_lista(meta.get('temas_clave', []))
                    )
                )
            with col_t2:
                subcats_f = st.text_input(
                    "Subcategorías (separadas por coma)",
                    value=", ".join(
                        parsear_lista(meta.get('subcategorias', []))
                    )
                )

            col_g, col_c = st.columns(2)
            with col_g:
                guardar = st.form_submit_button(
                    "✅ Guardar en biblioteca",
                    use_container_width=True,
                    type="primary"
                )
            with col_c:
                cancelar = st.form_submit_button(
                    "❌ Cancelar",
                    use_container_width=True
                )

            # ── Guardar ───────────────────────────────────
            if guardar:
                if not titulo_f.strip():
                    st.error("⚠️ El título es obligatorio")
                else:
                    guardar_metadatos_ia(
                        st.session_state.libro_en_proceso,
                        {
                            'titulo':              titulo_f.strip(),
                            'autor':               autor_f.strip(),
                            'isbn':                isbn_f.strip(),
                            'editorial':           editorial_f.strip(),
                            'anio_publicacion':    int(anio_f),
                            'categoria_principal': categoria_f,
                            'total_paginas':       int(paginas_f),
                            'descripcion':         desc_f.strip(),
                            'temas_clave':  [t.strip() for t in
                                             temas_f.split(',') if t.strip()],
                            'subcategorias':[s.strip() for s in
                                             subcats_f.split(',') if s.strip()],
                            'autores_adicionales': meta.get(
                                'autores_adicionales', []
                            ),
                            'notas_bibliotecaria': meta.get(
                                'notas_bibliotecaria', ''
                            ),
                            'fuente_metadatos': meta.get(
                                'fuente_metadatos', 'IA'
                            ),
                            'confianza_ia': confianza,
                        }
                    )
                    # Limpiar todo
                    st.session_state.libro_en_proceso     = None
                    st.session_state.metadatos_propuestos = None
                    st.session_state._ia_procesando       = False
                    st.session_state.pop('pdf_contenido', None)
                    st.success("✅ ¡Libro catalogado!")
                    st.rerun()

            # ── Cancelar ──────────────────────────────────
            if cancelar:
                st.session_state.libro_en_proceso     = None
                st.session_state.metadatos_propuestos = None
                st.session_state._ia_procesando       = False
                st.session_state.pop('pdf_contenido', None)
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: CATÁLOGO - SIN HTML, SOLO COMPONENTES NATIVOS
# ═══════════════════════════════════════════════════════════════

with tab_catalogo:
    st.subheader("Todos los libros")

    # ── Session state para paginación ────────────────────────
    if 'cat_pagina' not in st.session_state:
        st.session_state.cat_pagina = 1

    # ── FILTROS ───────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_estado = st.selectbox(
            "Estado",
            ["Todos", "por_procesar", "catalogado",
             "leyendo", "completado", "pausado"],
            key="filtro_estado_cat"
        )
    with col_f2:
        filtro_categoria = st.selectbox(
            "Categoría",
            ["Todas", "Teologia", "Programacion", "Matrimonio",
             "Filosofia", "Liderazgo", "Historia", "Otros"],
            key="filtro_categoria_cat"
        )
    with col_f3:
        filtro_color = st.selectbox(
            "Resaltados",
            ["Todos", "Ninguno", "Amarillo", "Verde",
             "Morado", "Rosa", "Azul"],
            key="filtro_color_cat"
        )

    # ── Búsqueda — incluye temas y subcategorías ──────────────
    busqueda = st.text_input(
        "🔍 Buscar",
        placeholder="Título, autor, descripción, temas clave, subcategorías...",
        key="busqueda_cat"
    )

    # ── Libros por página ─────────────────────────────────────
    col_pp, col_reset = st.columns([2, 1])
    with col_pp:
        por_pagina = st.select_slider(
            "Libros por página",
            options=[5, 10, 20, 50],
            value=10,
            key="por_pagina_cat"
        )
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Resetear filtros", use_container_width=True):
            st.session_state.cat_pagina = 1
            st.rerun()

    # ── Resetear página al cambiar filtros ────────────────────
    filtros_key = f"{filtro_estado}_{filtro_categoria}_{filtro_color}_{busqueda}_{por_pagina}"
    if 'filtros_prev' not in st.session_state:
        st.session_state.filtros_prev = filtros_key
    if st.session_state.filtros_prev != filtros_key:
        st.session_state.cat_pagina   = 1
        st.session_state.filtros_prev = filtros_key

    # ── Aplicar filtros ───────────────────────────────────────
    estado_filtro    = None if filtro_estado    == "Todos"  else filtro_estado
    categoria_filtro = None if filtro_categoria == "Todas"  else filtro_categoria
    color_filtro     = None if filtro_color     == "Todos"  else filtro_color

    libros, total = obtener_libros_por_estado(
        estado=estado_filtro,
        categoria=categoria_filtro,
        color=color_filtro,
        busqueda=busqueda,
        pagina=st.session_state.cat_pagina,
        por_pagina=por_pagina
    )

    total_paginas = max(1, -(-total // por_pagina))  # ceil division

    # ── Info de resultados ────────────────────────────────────
    st.divider()
    col_info, col_pag_info = st.columns([3, 1])
    with col_info:
        inicio = (st.session_state.cat_pagina - 1) * por_pagina + 1
        fin    = min(st.session_state.cat_pagina * por_pagina, total)
        if total > 0:
            st.caption(
                f"Mostrando **{inicio}–{fin}** de **{total}** libros "
                f"· Página **{st.session_state.cat_pagina}** de **{total_paginas}**"
            )
        else:
            st.caption("Sin resultados")
    with col_pag_info:
        if busqueda:
            st.caption(f"🔍 Buscando: *{busqueda}*")

    # ── Lista de libros ───────────────────────────────────────
    if not libros:
        st.info("📭 No se encontraron libros con estos filtros")
    else:
        for libro in libros:
            emoji_estado = {
                'por_procesar': '⏳',
                'catalogado':   '📚',
                'leyendo':      '🔥',
                'pausado':      '⏸️',
                'completado':   '✅',
                'abandonado':   '🗑️'
            }.get(libro['estado'], '📖')

            pag_actual   = libro['pagina_actual'] or 0
            total_pags   = libro['total_paginas'] or 0
            progreso_pct = (
                min(100, int(pag_actual / total_pags * 100))
                if total_pags > 0 else 0
            )

            # Parsear etiquetas
            temas   = parsear_lista(libro.get('temas_clave'))
            subcats = parsear_lista(libro.get('subcategorias'))
            todas_tags = temas + subcats

            with st.container():
                col_header, col_estado = st.columns([6, 1])
                with col_header:
                    st.markdown(
                        f"### {emoji_estado} {libro['titulo'] or 'Sin título'}"
                    )
                with col_estado:
                    st.caption(libro['estado'].replace('_', ' '))

                st.caption(
                    f"**{libro['autor'] or 'Autor desconocido'}** "
                    f"• {libro['categoria_principal'] or 'Sin categoría'}"
                )

                # ── Etiquetas visuales ────────────────────────
                if todas_tags:
                    badges_html = " ".join(
                        f"<span style='"
                        f"background:#21262d; color:#58a6ff; "
                        f"border:1px solid #30363d; border-radius:20px; "
                        f"padding:0.15rem 0.6rem; font-size:0.72rem; "
                        f"margin-right:0.3rem; display:inline-block; "
                        f"margin-bottom:0.2rem;'>"
                        f"🏷️ {tag}</span>"
                        for tag in todas_tags[:8]
                    )
                    st.markdown(badges_html, unsafe_allow_html=True)
                    st.markdown("")

                descripcion = libro['descripcion'] or 'Sin descripción'
                if len(descripcion) > 120:
                    descripcion = descripcion[:120] + '...'
                st.write(descripcion)

                st.progress(
                    progreso_pct / 100,
                    text=(
                        f"{pag_actual} / "
                        f"{total_pags if total_pags > 0 else '?'} "
                        f"páginas ({progreso_pct}%)"
                    )
                )

                if libro['estado'] in ['catalogado', 'leyendo', 'pausado', 'por_procesar', 'completado', 'abandonado']:
                    with st.expander("⚙️ Gestionar libro"):
                        key_base = f"cat_{libro['id']}"
                        
                        tab_prog, tab_edit, tab_del = st.tabs([
                            "📖 Progreso", "✏️ Editar", "🗑️ Eliminar"
                        ])
                        
                        # ── Tab Progreso ──────────────────────────────────
                        with tab_prog:
                            nueva_pagina = st.number_input(
                                "Página actual",
                                min_value=0,
                                max_value=total_pags or 9999,
                                value=pag_actual,
                                key=f"pag_{key_base}"
                            )
                            nuevo_estado = st.selectbox(
                                "Estado",
                                ['por_procesar', 'catalogado', 'leyendo', 
                                'pausado', 'completado', 'abandonado'],
                                index=['por_procesar', 'catalogado', 'leyendo',
                                    'pausado', 'completado', 'abandonado'].index(
                                    libro['estado']
                                    if libro['estado'] in ['por_procesar', 'catalogado',
                                        'leyendo', 'pausado', 'completado', 'abandonado']
                                    else 'catalogado'
                                ),
                                key=f"est_{key_base}"
                            )
                            if st.button("💾 Guardar progreso", key=f"upd_{key_base}",
                                        use_container_width=True):
                                actualizar_progreso(libro['id'], nueva_pagina, nuevo_estado)
                                st.success("✅ Progreso guardado")
                                st.rerun()
                        
                        # ── Tab Editar ────────────────────────────────────
                        with tab_edit:
                            with st.form(f"form_edit_{libro['id']}"):
                                col_e1, col_e2 = st.columns(2)
                                with col_e1:
                                    titulo_e = st.text_input(
                                        "Título", value=libro.get('titulo') or '',
                                        key=f"tit_e_{key_base}"
                                    )
                                    autor_e = st.text_input(
                                        "Autor", value=libro.get('autor') or '',
                                        key=f"aut_e_{key_base}"
                                    )
                                    editorial_e = st.text_input(
                                        "Editorial", value=libro.get('editorial') or '',
                                        key=f"edi_e_{key_base}"
                                    )
                                    isbn_e = st.text_input(
                                        "ISBN", value=libro.get('isbn') or '',
                                        key=f"isbn_e_{key_base}"
                                    )
                                with col_e2:
                                    categoria_e = st.selectbox(
                                        "Categoría",
                                        ["Teologia", "Programacion", "Matrimonio",
                                        "Filosofia", "Liderazgo", "Historia", "Otros"],
                                        index=["Teologia", "Programacion", "Matrimonio",
                                            "Filosofia", "Liderazgo", "Historia", "Otros"].index(
                                            libro.get('categoria_principal', 'Otros')
                                            if libro.get('categoria_principal') in
                                            ["Teologia", "Programacion", "Matrimonio",
                                                "Filosofia", "Liderazgo", "Historia", "Otros"]
                                            else 'Otros'
                                        ),
                                        key=f"cat_e_{key_base}"
                                    )
                                    anio_e = st.number_input(
                                        "Año", min_value=1000, max_value=2030,
                                        value=int(libro.get('anio_publicacion') or 2020),
                                        key=f"anio_e_{key_base}"
                                    )
                                    paginas_e = st.number_input(
                                        "Total páginas", min_value=1,
                                        value=int(libro.get('total_paginas') or 100),
                                        key=f"pags_e_{key_base}"
                                    )
                                
                                desc_e = st.text_area(
                                    "Descripción",
                                    value=libro.get('descripcion') or '',
                                    height=80,
                                    key=f"desc_e_{key_base}"
                                )
                                
                                temas_e = st.text_input(
                                    "Temas clave (separados por coma)",
                                    value=", ".join(parsear_lista(libro.get('temas_clave'))),
                                    key=f"temas_e_{key_base}"
                                )
                                subcats_e = st.text_input(
                                    "Subcategorías (separadas por coma)",
                                    value=", ".join(parsear_lista(libro.get('subcategorias'))),
                                    key=f"subcats_e_{key_base}"
                                )
                                
                                if st.form_submit_button("💾 Guardar cambios",
                                                        use_container_width=True,
                                                        type="primary"):
                                    from app.database import ejecutar
                                    ejecutar("""
                                        UPDATE libros SET
                                            titulo=?, autor=?, editorial=?, isbn=?,
                                            categoria_principal=?, anio_publicacion=?,
                                            total_paginas=?, descripcion=?,
                                            temas_clave=?, subcategorias=?,
                                            actualizado_en=?
                                        WHERE id=?
                                    """, [
                                        titulo_e, autor_e, editorial_e, isbn_e,
                                        categoria_e, anio_e, paginas_e, desc_e,
                                        json.dumps([t.strip() for t in temas_e.split(',') if t.strip()]),
                                        json.dumps([s.strip() for s in subcats_e.split(',') if s.strip()]),
                                        datetime.now().isoformat(),
                                        libro['id']
                                    ])
                                    st.success("✅ Libro actualizado")
                                    st.rerun()
                        
                        # ── Tab Eliminar ──────────────────────────────────
                        with tab_del:
                            st.warning(
                                f"⚠️ Eliminarás **{libro.get('titulo','este libro')}** "
                                f"y todos sus resaltados permanentemente."
                            )
                            confirmar_del = st.checkbox(
                                "Confirmo que quiero eliminar este libro",
                                key=f"confirm_del_{key_base}"
                            )
                            if st.button("🗑️ Eliminar libro", key=f"del_{key_base}",
                                        type="secondary", use_container_width=True):
                                if not confirmar_del:
                                    st.error("Marca la casilla de confirmación primero")
                                else:
                                    from app.database import ejecutar
                                    ejecutar(
                                        "DELETE FROM resaltados WHERE libro_id = ?",
                                        [libro['id']]
                                    )
                                    ejecutar(
                                        "DELETE FROM libros WHERE id = ?",
                                        [libro['id']]
                                    )
                                    st.success("🗑️ Libro eliminado")
                                    st.rerun()

                st.divider()

    # ── CONTROLES DE PAGINACIÓN ───────────────────────────────
    if total_paginas > 1:
        st.markdown("---")
        
        # Calcular rango de páginas visibles (máximo 5)
        mitad    = 2
        pag_min  = max(1, st.session_state.cat_pagina - mitad)
        pag_max  = min(total_paginas, pag_min + 4)
        pag_min  = max(1, pag_max - 4)
        rango    = list(range(pag_min, pag_max + 1))

        # Fila de botones de paginación
        n_cols       = len(rango) + 2          # anterior + páginas + siguiente
        cols_pag     = st.columns(n_cols)
        pag_actual_s = st.session_state.cat_pagina

        # ← Anterior
        with cols_pag[0]:
            if st.button(
                "◀",
                disabled=pag_actual_s == 1,
                use_container_width=True,
                key="pag_prev"
            ):
                st.session_state.cat_pagina -= 1
                st.rerun()

        # Páginas numeradas
        for j, num_pag in enumerate(rango):
            with cols_pag[j + 1]:
                es_actual = num_pag == pag_actual_s
                if st.button(
                    f"**{num_pag}**" if es_actual else str(num_pag),
                    key=f"pag_{num_pag}",
                    use_container_width=True,
                    type="primary" if es_actual else "secondary"
                ):
                    st.session_state.cat_pagina = num_pag
                    st.rerun()

        # Siguiente →
        with cols_pag[-1]:
            if st.button(
                "▶",
                disabled=pag_actual_s == total_paginas,
                use_container_width=True,
                key="pag_next"
            ):
                st.session_state.cat_pagina += 1
                st.rerun()

        # Ir a página específica
        st.markdown("")
        col_goto, _ = st.columns([1, 3])
        with col_goto:
            goto = st.number_input(
                "Ir a página",
                min_value=1,
                max_value=total_paginas,
                value=pag_actual_s,
                step=1,
                key="goto_pag"
            )
            if st.button("Ir →", use_container_width=True, key="btn_goto"):
                st.session_state.cat_pagina = goto
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 3: EN LECTURA
# ═══════════════════════════════════════════════════════════════

with tab_leyendo:
    st.subheader("🔥 Lectura Activa")

    libros_leyendo, _ = obtener_libros_por_estado("leyendo")

    if not libros_leyendo:
        st.info("🔥 No hay libros en lectura activa. Marca uno como 'leyendo' desde el catálogo.")
    else:
        for libro in libros_leyendo:
            pag_actual  = libro['pagina_actual'] or 0
            total       = libro['total_paginas'] or 1
            progreso    = min(100, int(pag_actual / total * 100))
            pag_rest    = total - pag_actual
            dias_est    = max(1, pag_rest // 20)

            # Etiquetas del libro
            temas   = parsear_lista(libro.get('temas_clave'))
            subcats = parsear_lista(libro.get('subcategorias'))
            tags    = temas + subcats

            # ── Card principal ────────────────────────────────
            st.markdown(f"### 🔥 {libro['titulo'] or 'Sin título'}")
            st.caption(
                f"*{libro['autor'] or 'Autor desconocido'}* "
                f"• {libro['categoria_principal'] or 'Sin categoría'}"
            )

            # Etiquetas
            if tags:
                badges = " ".join(
                    f"<span style='background:#21262d; color:#58a6ff; "
                    f"border:1px solid #30363d; border-radius:20px; "
                    f"padding:0.15rem 0.6rem; font-size:0.72rem; "
                    f"margin-right:0.3rem;'>🏷️ {tag}</span>"
                    for tag in tags[:6]
                )
                st.markdown(badges, unsafe_allow_html=True)
                st.markdown("")

            # Barra de progreso
            st.progress(
                progreso / 100,
                text=f"📖 {pag_actual} / {total} páginas — {progreso}%"
            )

            # Métricas
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Progreso",   f"{progreso}%")
            col_m2.metric("Página",     f"{pag_actual}/{total}")
            col_m3.metric("Restantes",  f"{pag_rest} págs")
            col_m4.metric("Estimado",   f"~{dias_est} días")

            st.markdown("")

            # ── Dos columnas: Actualizar + Resaltado ──────────
            col_upd, col_res = st.columns(2)

            # ── Actualizar progreso ───────────────────────────
            with col_upd:
                with st.expander("📖 Actualizar progreso", expanded=False):
                    key_b = f"ley_{libro['id']}"

                    nueva_pag = st.number_input(
                        "Página actual",
                        min_value=0,
                        max_value=total,
                        value=pag_actual,
                        step=1,
                        key=f"npag_{key_b}"
                    )

                    # Slider visual
                    nueva_pag_slider = st.slider(
                        "O usa el slider",
                        min_value=0,
                        max_value=total,
                        value=pag_actual,
                        key=f"slid_{key_b}"
                    )

                    # Usar el mayor de los dos (el que cambió)
                    pag_a_guardar = max(nueva_pag, nueva_pag_slider)

                    nuevo_estado = st.selectbox(
                        "Estado",
                        ['leyendo', 'pausado', 'completado', 'abandonado'],
                        index=0,
                        key=f"nest_{key_b}"
                    )

                    notas_prog = st.text_input(
                        "Nota rápida (opcional)",
                        placeholder="Ej: Capítulo 5 terminado, muy denso...",
                        key=f"nota_{key_b}"
                    )

                    if st.button(
                        "💾 Guardar progreso",
                        key=f"upd_{key_b}",
                        use_container_width=True,
                        type="primary"
                    ):
                        actualizar_progreso(libro['id'], pag_a_guardar, nuevo_estado)
                        st.success(
                            f"✅ Guardado — página {pag_a_guardar} · {nuevo_estado}"
                        )
                        st.rerun()

            # ── Agregar resaltado directo ─────────────────────
            with col_res:
                with st.expander("🎨 Agregar resaltado", expanded=False):
                    key_r = f"res_{libro['id']}"

                    pag_res = st.number_input(
                        "Página del resaltado",
                        min_value=1,
                        max_value=total,
                        value=pag_actual or 1,
                        key=f"pres_{key_r}"
                    )

                    color_res = st.selectbox(
                        "Color / Tipo",
                        options=[
                            "Amarillo",
                            "Verde",
                            "Azul",
                            "Rosa",
                            "Morado"
                        ],
                        format_func=lambda x: {
                            "Amarillo": "🟡 Concepto clave",
                            "Verde":    "🟢 Aplicación práctica",
                            "Azul":     "🔵 Duda / Investigar",
                            "Rosa":     "🩷 Cita importante",
                            "Morado":   "🟣 Idea propia"
                        }[x],
                        key=f"cres_{key_r}"
                    )

                    texto_res = st.text_area(
                        "Texto resaltado *",
                        placeholder="Copia aquí el texto...",
                        height=80,
                        key=f"tres_{key_r}"
                    )

                    nota_res = st.text_area(
                        "Tu nota personal",
                        placeholder="¿Por qué es importante?",
                        height=60,
                        key=f"nres_{key_r}"
                    )

                    if st.button(
                        "🎨 Guardar resaltado",
                        key=f"btnres_{key_r}",
                        use_container_width=True,
                        type="primary"
                    ):
                        if not texto_res.strip():
                            st.error("⚠️ El texto del resaltado es obligatorio")
                        else:
                            agregar_resaltado(
                                libro_id=libro['id'],
                                pagina=pag_res,
                                texto_resaltado=texto_res.strip(),
                                color_etiqueta=color_res,
                                nota_personal=nota_res,
                                texto_contexto=""
                            )
                            st.success(
                                f"✅ Resaltado guardado — "
                                f"Pág. {pag_res} · {color_res}"
                            )
                            st.rerun()

                    # Mini resumen de resaltados del libro
                    resaltados_libro = obtener_resaltados(libro['id'])
                    total_res        = len(resaltados_libro)

                    if total_res > 0:
                        st.divider()
                        st.caption(f"📑 {total_res} resaltados en este libro")

                        EMOJIS_COLOR = {
                            'Amarillo': '🟡',
                            'Verde':    '🟢',
                            'Azul':     '🔵',
                            'Rosa':     '🩷',
                            'Morado':   '🟣'
                        }

                        por_color = {}
                        for r in resaltados_libro:
                            c = r['color_etiqueta']
                            por_color[c] = por_color.get(c, 0) + 1

                        resumen_col = " · ".join(
                            f"{EMOJIS_COLOR.get(c, '⚪')} {n}"
                            for c, n in por_color.items()
                        )
                        st.caption(resumen_col)

            st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 4: MIS RESALTADOS
# ═══════════════════════════════════════════════════════════════

with tab_resaltados:
    st.subheader("Sistema de resaltados")
    
    libros_disponibles, _ = obtener_libros_por_estado()
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