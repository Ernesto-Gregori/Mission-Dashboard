"""CRUD Matrimonio — citas, notas y hábitos de conexión."""
from __future__ import annotations

from datetime import timedelta

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import datetime, hoy as _hoy, iso_ahora

AMBITOS = ["Matrimonio", "Familia"]

TIPOS_CITA = {
    "Matrimonio": [
        "Cena_Romantica",
        "Salida_Casual",
        "Estadia_Casa",
        "Viaje_Corto",
        "Aniversario",
        "Cumpleanos_Esposa",
        "Sorpresa",
        "Otra",
    ],
    "Familia": [
        "Salida_Familiar",
        "Vacaciones",
        "Actividad_Recreativa",
        "Visita_Familiares",
        "Celebracion",
        "Deporte_Juntos",
        "Cine_Teatro",
        "Parque",
        "Otra",
    ],
}

EMOJIS_TIPO = {
    "Cena_Romantica": "🍷",
    "Salida_Casual": "☕",
    "Estadia_Casa": "🏠",
    "Viaje_Corto": "🚗",
    "Aniversario": "💍",
    "Cumpleanos_Esposa": "🎂",
    "Sorpresa": "🎉",
    "Salida_Familiar": "👨‍👩‍👧",
    "Vacaciones": "🏖️",
    "Actividad_Recreativa": "🎮",
    "Visita_Familiares": "🏡",
    "Celebracion": "🎊",
    "Deporte_Juntos": "⚽",
    "Cine_Teatro": "🎬",
    "Parque": "🌳",
    "Otra": "💑",
}

ESTADOS_CITA = ["Idea", "Planeando", "Confirmada", "Completada", "Cancelada"]

COLORES_ESTADO = {
    "Idea": "#8b949e",
    "Planeando": "#58a6ff",
    "Confirmada": "#3fb950",
    "Completada": "#a371f7",
    "Cancelada": "#f85149",
}

CATEGORIAS_NOTA = [
    "Preferencias_Esposa",
    "Ideas_Regalo",
    "Frases_Recordar",
    "Momentos_Especiales",
    "Metas_Pareja",
    "Conversaciones_Pendientes",
    "Familia",
    "Hijos",
    "Otro",
]

EMOJIS_NOTA = {
    "Preferencias_Esposa": "💝",
    "Ideas_Regalo": "🎁",
    "Frases_Recordar": "💬",
    "Momentos_Especiales": "✨",
    "Metas_Pareja": "🎯",
    "Conversaciones_Pendientes": "🗣️",
    "Familia": "👨‍👩‍👧",
    "Hijos": "👶",
    "Otro": "📝",
}

TIPOS_CONEXION = [
    "Conversacion",
    "Cena",
    "Paseo",
    "Oracion",
    "Actividad",
    "Otro",
]

INICIADO_POR = ["Yo", "Ella", "Ambos"]


def obtener_citas(fecha_desde=None, estado=None, ambito=None) -> list:
    conditions = ["user_id = ?"]
    params: list = [uid()]
    if fecha_desde:
        conditions.append("fecha >= ?")
        params.append(str(fecha_desde))
    if estado:
        conditions.append("estado_planificacion = ?")
        params.append(estado)
    if ambito:
        conditions.append("ambito = ?")
        params.append(ambito)
    where = " AND ".join(conditions)
    return (
        ejecutar(
            f"SELECT * FROM matrimonio_citas WHERE {where} ORDER BY fecha, hora",
            params,
            fetchall=True,
        )
        or []
    )


