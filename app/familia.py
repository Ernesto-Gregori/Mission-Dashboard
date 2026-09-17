"""Comparativa familiar — gastos, hábitos y tareas por miembro (admin)."""
from __future__ import annotations

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy

log = get_logger("familia")


def _es_admin(user: dict) -> bool:
    return str(user.get("rol") or "").lower() == "admin"


def snapshot_miembro(user_id: int, mes: int, anio: int) -> dict:
    """Lee datos de un usuario con as_user — no usa el uid de la sesión."""
    from app.database import obtener_usuario_activo
    from app.db.core import ejecutar
    from app.db.finanzas import obtener_gastos_sobre, obtener_ingreso
    from app.tenant import as_user

    perfil = obtener_usuario_activo(int(user_id))
    if not perfil:
        rows = ejecutar(
            "SELECT id, username, rol, activo FROM usuarios WHERE id = ?",
            [int(user_id)],
            fetchall=True,
        ) or []
        if not rows:
            return {}
        perfil = {
            "id": rows[0]["id"],
            "username": rows[0]["username"],
            "rol": rows[0]["rol"],
        }

    hoy = str(_hoy())
    with as_user(perfil):
        ingreso = float(obtener_ingreso(mes, anio) or 0)
        gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=80)
        total_gastos = sum(float(g.get("monto") or 0) for g in gastos)

        habitos_cfg = (
            ejecutar(
                """
                SELECT clave, label, emoji, COALESCE(activo, 1) AS activo
                FROM habitos_config
                WHERE user_id = ? AND COALESCE(activo, 1) = 1
                ORDER BY orden, label
                """,
                [int(user_id)],
                fetchall=True,
            )
            or []
        )
        hechos = (
            ejecutar(
                """
                SELECT habito_clave, completado
                FROM habitos_diarios_v2
                WHERE user_id = ? AND fecha = ?
                """,
                [int(user_id), hoy],
                fetchall=True,
            )
            or []
        )
        hechos_map = {r["habito_clave"]: int(r.get("completado") or 0) for r in hechos}
        habitos = []
        hechos_n = 0
        for h in habitos_cfg:
            done = bool(hechos_map.get(h["clave"]))
            if done:
                hechos_n += 1
            habitos.append({
                "label": h.get("label") or h["clave"],
                "emoji": h.get("emoji") or "⭐",
                "hecho": done,
            })

        eventos = (
            ejecutar(
                """
                SELECT fecha, hora_inicio, titulo
                FROM eventos_calendario
                WHERE user_id = ? AND fecha >= ?
                  AND COALESCE(fuente, 'local') = 'local'
                ORDER BY fecha, hora_inicio
                LIMIT 8
                """,
                [int(user_id), hoy],
                fetchall=True,
            )
            or []
        )
        pendientes_habito = [h for h in habitos if not h["hecho"]]

    return {
        "id": int(perfil["id"]),
        "username": perfil.get("username") or "",
        "rol": perfil.get("rol") or "usuario",
        "ingreso": ingreso,
        "total_gastos": total_gastos,
        "gastos": gastos[:12],
        "habitos": habitos,
        "habitos_hechos": hechos_n,
        "habitos_total": len(habitos),
        "tareas_pendientes": pendientes_habito,
        "eventos": eventos,
    }


def listar_comparativa(viewer: dict, mes: int, anio: int, miembro_id: int | None = None) -> dict:
    from app.database import listar_usuarios

    if not _es_admin(viewer):
        raise PermissionError("Solo administradores.")

    usuarios = [u for u in (listar_usuarios() or []) if int(u.get("activo") or 0) == 1]
    miembros = []
    for u in usuarios:
        snap = snapshot_miembro(int(u["id"]), mes, anio)
        if snap:
            miembros.append(snap)

    seleccionado = None
    if miembro_id is not None:
        seleccionado = next((m for m in miembros if m["id"] == int(miembro_id)), None)
        if seleccionado is None:
            raise LookupError("Miembro no encontrado.")

    return {
        "miembros": miembros,
        "seleccionado": seleccionado,
        "usuarios": usuarios,
    }
