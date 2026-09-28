"""
rate_limit.py — Backoff de login (fuerza bruta).
"""
from __future__ import annotations

import time
from typing import Optional

# username -> {fails, locked_until}
_FAILS: dict[str, dict] = {}

MAX_FAILS = 5
LOCK_SECONDS = 60          # primer bloqueo
LOCK_SECONDS_MAX = 15 * 60  # tope

# Telegram: no es un bypass del login; techo propio por chat_id.
_TG_HITS: dict[str, list[float]] = {}
TG_MAX = 20
TG_WINDOW = 600


def _key(username: str) -> str:
    return (username or "").strip().lower() or "_"


def _leer_intento(username: str) -> dict | None:
    try:
        from app.cuenta import asegurar_schema
        from app.db.core import ejecutar

        asegurar_schema()
        rows = ejecutar(
            "SELECT fails, locked_until FROM login_intentos WHERE username = ?",
            [username],
            fetchall=True,
        ) or []
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def _guardar_intento(username: str, fails: int, locked_until: float) -> None:
    try:
        from app.cuenta import asegurar_schema
        from app.db.core import ejecutar

        asegurar_schema()
        ejecutar(
            """
            INSERT INTO login_intentos (username, fails, locked_until)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                fails = excluded.fails,
                locked_until = excluded.locked_until
            """,
            [username, fails, locked_until],
        )
    except Exception:
        pass


def segundos_bloqueo(username: str) -> int:
    """Segundos restantes de bloqueo (0 = libre)."""
    rec = _FAILS.get(_key(username)) or {}
    until = float(rec.get("locked_until") or 0)
    persisted = _leer_intento(_key(username))
    if persisted:
        until = max(until, float(persisted.get("locked_until") or 0))
    left = int(until - time.time())
    return max(0, left)


def registrar_fallo(username: str) -> int:
    """Registra fallo. Retorna segundos de bloqueo aplicados (0 si aún no bloquea)."""
    k = _key(username)
    rec = _FAILS.get(k) or {"fails": 0, "locked_until": 0.0}
    rec["fails"] = int(rec.get("fails") or 0) + 1
    lock = 0
    if rec["fails"] >= MAX_FAILS:
        # backoff exponencial suave: 60, 120, 240... hasta tope
        extra = rec["fails"] - MAX_FAILS
        lock = min(LOCK_SECONDS_MAX, LOCK_SECONDS * (2 ** max(0, extra)))
        rec["locked_until"] = time.time() + lock
    _FAILS[k] = rec
    _guardar_intento(k, int(rec["fails"]), float(rec.get("locked_until") or 0))
    return lock


def registrar_exito(username: str) -> None:
    k = _key(username)
    _FAILS.pop(k, None)
    try:
        from app.db.core import ejecutar

        ejecutar("DELETE FROM login_intentos WHERE username = ?", [k])
    except Exception:
        pass


def limpiar_todo() -> None:
    """Solo para tests."""
    _FAILS.clear()
    _TG_HITS.clear()
    try:
        from app.db.core import ejecutar

        ejecutar("DELETE FROM login_intentos")
    except Exception:
        pass


def telegram_permitido(chat_id: str) -> bool:
    """True si el chat aún está bajo el techo de mensajes."""
    key = str(chat_id or "").strip() or "_"
    now = time.time()
    hits = [t for t in _TG_HITS.get(key, []) if now - t < TG_WINDOW]
    if len(hits) >= TG_MAX:
        _TG_HITS[key] = hits
        return False
    hits.append(now)
    _TG_HITS[key] = hits
    return True
