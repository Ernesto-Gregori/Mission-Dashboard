"""
📅 Agenda — Calendario unificado + Bitácora semanal + Rachas
"""

import streamlit as st
from datetime import timedelta
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, after_write, invalidate_data_caches
from app.database import (
    ejecutar,
    ejecutar_cached,
    obtener_ingreso,
    calcular_sobres,
)
from app.tenant import uid
from app.ai_client import chat_simple, api_key_configurada
from app.google_calendar import (
    obtener_eventos_google,
    crear_evento_google,
    eliminar_evento_google,
    calendar_disponible,
    sincronizar_bloques_semana,
)
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    ahora as _ahora,
    iso_ahora,
)

st.set_page_config(
    page_title="Agenda | Mission Dashboard",
    page_icon="📅",
    layout="wide"
)

from app.auth import require_auth
require_auth()
ensure_database()

# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════

DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
SEMAFOROS   = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}

SYSTEM_AGENDA = """Eres un asistente de planificación semanal cristiano.
Ayudas a revisar victorias, planificar la semana y reflexionar.
Eres práctico, motivador y consideras el balance vida-fe-familia.
Máximo 120 palabras."""

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — BITÁCORA
# ═══════════════════════════════════════════════════════════════

def obtener_lunes_semana(fecha=None):
    f = fecha or _hoy()
    return f - timedelta(days=f.weekday())


def guardar_bitacora(datos: dict) -> bool:
    try:
        ejecutar("""
            INSERT INTO bitacora_semanal (
                user_id, semana_inicio, victoria_1, victoria_2, victoria_3,
                ingreso_actual, sobre_supervivencia, aporte_transicion,
                presupuesto_cita, semaforo_superv, semaforo_ahorros,
                semaforo_extras, gasto_pausado,
                actividad_cita, costo_cita,
                libro_actual, pagina_actual, frase_favorita,
                pendientes_soltar, reflexion_semana, estado,
                actualizado_en
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'abierta',?
            )
            ON CONFLICT(user_id, semana_inicio) DO UPDATE SET
                victoria_1          = excluded.victoria_1,
                victoria_2          = excluded.victoria_2,
                victoria_3          = excluded.victoria_3,
                ingreso_actual      = excluded.ingreso_actual,
                sobre_supervivencia = excluded.sobre_supervivencia,
                aporte_transicion   = excluded.aporte_transicion,
                presupuesto_cita    = excluded.presupuesto_cita,
                semaforo_superv     = excluded.semaforo_superv,
                semaforo_ahorros    = excluded.semaforo_ahorros,
                semaforo_extras     = excluded.semaforo_extras,
                gasto_pausado       = excluded.gasto_pausado,
                actividad_cita      = excluded.actividad_cita,
                costo_cita          = excluded.costo_cita,
                libro_actual        = excluded.libro_actual,
                pagina_actual       = excluded.pagina_actual,
                frase_favorita      = excluded.frase_favorita,
                pendientes_soltar   = excluded.pendientes_soltar,
                reflexion_semana    = excluded.reflexion_semana,
                actualizado_en      = excluded.actualizado_en
        """, [
            uid(),
            datos["semana_inicio"],
            datos.get("victoria_1", ""),
            datos.get("victoria_2", ""),
            datos.get("victoria_3", ""),
            datos.get("ingreso_actual", 0),
            datos.get("sobre_supervivencia", 0),
            datos.get("aporte_transicion", 0),
            datos.get("presupuesto_cita", 0),
            datos.get("semaforo_superv", "verde"),
            datos.get("semaforo_ahorros", "verde"),
            datos.get("semaforo_extras", "verde"),
            datos.get("gasto_pausado", ""),
            datos.get("actividad_cita", ""),
            datos.get("costo_cita", 0),
            datos.get("libro_actual", ""),
            datos.get("pagina_actual", 0),
            datos.get("frase_favorita", ""),
            datos.get("pendientes_soltar", ""),
            datos.get("reflexion_semana", ""),
            iso_ahora(),                          # ← zona horaria local
        ])
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False


def obtener_bitacora(semana_inicio: str) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM bitacora_semanal WHERE semana_inicio = ? AND user_id = ?",
        [semana_inicio, uid()], fetchall=True,
    )
    return rows[0] if rows else None


def obtener_bitacoras_recientes(limite: int = 10) -> list:
    return ejecutar_cached("""
        SELECT * FROM bitacora_semanal
        WHERE user_id = ?
        ORDER BY semana_inicio DESC LIMIT ?
    """, (uid(), limite)) or []


# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB — DATOS DE MÓDULOS
# ═══════════════════════════════════════════════════════════════

def obtener_eventos_semana(lunes: date, domingo: date) -> list:
    citas = ejecutar("""
        SELECT fecha, hora AS hora_inicio, titulo,
               tipo_cita AS tipo, estado_planificacion,
               COALESCE(ambito,'Matrimonio') AS ambito,
               '#a371f7' AS color, NULL AS google_id
        FROM matrimonio_citas
        WHERE fecha >= ? AND fecha <= ? AND user_id = ?
        ORDER BY fecha, hora
    """, [lunes.isoformat(), domingo.isoformat(), uid()], fetchall=True) or []

    locales = ejecutar("""
        SELECT fecha, hora_inicio, titulo, tipo,
               '' AS estado_planificacion, tipo AS ambito,
               color, google_id
        FROM eventos_calendario
        WHERE fecha >= ? AND fecha <= ? AND user_id = ?
        ORDER BY fecha, hora_inicio
    """, [lunes.isoformat(), domingo.isoformat(), uid()], fetchall=True) or []

    bloques_rows = ejecutar_cached(
        "SELECT nombre FROM bloques_fijos WHERE activo = 1 AND user_id = ?",
        (uid(),),
    ) or []
    nombres_bloques = {r["nombre"] for r in bloques_rows}

    google_ids_sincronizados = {
        e["google_id"] for e in locales if e.get("google_id")
    }

    google_eventos = []
    if calendar_disponible():
        eventos_gc    = obtener_eventos_google(lunes, domingo)
        google_eventos = [
            e for e in eventos_gc
            if e.get("google_id") not in google_ids_sincronizados
            and e.get("titulo") not in nombres_bloques
        ]

    todos = citas + locales + google_eventos
    todos.sort(key=lambda e: (e.get("fecha",""), e.get("hora_inicio") or "23:59"))
    return todos


