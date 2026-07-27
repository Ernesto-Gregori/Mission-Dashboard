"""
💪 Salud y Energía - Correlación ejercicio-productividad
"""

import streamlit as st
from datetime import timedelta
import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import ejecutar, ejecutar_cached
from app.ai_client import chat_simple, api_key_configurada, probar_groq
from app.google_fit import (
    obtener_datos_dia,
    estado_google_fit,
    iniciar_oauth_local,
    guardar_token_desde_json,
)
from app.timezone_config import (
    date, datetime,
    hoy as _hoy,
    iso_ahora,
)

st.set_page_config(
    page_title="Salud | Mission Dashboard",
    page_icon="💪",
    layout="wide"
)

from app.auth import require_auth
require_auth()
ensure_database()

# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

SYSTEM_SALUD = """Eres un coach de salud cristiano para un estudiante de teología que 
también programa. Su rutina incluye: despertar 05:30, devocional 05:45, código 06:15, 
instituto 08:00-12:30, calistenia los miércoles 16:30. Eres práctico, motivador y 
consideras el cuerpo como templo del Espíritu Santo. Máximo 150 palabras."""

ZONAS_LISTA = [
    "Pecho", "Espalda", "Hombros", "Bíceps", "Tríceps",
    "Core/Abdomen", "Piernas", "Glúteos", "Cuerpo completo"
]
TIPOS_EJERCICIO = [
    "Calistenia", "Caminata", "Carrera", "Gimnasio",
    "Entrenamiento fuerza", "Yoga", "Ciclismo", "Natación", "Otro"
]
DIAS_NOMBRES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
DIAS_CORTOS  = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]


def _panel_reconectar_google():
    """UI para restaurar Google Fit sin perder el vínculo tras cada sleep."""
    st.markdown("#### 🔗 Restaurar / vincular Google Fit")
    st.caption(
        "En Streamlit Cloud el disco se borra al dormir. El token debe quedar en la "
        "**base de datos (Turso)** o en secrets con `refresh_token`."
    )

    tab_local, tab_pegar = st.tabs(["PC local (OAuth)", "Pegar token JSON"])

    with tab_local:
        st.caption(
            "Solo funciona si corres la app en tu computadora con "
            "`credentials_fit.json`. Luego el token se guarda en BD."
        )
        if st.button("🔗 Abrir OAuth en navegador", key="btn_oauth_fit"):
            with st.spinner("Esperando autorización de Google..."):
                ok, msg = iniciar_oauth_local()
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with tab_pegar:
        st.caption(
            "1) En local genera `token_fit.json` con OAuth. "
            "2) Copia TODO el JSON aquí. "
            "3) Guardar — queda en BD y sobrevive al sleep."
        )
        texto = st.text_area(
            "Contenido de token_fit.json",
            height=160,
            placeholder='{"token":"...","refresh_token":"...","client_id":"...", ...}',
            key="paste_fit_token",
        )
        if st.button("💾 Guardar token en BD", type="primary", key="btn_save_fit_token"):
            ok, msg = guardar_token_desde_json(texto)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DB
# ═══════════════════════════════════════════════════════════════

def guardar_registro_salud(fecha, datos: dict) -> None:
    """
    FIX Turso: fecha → str ISO, todos los numéricos → int/float,
    None se deja como None (Turso acepta NULL pero no objetos Python).
    """
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    zonas     = datos.get("zonas_musculares", [])
    sesiones  = datos.get("sesiones_json",    [])

    def _int(v):
        return int(v) if v is not None else None

    def _float(v):
        return float(v) if v is not None else None

    campos = [
        "fecha", "horas_sueno", "calidad_sueno", "hora_dormir", "hora_despertar",
        "energia_manana", "energia_tarde", "energia_noche",
        "hizo_ejercicio", "tipo_ejercicio", "duracion_minutos", "intensidad",
        "notas_ejercicio", "zonas_musculares", "sesiones_json",
        "calorias_fit", "pasos_fit", "fc_promedio_fit", "fc_maxima_fit",
        "fuente_datos", "productividad_percibida",
    ]
    valores = [
        fecha_iso,                                          # str
        _float(datos.get("horas_sueno")),
        _int(datos.get("calidad_sueno")),
        str(datos.get("hora_dormir")  or ""),
        str(datos.get("hora_despertar") or ""),
        _int(datos.get("energia_manana")),
        _int(datos.get("energia_tarde")),
        _int(datos.get("energia_noche")),
        1 if datos.get("hizo_ejercicio") else 0,            # int 0/1
        str(datos.get("tipo_ejercicio") or "") or None,
        _int(datos.get("duracion_minutos")),
        _int(datos.get("intensidad")),
        str(datos.get("notas_ejercicio") or "") or None,
        json.dumps(zonas)    if isinstance(zonas, list)    else zonas,
        json.dumps(sesiones) if isinstance(sesiones, list) else sesiones,
        _float(datos.get("calorias_fit")),
        _int(datos.get("pasos_fit")),
        _int(datos.get("fc_promedio_fit")),
        _int(datos.get("fc_maxima_fit")),
        str(datos.get("fuente_datos") or "manual"),
        _int(datos.get("productividad_percibida")),
    ]
    ejecutar(
        f"""INSERT OR REPLACE INTO registros_salud
            ({', '.join(campos)})
            VALUES ({', '.join(['?'] * len(valores))})""",
        valores,
    )


def obtener_registro_salud(fecha) -> dict | None:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    rows = ejecutar(
        "SELECT * FROM registros_salud WHERE fecha = ?",
        [fecha_iso], fetchall=True,
    )
    return rows[0] if rows else None


