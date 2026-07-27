"""
database.py - Capa de acceso a datos para Mission Dashboard
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
import os
import json

try:
    import libsql
except ImportError:  # entorno local sin Turso
    libsql = None

# ═════════════════════════════════════════════════════════
# ADAPTADOR SQLITE PARA PYTHON 3.12+ (evita DeprecationWarning)
# ═════════════════════════════════════════════════════════

def adapt_date(val):
    """Adaptador para fechas en SQLite"""
    return val.isoformat()

def adapt_datetime(val):
    """Adaptador para datetimes en SQLite"""
    return val.isoformat()

sqlite3.register_adapter(date, adapt_date)
sqlite3.register_adapter(datetime, adapt_datetime)

def convert_date(val):
    """Conversor de fechas desde SQLite"""
    return datetime.fromisoformat(val.decode()).date()

def convert_datetime(val):
    """Conversor de datetimes desde SQLite"""
    return datetime.fromisoformat(val.decode())

sqlite3.register_converter("DATE", convert_date)
sqlite3.register_converter("TIMESTAMP", convert_datetime)

# Ruta de la base de datos
DB_PATH = Path(__file__).parent.parent / "data" / "mission.db"

# ═════════════════════════════════════════════════════════════════
# SISTEMA DE 3 SOBRES
# ═════════════════════════════════════════════════════════════════

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
    DB_PATH.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
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
    
    # Insertar tus bloques fijos si no existen
    bloques_default = [
        ("Instituto Bíblico", "08:00", "12:30", "[1,2,3,4,5]", "Instituto", "#a371f7"),
        ("Deep Work: Código", "06:15", "07:15", "[1,2,3,4,5]", "Programacion", "#3fb950"),
        ("Sesión Biblioteca", "19:30", "21:00", "[2,3,4]", "Biblioteca", "#e3b341"),
    ]
    
    for nombre, inicio, fin, dias, tipo, color in bloques_default:
        cursor.execute("""
            INSERT OR IGNORE INTO bloques_fijos (nombre, hora_inicio, hora_fin, dias_semana, tipo, color)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nombre, inicio, fin, dias, tipo, color))

    cursor.execute("""
        DELETE FROM bloques_fijos 
        WHERE id NOT IN (
            SELECT MIN(id) FROM bloques_fijos GROUP BY nombre
        )
    """)
    
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

    # Insertar hábitos fijos por defecto si no existen
    habitos_defaults = [
        ('devocional', 'Devocional', '📖', '05:45', 1),
        ('codigo',     'Código',     '💻', '06:15', 2),
        ('lectura',    'Lectura',    '📚', '19:30', 3),
        ('calistenia', 'Calistenia', '💪', 'Mié 16:30', 4),
    ]
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
            creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    init_sobres(cursor)
    conn.commit()
    conn.close()
    # Si Turso está activo, asegurar tablas críticas también allá
    try:
        ensure_remote_schema()
    except NameError:
        pass


# ═════════════════════════════════════════════════════════════════
# FUNCIONES CRUD PARA GASTOS
# Todas pasan por ejecutar() → misma BD (SQLite local o Turso)
# ═════════════════════════════════════════════════════════════════

def guardar_ingreso(mes: int, anio: int, monto: float, notas: str = "") -> bool:
    from app.tenant import uid
    try:
        ejecutar("""
            INSERT INTO ingreso_mensual (user_id, mes, anio, monto_total, notas)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, mes, anio)
            DO UPDATE SET monto_total = ?, notas = ?
        """, [uid(), mes, anio, monto, notas, monto, notas])
        try:
            invalidate_data_caches()
        except NameError:
            pass
        return True
    except Exception as e:
        try:
            ejecutar("""
                DELETE FROM ingreso_mensual
                WHERE user_id = ? AND mes = ? AND anio = ?
            """, [uid(), mes, anio])
            ejecutar("""
                INSERT INTO ingreso_mensual (user_id, mes, anio, monto_total, notas)
                VALUES (?, ?, ?, ?, ?)
            """, [uid(), mes, anio, monto, notas])
            try:
                invalidate_data_caches()
            except NameError:
                pass
            return True
        except Exception as e2:
            print(f"Error guardando ingreso: {e} / {e2}")
            return False

def obtener_ingreso(mes: int, anio: int) -> float:
    from app.tenant import uid
    rows = ejecutar("""
        SELECT monto_total FROM ingreso_mensual
        WHERE user_id = ? AND mes = ? AND anio = ?
    """, [uid(), mes, anio], fetchall=True) or []
    return float(rows[0]["monto_total"]) if rows else 0.0

