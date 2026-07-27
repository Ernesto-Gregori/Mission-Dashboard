"""Migración one-shot SQLite local → Turso."""
from __future__ import annotations

import sqlite3

from app.db import core as _core


def migrar_local_a_turso():
    """
    Migra todos los datos de SQLite local a Turso.
    Ejecutar UNA SOLA VEZ después de configurar Turso.
    """
    url, token = _core._get_turso_config()
    if not url or not token:
        print("❌ TURSO_URL y TURSO_TOKEN no configurados")
        return False

    print(f"🔄 Conectando a Turso: {url}")

    # Leer datos locales
    conn_local = sqlite3.connect(_core.DB_PATH, timeout=30)
    conn_local.row_factory = sqlite3.Row
    cursor_local = conn_local.cursor()

    # Conectar a Turso
    libsql = _core.libsql
    conn_turso = libsql.connect(url, auth_token=token)
    cursor_turso = conn_turso.cursor()

    # Paso 1 — Crear esquema en Turso
    print("📋 Creando esquema en Turso...")
    cursor_local.execute("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND sql IS NOT NULL
        ORDER BY rootpage
    """)
    for (schema_sql,) in cursor_local.fetchall():
        if schema_sql:
            try:
                cursor_turso.execute(schema_sql)
                conn_turso.commit()
            except Exception as e:
                if 'already exists' not in str(e).lower():
                    print(f"  ⚠️ Schema: {e}")

    # Paso 2 — Migrar datos
    tablas = [
        'bitacora_semanal', 'bloques_fijos', 'sesiones_completadas',
        'libros', 'resaltados', 'devocionales', 'registros_salud',
        'sandbox_ideas', 'sandbox_snippets', 'sandbox_sesiones',
        'matrimonio_citas', 'matrimonio_notas', 'matrimonio_habitos',
        'habitos_config', 'habitos_diarios_v2', 'pedidos_oracion',
        'ingreso_mensual', 'gastos_sobres', 'eventos_calendario',
        'usuarios', 'oauth_tokens',
    ]

    total = 0
    for tabla in tablas:
        try:
            cursor_local.execute(f"SELECT * FROM {tabla}")
            filas = cursor_local.fetchall()
            if not filas:
                print(f"  ⏭️  {tabla}: vacía")
                continue

            cols = [d[0] for d in cursor_local.description]
            placeholders = ', '.join(['?' for _ in cols])
            cols_str = ', '.join(cols)
            sql_insert = (
                f"INSERT OR IGNORE INTO {tabla} "
                f"({cols_str}) VALUES ({placeholders})"
            )

            errores = 0
            for fila in filas:
                try:
                    cursor_turso.execute(sql_insert, list(fila))
                except Exception as e:
                    errores += 1

            conn_turso.commit()
            total += len(filas)
            status = f"({errores} errores)" if errores else "✅"
            print(f"  {status} {tabla}: {len(filas)} filas")

        except Exception as e:
            print(f"  ❌ {tabla}: {e}")

    conn_local.close()
    print(f"\n🎉 Migración completa — {total} filas totales")
    return True
