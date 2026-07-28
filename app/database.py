"""
database.py — compat shim.

La implementación vive en app.db.* por dominio.
Todo `from app.database import …` sigue funcionando.
"""
from __future__ import annotations

from app.db.adapters import (  # noqa: F401
    adapt_date,
    adapt_datetime,
    convert_date,
    convert_datetime,
)
from app.db.core import (  # noqa: F401
    DB_PATH,
    ejecutar,
    ejecutar_cached,
    ensure_database,
    ensure_remote_schema,
    invalidate_data_caches,
    usar_turso,
    _get_turso_config,
    _get_turso_conn,
    libsql,
)
from app.db.schema import SOBRES_CONFIG, init_sobres, init_database  # noqa: F401
from app.db.finanzas import (  # noqa: F401
    guardar_ingreso,
    obtener_ingreso,
    agregar_gasto_sobre,
    obtener_gastos_sobre,
    actualizar_gasto_sobre,
    eliminar_gasto_sobre,
    _calcular_sobres_uncached,
    obtener_tipos_bloque,
    calcular_sobres,
    _calcular_sobres_cached,
)
from app.db.usuarios import (  # noqa: F401
    _hash_password,
    verificar_password,
    contar_usuarios,
    crear_usuario,
    obtener_usuario_activo,
    autenticar_usuario,
    listar_usuarios,
)
from app.db.agenda import (  # noqa: F401
    COLORES_TIPO,
    DIAS_SEMANA,
    SEMAFOROS,
    SYSTEM_AGENDA,
    TIPOS_EVENTO,
    calcular_racha_deepwork,
    calcular_racha_devocional,
    calcular_racha_ejercicio,
    eliminar_evento,
    guardar_bitacora,
    guardar_evento,
    obtener_bitacora,
    obtener_bitacoras_recientes,
    obtener_deepwork_semana,
    obtener_devocionales_semana,
    obtener_eventos_personalizados,
    obtener_eventos_semana,
    obtener_libros_leyendo,
    obtener_lunes_semana,
    obtener_salud_semana,
)
from app.db.salud import (  # noqa: F401
    SYSTEM_SALUD,
    TIPOS_EJERCICIO,
    ZONAS_LISTA,
    analizar_correlacion_simple,
    calcular_promedios,
    construir_contexto_salud,
    guardar_registro_salud,
    obtener_registro_salud,
    obtener_registros_rango,
)
from app.db.deep_work import (  # noqa: F401
    COLORES as COLORES_DW,
    DIAS_LABELS as DIAS_LABELS_DW,
    DIAS_NOMBRES as DIAS_NOMBRES_DW,
    ESTADOS_SESION,
    SYSTEM_COACH_DW,
    actualizar_bloque,
    bloques_para_fecha,
    construir_resumen_semana,
    crear_bloque,
    desactivar_bloque,
    obtener_bloques_fijos,
    obtener_estado_sesion,
    obtener_sesiones_semana,
    obtener_todos_bloques,
    parse_dias_bloque,
    reactivar_bloque,
    registrar_sesion,
)
from app.db.teologia import (  # noqa: F401
    CATEGORIAS_PEDIDO,
    DIAS_ORACION_LABELS,
    ESTADOS_PEDIDO,
    URGENCIA_LABELS,
    VERSIONES_BIBLIA,
    actualizar_estado_pedido,
    agregar_pedido,
    editar_pedido,
    eliminar_pedido,
    guardar_devocional,
    obtener_devocional,
    obtener_devocionales_recientes,
    obtener_pedidos,
    parse_dias_oracion,
    pedidos_para_hoy,
)
from app.db.biblioteca import (  # noqa: F401
    CATEGORIAS as CATEGORIAS_LIBRO,
    COLORES_RESALTADO,
    ESTADOS_LIBRO,
    actualizar_libro,
    actualizar_progreso,
    agregar_libro_por_procesar,
    agregar_resaltado,
    crear_libro_manual,
    eliminar_libro,
    guardar_metadatos_ia,
    obtener_libro,
    obtener_libros_por_estado,
    obtener_resaltados,
    parsear_lista,
    pct_progreso,
    stats_biblioteca,
)
from app.db.migrate import migrar_local_a_turso  # noqa: F401

if __name__ == "__main__":
    init_database()
    print("🚀 Base de datos lista para usar")
