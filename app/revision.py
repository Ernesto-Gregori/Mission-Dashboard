"""Revisión semanal — métricas leídas de sus fuentes, nunca reescritas a mano."""
from __future__ import annotations

from datetime import date, timedelta

from app.db.agenda import SEMAFOROS

# Columnas de bitacora_semanal que el usuario sigue escribiendo.
CAMPOS_BITACORA = (
    "victoria_1",
    "victoria_2",
    "victoria_3",
    "frase_favorita",
    "pendientes_soltar",
    "reflexion_semana",
)


def semaforo(pct_usado: float) -> str:
    if pct_usado >= 100:
        return "rojo"
    if pct_usado >= 80:
        return "amarillo"
    return "verde"


def resumen_semana(lunes: date, user_id: int) -> dict:
    from app.db.agenda import (
        obtener_deepwork_semana,
        obtener_devocionales_semana,
        obtener_libros_leyendo,
        obtener_salud_semana,
    )
    from app.db.core import ejecutar
    from app.presupuesto import resumen_mes

    domingo = lunes + timedelta(days=6)
    dw = obtener_deepwork_semana(lunes, domingo)
    salud = obtener_salud_semana(lunes, domingo)
    energias = [int(s["nivel_energia"]) for s in salud if s.get("nivel_energia")]

    fin = resumen_mes(lunes.month, lunes.year, user_id=user_id)
    sobres = []
    for s in fin["sobres"].values():
        color = None if fin["sin_ingreso"] else semaforo(s["pct_usado"])
        sobres.append({
            "nombre": s["nombre"],
            "emoji": s["emoji"],
            "gastado": s["gastado"],
            "presupuesto": s["presupuesto"],
            "semaforo": color,
            "icono": SEMAFOROS.get(color or "", "⚪"),
        })

    citas = (
        ejecutar(
            """
            SELECT fecha, titulo, estado_planificacion
            FROM matrimonio_citas
            WHERE user_id = ? AND fecha >= ? AND fecha <= ?
            ORDER BY fecha
            """,
            [int(user_id), lunes.isoformat(), domingo.isoformat()],
            fetchall=True,
        )
        or []
    )
    libros = obtener_libros_leyendo()

    return {
        "lunes": lunes,
        "domingo": domingo,
        "devocionales": len(obtener_devocionales_semana(lunes, domingo)),
        "dw_completados": len([s for s in dw if s.get("completado") == 1]),
        "dw_total": len(dw),
        "ejercicios": len([s for s in salud if s.get("hizo_ejercicio")]),
        "energia": round(sum(energias) / len(energias), 1) if energias else None,
        "mes_label": f"{lunes.month:02d}/{lunes.year}",
        "sin_ingreso": fin["sin_ingreso"],
        "sobres": sobres,
        "libro": libros[0] if libros else None,
        "citas": citas,
    }
