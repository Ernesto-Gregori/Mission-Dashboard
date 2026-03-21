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
            
            -- Energía durante el día (autoevaluación)
            energia_manana INTEGER CHECK(energia_manana BETWEEN 1 AND 10),
            energia_tarde INTEGER CHECK(energia_tarde BETWEEN 1 AND 10),
            energia_noche INTEGER CHECK(energia_noche BETWEEN 1 AND 10),
            
            -- Ejercicio (principalmente calistenia miércoles)
            hizo_ejercicio BOOLEAN DEFAULT 0,
            tipo_ejercicio TEXT,  -- 'Calistenia', 'Caminata', 'Otro'
            duracion_minutos INTEGER,
            intensidad INTEGER CHECK(intensidad BETWEEN 1 AND 10),  -- 1=suave, 10=máxima
            notas_ejercicio TEXT,
            
            -- Correlación con productividad (para análisis posterior)
            productividad_percibida INTEGER CHECK(productividad_percibida BETWEEN 1 AND 10),
            
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_salud_fecha ON registros_salud(fecha DESC)")
    
    # ═════════════════════════════════════════════════════════
    # TABLA: CORRELACION_ANALISIS (Resultados de IA)
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS correlacion_analisis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_analisis DATE DEFAULT CURRENT_DATE,
            tipo_correlacion TEXT,  -- 'ejercicio_productividad', 'sueno_energia', etc.
            descripcion TEXT,
            coeficiente_correlacion REAL,  -- -1 a 1 si aplica
            recomendacion TEXT,
            generado_por TEXT DEFAULT 'IA'  -- 'IA' o 'Manual'
        )
    """)

        # ═════════════════════════════════════════════════════════
    # TABLA: SANDBOX - Ideas, snippets y recursos técnicos
    # ═════════════════════════════════════════════════════════
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            categoria TEXT CHECK(categoria IN (
                'Script_Automatizacion', 'Web_App', 'Mobile', 'Data_Science', 
                'DevOps', 'Seguridad', 'Otro'
            )) DEFAULT 'Otro',
            tecnologias TEXT,  -- JSON: ["Python", "Streamlit", "SQLite"]
            complejidad INTEGER CHECK(complejidad BETWEEN 1 AND 5),  -- 1=fácil, 5=experto
            estado TEXT CHECK(estado IN (
                'Idea', 'Investigando', 'Prototipo', 'Pausado', 'Completado', 'Abandonado'
            )) DEFAULT 'Idea',
            motivacion INTEGER CHECK(motivacion BETWEEN 1 AND 10),  -- ganas de hacerlo
            notas_tecnicas TEXT,
            enlaces_referencia TEXT,  -- JSON array de URLs
            tiempo_estimado_horas INTEGER,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            lenguaje TEXT CHECK(lenguaje IN (
                'Python', 'JavaScript', 'HTML_CSS', 'SQL', 'Bash', 'Markdown', 'Otro'
            )),
            codigo TEXT NOT NULL,
            descripcion TEXT,
            tags TEXT,  -- JSON: ["pandas", "streamlit", "sqlite"]
            fuente_url TEXT,  -- de dónde lo sacaste
            proyecto_relacionado_id INTEGER,  -- FK a sandbox_ideas opcional
            veces_usado INTEGER DEFAULT 0,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proyecto_relacionado_id) REFERENCES sandbox_ideas(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            hora_inicio TIME,
            hora_fin TIME,
            duracion_minutos INTEGER,
            tipo_actividad TEXT CHECK(tipo_actividad IN (
                'Investigando', 'Codificando', 'Depurando', 'Aprendiendo', 'Documentando'
            )),
            proyecto_id INTEGER,  -- FK opcional
            descripcion TEXT,  -- qué hiciste, logros, bloqueos
            codigo_producido TEXT,  -- snippet resultado de la sesión
            satisfaccion INTEGER CHECK(satisfaccion BETWEEN 1 AND 10),
            FOREIGN KEY (proyecto_id) REFERENCES sandbox_ideas(id)
        )
    """)
    
    # Índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sandbox_ideas_estado ON sandbox_ideas(estado)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sandbox_snippets_lenguaje ON sandbox_snippets(lenguaje)")
    
    # Datos de ejemplo
    ideas_ejemplo = [
        ("Organizador de 500 libros en Linux", "Script para escanear y catalogar PDFs automáticamente", "Script_Automatizacion", '["Python", "OS", "SQLite"]', 3, "Investigando", 8),
        ("App de citas matrimoniales", "Recordatorio inteligente de aniversarios y preferencias", "Web_App", '["Streamlit", "SQLite"]', 2, "Idea", 9),
        ("Analizador de devocionales", "NLP para encontrar temas recurrentes en mis notas teológicas", "Data_Science", '["Python", "spaCy", "pandas"]', 4, "Idea", 6),
    ]
    
    for titulo, desc, cat, tech, comp, estado, motiv in ideas_ejemplo:
        cursor.execute("""
            INSERT OR IGNORE INTO sandbox_ideas (titulo, descripcion, categoria, tecnologias, complejidad, estado, motivacion)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titulo, desc, cat, tech, comp, estado, motiv))
    
    snippets_ejemplo = [
        ("Leer PDFs en carpeta recursiva", "Python", 
         "import os\nfrom pathlib import Path\n\ndef find_pdfs(root_dir):\n    return list(Path(root_dir).rglob('*.pdf'))",
         "Busca todos los PDFs recursivamente", '["os", "pathlib"]', None, 0),
        ("Streamlit dark mode CSS", "HTML_CSS",
         "st.markdown('<style>...dark mode...</style>', unsafe_allow_html=True)",
         "Template base para tema oscuro", '["streamlit", "css"]', None, 0),
    ]
    
    for titulo, lang, codigo, desc, tags, proj, usado in snippets_ejemplo:
        cursor.execute("""
            INSERT OR IGNORE INTO sandbox_snippets (titulo, lenguaje, codigo, descripcion, tags, proyecto_relacionado_id, veces_usado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titulo, lang, codigo, desc, tags, proj, usado))

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
    
    # Índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_citas_fecha ON matrimonio_citas(fecha)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notas_categoria ON matrimonio_notas(categoria)")
    
    # Datos de ejemplo
    citas_ejemplo = [
        ("2026-03-21", "21:00", "Cena_Romantica", "Cena de viernes tradicional", 
         "Restaurante italiano favorito", 800, "Confirmada", "Reserva hecha, llevar flores"),
        ("2026-04-15", None, "Aniversario", "Aniversario de bodas", 
         "Sorpresa", 2500, "Planeando", "Investigar destino fin de semana"),
    ]
    
    for fecha, hora, tipo, titulo, lugar, presup, estado, prep in citas_ejemplo:
        cursor.execute("""
            INSERT OR IGNORE INTO matrimonio_citas 
            (fecha, hora, tipo_cita, titulo, lugar, presupuesto_estimado, estado_planificacion, notas_preparacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha, hora, tipo, titulo, lugar, presup, estado, prep))
    
    notas_ejemplo = [
        ("Preferencias_Esposa", "Le encanta el chocolate amargo, no el dulce", 
         "Conversación cafetería", "2026-02-14", 8),
        ("Ideas_Regalo", "Libro de teología sistemática de Frame", 
         "Mencionó en clase", "2026-03-10", 9),
        ("Frases_Recordar", "\"Me siento más conectada cuando caminamos juntos\"", 
         "Después de cena", "2026-03-05", 10),
    ]
    
    for cat, contenido, contexto, fecha, urg in notas_ejemplo:
        cursor.execute("""
            INSERT OR IGNORE INTO matrimonio_notas 
            (categoria, contenido, contexto, fecha_mencion, urgencia)
            VALUES (?, ?, ?, ?, ?)
        """, (cat, contenido, contexto, fecha, urg))
    
    # ═════════════════════════════════════════════════════════
    # TABLA: HABITOS_DIARIOS
    # ═════════════════════════════════════════════════════════
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habitos_diarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            habito TEXT NOT NULL CHECK(habito IN (
                'devocional', 'codigo', 'lectura', 'calistenia'
            )),
            completado BOOLEAN DEFAULT 0,
            hora_completado TIME,
            UNIQUE(fecha, habito)
        )
    """)


    init_sobres(cursor)
    conn.commit()
    conn.close()
    # print(f"✅ Base de datos inicializada en: {DB_PATH}")


