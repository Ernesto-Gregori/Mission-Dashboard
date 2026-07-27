"""
onboarding.py — Coach IA + activación de plantillas por usuario
"""
from __future__ import annotations

import json
import re
from typing import Any

import streamlit as st

from app.database import ejecutar, invalidate_data_caches
from app.templates import (
    MODULE_TEMPLATES,
    COACH_SYSTEM,
    catalogo_para_prompt,
    claves_validas,
)
from app.tenant import uid
from app.multiuser import _ensure_user_modulos_table, MODULOS_DEFAULT


def _ensure_onboarding_column() -> None:
    try:
        ejecutar("ALTER TABLE usuarios ADD COLUMN onboarding_completo INTEGER DEFAULT 0")
    except Exception:
        pass


def usuario_onboarding_completo(user_id: int | None = None) -> bool:
    _ensure_onboarding_column()
    user_id = user_id or uid()
    rows = ejecutar(
        "SELECT onboarding_completo FROM usuarios WHERE id = ?",
        [user_id],
        fetchall=True,
    ) or []
    if not rows:
        return True
    val = rows[0].get("onboarding_completo")
    return bool(int(val or 0))


def marcar_onboarding_completo(user_id: int | None = None, done: bool = True) -> None:
    _ensure_onboarding_column()
    user_id = user_id or uid()
    ejecutar(
        "UPDATE usuarios SET onboarding_completo = ? WHERE id = ?",
        [1 if done else 0, user_id],
    )


def marcar_admins_existentes_como_onboarded() -> None:
    """Usuarios con módulos ya activos (legacy) no pasan por el coach."""
    _ensure_onboarding_column()
    _ensure_user_modulos_table(ejecutar)
    rows = ejecutar(
        """
        SELECT DISTINCT user_id FROM user_modulos
        WHERE activo = 1
        """,
        fetchall=True,
    ) or []
    for r in rows:
        ejecutar(
            """
            UPDATE usuarios SET onboarding_completo = 1
            WHERE id = ?
              AND (onboarding_completo IS NULL OR onboarding_completo = 0)
            """,
            [r["user_id"]],
        )


def aplicar_filtro_nav() -> None:
    """Oculta en el sidebar de Streamlit las páginas de módulos inactivos."""
    activos = modulos_activos()
    selectores = []
    for key, meta in MODULE_TEMPLATES.items():
        if key in activos:
            continue
        page_file = str(meta.get("page", "")).split("/")[-1]
        if page_file:
            selectores.append(
                f'[data-testid="stSidebarNav"] a[href*="{page_file}"]'
            )
    if not selectores:
        return
    css = ", ".join(selectores) + " { display: none !important; }"
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def listar_modulos_usuario(user_id: int | None = None) -> list[dict]:
    _ensure_user_modulos_table(ejecutar)
    user_id = user_id or uid()
    rows = ejecutar(
        """
        SELECT modulo, activo, config_json
        FROM user_modulos WHERE user_id = ?
        ORDER BY modulo
        """,
        [user_id],
        fetchall=True,
    ) or []
    return rows


def modulos_activos(user_id: int | None = None) -> set[str]:
    return {
        r["modulo"]
        for r in listar_modulos_usuario(user_id)
        if int(r.get("activo") or 0) == 1
    }


def modulo_activo(clave: str, user_id: int | None = None) -> bool:
    return clave in modulos_activos(user_id)


def aplicar_modulos(
    claves: list[str],
    user_id: int | None = None,
    razones: dict | None = None,
) -> None:
    _ensure_user_modulos_table(ejecutar)
    user_id = user_id or uid()
    valid = claves_validas()
    elegidos = [c for c in claves if c in valid]
    if not elegidos:
        elegidos = ["agenda"]

    # Desactivar todos, activar elegidos
    for mod in MODULOS_DEFAULT:
        ejecutar("""
            INSERT INTO user_modulos (user_id, modulo, activo, config_json)
            VALUES (?, ?, 0, '{}')
            ON CONFLICT(user_id, modulo) DO UPDATE SET activo = 0
        """, [user_id, mod])

    razones = razones or {}
    for mod in elegidos:
        cfg = json.dumps({"razon": razones.get(mod, "")}, ensure_ascii=False)
        ejecutar("""
            INSERT INTO user_modulos (user_id, modulo, activo, config_json)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id, modulo) DO UPDATE SET
                activo = 1,
                config_json = excluded.config_json
        """, [user_id, mod, cfg])

    invalidate_data_caches()


