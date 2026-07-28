"""CRUD Biblioteca — libros, progreso y resaltados."""
from __future__ import annotations

import json

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import iso_ahora

CATEGORIAS = [
    "Teologia",
    "Programacion",
    "Matrimonio",
    "Filosofia",
    "Liderazgo",
    "Historia",
    "Otros",
]

ESTADOS_LIBRO = [
    "por_procesar",
    "catalogado",
    "leyendo",
    "pausado",
    "completado",
    "abandonado",
]

COLORES_RESALTADO = ["Amarillo", "Verde", "Azul", "Rosa", "Morado"]


def parsear_lista(valor) -> list:
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    try:
        resultado = json.loads(valor)
        return [str(v) for v in resultado if v] if isinstance(resultado, list) else []
    except Exception:
        return []


def agregar_libro_por_procesar(
    nombre_archivo: str,
    ruta: str,
    tamano: float,
    formato: str,
    hash_archivo: str,
) -> int | None:
    titulo_temp = (
        nombre_archivo.replace(f".{formato.lower()}", "").replace("_", " ").title()
    )
    try:
        return ejecutar(
            """
            INSERT INTO libros
                (user_id, titulo, nombre_archivo, ruta_archivo,
                 tamano_mb, formato, hash_archivo, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'por_procesar')
            """,
            [
                uid(),
                titulo_temp,
                nombre_archivo,
                ruta,
                float(tamano),
                formato,
                hash_archivo,
            ],
        )
    except Exception:
        return None


