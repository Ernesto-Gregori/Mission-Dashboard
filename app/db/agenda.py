"""CRUD Agenda: bitácora semanal, eventos de calendario, rachas y lecturas cruzadas."""
from __future__ import annotations

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


def obtener_lunes_semana(fecha=None):
    f = fecha or _hoy()
    return f - timedelta(days=f.weekday())


def inicio_semana(fecha=None, week_start: str = "lun"):
    """Primer día de la semana visible (lunes o domingo)."""
    f = fecha or _hoy()
    if str(week_start).lower().startswith("dom"):
        return f - timedelta(days=(f.weekday() + 1) % 7)
    return obtener_lunes_semana(f)


def etiquetas_semana(week_start: str = "lun") -> list[str]:
    if str(week_start).lower().startswith("dom"):
        return ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    return list(DIAS_SEMANA)


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
            SELECT id, fecha, hora AS hora_inicio, NULL AS hora_fin, titulo,
                   tipo_cita AS tipo, estado_planificacion,
                   COALESCE(ambito,'Matrimonio') AS ambito,
                   '#a371f7' AS color, NULL AS google_id, 'matrimonio' AS fuente
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
            SELECT id, fecha, hora_inicio, hora_fin, titulo, tipo,
                   '' AS estado_planificacion, tipo AS ambito,
                   color, google_id, COALESCE(fuente, 'local') AS fuente,
                   actualizado_en, google_updated
            FROM eventos_calendario
            WHERE fecha >= ? AND fecha <= ? AND user_id = ?
            ORDER BY fecha, hora_inicio
            """,
            [lunes.isoformat(), domingo.isoformat(), uid()],
            fetchall=True,
        )
        or []
    )

    from app.db.deep_work import bloques_en_rango

    bloques = [
        {
            "id": None,
            "bloque_id": b["id"],
            "fecha": b["fecha"],
            "hora_inicio": b["hora_inicio"],
            "hora_fin": b["hora_fin"],
            "titulo": b["nombre"],
            "tipo": b["tipo"],
            "estado_planificacion": b["estado"],
            "ambito": b["tipo"],
            "color": b["color"],
            "google_id": None,
            "fuente": "deep_work",
        }
        for b in bloques_en_rango(lunes, domingo)
    ]
    # Bloques que antes se subían a Google: no duplicarlos al leer Calendar.
    nombres_bloques = {b["titulo"] for b in bloques}

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

    todos = list(citas) + list(locales) + bloques + list(google_eventos)
    todos.sort(key=lambda e: (e.get("fecha", ""), e.get("hora_inicio") or "23:59"))
    return todos


def obtener_deepwork_semana(lunes: date, domingo: date) -> list:
    from app.db.deep_work import bloques_en_rango

    return [
        {
            "fecha": b["fecha"],
            "bloque_nombre": b["nombre"],
            "color": b["color"],
            "tipo": b["tipo"],
            "hora_inicio": b["hora_inicio"],
            "duracion_real": b["duracion_real"],
            "estado": b["estado"],
            "completado": 1 if b["estado"] == "Completado" else 0,
            "notas": b["notas"],
        }
        for b in bloques_en_rango(lunes, domingo)
    ]


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


def guardar_evento(datos: dict, *, sync_google: bool = True) -> int:
    from app.calendar_sync import ensure_calendar_sync_schema

    ensure_calendar_sync_schema()
    google_id = datos.get("google_id")
    google_updated = datos.get("google_updated") or ""
    if sync_google and not google_id:
        try:
            from app.google_calendar import calendar_disponible, crear_evento_google

            if calendar_disponible():
                google_id = crear_evento_google(datos)
                google_updated = iso_ahora()
        except Exception:
            google_id = google_id or None
    fuente = str(datos.get("fuente") or "local")
    if fuente not in ("local", "google_calendar"):
        fuente = "local"
    if google_id:
        fuente = fuente if fuente == "google_calendar" else "local"
    stamp = datos.get("actualizado_en") or iso_ahora()
    return ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, descripcion,
             tipo, color, google_id, fuente, actualizado_en, google_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            fuente,
            stamp,
            google_updated,
        ],
    )


def actualizar_evento(evento_id: int, datos: dict, *, sync_google: bool = True) -> bool:
    """Edita un evento local y, si tiene google_id, el de Calendar.

    Conflict rule: newest timestamp wins — this write stamps actualizado_en
    now, so a later pull will push this version if Google is older.
    """
    from app.calendar_sync import ensure_calendar_sync_schema

    ensure_calendar_sync_schema()
    rows = ejecutar(
        """
        SELECT * FROM eventos_calendario
        WHERE id = ? AND user_id = ?
        """,
        [int(evento_id), uid()],
        fetchall=True,
    )
    if not rows:
        return False
    prev = rows[0]
    tipo = datos.get("tipo") or prev.get("tipo") or "Personal"
    if tipo not in COLORES_TIPO:
        tipo = "Personal"
    stamp = iso_ahora()
    google_id = prev.get("google_id")
    payload = {
        "fecha": str(datos.get("fecha") or prev.get("fecha")),
        "hora_inicio": datos.get("hora_inicio", prev.get("hora_inicio")),
        "hora_fin": datos.get("hora_fin", prev.get("hora_fin")),
        "titulo": str(datos.get("titulo") or prev.get("titulo") or ""),
        "descripcion": str(datos.get("descripcion", prev.get("descripcion") or "")),
        "tipo": tipo,
        "color": datos.get("color") or COLORES_TIPO.get(tipo, prev.get("color") or "#58a6ff"),
    }
    google_updated = prev.get("google_updated") or ""
    if sync_google and google_id:
        try:
            from app.google_calendar import actualizar_evento_google, calendar_disponible

            if calendar_disponible():
                if actualizar_evento_google(str(google_id), payload):
                    google_updated = stamp
        except Exception:
            pass
    elif sync_google and not google_id:
        try:
            from app.google_calendar import calendar_disponible, crear_evento_google

            if calendar_disponible():
                google_id = crear_evento_google(payload)
                if google_id:
                    google_updated = stamp
        except Exception:
            pass
    ejecutar(
        """
        UPDATE eventos_calendario
           SET fecha=?, hora_inicio=?, hora_fin=?, titulo=?, descripcion=?,
               tipo=?, color=?, google_id=?, actualizado_en=?, google_updated=?
         WHERE id=? AND user_id=?
        """,
        [
            payload["fecha"],
            payload.get("hora_inicio"),
            payload.get("hora_fin"),
            payload["titulo"],
            payload.get("descripcion"),
            payload["tipo"],
            payload["color"],
            google_id,
            stamp,
            google_updated,
            int(evento_id),
            uid(),
        ],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True


def eventos_con_hora(desde: str, hasta: str) -> list[dict]:
    """Eventos del usuario actual con hora de inicio entre dos fechas ISO (inclusive), cualquier fuente."""
    return (
        ejecutar(
            """
            SELECT id, fecha, hora_inicio, titulo FROM eventos_calendario
            WHERE user_id = ? AND fecha BETWEEN ? AND ?
              AND hora_inicio IS NOT NULL AND hora_inicio != ''
            ORDER BY fecha, hora_inicio
            """,
            [uid(), str(desde), str(hasta)],
            fetchall=True,
        )
        or []
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
