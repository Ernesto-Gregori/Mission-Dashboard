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


def _key(username: str) -> str:
    return (username or "").strip().lower() or "_"


def segundos_bloqueo(username: str) -> int:
    """Segundos restantes de bloqueo (0 = libre)."""
    rec = _FAILS.get(_key(username))
    if not rec:
        return 0
    until = float(rec.get("locked_until") or 0)
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
    return lock


def registrar_exito(username: str) -> None:
    _FAILS.pop(_key(username), None)


def limpiar_todo() -> None:
    """Solo para tests."""
    _FAILS.clear()
