"""Ideas del sandbox por Telegram. Dominio por #etiqueta; si no, Otros."""
from __future__ import annotations

import re

from app.db.sandbox import CATEGORIAS_DEFAULT_POR_DOMINIO, DOMINIOS
from app.telegram_actions.base import Accion, Contexto, Respuesta
from app.telegram_actions.briefing import normalize

_HASH = re.compile(r"\s+#([^\s#]+)\s*$")


def _dominio(token: str) -> str | None:
    q = normalize(token)
    return next((d for d in DOMINIOS if normalize(d) == q), None)


def _parse(args: str) -> dict | None:
    raw = (args or "").strip()
    if not raw:
        return None
    dominio, crudo = "Otros", ""
    m = _HASH.search(raw)
    if m:
        crudo = m.group(1)
        encontrado = _dominio(crudo)
        if encontrado is None:
            return {"titulo": "", "dominio": "", "dominio_malo": crudo}
        dominio = encontrado
        raw = raw[: m.start()].strip()
        if not raw:
            return None
    return {"titulo": raw[:200], "dominio": dominio}


def _ejecutar(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.db.sandbox import guardar_idea

    if datos.get("dominio_malo"):
        lista = ", ".join(DOMINIOS)
        return Respuesta(
            f"No conozco el dominio «{datos['dominio_malo']}». No guardé nada. Usá: {lista}."
        )
    dominio = datos["dominio"]
    cats = CATEGORIAS_DEFAULT_POR_DOMINIO.get(dominio) or ["General"]
    rid = guardar_idea(
        datos["titulo"],
        "",
        dominio,
        cats[0],
        [],
        3,
        3,
        estado="Idea",
    )
    return Respuesta(
        f"Anoté la idea «{datos['titulo']}» en {dominio}.",
        entidad_id=int(rid),
        resumen=f"idea «{datos['titulo']}»",
    )


def _deshacer(_ctx: Contexto, entidad_id: int, _resumen: str = "") -> bool:
    from app.db.sandbox import eliminar_idea, obtener_idea

    if obtener_idea(int(entidad_id)) is None:
        return False
    eliminar_idea(int(entidad_id))
    return True


def _listar(_ctx: Contexto, _datos: dict) -> Respuesta:
    from app.db.sandbox import obtener_ideas

    ideas = obtener_ideas()[:8]
    if not ideas:
        return Respuesta("No tenés ideas. Ejemplo: /idea armar un estante #personal")
    lineas = ["Ideas"]
    for idea in ideas:
        lineas.append(f"· {idea['titulo']} ({idea['dominio']})")
    return Respuesta("\n".join(lineas))


IDEA = Accion(
    clave="idea",
    comandos=("/idea",),
    modulo="sandbox",
    ejecutar=_ejecutar,
    deshacer=_deshacer,
    uso="Escribí la idea. Ejemplo: /idea armar un estante #personal",
    parse=_parse,
)

IDEAS = Accion(
    clave="ideas",
    comandos=("/ideas",),
    modulo="sandbox",
    ejecutar=_listar,
    parse=lambda _args: {},
)
