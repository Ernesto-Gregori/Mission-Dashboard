"""Biblioteca HTMX — catálogo, progreso y resaltados (MVP sin PDF)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import (
    CATEGORIAS_LIBRO,
    COLORES_RESALTADO,
    ESTADOS_LIBRO,
    actualizar_libro,
    actualizar_progreso,
    agregar_resaltado,
    crear_libro_manual,
    eliminar_libro,
    obtener_libro,
    obtener_libros_por_estado,
    obtener_resaltados,
    pct_progreso,
    stats_biblioteca,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/biblioteca", tags=["biblioteca"])

TABS = ("catalogo", "nuevo", "leyendo", "resaltados")


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


def _tab(request: Request) -> str:
    t = (request.query_params.get("tab") or request.session.get("bib_tab") or "catalogo").lower()
    if t not in TABS:
        t = "catalogo"
    request.session["bib_tab"] = t
    return t


def _enrich(libros: list) -> list:
    out = []
    for L in libros:
        item = dict(L)
        item["pct"] = pct_progreso(item)
        out.append(item)
    return out


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
):
    tab = _tab(request)
    try:
        pagina = int(request.query_params.get("p") or request.session.get("bib_p") or 1)
    except Exception:
        pagina = 1
    pagina = max(1, pagina)
    request.session["bib_p"] = pagina

    estado = request.query_params.get("estado") or ""
    categoria = request.query_params.get("categoria") or ""
    busqueda = request.query_params.get("q") or ""

    libros, total = obtener_libros_por_estado(
        estado=estado or None,
        categoria=categoria or None,
        busqueda=busqueda,
        pagina=pagina,
        por_pagina=12,
    )
    libros = _enrich(libros)
    leyendo, _ = obtener_libros_por_estado(estado="leyendo", por_pagina=50)
    leyendo = _enrich(leyendo)

    todos, _ = obtener_libros_por_estado(por_pagina=200)
    libro_sel = request.query_params.get("libro")
    resaltados = []
    libro_res = None
    if libro_sel:
        try:
            libro_res = obtener_libro(int(libro_sel))
            if libro_res:
                resaltados = obtener_resaltados(int(libro_sel))
        except Exception:
            pass

    pages = max(1, (total + 11) // 12)

    return {
        "title": "Biblioteca",
        "user": user,
        "meta": MODULE_TEMPLATES["biblioteca"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "modulos_nav": _nav(int(user["id"])),
        "stats": stats_biblioteca(),
        "libros": libros,
        "total": total,
        "pagina": pagina,
        "pages": pages,
        "filtro_estado": estado,
        "filtro_categoria": categoria,
        "busqueda": busqueda,
        "estados": ESTADOS_LIBRO,
        "categorias": CATEGORIAS_LIBRO,
        "leyendo": leyendo,
        "todos": todos,
        "colores": COLORES_RESALTADO,
        "libro_res": libro_res,
        "resaltados": resaltados,
        "libro_sel": libro_sel or "",
    }


def _redirect(tab: str = "catalogo", **extra) -> RedirectResponse:
    q = [f"tab={tab}"]
    for k, v in extra.items():
        if v is not None and v != "":
            q.append(f"{k}={v}")
    return RedirectResponse(f"/app/m/biblioteca?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def biblioteca_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("biblioteca", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Biblioteca",
            user=user,
            meta=MODULE_TEMPLATES["biblioteca"],
            clave="biblioteca",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/biblioteca.html", **_ctx(request, user))


@router.post("/nuevo")
async def nuevo_libro(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    request.session["bib_tab"] = "nuevo"
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="El título es obligatorio."),
        )
    try:
        paginas = int(form.get("total_paginas") or 0)
        anio = int(form.get("anio") or 0)
    except Exception:
        paginas, anio = 0, 0
    estado = str(form.get("estado") or "catalogado")
    lid = crear_libro_manual(
        titulo,
        autor=str(form.get("autor") or ""),
        categoria=str(form.get("categoria") or "Otros"),
        total_paginas=paginas,
        descripcion=str(form.get("descripcion") or ""),
        isbn=str(form.get("isbn") or ""),
        editorial=str(form.get("editorial") or ""),
        anio=anio,
        estado=estado,
    )
    if lid is None:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo crear el libro."),
        )
    return _redirect("catalogo")


@router.post("/libro/{libro_id}/progreso")
async def set_progreso(
    libro_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    try:
        pagina = int(form.get("pagina_actual") or 0)
    except Exception:
        pagina = 0
    estado = str(form.get("estado") or "") or None
    actualizar_progreso(int(libro_id), pagina, estado)
    tab = str(form.get("next_tab") or "leyendo")
    return _redirect(tab if tab in TABS else "leyendo")


@router.post("/libro/{libro_id}/editar")
async def edit_libro(
    libro_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    try:
        total = int(form.get("total_paginas") or 0)
        pagina = int(form.get("pagina_actual") or 0)
    except Exception:
        total, pagina = 0, 0
    ok = actualizar_libro(
        int(libro_id),
        titulo=str(form.get("titulo") or ""),
        autor=str(form.get("autor") or ""),
        categoria=str(form.get("categoria") or "Otros"),
        total_paginas=total,
        pagina_actual=pagina,
        descripcion=str(form.get("descripcion") or ""),
        isbn=str(form.get("isbn") or ""),
        editorial=str(form.get("editorial") or ""),
        estado=str(form.get("estado") or None),
    )
    if not ok:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo editar el libro."),
        )
    return _redirect("catalogo")


@router.post("/libro/{libro_id}/eliminar")
def delete_libro(
    libro_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_libro(int(libro_id))
    return _redirect("catalogo")


@router.post("/resaltado")
async def add_resaltado(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    request.session["bib_tab"] = "resaltados"
    try:
        libro_id = int(form.get("libro_id"))
        pagina = int(form.get("pagina") or 1)
    except Exception:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="Libro o página inválidos."),
        )
    texto = str(form.get("texto_resaltado") or "").strip()
    if not texto:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="El texto del resaltado es obligatorio."),
        )
    rid = agregar_resaltado(
        libro_id,
        pagina,
        texto,
        str(form.get("color_etiqueta") or "Amarillo"),
        str(form.get("nota_personal") or ""),
    )
    if rid is None:
        return render(
            request,
            "modules/biblioteca.html",
            status_code=400,
            **_ctx(request, user, error="No se pudo guardar el resaltado."),
        )
    return _redirect("resaltados", libro=libro_id)
