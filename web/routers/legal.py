"""Páginas públicas para la pantalla de consentimiento de Google."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.deps import render

router = APIRouter(tags=["legal"])


def _contacto() -> str:
    return (os.getenv("SUPPORT_EMAIL") or os.getenv("GOOGLE_SUPPORT_EMAIL") or "").strip()


@router.get("/privacidad", response_class=HTMLResponse)
def privacidad(request: Request):
    return render(
        request,
        "privacidad.html",
        title="Política de privacidad",
        contacto=_contacto(),
    )


@router.get("/terminos", response_class=HTMLResponse)
def terminos(request: Request):
    return render(
        request,
        "terminos.html",
        title="Términos de servicio",
        contacto=_contacto(),
    )
