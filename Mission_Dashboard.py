"""
🏠 Mission Dashboard - Control de Mando Personal
"""

import streamlit as st
from datetime import timedelta
import sys
from pathlib import Path

# ── PATH ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR / "app"))

from app.database import (
    ensure_database,
    calcular_sobres,
    ejecutar,
    ejecutar_cached,
    invalidate_data_caches,
)
from app.stability import after_write
from app.auth import require_auth, logout, panel_gestion_usuarios
from app.ai_client import chat_simple, estado_gemini, verificar_conexion
from app.timezone_config import (
    date, datetime,           # re-exportados — todo el código existente funciona
    hoy as _hoy,              # función con zona horaria
    ahora as _ahora,          # función con zona horaria
    TZ_NAME,
)

# ═══════════════════════════════════════════════════════════════
# 1. set_page_config — SIEMPRE PRIMERO
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Mission Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════
# 2. AUTENTICACIÓN (usuario + contraseña, todas las rutas)
# ═══════════════════════════════════════════════════════════════
require_auth()

# ═══════════════════════════════════════════════════════════════
# 3. Cache de IA
# ═══════════════════════════════════════════════════════════════
@st.cache_resource(ttl=300)
def _init_gemini():
    verificar_conexion()
    return True

_init_gemini()

# ═══════════════════════════════════════════════════════════════
# 4. Inicializar BD (una vez por sesión)
# ═══════════════════════════════════════════════════════════════
ensure_database()

# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════
def load_css():
    st.markdown("""
    <style>
        :root {
            --bg-primary: #0d1117; --bg-secondary: #161b22;
            --bg-tertiary: #21262d; --text-primary: #f0f6fc;
            --text-secondary: #8b949e; --accent-gold: #e3b341;
            --accent-blue: #58a6ff; --accent-green: #3fb950;
            --accent-purple: #a371f7; --accent-red: #f85149;
        }
        .stApp { background-color: var(--bg-primary); }
        [data-testid="stSidebar"] {
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--bg-tertiary);
        }
        h1, h2, h3 { color: var(--text-primary) !important; font-weight: 600 !important; }
        .mission-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--bg-tertiary);
            border-radius: 12px; padding: 1.5rem;
            margin-bottom: 1rem; transition: border-color 0.2s ease;
        }
        .mission-card:hover { border-color: var(--accent-blue); }
        .stButton > button {
            background-color: var(--bg-tertiary); color: var(--text-primary);
            border: 1px solid var(--bg-tertiary); border-radius: 8px;
        }
        .stButton > button:hover { border-color: var(--accent-blue); }
        [data-testid="stMetricValue"] { color: var(--accent-gold) !important; }
        [data-testid="stMetricLabel"] { color: var(--text-secondary) !important; }
    </style>
    """, unsafe_allow_html=True)

load_css()

# ═══════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN
# ═══════════════════════════════════════════════════════════════
if "user_name" not in st.session_state or not st.session_state.user_name:
    user = st.session_state.get("user") or {}
    st.session_state.user_name = user.get("username") or "Usuario"

# ═══════════════════════════════════════════════════════════════
# HELPERS DE TIEMPO — zona horaria correcta
# ═══════════════════════════════════════════════════════════════

def _hoy_iso() -> str:
    return _hoy().isoformat()

def _ahora_hora() -> int:
    return _ahora().hour

def _ahora_str() -> str:
    return _ahora().strftime("%H:%M")

def _ahora_fecha_str() -> str:
    return _ahora().strftime("%A, %d de %B")

# ═══════════════════════════════════════════════════════════════
# FUNCIONES DE BD
# ═══════════════════════════════════════════════════════════════

def get_habitos_config() -> list:
    return ejecutar_cached("""
        SELECT id, clave, label, emoji, hora, activo, orden
        FROM habitos_config
        WHERE activo = 1
        ORDER BY orden, id
    """) or []


def get_todos_habitos_config() -> list:
    return ejecutar_cached("""
        SELECT id, clave, label, emoji, hora, activo, orden
        FROM habitos_config
        ORDER BY orden, id
    """) or []


def get_habitos_hoy() -> dict:
    hoy_iso = _hoy_iso()
    # Sembrar filas del día solo una vez por sesión (no en cada recarga)
    seed_key = f"_habitos_seeded_{hoy_iso}"
    if not st.session_state.get(seed_key):
        for h in get_habitos_config():
            ejecutar("""
                INSERT OR IGNORE INTO habitos_diarios_v2
                    (fecha, habito_clave, completado)
                VALUES (?, ?, 0)
            """, [hoy_iso, h["clave"]])
        st.session_state[seed_key] = True

    rows = ejecutar("""
        SELECT habito_clave, completado, hora_completado, fecha
        FROM habitos_diarios_v2
        WHERE fecha = ?
    """, [hoy_iso], fetchall=True) or []

    return {r["habito_clave"]: r for r in rows}


