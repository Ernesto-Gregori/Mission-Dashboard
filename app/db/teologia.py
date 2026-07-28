"""CRUD Teología — devocionales y pedidos de oración."""
from __future__ import annotations

import json
from datetime import timedelta

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import datetime, hoy as _hoy, iso_ahora

VERSIONES_BIBLIA = ["NVI", "RVR1960", "NLT", "ESV", "Otra"]
CATEGORIAS_PEDIDO = [
    "Personal",
    "Familia",
    "Matrimonio",
    "Instituto",
    "Ministerio",
    "Otros",
]
ESTADOS_PEDIDO = ["Activo", "En_espera", "Respondido", "Archivado"]
DIAS_ORACION_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
URGENCIA_LABELS = {
    1: "Baja",
    2: "Normal",
    3: "Media",
    4: "Alta",
    5: "Urgente",
}


def guardar_devocional(
    fecha,
    pasaje_ref,
    pasaje_texto,
    observacion,
    interpretacion,
    aplicacion,
    conexion_inst,
    conexion_sit,
    oracion,
    duracion,
    version_bib: str = "NVI",
) -> bool:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    try:
        ejecutar(
            """
            INSERT INTO devocionales (
                user_id, fecha, pasaje_referencia, pasaje_texto, version_biblia,
                observacion, interpretacion, aplicacion,
                conexion_instituto, conexion_situacion,
                oracion_escrita, duracion_minutos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, fecha) DO UPDATE SET
                pasaje_referencia  = excluded.pasaje_referencia,
                pasaje_texto       = excluded.pasaje_texto,
                version_biblia     = excluded.version_biblia,
                observacion        = excluded.observacion,
                interpretacion     = excluded.interpretacion,
                aplicacion         = excluded.aplicacion,
                conexion_instituto = excluded.conexion_instituto,
                conexion_situacion = excluded.conexion_situacion,
                oracion_escrita    = excluded.oracion_escrita,
                duracion_minutos   = excluded.duracion_minutos
            """,
            [
                uid(),
                fecha_iso,
                str(pasaje_ref or ""),
                str(pasaje_texto or ""),
                str(version_bib or "NVI"),
                str(observacion or ""),
                str(interpretacion or ""),
                str(aplicacion or ""),
                str(conexion_inst or ""),
                str(conexion_sit or ""),
                str(oracion or ""),
                int(duracion or 30),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def obtener_devocional(fecha) -> dict | None:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    rows = ejecutar(
        "SELECT * FROM devocionales WHERE fecha = ? AND user_id = ?",
        [fecha_iso, uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def obtener_devocionales_recientes(limite: int = 7) -> list:
    return (
        ejecutar_cached(
            """
            SELECT * FROM devocionales
            WHERE user_id = ? ORDER BY fecha DESC LIMIT ?
            """,
            (uid(), limite),
        )
        or []
    )


def agregar_pedido(
    titulo: str,
    descripcion: str,
    categoria: str,
    urgencia: int,
    dias_oracion: list,
) -> int | None:
    try:
        rid = ejecutar(
            """
            INSERT INTO pedidos_oracion
                (user_id, titulo, descripcion, categoria, urgencia, dias_oracion)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                uid(),
                titulo,
                descripcion,
                categoria,
                int(urgencia),
                json.dumps(dias_oracion or []),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return rid
    except Exception:
        return None


def obtener_pedidos(estado: str | None = None) -> list:
    if estado:
        return (
            ejecutar(
                """
                SELECT * FROM pedidos_oracion
                WHERE estado = ? AND user_id = ?
                ORDER BY urgencia DESC, creado_en DESC
                """,
                [estado, uid()],
                fetchall=True,
            )
            or []
        )
    return (
        ejecutar(
            """
            SELECT * FROM pedidos_oracion
            WHERE user_id = ?
            ORDER BY
                CASE estado
                    WHEN 'Activo'     THEN 1
                    WHEN 'En_espera'  THEN 2
                    WHEN 'Respondido' THEN 3
                    WHEN 'Archivado'  THEN 4
                END,
                urgencia DESC, creado_en DESC
            """,
            [uid()],
            fetchall=True,
        )
        or []
    )


def actualizar_estado_pedido(
    pedido_id: int,
    nuevo_estado: str,
    nota_respuesta: str = "",
    fecha_respuesta=None,
) -> bool:
    if nuevo_estado not in ESTADOS_PEDIDO:
        return False
    try:
        ejecutar(
            """
            UPDATE pedidos_oracion
            SET estado          = ?,
                nota_respuesta  = ?,
                fecha_respuesta = ?,
                actualizado_en  = ?
            WHERE id = ? AND user_id = ?
            """,
            [
                nuevo_estado,
                nota_respuesta,
                fecha_respuesta
                or (
                    _hoy().isoformat() if nuevo_estado == "Respondido" else None
                ),
                iso_ahora(),
                pedido_id,
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


def eliminar_pedido(pedido_id: int) -> bool:
    try:
        ejecutar(
            "DELETE FROM pedidos_oracion WHERE id = ? AND user_id = ?",
            [pedido_id, uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def editar_pedido(
    pedido_id: int,
    titulo: str,
    descripcion: str,
    categoria: str,
    urgencia: int,
    dias_oracion: list,
) -> bool:
    try:
        ejecutar(
            """
            UPDATE pedidos_oracion
            SET titulo         = ?,
                descripcion    = ?,
                categoria      = ?,
                urgencia       = ?,
                dias_oracion   = ?,
                actualizado_en = ?
            WHERE id = ? AND user_id = ?
            """,
            [
                titulo,
                descripcion,
                categoria,
                int(urgencia),
                json.dumps(dias_oracion or []),
                iso_ahora(),
                pedido_id,
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


def parse_dias_oracion(pedido: dict) -> list[int]:
    try:
        dias = json.loads(pedido.get("dias_oracion") or "[]")
        return [int(d) for d in dias]
    except Exception:
        return []


def pedidos_para_hoy(pedidos: list | None = None) -> list:
    """Pedidos Activos cuyo dias_oracion incluye hoy (1=Lun … 7=Dom)."""
    hoy_num = _hoy().weekday() + 1
    out = []
    for p in pedidos if pedidos is not None else obtener_pedidos("Activo"):
        if p.get("estado") and p["estado"] != "Activo":
            continue
        dias = parse_dias_oracion(p)
        if not dias or hoy_num in dias:
            out.append(p)
    return out
