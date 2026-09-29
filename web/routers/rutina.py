"""Rutas de la rutina semanal: equipamiento disponible y plan del coach IA."""
from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.db.exercises import (
    agregar_equipment,
    borrar_equipment,
    borrar_routine,
    guardar_routine,
    listar_equipment,
    obtener_routine,
)
from app.exercise_routine import RoutineError, generate_routine
from app.onboarding import modulo_activo
from web.deps import require_onboarded

router = APIRouter(prefix="/app/m/salud", tags=["salud-rutina"])


def _redirect_rutina(**extra) -> RedirectResponse:
    q = ["tab=rutina"]
    for k, v in extra.items():
        if v is not None:
            q.append(f"{k}={quote(str(v), safe='')}")
    return RedirectResponse(f"/app/m/salud?{'&'.join(q)}", status_code=303)


@router.post("/equipamiento")
async def agregar_equipamiento(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
):
    form = await request.form()
    ok, msg = agregar_equipment(int(user["id"]), str(form.get("equipment_name") or ""))
    if ok:
        return _redirect_rutina(flash=msg)
    return _redirect_rutina(error=msg)


@router.post("/equipamiento/{equipment_id}/borrar")
async def borrar_equipamiento(
    equipment_id: int,
    user: Annotated[dict, Depends(require_onboarded)],
):
    borrar_equipment(equipment_id, int(user["id"]))
    return _redirect_rutina(flash="Equipamiento eliminado.")


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
        return _redirect_rutina(error="El área Cuerpo está apagada.")
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


def rutina_page_extras(user_id: int) -> dict:
    """Contexto extra para la pestaña Rutina (usado por salud._ctx)."""
    equipment = listar_equipment(user_id)
    rutina = obtener_routine(user_id)
    selected = (rutina or {}).get("equipamiento") or ["peso corporal"]
    options = ["peso corporal"]
    for row in equipment:
        name = (row.get("equipment_name") or "").strip()
        if name and name not in options:
            options.append(name)
    return {
        "user_equipment": equipment,
        "rutina": rutina,
        "rutina_dias": (rutina or {}).get("dias_semana") or 3,
        "rutina_minutos": (rutina or {}).get("minutos_sesion") or 45,
        "rutina_equipo_opciones": [
            {"name": n, "checked": n in selected} for n in options
        ],
    }
