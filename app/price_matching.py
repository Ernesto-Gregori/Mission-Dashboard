"""
Matching de ítems de recibo ↔ catálogo supermarket_products (Fase 4).

v1: normalización salvadoreña + similitud de texto (difflib + tokens).
Umbral: PRICE_MATCH_SCORE_MIN (default 0.78). Por debajo → sin coincidencia clara.
Embeddings: pospuesto.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional

from app.db.schema import PRICE_MATCH_SCORE_MIN, SUPERMERCADOS

# Abreviaturas frecuentes en tickets SV (orden: más largas primero al aplicar)
_ABBREVS: list[tuple[str, str]] = [
    ("deslac", "deslactosada"),
    ("semides", "semidescremada"),
    ("semidesc", "semidescremada"),
    ("incapar", "incaparina"),
    ("yog", "yogurt"),
    ("manteq", "mantequilla"),
    ("det", "detergente"),
    ("jab", "jabon"),
    ("papel hig", "papel higienico"),
    ("p/higienico", "papel higienico"),
    ("p higienico", "papel higienico"),
    ("lech", "leche"),
    ("lche", "leche"),
    ("pack", "pack"),
    ("pq", "pack"),
    ("unid", "unidad"),
    ("und", "unidad"),
    ("uds", "unidades"),
    ("ud", "unidad"),
    ("lts", "litros"),
    ("lt", "litro"),
    ("litro", "litro"),
    ("ml", "ml"),
    ("kgs", "kg"),
    ("kg", "kg"),
    ("grs", "g"),
    ("gr", "g"),
    ("pz", "pieza"),
    ("pza", "pieza"),
    ("cj", "caja"),
    ("doc", "docena"),
]

_STOP = frozenset(
    {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
        "en",
        "con",
        "para",
        "por",
        "a",
        "un",
        "una",
        "the",
        "x",
    }
)


def strip_accents(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def normalize_product_name(text: str) -> str:
    """Minúsculas, sin acentos, abreviaturas SV expandidas, espacios limpios."""
    t = strip_accents((text or "").lower())
    t = t.replace("&", " y ")
    # separar número+unidad pegados: 52.7g → 52.7 g, 12u → 12 u
    t = re.sub(r"(\d+[.,]?\d*)(ml|l|kg|g|u|und|uds|unid|pz)\b", r"\1 \2", t)
    t = re.sub(r"[^a-z0-9\s./]", " ", t)
    t = t.replace("/", " ")
    t = t.replace(",", ".")
    # volúmenes equivalentes
    t = re.sub(r"\b1000\s*ml\b", "1 litro", t)
    t = re.sub(r"\b1\.0*\s*l\b", "1 litro", t)
    t = re.sub(r"\b(\d+)\s*l\b", r"\1 litro", t)
    t = re.sub(r"\b(\d+)\s*ml\b", r"\1 ml", t)
    t = re.sub(r"\b(\d+)\s*g\b", r"\1 g", t)
    t = re.sub(r"\b(\d+)\s*kg\b", r"\1 kg", t)
    # aplicar abreviaturas como tokens
    tokens = t.split()
    out: list[str] = []
    i = 0
    abbrev_map = {k: v for k, v in _ABBREVS}
    while i < len(tokens):
        if i + 1 < len(tokens):
            bigram = f"{tokens[i]} {tokens[i + 1]}"
            if bigram in abbrev_map:
                out.extend(abbrev_map[bigram].split())
                i += 2
                continue
        tok = tokens[i]
        if tok in abbrev_map:
            out.extend(abbrev_map[tok].split())
        else:
            out.append(tok)
        i += 1
    cleaned = [tok for tok in out if tok not in _STOP]
    return " ".join(cleaned)


def _tokens(text: str) -> set[str]:
    return {t for t in normalize_product_name(text).split() if len(t) > 1}


def similarity_score(a: str, b: str) -> float:
    """
    Score 0..1: max entre SequenceMatcher, token-sort y contención de tokens núcleo.
    """
    na = normalize_product_name(a)
    nb = normalize_product_name(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return seq
    jaccard = len(ta & tb) / len(ta | tb)
    containment = len(ta & tb) / len(ta)
    sort_ratio = SequenceMatcher(
        None, " ".join(sorted(ta)), " ".join(sorted(tb))
    ).ratio()
    # tokens “núcleo” (marcas / producto): letras len>=4
    core_a = {t for t in ta if t.isalpha() and len(t) >= 4}
    core_b = {t for t in tb if t.isalpha() and len(t) >= 4}
    if core_a:
        core_hit = len(core_a & core_b) / len(core_a)
    else:
        core_hit = 0.0
    blended = 0.35 * seq + 0.25 * jaccard + 0.20 * containment + 0.20 * core_hit
    return max(seq, sort_ratio, blended, core_hit * 0.85 + containment * 0.15)


@dataclass
class CatalogHit:
    product_id: int
    supermercado: str
    nombre: str
    precio: float | None
    url_producto: str | None
    score: float


@dataclass
class ItemMatchResult:
    nombre_original: str
    nombre_normalizado: str
    hits: list[CatalogHit]  # mejores por supermercado (si pasan umbral)
    sin_coincidencia_clara: bool

    def resumen_precios(self) -> str:
        if self.sin_coincidencia_clara or not self.hits:
            return "Sin coincidencia clara en supermercados"
        labels = {
            "super_selectos": "Súper Selectos",
            "walmart_sv": "Walmart",
            "despensa_don_juan": "La Despensa",
        }
        parts = []
        for h in sorted(self.hits, key=lambda x: x.supermercado):
            label = labels.get(h.supermercado, h.supermercado)
            if h.precio is None:
                parts.append(f"{label} (sin precio)")
            else:
                parts.append(f"{label} a ${h.precio:.2f}")
        return "Lo encontramos en " + " y en ".join(parts)


def match_item_against_catalog(
    nombre: str,
    catalog: Iterable[dict],
    *,
    score_min: float = PRICE_MATCH_SCORE_MIN,
    per_store_limit: int = 1,
) -> ItemMatchResult:
    """
    `catalog`: filas con id, supermercado, nombre, nombre_normalizado, precio, url_producto.
    Devuelve el mejor hit por supermercado si score >= umbral.
    """
    norm = normalize_product_name(nombre)
    query_tokens = _tokens(nombre)
    best_by_store: dict[str, CatalogHit] = {}

    for row in catalog:
        store = row.get("supermercado") or ""
        if store not in SUPERMERCADOS:
            continue
        cand_name = row.get("nombre") or ""
        cand_norm = row.get("nombre_normalizado") or normalize_product_name(cand_name)
        # prefiltro: al menos un token significativo en común (o score seq alto después)
        cand_tokens = set((cand_norm or "").split())
        if query_tokens and cand_tokens and not (query_tokens & cand_tokens):
            # permitir si SequenceMatcher aún así sería alto (nombres cortos)
            if SequenceMatcher(None, norm, cand_norm).ratio() < 0.72:
                continue
        score = similarity_score(nombre, cand_name)
        if score < score_min:
            continue
        precio = row.get("precio")
        try:
            precio_f = float(precio) if precio is not None else None
        except (TypeError, ValueError):
            precio_f = None
        hit = CatalogHit(
            product_id=int(row["id"]),
            supermercado=store,
            nombre=cand_name,
            precio=precio_f,
            url_producto=row.get("url_producto"),
            score=score,
        )
        prev = best_by_store.get(store)
        if prev is None or hit.score > prev.score:
            best_by_store[store] = hit

    hits = sorted(best_by_store.values(), key=lambda h: (-h.score, h.supermercado))
    if per_store_limit:
        # ya hay 1 por tienda
        pass
    return ItemMatchResult(
        nombre_original=nombre,
        nombre_normalizado=norm,
        hits=hits,
        sin_coincidencia_clara=len(hits) == 0,
    )


def load_catalog(activo_only: bool = True) -> list[dict]:
    from app.db.core import ejecutar

    sql = """
        SELECT id, supermercado, nombre, nombre_normalizado, precio, url_producto
        FROM supermarket_products
    """
    if activo_only:
        sql += " WHERE activo = 1"
    return ejecutar(sql, fetchall=True) or []


def match_receipt_items(
    items: list[dict],
    *,
    catalog: Optional[list[dict]] = None,
    score_min: float = PRICE_MATCH_SCORE_MIN,
) -> list[ItemMatchResult]:
    """items: dicts con clave nombre (u nombre_original)."""
    cat = catalog if catalog is not None else load_catalog()
    results = []
    for it in items:
        nombre = (it.get("nombre") or it.get("nombre_original") or "").strip()
        if not nombre:
            continue
        results.append(
            match_item_against_catalog(nombre, cat, score_min=score_min)
        )
    return results


def persist_matches_for_receipt_item(
    receipt_item_id: int,
    match: ItemMatchResult,
) -> list[int]:
    """Guarda price_matches; marca es_mejor_precio al de menor precio entre hits."""
    from app.db import finanzas_receipts as fr

    if match.sin_coincidencia_clara:
        return []
    priced = [h for h in match.hits if h.precio is not None]
    best_price = min((h.precio for h in priced), default=None)
    ids = []
    for h in match.hits:
        mid = fr.guardar_price_match(
            receipt_item_id=receipt_item_id,
            supermarket_product_id=h.product_id,
            score=round(h.score, 4),
            metodo="fuzzy",
            es_mejor_precio=bool(
                best_price is not None
                and h.precio is not None
                and abs(h.precio - best_price) < 0.001
            ),
        )
        ids.append(mid)
    return ids