def toggle_habito(clave: str):
    hoy_iso  = _hoy_iso()
    hora_now = _ahora_str()

    rows = ejecutar("""
        SELECT completado FROM habitos_diarios_v2
        WHERE fecha = ? AND habito_clave = ?
    """, [hoy_iso, clave], fetchall=True)

    nuevo = 0 if (rows and rows[0]["completado"]) else 1
    hora  = hora_now if nuevo else None

    ejecutar("""
        INSERT INTO habitos_diarios_v2
            (fecha, habito_clave, completado, hora_completado)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(fecha, habito_clave)
        DO UPDATE SET
            completado      = excluded.completado,
            hora_completado = excluded.hora_completado
    """, [hoy_iso, clave, nuevo, hora])
    invalidate_data_caches()


def agregar_habito(label: str, emoji: str, hora: str) -> bool:
    clave = label.lower().strip().replace(" ", "_")[:20]
    rows  = ejecutar("SELECT MAX(orden) AS m FROM habitos_config", fetchall=True)
    max_ord = (rows[0]["m"] or 0) if rows else 0
    try:
        ejecutar("""
            INSERT OR IGNORE INTO habitos_config
                (clave, label, emoji, hora, activo, orden)
            VALUES (?, ?, ?, ?, 1, ?)
        """, [clave, label.strip(), emoji or "⭐", hora or "—", max_ord + 1])
        invalidate_data_caches()
        # permitir re-sembrar hábitos del día
        hoy_iso = _hoy_iso()
        st.session_state.pop(f"_habitos_seeded_{hoy_iso}", None)
        return True
    except Exception:
        return False


def editar_habito(clave: str, label: str, emoji: str, hora: str) -> bool:
    ejecutar("""
        UPDATE habitos_config SET label=?, emoji=?, hora=? WHERE clave=?
    """, [label, emoji, hora, clave])
    invalidate_data_caches()
    return True


def eliminar_habito(clave: str) -> bool:
    ejecutar("UPDATE habitos_config SET activo=0 WHERE clave=?", [clave])
    invalidate_data_caches()
    return True


def reactivar_habito(clave: str):
    ejecutar("UPDATE habitos_config SET activo=1 WHERE clave=?", [clave])
    invalidate_data_caches()


def restaurar_habitos_default():
    for clave in ["devocional", "codigo", "lectura", "calistenia"]:
        ejecutar("UPDATE habitos_config SET activo=1 WHERE clave=?", [clave])
    invalidate_data_caches()


# ═══════════════════════════════════════════════════════════════
# MÉTRICAS DE MÓDULOS
# ═══════════════════════════════════════════════════════════════

