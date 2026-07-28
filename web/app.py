"""
Mission Dashboard — FastAPI + HTMX (migración desde Streamlit).

Arranque local:
  MISSION_ALLOW_SQLITE=1 uvicorn web.app:app --reload --port 8000

Producción (Railway):
  TURSO_URL / TURSO_TOKEN / SESSION_SECRET / ...
  uvicorn web.app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from web.deps import NotAuthenticated, NeedsOnboarding, init_app_state
from web.routers import auth as auth_router
from web.routers import billing as billing_router
from web.routers import coach as coach_router
from web.routers import dashboard as dash_router
from web.routers import modules as modules_router
from web.routers import stripe_hook as stripe_router

SESSION_SECRET = os.getenv("SESSION_SECRET") or os.getenv("APP_PASSWORD") or "dev-change-me"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_app_state()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mission Dashboard",
        version="2.0.0-skeleton",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET,
        session_cookie="mission_session",
        same_site="lax",
        https_only=os.getenv("MISSION_HTTPS", "").lower() in ("1", "true", "yes"),
        max_age=60 * 60 * 24 * 14,
    )

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(auth_router.router)
    app.include_router(coach_router.router)
    app.include_router(dash_router.router)
    app.include_router(modules_router.router)
    app.include_router(billing_router.router)
    app.include_router(stripe_router.router)

    @app.exception_handler(NotAuthenticated)
    async def _not_auth(request: Request, exc: NotAuthenticated):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(NeedsOnboarding)
    async def _needs_coach(request: Request, exc: NeedsOnboarding):
        return RedirectResponse("/app/coach", status_code=303)

    @app.get("/health")
    def health():
        from app.db.core import usar_turso

        return {
            "ok": True,
            "app": "mission-dashboard-web",
            "turso": usar_turso(),
            "framework": "fastapi+htmx",
        }

    @app.get("/")
    def root(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/app", status_code=303)
        return RedirectResponse("/login", status_code=303)

    return app


app = create_app()
