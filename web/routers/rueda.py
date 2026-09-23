"""Rueda de la vida — vive dentro de la Revisión semanal."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.rueda import CLAVES, guardar_scores
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/rueda", tags=["rueda"])


@router.get("")
@router.get("/")
def rueda_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return RedirectResponse("/app/revision#rueda", status_code=303)


@router.post("")
async def guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    from web.routers.revision import revision_ctx

    form = await request.form()
    raw = {k: form.get(k) for k in CLAVES}
    ok, msg, clean = guardar_scores(raw, user_id=int(user["id"]))
    if not ok:
        return render(
            request,
            "revision.html",
            status_code=400,
            **revision_ctx(request, user, error=msg, rueda_scores=clean),
        )
    request.session["revision_flash"] = "Rueda actualizada."
    return RedirectResponse("/app/revision#rueda", status_code=303)
