"""Ritual de mañana HTMX."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.onboarding import listar_modulos_usuario
from app.ritual import guardar_ritual, habitos_hoy, listar_habitos, obtener_ritual
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/ritual", tags=["ritual"])


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


def _ctx(request: Request, user: dict, *, flash: str | None = None, error: str | None = None):
    uid = int(user["id"])
    ritual = obtener_ritual(uid)
    hechos = habitos_hoy(uid)
    habitos = []
    for h in listar_habitos(uid):
        habitos.append({**h, "hecho": bool(hechos.get(h["clave"]))})
    return {
        "title": "Ritual de mañana",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "ritual": ritual,
        "habitos": habitos,
        "hoy": str(_hoy()),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def ritual_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "ritual.html", **_ctx(request, user))


@router.post("")
async def guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    claves = [str(v) for v in form.getlist("habito") if str(v).strip()]
    guardar_ritual(
        gratitud=str(form.get("gratitud") or ""),
        intencion=str(form.get("intencion") or ""),
        claves_habito=claves,
        user_id=int(user["id"]),
    )
    dest = str(form.get("next") or "/app/ritual").strip() or "/app/ritual"
    if not dest.startswith("/app"):
        dest = "/app/ritual"
    return RedirectResponse(dest, status_code=303)