def aplicar_habitos_sugeridos(habitos: list[dict], user_id: int | None = None) -> None:
    user_id = user_id or uid()
    if not habitos:
        return
    rows = ejecutar(
        "SELECT MAX(orden) AS m FROM habitos_config WHERE user_id = ?",
        [user_id],
        fetchall=True,
    ) or [{"m": 0}]
    orden = int(rows[0]["m"] or 0)
    for h in habitos[:6]:
        clave = re.sub(r"[^a-z0-9_]", "", (h.get("clave") or "").lower().replace(" ", "_"))[:20]
        label = (h.get("label") or clave or "Hábito").strip()[:40]
        if not clave:
            clave = re.sub(r"[^a-z0-9_]", "", label.lower().replace(" ", "_"))[:20] or "habito"
        emoji = (h.get("emoji") or "⭐")[:4]
        hora = (h.get("hora") or "—")[:20]
        orden += 1
        ejecutar("""
            INSERT OR IGNORE INTO habitos_config
                (user_id, clave, label, emoji, hora, activo, orden)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, [user_id, clave, label, emoji, hora, orden])
    invalidate_data_caches()


def sugerir_con_ia(perfil: dict[str, Any]) -> dict:
    """Llama a Groq y devuelve {resumen, modulos, razones, habitos}."""
    from app.ai_client import _llamar_ai, api_key_configurada

    if not api_key_configurada():
        return _sugerencia_fallback(perfil)

    prompt = f"""Perfil del usuario:
Nombre/cómo se llama: {perfil.get('nombre', '')}
Situación: {perfil.get('situacion', '')}
Objetivos: {perfil.get('objetivos', '')}
Áreas que le importan: {', '.join(perfil.get('areas', []))}
Tiempo disponible al día (aprox): {perfil.get('tiempo', '')}
Notas: {perfil.get('notas', '')}

Módulos permitidos:
{catalogo_para_prompt()}

Elige el set mínimo útil. JSON únicamente.
"""
    raw = _llamar_ai(prompt, system=COACH_SYSTEM, max_tokens=700)
    if not raw:
        return _sugerencia_fallback(perfil)
    parsed = _parse_json(raw)
    if not parsed:
        return _sugerencia_fallback(perfil)
    return _normalizar_sugerencia(parsed, perfil)


def _parse_json(texto: str) -> dict | None:
    texto = texto.strip()
    if "```" in texto:
        parts = texto.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                texto = p
                break
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                return None
    return None


def _normalizar_sugerencia(data: dict, perfil: dict) -> dict:
    valid = claves_validas()
    mods = [m for m in (data.get("modulos") or []) if m in valid]
    if not mods:
        mods = _sugerencia_fallback(perfil)["modulos"]
    razones = data.get("razones") or {}
    if not isinstance(razones, dict):
        razones = {}
    habitos = data.get("habitos") if isinstance(data.get("habitos"), list) else []
    return {
        "resumen": (data.get("resumen") or "Aquí tienes un punto de partida.").strip(),
        "modulos": mods,
        "razones": {k: str(v) for k, v in razones.items() if k in valid},
        "habitos": habitos,
        "fuente": "ia",
    }


def _sugerencia_fallback(perfil: dict) -> dict:
    areas = set(perfil.get("areas") or [])
    mods = ["agenda"]
    razones = {"agenda": "Base para organizar tu semana."}
    mapa = {
        "dinero": "finanzas",
        "finanzas": "finanzas",
        "espiritual": "teologia",
        "devocional": "teologia",
        "estudio": "deep_work",
        "enfoque": "deep_work",
        "programacion": "deep_work",
        "lectura": "biblioteca",
        "libros": "biblioteca",
        "salud": "salud",
        "ejercicio": "salud",
        "pareja": "matrimonio",
        "matrimonio": "matrimonio",
        "ideas": "sandbox",
        "proyectos": "sandbox",
    }
    for a in areas:
        key = mapa.get(a.lower().strip())
        if key and key not in mods:
            mods.append(key)
            razones[key] = f"Lo pediste en el área «{a}»."
    # Si no marcó nada, set equilibrado corto
    if len(mods) == 1:
        mods += ["teologia", "finanzas", "salud"]
        razones.update({
            "teologia": "Base espiritual práctica.",
            "finanzas": "Visibilidad del dinero.",
            "salud": "Energía y cuerpo.",
        })
    return {
        "resumen": "Armé un set inicial según lo que compartiste (modo sin IA o IA offline).",
        "modulos": mods[:6],
        "razones": razones,
        "habitos": [
            {"clave": "devocional", "label": "Devocional", "emoji": "📖", "hora": "05:45"},
            {"clave": "movimiento", "label": "Movimiento", "emoji": "🚶", "hora": "—"},
        ],
        "fuente": "fallback",
    }


def require_module(clave: str) -> None:
    """Bloquea la página si el módulo no está activo para el usuario."""
    if usuario_onboarding_completo() and not modulo_activo(clave):
        meta = MODULE_TEMPLATES.get(clave, {})
        st.warning(
            f"El módulo **{meta.get('nombre', clave)}** no está activo en tu sistema."
        )
        st.caption("Puedes activarlo de nuevo desde el Coach o desde el dashboard.")
        if st.button("🏠 Ir al dashboard", use_container_width=True):
            st.switch_page("Mission_Dashboard.py")
        st.stop()


def require_onboarding() -> None:
    """Si el usuario no terminó el coach, muestra el flujo y detiene la página."""
    marcar_admins_existentes_como_onboarded()
    if usuario_onboarding_completo():
        aplicar_filtro_nav()
        return
    _ocultar_nav()
    render_coach()
    st.stop()


def _ocultar_nav() -> None:
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] {display: none !important;}
        </style>
    """, unsafe_allow_html=True)


