"""
Coach insights — análisis cruzado entre módulos (briefing semanal).

No es un chatbot por sección: agrega señales de finanzas, deep work,
matrimonio, salud y hábitos, y genera 3–5 insights en una sola pasada
(LLM si hay cuota/API; si no, heurísticas).
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from app.logging_config import get_logger

log = get_logger("coach_insights")

PERIOD_DAYS_DEFAULT = 21
MAX_INSIGHTS = 5

SYSTEM_BRIEFING = (
    "Eres el Coach de Mission Dashboard. Analizas la vida del usuario con datos "
    "estructurados de varios módulos (finanzas, deep work, matrimonio, salud, hábitos). "
    "Respondes SOLO JSON válido (sin markdown) con esta forma:\n"
    '{"insights":[{"titulo":"...","cuerpo":"...","modulos":["finanzas","deep_work"]}]}\n'
    "Reglas: español, tono cercano y respetuoso (sin alarmismo en pareja/finanzas), "
    "máximo 5 insights, cada cuerpo ≤ 2 oraciones, prioriza correlaciones cruzadas "
    "entre módulos. Si hay pocos datos, di qué falta registrar en vez de inventar."
)


def ensure_coach_insights_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS coach_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            period_days INTEGER NOT NULL,
            signals_json TEXT NOT NULL,
            insights_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'heuristic'
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_coach_insights_user
        ON coach_insights(user_id, created_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS coach_briefings_uso (
            user_id INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            semana INTEGER NOT NULL,
            llamadas INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, anio, semana)
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.warning("ensure_coach_insights_schema: %s", e)


def _semana_iso(d: date | None = None) -> tuple[int, int]:
    d = d or date.today()
    iso = d.isocalendar()
    return int(iso.year), int(iso.week)


def briefings_usados_semana(user_id: int, *, ref: date | None = None) -> int:
    ensure_coach_insights_schema()
    from app.db.core import ejecutar

    anio, semana = _semana_iso(ref)
    rows = (
        ejecutar(
            """
            SELECT llamadas FROM coach_briefings_uso
            WHERE user_id = ? AND anio = ? AND semana = ?
            """,
            [int(user_id), anio, semana],
            fetchall=True,
        )
        or []
    )
    return int(rows[0]["llamadas"]) if rows else 0


def registrar_briefing(user_id: int, *, ref: date | None = None) -> int:
    ensure_coach_insights_schema()
    from app.db.core import ejecutar

    anio, semana = _semana_iso(ref)
    ejecutar(
        """
        INSERT INTO coach_briefings_uso (user_id, anio, semana, llamadas)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, anio, semana)
        DO UPDATE SET llamadas = llamadas + 1
        """,
        [int(user_id), anio, semana],
    )
    return briefings_usados_semana(user_id, ref=ref)


def limite_briefings_semana(plan: str | None = None) -> int | None:
    from app.billing import limites, normalizar_plan, plan_vigente

    plan = normalizar_plan(plan or plan_vigente())
    lim = limites(plan).get("briefings_semana")
    if lim is None:
        return None
    return int(lim)


def cuota_briefing_ok(user_id: int, plan: str | None = None) -> bool:
    lim = limite_briefings_semana(plan)
    if lim is None:
        return True
    return briefings_usados_semana(user_id) < int(lim)


def resumen_cuota_briefing(user_id: int, plan: str | None = None) -> dict[str, Any]:
    lim = limite_briefings_semana(plan)
    usados = briefings_usados_semana(user_id)
    return {
        "usados": usados,
        "limite": lim,
        "restantes": None if lim is None else max(0, int(lim) - usados),
        "ok": cuota_briefing_ok(user_id, plan),
    }


def agregar_senales(user_id: int, dias: int = PERIOD_DAYS_DEFAULT) -> dict[str, Any]:
    """Métricas compactas por módulo (sin volcar tablas al LLM)."""
    from app.db.core import ejecutar
    from app.tenant import uid as tenant_uid

    # Asegurar tenant para helpers que usan uid()
    try:
        from app.database import obtener_usuario_activo
        from app.tenant import set_current_user

        if tenant_uid() != int(user_id):
            u = obtener_usuario_activo(int(user_id))
            if u:
                set_current_user(u)
    except Exception:
        pass

    hoy = date.today()
    desde = hoy - timedelta(days=int(dias))
    desde_iso = desde.isoformat()
    hoy_iso = hoy.isoformat()
    uid_i = int(user_id)

    signals: dict[str, Any] = {
        "period_days": int(dias),
        "desde": desde_iso,
        "hasta": hoy_iso,
        "modulos": {},
    }

    # ── Finanzas ──────────────────────────────────────────────
    try:
        rows = (
            ejecutar(
                """
                SELECT sobre, COUNT(*) AS n, COALESCE(SUM(monto), 0) AS total
                FROM gastos_sobres
                WHERE user_id = ? AND fecha >= ? AND fecha <= ?
                GROUP BY sobre
                """,
                [uid_i, desde_iso, hoy_iso],
                fetchall=True,
            )
            or []
        )
        por_sobre = {
            str(r["sobre"]): {"n": int(r["n"] or 0), "total": float(r["total"] or 0)}
            for r in rows
        }
        extras = por_sobre.get("Ministerio_Extras") or por_sobre.get("Extras") or {
            "n": 0,
            "total": 0.0,
        }
        total = sum(v["total"] for v in por_sobre.values())
        signals["modulos"]["finanzas"] = {
            "gastos_total": round(total, 2),
            "extras_total": round(float(extras["total"]), 2),
            "extras_n": int(extras["n"]),
            "extras_pct": round(100.0 * float(extras["total"]) / total, 1) if total else 0.0,
            "por_sobre": {k: {"n": v["n"], "total": round(v["total"], 2)} for k, v in por_sobre.items()},
        }
    except Exception as e:
        log.debug("senales finanzas: %s", e)
        signals["modulos"]["finanzas"] = {"error": "sin_datos"}

    # ── Deep Work ─────────────────────────────────────────────
    try:
        rows = (
            ejecutar(
                """
                SELECT estado, COUNT(*) AS n
                FROM sesiones_completadas
                WHERE user_id = ? AND fecha >= ? AND fecha <= ?
                GROUP BY estado
                """,
                [uid_i, desde_iso, hoy_iso],
                fetchall=True,
            )
            or []
        )
        por_estado = {str(r["estado"] or ""): int(r["n"] or 0) for r in rows}
        total_s = sum(por_estado.values())
        completadas = int(por_estado.get("Completado") or 0)
        signals["modulos"]["deep_work"] = {
            "sesiones": total_s,
            "completadas": completadas,
            "parciales": int(por_estado.get("Parcial") or 0),
            "no_realizado": int(por_estado.get("No_realizado") or 0),
            "pct_completado": round(100.0 * completadas / total_s, 1) if total_s else None,
        }
    except Exception as e:
        log.debug("senales deep_work: %s", e)
        signals["modulos"]["deep_work"] = {"error": "sin_datos"}

    # ── Matrimonio ────────────────────────────────────────────
    try:
        habitos = (
            ejecutar(
                """
                SELECT fecha, tiempo_calidad_minutos, satisfaccion
                FROM matrimonio_habitos
                WHERE user_id = ? AND fecha >= ?
                ORDER BY fecha DESC
                """,
                [uid_i, desde_iso],
                fetchall=True,
            )
            or []
        )
        citas = (
            ejecutar(
                """
                SELECT fecha, estado_planificacion
                FROM matrimonio_citas
                WHERE user_id = ? AND fecha >= ?
                ORDER BY fecha DESC
                """,
                [uid_i, desde_iso],
                fetchall=True,
            )
            or []
        )
        ultima = habitos[0]["fecha"] if habitos else None
        dias_sin = None
        if ultima:
            try:
                dias_sin = (hoy - date.fromisoformat(str(ultima)[:10])).days
            except Exception:
                dias_sin = None
        elif not citas:
            dias_sin = int(dias)
        sats = [
            float(h["satisfaccion"])
            for h in habitos
            if h.get("satisfaccion") is not None and str(h.get("satisfaccion")) != ""
        ]
        signals["modulos"]["matrimonio"] = {
            "registros_habito": len(habitos),
            "citas": len(citas),
            "dias_sin_actividad": dias_sin,
            "satisfaccion_promedio": round(sum(sats) / len(sats), 1) if sats else None,
        }
    except Exception as e:
        log.debug("senales matrimonio: %s", e)
        signals["modulos"]["matrimonio"] = {"error": "sin_datos"}

    # ── Salud ─────────────────────────────────────────────────
    try:
        from app.db.salud import calcular_promedios, obtener_registros_rango

        regs = obtener_registros_rango(dias=int(dias))
        prom = calcular_promedios(regs) if regs else {}
        ej_dias = int(prom.get("dias_ejercicio") or 0)
        sueno = prom.get("avg_sueno")
        energia = prom.get("avg_energia_manana")
        signals["modulos"]["salud"] = {
            "registros": len(regs),
            "sueno_promedio": round(float(sueno), 1) if sueno else None,
            "dias_ejercicio": ej_dias,
            "energia_promedio": round(float(energia), 1) if energia else None,
        }
    except Exception as e:
        log.debug("senales salud: %s", e)
        signals["modulos"]["salud"] = {"error": "sin_datos"}

    # ── Hábitos (agenda) ──────────────────────────────────────
    try:
        rows = (
            ejecutar(
                """
                SELECT fecha,
                       COUNT(*) AS total,
                       COALESCE(SUM(completado), 0) AS completados
                FROM habitos_diarios_v2
                WHERE user_id = ? AND fecha >= ?
                GROUP BY fecha
                ORDER BY fecha DESC
                """,
                [uid_i, desde_iso],
                fetchall=True,
            )
            or []
        )
        dias_ok = 0
        dias_con = len(rows)
        for r in rows:
            tot = int(r["total"] or 0)
            comp = int(r["completados"] or 0)
            if tot > 0 and comp >= tot:
                dias_ok += 1
        signals["modulos"]["habitos"] = {
            "dias_con_registro": dias_con,
            "dias_completos": dias_ok,
            "pct_dias_completos": round(100.0 * dias_ok / dias_con, 1) if dias_con else None,
        }
    except Exception as e:
        log.debug("senales habitos: %s", e)
        signals["modulos"]["habitos"] = {"error": "sin_datos"}

    return signals


def _insights_heuristicos(signals: dict[str, Any]) -> list[dict[str, Any]]:
    """Correlaciones simples sin LLM — útiles offline y en tests."""
    out: list[dict[str, Any]] = []
    mods = signals.get("modulos") or {}
    fin = mods.get("finanzas") or {}
    dw = mods.get("deep_work") or {}
    mat = mods.get("matrimonio") or {}
    salud = mods.get("salud") or {}
    hab = mods.get("habitos") or {}

    extras_pct = fin.get("extras_pct")
    pct_dw = dw.get("pct_completado")
    if (
        isinstance(extras_pct, (int, float))
        and extras_pct >= 25
        and isinstance(pct_dw, (int, float))
        and pct_dw < 50
        and int(dw.get("sesiones") or 0) >= 3
    ):
        out.append(
            {
                "titulo": "Extras altos y Deep Work flojo",
                "cuerpo": (
                    f"En este periodo, «extras» fue ~{extras_pct:.0f}% del gasto y solo "
                    f"completaste ~{pct_dw:.0f}% del Deep Work. Vale la pena mirar si el "
                    "gasto impulsivo coincide con semanas de menos foco."
                ),
                "modulos": ["finanzas", "deep_work"],
            }
        )

    dias_sin = mat.get("dias_sin_actividad")
    if isinstance(dias_sin, int) and dias_sin >= 14:
        cuerpo = (
            f"Llevas ~{dias_sin} días sin registrar actividad en Matrimonio. "
            "Un bloque corto de calidad esta semana puede romper la racha."
        )
        mods_i = ["matrimonio"]
        if isinstance(extras_pct, (int, float)) and extras_pct >= 30:
            cuerpo += (
                " Además, el sobre de extras está elevado: si el estrés financiero "
                "pesa, conviene nombrarlo en pareja con calma."
            )
            mods_i.append("finanzas")
        out.append(
            {
                "titulo": "Poca señal en Matrimonio",
                "cuerpo": cuerpo,
                "modulos": mods_i,
            }
        )

    sueno = salud.get("sueno_promedio")
    if isinstance(sueno, (int, float)) and sueno > 0 and sueno < 6.5 and int(salud.get("registros") or 0) >= 5:
        out.append(
            {
                "titulo": "Sueño por debajo del objetivo",
                "cuerpo": (
                    f"Promedio de sueño ~{sueno:.1f} h en el periodo. "
                    "Si el Deep Work o el ánimo bajan, empezar por dormir 7+ suele rendir más que otro hábito."
                ),
                "modulos": ["salud", "deep_work"],
            }
        )

    ej = salud.get("dias_ejercicio")
    if isinstance(ej, int) and ej == 0 and int(salud.get("registros") or 0) >= 7:
        out.append(
            {
                "titulo": "Sin días de ejercicio registrados",
                "cuerpo": (
                    "En estas semanas no hay ejercicio marcado en Salud. "
                    "Una sesión corta y fija (aunque sea caminata) suele mejorar energía y constancia."
                ),
                "modulos": ["salud"],
            }
        )

    pct_hab = hab.get("pct_dias_completos")
    if isinstance(pct_hab, (int, float)) and pct_hab < 40 and int(hab.get("dias_con_registro") or 0) >= 7:
        out.append(
            {
                "titulo": "Hábitos a medias",
                "cuerpo": (
                    f"Solo ~{pct_hab:.0f}% de los días con registro quedaron completos. "
                    "Reduce a 2–3 hábitos clave esta semana en vez de ampliar la lista."
                ),
                "modulos": ["agenda"],
            }
        )

    if not out:
        faltan = [
            k
            for k, v in mods.items()
            if isinstance(v, dict)
            and (
                v.get("error")
                or (
                    k == "finanzas"
                    and float(v.get("gastos_total") or 0) == 0
                )
                or (k == "deep_work" and int(v.get("sesiones") or 0) == 0)
                or (k == "salud" and int(v.get("registros") or 0) < 3)
                or (k == "matrimonio" and int(v.get("registros_habito") or 0) == 0 and int(v.get("citas") or 0) == 0)
            )
        ]
        if faltan:
            out.append(
                {
                    "titulo": "Aún faltan datos para cruzar",
                    "cuerpo": (
                        "El Coach necesita más registros recientes en: "
                        + ", ".join(faltan)
                        + ". Con 2–3 semanas de datos aparecen correlaciones reales entre módulos."
                    ),
                    "modulos": faltan[:4],
                }
            )
        else:
            out.append(
                {
                    "titulo": "Periodo estable",
                    "cuerpo": (
                        "No hay alertas fuertes entre módulos esta quincena. "
                        "Mantén el ritmo y revisa el briefing la próxima semana."
                    ),
                    "modulos": ["agenda"],
                }
            )

    return out[:MAX_INSIGHTS]


def _parse_insights_llm(texto: str) -> list[dict[str, Any]] | None:
    if not texto:
        return None
    raw = texto.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    items = data.get("insights") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[dict[str, Any]] = []
    for it in items[:MAX_INSIGHTS]:
        if not isinstance(it, dict):
            continue
        titulo = str(it.get("titulo") or "").strip()
        cuerpo = str(it.get("cuerpo") or "").strip()
        if not titulo or not cuerpo:
            continue
        mods = it.get("modulos") or []
        if not isinstance(mods, list):
            mods = []
        out.append(
            {
                "titulo": titulo[:120],
                "cuerpo": cuerpo[:400],
                "modulos": [str(x)[:40] for x in mods[:6]],
            }
        )
    return out or None


def _llamar_llm_briefing(signals: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Una sola llamada; no usa la cuota de chat mensual (solo briefing)."""
    from app.ai_client import _get_client, _hay_cuota, _registrar_llamada, api_key_configurada

    if not api_key_configurada() or not _hay_cuota():
        return None
    client = _get_client()
    if not client:
        return None

    # Compactar señales para el prompt
    compact = {
        "period_days": signals.get("period_days"),
        "modulos": signals.get("modulos"),
    }
    prompt = (
        "Con estas señales agregadas del usuario, genera insights cruzados.\n"
        f"DATOS:\n{json.dumps(compact, ensure_ascii=False)}"
    )
    try:
        from app.ai_client import MODELO

        response = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_BRIEFING},
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
        )
        _registrar_llamada()
        texto = response.choices[0].message.content
        return _parse_insights_llm(texto or "")
    except Exception as e:
        log.warning("llm briefing falló: %s", e)
        return None


