"""CRUD Sandbox — ideas, snippets y sesiones multi-dominio."""
from __future__ import annotations

import json

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import iso_ahora

DOMINIOS = [
    "Estudio",
    "Programacion",
    "Trabajo",
    "Familia",
    "Personal",
    "Ministerio",
    "Matrimonio",
    "Otros",
]

EMOJIS_DOMINIO = {
    "Estudio": "📚",
    "Programacion": "💻",
    "Trabajo": "💼",
    "Familia": "👨‍👩‍👧",
    "Personal": "👤",
    "Ministerio": "⛪",
    "Matrimonio": "💑",
    "Otros": "🌐",
}

CATEGORIAS_DEFAULT_POR_DOMINIO = {
    "Estudio": [
        "Teología",
        "Hermenéutica",
        "Idiomas",
        "Filosofía",
        "Historia",
        "Investigación",
    ],
    "Programacion": [
        "Script",
        "Web_App",
        "Mobile",
        "Data",
        "DevOps",
        "IA",
        "Automatización",
    ],
    "Trabajo": ["Proyecto", "Proceso", "Mejora", "Reunión", "Propuesta"],
    "Familia": [
        "Salida",
        "Vacaciones",
        "Actividad",
        "Conversación",
        "Celebración",
        "Apoyo",
    ],
    "Personal": ["Hábito", "Meta", "Reflexión", "Lectura", "Salud"],
    "Ministerio": [
        "Predicación",
        "Discipulado",
        "Servicio",
        "Oración",
        "Estudio Bíblico",
    ],
    "Matrimonio": [
        "Cita",
        "Conversación",
        "Plan",
        "Mejora",
        "Celebración",
        "Vacaciones",
    ],
    "Otros": ["General", "Idea", "Proyecto"],
}

ESTADOS_IDEA = [
    "Idea",
    "Investigando",
    "En_proceso",
    "Completado",
    "Pausado",
    "Abandonado",
]

COLORES_ESTADO = {
    "Idea": "#8b949e",
    "Investigando": "#58a6ff",
    "En_proceso": "#e3b341",
    "Completado": "#3fb950",
    "Pausado": "#f0883e",
    "Abandonado": "#f85149",
}

LENGUAJES = [
    "Python",
    "JavaScript",
    "TypeScript",
    "HTML_CSS",
    "SQL",
    "Bash",
    "Markdown",
    "Otro",
]

EMOJIS_LANG = {
    "Python": "🐍",
    "JavaScript": "⚡",
    "TypeScript": "📘",
    "HTML_CSS": "🎨",
    "SQL": "🗄️",
    "Bash": "💻",
    "Markdown": "📝",
    "Otro": "🔧",
}

TIPOS_SESION = [
    "Investigando",
    "Codificando",
    "Estudiando",
    "Planificando",
    "Leyendo",
    "Reflexionando",
    "Prototipando",
    "Documentando",
]

SYSTEM_MENTOR = """Eres un mentor versátil y sabio para un estudiante cristiano de teología
que también programa. Puedes orientar en:
- Programación (Python, web, scripts, IA)
- Estudio académico (teología, hermenéutica, investigación)
- Vida personal (hábitos, metas, disciplina)
- Familia y matrimonio (comunicación, planes, relaciones)
- Ministerio (predicación, discipulado, servicio)
- Trabajo y proyectos (planificación, ejecución)
Eres práctico, alentador y sabio. Máximo 150 palabras por respuesta."""


def parsear_lista(valor) -> list:
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    try:
        resultado = json.loads(valor)
        return [str(v) for v in resultado if v] if isinstance(resultado, list) else []
    except Exception:
        return [t.strip() for t in str(valor).split(",") if t.strip()]