@st.cache_data(ttl=60, show_spinner=False)
def _eventos_semana_cached(lunes_iso: str, domingo_iso: str, _user_id: int) -> list:
    """Cache corto para no pegarle a Google en cada tecla/recarga."""
    from datetime import date as _date
    return obtener_eventos_semana(
        _date.fromisoformat(lunes_iso),
        _date.fromisoformat(domingo_iso),
    )


def obtener_deepwork_semana(lunes: date, domingo: date) -> list:
    resultado = []
    for i in range(7):
        dia        = lunes + timedelta(days=i)
        dia_iso    = dia.isoformat()
        dia_numero = dia.weekday() + 1

        bloques = ejecutar("""
            SELECT b.id, b.nombre, b.color, b.tipo,
                   b.hora_inicio, b.hora_fin, b.dias_semana,
                   s.estado, s.duracion_real, s.notas
            FROM bloques_fijos b
            LEFT JOIN sesiones_completadas s
                ON s.bloque_fijo_id = b.id AND s.fecha = ? AND s.user_id = ?
            WHERE b.activo = 1 AND b.user_id = ?
        """, [dia_iso, uid(), uid()], fetchall=True) or []

        for b in bloques:
            dias = json.loads(b["dias_semana"])
            if dia_numero not in dias:
                continue
            estado     = b["estado"] or "Pendiente"
            completado = 1 if estado == "Completado" else 0
            resultado.append({
                "fecha":         dia_iso,
                "bloque_nombre": b["nombre"],
                "color":         b["color"],
                "tipo":          b["tipo"],
                "hora_inicio":   b["hora_inicio"],
                "duracion_real": b["duracion_real"],
                "estado":        estado,
                "completado":    completado,
                "notas":         b["notas"],
            })

    resultado.sort(key=lambda x: (x["fecha"], x.get("hora_inicio") or ""))
    return resultado


def obtener_devocionales_semana(lunes: date, domingo: date) -> list:
    return ejecutar("""
        SELECT fecha, pasaje_referencia, duracion_minutos
        FROM devocionales
        WHERE fecha BETWEEN ? AND ? AND user_id = ?
        ORDER BY fecha
    """, [lunes.isoformat(), domingo.isoformat(), uid()], fetchall=True) or []


def obtener_salud_semana(lunes: date, domingo: date) -> list:
    return ejecutar("""
        SELECT fecha, horas_sueno,
               energia_manana AS nivel_energia,
               hizo_ejercicio, productividad_percibida
        FROM registros_salud
        WHERE fecha BETWEEN ? AND ? AND user_id = ?
        ORDER BY fecha
    """, [lunes.isoformat(), domingo.isoformat(), uid()], fetchall=True) or []


def obtener_libros_leyendo() -> list:
    return ejecutar_cached("""
        SELECT titulo, autor, pagina_actual, total_paginas
        FROM libros WHERE estado = 'leyendo' AND user_id = ?
        ORDER BY actualizado_en DESC
    """, (uid(),)) or []


# ═══════════════════════════════════════════════════════════════
# FUNCIONES — RACHAS  (usan _hoy() en lugar de date.today())
# ═══════════════════════════════════════════════════════════════

def calcular_racha_devocional() -> int:
    fechas_rows = ejecutar_cached(
        "SELECT fecha FROM devocionales WHERE user_id = ? ORDER BY fecha DESC LIMIT 30",
        (uid(),),
    ) or []
    fechas = [
        datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        for r in fechas_rows
    ]
    racha = 0
    hoy   = _hoy()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha


def calcular_racha_ejercicio() -> int:
    fechas_rows = ejecutar_cached("""
        SELECT fecha FROM registros_salud
        WHERE hizo_ejercicio = 1 AND user_id = ?
        ORDER BY fecha DESC LIMIT 30
    """, (uid(),)) or []
    fechas = [
        datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        for r in fechas_rows
    ]
    if not fechas:
        return 0
    hoy_lun = _hoy() - timedelta(days=_hoy().weekday())
    semanas  = {f - timedelta(days=f.weekday()) for f in fechas}
    racha    = 0
    for i in range(52):
        if (hoy_lun - timedelta(weeks=i)) in semanas:
            racha += 1
        else:
            break
    return racha


def calcular_racha_deepwork() -> int:
    fechas_rows = ejecutar_cached("""
        SELECT DISTINCT fecha FROM sesiones_completadas
        WHERE estado = 'Completado' AND user_id = ?
        ORDER BY fecha DESC LIMIT 30
    """, (uid(),)) or []
    fechas = [
        datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        for r in fechas_rows
    ]
    racha = 0
    hoy   = _hoy()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha


# ═══════════════════════════════════════════════════════════════
# FUNCIONES — EVENTOS PERSONALIZADOS
# ═══════════════════════════════════════════════════════════════

def obtener_eventos_personalizados(fecha: str = None) -> list:
    if fecha:
        return ejecutar("""
            SELECT * FROM eventos_calendario
            WHERE fecha = ? AND user_id = ? ORDER BY hora_inicio
        """, [fecha, uid()], fetchall=True) or []
    return ejecutar("""
        SELECT * FROM eventos_calendario
        WHERE user_id = ?
        ORDER BY fecha DESC, hora_inicio LIMIT 50
    """, [uid()], fetchall=True) or []


