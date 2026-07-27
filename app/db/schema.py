"""Schema init: tablas SQLite + SOBRES_CONFIG."""
from __future__ import annotations

import sqlite3

from app.db.adapters import *  # noqa: F401,F403 — registra adapters
from app.db import core as _core


def _db_path():
    """Lee DB_PATH en runtime (tests pueden monkeypatchear core.DB_PATH)."""
    return _core.DB_PATH


SOBRES_CONFIG = {
    'Supervivencia': {
        'nombre': 'SUPERVIVENCIA',
        'emoji': '🔴',
        'descripcion': 'Gastos fijos + necesidades básicas',
        'color': '#f85149',
        'pct': 0.65,
        'subcategorias': [
            'Tarjeta_MSI',
            'Deuda_Fija',
            'Comida',
            'Transporte',
            'Servicios',
            'Otro_Supervivencia'
        ]
    },
    'Futuro_Hogar': {
        'nombre': 'FUTURO Y HOGAR',
        'emoji': '🟢',
        'descripcion': 'Ahorro sagrado — no tocar',
        'color': '#3fb950',
        'pct': 0.20,
        'subcategorias': [
            'Ahorro_Emergencia',
            'Fondo_Renta',
            'Otro_Ahorro'
        ]
    },
    'Ministerio_Extras': {
        'nombre': 'MINISTERIO Y EXTRAS',
        'emoji': '🔵',
        'descripcion': 'Libros, citas, ofrendas',
        'color': '#58a6ff',
        'pct': 0.15,
        'subcategorias': [
            'Libros_Cursos',
            'Cita_Esposa',
            'Ofrenda_Diezmo',
            'Personal'
        ]
    }
}