def get_metricas_modulos() -> dict:
    metricas = {}
    hoy      = _hoy()
    hoy_iso  = hoy.isoformat()

    # ── FINANZAS ─────────────────────────────────────────────
    try:
        datos         = calcular_sobres(hoy.month, hoy.year)
        total_gastado = datos["total_gastado"]
        ingreso       = datos["ingreso"]
        pct           = int(total_gastado / ingreso * 100) if ingreso > 0 else 0
        metricas["finanzas"] = {
            "gastos":      total_gastado,
            "presupuesto": ingreso,
            "pct":         pct,
            "semaforo":    "🟢" if pct < 70 else "🟡" if pct < 90 else "🔴",
            "color":       "#3fb950" if pct < 70 else "#e3b341" if pct < 90 else "#f85149",
            "sin_ingreso": datos["sin_ingreso"],
        }
    except Exception:
        metricas["finanzas"] = {
            "gastos": 0, "presupuesto": 0, "pct": 0,
            "semaforo": "⚪", "color": "#8b949e", "sin_ingreso": True,
        }

    # ── DEEP WORK ─────────────────────────────────────────────
    try:
        lunes = (hoy - timedelta(days=hoy.weekday())).isoformat()
        rows  = ejecutar_cached("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado='Completado' THEN 1 ELSE 0 END) AS completados
            FROM sesiones_completadas WHERE fecha >= ?
        """, (lunes,))
        r = rows[0] if rows else {"total": 0, "completados": 0}
        total_dw = r["total"] or 0
        comp_dw  = r["completados"] or 0
        metricas["deep_work"] = {
            "completados": comp_dw, "total": total_dw,
            "pct": int(comp_dw / total_dw * 100) if total_dw > 0 else 0,
        }
    except Exception:
        metricas["deep_work"] = {"completados": 0, "total": 0, "pct": 0}

    # ── BIBLIOTECA ────────────────────────────────────────────
    try:
        total_libros = (ejecutar_cached(
            "SELECT COUNT(*) AS n FROM libros"
        ) or [{"n": 0}])[0]["n"] or 0

        rows = ejecutar_cached("""
            SELECT titulo, pagina_actual, total_paginas
            FROM libros WHERE estado='leyendo'
            ORDER BY actualizado_en DESC LIMIT 1
        """)
        leyendo = rows[0] if rows else None
        if leyendo and leyendo["total_paginas"]:
            pct_libro   = int((leyendo["pagina_actual"] or 0) / leyendo["total_paginas"] * 100)
            libro_texto = f"{leyendo['titulo'][:28]}... • {pct_libro}%"
        else:
            libro_texto = "Sin libro activo"
        metricas["biblioteca"] = {"total": total_libros, "leyendo": libro_texto}
    except Exception:
        metricas["biblioteca"] = {"total": 0, "leyendo": "Sin datos"}

    # ── TEOLOGÍA ──────────────────────────────────────────────
    try:
        rows = ejecutar_cached("SELECT COUNT(*) AS total, MAX(fecha) AS ultimo FROM devocionales")
        r         = rows[0] if rows else {"total": 0, "ultimo": "—"}
        total_teo = r["total"] or 0
        ultimo    = r["ultimo"] or "—"

        fechas_teo = ejecutar_cached("SELECT fecha FROM devocionales ORDER BY fecha DESC")
        racha = 0
        check = hoy
        for row in (fechas_teo or []):
            if row["fecha"] == check.isoformat():
                racha += 1
                check -= timedelta(days=1)
            else:
                break
        metricas["teologia"] = {"total": total_teo, "ultimo": ultimo, "racha": racha}
    except Exception:
        metricas["teologia"] = {"total": 0, "ultimo": "—", "racha": 0}

    # ── SALUD ─────────────────────────────────────────────────
    try:
        rows = ejecutar("""
            SELECT energia_manana, hizo_ejercicio, productividad_percibida
            FROM registros_salud WHERE fecha = ?
        """, [hoy_iso], fetchall=True)
        sal = rows[0] if rows else None
        metricas["salud"] = {
            "energia":       (sal["energia_manana"] or 0) if sal else 0,
            "ejercicio":     bool(sal["hizo_ejercicio"]) if sal else False,
            "productividad": (sal["productividad_percibida"] or 0) if sal else 0,
            "registrado":    sal is not None,
        }
    except Exception:
        metricas["salud"] = {"energia": 0, "ejercicio": False, "productividad": 0, "registrado": False}

    # ── MATRIMONIO ────────────────────────────────────────────
    try:
        rows = ejecutar("""
            SELECT titulo, fecha, hora FROM matrimonio_citas
            WHERE fecha >= ? AND estado_planificacion NOT IN ('Cancelada','Completada')
            ORDER BY fecha, hora LIMIT 1
        """, [hoy_iso], fetchall=True)
        prox = rows[0] if rows else None
        if prox:
            dias       = (datetime.strptime(prox["fecha"], "%Y-%m-%d").date() - hoy).days
            label      = "Hoy" if dias == 0 else f"En {dias}d"
            prox_texto = f"{label}: {prox['titulo'][:22]}"
        else:
            prox_texto = "Sin citas próximas"

        rows_mes = ejecutar_cached("""
            SELECT COUNT(*) AS n FROM matrimonio_citas
            WHERE strftime('%Y-%m', fecha) = ?
              AND estado_planificacion = 'Completada'
        """, (hoy.strftime("%Y-%m"),))
        citas_mes = (rows_mes[0]["n"] or 0) if rows_mes else 0
        metricas["matrimonio"] = {"proxima": prox_texto, "citas_mes": citas_mes}
    except Exception:
        metricas["matrimonio"] = {"proxima": "Sin datos", "citas_mes": 0}

    # ── SANDBOX ───────────────────────────────────────────────
    try:
        ideas = (ejecutar_cached("""
            SELECT COUNT(*) AS n FROM sandbox_ideas
            WHERE estado NOT IN ('Completado','Abandonado')
        """) or [{"n": 0}])[0]["n"] or 0

        snips = (ejecutar_cached(
            "SELECT COUNT(*) AS n FROM sandbox_snippets"
        ) or [{"n": 0}])[0]["n"] or 0

        metricas["sandbox"] = {"ideas_activas": ideas, "snippets": snips}
    except Exception:
        metricas["sandbox"] = {"ideas_activas": 0, "snippets": 0}

    return metricas


# ═══════════════════════════════════════════════════════════════
# SIDEBAR DATA
# ═══════════════════════════════════════════════════════════════

def get_sidebar_data() -> dict:
    hoy     = _hoy()
    hoy_iso = hoy.isoformat()

    fechas_dev = ejecutar_cached(
        "SELECT fecha FROM devocionales ORDER BY fecha DESC LIMIT 30"
    ) or []
    racha_dev = 0
    check = hoy
    for r in fechas_dev:
        if r["fecha"] == check.isoformat():
            racha_dev += 1
            check -= timedelta(days=1)
        else:
            break

    hab_rows = ejecutar_cached("""
        SELECT fecha, COUNT(*) AS total, SUM(completado) AS completados
        FROM habitos_diarios_v2
        GROUP BY fecha
        ORDER BY fecha DESC LIMIT 30
    """) or []
    racha_hab = 0
    check_hab = hoy
    for row in hab_rows:
        f = datetime.strptime(row["fecha"], "%Y-%m-%d").date()
        if f == check_hab and (row["completados"] or 0) == (row["total"] or 0):
            racha_hab += 1
            check_hab -= timedelta(days=1)
        else:
            break

    citas = ejecutar("""
        SELECT titulo, fecha, hora FROM matrimonio_citas
        WHERE fecha >= ? AND estado_planificacion IN ('Confirmada','Planeando')
        ORDER BY fecha, hora LIMIT 1
    """, [hoy_iso], fetchall=True)

    ing_rows = ejecutar_cached("""
        SELECT monto_total FROM ingreso_mensual WHERE mes=? AND anio=?
    """, (hoy.month, hoy.year))
    ingreso_sb = (ing_rows[0]["monto_total"] or 0) if ing_rows else 0

    gasto_rows = ejecutar_cached("""
        SELECT SUM(monto) AS total FROM gastos_sobres
        WHERE strftime('%Y-%m', fecha) = ?
    """, (hoy.strftime("%Y-%m"),))
    gastado_sb = (gasto_rows[0]["total"] or 0) if gasto_rows else 0

    return {
        "racha_dev":    racha_dev,
        "racha_hab":    racha_hab,
        "proxima_cita": citas[0] if citas else None,
        "ingreso":      ingreso_sb,
        "gastado":      gastado_sb,
    }


# ═══════════════════════════════════════════════════════════════
# ALERTAS DATA
# ═══════════════════════════════════════════════════════════════

def get_alertas_data(hoy_iso: str) -> dict:
    dev = ejecutar(
        "SELECT id FROM devocionales WHERE fecha=?",
        [hoy_iso], fetchall=True
    )
    dw = ejecutar("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN estado='Completado' THEN 1 ELSE 0 END) AS comp
        FROM sesiones_completadas WHERE fecha=?
    """, [hoy_iso], fetchall=True)
    dw_row = dw[0] if dw else {"total": 0, "comp": 0}

    sal = ejecutar(
        "SELECT id FROM registros_salud WHERE fecha=?",
        [hoy_iso], fetchall=True
    )
    cita = ejecutar("""
        SELECT titulo, hora FROM matrimonio_citas
        WHERE fecha=? AND estado_planificacion IN ('Confirmada','Planeando')
        LIMIT 1
    """, [hoy_iso], fetchall=True)

    return {
        "devocional_hoy": len(dev) > 0,
        "dw_total":       dw_row["total"] or 0,
        "dw_comp":        dw_row["comp"]  or 0,
        "salud_hoy":      len(sal) > 0,
        "cita_hoy":       cita[0] if cita else None,
    }


