"""Compat: el 50/30/20 ahora es un preset del reparto en Finanzas."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from web.deps import require_onboarded

router = APIRouter(prefix="/app/presupuesto", tags=["presupuesto"])


@router.get("")
@router.get("/")
def presupuesto_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    q = request.url.query
    return RedirectResponse(f"/app/m/finanzas?{q}" if q else "/app/m/finanzas", status_code=303)