def obtener_categorias_dominio(dominio: str) -> list:
    defaults = CATEGORIAS_DEFAULT_POR_DOMINIO.get(dominio, ["General"])
    try:
        rows = (
            ejecutar_cached(
                """
                SELECT DISTINCT categoria FROM sandbox_ideas
                WHERE dominio = ? AND categoria IS NOT NULL AND user_id = ?
                ORDER BY categoria
                """,
                (dominio, uid()),
            )
            or []
        )
        en_bd = [r["categoria"] for r in rows]
        return list(dict.fromkeys(defaults + en_bd))
    except Exception:
        return defaults


def obtener_ideas(estado=None, dominio=None, busqueda="") -> list:
    conditions = ["user_id = ?"]
    params: list = [uid()]
    if estado:
        conditions.append("estado = ?")
        params.append(estado)
    if dominio:
        conditions.append("dominio = ?")
        params.append(dominio)
    if busqueda:
        conditions.append(
            "(titulo LIKE ? OR descripcion LIKE ? OR etiquetas LIKE ?)"
        )
        params.extend([f"%{busqueda}%"] * 3)
    where = " AND ".join(conditions)
    return (
        ejecutar(
            f"""SELECT * FROM sandbox_ideas WHERE {where}
                ORDER BY prioridad DESC, motivacion DESC, creado_en DESC""",
            params,
            fetchall=True,
        )
        or []
    )


