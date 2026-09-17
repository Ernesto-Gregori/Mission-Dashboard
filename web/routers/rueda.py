"""Rueda de la vida HTMX."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.onboarding import listar_modulos_usuario
from app.rueda import AREAS, CLAVES, geometria, guardar_scores, obtener_scores
from app.templates import MODULE_TEMPLATES
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/rueda", tags=["rueda"])


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


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    scores: dict | None = None,
):
    uid = int(user["id"])
    vals = scores if scores is not None else obtener_scores(uid)
    geo = geometria(vals)
    return {
        "title": "Rueda de la vida",
        "user": user,
        "modulos_nav": _nav(uid),
        "flash": flash,
        "error": error,
        "geo": geo,
        "areas": AREAS,
        "scores": vals,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def rueda_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "rueda.html", **_ctx(request, user))


@router.post("")
async def guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    raw = {k: form.get(k) for k in CLAVES}
    ok, msg, clean = guardar_scores(raw, user_id=int(user["id"]))
    if not ok:
        return render(
            request,
            "rueda.html",
            status_code=400,
            **_ctx(request, user, error=msg, scores=clean),
        )
    return RedirectResponse("/app/rueda", status_code=303)
