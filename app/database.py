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
from app.db.migrate import migrar_local_a_turso  # noqa: F401

if __name__ == "__main__":
    init_database()
    print("🚀 Base de datos lista para usar")
