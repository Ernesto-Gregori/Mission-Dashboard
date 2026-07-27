"""
billing.py — Planes Free / Premium / Familia (app web).

Stripe Checkout llega después: por ahora secrets opcionales
STRIPE_LINK_PREMIUM / STRIPE_LINK_FAMILIA para el CTA de upgrade.
La fuente de verdad del plan vive en usuarios.plan (Turso).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from app.logging_config import get_logger
from app.templates import MODULE_TEMPLATES

log = get_logger("billing")

PLAN_FREE = "free"
PLAN_PREMIUM = "premium"
PLAN_FAMILIA = "familia"
PLANES_VALIDOS = (PLAN_FREE, PLAN_PREMIUM, PLAN_FAMILIA)

# Límites por plan (producto web — no modo local)
PLAN_LIMITES: dict[str, dict[str, Any]] = {
    PLAN_FREE: {
        "nombre": "Free",
        "precio": "$0",
        "modulos_max": 3,
        "ia_mensual": 15,          # chats Groq / mes (además del coach de setup)
        "coach_reconfig": False,  # solo 1 setup inicial
        "google": False,
        "historial_dias": 90,     # UI: no borrar datos, solo acotar vistas
        "export": False,
        "usuarios_cuenta": 1,
    },
    PLAN_PREMIUM: {
        "nombre": "Premium",
        "precio": "$7/mes",
        "modulos_max": None,      # todos
        "ia_mensual": None,       # ilimitado (sujeto a techo global Groq)
        "coach_reconfig": True,
        "google": True,
        "historial_dias": None,
        "export": True,
        "usuarios_cuenta": 1,
    },
    PLAN_FAMILIA: {
        "nombre": "Pareja / Familia",
        "precio": "$14/mes",
        "modulos_max": None,
        "ia_mensual": None,
        "coach_reconfig": True,
        "google": True,
        "historial_dias": None,
        "export": True,
        "usuarios_cuenta": 2,
    },
}


def ensure_billing_schema() -> None:
    """Columnas de plan + tabla uso_ia (idempotente)."""
    from app.db.core import ejecutar

    for sql in (
        "ALTER TABLE usuarios ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE usuarios ADD COLUMN plan_expira_en TEXT",
        "ALTER TABLE usuarios ADD COLUMN coach_ia_usado INTEGER DEFAULT 0",
        """
        CREATE TABLE IF NOT EXISTS uso_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            llamadas INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, anio, mes)
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception:
            pass

    # Grandfather: admins legacy sin plan → premium (no bloquear al dueño)
    try:
        ejecutar(
            """
            UPDATE usuarios
            SET plan = 'premium'
            WHERE (plan IS NULL OR plan = '')
              AND rol = 'admin'
            """
        )
        ejecutar(
            """
            UPDATE usuarios
            SET plan = 'free'
            WHERE plan IS NULL OR plan = ''
            """
        )
    except Exception as e:
        log.warning("ensure_billing_schema grandfather: %s", e)


def normalizar_plan(plan: str | None) -> str:
    p = (plan or PLAN_FREE).strip().lower()
    if p not in PLANES_VALIDOS:
        return PLAN_FREE
    return p


def limites(plan: str | None) -> dict[str, Any]:
    return PLAN_LIMITES[normalizar_plan(plan)]


def plan_vigente(user: dict | None = None) -> str:
    """Plan efectivo: si plan_expira_en pasó → free."""
    ensure_billing_schema()
    user = user or st.session_state.get("user") or {}
    plan = normalizar_plan(user.get("plan"))
    exp = user.get("plan_expira_en")
    if exp and plan != PLAN_FREE:
        try:
            if isinstance(exp, str):
                exp_d = date.fromisoformat(exp[:10])
            elif isinstance(exp, datetime):
                exp_d = exp.date()
            elif isinstance(exp, date):
                exp_d = exp
            else:
                exp_d = None
            if exp_d and exp_d < date.today():
                return PLAN_FREE
        except Exception:
            pass
    return plan


def modulos_permitidos(plan: str | None = None) -> list[str]:
    """
    Módulos que el plan puede activar.
    Free/Premium/Familia: catálogo completo; Free limita por cantidad (modulos_max).
    """
    _ = normalizar_plan(plan or plan_vigente())
    return list(MODULE_TEMPLATES.keys())


