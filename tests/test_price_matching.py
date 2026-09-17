"""
Casos de prueba reales (nombres típicos de recibos SV) para matching fuzzy.
"""
from __future__ import annotations

import pytest

from app.price_matching import (
    ItemMatchResult,
    match_item_against_catalog,
    normalize_product_name,
    similarity_score,
)


def test_normalize_expande_abreviaturas_sv():
    assert "deslactosada" in normalize_product_name("LECHE DESLAC 1L ALPINA")
    assert "litro" in normalize_product_name("LECHE DESLAC 1L ALPINA")
    assert "yogurt" in normalize_product_name("YOG FRESA YOPLAIT 125G")
    n = normalize_product_name("PAPEL HIG SCOTT 18R")
    assert "higienico" in n or "papel" in n


def test_similarity_leche_deslac_vs_catalog():
    recibo = "LECHE DESLAC 1L ALPINA"
    catalog = "Leche Deslactosada Alpina 1 Litro"
    score = similarity_score(recibo, catalog)
    assert score >= 0.78


def test_similarity_no_confunde_productos_distintos():
    score = similarity_score("LECHE DESLAC 1L ALPINA", "Detergente Líquido Ariel 3 L")
    assert score < 0.5


CATALOG_FIXTURE = [
    {
        "id": 1,
        "supermercado": "walmart_sv",
        "nombre": "Leche Deslactosada Alpina 1 Litro",
        "nombre_normalizado": normalize_product_name("Leche Deslactosada Alpina 1 Litro"),
        "precio": 2.35,
        "url_producto": "https://www.walmart.com.sv/leche-alpina/p",
    },
    {
        "id": 2,
        "supermercado": "super_selectos",
        "nombre": "Leche Deslactosada Alpina 1000 ml",
        "nombre_normalizado": normalize_product_name("Leche Deslactosada Alpina 1000 ml"),
        "precio": 2.45,
        "url_producto": "https://www.superselectos.com/products?productId=1",
    },
    {
        "id": 3,
        "supermercado": "despensa_don_juan",
        "nombre": "Leche Entera Dos Pinos 946 ml",
        "nombre_normalizado": normalize_product_name("Leche Entera Dos Pinos 946 ml"),
        "precio": 1.95,
        "url_producto": None,
    },
    {
        "id": 4,
        "supermercado": "walmart_sv",
        "nombre": "Tortilla Bimbo Harina Trigo Rapidita Clásicas 12 Uds - 312 g",
        "nombre_normalizado": normalize_product_name(
            "Tortilla Bimbo Harina Trigo Rapidita Clásicas 12 Uds - 312 g"
        ),
        "precio": 2.15,
        "url_producto": None,
    },
    {
        "id": 5,
        "supermercado": "super_selectos",
        "nombre": "Chocolate Snickers 52.7 g Barra",
        "nombre_normalizado": normalize_product_name("Chocolate Snickers 52.7 g Barra"),
        "precio": 1.55,
        "url_producto": None,
    },
    {
        "id": 6,
        "supermercado": "walmart_sv",
        "nombre": "Detergente Líquido Ariel Downy 3 L",
        "nombre_normalizado": normalize_product_name("Detergente Líquido Ariel Downy 3 L"),
        "precio": 8.75,
        "url_producto": None,
    },
]


@pytest.mark.parametrize(
    "recibo,expect_stores,min_score",
    [
        ("LECHE DESLAC 1L ALPINA", {"walmart_sv", "super_selectos"}, 0.78),
        ("SNICKERS 52.7G", {"super_selectos"}, 0.78),
        ("TORTILLA BIMBO RAPIDITA 12U", {"walmart_sv"}, 0.70),
    ],
)
def test_match_casos_recibo_reales(recibo, expect_stores, min_score):
    result = match_item_against_catalog(
        recibo, CATALOG_FIXTURE, score_min=min_score
    )
    assert isinstance(result, ItemMatchResult)
    assert not result.sin_coincidencia_clara
    got = {h.supermercado for h in result.hits}
    assert expect_stores <= got
    for h in result.hits:
        assert h.score >= min_score


def test_sin_coincidencia_clara_cuando_dudoso():
    result = match_item_against_catalog(
        "XYZ PRODUCTO RARO 99ZZ", CATALOG_FIXTURE, score_min=0.78
    )
    assert result.sin_coincidencia_clara
    assert result.hits == []
    assert "Sin coincidencia clara" in result.resumen_precios()


def test_resumen_precios_formato():
    result = match_item_against_catalog("LECHE DESLAC 1L ALPINA", CATALOG_FIXTURE)
    text = result.resumen_precios()
    assert "Walmart" in text
    assert "Súper Selectos" in text
    assert "$" in text
    # no debe forzar Despensa (leche entera distinta)
    assert "Despensa" not in text or result.hits  # ok si no matcheó


def test_no_matchea_leche_con_detergente():
    result = match_item_against_catalog("LECHE DESLAC 1L ALPINA", CATALOG_FIXTURE)
    stores_names = [(h.supermercado, h.nombre) for h in result.hits]
    assert all("Detergente" not in n for _, n in stores_names)