def guardar_briefing(
    user_id: int,
    signals: dict[str, Any],
    insights: list[dict[str, Any]],
    source: str,
) -> int:
    ensure_coach_insights_schema()
    from app.db.core import ejecutar

    from datetime import datetime, timezone

    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    row_id = ejecutar(
        """
        INSERT INTO coach_insights
            (user_id, created_at, period_days, signals_json, insights_json, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            int(user_id),
            created,
            int(signals.get("period_days") or PERIOD_DAYS_DEFAULT),
            json.dumps(signals, ensure_ascii=False),
            json.dumps(insights, ensure_ascii=False),
            str(source),
        ],
    )
    return int(row_id or 0)


def ultimo_briefing(user_id: int) -> dict[str, Any] | None:
    ensure_coach_insights_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            """
            SELECT id, user_id, created_at, period_days, signals_json, insights_json, source
            FROM coach_insights
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return None
    return _row_briefing(rows[0])


def listar_briefings(user_id: int, limite: int = 5) -> list[dict[str, Any]]:
    ensure_coach_insights_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            """
            SELECT id, user_id, created_at, period_days, signals_json, insights_json, source
            FROM coach_insights
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            [int(user_id), int(limite)],
            fetchall=True,
        )
        or []
    )
    return [_row_briefing(r) for r in rows]


def _row_briefing(r: dict) -> dict[str, Any]:
    try:
        insights = json.loads(r.get("insights_json") or "[]")
    except Exception:
        insights = []
    try:
        signals = json.loads(r.get("signals_json") or "{}")
    except Exception:
        signals = {}
    return {
        "id": r.get("id"),
        "user_id": r.get("user_id"),
        "created_at": r.get("created_at"),
        "period_days": r.get("period_days"),
        "insights": insights if isinstance(insights, list) else [],
        "signals": signals if isinstance(signals, dict) else {},
        "source": r.get("source") or "heuristic",
    }


def generar_briefing(
    user_id: int,
    *,
    plan: str | None = None,
    dias: int = PERIOD_DAYS_DEFAULT,
    force: bool = False,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Genera y persiste un briefing cruzado.
    Retorna (ok, mensaje, briefing|None).
    """
    ensure_coach_insights_schema()
    user_id = int(user_id)

    if not force and not cuota_briefing_ok(user_id, plan):
        cuota = resumen_cuota_briefing(user_id, plan)
        return (
            False,
            f"Cupo de briefings de esta semana agotado ({cuota['usados']}/{cuota['limite']}).",
            None,
        )

    signals = agregar_senales(user_id, dias=dias)
    insights = _llamar_llm_briefing(signals)
    source = "llm"
    if not insights:
        insights = _insights_heuristicos(signals)
        source = "heuristic"

    briefing_id = guardar_briefing(user_id, signals, insights, source)
    if not force:
        registrar_briefing(user_id)

    briefing = ultimo_briefing(user_id)
    if briefing is None and briefing_id:
        briefing = {
            "id": briefing_id,
            "insights": insights,
            "signals": signals,
            "source": source,
            "period_days": dias,
            "created_at": date.today().isoformat(),
        }
    return True, "Briefing generado", briefing