def modulos_max(plan: str | None = None) -> int | None:
    return limites(plan or plan_vigente()).get("modulos_max")


def puede_google(plan: str | None = None) -> bool:
    return bool(limites(plan or plan_vigente()).get("google"))


def puede_exportar(plan: str | None = None) -> bool:
    return bool(limites(plan or plan_vigente()).get("export"))


def puede_reconfigurar_coach(plan: str | None = None) -> bool:
    return bool(limites(plan or plan_vigente()).get("coach_reconfig"))


def historial_dias(plan: str | None = None) -> int | None:
    return limites(plan or plan_vigente()).get("historial_dias")


def fecha_minima_historial(plan: str | None = None) -> date | None:
    dias = historial_dias(plan)
    if dias is None:
        return None
    return date.today() - timedelta(days=int(dias))


def stripe_link(plan_destino: str) -> str:
    """Link de Stripe Checkout (Payment Link) desde secrets, si existe."""
    key = {
        PLAN_PREMIUM: "STRIPE_LINK_PREMIUM",
        PLAN_FAMILIA: "STRIPE_LINK_FAMILIA",
    }.get(normalizar_plan(plan_destino), "")
    if not key:
        return ""
    try:
        return (st.secrets.get(key) or "").strip()
    except Exception:
        return ""


def render_paywall(
    motivo: str,
    *,
    modulo: str | None = None,
    plan_sugerido: str = PLAN_PREMIUM,
) -> None:
    """Bloqueo amable + CTA de upgrade (Stripe link o aviso)."""
    lim = limites(plan_sugerido)
    st.warning(motivo)
    meta = MODULE_TEMPLATES.get(modulo or "", {})
    if meta:
        st.caption(
            f"Módulo: {meta.get('emoji', '')} {meta.get('nombre', modulo)}"
        )
    st.markdown(
        f"### Pasa a **{lim['nombre']}** ({lim['precio']}) para desbloquearlo"
    )
    st.markdown(
        "- Todos los módulos\n"
        "- Coach IA reconfigurable\n"
        "- Google Calendar / Fit\n"
        "- Historial completo + export"
    )
    link = stripe_link(plan_sugerido)
    if link:
        st.link_button(
            f"Upgrade a {lim['nombre']}",
            link,
            type="primary",
            use_container_width=True,
        )
    else:
        st.info(
            "Los cobros con Stripe se activan pronto. "
            "Si eres admin, puedes cambiar el plan en **Usuarios** mientras tanto."
        )
        if st.session_state.get("user", {}).get("rol") == "admin":
            st.caption("Atajo temporal: Usuarios → plan del usuario.")
    if st.button("🏠 Volver al dashboard", use_container_width=True):
        st.switch_page("Mission_Dashboard.py")


def require_plan_module(clave: str) -> None:
    """
    Si el módulo no está activo: paywall si Free (upsell) o aviso de activar.
    Llamar después de require_onboarding / junto a require_module.
    """
    from app.onboarding import modulo_activo, usuario_onboarding_completo

    if not usuario_onboarding_completo():
        return
    if modulo_activo(clave):
        return

    plan = plan_vigente()
    meta = MODULE_TEMPLATES.get(clave, {})
    nombre = meta.get("nombre", clave)
    if plan == PLAN_FREE:
        render_paywall(
            f"**{nombre}** no está en tu cupo Free "
            f"(máx. {limites(PLAN_FREE)['modulos_max']} módulos). "
            "Activa Premium para usar todos, o reconfigura cuando tengas un plan que lo permita.",
            modulo=clave,
        )
    else:
        st.warning(f"El módulo **{nombre}** no está activo en tu sistema.")
        st.caption("Actívalo desde el Coach en el dashboard.")
        if st.button("🏠 Ir al dashboard", use_container_width=True, key=f"go_dash_{clave}"):
            st.switch_page("Mission_Dashboard.py")
    st.stop()


def require_google_feature(nombre: str = "Google Fit / Calendar") -> bool:
    """
    True si el plan permite Google. Si no, muestra paywall y retorna False
    (el caller decide si hace st.stop()).
    """
    if puede_google():
        return True
    render_paywall(
        f"**{nombre}** está disponible en Premium y Familia.",
        plan_sugerido=PLAN_PREMIUM,
    )
    return False


# ── Cuota IA ───────────────────────────────────────────────────

def _mes_actual() -> tuple[int, int]:
    hoy = date.today()
    return hoy.year, hoy.month


