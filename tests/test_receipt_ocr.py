"""
Tests Fase 2a — parseo/validación OCR de recibos (sin llamar a Groq).
"""
from __future__ import annotations

import json

import pytest

from app.receipt_ocr import (
    compress_image_bytes,
    extract_from_image,
    parse_and_validate_extraction,
)


def test_parse_recibo_valido():
    raw = {
        "tipo": "recibo",
        "comercio": "Súper Selectos",
        "fecha": "2026-08-15",
        "monto_total": 25.5,
        "metodo_pago": "tarjeta",
        "items": [
            {
                "nombre": "LECHE DESLAC 1L ALPINA",
                "cantidad": 1,
                "precio_unitario": 2.5,
                "precio_total": 2.5,
            },
            {
                "nombre": "PAN TAJADO",
                "cantidad": 2,
                "precio_unitario": 1.25,
                "precio_total": 2.5,
            },
        ],
    }
    result = parse_and_validate_extraction(json.dumps(raw))
    assert result.ok
    assert result.tipo == "recibo"
    assert result.comercio == "Súper Selectos"
    assert result.fecha == "2026-08-15"
    assert result.monto_total == pytest.approx(25.5)
    assert len(result.items) == 2
    # items no suman el total → warning, no fallo duro
    assert any("items" in w.lower() or "suma" in w.lower() for w in result.warnings)


def test_parse_transferencia_sin_items():
    raw = {
        "tipo": "transferencia",
        "comercio": "BAC Credomatic",
        "fecha": "2026-09-01",
        "monto_total": 40.0,
        "metodo_pago": "transferencia",
        "items": [],
    }
    result = parse_and_validate_extraction(json.dumps(raw))
    assert result.ok
    assert result.tipo == "transferencia"
    assert result.items == []


def test_parse_json_en_markdown_fence():
    text = """```json
{"tipo":"recibo","comercio":null,"fecha":null,"monto_total":10,"metodo_pago":null,"items":[]}
```"""
    result = parse_and_validate_extraction(text)
    assert result.ok
    assert result.monto_total == pytest.approx(10.0)


def test_rechaza_imagen_ilegible():
    raw = {
        "tipo": None,
        "comercio": None,
        "fecha": None,
        "monto_total": None,
        "metodo_pago": None,
        "items": [],
        "error": "imagen_ilegible",
    }
    result = parse_and_validate_extraction(json.dumps(raw))
    assert not result.ok
    assert "ilegible" in (result.error or "").lower() or "válid" in (result.error or "").lower()


def test_rechaza_tipo_invalido():
    result = parse_and_validate_extraction(
        json.dumps(
            {
                "tipo": "factura_rara",
                "comercio": "X",
                "fecha": "2026-01-01",
                "monto_total": 1,
                "metodo_pago": None,
                "items": [],
            }
        )
    )
    assert not result.ok


def test_fecha_invalida_queda_null_con_warning():
    result = parse_and_validate_extraction(
        json.dumps(
            {
                "tipo": "recibo",
                "comercio": "Walmart",
                "fecha": "15/08/2026",
                "monto_total": 5,
                "metodo_pago": None,
                "items": [],
            }
        )
    )
    assert result.ok
    assert result.fecha is None
    assert any("fecha" in w.lower() for w in result.warnings)


def test_compress_image_reduce_size():
    # PNG 1x1 mínimo vía bytes sintéticos con Pillow
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    img = Image.new("RGB", (2400, 1800), color=(200, 200, 200))
    img.save(buf, format="JPEG", quality=95)
    original = buf.getvalue()
    compressed, mime = compress_image_bytes(original)
    assert mime == "image/jpeg"
    assert len(compressed) < len(original)
    assert len(compressed) > 0


def test_extract_from_image_usa_vision_mock(monkeypatch):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (100, 80), color=(10, 10, 10)).save(buf, format="JPEG")
    payload = buf.getvalue()

    fake_json = json.dumps(
        {
            "tipo": "recibo",
            "comercio": "La Despensa",
            "fecha": "2026-07-01",
            "monto_total": 9.99,
            "metodo_pago": "efectivo",
            "items": [],
        }
    )

    def _fake_vision(**kwargs):
        return fake_json

    monkeypatch.setattr("app.receipt_ocr._llamar_vision_groq", _fake_vision)
    result = extract_from_image(payload)
    assert result.ok
    assert result.comercio == "La Despensa"
    assert result.monto_total == pytest.approx(9.99)


def test_extract_falla_si_api_none(monkeypatch):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 40), color=(1, 1, 1)).save(buf, format="JPEG")
    monkeypatch.setattr("app.receipt_ocr._llamar_vision_groq", lambda **kw: None)
    result = extract_from_image(buf.getvalue())
    assert not result.ok
    assert result.error