def agregar_gasto_sobre(fecha, sobre: str, subcategoria: str,
                        descripcion: str, monto: float,
                        es_fijo: bool = False, notas: str = "") -> int:
    from app.tenant import uid
    gid = ejecutar("""
        INSERT INTO gastos_sobres
            (user_id, fecha, sobre, subcategoria, descripcion, monto, es_fijo, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [uid(), str(fecha), sobre, subcategoria, descripcion, monto,
          1 if es_fijo else 0, notas])
    try:
        invalidate_data_caches()
    except NameError:
        pass
    return gid

def obtener_gastos_sobre(mes=None, anio=None, sobre=None, limite=100) -> list:
    from app.tenant import uid
    query = "SELECT * FROM gastos_sobres WHERE user_id = ?"
    params = [uid()]

    if mes and anio:
        query += """ AND strftime('%m', fecha) = ?
                    AND strftime('%Y', fecha) = ?"""
        params.extend([f"{mes:02d}", str(anio)])
    if sobre:
        query += " AND sobre = ?"
        params.append(sobre)

    query += " ORDER BY fecha DESC, creado_en DESC LIMIT ?"
    params.append(limite)

    return ejecutar(query, params, fetchall=True) or []

def actualizar_gasto_sobre(gasto_id: int, **kwargs) -> bool:
    from app.tenant import uid
    campos_permitidos = {
        'fecha', 'sobre', 'subcategoria',
        'descripcion', 'monto', 'es_fijo', 'notas'
    }
    campos = {}
    for k, v in kwargs.items():
        if k not in campos_permitidos or v is None:
            continue
        if k == 'fecha':
            campos[k] = str(v)
        elif k == 'es_fijo':
            campos[k] = 1 if v else 0
        else:
            campos[k] = v
    if not campos:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in campos)
    try:
        ejecutar(
            f"UPDATE gastos_sobres SET {set_clause} WHERE id = ? AND user_id = ?",
            list(campos.values()) + [gasto_id, uid()]
        )
        rows = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        if rows:
            try:
                invalidate_data_caches()
            except NameError:
                pass
        return bool(rows)
    except Exception as e:
        print(f"Error actualizando gasto: {e}")
        return False

def eliminar_gasto_sobre(gasto_id: int) -> bool:
    from app.tenant import uid
    try:
        antes = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        if not antes:
            return False
        ejecutar(
            "DELETE FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()]
        )
        despues = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        ok = not despues
        if ok:
            try:
                invalidate_data_caches()
            except NameError:
                pass
        return ok
    except Exception as e:
        print(f"Error eliminando gasto: {e}")
        return False

def _calcular_sobres_uncached(mes: int, anio: int, user_id: int) -> dict:
    """Implementación interna — user_id obligatorio para cache correcta."""
    ingreso = obtener_ingreso(mes, anio)
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=500)
    
    sobres = {}
    ingreso_restante = ingreso
    
    for key, config in SOBRES_CONFIG.items():
        gastos_sobre = [g for g in gastos if g['sobre'] == key]
        gastado = sum(g['monto'] for g in gastos_sobre)
        
        # Presupuesto ideal según % del ingreso
        presupuesto_ideal = ingreso * config['pct']
        
        # Lógica de llenado en orden
        presupuesto_real = min(presupuesto_ideal, max(0, ingreso_restante))
        ingreso_restante -= presupuesto_ideal
        
        disponible = presupuesto_real - gastado
        pct_usado = (gastado / presupuesto_real * 100) if presupuesto_real > 0 else 0
        
        # Desglose por subcategoría
        por_subcat = {}
        for g in gastos_sobre:
            sub = g['subcategoria']
            if sub not in por_subcat:
                por_subcat[sub] = 0
            por_subcat[sub] += g['monto']
        
        # Separar fijos y variables (solo Supervivencia)
        fijos = sum(g['monto'] for g in gastos_sobre if g['es_fijo'])
        variables = gastado - fijos
        
        sobres[key] = {
            **config,
            'gastado': gastado,
            'presupuesto': presupuesto_real,
            'presupuesto_ideal': presupuesto_ideal,
            'disponible': disponible,
            'pct_usado': pct_usado,
            'gastos': gastos_sobre,
            'cantidad_gastos': len(gastos_sobre),
            'sobre_lleno': presupuesto_real >= presupuesto_ideal,
            'por_subcat': por_subcat,
            'fijos': fijos,
            'variables': variables,
        }
    
    # Calcular excedente
    excedente = ingreso - sum(
        SOBRES_CONFIG[k]['pct'] for k in SOBRES_CONFIG
    ) * ingreso
    
    return {
        'ingreso': ingreso,
        'mes': mes,
        'anio': anio,
        'total_gastado': sum(g['monto'] for g in gastos),
        'total_disponible': ingreso - sum(g['monto'] for g in gastos),
        'pct_global': (
            sum(g['monto'] for g in gastos) / ingreso * 100
        ) if ingreso > 0 else 0,
        'sobres': sobres,
        'excedente': excedente,
        'sin_ingreso': ingreso == 0,
    }

def obtener_tipos_bloque() -> list:
    """
    Obtiene los tipos únicos ya usados en BD
    más los defaults, sin duplicados.
    """
    defaults = ['Instituto', 'Programacion', 'Biblioteca', 'Personal']
    try:
        from app.tenant import uid
        rows = ejecutar("""
            SELECT DISTINCT tipo FROM bloques_fijos
            WHERE user_id = ? AND tipo IS NOT NULL
            ORDER BY tipo
        """, [uid()], fetchall=True) or []
        en_bd = [row["tipo"] for row in rows]
        return list(dict.fromkeys(defaults + en_bd))
    except Exception:
        return defaults

# ═════════════════════════════════════════════════════════════════
# CAPA DE COMPATIBILIDAD SQLITE / TURSO
# ═════════════════════════════════════════════════════════════════

import functools

@functools.lru_cache(maxsize=1)
def _get_turso_config():
    """
    Lee secrets UNA SOLA VEZ y cachea el resultado.
    lru_cache(maxsize=1) = singleton — nunca vuelve a leer secrets.
    """
    url   = None
    token = None
    try:
        import streamlit as st
        url   = st.secrets.get("TURSO_URL")
        token = st.secrets.get("TURSO_TOKEN")
    except Exception:
        pass
    if not url or not token:
        from dotenv import load_dotenv
        load_dotenv()
        url   = os.getenv("TURSO_URL")
        token = os.getenv("TURSO_TOKEN")
    return url, token


@functools.lru_cache(maxsize=1)
def usar_turso() -> bool:
    """Cacheado — evalúa UNA SOLA VEZ si Turso está disponible."""
    if libsql is None:
        return False
    url, token = _get_turso_config()
    return bool(url and token)


# Conexión global a Turso — se crea una vez, se reutiliza siempre
_turso_conn = None

def _get_turso_conn():
    """
    Retorna la conexión global a Turso.
    La crea solo la primera vez (patrón singleton).
    """
    global _turso_conn
    if _turso_conn is None:
        url, token = _get_turso_config()
        _turso_conn = libsql.connect(url, auth_token=token)
    return _turso_conn


def ejecutar(sql: str, params: list = None, fetchall: bool = False):
    """
    Wrapper unificado optimizado.
    - Turso: reutiliza conexión persistente (no abre una nueva cada vez)
    - SQLite: igual que antes
    """
    if usar_turso():
        try:
            conn   = _get_turso_conn()          # ← conexión ya abierta
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            if fetchall:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            # Si la conexión murió, resetear y reintentar una vez
            global _turso_conn
            _turso_conn = None
            conn   = _get_turso_conn()
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            if fetchall:
                cols = [d[0] for d in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or [])
            if fetchall:
                return [dict(r) for r in cursor.fetchall()]
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

import streamlit as st

@st.cache_data(ttl=30)
def ejecutar_cached(sql: str, params: tuple = ()) -> list:
    """
    SELECT cacheado — params como TUPLA, siempre retorna list.
    NUNCA usar para INSERT / UPDATE / DELETE.
    """
    return ejecutar(sql, list(params), fetchall=True) or []


# Cache por (mes, anio, user_id)
_calcular_sobres_cached = st.cache_data(ttl=30)(_calcular_sobres_uncached)

def calcular_sobres(mes: int, anio: int) -> dict:
    from app.tenant import uid
    return _calcular_sobres_cached(mes, anio, uid())

def invalidate_data_caches() -> None:
    """Limpia caches de lectura para que los guardados se vean al instante."""
    try:
        ejecutar_cached.clear()
    except Exception:
        pass
    try:
        _calcular_sobres_cached.clear()
    except Exception:
        pass


def ensure_database() -> None:
    """
    init_database() + migración multi-usuario, una vez por sesión.
    """
    try:
        if st.session_state.get("_db_ready"):
            return
        init_database()
        try:
            from app.multiuser import migrate_multiuser
            migrate_multiuser()
        except Exception as e:
            print(f"[ensure_database] migrate_multiuser: {e}")
        st.session_state["_db_ready"] = True
    except Exception:
        init_database()
        try:
            from app.multiuser import migrate_multiuser
            migrate_multiuser()
        except Exception as e:
            print(f"[ensure_database] migrate_multiuser: {e}")


def ensure_remote_schema():
    """
    Crea en Turso (o SQLite vía ejecutar) las tablas críticas
    que Finanzas y Auth necesitan, si aún no existen.
    """
    if not usar_turso():
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS ingreso_mensual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            monto_total REAL NOT NULL DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mes, anio)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gastos_sobres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            sobre TEXT NOT NULL,
            subcategoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL,
            es_fijo BOOLEAN DEFAULT 0,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'admin',
            activo BOOLEAN DEFAULT 1,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider TEXT PRIMARY KEY,
            token_json TEXT NOT NULL,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    for sql in statements:
        try:
            ejecutar(sql)
        except Exception as e:
            print(f"ensure_remote_schema: {e}")

    # También en SQLite local (por si ensure_database ya corrió antes del ALTER)
    try:
        ejecutar("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                provider TEXT PRIMARY KEY,
                token_json TEXT NOT NULL,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════
# USUARIOS / AUTH (hashes PBKDF2 — sin contraseñas en texto plano)
# ═════════════════════════════════════════════════════════════════

import hashlib
import secrets as _secrets


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if not salt:
        salt = _secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    )
    return digest.hex(), salt


def verificar_password(password: str, password_hash: str, salt: str) -> bool:
    candidato, _ = _hash_password(password, salt)
    return _secrets.compare_digest(candidato, password_hash)


def contar_usuarios() -> int:
    try:
        rows = ejecutar(
            "SELECT COUNT(*) AS n FROM usuarios WHERE activo = 1",
            fetchall=True,
        ) or []
        return int(rows[0]["n"]) if rows else 0
    except Exception:
        return 0


def crear_usuario(username: str, password: str, rol: str = "admin") -> tuple[bool, str]:
    username = (username or "").strip().lower()
    if len(username) < 3:
        return False, "El usuario debe tener al menos 3 caracteres"
    if len(password or "") < 6:
        return False, "La contraseña debe tener al menos 6 caracteres"
    if rol not in ("admin", "usuario"):
        rol = "usuario"
    existentes = ejecutar(
        "SELECT id FROM usuarios WHERE username = ?",
        [username], fetchall=True,
    ) or []
    if existentes:
        return False, "Ese nombre de usuario ya existe"
    password_hash, salt = _hash_password(password)
    try:
        ejecutar("""
            INSERT INTO usuarios (username, password_hash, salt, rol, activo)
            VALUES (?, ?, ?, ?, 1)
        """, [username, password_hash, salt, rol])
        return True, "Usuario creado"
    except Exception as e:
        return False, f"No se pudo crear: {e}"


def autenticar_usuario(username: str, password: str) -> dict | None:
    username = (username or "").strip().lower()
    rows = ejecutar("""
        SELECT id, username, password_hash, salt, rol, activo
        FROM usuarios
        WHERE username = ? AND activo = 1
    """, [username], fetchall=True) or []
    if not rows:
        return None
    u = rows[0]
    if not verificar_password(password, u["password_hash"], u["salt"]):
        return None
    return {
        "id": u["id"],
        "username": u["username"],
        "rol": u["rol"],
    }


def listar_usuarios() -> list:
    return ejecutar("""
        SELECT id, username, rol, activo, creado_en
        FROM usuarios
        ORDER BY id
    """, fetchall=True) or []


def migrar_local_a_turso():
    """
    Migra todos los datos de SQLite local a Turso.
    Ejecutar UNA SOLA VEZ después de configurar Turso.
    """
    url, token = _get_turso_config()
    if not url or not token:
        print("❌ TURSO_URL y TURSO_TOKEN no configurados")
        return False

    print(f"🔄 Conectando a Turso: {url}")

    # Leer datos locales
    conn_local = sqlite3.connect(DB_PATH, timeout=30)
    conn_local.row_factory = sqlite3.Row
    cursor_local = conn_local.cursor()

    # Conectar a Turso
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


# ═════════════════════════════════════════════════════════════════
# INICIALIZACIÓN AUTOMÁTICA
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_database()
    print("🚀 Base de datos lista para usar")