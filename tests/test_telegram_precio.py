"""Telegram v2 · /precio y /estado."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound(
        "42",
        text=text,
        update_id=uid,
        send_fn=lambda c, b: None,
        parse_fn=lambda t: {"intent": "unknown"},
    )


def _setup(client):
    _onboard(client)
    _link_admin("42")


def test_precio_tres_mas_baratos(web_client, monkeypatch):
    _setup(web_client)
    catalogo = [
        {"nombre": "Leche entera", "precio": 1.5, "supermercado": "selectos", "fecha_actualizacion": "2026-09-01"},
        {"nombre": "Leche descremada", "precio": 0.99, "supermercado": "walmart", "fecha_actualizacion": "2026-09-02"},
        {"nombre": "Leche deslactosada", "precio": 1.2, "supermercado": "despensa", "fecha_actualizacion": "2026-09-03"},
        {"nombre": "Leche extra", "precio": 2.0, "supermercado": "selectos", "fecha_actualizacion": "2026-09-04"},
    ]

    def buscar(q="", supermercado=None, limit=40):
        if not q:
            return catalogo[:1]
        return catalogo

    monkeypatch.setattr("app.db.finanzas_receipts.buscar_productos", buscar)
    out = _say("/precio leche", "c1")
    assert out.index("0.99") < out.index("1.20") < out.index("1.50")
    assert "2.00" not in out


def test_catalogo_vacio(web_client, monkeypatch):
    _setup(web_client)
    monkeypatch.setattr("app.db.finanzas_receipts.buscar_productos", lambda *a, **k: [])
    assert "vacío" in _say("/precio leche", "c2")


def test_precio_sin_producto(web_client):
    _setup(web_client)
    assert "producto" in _say("/precio", "c3").lower()


def test_modulo_finanzas_apagado(web_client):
    _setup(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    assert "apagado" in _say("/precio leche", "c4")


def test_estado_resume(web_client, monkeypatch):
    _setup(web_client)
    monkeypatch.setattr("app.google_calendar.calendar_disponible", lambda: False)
    out = _say("/estado", "c5")
    assert "Plan:" in out and "finanzas" in out and "sin vincular" in out
    assert "Llamadas de IA" in out
