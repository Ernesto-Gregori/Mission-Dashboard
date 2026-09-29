"""Usuarios HTMX — plan propio, gestión admin, backup y auditoría."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.backup import exportar_backup_json
from app.billing import plan_vigente, puede_telegram, set_plan
from app.database import crear_usuario, listar_usuarios
from app.multiuser import provision_user_defaults
from app.stability import invalidate_data_caches
from app.db.telegram_state import guardar_prefs_briefing, guardar_recordatorio_min
from app.telegram import ensure_telegram_schema, start_link, unlink
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/usuarios", tags=["usuarios"])

def _is_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def _pagina(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    status_code: int = 200,
    backup_path: str | None = None,
):
    from web.routers.configuracion import _ctx

    if not _is_admin(user):
        return render(
            request,
            "configuracion.html",
            status_code=403,
            **_ctx(request, user, error=error or "Solo administradores.", tab="areas"),
        )
    return render(
        request,
        "configuracion.html",
        status_code=status_code,
        **_ctx(
            request,
            user,
            flash=flash,
            error=error,
            tab="usuarios",
            backup_path=backup_path,
        ),
    )


def _conexiones(request: Request, user: dict, *, flash: str | None = None, error: str | None = None, status_code: int = 200, fragment: bool = False):
    from web.routers.configuracion import _ctx

    if fragment:
        return render(request, "telegram_briefing.html", **_ctx(request, user, flash=flash, error=error, tab="conexiones"))
    if status_code == 200:
        if flash:
            request.session["config_flash"] = flash
        if error:
            request.session["config_error"] = error
        return RedirectResponse("/app/configuracion?tab=conexiones", status_code=303)
    return render(
        request,
        "configuracion.html",
        status_code=status_code,
        **_ctx(request, user, flash=flash, error=error, tab="conexiones"),
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def usuarios_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    tab = str(request.query_params.get("tab") or "").lower()
    if tab == "telegram" or not _is_admin(user):
        return RedirectResponse("/app/configuracion?tab=conexiones", status_code=303)
    return RedirectResponse("/app/configuracion?tab=usuarios", status_code=303)


@router.post("/crear")
async def crear(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return _pagina(request, user, error="Solo administradores.")
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    password2 = str(form.get("password2") or "")
    rol = str(form.get("rol") or "usuario")
    plan = str(form.get("plan") or "free")
    if password != password2:
        return _pagina(request, user, error="Las contraseñas no coinciden.", status_code=400)
    ok, msg = crear_usuario(username, password, rol=rol, plan=plan)
    if not ok:
        return _pagina(request, user, error=msg, status_code=400)
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
    return _pagina(request, user, flash=f"{msg}: {username.strip().lower()} (plan {plan})")


@router.post("/plan")
async def cambiar_plan(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return _pagina(request, user, error="Solo administradores.")
    form = await request.form()
    try:
        uid = int(form.get("user_id"))
    except Exception:
        return _pagina(request, user, error="Usuario inválido.", status_code=400)
    plan = str(form.get("plan") or "free")
    expira = str(form.get("expira") or "").strip() or None
    ok, msg = set_plan(uid, plan, expira)
    if not ok:
        return _pagina(request, user, error=msg, status_code=400)
    # Refrescar sesión si el admin se cambió el plan a sí mismo
    if int(user["id"]) == uid:
        from app.database import obtener_usuario_activo
        from web.deps import login_user

        fresh = obtener_usuario_activo(uid)
        if fresh:
            login_user(request, fresh)
            user = fresh
    return _pagina(request, user, flash=msg)


@router.post("/backup")
async def backup(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return _pagina(request, user, error="Solo administradores.")
    path = exportar_backup_json(tag="manual")
    if not path:
        return _pagina(request, user, error="No se pudo crear el backup.", status_code=500)
    return _pagina(request, user, flash="Backup creado.", backup_path=str(path))


@router.post("/telegram/vincular")
def tg_vincular(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["usr_tab"] = "telegram"
    ok, msg, code = start_link(int(user["id"]))
    if not ok:
        return _conexiones(request, user, error=msg, status_code=400)
    request.session["tg_code"] = code
    return _conexiones(request, user, flash=f"{msg} Código: {code}")


@router.post("/telegram/desvincular")
def tg_desvincular(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["usr_tab"] = "telegram"
    unlink(int(user["id"]))
    request.session.pop("tg_code", None)
    return _conexiones(request, user, flash="Telegram desvinculado.")


@router.post("/telegram/recordatorios")
async def tg_recordatorios(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["usr_tab"] = "telegram"
    if not puede_telegram(plan_vigente(user)):
        return _conexiones(request, user, error="Telegram requiere plan Premium.", status_code=403)
    form = await request.form()
    ensure_telegram_schema()
    try:
        minutos = int(str(form.get("recordatorio_min") or ""))
    except ValueError:
        minutos = -1
    if not guardar_recordatorio_min(int(user["id"]), minutos):
        return _conexiones(request, user, error="Elige una anticipación de la lista.", status_code=400)
    aviso = "Recordatorios apagados." if minutos == 0 else f"Te aviso {minutos} min antes de cada evento."
    return _conexiones(request, user, flash=aviso)


@router.post("/telegram/briefing")
async def tg_briefing(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    request.session["usr_tab"] = "telegram"
    if not puede_telegram(plan_vigente(user)):
        return _conexiones(request, user, error="Telegram requiere plan Premium.", status_code=403)
    form = await request.form()
    ensure_telegram_schema()
    extra = [str(v) for v in form.getlist("extra")]
    ok = guardar_prefs_briefing(
        int(user["id"]),
        activo=form.get("activo") == "1",
        hora=str(form.get("hora") or ""),
        extra=extra,
    )
    if not ok:
        return _conexiones(request, user, error="Revisa la hora (HH:MM) y las secciones.", status_code=400)
    if request.headers.get("hx-request"):
        return _conexiones(request, user, flash="Briefing de la mañana guardado.", fragment=True)
    return _conexiones(request, user, flash="Briefing de la mañana guardado.")
