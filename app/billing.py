"""
billing.py — Planes Free / Premium / Familia (app web).

Stripe Checkout (Streamlit) + webhook FastAPI (webhook/main.py)
actualizan usuarios.plan en Turso.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

try:
    import streamlit as st
except ImportError:
    st = None

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
        "ALTER TABLE usuarios ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE usuarios ADD COLUMN stripe_subscription_id TEXT",
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

    # Grandfather: todo admin tiene al menos Premium (dueño de la app)
    try:
        ejecutar(
            """
            UPDATE usuarios
            SET plan = 'premium', plan_expira_en = NULL
            WHERE rol = 'admin'
              AND COALESCE(LOWER(TRIM(plan)), 'free') NOT IN ('premium', 'familia')
            """
        )
        ejecutar(
            """
            UPDATE usuarios
            SET plan_expira_en = NULL
            WHERE rol = 'admin'
              AND plan_expira_en IS NOT NULL
            """
        )
        ejecutar(
            """
            UPDATE usuarios
            SET plan = 'free'
            WHERE (plan IS NULL OR plan = '')
              AND COALESCE(rol, 'usuario') != 'admin'
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


def es_admin(user: dict | None = None) -> bool:
    """True si el usuario es administrador (dueño)."""
    if user is None and st is not None:
        try:
            user = st.session_state.get("user") or {}
        except Exception:
            user = {}
    user = user or {}
    if str(user.get("rol") or "").lower() == "admin":
        return True
    try:
        from app.tenant import current_user

        cu = current_user() or {}
        return str(cu.get("rol") or "").lower() == "admin"
    except Exception:
        return False


def plan_vigente(user: dict | None = None) -> str:
    """
    Plan efectivo del usuario.

    - Admin: siempre Premium (o Familia si ya lo tiene). Sin expiración.
    - Otros: si plan_expira_en pasó → free.
    """
    ensure_billing_schema()
    if user is None and st is not None:
        try:
            user = st.session_state.get("user") or {}
        except Exception:
            user = {}
    user = user or {}

    # Dueño / admin: acceso completo a lo Premium (Google, módulos ilimitados, IA…)
    if str(user.get("rol") or "").lower() == "admin":
        plan = normalizar_plan(user.get("plan"))
        if plan == PLAN_FAMILIA:
            return PLAN_FAMILIA
        return PLAN_PREMIUM

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


def _secret(name: str, default: str = "") -> str:
    """Lee secret unificado (Streamlit / env / secrets.toml)."""
    from app.secrets import get_secret

    return get_secret(name, default)


def stripe_configured() -> bool:
    return bool(_secret("STRIPE_SECRET_KEY") and (
        _secret("STRIPE_PRICE_PREMIUM")
        or _secret("STRIPE_LINK_PREMIUM")
        or _secret("STRIPE_PRICE_FAMILIA")
        or _secret("STRIPE_LINK_FAMILIA")
    ))


def stripe_link(plan_destino: str) -> str:
    """Payment Link estático (fallback). Preferir Checkout Session."""
    key = {
        PLAN_PREMIUM: "STRIPE_LINK_PREMIUM",
        PLAN_FAMILIA: "STRIPE_LINK_FAMILIA",
    }.get(normalizar_plan(plan_destino), "")
    if not key:
        return ""
    return _secret(key)


def stripe_price_id(plan_destino: str) -> str:
    key = {
        PLAN_PREMIUM: "STRIPE_PRICE_PREMIUM",
        PLAN_FAMILIA: "STRIPE_PRICE_FAMILIA",
    }.get(normalizar_plan(plan_destino), "")
    return _secret(key) if key else ""


def app_base_url() -> str:
    """URL pública de la app (success/cancel de Checkout)."""
    url = _secret("APP_URL") or _secret("STREAMLIT_APP_URL")
    if url:
        return url.rstrip("/")
    if st is not None:
        try:
            # Streamlit ≥1.30
            return st.get_option("browser.serverAddress") or ""
        except Exception:
            pass
    return ""


