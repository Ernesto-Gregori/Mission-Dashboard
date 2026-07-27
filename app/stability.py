"""
stability.py — Menos recargas dolorosas en Streamlit.

Reexporta helpers de database y añade after_write().
"""
from __future__ import annotations

import streamlit as st

from app.database import ensure_database, invalidate_data_caches


def after_write(rerun: bool = True) -> None:
    """Llamar justo después de INSERT/UPDATE/DELETE exitosos en la UI."""
    invalidate_data_caches()
    if rerun:
        st.rerun()


__all__ = [
    "ensure_database",
    "invalidate_data_caches",
    "after_write",
]
