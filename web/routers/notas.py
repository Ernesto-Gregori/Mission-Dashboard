"""Notas, ideas y tareas pendientes."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.notas import actualizar, crear, eliminar, listar, marcar
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/notas", tags=["notas"])


def _tab(request: Request) -> str:
    t = (request.query_params.get("tab") or "tareas").lower()
    if t in ("notas", "ideas"):
        return "notas"
    return "tareas"


def _tipo(tab: str) -> str:
    return "nota" if tab == "notas" else "tarea"


def _ctx(request: Request, user: dict, *, error: str | None = None, flash: str | None = None) -> dict:
    tab = _tab(request)
    return {
        "title": "Notas",
        "user": user,
        "tab": tab,
        "items": listar(int(user["id"]), tipo=_tipo(tab)),
        "error": error or request.session.pop("notas_error", None),
        "flash": flash or request.session.pop("notas_flash", None),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def pagina(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "notas.html", **_ctx(request, user))


@router.post("")
@router.post("/")
async def crear_item(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    tab = _tab(request)
    ok, msg = crear(
        str(form.get("titulo") or ""),
        cuerpo=str(form.get("cuerpo") or ""),
        tipo=_tipo(tab),
        user_id=int(user["id"]),
    )
    if not ok:
        return render(
            request,
            "notas.html",
            status_code=400,
            **_ctx(request, user, error=msg),
        )
    request.session["notas_flash"] = msg
    return RedirectResponse(f"/app/notas?tab={tab}", status_code=303)


@router.post("/{nota_id}/editar")
async def editar_item(
    nota_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    tab = _tab(request)
    ok, msg = actualizar(
        int(nota_id),
        str(form.get("titulo") or ""),
        cuerpo=str(form.get("cuerpo") or ""),
        estado=str(form.get("estado") or "abierta"),
        user_id=int(user["id"]),
    )
    if not ok:
        request.session["notas_error"] = msg
    else:
        request.session["notas_flash"] = msg
    return RedirectResponse(f"/app/notas?tab={tab}", status_code=303)


@router.post("/{nota_id}/hecha")
async def marcar_hecha(
    nota_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    hecha = str(form.get("hecha") or "1") in ("1", "on", "true")
    marcar(int(nota_id), hecha, user_id=int(user["id"]))
    return RedirectResponse(f"/app/notas?tab={_tab(request)}", status_code=303)


@router.post("/{nota_id}/eliminar")
def eliminar_item(
    nota_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    if eliminar(int(nota_id), user_id=int(user["id"])):
        request.session["notas_flash"] = "Eliminado."
    else:
        request.session["notas_error"] = "No encontré esa nota."
    return RedirectResponse(f"/app/notas?tab={_tab(request)}", status_code=303)
