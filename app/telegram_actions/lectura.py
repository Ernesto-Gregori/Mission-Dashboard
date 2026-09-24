"""Biblioteca por Telegram: qué se está leyendo y en qué página."""
from __future__ import annotations

import difflib
import re

from app.telegram_actions.base import Accion, Contexto, Respuesta
from app.telegram_actions.briefing import normalize

_LEER = re.compile(r"^(?P<titulo>.+?)\s+(?P<pag>\d{1,5})$")


def _libros(busqueda: str = "") -> list[dict]:
    from app.db.biblioteca import obtener_libros_por_estado

    libros, _total = obtener_libros_por_estado(busqueda=busqueda, por_pagina=40)
    return list(libros or [])


def candidatos(texto: str) -> list[dict]:
    q = normalize(texto)
    if not q:
        return []
    like = _libros(texto)
    exactos = [b for b in like if normalize(b.get("titulo") or "") == q]
    if exactos:
        return exactos
    if like:
        return like
    todos = _libros()
    por_titulo = {normalize(b.get("titulo") or ""): b for b in todos if b.get("titulo")}
    return [por_titulo[n] for n in difflib.get_close_matches(q, por_titulo, n=3, cutoff=0.55)]


def _aplicar(ctx: Contexto, libro: dict, pagina: int) -> Respuesta:
    from app.db.biblioteca import actualizar_progreso, obtener_libro

    actual = obtener_libro(int(libro["id"])) or libro
    previa = int(actual.get("pagina_actual") or 0)
    ok = actualizar_progreso(int(libro["id"]), pagina)
    if not ok:
        return Respuesta("No pude guardar la página. No cambié nada.")
    titulo = actual.get("titulo") or libro.get("titulo")
    return Respuesta(
        f"📖 {titulo}, página {pagina}.",
        accion="leer",
        entidad_id=int(libro["id"]),
        resumen=str(previa),
    )


def leer_desde_boton(ctx: Contexto, n: int, pagina: int) -> Respuesta:
    from app.db.biblioteca import obtener_libro
    from app.db.telegram_state import buscar_ref

    libro_id = buscar_ref(ctx.user_id, ctx.chat_id, "libro", n)
    if libro_id is None:
        return Respuesta("Esa lista ya no está. Mandá /leer de nuevo. No cambié nada.", accion="leer")
    libro = obtener_libro(libro_id)
    if libro is None:
        return Respuesta("Ese libro ya no está. No cambié nada.", accion="leer")
    return _aplicar(ctx, libro, pagina)


def _parse(args: str) -> dict | None:
    m = _LEER.match((args or "").strip())
    if not m or not m.group("titulo").strip():
        return None
    return {"titulo": m.group("titulo").strip(), "pagina": int(m.group("pag"))}


def _ejecutar(ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.telegram_state import guardar_refs

    titulo = str(datos.get("titulo") or "")
    pagina = int(datos.get("pagina") or 0)
    encontrados = candidatos(titulo)
    if not encontrados:
        return Respuesta(f"No encontré «{titulo[:40]}». Mirá /leyendo. No cambié nada.")
    if len(encontrados) > 1:
        guardar_refs(ctx.user_id, ctx.chat_id, "libro", [int(b["id"]) for b in encontrados[:6]])
        return Respuesta(
            f"«{titulo[:40]}» coincide con varios. ¿Cuál, en la página {pagina}?",
            accion="leer",
            botones=[
                ((b.get("titulo") or "")[:20], f"b:{i}:{pagina}")
                for i, b in enumerate(encontrados[:6], start=1)
            ],
        )
    return _aplicar(ctx, encontrados[0], pagina)


def _deshacer(_ctx: Contexto, entidad_id: int, resumen: str = "") -> bool:
    from app.db.biblioteca import actualizar_progreso

    try:
        previa = int(resumen or "0")
    except ValueError:
        return False
    return bool(actualizar_progreso(int(entidad_id), previa))


def _leyendo(_ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.biblioteca import obtener_libros_por_estado

    libros, _total = obtener_libros_por_estado(estado="leyendo", por_pagina=8)
    if not libros:
        return Respuesta("No estás leyendo ningún libro. Se marcan en la app, en Biblioteca.")
    lineas = ["Leyendo"]
    for libro in libros:
        pag = int(libro.get("pagina_actual") or 0)
        total = int(libro.get("total_paginas") or 0)
        extra = f" · p. {pag}" + (f"/{total}" if total else "")
        lineas.append(f"· {libro.get('titulo')}{extra}")
    lineas.append("Para avanzar: /leer el título y la página.")
    return Respuesta("\n".join(lineas))


LEYENDO = Accion(
    clave="leyendo",
    comandos=("/leyendo",),
    modulo="biblioteca",
    ejecutar=_leyendo,
    parse=lambda _args: {},
)

LEER = Accion(
    clave="leer",
    comandos=("/leer",),
    modulo="biblioteca",
    ejecutar=_ejecutar,
    deshacer=_deshacer,
    uso="Decime el libro y la página. Ejemplo: /leer El Hobbit 40",
    parse=_parse,
)
