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
        return fake_json, None

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
    monkeypatch.setattr(
        "app.receipt_ocr._llamar_vision_groq",
        lambda **kw: (None, "Falta GROQ_API_KEY en el entorno (.env / secrets)."),
    )
    result = extract_from_image(buf.getvalue())
    assert not result.ok
    assert "GROQ_API_KEY" in (result.error or "")


def test_vision_model_default_es_qwen36():
    from app.receipt_ocr import VISION_MODEL_DEFAULT, vision_model

    assert VISION_MODEL_DEFAULT == "qwen/qwen3.6-27b"
    assert vision_model() == VISION_MODEL_DEFAULT


def test_vision_model_alias_scout_retirado(monkeypatch):
    from app import receipt_ocr

    monkeypatch.setenv(
        "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
    )
    monkeypatch.setattr(
        "app.secrets.get_secret",
        lambda name, default="": "",
    )
    assert receipt_ocr.vision_model() == "qwen/qwen3.6-27b"


def test_humanize_model_not_found():
    from app.receipt_ocr import _humanize_vision_error

    msg = _humanize_vision_error(
        "Error code: 404 - model_not_found",
        model="meta-llama/llama-4-scout-17b-16e-instruct",
    )
    assert "no está disponible" in msg
    assert "qwen/qwen3.6-27b" in msg


def test_llamar_vision_prueba_fallback_si_modelo_falla(monkeypatch):
    from app import receipt_ocr

    calls: list[str] = []

    class _Msg:
        content = '{"tipo":"recibo","comercio":"X","fecha":null,"monto_total":1,"metodo_pago":null,"items":[]}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _FakeCompletions:
        def create(self, **kwargs):
            model = kwargs["model"]
            calls.append(model)
            if "qwen3.6" not in model:
                raise RuntimeError("model_not_found: does not exist")
            return _Resp()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    monkeypatch.setenv("GROQ_VISION_MODEL", "modelo-inexistente-xyz")
    monkeypatch.setattr("app.secrets.get_secret", lambda name, default="": "")
    monkeypatch.setattr("app.ai_client._get_api_key", lambda: "gsk_test_key_1234567890")
    monkeypatch.setattr("app.ai_client._hay_cuota", lambda: True)
    monkeypatch.setattr("app.ai_client._get_client", lambda: _FakeClient())
    monkeypatch.setattr("app.ai_client._registrar_llamada", lambda: None)
    monkeypatch.setattr(
        "app.billing.cuota_ia_ok",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "app.billing.registrar_llamada_ia",
        lambda *a, **k: 1,
    )

    text, err = receipt_ocr._llamar_vision_groq(image_b64="abc", mime="image/jpeg")
    assert err is None
    assert text and "recibo" in text
    assert calls[0] == "modelo-inexistente-xyz"
    assert any("qwen3.6" in c for c in calls)