def obtener_idea(idea_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM sandbox_ideas WHERE id=? AND user_id=?",
        [int(idea_id), uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def guardar_idea(
    titulo: str,
    descripcion: str,
    dominio: str,
    categoria: str,
    etiquetas: list,
    prioridad: int,
    motivacion: int,
    notas: str = "",
    estado: str = "Idea",
) -> int:
    rid = ejecutar(
        """
        INSERT INTO sandbox_ideas
            (user_id, titulo, descripcion, dominio, categoria,
             etiquetas, estado, prioridad, motivacion, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            str(titulo),
            str(descripcion or ""),
            str(dominio),
            str(categoria or ""),
            json.dumps(list(etiquetas or [])),
            str(estado or "Idea"),
            int(prioridad),
            int(motivacion),
            str(notas or ""),
        ],
    )
    invalidate_data_caches()
    return rid


def actualizar_idea(
    idea_id: int,
    titulo: str,
    descripcion: str,
    dominio: str,
    categoria: str,
    etiquetas: list,
    estado: str,
    prioridad: int,
    motivacion: int,
    notas: str,
) -> None:
    ejecutar(
        """
        UPDATE sandbox_ideas
        SET titulo=?, descripcion=?, dominio=?, categoria=?,
            etiquetas=?, estado=?, prioridad=?,
            motivacion=?, notas=?, actualizado_en=?
        WHERE id=? AND user_id=?
        """,
        [
            str(titulo),
            str(descripcion or ""),
            str(dominio),
            str(categoria or ""),
            json.dumps(list(etiquetas or [])),
            str(estado),
            int(prioridad),
            int(motivacion),
            str(notas or ""),
            iso_ahora(),
            int(idea_id),
            uid(),
        ],
    )
    invalidate_data_caches()


def eliminar_idea(idea_id: int) -> None:
    ejecutar(
        "DELETE FROM sandbox_ideas WHERE id=? AND user_id=?",
        [int(idea_id), uid()],
    )
    invalidate_data_caches()


def stats_sandbox() -> dict:
    ideas = obtener_ideas()
    snippets = obtener_snippets()
    activas = len(
        [i for i in ideas if i.get("estado") not in ("Completado", "Abandonado")]
    )
    completadas = len([i for i in ideas if i.get("estado") == "Completado"])
    por_dom: dict = {}
    for i in ideas:
        d = i.get("dominio") or "Otros"
        por_dom[d] = por_dom.get(d, 0) + 1
    return {
        "activas": activas,
        "completadas": completadas,
        "snippets": len(snippets),
        "por_dominio": por_dom,
    }


def obtener_snippets(lenguaje=None, dominio=None, busqueda="") -> list:
    conditions = ["user_id = ?"]
    params: list = [uid()]
    if lenguaje:
        conditions.append("lenguaje = ?")
        params.append(lenguaje)
    if dominio:
        conditions.append("dominio = ?")
        params.append(dominio)
    if busqueda:
        conditions.append("(titulo LIKE ? OR descripcion LIKE ? OR tags LIKE ?)")
        params.extend([f"%{busqueda}%"] * 3)
    where = " AND ".join(conditions)
    return (
        ejecutar(
            f"""SELECT * FROM sandbox_snippets WHERE {where}
                ORDER BY veces_usado DESC, creado_en DESC""",
            params,
            fetchall=True,
        )
        or []
    )


def obtener_snippet(snip_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM sandbox_snippets WHERE id=? AND user_id=?",
        [int(snip_id), uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def guardar_snippet(
    titulo: str,
    descripcion: str,
    lenguaje: str,
    codigo: str,
    tags: list,
    dominio: str,
) -> int:
    rid = ejecutar(
        """
        INSERT INTO sandbox_snippets
            (user_id, titulo, descripcion, lenguaje, codigo, tags, dominio)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            str(titulo),
            str(descripcion or ""),
            str(lenguaje),
            str(codigo),
            json.dumps(list(tags or [])),
            str(dominio),
        ],
    )
    invalidate_data_caches()
    return rid


def actualizar_snippet(
    snip_id: int,
    titulo: str,
    descripcion: str,
    lenguaje: str,
    codigo: str,
    tags: list,
    dominio: str,
) -> None:
    ejecutar(
        """
        UPDATE sandbox_snippets
        SET titulo=?, descripcion=?, lenguaje=?,
            codigo=?, tags=?, dominio=?, actualizado_en=?
        WHERE id=? AND user_id=?
        """,
        [
            str(titulo),
            str(descripcion or ""),
            str(lenguaje),
            str(codigo),
            json.dumps(list(tags or [])),
            str(dominio),
            iso_ahora(),
            int(snip_id),
            uid(),
        ],
    )
    invalidate_data_caches()


def eliminar_snippet(snip_id: int) -> None:
    ejecutar(
        "DELETE FROM sandbox_snippets WHERE id=? AND user_id=?",
        [int(snip_id), uid()],
    )
    invalidate_data_caches()


def incrementar_uso(snip_id: int) -> None:
    ejecutar(
        """
        UPDATE sandbox_snippets
        SET veces_usado = veces_usado + 1
        WHERE id=? AND user_id=?
        """,
        [int(snip_id), uid()],
    )
    invalidate_data_caches()


def guardar_sesion(
    fecha,
    duracion: int,
    tipo: str,
    dominio: str,
    proyecto_id,
    descripcion: str,
    codigo: str,
    satisfaccion: int,
) -> int:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    rid = ejecutar(
        """
        INSERT INTO sandbox_sesiones
            (user_id, fecha, duracion_minutos, tipo_actividad, dominio,
             proyecto_id, descripcion, codigo_producido, satisfaccion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid(),
            fecha_iso,
            int(duracion),
            str(tipo),
            str(dominio),
            int(proyecto_id) if proyecto_id not in (None, "", 0, "0") else None,
            str(descripcion or ""),
            str(codigo or "") or None,
            int(satisfaccion),
        ],
    )
    invalidate_data_caches()
    return rid


def obtener_sesiones_recientes(limite: int = 10) -> list:
    return (
        ejecutar_cached(
            """
            SELECT ss.*, si.titulo as proyecto_titulo
            FROM sandbox_sesiones ss
            LEFT JOIN sandbox_ideas si
              ON ss.proyecto_id = si.id AND si.user_id = ss.user_id
            WHERE ss.user_id = ?
            ORDER BY ss.fecha DESC, ss.creado_en DESC
            LIMIT ?
            """,
            (uid(), int(limite)),
        )
        or []
    )
