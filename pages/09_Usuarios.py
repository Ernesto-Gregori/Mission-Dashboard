"""
🔐 Usuarios — Crear y gestionar accesos a Mission Dashboard
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from app.stability import ensure_database, invalidate_data_caches
from app.database import listar_usuarios, crear_usuario
from app.auth import require_auth, panel_gestion_usuarios, logout
from app.onboarding import require_onboarding

st.set_page_config(
    page_title="Usuarios | Mission Dashboard",
    page_icon="🔐",
    layout="wide",
)

require_auth()
require_onboarding()
ensure_database()

st.title("🔐 Usuarios y seguridad")
st.caption(
    "App web multi-usuario (datos en Turso). "
    "Cada cuenta tiene plan Free / Premium / Familia. "
    "Las contraseñas se guardan con hash. "
    "Los usuarios nuevos pasan por el Coach IA al primer login. "
    "Versión HTMX: /app/usuarios"
)

user = st.session_state.get("user") or {}
st.info(
    f"Sesión actual: **{user.get('username', '—')}** · rol **{user.get('rol', '—')}**"
)

# Cualquier usuario puede ver/mejorar su plan
st.subheader("💳 Tu plan")
try:
    from app.billing import (
        PLAN_FREE,
        limites,
        plan_vigente,
        render_upgrade_buttons,
        resumen_plan_ui,
        stripe_configured,
    )

    st.caption(resumen_plan_ui(user))
    if plan_vigente(user) == PLAN_FREE:
        st.markdown(
            f"Free incluye hasta **{limites(PLAN_FREE)['modulos_max']} módulos**, "
            "Coach IA de setup y cuota mensual de IA. "
            "Premium desbloquea todo + Google Fit/Calendar."
        )
        if stripe_configured():
            render_upgrade_buttons()
        else:
            st.caption(
                "Stripe aún no está configurado en secrets "
                "(`STRIPE_SECRET_KEY`, `STRIPE_PRICE_PREMIUM`, `APP_URL`)."
            )
    else:
        st.success(f"Plan activo: **{limites(plan_vigente(user))['nombre']}**")
except Exception as e:
    st.warning(f"No se pudo cargar billing: {e}")

st.divider()

if user.get("rol") != "admin":
    st.warning("Tu cuenta no es administrador. Pide a un admin que te dé acceso o cree usuarios.")
    st.stop()

panel_gestion_usuarios()

st.divider()
st.subheader("💾 Backup")
st.caption(
    "Exporta un JSON de tablas clave a `data/backups/` "
    "(útil antes de migrar o tocar producción). "
    "También hay backup nocturno automático vía GitHub Actions → Artifacts "
    "(requiere secrets `TURSO_URL` / `TURSO_TOKEN` en el repo)."
)
if st.button("📦 Exportar backup ahora", use_container_width=True):
    from app.backup import exportar_backup_json
    path = exportar_backup_json(tag="manual")
    if path:
        st.success(f"Backup creado: `{path}`")
    else:
        st.error("No se pudo crear el backup (revisa logs).")

st.divider()
st.subheader("🧾 Auditoría reciente")
st.caption("Últimas acciones sensibles (finanzas / usuarios).")
try:
    from app.audit import listar_auditoria

    rows = listar_auditoria(limite=30)
    if not rows:
        st.info("Sin eventos de auditoría aún.")
    else:
        for r in rows:
            quien = r.get("username") or (f"user#{r.get('user_id')}" if r.get("user_id") else "—")
            st.text(
                f"{r.get('creado_en', '—')} · {quien} · "
                f"{r.get('accion')} · {r.get('entidad') or ''} "
                f"{r.get('entidad_id') or ''}"
            )
except Exception as e:
    st.warning(f"No se pudo leer auditoría: {e}")

st.divider()
col1, col2 = st.columns(2)
with col1:
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        logout()
with col2:
    st.caption("Tip: esta página aparece en el menú lateral como **Usuarios**.")