def crear_libro_manual(
    titulo: str,
    autor: str = "",
    categoria: str = "Otros",
    total_paginas: int = 0,
    descripcion: str = "",
    isbn: str = "",
    editorial: str = "",
    anio: int = 0,
    estado: str = "catalogado",
) -> int | None:
    titulo = (titulo or "").strip()
    if not titulo:
        return None
    if categoria not in CATEGORIAS:
        categoria = "Otros"
    if estado not in ESTADOS_LIBRO:
        estado = "catalogado"
    try:
        lid = ejecutar(
            """
            INSERT INTO libros
                (user_id, titulo, autor, isbn, editorial, anio_publicacion,
                 categoria_principal, total_paginas, descripcion,
                 estado, fuente_metadatos, revisado_manual, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Manual', 1, ?)
            """,
            [
                uid(),
                titulo,
                str(autor or ""),
                str(isbn or ""),
                str(editorial or ""),
                int(anio or 0),
                categoria,
                int(total_paginas or 0),
                str(descripcion or ""),
                estado,
                iso_ahora(),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return lid
    except Exception:
        return None


def obtener_libro(libro_id: int) -> dict | None:
    rows = ejecutar(
        "SELECT * FROM libros WHERE id = ? AND user_id = ?",
        [libro_id, uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def obtener_libros_por_estado(
    estado=None,
    categoria=None,
    color=None,  # legacy Streamlit filter (columna inexistente; ignorado)
    busqueda="",
    pagina=1,
    por_pagina=10,
) -> tuple:
    _ = color
    conditions = ["user_id = ?"]
    params: list = [uid()]

    if estado:
        conditions.append("estado = ?")
        params.append(estado)
    if categoria:
        conditions.append("categoria_principal = ?")
        params.append(categoria)
    if busqueda:
        termino = f"%{busqueda}%"
        conditions.append(
            """(
            titulo        LIKE ? OR
            autor         LIKE ? OR
            descripcion   LIKE ? OR
            temas_clave   LIKE ? OR
            subcategorias LIKE ?
        )"""
        )
        params.extend([termino] * 5)

    where = " AND ".join(conditions)
    total_rows = ejecutar(
        f"SELECT COUNT(*) as total FROM libros WHERE {where}",
        params,
        fetchall=True,
    )
    total = total_rows[0]["total"] if total_rows else 0
    offset = max(0, (int(pagina) - 1) * int(por_pagina))
    libros = (
        ejecutar(
            f"""SELECT * FROM libros WHERE {where}
                ORDER BY actualizado_en DESC, creado_en DESC
                LIMIT ? OFFSET ?""",
            params + [int(por_pagina), offset],
            fetchall=True,
        )
        or []
    )
    return libros, total


def guardar_metadatos_ia(libro_id: int, metadatos: dict) -> bool:
    try:
        data = dict(metadatos)
        for campo in ["subcategorias", "temas_clave", "autores_adicionales"]:
            valor = data.get(campo)
            if isinstance(valor, list):
                data[campo] = json.dumps(valor, ensure_ascii=False)
            elif not isinstance(valor, str):
                data[campo] = json.dumps([])

        campos = {
            "titulo": str(data.get("titulo") or ""),
            "autor": str(data.get("autor") or ""),
            "isbn": str(data.get("isbn") or ""),
            "editorial": str(data.get("editorial") or ""),
            "anio_publicacion": int(data.get("anio_publicacion") or 0),
            "categoria_principal": str(data.get("categoria_principal") or "Otros"),
            "total_paginas": int(data.get("total_paginas") or 0),
            "descripcion": str(data.get("descripcion") or ""),
            "subcategorias": data.get("subcategorias", "[]"),
            "temas_clave": data.get("temas_clave", "[]"),
            "autores_adicionales": data.get("autores_adicionales", "[]"),
            "notas_bibliotecaria": str(data.get("notas_bibliotecaria") or ""),
            "fuente_metadatos": str(data.get("fuente_metadatos") or "IA"),
            "confianza_ia": int(data.get("confianza_ia") or 5),
            "estado": "catalogado",
            "revisado_manual": 1,
            "actualizado_en": iso_ahora(),
        }
        set_clause = ", ".join(f"{k} = ?" for k in campos)
        ejecutar(
            f"UPDATE libros SET {set_clause} WHERE id = ? AND user_id = ?",
            list(campos.values()) + [int(libro_id), uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def actualizar_libro(
    libro_id: int,
    *,
    titulo: str,
    autor: str = "",
    categoria: str = "Otros",
    total_paginas: int = 0,
    pagina_actual: int | None = None,
    descripcion: str = "",
    isbn: str = "",
    editorial: str = "",
    estado: str | None = None,
) -> bool:
    if not obtener_libro(libro_id):
        return False
    if categoria not in CATEGORIAS:
        categoria = "Otros"
    campos = {
        "titulo": str(titulo or "").strip() or "Sin título",
        "autor": str(autor or ""),
        "categoria_principal": categoria,
        "total_paginas": int(total_paginas or 0),
        "descripcion": str(descripcion or ""),
        "isbn": str(isbn or ""),
        "editorial": str(editorial or ""),
        "actualizado_en": iso_ahora(),
    }
    if pagina_actual is not None:
        campos["pagina_actual"] = int(pagina_actual)
    if estado and estado in ESTADOS_LIBRO:
        campos["estado"] = estado
    set_clause = ", ".join(f"{k} = ?" for k in campos)
    try:
        ejecutar(
            f"UPDATE libros SET {set_clause} WHERE id = ? AND user_id = ?",
            list(campos.values()) + [int(libro_id), uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def actualizar_progreso(
    libro_id: int,
    pagina_actual: int,
    estado: str | None = None,
) -> bool:
    try:
        if estado and estado in ESTADOS_LIBRO:
            ejecutar(
                """
                UPDATE libros
                SET pagina_actual = ?, estado = ?, actualizado_en = ?
                WHERE id = ? AND user_id = ?
                """,
                [int(pagina_actual), estado, iso_ahora(), int(libro_id), uid()],
            )
        else:
            ejecutar(
                """
                UPDATE libros
                SET pagina_actual = ?, actualizado_en = ?
                WHERE id = ? AND user_id = ?
                """,
                [int(pagina_actual), iso_ahora(), int(libro_id), uid()],
            )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def agregar_resaltado(
    libro_id: int,
    pagina: int,
    texto_resaltado: str,
    color_etiqueta: str,
    nota_personal: str = "",
    texto_contexto: str = "",
) -> int | None:
    own = (
        ejecutar(
            "SELECT id FROM libros WHERE id = ? AND user_id = ?",
            [int(libro_id), uid()],
            fetchall=True,
        )
        or []
    )
    if not own:
        return None
    if color_etiqueta not in COLORES_RESALTADO:
        color_etiqueta = "Amarillo"
    try:
        rid = ejecutar(
            """
            INSERT INTO resaltados
                (user_id, libro_id, pagina, texto_resaltado,
                 color_etiqueta, nota_personal, texto_contexto)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                uid(),
                int(libro_id),
                int(pagina),
                str(texto_resaltado),
                str(color_etiqueta),
                str(nota_personal or ""),
                str(texto_contexto or ""),
            ],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return rid
    except Exception:
        return None


def obtener_resaltados(libro_id: int, color: str | None = None) -> list:
    if color:
        return (
            ejecutar_cached(
                """
                SELECT * FROM resaltados
                WHERE libro_id = ? AND color_etiqueta = ? AND user_id = ?
                ORDER BY pagina, creado_en
                """,
                (int(libro_id), color, uid()),
            )
            or []
        )
    return (
        ejecutar_cached(
            """
            SELECT * FROM resaltados
            WHERE libro_id = ? AND user_id = ?
            ORDER BY pagina, creado_en
            """,
            (int(libro_id), uid()),
        )
        or []
    )


def eliminar_libro(libro_id: int) -> bool:
    try:
        ejecutar(
            "DELETE FROM resaltados WHERE libro_id = ? AND user_id = ?",
            [int(libro_id), uid()],
        )
        ejecutar(
            "DELETE FROM libros WHERE id = ? AND user_id = ?",
            [int(libro_id), uid()],
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def stats_biblioteca() -> dict:
    rows = (
        ejecutar(
            """
            SELECT estado, COUNT(*) AS n FROM libros
            WHERE user_id = ? GROUP BY estado
            """,
            [uid()],
            fetchall=True,
        )
        or []
    )
    by = {r["estado"]: int(r["n"]) for r in rows}
    total = sum(by.values())
    return {
        "total": total,
        "por_procesar": by.get("por_procesar", 0),
        "leyendo": by.get("leyendo", 0),
        "completados": by.get("completado", 0),
        "catalogado": by.get("catalogado", 0),
    }


def pct_progreso(libro: dict) -> float:
    total = int(libro.get("total_paginas") or 0)
    actual = int(libro.get("pagina_actual") or 0)
    if total <= 0:
        return 0.0
    return min(100.0, actual / total * 100)
