"""Hábitos por Telegram. Siempre disponibles (no dependen de un módulo)."""
from __future__ import annotations

import difflib
import re

from app.telegram_actions.base import Accion, Contexto, Respuesta
from app.telegram_actions.briefing import normalize

HECHO_RE = re.compile(r"^(?:ya|hice|hecho)\s+(.+)$", re.I)


def candidatos(texto: str, habitos: list[dict]) -> list[dict]:
    q = normalize(texto)
    if not q:
        return []
    exactos = [h for h in habitos if normalize(h["label"]) == q or normalize(h["clave"]) == q]
    if exactos:
        return exactos
    parciales = [h for h in habitos if q in normalize(h["label"]) or normalize(h["label"]) in q]
    if parciales:
        return parciales
    por_label = {normalize(h["label"]): h for h in habitos}
    return [por_label[n] for n in difflib.get_close_matches(q, por_label, n=3, cutoff=0.55)]


def _completos() -> set[str]:
    from app.ritual import habitos_hoy

    return {clave for clave, hecho in habitos_hoy().items() if hecho}


def _marcar(clave: str) -> None:
    from app.ritual import marcar_habitos

    marcar_habitos(sorted(_completos() | {clave}))


def _desmarcar(clave: str) -> None:
    from app.ritual import marcar_habitos

    marcar_habitos(sorted(_completos() - {clave}))


def _listar(_ctx: Contexto, _datos: dict) -> Respuesta:
    from app.ritual import habitos_hoy, listar_habitos

    hechos = habitos_hoy()
    habitos = listar_habitos()
    if not habitos:
        return Respuesta("No tenés hábitos activos. Se crean en la app, en Coach.")
    lineas = ["Hábitos de hoy"]
    for h in habitos:
        mark = "✓" if hechos.get(h["clave"]) else "·"
        lineas.append(f"{mark} {h.get('emoji') or ''} {h['label']}".strip())
    lineas.append("Para marcar: /hecho leer  (o «ya leí»).")
    return Respuesta("\n".join(lineas))


def _aplicar(ctx: Contexto, texto: str) -> Respuesta:
    from app.ritual import listar_habitos

    encontrados = candidatos(texto, listar_habitos())
    if not encontrados:
        return Respuesta(f"No encontré un hábito para «{texto[:40]}». Mirá /habitos. No marqué nada.")
    if len(encontrados) > 1:
        return Respuesta(
            f"«{texto[:40]}» coincide con varios. ¿Cuál?",
            accion="habito",
            botones=[(h["label"][:20], f"k:{h['clave']}") for h in encontrados[:6]],
        )
    habito = encontrados[0]
    _marcar(habito["clave"])
    return Respuesta(
        f"✓ {habito['label']}. Los otros hábitos de hoy siguen como estaban.",
        accion="habito",
        entidad_id=0,
        resumen=f"habito:{habito['clave']}",
    )


def marcar_desde_boton(ctx: Contexto, clave: str) -> Respuesta:
    from app.ritual import listar_habitos

    habito = next((h for h in listar_habitos() if h["clave"] == clave), None)
    if habito is None:
        return Respuesta("Ese hábito ya no está. No marqué nada.", accion="habito")
    _marcar(clave)
    return Respuesta(
        f"✓ {habito['label']}. Los otros hábitos de hoy siguen como estaban.",
        accion="habito",
        entidad_id=0,
        resumen=f"habito:{clave}",
    )


def _resto(texto: str) -> str:
    actual = (texto or "").strip()
    while True:
        m = HECHO_RE.match(actual)
        if not m:
            return actual
        actual = m.group(1).strip()


def _ejecutar_hecho(ctx: Contexto, datos: dict) -> Respuesta:
    return _aplicar(ctx, _resto(str(datos.get("texto") or datos.get("_texto") or "")))


def _patron(texto: str) -> dict | None:
    resto = _resto(texto)
    if resto == (texto or "").strip():
        return None
    return {"texto": resto}


def _deshacer(_ctx: Contexto, _entidad_id: int, resumen: str = "") -> bool:
    clave = resumen.removeprefix("habito:")
    if not clave or clave == resumen:
        return False
    _desmarcar(clave)
    return True


HABITOS = Accion(
    clave="habitos",
    comandos=("/habitos",),
    alias=("/hábitos",),
    ejecutar=_listar,
    parse=lambda _args: {},
)

HECHO = Accion(
    clave="habito",
    comandos=("/hecho",),
    ejecutar=_ejecutar_hecho,
    deshacer=_deshacer,
    uso="Decime cuál. Ejemplo: /hecho leer  (o «ya leí»).",
    parse=lambda args: {"texto": args.strip()} if args.strip() else None,
    patron=_patron,
)
