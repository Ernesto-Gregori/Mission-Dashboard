"""Inglés opcional y tokens de Google cifrados en reposo."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.i18n import traducir_html
from app.tenant import clear_current_user, set_current_user
from app.token_crypto import TokenIlegible, abrir, sellar


def test_sellar_no_deja_el_refresh_token_en_claro(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    secreto = '{"refresh_token":"refresh-secret-xyz","token":"access-token"}'
    cerrado = sellar(secreto)
    assert cerrado.startswith("enc:v1:")
    assert "refresh-secret-xyz" not in cerrado
    assert "refresh_token" not in cerrado
    assert abrir(cerrado) == secreto
    assert sellar(cerrado) == cerrado


def test_json_legado_sigue_abriendo_y_un_sobre_alterado_falla(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-please-change")
    plano = '{"refresh_token":"plain-legacy"}'
    assert abrir(plano) == plano
    cerrado = sellar("otro-secreto")
    with pytest.raises(TokenIlegible):
        abrir(cerrado[:-8] + "xxxxxxxx")


def test_html_ingles_traduce_nodos_y_deja_alias_y_values():
    html = (
        '<p>Hoy</p><p>3 módulos activos</p>'
        '<input value="Hoy" placeholder="Usuario">'
        '<span>Teología / Devocional</span>'
        '<span>Salud &amp; Energía</span>'
        '<span>Fe</span><span>Pareja</span>'
        '<script>if (a < b) { return "Hoy"; }</script>'
        '<textarea>Hoy</textarea>'
    )
    out = traducir_html(html)
    assert "<p>Today</p>" in out
    assert "<p>3 active modules</p>" in out
    assert 'value="Hoy"' in out
    assert 'placeholder="Username"' in out
    assert "Teología / Devocional" in out
    assert "Salud &amp; Energía" in out
    assert ">Fe</span>" in out
    assert ">Pareja</span>" in out
    assert 'return "Hoy;"' not in out
    assert 'return "Hoy"' in out
    assert "<textarea>Hoy</textarea>" in out
    assert "<textarea>Today</textarea>" not in out


@pytest.fixture()
def web_client(monkeypatch):
    td = Path(tempfile.mkdtemp())
    db_path = td / "i18n.db"
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


def test_el_idioma_por_defecto_sigue_en_espanol(web_client):
    page = web_client.get("/setup")
    assert page.status_code == 200
    assert 'lang="es"' in page.text
    assert "Primer acceso" in page.text
    assert "First sign-in" not in page.text
    assert "htmx.min.js" in page.text


def test_cookie_de_idioma_traduce_el_alta_y_el_aviso_legal(web_client):
    salto = web_client.get("/idioma?lang=en&next=/setup", follow_redirects=False)
    assert salto.status_code == 303
    assert salto.headers["location"].endswith("/setup")
    cookie = salto.headers["set-cookie"].lower()
    assert "mission_lang=en" in cookie
    assert "httponly" not in cookie
    page = web_client.get("/setup")
    assert 'lang="en"' in page.text
    assert "First sign-in" in page.text
    assert "Primer acceso" not in page.text
    assert 'name="username"' in page.text
    assert page.text.strip().endswith("</html>")
    abierto = web_client.get("/idioma?lang=en&next=//evil.example", follow_redirects=False)
    assert abierto.headers["location"].endswith("/app")
    legal = web_client.get("/terminos")
    assert "This legal text is in Spanish." in legal.text
    assert "El tablero es privado." in legal.text


def test_la_preferencia_guardada_gana_a_la_cookie(web_client):
    _setup(web_client)
    web_client.post("/app/coach/plantilla", data={"plantilla": "blanco"}, follow_redirects=False)
    web_client.get("/idioma?lang=en&next=/app", follow_redirects=False)
    hoy = web_client.get("/app")
    assert ">Today</a>" in hoy.text
    assert ">Settings</a>" in hoy.text
    assert ">Sign out</button>" in hoy.text
    assert ">Hoy</a>" not in hoy.text
    assert ">Configuración</a>" not in hoy.text
    assert "0 active modules" in hoy.text
    cfg = web_client.get("/app/configuracion")
    assert "Language" in cfg.text
    from app.db.core import ejecutar

    fila = ejecutar("SELECT idioma FROM user_prefs WHERE user_id = 1", fetchall=True)
    assert fila[0]["idioma"] == "en"
    ejecutar("UPDATE user_prefs SET idioma = 'es' WHERE user_id = 1")
    web_client.cookies.set("mission_lang", "en")
    espanol = web_client.get("/app")
    assert ">Hoy</a>" in espanol.text
    assert ">Today</a>" not in espanol.text


def test_ingles_conserva_el_script_de_finanzas(web_client):
    _setup(web_client, "money")
    web_client.post("/app/coach/plantilla", data={"plantilla": "diario"}, follow_redirects=False)
    web_client.get("/idioma?lang=en&next=/app/m/finanzas", follow_redirects=False)
    page = web_client.get("/app/m/finanzas")
    assert page.status_code == 200
    assert "function fillSubs()" in page.text
    assert "innerHTML" in page.text
    assert ">Money</a>" in page.text


def test_token_de_google_se_guarda_cifrado_y_el_plano_se_migra(web_client, monkeypatch, tmp_path):
    _setup(web_client)
    import app.google_fit as gf
    from app.database import ejecutar

    monkeypatch.setattr(gf, "TOKEN_FILE", tmp_path / "token_fit.json")
    set_current_user({"id": 1, "username": "persona"})
    secreto = "refresh-secret-xyz"
    assert gf._save_token_dict(
        {"refresh_token": secreto, "token": "access", "client_id": "c", "client_secret": "s"}
    )
    rows = ejecutar("SELECT token_json FROM oauth_tokens WHERE user_id = 1", fetchall=True)
    assert rows[0]["token_json"].startswith("enc:v1:")
    assert secreto not in rows[0]["token_json"]
    disco = (tmp_path / "token_fit_u1.json").read_text()
    assert disco.startswith("enc:v1:")
    assert secreto not in disco
    data = gf._load_token_from_db()
    assert data["refresh_token"] == secreto

    legado = json.dumps({"refresh_token": "plain-legacy", "token": "t"})
    ejecutar(
        "UPDATE oauth_tokens SET token_json = ? WHERE user_id = 1 AND provider = ?",
        [legado, gf.PROVIDER],
    )
    migrado = gf._load_token_from_db()
    assert migrado["refresh_token"] == "plain-legacy"
    rows = ejecutar("SELECT token_json FROM oauth_tokens WHERE user_id = 1", fetchall=True)
    assert rows[0]["token_json"].startswith("enc:v1:")
    assert "plain-legacy" not in rows[0]["token_json"]

    ejecutar(
        "UPDATE oauth_tokens SET token_json = ? WHERE user_id = 1 AND provider = ?",
        ["enc:v1:alterado", gf.PROVIDER],
    )
    assert gf._load_token_from_db() is None
