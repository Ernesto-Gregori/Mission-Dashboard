"""Vista familiar HTMX — comparativa admin de gastos, hábitos y tareas."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.familia import listar_comparativa
from app.timezone_config import hoy as _hoy
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/familia", tags=["familia"])

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _is_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def _periodo(request: Request) -> tuple[int, int]:
    hoy = _hoy()
    try:
        mes = int(request.query_params.get("mes") or request.session.get("fam_mes") or hoy.month)
        anio = int(request.query_params.get("anio") or request.session.get("fam_anio") or hoy.year)
    except Exception:
        mes, anio = hoy.month, hoy.year
    mes = min(12, max(1, mes))
    anio = min(2035, max(2020, anio))
    request.session["fam_mes"] = mes
    request.session["fam_anio"] = anio
    return mes, anio


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    data: dict | None = None,
):
    mes, anio = _periodo(request)
    return {
        "title": "Familia",
        "user": user,
        "flash": flash,
        "error": error,
        "mes": mes,
        "anio": anio,
        "meses": list(enumerate(MESES, start=1)),
        "is_admin": _is_admin(user),
        "miembros": (data or {}).get("miembros") or [],
        "seleccionado": (data or {}).get("seleccionado"),
        "miembro_id": request.query_params.get("miembro") or "",
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def familia_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not _is_admin(user):
        return render(
            request,
            "familia.html",
            status_code=403,
            **_ctx(request, user, error="Solo administradores."),
        )
    mes, anio = _periodo(request)
    raw = (request.query_params.get("miembro") or "").strip()
    miembro_id = None
    if raw:
        try:
            miembro_id = int(raw)
        except ValueError:
            return render(
                request,
                "familia.html",
                status_code=400,
                **_ctx(request, user, error="Miembro inválido."),
            )
    try:
        data = listar_comparativa(user, mes, anio, miembro_id=miembro_id)
    except LookupError:
        return render(
            request,
            "familia.html",
            status_code=404,
            **_ctx(request, user, error="Ese miembro no existe."),
        )
    except PermissionError:
        return render(
            request,
            "familia.html",
            status_code=403,
            **_ctx(request, user, error="Solo administradores."),
        )
    return render(request, "familia.html", **_ctx(request, user, data=data))
