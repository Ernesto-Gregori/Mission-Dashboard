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


def set_current_user(user: dict | None):
    """Fija el usuario del request. Devuelve Token para reset_current_user."""
    return _user_ctx.set(user)


def reset_current_user(token) -> None:
    """Restaura el ContextVar al valor previo (usar tras set_current_user)."""
    _user_ctx.reset(token)


def clear_current_user() -> None:
    _user_ctx.set(None)


def current_user() -> dict | None:
    # 1) ContextVar (FastAPI)
    u = _user_ctx.get()
    if u:
        return u
    # 2) Streamlit session (solo con ScriptRunContext)
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx() is None:
            return None
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
