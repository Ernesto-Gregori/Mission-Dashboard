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


def test_meses_y_avisos_sueltos_pasan_a_ingles():
    meses = "<option>Ene</option><option>Mar</option><option>Abr</option><option>Ago</option><option>Dic</option>"
    out = traducir_html(meses)
    assert ">Jan</option>" in out
    assert ">Mar</option>" in out
    assert ">Apr</option>" in out
    assert ">Aug</option>" in out
    assert ">Dec</option>" in out
    assert "Wheel updated." in traducir_html("<p>Rueda actualizada.</p>")
    assert "Log saved." in traducir_html("<p>Bitácora guardada.</p>")
    assert "Settings saved." in traducir_html("<p>Configuración guardada.</p>")
    sugerido = "<p>Sugerido desde tus vencimientos de ingreso (Nómina). Guárdalo para usarlo este mes.</p>"
    assert "Suggested from your income bills (Nómina)" in traducir_html(sugerido)
    assert "Payment received. Active plan: Premium." in traducir_html(
        "<p>Pago recibido. Plan activo: Premium.</p>"
    )
    assert "Checkout cancelled." in traducir_html(
        "<p>Checkout cancelado. Puedes intentarlo cuando quieras.</p>"
    )


def test_el_resto_visible_pasa_a_ingles_y_conserva_lo_propio():
    ritual = (
        '<textarea id="ritual-a" placeholder="Tres cosas por las que estoy agradecido">'
        "ya escrito</textarea>"
    )
    out = traducir_html(ritual)
    assert 'placeholder="Three things I am grateful for"' in out
    assert ">ya escrito</textarea>" in out
    assert "The one thing that makes the day count" in traducir_html(
        '<textarea placeholder="Lo único que, si lo hago, el día ya valió"></textarea>'
    )
    assert "E.g. more legs, less shoulder, strength in 40 minutes" in traducir_html(
        '<textarea placeholder="Ej. más piernas, menos hombro, fuerza en 40 minutos"></textarea>'
    )
    assert "Life wheel · 0.0 / 10" in traducir_html("<h2>Rueda de la vida · 0.0 / 10</h2>")
    assert "💰 Finance — Income, expenses, bills, and a split if you want one." in traducir_html(
        "<li>💰 Finanzas — Ingreso, gastos, vencimientos y un reparto si quieres usarlo.</li>"
    )
    assert "⏱️ Deep Work — Deep focus blocks and a daily log." in traducir_html(
        "<li>⏱️ Deep Work — Bloques de enfoque profundo y registro diario.</li>"
    )
    alias = "<span>✝️ Teología / Devocional — Práctica espiritual, lectura y pedidos.</span>"
    alias_en = traducir_html(alias)
    assert "Teología / Devocional" in alias_en
    assert "Spiritual practice, reading, and requests." in alias_en
    assert "— Gratitude and intention on Today" in traducir_html(
        "<span> — Gratitud e intención en Hoy</span>"
    )
    assert "💪 Health" in traducir_html("<label>💪 Salud</label>")
    assert "💑 Connections" in traducir_html("<label>💑 Vínculos</label>")
    assert "🎯 Purpose" in traducir_html("<label>🎯 Propósito</label>")
    assert ">💑 Pareja</span>" in traducir_html("<span>💑 Pareja</span>")
    assert "Recent habits" in traducir_html("<span>Hábitos recientes</span>")
    assert ">Habits</span>" in traducir_html("<span>Hábitos</span>")
    assert "Deep Work this week" in traducir_html("<span>Deep Work de la semana</span>")
    assert 'aria-label="0-day streak"' in traducir_html('<p aria-label="0 días de racha">🔥 0</p>')
    assert "✝️ 0 days" in traducir_html("<strong>✝️ 0 días</strong>")
    cuota = "<p>\n    Una lectura de tus módulos juntos.\n    Cupo esta semana: 0/7.\n  </p>"
    assert "A reading of your modules together. Quota this week: 0/7." in traducir_html(cuota)
    assert "Maximum 100 MB." in traducir_html(
        "<p>Máximo 100 MB. Lo ideal es un solo ejercicio de 60 s o menos (se rechaza si supera 90 s).</p>"
    )
    assert "No token for your user." in traducir_html(
        "<p>Sin token para tu usuario. Conecta Google Fit o pega el JSON del token.</p>"
    )
    assert "Delete this expense?" in traducir_html(
        """<form onsubmit="return confirm('¿Eliminar gasto?')"></form>"""
    )
    assert ">Hacer ejercicio</label>" in traducir_html("<label>Hacer ejercicio</label>")
    assert ">Pasos mínimos</span>" in traducir_html("<span>Pasos mínimos</span>")
    assert ">🕯️ Práctica</span>" in traducir_html("<span>🕯️ Práctica</span>")
    assert ">Mar</option>" in traducir_html("<option>Mar</option>")
    assert ">matrimonio</span>" in traducir_html("<span>matrimonio</span>")
    assert ">Matrimonio</option>" in traducir_html('<option value="Matrimonio">Matrimonio</option>')
    assert ">/gasto 35 super</code>" in traducir_html("<code>/gasto 35 super</code>")
    assert "💾 Save day" in traducir_html("<button>💾 Guardar día</button>")
    assert "Last scrape: ok" in traducir_html("<p>Último scrape: ok</p>")
    assert "12 products" in traducir_html("<span>12 productos</span>")
    assert "· sleep 7.5h · ⚡8" in traducir_html("<span> · sueño 7.5h · ⚡8</span>")
    assert "Day 5 · 🏠 Alquiler · $100.00" in traducir_html("<span>Día 5 · 🏠 Alquiler · $100.00</span>")
    assert 'aria-label="Delete expense super"' in traducir_html(
        '<button aria-label="Eliminar gasto super">✕</button>'
    )
    assert "El quijote · p. 12/300" in traducir_html("<p>El quijote · pág. 12/300</p>")
    assert "p. 0/— · 4%" in traducir_html("<span>pág. 0/— · 4%</span>")
    assert ">Calisthenics</option>" in traducir_html('<option value="Calistenia">Calistenia</option>')
    assert 'value="Calistenia"' in traducir_html('<option value="Calistenia">Calistenia</option>')
    assert ">Chest</label>" in traducir_html("<label>Pecho</label>")
    assert "At home</option>" in traducir_html('<option value="En_casa"> En casa</option>')
    assert "🎊 Celebration" in traducir_html("<option>🎊 Celebracion</option>")
    assert ">Matrimonio</option>" in traducir_html('<option value="Matrimonio">Matrimonio</option>')
    assert ">Pasos mínimos</option>" in traducir_html('<option value="pasos">Pasos mínimos</option>')


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
    assert "Choose how to start · Mission" in traducir_html(
        "<title>Elige cómo empezar · Mission</title>"
    )
    assert ">💑 Pareja</span>" in traducir_html("<span>💑 Pareja</span>")
    assert "Quota this week: 1/3." in traducir_html("<p>Cupo esta semana: 1/3.</p>")
    assert "Week 28/09 — 04/10/2026" in traducir_html("<h2>Semana 28/09 — 04/10/2026</h2>")
    aviso = (
        "<div>Este módulo no está en tu cupo Free (máx. 3 módulos).\n"
        "  Pasa a Premium para desbloquearlo, o actívalo dentro de tu cupo cuando el Coach esté en HTMX.</div>"
    )
    assert "Free allowance (max. 3 modules)" in traducir_html(aviso)
    assert ">Mar</option>" in traducir_html("<option>Mar</option>")
    assert "Days in a row met: Hacer ejercicio" in traducir_html(
        "<p>Días seguidos cumpliendo: Hacer ejercicio</p>"
    )
    assert "3 envelopes · Sep 2026" in traducir_html("<p>3 sobres · Sep 2026</p>")
    assert ">SURVIVAL</strong>" in traducir_html("<strong>SUPERVIVENCIA</strong>")
    assert "Available: $0" in traducir_html("<p>Disponible: $0</p>")
    assert "🔴 SURVIVAL" in traducir_html("<option>🔴 SUPERVIVENCIA</option>")


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


