"""Alma, coach y resumen de la semana. Alma solo se llama con /alma, nunca como respaldo."""
from __future__ import annotations

from datetime import timedelta

from app.telegram_actions.base import Accion, Contexto, Respuesta


def _alma(ctx: Contexto, datos: dict) -> Respuesta:
    from app.asistente import obtener_prefs, responder

    flags = obtener_prefs(ctx.user_id)
    try:
        texto = responder(str(datos.get("texto") or ""), flags, user_id=ctx.user_id)
    except ValueError:
        return Respuesta("Escribí el mensaje. Ejemplo: /alma cómo viene mi semana")
    if not any(flags.values()):
        texto += "\n\nNo hay categorías autorizadas. Se activan en la app, en Alma. El bot no puede prenderlas."
    return Respuesta(texto[:1500])


ALMA = Accion(
    clave="alma",
    comandos=("/alma",),
    ejecutar=_alma,
    uso="Escribí el mensaje. Ejemplo: /alma cómo viene mi semana",
    parse=lambda args: {"texto": args.strip()} if args.strip() else None,
)


def _coach(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.billing import plan_vigente
    from app.coach_insights import generar_briefing, resumen_cuota_briefing

    plan = plan_vigente(ctx.user)
    ok, mensaje, briefing = generar_briefing(ctx.user_id, plan=plan)
    cuota = resumen_cuota_briefing(ctx.user_id, plan)
    tope = "sin tope" if cuota["limite"] is None else f"{cuota['usados']}/{cuota['limite']} esta semana"
    if not ok or not briefing:
        return Respuesta(f"{mensaje}\nCoach: {tope}.")
    lineas = [f"Coach ({tope})"]
    for item in (briefing.get("insights") or [])[:5]:
        if isinstance(item, dict):
            lineas.append(str(item.get("titulo") or item.get("texto") or item.get("title") or "").strip())
        else:
            lineas.append(str(item).strip())
    lineas = [ln for ln in lineas if ln]
    return Respuesta("\n".join(lineas)[:1500])


COACH = Accion(
    clave="coach",
    comandos=("/coach",),
    ejecutar=_coach,
    parse=lambda _args: {},
)


def _semana(ctx: Contexto, _datos: dict) -> Respuesta:
    from app.revision import resumen_semana
    from app.timezone_config import hoy

    dia = hoy()
    lunes = dia - timedelta(days=dia.weekday())
    res = resumen_semana(lunes, ctx.user_id)
    lineas = [f"Semana del {lunes.isoformat()}"]
    lineas.append(f"Enfoque: {res['dw_completados']}/{res['dw_total']} bloques")
    lineas.append(f"Ejercicio: {res['ejercicios']} días")
    if res.get("energia") is not None:
        lineas.append(f"Energía: {res['energia']}")
    if res.get("libro"):
        lineas.append(f"Leyendo: {res['libro'].get('titulo')}")
    justos = [s for s in res.get("sobres") or [] if s.get("semaforo") == "rojo"]
    if justos:
        lineas.append("Sobres en rojo: " + ", ".join(s["nombre"] for s in justos[:3]))
    return Respuesta("\n".join(lineas))


SEMANA = Accion(
    clave="semana",
    comandos=("/semana",),
    ejecutar=_semana,
    parse=lambda _args: {},
)