def guardar_evento(datos: dict) -> int:
    google_id = None
    if calendar_disponible():
        google_id = crear_evento_google(datos)
    return ejecutar("""
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, descripcion,
             tipo, color, google_id, fuente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        uid(),
        datos["fecha"], datos.get("hora_inicio"), datos.get("hora_fin"),
        datos["titulo"], datos.get("descripcion", ""),
        datos.get("tipo", "Personal"), datos.get("color", "#58a6ff"),
        google_id, "local",
    ])


def eliminar_evento(evento_id: int) -> bool:
    rows = ejecutar(
        "SELECT google_id FROM eventos_calendario WHERE id = ? AND user_id = ?",
        [evento_id, uid()], fetchall=True,
    )
    google_id = rows[0]["google_id"] if rows else None
    ejecutar("DELETE FROM eventos_calendario WHERE id = ? AND user_id = ?", [evento_id, uid()])
    if google_id and calendar_disponible():
        eliminar_evento_google(google_id)
    return True


def _presupuesto_cita_auto(citas_mat: list) -> float:
    if not citas_mat:
        return 0.0
    rows = ejecutar("""
        SELECT presupuesto_estimado FROM matrimonio_citas
        WHERE titulo = ? AND fecha = ? AND user_id = ?
    """, [citas_mat[0]["titulo"], citas_mat[0]["fecha"], uid()], fetchall=True)
    if rows and rows[0]["presupuesto_estimado"]:
        return float(rows[0]["presupuesto_estimado"])
    return 0.0


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("📅 Agenda")
st.caption(
    "Calendario unificado · Bitácora semanal · Rachas · "
    "Lunes 18:00 abrir · Domingo 20:30 vaciado mental"
)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — RACHAS
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔥 Rachas activas")

    r_dev = calcular_racha_devocional()
    r_ej  = calcular_racha_ejercicio()
    r_dw  = calcular_racha_deepwork()

    color_dev = "#3fb950" if r_dev >= 7 else "#e3b341" if r_dev >= 3 else "#f85149"
    st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-radius:10px;padding:0.75rem 1rem;
            margin-bottom:0.5rem;text-align:center;">
    <div style="font-size:1.5rem;">✝️</div>
    <div style="font-weight:700;color:{color_dev};font-size:1.25rem;">{r_dev} días</div>
    <div style="color:#8b949e;font-size:0.75rem;">Racha devocional</div>
</div>""")

    color_ej = "#3fb950" if r_ej >= 4 else "#e3b341" if r_ej >= 2 else "#f85149"
    st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-radius:10px;padding:0.75rem 1rem;
            margin-bottom:0.5rem;text-align:center;">
    <div style="font-size:1.5rem;">💪</div>
    <div style="font-weight:700;color:{color_ej};font-size:1.25rem;">{r_ej} semanas</div>
    <div style="color:#8b949e;font-size:0.75rem;">Racha ejercicio</div>
</div>""")

    color_dw = "#3fb950" if r_dw >= 5 else "#e3b341" if r_dw >= 3 else "#f85149"
    st.html(f"""
<div style="background:#161b22;border:1px solid #30363d;
            border-radius:10px;padding:0.75rem 1rem;
            margin-bottom:0.5rem;text-align:center;">
    <div style="font-size:1.5rem;">⏱️</div>
    <div style="font-weight:700;color:{color_dw};font-size:1.25rem;">{r_dw} días</div>
    <div style="color:#8b949e;font-size:0.75rem;">Racha Deep Work</div>
</div>""")

    st.divider()

    # Hora local para alertas de sidebar
    hora_actual = _ahora().hour
    if hora_actual >= 20 and _hoy().weekday() == 6:
        st.warning("🌙 Domingo 20:30 — Vaciado mental")

    if api_key_configurada():
        st.success("🤖 IA activa")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_cal, tab_bitacora, tab_historial_bit = st.tabs([
    "📅 Calendario", "📋 Bitácora Semanal", "🗂️ Historial"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: CALENDARIO
# ═══════════════════════════════════════════════════════════════

with tab_cal:
    st.subheader("📅 Vista semanal unificada")

    col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
    with col_nav1:
        if st.button("◀ Anterior", use_container_width=True):
            st.session_state.cal_offset = st.session_state.get("cal_offset", 0) - 1
    with col_nav2:
        lunes_base  = obtener_lunes_semana()
        lunes_sel   = lunes_base + timedelta(weeks=st.session_state.get("cal_offset", 0))
        domingo_sel = lunes_sel + timedelta(days=6)
        st.markdown(
            f"<h4 style='text-align:center;margin:0;'>"
            f"Semana del {lunes_sel.strftime('%d/%m')} "
            f"al {domingo_sel.strftime('%d/%m/%Y')}</h4>",
            unsafe_allow_html=True,
        )
    with col_nav3:
        if st.button("Siguiente ▶", use_container_width=True):
            st.session_state.cal_offset = st.session_state.get("cal_offset", 0) + 1

    clave_sync = f"sync_dw_{lunes_sel.isoformat()}"
    if calendar_disponible() and clave_sync not in st.session_state:
        with st.spinner("Sincronizando bloques con Google Calendar..."):
            creados = sincronizar_bloques_semana(lunes_sel, domingo_sel)
            st.session_state[clave_sync] = True
        if creados > 0:
            st.success(f"✅ {creados} bloques sincronizados con Google Calendar")

    col_hoy, col_nuevo, col_gcal = st.columns([1, 2, 1])
    with col_hoy:
        if st.button("📅 Hoy", use_container_width=True):
            st.session_state.cal_offset = 0
            st.rerun()
    with col_nuevo:
        if st.button("➕ Nuevo evento", use_container_width=True, type="primary"):
            st.session_state["mostrar_form_evento"] = True
    with col_gcal:
        if calendar_disponible():
            st.success("📅 Sincronizado")
        else:
            st.warning("⚠️ Sin Google Cal")

    # Formulario nuevo evento
    if st.session_state.get("mostrar_form_evento"):
        COLORES_TIPO = {
            "Lectura":    "#e3b341",
            "Personal":   "#58a6ff",
            "Ministerio": "#a371f7",
            "Salud":      "#3fb950",
            "Estudio":    "#f0883e",
            "Otro":       "#8b949e",
        }
        with st.expander("➕ Agregar evento al calendario", expanded=True):
            with st.form("form_nuevo_evento", clear_on_submit=True):
                col_fe1, col_fe2 = st.columns(2)
                with col_fe1:
                    fecha_ev  = st.date_input("Fecha", value=_hoy(), key="ev_fecha")
                    titulo_ev = st.text_input("Título *",
                        placeholder="Ej: Lectura biblioteca", key="ev_titulo")
                    tipo_ev   = st.selectbox("Tipo",
                        ["Lectura","Personal","Ministerio","Salud","Estudio","Otro"],
                        key="ev_tipo")
                with col_fe2:
                    hora_ini = st.time_input("Hora inicio", key="ev_hora_ini",
                        value=datetime.strptime("19:30", "%H:%M").time())
                    hora_fin = st.time_input("Hora fin", key="ev_hora_fin",
                        value=datetime.strptime("21:00", "%H:%M").time())
                desc_ev = st.text_area("Descripción (opcional)", height=60, key="ev_desc")

                col_guardar, col_cancelar = st.columns(2)
                with col_guardar:
                    if st.form_submit_button("💾 Guardar evento", use_container_width=True):
                        if titulo_ev:
                            guardar_evento({
                                "fecha":       fecha_ev.isoformat(),
                                "hora_inicio": hora_ini.strftime("%H:%M"),
                                "hora_fin":    hora_fin.strftime("%H:%M"),
                                "titulo":      titulo_ev,
                                "descripcion": desc_ev,
                                "tipo":        tipo_ev,
                                "color":       COLORES_TIPO.get(tipo_ev, "#58a6ff"),
                            })
                            st.session_state["mostrar_form_evento"] = False
                            st.success("✅ Evento guardado")
                            st.rerun()
                        else:
                            st.error("El título es obligatorio")
                with col_cancelar:
                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.session_state["mostrar_form_evento"] = False
                        st.rerun()

    st.divider()

    # Datos de la semana
    eventos   = obtener_eventos_semana(lunes_sel, domingo_sel)
    dw_ses    = obtener_deepwork_semana(lunes_sel, domingo_sel)
    devos     = obtener_devocionales_semana(lunes_sel, domingo_sel)
    salud_sem = obtener_salud_semana(lunes_sel, domingo_sel)

    eventos_x_fecha = {}
    for e in eventos:
        eventos_x_fecha.setdefault(e["fecha"], []).append(e)
    dw_x_fecha = {}
    for s in dw_ses:
        dw_x_fecha.setdefault(s["fecha"], []).append(s)
    devo_x_fecha  = {d["fecha"]: d for d in devos}
    salud_x_fecha = {s["fecha"]: s for s in salud_sem}

    col_l1,col_l2,col_l3,col_l4,col_l5,col_l6 = st.columns(6)
    col_l1.caption("✝️ Devocional")
    col_l2.caption("⏱️ Deep Work")
    col_l3.caption("💑 Matrimonio")
    col_l4.caption("📚 Lectura")
    col_l5.caption("💪 Ejercicio")
    col_l6.caption("🔵 Personal")
    st.markdown("")

    cols_dias = st.columns(7)
    hoy = _hoy()   # ← zona horaria local

    COLORES_AMBITO = {
        "Matrimonio": ("#a371f7", "#1a1229", "💑"),
        "Lectura":    ("#e3b341", "#1f1a0d", "📚"),
        "Personal":   ("#58a6ff", "#0d1629", "🔵"),
        "Ministerio": ("#a371f7", "#1a1229", "⛪"),
        "Salud":      ("#3fb950", "#0d2818", "💪"),
        "Estudio":    ("#f0883e", "#1f1209", "📖"),
        "Otro":       ("#8b949e", "#161b22", "📌"),
    }

    for i, col in enumerate(cols_dias):
        dia     = lunes_sel + timedelta(days=i)
        dia_iso = dia.isoformat()
        es_hoy  = dia == hoy
        bg_header = "#0d2818" if es_hoy else "#161b22"
        border_c  = "#3fb950" if es_hoy else "#30363d"

        with col:
            st.html(f"""
