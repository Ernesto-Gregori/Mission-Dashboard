"""Compat: Agenda se repartió entre el Planificador y la Revisión semanal."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from web.deps import require_onboarded

router = APIRouter(prefix="/app/m/agenda", tags=["agenda"])


@router.get("")
@router.get("/")
def agenda_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if (request.query_params.get("tab") or "").lower() == "calendario":
        return RedirectResponse("/app/planificador?vista=semana", status_code=303)
    semana = request.query_params.get("semana") or request.query_params.get("hist")
    dest = f"/app/revision?semana={semana}" if semana else "/app/revision"
    return RedirectResponse(dest, status_code=303)