def obtener_registros_rango(dias: int = 14) -> list:
    fecha_desde = (_hoy() - timedelta(days=dias)).isoformat()  # ← local
    return ejecutar_cached("""
        SELECT * FROM registros_salud
        WHERE fecha >= ? ORDER BY fecha DESC
    """, (fecha_desde,)) or []


def calcular_promedios(registros: list) -> dict:
    if not registros:
        return {}

    def avg(key):
        vals = [r[key] for r in registros if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    dias_ejercicio = sum(1 for r in registros if r["hizo_ejercicio"])
    return {
        "total_dias":         len(registros),
        "dias_ejercicio":     dias_ejercicio,
        "pct_ejercicio":      dias_ejercicio / len(registros) * 100,
        "avg_energia_manana": avg("energia_manana"),
        "avg_energia_tarde":  avg("energia_tarde"),
        "avg_energia_noche":  avg("energia_noche"),
        "avg_sueno":          avg("horas_sueno"),
        "avg_calidad_sueno":  avg("calidad_sueno"),
        "avg_productividad":  avg("productividad_percibida"),
    }


def analizar_correlacion_simple(registros: list) -> tuple:
    if len(registros) < 4:
        return None, "Se necesitan al menos 4 días de datos"

    por_fecha    = {r["fecha"]: r for r in registros}
    ejercicio_si = []
    ejercicio_no = []

    for r in registros:
        fecha = datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        if fecha.weekday() == 2:
            jueves = (fecha + timedelta(days=1)).isoformat()
            if jueves in por_fecha and por_fecha[jueves]["productividad_percibida"]:
                target = por_fecha[jueves]["productividad_percibida"]
                (ejercicio_si if r["hizo_ejercicio"] else ejercicio_no).append(target)

    if not ejercicio_si or not ejercicio_no:
        return None, "Necesitas miércoles con y sin ejercicio para comparar"

    prom_con = sum(ejercicio_si) / len(ejercicio_si)
    prom_sin = sum(ejercicio_no) / len(ejercicio_no)
    diff     = prom_con - prom_sin
    return {
        "promedio_con_ejercicio": prom_con,
        "promedio_sin_ejercicio": prom_sin,
        "diferencia":             diff,
        "pct_mejora":             (diff / prom_sin * 100) if prom_sin > 0 else 0,
        "muestras_con":           len(ejercicio_si),
        "muestras_sin":           len(ejercicio_no),
    }, None


# ═══════════════════════════════════════════════════════════════
# HELPER IA
# ═══════════════════════════════════════════════════════════════

def _construir_contexto_completo(registros: list, stats: dict) -> str:
    if not registros or not stats:
        return "Sin datos de salud registrados aún."

    hoy_local = _hoy()   # ← local

    lineas = [
        f"Período: últimos {stats['total_dias']} días",
        f"Ejercicio: {stats['dias_ejercicio']}/{stats['total_dias']} días ({stats['pct_ejercicio']:.0f}%)",
        f"Sueño promedio: {stats['avg_sueno']:.1f}h (calidad: {stats['avg_calidad_sueno']:.1f}/10)",
        f"Energía mañana: {stats['avg_energia_manana']:.1f}/10",
        f"Energía tarde:  {stats['avg_energia_tarde']:.1f}/10",
        f"Productividad:  {stats['avg_productividad']:.1f}/10",
    ]

    conteo_zonas = {z: 0 for z in ZONAS_LISTA}
    for r in registros:
        notas = r.get("notas_ejercicio") or ""
        for zona in ZONAS_LISTA:
            if zona in notas:
                conteo_zonas[zona] += 1

    zonas_activas = {k: v for k, v in conteo_zonas.items() if v > 0}
    if zonas_activas:
        lineas.append("Zonas trabajadas: " + ", ".join(
            f"{k}({v}x)" for k, v in
            sorted(zonas_activas.items(), key=lambda x: -x[1])
        ))
        sin_trabajar = [z for z in ZONAS_LISTA
                        if z not in zonas_activas and z != "Cuerpo completo"]
        if sin_trabajar:
            lineas.append(f"Zonas sin trabajar: {', '.join(sin_trabajar)}")

    inicio_sem = hoy_local - timedelta(days=hoy_local.weekday())
    inicio_ant = inicio_sem - timedelta(days=7)
    sem_act    = [r for r in registros if r["fecha"] >= inicio_sem.isoformat()]
    sem_ant    = [r for r in registros
                  if inicio_ant.isoformat() <= r["fecha"] < inicio_sem.isoformat()]
    if sem_act and sem_ant:
        sa = calcular_promedios(sem_act)
        an = calcular_promedios(sem_ant)
        lineas.append(
            f"Semana actual vs anterior: "
            f"productividad {sa['avg_productividad'] - an['avg_productividad']:+.1f}, "
            f"sueño {sa['avg_sueno'] - an['avg_sueno']:+.1f}h"
        )

    suenos = [r["horas_sueno"] for r in registros if r.get("horas_sueno")]
    if suenos:
        lineas.append(
            f"Noches con <7h sueño: {sum(1 for s in suenos if s < 7)}/{len(suenos)}"
        )

    for r in registros[:3]:
        ej    = (f"✓ {r.get('tipo_ejercicio','ejercicio')} {r.get('duracion_minutos',0)}min"
                 if r["hizo_ejercicio"] else "✗ sin ejercicio")
        notas = r.get("notas_ejercicio") or ""
        zonas_hoy = [z for z in ZONAS_LISTA if z in notas]
        z_str     = f" [{', '.join(zonas_hoy)}]" if zonas_hoy else ""
        lineas.append(
            f"  {r['fecha']}: {ej}{z_str}, "
            f"sueño {r.get('horas_sueno') or '-'}h, "
            f"energía {r.get('energia_manana') or '-'}/10, "
            f"productividad {r.get('productividad_percibida') or '-'}/10"
        )

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.title("💪 Salud y Energía")
st.caption("Correlación ejercicio-productividad • Calistenia miércoles 16:30")

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📊 Tu semana")
    stats_semana = calcular_promedios(obtener_registros_rango(7))

    if stats_semana:
        col1, col2 = st.columns(2)
        col1.metric("Ejercicios",     f"{stats_semana['dias_ejercicio']}/7")
        col2.metric("Energía mañana", f"{stats_semana['avg_energia_manana']:.1f}/10")
        st.progress(stats_semana["avg_energia_manana"] / 10, text="Energía promedio")
        st.metric("Sueño promedio",   f"{stats_semana['avg_sueno']:.1f}h")
        st.metric("Productividad",    f"{stats_semana['avg_productividad']:.1f}/10")
    else:
        st.info("📝 Comienza a registrar hoy")

    st.divider()
    if api_key_configurada():
        st.success("🤖 Coach IA (Groq) activo")
    else:
        st.caption("🤖 Coach IA offline — falta GROQ_API_KEY")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════

tab_hoy, tab_historial, tab_analisis, tab_ia = st.tabs([
    "📋 Hoy", "📈 Historial", "🔬 Análisis", "🤖 Coach IA"
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: HOY
# ═══════════════════════════════════════════════════════════════

with tab_hoy:
    fecha_hoy  = _hoy()                        # ← zona horaria local
    dia_semana = fecha_hoy.weekday()

    st.subheader(f"{DIAS_NOMBRES[dia_semana]} {fecha_hoy.strftime('%d/%m/%Y')}")

    if dia_semana == 2:
        st.info("🏋️ **Miércoles de Calistenia** • 16:30 - 18:30")

    # ── Google Fit (token en BD para sobrevivir al sleep) ─────
    fit_st = estado_google_fit()
    if fit_st["autenticado"]:
        col_fit1, col_fit2, col_fit3 = st.columns([2.5, 1, 1])
        with col_fit1:
            donde = []
            if fit_st["en_bd"]:
                donde.append("BD")
            if fit_st["en_secrets"]:
                donde.append("secrets")
            if fit_st["en_disco"]:
                donde.append("disco")
            st.success(
                "✅ Google Fit conectado"
                + (f" · token en {'+'.join(donde)}" if donde else "")
            )
        with col_fit2:
            if st.button("🔄 Importar hoy", use_container_width=True):
                with st.spinner("Obteniendo datos de Google Fit..."):
                    datos_imp = obtener_datos_dia(fecha_hoy)
                    st.session_state["datos_fit_hoy"] = datos_imp
                    st.session_state["fit_fecha"] = fecha_hoy.isoformat()
                    st.rerun()
        with col_fit3:
            with st.popover("⚙️ Token"):
                st.caption(
                    "Si la app se duerme, el token debe estar en la **BD** "
                    "(Turso) o en secrets con refresh_token."
                )
                _panel_reconectar_google()
    else:
        st.warning("🔑 Google Fit no autenticado — hay que vincular / restaurar token")
        if fit_st["error"]:
            st.error(fit_st["error"])
        _panel_reconectar_google()

    fit = {}
    if (st.session_state.get("fit_fecha") == fecha_hoy.isoformat()
            and "datos_fit_hoy" in st.session_state):
        fit = st.session_state["datos_fit_hoy"]
        if "error" not in fit:
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("😴 Sueño",     f"{fit.get('horas_sueno') or '-'}h")
            col_b.metric("🏋️ Ejercicio", f"{fit.get('duracion_minutos') or 0} min")
            col_c.metric("👟 Pasos",     f"{fit.get('pasos') or 0:,}")
            col_d.metric("❤️ FC prom.",  f"{fit.get('fc_promedio') or '-'} bpm")
            sesiones = fit.get("sesiones_fit", [])
            if sesiones:
                st.caption("Sesiones detectadas: " +
                    " • ".join(f"{s['tipo']} ({s['duracion_min']} min)"
                               for s in sesiones))

    st.divider()
    st.markdown("### ✏️ Editar y completar registro")

    reg = obtener_registro_salud(fecha_hoy) or {}

    def val(campo, default):
        if reg.get(campo) is not None:
            return reg[campo]
        if fit.get(campo) is not None:
            return fit[campo]
        return default

    # ── Sueño ─────────────────────────────────────────────────
    with st.expander("😴 Sueño", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            hora_dormir_str = val("hora_dormir", "22:00")
            if not isinstance(hora_dormir_str, str) or not hora_dormir_str:
                hora_dormir_str = "22:00"
            hora_dormir = st.time_input(
                "Hora de dormir",
                value=datetime.strptime(hora_dormir_str, "%H:%M").time(),
                key="td_dormir"
            )
            hora_despertar_str = val("hora_despertar", "05:30")
            if not isinstance(hora_despertar_str, str) or not hora_despertar_str:
                hora_despertar_str = "05:30"
            hora_despertar = st.time_input(
                "Hora de despertar",
                value=datetime.strptime(hora_despertar_str, "%H:%M").time(),
                key="td_despertar"
            )
            horas_fit = val("horas_sueno", None)
            if horas_fit:
                horas_sueno = float(horas_fit)
                st.metric("Horas dormidas (Google Fit)", f"{horas_sueno:.1f}h")
                st.caption("⚡ Dato real de Google Fit")
            else:
                # combine usa date objects — _hoy() devuelve date compatible
                dormir    = datetime.combine(fecha_hoy, hora_dormir)
                despertar = datetime.combine(
                    fecha_hoy + timedelta(days=1), hora_despertar
                )
                horas_sueno = (despertar - dormir).total_seconds() / 3600
                st.metric("Horas dormidas (calculado)", f"{horas_sueno:.1f}h")
        with col2:
            calidad_sueno = st.slider(
                "Calidad del sueño", 1, 10,
                int(val("calidad_sueno", 7)),
                key="sl_calidad_sueno"
            )

    # ── Energía ───────────────────────────────────────────────
    with st.expander("⚡ Energía del día", expanded=True):
        st.caption("Solo tú puedes registrar esto — Google Fit no lo mide")
        col3, col4, col5 = st.columns(3)
        with col3:
            energia_manana = st.slider("Mañana (05:45)", 1, 10,
                int(val("energia_manana", 7)), key="sl_e_man")
        with col4:
            energia_tarde  = st.slider("Tarde (14:00)", 1, 10,
                int(val("energia_tarde",  6)), key="sl_e_tar")
        with col5:
            energia_noche  = st.slider("Noche (21:00)", 1, 10,
                int(val("energia_noche",  5)), key="sl_e_noc")

    # ── Ejercicio ─────────────────────────────────────────────
    with st.expander("🏋️ Ejercicio", expanded=True):
        hizo_ejercicio = st.checkbox(
            "¿Hiciste ejercicio hoy?",
            value=bool(val("hizo_ejercicio", dia_semana == 2)),
            key="cb_ejercicio"
        )
        sesiones_ejercicio = []

        if hizo_ejercicio:
            sesiones_fit = fit.get("sesiones_fit", [])
            n_def        = max(1, len(sesiones_fit))

            if "n_sesiones" not in st.session_state:
                st.session_state.n_sesiones = n_def

            col_ns1, col_ns2, col_ns3 = st.columns([2, 1, 1])
            with col_ns1:
                st.caption(f"Sesiones: {st.session_state.n_sesiones}")
            with col_ns2:
                if st.button("➕ Agregar sesión", key="btn_add_sesion"):
                    st.session_state.n_sesiones += 1
                    st.rerun()
            with col_ns3:
                if st.session_state.n_sesiones > 1:
                    if st.button("➖ Quitar", key="btn_rm_sesion"):
                        st.session_state.n_sesiones -= 1
                        st.rerun()

            for i in range(st.session_state.n_sesiones):
                st.markdown(f"**Sesión {i + 1}**")
                fit_s = sesiones_fit[i] if i < len(sesiones_fit) else {}

                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    tipo_def  = fit_s.get("tipo", "Calistenia")
                    idx_tipo  = (TIPOS_EJERCICIO.index(tipo_def)
                                 if tipo_def in TIPOS_EJERCICIO else 0)
                    tipo      = st.selectbox("Tipo", TIPOS_EJERCICIO,
                                             index=idx_tipo, key=f"tipo_s{i}")
                    duracion  = st.number_input("Duración (min)",
                                                min_value=5, max_value=240,
                                                value=int(fit_s.get("duracion_min", 60)),
                                                step=5, key=f"dur_s{i}")
                    intensidad = st.slider("Intensidad", 1, 10, 5, key=f"int_s{i}")
                with col_s2:
                    zonas   = st.multiselect("Zona muscular", ZONAS_LISTA,
                                             default=[], key=f"zona_s{i}")
                    notas_s = st.text_area("Notas de la sesión",
                                           placeholder="Series, reps...",
                                           height=100, key=f"notas_s{i}")

                sesiones_ejercicio.append({
                    "tipo": tipo, "duracion": int(duracion),
                    "intensidad": int(intensidad),
                    "zonas": zonas, "notas": notas_s,
                })
                if i < st.session_state.n_sesiones - 1:
                    st.divider()

            if fit.get("calorias"):
                st.caption(f"🔥 Calorías (Google Fit): {fit['calorias']} kcal")
            if fit.get("fc_maxima"):
                st.caption(f"❤️ FC máxima: {fit['fc_maxima']} bpm")
            if fit.get("pasos"):
                st.caption(f"👟 Pasos: {fit['pasos']:,}")

    # ── Productividad ─────────────────────────────────────────
    with st.expander("📈 Productividad", expanded=True):
        productividad = st.slider(
            "Productividad percibida hoy", 1, 10,
            int(val("productividad_percibida", 6)), key="sl_prod"
        )
        st.caption("💡 Este dato se correlaciona con tu sueño y ejercicio")

    # ── Guardar ───────────────────────────────────────────────
    st.divider()
    if st.button("💾 Guardar registro del día",
                 use_container_width=True, type="primary"):

        if hizo_ejercicio and sesiones_ejercicio:
            tipo_principal      = sesiones_ejercicio[0]["tipo"]
            duracion_total      = sum(s["duracion"]   for s in sesiones_ejercicio)
            intensidad_promedio = round(
                sum(s["intensidad"] for s in sesiones_ejercicio) /
                len(sesiones_ejercicio)
            )
            todas_zonas = list({z for s in sesiones_ejercicio for z in s["zonas"]})
            partes      = []
            for i, s in enumerate(sesiones_ejercicio, 1):
                p = f"Sesión {i}: {s['tipo']} {s['duracion']}min"
                if s["zonas"]:  p += f" | Zonas: {', '.join(s['zonas'])}"
                if s["notas"]:  p += f" | {s['notas']}"
                partes.append(p)
            notas_consolidadas = " || ".join(partes)
        else:
            tipo_principal = duracion_total = intensidad_promedio = None
            todas_zonas    = []
            notas_consolidadas = ""

        guardar_registro_salud(fecha_hoy, {
            "horas_sueno":             round(horas_sueno, 1),
            "calidad_sueno":           calidad_sueno,
            "hora_dormir":             hora_dormir.strftime("%H:%M"),
            "hora_despertar":          hora_despertar.strftime("%H:%M"),
            "energia_manana":          energia_manana,
            "energia_tarde":           energia_tarde,
            "energia_noche":           energia_noche,
            "hizo_ejercicio":          1 if hizo_ejercicio else 0,
            "tipo_ejercicio":          tipo_principal,
            "duracion_minutos":        duracion_total,
            "intensidad":              intensidad_promedio,
            "notas_ejercicio":         notas_consolidadas,
            "zonas_musculares":        todas_zonas,
            "sesiones_json":           sesiones_ejercicio,
            "calorias_fit":            fit.get("calorias")    if fit else None,
            "pasos_fit":               fit.get("pasos")       if fit else None,
            "fc_promedio_fit":         fit.get("fc_promedio") if fit else None,
            "fc_maxima_fit":           fit.get("fc_maxima")   if fit else None,
            "fuente_datos":            "mixto" if fit else "manual",
            "productividad_percibida": productividad,
        })
        st.session_state.pop("n_sesiones", None)
        st.success("✅ Registro guardado. ¡Tu cuerpo es templo del Espíritu!")
        st.balloons()

# ═══════════════════════════════════════════════════════════════
# TAB 2: HISTORIAL
# ═══════════════════════════════════════════════════════════════

with tab_historial:
    st.subheader("📈 Historial de salud")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        dias_historial = st.selectbox("Período", [7,14,30,60],
            format_func=lambda x: f"Últimos {x} días", index=1)
    with col_f2:
        filtro_ejercicio = st.selectbox("Ejercicio",
            ["Todos","Con ejercicio","Sin ejercicio"])
    with col_f3:
        filtro_zona = st.selectbox("Zona muscular",
            ["Todas"] + ZONAS_LISTA)

    registros = obtener_registros_rango(dias_historial)

    if filtro_ejercicio == "Con ejercicio":
        registros = [r for r in registros if r["hizo_ejercicio"]]
    elif filtro_ejercicio == "Sin ejercicio":
        registros = [r for r in registros if not r["hizo_ejercicio"]]
    if filtro_zona != "Todas":
        registros = [r for r in registros
                     if filtro_zona in (r.get("notas_ejercicio") or "")]

    if not registros:
        st.info("📭 No hay registros con estos filtros.")
    else:
        import pandas as pd

        st.markdown("### 📊 Tendencias")
        df = pd.DataFrame([{
            "Fecha":          r["fecha"],
            "Sueño (h)":      r["horas_sueno"] or 0,
            "Energía mañana": r["energia_manana"] or 0,
            "Energía tarde":  r["energia_tarde"]  or 0,
            "Productividad":  r["productividad_percibida"] or 0,
            "Ejercicio":      10 if r["hizo_ejercicio"] else 0,
        } for r in reversed(registros)])

        tab_g1, tab_g2, tab_g3 = st.tabs(
            ["😴 Sueño","⚡ Energía","📈 Productividad"]
        )
        with tab_g1:
            st.line_chart(df.set_index("Fecha")[["Sueño (h)"]])
            prom = df["Sueño (h)"].mean()
            c    = "🟢" if prom >= 7 else "🟡" if prom >= 6 else "🔴"
            st.caption(
                f"{c} Promedio: {prom:.1f}h — "
                f"{'Óptimo' if prom>=7 else 'Mejorable' if prom>=6 else 'Insuficiente'}"
            )
        with tab_g2:
            st.line_chart(df.set_index("Fecha")[["Energía mañana","Energía tarde"]])
        with tab_g3:
            st.line_chart(df.set_index("Fecha")[["Productividad"]])
            dias_ej = [r["fecha"] for r in registros if r["hizo_ejercicio"]]
            if dias_ej:
                st.caption(f"🏋️ Días con ejercicio: {', '.join(dias_ej[-5:])}")

        st.divider()
        st.markdown("### 📋 Detalle por día")

        for r in registros:
            fecha_r = datetime.strptime(r["fecha"], "%Y-%m-%d").date()
            dia_n   = DIAS_CORTOS[fecha_r.weekday()]
            sueno   = r["horas_sueno"]
            color_s = "🟢" if sueno and sueno >= 7 else "🟡" if sueno and sueno >= 6 else "🔴"

            col_d1,col_d2,col_d3,col_d4,col_d5 = st.columns([1,2,2,2,2])
            with col_d1:
                st.markdown(f"**{dia_n}**  \n{fecha_r.strftime('%d/%m')}")
            with col_d2:
                st.metric("Ejercicio", "🏋️" if r["hizo_ejercicio"] else "❌")
            with col_d3:
                st.metric("Sueño",
                    f"{color_s} {sueno:.1f}h" if sueno else "-")
            with col_d4:
                st.metric("Energía", f"{r['energia_manana'] or '-'}/10")
            with col_d5:
                st.metric("Productividad",
                    f"{r['productividad_percibida'] or '-'}/10")

            if r["hizo_ejercicio"] or r.get("notas_ejercicio"):
                with st.expander("Ver detalle"):
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        if r["hizo_ejercicio"]:
                            st.markdown("**🏋️ Ejercicio:**")
                            st.write(f"Tipo: {r.get('tipo_ejercicio') or '-'}")
                            st.write(f"Duración: {r.get('duracion_minutos') or '-'} min")
                            st.write(f"Intensidad: {r.get('intensidad') or '-'}/10")
                            notas = r.get("notas_ejercicio") or ""
                            if "||" in notas:
                                st.markdown("**Sesiones:**")
                                for s in notas.split("||"):
                                    st.caption(f"• {s.strip()}")
                            elif notas:
                                st.caption(f"📝 {notas}")
                    with col_det2:
                        st.markdown("**😴 Sueño:**")
                        st.write(f"Horas: {r.get('horas_sueno') or '-'}h")
                        st.write(f"Calidad: {r.get('calidad_sueno') or '-'}/10")
                        st.write(f"Dormir: {r.get('hora_dormir') or '-'}")
                        st.write(f"Despertar: {r.get('hora_despertar') or '-'}")
                        st.markdown("**⚡ Energía:**")
                        st.write(f"Mañana: {r.get('energia_manana') or '-'}/10")
                        st.write(f"Tarde: {r.get('energia_tarde') or '-'}/10")
                        st.write(f"Noche: {r.get('energia_noche') or '-'}/10")

            st.divider()

# ═══════════════════════════════════════════════════════════════
# TAB 3: ANÁLISIS
# ═══════════════════════════════════════════════════════════════

with tab_analisis:
    st.subheader("🔬 Análisis de patrones de salud")
    registros_30 = obtener_registros_rango(30)

    if len(registros_30) < 4:
        st.info("📊 Necesitas al menos 4 días de datos para ver análisis.")
    else:
        import pandas as pd

        df_an = pd.DataFrame([{
            "fecha":              r["fecha"],
            "dia_semana":         datetime.strptime(r["fecha"], "%Y-%m-%d").weekday(),
            "horas_sueno":        r["horas_sueno"] or 0,
            "calidad_sueno":      r["calidad_sueno"] or 0,
            "energia_manana":     r["energia_manana"] or 0,
            "energia_tarde":      r["energia_tarde"]  or 0,
            "productividad":      r["productividad_percibida"] or 0,
            "hizo_ejercicio":     bool(r["hizo_ejercicio"]),
            "duracion_ejercicio": r["duracion_minutos"] or 0,
            "notas":              r.get("notas_ejercicio") or "",
        } for r in registros_30])

        # 1. Correlación ejercicio → productividad
        st.markdown("### 🏋️ Correlación ejercicio → productividad")
        resultado, error = analizar_correlacion_simple(registros_30)

        if error:
            st.warning(f"⚠️ {error}")
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Con ejercicio",
                f"{resultado['promedio_con_ejercicio']:.1f}/10")
            col2.metric("Sin ejercicio",
                f"{resultado['promedio_sin_ejercicio']:.1f}/10")
            with col3:
                color = "#3fb950" if resultado["diferencia"] > 0 else "#f85149"
                st.markdown(f"""
<div style="text-align:center;">
    <div style="font-size:2rem;color:{color};font-weight:bold;">
        {resultado['pct_mejora']:+.0f}%
    </div>
    <div style="font-size:0.875rem;color:#8b949e;">impacto en productividad</div>
</div>""", unsafe_allow_html=True)

            if resultado["diferencia"] > 1:
                st.success(
                    f"✅ Confirmado: ejercicio mejora tu productividad "
                    f"{resultado['pct_mejora']:.0f}%"
                )
            elif resultado["diferencia"] > 0:
                st.info("📈 Tendencia positiva — sigue registrando para confirmar")
            else:
                st.warning("⚠️ Sin mejora detectada aún — ¿estás durmiendo suficiente?")

        st.divider()

        # 2. Correlación sueño → energía
        st.markdown("### 😴 Correlación sueño → energía mañana")
        df_sueno = df_an[df_an["horas_sueno"] > 0].copy()

        if len(df_sueno) >= 4:
            s_bueno = df_sueno[df_sueno["horas_sueno"] >= 7]["energia_manana"].mean()
            s_malo  = df_sueno[df_sueno["horas_sueno"] <  7]["energia_manana"].mean()

            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("Energía con ≥7h",
                f"{s_bueno:.1f}/10" if not pd.isna(s_bueno) else "Sin datos")
            col_s2.metric("Energía con <7h",
                f"{s_malo:.1f}/10"  if not pd.isna(s_malo)  else "Sin datos")
            if not pd.isna(s_bueno) and not pd.isna(s_malo):
                dif_s = s_bueno - s_malo
                col_s3.metric("Diferencia", f"{dif_s:+.1f} pts",
                    delta_color="normal" if dif_s > 0 else "inverse")
                df_sueno = df_sueno.copy()
                df_sueno["cat"] = df_sueno["horas_sueno"].apply(
                    lambda x: "≥7h (óptimo)" if x >= 7 else "<7h (insuficiente)"
                )
                st.bar_chart(df_sueno.groupby("cat")["energia_manana"].mean())
        else:
            st.info("Necesitas más datos de sueño para este análisis.")

        st.divider()

        # 3. Patrón semanal
        st.markdown("### 📅 Patrón semanal — ¿Qué día tienes más energía?")
        patron = df_an.groupby("dia_semana").agg({
            "energia_manana": "mean",
            "productividad":  "mean",
            "horas_sueno":    "mean",
        }).round(1)
        patron.index = [DIAS_CORTOS[i] for i in patron.index]

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown("**Energía por día:**")
            st.bar_chart(patron["energia_manana"])
        with col_p2:
            st.markdown("**Productividad por día:**")
            st.bar_chart(patron["productividad"])

        if not patron.empty:
            mejor = patron["energia_manana"].idxmax()
            peor  = patron["energia_manana"].idxmin()
            st.success(
                f"🌟 Mejor día: **{mejor}** "
                f"({patron.loc[mejor,'energia_manana']:.1f}/10)"
            )
            st.warning(
                f"⚠️ Peor día: **{peor}** "
                f"({patron.loc[peor,'energia_manana']:.1f}/10) — ¿Qué pasa ese día?"
            )

        st.divider()

        # 4. Zonas musculares
        st.markdown("### 💪 Zonas musculares más trabajadas")
        conteo_zonas = {z: 0 for z in ZONAS_LISTA}
        for r in registros_30:
            notas = r.get("notas_ejercicio") or ""
            for zona in ZONAS_LISTA:
                if zona in notas:
                    conteo_zonas[zona] += 1

        zonas_trabajadas = {k: v for k, v in conteo_zonas.items() if v > 0}
        if zonas_trabajadas:
            df_z = pd.DataFrame(
                list(zonas_trabajadas.items()), columns=["Zona","Sesiones"]
            ).sort_values("Sesiones", ascending=False)
            st.bar_chart(df_z.set_index("Zona"))
            st.success(f"💪 Zona más trabajada: **{df_z.iloc[0]['Zona']}**")
            if len(df_z) > 1:
                st.info(
                    f"⚖️ Zona menos trabajada: "
                    f"**{df_z.iloc[-1]['Zona']}** — considera balancear"
                )
            sin_trabajar = [z for z in ZONAS_LISTA
                            if z not in zonas_trabajadas and z != "Cuerpo completo"]
            if sin_trabajar:
                st.warning(f"🔴 Sin trabajar este mes: {', '.join(sin_trabajar)}")
        else:
            st.info("📝 Registra zonas musculares para ver este análisis.")

        st.divider()

        # 5. Tendencia productividad
        st.markdown("### 📈 Tendencia de productividad")
        df_prod = df_an[df_an["productividad"] > 0].copy()
        if len(df_prod) >= 3:
            st.line_chart(df_prod.set_index("fecha")[["productividad"]])

            hoy_an  = _hoy()                                # ← local
            ini_sem = hoy_an - timedelta(days=hoy_an.weekday())
            ini_ant = ini_sem - timedelta(days=7)
            p_act   = df_an[df_an["fecha"] >= ini_sem.isoformat()]["productividad"].mean()
            p_ant   = df_an[
                (df_an["fecha"] >= ini_ant.isoformat()) &
                (df_an["fecha"] <  ini_sem.isoformat())
            ]["productividad"].mean()

            if not pd.isna(p_act) and not pd.isna(p_ant):
                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric("Esta semana",     f"{p_act:.1f}/10")
                col_p2.metric("Semana anterior", f"{p_ant:.1f}/10")
                delta = p_act - p_ant
                col_p3.metric("Cambio", f"{delta:+.1f}",
                    delta_color="normal" if delta >= 0 else "inverse")

# ═══════════════════════════════════════════════════════════════
# TAB 4: COACH IA
# ═══════════════════════════════════════════════════════════════

with tab_ia:
    st.subheader("🤖 Coach de Salud IA")

    if not api_key_configurada():
        st.warning("⚠️ IA en modo offline — respuestas predefinidas disponibles.")

    registros_ia      = obtener_registros_rango(14)
    stats_ia          = calcular_promedios(registros_ia)
    resultado_corr, _ = analizar_correlacion_simple(obtener_registros_rango(30))
    contexto          = _construir_contexto_completo(registros_ia, stats_ia)

    if stats_ia:
        col1,col2,col3,col4 = st.columns(4)
        col1.metric("Ejercicios",
            f"{stats_ia['dias_ejercicio']}/{stats_ia['total_dias']}")
        col2.metric("Energía prom.", f"{stats_ia['avg_energia_manana']:.1f}/10")
        col3.metric("Sueño prom.",   f"{stats_ia['avg_sueno']:.1f}h")
        col4.metric("Productividad", f"{stats_ia['avg_productividad']:.1f}/10")

    # Comparativa semanas
    hoy_ia     = _hoy()                                     # ← local
    ini_sem_ia = hoy_ia - timedelta(days=hoy_ia.weekday())
    ini_ant_ia = ini_sem_ia - timedelta(days=7)
    sem_act    = [r for r in registros_ia
                  if r["fecha"] >= ini_sem_ia.isoformat()]
    sem_ant    = [r for r in registros_ia
                  if ini_ant_ia.isoformat() <= r["fecha"] < ini_sem_ia.isoformat()]

    if sem_act and sem_ant:
        st.markdown("#### 📊 Esta semana vs semana anterior")
        sa = calcular_promedios(sem_act)
        an = calcular_promedios(sem_ant)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Productividad",  f"{sa['avg_productividad']:.1f}",
            f"{sa['avg_productividad'] - an['avg_productividad']:+.1f}")
        c2.metric("Sueño",          f"{sa['avg_sueno']:.1f}h",
            f"{sa['avg_sueno'] - an['avg_sueno']:+.1f}h")
        c3.metric("Energía mañana", f"{sa['avg_energia_manana']:.1f}",
            f"{sa['avg_energia_manana'] - an['avg_energia_manana']:+.1f}")
        c4.metric("Ejercicios",     f"{sa['dias_ejercicio']}",
            f"{sa['dias_ejercicio'] - an['dias_ejercicio']:+d}")

    st.divider()

    # Resumen semanal
    st.markdown("### 📊 Resumen semanal con insights")
    if st.button("🤖 Generar resumen semanal", key="btn_resumen",
                 use_container_width=True):
        with st.spinner("Generando resumen..."):
            st.info(chat_simple(
                f"Genera un resumen semanal de salud con insights accionables.\n\n"
                f"{contexto}\n\n"
                f"Incluye:\n"
                f"1. Victoria más importante\n"
                f"2. Área de mejora con acción concreta\n"
                f"3. Observación sobre balance muscular\n"
                f"4. Versículo motivador sobre el cuerpo",
                contexto=SYSTEM_SALUD
            ))

    st.divider()

    # Correlación
    st.markdown("### 🔬 Análisis de correlación con IA")
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        tipo_corr = st.selectbox("¿Qué correlación analizar?", [
            "Ejercicio → Productividad del día siguiente",
            "Sueño → Energía mañana",
            "Calidad sueño → Productividad",
            "Energía mañana → Productividad",
            "Patrón general de la semana",
            "Semana actual vs semana anterior",
        ], key="sel_correlacion")
    with col_c2:
        if st.button("🔬 Analizar correlación", key="btn_corr",
                     use_container_width=True):
            extra = ""
            if resultado_corr:
                extra = (
                    f"Correlación ejercicio-productividad calculada:\n"
                    f"- Con ejercicio: {resultado_corr['promedio_con_ejercicio']:.1f}/10\n"
                    f"- Sin ejercicio: {resultado_corr['promedio_sin_ejercicio']:.1f}/10\n"
                    f"- Impacto: {resultado_corr['pct_mejora']:+.0f}%"
                )
            with st.spinner("Analizando..."):
                st.info(chat_simple(
                    f"Analiza: {tipo_corr}\n\nDatos:\n{contexto}\n\n{extra}\n\n"
                    f"Da 2-3 observaciones con números y 1 recomendación accionable.",
                    contexto=SYSTEM_SALUD
                ))

    st.divider()

    # Recuperación
    st.markdown("### 💪 Recuperación y balance muscular")
    col_r1, col_r2 = st.columns([1, 2])
    with col_r1:
        tipo_rec = st.selectbox("¿Qué necesitas?", [
            "Plan de recuperación según zonas trabajadas",
            "¿Qué zona trabajar hoy para balancear?",
            "Señales de sobreentrenamiento",
            "Rutina de movilidad entre sesiones",
        ], key="sel_recuperacion")
    with col_r2:
        if st.button("💪 Consejo de recuperación", key="btn_rec",
                     use_container_width=True):
            with st.spinner("Analizando recuperación..."):
                st.info(chat_simple(
                    f"Solicitud: {tipo_rec}\n\nHistorial:\n{contexto}\n\n"
                    f"Considera: calistenia miércoles 16:30, "
                    f"instituto lun-vie 08:00-12:30.",
                    contexto=SYSTEM_SALUD
                ))

    st.divider()

    # Sueño
    st.markdown("### 😴 Recomendaciones de sueño y energía")
    col_s1, col_s2 = st.columns([1, 2])
    with col_s1:
        prob_sueno = st.selectbox("¿Cuál es tu situación?", [
            "Me cuesta despertar a las 05:30",
            "Energía baja en la tarde",
            "Sueño de mala calidad",
            "Me duermo tarde (>23:00)",
            "Energía inconsistente durante la semana",
        ], key="sel_sueno")
        hora_dormir_ia = st.time_input(
            "¿A qué hora te duermes normalmente?",
            value=datetime.strptime("22:30", "%H:%M").time(),
            key="ti_dormir"
        )
        if stats_ia.get("avg_sueno"):
            st.metric("Tu sueño real promedio", f"{stats_ia['avg_sueno']:.1f}h",
                "✓ Suficiente" if stats_ia["avg_sueno"] >= 7 else "⚠ Insuficiente")
    with col_s2:
        if st.button("💡 Recomendaciones personalizadas", key="btn_sueno",
                     use_container_width=True):
            with st.spinner("Generando recomendaciones..."):
                st.info(chat_simple(
                    f"Situación: {prob_sueno}\n"
                    f"Hora de dormir: {hora_dormir_ia.strftime('%H:%M')}\n"
                    f"Meta: despertar 05:30\n\nDatos:\n{contexto}\n\n"
                    f"Da 3 recomendaciones específicas y prácticas.",
                    contexto=SYSTEM_SALUD
                ))

    st.divider()

    # Calistenia
    st.markdown("### 🏋️ Coach de calistenia")
    col_ca1, col_ca2 = st.columns([1, 2])
    with col_ca1:
        tipo_ses = st.selectbox("Tipo de ayuda", [
            "Planificar sesión de hoy",
            "Progresión para mi nivel actual",
            "Recuperación post-entrenamiento",
            "Motivación para no saltarme el miércoles",
            "Rutina corta (30 min)",
        ], key="sel_calistenia")
        nivel     = st.select_slider("Tu nivel",
            options=["Principiante","Básico","Intermedio"],
            value="Básico", key="sl_nivel")
        ultimo_ej = next((r for r in registros_ia if r["hizo_ejercicio"]), None)
        if ultimo_ej:
            st.caption(f"Último entreno: {ultimo_ej['fecha']}")
    with col_ca2:
        if st.button("🏋️ Consejo del coach", key="btn_calistenia",
                     use_container_width=True):
            ultimo_info = ""
            if ultimo_ej:
                notas_ej    = ultimo_ej.get("notas_ejercicio") or ""
                ultimo_info = (
                    f"Último entrenamiento: {ultimo_ej['fecha']}, "
                    f"{ultimo_ej.get('tipo_ejercicio','calistenia')} "
                    f"{ultimo_ej.get('duracion_minutos',0)}min, "
                    f"intensidad {ultimo_ej.get('intensidad','-')}/10"
                )
                if notas_ej:
                    ultimo_info += f"\nDetalle: {notas_ej[:200]}"
            with st.spinner("Coach preparando tu plan..."):
                st.info(chat_simple(
                    f"Solicitud: {tipo_ses}\nNivel: {nivel}\n{ultimo_info}\n\n"
                    f"Contexto:\n{contexto}\n\n"
                    f"Da consejos para calistenia en casa, "
                    f"horario miércoles 16:30-18:30.",
                    contexto=SYSTEM_SALUD
                ))

    st.divider()

    # Chat libre
    st.markdown("### 💬 Pregunta libre al coach")
    pregunta = st.text_input(
        "Tu pregunta",
        placeholder="Ej: ¿Cómo mantengo energía en el bloque de código de las 06:15?",
        key="txt_pregunta_salud"
    )
    if pregunta:
        with st.spinner("Coach pensando..."):
            st.info(chat_simple(
                f"Contexto de salud:\n{contexto}\n\nPregunta: {pregunta}",
                contexto=SYSTEM_SALUD
            ))

st.divider()
st.caption("💪 Módulo Salud • Google Fit + IA")