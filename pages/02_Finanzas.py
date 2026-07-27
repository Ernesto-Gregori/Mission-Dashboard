"""
💰 Finanzas Personales - Módulo de gestión de gastos
"""

import streamlit as st
from datetime import timedelta
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import (
    guardar_ingreso, obtener_ingreso,
    agregar_gasto_sobre, obtener_gastos_sobre,
    actualizar_gasto_sobre, eliminar_gasto_sobre,
    calcular_sobres, SOBRES_CONFIG,
)
from app.stability import ensure_database, after_write, invalidate_data_caches
from app.ai_client import chat_simple, api_key_configurada
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    ahora as _ahora,
)

st.set_page_config(
    page_title="Finanzas | Mission Dashboard",
    page_icon="💰",
    layout="wide"
)

from app.auth import require_auth
require_auth()
ensure_database()

# ═══════════════════════════════════════════════════════════════
# CONSTANTES UI
# ═══════════════════════════════════════════════════════════════

SUBCATEGORIAS_LABELS = {
    'Tarjeta_MSI':        '💳 Tarjeta MSI',
    'Deuda_Fija':         '📋 Deuda Fija',
    'Comida':             '🍽️ Comida',
    'Transporte':         '🚌 Transporte',
    'Servicios':          '💡 Servicios',
    'Otro_Supervivencia': '📦 Otro',
    'Ahorro_Emergencia':  '🛡️ Ahorro Emergencia',
    'Fondo_Renta':        '🏠 Fondo Renta',
    'Otro_Ahorro':        '💾 Otro Ahorro',
    'Libros_Cursos':      '📚 Libros / Cursos',
    'Cita_Esposa':        '💑 Cita con Esposa',
    'Ofrenda_Diezmo':     '⛪ Ofrenda / Diezmo',
    'Personal':           '👤 Personal',
}

