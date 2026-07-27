"""
💑 Conexión Matrimonial y Familiar
Calendario · Notas · Historial · IA Consejero
"""

import streamlit as st
from datetime import timedelta
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import ejecutar, ejecutar_cached
from app.tenant import uid
from app.ai_client import generar_alerta_matrimonio, api_key_configurada, chat_simple
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    iso_ahora,
)

st.set_page_config(
    page_title="Matrimonio | Mission Dashboard",
    page_icon="💑",
    layout="wide"
)

from app.auth import require_auth
from app.onboarding import require_onboarding, require_module
require_auth()
require_onboarding()
require_module("matrimonio")
ensure_database()

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

AMBITOS = ["Matrimonio", "Familia"]

TIPOS_CITA = {
    "Matrimonio": [
        "Cena_Romantica","Salida_Casual","Estadia_Casa",
        "Viaje_Corto","Aniversario","Cumpleanos_Esposa",
        "Sorpresa","Otra",
    ],
    "Familia": [
        "Salida_Familiar","Vacaciones","Actividad_Recreativa",
        "Visita_Familiares","Celebracion","Deporte_Juntos",
        "Cine_Teatro","Parque","Otra",
    ],
}
EMOJIS_TIPO = {
    "Cena_Romantica":"🍷","Salida_Casual":"☕","Estadia_Casa":"🏠",
    "Viaje_Corto":"🚗","Aniversario":"💍","Cumpleanos_Esposa":"🎂",
    "Sorpresa":"🎉","Salida_Familiar":"👨‍👩‍👧","Vacaciones":"🏖️",
    "Actividad_Recreativa":"🎮","Visita_Familiares":"🏡",
    "Celebracion":"🎊","Deporte_Juntos":"⚽","Cine_Teatro":"🎬",
    "Parque":"🌳","Otra":"💑",
}
ESTADOS_CITA = ["Idea","Planeando","Confirmada","Completada","Cancelada"]
COLORES_ESTADO = {
    "Idea":"#8b949e","Planeando":"#58a6ff",
    "Confirmada":"#3fb950","Completada":"#a371f7","Cancelada":"#f85149",
}
CATEGORIAS_NOTA = [
    "Preferencias_Esposa","Ideas_Regalo","Frases_Recordar",
    "Momentos_Especiales","Metas_Pareja","Conversaciones_Pendientes",
    "Familia","Hijos","Otro",
]
EMOJIS_NOTA = {
    "Preferencias_Esposa":"💝","Ideas_Regalo":"🎁",
    "Frases_Recordar":"💬","Momentos_Especiales":"✨",
    "Metas_Pareja":"🎯","Conversaciones_Pendientes":"🗣️",
    "Familia":"👨‍👩‍👧","Hijos":"👶","Otro":"📝",
}

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB
# ═══════════════════════════════════════════════════════════════

# ── CITAS ─────────────────────────────────────────────────────

def obtener_citas(fecha_desde=None, estado=None, ambito=None) -> list:
    conditions = ["user_id = ?"]
    params     = [uid()]
    if fecha_desde:
        conditions.append("fecha >= ?")
        params.append(str(fecha_desde))
    if estado:
        conditions.append("estado_planificacion = ?")
        params.append(estado)
    if ambito:
        conditions.append("ambito = ?")
        params.append(ambito)
    where = " AND ".join(conditions)
    return ejecutar(
        f"SELECT * FROM matrimonio_citas WHERE {where} ORDER BY fecha, hora",
        params, fetchall=True
    ) or []


def guardar_cita(fecha: str, hora, tipo: str, titulo: str,
                 descripcion: str, lugar: str, presupuesto,
                 ambito: str = "Matrimonio",
                 preparacion: str = "") -> int:
    """FIX Turso: todos los valores como tipos primitivos."""
    return ejecutar("""
        INSERT INTO matrimonio_citas
            (user_id, fecha, hora, tipo_cita, titulo, descripcion,
             lugar, presupuesto_estimado, estado_planificacion,
             ambito, notas_preparacion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Planeando', ?, ?)
    """, [
        uid(),
        str(fecha),
        str(hora) if hora else None,
        str(tipo),
        str(titulo),
        str(descripcion or ""),
        str(lugar or ""),
        float(presupuesto) if presupuesto else 0.0,
        str(ambito),
        str(preparacion or ""),
    ])