# ═══════════════════════════════════════════════════════════════
# CARGAR DATOS — con zona horaria correcta
# ═══════════════════════════════════════════════════════════════

hoy         = _hoy()          # ← zona horaria local
hoy_iso     = _hoy_iso()
hora_actual = _ahora_hora()   # ← hora local

configs_hab = get_habitos_config()
habitos     = get_habitos_hoy()
metricas    = get_metricas_modulos()
sb_data     = get_sidebar_data()
a_data      = get_alertas_data(hoy_iso)

racha_dev    = sb_data["racha_dev"]
racha_hab    = sb_data["racha_hab"]
proxima_cita = sb_data["proxima_cita"]
ingreso_sb   = sb_data["ingreso"]
gastado_sb   = sb_data["gastado"]

completados_hoy = sum(
    1 for cfg in configs_hab
    if habitos.get(cfg["clave"], {}).get("completado")
)
total_hoy = len(configs_hab)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(f"""
    <div style="padding:0.5rem;">
        <p style="color:#f0f6fc;margin:0;font-weight:600;">
            👤 {st.session_state.user_name}
        </p>
        <p style="color:#8b949e;margin:0;font-size:0.75rem;">
            {_ahora_fecha_str()} · {TZ_NAME}
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown("**🔥 Rachas activas**")
    color_dev = "#3fb950" if racha_dev >= 7 else "#e3b341" if racha_dev >= 3 else "#f85149"
    color_hab = "#3fb950" if racha_hab >= 7 else "#e3b341" if racha_hab >= 3 else "#f85149"

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;
                    border-radius:8px;padding:0.6rem;text-align:center;">
            <div style="font-size:1.2rem;">✝️</div>
            <div style="color:{color_dev};font-weight:700;font-size:1.1rem;">{racha_dev}d</div>
            <div style="color:#8b949e;font-size:0.65rem;">Devocional</div>
        </div>
        """, unsafe_allow_html=True)
    with col_sb2:
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;
                    border-radius:8px;padding:0.6rem;text-align:center;">
            <div style="font-size:1.2rem;">📋</div>
            <div style="color:{color_hab};font-weight:700;font-size:1.1rem;">{racha_hab}d</div>
            <div style="color:#8b949e;font-size:0.65rem;">Hábitos</div>
        </div>
        """, unsafe_allow_html=True)
    st.divider()

    st.markdown("**💑 Próxima cita**")
    if proxima_cita:
        dias_cita  = (datetime.strptime(proxima_cita["fecha"], "%Y-%m-%d").date() - hoy).days
        label_cita = "Hoy 🎉" if dias_cita == 0 else f"En {dias_cita} días"
        hora_txt   = f" — {proxima_cita['hora'][:5]}" if proxima_cita.get("hora") else ""
        st.markdown(f"""
        <div style="background:#1a1229;border:1px solid #a371f7;border-radius:8px;padding:0.6rem;">
            <div style="color:#a371f7;font-size:0.7rem;font-weight:700;">{label_cita}</div>
            <div style="color:#f0f6fc;font-size:0.8rem;">{proxima_cita['titulo'][:25]}</div>
            <div style="color:#8b949e;font-size:0.7rem;">{proxima_cita['fecha']}{hora_txt}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.caption("Sin citas programadas")
    st.divider()

    st.markdown("**💰 Finanzas del mes**")
    if ingreso_sb > 0:
        pct_sb    = int(gastado_sb / ingreso_sb * 100)
        color_fin = "#3fb950" if pct_sb < 70 else "#e3b341" if pct_sb < 90 else "#f85149"
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:0.6rem;">
            <div style="display:flex;justify-content:space-between;">
                <span style="color:#8b949e;font-size:0.75rem;">${gastado_sb:,.0f} / ${ingreso_sb:,.0f}</span>
                <span style="color:{color_fin};font-size:0.75rem;font-weight:700;">{pct_sb}%</span>
            </div>
            <div style="background:#21262d;border-radius:4px;height:6px;margin-top:0.4rem;">
                <div style="background:{color_fin};width:{min(pct_sb,100)}%;height:100%;border-radius:4px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.caption("⚠️ Sin ingreso registrado")
    st.divider()

    st.markdown("**🤖 Estado IA**")
    estado_ia = estado_gemini()
    if not estado_ia.get("api_key_configurada"):
        st.error("❌ Sin API Key")
    elif estado_ia.get("modo") == "offline_sin_cuota":
        st.warning("⚠️ Sin cuota hoy")
    else:
        llamadas = estado_ia.get("llamadas_hoy", 0)
        max_llam = estado_ia.get("max_llamadas", 400)
        pct_ia   = int(llamadas / max_llam * 100) if max_llam > 0 else 0
        color_ia = "#3fb950" if pct_ia < 70 else "#e3b341" if pct_ia < 90 else "#f85149"
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:0.6rem;">
            <div style="display:flex;justify-content:space-between;">
                <span style="color:#3fb950;font-size:0.75rem;">✅ Conectado</span>
                <span style="color:{color_ia};font-size:0.75rem;">{llamadas}/{max_llam}</span>
            </div>
            <div style="background:#21262d;border-radius:4px;height:6px;margin-top:0.4rem;">
                <div style="background:{color_ia};width:{min(pct_ia,100)}%;height:100%;border-radius:4px;"></div>
            </div>
            <div style="color:#8b949e;font-size:0.65rem;margin-top:0.3rem;">llamadas hoy</div>
        </div>
        """, unsafe_allow_html=True)
    st.divider()
    user = st.session_state.get("user") or {}
    st.caption(f"👤 {user.get('username', '—')} · {user.get('rol', '')}")
    if user.get("rol") == "admin":
        st.page_link("pages/09_Usuarios.py", label="🔐 Crear / gestionar usuarios", icon="🔐")
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        logout()
    st.caption(f"v1.2 • Python + Streamlit • {TZ_NAME}")

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<h1 style="margin-bottom:0.25rem;">Control de Mando</h1>
<p style="color:#8b949e;margin-top:0;">Dashboard integral de vida</p>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# ALERTAS
# ═══════════════════════════════════════════════════════════════

alertas = []

if hora_actual >= 6:
    if a_data["devocional_hoy"]:
        alertas.append(("success", "✝️ Devocional completado hoy ✓"))
    else:
        alertas.append(("warning", "✝️ Sin devocional hoy — recuerda apartar tiempo con Dios"))

if hora_actual >= 8:
    if a_data["dw_comp"] > 0:
        alertas.append(("success", f"⏱️ {a_data['dw_comp']} bloques Deep Work completados ✓"))
    elif a_data["dw_total"] > 0:
        alertas.append(("error", "⏱️ Sin bloques Deep Work completados hoy"))

if hora_actual >= 21 and not a_data["salud_hoy"]:
    alertas.append(("warning", "💪 Sin registro de salud hoy"))

if a_data["cita_hoy"]:
    titulo_c = a_data["cita_hoy"]["titulo"]
    hora_c   = a_data["cita_hoy"].get("hora", "")
    alertas.append(("info",
        f"💑 Cita hoy: {titulo_c[:25]}"
        f"{' — ' + hora_c[:5] if hora_c else ''}"
    ))

try:
    sobres_alert = calcular_sobres(hoy.month, hoy.year)
    for key, sobre in sobres_alert["sobres"].items():
        if sobre["pct_usado"] >= 100:
            alertas.append(("error",   f"🔴 Sobre {sobre['nombre'][:20]} AGOTADO"))
        elif sobre["pct_usado"] >= 80:
            alertas.append(("warning", f"🟡 Sobre {sobre['nombre'][:20]} al {sobre['pct_usado']:.0f}%"))
except Exception:
    pass

if completados_hoy == total_hoy and total_hoy > 0:
    alertas.append(("success", "🎉 ¡Todos los hábitos completados hoy!"))
elif hora_actual >= 22 and completados_hoy < total_hoy:
    alertas.append(("warning", f"⚡ {completados_hoy}/{total_hoy} hábitos completados"))

for tipo, mensaje in alertas:
    getattr(st, tipo)(mensaje)

st.divider()

# ═══════════════════════════════════════════════════════════════
# HÁBITOS DIARIOS
# ═══════════════════════════════════════════════════════════════

st.subheader("📋 Hábitos del día")

if "modo_gestion_hab" not in st.session_state:
    st.session_state.modo_gestion_hab = False
if "hab_editando" not in st.session_state:
    st.session_state.hab_editando = None

col_tit_h, col_btn_h = st.columns([5, 1])
with col_btn_h:
    if st.button(
        "✖ Cerrar" if st.session_state.modo_gestion_hab else "⚙️ Gestionar",
        use_container_width=True, key="btn_gest_hab"
    ):
        st.session_state.modo_gestion_hab = not st.session_state.modo_gestion_hab
        st.session_state.hab_editando = None
        st.rerun()

if st.session_state.modo_gestion_hab:
    with st.container():
        st.markdown("#### ⚙️ Gestión de hábitos")
        st.markdown("**➕ Nuevo hábito**")
        with st.form("form_nuevo_habito", clear_on_submit=True):
            col_n1, col_n2, col_n3 = st.columns([3, 1, 2])
            with col_n1:
                nh_label = st.text_input("Nombre", placeholder="Ej: Meditación")
            with col_n2:
                nh_emoji = st.text_input("Emoji", value="⭐", max_chars=2)
            with col_n3:
                nh_hora = st.text_input("Hora", placeholder="07:00")
            if st.form_submit_button("➕ Agregar", use_container_width=True, type="primary"):
                if not nh_label.strip():
                    st.error("⚠️ Nombre requerido")
                elif agregar_habito(nh_label, nh_emoji, nh_hora):
                    st.success(f"✅ '{nh_label}' creado")
                    st.rerun()
                else:
                    st.warning("Ya existe un hábito con ese nombre")

        st.divider()
        st.markdown("**📋 Hábitos activos:**")
        todos_configs = get_todos_habitos_config()

        for hc in todos_configs:
            col_e,col_em,col_lab,col_hor,col_est,col_ed,col_del = \
                st.columns([0.5,0.5,2,1.5,1,0.8,0.8])
            with col_e:   st.caption(hc["emoji"])
            with col_em:  st.caption("🟢" if hc["activo"] else "⚪")
            with col_lab: st.caption(f"**{hc['label']}**")
            with col_hor: st.caption(hc["hora"])
            with col_est: st.caption("Activo" if hc["activo"] else "Inactivo")
            with col_ed:
                if st.button("✏️", key=f"ed_h_{hc['clave']}", use_container_width=True):
                    st.session_state.hab_editando = hc["clave"]
                    st.rerun()
            with col_del:
                icono = "🗑️" if hc["activo"] else "♻️"
                if st.button(icono, key=f"del_h_{hc['clave']}", use_container_width=True,
                             help="Desactivar" if hc["activo"] else "Reactivar"):
                    if hc["activo"]:
                        st.session_state[f"confirm_del_h_{hc['clave']}"] = True
                    else:
                        reactivar_habito(hc["clave"])
                        st.success(f"♻️ '{hc['label']}' reactivado")
                        st.rerun()

            if st.session_state.get(f"confirm_del_h_{hc['clave']}"):
                c1, c2, c3 = st.columns([3,1,1])
                with c1: st.warning(f"⚠️ ¿Desactivar *{hc['label']}*?")
                with c2:
                    if st.button("🗑️ Sí", key=f"cfd_h_{hc['clave']}", use_container_width=True):
                        eliminar_habito(hc["clave"])
                        st.session_state[f"confirm_del_h_{hc['clave']}"] = False
                        st.rerun()
                with c3:
                    if st.button("✖", key=f"cnf_h_{hc['clave']}", use_container_width=True):
                        st.session_state[f"confirm_del_h_{hc['clave']}"] = False
                        st.rerun()

            if st.session_state.hab_editando == hc["clave"]:
                with st.form(f"form_edit_h_{hc['clave']}"):
                    st.markdown(f"#### ✏️ Editando: {hc['label']}")
                    col_f1,col_f2,col_f3 = st.columns([3,1,2])
                    with col_f1: e_label = st.text_input("Nombre", value=hc["label"])
                    with col_f2: e_emoji = st.text_input("Emoji",  value=hc["emoji"], max_chars=2)
                    with col_f3: e_hora  = st.text_input("Hora",   value=hc["hora"])
                    col_sg, col_sc = st.columns(2)
                    with col_sg:
                        if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                            if not e_label.strip():
                                st.error("⚠️ Nombre requerido")
                            else:
                                editar_habito(hc["clave"], e_label, e_emoji, e_hora)
                                st.session_state.hab_editando = None
                                st.success("✅ Actualizado")
                                st.rerun()
                    with col_sc:
                        if st.form_submit_button("✖ Cancelar", use_container_width=True):
                            st.session_state.hab_editando = None
                            st.rerun()

        st.divider()
        if st.button("♻️ Restaurar hábitos por defecto"):
            restaurar_habitos_default()
            st.success("✅ Restaurados")
            st.rerun()
    st.divider()

# ── TARJETAS ──────────────────────────────────────────────────
n_cols = min(len(configs_hab), 6) if configs_hab else 4
cols_h = st.columns(n_cols)

for i, cfg in enumerate(configs_hab):
    clave      = cfg["clave"]
    completado = habitos.get(clave, {}).get("completado", 0)
    hora_ok    = habitos.get(clave, {}).get("hora_completado", "")
    color_b    = "#3fb950" if completado else "#30363d"
    color_f    = "#0f2d0f" if completado else "#161b22"
    simbolo    = "✅"       if completado else "○"
    color_s    = "#3fb950" if completado else "#8b949e"
    hora_tag   = (
        f'<div style="color:#3fb950;font-size:0.7rem;">✓ {hora_ok}</div>'
        if hora_ok else ""
    )
    with cols_h[i % n_cols]:
        st.markdown(f"""
        <div style="background:{color_f};border:1px solid {color_b};
                    border-radius:12px;padding:1rem;
                    text-align:center;margin-bottom:0.5rem;">
            <div style="font-size:1.5rem;">{cfg['emoji']}</div>
            <div style="color:#f0f6fc;font-weight:600;font-size:0.9rem;">{cfg['label']}</div>
            <div style="color:{color_s};font-size:1.8rem;line-height:1.2;">{simbolo}</div>
            <div style="color:#8b949e;font-size:0.75rem;">{cfg['hora']}</div>
            {hora_tag}
        </div>
        """, unsafe_allow_html=True)
        if st.button(
            "✓ Hecho" if completado else "Marcar ✓",
            key=f"hab_{clave}",
            use_container_width=True,
            type="secondary" if completado else "primary"
        ):
            toggle_habito(clave)
            st.rerun()

st.progress(
    completados_hoy / total_hoy if total_hoy else 0,
    text=f"Hábitos completados: {completados_hoy}/{total_hoy}"
)
st.divider()

# ═══════════════════════════════════════════════════════════════
# MÓDULOS
# ═══════════════════════════════════════════════════════════════

st.subheader("🗂️ Módulos del Sistema")
mod_col1, mod_col2 = st.columns(2)

with mod_col1:
    fin = metricas["finanzas"]
    sin_txt = " · ⚠️ Registra ingreso en Finanzas" if fin.get("sin_ingreso") else ""
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">💰 Finanzas Personales</span>
            <span style="color:{fin['color']};font-size:0.875rem;">{fin['semaforo']} {fin['pct']}% usado</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">
            Gastado: ${fin['gastos']:,.0f} / Ingreso: ${fin['presupuesto']:,.0f}{sin_txt}
        </p>
    </div>""", unsafe_allow_html=True)

    dw = metricas["deep_work"]
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">⏰ Deep Work</span>
            <span style="color:#58a6ff;font-size:0.875rem;">{dw['completados']}/{dw['total']} bloques esta semana</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">Tasa de éxito: {dw['pct']}%</p>
    </div>""", unsafe_allow_html=True)

    teo = metricas["teologia"]
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">✝️ Bitácora Teológica</span>
            <span style="color:#a371f7;font-size:0.875rem;">{teo['total']} entradas · 🔥{teo['racha']} días</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">Último devocional: {teo['ultimo']}</p>
    </div>""", unsafe_allow_html=True)

