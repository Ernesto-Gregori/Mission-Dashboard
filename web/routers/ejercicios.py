"""Rutas de biblioteca de ejercicios (subida de video, análisis, edición)."""
from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.billing import PLAN_FREE, limites, plan_vigente
from app.db.exercises import (
    CONFIANZAS,
    NIVELES,
    PLATFORMS,
    TIPOS_MOVIMIENTO,
    agregar_equipment,
    actualizar_exercise,
    borrar_equipment,
    borrar_exercise,
    borrar_routine,
    fail_stale_processing,
    guardar_routine,
    listar_equipment,
    listar_exercises,
    mark_processing,
    obtener_exercise,
    obtener_routine,
)
from app.exercise_analysis import run_exercise_analysis
from app.exercise_routine import RoutineError, generate_routine
from app.exercise_uploads import (
    VideoUploadError,
    hard_max_video_seconds,
    max_video_bytes,
    max_video_seconds,
    resolve_exercise_video_path,
    save_exercise_video,
)
from app.onboarding import listar_modulos_usuario, modulo_activo
from app.templates import MODULE_TEMPLATES
from web.deps import render, require_onboarded

router = APIRouter(prefix="/app/m/salud", tags=["salud-ejercicios"])

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "facebook": "Facebook",
    "otro": "Otro",
}


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


def _redirect_ejercicios(**extra) -> RedirectResponse:
    q = ["tab=ejercicios"]
    for k, v in extra.items():
        if v is not None:
            q.append(f"{k}={quote(str(v), safe='')}")
    return RedirectResponse(f"/app/m/salud?{'&'.join(q)}", status_code=303)


def _redirect_rutina(**extra) -> RedirectResponse:
    q = ["tab=rutina"]
    for k, v in extra.items():
        if v is not None:
            q.append(f"{k}={quote(str(v), safe='')}")
    return RedirectResponse(f"/app/m/salud?{'&'.join(q)}", status_code=303)


def _detail_ctx(request: Request, user: dict, ex: dict, **extra) -> dict:
    return {
        "title": ex.get("nombre_ejercicio") or "Ejercicio",
        "user": user,
        "meta": MODULE_TEMPLATES["salud"],
        "modulos_nav": _nav(int(user["id"])),
        "ex": ex,
        "platforms": PLATFORMS,
        "platform_labels": PLATFORM_LABELS,
        "niveles": NIVELES,
        "tipos_movimiento": TIPOS_MOVIMIENTO,
        "confianzas": CONFIANZAS,
        **extra,
    }


@router.post("/ejercicios/subir")
async def subir_ejercicio(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    source_platform: str = Form(""),
):
    if not modulo_activo("salud", int(user["id"])):
        return _redirect_ejercicios(error="Módulo Salud inactivo.")

    uid = int(user["id"])
    raw = await video.read(max_video_bytes() + 1)
    try:
        if len(raw) > max_video_bytes():
            mb = max_video_bytes() // (1024 * 1024)
            raise VideoUploadError(f"El video supera el límite de {mb} MB.")
        rel, duration = save_exercise_video(
            uid,
            raw,
            video.filename,
            video.content_type,
        )
    except VideoUploadError as e:
        return _redirect_ejercicios(error=str(e))
    except Exception:
        return _redirect_ejercicios(error="No se pudo guardar el video.")

    from app.db.exercises import crear_exercise

    platform = (source_platform or "").strip().lower() or None
    eid = crear_exercise(uid, rel, platform)
    background_tasks.add_task(run_exercise_analysis, eid, uid)

    extra = {"flash": "Video subido. El coach IA está analizando el ejercicio."}
    suggested = max_video_seconds()
    if duration is not None and duration > suggested:
        extra["warn"] = (
            f"El clip dura {duration:.0f} s (lo ideal es {suggested} s). "
            "Se analizará igual si es un solo ejercicio."
        )
    return _redirect_ejercicios(**extra)


@router.post("/ejercicios/{exercise_id}/reintentar")
async def reintentar_ejercicio(
    exercise_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
    background_tasks: BackgroundTasks,
):
    uid = int(user["id"])
    if not mark_processing(exercise_id, uid):
        return _redirect_ejercicios(error="Solo se puede reintentar un análisis fallido.")
    background_tasks.add_task(run_exercise_analysis, exercise_id, uid)
    return _redirect_ejercicios(flash="Reintentando el análisis.")


