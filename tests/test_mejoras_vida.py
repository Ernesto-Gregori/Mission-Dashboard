"""Notas, perfil del coach, categorías, semillas y jobs nocturnos."""
from __future__ import annotations

import re
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "vida_test.db"
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


def _onboard(client: TestClient) -> None:
    r = client.post(
        "/setup",
        data={"username": "vida", "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    client.post(
        "/app/coach/activar",
        data={"modulos": ["salud", "biblioteca", "finanzas", "deep_work"]},
        follow_redirects=False,
    )


def test_notas_crud(web_client):
    _onboard(web_client)
    page = web_client.get("/app/notas")
    assert page.status_code == 200
    assert "Tareas" in page.text
    assert "Ideas" in page.text

    creado = web_client.post(
        "/app/notas?tab=tareas",
        data={"titulo": "Llamar al médico", "cuerpo": "mañana"},
        follow_redirects=True,
    )
    assert "Llamar al médico" in creado.text
    match = re.search(r"/app/notas/(\d+)/editar", creado.text)
    assert match
    nota_id = match.group(1)

    editado = web_client.post(
        f"/app/notas/{nota_id}/editar?tab=tareas",
        data={"titulo": "Llamar hoy", "cuerpo": "ya", "estado": "abierta"},
        follow_redirects=True,
    )
    assert "Llamar hoy" in editado.text

    hecha = web_client.post(
        f"/app/notas/{nota_id}/hecha?tab=tareas",
        data={"hecha": "1"},
        follow_redirects=True,
    )
    assert "Reabrir" in hecha.text

    idea = web_client.post(
        "/app/notas?tab=notas",
        data={"titulo": "Idea de viaje"},
        follow_redirects=True,
    )
    assert "Idea de viaje" in idea.text

    borrada = web_client.post(
        f"/app/notas/{nota_id}/eliminar?tab=tareas",
        follow_redirects=True,
    )
    assert "Llamar hoy" not in borrada.text


def test_perfil_llega_al_coach(web_client):
    _onboard(web_client)
    pagina = web_client.get("/app/m/salud?tab=rutina")
    assert "Datos para el coach" in pagina.text
    r = web_client.post(
        "/app/m/salud/perfil",
        data={
            "peso_kg": "82.5",
            "altura_cm": "178",
            "edad": "34",
            "sexo": "hombre",
            "objetivo": "fuerza",
            "notas": "rodilla izquierda",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    from app.database import autenticar_usuario
    from app.exercise_routine import _build_prompt
    from app.perfil_fisico import leer, texto_para_coach

    uid = int(autenticar_usuario("vida", "password1")["id"])
    prompt = _build_prompt(
        dias=3,
        minutos=45,
        equipo=["peso corporal"],
        notas="",
        previous=None,
        perfil_txt=texto_para_coach(leer(uid)),
    )
    assert "82.5 kg" in prompt


def test_normalizar_categoria_alias():
    from app.db.biblioteca import normalizar_categoria

    assert normalizar_categoria("Teologia") == "Espiritualidad"
    assert normalizar_categoria("Programacion") == "Ciencia"
    assert normalizar_categoria("Matrimonio") == "Relaciones"
    assert normalizar_categoria("Salud") == "Salud"
    assert normalizar_categoria("cualquier cosa") == "Otros"


def test_sugerir_categoria_traduce_programacion(monkeypatch):
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: True)
    monkeypatch.setattr(
        "app.ai_client.chat_simple",
        lambda *args, **kwargs: (
            '{"categoria": "Programacion", "descripcion": "Un libro de codigo.", "temas": ["python"]}'
        ),
    )
    from app.biblioteca_ia import sugerir_categoria

    out = sugerir_categoria("Clean Code", "Robert Martin")
    assert out["categoria"] == "Ciencia"
    assert "codigo" in out["descripcion"]


def test_semillas_sin_codigo_ni_instituto(web_client):
    _onboard(web_client)
    from app.database import autenticar_usuario
    from app.db.core import ejecutar
    from app.multiuser import provision_user_defaults

    uid = int(autenticar_usuario("vida", "password1")["id"])
    ejecutar("DELETE FROM habitos_config WHERE user_id = ?", [uid])
    ejecutar("DELETE FROM bloques_fijos WHERE user_id = ?", [uid])
    provision_user_defaults(uid, seed_modules=True, only_if_empty=True)
    claves = [
        row["clave"]
        for row in (
            ejecutar(
                "SELECT clave FROM habitos_config WHERE user_id = ?",
                [uid],
                fetchall=True,
            )
            or []
        )
    ]
    assert "codigo" not in claves
    nombres = " ".join(
        row["nombre"]
        for row in (
            ejecutar(
                "SELECT nombre FROM bloques_fijos WHERE user_id = ?",
                [uid],
                fetchall=True,
            )
            or []
        )
    )
    assert "Instituto" not in nombres
    assert "Código" not in nombres


def test_fit_nocturno_una_vez_en_la_ventana(web_client, monkeypatch):
    _onboard(web_client)
    import app.nightly_jobs as jobs

    monkeypatch.setattr(jobs, "iso_ahora", lambda: "2026-09-30T22:10:00")
    llamadas = []

    def falso(fecha):
        llamadas.append(fecha)
        return True, "ok"

    monkeypatch.setattr("app.fit_import.importar_dia", falso)
    assert jobs.importar_fit_vencidos(datetime(2026, 9, 30, 10, 0)) == 0
    assert llamadas == []
    assert jobs.importar_fit_vencidos(datetime(2026, 9, 30, 22, 10)) == 1
    assert jobs.importar_fit_vencidos(datetime(2026, 9, 30, 22, 20)) == 0
    assert len(llamadas) == 1


def test_precios_nocturnos_una_vez(web_client, monkeypatch):
    _onboard(web_client)
    import app.nightly_jobs as jobs

    monkeypatch.setattr(jobs, "iso_ahora", lambda: "2026-09-30T03:15:00")
    llamadas = []

    def falso(key):
        llamadas.append(key)
        from app.scrapers.base import ScrapeResult

        return ScrapeResult(products=[])

    monkeypatch.setattr("app.scrapers.run_scraper", falso)
    assert jobs.actualizar_precios_si_toca(datetime(2026, 9, 30, 3, 15)) is True
    assert llamadas
    assert jobs.actualizar_precios_si_toca(datetime(2026, 9, 30, 3, 20)) is False


def test_en_ventana():
    from app.sync_horario import en_ventana

    dentro = datetime(2026, 9, 30, 22, 30)
    assert en_ventana(22, dentro, None) is True
    assert en_ventana(22, dentro, "2026-09-30T22:01:00") is False
    assert en_ventana(10, dentro, None) is False
    assert en_ventana(22, datetime(2026, 9, 30, 23, 20), None) is True
    assert en_ventana(22, datetime(2026, 9, 30, 23, 40), None) is False
