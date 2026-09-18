"""Coach IA: arma y mejora una rutina semanal a partir de la biblioteca."""
from __future__ import annotations

import json

from app.ai_client import api_key_configurada, chat_simple, last_ai_error
from app.db.exercises import listar_exercises
from app.exercise_analysis import extract_json_object
from app.logging_config import get_logger

log = get_logger("exercise_routine")

SYSTEM_COACH_RUTINA = (
    "Eres un coach de fuerza y acondicionamiento. Hablas español, eres concreto "
    "y armás rutinas que se pueden seguir como en una app de entrenamiento: "
    "días, ejercicios, series, repeticiones y descanso. "
    "No recetes suplementos ni dietas. No inventes máquinas que el usuario no tiene."
)

MAX_DIAS = 7
MIN_DIAS = 1
MIN_MINUTOS = 15
MAX_MINUTOS = 120


class RoutineError(ValueError):
    """Error controlado al armar o interpretar la rutina."""


def catalogo_ejercicios(user_id: int) -> list[dict]:
    rows = listar_exercises(user_id, status="ready")
    catalog = []
    for r in rows:
        catalog.append(
            {
                "id": int(r["id"]),
                "nombre": (r.get("nombre_ejercicio") or "Ejercicio")[:120],
                "primarios": r.get("grupos_musculares_primarios") or [],
                "equipo": r.get("equipamiento_detectado") or [],
                "nivel": r.get("nivel_dificultad"),
                "tipo": r.get("tipo_movimiento"),
                "series_reps": r.get("series_reps_sugeridas")
                or r.get("series_reps_mencionadas"),
                "cues": (r.get("cues_de_forma") or [])[:2],
            }
        )
    return catalog


def _clamp_int(val, default: int, lo: int, hi: int) -> int:
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def parse_routine_payload(
    text: str,
    *,
    allowed_ids: set[int],
    expected_days: int,
    minutos: int,
) -> dict:
    data = extract_json_object(text)
    dias_in = data.get("dias")
    if not isinstance(dias_in, list) or not dias_in:
        raise RoutineError("La IA no armó los días de la rutina.")

    days: list[dict] = []
    for i, raw_day in enumerate(dias_in[:expected_days], start=1):
        if not isinstance(raw_day, dict):
            continue
        bloques_in = raw_day.get("bloques") or raw_day.get("ejercicios") or []
        if not isinstance(bloques_in, list):
            bloques_in = []
        bloques: list[dict] = []
        for b in bloques_in[:12]:
            if not isinstance(b, dict):
                continue
            nombre = str(b.get("nombre") or "").strip()[:120]
            if not nombre:
                continue
            eid_raw = b.get("exercise_id")
            eid = None
            if eid_raw not in (None, "", "null", "None"):
                try:
                    eid = int(eid_raw)
                except (TypeError, ValueError):
                    eid = None
            if eid is not None and eid not in allowed_ids:
                eid = None
            bloques.append(
                {
                    "exercise_id": eid,
                    "nombre": nombre,
                    "series": _clamp_int(b.get("series"), 3, 1, 8),
                    "reps": str(b.get("reps") or "8-12").strip()[:40],
                    "descanso_seg": _clamp_int(b.get("descanso_seg"), 60, 0, 300),
                    "notas": str(b.get("notas") or "").strip()[:200],
                }
            )
        if not bloques:
            continue
        cal = raw_day.get("calentamiento") or []
        cierre = raw_day.get("cierre") or []
        if not isinstance(cal, list):
            cal = [cal]
        if not isinstance(cierre, list):
            cierre = [cierre]
        days.append(
            {
                "nombre": str(raw_day.get("nombre") or f"Día {i}").strip()[:80],
                "enfoque": str(raw_day.get("enfoque") or "").strip()[:120],
                "duracion_min": _clamp_int(
                    raw_day.get("duracion_min"), minutos, 10, 150
                ),
                "calentamiento": [
                    str(x).strip()[:80] for x in cal if str(x).strip()
                ][:6],
                "bloques": bloques,
                "cierre": [str(x).strip()[:80] for x in cierre if str(x).strip()][:6],
            }
        )
    if not days:
        raise RoutineError("La IA no dejó ejercicios en ningún día.")
    return {
        "nombre": str(data.get("nombre") or f"Rutina {expected_days} días").strip()[:80],
        "objetivo": str(data.get("objetivo") or "").strip()[:120],
        "notas_coach": str(data.get("notas_coach") or "").strip()[:800],
        "dias": days,
    }


