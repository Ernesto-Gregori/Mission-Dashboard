"""
multiuser.py — Migración a datos por usuario + provisión de defaults
"""
from __future__ import annotations

import json
from typing import Optional

# Tablas de negocio que deben llevar user_id
USER_TABLES = [
    "ingreso_mensual",
    "gastos_sobres",
    "receipt_items",
    "price_matches",
    "bitacora_semanal",
    "bloques_fijos",
    "sesiones_completadas",
    "libros",
    "resaltados",
    "devocionales",
    "registros_salud",
    "sandbox_ideas",
    "sandbox_snippets",
    "sandbox_sesiones",
    "matrimonio_citas",
    "matrimonio_notas",
    "matrimonio_habitos",
    "habitos_config",
    "habitos_diarios_v2",
    "pedidos_oracion",
    "eventos_calendario",
]

MODULOS_DEFAULT = [
    "agenda", "finanzas", "deep_work", "teologia",
    "biblioteca", "salud", "sandbox", "matrimonio",
]


def _table_columns(ejecutar, table: str) -> set[str]:
    rows = ejecutar(f"PRAGMA table_info({table})", fetchall=True) or []
    # Turso/libsql may not support PRAGMA the same way — fallback
    if not rows:
        return set()
    cols = set()
    for r in rows:
        # sqlite Row dict: name key; or index 1
        if isinstance(r, dict):
            cols.add(r.get("name") or r.get("Name") or "")
        else:
            cols.add(r[1])
    return {c for c in cols if c}


def _first_admin_id(ejecutar) -> Optional[int]:
    rows = ejecutar(
        "SELECT id FROM usuarios WHERE activo = 1 ORDER BY id LIMIT 1",
        fetchall=True,
    ) or []
    if not rows:
        return None
    return int(rows[0]["id"])


