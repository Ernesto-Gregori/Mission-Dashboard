"""Centro de configuración: alias, interruptores y datos de la cuenta."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.billing import modulos_max, plan_vigente, puede_exportar
from app.cuenta import (
    FRECUENCIAS,
    METODOS,
    MONEDAS,
    areas_rueda,
    borrar_cuenta,
    catalogo_sobres,
    clave_categoria,
    exportar_datos,
    guardar_categorias,
    guardar_modulos,
    guardar_prefs,
    leer_prefs,
    snippets_visibles,
)
from app.onboarding import listar_modulos_usuario, nombre_visible
from app.ritual import listar_habitos_config
from app.rueda import AREAS
from app.templates import MODULE_TEMPLATES, SUPERFICIES
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/configuracion", tags=["configuracion"])

_SUPERFICIE_NOMBRE = {
    "ritual": ("Ritual", "Gratitud e intención en Hoy"),
    "rueda": ("Rueda de la vida", "La puntuación de la revisión semanal"),
    "alma": ("Alma", "La asistente"),
}
_SALUD = (
    ("sueno", "Sueño"),
    ("energia_manana", "Energía de la mañana"),
    ("energia_tarde", "Energía de la tarde"),
    ("energia_noche", "Energía de la noche"),
)


def _ctx(request: Request, user: dict, *, error: str | None = None, flash: str | None = None) -> dict:
    uid = int(user["id"])
    filas = {r["modulo"]: r for r in listar_modulos_usuario(uid)}
    prefs = leer_prefs(uid)
    modulos = []
    for clave in MODULE_TEMPLATES:
        row = filas.get(clave) or {}
        modulos.append({
            "clave": clave,
            "emoji": MODULE_TEMPLATES[clave]["emoji"],
            "nombre": nombre_visible(clave, uid),
            "alias": (row.get("alias") or ""),
            "activo": int(row.get("activo") or 0) == 1,
        })
    superficies = []
    for clave in SUPERFICIES:
        row = filas.get(clave)
        activo = True if row is None else int(row.get("activo") or 0) == 1
        superficies.append({
            "clave": clave,
            "nombre": _SUPERFICIE_NOMBRE[clave][0],
            "detalle": _SUPERFICIE_NOMBRE[clave][1],
            "activo": activo,
        })
    categorias = [
        {"clave": clave, "nombre": data["nombre"]}
        for clave, data in catalogo_sobres(uid).items()
    ]
    return {
        "title": "Configuración",
        "user": user,
        "error": error or request.session.pop("config_error", None),
        "flash": flash or request.session.pop("config_flash", None),
        "modulos": modulos,
        "superficies": superficies,
        "snippets": snippets_visibles(uid),
        "prefs": prefs,
        "monedas": MONEDAS,
        "metodos": METODOS,
        "frecuencias": FRECUENCIAS,
        "habitos": listar_habitos_config(uid),
        "categorias": categorias,
        "areas": areas_rueda(uid),
        "salud_ops": _SALUD,
        "salud_on": set(prefs["salud"]) or {k for k, _ in _SALUD},
        "puede_exportar": puede_exportar(plan_vigente(user)),
        "areas_base": AREAS,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def configuracion_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    return render(request, "configuracion.html", **_ctx(request, user))


@router.post("")
async def configuracion_guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    uid = int(user["id"])
    form = await request.form()
    activos = {str(v) for v in form.getlist("activo")}
    alias = {
        clave: str(form.get(f"alias_{clave}") or "")
        for clave in MODULE_TEMPLATES
    }
    error = guardar_modulos(
        uid,
        activos=activos,
        alias=alias,
        snippets=str(form.get("snippets") or "") in ("1", "on", "true"),
        tope=modulos_max(plan_vigente(user)),
    )
    if error:
        return render(
            request,
            "configuracion.html",
            status_code=400,
            **_ctx(request, user, error=error),
        )
    rueda = {}
    for clave, _nombre, _emoji in AREAS:
        texto = str(form.get(f"rueda_{clave}") or "").strip()
        if texto:
            rueda[clave] = texto[:40]
    salud = [str(v) for v in form.getlist("salud")]
    try:
        desde = int(form.get("hora_desde") or 6)
        hasta = int(form.get("hora_hasta") or 22)
    except ValueError:
        desde, hasta = 6, 22
    from app.i18n import normalizar

    raw_idioma = form.get("idioma")
    idioma = normalizar(str(raw_idioma)) if raw_idioma else None
    guardar_prefs(
        uid,
        moneda=str(form.get("moneda") or "USD"),
        metodo=str(form.get("metodo") or "sobres"),
        ritual_a=str(form.get("ritual_a") or ""),
        ritual_b=str(form.get("ritual_b") or ""),
        hora_desde=desde,
        hora_hasta=hasta,
        rueda=rueda,
        salud=salud,
        idioma=idioma,
    )
    categorias = []
    for clave in form.getlist("cat_clave"):
        categorias.append((str(clave), str(form.get(f"cat_nombre_{clave}") or "")))
    nueva = str(form.get("cat_nueva") or "").strip()
    if nueva:
        categorias.append((clave_categoria(nueva), nueva))
    if categorias:
        guardar_categorias(uid, categorias)
    from app.db.core import ejecutar

    for hab in listar_habitos_config(uid):
        freq = str(form.get(f"freq_{hab['clave']}") or "")
        if freq:
            ejecutar(
                "UPDATE habitos_config SET frecuencia = ? WHERE user_id = ? AND clave = ?",
                [freq, uid, hab["clave"]],
            )
    request.session["config_flash"] = "Configuración guardada."
    response = RedirectResponse("/app/configuracion", status_code=303)
    if idioma:
        from app.i18n import aplicar_cookie_idioma

        aplicar_cookie_idioma(response, idioma)
    return response


@router.get("/exportar")
def configuracion_exportar(user: Annotated[dict, Depends(require_onboarded)]):
    if not puede_exportar(plan_vigente(user)):
        return Response("El plan Free no incluye exportación.", status_code=403)
    data = exportar_datos(int(user["id"]))
    body = json.dumps(data, ensure_ascii=False, default=str)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=mission-cuenta.json"},
    )


@router.post("/borrar")
async def configuracion_borrar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    ok, msg = borrar_cuenta(int(user["id"]), str(form.get("password") or ""))
    if not ok:
        request.session["config_error"] = msg
        return RedirectResponse("/app/configuracion#borrar", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