<div style="background:{bg_header};border:1px solid {border_c};
            border-radius:8px 8px 0 0;padding:0.4rem;
            text-align:center;margin-bottom:2px;">
    <div style="font-weight:700;color:#f0f6fc;font-size:0.85rem;">{DIAS_SEMANA[i]}</div>
    <div style="color:{'#3fb950' if es_hoy else '#8b949e'};font-size:0.75rem;">
        {dia.strftime('%d/%m')}
    </div>
</div>""")

            if dia_iso in devo_x_fecha:
                d = devo_x_fecha[dia_iso]
                st.html(f"""
<div style="background:#0d2818;border-left:3px solid #3fb950;
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#9be4a0;">
    ✝️ {(d.get('pasaje_referencia') or '')[:14]}
</div>""")

            if dia_iso in dw_x_fecha:
                for s in dw_x_fecha[dia_iso]:
                    color_dw_b = s.get("color") or "#58a6ff"
                    completado = s.get("completado", 0)
                    bg_dw      = "#0d1f2d" if completado else "#161b22"
                    opacity    = "1" if completado else "0.6"
                    check      = "✓ " if completado else ""
                    st.html(f"""
<div style="background:{bg_dw};border-left:3px solid {color_dw_b};
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;
            color:#c9d1d9;opacity:{opacity};">
    ⏱️ {check}{(s.get('bloque_nombre') or s.get('tipo','DW'))[:12]}
</div>""")

            if dia_iso in eventos_x_fecha:
                for e in eventos_x_fecha[dia_iso]:
                    ambito              = e.get("ambito", "Otro")
                    color_e, bg_e, icon = COLORES_AMBITO.get(
                        ambito, ("#8b949e", "#161b22", "📌")
                    )
                    hora_str = f" {e['hora_inicio'][:5]}" if e.get("hora_inicio") else ""
                    st.html(f"""
<div style="background:{bg_e};border-left:3px solid {color_e};
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#c9d1d9;">
    {icon} {(e.get('titulo') or '')[:13]}{hora_str}
</div>""")

            if dia_iso in salud_x_fecha:
                s_dia = salud_x_fecha[dia_iso]
                if s_dia.get("hizo_ejercicio"):
                    tipo_ej = s_dia.get("tipo_ejercicio", "Ejercicio") or "Ejercicio"
                    st.html(f"""
<div style="background:#0d2818;border-left:3px solid #f0883e;
            border-radius:4px;padding:0.3rem 0.4rem;
            margin-bottom:2px;font-size:0.7rem;color:#f0883e;">
    💪 {tipo_ej[:14]}
</div>""")
                energia = s_dia.get("nivel_energia") or 0
                if energia:
                    color_en = (
                        "#3fb950" if energia >= 8 else
                        "#e3b341" if energia >= 5 else "#f85149"
                    )
                    st.html(f"""
<div style="background:#161b22;border-radius:4px;
            padding:0.2rem 0.4rem;font-size:0.65rem;
            color:{color_en};">⚡ {energia}/10</div>""")

    st.divider()
    col_res, col_gest = st.columns([2, 1])

    with col_res:
        st.markdown("### 📊 Resumen de la semana")
        col_r1,col_r2,col_r3,col_r4,col_r5 = st.columns(5)
        col_r1.metric("✝️ Devocionales", f"{len(devos)}/7")
        col_r2.metric("⏱️ Deep Work",
            len([s for s in dw_ses if s.get("completado") == 1]))
        col_r3.metric("📅 Eventos", len(eventos))
        col_r4.metric("💪 Ejercicios",
            len([s for s in salud_sem if s.get("hizo_ejercicio")]))
        prom_energia = (
            sum(s.get("nivel_energia") or 0 for s in salud_sem) / len(salud_sem)
            if salud_sem else 0
        )
        col_r5.metric("⚡ Energía",
            f"{prom_energia:.1f}/10" if prom_energia else "—")

    with col_gest:
        st.markdown("### 🗑️ Gestionar eventos")
        eventos_pers = obtener_eventos_personalizados()
        if not eventos_pers:
            st.caption("Sin eventos personalizados aún")
        else:
            for ep in eventos_pers[:5]:
                col_ep1, col_ep2 = st.columns([3, 1])
                with col_ep1:
                    st.caption(f"📌 {ep['fecha']} — {ep['titulo'][:20]}")
                with col_ep2:
                    if st.button("🗑️", key=f"del_ev_{ep['id']}"):
                        eliminar_evento(ep["id"])
                        st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 2: BITÁCORA SEMANAL
