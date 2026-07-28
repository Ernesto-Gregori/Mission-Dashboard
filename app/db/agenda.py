"""CRUD Agenda: bitácora semanal, eventos de calendario, rachas y lecturas cruzadas."""
from __future__ import annotations

import json
from datetime import timedelta

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import date, datetime, hoy as _hoy, iso_ahora


DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
SEMAFOROS = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}

COLORES_TIPO = {
    "Lectura": "#e3b341",
    "Personal": "#58a6ff",
    "Ministerio": "#a371f7",
    "Salud": "#3fb950",
    "Estudio": "#f0883e",
    "Otro": "#8b949e",
}

TIPOS_EVENTO = list(COLORES_TIPO.keys())

SYSTEM_AGENDA = """Eres un asistente de planificación semanal cristiano.
Ayudas a revisar victorias, planificar la semana y reflexionar.
Eres práctico, motivador y consideras el balance vida-fe-familia.
Máximo 120 palabras."""


def obtener_lunes_semana(fecha=None):
    f = fecha or _hoy()
    return f - timedelta(days=f.weekday())


def guardar_bitacora(datos: dict) -> bool:
    try:
        ejecutar(
            """
            INSERT INTO bitacora_semanal (
                user_id, semana_inicio, victoria_1, victoria_2, victoria_3,
                ingreso_actual, sobre_supervivencia, aporte_transicion,
                presupuesto_cita, semaforo_superv, semaforo_ahorros,
                semaforo_extras, gasto_pausado,
                actividad_cita, costo_cita,
                libro_actual, pagina_actual, frase_favorita,
                pendientes_soltar, reflexion_semana, estado,
                actualizado_en
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'abierta',?
            )
            ON CONFLICT(user_id, semana_inicio) DO UPDATE SET
                victoria_1          = excluded.victoria_1,
                victoria_2          = excluded.victoria_2,
                victoria_3          = excluded.victoria_3,
                ingreso_actual      = excluded.ingreso_actual,
                sobre_supervivencia = excluded.sobre_supervivencia,
                aporte_transicion   = excluded.aporte_transicion,
                presupuesto_cita    = excluded.presupuesto_cita,
                semaforo_superv     = excluded.semaforo_superv,
                semaforo_ahorros    = excluded.semaforo_ahorros,
                semaforo_extras     = excluded.semaforo_extras,
                gasto_pausado       = excluded.gasto_pausado,
                actividad_cita      = excluded.actividad_cita,
                costo_cita          = excluded.costo_cita,
                libro_actual        = excluded.libro_actual,
                pagina_actual       = excluded.pagina_actual,
                frase_favorita      = excluded.frase_favorita,
                pendientes_soltar   = excluded.pendientes_soltar,
                reflexion_semana    = excluded.reflexion_semana,
                actualizado_en      = excluded.actualizado_en
            """,
            [
                uid(),
                datos["semana_inicio"],
                datos.get("victoria_1", ""),
                datos.get("victoria_2", ""),
                datos.get("victoria_3", ""),
                datos.get("ingreso_actual", 0),
                datos.get("sobre_supervivencia", 0),
                datos.get("aporte_transicion", 0),
                datos.get("presupuesto_cita", 0),
                datos.get("semaforo_superv", "verde"),
                datos.get("semaforo_ahorros", "verde"),
                datos.get("semaforo_extras", "verde"),
                datos.get("gasto_pausado", ""),
                datos.get("actividad_cita", ""),
                datos.get("costo_cita", 0),
                datos.get("libro_actual", ""),
                datos.get("pagina_actual", 0),
                datos.get("frase_favorita", ""),
                datos.get("pendientes_soltar", ""),
                datos.get("reflexion_semana", ""),
                iso_ahora(),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def obtener_bitacora(semana_inicio: str) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM bitacora_semanal WHERE semana_inicio = ? AND user_id = ?",
        [semana_inicio, uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def obtener_bitacoras_recientes(limite: int = 10) -> list:
    return (
        ejecutar_cached(
            """
            SELECT * FROM bitacora_semanal
            WHERE user_id = ?
            ORDER BY semana_inicio DESC LIMIT ?
            """,
            (uid(), limite),
        )
        or []
    )


def obtener_eventos_semana(lunes: date, domingo: date) -> list:
    citas = (
        ejecutar(
            """
            SELECT fecha, hora AS hora_inicio, titulo,
                   tipo_cita AS tipo, estado_planificacion,
                   COALESCE(ambito,'Matrimonio') AS ambito,
                   '#a371f7' AS color, NULL AS google_id
            FROM matrimonio_citas
            WHERE fecha >= ? AND fecha <= ? AND user_id = ?
            ORDER BY fecha, hora
            """,
            [lunes.isoformat(), domingo.isoformat(), uid()],
            fetchall=True,
        )
        or []
    )

    locales = (
        ejecutar(
            """
            SELECT fecha, hora_inicio, titulo, tipo,
                   '' AS estado_planificacion, tipo AS ambito,
                   color, google_id
            FROM eventos_calendario
            WHERE fecha >= ? AND fecha <= ? AND user_id = ?
            ORDER BY fecha, hora_inicio
            """,
            [lunes.isoformat(), domingo.isoformat(), uid()],
            fetchall=True,
        )
        or []
    )

    bloques_rows = (
        ejecutar_cached(
            "SELECT nombre FROM bloques_fijos WHERE activo = 1 AND user_id = ?",
            (uid(),),
        )
        or []
    )
    nombres_bloques = {r["nombre"] for r in bloques_rows}

    google_ids_sincronizados = {e["google_id"] for e in locales if e.get("google_id")}

    google_eventos = []
    try:
        from app.google_calendar import calendar_disponible, obtener_eventos_google

        if calendar_disponible():
            eventos_gc = obtener_eventos_google(lunes, domingo) or []
            google_eventos = [
                e
                for e in eventos_gc
                if e.get("google_id") not in google_ids_sincronizados
                and e.get("titulo") not in nombres_bloques
            ]
    except Exception:
        google_eventos = []

    todos = list(citas) + list(locales) + list(google_eventos)
    todos.sort(key=lambda e: (e.get("fecha", ""), e.get("hora_inicio") or "23:59"))
    return todos


def obtener_deepwork_semana(lunes: date, domingo: date) -> list:
    resultado = []
    for i in range(7):
        dia = lunes + timedelta(days=i)
        dia_iso = dia.isoformat()
        dia_numero = dia.weekday() + 1

        bloques = (
            ejecutar(
                """
                SELECT b.id, b.nombre, b.color, b.tipo,
                       b.hora_inicio, b.hora_fin, b.dias_semana,
                       s.estado, s.duracion_real, s.notas
                FROM bloques_fijos b
                LEFT JOIN sesiones_completadas s
                    ON s.bloque_fijo_id = b.id AND s.fecha = ? AND s.user_id = ?
                WHERE b.activo = 1 AND b.user_id = ?
                """,
                [dia_iso, uid(), uid()],
                fetchall=True,
            )
            or []
        )

        for b in bloques:
            try:
                dias = json.loads(b["dias_semana"] or "[]")
            except Exception:
                dias = []
            if dia_numero not in dias:
                continue
            estado = b["estado"] or "Pendiente"
            completado = 1 if estado == "Completado" else 0
            resultado.append(
                {
                    "fecha": dia_iso,
                    "bloque_nombre": b["nombre"],
                    "color": b["color"],
                    "tipo": b["tipo"],
                    "hora_inicio": b["hora_inicio"],
                    "duracion_real": b["duracion_real"],
                    "estado": estado,
                    "completado": completado,
                    "notas": b["notas"],
                }
            )

    resultado.sort(key=lambda x: (x["fecha"], x.get("hora_inicio") or ""))
    return resultado


def obtener_devocionales_semana(lunes: date, domingo: date) -> list:
    return (
        ejecutar(
            """
            SELECT fecha, pasaje_referencia, duracion_minutos
            FROM devocionales
            WHERE fecha BETWEEN ? AND ? AND user_id = ?
            ORDER BY fecha
            """,
            [lunes.isoformat(), domingo.isoformat(), uid()],
            fetchall=True,
        )
        or []
    )


def obtener_salud_semana(lunes: date, domingo: date) -> list:
    return (
        ejecutar(
            """
            SELECT fecha, horas_sueno,
                   energia_manana AS nivel_energia,
                   hizo_ejercicio, productividad_percibida
            FROM registros_salud
            WHERE fecha BETWEEN ? AND ? AND user_id = ?
            ORDER BY fecha
            """,
            [lunes.isoformat(), domingo.isoformat(), uid()],
            fetchall=True,
        )
        or []
    )


def obtener_libros_leyendo() -> list:
    return (
        ejecutar_cached(
            """
            SELECT titulo, autor, pagina_actual, total_paginas
            FROM libros WHERE estado = 'leyendo' AND user_id = ?
            ORDER BY actualizado_en DESC
            """,
            (uid(),),
        )
        or []
    )


def calcular_racha_devocional() -> int:
    fechas_rows = (
        ejecutar_cached(
            "SELECT fecha FROM devocionales WHERE user_id = ? ORDER BY fecha DESC LIMIT 30",
            (uid(),),
        )
        or []
    )
    fechas = [datetime.strptime(r["fecha"], "%Y-%m-%d").date() for r in fechas_rows]
    racha = 0
    hoy = _hoy()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha


def calcular_racha_ejercicio() -> int:
    fechas_rows = (
        ejecutar_cached(
            """
            SELECT fecha FROM registros_salud
            WHERE hizo_ejercicio = 1 AND user_id = ?
            ORDER BY fecha DESC LIMIT 30
            """,
            (uid(),),
        )
        or []
    )
    fechas = [datetime.strptime(r["fecha"], "%Y-%m-%d").date() for r in fechas_rows]
    if not fechas:
        return 0
    hoy_lun = _hoy() - timedelta(days=_hoy().weekday())
    semanas = {f - timedelta(days=f.weekday()) for f in fechas}
    racha = 0
    for i in range(52):
        if (hoy_lun - timedelta(weeks=i)) in semanas:
            racha += 1
        else:
            break
    return racha


def calcular_racha_deepwork() -> int:
    fechas_rows = (
        ejecutar_cached(
            """
            SELECT DISTINCT fecha FROM sesiones_completadas
            WHERE estado = 'Completado' AND user_id = ?
            ORDER BY fecha DESC LIMIT 30
            """,
            (uid(),),
        )
        or []
    )
    fechas = [datetime.strptime(r["fecha"], "%Y-%m-%d").date() for r in fechas_rows]
    racha = 0
    hoy = _hoy()
    for i, f in enumerate(sorted(fechas, reverse=True)):
        if f == hoy - timedelta(days=i):
            racha += 1
        else:
            break
    return racha


def obtener_eventos_personalizados(fecha: str | None = None) -> list:
    if fecha:
        return (
            ejecutar(
                """
                SELECT * FROM eventos_calendario
                WHERE fecha = ? AND user_id = ? ORDER BY hora_inicio
                """,
                [fecha, uid()],
                fetchall=True,
            )
            or []
        )
    return (
        ejecutar(
            """
            SELECT * FROM eventos_calendario
            WHERE user_id = ?
            ORDER BY fecha DESC, hora_inicio LIMIT 50
            """,
            [uid()],
            fetchall=True,
        )
        or []
    )


def guardar_evento(datos: dict) -> int:
    google_id = None
    try:
        from app.google_calendar import calendar_disponible, crear_evento_google

        if calendar_disponible():
            google_id = crear_evento_google(datos)
    except Exception:
        google_id = None
    return ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, descripcion,
             tipo, color, google_id, fuente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            datos["fecha"],
            datos.get("hora_inicio"),
            datos.get("hora_fin"),
            datos["titulo"],
            datos.get("descripcion", ""),
            datos.get("tipo", "Personal"),
            datos.get("color", COLORES_TIPO.get(datos.get("tipo", "Personal"), "#58a6ff")),
            google_id,
            "local",
        ],
    )


def eliminar_evento(evento_id: int) -> bool:
    rows = ejecutar(
        "SELECT google_id FROM eventos_calendario WHERE id = ? AND user_id = ?",
        [evento_id, uid()],
        fetchall=True,
    )
    google_id = rows[0]["google_id"] if rows else None
    ejecutar(
        "DELETE FROM eventos_calendario WHERE id = ? AND user_id = ?",
        [evento_id, uid()],
    )
    if google_id:
        try:
            from app.google_calendar import calendar_disponible, eliminar_evento_google

            if calendar_disponible():
                eliminar_evento_google(google_id)
        except Exception:
            pass
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True
