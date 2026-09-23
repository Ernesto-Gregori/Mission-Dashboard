"""CRUD Deep Work — bloques fijos y sesiones diarias."""
from __future__ import annotations

import json
from datetime import date, timedelta

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid

DIAS_NOMBRES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

COLORES = {
    "Azul": "#58a6ff",
    "Verde": "#3fb950",
    "Morado": "#a371f7",
    "Amarillo": "#e3b341",
    "Rojo": "#f85149",
    "Rosa": "#f778ba",
}

ESTADOS_SESION = ["Pendiente", "Completado", "Parcial", "No_realizado", "Postergado"]


def obtener_bloques_fijos(user_id: int | None = None) -> list:
    uid_ = int(user_id if user_id is not None else uid())
    return (
        ejecutar(
            "SELECT * FROM bloques_fijos WHERE activo = 1 AND user_id = ? ORDER BY hora_inicio",
            [uid_],
            fetchall=True,
        )
        or []
    )


def obtener_todos_bloques() -> list:
    return (
        ejecutar_cached(
            "SELECT * FROM bloques_fijos WHERE user_id = ? ORDER BY activo DESC, hora_inicio",
            (uid(),),
        )
        or []
    )


def obtener_estado_sesion(fecha: str, bloque_id: int) -> tuple:
    rows = ejecutar(
        """
        SELECT estado, notas FROM sesiones_completadas
        WHERE fecha = ? AND bloque_fijo_id = ? AND user_id = ?
        """,
        [fecha, bloque_id, uid()],
        fetchall=True,
    )
    if rows:
        return rows[0]["estado"], rows[0]["notas"]
    return None, None


def registrar_sesion(fecha: str, bloque_id: int, estado: str, notas: str = "") -> bool:
    if estado not in ESTADOS_SESION:
        estado = "Pendiente"
    try:
        ejecutar(
            """
            INSERT INTO sesiones_completadas
                (user_id, fecha, bloque_fijo_id, estado, notas)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, fecha, bloque_fijo_id) DO UPDATE SET
                estado = excluded.estado,
                notas  = excluded.notas
            """,
            [uid(), fecha, bloque_id, estado, notas],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def obtener_sesiones_semana(fecha_inicio: str, fecha_fin: str) -> list:
    return (
        ejecutar_cached(
            """
            SELECT sc.*, bf.nombre, bf.tipo, bf.hora_inicio, bf.hora_fin
            FROM sesiones_completadas sc
            JOIN bloques_fijos bf ON sc.bloque_fijo_id = bf.id AND bf.user_id = sc.user_id
            WHERE sc.fecha BETWEEN ? AND ? AND sc.user_id = ?
            ORDER BY sc.fecha, bf.hora_inicio
            """,
            (fecha_inicio, fecha_fin, uid()),
        )
        or []
    )


def crear_bloque(
    nombre: str,
    hora_inicio: str,
    hora_fin: str,
    dias: list,
    tipo: str,
    color: str,
) -> int | None:
    try:
        bloque_id = ejecutar(
            """
            INSERT INTO bloques_fijos
                (user_id, nombre, hora_inicio, hora_fin, dias_semana, tipo, color, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            [uid(), nombre, hora_inicio, hora_fin, json.dumps(dias), tipo, color],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return bloque_id
    except Exception:
        return None


def actualizar_bloque(
    bloque_id: int,
    nombre: str,
    hora_inicio: str,
    hora_fin: str,
    dias: list,
    tipo: str,
    color: str,
    activo: bool = True,
) -> bool:
    try:
        ejecutar(
            """
            UPDATE bloques_fijos
            SET nombre=?, hora_inicio=?, hora_fin=?,
                dias_semana=?, tipo=?, color=?, activo=?
            WHERE id=? AND user_id=?
            """,
            [
                nombre,
                hora_inicio,
                hora_fin,
                json.dumps(dias),
                tipo,
                color,
                int(activo),
                bloque_id,
                uid(),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def desactivar_bloque(bloque_id: int) -> bool:
    try:
        ejecutar(
            "UPDATE bloques_fijos SET activo = 0 WHERE id = ? AND user_id = ?",
            [bloque_id, uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def reactivar_bloque(bloque_id: int) -> bool:
    try:
        ejecutar(
            "UPDATE bloques_fijos SET activo = 1 WHERE id = ? AND user_id = ?",
            [bloque_id, uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def bloques_en_rango(inicio: date, fin: date, user_id: int | None = None) -> list[dict]:
    """Ocurrencias de los bloques activos entre dos fechas, con el estado de su sesión."""
    uid_ = int(user_id if user_id is not None else uid())
    bloques = obtener_bloques_fijos(uid_)
    if not bloques:
        return []
    sesiones = (
        ejecutar(
            """
            SELECT fecha, bloque_fijo_id, estado, notas, duracion_real
            FROM sesiones_completadas
            WHERE user_id = ? AND fecha BETWEEN ? AND ?
            """,
            [uid_, inicio.isoformat(), fin.isoformat()],
            fetchall=True,
        )
        or []
    )
    por_clave = {(str(s["fecha"]), int(s["bloque_fijo_id"])): s for s in sesiones}
    out = []
    dia = inicio
    while dia <= fin:
        for b in bloques:
            dias = parse_dias_bloque(b)
            if dia.weekday() + 1 not in dias:
                continue
            ses = por_clave.get((dia.isoformat(), int(b["id"]))) or {}
            out.append({
                **dict(b),
                "fecha": dia.isoformat(),
                "dias_list": dias,
                "estado": ses.get("estado") or "Pendiente",
                "notas": ses.get("notas") or "",
                "duracion_real": ses.get("duracion_real"),
            })
        dia += timedelta(days=1)
    return out


def bloques_para_fecha(fecha_iso: str, user_id: int | None = None) -> list:
    dia = date.fromisoformat(fecha_iso)
    return bloques_en_rango(dia, dia, user_id)


def construir_resumen_semana(sesiones: list) -> str:
    if not sesiones:
        return "Sin sesiones registradas esta semana."

    total = len(sesiones)
    completados = len([s for s in sesiones if s["estado"] == "Completado"])
    parciales = len([s for s in sesiones if s["estado"] == "Parcial"])
    no_realizados = len([s for s in sesiones if s["estado"] == "No_realizado"])

    por_tipo: dict = {}
    for s in sesiones:
        tipo = s.get("tipo") or "Otro"
        if tipo not in por_tipo:
            por_tipo[tipo] = {"total": 0, "completados": 0}
        por_tipo[tipo]["total"] += 1
        if s["estado"] == "Completado":
            por_tipo[tipo]["completados"] += 1

    resumen = (
        f"Semana: {total} bloques. "
        f"Completados: {completados}, Parciales: {parciales}, "
        f"No realizados: {no_realizados}.\n"
    )
    resumen += "Por tipo: " + ", ".join(
        f"{tipo}: {v['completados']}/{v['total']}" for tipo, v in por_tipo.items()
    )
    notas = [s["notas"] for s in sesiones if s.get("notas") and len(s["notas"]) > 10]
    if notas:
        resumen += f"\nNotas del usuario: {' | '.join(notas[:3])}"
    return resumen


def parse_dias_bloque(bloque: dict) -> list[int]:
    try:
        dias = json.loads(bloque.get("dias_semana") or "[]")
        return [int(d) for d in dias]
    except Exception:
        return []
