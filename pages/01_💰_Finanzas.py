"""
💰 Finanzas Personales - Módulo de gestión de gastos
"""

import streamlit as st
from datetime import date, datetime
import sys
from pathlib import Path

# Agregar app al path para importar database
sys.path.append(str(Path(__file__).parent.parent))
from app.database import (
    init_database, agregar_gasto, obtener_gastos, 
    actualizar_gasto, eliminar_gasto, resumen_mensual
)

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE PÁGINA
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Finanzas | Mission Dashboard",
    page_icon="💰",
    layout="wide"
)

# Inicializar base de datos
init_database()

# ═══════════════════════════════════════════════════════════════
# CSS PERSONALIZADO (heredado del tema oscuro)
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .finanza-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .categoria-hogar { border-left: 4px solid #58a6ff; }
    .categoria-instituto { border-left: 4px solid #a371f7; }
    .categoria-programacion { border-left: 4px solid #3fb950; }
    .categoria-citas { border-left: 4px solid #f778ba; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("💰 Finanzas Personales")
st.caption("Gestión de gastos con presupuesto mensual")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR - FILTROS Y ACCIONES RÁPIDAS
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚡ Acciones")
    
    # Selector de mes/año
    col_mes, col_anio = st.columns(2)
    with col_mes:
        mes_actual = st.selectbox(
            "Mes",
            range(1, 13),
            index=date.today().month - 1,
            format_func=lambda x: ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][x-1]
        )
    with col_anio:
        anio_actual = st.number_input("Año", 2024, 2030, date.today().year)
    
    st.divider()
    
    # Botón para nuevo gasto (abre formulario abajo)
    st.info("Usa el formulario en la pestaña '➕ Nuevo Gasto'")

# ═══════════════════════════════════════════════════════════════
# TABS PRINCIPALES
# ═══════════════════════════════════════════════════════════════

tab_resumen, tab_nuevo, tab_historial, tab_editar = st.tabs([
    "📊 Resumen", "➕ Nuevo Gasto", "📜 Historial", "✏️ Editar/Eliminar"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: RESUMEN DEL MES
# ═══════════════════════════════════════════════════════════════

with tab_resumen:
    resumen = resumen_mensual(mes_actual, anio_actual)
    
    # ═════════════════════════════════════════════════════════
    # FUNCIÓN AUXILIAR: Definida ANTES de usarla
    # ═════════════════════════════════════════════════════════
    
    def renderizar_tarjeta_categoria(cat: dict):
        """Renderiza una tarjeta de categoría financiera"""
        categoria_nombre = cat.get('categoria', 'Sin_Categoria')
        css_class = f"categoria-{categoria_nombre.lower().replace('_', '-')}"
        
        # Color de progreso
        porcentaje = cat['porcentaje_usado']
        if porcentaje < 70:
            color_bar = "#3fb950"  # verde
        elif porcentaje < 90:
            color_bar = "#e3b341"  # amarillo
        else:
            color_bar = "#f85149"  # rojo
        
        # Emoji según categoría
        emoji_cat = {
            "Hogar": "🏠",
            "Instituto": "📚",
            "Programacion": "💻",
            "Citas_Esposa": "💑"
        }.get(categoria_nombre, "💰")
        
        nombre_legible = categoria_nombre.replace('_', ' ')
        
        st.markdown(f"""
        <div class="finanza-card {css_class}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="color: #f0f6fc; font-weight: 600;">{emoji_cat} {nombre_legible}</span>
                <span style="color: {color_bar}; font-weight: 600;">{porcentaje:.0f}%</span>
            </div>
            <div style="background: #21262d; border-radius: 4px; height: 8px; margin-bottom: 0.75rem;">
                <div style="background: {color_bar}; width: {min(porcentaje, 100)}%; height: 100%; border-radius: 4px;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 0.875rem;">
                <span style="color: #8b949e;">Gastado: ${cat['gastado']:,.0f}</span>
                <span style="color: #8b949e;">Límite: ${cat['limite']:,.0f}</span>
            </div>
            <div style="color: {'#3fb950' if cat['disponible'] > 0 else '#f85149'}; font-size: 0.875rem; margin-top: 0.25rem;">
                {'✓' if cat['disponible'] > 0 else '⚠'} Disponible: ${cat['disponible']:,.0f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ═════════════════════════════════════════════════════════
    # MÉTRICAS GLOBALES
    # ═════════════════════════════════════════════════════════
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Gastado",
            f"${resumen['total_gastado']:,.0f}",
            f"-{resumen['porcentaje_global']}% del presupuesto"
        )
    with col2:
        st.metric(
            "Presupuesto Total",
            f"${resumen['total_presupuesto']:,.0f}"
        )
    with col3:
        color = "normal" if resumen['total_disponible'] > 0 else "inverse"
        st.metric(
            "Disponible",
            f"${resumen['total_disponible']:,.0f}",
            delta_color=color
        )
    with col4:
        activas = len([c for c in resumen['categorias'] if c['gastado'] > 0])
        st.metric(
            "Categorías",
            f"{activas}/4 activas"
        )
    
    st.divider()
    
    # ═════════════════════════════════════════════════════════
    # DESGLOSE POR CATEGORÍA - GRID DE 2 COLUMNAS
    # ═════════════════════════════════════════════════════════
    
    st.subheader("Desglose por Categoría")
    
    categorias = resumen['categorias']
    
    # Crear filas de 2 columnas cada vez
    for i in range(0, len(categorias), 2):
        col_izq, col_der = st.columns(2)
        
        # Primera categoría de la fila
        if i < len(categorias):
            with col_izq:
                renderizar_tarjeta_categoria(categorias[i])
        
        # Segunda categoría de la fila
        if i + 1 < len(categorias):
            with col_der:
                renderizar_tarjeta_categoria(categorias[i + 1])

# ═══════════════════════════════════════════════════════════════
# TAB 2: NUEVO GASTO (CREATE)
# ═══════════════════════════════════════════════════════════════

with tab_nuevo:
    st.subheader("Registrar Nuevo Gasto")
    
    with st.form("form_nuevo_gasto", clear_on_submit=True):
        col_fecha, col_cat = st.columns(2)
        
        with col_fecha:
            fecha_gasto = st.date_input(
                "Fecha",
                value=date.today(),
                max_value=date.today()
            )
        
        with col_cat:
            categoria = st.selectbox(
                "Categoría",
                ["Hogar", "Instituto", "Programacion", "Citas_Esposa"],
                format_func=lambda x: {
                    "Hogar": "🏠 Hogar",
                    "Instituto": "📚 Instituto",
                    "Programacion": "💻 Programación",
                    "Citas_Esposa": "💑 Citas con Esposa"
                }[x]
            )
        
        descripcion = st.text_input(
            "Descripción",
            placeholder="Ej: Compra de libros, Cena aniversario..."
        )
        
        col_monto, col_notas = st.columns([1, 2])
        
        with col_monto:
            monto = st.number_input(
                "Monto ($)",
                min_value=0.01,
                step=100.0,
                format="%.2f"
            )
        
        with col_notas:
            notas = st.text_input(
                "Notas (opcional)",
                placeholder="Detalles adicionales..."
            )
        
        submitted = st.form_submit_button("💾 Guardar Gasto", use_container_width=True)
        
        if submitted:
            if not descripcion:
                st.error("⚠️ La descripción es obligatoria")
            elif monto <= 0:
                st.error("⚠️ El monto debe ser mayor a 0")
            else:
                nuevo_id = agregar_gasto(
                    fecha=fecha_gasto,
                    categoria=categoria,
                    descripcion=descripcion,
                    monto=monto,
                    notas=notas
                )
                st.success(f"✅ Gasto guardado con ID: {nuevo_id}")
                st.balloons()

# ═══════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL (READ)
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.subheader("Historial de Gastos")
    
    # Filtros adicionales
    col_filtro1, col_filtro2 = st.columns(2)
    
    with col_filtro1:
        filtro_categoria = st.selectbox(
            "Filtrar por categoría",
            ["Todas", "Hogar", "Instituto", "Programacion", "Citas_Esposa"],
            format_func=lambda x: x if x == "Todas" else {
                "Hogar": "🏠 Hogar",
                "Instituto": "📚 Instituto",
                "Programacion": "💻 Programación",
                "Citas_Esposa": "💑 Citas con Esposa"
            }.get(x, x)
        )
    
    with col_filtro2:
        limite_registros = st.slider("Mostrar últimos:", 10, 100, 20)
    
    # Obtener datos
    categoria_filtro = None if filtro_categoria == "Todas" else filtro_categoria
    gastos = obtener_gastos(
        mes=mes_actual if st.checkbox("Solo mes seleccionado", True) else None,
        anio=anio_actual if st.checkbox("Solo año seleccionado", True) else None,
        categoria=categoria_filtro,
        limite=limite_registros
    )
    
    if not gastos:
        st.info("📭 No hay gastos registrados con estos filtros")
    else:
        # Mostrar como tabla estilizada
        for gasto in gastos:
            emoji_cat = {
                "Hogar": "🏠",
                "Instituto": "📚",
                "Programacion": "💻",
                "Citas_Esposa": "💑"
            }.get(gasto['categoria'], "💰")
            
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.markdown(f"""
                    **{emoji_cat} {gasto['descripcion']}**  
                    <span style="color: #8b949e; font-size: 0.875rem;">
                        {gasto['fecha']} • ID: {gasto['id']}
                    </span>
                    """, unsafe_allow_html=True)
                    if gasto['notas']:
                        st.caption(f"📝 {gasto['notas']}")
                
                with col2:
                    st.markdown(f"""
                    <div style="text-align: right; color: #f0f6fc; font-weight: 600;">
                        ${gasto['monto']:,.2f}
                    </div>
                    """, unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f"""
                    <div style="text-align: right;">
                        <span style="background: #21262d; padding: 0.25rem 0.5rem; 
                                     border-radius: 4px; font-size: 0.75rem; color: #8b949e;">
                            {gasto['categoria'].replace('_', ' ')}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 4: EDITAR/ELIMINAR (UPDATE & DELETE)
# ═══════════════════════════════════════════════════════════════

with tab_editar:
    st.subheader("Editar o Eliminar Gastos")
    
    # ═════════════════════════════════════════════════════════
    # SECCIÓN 1: BUSCAR GASTO
    # ═════════════════════════════════════════════════════════
    
    col_buscar, col_vacio = st.columns([1, 3])
    
    with col_buscar:
        id_buscar = st.number_input("ID del gasto", min_value=1, step=1, value=1)
        buscar = st.button("🔍 Buscar Gasto", use_container_width=True)
    
    # Variable para guardar el gasto encontrado
    if 'gasto_encontrado' not in st.session_state:
        st.session_state.gasto_encontrado = None
    
    if buscar:
        gastos_todos = obtener_gastos(limite=1000)
        gasto_objetivo = next((g for g in gastos_todos if g['id'] == id_buscar), None)
        
        if not gasto_objetivo:
            st.error(f"❌ No se encontró gasto con ID {id_buscar}")
            st.session_state.gasto_encontrado = None
        else:
            st.success(f"✅ Encontrado: {gasto_objetivo['descripcion']} - ${gasto_objetivo['monto']:,.2f}")
            st.session_state.gasto_encontrado = gasto_objetivo
    
    # ═════════════════════════════════════════════════════════
    # SECCIÓN 2: EDITAR (solo si se encontró)
    # ═════════════════════════════════════════════════════════
    
    if st.session_state.gasto_encontrado:
        gasto = st.session_state.gasto_encontrado
        
        st.divider()
        st.markdown("### ✏️ Editar Gasto")
        
        with st.form("form_editar"):
            col_f, col_c = st.columns(2)
            
            with col_f:
                # Convertir fecha string a objeto date
                fecha_actual = datetime.strptime(gasto['fecha'], '%Y-%m-%d').date()
                nueva_fecha = st.date_input("Fecha", value=fecha_actual)
            
            with col_c:
                categorias_lista = ["Hogar", "Instituto", "Programacion", "Citas_Esposa"]
                idx_categoria = categorias_lista.index(gasto['categoria']) if gasto['categoria'] in categorias_lista else 0
                nueva_categoria = st.selectbox(
                    "Categoría",
                    categorias_lista,
                    index=idx_categoria,
                    format_func=lambda x: {
                        "Hogar": "🏠 Hogar",
                        "Instituto": "📚 Instituto",
                        "Programacion": "💻 Programación",
                        "Citas_Esposa": "💑 Citas con Esposa"
                    }[x]
                )
            
            nueva_desc = st.text_input("Descripción", value=gasto['descripcion'])
            
            col_m, col_n = st.columns([1, 2])
            with col_m:
                nuevo_monto = st.number_input(
                    "Monto",
                    min_value=0.01,
                    value=float(gasto['monto']),
                    format="%.2f"
                )
            with col_n:
                nuevas_notas = st.text_input("Notas", value=gasto['notas'] or "")
            
            # UN SOLO BOTÓN DE SUBMIT
            guardar = st.form_submit_button("💾 Guardar Cambios", use_container_width=True)
            
            if guardar:
                exito = actualizar_gasto(
                    gasto['id'],
                    fecha=nueva_fecha,
                    categoria=nueva_categoria,
                    descripcion=nueva_desc,
                    monto=nuevo_monto,
                    notas=nuevas_notas
                )
                
                if exito:
                    st.success("✅ Gasto actualizado correctamente")
                    st.session_state.gasto_encontrado = None  # Limpiar para forzar recarga
                else:
                    st.error("❌ No se pudo actualizar")
        
        # ═════════════════════════════════════════════════════
        # SECCIÓN 3: ELIMINAR (fuera del form de editar)
        # ═════════════════════════════════════════════════════
        
        st.divider()
        st.markdown("### 🗑️ Eliminar Gasto")
        
        col_eliminar, col_confirmar = st.columns([1, 2])
        
        with col_confirmar:
            confirmar = st.checkbox("⚠️ Confirmo que quiero eliminar este gasto permanentemente")
        
        with col_eliminar:
            if st.button("🗑️ Eliminar Gasto", use_container_width=True, type="secondary"):
                if not confirmar:
                    st.warning("⚠️ Debes marcar la casilla de confirmación")
                else:
                    exito = eliminar_gasto(gasto['id'])
                    if exito:
                        st.success("🗑️ Gasto eliminado permanentemente")
                        st.session_state.gasto_encontrado = None
                        st.rerun()
                    else:
                        st.error("❌ No se pudo eliminar")

# Footer
st.divider()
st.caption("💰 Módulo Finanzas • CRUD completo implementado")