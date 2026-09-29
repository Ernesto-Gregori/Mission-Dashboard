from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.billing import plan_vigente, puede_google
from app.calendar_sync import completar_item, items_foco, pull_range
from app.coach_insights import ultimo_briefing
from app.onboarding import modulo_activo
from app.cuenta import ritual_etiquetas
from app.ritual import habitos_hoy, listar_habitos, obtener_ritual
from app.timezone_config import hoy as _hoy
from web.checkout_flash import consume_checkout_query, pop_checkout_flash
from web.deps import require_onboarded, render

router = APIRouter(prefix="/app", tags=["dashboard"])
log = logging.getLogger("mission.dashboard")


def _aviso_hoy(
    *,
    hoy_error: str | None,
    foco_falla: bool,
    puede_cal: bool,
    google_ok: bool,
    google_error: str,
    checkout_flash: dict | None,
    hoy_flash: str | None,
    onboarded: bool,
    just: Any,
) -> dict | None:
    """Un solo aviso. Lo urgente tapa al resto en esta carga."""
    if hoy_error:
        return {"kind": "error", "role": "alert", "message": hoy_error}
    if foco_falla:
        return {
            "kind": "warn",
            "role": "alert",
            "message": "No se pudo leer tu agenda de hoy. Vuelve a intentar en un momento.",
        }
    if hoy_flash:
        return {"kind": "ok", "role": "status", "message": hoy_flash}
    if puede_cal and google_error:
        aviso = {"kind": "warn", "role": "alert", "message": google_error}
        if not google_ok:
            aviso["href"] = "/app/configuracion?tab=conexiones"
            aviso["link"] = "Conectar en Configuración"
        return aviso
    if checkout_flash and checkout_flash.get("kind") != "ok":
        return {"kind": "warn", "role": "status", "message": checkout_flash.get("message") or ""}
    if checkout_flash:
        return {"kind": "ok", "role": "status", "message": checkout_flash.get("message") or ""}
    if onboarded:
        return {
            "kind": "ok",
            "role": "status",
            "message": "Tu sistema quedó configurado con el Coach.",
        }
    resto = (just or {}).get("resto") if isinstance(just, dict) else None
    if resto:
        return {
            "kind": "warn",
            "role": "status",
            "message": "También te pueden servir (Premium)",
            "detalle": ", ".join(str(k) for k in resto),
            "href": "/app/billing",
            "link": "Ver planes",
        }
    return None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: Annotated[dict, Depends(require_onboarded)]):
    # Compat: si Stripe (o un bookmark) aterriza en /app?checkout=…
    user, redirect = consume_checkout_query(request, user, clean_path="/app/billing")
    if redirect is not None:
        return redirect

    uid = int(user["id"])
    plan = plan_vigente(user)
    just = request.session.pop("coach_just_finished", None)
    onboarded_flash = request.query_params.get("onboarded") == "1"
    checkout_flash = pop_checkout_flash(request)
    briefing = ultimo_briefing(uid)
    insight_destacado = None
    if briefing and briefing.get("insights"):
        insight_destacado = briefing["insights"][0]

    ritual = obtener_ritual(uid)
    hechos = habitos_hoy(uid)
    habitos = [{**h, "hecho": bool(hechos.get(h["clave"]))} for h in listar_habitos(uid)]
    google_ok = False
    google_error = ""
    try:
        from app.google_calendar import estado_google_calendar

        estado_cal = estado_google_calendar(uid)
        google_ok = bool(estado_cal.get("disponible"))
        google_error = estado_cal.get("error") or ""
    except Exception as e:
        google_ok = False
        google_error = str(e)[:180]
    if google_ok and puede_google(plan):
        try:
            pull_range(_hoy(), _hoy(), user_id=uid)
        except Exception as e:
            google_error = str(e)[:180]
        try:
            from app.google_calendar import estado_google_calendar

            estado_cal = estado_google_calendar(uid)
            google_ok = bool(estado_cal.get("disponible"))
            if estado_cal.get("error"):
                google_error = estado_cal["error"]
        except Exception:
            pass
    foco_falla = False
    try:
        foco_items = [i for i in items_foco(user_id=uid) if i.get("kind") != "habito"]
    except Exception:
        # Sin esto, un fallo de agenda se veía igual que un día sin nada agendado.
        log.exception("items_foco falló para el usuario %s", uid)
        foco_items = []
        foco_falla = True
    puede_cal = puede_google(plan)
    hoy_flash = request.session.pop("hoy_flash", None)
    hoy_error = request.session.pop("hoy_error", None)

    return render(
        request,
        "dashboard.html",
        title="Hoy",
        user=user,
        insight_destacado=insight_destacado,
        ritual=ritual,
        ritual_a=ritual_etiquetas(uid)[0],
        ritual_b=ritual_etiquetas(uid)[1],
        habitos=habitos,
        foco_items=foco_items,
        foco_falla=foco_falla,
        google_ok=google_ok,
        puede_google=puede_cal,
        ritual_activo=modulo_activo("ritual", uid),
        aviso=_aviso_hoy(
            hoy_error=hoy_error,
            foco_falla=foco_falla,
            puede_cal=puede_cal,
            google_ok=google_ok,
            google_error=google_error,
            checkout_flash=checkout_flash,
            hoy_flash=hoy_flash,
            onboarded=onboarded_flash,
            just=just,
        ),
    )


@router.post("/completar")
def completar_desde_hoy(
    request: Request,
    user: Annotated[dict, Depends(require_onboarded)],
    kind: Annotated[str, Form()] = "",
    ref: Annotated[str, Form()] = "",
):
    ok, msg = completar_item(kind, ref, int(user["id"]))
    if ok:
        request.session["hoy_flash"] = "Listo."
    else:
        request.session["hoy_error"] = msg
    return RedirectResponse("/app", status_code=303)
