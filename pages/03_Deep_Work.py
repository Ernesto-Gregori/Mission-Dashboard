"""
⏰ Deep Work - Gestión de bloques de tiempo y productividad
"""

import streamlit as st
from datetime import datetime, date, timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.database import init_database, ejecutar, obtener_tipos_bloque
from app.ai_client import chat_simple, api_key_configurada

st.set_page_config(
    page_title="Deep Work | Mission Dashboard",
    page_icon="⏰",
    layout="wide"
)

init_database()

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .bloque-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    .bloque-pendiente  { border-left: 4px solid #8b949e; }
    .bloque-completado { border-left: 4px solid #3fb950; opacity: 0.8; }
    .bloque-parcial    { border-left: 4px solid #e3b341; }
    .hora-badge {
        background: #21262d;
        padding: 0.25rem 0.75rem;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.875rem;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

DIAS_NOMBRES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
DIAS_LABELS  = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
COLORES      = {
    '🔵 Azul':     '#58a6ff',
    '🟢 Verde':    '#3fb950',
    '🟣 Morado':   '#a371f7',
    '🟡 Amarillo': '#e3b341',
    '🔴 Rojo':     '#f85149',
    '🩷 Rosa':     '#f778ba',
}

SYSTEM_COACH = """Eres un coach de productividad cristiano para un estudiante de teología 
que también programa. Eres directo, práctico y motivador. Máximo 100 palabras por respuesta."""

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BD — todas usan ejecutar()
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=60)
def obtener_bloques_fijos() -> list:
    return ejecutar(
        "SELECT * FROM bloques_fijos WHERE activo = 1 ORDER BY hora_inicio",
        fetchall=True,
    ) or []


def obtener_todos_bloques() -> list:
    return ejecutar(
        "SELECT * FROM bloques_fijos ORDER BY activo DESC, hora_inicio",
        fetchall=True,
    ) or []


def obtener_estado_sesion(fecha: str, bloque_id: int) -> tuple:
    rows = ejecutar("""
        SELECT estado, notas FROM sesiones_completadas
        WHERE fecha = ? AND bloque_fijo_id = ?
    """, [fecha, bloque_id], fetchall=True)
    if rows:
        return rows[0]["estado"], rows[0]["notas"]
    return None, None


def registrar_sesion(fecha: str, bloque_id: int,
                     estado: str, notas: str = "") -> None:
    ejecutar("""
        INSERT OR REPLACE INTO sesiones_completadas
            (fecha, bloque_fijo_id, estado, notas)
        VALUES (?, ?, ?, ?)
    """, [fecha, bloque_id, estado, notas])
    obtener_bloques_fijos.clear()


def obtener_sesiones_semana(fecha_inicio: str, fecha_fin: str) -> list:
    return ejecutar("""
        SELECT sc.*, bf.nombre, bf.tipo, bf.hora_inicio, bf.hora_fin
        FROM sesiones_completadas sc
        JOIN bloques_fijos bf ON sc.bloque_fijo_id = bf.id
        WHERE sc.fecha BETWEEN ? AND ?
        ORDER BY sc.fecha, bf.hora_inicio
    """, [fecha_inicio, fecha_fin], fetchall=True) or []


def crear_bloque(nombre: str, hora_inicio: str, hora_fin: str,
                 dias: list, tipo: str, color: str) -> int:
    bloque_id = ejecutar("""
        INSERT INTO bloques_fijos
            (nombre, hora_inicio, hora_fin, dias_semana, tipo, color, activo)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, [nombre, hora_inicio, hora_fin, json.dumps(dias), tipo, color])
    obtener_bloques_fijos.clear()
    return bloque_id


def actualizar_bloque(bloque_id: int, nombre: str, hora_inicio: str,
                      hora_fin: str, dias: list, tipo: str,
                      color: str, activo: bool) -> bool:
    ejecutar("""
        UPDATE bloques_fijos
        SET nombre=?, hora_inicio=?, hora_fin=?,
            dias_semana=?, tipo=?, color=?, activo=?
        WHERE id=?
    """, [nombre, hora_inicio, hora_fin,
          json.dumps(dias), tipo, color, int(activo), bloque_id])
    obtener_bloques_fijos.clear()
    return True


def desactivar_bloque(bloque_id: int) -> None:
    ejecutar(
        "UPDATE bloques_fijos SET activo = 0 WHERE id = ?",
        [bloque_id]
    )
    obtener_bloques_fijos.clear()


def reactivar_bloque(bloque_id: int) -> None:
    ejecutar(
        "UPDATE bloques_fijos SET activo = 1 WHERE id = ?",
        [bloque_id]
    )
    obtener_bloques_fijos.clear()


# ═══════════════════════════════════════════════════════════════
# HELPERS IA
# ═══════════════════════════════════════════════════════════════

def _construir_resumen_semana(sesiones: list) -> str:
    if not sesiones:
        return "Sin sesiones registradas esta semana."

    total         = len(sesiones)
    completados   = len([s for s in sesiones if s["estado"] == "Completado"])
    parciales     = len([s for s in sesiones if s["estado"] == "Parcial"])
    no_realizados = len([s for s in sesiones if s["estado"] == "No_realizado"])

    por_tipo: dict = {}
    for s in sesiones:
        tipo = s["tipo"]
        if tipo not in por_tipo:
            por_tipo[tipo] = {"total": 0, "completados": 0}
        por_tipo[tipo]["total"] += 1
        if s["estado"] == "Completado":
            por_tipo[tipo]["completados"] += 1

    resumen  = (
        f"Semana: {total} bloques. "
        f"Completados: {completados}, Parciales: {parciales}, "
        f"No realizados: {no_realizados}.\n"
    )
    resumen += "Por tipo: " + ", ".join(
        f"{tipo}: {v['completados']}/{v['total']}"
        for tipo, v in por_tipo.items()
    )

    notas = [s["notas"] for s in sesiones if s.get("notas") and len(s["notas"]) > 10]
    if notas:
        resumen += f"\nNotas del usuario: {' | '.join(notas[:3])}"

    return resumen


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("⏰ Deep Work")
st.caption("Bloques de tiempo para enfoque profundo")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📅 Fecha de trabajo")
    fecha_seleccionada = st.date_input(
        "Seleccionar fecha", value=date.today(), key="fecha_deep_work"
    )
    dia_semana = fecha_seleccionada.weekday()
    st.info(f"**{DIAS_NOMBRES[dia_semana]}** {fecha_seleccionada.strftime('%d/%m/%Y')}")

    if dia_semana in [1, 3]:
        st.success("📚 Hoy es día de Biblioteca")

    st.divider()
    if api_key_configurada():
        st.success("🤖 Coach IA activo")
    else:
        st.caption("🤖 Coach IA en modo offline")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_semana, tab_ia, tab_config = st.tabs([
    "📋 Mi Día", "📊 Semana", "🤖 Coach IA", "⚙️ Configuración"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: MI DÍA
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    st.subheader(f"Bloques para el {fecha_seleccionada.strftime('%d/%m/%Y')}")

    bloques    = obtener_bloques_fijos()
    fecha_str  = fecha_seleccionada.isoformat()
    dia_numero = dia_semana + 1

    bloques_hoy = [
        b for b in bloques
        if dia_numero in json.loads(b["dias_semana"])
    ]

    if not bloques_hoy:
        st.info("🌴 No hay bloques programados para este día.")
    else:
        for bloque in bloques_hoy:
            estado_actual, notas_actuales = obtener_estado_sesion(
                fecha_str, bloque["id"]
            )

            if estado_actual == "Completado":
                clase_css, emoji = "bloque-completado", "✅"
            elif estado_actual == "Parcial":
                clase_css, emoji = "bloque-parcial",    "⏳"
            else:
                clase_css, emoji = "bloque-pendiente",  "○"

            h_ini      = datetime.strptime(bloque["hora_inicio"], "%H:%M")
            h_fin      = datetime.strptime(bloque["hora_fin"],    "%H:%M")
            dur_min    = int((h_fin - h_ini).total_seconds() / 60)
            key_base   = f"{bloque['id']}_{fecha_str}"

            col_info, col_accion = st.columns([4, 1])

            with col_info:
                st.markdown(f"""
<div class="bloque-card {clase_css}">
    <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
        <span style="font-size:1.25rem;">{emoji}</span>
        <span style="color:{bloque['color']};font-weight:600;font-size:1.1rem;">
            {bloque['nombre']}
        </span>
        <span class="hora-badge">
            {bloque['hora_inicio']} – {bloque['hora_fin']}
        </span>
        <span style="color:#8b949e;">({dur_min} min)</span>
    </div>
    <div style="color:#8b949e;font-size:0.875rem;">
        {bloque['tipo']} • {estado_actual or 'Pendiente'}
    </div>
</div>
                """, unsafe_allow_html=True)

            with col_accion:
                with st.popover("⚡ Marcar", use_container_width=True):
                    st.markdown(f"**{bloque['nombre']}**")
                    ESTADOS = ["Pendiente","Completado","Parcial","No_realizado","Postergado"]

                    nuevo_estado = st.selectbox(
                        "Estado", ESTADOS,
                        index=ESTADOS.index(estado_actual) if estado_actual else 0,
                        key=f"estado_{key_base}",
                    )
                    notas = st.text_area(
                        "Notas de la sesión",
                        value=notas_actuales or "",
                        placeholder="¿Qué lograste? ¿Hubo distracciones?",
                        key=f"notas_{key_base}",
                    )

                    if st.button("💾 Guardar", key=f"guardar_{key_base}",
                                 use_container_width=True):
                        registrar_sesion(fecha_str, bloque["id"], nuevo_estado, notas)
                        st.success("✅ Guardado")
                        st.rerun()

                    st.divider()
                    st.caption("🤖 Coach IA")

                    tipo_ayuda = st.selectbox(
                        "Tipo",
                        ["Motivación para iniciar",
                         "Estrategia de enfoque",
                         "Resumen de lo logrado"],
                        key=f"tipo_coach_{key_base}",
                    )

                    if st.button("✨ Pedir consejo", key=f"coach_{key_base}",
                                 use_container_width=True):
                        ctx_bloque = (
                            f"Bloque: {bloque['nombre']} ({bloque['tipo']}), "
                            f"{bloque['hora_inicio']}–{bloque['hora_fin']} ({dur_min} min). "
                            f"Estado: {estado_actual or 'Pendiente'}. "
                            f"Notas: {notas or 'Sin notas'}."
                        )
                        prompts = {
                            "Motivación para iniciar":
                                f"Dame una motivación breve y práctica para iniciar este bloque ahora mismo. {ctx_bloque}",
                            "Estrategia de enfoque":
                                f"Sugiere una estrategia concreta para maximizar este bloque. {ctx_bloque}",
                            "Resumen de lo logrado":
                                f"Ayúdame a reflexionar sobre lo logrado en este bloque. {ctx_bloque}",
                        }
                        with st.spinner("Coach pensando..."):
                            st.info(chat_simple(prompts[tipo_ayuda], contexto=SYSTEM_COACH))

# ═══════════════════════════════════════════════════════════════
# TAB 2: SEMANA
# ═══════════════════════════════════════════════════════════════

with tab_semana:
    st.subheader("Vista Semanal")

    lunes   = fecha_seleccionada - timedelta(days=fecha_seleccionada.weekday())
    domingo = lunes + timedelta(days=6)

    sesiones_semana = obtener_sesiones_semana(lunes.isoformat(), domingo.isoformat())
    st.caption(f"Semana del {lunes.strftime('%d/%m')} al {domingo.strftime('%d/%m/%Y')}")

    if not sesiones_semana:
        st.info("📊 Sin sesiones registradas esta semana.")
    else:
        total       = len(sesiones_semana)
        completados = len([s for s in sesiones_semana if s["estado"] == "Completado"])
        tasa        = int(completados / total * 100) if total > 0 else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Total bloques", total)
        col2.metric("Completados",   completados)
        col3.metric("Tasa de éxito", f"{tasa}%")
        st.progress(tasa / 100, text=f"{tasa}% de bloques completados")

        st.divider()
        for dia_offset in range(7):
            dia          = lunes + timedelta(days=dia_offset)
            sesiones_dia = [s for s in sesiones_semana if s["fecha"] == dia.isoformat()]

            if sesiones_dia:
                comp_dia  = len([s for s in sesiones_dia if s["estado"] == "Completado"])
                emoji_dia = (
                    "✅" if comp_dia == len(sesiones_dia)
                    else "⚡" if comp_dia > 0 else "○"
                )
                with st.expander(
                    f"{emoji_dia} {DIAS_NOMBRES[dia_offset]} "
                    f"{dia.strftime('%d/%m')} — "
                    f"{comp_dia}/{len(sesiones_dia)} completados"
                ):
                    for s in sesiones_dia:
                        color = (
                            "#3fb950" if s["estado"] == "Completado"
                            else "#e3b341" if s["estado"] == "Parcial"
                            else "#8b949e"
                        )
                        st.markdown(
                            f"- <span style='color:{color}'>{s['nombre']}</span> "
                            f"({s['hora_inicio']}–{s['hora_fin']}) • {s['estado']}",
                            unsafe_allow_html=True,
                        )
                        if s.get("notas"):
                            st.caption(f"  📝 {s['notas']}")

# ═══════════════════════════════════════════════════════════════
# TAB 3: COACH IA
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Coach de Productividad")

    if not api_key_configurada():
        st.warning("⚠️ Coach IA en modo offline — respuestas predefinidas disponibles.")

    lunes_ia   = fecha_seleccionada - timedelta(days=fecha_seleccionada.weekday())
    domingo_ia = lunes_ia + timedelta(days=6)
    sesiones_ia      = obtener_sesiones_semana(lunes_ia.isoformat(), domingo_ia.isoformat())
    resumen_semana   = _construir_resumen_semana(sesiones_ia)

    st.caption(f"Analizando semana: {lunes_ia.strftime('%d/%m')} – {domingo_ia.strftime('%d/%m/%Y')}")

    col_datos, col_chat = st.columns([1, 2])

    with col_datos:
        st.markdown("**📊 Datos de la semana**")

        if sesiones_ia:
            total_ia    = len(sesiones_ia)
            comp_ia     = len([s for s in sesiones_ia if s["estado"] == "Completado"])
            st.metric("Completados", f"{comp_ia}/{total_ia}")
            st.progress(comp_ia / total_ia if total_ia > 0 else 0)

            por_tipo: dict = {}
            for s in sesiones_ia:
                t = s["tipo"]
                por_tipo[t] = por_tipo.get(t, 0) + (1 if s["estado"] == "Completado" else 0)
            for tipo, count in por_tipo.items():
                st.caption(f"• {tipo}: {count} completados")
        else:
            st.info("Sin datos esta semana.")

        st.divider()
        tipo_analisis = st.selectbox(
            "Tipo de análisis",
            [
                "Análisis general de la semana",
                "¿Por qué fallé en algunos bloques?",
                "Cómo mejorar la semana que viene",
                "Correlación descanso-productividad",
                "Qué bloque priorizar mañana",
            ],
        )
        ctx_adicional = st.text_area(
            "Contexto extra (opcional)",
            placeholder="Ej: Esta semana tuve exámenes en el instituto...",
            height=80,
        )

    with col_chat:
        st.markdown("**💬 Análisis con IA**")

        if st.button("🚀 Analizar mi semana", use_container_width=True, type="primary"):
            prompt = (
                f"{tipo_analisis}\n\n"
                f"Datos de productividad:\n{resumen_semana}\n\n"
                + (f"Contexto del usuario: {ctx_adicional}\n\n" if ctx_adicional else "")
                + "Sé específico con los datos. Da 2-3 observaciones concretas y 1 acción."
            )
            with st.spinner("Analizando tu semana..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_COACH))

        st.divider()
        st.markdown("**💬 Pregunta libre al coach**")
        pregunta_libre = st.text_input(
            "Tu pregunta",
            placeholder="Ej: ¿Cómo protejo el bloque de código de las 06:15?"
        )
        if pregunta_libre:
            with st.spinner("Coach pensando..."):
                st.info(chat_simple(
                    f"Contexto semanal: {resumen_semana}\n\nPregunta: {pregunta_libre}",
                    contexto=SYSTEM_COACH,
                ))

# ═══════════════════════════════════════════════════════════════
# TAB 4: CONFIGURACIÓN — CRUD DE BLOQUES
# ═══════════════════════════════════════════════════════════════

with tab_config:

    TIPOS_BLOQUE = obtener_tipos_bloque()

    if "bloque_editando" not in st.session_state:
        st.session_state.bloque_editando = None
    if "mostrar_form_nuevo" not in st.session_state:
        st.session_state.mostrar_form_nuevo = False

    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        st.subheader("⚙️ Gestión de Bloques")
    with col_btn:
        if st.button("➕ Nuevo bloque", use_container_width=True, type="primary"):
            st.session_state.mostrar_form_nuevo = True
            st.session_state.bloque_editando    = None

    # ── Formulario: Nuevo bloque ──────────────────────────────
    if st.session_state.mostrar_form_nuevo:
        st.divider()
        st.markdown("### ➕ Crear nuevo bloque")

        with st.form("form_nuevo_bloque", clear_on_submit=True):
            nuevo_nombre = st.text_input(
                "Nombre del bloque *", placeholder="Ej: Deep Work: Código"
            )

            col_t, col_t2 = st.columns(2)
            with col_t:
                nuevo_tipo_sel = st.selectbox(
                    "Tipo *", options=TIPOS_BLOQUE + ["✏️ Nuevo tipo..."]
                )
            with col_t2:
                nuevo_tipo_custom = st.text_input(
                    "Nuevo tipo (si elegiste Escribir nuevo)",
                    placeholder="Ej: Trabajo, Estudios..."
                )

            nuevo_tipo = (
                nuevo_tipo_custom.strip()
                if nuevo_tipo_sel == "✏️ Nuevo tipo..." else nuevo_tipo_sel
            )

            col_hi, col_hf, col_col = st.columns(3)
            with col_hi:
                nuevo_inicio = st.text_input("Hora inicio *", placeholder="06:15")
            with col_hf:
                nuevo_fin = st.text_input("Hora fin *", placeholder="07:15")
            with col_col:
                nuevo_color_label = st.selectbox("Color", list(COLORES.keys()))

            st.markdown("**Días de la semana *:**")
            cols_dias  = st.columns(7)
            nuevos_dias = []
            for i, dia in enumerate(DIAS_LABELS):
                with cols_dias[i]:
                    if st.checkbox(dia, key=f"nuevo_dia_{i}", value=i < 5):
                        nuevos_dias.append(i + 1)

            col_g, col_c = st.columns(2)
            with col_g:
                submit_nuevo = st.form_submit_button(
                    "💾 Crear bloque", use_container_width=True, type="primary"
                )
            with col_c:
                cancel_nuevo = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_nuevo:
                st.session_state.mostrar_form_nuevo = False
                st.rerun()

            if submit_nuevo:
                errores = []
                if not nuevo_nombre.strip():
                    errores.append("El nombre es obligatorio")
                if not nuevos_dias:
                    errores.append("Selecciona al menos un día")
                if nuevo_tipo_sel == "✏️ Nuevo tipo..." and not nuevo_tipo_custom.strip():
                    errores.append("Escribe el nombre del nuevo tipo")
                try:
                    datetime.strptime(nuevo_inicio, "%H:%M")
                    datetime.strptime(nuevo_fin,    "%H:%M")
                except ValueError:
                    errores.append("Formato de hora inválido (usa HH:MM)")

                if errores:
                    for e in errores:
                        st.error(f"⚠️ {e}")
                else:
                    nuevo_id = crear_bloque(
                        nombre=nuevo_nombre.strip(),
                        hora_inicio=nuevo_inicio,
                        hora_fin=nuevo_fin,
                        dias=nuevos_dias,
                        tipo=nuevo_tipo,
                        color=COLORES[nuevo_color_label],
                    )
                    st.success(f"✅ Bloque '{nuevo_nombre}' creado · ID: {nuevo_id}")
                    st.session_state.mostrar_form_nuevo = False
                    st.rerun()

    # ── Lista de bloques ──────────────────────────────────────
    st.divider()
    todos     = obtener_todos_bloques()
    activos   = [b for b in todos if b["activo"]]
    inactivos = [b for b in todos if not b["activo"]]
    st.markdown(f"**{len(activos)} bloques activos · {len(inactivos)} inactivos**")

    for b in todos:
        dias      = json.loads(b["dias_semana"])
        dias_txt  = ", ".join(DIAS_LABELS[d - 1] for d in dias)
        h_ini     = datetime.strptime(b["hora_inicio"], "%H:%M")
        h_fin     = datetime.strptime(b["hora_fin"],    "%H:%M")
        dur_min   = int((h_fin - h_ini).total_seconds() / 60)
        activo    = bool(b["activo"])
        badge_txt = "● Activo" if activo else "○ Inactivo"
        badge_col = "#3fb950"  if activo else "#8b949e"
        opacidad  = "1"        if activo else "0.45"

        col_card, col_editar, col_del = st.columns([5, 1, 1])

        with col_card:
            st.markdown(f"""
<div class="bloque-card" style="opacity:{opacidad};">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="color:{b['color']};font-weight:700;font-size:1rem;">
            {b['nombre']}
        </span>
        <span style="background:#21262d;padding:0.2rem 0.6rem;
                     border-radius:6px;font-family:monospace;font-size:0.85rem;">
            {b['hora_inicio']} – {b['hora_fin']}
        </span>
    </div>
    <div style="color:#8b949e;font-size:0.8rem;margin-top:0.4rem;">
        🏷️ {b['tipo']} &nbsp;·&nbsp; ⏱ {dur_min} min
        &nbsp;·&nbsp; 📅 {dias_txt}
        &nbsp;·&nbsp;
        <span style="color:{badge_col};">{badge_txt}</span>
    </div>
</div>
            """, unsafe_allow_html=True)

        with col_editar:
            if st.button("✏️", key=f"edit_{b['id']}",
                         help="Editar", use_container_width=True):
                st.session_state.bloque_editando    = b["id"]
                st.session_state.mostrar_form_nuevo = False

        with col_del:
            icono = "🗑️" if activo else "♻️"
            ayuda = "Desactivar" if activo else "Reactivar"
            if st.button(icono, key=f"del_{b['id']}",
                         help=ayuda, use_container_width=True):
                if activo:
                    desactivar_bloque(b["id"])
                    st.warning(f"⚠️ '{b['nombre']}' desactivado")
                else:
                    reactivar_bloque(b["id"])
                    st.success(f"✅ '{b['nombre']}' reactivado")
                st.rerun()

        # ── Formulario edición inline ─────────────────────────
        if st.session_state.bloque_editando == b["id"]:
            with st.form(f"form_editar_{b['id']}"):
                st.markdown(f"#### ✏️ Editando: {b['nombre']}")

                edit_nombre = st.text_input("Nombre", value=b["nombre"])

                tipo_en_lista = b["tipo"] in TIPOS_BLOQUE
                col_et, col_et2 = st.columns(2)
                with col_et:
                    edit_tipo_sel = st.selectbox(
                        "Tipo",
                        options=TIPOS_BLOQUE + ["✏️ Nuevo tipo..."],
                        index=(
                            TIPOS_BLOQUE.index(b["tipo"])
                            if tipo_en_lista else len(TIPOS_BLOQUE)
                        ),
                    )
                with col_et2:
                    edit_tipo_custom = st.text_input(
                        "Nuevo tipo (si elegiste Escribir nuevo)",
                        value=b["tipo"] if not tipo_en_lista else "",
                        placeholder="Ej: Trabajo, Estudios...",
                    )

                edit_tipo = (
                    edit_tipo_custom.strip()
                    if edit_tipo_sel == "✏️ Nuevo tipo..." else edit_tipo_sel
                )

                col_ehi, col_ehf, col_ecol = st.columns(3)
                with col_ehi:
                    edit_inicio = st.text_input("Hora inicio", value=b["hora_inicio"])
                with col_ehf:
                    edit_fin = st.text_input("Hora fin", value=b["hora_fin"])
                with col_ecol:
                    color_label_actual = next(
                        (k for k, v in COLORES.items() if v == b["color"]),
                        list(COLORES.keys())[0],
                    )
                    edit_color_label = st.selectbox(
                        "Color", list(COLORES.keys()),
                        index=list(COLORES.keys()).index(color_label_actual),
                    )

                st.markdown("**Días:**")
                cols_ed  = st.columns(7)
                edit_dias = []
                for i, dia in enumerate(DIAS_LABELS):
                    with cols_ed[i]:
                        if st.checkbox(
                            dia, key=f"edit_dia_{b['id']}_{i}",
                            value=(i + 1) in dias
                        ):
                            edit_dias.append(i + 1)

                edit_activo = st.checkbox("Bloque activo", value=activo)

                col_sg, col_sc = st.columns(2)
                with col_sg:
                    submit_edit = st.form_submit_button(
                        "💾 Guardar cambios", use_container_width=True, type="primary"
                    )
                with col_sc:
                    cancel_edit = st.form_submit_button(
                        "✖ Cancelar", use_container_width=True
                    )

                if cancel_edit:
                    st.session_state.bloque_editando = None
                    st.rerun()

                if submit_edit:
                    errores_e = []
                    if not edit_nombre.strip():
                        errores_e.append("El nombre es obligatorio")
                    if not edit_dias:
                        errores_e.append("Selecciona al menos un día")
                    if edit_tipo_sel == "✏️ Nuevo tipo..." and not edit_tipo_custom.strip():
                        errores_e.append("Escribe el nombre del nuevo tipo")
                    try:
                        datetime.strptime(edit_inicio, "%H:%M")
                        datetime.strptime(edit_fin,    "%H:%M")
                    except ValueError:
                        errores_e.append("Formato de hora inválido (HH:MM)")

                    if errores_e:
                        for e in errores_e:
                            st.error(f"⚠️ {e}")
                    else:
                        actualizar_bloque(
                            bloque_id=b["id"],
                            nombre=edit_nombre.strip(),
                            hora_inicio=edit_inicio,
                            hora_fin=edit_fin,
                            dias=edit_dias,
                            tipo=edit_tipo,
                            color=COLORES[edit_color_label],
                            activo=edit_activo,
                        )
                        st.success(f"✅ '{edit_nombre}' actualizado")
                        st.session_state.bloque_editando = None
                        st.rerun()

st.divider()
st.caption("⏰ Módulo Deep Work")