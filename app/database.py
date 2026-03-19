"""
database.py - Capa de acceso a datos para Mission Dashboard
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path
import json

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


def init_database():
    """
    Inicializa la base de datos con todas las tablas necesarias.
    Ejecutar UNA VEZ al inicio de la aplicación.
    """
    # Crear carpeta data si no existe
    DB_PATH.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ═════════════════════════════════════════════════════════
    # TABLA: GASTOS (Finanzas)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            categoria TEXT NOT NULL CHECK(categoria IN (
                'Hogar', 'Instituto', 'Programacion', 'Citas_Esposa'
            )),
            descripcion TEXT NOT NULL,
            monto REAL NOT NULL CHECK(monto > 0),
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Índice para búsquedas rápidas por fecha
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gastos_fecha 
        ON gastos(fecha DESC)
    """)
    
    # ═════════════════════════════════════════════════════════
    # TABLA: PRESUPUESTOS MENSUALES
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presupuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
            anio INTEGER NOT NULL,
            categoria TEXT NOT NULL CHECK(categoria IN (
                'Hogar', 'Instituto', 'Programacion', 'Citas_Esposa'
            )),
            limite REAL NOT NULL CHECK(limite > 0),
            UNIQUE(mes, anio, categoria)
        )
    """)
    
    # Insertar presupuestos de ejemplo para marzo 2026
    # (Puedes modificar estos valores)
    # Insertar presupuestos de ejemplo para el mes actual si no existen
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    presupuestos_ejemplo = [
        (mes_actual, anio_actual, 'Hogar', 8000),
        (mes_actual, anio_actual, 'Instituto', 3000),
        (mes_actual, anio_actual, 'Programacion', 2000),
        (mes_actual, anio_actual, 'Citas_Esposa', 2500),
    ]
    
    # DEBUG: Verificar qué se está insertando
    # print(f"Insertando presupuestos para {mes_actual}/{anio_actual}")
    
    for mes, anio, cat, limite in presupuestos_ejemplo:
        cursor.execute("""
            INSERT OR IGNORE INTO presupuestos (mes, anio, categoria, limite)
            VALUES (?, ?, ?, ?)
        """, (mes, anio, cat, limite))
        # print(f"  → {cat}: ${limite}")
    
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
            tipo TEXT NOT NULL CHECK(tipo IN ('Instituto', 'Programacion', 'Biblioteca', 'Personal')),
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
    # LIBROS DE EJEMPLO (NUEVA ESTRUCTURA)
    # ═════════════════════════════════════════════════════════
    
    libros_ejemplo = [
        {
            'titulo': 'Python Crash Course',
            'autor': 'Eric Matthes',
            'categoria_principal': 'Programacion',
            'descripcion': 'Libro práctico para aprender Python desde cero con proyectos reales.',
            'total_paginas': 544,
            'estado': 'leyendo',
            'pagina_actual': 120,
            'fuente_metadatos': 'IA',
            'confianza_ia': 8,
            'formato': 'PDF',
            'nombre_archivo': 'python_crash_course.pdf'
        },
        {
            'titulo': 'Systematic Theology',
            'autor': 'Wayne A. Grudem',
            'categoria_principal': 'Teologia',
            'descripcion': 'Obra magistral de teología sistemática desde perspectiva evangélica.',
            'total_paginas': 1291,
            'estado': 'catalogado',
            'pagina_actual': 0,
            'fuente_metadatos': 'IA',
            'confianza_ia': 9,
            'formato': 'PDF',
            'nombre_archivo': 'grudem_systematic.pdf'
        },
        {
            'titulo': 'The Meaning of Marriage',
            'autor': 'Timothy Keller',
            'categoria_principal': 'Matrimonio',
            'descripcion': 'Visión bíblica del matrimonio para parejas modernas.',
            'total_paginas': 352,
            'estado': 'por_procesar',
            'pagina_actual': 0,
            'fuente_metadatos': 'Manual',
            'confianza_ia': 10,
            'formato': 'EPUB',
            'nombre_archivo': 'keller_marriage.epub'
        },
        {
            'titulo': 'Clean Code',
            'autor': 'Robert C. Martin',
            'categoria_principal': 'Programacion',
            'descripcion': 'Guía de mejores prácticas para código limpio y mantenible.',
            'total_paginas': 464,
            'estado': 'completado',
            'pagina_actual': 464,
            'fuente_metadatos': 'IA',
            'confianza_ia': 8,
            'formato': 'PDF',
            'nombre_archivo': 'clean_code.pdf'
        },
        {
            'titulo': 'Institutes of the Christian Religion',
            'autor': 'John Calvin',
            'categoria_principal': 'Teologia',
            'descripcion': 'Obra fundamental de la Reforma protestante.',
            'total_paginas': 1800,
            'estado': 'por_procesar',
            'pagina_actual': 0,
            'fuente_metadatos': 'Manual',
            'confianza_ia': 10,
            'formato': 'PDF',
            'nombre_archivo': 'calvin_institutes.pdf'
        }
    ]
    
    for libro in libros_ejemplo:
        # Verificar si ya existe por título
        cursor.execute("SELECT id FROM libros WHERE titulo = ?", (libro['titulo'],))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO libros (
                    titulo, autor, categoria_principal, descripcion, total_paginas,
                    pagina_actual, estado, fuente_metadatos, confianza_ia,
                    formato, nombre_archivo, subcategorias, temas_clave, autores_adicionales
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                libro['titulo'], libro['autor'], libro['categoria_principal'],
                libro['descripcion'], libro['total_paginas'], libro['pagina_actual'],
                libro['estado'], libro['fuente_metadatos'], libro['confianza_ia'],
                libro['formato'], libro['nombre_archivo'],
                json.dumps([]), json.dumps([]), json.dumps([])
            ))

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

    conn.commit()
    conn.close()
    # print(f"✅ Base de datos inicializada en: {DB_PATH}")


# ═════════════════════════════════════════════════════════════════
# FUNCIONES CRUD PARA GASTOS
# ═════════════════════════════════════════════════════════════════

def agregar_gasto(fecha: date, categoria: str, descripcion: str, 
                  monto: float, notas: str = "") -> int:
    """
    CREATE: Agrega un nuevo gasto.
    Retorna el ID del registro creado.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO gastos (fecha, categoria, descripcion, monto, notas)
        VALUES (?, ?, ?, ?, ?)
    """, (fecha, categoria, descripcion, monto, notas))
    
    nuevo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return nuevo_id


def obtener_gastos(mes: int = None, anio: int = None, 
                   categoria: str = None, limite: int = 100) -> list:
    """
    READ: Obtiene gastos con filtros opcionales.
    Retorna lista de diccionarios.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Para acceder por nombre de columna
    cursor = conn.cursor()
    
    query = "SELECT * FROM gastos WHERE 1=1"
    params = []
    
    if mes and anio:
        query += " AND strftime('%m', fecha) = ? AND strftime('%Y', fecha) = ?"
        params.extend([f"{mes:02d}", str(anio)])
    
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    
    query += " ORDER BY fecha DESC LIMIT ?"
    params.append(limite)
    
    cursor.execute(query, params)
    filas = cursor.fetchall()
    
    # Convertir a lista de diccionarios
    resultado = [dict(fila) for fila in filas]
    
    conn.close()
    return resultado


