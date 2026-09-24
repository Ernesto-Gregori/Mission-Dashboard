"""Telegram v2 · foto de recibo: cupo, 5 MB, borrador y confirmación."""
from __future__ import annotations

from types import SimpleNamespace

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _foto(raw: bytes, uid: str, size: int = 0) -> str:
    from app.telegram import handle_inbound

    return handle_inbound(
        "42",
        text="",
        update_id=uid,
        send_fn=lambda c, b: None,
        photo_id="ph",
        photo_size=size or len(raw),
        photo_bytes=raw,
        parse_fn=lambda t: {"intent": "unknown"},
    )


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None)


def _setup(client):
    _onboard(client)
    _link_admin("42")


def _ocr(monkeypatch, monto=12.5):
    item = SimpleNamespace(nombre="Pan", cantidad=1, precio_unitario=monto, precio_total=monto)
    result = SimpleNamespace(
        ok=True,
        error="",
        tipo="recibo",
        comercio="Panadería",
        fecha="2026-09-24",
        monto_total=monto,
        metodo_pago="efectivo",
        items=[item],
        warnings=[],
        raw={},
    )
    called = []
    monkeypatch.setattr("app.receipt_service.extract_from_image", lambda raw: called.append(1) or result)
    monkeypatch.setattr("app.receipt_service.save_receipt_image", lambda *a, **k: "data/uploads/receipts/1/a.jpg")
    return called


def test_foto_pide_confirmacion_y_si_guarda(web_client, monkeypatch):
    _setup(web_client)
    called = _ocr(monkeypatch)
    out = _foto(b"jpeg", "r1")
    assert "12.50" in out and "Panadería" in out
    assert called == [1]
    assert _rows("gastos_sobres") == []
    assert "Anoté $12.50" in _say("sí", "r2")
    row = _rows("gastos_sobres")[0]
    assert row["ocr_estado"] == "confirmado" and row["origen"] == "recibo"
    assert float(row["monto"]) == 12.5


def test_no_no_guarda(web_client, monkeypatch):
    _setup(web_client)
    _ocr(monkeypatch)
    _foto(b"jpeg", "r3")
    assert "Cancelado" in _say("no", "r4")
    assert _rows("gastos_sobres") == []


def test_foto_grande_no_llama_ocr(web_client, monkeypatch):
    _setup(web_client)
    called = _ocr(monkeypatch)
    out = _foto(b"", "r5", size=5 * 1024 * 1024 + 1)
    assert "5 MB" in out and called == []
    assert _rows("gastos_sobres") == []


def test_sin_cupo_no_lee(web_client, monkeypatch):
    _setup(web_client)
    called = _ocr(monkeypatch)
    monkeypatch.setattr("app.billing.cuota_ia_ok", lambda *a, **k: False)
    out = _foto(b"jpeg", "r6")
    assert "cupo" in out and called == []


def test_extract_solo_fotos(web_client):
    from app.telegram import extract_inbound

    photo = extract_inbound(
        {"update_id": 1, "message": {"chat": {"id": 1, "type": "private"}, "photo": [{"file_id": "a", "file_size": 10}, {"file_id": "b", "file_size": 99}]}}
    )
    assert photo[0]["photo_id"] == "b" and photo[0]["photo_size"] == 99
    doc = extract_inbound(
        {"update_id": 2, "message": {"chat": {"id": 1, "type": "private"}, "document": {"file_id": "d", "mime_type": "image/jpeg"}}}
    )
    assert doc[0]["photo_id"] == ""
    grupo = extract_inbound(
        {"update_id": 3, "message": {"chat": {"id": 9, "type": "group"}, "photo": [{"file_id": "g", "file_size": 1}]}}
    )
    assert grupo == []