# ═══════════════════════════════════════════════════════════════

with tab_bitacora:
    st.subheader("📋 Bitácora Semanal")
    st.caption("Abrir domingo 19:00 · cierre de revisión semanal")

    col_bs1, col_bs2 = st.columns([2, 1])
    with col_bs1:
        fecha_bit_sel = st.date_input(
            "Semana (selecciona cualquier día)",
            value=obtener_lunes_semana(),
            key="fecha_bitacora",
        )
        lunes_bit_sel = obtener_lunes_semana(fecha_bit_sel)
        domingo_bit   = lunes_bit_sel + timedelta(days=6)
        st.caption(
            f"Semana: {lunes_bit_sel.strftime('%d/%m/%Y')} "
            f"— {domingo_bit.strftime('%d/%m/%Y')}"
        )
    with col_bs2:
        st.markdown("<br>", unsafe_allow_html=True)
        if lunes_bit_sel == obtener_lunes_semana():
            st.success("📅 Semana actual")
        else:
            st.caption("📁 Semana pasada")

    bit = obtener_bitacora(lunes_bit_sel.isoformat()) or {}

    mes_bit      = lunes_bit_sel.month
    anio_bit     = lunes_bit_sel.year
    ingreso_auto = obtener_ingreso(mes_bit, anio_bit)
    sobres_data  = calcular_sobres(mes_bit, anio_bit)

    def _semaforo(sobre_key: str) -> str:
        if sobres_data["sin_ingreso"]:
            return "verde"
        pct = sobres_data["sobres"].get(sobre_key, {}).get("pct_usado", 0)
        return "rojo" if pct >= 100 else "amarillo" if pct >= 80 else "verde"

    semaforo_sup_auto = _semaforo("Supervivencia")
    semaforo_aho_auto = _semaforo("Futuro_Hogar")
    semaforo_ext_auto = _semaforo("Ministerio_Extras")

    eventos_bit_auto = _eventos_semana_cached(lunes_bit_sel.isoformat(), domingo_bit.isoformat(), uid())
    citas_mat_auto   = [e for e in eventos_bit_auto if e.get("ambito") == "Matrimonio"]

    racha_dev_auto = calcular_racha_devocional()
    racha_ej_auto  = calcular_racha_ejercicio()
    racha_dw_auto  = calcular_racha_deepwork()

    # ── Formulario bitácora (sin recarga al escribir) ─────────
    st.info("✏️ Completa el formulario y pulsa **Guardar bitácora**. Mientras escribes no se recarga la página.")

    with st.form("form_bitacora_semanal"):
        st.markdown("### 🏆 1. Definición de Objetivos — Las 3 Victorias")
        st.caption("¿Qué 3 cosas harían esta semana un éxito?")

        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            v1 = st.text_area("🥇 Victoria #1", value=bit.get("victoria_1",""),
                height=100, placeholder="Ej: Entregar proyecto de programación")
        with col_v2:
            v2 = st.text_area("🥈 Victoria #2", value=bit.get("victoria_2",""),
                height=100, placeholder="Ej: Completar capítulo de Hermenéutica")
        with col_v3:
            v3 = st.text_area("🥉 Victoria #3", value=bit.get("victoria_3",""),
                height=100, placeholder="Ej: Cita de calidad con esposa")

        st.markdown("---")
        st.markdown("### 💰 2. Monitor Financiero")
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            ingreso = st.number_input("Ingreso actual $", min_value=0.0, step=100.0,
                value=float(bit.get("ingreso_actual") or ingreso_auto or 0))
            sobre_sup = st.checkbox("✅ Sobre de Supervivencia (60-70%) llenado",
                value=bool(bit.get("sobre_supervivencia", 0)))
        with col_f2:
            aporte_trans = st.number_input("Aporte Fondo Transición $", min_value=0.0,
                step=50.0, value=float(bit.get("aporte_transicion") or 0))
            presup_cita = st.number_input("Presupuesto cita con esposa $", min_value=0.0,
                step=50.0, value=float(bit.get("presupuesto_cita") or 0))
        with col_f3:
            gasto_pausado = st.text_input("⚠️ Gasto/sobre a pausar (opcional)",
                value=bit.get("gasto_pausado",""))

        st.markdown("**🚦 Estado del Semáforo:**")
        col_sf1, col_sf2, col_sf3 = st.columns(3)
        opciones_sem = ["verde", "amarillo", "rojo"]
        with col_sf1:
            sem_sup = st.selectbox("Supervivencia", opciones_sem,
                index=opciones_sem.index(bit.get("semaforo_superv","verde")),
                format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}")
        with col_sf2:
            sem_aho = st.selectbox("Ahorros", opciones_sem,
                index=opciones_sem.index(bit.get("semaforo_ahorros","verde")),
                format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}")
        with col_sf3:
            sem_ext = st.selectbox("Extras", opciones_sem,
                index=opciones_sem.index(bit.get("semaforo_extras","verde")),
                format_func=lambda x: f"{SEMAFOROS[x]} {x.capitalize()}")

        st.markdown("---")
        st.markdown("### 💑 3. Diseño de Cita y Conexión")
        eventos_bit = eventos_bit_auto
        citas_mat = citas_mat_auto
        if citas_mat and not bit.get("actividad_cita"):
            st.info(f"💡 Tienes programado: **{citas_mat[0]['titulo']}** el {citas_mat[0]['fecha']}")
        col_cit1, col_cit2 = st.columns(2)
        with col_cit1:
            act_cita = st.text_input("Actividad elegida",
                value=bit.get("actividad_cita","") or (citas_mat[0]["titulo"] if citas_mat else ""),
                placeholder="Cena en casa, salida al parque...")
        with col_cit2:
            costo_cita = st.number_input("Costo estimado $", min_value=0.0, step=50.0,
                value=float(bit.get("costo_cita") or 0))

        st.markdown("---")
        st.markdown("### 📚 4. Log de Lectura y Conocimiento")
        libros_leyendo = obtener_libros_leyendo()
        libro_bit = bit.get("libro_actual","") or ""
        pag_default = 0
        col_lib1, col_lib2 = st.columns(2)
        with col_lib1:
            if libros_leyendo:
                if len(libros_leyendo) > 1:
                    libro_sel_idx = st.selectbox(
                        "📖 Seleccionar libro",
                        options=range(len(libros_leyendo)),
                        format_func=lambda i: (
                            f"{libros_leyendo[i]['titulo']} "
                            f"— pág. {libros_leyendo[i]['pagina_actual'] or 0}"
                        ),
                    )
                    libro_activo_sel = libros_leyendo[libro_sel_idx]
                else:
                    libro_activo_sel = libros_leyendo[0]
                pag_default = libro_activo_sel.get("pagina_actual") or 0
                total_pag   = libro_activo_sel.get("total_paginas") or 0
                pct_libro   = int(pag_default / total_pag * 100) if total_pag else 0
                st.success(
                    f"📖 **{libro_activo_sel['titulo']}** — "
                    f"pág. {pag_default} / {total_pag} ({pct_libro}%)"
                )
                st.progress(pct_libro / 100)
                libro_bit = f"{libro_activo_sel['titulo']} — {libro_activo_sel['autor'] or ''}"
            else:
                st.info("📚 No hay libros en lectura activa")
                libro_bit = st.text_input("Libro actual",
                    value=bit.get("libro_actual",""),
                    placeholder="Título del libro...")
            pag_bit = st.number_input("Página actual", min_value=0, step=1,
                value=int(bit.get("pagina_actual") or pag_default))
        with col_lib2:
            frase_bit = st.text_area("✨ Frase favorita de la semana",
                value=bit.get("frase_favorita",""), height=120,
                placeholder="La frase que más te impactó...")

        st.markdown("---")
        st.markdown("### 🌙 5. Vaciado Mental y Fricción Cero")
        st.caption("Domingo 20:30 — Soltar antes de dormir")
        col_vm1, col_vm2 = st.columns(2)
        with col_vm1:
            pendientes = st.text_area("📤 Pendientes para 'Soltar'",
                value=bit.get("pendientes_soltar",""), height=120,
                placeholder="Escribe todo lo que está en tu mente...")
        with col_vm2:
            reflexion = st.text_area("💭 Reflexión de la semana",
                value=bit.get("reflexion_semana",""), height=120,
                placeholder="¿Cómo fue la semana?\n¿Qué aprendiste?")

        guardar_bit = st.form_submit_button(
            "💾 Guardar bitácora", use_container_width=True, type="primary"
        )

    if guardar_bit:
        ok = guardar_bitacora({
            "semana_inicio":       lunes_bit_sel.isoformat(),
            "victoria_1":          v1,
            "victoria_2":          v2,
            "victoria_3":          v3,
            "ingreso_actual":      ingreso,
            "sobre_supervivencia": 1 if sobre_sup else 0,
            "aporte_transicion":   aporte_trans,
            "presupuesto_cita":    presup_cita,
            "semaforo_superv":     sem_sup,
            "semaforo_ahorros":    sem_aho,
            "semaforo_extras":     sem_ext,
            "gasto_pausado":       gasto_pausado,
            "actividad_cita":      act_cita,
            "costo_cita":          costo_cita,
            "libro_actual":        libro_bit,
            "pagina_actual":       pag_bit,
            "frase_favorita":      frase_bit,
            "pendientes_soltar":   pendientes,
            "reflexion_semana":    reflexion,
        })
        if ok:
            invalidate_data_caches()
            try:
                _eventos_semana_cached.clear()
            except Exception:
                pass
            st.success("✅ Bitácora guardada correctamente")
            st.rerun()

    eventos_bit = eventos_bit_auto

    # ── Datos automáticos ────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Datos automáticos de la semana")

    devos_bit = obtener_devocionales_semana(lunes_bit_sel, domingo_bit)
    dw_bit    = obtener_deepwork_semana(lunes_bit_sel, domingo_bit)
    salud_bit = obtener_salud_semana(lunes_bit_sel, domingo_bit)

    col_a1,col_a2,col_a3,col_a4,col_a5 = st.columns(5)
    col_a1.metric("✝️ Devocionales", f"{len(devos_bit)}/7",
        delta="✅" if len(devos_bit) >= 5 else "⚠️")
    col_a2.metric("⏱️ Deep Work",
        len([s for s in dw_bit if s.get("completado") == 1]))
    col_a3.metric("💪 Ejercicios",
        len([s for s in salud_bit if s.get("hizo_ejercicio")]))
    col_a4.metric("💑 Eventos", len(eventos_bit))
    prom_e = (
        sum(s.get("nivel_energia") or 0 for s in salud_bit) / len(salud_bit)
        if salud_bit else 0
    )
    col_a5.metric("⚡ Energía prom", f"{prom_e:.1f}/10" if prom_e else "—")

    st.markdown("**🔥 Rachas activas esta semana:**")
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("✝️ Racha devocional", f"{racha_dev_auto} días")
    col_r2.metric("💪 Racha ejercicio",  f"{racha_ej_auto} semanas")
    col_r3.metric("⏱️ Racha Deep Work",  f"{racha_dw_auto} días")

    if not sobres_data["sin_ingreso"]:
        st.markdown("**💰 Estado financiero automático:**")
        col_fa1,col_fa2,col_fa3,col_fa4 = st.columns(4)
        col_fa1.metric("Ingreso",       f"${sobres_data['ingreso']:,.0f}")
        col_fa2.metric("Gastado",       f"${sobres_data['total_gastado']:,.0f}",
            f"{sobres_data['pct_global']:.0f}%")
        col_fa3.metric("Supervivencia",
            f"{sobres_data['sobres']['Supervivencia']['pct_usado']:.0f}%",
            SEMAFOROS[semaforo_sup_auto])
        col_fa4.metric("Disponible",    f"${sobres_data['total_disponible']:,.0f}")

    # ── IA (fuera del form) ──────────────────────────────────
    st.markdown("---")
    col_gbtn, col_ia_btn = st.columns(2)
    with col_gbtn:
        st.caption("La bitácora se guarda con el botón del formulario de arriba.")

    with col_ia_btn:
        if st.button("🤖 Análisis completo IA", use_container_width=True,
                     type="primary", key="btn_ia_completo"):
            bitacoras_historial = obtener_bitacoras_recientes(8)
            dw_completados      = len([s for s in dw_bit if s.get("completado") == 1])
            victorias_txt       = [v for v in [v1, v2, v3] if v]

            historial_txt = ""
            if len(bitacoras_historial) > 1:
                historial_txt = "\nHISTORIAL ÚLTIMAS SEMANAS:\n"
                for b in bitacoras_historial[1:4]:
                    vs = [b.get(f"victoria_{i}","") for i in range(1,4)]
                    historial_txt += (
                        f"  {b['semana_inicio']}: "
                        f"{len([v for v in vs if v])} victorias | "
                        f"Semáforo: {b.get('semaforo_superv','?')}/"
                        f"{b.get('semaforo_ahorros','?')}/"
                        f"{b.get('semaforo_extras','?')}\n"
                    )
                    if b.get("reflexion_semana"):
                        historial_txt += f"  Reflexión: {b['reflexion_semana'][:80]}\n"

            prompt = f"""
Analiza esta bitácora semanal:

VICTORIAS PLANIFICADAS:
{chr(10).join(f'{i+1}. {v}' for i,v in enumerate(victorias_txt)) or 'No definidas'}

DATOS REALES:
- Devocionales: {len(devos_bit)}/7
- Deep Work: {dw_completados}
- Ejercicios: {len([s for s in salud_bit if s.get('hizo_ejercicio')])}
- Energía: {prom_e:.1f}/10
- Rachas: devocional {racha_dev_auto}d, ejercicio {racha_ej_auto}sem, DW {racha_dw_auto}d

FINANZAS:
- Ingreso: ${sobres_data['ingreso']:,.0f} | Gastado: ${sobres_data['total_gastado']:,.0f}
- Semáforo: Sup {sem_sup} | Ahorros {sem_aho} | Extras {sem_ext}

REFLEXIÓN: {reflexion or 'Sin reflexión aún'}
{historial_txt}

Responde en 4 secciones (máx 200 palabras total):
🏆 VICTORIAS: ¿Cuáles se lograron?
🔍 PATRÓN: Una observación del historial
⚖️ BALANCE: Lo más positivo y lo más preocupante
🚀 PRÓXIMA SEMANA: 2 acciones + versículo
"""
            with st.spinner("Analizando tu semana..."):
                st.info(chat_simple(prompt, contexto=SYSTEM_AGENDA))

