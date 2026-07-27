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
    import streamlit as st

    user_id = user_id or uid()
    # Cache de sesión: evita query en cada navegación
    if (
        st.session_state.get("_modulos_activos_uid") == user_id
        and isinstance(st.session_state.get("_modulos_activos"), set)
    ):
        return st.session_state["_modulos_activos"]

    activos = {
        r["modulo"]
        for r in listar_modulos_usuario(user_id)
        if int(r.get("activo") or 0) == 1
    }
    st.session_state["_modulos_activos"] = activos
    st.session_state["_modulos_activos_uid"] = user_id
    return activos


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

    # Cupo por plan (Free: máx N; agenda primero)
    try:
        from app.billing import modulos_max, plan_vigente

        tope = modulos_max(plan_vigente())
        if tope is not None and len(elegidos) > int(tope):
            if "agenda" in elegidos:
                resto = [c for c in elegidos if c != "agenda"]
                elegidos = ["agenda"] + resto[: max(0, int(tope) - 1)]
            else:
                elegidos = elegidos[: int(tope)]
    except Exception:
        pass

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

    # Invalidar cache de módulos de la sesión
    try:
        import streamlit as st
        st.session_state.pop("_modulos_activos", None)
        st.session_state.pop("_modulos_activos_uid", None)
    except Exception:
        pass
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

    try:
        from app.billing import (
            coach_ia_ya_usado,
            marcar_coach_ia_usado,
            modulos_max,
            puede_reconfigurar_coach,
            plan_vigente,
        )

        if coach_ia_ya_usado() and not puede_reconfigurar_coach():
            sug = _sugerencia_fallback(perfil)
            tope = modulos_max(plan_vigente())
            if tope:
                sug["modulos"] = sug["modulos"][: int(tope)]
            sug["fuente"] = "fallback"
            sug["resumen"] = (
                (sug.get("resumen") or "")
                + " (Free: Coach IA de setup ya usado; upgrade para reconfigurar con IA)."
            )
            return sug
    except Exception:
        pass

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
    if raw:
        try:
            from app.billing import marcar_coach_ia_usado

            marcar_coach_ia_usado()
        except Exception:
            pass
    if not raw:
        return _sugerencia_fallback(perfil)
    parsed = _parse_json(raw)
    if not parsed:
        return _sugerencia_fallback(perfil)
    sug = _normalizar_sugerencia(parsed, perfil)
    try:
        from app.billing import modulos_max, plan_vigente

        tope = modulos_max(plan_vigente())
        if tope and len(sug.get("modulos") or []) > int(tope):
            mods = sug["modulos"]
            if "agenda" in mods:
                resto = [m for m in mods if m != "agenda"]
                sug["modulos"] = ["agenda"] + resto[: max(0, int(tope) - 1)]
            else:
                sug["modulos"] = mods[: int(tope)]
            sug["resumen"] = (
                (sug.get("resumen") or "")
                + f" (ajustado al cupo Free de {tope} módulos)."
            )
    except Exception:
        pass
    return sug


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
    """Bloquea la página si el módulo no está activo / fuera del plan."""
    from app.billing import require_plan_module

    require_plan_module(clave)


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
        from app.billing import (
            PLAN_FREE,
            limites,
            plan_vigente,
            puede_reconfigurar_coach,
            render_paywall,
            resumen_plan_ui,
            stripe_link,
            PLAN_PREMIUM,
        )

        st.markdown("**Tu sistema actual**")
        st.caption(resumen_plan_ui())
        activos = modulos_activos()
        if activos:
            for k in sorted(activos):
                meta = MODULE_TEMPLATES.get(k, {})
                st.markdown(f"- {meta.get('emoji', '')} **{meta.get('nombre', k)}**")
        else:
            st.caption("Ningún módulo activo.")

        # Módulos fuera del cupo Free → upsell
        if plan_vigente() == PLAN_FREE:
            bloqueados = [k for k in MODULE_TEMPLATES if k not in activos]
            if bloqueados:
                st.markdown("#### Disponibles en Premium")
                for k in bloqueados[:6]:
                    meta = MODULE_TEMPLATES[k]
                    st.markdown(f"- {meta['emoji']} {meta['nombre']} — _{meta['descripcion']}_")
                link = stripe_link(PLAN_PREMIUM)
                if link:
                    st.link_button(
                        f"Upgrade a Premium ({limites(PLAN_PREMIUM)['precio']})",
                        link,
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.info("Premium desbloquea todos los módulos, Google Fit/Calendar y Coach ilimitado.")

        if puede_reconfigurar_coach():
            if st.button("✏️ Cambiar módulos con el coach", type="primary", use_container_width=True):
                st.session_state.coach_reconfig = True
                st.session_state.coach_step = 1
                st.session_state.coach_sugerencia = None
                st.rerun()
        else:
            st.caption("Plan Free: el Coach IA de setup es una sola vez.")
            if st.button("Desbloquear reconfiguración (Premium)", use_container_width=True):
                render_paywall(
                    "Reconfigurar el sistema con Coach IA requiere Premium o Familia.",
                    plan_sugerido=PLAN_PREMIUM,
                )
                st.stop()
        return

    st.title("🤖 Coach Mission Dashboard")
    st.caption("Te ayudo a armar tu sistema con plantillas según lo que necesitas.")
    try:
        from app.billing import modulos_max, plan_vigente, resumen_plan_ui

        st.caption(resumen_plan_ui())
        tope = modulos_max(plan_vigente())
        if tope:
            st.info(f"Tu plan Free permite hasta **{tope} módulos** activos (Agenda + los que elijas).")
    except Exception:
        pass

    if "coach_step" not in st.session_state:
        st.session_state.coach_step = 1
    if "coach_sugerencia" not in st.session_state:
        st.session_state.coach_sugerencia = None

    step = st.session_state.coach_step

    # ── Paso 1: perfil ───────────────────────────────────────
    if step == 1:
        st.subheader("1. Cuéntame de ti")
        # Form key must differ from session_state key "coach_perfil"
        with st.form("coach_perfil_form"):
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
                    try:
                        from app.billing import modulos_max, plan_vigente

                        tope = modulos_max(plan_vigente())
                        if tope and len(seleccion) > int(tope):
                            st.error(
                                f"Tu plan permite máximo {tope} módulos. "
                                f"Desmarca {len(seleccion) - int(tope)} o pasa a Premium."
                            )
                            st.stop()
                    except Exception:
                        pass
                    aplicar_modulos(seleccion, razones=razones)
                    aplicar_habitos_sugeridos(sug.get("habitos") or [])
                    marcar_onboarding_completo(True)
                    st.session_state.coach_step = 1
                    st.session_state.coach_sugerencia = None
                    st.session_state.coach_reconfig = False
                    invalidate_data_caches()
                    st.success("¡Listo! Tu sistema quedó configurado.")
                    # Upsell post-onboarding Free
                    try:
                        from app.billing import (
                            PLAN_FREE,
                            PLAN_PREMIUM,
                            limites,
                            plan_vigente,
                            stripe_link,
                        )

                        if plan_vigente() == PLAN_FREE:
                            resto = [k for k in MODULE_TEMPLATES if k not in seleccion]
                            if resto:
                                st.markdown("#### También te pueden servir (Premium)")
                                for k in resto[:4]:
                                    st.markdown(
                                        f"- {MODULE_TEMPLATES[k]['emoji']} "
                                        f"{MODULE_TEMPLATES[k]['nombre']}"
                                    )
                                link = stripe_link(PLAN_PREMIUM)
                                if link:
                                    st.link_button(
                                        f"Upgrade ({limites(PLAN_PREMIUM)['precio']})",
                                        link,
                                        use_container_width=True,
                                    )
                    except Exception:
                        pass
                    st.balloons()
                    st.rerun()
