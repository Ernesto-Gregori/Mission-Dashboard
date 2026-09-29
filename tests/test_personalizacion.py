"""Configuración, plantillas y datos de la cuenta."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tenant import clear_current_user


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "personalizacion.db"
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


def _setup(client: TestClient, username: str = "persona") -> None:
    r = client.post(
        "/setup",
        data={"username": username, "password": "password1", "password2": "password1"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)


def test_la_rueda_oculta_un_area_y_acepta_otra(web_client):
    _setup(web_client, "rueda")
    web_client.post("/app/coach/plantilla", data={"plantilla": "blanco"}, follow_redirects=False)
    base = ["fe", "matrimonio", "salud", "finanzas", "trabajo", "relaciones", "descanso", "proposito"]
    datos = {k: "4" for k in base}
    datos["fe"] = "9"
    primera = web_client.post("/app/rueda", data=datos, follow_redirects=True)
    assert primera.status_code == 200
    assert 'name="fe" type="number" min="0" max="10" step="1" value="9"' in primera.text
    on = [k for k in base if k != "descanso"]
    guardado = web_client.post(
        "/app/configuracion",
        data={
            "moneda": "USD",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "activo": ["rueda"],
            "hora_desde": "6",
            "hora_hasta": "22",
            "rueda_areas": "1",
            "rueda_on": on,
            "rueda_nueva": "Creatividad",
            "rueda_nueva_emoji": "🎨",
        },
        follow_redirects=True,
    )
    assert guardado.status_code == 200
    revision = web_client.get("/app/revision").text
    assert 'name="descanso"' not in revision
    assert 'name="creatividad"' in revision
    assert "Creatividad" in revision
    puntuar = {k: "4" for k in on}
    puntuar["fe"] = "9"
    puntuar["creatividad"] = "8"
    web_client.post("/app/rueda", data=puntuar, follow_redirects=True)
    otra = web_client.get("/app/revision").text
    assert 'name="creatividad" type="number" min="0" max="10" step="1" value="8"' in otra
    assert 'name="fe" type="number" min="0" max="10" step="1" value="9"' in otra
    web_client.post(
        "/app/configuracion",
        data={
            "activo": ["rueda"],
            "moneda": "USD",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "hora_desde": "6",
            "hora_hasta": "22",
        },
        follow_redirects=True,
    )
    sigue = web_client.get("/app/revision").text
    assert 'name="creatividad"' in sigue
    assert 'name="descanso"' not in sigue


def test_la_rueda_no_baja_de_tres_areas(web_client):
    _setup(web_client, "ruedamin")
    web_client.post("/app/coach/plantilla", data={"plantilla": "blanco"}, follow_redirects=False)
    r = web_client.post(
        "/app/configuracion",
        data={
            "moneda": "USD",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "activo": ["rueda"],
            "hora_desde": "6",
            "hora_hasta": "22",
            "rueda_areas": "1",
            "rueda_on": ["fe", "salud"],
        },
        follow_redirects=True,
    )
    assert r.status_code == 400
    assert "al menos 3" in r.text
    assert 'name="descanso"' in web_client.get("/app/revision").text


def test_en_blanco_no_siembra_habitos_ni_areas(web_client):
    _setup(web_client)
    r = web_client.post(
        "/app/coach/plantilla",
        data={"plantilla": "blanco"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    from app.db.core import ejecutar

    habitos = ejecutar("SELECT COUNT(*) AS n FROM habitos_config", fetchall=True)
    assert int(habitos[0]["n"]) == 0
    activos = ejecutar(
        "SELECT modulo FROM user_modulos WHERE activo = 1",
        fetchall=True,
    ) or []
    assert [r["modulo"] for r in activos] == []
    hoy = web_client.get("/app")
    assert hoy.status_code == 200
    assert "Todavía no activaste áreas" in hoy.text
    cfg = web_client.get("/app/configuracion?tab=rueda").text
    assert cfg.count('value="Relaciones"') == 1
    assert 'value="Vínculos"' in cfg


def test_plantilla_diario_solo_siembra_lo_suyo(web_client):
    _setup(web_client, "diario")
    r = web_client.post(
        "/app/coach/plantilla",
        data={"plantilla": "diario"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    from app.db.core import ejecutar

    mods = {
        row["modulo"]
        for row in ejecutar(
            "SELECT modulo FROM user_modulos WHERE activo = 1",
            fetchall=True,
        )
        or []
    }
    assert mods == {"finanzas", "salud"}
    labels = [
        row["label"]
        for row in ejecutar("SELECT label FROM habitos_config", fetchall=True) or []
    ]
    assert labels == ["Movimiento"]
    assert "Devocional" not in labels


def test_fallback_sin_areas_no_agrega_teologia(monkeypatch):
    from app.onboarding import _sugerencia_fallback

    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: False)
    fb = _sugerencia_fallback({"areas": []})
    assert fb["modulos"] == ["agenda"]
    assert fb["habitos"] == []
    assert "05:45" not in json.dumps(fb)


def test_configuracion_apaga_un_area_sin_borrar_sus_datos(web_client):
    _setup(web_client, "cfg")
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["matrimonio", "finanzas"]},
        follow_redirects=False,
    )
    from app.db.core import ejecutar
    from app.timezone_config import hoy as _hoy

    ejecutar(
        """
        INSERT INTO matrimonio_citas (user_id, fecha, titulo, ambito)
        VALUES (1, ?, 'Cena secreta', 'Matrimonio')
        """,
        [str(_hoy())],
    )
    page = web_client.get("/app/configuracion")
    assert page.status_code == 200
    assert "Configuración" in page.text
    r = web_client.post(
        "/app/configuracion",
        data={
            "activo": ["finanzas", "ritual", "rueda", "alma"],
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "hora_desde": "6",
            "hora_hasta": "22",
            "moneda": "USD",
            "metodo": "sobres",
            "cat_clave": ["Supervivencia", "Futuro_Hogar", "Ministerio_Extras"],
            "cat_nombre_Supervivencia": "SUPERVIVENCIA",
            "cat_nombre_Futuro_Hogar": "FUTURO Y HOGAR",
            "cat_nombre_Ministerio_Extras": "MINISTERIO Y EXTRAS",
        },
        follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    lado = web_client.get("/app").text
    assert "Dinero" in lado
    assert "Relaciones" not in lado
    queda = ejecutar("SELECT COUNT(*) AS n FROM matrimonio_citas", fetchall=True)
    assert int(queda[0]["n"]) == 1


def test_habito_en_dias_concretos_solo_sale_esos_dias(web_client):
    _setup(web_client, "dias")
    web_client.post("/app/coach/plantilla", data={"plantilla": "blanco"}, follow_redirects=False)
    from app.ritual import crear_habito, listar_habitos, listar_habitos_config

    ok, _ = crear_habito("Piano", user_id=1)
    assert ok
    clave = listar_habitos_config(1)[0]["clave"]
    inicial = web_client.get("/app/configuracion?tab=dia").text
    assert f'id="freq-days-{clave}" hidden' in inicial
    vacio = web_client.post(
        "/app/configuracion",
        data={
            "moneda": "USD",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "hora_desde": "6",
            "hora_hasta": "22",
            f"freq_{clave}": "custom",
        },
        follow_redirects=True,
    )
    assert vacio.status_code == 400
    assert "Elige al menos un día." in vacio.text
    assert listar_habitos(1, fecha="2026-09-29")
    guardado = web_client.post(
        "/app/configuracion",
        data={
            "moneda": "USD",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "hora_desde": "6",
            "hora_hasta": "22",
            f"freq_{clave}": "custom",
            f"freqdia_{clave}": ["mie", "lun"],
        },
        follow_redirects=True,
    )
    assert guardado.status_code == 200
    assert listar_habitos(1, fecha="2026-09-28")
    assert listar_habitos(1, fecha="2026-09-30")
    assert listar_habitos(1, fecha="2026-09-29") == []
    web_client.post(
        f"/app/coach/habitos/{clave}/editar",
        data={"label": "Piano suave", "emoji": "🎹", "hora": ""},
        follow_redirects=False,
    )
    assert listar_habitos(1, fecha="2026-09-29") == []
    assert listar_habitos(1, fecha="2026-09-28")
    pagina = web_client.get("/app/configuracion?tab=dia").text
    assert 'value="custom" selected' in pagina or "selected>Días concretos" in pagina
    assert f'id="freq-days-{clave}" hidden' not in pagina
    assert "Solo se guardan si eliges Días concretos." in pagina


def test_habito_entre_semana_no_sale_el_domingo(web_client):
    _setup(web_client, "hab")
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]}, follow_redirects=False)
    from app.ritual import crear_habito, listar_habitos

    ok, _ = crear_habito("Lectura corta", frecuencia="lun,mar,mie,jue,vie", user_id=1)
    assert ok
    assert listar_habitos(1, fecha="2026-09-27") == []
    assert listar_habitos(1, fecha="2026-09-28")


def test_categoria_nueva_acepta_un_gasto(web_client):
    _setup(web_client, "dinero")
    web_client.post("/app/coach/activar", data={"modulos": ["finanzas"]}, follow_redirects=False)
    web_client.post(
        "/app/configuracion",
        data={
            "activo": ["finanzas"],
            "moneda": "EUR",
            "metodo": "sobres",
            "ritual_a": "Gratitud",
            "ritual_b": "Intención",
            "hora_desde": "8",
            "hora_hasta": "20",
            "cat_clave": ["Supervivencia"],
            "cat_nombre_Supervivencia": "Casa",
            "cat_nueva": "Mascotas",
        },
        follow_redirects=False,
    )
    r = web_client.post(
        "/app/m/finanzas/gasto",
        data={
            "fecha": "2026-09-28",
            "sobre": "Mascotas",
            "subcategoria": "General",
            "descripcion": "alimento",
            "monto": "12",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "alimento" in r.text
    assert "€" in r.text


def test_exportar_y_borrar_la_propia_cuenta(web_client):
    _setup(web_client, "borrar")
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]}, follow_redirects=False)
    exported = web_client.get("/app/configuracion/exportar")
    assert exported.status_code == 200
    data = exported.json()
    assert data["tablas"]["usuarios"][0]["username"] == "borrar"
    assert "password_hash" not in data["tablas"]["usuarios"][0]
    mal = web_client.post(
        "/app/configuracion/borrar",
        data={"password": "no-es"},
        follow_redirects=False,
    )
    assert mal.status_code in (303, 307)
    assert "/app/configuracion" in mal.headers["location"]
    ok = web_client.post(
        "/app/configuracion/borrar",
        data={"password": "password1"},
        follow_redirects=False,
    )
    assert ok.status_code in (303, 307)
    assert "/login" in ok.headers["location"]
    from app.db.core import ejecutar

    queda = ejecutar("SELECT COUNT(*) AS n FROM usuarios WHERE username = 'borrar'", fetchall=True)
    assert int(queda[0]["n"]) == 0


def test_cada_pestana_guarda_solo_lo_suyo(web_client):
    _setup(web_client, "pestanas")
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["finanzas", "salud"]},
        follow_redirects=False,
    )
    areas = web_client.get("/app/configuracion")
    assert areas.status_code == 200
    assert 'name="seccion" value="areas"' in areas.text
    assert 'name="moneda"' not in areas.text
    assert 'href="/app/configuracion?tab=dinero"' in areas.text
    for tab, marca in (
        ("dia", 'name="seccion" value="dia"'),
        ("dinero", 'name="moneda"'),
        ("rueda", 'name="seccion" value="rueda"'),
        ("datos", 'id="borrar"'),
    ):
        cuerpo = web_client.get(f"/app/configuracion?tab={tab}").text
        assert marca in cuerpo
    web_client.post(
        "/app/configuracion",
        data={"seccion": "dinero", "moneda": "EUR", "metodo": "sobres"},
        follow_redirects=False,
    )
    from app.cuenta import leer_prefs
    from app.onboarding import modulos_activos

    assert leer_prefs(1)["moneda"] == "EUR"
    assert "finanzas" in modulos_activos(1)
    web_client.post(
        "/app/configuracion",
        data={"seccion": "areas", "activo": ["salud", "ritual", "rueda", "alma"], "idioma": "es"},
        follow_redirects=False,
    )
    assert leer_prefs(1)["moneda"] == "EUR"
    assert modulos_activos(1) == {"salud"}