def init_sobres(cursor):
    """Crea tablas del sistema de 3 sobres"""
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingreso_mensual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            monto_total REAL NOT NULL DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mes, anio)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos_sobres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            sobre TEXT NOT NULL CHECK(sobre IN (
                'Supervivencia', 'Futuro_Hogar', 'Ministerio_Extras'
            )),
            subcategoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL CHECK(monto > 0),
            es_fijo BOOLEAN DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gastos_sobres_fecha
        ON gastos_sobres(fecha DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gastos_sobres_sobre
        ON gastos_sobres(sobre)
    """)


def init_database():
    """
    Inicializa la base de datos con todas las tablas necesarias.
    Ejecutar UNA VEZ al inicio de la aplicación.
    """
    # Crear carpeta data si no existe
    db_path = _db_path()
    db_path.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")  # ← permite lecturas simultáneas
    cursor.execute("PRAGMA synchronous=NORMAL")

    # ═══════════════════════════════════════════════════════════
    # TABLA: AGENDA — BITÁCORA SEMANAL
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bitacora_semanal (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            semana_inicio       DATE    UNIQUE NOT NULL,
            -- 3 Victorias
            victoria_1          TEXT,
            victoria_2          TEXT,
            victoria_3          TEXT,
            -- Monitor financiero
            ingreso_actual      REAL,
            sobre_supervivencia INTEGER DEFAULT 0,
            aporte_transicion   REAL    DEFAULT 0,
            presupuesto_cita    REAL    DEFAULT 0,
            semaforo_superv     TEXT    DEFAULT 'verde',
            semaforo_ahorros    TEXT    DEFAULT 'verde',
            semaforo_extras     TEXT    DEFAULT 'verde',
            gasto_pausado       TEXT,
            -- Cita/conexión
            actividad_cita      TEXT,
            costo_cita          REAL,
            -- Lectura
            libro_actual        TEXT,
            pagina_actual       INTEGER DEFAULT 0,
            frase_favorita      TEXT,
            -- Vaciado mental
            pendientes_soltar   TEXT,
            reflexion_semana    TEXT,
            -- Estado general
            estado              TEXT    DEFAULT 'abierta'
                                CHECK(estado IN ('abierta','cerrada')),
            creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bitacora_semana
        ON bitacora_semanal(semana_inicio)
    """)
    
        # ═════════════════════════════════════════════════════════
    # TABLA: BLOQUES_FIJOS (Deep Work - horarios recurrentes)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloques_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            hora_inicio TIME NOT NULL,
            hora_fin TIME NOT NULL,
            dias_semana TEXT NOT NULL,  -- JSON: [1,2,3,4,5] = Lunes a Viernes
            tipo TEXT NOT NULL,
            color TEXT DEFAULT '#58a6ff',
            activo BOOLEAN DEFAULT 1
        )
    """)
    
    # Bloques por defecto: ya no se siembran globalmente (Coach / provision por usuario).
    # NO deduplicar por nombre globalmente: borraría bloques de otros usuarios.
    bloques_default = []

    for nombre, inicio, fin, dias, tipo, color in bloques_default:
        cursor.execute("""
            INSERT OR IGNORE INTO bloques_fijos (nombre, hora_inicio, hora_fin, dias_semana, tipo, color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nombre, inicio, fin, dias, tipo, color))
    
    # ═════════════════════════════════════════════════════════
    # TABLA: SESIONES_COMPLETADAS (registro diario)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sesiones_completadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            bloque_fijo_id INTEGER NOT NULL,
            estado TEXT NOT NULL CHECK(estado IN ('Completado', 'Parcial', 'No_realizado', 'Postergado')),
            duracion_real INTEGER,  -- minutos efectivos
            notas TEXT,
            energia_inicio INTEGER CHECK(energia_inicio BETWEEN 1 AND 10),
            energia_fin INTEGER CHECK(energia_fin BETWEEN 1 AND 10),
            FOREIGN KEY (bloque_fijo_id) REFERENCES bloques_fijos(id),
            UNIQUE(fecha, bloque_fijo_id)
        )
    """)

    # ═════════════════════════════════════════════════════════
    # TABLA: LIBROS (metadatos extraídos por IA o manual)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS libros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT,
            titulo TEXT NOT NULL,
            subtitulo TEXT,
            autor TEXT,
            autores_adicionales TEXT,
            editorial TEXT,
            anio_publicacion INTEGER,
            edicion TEXT,
            idioma TEXT DEFAULT 'es',
            categoria_principal TEXT,
            subcategorias TEXT,
            temas_clave TEXT,
            descripcion TEXT,
            indice TEXT,
            notas_bibliotecaria TEXT,
            nombre_archivo TEXT,
            ruta_archivo TEXT,
            tamano_mb REAL,
            formato TEXT CHECK(formato IN ('PDF', 'EPUB', 'MOBI', 'TXT', 'Otro')),
            hash_archivo TEXT,
            total_paginas INTEGER,
            pagina_actual INTEGER DEFAULT 0,
            estado TEXT CHECK(estado IN (
                'por_procesar', 'procesando', 'catalogado',
                'leyendo', 'pausado', 'completado', 'abandonado'
            )) DEFAULT 'por_procesar',
            fuente_metadatos TEXT CHECK(fuente_metadatos IN ('IA', 'Manual', 'ISBN', 'Combinado')),
            confianza_ia INTEGER CHECK(confianza_ia BETWEEN 1 AND 10),
            revisado_manual BOOLEAN DEFAULT 0,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_libros_estado ON libros(estado)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_libros_isbn ON libros(isbn)")
    
    # ═════════════════════════════════════════════════════════
    # TABLA: RESALTADOS
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resaltados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            libro_id INTEGER NOT NULL,
            pagina INTEGER NOT NULL,
            parrafo_o_ubicacion TEXT,
            texto_resaltado TEXT NOT NULL,
            texto_contexto TEXT,
            color_etiqueta TEXT CHECK(color_etiqueta IN (
                'Amarillo', 'Verde', 'Azul', 'Rosa', 'Morado'
            )) DEFAULT 'Amarillo',
            nota_personal TEXT,
            fecha_resaltado DATE DEFAULT CURRENT_DATE,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (libro_id) REFERENCES libros(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resaltados_libro ON resaltados(libro_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resaltados_color ON resaltados(color_etiqueta)")

    # ═════════════════════════════════════════════════════════
    # TABLA: DEVOCIONALES (Bitácora Teológica)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devocionales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL UNIQUE,
            hora_inicio TIME DEFAULT '05:45',
            
            -- Lectura bíblica
            pasaje_referencia TEXT NOT NULL,  -- "Salmo 23:1-6", "Juan 3:16", etc.
            pasaje_texto TEXT,  -- Texto completo del pasaje
            version_biblia TEXT DEFAULT 'NVI',  -- NVI, RVR1960, ESV, etc.
            
            -- Reflexión estructurada
            observacion TEXT,  -- "¿Qué dice el texto?" (método inductive)
            interpretacion TEXT,  -- "¿Qué significa?"
            aplicacion TEXT,  -- "¿Cómo aplica a mi vida?"
            
            -- Conexiones personales
            conexion_instituto TEXT,  -- ¿Relación con clases actuales?
            conexion_situacion TEXT,  -- ¿Qué estoy viviendo hoy?
            
            -- Oración
            oracion_escrita TEXT,
            
            -- Metadata
            duracion_minutos INTEGER,  -- Cuánto duró el devocional
            lugar TEXT DEFAULT 'Casa',
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_devocionales_fecha ON devocionales(fecha DESC)")

    # ═════════════════════════════════════════════════════════
    # TABLA: REGISTROS_SALUD (Energía y ejercicio diario)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_salud (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL UNIQUE,
            
            -- Sueño
            horas_sueno REAL,
            calidad_sueno INTEGER CHECK(calidad_sueno BETWEEN 1 AND 10),
            hora_dormir TIME,
            hora_despertar TIME,
            
            -- Energía
            energia_manana INTEGER CHECK(energia_manana BETWEEN 1 AND 10),
            energia_tarde INTEGER CHECK(energia_tarde BETWEEN 1 AND 10),
            energia_noche INTEGER CHECK(energia_noche BETWEEN 1 AND 10),
            
            -- Ejercicio principal (resumen)
            hizo_ejercicio BOOLEAN DEFAULT 0,
            tipo_ejercicio TEXT,
            duracion_minutos INTEGER,
            intensidad INTEGER CHECK(intensidad BETWEEN 1 AND 10),
            notas_ejercicio TEXT,
            
            -- NUEVO: Detalle de sesiones múltiples
            zonas_musculares TEXT,   -- JSON: ["Pecho", "Core/Abdomen"]
            sesiones_json TEXT,      -- JSON: lista completa de sesiones
            
            -- NUEVO: Datos de Google Fit
            calorias_fit REAL,
            pasos_fit INTEGER,
            fc_promedio_fit INTEGER,
            fc_maxima_fit INTEGER,
            fuente_datos TEXT DEFAULT 'manual',  -- 'manual', 'google_fit', 'mixto'
            
            -- Productividad
            productividad_percibida INTEGER CHECK(productividad_percibida BETWEEN 1 AND 10),
            
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_salud_fecha ON registros_salud(fecha DESC)")

    # ═══════════════════════════════════════════════════════════
    # TABLAS: SANDBOX MULTI-DOMINIO
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_ideas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo      TEXT    NOT NULL,
            descripcion TEXT,
            dominio     TEXT    DEFAULT 'Personal',
            categoria   TEXT,
            etiquetas   TEXT    DEFAULT '[]',
            estado      TEXT    DEFAULT 'Idea'
                        CHECK(estado IN (
                            'Idea','Investigando','En_proceso',
                            'Completado','Pausado','Abandonado'
                        )),
            prioridad   INTEGER DEFAULT 3
                        CHECK(prioridad BETWEEN 1 AND 5),
            motivacion  INTEGER DEFAULT 7
                        CHECK(motivacion BETWEEN 1 AND 10),
            notas       TEXT,
            creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_snippets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo      TEXT    NOT NULL,
            descripcion TEXT,
            lenguaje    TEXT    DEFAULT 'Python',
            codigo      TEXT,
            tags        TEXT    DEFAULT '[]',
            dominio     TEXT    DEFAULT 'Programacion',
            veces_usado INTEGER DEFAULT 0,
            creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_sesiones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           DATE    DEFAULT CURRENT_DATE,
            duracion_minutos INTEGER,
            tipo_actividad  TEXT,
            dominio         TEXT    DEFAULT 'Personal',
            proyecto_id     INTEGER REFERENCES sandbox_ideas(id),
            descripcion     TEXT,
            codigo_producido TEXT,
            satisfaccion    INTEGER CHECK(satisfaccion BETWEEN 1 AND 10),
            creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migraciones seguras
    migraciones_sandbox = [
        "ALTER TABLE sandbox_ideas ADD COLUMN dominio TEXT DEFAULT 'Personal'",
        "ALTER TABLE sandbox_ideas ADD COLUMN etiquetas TEXT DEFAULT '[]'",
        "ALTER TABLE sandbox_ideas ADD COLUMN prioridad INTEGER DEFAULT 3",
        "ALTER TABLE sandbox_ideas ADD COLUMN notas TEXT",
        "ALTER TABLE sandbox_ideas ADD COLUMN actualizado_en TIMESTAMP",
        "ALTER TABLE sandbox_snippets ADD COLUMN dominio TEXT DEFAULT 'Programacion'",
        "ALTER TABLE sandbox_snippets ADD COLUMN actualizado_en TIMESTAMP",
        "ALTER TABLE sandbox_sesiones ADD COLUMN dominio TEXT DEFAULT 'Personal'",
    ]
    for sql in migraciones_sandbox:
        try:
            cursor.execute(sql)
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════
    # TABLA: MATRIMONIO - Gestión de citas y conexión de pareja
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matrimonio_citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            hora TIME,
            tipo_cita TEXT CHECK(tipo_cita IN (
                'Cena_Romantica', 'Salida_Casual', 'Estadia_Casa', 
                'Viaje_Corto', 'Aniversario', 'Cumpleanos_Esposa',
                'Sorpresa', 'Otra'
            )) DEFAULT 'Otra',
            titulo TEXT NOT NULL,  -- "Cena en el lugar favorito"
            descripcion TEXT,
            lugar TEXT,
            presupuesto_estimado REAL,
            
            -- Planificación
            estado_planificacion TEXT CHECK(estado_planificacion IN (
                'Idea', 'Planeando', 'Confirmada', 'Completada', 'Cancelada'
            )) DEFAULT 'Idea',
            
            -- Notas de preparación
            que_llevar TEXT,  -- flores, regalo, reserva confirmada
            notas_preparacion TEXT,
            
            -- Post-cita: reflexión
            como_salio TEXT,  -- descripción de cómo fue
            calidad_conexion INTEGER CHECK(calidad_conexion BETWEEN 1 AND 10),
            aprendizaje TEXT,  -- qué descubriste de tu esposa
            
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recordatorio_20_30_enviado BOOLEAN DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matrimonio_notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT CHECK(categoria IN (
                'Preferencias_Esposa', 'Ideas_Regalo', 'Frases_Recordar',
                'Momentos_Especiales', 'Metas_Pareja', 'Conversaciones_Pendientes'
            )),
            contenido TEXT NOT NULL,
            contexto TEXT,  -- dónde/when se mencionó
            fecha_mencion DATE,
            urgencia INTEGER CHECK(urgencia BETWEEN 1 AND 10),  -- 10 = hacer ASAP
            usado_en_cita_id INTEGER,  -- FK si se usó
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usado_en_cita_id) REFERENCES matrimonio_citas(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matrimonio_habitos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL UNIQUE,
            tiempo_calidad_minutos INTEGER,  -- tiempo real dedicado
            tipo_conexion TEXT CHECK(tipo_conexion IN (
                'Conversacion_Profunda', 'Actividad_Juntos', 'Intimidad_Fisica',
                'Servicio_Amor', 'Tiempo_Qualidad', 'Otro'
            )),
            iniciado_por TEXT CHECK(iniciado_por IN ('Yo', 'Esposa', 'Ambos')),
            satisfaccion INTEGER CHECK(satisfaccion BETWEEN 1 AND 10),
            notas TEXT,
            modo_pareja_activado BOOLEAN DEFAULT 0  -- ¿se respetó el 21:00?
        )
    """)

    # Migraciones matrimonio/familia
    migraciones_matrim = [
        "ALTER TABLE matrimonio_citas ADD COLUMN ambito TEXT DEFAULT 'Matrimonio'",
        "ALTER TABLE matrimonio_citas ADD COLUMN actualizado_en TIMESTAMP",
        "ALTER TABLE matrimonio_notas ADD COLUMN actualizado_en TIMESTAMP",
        "ALTER TABLE matrimonio_habitos ADD COLUMN actualizado_en TIMESTAMP",
    ]
    for sql in migraciones_matrim:
        try:
            cursor.execute(sql)
        except Exception:
            pass
    
    # Índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_citas_fecha ON matrimonio_citas(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_categoria ON matrimonio_notas(categoria)")

    # ═══════════════════════════════════════════════════════════
    # TABLA: HABITOS_CONFIG (catálogo dinámico)
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habitos_config (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            clave       TEXT    NOT NULL UNIQUE,
            label       TEXT    NOT NULL,
            emoji       TEXT    DEFAULT '⭐',
            hora        TEXT    DEFAULT '—',
            activo      BOOLEAN DEFAULT 1,
            orden       INTEGER DEFAULT 0,
            creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migración: tabla habitos_diarios sin CHECK constraint fijo
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habitos_diarios_v2 (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           DATE    NOT NULL,
            habito_clave    TEXT    NOT NULL,
            completado      BOOLEAN DEFAULT 0,
            hora_completado TIME,
            UNIQUE(fecha, habito_clave)
        )
    """)

    # Hábitos por defecto: ya no se siembran globalmente.
    # Cada usuario los recibe vía Coach IA o provision_user_defaults (legacy).
    habitos_defaults = []
    for clave, label, emoji, hora, orden in habitos_defaults:
        cursor.execute("""
            INSERT OR IGNORE INTO habitos_config
                (clave, label, emoji, hora, activo, orden)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (clave, label, emoji, hora, orden))

    # ═══════════════════════════════════════════════════════════
    # TABLA: PEDIDOS DE ORACIÓN
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_oracion (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo        TEXT    NOT NULL,
            descripcion   TEXT,
            categoria     TEXT    CHECK(categoria IN (
                              'Personal', 'Familia', 'Matrimonio',
                              'Instituto', 'Ministerio', 'Otros'
                          )) DEFAULT 'Personal',
            urgencia      INTEGER CHECK(urgencia BETWEEN 1 AND 5) DEFAULT 3,
            estado        TEXT    CHECK(estado IN (
                              'Activo', 'Respondido', 'En_espera', 'Archivado'
                          )) DEFAULT 'Activo',
            fecha_inicio  DATE    DEFAULT CURRENT_DATE,
            fecha_respuesta DATE,
            nota_respuesta TEXT,
            creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pedidos_estado
        ON pedidos_oracion(estado)
    """)
        # Migración: agregar dias_oracion si no existe
    try:
        cursor.execute("""
            ALTER TABLE pedidos_oracion
            ADD COLUMN dias_oracion TEXT DEFAULT '[]'
        """)
    except Exception:
        pass  # Ya existe

    # ═══════════════════════════════════════════════════════════════
    # TABLA: EVENTOS_CALENDARIO
    # ═══════════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_calendario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            hora_inicio TIME,
            hora_fin TIME,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            tipo TEXT DEFAULT 'Personal',
            color TEXT DEFAULT '#58a6ff',
            recurrente BOOLEAN DEFAULT 0,
            google_id TEXT,
            fuente TEXT DEFAULT 'local',
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_eventos_fecha 
        ON eventos_calendario(fecha)
    """)

    # ═══════════════════════════════════════════════════════════════
    # MIGRACIÓN: columnas Google Calendar en eventos_calendario
    # ═══════════════════════════════════════════════════════════════
    for sql in [
        "ALTER TABLE eventos_calendario ADD COLUMN google_id TEXT",
        "ALTER TABLE eventos_calendario ADD COLUMN fuente TEXT DEFAULT 'local'",
    ]:
        try:
            cursor.execute(sql)
        except Exception:
            pass  # Ya existe

    # ═══════════════════════════════════════════════════════════
    # TABLA: USUARIOS (auth local, hashes PBKDF2)
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            salt          TEXT    NOT NULL,
            rol           TEXT    NOT NULL DEFAULT 'admin'
                              CHECK(rol IN ('admin', 'usuario')),
            activo        BOOLEAN DEFAULT 1,
            plan          TEXT    DEFAULT 'free',
            plan_expira_en TEXT,
            coach_ia_usado INTEGER DEFAULT 0,
            onboarding_completo INTEGER DEFAULT 0,
            creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for sql in (
        "ALTER TABLE usuarios ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE usuarios ADD COLUMN plan_expira_en TEXT",
        "ALTER TABLE usuarios ADD COLUMN coach_ia_usado INTEGER DEFAULT 0",
        "ALTER TABLE usuarios ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE usuarios ADD COLUMN stripe_subscription_id TEXT",
        "ALTER TABLE usuarios ADD COLUMN onboarding_completo INTEGER DEFAULT 0",
    ):
        try:
            cursor.execute(sql)
        except Exception:
            pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uso_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            llamadas INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, anio, mes)
        )
    """)

    # ═══════════════════════════════════════════════════════════
    # TABLA: OAUTH_TOKENS (Google Fit/Calendar sobreviven al sleep)
    # ═══════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider       TEXT PRIMARY KEY,
            token_json     TEXT NOT NULL,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            accion TEXT NOT NULL,
            entidad TEXT,
            entidad_id TEXT,
            detalle TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_creado ON audit_log(creado_en DESC)"
    )

    init_sobres(cursor)
    conn.commit()
    conn.close()
    # Si Turso está activo, asegurar tablas críticas también allá
    try:
        from app.db.core import ensure_remote_schema
        ensure_remote_schema()
    except Exception:
        pass

