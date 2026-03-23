"""
📚 Biblioteca Digital - Sistema con IA + Resaltados personales
Flujo: Subir → IA procesa → Revisar → Guardar → Agregar resaltados
"""

import sys
from pathlib import Path
from datetime import date, datetime
import json
import hashlib

sys.path.append(str(Path(__file__).parent.parent))

from app.database import init_database, ejecutar
from app.ai_client import (
    extraer_metadatos_libro,
    buscar_metadatos_isbn,
    verificar_conexion,
    estado_gemini,
    api_key_configurada,
)

import streamlit as st

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
    .estado-catalogado   { border-left: 4px solid #58a6ff; }
    .estado-leyendo      { border-left: 4px solid #e3b341; border: 1px solid #e3b341; }
    .estado-completado   { border-left: 4px solid #3fb950; }

    .resaltado-amarillo { background: rgba(227,179,65,0.15);  border-left: 3px solid #e3b341; }
    .resaltado-verde    { background: rgba(63,185,80,0.15);   border-left: 3px solid #3fb950; }
    .resaltado-azul     { background: rgba(88,166,255,0.15);  border-left: 3px solid #58a6ff; }
    .resaltado-rosa     { background: rgba(247,120,186,0.15); border-left: 3px solid #f778ba; }
    .resaltado-morado   { background: rgba(163,113,247,0.15); border-left: 3px solid #a371f7; }

    .libro-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — todas usan ejecutar()
# ═══════════════════════════════════════════════════════════════

def parsear_lista(valor) -> list:
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    try:
        resultado = json.loads(valor)
        return [str(v) for v in resultado if v] if isinstance(resultado, list) else []
    except Exception:
        return []


def agregar_libro_por_procesar(nombre_archivo: str, ruta: str,
                                tamano: float, formato: str,
                                hash_archivo: str) -> int:
    titulo_temp = (nombre_archivo
                   .replace(f".{formato.lower()}", "")
                   .replace("_", " ")
                   .title())
    return ejecutar("""
        INSERT INTO libros
            (titulo, nombre_archivo, ruta_archivo,
             tamano_mb, formato, hash_archivo, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'por_procesar')
    """, [titulo_temp, nombre_archivo, ruta,
          tamano, formato, hash_archivo])


def obtener_libro(libro_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM libros WHERE id = ?",
        [libro_id], fetchall=True
    )
    return rows[0] if rows else None


def obtener_libros_por_estado(estado=None, categoria=None,
                               color=None, busqueda="",
                               pagina=1, por_pagina=10) -> tuple:
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

    total_rows = ejecutar(
        f"SELECT COUNT(*) as total FROM libros WHERE {where}",
        params, fetchall=True
    )
    total  = total_rows[0]["total"] if total_rows else 0
    offset = (pagina - 1) * por_pagina
    libros = ejecutar(
        f"""SELECT * FROM libros WHERE {where}
            ORDER BY creado_en DESC LIMIT ? OFFSET ?""",
        params + [por_pagina, offset], fetchall=True
    ) or []

    return libros, total


def guardar_metadatos_ia(libro_id: int, metadatos: dict) -> None:
    for campo in ["subcategorias", "temas_clave", "autores_adicionales"]:
        valor = metadatos.get(campo)
        if isinstance(valor, list):
            metadatos[campo] = json.dumps(valor)
        elif valor is None:
            metadatos[campo] = json.dumps([])

    campos = {
        "titulo":              metadatos.get("titulo"),
        "autor":               metadatos.get("autor"),
        "isbn":                metadatos.get("isbn"),
        "editorial":           metadatos.get("editorial"),
        "anio_publicacion":    metadatos.get("anio_publicacion"),
        "categoria_principal": metadatos.get("categoria_principal"),
        "total_paginas":       metadatos.get("total_paginas"),
        "descripcion":         metadatos.get("descripcion"),
        "subcategorias":       metadatos.get("subcategorias", json.dumps([])),
        "temas_clave":         metadatos.get("temas_clave",   json.dumps([])),
        "autores_adicionales": metadatos.get("autores_adicionales", json.dumps([])),
        "notas_bibliotecaria": metadatos.get("notas_bibliotecaria", ""),
        "fuente_metadatos":    metadatos.get("fuente_metadatos", "IA"),
        "confianza_ia":        metadatos.get("confianza_ia", 5),
        "estado":              "catalogado",
        "revisado_manual":     1,
        "actualizado_en":      datetime.now().isoformat(),
    }

    set_clause = ", ".join(f"{k} = ?" for k in campos)
    ejecutar(
        f"UPDATE libros SET {set_clause} WHERE id = ?",
        list(campos.values()) + [libro_id]
    )


def actualizar_progreso(libro_id: int, pagina_actual: int,
                         estado: str = None) -> None:
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


def agregar_resaltado(libro_id: int, pagina: int, texto_resaltado: str,
                      color_etiqueta: str, nota_personal: str = "",
                      texto_contexto: str = "") -> int:
    return ejecutar("""
        INSERT INTO resaltados
            (libro_id, pagina, texto_resaltado,
             color_etiqueta, nota_personal, texto_contexto)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [libro_id, pagina, texto_resaltado,
          color_etiqueta, nota_personal, texto_contexto])


def obtener_resaltados(libro_id: int, color: str = None) -> list:
    if color:
        return ejecutar("""
            SELECT * FROM resaltados
            WHERE libro_id = ? AND color_etiqueta = ?
            ORDER BY pagina, creado_en
        """, [libro_id, color], fetchall=True) or []
    return ejecutar("""
        SELECT * FROM resaltados
        WHERE libro_id = ?
        ORDER BY pagina, creado_en
    """, [libro_id], fetchall=True) or []


def eliminar_libro(libro_id: int) -> None:
    ejecutar("DELETE FROM resaltados WHERE libro_id = ?", [libro_id])
    ejecutar("DELETE FROM libros WHERE id = ?",           [libro_id])


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("📚 Biblioteca Digital")
st.caption("Catalogación con IA + Sistema de resaltados personal")

# ═══════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════

for key, default in [
    ("libro_en_proceso",     None),
    ("metadatos_propuestos", None),
    ("libro_para_resaltar",  None),
    ("_ia_procesando",       False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Estadísticas")

    todos, _ = obtener_libros_por_estado(por_pagina=9999)
    st.metric("Total",        len(todos))
    st.metric("Por procesar", len([l for l in todos if l["estado"] == "por_procesar"]))
    st.metric("En lectura",   len([l for l in todos if l["estado"] == "leyendo"]))
    st.metric("Completados",  len([l for l in todos if l["estado"] == "completado"]))

    st.divider()
    st.header("🤖 Bibliotecaria IA")
    estado_ia = estado_gemini()

    if not estado_ia["api_key_configurada"]:
        st.error("❌ IA no configurada")
        st.info("Añade GROQ_API_KEY al archivo .env")
    elif estado_ia["modo"] == "offline_sin_cuota":
        st.warning("⚠️ Sin cuota disponible (vuelve mañana)")
    else:
        st.success(f"✅ Groq: {estado_ia['modo']}")

    col1, col2 = st.columns(2)
    col1.metric("API Key",       "✓" if estado_ia["api_key_configurada"] else "✗")
    col2.metric("Consultas hoy", f"{estado_ia['llamadas_hoy']}/{estado_ia['max_llamadas']}")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_cargar, tab_catalogo, tab_leyendo, tab_resaltados = st.tabs([
    "➕ Cargar Nuevo", "📚 Catálogo", "🔥 En Lectura", "🎨 Mis Resaltados"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: CARGAR NUEVO
# ═══════════════════════════════════════════════════════════════

with tab_cargar:
    st.subheader("Cargar nuevo libro")

    # ── PASO 1 — Sin libro en proceso ────────────────────────
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
                "Seleccionar archivo", type=["pdf", "epub", "mobi"]
            )
            if archivo:
                contenido    = archivo.getvalue()
                hash_archivo = hashlib.md5(contenido).hexdigest()[:16]

                existentes = ejecutar(
                    "SELECT id, titulo, nombre_archivo, hash_archivo FROM libros",
                    [], fetchall=True
                ) or []

                duplicado = next(
                    (l for l in existentes
                     if l.get("hash_archivo") == hash_archivo),
                    None
                )

                if duplicado:
                    st.error(
                        f"⚠️ Este archivo ya existe: "
                        f"**{duplicado.get('titulo') or duplicado.get('nombre_archivo')}**"
                    )
                else:
                    extension = archivo.name.split(".")[-1].upper()
                    tamano    = len(contenido) / (1024 * 1024)
                    libro_id  = agregar_libro_por_procesar(
                        archivo.name,
                        f"./biblioteca_temp/{archivo.name}",
                        round(tamano, 2), extension, hash_archivo
                    )
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
                    "🔍 Buscar", use_container_width=True, type="primary"
                )

            if buscar_isbn and isbn_input:
                isbn_limpio = isbn_input.replace("-","").replace(" ","").strip()
                if len(isbn_limpio) not in [10, 13]:
                    st.error("⚠️ El ISBN debe tener 10 o 13 dígitos")
                else:
                    with st.spinner("🔍 Buscando..."):
                        metadatos_isbn = buscar_metadatos_isbn(isbn_limpio)
                    if metadatos_isbn.get("titulo"):
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
                    paginas = st.number_input("Total páginas", min_value=1, value=200)
                descripcion = st.text_area("Descripción")
                submitted   = st.form_submit_button("💾 Guardar", use_container_width=True)

                if submitted and titulo.strip():
                    libro_id = agregar_libro_por_procesar(
                        f"{titulo}.manual", "manual", 0,
                        "Otro", f"manual_{titulo[:10]}"
                    )
                    guardar_metadatos_ia(libro_id, {
                        "titulo":              titulo,
                        "autor":               autor or "Desconocido",
                        "categoria_principal": categoria,
                        "descripcion":         descripcion,
                        "total_paginas":       paginas,
                        "fuente_metadatos":    "Manual",
                        "confianza_ia":        10,
                        "subcategorias":       [],
                        "temas_clave":         [],
                        "autores_adicionales": [],
                        "notas_bibliotecaria": "Ingresado manualmente",
                    })
                    st.success("✅ Libro guardado")
                    st.rerun()

    # ── PASO 2 — IA procesando ───────────────────────────────
    elif (st.session_state.libro_en_proceso
          and not st.session_state.metadatos_propuestos):

        st.markdown("### ⏳ Paso 2: Bibliotecaria IA analizando...")

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
                        st.session_state.get("pdf_contenido", b""),
                        libro["nombre_archivo"]
                    )
                except Exception as e:
                    st.warning(f"⚠️ Error en IA: {e}. Usando fallback.")
                    metadatos = {
                        "titulo": (libro["nombre_archivo"]
                                   .replace(".pdf","").replace("_"," ").title()),
                        "autor":               "Desconocido",
                        "categoria_principal": "Otros",
                        "descripcion":         "Completa manualmente.",
                        "total_paginas":       0,
                        "confianza_ia":        1,
                        "fuente_metadatos":    "Manual_Fallback",
                        "temas_clave":         [],
                        "subcategorias":       [],
                    }
            st.session_state.metadatos_propuestos = metadatos
            st.session_state._ia_procesando        = False
            st.rerun()

    # ── PASO 3 — Revisar y confirmar ─────────────────────────
    elif st.session_state.metadatos_propuestos:

        st.markdown("### ✅ Paso 3: Revisar y confirmar")
        meta      = st.session_state.metadatos_propuestos
        confianza = int(meta.get("confianza_ia") or
                        meta.get("confianza_extraccion") or 5)
        color_c   = ("#3fb950" if confianza >= 7
                     else "#e3b341" if confianza >= 5 else "#f85149")

        todas_tags = (parsear_lista(meta.get("temas_clave", [])) +
                      parsear_lista(meta.get("subcategorias", [])))
        if todas_tags:
            badges = " ".join(
                f"<span style='background:#0d1117;color:#e3b341;"
                f"border:1px solid #e3b341;border-radius:20px;"
                f"padding:0.15rem 0.6rem;font-size:0.75rem;"
                f"margin-right:0.3rem;'>✨ {t}</span>"
                for t in todas_tags[:10]
            )
            st.markdown("**🤖 Etiquetas sugeridas:**")
            st.markdown(badges, unsafe_allow_html=True)
            st.markdown("")

        st.markdown(f"""
<div style="background:#161b22;padding:1rem;border-radius:8px;margin-bottom:1rem;">
    <span>🤖 Confianza IA: </span>
    <strong style="color:{color_c};">{confianza}/10</strong>
    <div style="background:#21262d;height:6px;border-radius:3px;margin-top:0.5rem;">
        <div style="background:{color_c};width:{confianza*10}%;height:100%;border-radius:3px;"></div>
    </div>
</div>
        """, unsafe_allow_html=True)

        with st.form("revisar_metadatos", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                titulo_f    = st.text_input("Título *",    value=meta.get("titulo") or "")
                autor_f     = st.text_input("Autor",       value=meta.get("autor") or "")
                isbn_f      = st.text_input("ISBN",        value=meta.get("isbn") or "")
                editorial_f = st.text_input("Editorial",   value=meta.get("editorial") or "")
            with col2:
                cats    = ["Teologia","Programacion","Matrimonio",
                           "Filosofia","Liderazgo","Historia","Otros"]
                cat_val = meta.get("categoria_principal", "Otros")
                categoria_f = st.selectbox(
                    "Categoría", cats,
                    index=cats.index(cat_val) if cat_val in cats else 6
                )
                anio_f    = st.number_input("Año", min_value=1000, max_value=2030,
                                            value=int(meta.get("anio_publicacion") or 2020))
                paginas_f = st.number_input("Total páginas", min_value=1,
                                            value=int(meta.get("total_paginas") or 100))

            desc_f = st.text_area("Descripción",
                                  value=meta.get("descripcion") or "", height=100)

            st.markdown("**🏷️ Etiquetas**")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                temas_f = st.text_input(
                    "Temas clave (separados por coma)",
                    value=", ".join(parsear_lista(meta.get("temas_clave", [])))
                )
            with col_t2:
                subcats_f = st.text_input(
                    "Subcategorías (separadas por coma)",
                    value=", ".join(parsear_lista(meta.get("subcategorias", [])))
                )

            col_g, col_c = st.columns(2)
            with col_g:
                guardar = st.form_submit_button(
                    "✅ Guardar en biblioteca",
                    use_container_width=True, type="primary"
                )
            with col_c:
                cancelar = st.form_submit_button("❌ Cancelar", use_container_width=True)

            if guardar:
                if not titulo_f.strip():
                    st.error("⚠️ El título es obligatorio")
                else:
                    guardar_metadatos_ia(
                        st.session_state.libro_en_proceso,
                        {
                            "titulo":              titulo_f.strip(),
                            "autor":               autor_f.strip(),
                            "isbn":                isbn_f.strip(),
                            "editorial":           editorial_f.strip(),
                            "anio_publicacion":    int(anio_f),
                            "categoria_principal": categoria_f,
                            "total_paginas":       int(paginas_f),
                            "descripcion":         desc_f.strip(),
                            "temas_clave":  [t.strip() for t in temas_f.split(",") if t.strip()],
                            "subcategorias":[s.strip() for s in subcats_f.split(",") if s.strip()],
                            "autores_adicionales": meta.get("autores_adicionales", []),
                            "notas_bibliotecaria": meta.get("notas_bibliotecaria", ""),
                            "fuente_metadatos":    meta.get("fuente_metadatos", "IA"),
                            "confianza_ia":        confianza,
                        }
                    )
                    for k in ["libro_en_proceso","metadatos_propuestos",
                               "_ia_procesando","pdf_contenido"]:
                        st.session_state.pop(k, None)
                    st.session_state.libro_en_proceso     = None
                    st.session_state.metadatos_propuestos = None
                    st.session_state._ia_procesando       = False
                    st.success("✅ ¡Libro catalogado!")
                    st.rerun()

            if cancelar:
                for k in ["libro_en_proceso","metadatos_propuestos",
                           "_ia_procesando","pdf_contenido"]:
                    st.session_state.pop(k, None)
                st.session_state.libro_en_proceso     = None
                st.session_state.metadatos_propuestos = None
                st.session_state._ia_procesando       = False
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: CATÁLOGO
# ═══════════════════════════════════════════════════════════════

with tab_catalogo:
    st.subheader("Todos los libros")

    if "cat_pagina" not in st.session_state:
        st.session_state.cat_pagina = 1

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_estado = st.selectbox(
            "Estado",
            ["Todos","por_procesar","catalogado","leyendo","completado","pausado"],
            key="filtro_estado_cat"
        )
    with col_f2:
        filtro_categoria = st.selectbox(
            "Categoría",
            ["Todas","Teologia","Programacion","Matrimonio",
             "Filosofia","Liderazgo","Historia","Otros"],
            key="filtro_categoria_cat"
        )
    with col_f3:
        filtro_color = st.selectbox(
            "Resaltados",
            ["Todos","Ninguno","Amarillo","Verde","Morado","Rosa","Azul"],
            key="filtro_color_cat"
        )

    busqueda = st.text_input(
        "🔍 Buscar",
        placeholder="Título, autor, descripción, temas clave, subcategorías...",
        key="busqueda_cat"
    )

    col_pp, col_reset = st.columns([2, 1])
    with col_pp:
        por_pagina = st.select_slider(
            "Libros por página", options=[5,10,20,50], value=10, key="por_pagina_cat"
        )
    with col_reset:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Resetear filtros", use_container_width=True):
            st.session_state.cat_pagina = 1
            st.rerun()

    filtros_key = f"{filtro_estado}_{filtro_categoria}_{filtro_color}_{busqueda}_{por_pagina}"
    if "filtros_prev" not in st.session_state:
        st.session_state.filtros_prev = filtros_key
    if st.session_state.filtros_prev != filtros_key:
        st.session_state.cat_pagina   = 1
        st.session_state.filtros_prev = filtros_key

    libros, total = obtener_libros_por_estado(
        estado=None if filtro_estado    == "Todos" else filtro_estado,
        categoria=None if filtro_categoria == "Todas" else filtro_categoria,
        color=None if filtro_color      == "Todos" else filtro_color,
        busqueda=busqueda,
        pagina=st.session_state.cat_pagina,
        por_pagina=por_pagina,
    )
    total_paginas = max(1, -(-total // por_pagina))

    st.divider()
    inicio = (st.session_state.cat_pagina - 1) * por_pagina + 1
    fin    = min(st.session_state.cat_pagina * por_pagina, total)
    if total > 0:
        st.caption(
            f"Mostrando **{inicio}–{fin}** de **{total}** libros "
            f"· Página **{st.session_state.cat_pagina}** de **{total_paginas}**"
        )
    else:
        st.caption("Sin resultados")

    ESTADOS_LIBRO  = ["por_procesar","catalogado","leyendo","pausado","completado","abandonado"]
    EMOJI_ESTADO   = {
        "por_procesar":"⏳","catalogado":"📚",
        "leyendo":"🔥","pausado":"⏸️",
        "completado":"✅","abandonado":"🗑️"
    }
    CATS_LIBRO = ["Teologia","Programacion","Matrimonio",
                  "Filosofia","Liderazgo","Historia","Otros"]

    if not libros:
        st.info("📭 No se encontraron libros con estos filtros")
    else:
        for libro in libros:
            emoji_e    = EMOJI_ESTADO.get(libro["estado"], "📖")
            pag_actual = libro["pagina_actual"] or 0
            total_pags = libro["total_paginas"] or 0
            prog_pct   = (min(100, int(pag_actual / total_pags * 100))
                          if total_pags > 0 else 0)
            todas_tags = (parsear_lista(libro.get("temas_clave")) +
                          parsear_lista(libro.get("subcategorias")))

            with st.container():
                col_h, col_e = st.columns([6, 1])
                with col_h:
                    st.markdown(f"### {emoji_e} {libro['titulo'] or 'Sin título'}")
                with col_e:
                    st.caption(libro["estado"].replace("_"," "))

                st.caption(
                    f"**{libro['autor'] or 'Autor desconocido'}** "
                    f"• {libro['categoria_principal'] or 'Sin categoría'}"
                )

                if todas_tags:
                    badges = " ".join(
                        f"<span style='background:#21262d;color:#58a6ff;"
                        f"border:1px solid #30363d;border-radius:20px;"
                        f"padding:0.15rem 0.6rem;font-size:0.72rem;"
                        f"margin-right:0.3rem;display:inline-block;"
                        f"margin-bottom:0.2rem;'>🏷️ {tag}</span>"
                        for tag in todas_tags[:8]
                    )
                    st.markdown(badges, unsafe_allow_html=True)
                    st.markdown("")

                desc = libro["descripcion"] or "Sin descripción"
                st.write(desc[:120] + "..." if len(desc) > 120 else desc)
                st.progress(
                    prog_pct / 100,
                    text=f"{pag_actual} / {total_pags or '?'} páginas ({prog_pct}%)"
                )

                with st.expander("⚙️ Gestionar libro"):
                    key_base = f"cat_{libro['id']}"
                    tab_prog, tab_edit, tab_del = st.tabs(
                        ["📖 Progreso", "✏️ Editar", "🗑️ Eliminar"]
                    )

                    with tab_prog:
                        nueva_pagina = st.number_input(
                            "Página actual", min_value=0,
                            max_value=total_pags or 9999,
                            value=pag_actual, key=f"pag_{key_base}"
                        )
                        nuevo_estado = st.selectbox(
                            "Estado", ESTADOS_LIBRO,
                            index=ESTADOS_LIBRO.index(libro["estado"])
                            if libro["estado"] in ESTADOS_LIBRO else 1,
                            key=f"est_{key_base}"
                        )
                        if st.button("💾 Guardar progreso",
                                     key=f"upd_{key_base}",
                                     use_container_width=True):
                            actualizar_progreso(libro["id"], nueva_pagina, nuevo_estado)
                            st.success("✅ Progreso guardado")
                            st.rerun()

                    with tab_edit:
                        with st.form(f"form_edit_{libro['id']}"):
                            col_e1, col_e2 = st.columns(2)
                            with col_e1:
                                titulo_e    = st.text_input("Título",
                                    value=libro.get("titulo") or "")
                                autor_e     = st.text_input("Autor",
                                    value=libro.get("autor") or "")
                                editorial_e = st.text_input("Editorial",
                                    value=libro.get("editorial") or "")
                                isbn_e      = st.text_input("ISBN",
                                    value=libro.get("isbn") or "")
                            with col_e2:
                                cat_val_e   = libro.get("categoria_principal", "Otros")
                                categoria_e = st.selectbox(
                                    "Categoría", CATS_LIBRO,
                                    index=CATS_LIBRO.index(cat_val_e)
                                    if cat_val_e in CATS_LIBRO else 6
                                )
                                anio_e    = st.number_input("Año", min_value=1000,
                                    max_value=2030,
                                    value=int(libro.get("anio_publicacion") or 2020))
                                paginas_e = st.number_input("Total páginas",
                                    min_value=1,
                                    value=int(libro.get("total_paginas") or 100))
                            desc_e    = st.text_area("Descripción",
                                value=libro.get("descripcion") or "", height=80)
                            temas_e   = st.text_input("Temas clave (separados por coma)",
                                value=", ".join(parsear_lista(libro.get("temas_clave"))))
                            subcats_e = st.text_input("Subcategorías (separadas por coma)",
                                value=", ".join(parsear_lista(libro.get("subcategorias"))))

                            if st.form_submit_button("💾 Guardar cambios",
                                                     use_container_width=True,
                                                     type="primary"):
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
                                    json.dumps([t.strip() for t in temas_e.split(",") if t.strip()]),
                                    json.dumps([s.strip() for s in subcats_e.split(",") if s.strip()]),
                                    datetime.now().isoformat(),
                                    libro["id"],
                                ])
                                st.success("✅ Libro actualizado")
                                st.rerun()

                    with tab_del:
                        st.warning(
                            f"⚠️ Eliminarás **{libro.get('titulo','este libro')}** "
                            f"y todos sus resaltados permanentemente."
                        )
                        confirmar = st.checkbox(
                            "Confirmo que quiero eliminar este libro",
                            key=f"confirm_del_{key_base}"
                        )
                        if st.button("🗑️ Eliminar libro",
                                     key=f"del_{key_base}",
                                     type="secondary",
                                     use_container_width=True):
                            if not confirmar:
                                st.error("Marca la casilla de confirmación primero")
                            else:
                                eliminar_libro(libro["id"])
                                st.success("🗑️ Libro eliminado")
                                st.rerun()

            st.divider()

    # ── Paginación ────────────────────────────────────────────
    if total_paginas > 1:
        st.markdown("---")
        mitad   = 2
        pag_min = max(1, st.session_state.cat_pagina - mitad)
        pag_max = min(total_paginas, pag_min + 4)
        pag_min = max(1, pag_max - 4)
        rango   = list(range(pag_min, pag_max + 1))

        cols_pag = st.columns(len(rango) + 2)
        pag_act  = st.session_state.cat_pagina

        with cols_pag[0]:
            if st.button("◀", disabled=pag_act == 1,
                         use_container_width=True, key="pag_prev"):
                st.session_state.cat_pagina -= 1
                st.rerun()

        for j, num_pag in enumerate(rango):
            with cols_pag[j + 1]:
                if st.button(
                    f"**{num_pag}**" if num_pag == pag_act else str(num_pag),
                    key=f"pag_{num_pag}",
                    use_container_width=True,
                    type="primary" if num_pag == pag_act else "secondary"
                ):
                    st.session_state.cat_pagina = num_pag
                    st.rerun()

        with cols_pag[-1]:
            if st.button("▶", disabled=pag_act == total_paginas,
                         use_container_width=True, key="pag_next"):
                st.session_state.cat_pagina += 1
                st.rerun()

        col_goto, _ = st.columns([1, 3])
        with col_goto:
            goto = st.number_input("Ir a página", min_value=1,
                                   max_value=total_paginas,
                                   value=pag_act, step=1, key="goto_pag")
            if st.button("Ir →", use_container_width=True, key="btn_goto"):
                st.session_state.cat_pagina = goto
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 3: EN LECTURA
# ═══════════════════════════════════════════════════════════════

with tab_leyendo:
    st.subheader("🔥 Lectura Activa")

    libros_leyendo, _ = obtener_libros_por_estado("leyendo", por_pagina=50)

    if not libros_leyendo:
        st.info("🔥 No hay libros en lectura activa.")
    else:
        EMOJIS_COLOR = {
            "Amarillo":"🟡","Verde":"🟢",
            "Azul":"🔵","Rosa":"🩷","Morado":"🟣"
        }

        for libro in libros_leyendo:
            pag_actual = libro["pagina_actual"] or 0
            total      = libro["total_paginas"] or 1
            progreso   = min(100, int(pag_actual / total * 100))
            pag_rest   = total - pag_actual
            dias_est   = max(1, pag_rest // 20)
            tags       = (parsear_lista(libro.get("temas_clave")) +
                          parsear_lista(libro.get("subcategorias")))

            st.markdown(f"### 🔥 {libro['titulo'] or 'Sin título'}")
            st.caption(
                f"*{libro['autor'] or 'Autor desconocido'}* "
                f"• {libro['categoria_principal'] or 'Sin categoría'}"
            )

            if tags:
                badges = " ".join(
                    f"<span style='background:#21262d;color:#58a6ff;"
                    f"border:1px solid #30363d;border-radius:20px;"
                    f"padding:0.15rem 0.6rem;font-size:0.72rem;"
                    f"margin-right:0.3rem;'>🏷️ {t}</span>"
                    for t in tags[:6]
                )
                st.markdown(badges, unsafe_allow_html=True)
                st.markdown("")

            st.progress(progreso / 100,
                        text=f"📖 {pag_actual} / {total} páginas — {progreso}%")

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Progreso",  f"{progreso}%")
            col_m2.metric("Página",    f"{pag_actual}/{total}")
            col_m3.metric("Restantes", f"{pag_rest} págs")
            col_m4.metric("Estimado",  f"~{dias_est} días")
            st.markdown("")

            col_upd, col_res = st.columns(2)
            key_b = f"ley_{libro['id']}"

            with col_upd:
                with st.expander("📖 Actualizar progreso"):
                    nueva_pag = st.number_input(
                        "Página actual", min_value=0,
                        max_value=total, value=pag_actual,
                        key=f"npag_{key_b}"
                    )
                    nueva_pag_slider = st.slider(
                        "O usa el slider", min_value=0,
                        max_value=total, value=pag_actual,
                        key=f"slid_{key_b}"
                    )
                    pag_guardar = max(nueva_pag, nueva_pag_slider)
                    nuevo_estado = st.selectbox(
                        "Estado",
                        ["leyendo","pausado","completado","abandonado"],
                        index=0, key=f"nest_{key_b}"
                    )
                    st.text_input(
                        "Nota rápida (opcional)",
                        placeholder="Ej: Capítulo 5 terminado...",
                        key=f"nota_{key_b}"
                    )
                    if st.button("💾 Guardar progreso",
                                 key=f"upd_{key_b}",
                                 use_container_width=True, type="primary"):
                        actualizar_progreso(libro["id"], pag_guardar, nuevo_estado)
                        st.success(f"✅ Guardado — pág. {pag_guardar} · {nuevo_estado}")
                        st.rerun()

            with col_res:
                with st.expander("🎨 Agregar resaltado"):
                    key_r  = f"res_{libro['id']}"
                    pag_r  = st.number_input(
                        "Página", min_value=1, max_value=total,
                        value=pag_actual or 1, key=f"pres_{key_r}"
                    )
                    color_r = st.selectbox(
                        "Color / Tipo",
                        ["Amarillo","Verde","Azul","Rosa","Morado"],
                        format_func=lambda x: {
                            "Amarillo":"🟡 Concepto clave",
                            "Verde":   "🟢 Aplicación práctica",
                            "Azul":    "🔵 Duda / Investigar",
                            "Rosa":    "🩷 Cita importante",
                            "Morado":  "🟣 Idea propia",
                        }[x],
                        key=f"cres_{key_r}"
                    )
                    texto_r = st.text_area(
                        "Texto resaltado *", height=80,
                        placeholder="Copia aquí el texto...",
                        key=f"tres_{key_r}"
                    )
                    nota_r = st.text_area(
                        "Tu nota personal", height=60,
                        placeholder="¿Por qué es importante?",
                        key=f"nres_{key_r}"
                    )
                    if st.button("🎨 Guardar resaltado",
                                 key=f"btnres_{key_r}",
                                 use_container_width=True, type="primary"):
                        if not texto_r.strip():
                            st.error("⚠️ El texto del resaltado es obligatorio")
                        else:
                            agregar_resaltado(
                                libro["id"], pag_r,
                                texto_r.strip(), color_r, nota_r, ""
                            )
                            st.success(f"✅ Guardado — Pág. {pag_r} · {color_r}")
                            st.rerun()

                    resaltados_libro = obtener_resaltados(libro["id"])
                    if resaltados_libro:
                        st.divider()
                        st.caption(f"📑 {len(resaltados_libro)} resaltados")
                        por_color: dict = {}
                        for r in resaltados_libro:
                            c = r["color_etiqueta"]
                            por_color[c] = por_color.get(c, 0) + 1
                        st.caption(" · ".join(
                            f"{EMOJIS_COLOR.get(c,'⚪')} {n}"
                            for c, n in por_color.items()
                        ))

            st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 4: MIS RESALTADOS
# ═══════════════════════════════════════════════════════════════

with tab_resaltados:
    st.subheader("Sistema de resaltados")

    libros_disponibles, _ = obtener_libros_por_estado(por_pagina=9999)
    libros_con_id = [
        (l["id"],
         f"{l['titulo'] or 'Sin título'} - {l['autor'] or 'Desconocido'}")
        for l in libros_disponibles
        if l["estado"] != "por_procesar"
    ]

    if not libros_con_id:
        st.info("📚 Primero debes catalogar libros para agregar resaltados")
    else:
        default_index = 0
        if st.session_state.get("libro_para_resaltar"):
            idx = next(
                (i for i, (lid, _) in enumerate(libros_con_id)
                 if lid == st.session_state["libro_para_resaltar"]),
                0
            )
            default_index = idx
            st.session_state["libro_para_resaltar"] = None

        libro_sel = st.selectbox(
            "Seleccionar libro",
            options=[l[0] for l in libros_con_id],
            format_func=lambda x: next(
                l[1] for l in libros_con_id if l[0] == x
            ),
            index=default_index,
            key="sel_libro_res"
        )

        libro_actual = obtener_libro(libro_sel)
        col_form, col_lista = st.columns([1, 2])

        with col_form:
            st.markdown("### ➕ Nuevo resaltado")
            with st.form("nuevo_resaltado", clear_on_submit=True):
                pagina_res = st.number_input(
                    "Página", min_value=1,
                    max_value=libro_actual["total_paginas"] or 9999,
                    value=libro_actual["pagina_actual"] or 1
                )
                color_res = st.selectbox(
                    "Color / Tipo",
                    [("Amarillo","🟡 Concepto clave"),
                     ("Verde",   "🟢 Aplicación práctica"),
                     ("Azul",    "🔵 Duda / Investigar"),
                     ("Rosa",    "🩷 Cita importante"),
                     ("Morado",  "🟣 Idea propia")],
                    format_func=lambda x: x[1],
                    key="color_res"
                )[0]
                texto_res   = st.text_area("Texto resaltado *",
                    placeholder="Copia aquí el texto...", height=100)
                contexto_res = st.text_area("Contexto (opcional)",
                    placeholder="Párrafo completo...", height=80)
                nota_res     = st.text_area("Tu nota personal",
                    placeholder="¿Por qué es importante?", height=80)

                if st.form_submit_button("💾 Guardar resaltado",
                                         use_container_width=True):
                    if texto_res.strip():
                        agregar_resaltado(
                            libro_sel, pagina_res,
                            texto_res.strip(), color_res,
                            nota_res, contexto_res
                        )
                        st.success("✅ Resaltado guardado")
                        st.rerun()
                    else:
                        st.error("⚠️ El texto del resaltado es obligatorio")

        with col_lista:
            st.markdown(
                f"### 📑 Resaltados de: **{libro_actual['titulo'] or 'Sin título'}**"
            )
            filtro_c = st.selectbox(
                "Filtrar por color",
                ["Todos","Amarillo","Verde","Azul","Rosa","Morado"],
                key="filtro_res"
            )
            resaltados = obtener_resaltados(
                libro_sel, None if filtro_c == "Todos" else filtro_c
            )

            if not resaltados:
                st.info("📝 Aún no tienes resaltados en este libro")
            else:
                por_color: dict = {}
                for r in resaltados:
                    por_color[r["color_etiqueta"]] = (
                        por_color.get(r["color_etiqueta"], 0) + 1
                    )
                cols_stat = st.columns(len(por_color) or 1)
                EMOJIS_RES = {
                    "Amarillo":"🟡","Verde":"🟢",
                    "Azul":"🔵","Rosa":"🩷","Morado":"🟣"
                }
                for (color, cantidad), col in zip(por_color.items(), cols_stat):
                    col.metric(
                        f"{EMOJIS_RES.get(color,'⚪')} {color}", cantidad
                    )

                st.divider()
                for res in resaltados:
                    clase = f"resaltado-{res['color_etiqueta'].lower()}"
                    emoji = EMOJIS_RES.get(res["color_etiqueta"], "⚪")
                    nota_div = (
                        f"<div style='color:#8b949e;font-size:0.875rem;"
                        f"margin-top:0.5rem;'>📝 {res['nota_personal']}</div>"
                        if res.get("nota_personal") else ""
                    )
                    texto_preview = res["texto_resaltado"][:200] + (
                        "..." if len(res["texto_resaltado"]) > 200 else ""
                    )
                    st.markdown(f"""
<div class="{clase}" style="padding:1rem;border-radius:8px;margin-bottom:0.75rem;">
    <div style="display:flex;justify-content:space-between;
                align-items:center;margin-bottom:0.5rem;">
        <span>{emoji} <strong>Pág. {res['pagina']}</strong></span>
        <span style="font-size:0.75rem;color:#8b949e;">
            {res['fecha_resaltado']}
        </span>
    </div>
    <div style="color:#f0f6fc;font-style:italic;margin-bottom:0.5rem;">
        "{texto_preview}"
    </div>
    {nota_div}
</div>
                    """, unsafe_allow_html=True)

st.divider()
st.caption("📚 Biblioteca Digital • IA + Resaltados personales")