"""
stability.py — Helpers de invalidación post-escritura (FastAPI).

Reexporta helpers de database y añade after_write().
"""
from __future__ import annotations

from app.database import ensure_database, invalidate_data_caches


def after_write(rerun: bool = True) -> None:
    """Llamar justo después de INSERT/UPDATE/DELETE exitosos."""
    invalidate_data_caches()


__all__ = [
    "ensure_database",
    "invalidate_data_caches",
    "after_write",
]