# ═════════════════════════════════════════════════════════════════
# FUNCIONES CRUD PARA GASTOS
# ═════════════════════════════════════════════════════════════════

def guardar_ingreso(mes: int, anio: int, monto: float, notas: str = "") -> bool:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO ingreso_mensual (mes, anio, monto_total, notas)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(mes, anio)
            DO UPDATE SET monto_total = ?, notas = ?
        """, (mes, anio, monto, notas, monto, notas))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error guardando ingreso: {e}")
        return False
    finally:
        conn.close()

def obtener_ingreso(mes: int, anio: int) -> float:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT monto_total FROM ingreso_mensual
        WHERE mes = ? AND anio = ?
    """, (mes, anio))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def agregar_gasto_sobre(fecha, sobre: str, subcategoria: str,
                        descripcion: str, monto: float,
                        es_fijo: bool = False, notas: str = "") -> int:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO gastos_sobres
            (fecha, sobre, subcategoria, descripcion, monto, es_fijo, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(fecha), sobre, subcategoria, descripcion, monto, es_fijo, notas))
    gasto_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return gasto_id

def obtener_gastos_sobre(mes=None, anio=None, sobre=None, limite=100) -> list:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM gastos_sobres WHERE 1=1"
    params = []
    
    if mes and anio:
        query += """ AND strftime('%m', fecha) = ? 
                    AND strftime('%Y', fecha) = ?"""
        params.extend([f"{mes:02d}", str(anio)])
    if sobre:
        query += " AND sobre = ?"
        params.append(sobre)
    
    query += " ORDER BY fecha DESC, creado_en DESC LIMIT ?"
    params.append(limite)
    
    cursor.execute(query, params)
    gastos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return gastos

def actualizar_gasto_sobre(gasto_id: int, **kwargs) -> bool:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    try:
        campos_permitidos = {
            'fecha', 'sobre', 'subcategoria',
            'descripcion', 'monto', 'es_fijo', 'notas'
        }
        campos = {
            k: (str(v) if k == 'fecha' else v)
            for k, v in kwargs.items()
            if k in campos_permitidos and v is not None
        }
        if not campos:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in campos)
        cursor.execute(
            f"UPDATE gastos_sobres SET {set_clause} WHERE id = ?",
            list(campos.values()) + [gasto_id]
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def eliminar_gasto_sobre(gasto_id: int) -> bool:
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM gastos_sobres WHERE id = ?", (gasto_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def calcular_sobres(mes: int, anio: int) -> dict:
    """
    Calcula el estado de los 3 sobres.
    Lógica: llenar en orden según ingreso disponible.
    """
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


# ═════════════════════════════════════════════════════════════════
# INICIALIZACIÓN AUTOMÁTICA
# ═════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_database()
    print("🚀 Base de datos lista para usar")