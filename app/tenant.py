"""
tenant.py — Aislamiento multi-usuario

Cada dato de negocio pertenece a un user_id.
Usar uid() en INSERT/SELECT/UPDATE/DELETE.
"""
from __future__ import annotations

import streamlit as st


def current_user() -> dict | None:
    return st.session_state.get("user")


def uid() -> int:
    """ID del usuario autenticado. Falla si no hay sesión."""
    user = current_user()
    if not user or user.get("id") is None:
        raise RuntimeError("No hay usuario autenticado (uid)")
    return int(user["id"])


def try_uid() -> int | None:
    try:
        return uid()
    except Exception:
        return None