def _build_prompt(
    *,
    dias: int,
    minutos: int,
    equipo: list[str],
    catalog: list[dict],
    notas: str,
    previous: dict | None,
) -> str:
    catalog_txt = json.dumps(catalog[:40], ensure_ascii=False)
    equipo_txt = ", ".join(equipo) if equipo else "peso corporal"
    prev = ""
    if previous:
        prev = (
            "\nRUTINA ACTUAL A MEJORAR (respeta lo que funcione, cambia lo pedido):\n"
            + json.dumps(previous, ensure_ascii=False)[:6000]
        )
    notas_txt = (notas or "").strip() or "(sin notas extra)"
    return f"""Arma una rutina semanal para entrenar en casa / gym ligero.

Restricciones:
- Exactamente {dias} días de entrenamiento (no más, no menos).
- Cada sesión debe caber en {minutos} minutos, incluyendo calentamiento y cierre.
- Equipamiento disponible: {equipo_txt}.
- Prefiere ejercicios de la BIBLIOTECA y usa su id en exercise_id.
- Si falta un patrón (empuje, jalón, piernas, core), puedes añadir movimientos
  de peso corporal o del equipo listado, con exercise_id null.
- No uses máquinas ni equipo que no esté en la lista.
- Series y reps realistas para el tiempo. Descanso en segundos.

Notas del usuario: {notas_txt}
{prev}

BIBLIOTECA (JSON): {catalog_txt}

Devuelve ÚNICAMENTE un JSON con esta forma:
{{
  "nombre": "string corto",
  "objetivo": "fuerza | hipertrofia | resistencia | movilidad | general",
  "notas_coach": "2-4 frases: por qué esta semana y cómo progresar la próxima",
  "dias": [
    {{
      "nombre": "Día 1 · Empuje",
      "enfoque": "grupos del día",
      "duracion_min": {minutos},
      "calentamiento": ["2-4 ítems cortos"],
      "bloques": [
        {{
          "exercise_id": 12,
          "nombre": "nombre del ejercicio",
          "series": 3,
          "reps": "8-10",
          "descanso_seg": 90,
          "notas": "una cue de forma"
        }}
      ],
      "cierre": ["1-3 ítems"]
    }}
  ]
}}
No agregues texto fuera del JSON."""


def generate_routine(
    *,
    user_id: int,
    dias: int,
    minutos: int,
    equipo: list[str],
    notas: str = "",
    previous: dict | None = None,
) -> dict:
    dias_n = _clamp_int(dias, 3, MIN_DIAS, MAX_DIAS)
    minutos_n = _clamp_int(minutos, 45, MIN_MINUTOS, MAX_MINUTOS)
    equipo_n = [str(x).strip()[:80] for x in (equipo or []) if str(x).strip()]
    if not equipo_n:
        equipo_n = ["peso corporal"]
    if not api_key_configurada():
        raise RoutineError("Configura GROQ_API_KEY para que el coach arme la rutina.")

    catalog = catalogo_ejercicios(user_id)
    prompt = _build_prompt(
        dias=dias_n,
        minutos=minutos_n,
        equipo=equipo_n,
        catalog=catalog,
        notas=notas,
        previous=previous,
    )
    raw = chat_simple(prompt, contexto=SYSTEM_COACH_RUTINA, max_tokens=2500)
    if not raw or raw.startswith("🤖"):
        detalle = last_ai_error() or "el coach no respondió"
        raise RoutineError(f"No se pudo armar la rutina ({detalle}).")
    plan = parse_routine_payload(
        raw,
        allowed_ids={int(e["id"]) for e in catalog},
        expected_days=dias_n,
        minutos=minutos_n,
    )
    log.info(
        {
            "event": "exercise_routine_generated",
            "user_id": int(user_id),
            "dias": len(plan.get("dias") or []),
            "catalog": len(catalog),
            "improve": bool(previous),
        }
    )
    return plan
