"""
tenant.py — Aislamiento multi-usuario

Cada dato de negocio pertenece a un user_id.
Usar uid() en INSERT/SELECT/UPDATE/DELETE.

Soporta:
- Streamlit (session_state)
- FastAPI / scripts (contextvars)
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_user_ctx: ContextVar[dict | None] = ContextVar("mission_user", default=None)


def set_current_user(user: dict | None) -> None:
    """Fija el usuario del request (FastAPI middleware / depends)."""
    _user_ctx.set(user)


def clear_current_user() -> None:
    _user_ctx.set(None)


def current_user() -> dict | None:
    # 1) ContextVar (FastAPI)
    u = _user_ctx.get()
    if u:
        return u
    # 2) Streamlit session
    try:
        import streamlit as st

        return st.session_state.get("user")
    except Exception:
        return None


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


def as_user(user: dict | None):
    """Context manager ligero para tests / jobs."""
    class _CM:
        def __enter__(self_inner) -> dict | None:
            self_inner._token = _user_ctx.set(user)
            return user

        def __exit__(self_inner, *args: Any) -> None:
            _user_ctx.reset(self_inner._token)

    return _CM()
