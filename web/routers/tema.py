"""Cambio de tema claro/oscuro."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.tema import aplicar_cookie, guardar_tema, next_seguro, normalizar
from web.deps import require_user

router = APIRouter(prefix="/app/tema", tags=["tema"])


@router.post("")
async def set_tema(request: Request, user: Annotated[dict, Depends(require_user)]):
    form = await request.form()
    tema = guardar_tema(str(form.get("theme") or ""), user_id=int(user["id"]))
    request.session["theme"] = tema
    dest = next_seguro(request, str(form.get("next") or ""))
    resp = RedirectResponse(dest, status_code=303)
    aplicar_cookie(resp, tema)
    return resp