# ═══════════════════════════════════════════════════════════════
# TAB 3: HISTORIAL
# ═══════════════════════════════════════════════════════════════

with tab_historial_bit:
    st.subheader("🗂️ Historial de bitácoras")

    bitacoras = obtener_bitacoras_recientes(12)

    if not bitacoras:
        st.info("📭 Sin bitácoras registradas aún")
    else:
        semanas_opciones = [b["semana_inicio"] for b in bitacoras]
        semana_sel = st.selectbox(
            "Seleccionar semana",
            options=semanas_opciones,
            format_func=lambda x: (
                f"Semana del {x} al "
                f"{(datetime.strptime(x,'%Y-%m-%d').date() + timedelta(days=6)).strftime('%d/%m/%Y')}"
            ),
            key="sel_semana_historial",
        )

        bit_sel = next((b for b in bitacoras if b["semana_inicio"] == semana_sel), None)

        if bit_sel:
            lun_sel = datetime.strptime(semana_sel, "%Y-%m-%d").date()
            dom_sel = lun_sel + timedelta(days=6)

            s_sup = SEMAFOROS.get(bit_sel.get("semaforo_superv",  "verde"), "🟢")
            s_aho = SEMAFOROS.get(bit_sel.get("semaforo_ahorros", "verde"), "🟢")
            s_ext = SEMAFOROS.get(bit_sel.get("semaforo_extras",  "verde"), "🟢")

            victorias_sel    = [bit_sel.get(f"victoria_{i}","") for i in range(1,4)]
            victorias_ok_sel = [v for v in victorias_sel if v]

            with st.expander("📋 Ver bitácora completa", expanded=False):
                col_hb1, col_hb2 = st.columns(2)
                with col_hb1:
                    st.markdown("**🏆 Victorias:**")
                    for i, v in enumerate(victorias_ok_sel, 1):
                        st.caption(f"{i}. {v}")
                    st.markdown("**💰 Financiero:**")
                    st.caption(
                        f"Ingreso: ${bit_sel.get('ingreso_actual') or 0:,.0f} · "
                        f"Sup: {s_sup} · Aho: {s_aho} · Ext: {s_ext}"
                    )
                    if bit_sel.get("actividad_cita"):
                        st.caption(f"💑 Cita: {bit_sel['actividad_cita']}")
                    if bit_sel.get("pendientes_soltar"):
                        st.markdown("**📤 Pendientes soltados:**")
                        st.caption(bit_sel["pendientes_soltar"][:200])
                with col_hb2:
                    if bit_sel.get("libro_actual"):
                        st.markdown("**📚 Lectura:**")
                        st.caption(
                            f"{bit_sel['libro_actual']} — "
                            f"pág. {bit_sel.get('pagina_actual') or 0}"
                        )
                    if bit_sel.get("frase_favorita"):
                        st.caption(f"✨ *{bit_sel['frase_favorita'][:150]}*")
                    if bit_sel.get("reflexion_semana"):
                        st.markdown("**💭 Reflexión:**")
                        st.caption(bit_sel["reflexion_semana"][:300])

            devos_sel   = obtener_devocionales_semana(lun_sel, dom_sel)
            dw_sel      = obtener_deepwork_semana(lun_sel, dom_sel)
            salud_sel   = obtener_salud_semana(lun_sel, dom_sel)
            eventos_sel = obtener_eventos_semana(lun_sel, dom_sel)

            dw_comp_sel = len([s for s in dw_sel if s.get("completado") == 1])
            ej_sel      = len([s for s in salud_sel if s.get("hizo_ejercicio")])
            prom_e_sel  = (
                sum(s.get("nivel_energia") or 0 for s in salud_sel) / len(salud_sel)
                if salud_sel else 0
            )

            st.markdown("**📊 Datos reales de esa semana:**")
            col_m1,col_m2,col_m3,col_m4,col_m5 = st.columns(5)
            col_m1.metric("✝️ Devocionales", f"{len(devos_sel)}/7")
            col_m2.metric("⏱️ Deep Work",    dw_comp_sel)
            col_m3.metric("💪 Ejercicios",   ej_sel)
            col_m4.metric("💑 Eventos",      len(eventos_sel))
            col_m5.metric("⚡ Energía",
                f"{prom_e_sel:.1f}/10" if prom_e_sel else "—")

            st.divider()
            st.markdown("### 🤖 Análisis IA de esta semana")
            if not api_key_configurada():
                st.warning("⚠️ IA en modo offline")

            def _ctx_semana_sel() -> str:
                vs = "\n".join(
                    f"  {i+1}. {v}" for i, v in enumerate(victorias_ok_sel)
                ) or "  No definidas"
                otras = [b for b in bitacoras if b["semana_inicio"] != semana_sel][:4]
                hist  = ""
                if otras:
                    hist = "\nHISTORIAL OTRAS SEMANAS:\n"
                    for b in otras:
                        vs_b = [b.get(f"victoria_{i}","") for i in range(1,4)]
                        hist += (
                            f"  {b['semana_inicio']}: "
                            f"{len([v for v in vs_b if v])} victorias | "
                            f"Semáforo {b.get('semaforo_superv','?')}/"
                            f"{b.get('semaforo_ahorros','?')}/"
                            f"{b.get('semaforo_extras','?')}\n"
                        )
                        if b.get("reflexion_semana"):
                            hist += f"  → {b['reflexion_semana'][:80]}\n"
                return f"""
SEMANA: {semana_sel} — {dom_sel.strftime('%d/%m/%Y')}
VICTORIAS:\n{vs}
DATOS: Devocionales {len(devos_sel)}/7 | DW {dw_comp_sel} | Ej {ej_sel} | Energía {prom_e_sel:.1f}/10
FINANZAS: ${bit_sel.get('ingreso_actual') or 0:,.0f} | Sup {bit_sel.get('semaforo_superv','?')} | Aho {bit_sel.get('semaforo_ahorros','?')} | Ext {bit_sel.get('semaforo_extras','?')}
REFLEXIÓN: {bit_sel.get('reflexion_semana') or 'Sin reflexión'}
{hist}"""

            col_ia1, col_ia2 = st.columns(2)
            with col_ia1:
                if st.button("🏆 Victorias vs Resultados",
                             use_container_width=True, key="btn_hist_victorias"):
                    with st.spinner("Analizando victorias..."):
                        st.info(chat_simple(
                            f"Evalúa victorias vs datos reales:\n{_ctx_semana_sel()}\n"
                            f"Para cada victoria: ✅/⚠️/❌. Máx 120 palabras.",
                            contexto=SYSTEM_AGENDA
                        ))

                if st.button("⚖️ Balance vida-fe-familia-finanzas",
                             use_container_width=True, key="btn_hist_balance"):
                    citas_mat_sel = len([e for e in eventos_sel if e.get("ambito") == "Matrimonio"])
                    with st.spinner("Analizando balance..."):
                        st.info(chat_simple(
                            f"Califica 1-10 cada área:\n"
                            f"✝️ FE: {len(devos_sel)}/7 | 💪 CUERPO: {ej_sel} ej, {prom_e_sel:.1f}/10\n"
                            f"💑 FAMILIA: {citas_mat_sel} citas | 💰 SUP:{bit_sel.get('semaforo_superv','?')}\n"
                            f"¿Qué área necesitaba más atención? Máx 120 palabras.",
                            contexto=SYSTEM_AGENDA
                        ))

            with col_ia2:
                if st.button("🔍 Patrones históricos",
                             use_container_width=True, key="btn_hist_patrones"):
                    if len(bitacoras) < 3:
                        st.warning("Necesitas al menos 3 semanas registradas.")
                    else:
                        with st.spinner("Detectando patrones..."):
                            st.info(chat_simple(
                                f"Detecta patrones:\n{_ctx_semana_sel()}\n"
                                f"1. ¿Qué funciona? 2. ¿Qué falla? 3. ¿Correlaciones? Máx 120 palabras.",
                                contexto=SYSTEM_AGENDA
                            ))

                if st.button("🚀 Sugerencias semana siguiente",
                             use_container_width=True, key="btn_hist_siguiente"):
                    semana_sig = lun_sel + timedelta(weeks=1)
                    with st.spinner("Planificando..."):
                        st.info(chat_simple(
                            f"Sugiere para {semana_sig.strftime('%d/%m/%Y')}:\n{_ctx_semana_sel()}\n"
                            f"1. 3 victorias 2. Hábito a reforzar 3. Alerta financiera 4. Versículo. Máx 150 palabras.",
                            contexto=SYSTEM_AGENDA
                        ))

            st.divider()
            if st.button("🤖 Análisis completo integrado",
                         use_container_width=True, type="primary",
                         key="btn_hist_completo"):
                with st.spinner("Generando análisis completo..."):
                    st.info(chat_simple(
                        f"Análisis ejecutivo:\n{_ctx_semana_sel()}\n"
                        f"4 secciones (máx 200 palabras):\n"
                        f"🏆 VICTORIAS 🔍 PATRÓN ⚖️ BALANCE 🚀 PRÓXIMA SEMANA + versículo",
                        contexto=SYSTEM_AGENDA
                    ))

        st.divider()
        st.markdown("### 📋 Todas las semanas")
        for b in bitacoras:
            lun_b = datetime.strptime(b["semana_inicio"], "%Y-%m-%d").date()
            dom_b = lun_b + timedelta(days=6)
            s_sup = SEMAFOROS.get(b.get("semaforo_superv",  "verde"), "🟢")
            s_aho = SEMAFOROS.get(b.get("semaforo_ahorros", "verde"), "🟢")
            s_ext = SEMAFOROS.get(b.get("semaforo_extras",  "verde"), "🟢")
            vs_ok = [v for v in [b.get(f"victoria_{i}","") for i in range(1,4)] if v]
            st.caption(
                f"📅 {lun_b.strftime('%d/%m')}—{dom_b.strftime('%d/%m/%Y')} · "
                f"💰 {s_sup}{s_aho}{s_ext} · 🏆 {len(vs_ok)} victorias · "
                f"{'📝 ' + b['reflexion_semana'][:60] + '...' if b.get('reflexion_semana') else '—'}"
            )

st.divider()
st.caption("📅 Agenda · Calendario unificado · Bitácora semanal · Abrir lunes 18:00")