@router.get("/ejercicios/fragmento", response_class=HTMLResponse)
def ejercicios_fragmento(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    uid = int(user["id"])
    fail_stale_processing(uid)
    ejercicios = listar_exercises(uid)
    return render(
        request,
        "modules/_ejercicios_lista.html",
        ejercicios=ejercicios,
        hay_processing=any(e.get("status") == "processing" for e in ejercicios),
        platform_labels=PLATFORM_LABELS,
    )


@router.get("/ejercicios/{exercise_id}", response_class=HTMLResponse)
def ejercicio_detalle(
    exercise_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    if not modulo_activo("salud", int(user["id"])):
        return render(
            request,
            "paywall.html",
            title="Salud",
            user=user,
            meta=MODULE_TEMPLATES["salud"],
            clave="salud",
            plan=plan_vigente(user),
            plan_free=plan_vigente(user) == PLAN_FREE,
            lim_free=limites(PLAN_FREE),
            modulos_nav=_nav(int(user["id"])),
        )
    ex = obtener_exercise(exercise_id, int(user["id"]))
    if not ex:
        return _redirect_ejercicios(error="No encontramos ese ejercicio.")
    flash = request.query_params.get("flash")
    error = request.query_params.get("error")
    return render(
        request,
        "modules/ejercicio_detalle.html",
        **_detail_ctx(request, user, ex, flash=flash, error=error),
    )


@router.post("/ejercicios/{exercise_id}/eliminar")
async def eliminar_ejercicio(
    exercise_id: int,
    user: Annotated[dict, Depends(require_onboarded)],
):
    uid = int(user["id"])
    if not borrar_exercise(exercise_id, uid):
        return _redirect_ejercicios(error="No encontramos ese ejercicio.")
    return _redirect_ejercicios(flash="Ejercicio eliminado.")


@router.post("/ejercicios/{exercise_id}/editar")
async def editar_ejercicio(
    exercise_id: int,
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    uid = int(user["id"])
    ex = obtener_exercise(exercise_id, uid)
    if not ex:
        return _redirect_ejercicios(error="No encontramos ese ejercicio.")
    form = await request.form()

    def _lines(name: str) -> list[str]:
        raw = str(form.get(name) or "")
        return [p.strip() for p in re_split_lines(raw) if p.strip()]

    campos = {
        "nombre_ejercicio": str(form.get("nombre_ejercicio") or "").strip(),
        "grupos_musculares_primarios": _lines("grupos_musculares_primarios"),
        "grupos_musculares_secundarios": _lines("grupos_musculares_secundarios"),
        "equipamiento_detectado": _lines("equipamiento_detectado"),
        "nivel_dificultad": str(form.get("nivel_dificultad") or "").strip(),
        "tipo_movimiento": str(form.get("tipo_movimiento") or "").strip(),
        "series_reps_mencionadas": str(form.get("series_reps_mencionadas") or "").strip() or None,
        "series_reps_sugeridas": str(form.get("series_reps_sugeridas") or "").strip() or None,
        "cues_de_forma": _lines("cues_de_forma"),
        "confianza_analisis": str(form.get("confianza_analisis") or "").strip(),
        "source_platform": str(form.get("source_platform") or "").strip() or None,
    }
    dur_raw = str(form.get("duracion_estimada_segundos") or "").strip()
    if dur_raw:
        try:
            campos["duracion_estimada_segundos"] = int(float(dur_raw))
        except ValueError:
            return render(
                request,
                "modules/ejercicio_detalle.html",
                status_code=400,
                **_detail_ctx(request, user, ex, error="Duración estimada inválida."),
            )
    else:
        campos["duracion_estimada_segundos"] = None

    if not campos["nombre_ejercicio"]:
        return render(
            request,
            "modules/ejercicio_detalle.html",
            status_code=400,
            **_detail_ctx(request, user, ex, error="El nombre del ejercicio es obligatorio."),
        )

    actualizar_exercise(exercise_id, uid, campos)
    return RedirectResponse(
        f"/app/m/salud/ejercicios/{exercise_id}?flash={quote('Cambios guardados.')}",
        status_code=303,
    )


@router.get("/ejercicios/{exercise_id}/video")
def servir_video(
    exercise_id: int,
    user: Annotated[dict, Depends(require_onboarded)],
):
    ex = obtener_exercise(exercise_id, int(user["id"]))
    if not ex:
        return RedirectResponse("/app/m/salud?tab=ejercicios", status_code=303)
    path = resolve_exercise_video_path(ex.get("source_video_url") or "", int(user["id"]))
    if not path:
        return RedirectResponse(
            f"/app/m/salud/ejercicios/{exercise_id}?error={quote('Video no disponible.')}",
            status_code=303,
        )
    media = "video/quicktime" if path.suffix.lower() == ".mov" else "video/mp4"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/equipamiento")
async def agregar_equipamiento(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    ok, msg = agregar_equipment(int(user["id"]), str(form.get("equipment_name") or ""))
    if ok:
        return _redirect_ejercicios(flash=msg)
    return _redirect_ejercicios(error=msg)


@router.post("/equipamiento/{equipment_id}/borrar")
async def borrar_equipamiento(
    equipment_id: int,
    user: Annotated[dict, Depends(require_onboarded)],
):
    borrar_equipment(equipment_id, int(user["id"]))
    return _redirect_ejercicios(flash="Equipamiento eliminado.")


def _form_equipo(form) -> list[str]:
    if hasattr(form, "getlist"):
        raw = form.getlist("equipo")
    else:
        raw = [form.get("equipo")]
    out = []
    for item in raw or []:
        name = str(item or "").strip()[:80]
        if name and name not in out:
            out.append(name)
    return out or ["peso corporal"]


@router.post("/rutina/generar")
async def generar_rutina(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    if not modulo_activo("salud", int(user["id"])):
        return _redirect_rutina(error="Módulo Salud inactivo.")
    uid = int(user["id"])
    form = await request.form()
    try:
        dias = int(float(str(form.get("dias_semana") or "3")))
        minutos = int(float(str(form.get("minutos_sesion") or "45")))
    except ValueError:
        return _redirect_rutina(error="Revisa los días y los minutos.")
    equipo = _form_equipo(form)
    notas = str(form.get("notas") or "").strip()
    try:
        plan = generate_routine(
            user_id=uid,
            dias=dias,
            minutos=minutos,
            equipo=equipo,
            notas=notas,
        )
    except RoutineError as e:
        return _redirect_rutina(error=str(e))
    guardar_routine(
        uid,
        dias,
        minutos,
        equipo,
        plan,
        notas_usuario=notas,
        notas_coach=plan.get("notas_coach"),
    )
    return _redirect_rutina(flash="Rutina lista. El coach ya armó tu semana.")


@router.post("/rutina/mejorar")
async def mejorar_rutina(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    uid = int(user["id"])
    current = obtener_routine(uid)
    if not current:
        return _redirect_rutina(error="Primero arma una rutina.")
    form = await request.form()
    notas = str(form.get("notas") or "").strip()
    if not notas:
        return _redirect_rutina(error="Dile al coach qué quieres cambiar.")
    try:
        plan = generate_routine(
            user_id=uid,
            dias=current["dias_semana"],
            minutos=current["minutos_sesion"],
            equipo=current.get("equipamiento") or ["peso corporal"],
            notas=notas,
            previous=current.get("plan"),
        )
    except RoutineError as e:
        return _redirect_rutina(error=str(e))
    guardar_routine(
        uid,
        current["dias_semana"],
        current["minutos_sesion"],
        current.get("equipamiento") or ["peso corporal"],
        plan,
        notas_usuario=notas,
        notas_coach=plan.get("notas_coach"),
    )
    return _redirect_rutina(flash="El coach actualizó tu rutina.")


@router.post("/rutina/eliminar")
async def eliminar_rutina(
    user: Annotated[dict, Depends(require_onboarded)],
):
    if not borrar_routine(int(user["id"])):
        return _redirect_rutina(error="No hay una rutina que borrar.")
    return _redirect_rutina(flash="Rutina eliminada.")


def re_split_lines(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in raw.replace(";", "\n").split("\n"):
        for bit in chunk.split(","):
            if bit.strip():
                parts.append(bit.strip())
    return parts


def ejercicios_page_extras(user_id: int) -> dict:
    """Contexto extra para el tab Mis ejercicios (usado por salud._ctx)."""
    fail_stale_processing(user_id)
    ejercicios = listar_exercises(user_id)
    equipment = listar_equipment(user_id)
    rutina = obtener_routine(user_id)
    selected = (rutina or {}).get("equipamiento") or ["peso corporal"]
    options = ["peso corporal"]
    for row in equipment:
        name = (row.get("equipment_name") or "").strip()
        if name and name not in options:
            options.append(name)
    return {
        "ejercicios": ejercicios,
        "hay_processing": any(e.get("status") == "processing" for e in ejercicios),
        "user_equipment": equipment,
        "platforms": PLATFORMS,
        "platform_labels": PLATFORM_LABELS,
        "video_max_mb": max_video_bytes() // (1024 * 1024),
        "video_max_seconds": max_video_seconds(),
        "video_hard_max_seconds": hard_max_video_seconds(),
        "rutina": rutina,
        "rutina_dias": (rutina or {}).get("dias_semana") or 3,
        "rutina_minutos": (rutina or {}).get("minutos_sesion") or 45,
        "rutina_equipo_opciones": [
            {"name": n, "checked": n in selected} for n in options
        ],
        "rutina_ready_count": sum(1 for e in ejercicios if e.get("status") == "ready"),
    }
