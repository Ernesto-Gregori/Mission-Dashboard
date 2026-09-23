"""Ritual de mañana — el formulario vive en Hoy."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.ritual import guardar_ritual
from web.deps import require_onboarded

router = APIRouter(prefix="/app/ritual", tags=["ritual"])


@router.get("")
@router.get("/")
def ritual_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return RedirectResponse("/app", status_code=303)


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
    dest = str(form.get("next") or "/app").strip() or "/app"
    if not dest.startswith("/app"):
        dest = "/app"
    return RedirectResponse(dest, status_code=303)