with mod_col2:
    bib = metricas["biblioteca"]
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">📚 Biblioteca</span>
            <span style="color:#e3b341;font-size:0.875rem;">{bib['total']} libros</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">📖 {bib['leyendo']}</p>
    </div>""", unsafe_allow_html=True)

    sal = metricas["salud"]
    sal_texto = (
        f"Energía: {sal['energia']}/10 · "
        f"{'🏋️ Ejercicio ✓' if sal['ejercicio'] else '❌ Sin ejercicio'} · "
        f"Productividad: {sal['productividad']}/10"
        if sal["registrado"] else "Sin registro hoy — ve al módulo Salud"
    )
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">💪 Salud y Energía</span>
            <span style="color:#f85149;font-size:0.875rem;">Energía: {sal['energia']}/10</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">{sal_texto}</p>
    </div>""", unsafe_allow_html=True)

    mat = metricas["matrimonio"]
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">💑 Conexión Matrimonial</span>
            <span style="color:#ff69b4;font-size:0.875rem;">{mat['citas_mes']} citas este mes</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">📅 {mat['proxima']}</p>
    </div>""", unsafe_allow_html=True)

    sand = metricas["sandbox"]
    st.markdown(f"""
    <div class="mission-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f0f6fc;font-weight:600;">🧪 Sandbox</span>
            <span style="color:#58a6ff;font-size:0.875rem;">{sand['ideas_activas']} ideas activas</span>
        </div>
        <p style="color:#8b949e;font-size:0.875rem;margin-top:0.5rem;">🧩 {sand['snippets']} snippets guardados</p>
    </div>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SECRETARIA IA
