"""Catálogo SV — resumen, búsqueda y UI de actualizar scrapers."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated_db(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "test.db"

    import app.database as dbmod
    import app.db.core as core

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    monkeypatch.setattr(core, "DB_PATH", db_path)
    if hasattr(dbmod.usar_turso, "cache_clear"):
        dbmod.usar_turso.cache_clear()
    if hasattr(core.usar_turso, "cache_clear"):
        core.usar_turso.cache_clear()
    if hasattr(core._get_turso_config, "cache_clear"):
        core._get_turso_config.cache_clear()
    monkeypatch.setenv("TURSO_URL", "")
    monkeypatch.setenv("TURSO_TOKEN", "")
    monkeypatch.setattr(dbmod, "usar_turso", lambda: False)
    monkeypatch.setattr(core, "usar_turso", lambda: False)

    dbmod.init_database()
    from app.multiuser import migrate_multiuser

    migrate_multiuser()
    yield dbmod


@pytest.fixture()
def web_client(monkeypatch):
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


def _setup_finanzas(client: TestClient) -> None:
    client.post(
        "/setup",
        data={
            "username": "precios_user",
            "password": "password1",
            "password2": "password1",
        },
        follow_redirects=False,
    )
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


def test_resumen_y_busqueda_catalogo(isolated_db):
    from app.db import finanzas_receipts as fr
    from app.db.schema import SUPERMERCADO_SELECTOS, SUPERMERCADO_WALMART

    assert fr.contar_productos_activos() == 0
    resumen = fr.resumen_catalogo_sv()
    assert len(resumen) == 3
    assert all(r["productos"] == 0 for r in resumen)

    fr.upsert_supermarket_product(
        supermercado=SUPERMERCADO_SELECTOS,
        nombre="Leche Alpina 1L",
        nombre_normalizado="leche alpina 1 litro",
        precio=1.85,
        sku_o_id_externo="sel-1",
    )
    fr.upsert_supermarket_product(
        supermercado=SUPERMERCADO_WALMART,
        nombre="Papel Higienico Scott",
        nombre_normalizado="papel higienico scott",
        precio=4.5,
        sku_o_id_externo="wm-1",
    )
    rid = fr.iniciar_scrape_run(SUPERMERCADO_SELECTOS)
    fr.finalizar_scrape_run(rid, status="ok", products_upserted=1)

    resumen = fr.resumen_catalogo_sv()
    by_key = {r["key"]: r for r in resumen}
    assert by_key[SUPERMERCADO_SELECTOS]["productos"] == 1
    assert by_key[SUPERMERCADO_SELECTOS]["ultimo_status"] == "ok"
    assert by_key[SUPERMERCADO_WALMART]["productos"] == 1

    hits = fr.buscar_productos("leche")
    assert len(hits) == 1
    assert hits[0]["nombre"].startswith("Leche")


def test_finanzas_muestra_seccion_supermercados(web_client):
    _setup_finanzas(web_client)
    r = web_client.get("/app/m/finanzas")
    assert r.status_code == 200
    body = r.text
    assert "Precios supermercados SV" in body
    assert "Súper Selectos" in body
    assert "Walmart SV" in body
    assert "Despensa de Don Juan" in body
    assert "Catálogo vacío" in body


def test_actualizar_catalogo_dispara_scraper(web_client, monkeypatch):
    from app.scrapers.base import ScrapeResult

    _setup_finanzas(web_client)

    called: list[str] = []

    def fake_run(key: str) -> ScrapeResult:
        called.append(key)
        return ScrapeResult(products=[], upserted=3, unchanged=0)

    monkeypatch.setattr("app.scrapers.run_scraper", fake_run)

    r = web_client.post(
        "/app/m/finanzas/precios/actualizar",
        data={"supermercado": "super_selectos"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "flash=catalogo" in r.headers.get("location", "")
    assert called == ["super_selectos"]

    from app.db import finanzas_receipts as fr
    from app.db.schema import SUPERMERCADO_SELECTOS

    fr.upsert_supermarket_product(
        supermercado=SUPERMERCADO_SELECTOS,
        nombre="Yogurt Fresa",
        precio=0.65,
        sku_o_id_externo="y1",
    )
    r2 = web_client.get("/app/m/finanzas?q_precios=yogurt")
    assert r2.status_code == 200
    assert "Yogurt Fresa" in r2.text