def _add_user_id_column(ejecutar, table: str) -> None:
    cols = _table_columns(ejecutar, table)
    if not cols:
        # PRAGMA falló (p.ej. Turso): intentar ALTER y tragar "duplicate"
        try:
            ejecutar(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        except Exception:
            pass
        return
    if "user_id" in cols:
        return
    try:
        ejecutar(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
    except Exception as e:
        print(f"[multiuser] ALTER {table}: {e}")


def _assign_orphans(ejecutar, table: str, admin_id: int) -> None:
    try:
        ejecutar(
            f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
            [admin_id],
        )
    except Exception as e:
        print(f"[multiuser] assign {table}: {e}")


def _ensure_user_modulos_table(ejecutar) -> None:
    ejecutar("""
        CREATE TABLE IF NOT EXISTS user_modulos (
            user_id INTEGER NOT NULL,
            modulo TEXT NOT NULL,
            activo BOOLEAN DEFAULT 1,
            config_json TEXT DEFAULT '{}',
            PRIMARY KEY (user_id, modulo)
        )
    """)


def _rebuild_oauth_tokens(ejecutar) -> None:
    """PK pasa de provider → (user_id, provider)."""
    try:
        cols = _table_columns(ejecutar, "oauth_tokens")
        if cols and "user_id" in cols:
            return
    except Exception:
        pass
    try:
        ejecutar("""
            CREATE TABLE IF NOT EXISTS oauth_tokens_v2 (
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                token_json TEXT NOT NULL,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, provider)
            )
        """)
        # Copiar filas antiguas (sin user_id) al admin si existe
        admin_id = _first_admin_id(ejecutar)
        if admin_id:
            old = ejecutar(
                "SELECT provider, token_json, actualizado_en FROM oauth_tokens",
                fetchall=True,
            ) or []
            for row in old:
                # puede fallar si ya es v2
                try:
                    ejecutar("""
                        INSERT OR IGNORE INTO oauth_tokens_v2
                            (user_id, provider, token_json, actualizado_en)
                        VALUES (?, ?, ?, ?)
                    """, [
                        admin_id,
                        row["provider"],
                        row["token_json"],
                        row.get("actualizado_en"),
                    ])
                except Exception:
                    pass
        # Renombrar: drop old, rename v2 — SQLite
        try:
            ejecutar("DROP TABLE IF EXISTS oauth_tokens")
            ejecutar("ALTER TABLE oauth_tokens_v2 RENAME TO oauth_tokens")
        except Exception as e:
            print(f"[multiuser] oauth rename: {e}")
            # Si DROP falló porque v2 ya es la tabla, ok
    except Exception as e:
        print(f"[multiuser] oauth rebuild: {e}")


def _ensure_per_user_indexes(ejecutar) -> None:
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_gastos_user ON gastos_sobres(user_id, fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_ingreso_user ON ingreso_mensual(user_id, anio, mes)",
        "CREATE INDEX IF NOT EXISTS idx_bitacora_user ON bitacora_semanal(user_id, semana_inicio)",
        "CREATE INDEX IF NOT EXISTS idx_devocionales_user ON devocionales(user_id, fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_salud_user ON registros_salud(user_id, fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_habitos_cfg_user ON habitos_config(user_id, clave)",
        "CREATE INDEX IF NOT EXISTS idx_habitos_dia_user ON habitos_diarios_v2(user_id, fecha)",
        "CREATE INDEX IF NOT EXISTS idx_bloques_user ON bloques_fijos(user_id, activo)",
        "CREATE INDEX IF NOT EXISTS idx_libros_user ON libros(user_id, estado)",
        "CREATE INDEX IF NOT EXISTS idx_eventos_user ON eventos_calendario(user_id, fecha)",
        "CREATE INDEX IF NOT EXISTS idx_citas_user ON matrimonio_citas(user_id, fecha)",
        # Unique compuestos (SQLite permite varios unique indexes)
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ingreso_user_mes ON ingreso_mensual(user_id, mes, anio)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bitacora_user_sem ON bitacora_semanal(user_id, semana_inicio)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_devocional_user_fecha ON devocionales(user_id, fecha)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_salud_user_fecha ON registros_salud(user_id, fecha)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_habito_cfg_user_clave ON habitos_config(user_id, clave)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_habito_dia_user ON habitos_diarios_v2(user_id, fecha, habito_clave)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mat_habito_user ON matrimonio_habitos(user_id, fecha)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sesion_user ON sesiones_completadas(user_id, fecha, bloque_fijo_id)",
    ]
    for sql in indexes:
        try:
            ejecutar(sql)
        except Exception as e:
            # UNIQUE viejo en tabla puede chocar al insertar 2º usuario — documentado
            print(f"[multiuser] index: {e}")


def _sqlite_rebuild_unique_tables(ejecutar) -> None:
    """
    SQLite no deja quitar UNIQUE del CREATE original.
    Recreamos tablas críticas con UNIQUE(user_id, ...).
    """
    rebuilds = {
        "ingreso_mensual": """
            CREATE TABLE ingreso_mensual_mu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                anio INTEGER NOT NULL,
                monto_total REAL NOT NULL DEFAULT 0,
                notas TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, mes, anio)
            )
        """,
        "devocionales": None,  # muchas columnas — solo índices compuestos; riesgo si UNIQUE(fecha) queda
        "registros_salud": None,
        "habitos_diarios_v2": """
            CREATE TABLE habitos_diarios_v2_mu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fecha DATE NOT NULL,
                habito_clave TEXT NOT NULL,
                completado BOOLEAN DEFAULT 0,
                hora_completado TIME,
                UNIQUE(user_id, fecha, habito_clave)
            )
        """,
        "bitacora_semanal": None,
        "matrimonio_habitos": """
            CREATE TABLE matrimonio_habitos_mu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fecha DATE NOT NULL,
                tiempo_calidad_minutos INTEGER,
                tipo_conexion TEXT,
                iniciado_por TEXT,
                satisfaccion INTEGER,
                notas TEXT,
                modo_pareja_activado BOOLEAN DEFAULT 0,
                actualizado_en TIMESTAMP,
                UNIQUE(user_id, fecha)
            )
        """,
    }

    # ingreso_mensual
    try:
        cols = _table_columns(ejecutar, "ingreso_mensual")
        # Si ya tiene el esquema nuevo (solo UNIQUE user) — detectar por índice
        # Siempre intentar rebuild si existe UNIQUE viejo: copiar a _mu
        ejecutar(rebuilds["ingreso_mensual"])
        rows = ejecutar("SELECT * FROM ingreso_mensual", fetchall=True) or []
        for r in rows:
            uid = r.get("user_id")
            if uid is None:
                continue
            ejecutar("""
                INSERT OR IGNORE INTO ingreso_mensual_mu
                    (id, user_id, mes, anio, monto_total, notas, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                r.get("id"), uid, r.get("mes"), r.get("anio"),
                r.get("monto_total"), r.get("notas"), r.get("creado_en"),
            ])
        ejecutar("DROP TABLE ingreso_mensual")
        ejecutar("ALTER TABLE ingreso_mensual_mu RENAME TO ingreso_mensual")
        print("[multiuser] rebuilt ingreso_mensual")
    except Exception as e:
        print(f"[multiuser] rebuild ingreso_mensual: {e}")
        try:
            ejecutar("DROP TABLE IF EXISTS ingreso_mensual_mu")
        except Exception:
            pass

    # habitos_diarios_v2
    try:
        ejecutar(rebuilds["habitos_diarios_v2"])
        rows = ejecutar("SELECT * FROM habitos_diarios_v2", fetchall=True) or []
        for r in rows:
            uid = r.get("user_id")
            if uid is None:
                continue
            ejecutar("""
                INSERT OR IGNORE INTO habitos_diarios_v2_mu
                    (id, user_id, fecha, habito_clave, completado, hora_completado)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                r.get("id"), uid, r.get("fecha"), r.get("habito_clave"),
                r.get("completado"), r.get("hora_completado"),
            ])
        ejecutar("DROP TABLE habitos_diarios_v2")
        ejecutar("ALTER TABLE habitos_diarios_v2_mu RENAME TO habitos_diarios_v2")
        print("[multiuser] rebuilt habitos_diarios_v2")
    except Exception as e:
        print(f"[multiuser] rebuild habitos_diarios: {e}")
        try:
            ejecutar("DROP TABLE IF EXISTS habitos_diarios_v2_mu")
        except Exception:
            pass

    # matrimonio_habitos
    try:
        ejecutar(rebuilds["matrimonio_habitos"])
        rows = ejecutar("SELECT * FROM matrimonio_habitos", fetchall=True) or []
        for r in rows:
            uid = r.get("user_id")
            if uid is None:
                continue
            ejecutar("""
                INSERT OR IGNORE INTO matrimonio_habitos_mu
                    (id, user_id, fecha, tiempo_calidad_minutos, tipo_conexion,
                     iniciado_por, satisfaccion, notas, modo_pareja_activado, actualizado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                r.get("id"), uid, r.get("fecha"), r.get("tiempo_calidad_minutos"),
                r.get("tipo_conexion"), r.get("iniciado_por"), r.get("satisfaccion"),
                r.get("notas"), r.get("modo_pareja_activado"), r.get("actualizado_en"),
            ])
        ejecutar("DROP TABLE matrimonio_habitos")
        ejecutar("ALTER TABLE matrimonio_habitos_mu RENAME TO matrimonio_habitos")
        print("[multiuser] rebuilt matrimonio_habitos")
    except Exception as e:
        print(f"[multiuser] rebuild matrimonio_habitos: {e}")
        try:
            ejecutar("DROP TABLE IF EXISTS matrimonio_habitos_mu")
        except Exception:
            pass

    # devocionales / registros_salud / bitacora — rebuild slim unique key via copy
    for table, uk_cols, create_sql in [
        ("devocionales", ["user_id", "fecha"], None),
        ("registros_salud", ["user_id", "fecha"], None),
        ("bitacora_semanal", ["user_id", "semana_inicio"], None),
        ("habitos_config", ["user_id", "clave"], None),
        ("sesiones_completadas", ["user_id", "fecha", "bloque_fijo_id"], None),
    ]:
        try:
            _rebuild_table_generic(ejecutar, table)
        except Exception as e:
            print(f"[multiuser] rebuild {table}: {e}")


def _rebuild_table_generic(ejecutar, table: str) -> None:
    """
    Recrea la tabla copiando esquema vía SELECT, quitando UNIQUE de una columna sola.
    Estrategia: CREATE TABLE AS no conserva constraints bien.
    Usamos: rename old → create new from pragma → copy → drop old.
    Si falla, dejamos índices compuestos (pueden chocar con UNIQUE viejo al 2º usuario).
    """
    # Marca: si ya migró esta tabla
    try:
        done = ejecutar(
            "SELECT id FROM _migrations WHERE id = ?",
            [f"rebuild_{table}"], fetchall=True,
        ) or []
        if done:
            return
    except Exception:
        pass

    cols_info = ejecutar(f"PRAGMA table_info({table})", fetchall=True) or []
    if not cols_info:
        return
    # Solo rebuild si user_id existe
    names = [c.get("name") if isinstance(c, dict) else c[1] for c in cols_info]
    if "user_id" not in names:
        return

    tmp = f"{table}__old_mu"
    new = f"{table}__new_mu"
    try:
        ejecutar(f"ALTER TABLE {table} RENAME TO {tmp}")
    except Exception:
        return

    # Recrear sin UNIQUE de columna única: generar DDL simple
    col_defs = []
    for c in cols_info:
        if isinstance(c, dict):
            name, ctype, notnull, dflt, pk = c["name"], c.get("type") or "", c.get("notnull"), c.get("dflt_value"), c.get("pk")
        else:
            name, ctype, notnull, dflt, pk = c[1], c[2], c[3], c[4], c[5]
        parts = [name, ctype or ""]
        if pk:
            parts.append("PRIMARY KEY")
        elif notnull:
            parts.append("NOT NULL")
        if dflt is not None:
            parts.append(f"DEFAULT {dflt}")
        col_defs.append(" ".join(str(p) for p in parts if p != ""))

    # Añadir UNIQUE compuesto según tabla
    uniques = {
        "devocionales": "UNIQUE(user_id, fecha)",
        "registros_salud": "UNIQUE(user_id, fecha)",
        "bitacora_semanal": "UNIQUE(user_id, semana_inicio)",
        "habitos_config": "UNIQUE(user_id, clave)",
        "sesiones_completadas": "UNIQUE(user_id, fecha, bloque_fijo_id)",
    }
    ddl = f"CREATE TABLE {new} ({', '.join(col_defs)}"
    if table in uniques:
        ddl += f", {uniques[table]}"
    ddl += ")"
    try:
        ejecutar(ddl)
        col_list = ", ".join(names)
        ejecutar(f"INSERT INTO {new} ({col_list}) SELECT {col_list} FROM {tmp}")
        ejecutar(f"DROP TABLE {tmp}")
        ejecutar(f"ALTER TABLE {new} RENAME TO {table}")
        ejecutar(
            "INSERT OR IGNORE INTO _migrations (id) VALUES (?)",
            [f"rebuild_{table}"],
        )
        print(f"[multiuser] rebuilt {table}")
    except Exception as e:
        print(f"[multiuser] generic rebuild {table} failed: {e}")
        # Intentar restaurar
        try:
            ejecutar(f"ALTER TABLE {tmp} RENAME TO {table}")
        except Exception:
            pass
        try:
            ejecutar(f"DROP TABLE IF EXISTS {new}")
        except Exception:
            pass


def migrate_multiuser() -> dict:
    """
    Idempotente. Añade user_id, asigna huérfanos al primer admin,
    reconstruye oauth_tokens y crea índices por usuario.
    """
    from app.database import ejecutar

    report = {"ok": True, "admin_id": None, "tables": []}

    # Asegurar usuarios / oauth base
    try:
        ejecutar("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'admin',
                activo BOOLEAN DEFAULT 1,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass

    try:
        ejecutar("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id TEXT PRIMARY KEY,
                aplicado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass

    # Fast path: migración ya aplicada → no repetir PRAGMA/ALTER/rebuild
    try:
        done = ejecutar(
            "SELECT id FROM _migrations WHERE id = 'multiuser_v1'",
            fetchall=True,
        ) or []
        if done:
            _ensure_user_modulos_table(ejecutar)
            admin_id = _first_admin_id(ejecutar)
            report["admin_id"] = admin_id
            report["skipped"] = True
            if admin_id:
                try:
                    n_mod = ejecutar(
                        "SELECT COUNT(*) AS n FROM user_modulos WHERE user_id = ? AND activo = 1",
                        [admin_id],
                        fetchall=True,
                    ) or [{"n": 0}]
                    has_modules = int(n_mod[0]["n"] or 0) > 0
                    has_legacy = False
                    if not has_modules:
                        for table in (
                            "gastos_sobres",
                            "devocionales",
                            "bitacora_semanal",
                            "libros",
                            "registros_salud",
                            "matrimonio_citas",
                            "sandbox_ideas",
                            "sesiones_completadas",
                        ):
                            try:
                                r = ejecutar(
                                    f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?",
                                    [admin_id],
                                    fetchall=True,
                                ) or [{"n": 0}]
                                if int(r[0]["n"] or 0) > 0:
                                    has_legacy = True
                                    break
                            except Exception:
                                pass
                    if has_modules or has_legacy:
                        provision_user_defaults(
                            admin_id, only_if_empty=True, seed_modules=True
                        )
                except Exception as e:
                    print(f"[multiuser] provision admin (fast): {e}")
            return report
    except Exception as e:
        print(f"[multiuser] fast-path check: {e}")

    _ensure_user_modulos_table(ejecutar)
    _rebuild_oauth_tokens(ejecutar)

    admin_id = _first_admin_id(ejecutar)
    report["admin_id"] = admin_id

    for table in USER_TABLES:
        try:
            _add_user_id_column(ejecutar, table)
            if admin_id:
                _assign_orphans(ejecutar, table, admin_id)
            report["tables"].append(table)
        except Exception as e:
            print(f"[multiuser] table {table}: {e}")
            report["ok"] = False

    # Rebuild unique constraints (solo una vez)
    try:
        done = ejecutar(
            "SELECT id FROM _migrations WHERE id = 'multiuser_rebuild_v1'",
            fetchall=True,
        ) or []
        if not done:
            _sqlite_rebuild_unique_tables(ejecutar)
            ejecutar(
                "INSERT OR IGNORE INTO _migrations (id) VALUES ('multiuser_rebuild_v1')"
            )
    except Exception as e:
        print(f"[multiuser] rebuild phase: {e}")

    _ensure_per_user_indexes(ejecutar)

    try:
        ejecutar(
            "INSERT OR IGNORE INTO _migrations (id) VALUES ('multiuser_v1')"
        )
    except Exception:
        pass

    if admin_id:
        # Solo auto-sembrar si ya hay módulos activos o datos de negocio reales.
        # Los hábitos seed de init_database (huérfanos asignados) NO cuentan:
        # en installs nuevas el admin debe pasar por el Coach IA.
        try:
            n_mod = ejecutar(
                "SELECT COUNT(*) AS n FROM user_modulos WHERE user_id = ? AND activo = 1",
                [admin_id],
                fetchall=True,
            ) or [{"n": 0}]
            has_modules = int(n_mod[0]["n"] or 0) > 0
            has_legacy = False
            for table in (
                "gastos_sobres",
                "devocionales",
                "bitacora_semanal",
                "libros",
                "registros_salud",
                "matrimonio_citas",
                "sandbox_ideas",
                "sesiones_completadas",
            ):
                try:
                    r = ejecutar(
                        f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?",
                        [admin_id],
                        fetchall=True,
                    ) or [{"n": 0}]
                    if int(r[0]["n"] or 0) > 0:
                        has_legacy = True
                        break
                except Exception:
                    pass
            if has_modules or has_legacy:
                provision_user_defaults(admin_id, only_if_empty=True, seed_modules=True)
        except Exception as e:
            print(f"[multiuser] provision admin: {e}")

    return report


def provision_user_defaults(
    user_id: int,
    only_if_empty: bool = False,
    seed_modules: bool | None = None,
) -> None:
    """
    Prepara defaults de un usuario.

    - Usuarios nuevos (seed_modules=False): no activan módulos ni hábitos;
      el Coach IA lo hace en el primer login.
    - Migración del admin existente (only_if_empty=True): activa todos los
      módulos, marca onboarding completo y siembra hábitos/bloques si faltan.
    """
    from app.database import ejecutar

    _ensure_user_modulos_table(ejecutar)

    if seed_modules is None:
        seed_modules = bool(only_if_empty)

    if seed_modules:
        for mod in MODULOS_DEFAULT:
            ejecutar("""
                INSERT OR IGNORE INTO user_modulos (user_id, modulo, activo, config_json)
                VALUES (?, ?, 1, '{}')
            """, [user_id, mod])
        try:
            ejecutar(
                "ALTER TABLE usuarios ADD COLUMN onboarding_completo INTEGER DEFAULT 0"
            )
        except Exception:
            pass
        ejecutar(
            "UPDATE usuarios SET onboarding_completo = 1 WHERE id = ?",
            [user_id],
        )

    # Usuarios nuevos: el coach siembra hábitos/módulos
    if not seed_modules:
        return

    if only_if_empty:
        n = ejecutar(
            "SELECT COUNT(*) AS n FROM habitos_config WHERE user_id = ?",
            [user_id], fetchall=True,
        ) or [{"n": 0}]
        if int(n[0]["n"] or 0) > 0:
            return

    habitos = [
        ("devocional", "Devocional", "📖", "05:45", 1),
        ("codigo", "Código", "💻", "06:15", 2),
        ("lectura", "Lectura", "📚", "19:30", 3),
        ("calistenia", "Calistenia", "💪", "Mié 16:30", 4),
    ]
    for clave, label, emoji, hora, orden in habitos:
        ejecutar("""
            INSERT OR IGNORE INTO habitos_config
                (user_id, clave, label, emoji, hora, activo, orden)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, [user_id, clave, label, emoji, hora, orden])

    n_b = ejecutar(
        "SELECT COUNT(*) AS n FROM bloques_fijos WHERE user_id = ?",
        [user_id], fetchall=True,
    ) or [{"n": 0}]
    if int(n_b[0]["n"] or 0) == 0:
        bloques = [
            ("Instituto Bíblico", "08:00", "12:30", "[1,2,3,4,5]", "Instituto", "#a371f7"),
            ("Deep Work: Código", "06:15", "07:15", "[1,2,3,4,5]", "Programacion", "#3fb950"),
            ("Sesión Biblioteca", "19:30", "21:00", "[2,3,4]", "Biblioteca", "#e3b341"),
        ]
        for nombre, inicio, fin, dias, tipo, color in bloques:
            ejecutar("""
                INSERT INTO bloques_fijos
                    (user_id, nombre, hora_inicio, hora_fin, dias_semana, tipo, color, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, [user_id, nombre, inicio, fin, dias, tipo, color])
