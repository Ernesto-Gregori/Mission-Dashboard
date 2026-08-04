"""Usuarios HTMX — plan propio, gestión admin, backup y auditoría."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.audit import listar_auditoria
from app.backup import exportar_backup_json
from app.billing import (
    PLAN_FREE,
    PLANES_VALIDOS,
    limites,
    plan_vigente,
    resumen_plan_ui,
    payments_configured,
    set_plan,
)
from app.database import crear_usuario, listar_usuarios
from app.multiuser import provision_user_defaults
from app.onboarding import listar_modulos_usuario
from app.stability import invalidate_data_caches
from app.templates import MODULE_TEMPLATES
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/usuarios", tags=["usuarios"])

TABS = ("plan", "gestion", "backup", "auditoria")


def _nav(user_id: int) -> list[dict]:
    rows = listar_modulos_usuario(user_id)
    activos = {r["modulo"] for r in rows if int(r.get("activo") or 0) == 1}
    return [
        {
            **meta,
            "clave": key,
            "activo": key in activos,
            "href": f"/app/m/{key}",
        }
        for key, meta in MODULE_TEMPLATES.items()
    ]


def _tab(request: Request, user: dict) -> str:
    t = (request.query_params.get("tab") or request.session.get("usr_tab") or "plan").lower()
    if t not in TABS:
        t = "plan"
    if user.get("rol") != "admin" and t != "plan":
        t = "plan"
    request.session["usr_tab"] = t
    return t


def _is_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    backup_path: str | None = None,
):
    tab = _tab(request, user)
    plan = plan_vigente(user)
    usuarios = listar_usuarios() if _is_admin(user) else []
    auditoria = listar_auditoria(limite=30) if _is_admin(user) and tab == "auditoria" else []

    return {
        "title": "Usuarios",
        "user": user,
        "tab": tab,
        "flash": flash,
        "error": error,
        "backup_path": backup_path,
        "modulos_nav": _nav(int(user["id"])),
        "is_admin": _is_admin(user),
        "plan": plan,
        "plan_label": limites(plan)["nombre"],
        "plan_resumen": resumen_plan_ui(user),
        "plan_free": PLAN_FREE,
        "lim_free": limites(PLAN_FREE),
        "stripe_ok": payments_configured(),
        "usuarios": usuarios,
        "planes_validos": list(PLANES_VALIDOS),
        "auditoria": auditoria,
    }


def _redirect(tab: str = "plan") -> RedirectResponse:
    return RedirectResponse(f"/app/usuarios?tab={tab}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def usuarios_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "usuarios.html", **_ctx(request, user))


@router.post("/crear")
async def crear(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return render(
            request,
            "usuarios.html",
            status_code=403,
            **_ctx(request, user, error="Solo administradores."),
        )
    request.session["usr_tab"] = "gestion"
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    password2 = str(form.get("password2") or "")
    rol = str(form.get("rol") or "usuario")
    plan = str(form.get("plan") or "free")
    if password != password2:
        return render(
            request,
            "usuarios.html",
            status_code=400,
            **_ctx(request, user, error="Las contraseñas no coinciden."),
        )
    ok, msg = crear_usuario(username, password, rol=rol, plan=plan)
    if not ok:
        return render(
            request,
            "usuarios.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    try:
        rows = listar_usuarios()
        nuevo = next(
            (u for u in rows if str(u.get("username") or "").lower() == username.lower()),
            None,
        )
        if nuevo:
            provision_user_defaults(int(nuevo["id"]), seed_modules=False)
    except Exception:
        pass
    invalidate_data_caches()
    return render(
        request,
        "usuarios.html",
        **_ctx(request, user, flash=f"{msg}: {username.strip().lower()} (plan {plan})"),
    )


@router.post("/plan")
async def cambiar_plan(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return render(
            request,
            "usuarios.html",
            status_code=403,
            **_ctx(request, user, error="Solo administradores."),
        )
    request.session["usr_tab"] = "gestion"
    form = await request.form()
    try:
        uid = int(form.get("user_id"))
    except Exception:
        return render(
            request,
            "usuarios.html",
            status_code=400,
            **_ctx(request, user, error="Usuario inválido."),
        )
    plan = str(form.get("plan") or "free")
    expira = str(form.get("expira") or "").strip() or None
    ok, msg = set_plan(uid, plan, expira)
    if not ok:
        return render(
            request,
            "usuarios.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    # Refrescar sesión si el admin se cambió el plan a sí mismo
    if int(user["id"]) == uid:
        from app.database import obtener_usuario_activo
        from web.deps import login_user

        fresh = obtener_usuario_activo(uid)
        if fresh:
            login_user(request, fresh)
            user = fresh
    return render(
        request,
        "usuarios.html",
        **_ctx(request, user, flash=msg),
    )


@router.post("/backup")
async def backup(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return render(
            request,
            "usuarios.html",
            status_code=403,
            **_ctx(request, user, error="Solo administradores."),
        )
    request.session["usr_tab"] = "backup"
    path = exportar_backup_json(tag="manual")
    if not path:
        return render(
            request,
            "usuarios.html",
            status_code=500,
            **_ctx(request, user, error="No se pudo crear el backup."),
        )
    return render(
        request,
        "usuarios.html",
        **_ctx(
            request,
            user,
            flash="Backup creado.",
            backup_path=str(path),
        ),
    )
