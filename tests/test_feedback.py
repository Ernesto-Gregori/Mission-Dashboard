"""Después de guardar, la app lo dice; antes de borrar, pregunta."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user

PLANTILLAS = Path(__file__).resolve().parent.parent / "web/templates"


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "feedback.db"
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
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)
    from web.app import create_app

    application = create_app()
    with TestClient(application) as client:
        yield client
    clear_current_user()


def _onboard(client: TestClient, mods: list[str]) -> None:
    r = client.post(
        "/setup",
        data={"username": "feedback", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post("/app/coach/activar", data={"modulos": mods}, follow_redirects=False)


DESTRUCTIVO = re.compile(r"/(eliminar|borrar|archivar|desvincular|cancelar)\b")


def test_toda_accion_destructiva_pide_confirmacion():
    """Nada que borre datos se dispara con un solo clic."""
    sin_confirmar = []
    for plantilla in PLANTILLAS.rglob("*.html"):
        html = plantilla.read_text("utf-8")
        for tag in re.findall(r"<(?:form|button)[^>]*>", html):
            destino = re.search(r'(?:action|formaction)="([^"]+)"', tag)
            if not destino or not DESTRUCTIVO.search(destino.group(1)):
                continue
            if "confirm(" in tag:
                continue
            sin_confirmar.append(f"{plantilla.name}: {destino.group(1)}")
    assert sin_confirmar == []


GUARDADOS = (
    ("/app/m/biblioteca/nuevo", {"titulo": "Los hermanos Karamázov"}, "Libro agregado."),
    ("/app/m/deep_work/bloque", {"nombre": "Mañana profunda"}, "Bloque agregado."),
    (
        "/app/m/teologia/devocional",
        {"pasaje_referencia": "Juan 15:1-8", "fecha": "2026-09-28"},
        "Devocional guardado.",
    ),
)


@pytest.mark.parametrize("ruta,datos,aviso", GUARDADOS)
def test_guardar_avisa_en_pantalla(web_client, ruta, datos, aviso):
    _onboard(web_client, ["biblioteca", "deep_work", "teologia"])
    r = web_client.post(ruta, data=datos, follow_redirects=True)
    assert r.status_code == 200
    assert aviso in r.text
    # El aviso se consume: recargar no lo repite.
    assert aviso not in web_client.get(r.url.path).text


def test_si_la_agenda_falla_la_pantalla_lo_dice(web_client, monkeypatch):
    """Un fallo al leer la agenda no se puede confundir con un día vacío."""
    _onboard(web_client, ["agenda"])
    vacio = web_client.get("/app")
    assert "Nada agendado para hoy." in vacio.text

    def explota(*a, **kw):
        raise RuntimeError("turso no responde")

    monkeypatch.setattr("web.routers.dashboard.items_foco", explota)
    roto = web_client.get("/app")
    assert roto.status_code == 200
    assert "No se pudo leer tu agenda de hoy." in roto.text
    assert "Nada agendado para hoy." not in roto.text
    assert "turso no responde" not in roto.text
