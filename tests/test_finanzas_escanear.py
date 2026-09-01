"""Flujo web: escanear recibo → confirmar → guardar (OCR mockeado)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.receipt_ocr import ExtractionResult, ReceiptItemDraft


@pytest.fixture()
def web_client(monkeypatch):
    import tempfile

    td = Path(tempfile.mkdtemp())
    db_path = td / "web_test.db"

    monkeypatch.setenv("MISSION_ALLOW_SQLITE", "1")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.delenv("MISSION_WEB", raising=False)

    import app.db.core as core

    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setattr(core, "usar_turso", lambda: False)
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: True)

    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client


def _setup_finanzas(client: TestClient, username: str = "scan_user") -> None:
    r = client.post(
        "/setup",
        data={
            "username": username,
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/perfil",
        data={
            "nombre": "Neto",
            "situacion": "prueba",
            "objetivos": "finanzas",
            "tiempo": "15",
            "notas": "",
            "areas": ["finanzas"],
        },
        follow_redirects=False,
    )
    client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas"]},
        follow_redirects=False,
    )


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (120, 80), color=(90, 90, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def test_finanzas_muestra_bloque_escanear(web_client):
    _setup_finanzas(web_client)
    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    assert b"Escanear recibo" in r.content
    assert b"/app/m/finanzas/escanear" in r.content


def test_escanear_confirm_y_guardar(web_client, monkeypatch):
    _setup_finanzas(web_client, "scan_ok")

    fake = ExtractionResult(
        ok=True,
        tipo="recibo",
        comercio="Súper Selectos",
        fecha="2026-09-01",
        monto_total=15.75,
        metodo_pago="tarjeta",
        items=[
            ReceiptItemDraft("LECHE", 1, 2.5, 2.5),
            ReceiptItemDraft("PAN", 2, 1.0, 2.0),
        ],
        raw={"tipo": "recibo"},
        warnings=["demo warning"],
    )
    monkeypatch.setattr("web.routers.finanzas.extract_from_image", lambda raw: fake)

    r = web_client.post(
        "/app/m/finanzas/escanear",
        files={"imagen": ("ticket.jpg", _jpeg_bytes(), "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert b"Confirmar escaneo" in r.content
    assert b"S" in r.content  # comercio / selectos
    assert b"LECHE" in r.content
    assert b"demo warning" in r.content

    r = web_client.post(
        "/app/m/finanzas/escanear/confirmar",
        data={
            "fecha": "2026-09-01",
            "monto_total": "15.75",
            "comercio": "Súper Selectos",
            "metodo_pago": "tarjeta",
            "origen": "recibo",
            "sobre": "Supervivencia",
            "subcategoria": "Comida",
            "descripcion": "Súper Selectos",
            "item_nombre_0": "LECHE",
            "item_cantidad_0": "1",
            "item_pu_0": "2.5",
            "item_pt_0": "2.5",
            "item_nombre_1": "PAN",
            "item_cantidad_1": "2",
            "item_pu_1": "1",
            "item_pt_1": "2",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "flash=escaneado" in r.headers.get("location", "")

    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    assert b"escaneado" in r.content.lower() or b"Selectos" in r.content
    assert b"recibo" in r.content

    import app.db.core as core

    rows = core.ejecutar(
        "SELECT origen, comercio, monto FROM gastos_sobres WHERE origen='recibo'",
        fetchall=True,
    ) or []
    assert len(rows) >= 1
    assert float(rows[0]["monto"]) == pytest.approx(15.75)
    items = core.ejecutar("SELECT * FROM receipt_items", fetchall=True) or []
    assert len(items) == 2


def test_escanear_error_ocr(web_client, monkeypatch):
    _setup_finanzas(web_client, "scan_bad")
    monkeypatch.setattr(
        "web.routers.finanzas.extract_from_image",
        lambda raw: ExtractionResult(ok=False, error="La imagen es ilegible."),
    )
    r = web_client.post(
        "/app/m/finanzas/escanear",
        files={"imagen": ("bad.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code == 422
    assert b"ilegible" in r.content.lower()
