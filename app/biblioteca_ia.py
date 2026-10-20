"""Sugiere categoría y una descripción corta a partir del título."""
from __future__ import annotations

import json

from app.db.biblioteca import CATEGORIAS, normalizar_categoria


def _json(texto: str) -> dict:
    raw = (texto or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def sugerir_categoria(titulo: str, autor: str = "", descripcion: str = "") -> dict:
    """Llama a la IA. La categoría siempre queda en la lista permitida."""
    from app.ai_client import api_key_configurada, chat_simple, last_ai_error

    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("El libro necesita título.")
    if not api_key_configurada():
        raise ValueError("Configura GROQ_API_KEY para categorizar con IA.")
    lista = ", ".join(CATEGORIAS)
    prompt = f"""Clasifica este libro para una biblioteca personal.

Título: {titulo}
Autor: {autor or "desconocido"}
Descripción: {(descripcion or "sin descripción")[:500]}

Responde SOLO JSON:
{{
  "categoria": "una de: {lista}",
  "descripcion": "2 oraciones, en español, sin inventar datos que no se deduzcan del título",
  "temas": ["hasta 4 temas cortos"]
}}"""
    raw = chat_simple(
        prompt,
        contexto=(
            "Clasificas libros. Respondes solo JSON. "
            "No uses categorías fuera de la lista."
        ),
        max_tokens=400,
    )
    data = _json(raw or "")
    if not data:
        detalle = last_ai_error() or "la IA no devolvió JSON"
        raise ValueError(f"No se pudo categorizar ({detalle}).")
    temas = data.get("temas") if isinstance(data.get("temas"), list) else []
    return {
        "categoria": normalizar_categoria(str(data.get("categoria") or "")),
        "descripcion": str(data.get("descripcion") or "").strip()[:600],
        "temas": [str(t).strip()[:40] for t in temas if str(t).strip()][:4],
    }
