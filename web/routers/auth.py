from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import autenticar_usuario, contar_usuarios, crear_usuario
from app.multiuser import provision_user_defaults
from app.rate_limit import registrar_exito, registrar_fallo, segundos_bloqueo
from web.deps import get_session_user, login_user, logout_user, render

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/app", status_code=303)
    if contar_usuarios() == 0:
        return RedirectResponse("/setup", status_code=303)
    return render(request, "login.html", error=None, title="Entrar")


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    key = (username or "").strip().lower()
    if not key and request.client:
        key = request.client.host
    key = key or "anon"
    wait = segundos_bloqueo(key)
    if wait > 0:
        return render(
            request,
            "login.html",
            error=f"Demasiados intentos. Espera {wait}s.",
            title="Entrar",
            status_code=429,
        )
    user = autenticar_usuario(username, password)
    if not user:
        registrar_fallo(key)
        return render(
            request,
            "login.html",
            error="Usuario o contraseña incorrectos.",
            title="Entrar",
            status_code=401,
        )
    registrar_exito(key)
    login_user(request, user)
    return RedirectResponse("/app", status_code=303)


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    if contar_usuarios() > 0:
        return RedirectResponse("/login", status_code=303)
    return render(request, "setup.html", error=None, title="Primer acceso")


@router.post("/setup", response_class=HTMLResponse)
def setup_submit(
    request: Request,
    username: Annotated[str, Form()] = "admin",
    password: Annotated[str, Form()] = "",
    password2: Annotated[str, Form()] = "",
):
    if contar_usuarios() > 0:
        return RedirectResponse("/login", status_code=303)
    if password != password2:
        return render(
            request,
            "setup.html",
            error="Las contraseñas no coinciden.",
            title="Primer acceso",
            status_code=400,
        )
    ok, msg = crear_usuario(username, password, rol="admin", plan="premium")
    if not ok:
        return render(
            request,
            "setup.html",
            error=msg,
            title="Primer acceso",
            status_code=400,
        )
    user = autenticar_usuario(username, password)
    if user:
        provision_user_defaults(int(user["id"]), seed_modules=False)
        login_user(request, user)
    return RedirectResponse("/app", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)