def test_los_modulos_se_traducen_y_el_espanol_sigue_igual(web_client):
    _setup(web_client, "modulos")
    web_client.post("/app/coach/plantilla", data={"plantilla": "diario"}, follow_redirects=False)
    antes = web_client.get("/app/planificador")
    assert "Línea de tiempo arrastrable, sincronizada con Google Calendar." in antes.text
    web_client.get("/idioma?lang=en&next=/app/m/finanzas", follow_redirects=False)
    dinero = web_client.get("/app/m/finanzas")
    assert dinero.status_code == 200
    assert "Add expense" in dinero.text
    assert "Agregar gasto" not in dinero.text
    assert ">Jan</option>" in dinero.text
    assert ">Dec</option>" in dinero.text
    assert ">Mar</option>" in dinero.text
    plan = web_client.get("/app/planificador")
    assert "Draggable timeline, synced with Google Calendar." in plan.text
    assert "Línea de tiempo arrastrable" not in plan.text
    revision = web_client.get("/app/revision")
    assert "The week in numbers" in revision.text
    assert "Generate briefing" in revision.text
    assert "La semana en números" not in revision.text
    assert "Generar briefing" not in revision.text
    salud = web_client.get("/app/m/salud")
    assert "Save day" in salud.text or "Today's log" in salud.text
    assert "Registro del día" not in salud.text


def test_lectura_y_enfoque_en_ingles(web_client):
    _setup(web_client, "estudio")
    web_client.post("/app/coach/plantilla", data={"plantilla": "estudio"}, follow_redirects=False)
    web_client.get("/idioma?lang=en&next=/app/m/biblioteca", follow_redirects=False)
    libros = web_client.get("/app/m/biblioteca")
    assert libros.status_code == 200
    assert "No books yet. Add one under New." in libros.text
    assert "Sin libros" not in libros.text
    nuevo = web_client.get("/app/m/biblioteca?tab=nuevo")
    assert "Save book" in nuevo.text
    foco = web_client.get("/app/m/deep_work")
    assert "Focus blocks · daily log" in foco.text
    assert "Bloques de enfoque" not in foco.text
    config = web_client.get("/app/m/deep_work?tab=config")
    assert "Create block" in config.text


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