def crear_checkout_session(
    plan_destino: str,
    user_id: int,
    *,
    username: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Crea Stripe Checkout Session (subscription).
    Retorna (url, error).
    """
    plan_destino = normalizar_plan(plan_destino)
    if plan_destino == PLAN_FREE:
        return None, "Plan Free no requiere pago"

    secret = _secret("STRIPE_SECRET_KEY")
    price = stripe_price_id(plan_destino)
    if not secret:
        return None, "Falta STRIPE_SECRET_KEY en secrets"
    if not price:
        # Fallback: payment link
        link = stripe_link(plan_destino)
        if link:
            sep = "&" if "?" in link else "?"
            return f"{link}{sep}client_reference_id={int(user_id)}", None
        return None, f"Falta STRIPE_PRICE_{plan_destino.upper()} o STRIPE_LINK_*"

    try:
        import stripe
    except ImportError:
        return None, "Instala el paquete stripe (requirements.txt)"

    stripe.api_key = secret
    base = app_base_url() or "https://localhost"
    success = f"{base}/?checkout=success&plan={plan_destino}"
    cancel = f"{base}/?checkout=cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=success,
            cancel_url=cancel,
            client_reference_id=str(int(user_id)),
            metadata={
                "user_id": str(int(user_id)),
                "plan": plan_destino,
                "username": username or "",
            },
            subscription_data={
                "metadata": {
                    "user_id": str(int(user_id)),
                    "plan": plan_destino,
                }
            },
            allow_promotion_codes=True,
        )
        return session.url, None
    except Exception as e:
        log.exception("crear_checkout_session: %s", e)
        return None, str(e)[:200]


def render_upgrade_buttons(plan_sugerido: str = PLAN_PREMIUM) -> None:
    """CTA de pago: Checkout Session o Payment Link."""
    if st is None:
        return
    user = st.session_state.get("user") or {}
    uid = user.get("id")
    planes = [plan_sugerido]
    if plan_sugerido == PLAN_PREMIUM:
        planes = [PLAN_PREMIUM, PLAN_FAMILIA]

    for plan in planes:
        lim = limites(plan)
        label = f"Upgrade a {lim['nombre']} ({lim['precio']})"
        if st.button(label, type="primary", use_container_width=True, key=f"upgrade_{plan}"):
            if not uid:
                st.error("Inicia sesión para pagar.")
                return
            url, err = crear_checkout_session(
                plan, int(uid), username=user.get("username")
            )
            if url:
                st.markdown(f"[Continuar al pago seguro en Stripe →]({url})")
                st.link_button("Abrir Stripe Checkout", url, use_container_width=True)
            else:
                st.error(err or "No se pudo crear el checkout")
                if st.session_state.get("user", {}).get("rol") == "admin":
                    st.caption("Admin: asigna el plan manualmente en Usuarios mientras configuras Stripe.")


def render_paywall(
    motivo: str,
    *,
    modulo: str | None = None,
    plan_sugerido: str = PLAN_PREMIUM,
) -> None:
    """Bloqueo amable + CTA de upgrade (Stripe Checkout)."""
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
    if stripe_configured():
        render_upgrade_buttons(plan_sugerido)
    else:
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
                "Los cobros con Stripe se activan cuando configures "
                "`STRIPE_SECRET_KEY` + `STRIPE_PRICE_PREMIUM` (y el webhook). "
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
    from app.tenant import current_user, set_current_user, uid

    user_id = int(user_id or uid())
    ejecutar(
        "UPDATE usuarios SET coach_ia_usado = 1 WHERE id = ?",
        [user_id],
    )
    # Refrescar contextvar / session_state si aplica
    try:
        u = current_user()
        if u and int(u.get("id", -1)) == user_id:
            u = dict(u)
            u["coach_ia_usado"] = 1
            set_current_user(u)
    except Exception:
        pass
    if st is not None:
        try:
            u = st.session_state.get("user")
            if u and int(u.get("id", -1)) == user_id:
                u["coach_ia_usado"] = 1
                st.session_state.user = u
        except Exception:
            pass


def coach_ia_ya_usado(user_id: int | None = None) -> bool:
    ensure_billing_schema()
    from app.tenant import current_user, uid

    user = current_user() or {}
    if st is not None and not user:
        try:
            user = st.session_state.get("user") or {}
        except Exception:
            user = {}
    if user_id is None or int(user.get("id", -1)) == int(user_id or user.get("id") or 0):
        if "coach_ia_usado" in user:
            return bool(int(user.get("coach_ia_usado") or 0))
    from app.db.core import ejecutar

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
    *,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> tuple[bool, str]:
    ensure_billing_schema()
    from app.db.core import ejecutar

    plan = normalizar_plan(plan)
    try:
        # Construir UPDATE dinámico para no pisar stripe ids si no vienen
        sets = ["plan = ?", "plan_expira_en = ?"]
        params: list[Any] = [plan, plan_expira_en]
        if stripe_customer_id is not None:
            sets.append("stripe_customer_id = ?")
            params.append(stripe_customer_id)
        if stripe_subscription_id is not None:
            sets.append("stripe_subscription_id = ?")
            params.append(stripe_subscription_id)
        params.append(int(user_id))
        ejecutar(
            f"UPDATE usuarios SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        try:
            from app.audit import registrar

            registrar(
                "set_plan",
                "usuarios",
                user_id,
                {
                    "plan": plan,
                    "plan_expira_en": plan_expira_en,
                    "stripe_customer_id": stripe_customer_id,
                    "stripe_subscription_id": stripe_subscription_id,
                },
            )
        except Exception:
            pass
        # refrescar sesión si es el mismo usuario
        if st is not None:
            try:
                u = st.session_state.get("user")
                if u and int(u.get("id", -1)) == int(user_id):
                    u["plan"] = plan
                    u["plan_expira_en"] = plan_expira_en
                    st.session_state.user = u
            except Exception:
                pass
        return True, f"Plan actualizado a {plan}"
    except Exception as e:
        log.exception("set_plan: %s", e)
        return False, "No se pudo actualizar el plan"


def plan_desde_price_id(price_id: str | None) -> str | None:
    """Mapea price_id de Stripe → plan interno."""
    if not price_id:
        return None
    price_id = price_id.strip()
    if price_id and price_id == stripe_price_id(PLAN_PREMIUM):
        return PLAN_PREMIUM
    if price_id and price_id == stripe_price_id(PLAN_FAMILIA):
        return PLAN_FAMILIA
    # Env sin Streamlit (webhook)
    import os

    if price_id == (os.getenv("STRIPE_PRICE_PREMIUM") or "").strip():
        return PLAN_PREMIUM
    if price_id == (os.getenv("STRIPE_PRICE_FAMILIA") or "").strip():
        return PLAN_FAMILIA
    return None


def aplicar_evento_checkout(session: dict) -> tuple[bool, str]:
    """
    Aplica checkout.session.completed (dict JSON de Stripe).
    Usado por el webhook FastAPI.
    """
    ensure_billing_schema()
    from app.db.core import ejecutar

    meta = session.get("metadata") or {}
    user_id = session.get("client_reference_id") or meta.get("user_id")
    plan = (meta.get("plan") or "").strip().lower()

    # Inferir plan desde line items / price si falta metadata
    if plan not in PLANES_VALIDOS or plan == PLAN_FREE:
        plan = None
        # session from webhook expanded? try amount lookup via price in metadata
        for key in ("price_id", "stripe_price"):
            inferred = plan_desde_price_id(meta.get(key))
            if inferred:
                plan = inferred
                break

    if not plan:
        # Último recurso: mirar display name / mode subscription + default premium
        plan = PLAN_PREMIUM

    if not user_id:
        return False, "checkout sin client_reference_id / user_id"

    try:
        user_id_i = int(user_id)
    except Exception:
        return False, f"user_id inválido: {user_id}"

    customer = session.get("customer")
    subscription = session.get("subscription")
    if isinstance(customer, dict):
        customer = customer.get("id")
    if isinstance(subscription, dict):
        subscription = subscription.get("id")

    ok, msg = set_plan(
        user_id_i,
        plan,
        stripe_customer_id=str(customer) if customer else None,
        stripe_subscription_id=str(subscription) if subscription else None,
    )
    return ok, msg


def aplicar_cancelacion_subscription(subscription: dict) -> tuple[bool, str]:
    """customer.subscription.deleted → vuelve a free."""
    ensure_billing_schema()
    from app.db.core import ejecutar

    sub_id = subscription.get("id")
    meta = subscription.get("metadata") or {}
    user_id = meta.get("user_id")

    if not user_id and sub_id:
        rows = (
            ejecutar(
                "SELECT id FROM usuarios WHERE stripe_subscription_id = ?",
                [sub_id],
                fetchall=True,
            )
            or []
        )
        if rows:
            user_id = rows[0]["id"]

    if not user_id:
        return False, "cancelación sin user_id ni subscription conocida"

    return set_plan(
        int(user_id),
        PLAN_FREE,
        stripe_subscription_id="",
    )


def resumen_plan_ui(user: dict | None = None) -> str:
    user = user or (st.session_state.get("user") if st is not None else {}) or {}
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