def render_coach(force: bool = False) -> None:
    """UI del coach (también usable para reconfigurar)."""
    if force and usuario_onboarding_completo() and not st.session_state.get("coach_reconfig"):
        st.markdown("**Tu sistema actual**")
        activos = modulos_activos()
        if activos:
            for k in sorted(activos):
                meta = MODULE_TEMPLATES.get(k, {})
                st.markdown(f"- {meta.get('emoji', '')} **{meta.get('nombre', k)}**")
        else:
            st.caption("Ningún módulo activo.")
        if st.button("✏️ Cambiar módulos con el coach", type="primary", use_container_width=True):
            st.session_state.coach_reconfig = True
            st.session_state.coach_step = 1
            st.session_state.coach_sugerencia = None
            st.rerun()
        return

    st.title("🤖 Coach Mission Dashboard")
    st.caption("Te ayudo a armar tu sistema con plantillas según lo que necesitas.")

    if "coach_step" not in st.session_state:
        st.session_state.coach_step = 1
    if "coach_sugerencia" not in st.session_state:
        st.session_state.coach_sugerencia = None

    step = st.session_state.coach_step

    # ── Paso 1: perfil ───────────────────────────────────────
    if step == 1:
        st.subheader("1. Cuéntame de ti")
        with st.form("coach_perfil"):
            nombre = st.text_input("¿Cómo te llamo?", value=st.session_state.get("user_name", ""))
            situacion = st.text_area(
                "¿En qué etapa estás?",
                placeholder="Ej: estudiante de teología, trabajo remoto, recién casado…",
                height=80,
            )
            objetivos = st.text_area(
                "¿Qué quieres mejorar o registrar?",
                placeholder="Ej: disciplina matutina, finanzas, citas con mi esposa…",
                height=80,
            )
            areas = st.multiselect(
                "Áreas importantes ahora",
                options=[
                    "espiritual", "finanzas", "estudio", "programacion",
                    "lectura", "salud", "ejercicio", "pareja", "matrimonio",
                    "proyectos", "ideas", "enfoque",
                ],
                default=["espiritual"],
            )
            tiempo = st.selectbox(
                "Tiempo al día para el sistema",
                ["5-10 min", "15-20 min", "30+ min"],
                index=1,
            )
            notas = st.text_input("Algo más que deba saber (opcional)")
            if st.form_submit_button("Continuar →", type="primary", use_container_width=True):
                st.session_state.coach_perfil = {
                    "nombre": nombre,
                    "situacion": situacion,
                    "objetivos": objetivos,
                    "areas": areas,
                    "tiempo": tiempo,
                    "notas": notas,
                }
                with st.spinner("El coach está eligiendo plantillas…"):
                    st.session_state.coach_sugerencia = sugerir_con_ia(
                        st.session_state.coach_perfil
                    )
                st.session_state.coach_step = 2
                st.rerun()

    # ── Paso 2: sugerencia + confirmación ────────────────────
    elif step == 2:
        sug = st.session_state.coach_sugerencia or _sugerencia_fallback(
            st.session_state.get("coach_perfil") or {}
        )
        st.subheader("2. Tu sistema propuesto")
        st.info(sug.get("resumen", ""))
        if sug.get("fuente") == "fallback":
            st.caption("Sugerencia por reglas (Groq offline o sin respuesta).")
        else:
            st.caption("Sugerencia generada con Groq.")

        st.markdown("#### Módulos")
        seleccion = []
        razones = sug.get("razones") or {}
        for key, meta in MODULE_TEMPLATES.items():
            default_on = key in (sug.get("modulos") or [])
            col1, col2 = st.columns([1, 3])
            with col1:
                on = st.checkbox(
                    f"{meta['emoji']} {meta['nombre']}",
                    value=default_on,
                    key=f"coach_mod_{key}",
                )
            with col2:
                st.caption(razones.get(key) or meta["descripcion"])
            if on:
                seleccion.append(key)

        st.markdown("#### Hábitos sugeridos")
        for h in (sug.get("habitos") or [])[:6]:
            st.markdown(
                f"- {h.get('emoji', '⭐')} **{h.get('label', h.get('clave'))}** "
                f"· {h.get('hora', '—')}"
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Atrás", use_container_width=True):
                st.session_state.coach_step = 1
                st.rerun()
        with c2:
            if st.button("✅ Activar mi sistema", type="primary", use_container_width=True):
                if not seleccion:
                    st.error("Elige al menos un módulo.")
                else:
                    aplicar_modulos(seleccion, razones=razones)
                    aplicar_habitos_sugeridos(sug.get("habitos") or [])
                    marcar_onboarding_completo(True)
                    st.session_state.coach_step = 1
                    st.session_state.coach_sugerencia = None
                    st.session_state.coach_reconfig = False
                    invalidate_data_caches()
                    st.success("¡Listo! Tu sistema quedó configurado.")
                    st.balloons()
                    st.rerun()
