"""Sandbox HTMX — ideas, snippets, sesiones y mentor IA."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.ai_client import api_key_configurada, chat_simple
from app.billing import PLAN_FREE, limites, plan_vigente
from app.database import (
    CATEGORIAS_DEFAULT_POR_DOMINIO,
    COLORES_ESTADO_SANDBOX,
    DOMINIOS_SANDBOX,
    EMOJIS_DOMINIO,
    EMOJIS_LANG,
    ESTADOS_IDEA,
    LENGUAJES,
    SYSTEM_MENTOR,
    TIPOS_SESION,
    actualizar_idea,
    actualizar_snippet,
    eliminar_idea,
    eliminar_snippet,
    guardar_idea,
    guardar_sesion,
    guardar_snippet,
    incrementar_uso,
    obtener_categorias_dominio,
    obtener_idea,
    obtener_ideas,
    obtener_sesiones_recientes,
    obtener_snippet,
    obtener_snippets,
    parsear_lista_sandbox,
    stats_sandbox,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from app.timezone_config import hoy as _hoy
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app/m/sandbox", tags=["sandbox"])

TABS = ("ideas", "nueva", "snippets", "sesiones", "mentor")


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
    t = (request.query_params.get("tab") or request.session.get("sb_tab") or "ideas").lower()
    if t not in TABS:
        t = "ideas"
    request.session["sb_tab"] = t
    return t


def _tags(raw) -> list:
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw or "").split(",") if t.strip()]


def _enrich_ideas(ideas: list) -> list:
    out = []
    for i in ideas:
        item = dict(i)
        dom = item.get("dominio") or "Otros"
        item["emoji"] = EMOJIS_DOMINIO.get(dom, "🌐")
        item["color"] = COLORES_ESTADO_SANDBOX.get(item.get("estado") or "", "#8b949e")
        item["tags"] = parsear_lista_sandbox(item.get("etiquetas"))
        out.append(item)
    return out


def _enrich_snippets(snippets: list) -> list:
    out = []
    for s in snippets:
        item = dict(s)
        item["emoji_lang"] = EMOJIS_LANG.get(item.get("lenguaje") or "Otro", "🔧")
        item["emoji_dom"] = EMOJIS_DOMINIO.get(item.get("dominio") or "Otros", "🌐")
        item["tags"] = parsear_lista_sandbox(item.get("tags"))
        out.append(item)
    return out


def _ctx(
    request: Request,
    user: dict,
    *,
    flash: str | None = None,
    error: str | None = None,
    mentor_reply: str | None = None,
    idea_edit: dict | None = None,
    snip_edit: dict | None = None,
):
    tab = _tab(request)
    f_estado = request.query_params.get("estado") or ""
    f_dominio = request.query_params.get("dominio") or ""
    f_q = request.query_params.get("q") or ""
    f_lang = request.query_params.get("lang") or ""
    f_snip_dom = request.query_params.get("sdom") or ""
    f_snip_q = request.query_params.get("sq") or ""

    ideas = _enrich_ideas(
        obtener_ideas(
            estado=f_estado or None,
            dominio=f_dominio or None,
            busqueda=f_q,
        )
    )
    todas_ideas = _enrich_ideas(obtener_ideas()) if (f_estado or f_dominio or f_q) else ideas
    snippets = _enrich_snippets(
        obtener_snippets(
            lenguaje=f_lang or None,
            dominio=f_snip_dom or None,
            busqueda=f_snip_q,
        )
    )
    sesiones = obtener_sesiones_recientes(12)
    for s in sesiones:
        s["emoji"] = EMOJIS_DOMINIO.get(s.get("dominio") or "Otros", "🌐")

    edit_id = request.query_params.get("edit")
    if edit_id and idea_edit is None and tab in ("ideas", "nueva"):
        try:
            row = obtener_idea(int(edit_id))
            if row:
                idea_edit = dict(row)
                idea_edit["tags"] = parsear_lista_sandbox(row.get("etiquetas"))
                idea_edit["tags_txt"] = ", ".join(idea_edit["tags"])
        except Exception:
            idea_edit = None
    if edit_id and snip_edit is None and tab == "snippets":
        try:
            row = obtener_snippet(int(edit_id))
            if row:
                snip_edit = dict(row)
                snip_edit["tags"] = parsear_lista_sandbox(row.get("tags"))
                snip_edit["tags_txt"] = ", ".join(snip_edit["tags"])
        except Exception:
            snip_edit = None

    dominio_form = (
        (idea_edit or {}).get("dominio")
        or request.query_params.get("form_dom")
        or "Personal"
    )
    categorias = obtener_categorias_dominio(dominio_form)

    return {
        "title": "Sandbox",
        "user": user,
        "meta": MODULE_TEMPLATES["sandbox"],
        "tab": tab,
        "flash": flash,
        "error": error,
        "mentor_reply": mentor_reply or request.session.pop("sb_mentor", None),
        "modulos_nav": _nav(int(user["id"])),
        "hoy": str(_hoy()),
        "stats": stats_sandbox(),
        "ideas": ideas,
        "snippets": snippets,
        "sesiones": sesiones,
        "dominios": DOMINIOS_SANDBOX,
        "estados_idea": ESTADOS_IDEA,
        "lenguajes": LENGUAJES,
        "tipos_sesion": TIPOS_SESION,
        "categorias": categorias,
        "categorias_por_dominio": CATEGORIAS_DEFAULT_POR_DOMINIO,
        "emojis_dominio": EMOJIS_DOMINIO,
        "emojis_lang": EMOJIS_LANG,
        "colores_estado": COLORES_ESTADO_SANDBOX,
        "f_estado": f_estado,
        "f_dominio": f_dominio,
        "f_q": f_q,
        "f_lang": f_lang,
        "f_snip_dom": f_snip_dom,
        "f_snip_q": f_snip_q,
        "idea_edit": idea_edit,
        "snip_edit": snip_edit,
        "dominio_form": dominio_form,
        "ideas_activas": [
            i
            for i in todas_ideas
            if i.get("estado") not in ("Completado", "Abandonado")
        ]
        or todas_ideas,
        "ia_ok": api_key_configurada(),
    }


def _redirect(tab: str = "ideas", **extra) -> RedirectResponse:
    q = [f"tab={tab}"]
    for k, v in extra.items():
        if v is not None and v != "":
            q.append(f"{k}={v}")
    return RedirectResponse(f"/app/m/sandbox?{'&'.join(q)}", status_code=303)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def sandbox_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    if not modulo_activo("sandbox", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Sandbox",
            user=user,
            meta=MODULE_TEMPLATES["sandbox"],
            clave="sandbox",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    return render(request, "modules/sandbox.html", **_ctx(request, user))


@router.post("/idea")
async def create_idea(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="El título es obligatorio."),
        )
    try:
        prioridad = int(form.get("prioridad") or 3)
        motivacion = int(form.get("motivacion") or 7)
    except Exception:
        prioridad, motivacion = 3, 7
    categoria = str(form.get("categoria_custom") or "").strip() or str(
        form.get("categoria") or ""
    )
    guardar_idea(
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        dominio=str(form.get("dominio") or "Personal"),
        categoria=categoria,
        etiquetas=_tags(form.get("etiquetas")),
        prioridad=max(1, min(5, prioridad)),
        motivacion=max(1, min(10, motivacion)),
        notas=str(form.get("notas") or ""),
        estado=str(form.get("estado") or "Idea"),
    )
    return _redirect("ideas")


@router.post("/idea/{idea_id}/actualizar")
async def update_idea(
    idea_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    if not titulo:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="El título es obligatorio."),
        )
    try:
        prioridad = int(form.get("prioridad") or 3)
        motivacion = int(form.get("motivacion") or 7)
    except Exception:
        prioridad, motivacion = 3, 7
    categoria = str(form.get("categoria_custom") or "").strip() or str(
        form.get("categoria") or ""
    )
    actualizar_idea(
        idea_id=idea_id,
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        dominio=str(form.get("dominio") or "Personal"),
        categoria=categoria,
        etiquetas=_tags(form.get("etiquetas")),
        estado=str(form.get("estado") or "Idea"),
        prioridad=max(1, min(5, prioridad)),
        motivacion=max(1, min(10, motivacion)),
        notas=str(form.get("notas") or ""),
    )
    return _redirect("ideas")


@router.post("/idea/{idea_id}/eliminar")
async def delete_idea(
    idea_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_idea(idea_id)
    return _redirect("ideas")


@router.post("/snippet")
async def create_snippet(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    codigo = str(form.get("codigo") or "").strip()
    if not titulo or not codigo:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="Título y código son obligatorios."),
        )
    guardar_snippet(
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        lenguaje=str(form.get("lenguaje") or "Python"),
        codigo=codigo,
        tags=_tags(form.get("tags")),
        dominio=str(form.get("dominio") or "Programacion"),
    )
    return _redirect("snippets")


@router.post("/snippet/{snip_id}/actualizar")
async def update_snippet(
    snip_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    titulo = str(form.get("titulo") or "").strip()
    codigo = str(form.get("codigo") or "").strip()
    if not titulo or not codigo:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="Título y código son obligatorios."),
        )
    actualizar_snippet(
        snip_id=snip_id,
        titulo=titulo,
        descripcion=str(form.get("descripcion") or ""),
        lenguaje=str(form.get("lenguaje") or "Python"),
        codigo=codigo,
        tags=_tags(form.get("tags")),
        dominio=str(form.get("dominio") or "Programacion"),
    )
    return _redirect("snippets")


@router.post("/snippet/{snip_id}/eliminar")
async def delete_snippet(
    snip_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    eliminar_snippet(snip_id)
    return _redirect("snippets")


@router.post("/snippet/{snip_id}/usar")
async def use_snippet(
    snip_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    incrementar_uso(snip_id)
    return _redirect("snippets")


@router.post("/sesion")
async def create_sesion(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    desc = str(form.get("descripcion") or "").strip()
    if not desc:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="Describe qué hiciste en la sesión."),
        )
    try:
        duracion = int(form.get("duracion") or 60)
        satisfaccion = int(form.get("satisfaccion") or 7)
    except Exception:
        duracion, satisfaccion = 60, 7
    proy = form.get("proyecto_id")
    guardar_sesion(
        fecha=str(form.get("fecha") or _hoy()),
        duracion=max(1, duracion),
        tipo=str(form.get("tipo") or "Investigando"),
        dominio=str(form.get("dominio") or "Personal"),
        proyecto_id=proy,
        descripcion=desc,
        codigo=str(form.get("codigo") or ""),
        satisfaccion=max(1, min(10, satisfaccion)),
    )
    return _redirect("sesiones")


@router.post("/mentor")
async def mentor(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    pregunta = str(form.get("pregunta") or "").strip()
    if not pregunta:
        return render(
            request,
            "modules/sandbox.html",
            status_code=400,
            **_ctx(request, user, error="Escribe una pregunta para el mentor."),
        )
    if not api_key_configurada():
        return render(
            request,
            "modules/sandbox.html",
            **_ctx(
                request,
                user,
                error="IA offline — configura GROQ_API_KEY.",
            ),
        )
    dominio = str(form.get("dominio") or "Personal")
    tipo_ayuda = str(form.get("tipo_ayuda") or "Consejo general")
    contexto_extra = f"Dominio: {dominio}\nTipo de ayuda: {tipo_ayuda}"
    idea_id = form.get("idea_id")
    if idea_id:
        try:
            idea = obtener_idea(int(idea_id))
            if idea:
                contexto_extra += (
                    f"\nIdea: {idea.get('titulo')}\n"
                    f"Estado: {idea.get('estado')}\n"
                    f"Descripción: {idea.get('descripcion') or ''}\n"
                    f"Notas: {idea.get('notas') or ''}"
                )
        except Exception:
            pass
    mensaje = (
        f"{contexto_extra}\n\n"
        f"Pregunta: {pregunta}\n\n"
        "Da una respuesta práctica y concreta. "
        "Si aplica, incluye un principio bíblico relevante."
    )
    reply = chat_simple(mensaje, contexto=SYSTEM_MENTOR)
    request.session["sb_mentor"] = reply or "Sin respuesta."
    return _redirect("mentor")
