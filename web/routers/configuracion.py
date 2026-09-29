"""Centro de configuración: interruptores de área, día a día y datos de la cuenta."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.billing import modulos_max, plan_vigente, puede_exportar, puede_google, puede_telegram
from app.cuenta import (
    DIAS_HABITO,
    FRECUENCIAS,
    METODOS,
    MONEDAS,
    areas_rueda,
    borrar_cuenta,
    catalogo_areas_rueda,
    rueda_conservando_estructura,
    rueda_desde_eleccion,
    catalogo_sobres,
    clave_categoria,
    exportar_datos,
    guardar_categorias,
    guardar_modulos,
    dias_de_frecuencia,
    frecuencia_desde_eleccion,
    guardar_prefs,
    leer_prefs,
)
from app.onboarding import listar_modulos_usuario, nombre_visible
from app.ritual import actualizar_habito, crear_habito, listar_habitos_config, set_habito_activo
from app.rueda import AREAS
from app.templates import MODULE_TEMPLATES, SUPERFICIES
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/configuracion", tags=["configuracion"])

PESTANAS = ("areas", "dia", "dinero", "rueda", "conexiones", "datos")
_SECCIONES = ("areas", "dia", "dinero", "rueda")


def _habitos_con_dias(uid: int) -> list[dict]:
    presets = {clave for clave, _ in FRECUENCIAS}
    filas = []
    for hab in listar_habitos_config(uid):
        fila = dict(hab)
        freq = str(fila.get("frecuencia") or "diaria")
        fila["es_custom"] = freq not in presets
        fila["dias"] = dias_de_frecuencia(freq)
        filas.append(fila)
    return filas

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


def _ctx(
    request: Request,
    user: dict,
    *,
    error: str | None = None,
    flash: str | None = None,
    tab: str = "areas",
) -> dict:
    uid = int(user["id"])
    filas = {r["modulo"]: r for r in listar_modulos_usuario(uid)}
    prefs = leer_prefs(uid)
    modulos = []
    for clave in MODULE_TEMPLATES:
        row = filas.get(clave) or {}
        modulos.append({
            "clave": clave,
            "emoji": MODULE_TEMPLATES[clave]["emoji"],
            "nombre": nombre_visible(clave),
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
    habitos = _habitos_con_dias(uid)
    return {
        "title": "Configuración",
        "user": user,
        "error": error or request.session.pop("config_error", None),
        "flash": flash or request.session.pop("config_flash", None),
        "modulos": modulos,
        "superficies": superficies,
        "prefs": prefs,
        "monedas": MONEDAS,
        "metodos": METODOS,
        "frecuencias": FRECUENCIAS,
        "dias_habito": DIAS_HABITO,
        "habitos": habitos,
        "habitos_activos": [h for h in habitos if int(h.get("activo") or 0) == 1],
        "habitos_archivados": [h for h in habitos if int(h.get("activo") or 0) != 1],
        "categorias": categorias,
        "areas": areas_rueda(uid),
        "areas_cfg": catalogo_areas_rueda(uid),
        "salud_ops": _SALUD,
        "salud_on": set(prefs["salud"]) or {k for k, _ in _SALUD},
        "puede_exportar": puede_exportar(plan_vigente(user)),
        "areas_base": AREAS,
        "tab": tab if tab in PESTANAS else "areas",
        "pestanas": PESTANAS,
        **_ctx_conexiones(user, tab),
    }


def _estado_google() -> dict:
    estado = {"autenticado": False, "error": ""}
    try:
        from app.google_fit import estado_google_fit

        estado = estado_google_fit() or estado
    except Exception as e:
        estado["error"] = str(e)
    return estado


def _ctx_conexiones(user: dict, tab: str) -> dict:
    vacio = {
        "puede_google": False,
        "fit": {},
        "puede_telegram": False,
        "tg_link": None,
        "tg_code": None,
        "tg_deep_link": "",
        "tg_recordatorio_min": 0,
        "tg_recordatorio_opciones": (),
        "tg_briefing": None,
        "tg_briefing_extras": (),
    }
    if tab != "conexiones":
        return vacio
    from app.db.telegram_state import BRIEFING_EXTRAS, RECORDATORIO_OPCIONES, prefs_briefing, recordatorio_min
    from app.telegram import deep_link, link_status

    plan = plan_vigente(user)
    uid = int(user["id"])
    return {
        "puede_google": puede_google(plan),
        "fit": _estado_google(),
        "puede_telegram": puede_telegram(plan),
        "tg_link": link_status(uid),
        "tg_recordatorio_min": recordatorio_min(uid),
        "tg_recordatorio_opciones": RECORDATORIO_OPCIONES,
        "tg_briefing": prefs_briefing(uid),
        "tg_briefing_extras": BRIEFING_EXTRAS,
        "tg_code": None,
        "tg_deep_link": "",
    }


def _tab_pedido(request: Request) -> str:
    tab = str(request.query_params.get("tab") or "areas")
    return tab if tab in PESTANAS else "areas"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def configuracion_page(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    tab = _tab_pedido(request)
    flash = None
    error = None
    if tab == "conexiones":
        g = request.query_params.get("google")
        if g == "ok":
            flash = "Google Fit/Calendar vinculados."
        elif g == "denied":
            error = "Google denegó el acceso."
        elif g == "err":
            error = request.query_params.get("msg") or "No se pudo vincular Google."
    ctx = _ctx(request, user, tab=tab, flash=flash, error=error)
    if tab == "conexiones":
        code = request.session.get("tg_code")
        from app.telegram import deep_link

        ctx["tg_code"] = code
        ctx["tg_deep_link"] = deep_link(code or "")
    return render(request, "configuracion.html", **ctx)


def _volver_habitos(request: Request, ok: bool, msg: str) -> RedirectResponse:
    request.session["config_flash" if ok else "config_error"] = msg
    return RedirectResponse("/app/configuracion?tab=dia", status_code=303)


@router.post("/habitos")
async def habito_crear(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    form = await request.form()
    ok, msg = crear_habito(
        str(form.get("label") or ""),
        str(form.get("emoji") or ""),
        str(form.get("hora") or ""),
        user_id=int(user["id"]),
        frecuencia=str(form.get("frecuencia") or "diaria"),
    )
    return _volver_habitos(request, ok, msg)


@router.post("/habitos/{clave}/editar")
async def habito_editar(
    clave: str, request: Request, user: Annotated[dict, Depends(require_onboarded)]
):
    form = await request.form()
    ok, msg = actualizar_habito(
        clave,
        str(form.get("label") or ""),
        str(form.get("emoji") or ""),
        str(form.get("hora") or ""),
        user_id=int(user["id"]),
        frecuencia=str(form.get("frecuencia")) if form.get("frecuencia") else None,
    )
    return _volver_habitos(request, ok, msg)


@router.post("/habitos/{clave}/archivar")
def habito_archivar(clave: str, request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    set_habito_activo(clave, False, user_id=int(user["id"]))
    return _volver_habitos(request, True, "Hábito archivado; su historial se conserva.")


@router.post("/habitos/{clave}/reactivar")
def habito_reactivar(clave: str, request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    set_habito_activo(clave, True, user_id=int(user["id"]))
    return _volver_habitos(request, True, "Hábito reactivado.")


def _guardar_parcial(uid: int, **cambios) -> None:
    """Escribe solo los campos que vienen; el resto queda como está."""
    prefs = leer_prefs(uid)
    prefs.update(cambios)
    guardar_prefs(
        uid,
        moneda=str(prefs["moneda"]),
        metodo=str(prefs["metodo"]),
        ritual_a=str(prefs["ritual_a"]),
        ritual_b=str(prefs["ritual_b"]),
        hora_desde=int(prefs["hora_desde"]),
        hora_hasta=int(prefs["hora_hasta"]),
        rueda=prefs["rueda"],
        salud=list(prefs["salud"]),
        idioma=prefs.get("idioma") or None,
    )


def _guardar_habitos(uid: int, form) -> str | None:
    from app.db.core import ejecutar

    for hab in listar_habitos_config(uid):
        freq_sel = str(form.get(f"freq_{hab['clave']}") or "")
        if not freq_sel:
            continue
        freq = frecuencia_desde_eleccion(
            freq_sel, [str(d) for d in form.getlist(f"freqdia_{hab['clave']}")]
        )
        if freq is None:
            return "Elige al menos un día."
        ejecutar(
            "UPDATE habitos_config SET frecuencia = ? WHERE user_id = ? AND clave = ?",
            [freq, uid, hab["clave"]],
        )
    return None


def _guardar_categorias_form(uid: int, form) -> None:
    categorias = []
    for clave in form.getlist("cat_clave"):
        categorias.append((str(clave), str(form.get(f"cat_nombre_{clave}") or "")))
    nueva = str(form.get("cat_nueva") or "").strip()
    if nueva:
        categorias.append((clave_categoria(nueva), nueva))
    if categorias:
        guardar_categorias(uid, categorias)


def _idioma_form(form):
    from app.i18n import normalizar

    raw = form.get("idioma")
    return normalizar(str(raw)) if raw else None


def _horas_form(form, prefs: dict) -> tuple[int, int]:
    try:
        desde = int(form.get("hora_desde") if form.get("hora_desde") not in (None, "") else prefs["hora_desde"])
        hasta = int(form.get("hora_hasta") if form.get("hora_hasta") not in (None, "") else prefs["hora_hasta"])
    except ValueError:
        desde, hasta = int(prefs["hora_desde"]), int(prefs["hora_hasta"])
    return desde, hasta


def _rueda_form(uid: int, form):
    prev = leer_prefs(uid)["rueda"]
    etiquetas = {clave: str(form.get(f"rueda_{clave}") or "") for clave, _nombre, _emoji in AREAS}
    for fila in catalogo_areas_rueda(uid):
        etiquetas.setdefault(fila["clave"], str(form.get(f"rueda_{fila['clave']}") or ""))
    if str(form.get("rueda_areas") or "") == "1":
        return rueda_desde_eleccion(
            prev,
            activas=[str(v) for v in form.getlist("rueda_on")],
            nueva=str(form.get("rueda_nueva") or ""),
            nueva_emoji=str(form.get("rueda_nueva_emoji") or ""),
            etiquetas=etiquetas,
        )
    return rueda_conservando_estructura(prev, etiquetas), None


def _respuesta_guardada(request: Request, seccion: str, idioma: str | None):
    request.session["config_flash"] = "Configuración guardada."
    destino = "/app/configuracion" if not seccion else f"/app/configuracion?tab={seccion}"
    response = RedirectResponse(destino, status_code=303)
    if idioma:
        from app.i18n import aplicar_cookie_idioma

        aplicar_cookie_idioma(response, idioma)
    return response


def _error(request: Request, user: dict, seccion: str, mensaje: str):
    return render(
        request,
        "configuracion.html",
        status_code=400,
        **_ctx(request, user, error=mensaje, tab=seccion or "areas"),
    )


def _guardar_seccion(request: Request, user: dict, form, seccion: str):
    uid = int(user["id"])
    prefs = leer_prefs(uid)
    idioma = None
    if seccion == "areas":
        error = guardar_modulos(
            uid,
            activos={str(v) for v in form.getlist("activo")},
            tope=modulos_max(plan_vigente(user)),
        )
        if error:
            return _error(request, user, seccion, error)
        idioma = _idioma_form(form)
        if idioma:
            _guardar_parcial(uid, idioma=idioma)
    elif seccion == "dia":
        desde, hasta = _horas_form(form, prefs)
        error = _guardar_habitos(uid, form)
        if error:
            return _error(request, user, seccion, error)
        _guardar_parcial(
            uid,
            ritual_a=str(form.get("ritual_a") or ""),
            ritual_b=str(form.get("ritual_b") or ""),
            hora_desde=desde,
            hora_hasta=hasta,
            salud=[str(v) for v in form.getlist("salud")],
        )
    elif seccion == "dinero":
        _guardar_parcial(
            uid,
            moneda=str(form.get("moneda") or prefs["moneda"]),
            metodo=str(form.get("metodo") or prefs["metodo"]),
        )
        _guardar_categorias_form(uid, form)
    elif seccion == "rueda":
        rueda, error_rueda = _rueda_form(uid, form)
        if error_rueda:
            return _error(request, user, seccion, error_rueda)
        _guardar_parcial(uid, rueda=rueda)
    return _respuesta_guardada(request, seccion, idioma)


@router.post("")
async def configuracion_guardar(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    uid = int(user["id"])
    form = await request.form()
    seccion = str(form.get("seccion") or "")
    if seccion in _SECCIONES:
        return _guardar_seccion(request, user, form, seccion)
    prev_rueda = leer_prefs(uid)["rueda"]
    etiquetas = {
        clave: str(form.get(f"rueda_{clave}") or "")
        for clave, _nombre, _emoji in AREAS
    }
    for fila in catalogo_areas_rueda(uid):
        etiquetas.setdefault(fila["clave"], str(form.get(f"rueda_{fila['clave']}") or ""))
    if str(form.get("rueda_areas") or "") == "1":
        rueda, error_rueda = rueda_desde_eleccion(
            prev_rueda,
            activas=[str(v) for v in form.getlist("rueda_on")],
            nueva=str(form.get("rueda_nueva") or ""),
            nueva_emoji=str(form.get("rueda_nueva_emoji") or ""),
            etiquetas=etiquetas,
        )
        if error_rueda:
            return render(
                request,
                "configuracion.html",
                status_code=400,
                **_ctx(request, user, error=error_rueda),
            )
    else:
        rueda = rueda_conservando_estructura(prev_rueda, etiquetas)
    activos = {str(v) for v in form.getlist("activo")}
    error = guardar_modulos(
        uid,
        activos=activos,
        tope=modulos_max(plan_vigente(user)),
    )
    if error:
        return render(
            request,
            "configuracion.html",
            status_code=400,
            **_ctx(request, user, error=error),
        )
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
        freq_sel = str(form.get(f"freq_{hab['clave']}") or "")
        if not freq_sel:
            continue
        freq = frecuencia_desde_eleccion(freq_sel, [str(d) for d in form.getlist(f"freqdia_{hab['clave']}")])
        if freq is None:
            return render(
                request,
                "configuracion.html",
                status_code=400,
                **_ctx(request, user, error="Elige al menos un día."),
            )
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
        return RedirectResponse("/app/configuracion?tab=datos#borrar", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