def actualizar_gasto(gasto_id: int, **campos) -> bool:
    """
    UPDATE: Modifica un gasto existente.
    Campos permitidos: fecha, categoria, descripcion, monto, notas
    """
    campos_permitidos = {'fecha', 'categoria', 'descripcion', 'monto', 'notas'}
    campos_actualizar = {k: v for k, v in campos.items() if k in campos_permitidos}
    
    if not campos_actualizar:
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    set_clause = ", ".join(f"{k} = ?" for k in campos_actualizar.keys())
    valores = list(campos_actualizar.values()) + [gasto_id]
    
    cursor.execute(f"""
        UPDATE gastos 
        SET {set_clause}
        WHERE id = ?
    """, valores)
    
    filas_afectadas = cursor.rowcount
    conn.commit()
    conn.close()
    
    return filas_afectadas > 0


def eliminar_gasto(gasto_id: int) -> bool:
    """
    DELETE: Elimina un gasto permanentemente.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
    
    filas_afectadas = cursor.rowcount
    conn.commit()
    conn.close()
    
    return filas_afectadas > 0


# ═════════════════════════════════════════════════════════════════
# FUNCIONES DE REPORTES
# ═════════════════════════════════════════════════════════════════

def resumen_mensual(mes: int, anio: int) -> dict:
    """
    Genera resumen de gastos vs. presupuesto para un mes específico.
    CORREGIDO: Maneja categorías sin gastos registrados.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # PRIMERO: Obtener todos los presupuestos del mes/año
    cursor.execute("""
        SELECT categoria, limite 
        FROM presupuestos 
        WHERE mes = ? AND anio = ?
    """, (mes, anio))
    
    presupuestos_raw = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Si no hay presupuestos para este mes/año, crear estructura vacía
    if not presupuestos_raw:
        # Intentar usar presupuestos de ejemplo o crear vacío
        categorias_default = ['Hogar', 'Instituto', 'Programacion', 'Citas_Esposa']
        presupuestos_raw = {cat: 0 for cat in categorias_default}
    
    # SEGUNDO: Obtener gastos reales del mes
    cursor.execute("""
        SELECT 
            categoria,
            COALESCE(SUM(monto), 0) as gastado
        FROM gastos
        WHERE strftime('%m', fecha) = ? AND strftime('%Y', fecha) = ?
        GROUP BY categoria
    """, (f"{mes:02d}", str(anio)))
    
    gastos_raw = {row[0]: row[1] for row in cursor.fetchall()}
    
    # TERCERO: Combinar datos (categoría SIEMPRE viene del presupuesto)
    categorias = []
    total_gastado = 0
    total_presupuesto = 0
    
    for categoria, limite in presupuestos_raw.items():
        gastado = gastos_raw.get(categoria, 0.0)  # 0 si no hay gastos
        disponible = limite - gastado
        porcentaje = (gastado / limite * 100) if limite > 0 else 0
        
        categorias.append({
            'categoria': categoria,  # ← SIEMPRE existe, nunca None
            'gastado': gastado,
            'limite': limite,
            'disponible': disponible,
            'porcentaje_usado': round(porcentaje, 1)
        })
        
        total_gastado += gastado
        total_presupuesto += limite
    
    conn.close()
    
    return {
        'mes': mes,
        'anio': anio,
        'categorias': categorias,
        'total_gastado': total_gastado,
        'total_presupuesto': total_presupuesto,
        'total_disponible': total_presupuesto - total_gastado,
        'porcentaje_global': round(total_gastado / total_presupuesto * 100, 1) if total_presupuesto > 0 else 0
    }


# ═════════════════════════════════════════════════════════════════
# INICIALIZACIÓN AUTOMÁTICA
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_database()
    print("🚀 Base de datos lista para usar")