def actualizar_cita(cita_id: int, fecha: str, hora, tipo: str,
                    titulo: str, descripcion: str, lugar: str,
                    presupuesto, estado: str, ambito: str,
                    preparacion: str) -> None:
    ejecutar("""
        UPDATE matrimonio_citas
        SET fecha=?, hora=?, tipo_cita=?, titulo=?,
            descripcion=?, lugar=?, presupuesto_estimado=?,
            estado_planificacion=?, ambito=?,
            notas_preparacion=?, actualizado_en=?
        WHERE id=? AND user_id=?
    """, [
        str(fecha),
        str(hora) if hora else None,
        str(tipo),
        str(titulo),
        str(descripcion or ""),
        str(lugar or ""),
        float(presupuesto) if presupuesto else 0.0,
        str(estado),
        str(ambito),
        str(preparacion or ""),
        iso_ahora(),        # ← str ISO local
        int(cita_id),
        uid(),
    ])


def eliminar_cita(cita_id: int) -> None:
    ejecutar("DELETE FROM matrimonio_citas WHERE id=? AND user_id=?", [int(cita_id), uid()])


# ── NOTAS ─────────────────────────────────────────────────────

def obtener_notas(categoria=None, urgencia_min: int = 1) -> list:
    conditions = ["user_id = ?", "urgencia >= ?"]
    params     = [uid(), int(urgencia_min)]
    if categoria:
        conditions.append("categoria = ?")
        params.append(categoria)
    where = " AND ".join(conditions)
    return ejecutar(
        f"""SELECT * FROM matrimonio_notas WHERE {where}
            ORDER BY urgencia DESC, creado_en DESC""",
        params, fetchall=True
    ) or []


