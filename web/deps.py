"""Dependencias FastAPI: sesión, usuario, BD."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.tenant import clear_current_user, reset_current_user, set_current_user

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class NotAuthenticated(Exception):
    """Redirige a /login (handler en web.app)."""


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Fija ContextVar del usuario en el contexto async del request.

    FastAPI ejecuta deps/endpoints sync en un threadpool; un set_current_user
    hecho solo en Depends no se propaga al endpoint. Al setear aquí (antes de
    call_next), la copia de contextvars al hilo sí incluye el usuario.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        token = set_current_user(None)
        request.state.user = None
        try:
            uid = request.session.get("user_id")
            if uid:
                from app.database import obtener_usuario_activo

                user = obtener_usuario_activo(int(uid))
                if user:
                    reset_current_user(token)
                    token = set_current_user(user)
                    request.state.user = user
                else:
                    request.session.clear()
            return await call_next(request)
        finally:
            reset_current_user(token)


def init_app_state() -> None:
    """Schema + billing columns al arrancar."""
    from app.billing import ensure_billing_schema
    from app.db.core import usar_turso
    from app.db.schema import init_database
    from app.multiuser import migrate_multiuser
    from app.runtime import es_entorno_cloud, permitir_sqlite

    if es_entorno_cloud() and not permitir_sqlite() and not usar_turso():
        raise RuntimeError(
            "Producción web requiere TURSO_URL y TURSO_TOKEN "
            "(o MISSION_ALLOW_SQLITE=1 solo para demos)."
        )

    init_database()
    try:
        migrate_multiuser()
    except Exception as e:
        print(f"[web.startup] migrate_multiuser: {e}")
    try:
        ensure_billing_schema()
    except Exception as e:
        print(f"[web.startup] billing: {e}")


def get_session_user(request: Request) -> dict | None:
    # Preferido: ya resuelto por TenantMiddleware
    cached = getattr(request.state, "user", None)
    if cached is not None:
        set_current_user(cached)
        return cached

    uid = request.session.get("user_id")
    if not uid:
        clear_current_user()
        return None
    from app.database import obtener_usuario_activo

    user = obtener_usuario_activo(int(uid))
    if not user:
        request.session.clear()
        clear_current_user()
        return None
    set_current_user(user)
    request.state.user = user
    return user


def require_user(request: Request) -> dict:
    user = get_session_user(request)
    if not user:
        raise NotAuthenticated()
    return user


class NeedsOnboarding(Exception):
    """Redirige a /app/coach."""


def require_onboarded(request: Request, user: dict = Depends(require_user)) -> dict:
    """Usuario autenticado que ya pasó el Coach (o legacy admin)."""
    from app.onboarding import marcar_admins_existentes_como_onboarded, usuario_onboarding_completo

    marcar_admins_existentes_como_onboarded()
    if not usuario_onboarding_completo(int(user["id"])):
        raise NeedsOnboarding()
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user.get("rol") != "admin":
        raise HTTPException(403, "Solo administradores")
    return user


def login_user(request: Request, user: dict) -> None:
    request.session.clear()
    request.session["user_id"] = int(user["id"])
    request.session["username"] = user.get("username")
    set_current_user(user)


def logout_user(request: Request) -> None:
    request.session.clear()
    clear_current_user()


def render(request: Request, name: str, status_code: int = 200, **ctx):
    # Starlette ≥0.37: TemplateResponse(request, name, context)
    return TEMPLATES.TemplateResponse(
        request,
        name,
        ctx,
        status_code=status_code,
    )
