"""El servicio de recibos arma el mismo borrador que antes armaba la web."""
from __future__ import annotations

from types import SimpleNamespace

from app.db.schema import DEFAULT_SOBRE_SCAN, DEFAULT_SUBCAT_SCAN, OCR_ESTADO_PENDIENTE
from app.receipt_service import MAX_SCAN_BYTES, ScanError, armar_borrador


def test_armar_borrador_recibo(monkeypatch):
    item = SimpleNamespace(nombre="Leche", cantidad=1, precio_unitario=1.25, precio_total=1.25)
    result = SimpleNamespace(
        ok=True,
        error="",
        tipo="recibo",
        comercio="Super",
        fecha="2026-09-01",
        monto_total=1.25,
        metodo_pago="efectivo",
        items=[item],
        warnings=["falta nit"],
        raw={"comercio": "Super"},
    )
    monkeypatch.setattr("app.receipt_service.extract_from_image", lambda raw: result)
    monkeypatch.setattr("app.receipt_service.save_receipt_image", lambda uid, raw, name: "data/uploads/receipts/1/a.jpg")
    draft = armar_borrador(1, b"img", "foto.jpg")
    assert draft["origen"] == "recibo"
    assert draft["sobre"] == DEFAULT_SOBRE_SCAN
    assert draft["subcategoria"] == DEFAULT_SUBCAT_SCAN
    assert draft["ocr_estado"] == OCR_ESTADO_PENDIENTE
    assert draft["lineas"][0]["nombre"] == "Leche"
    assert draft["imagen_url"].endswith("a.jpg")
    assert MAX_SCAN_BYTES == 8 * 1024 * 1024


def test_ocr_fallido_no_arma_borrador(monkeypatch):
    monkeypatch.setattr("app.receipt_service.save_receipt_image", lambda *a, **k: "x.jpg")
    monkeypatch.setattr(
        "app.receipt_service.extract_from_image",
        lambda raw: SimpleNamespace(ok=False, error="borroso", tipo="", comercio="", items=[], warnings=[], raw={}),
    )
    try:
        armar_borrador(1, b"img", "foto.jpg")
        raise AssertionError("debía fallar")
    except ScanError as e:
        assert "borroso" in str(e)