def llamadas_ia_mes(user_id: int | None = None) -> int:
    ensure_billing_schema()
    from app.db.core import ejecutar
    from app.tenant import uid

    user_id = int(user_id or uid())
    anio, mes = _mes_actual()
    rows = (
        ejecutar(
            """
            SELECT llamadas FROM uso_ia
            WHERE user_id = ? AND anio = ? AND mes = ?
            """,
            [user_id, anio, mes],
            fetchall=True,
        )
        or []
    )
    return int(rows[0]["llamadas"]) if rows else 0


def registrar_llamada_ia(user_id: int | None = None) -> int:
    """Incrementa contador mensual; retorna total del mes."""
    ensure_billing_schema()
    from app.db.core import ejecutar
    from app.tenant import uid

    user_id = int(user_id or uid())
    anio, mes = _mes_actual()
    ejecutar(
        """
        INSERT INTO uso_ia (user_id, anio, mes, llamadas)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, anio, mes)
        DO UPDATE SET llamadas = llamadas + 1
        """,
        [user_id, anio, mes],
    )
    return llamadas_ia_mes(user_id)


def cuota_ia_ok(user_id: int | None = None, plan: str | None = None) -> bool:
    """False si Free superó ia_mensual."""
    plan = normalizar_plan(plan or plan_vigente())
    lim = limites(plan).get("ia_mensual")
    if lim is None:
        return True
    try:
        from app.tenant import uid

        uid_val = int(user_id or uid())
    except Exception:
        return True
    return llamadas_ia_mes(uid_val) < int(lim)


def marcar_coach_ia_usado(user_id: int | None = None) -> None:
    ensure_billing_schema()
    from app.db.core import ejecutar
    from app.tenant import uid

    user_id = int(user_id or uid())
    ejecutar(
        "UPDATE usuarios SET coach_ia_usado = 1 WHERE id = ?",
        [user_id],
    )
    try:
        u = st.session_state.get("user")
        if u and int(u.get("id", -1)) == user_id:
            u["coach_ia_usado"] = 1
            st.session_state.user = u
    except Exception:
        pass


def coach_ia_ya_usado(user_id: int | None = None) -> bool:
    ensure_billing_schema()
    user = st.session_state.get("user") or {}
    if user_id is None or int(user.get("id", -1)) == int(user_id or user.get("id") or 0):
        if "coach_ia_usado" in user:
            return bool(int(user.get("coach_ia_usado") or 0))
    from app.db.core import ejecutar
    from app.tenant import uid

    user_id = int(user_id or uid())
    rows = (
        ejecutar(
            "SELECT coach_ia_usado FROM usuarios WHERE id = ?",
            [user_id],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return False
    return bool(int(rows[0].get("coach_ia_usado") or 0))


def set_plan(
    user_id: int,
    plan: str,
    plan_expira_en: str | None = None,
) -> tuple[bool, str]:
    ensure_billing_schema()
    from app.db.core import ejecutar

    plan = normalizar_plan(plan)
    try:
        ejecutar(
            """
            UPDATE usuarios
            SET plan = ?, plan_expira_en = ?
            WHERE id = ?
            """,
            [plan, plan_expira_en, int(user_id)],
        )
        try:
            from app.audit import registrar

            registrar(
                "set_plan",
                "usuarios",
                user_id,
                {"plan": plan, "plan_expira_en": plan_expira_en},
            )
        except Exception:
            pass
        # refrescar sesión si es el mismo usuario
        u = st.session_state.get("user")
        if u and int(u.get("id", -1)) == int(user_id):
            u["plan"] = plan
            u["plan_expira_en"] = plan_expira_en
            st.session_state.user = u
        return True, f"Plan actualizado a {plan}"
    except Exception as e:
        log.exception("set_plan: %s", e)
        return False, "No se pudo actualizar el plan"


def resumen_plan_ui(user: dict | None = None) -> str:
    user = user or st.session_state.get("user") or {}
    plan = plan_vigente(user)
    lim = limites(plan)
    usados = 0
    try:
        usados = llamadas_ia_mes(int(user["id"])) if user.get("id") else 0
    except Exception:
        pass
    ia = lim.get("ia_mensual")
    ia_txt = "IA ilimitada" if ia is None else f"IA {usados}/{ia} este mes"
    return f"{lim['nombre']} · {ia_txt}"
