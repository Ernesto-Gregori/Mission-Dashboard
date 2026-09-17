"""Asistente Alma — chat Groq con contexto opt-in del dashboard."""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy

log = get_logger("asistente")

CATEGORIAS = ("habitos", "tareas", "salud", "calendario")
MAX_MENSAJE = 2000
MAX_HISTORIAL_UI = 40
MAX_HISTORIAL_LLM = 16
MAX_CONTEXTO = 2800

SYSTEM_ALMA = (
    "Eres Alma, la asistente personal de Mission Dashboard. "
    "Hablas en español, con calidez breve y concreta: priorizás, proponés el siguiente paso "
    "y no inventás datos que el usuario no te haya autorizado a ver. "
    "Si no hay contexto compartido, preguntá qué necesita y no asumas hábitos, salud ni agenda. "
    "No menciones API keys, tokens ni detalles internos del sistema."
)


def ensure_asistente_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS asistente_mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('user', 'assistant')),
            contenido TEXT NOT NULL,
            contexto_json TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_asistente_msg_user
        ON asistente_mensajes(user_id, creado_en)
        """,
        """
        CREATE TABLE IF NOT EXISTS asistente_prefs (
            user_id INTEGER PRIMARY KEY,
            share_habitos INTEGER NOT NULL DEFAULT 0,
            share_tareas INTEGER NOT NULL DEFAULT 0,
            share_salud INTEGER NOT NULL DEFAULT 0,
            share_calendario INTEGER NOT NULL DEFAULT 0,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id INTEGER PRIMARY KEY,
            week_start TEXT NOT NULL DEFAULT 'lun',
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.warning("ensure_asistente_schema: %s", e)


def _uid(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def prefs_default() -> dict[str, bool]:
    return {k: False for k in CATEGORIAS}


def obtener_prefs(user_id: int | None = None) -> dict[str, bool]:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    rows = (
        ejecutar(
            """
            SELECT share_habitos, share_tareas, share_salud, share_calendario
            FROM asistente_prefs WHERE user_id = ?
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return prefs_default()
    r = rows[0]
    return {
        "habitos": bool(int(r.get("share_habitos") or 0)),
        "tareas": bool(int(r.get("share_tareas") or 0)),
        "salud": bool(int(r.get("share_salud") or 0)),
        "calendario": bool(int(r.get("share_calendario") or 0)),
    }


def guardar_prefs(flags: dict[str, Any], user_id: int | None = None) -> dict[str, bool]:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    clean = {
        "habitos": bool(flags.get("habitos")),
        "tareas": bool(flags.get("tareas")),
        "salud": bool(flags.get("salud")),
        "calendario": bool(flags.get("calendario")),
    }
    ejecutar(
        """
        INSERT INTO asistente_prefs
            (user_id, share_habitos, share_tareas, share_salud, share_calendario)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            share_habitos = excluded.share_habitos,
            share_tareas = excluded.share_tareas,
            share_salud = excluded.share_salud,
            share_calendario = excluded.share_calendario,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [
            uid_i,
            int(clean["habitos"]),
            int(clean["tareas"]),
            int(clean["salud"]),
            int(clean["calendario"]),
        ],
    )
    return clean


def flags_desde_form(form) -> dict[str, bool]:
    def _on(name: str) -> bool:
        raw = form.get(name) if hasattr(form, "get") else None
        return str(raw or "").lower() in ("1", "on", "true", "yes")

    return {
        "habitos": _on("share_habitos"),
        "tareas": _on("share_tareas"),
        "salud": _on("share_salud"),
        "calendario": _on("share_calendario"),
    }


def listar_mensajes(user_id: int | None = None, limite: int = MAX_HISTORIAL_UI) -> list[dict]:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    rows = (
        ejecutar(
            """
            SELECT id, rol, contenido, contexto_json, creado_en
            FROM asistente_mensajes
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            [uid_i, int(limite)],
            fetchall=True,
        )
        or []
    )
    out = list(reversed(rows))
    for m in out:
        raw = m.get("contexto_json")
        cats: list[str] = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    cats = [str(x) for x in parsed if str(x) in CATEGORIAS]
                elif isinstance(parsed, dict):
                    cats = [k for k, v in parsed.items() if v and k in CATEGORIAS]
            except Exception:
                cats = []
        m["categorias"] = cats
    return out


def guardar_mensaje(
    rol: str,
    contenido: str,
    *,
    categorias: list[str] | None = None,
    user_id: int | None = None,
) -> int:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    if rol not in ("user", "assistant"):
        raise ValueError("rol inválido")
    texto = (contenido or "").strip()[:MAX_MENSAJE]
    if not texto:
        raise ValueError("contenido vacío")
    cats = [c for c in (categorias or []) if c in CATEGORIAS]
    return ejecutar(
        """
        INSERT INTO asistente_mensajes (user_id, rol, contenido, contexto_json)
        VALUES (?, ?, ?, ?)
        """,
        [_uid(user_id), rol, texto, json.dumps(cats) if cats else None],
    )


def borrar_historial(user_id: int | None = None) -> None:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    ejecutar("DELETE FROM asistente_mensajes WHERE user_id = ?", [_uid(user_id)])
    log.info("asistente.historial_borrado user_id=%s", _uid(user_id))


def obtener_week_start(user_id: int | None = None) -> str:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            "SELECT week_start FROM user_prefs WHERE user_id = ?",
            [_uid(user_id)],
            fetchall=True,
        )
        or []
    )
    val = str(rows[0]["week_start"]) if rows else "lun"
    return val if val in ("lun", "dom") else "lun"


def guardar_week_start(valor: str, user_id: int | None = None) -> str:
    ensure_asistente_schema()
    from app.db.core import ejecutar

    clean = "dom" if str(valor).lower().startswith("dom") else "lun"
    ejecutar(
        """
        INSERT INTO user_prefs (user_id, week_start)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            week_start = excluded.week_start,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [_uid(user_id), clean],
    )
    return clean


def _trunc(texto: str, n: int = 700) -> str:
    t = (texto or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def construir_contexto(flags: dict[str, bool], user_id: int | None = None) -> str:
    """Arma el bloque de datos reales. Vacío si no hay categorías activas."""
    activas = [k for k in CATEGORIAS if flags.get(k)]
    if not activas:
        return ""

    uid_i = _uid(user_id)
    partes: list[str] = ["Datos que el usuario autorizó compartir:"]
    if "habitos" in activas:
        partes.append(_ctx_habitos(uid_i))
    if "tareas" in activas:
        partes.append(_ctx_tareas(uid_i))
    if "salud" in activas:
        partes.append(_ctx_salud())
    if "calendario" in activas:
        partes.append(_ctx_calendario(uid_i))
    texto = "\n\n".join(partes)
    return texto[:MAX_CONTEXTO]


def _ctx_habitos(uid_i: int) -> str:
    from app.db.core import ejecutar

    desde = (_hoy() - timedelta(days=7)).isoformat()
    rows = (
        ejecutar(
            """
            SELECT d.fecha, d.completado, COALESCE(c.label, d.habito_clave) AS label,
                   COALESCE(c.emoji, '⭐') AS emoji
            FROM habitos_diarios_v2 d
            LEFT JOIN habitos_config c
              ON c.clave = d.habito_clave AND c.user_id = d.user_id
            WHERE d.user_id = ? AND d.fecha >= ?
            ORDER BY d.fecha DESC, d.habito_clave
            LIMIT 40
            """,
            [uid_i, desde],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return "Hábitos (7 días): sin registros."
    lineas = ["Hábitos (7 días):"]
    for r in rows[:20]:
        mark = "sí" if r.get("completado") else "no"
        lineas.append(f"- {r.get('fecha')}: {r.get('emoji') or ''} {r.get('label')} → {mark}")
    return "\n".join(lineas)


def _ctx_tareas(uid_i: int) -> str:
    from app.db.core import ejecutar

    hoy = str(_hoy())
    incompletos = (
        ejecutar(
            """
            SELECT COALESCE(c.label, d.habito_clave) AS label
            FROM habitos_config c
            LEFT JOIN habitos_diarios_v2 d
              ON d.habito_clave = c.clave AND d.user_id = c.user_id AND d.fecha = ?
            WHERE c.user_id = ? AND COALESCE(c.activo, 1) = 1
              AND COALESCE(d.completado, 0) = 0
            ORDER BY c.orden, c.label
            LIMIT 12
            """,
            [hoy, uid_i],
            fetchall=True,
        )
        or []
    )
    proximos = (
        ejecutar(
            """
            SELECT fecha, hora_inicio, titulo
            FROM eventos_calendario
            WHERE user_id = ? AND fecha >= ? AND COALESCE(fuente, 'local') = 'local'
            ORDER BY fecha, hora_inicio
            LIMIT 8
            """,
            [uid_i, hoy],
            fetchall=True,
        )
        or []
    )
    bit = (
        ejecutar(
            """
            SELECT pendientes_soltar FROM bitacora_semanal
            WHERE user_id = ? AND COALESCE(pendientes_soltar, '') != ''
            ORDER BY semana_inicio DESC LIMIT 1
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )
    lineas = ["Tareas pendientes:"]
    if incompletos:
        lineas.append("Hábitos de hoy sin completar: " + ", ".join(r["label"] for r in incompletos))
    else:
        lineas.append("Hábitos de hoy: ninguno pendiente (o sin hábitos configurados).")
    if proximos:
        lineas.append("Bloques/eventos locales próximos:")
        for e in proximos:
            hora = (e.get("hora_inicio") or "")[:5]
            lineas.append(f"- {e.get('fecha')} {hora} {e.get('titulo')}")
    if bit and bit[0].get("pendientes_soltar"):
        lineas.append("Bitácora pendientes: " + _trunc(str(bit[0]["pendientes_soltar"]), 240))
    return "\n".join(lineas)


def _ctx_salud() -> str:
    from app.db.salud import calcular_promedios, construir_contexto_salud, obtener_registros_rango

    regs = obtener_registros_rango(14)
    stats = calcular_promedios(regs)
    return "Salud (14 días):\n" + construir_contexto_salud(regs, stats)


def _ctx_calendario(uid_i: int) -> str:
    from app.db.agenda import obtener_eventos_semana, obtener_lunes_semana

    lunes = obtener_lunes_semana()
    domingo = lunes + timedelta(days=6)
    try:
        eventos = obtener_eventos_semana(lunes, domingo) or []
    except Exception as e:
        log.warning("asistente.calendario user_id=%s err=%s", uid_i, e)
        eventos = []
    if not eventos:
        return "Calendario de esta semana: sin eventos."
    lineas = [f"Calendario {lunes.isoformat()} – {domingo.isoformat()}:"]
    for e in eventos[:18]:
        fuente = e.get("fuente") or ("google_calendar" if e.get("google_id") else "local")
        hora = (e.get("hora_inicio") or "")[:5]
        lineas.append(f"- {e.get('fecha')} {hora} {e.get('titulo')} [{fuente}]")
    return "\n".join(lineas)


def responder(mensaje: str, flags: dict[str, bool], user_id: int | None = None) -> str:
    """Guarda el turno del usuario, llama a Groq y persiste la respuesta."""
    from app.ai_client import chat_con_historial

    texto = (mensaje or "").strip()[:MAX_MENSAJE]
    if not texto:
        raise ValueError("Escribe un mensaje.")
    uid_i = _uid(user_id)
    cats = [k for k in CATEGORIAS if flags.get(k)]
    guardar_prefs(flags, user_id=uid_i)
    guardar_mensaje("user", texto, categorias=cats, user_id=uid_i)

    ctx = construir_contexto(flags, user_id=uid_i)
    system = SYSTEM_ALMA
    if ctx:
        system = SYSTEM_ALMA + "\n\n" + ctx
    else:
        system = (
            SYSTEM_ALMA
            + "\n\nEl usuario no autorizó categorías de datos. "
            "No asumas hábitos, tareas, salud ni calendario."
        )

    prev = listar_mensajes(uid_i, limite=MAX_HISTORIAL_LLM + 2)
    historial = []
    for m in prev:
        if m.get("rol") == "user" and (m.get("contenido") or "").strip() == texto:
            continue  # el prompt actual va aparte
        historial.append({"role": m.get("rol"), "content": m.get("contenido") or ""})
    historial = historial[-MAX_HISTORIAL_LLM:]

    log.info("asistente.mensaje user_id=%s categorias=%s chars=%s", uid_i, cats, len(texto))
    reply = chat_con_historial(texto, contexto=system, historial=historial, max_tokens=700)
    reply = (reply or "Sin respuesta de Alma.").strip()[:MAX_MENSAJE]
    guardar_mensaje("assistant", reply, categorias=cats, user_id=uid_i)
    return reply