# ═══════════════════════════════════════════════════════════════

st.divider()
st.subheader("🤖 Secretaria IA")
col_chat, col_alertas = st.columns([2, 1])

with col_chat:
    # Inicializar estado del chat (una vez)
    if "ia_respuesta" not in st.session_state:
        st.session_state.ia_respuesta = None
    if "ia_prompt_enviado" not in st.session_state:
        st.session_state.ia_prompt_enviado = ""

    with st.form("form_chat_ia"):
        prompt_usuario = st.text_input(
            "Pregunta a tu secretaria:",
            placeholder="Ej: ¿Qué pasaje leer hoy?",
        )
        enviar = st.form_submit_button(
            "➤ Enviar", use_container_width=True, type="primary"
        )

    if enviar and prompt_usuario.strip():
        if prompt_usuario != st.session_state.ia_prompt_enviado:
            with st.spinner("Pensando..."):
                st.session_state.ia_respuesta = chat_simple(prompt_usuario)
                st.session_state.ia_prompt_enviado = prompt_usuario

    if st.session_state.ia_respuesta:
        st.info(st.session_state.ia_respuesta)
        if st.button("🗑️ Limpiar", key="btn_limpiar_chat"):
            st.session_state.ia_respuesta = None
            st.session_state.ia_prompt_enviado = ""
            st.rerun()

with col_alertas:
    st.markdown("**🔔 Estado del día**")
    total_alertas = len([a for a in alertas if a[0] in ["warning","error"]])
    if total_alertas == 0:
        st.success("✅ Todo en orden hoy")
    else:
        st.warning(f"⚠️ {total_alertas} alertas pendientes")
    st.caption(f"🕐 {_ahora_str()} {TZ_NAME}")

# ═══════════════════════════════════════════════════════════════
# FOOTER + SEGURIDAD
# ═══════════════════════════════════════════════════════════════

st.divider()
st.caption(
    f"Mission Dashboard • {hoy.strftime('%d/%m/%Y')} • "
    f"Construido con ❤️ y disciplina • {completados_hoy}/{total_hoy} hábitos hoy"
)

user = st.session_state.get("user") or {}
if user.get("rol") == "admin":
    st.markdown("### 🔐 Usuarios")
    st.page_link("pages/09_Usuarios.py", label="Ir a crear y gestionar usuarios", icon="🔐")
    with st.expander("Gestionar aquí (rápido)", expanded=False):
        panel_gestion_usuarios()
