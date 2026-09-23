"""Asistente Alma — chat HTMX con contexto opt-in."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada
from app.asistente import (
    CATEGORIA_LABELS,
    borrar_historial,
    flags_desde_form,
    guardar_prefs,
    listar_mensajes,
    obtener_prefs,
    responder,
)
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/asistente", tags=["asistente"])


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
):
    uid = int(user["id"])
    return {
        "title": "Alma",
        "user": user,
        "flash": flash,
        "error": error,
        "prefs": obtener_prefs(uid),
        "categorias": CATEGORIA_LABELS,
        "mensajes": listar_mensajes(uid),
        "ia_ok": api_key_configurada(),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def asistente_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "asistente.html", **_ctx(request, user))


@router.post("/permisos")
async def guardar_permisos(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    guardar_prefs(flags_desde_form(form), user_id=int(user["id"]))
    return RedirectResponse("/app/asistente", status_code=303)


@router.post("/mensaje")
async def enviar_mensaje(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    flags = flags_desde_form(form)
    texto = str(form.get("mensaje") or "").strip()
    if not texto:
        return render(
            request,
            "asistente.html",
            status_code=400,
            **_ctx(request, user, error="Escribe un mensaje para Alma."),
        )
    try:
        responder(texto, flags, user_id=int(user["id"]))
    except ValueError as e:
        return render(
            request,
            "asistente.html",
            status_code=400,
            **_ctx(request, user, error=str(e)),
        )
    return RedirectResponse("/app/asistente", status_code=303)


@router.post("/borrar")
def borrar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    borrar_historial(int(user["id"]))
    return RedirectResponse("/app/asistente", status_code=303)
