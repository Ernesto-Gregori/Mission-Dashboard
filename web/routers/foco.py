"""Compat: el Foco del día vive en Hoy; otros días, en el Planificador."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.calendar_sync import pull_range
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded

router = APIRouter(prefix="/app/foco", tags=["foco"])


@router.get("")
@router.get("/")
def foco_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    try:
        dia = date.fromisoformat(str(request.query_params.get("fecha") or "")[:10])
    except ValueError:
        dia = _hoy()
    if dia == _hoy():
        return RedirectResponse("/app", status_code=303)
    return RedirectResponse(f"/app/planificador?vista=dia&d={(dia - _hoy()).days}", status_code=303)


@router.post("/sync")
def sync_now(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    dia = _hoy()
    try:
        pull_range(dia, dia, user_id=int(user["id"]), force=True)
        request.session["hoy_flash"] = "Calendar sincronizado."
    except Exception as e:
        request.session["hoy_error"] = str(e)[:160]
    return RedirectResponse("/app", status_code=303)