SYSTEM_FINANZAS = """Eres un asesor financiero cristiano para un estudiante de teología 
en México. Usa el Sistema de 3 Sobres:
- Sobre 1 SUPERVIVENCIA (65%): gastos fijos (tarjeta, deudas) + básicos (comida, transporte)
- Sobre 2 FUTURO/HOGAR (20%): ahorro sagrado, fondo de transición para rentar al graduarse
- Sobre 3 MINISTERIO/EXTRAS (15%): libros, citas con esposa, ofrendas
Ingreso ~$200 USD/mes. Si llega menos, llenar sobres en orden. 
Excedentes van al Sobre 2. Práctico, bíblico, máx 150 palabras."""

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .sobre-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
    }
    .sobre-1 { border-left: 6px solid #f85149; }
    .sobre-2 { border-left: 6px solid #3fb950; }
    .sobre-3 { border-left: 6px solid #58a6ff; }
    .ingreso-banner {
        background: linear-gradient(135deg, #161b22, #1c2128);
        border: 1px solid #e3b341; border-radius: 12px;
        padding: 1.25rem; margin-bottom: 1.5rem;
    }
    .subcat-tag {
        display: inline-block; background: #21262d;
        border-radius: 6px; padding: 0.15rem 0.5rem;
        font-size: 0.72rem; color: #8b949e; margin-right: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — período/ingreso en form (no recarga al escribir)
# ═══════════════════════════════════════════════════════════════

hoy = _hoy()
if "fin_mes" not in st.session_state:
    st.session_state.fin_mes = hoy.month
if "fin_anio" not in st.session_state:
    st.session_state.fin_anio = hoy.year

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

with st.sidebar:
    st.header("📅 Período e ingreso")
    ingreso_guardado = obtener_ingreso(
        st.session_state.fin_mes, st.session_state.fin_anio
    )

    with st.form("form_periodo_ingreso"):
        col_m, col_a = st.columns(2)
        with col_m:
            mes_form = st.selectbox(
                "Mes", range(1, 13),
                index=st.session_state.fin_mes - 1,
                format_func=lambda x: MESES[x - 1],
            )
        with col_a:
            anio_form = st.number_input(
                "Año", 2024, 2030, int(st.session_state.fin_anio)
            )
        nuevo_ingreso = st.number_input(
            "¿Cuánto recibiste? ($MXN)",
            min_value=0.0, step=100.0,
            value=float(ingreso_guardado),
        )
        nota_ingreso = st.text_input("Nota", placeholder="Ej: Quincena + apoyo")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            aplicar = st.form_submit_button("Aplicar período", use_container_width=True)
        with col_a2:
            guardar = st.form_submit_button(
                "💾 Guardar ingreso", use_container_width=True, type="primary"
            )

        if aplicar or guardar:
            st.session_state.fin_mes = int(mes_form)
            st.session_state.fin_anio = int(anio_form)
        if guardar:
            if guardar_ingreso(
                st.session_state.fin_mes,
                st.session_state.fin_anio,
                nuevo_ingreso,
                nota_ingreso,
            ):
                after_write(rerun=True)
        elif aplicar:
            st.rerun()

    mes_actual = st.session_state.fin_mes
    anio_actual = st.session_state.fin_anio
    ingreso_vista = obtener_ingreso(mes_actual, anio_actual)

    if ingreso_vista > 0:
        st.divider()
        st.markdown("**📊 Distribución sugerida:**")
        st.markdown(f"🔴 Supervivencia (65%): `${ingreso_vista * 0.65:,.0f}`")
        st.markdown(f"🟢 Futuro/Hogar (20%):  `${ingreso_vista * 0.20:,.0f}`")
        st.markdown(f"🔵 Ministerio (15%):    `${ingreso_vista * 0.15:,.0f}`")

    st.divider()
    if api_key_configurada():
        st.success("🤖 Asesor IA activo")
    else:
        st.caption("🤖 IA offline")

# ═══════════════════════════════════════════════════════════════
# HEADER + DATOS
# ═══════════════════════════════════════════════════════════════

st.title("💰 Finanzas Personales")
st.caption("Sistema de 3 Sobres • Supervivencia → Futuro/Hogar → Ministerio/Extras")

resumen = calcular_sobres(mes_actual, anio_actual)

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_resumen, tab_nuevo, tab_historial, tab_ia, tab_editar = st.tabs([
    "📊 Resumen", "➕ Nuevo Gasto", "📜 Historial", "🤖 Asesor IA", "✏️ Editar"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: RESUMEN
# ═══════════════════════════════════════════════════════════════

with tab_resumen:

    if resumen['sin_ingreso']:
        st.warning("⚠️ No has registrado tu ingreso de este mes.")

    ingreso    = resumen['ingreso']
    gastado    = resumen['total_gastado']
    disponible = resumen['total_disponible']
    pct        = resumen['pct_global']
    color_g    = '#3fb950' if pct < 70 else '#e3b341' if pct < 90 else '#f85149'

    st.markdown(f"""
    <div class="ingreso-banner">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="color:#e3b341;font-size:0.75rem;font-weight:700;
                            text-transform:uppercase;letter-spacing:0.05em;">
                    💵 Ingreso del mes
                </div>
                <div style="color:#f0f6fc;font-size:2.2rem;font-weight:700;line-height:1.1;">
                    ${ingreso:,.0f}
                </div>
                <div style="color:#8b949e;font-size:0.8rem;">MXN</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#8b949e;font-size:0.75rem;">Gastado</div>
                <div style="color:{color_g};font-size:1.6rem;font-weight:700;">
                    ${gastado:,.0f}
                </div>
                <div style="color:{color_g};font-size:0.8rem;">{pct:.0f}% del ingreso</div>
            </div>
            <div style="text-align:right;">
                <div style="color:#8b949e;font-size:0.75rem;">Disponible</div>
                <div style="color:{'#3fb950' if disponible >= 0 else '#f85149'};
                            font-size:1.6rem;font-weight:700;">
                    ${disponible:,.0f}
                </div>
                <div style="color:#8b949e;font-size:0.75rem;">
                    {'✅ En control' if disponible >= 0 else '⚠️ Excedido'}
                </div>
            </div>
        </div>
        <div style="background:#21262d;border-radius:6px;height:10px;margin-top:1rem;">
            <div style="background:{color_g};width:{min(pct,100):.0f}%;
                        height:100%;border-radius:6px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tarjetas de los 3 sobres ──────────────────────────────
    st.subheader("📬 Los 3 Sobres")
    css_clases  = ['sobre-1', 'sobre-2', 'sobre-3']
    cols_sobres = st.columns(3)

    for i, (key, sobre) in enumerate(resumen['sobres'].items()):
        pct_s   = sobre['pct_usado']
        color_s = sobre['color']
        color_b = '#3fb950' if pct_s < 70 else '#e3b341' if pct_s < 90 else '#f85149'
        css     = css_clases[i]

        if not resumen['sin_ingreso']:
            if sobre['sobre_lleno']:
                estado_txt, estado_color = "✅ Sobre completo", '#3fb950'
            elif sobre['presupuesto'] == 0:
                estado_txt, estado_color = "⚠️ Sin fondos",    '#f85149'
            else:
                estado_txt, estado_color = "○ Sobre parcial",  '#e3b341'
        else:
            estado_txt, estado_color     = "— Sin ingreso",    '#8b949e'

        color_disp = '#3fb950' if sobre['disponible'] >= 0 else '#f85149'
        pct_int    = int(sobre['pct'] * 100)

        with cols_sobres[i]:
            st.markdown(f"""
<div class="sobre-card {css}">
    <div style="font-size:0.7rem;color:{color_s};font-weight:700;
                text-transform:uppercase;letter-spacing:0.05em;">
        {sobre['emoji']} Sobre {i+1}
    </div>
    <div style="color:#f0f6fc;font-size:1rem;font-weight:700;margin:0.2rem 0;">
        {sobre['nombre']}
    </div>
    <div style="color:#8b949e;font-size:0.75rem;margin-bottom:0.75rem;">
        {sobre['descripcion']} • {pct_int}%
    </div>
    <div style="background:#21262d;border-radius:4px;height:8px;margin-bottom:0.75rem;">
        <div style="background:{color_b};width:{min(pct_s,100):.0f}%;
                    height:100%;border-radius:4px;"></div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:0.85rem;">
        <span style="color:#f0f6fc;font-weight:600;">${sobre['gastado']:,.0f}</span>
        <span style="color:{color_b};font-weight:600;">{pct_s:.0f}%</span>
    </div>
    <div style="display:flex;justify-content:space-between;
                font-size:0.75rem;margin-top:0.2rem;">
        <span style="color:#8b949e;">de ${sobre['presupuesto']:,.0f}</span>
        <span style="color:{color_disp};">Disp: ${sobre['disponible']:,.0f}</span>
    </div>
    <div style="margin-top:0.75rem;font-size:0.72rem;
                color:{estado_color};font-weight:600;">
        {estado_txt}
    </div>
    <div style="margin-top:0.5rem;color:#8b949e;font-size:0.7rem;">
        {sobre['cantidad_gastos']} gastos registrados
    </div>
</div>
            """, unsafe_allow_html=True)

            if sobre['por_subcat'] and sobre['gastado'] > 0:
                with st.expander("Ver desglose"):
                    for sub, monto_sub in sorted(
                        sobre['por_subcat'].items(),
                        key=lambda x: x[1], reverse=True
                    ):
                        label   = SUBCATEGORIAS_LABELS.get(sub, sub)
                        pct_sub = monto_sub / sobre['gastado'] * 100
                        st.markdown(
                            f"**{label}**: ${monto_sub:,.0f} "
                            f"<span style='color:#8b949e'>({pct_sub:.0f}%)</span>",
                            unsafe_allow_html=True
                        )

    # ── Orden de llenado ─────────────────────────────────────
    if not resumen['sin_ingreso']:
        st.divider()
        st.markdown("### 📋 Orden de llenado")
        st.caption("Si el ingreso es menor a lo esperado, los sobres se llenan en este orden:")

        cols_ord    = st.columns(3)
        ingreso_sim = resumen['ingreso']

        for i, (key, sobre) in enumerate(resumen['sobres'].items()):
            presup_ideal = sobre['presupuesto_ideal']
            asignado     = min(presup_ideal, max(0, ingreso_sim))
            ingreso_sim -= presup_ideal
            lleno        = asignado >= presup_ideal

            with cols_ord[i]:
                bg_c    = '#0f2d0f' if lleno else '#1c2128'
                brd_c   = sobre['color'] if lleno else '#30363d'
                txt_c   = '#3fb950' if lleno else '#e3b341'
                est_ord = '✅ Completo' if lleno else f"${asignado:,.0f} / ${presup_ideal:,.0f}"
                st.markdown(f"""
<div style="text-align:center;padding:0.75rem;background:{bg_c};
            border-radius:8px;border:1px solid {brd_c};height:120px;
            display:flex;flex-direction:column;justify-content:center;align-items:center;">
    <div style="font-size:1.8rem;margin-bottom:0.25rem;">{sobre['emoji']}</div>
    <div style="color:#f0f6fc;font-size:0.8rem;font-weight:600;">
        {i+1}. {sobre['nombre'][:14]}
    </div>
    <div style="color:{txt_c};font-size:0.75rem;margin-top:0.4rem;font-weight:600;">
        {est_ord}
    </div>
</div>
                """, unsafe_allow_html=True)

        excedente = resumen.get('excedente', 0)
        if excedente > 0:
            st.success(
                f"💰 **Excedente este mes: ${excedente:,.0f}** "
                f"→ Va directo al Sobre 2 (Futuro/Hogar)"
            )

# ═══════════════════════════════════════════════════════════════
# TAB 2: NUEVO GASTO
# ═══════════════════════════════════════════════════════════════

with tab_nuevo:
    st.subheader("➕ Registrar Nuevo Gasto")

    if not resumen['sin_ingreso']:
        cols_disp = st.columns(3)
        for i, (key, sobre) in enumerate(resumen['sobres'].items()):
            disp = sobre['disponible']
            with cols_disp[i]:
                st.metric(
                    f"{sobre['emoji']} {sobre['nombre'][:14]}",
                    f"${disp:,.0f}",
                    delta="disponible",
                    delta_color="normal" if disp >= 0 else "inverse"
                )
        st.divider()

    with st.form("form_nuevo_gasto", clear_on_submit=True):
        col_fecha, col_sobre = st.columns(2)
        with col_fecha:
            fecha_gasto = st.date_input(
                "Fecha *",
                value=_hoy(),               # ← zona horaria local
                max_value=_hoy()            # ← zona horaria local
            )
        with col_sobre:
            sobre_sel = st.selectbox(
                "Sobre *",
                options=list(SOBRES_CONFIG.keys()),
                format_func=lambda x: (
                    f"{SOBRES_CONFIG[x]['emoji']} {SOBRES_CONFIG[x]['nombre']}"
                )
            )

        subcats      = SOBRES_CONFIG[sobre_sel]['subcategorias']
        subcategoria = st.selectbox(
            "Subcategoría *", options=subcats,
            format_func=lambda x: SUBCATEGORIAS_LABELS.get(x, x)
        )

        es_fijo = False
        if sobre_sel == 'Supervivencia':
            es_fijo = st.checkbox(
                "🔒 Es gasto fijo (Tarjeta, deuda)",
                value=subcategoria in ['Tarjeta_MSI', 'Deuda_Fija']
            )

        descripcion = st.text_input(
            "Descripción *",
            placeholder="Ej: Pago tarjeta noviembre, despensa Walmart..."
        )

        col_monto, col_notas = st.columns([1, 2])
        with col_monto:
            monto = st.number_input(
                "Monto ($MXN) *", min_value=0.01, step=50.0, format="%.2f"
            )
        with col_notas:
            notas = st.text_input("Notas (opcional)", placeholder="Detalles adicionales...")

        if monto > 0 and not resumen['sin_ingreso']:
            disp_sobre = resumen['sobres'][sobre_sel]['disponible']
            if monto > disp_sobre:
                st.warning(
                    f"⚠️ Este gasto (${monto:,.0f}) excede lo disponible en "
                    f"{SOBRES_CONFIG[sobre_sel]['nombre']} "
                    f"(${disp_sobre:,.0f} disponible)"
                )

        if st.form_submit_button("💾 Guardar Gasto", use_container_width=True, type="primary"):
            if not descripcion.strip():
                st.error("⚠️ La descripción es obligatoria")
            elif monto <= 0:
                st.error("⚠️ El monto debe ser mayor a 0")
            else:
                nuevo_id = agregar_gasto_sobre(
                    fecha=fecha_gasto, sobre=sobre_sel,
                    subcategoria=subcategoria, descripcion=descripcion,
                    monto=monto, es_fijo=es_fijo, notas=notas
                )
                st.success(
                    f"✅ Gasto guardado en "
                    f"{SOBRES_CONFIG[sobre_sel]['emoji']} "
                    f"{SOBRES_CONFIG[sobre_sel]['nombre']} · ID: {nuevo_id}"
                )
                st.balloons()
                after_write(rerun=True)

# ═══════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL
# ═══════════════════════════════════════════════════════════════

@st.fragment
def _historial_gastos_fragment(mes_actual, anio_actual):
    """Fragmento: filtrar historial sin recargar todo el módulo."""
    st.subheader("📜 Historial de Gastos")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_sobre = st.selectbox(
            "Filtrar por sobre",
            ["Todos"] + list(SOBRES_CONFIG.keys()),
            format_func=lambda x: (
                "Todos los sobres" if x == "Todos"
                else f"{SOBRES_CONFIG[x]['emoji']} {SOBRES_CONFIG[x]['nombre']}"
            )
        )
    with col_f2:
        solo_mes = st.checkbox("Solo mes seleccionado", value=True)
    with col_f3:
        limite_h = st.slider("Mostrar últimos:", 10, 100, 30)

    gastos_h = obtener_gastos_sobre(
        mes=mes_actual   if solo_mes else None,
        anio=anio_actual if solo_mes else None,
        sobre=None if filtro_sobre == "Todos" else filtro_sobre,
        limite=limite_h
    )

    if not gastos_h:
        st.info("📭 No hay gastos con estos filtros")
    else:
        total_h = sum(g['monto'] for g in gastos_h)
        st.caption(f"**{len(gastos_h)} gastos** · Total: **${total_h:,.2f}**")
        st.divider()

        for g in gastos_h:
            cfg       = SOBRES_CONFIG.get(g['sobre'], {})
            emoji_g   = cfg.get('emoji', '💰')
            color_g   = cfg.get('color', '#8b949e')
            label_sub = SUBCATEGORIAS_LABELS.get(g['subcategoria'], g['subcategoria'])

            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                fijo_tag = " 🔒" if g.get('es_fijo') else ""
                st.markdown(
                    f"**{emoji_g} {g['descripcion']}{fijo_tag}**  \n"
                    f"<span style='color:#8b949e;font-size:0.8rem;'>"
                    f"{g['fecha']} · "
                    f"<span class='subcat-tag'>{label_sub}</span>"
                    f" · ID: {g['id']}</span>",
                    unsafe_allow_html=True
                )
                if g.get('notas'):
                    st.caption(f"📝 {g['notas']}")
            with col2:
                st.markdown(
                    f"<div style='text-align:right;color:#f0f6fc;"
                    f"font-weight:700;font-size:1.1rem;'>"
                    f"${g['monto']:,.2f}</div>",
                    unsafe_allow_html=True
                )
            with col3:
                st.markdown(
                    f"<div style='text-align:right;'>"
                    f"<span style='background:{color_g}22;color:{color_g};"
                    f"padding:0.2rem 0.5rem;border-radius:4px;"
                    f"font-size:0.7rem;'>{emoji_g}</span></div>",
                    unsafe_allow_html=True
                )
            st.divider()



with tab_historial:
    _historial_gastos_fragment(mes_actual, anio_actual)

# ═══════════════════════════════════════════════════════════════
# TAB 4: ASESOR IA
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Asesor Financiero IA")

    if not api_key_configurada():
        st.warning("⚠️ IA en modo offline — respuestas predefinidas")

    def _ctx_ia(r: dict) -> str:
        dia_local = _hoy().day          # ← día local
        lineas = [
            f"Mes: {r['mes']}/{r['anio']}",
            f"Ingreso registrado: ${r['ingreso']:,.0f} MXN",
            f"Total gastado hasta hoy: ${r['total_gastado']:,.0f} MXN",
            f"Días transcurridos del mes: {dia_local}/30",
            "",
            "Estado real de cada sobre:",
        ]
        for key, s in r['sobres'].items():
            lineas.append(
                f"  {s['emoji']} {s['nombre']}:"
                f"\n     - Presupuesto asignado: ${s['presupuesto']:,.0f}"
                f"\n     - Gastado hasta hoy:    ${s['gastado']:,.0f}"
                f"\n     - Disponible:           ${s['disponible']:,.0f}"
                f"\n     - Uso:                  {s['pct_usado']:.0f}%"
            )
        lineas += [
            "",
            "IMPORTANTE: Si el gasto es 0% en un sobre, el dinero",
            "está disponible pero no usado — eso es positivo.",
        ]
        return "\n".join(lineas)

    # ── Proyección ────────────────────────────────────────────
    st.markdown("### 📈 Proyección al fin de mes")

    dias   = _hoy().day                 # ← día local
    factor = (30 / dias) if dias > 0 else 1

    cols_p = st.columns(3)
    for i, (key, sobre) in enumerate(resumen['sobres'].items()):
        proy = sobre['gastado'] * factor
        dif  = sobre['presupuesto'] - proy
        with cols_p[i]:
            st.metric(
                f"{sobre['emoji']} {sobre['nombre'][:12]}",
                f"${proy:,.0f}",
                f"{'⚠ +' if dif < 0 else '✓ -'}${abs(dif):,.0f}",
                delta_color="inverse" if dif < 0 else "normal"
            )

    if st.button("🤖 Analizar proyección", key="btn_proy"):
        riesgo = [
            s['nombre'] for s in resumen['sobres'].values()
            if s['gastado'] * factor > s['presupuesto']
        ]
        prompt = (
            f"Analiza la situación financiera:\n\n{_ctx_ia(resumen)}\n\n"
            f"Proyección ({_hoy().day} días):\n"
        )
        for key, sobre in resumen['sobres'].items():
            proy = sobre['gastado'] * factor
            dif  = sobre['presupuesto'] - proy
            prompt += (
                f"\n  {sobre['emoji']} {sobre['nombre']}: "
                f"proyectado ${proy:,.0f} de ${sobre['presupuesto']:,.0f} "
                f"({'⚠️ EXCEDE' if dif < 0 else '✅ OK'})"
            )
        prompt += f"\n\nSobres en riesgo: {riesgo or 'Ninguno'}\n\nDa 2 observaciones y 1 acción concreta."
        with st.spinner("Analizando..."):
            st.info(chat_simple(prompt, contexto=SYSTEM_FINANZAS))

    st.divider()

    # ── Estado de sobres ──────────────────────────────────────
    st.markdown("### 🚨 Estado de sobres")
    criticos = [s for s in resumen['sobres'].values() if s['pct_usado'] >= 80]

    if not criticos:
        st.success("✅ Todos los sobres dentro del presupuesto")
    else:
        for s in criticos:
            color_c = '#f85149' if s['pct_usado'] >= 100 else '#e3b341'
            st.markdown(f"""
            <div style="background:#161b22;border-left:4px solid {color_c};
                        border-radius:8px;padding:0.75rem 1rem;margin-bottom:0.5rem;">
                {'🔴' if s['pct_usado'] >= 100 else '🟡'}
                <strong>{s['nombre']}</strong> — {s['pct_usado']:.0f}% usado ·
                Disponible: ${s['disponible']:,.0f}
            </div>
            """, unsafe_allow_html=True)

        if st.button("🤖 Consejos para sobres críticos", key="btn_criticos"):
            with st.spinner("Generando consejos..."):
                st.warning(chat_simple(
                    "Sobres críticos (>80%):\n"
                    + "\n".join(
                        f"- {s['nombre']}: {s['pct_usado']:.0f}%, "
                        f"${s['disponible']:,.0f} disponible"
                        for s in criticos
                    )
                    + f"\n\n{_ctx_ia(resumen)}",
                    contexto=SYSTEM_FINANZAS
                ))

    st.divider()

    # ── Sobre 2: Futuro/Hogar ─────────────────────────────────
    st.markdown("### 🟢 Seguimiento — Futuro y Hogar")
    futuro = resumen['sobres']['Futuro_Hogar']
    col_f1, col_f2, col_f3 = st.columns(3)
    col_f1.metric("Ahorrado este mes", f"${futuro['gastado']:,.0f}")
    col_f2.metric("Meta (20%)",        f"${futuro['presupuesto']:,.0f}")
    col_f3.metric("Faltante",          f"${max(0, futuro['disponible']):,.0f}")

    st.progress(
        min(futuro['pct_usado'] / 100, 1.0),
        text=f"{'✅' if futuro['pct_usado'] >= 100 else '🟡'} "
             f"{futuro['pct_usado']:.0f}% de la meta de ahorro"
    )

    if st.button("🤖 Estrategia de ahorro", key="btn_futuro"):
        with st.spinner("Pensando..."):
            st.info(chat_simple(
                f"Sobre Futuro/Hogar: ${futuro['gastado']:,.0f} ahorrado "
                f"de ${futuro['presupuesto']:,.0f} meta.\n"
                f"Ingreso total: ${resumen['ingreso']:,.0f}\n"
                f"Meta: acumular fondo para rentar al graduarme del instituto.\n"
                f"Dame estrategia práctica para alcanzar el 20%.",
                contexto=SYSTEM_FINANZAS
            ))

    st.divider()

    # ── Chat libre ────────────────────────────────────────────
    st.markdown("### 💬 Pregunta al asesor")
    gastos_ia = obtener_gastos_sobre(mes=mes_actual, anio=anio_actual, limite=10)
    pregunta  = st.text_input(
        "Tu pregunta",
        placeholder="Ej: ¿Puedo permitirme una cena esta semana?"
    )
    if pregunta:
        ultimos = ", ".join(
            f"{g['descripcion']} ${g['monto']:,.0f}" for g in gastos_ia[:5]
        )
        with st.spinner("Pensando..."):
            st.info(chat_simple(
                f"{_ctx_ia(resumen)}\nÚltimos gastos: {ultimos}\nPregunta: {pregunta}",
                contexto=SYSTEM_FINANZAS
            ))

# ═══════════════════════════════════════════════════════════════
# TAB 5: EDITAR / ELIMINAR
# ═══════════════════════════════════════════════════════════════

with tab_editar:
    st.subheader("✏️ Editar o Eliminar Gastos")

    if 'gasto_encontrado' not in st.session_state:
        st.session_state.gasto_encontrado = None

    col_b, _ = st.columns([1, 3])
    with col_b:
        id_buscar = st.number_input("ID del gasto", min_value=1, step=1)
        if st.button("🔍 Buscar", use_container_width=True):
            todos      = obtener_gastos_sobre(limite=2000)
            encontrado = next((g for g in todos if g['id'] == id_buscar), None)
            if encontrado:
                st.session_state.gasto_encontrado = encontrado
                st.success(f"✅ {encontrado['descripcion']} · ${encontrado['monto']:,.2f}")
            else:
                st.error(f"❌ ID {id_buscar} no encontrado")
                st.session_state.gasto_encontrado = None

    if st.session_state.gasto_encontrado:
        gasto = st.session_state.gasto_encontrado
        st.divider()
        st.markdown("### ✏️ Editar")

        with st.form("form_editar"):
            col_fe, col_so = st.columns(2)
            with col_fe:
                nueva_fecha = st.date_input(
                    "Fecha",
                    value=datetime.strptime(gasto['fecha'], '%Y-%m-%d').date()
                )
            with col_so:
                sobres_lista = list(SOBRES_CONFIG.keys())
                idx_s        = sobres_lista.index(gasto['sobre']) if gasto['sobre'] in sobres_lista else 0
                nuevo_sobre  = st.selectbox(
                    "Sobre", sobres_lista, index=idx_s,
                    format_func=lambda x: (
                        f"{SOBRES_CONFIG[x]['emoji']} {SOBRES_CONFIG[x]['nombre']}"
                    )
                )

            subcats_edit = SOBRES_CONFIG[nuevo_sobre]['subcategorias']
            idx_sub      = subcats_edit.index(gasto['subcategoria']) if gasto['subcategoria'] in subcats_edit else 0
            nueva_sub    = st.selectbox(
                "Subcategoría", subcats_edit, index=idx_sub,
                format_func=lambda x: SUBCATEGORIAS_LABELS.get(x, x)
            )

            nueva_desc = st.text_input("Descripción", value=gasto['descripcion'])
            col_m, col_n = st.columns([1, 2])
            with col_m:
                nuevo_monto = st.number_input(
                    "Monto", min_value=0.01,
                    value=float(gasto['monto']), format="%.2f"
                )
            with col_n:
                nuevas_notas = st.text_input("Notas", value=gasto.get('notas') or "")

            if st.form_submit_button("💾 Guardar cambios", use_container_width=True):
                if actualizar_gasto_sobre(
                    gasto['id'],
                    fecha=nueva_fecha, sobre=nuevo_sobre,
                    subcategoria=nueva_sub, descripcion=nueva_desc,
                    monto=nuevo_monto, notas=nuevas_notas
                ):
                    st.success("✅ Gasto actualizado")
                    st.session_state.gasto_encontrado = None
                    after_write(rerun=True)
                else:
                    st.error("❌ No se pudo actualizar")

        st.divider()
        st.markdown("### 🗑️ Eliminar")
        confirmar = st.checkbox("⚠️ Confirmo que quiero eliminar este gasto permanentemente")
        if st.button("🗑️ Eliminar", type="secondary"):
            if not confirmar:
                st.warning("Marca la casilla de confirmación")
            elif eliminar_gasto_sobre(gasto['id']):
                st.success("🗑️ Eliminado")
                st.session_state.gasto_encontrado = None
                after_write(rerun=True)
            else:
                st.error("❌ No se pudo eliminar")

st.divider()
st.caption("💰 Sistema de 3 Sobres • Supervivencia → Futuro/Hogar → Ministerio/Extras")