def obtener_cita(cita_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM matrimonio_citas WHERE id=? AND user_id=?",
        [int(cita_id), uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def guardar_cita(
    fecha: str,
    hora,
    tipo: str,
    titulo: str,
    descripcion: str,
    lugar: str,
    presupuesto,
    ambito: str = "Matrimonio",
    preparacion: str = "",
) -> int:
    rid = ejecutar(
        """
        INSERT INTO matrimonio_citas
            (user_id, fecha, hora, tipo_cita, titulo, descripcion,
             lugar, presupuesto_estimado, estado_planificacion,
             ambito, notas_preparacion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Planeando', ?, ?)
        """,
        [
            uid(),
            str(fecha),
            str(hora) if hora else None,
            str(tipo),
            str(titulo),
            str(descripcion or ""),
            str(lugar or ""),
            float(presupuesto) if presupuesto else 0.0,
            str(ambito),
            str(preparacion or ""),
        ],
    )
    invalidate_data_caches()
    return rid


def actualizar_cita(
    cita_id: int,
    fecha: str,
    hora,
    tipo: str,
    titulo: str,
    descripcion: str,
    lugar: str,
    presupuesto,
    estado: str,
    ambito: str,
    preparacion: str,
) -> None:
    ejecutar(
        """
        UPDATE matrimonio_citas
        SET fecha=?, hora=?, tipo_cita=?, titulo=?,
            descripcion=?, lugar=?, presupuesto_estimado=?,
            estado_planificacion=?, ambito=?,
            notas_preparacion=?, actualizado_en=?
        WHERE id=? AND user_id=?
        """,
        [
            str(fecha),
            str(hora) if hora else None,
            str(tipo),
            str(titulo),
            str(descripcion or ""),
            str(lugar or ""),
            float(presupuesto) if presupuesto else 0.0,
            str(estado),
            str(ambito),
            str(preparacion or ""),
            iso_ahora(),
            int(cita_id),
            uid(),
        ],
    )
    invalidate_data_caches()


def eliminar_cita(cita_id: int) -> None:
    ejecutar(
        "DELETE FROM matrimonio_citas WHERE id=? AND user_id=?",
        [int(cita_id), uid()],
    )
    invalidate_data_caches()


def obtener_notas(categoria=None, urgencia_min: int = 1) -> list:
    conditions = ["user_id = ?", "urgencia >= ?"]
    params: list = [uid(), int(urgencia_min)]
    if categoria:
        conditions.append("categoria = ?")
        params.append(categoria)
    where = " AND ".join(conditions)
    return (
        ejecutar(
            f"""SELECT * FROM matrimonio_notas WHERE {where}
                ORDER BY urgencia DESC, creado_en DESC""",
            params,
            fetchall=True,
        )
        or []
    )


def obtener_nota(nota_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM matrimonio_notas WHERE id=? AND user_id=?",
        [int(nota_id), uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def guardar_nota(
    categoria: str,
    contenido: str,
    contexto: str,
    fecha_mencion: str,
    urgencia: int,
) -> int:
    rid = ejecutar(
        """
        INSERT INTO matrimonio_notas
            (user_id, categoria, contenido, contexto, fecha_mencion, urgencia)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            str(categoria),
            str(contenido),
            str(contexto or ""),
            str(fecha_mencion),
            int(urgencia),
        ],
    )
    invalidate_data_caches()
    return rid


def actualizar_nota(
    nota_id: int,
    categoria: str,
    contenido: str,
    contexto: str,
    urgencia: int,
) -> None:
    ejecutar(
        """
        UPDATE matrimonio_notas
        SET categoria=?, contenido=?, contexto=?,
            urgencia=?, actualizado_en=?
        WHERE id=? AND user_id=?
        """,
        [
            str(categoria),
            str(contenido),
            str(contexto or ""),
            int(urgencia),
            iso_ahora(),
            int(nota_id),
            uid(),
        ],
    )
    invalidate_data_caches()


def eliminar_nota(nota_id: int) -> None:
    ejecutar(
        "DELETE FROM matrimonio_notas WHERE id=? AND user_id=?",
        [int(nota_id), uid()],
    )
    invalidate_data_caches()


def registrar_habito(
    fecha: str,
    minutos: int,
    tipo_conexion: str,
    iniciado_por: str,
    satisfaccion: int,
    notas: str,
    modo_pareja: int,
) -> None:
    ejecutar(
        """
        INSERT INTO matrimonio_habitos
            (user_id, fecha, tiempo_calidad_minutos, tipo_conexion,
             iniciado_por, satisfaccion, notas,
             modo_pareja_activado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, fecha) DO UPDATE SET
            tiempo_calidad_minutos = excluded.tiempo_calidad_minutos,
            tipo_conexion          = excluded.tipo_conexion,
            iniciado_por           = excluded.iniciado_por,
            satisfaccion           = excluded.satisfaccion,
            notas                  = excluded.notas,
            modo_pareja_activado   = excluded.modo_pareja_activado
        """,
        [
            uid(),
            str(fecha),
            int(minutos),
            str(tipo_conexion),
            str(iniciado_por),
            int(satisfaccion),
            str(notas or ""),
            int(modo_pareja),
        ],
    )
    invalidate_data_caches()


def obtener_habitos_recientes(dias: int = 14) -> list:
    fecha_desde = (_hoy() - timedelta(days=dias)).isoformat()
    return (
        ejecutar_cached(
            """
            SELECT * FROM matrimonio_habitos
            WHERE fecha >= ? AND user_id = ?
            ORDER BY fecha DESC
            """,
            (fecha_desde, uid()),
        )
        or []
    )


def verificar_alerta_20_30(hoy_local) -> tuple:
    """
    Recibe hoy_local (date) para zona horaria local.
    Devuelve (alerta: bool, proxima_cita | None).
    """
    hoy_iso = hoy_local.isoformat()
    manana_iso = (hoy_local + timedelta(days=1)).isoformat()

    citas_hoy = obtener_citas(fecha_desde=hoy_iso, estado="Confirmada")
    citas_manana = obtener_citas(fecha_desde=manana_iso)
    proxima = (
        citas_hoy[0]
        if citas_hoy
        else citas_manana[0]
        if citas_manana
        else None
    )

    ahora_local = datetime.now()
    hora = ahora_local.hour
    minuto = ahora_local.minute
    alerta = (
        proxima is not None
        and proxima["fecha"] == hoy_iso
        and ((hora == 20 and minuto >= 30) or (hora == 21 and minuto <= 15))
    )
    return alerta, proxima
