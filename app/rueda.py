"""Rueda de la vida — 8 áreas con puntuación 0–10."""
from __future__ import annotations

import json
import math

from app.logging_config import get_logger

log = get_logger("rueda")

AREAS = (
    ("fe", "Fe", "✝️"),
    ("matrimonio", "Matrimonio", "💑"),
    ("salud", "Salud", "💪"),
    ("finanzas", "Finanzas", "💰"),
    ("trabajo", "Trabajo / estudio", "💻"),
    ("relaciones", "Relaciones", "👥"),
    ("descanso", "Descanso", "🌙"),
    ("proposito", "Propósito", "🎯"),
)
CLAVES = tuple(a[0] for a in AREAS)


def ensure_rueda_schema() -> None:
    from app.db.core import ejecutar

    try:
        ejecutar(
            """
            CREATE TABLE IF NOT EXISTS rueda_vida (
                user_id INTEGER PRIMARY KEY,
                scores_json TEXT NOT NULL DEFAULT '{}',
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception as e:
        log.warning("ensure_rueda_schema: %s", e)


def _uid(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def _clamp(n: int) -> int:
    return max(0, min(10, int(n)))


def scores_default() -> dict[str, int]:
    return {k: 0 for k in CLAVES}


def parsear_scores(raw: dict | str | None) -> dict[str, int]:
    data: dict = {}
    if isinstance(raw, str):
        try:
            data = json.loads(raw) or {}
        except Exception:
            data = {}
    elif isinstance(raw, dict):
        data = raw
    out = scores_default()
    for k in CLAVES:
        try:
            out[k] = _clamp(int(data.get(k, 0) or 0))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def validar_scores(vals: dict) -> tuple[bool, str, dict[str, int]]:
    clean = scores_default()
    for k in CLAVES:
        try:
            n = int(vals.get(k, 0) or 0)
        except (TypeError, ValueError):
            return False, "Cada área necesita un número del 0 al 10.", clean
        if n < 0 or n > 10:
            return False, "Cada área debe estar entre 0 y 10.", clean
        clean[k] = n
    return True, "", clean


def obtener_scores(user_id: int | None = None) -> dict[str, int]:
    ensure_rueda_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            "SELECT scores_json FROM rueda_vida WHERE user_id = ?",
            [_uid(user_id)],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return scores_default()
    return parsear_scores(rows[0].get("scores_json"))


def guardar_scores(vals: dict, user_id: int | None = None) -> tuple[bool, str, dict[str, int]]:
    ok, msg, clean = validar_scores(vals)
    if not ok:
        return False, msg, clean
    ensure_rueda_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    ejecutar(
        """
        INSERT INTO rueda_vida (user_id, scores_json)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            scores_json = excluded.scores_json,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [uid_i, json.dumps(clean)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True, "Rueda actualizada.", clean


def geometria(scores: dict[str, int], *, size: int = 280) -> dict:
    """Puntos SVG para ejes y polígono de la rueda."""
    cx = cy = size / 2
    r = size * 0.38
    n = len(AREAS)
    ejes = []
    labels = []
    poly = []
    for i, (key, nombre, emoji) in enumerate(AREAS):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        ejes.append({"x1": cx, "y1": cy, "x2": x, "y2": y})
        lx = cx + r * 1.22 * math.cos(ang)
        ly = cy + r * 1.22 * math.sin(ang)
        labels.append({
            "x": lx,
            "y": ly,
            "nombre": nombre,
            "emoji": emoji,
            "key": key,
        })
        val = _clamp(int(scores.get(key, 0) or 0)) / 10.0
        px = cx + r * val * math.cos(ang)
        py = cy + r * val * math.sin(ang)
        poly.append(f"{px:.1f},{py:.1f}")
    anillos = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = []
        for i in range(n):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            pts.append(f"{cx + r * frac * math.cos(ang):.1f},{cy + r * frac * math.sin(ang):.1f}")
        anillos.append(" ".join(pts))
    return {
        "size": size,
        "cx": cx,
        "cy": cy,
        "ejes": ejes,
        "labels": labels,
        "poligono": " ".join(poly),
        "anillos": anillos,
        "areas": [
            {"key": k, "nombre": n, "emoji": e, "valor": _clamp(int(scores.get(k, 0) or 0))}
            for k, n, e in AREAS
        ],
        "promedio": round(sum(scores.get(k, 0) for k in CLAVES) / len(CLAVES), 1) if scores else 0,
    }