def guardar_nota(categoria: str, contenido: str, contexto: str,
                 fecha_mencion: str, urgencia: int) -> int:
    return ejecutar("""
        INSERT INTO matrimonio_notas
            (user_id, categoria, contenido, contexto, fecha_mencion, urgencia)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        uid(),
        str(categoria),
        str(contenido),
        str(contexto or ""),
        str(fecha_mencion),     # ← str ISO, no objeto date
        int(urgencia),
    ])


def actualizar_nota(nota_id: int, categoria: str, contenido: str,
                    contexto: str, urgencia: int) -> None:
    ejecutar("""
        UPDATE matrimonio_notas
        SET categoria=?, contenido=?, contexto=?,
            urgencia=?, actualizado_en=?
        WHERE id=? AND user_id=?
    """, [
        str(categoria),
        str(contenido),
        str(contexto or ""),
        int(urgencia),
        iso_ahora(),            # ← str ISO local
        int(nota_id),
        uid(),
    ])


def eliminar_nota(nota_id: int) -> None:
    ejecutar("DELETE FROM matrimonio_notas WHERE id=? AND user_id=?", [int(nota_id), uid()])


# ── HÁBITOS ───────────────────────────────────────────────────

def registrar_habito(fecha: str, minutos: int, tipo_conexion: str,
                     iniciado_por: str, satisfaccion: int,
                     notas: str, modo_pareja: int) -> None:
    ejecutar("""
        INSERT INTO matrimonio_habitos
            (user_id, fecha, tiempo_calidad_minutos, tipo_conexion,
             iniciado_por, satisfaccion, notas,
             modo_pareja_activado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
            tiempo_calidad_minutos = excluded.tiempo_calidad_minutos,
            tipo_conexion          = excluded.tipo_conexion,
            iniciado_por           = excluded.iniciado_por,
            satisfaccion           = excluded.satisfaccion,
            notas                  = excluded.notas,
            modo_pareja_activado   = excluded.modo_pareja_activado
    """, [
        uid(),
        str(fecha),             # ← str ISO, no objeto date
        int(minutos),
        str(tipo_conexion),
        str(iniciado_por),
        int(satisfaccion),
        str(notas or ""),
        int(modo_pareja),
    ])


def obtener_habitos_recientes(dias: int = 14) -> list:
    fecha_desde = (_hoy() - timedelta(days=dias)).isoformat()  # ← local
    return ejecutar_cached("""
        SELECT * FROM matrimonio_habitos
        WHERE fecha >= ? AND user_id = ?
        ORDER BY fecha DESC
    """, (fecha_desde, uid())) or []


def verificar_alerta_20_30(hoy_local) -> tuple:
    """
    FIX: recibe hoy_local para no llamar a date.today() ni datetime.now()
    internamente — todo usa zona horaria local.
    """
    hoy_iso    = hoy_local.isoformat()
    manana_iso = (hoy_local + timedelta(days=1)).isoformat()

    citas_hoy    = obtener_citas(fecha_desde=hoy_iso,    estado="Confirmada")
    citas_manana = obtener_citas(fecha_desde=manana_iso)
    proxima = (citas_hoy[0]    if citas_hoy
               else citas_manana[0] if citas_manana
               else None)

    ahora_local = datetime.now()           # desde timezone_config → local
    hora        = ahora_local.hour
    minuto      = ahora_local.minute
    alerta = (
        proxima is not None
        and proxima["fecha"] == hoy_iso
        and ((hora == 20 and minuto >= 30) or
             (hora == 21 and minuto <= 15))
    )
    return alerta, proxima


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("💑 Conexión Matrimonial y Familiar")
st.caption("Calendario · Notas · Historial · IA Consejero · Alerta 20:30")

# ═══════════════════════════════════════════════════════════════
# HOY — una sola vez, zona horaria local
# ═══════════════════════════════════════════════════════════════

hoy = _hoy()    # ← date local, reemplaza date.today() en todo el archivo

# ═══════════════════════════════════════════════════════════════
# ALERTA 20:30
# ═══════════════════════════════════════════════════════════════

alerta_activa, proxima_cita = verificar_alerta_20_30(hoy)

if alerta_activa and proxima_cita:
    st.error("⏰ **ALERTA 20:30 — MODO PAREJA ACTIVADO** ⏰")
    ctx = (f"Cita hoy: {proxima_cita['titulo']} "
           f"a las {proxima_cita['hora'] or '21:00'}")
    msg         = generar_alerta_matrimonio(ctx)
    ambito_icon = "💑" if proxima_cita.get("ambito") == "Matrimonio" else "👨‍👩‍👧"
    st.html(f"""
<div style="background:#3c1e1e;border:2px solid #f85149;
            border-radius:12px;padding:1.5rem;margin:1rem 0;">
    <h3 style="color:#f85149;margin:0;">{ambito_icon} {msg}</h3>
    <p style="color:#f0f6fc;margin:0.5rem 0 0 0;">
        <strong>Evento:</strong> {proxima_cita['titulo']}<br>
        <strong>Hora:</strong> {proxima_cita['hora'] or '21:00'}<br>
        <strong>Lugar:</strong> {proxima_cita['lugar'] or 'Por definir'}
    </p>
</div>""")
    if st.button("✅ Modo pareja activado", type="primary"):
        registrar_habito(
            hoy.isoformat(), 0, "Tiempo_Calidad", "Yo", 0,
            f"Inició para: {proxima_cita['titulo']}", 1
        )
        st.success("💑 ¡Disfruten su tiempo juntos!")
        st.balloons()

elif proxima_cita:
    dias_hasta  = (
        datetime.strptime(proxima_cita["fecha"], "%Y-%m-%d").date() - hoy
    ).days
    ambito_icon = "💑" if proxima_cita.get("ambito") == "Matrimonio" else "👨‍👩‍👧"
    hora_txt    = proxima_cita["hora"] or "21:00"
    if dias_hasta == 0:
        st.info(
            f"📅 **Hoy** — {ambito_icon} {proxima_cita['titulo']} "
            f"a las {hora_txt}"
        )
    elif dias_hasta == 1:
        st.warning(
            f"⏰ **Mañana** — {ambito_icon} {proxima_cita['titulo']}"
        )
    else:
        st.caption(
            f"Próximo evento en {dias_hasta} días: "
            f"{ambito_icon} {proxima_cita['titulo']}"
        )

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Conexión")
    habitos_sb = obtener_habitos_recientes(30)

    if habitos_sb:
        prom_sat = sum(h["satisfaccion"] or 0 for h in habitos_sb) / len(habitos_sb)
        modo_ok  = sum(1 for h in habitos_sb if h["modo_pareja_activado"])
        col1, col2 = st.columns(2)
        col1.metric("Citas/mes",    len(habitos_sb))
        col2.metric("Satisfacción", f"{prom_sat:.1f}/10")
        st.progress(prom_sat / 10, text="Calidad de conexión")
        st.metric("Modo 21:00 ok", f"{modo_ok}/{len(habitos_sb)}")
        if modo_ok < len(habitos_sb) * 0.7:
            st.warning("⚠️ Menos del 70% respetado")
    else:
        st.info("📝 Sin registros aún")

    proximos = obtener_citas(fecha_desde=hoy.isoformat())[:5]
    if proximos:
        st.divider()
        st.caption("📅 Próximos eventos")
        for c in proximos:
            icon = "💑" if c.get("ambito") == "Matrimonio" else "👨‍👩‍👧"
            dias = (datetime.strptime(c["fecha"], "%Y-%m-%d").date() - hoy).days
            st.caption(
                f"{icon} {c['titulo']} — "
                f"{'Hoy' if dias == 0 else f'en {dias}d'}"
            )

    notas_urg = obtener_notas(urgencia_min=8)
    if notas_urg:
        st.divider()
        st.caption("🔥 Notas urgentes")
        for n in notas_urg[:3]:
            emoji = EMOJIS_NOTA.get(n["categoria"], "📝")
            st.caption(f"{emoji} {n['contenido'][:50]}...")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_citas, tab_notas, tab_historial, tab_ia = st.tabs([
    "📅 Calendario", "📝 Notas", "📊 Historial", "🤖 IA Consejero"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: CALENDARIO
# ═══════════════════════════════════════════════════════════════

with tab_citas:
    for key, default in [
        ("cita_editando",     None),
        ("mostrar_form_cita", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    col_f1,col_f2,col_f3,col_fbtn = st.columns([2,2,2,1])
    with col_f1:
        f_ambito     = st.selectbox("Ámbito",
            ["Todos","Matrimonio","Familia"], key="f_ambito_cal")
    with col_f2:
        f_estado_cal = st.selectbox("Estado",
            ["Todos"]+ESTADOS_CITA, key="f_est_cal")
    with col_f3:
        f_periodo    = st.selectbox("Período",
            ["Próximos eventos","Este mes","Próximos 3 meses","Todos"],
            key="f_per_cal")
    with col_fbtn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nuevo", use_container_width=True,
                     type="primary", key="btn_nueva_cita"):
            st.session_state.mostrar_form_cita = True
            st.session_state.cita_editando     = None

    fecha_desde_map = {
        "Próximos eventos": hoy.isoformat(),
        "Este mes":         hoy.replace(day=1).isoformat(),
        "Próximos 3 meses": hoy.isoformat(),
        "Todos":            None,
    }
    fecha_desde_cal = fecha_desde_map[f_periodo]

    # ── Formulario: Nuevo evento ──────────────────────────────
    if st.session_state.mostrar_form_cita:
        st.divider()
        st.markdown("### ➕ Nuevo evento")
        nuevo_ambito      = st.selectbox("Ámbito *", AMBITOS, key="nuevo_ambito_sel")
        tipos_disponibles = TIPOS_CITA[nuevo_ambito]

        with st.form("form_nueva_cita", clear_on_submit=True):
            col_nc1, col_nc2 = st.columns(2)
            with col_nc1:
                nc_titulo = st.text_input("Título *",
                    placeholder="Ej: Cena de aniversario")
                nc_tipo   = st.selectbox("Tipo", tipos_disponibles)
            with col_nc2:
                nc_fecha  = st.date_input("Fecha",
                    value=hoy + timedelta(days=7))
                nc_hora   = st.time_input("Hora (opcional)", value=None)

            col_nc3, col_nc4 = st.columns(2)
            with col_nc3:
                nc_lugar  = st.text_input("Lugar",
                    placeholder="Restaurante, parque...")
            with col_nc4:
                nc_presup = st.number_input("Presupuesto",
                    min_value=0, step=100, value=0)

            nc_desc = st.text_area("Descripción / Plan", height=70)
            nc_prep = st.text_area("¿Qué preparar?", height=50,
                placeholder="Reservar, comprar detalles...")

            col_sg, col_sc = st.columns(2)
            with col_sg:
                submit_cita = st.form_submit_button(
                    "💾 Guardar evento",
                    use_container_width=True, type="primary"
                )
            with col_sc:
                cancel_cita = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_cita:
                st.session_state.mostrar_form_cita = False
                st.rerun()
            if submit_cita:
                if not nc_titulo.strip():
                    st.error("⚠️ El título es obligatorio")
                else:
                    guardar_cita(
                        nc_fecha.isoformat(),
                        nc_hora.strftime("%H:%M") if nc_hora else None,
                        nc_tipo, nc_titulo.strip(), nc_desc,
                        nc_lugar, nc_presup, nuevo_ambito, nc_prep
                    )
                    st.success(f"✅ '{nc_titulo}' guardado")
                    st.session_state.mostrar_form_cita = False
                    st.rerun()

    st.divider()

    # ── Lista de eventos ──────────────────────────────────────
    citas = obtener_citas(
        fecha_desde_cal,
        None if f_estado_cal == "Todos" else f_estado_cal,
        None if f_ambito     == "Todos" else f_ambito,
    )
    if f_periodo == "Próximos 3 meses":
        limite = (hoy + timedelta(days=90)).isoformat()
        citas  = [c for c in citas if c["fecha"] <= limite]

    if not citas:
        st.info("📭 No hay eventos con estos filtros")
    else:
        st.caption(f"**{len(citas)} eventos encontrados**")

        for c in citas:
            fecha_c     = datetime.strptime(c["fecha"], "%Y-%m-%d").date()
            dias_falta  = (fecha_c - hoy).days
            emoji_tipo  = EMOJIS_TIPO.get(c.get("tipo_cita",""), "💑")
            color_est   = COLORES_ESTADO.get(c["estado_planificacion"], "#8b949e")
            ambito_c    = c.get("ambito", "Matrimonio")
            ambito_icon = "💑" if ambito_c == "Matrimonio" else "👨‍👩‍👧"
            dias_txt    = (
                "¡Hoy!"    if dias_falta == 0 else
                "¡Mañana!" if dias_falta == 1 else
                f"En {dias_falta}d" if dias_falta > 0 else
                f"Hace {abs(dias_falta)}d"
            )
            desc_html = (
                f"<div style='color:#c9d1d9;font-size:0.85rem;"
                f"margin-top:0.3rem;'>{c['descripcion']}</div>"
            ) if c.get("descripcion") else ""
            prep_html = (
                f"<div style='color:#e3b341;font-size:0.75rem;"
                f"margin-top:0.3rem;'>📋 {c['notas_preparacion']}</div>"
            ) if c.get("notas_preparacion") else ""
            presup_html = (
                f"&nbsp;·&nbsp; 💰 ${c['presupuesto_estimado']:,.0f}"
                if c.get("presupuesto_estimado") else ""
            )

            col_card, col_acc = st.columns([5, 1])
            with col_card:
                st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-left:4px solid {color_est};
            border-radius:10px;padding:0.85rem 1.25rem;
            margin-bottom:0.4rem;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-weight:700;color:#f0f6fc;font-size:1rem;">
            {emoji_tipo} {c['titulo']}
            <span style="font-size:0.75rem;color:#8b949e;margin-left:0.5rem;">
                {ambito_icon} {ambito_c}
            </span>
        </span>
        <span style="font-size:0.75rem;color:#8b949e;">
            <span style="color:{color_est};">● {c['estado_planificacion']}</span>
            &nbsp;·&nbsp; {dias_txt}
        </span>
    </div>
    <div style="color:#8b949e;font-size:0.78rem;margin-top:0.25rem;">
        📅 {c['fecha']}
        &nbsp;·&nbsp; 🕐 {c['hora'] or 'Sin hora'}
        &nbsp;·&nbsp; 📍 {c['lugar'] or 'Sin lugar'}
        {presup_html}
    </div>
    {desc_html}{prep_html}
</div>""")

            with col_acc:
                if st.button("✏️", key=f"ec_{c['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.cita_editando     = c["id"]
                    st.session_state.mostrar_form_cita = False
                if st.button("🗑️", key=f"dc_{c['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f"del_cita_{c['id']}"] = True

            # Confirmar eliminación
            if st.session_state.get(f"del_cita_{c['id']}"):
                cx1, cx2, cx3 = st.columns([2,1,1])
                with cx1:
                    st.warning(f"⚠️ ¿Eliminar *{c['titulo']}*?")
                with cx2:
                    if st.button("🗑️ Sí", key=f"cdc_{c['id']}",
                                 use_container_width=True):
                        eliminar_cita(c["id"])
                        st.session_state[f"del_cita_{c['id']}"] = False
                        st.rerun()
                with cx3:
                    if st.button("✖", key=f"cnc_{c['id']}",
                                 use_container_width=True):
                        st.session_state[f"del_cita_{c['id']}"] = False
                        st.rerun()

            # Edición inline
            if st.session_state.cita_editando == c["id"]:
                edit_ambito = st.selectbox(
                    "Ámbito", AMBITOS,
                    index=AMBITOS.index(ambito_c) if ambito_c in AMBITOS else 0,
                    key=f"eamb_{c['id']}"
                )
                tipos_edit = TIPOS_CITA[edit_ambito]

                with st.form(f"form_edit_cita_{c['id']}"):
                    st.markdown(f"#### ✏️ Editando: {c['titulo']}")
                    col_ee1, col_ee2 = st.columns(2)
                    with col_ee1:
                        et_titulo = st.text_input("Título", value=c["titulo"])
                        et_tipo   = st.selectbox(
                            "Tipo", tipos_edit,
                            index=tipos_edit.index(c["tipo_cita"])
                            if c.get("tipo_cita") in tipos_edit else 0
                        )
                    with col_ee2:
                        et_fecha  = st.date_input("Fecha",
                            value=datetime.strptime(c["fecha"], "%Y-%m-%d").date())
                        et_estado = st.selectbox(
                            "Estado", ESTADOS_CITA,
                            index=ESTADOS_CITA.index(c["estado_planificacion"])
                            if c["estado_planificacion"] in ESTADOS_CITA else 0
                        )

                    col_ee3, col_ee4 = st.columns(2)
                    with col_ee3:
                        et_lugar  = st.text_input("Lugar",
                            value=c.get("lugar") or "")
                    with col_ee4:
                        et_presup = st.number_input("Presupuesto",
                            min_value=0, step=100,
                            value=int(c.get("presupuesto_estimado") or 0))

                    et_desc = st.text_area("Descripción",
                        value=c.get("descripcion") or "", height=70)
                    et_prep = st.text_area("¿Qué preparar?",
                        value=c.get("notas_preparacion") or "", height=50)

                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button("💾 Guardar",
                                                 use_container_width=True,
                                                 type="primary"):
                            if not et_titulo.strip():
                                st.error("⚠️ Título obligatorio")
                            else:
                                actualizar_cita(
                                    c["id"],
                                    et_fecha.isoformat(),
                                    None,           # hora sin campo en edición
                                    et_tipo,
                                    et_titulo.strip(),
                                    et_desc,
                                    et_lugar,
                                    et_presup,
                                    et_estado,
                                    edit_ambito,
                                    et_prep
                                )
                                st.session_state.cita_editando = None
                                st.success("✅ Evento actualizado")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button("✖ Cancelar",
                                                 use_container_width=True):
                            st.session_state.cita_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: NOTAS
# ═══════════════════════════════════════════════════════════════

with tab_notas:
    for key, default in [
        ("nota_editando",     None),
        ("mostrar_form_nota", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    col_nf1,col_nf2,col_nf3,col_nbtn = st.columns([2,2,2,1])
    with col_nf1:
        f_cat_nota = st.selectbox("Categoría",
            ["Todas"]+CATEGORIAS_NOTA, key="f_cat_nota")
    with col_nf2:
        f_urg_min  = st.select_slider("Urgencia mínima",
            options=[1,2,3,4,5,6,7,8,9,10], value=1, key="f_urg_nota")
    with col_nf3:
        f_bus_nota = st.text_input("Buscar",
            placeholder="Texto de la nota...", key="f_bus_nota")
    with col_nbtn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ Nueva", use_container_width=True,
                     type="primary", key="btn_nueva_nota"):
            st.session_state.mostrar_form_nota = True
            st.session_state.nota_editando     = None

    # ── Formulario: Nueva nota ────────────────────────────────
    if st.session_state.mostrar_form_nota:
        st.divider()
        st.markdown("### ➕ Nueva nota")
        with st.form("form_nueva_nota", clear_on_submit=True):
            col_nn1, col_nn2 = st.columns(2)
            with col_nn1:
                nn_cat      = st.selectbox("Categoría", CATEGORIAS_NOTA)
                nn_urgencia = st.slider("Urgencia", 1, 10, 5,
                    help="10 = hacer ASAP")
            with col_nn2:
                nn_fecha = st.date_input("Fecha de mención", value=hoy)
                nn_ctx   = st.text_input("Contexto",
                    placeholder="Dónde / cuándo se mencionó...")

            nn_contenido = st.text_area("Contenido *", height=80,
                placeholder="Ej: Le encanta el chocolate amargo...")

            col_sg, col_sc = st.columns(2)
            with col_sg:
                submit_nota = st.form_submit_button(
                    "💾 Guardar nota",
                    use_container_width=True, type="primary"
                )
            with col_sc:
                cancel_nota = st.form_submit_button(
                    "✖ Cancelar", use_container_width=True
                )

            if cancel_nota:
                st.session_state.mostrar_form_nota = False
                st.rerun()
            if submit_nota:
                if not nn_contenido.strip():
                    st.error("⚠️ El contenido es obligatorio")
                else:
                    guardar_nota(
                        nn_cat, nn_contenido.strip(),
                        nn_ctx,
                        nn_fecha.isoformat(),   # ← str ISO
                        nn_urgencia
                    )
                    st.success("✅ Nota guardada")
                    st.session_state.mostrar_form_nota = False
                    st.rerun()

    st.divider()

    # ── Lista de notas ────────────────────────────────────────
    notas = obtener_notas(
        None if f_cat_nota == "Todas" else f_cat_nota,
        f_urg_min
    )
    if f_bus_nota:
        notas = [n for n in notas
                 if f_bus_nota.lower() in (n.get("contenido") or "").lower()]

    if not notas:
        st.info("📝 No hay notas con estos filtros")
    else:
        st.caption(f"**{len(notas)} notas encontradas**")

        for n in notas:
            emoji_n   = EMOJIS_NOTA.get(n["categoria"], "📝")
            color_urg = (
                "#f85149" if n["urgencia"] >= 8 else
                "#e3b341" if n["urgencia"] >= 5 else "#8b949e"
            )
            ctx_html = (
                f"<div style='color:#8b949e;font-size:0.75rem;"
                f"margin-top:0.25rem;'>"
                f"📍 {n['contexto']} · {n['fecha_mencion']}</div>"
            ) if n.get("contexto") else ""

            col_ncard, col_nacc = st.columns([5, 1])
            with col_ncard:
                st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-left:4px solid {color_urg};
            border-radius:10px;padding:0.85rem 1.25rem;
            margin-bottom:0.4rem;">
    <div style="display:flex;justify-content:space-between;">
        <span style="font-weight:600;color:#f0f6fc;">
            {emoji_n} {n['categoria'].replace('_',' ')}
        </span>
        <span style="font-size:0.72rem;color:{color_urg};">
            ● {n['urgencia']}/10
        </span>
    </div>
    <div style="color:#c9d1d9;font-size:0.9rem;margin-top:0.35rem;">
        {n['contenido']}
    </div>
    {ctx_html}
</div>""")

            with col_nacc:
                if st.button("✏️", key=f"en_{n['id']}",
                             help="Editar", use_container_width=True):
                    st.session_state.nota_editando     = n["id"]
                    st.session_state.mostrar_form_nota = False
                if st.button("🗑️", key=f"dn_{n['id']}",
                             help="Eliminar", use_container_width=True):
                    st.session_state[f"del_nota_{n['id']}"] = True

            # Confirmar eliminación
            if st.session_state.get(f"del_nota_{n['id']}"):
                cn1, cn2, cn3 = st.columns([2,1,1])
                with cn1:
                    st.warning(
                        f"⚠️ ¿Eliminar nota de "
                        f"*{n['categoria'].replace('_',' ')}*?"
                    )
                with cn2:
                    if st.button("🗑️ Sí", key=f"cdn_{n['id']}",
                                 use_container_width=True):
                        eliminar_nota(n["id"])
                        st.session_state[f"del_nota_{n['id']}"] = False
                        st.rerun()
                with cn3:
                    if st.button("✖", key=f"cnn_{n['id']}",
                                 use_container_width=True):
                        st.session_state[f"del_nota_{n['id']}"] = False
                        st.rerun()

            # Edición inline
            if st.session_state.nota_editando == n["id"]:
                with st.form(f"form_edit_nota_{n['id']}"):
                    st.markdown("#### ✏️ Editando nota")
                    col_en1, col_en2 = st.columns(2)
                    with col_en1:
                        en_cat = st.selectbox(
                            "Categoría", CATEGORIAS_NOTA,
                            index=CATEGORIAS_NOTA.index(n["categoria"])
                            if n["categoria"] in CATEGORIAS_NOTA else 0
                        )
                        en_urg = st.slider("Urgencia", 1, 10,
                            value=int(n["urgencia"]))
                    with col_en2:
                        en_ctx = st.text_input("Contexto",
                            value=n.get("contexto") or "")

                    en_cont = st.text_area("Contenido",
                        value=n.get("contenido") or "", height=80)

                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button("💾 Guardar",
                                                 use_container_width=True,
                                                 type="primary"):
                            if not en_cont.strip():
                                st.error("⚠️ Contenido obligatorio")
                            else:
                                actualizar_nota(
                                    n["id"], en_cat,
                                    en_cont.strip(), en_ctx, en_urg
                                )
                                st.session_state.nota_editando = None
                                st.success("✅ Nota actualizada")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button("✖ Cancelar",
                                                 use_container_width=True):
                            st.session_state.nota_editando = None
                            st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.markdown("### 📊 Historial de conexión")
    col_h1, col_h2 = st.columns([1, 2])

    with col_h1:
        st.markdown("#### ⏱️ Registrar sesión")
        with st.form("form_habito", clear_on_submit=True):
            hb_fecha = st.date_input("Fecha", value=hoy)    # ← local
            hb_min   = st.slider("Tiempo calidad (min)", 15, 240, 60, step=15)
            hb_tipo  = st.selectbox("Tipo de conexión", [
                "Tiempo_Calidad","Conversacion_Profunda","Actividad_Juntos",
                "Oracion_Pareja","Salida_Familia","Otro",
            ])
            hb_inic  = st.selectbox("Iniciado por", ["Yo","Mi esposa","Ambos"])
            hb_sat   = st.slider("Satisfacción", 1, 10, 7)
            hb_notas = st.text_area("Notas", height=60,
                placeholder="¿Qué hicieron? ¿Cómo se sintieron?")
            hb_modo  = st.checkbox("Modo pareja 21:00 respetado")

            if st.form_submit_button("💾 Guardar",
                                     use_container_width=True, type="primary"):
                registrar_habito(
                    hb_fecha.isoformat(),   # ← str ISO
                    hb_min, hb_tipo,
                    hb_inic, hb_sat, hb_notas,
                    1 if hb_modo else 0
                )
                st.success("✅ Sesión registrada")
                st.rerun()

    with col_h2:
        habitos_h = obtener_habitos_recientes(90)

        if not habitos_h:
            st.info("📊 Sin datos. Registra tu primera sesión.")
        else:
            prom_sat_h = sum(h["satisfaccion"] or 0 for h in habitos_h) / len(habitos_h)
            modo_ok_h  = sum(1 for h in habitos_h if h["modo_pareja_activado"])
            prom_min_h = (
                sum(h["tiempo_calidad_minutos"] or 0 for h in habitos_h)
                / len(habitos_h)
            )

            col_m1,col_m2,col_m3,col_m4 = st.columns(4)
            col_m1.metric("Registros",    len(habitos_h))
            col_m2.metric("Satisfacción", f"{prom_sat_h:.1f}/10")
            col_m3.metric("Modo 21:00",   f"{modo_ok_h}/{len(habitos_h)}")
            col_m4.metric("Prom. tiempo", f"{prom_min_h:.0f} min")

            st.divider()
            st.markdown("**📈 Satisfacción en el tiempo**")
            import pandas as pd
            df_h = pd.DataFrame({
                "Fecha":        [h["fecha"] for h in habitos_h],
                "Satisfacción": [h["satisfaccion"] or 0 for h in habitos_h],
                "Tiempo (min)": [h["tiempo_calidad_minutos"] or 0
                                 for h in habitos_h],
            }).set_index("Fecha")
            st.line_chart(df_h)

# ═══════════════════════════════════════════════════════════════
# TAB 4: IA CONSEJERO
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.markdown("### 🤖 IA Consejero Matrimonial y Familiar")

    if not api_key_configurada():
        st.warning("⚠️ IA offline")

    col_ic, col_ich = st.columns([1, 2])

    with col_ic:
        st.markdown("**🎯 Contexto**")
        ia_ambito    = st.selectbox("Área de consulta",
            ["Matrimonio","Familia","Ambos"], key="ia_ambito")
        tipo_consejo = st.selectbox("Tipo de consejo", [
            "Planificar cita / salida",
            "Resolver conflicto reciente",
            "Reconectar después de temporada ocupada",
            "Ideas para actividades familiares",
            "Cómo mostrar aprecio diario",
            "Balance trabajo-familia-matrimonio",
            "Reflexión bíblica sobre el tema",
        ], key="tipo_consejo_ia")
        detalle_ia = st.text_area("Describe tu situación", height=100,
            placeholder="Ej: Hemos estado muy ocupados...",
            key="detalle_ia")

        citas_rec = obtener_citas(
            fecha_desde=(hoy - timedelta(days=30)).isoformat()
        )
        habs_rec  = obtener_habitos_recientes(30)
        ctx_auto  = (
            f"Último mes: {len(citas_rec)} eventos, "
            f"{len(habs_rec)} sesiones registradas."
        )
        st.caption(ctx_auto)

    with col_ich:
        st.markdown("**💬 Consejo personalizado**")
        if st.button("🚀 Obtener consejo", use_container_width=True,
                     type="primary", key="btn_consejo"):
            with st.spinner("Consejero reflexionando..."):
                st.info(chat_simple(
                    f"Área: {ia_ambito}\n"
                    f"Solicitud: {tipo_consejo}\n"
                    f"Situación: {detalle_ia or 'Ver contexto'}\n"
                    f"Contexto: {ctx_auto}\n\n"
                    f"Da 2-3 sugerencias prácticas. "
                    f"Incluye un principio bíblico relevante. "
                    f"Máximo 150 palabras.",
                    contexto=(
                        "Consejero matrimonial y familiar cristiano, "
                        "práctico, empático y bíblico."
                    )
                ))

        st.divider()
        st.markdown("**💬 Pregunta libre**")
        pregunta_libre_m = st.text_input(
            "Tu pregunta",
            placeholder="Ej: ¿Cómo equilibro el estudio con la familia?",
            key="preg_libre_m"
        )
        if pregunta_libre_m:
            with st.spinner("Pensando..."):
                st.info(chat_simple(
                    f"Contexto: {ctx_auto}\n"
                    f"Pregunta: {pregunta_libre_m}",
                    contexto=(
                        "Consejero matrimonial y familiar cristiano, "
                        "práctico y bíblico. Máximo 120 palabras."
                    )
                ))

st.divider()
st.caption(
    "💑 Conexión Matrimonial y Familiar · "
    "El tiempo de calidad es inversión, no gasto"
)