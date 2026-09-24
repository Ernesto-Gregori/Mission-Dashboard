"""Telegram v2 · hábitos: lista, coincidencia difusa y fusión al marcar."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str, **kw) -> str:
    from app.telegram import handle_inbound

    kw.setdefault("parse_fn", lambda t: {"intent": "unknown"})
    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None, **kw)


def _seed():
    from app.database import autenticar_usuario
    from app.onboarding import aplicar_habitos_sugeridos
    from app.tenant import set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    aplicar_habitos_sugeridos(
        [
            {"clave": "leer", "label": "Leer", "emoji": "📖"},
            {"clave": "oracion", "label": "Oración", "emoji": "🙏"},
            {"clave": "oracion_noche", "label": "Oración de la noche", "emoji": "🌙"},
            {"clave": "ejercicio", "label": "Ejercicio", "emoji": "🏃"},
        ]
    )


def _setup(client):
    _onboard(client)
    _link_admin("42")
    _seed()


def _hechos() -> dict:
    from app.database import autenticar_usuario
    from app.ritual import habitos_hoy
    from app.tenant import set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    return habitos_hoy()


def test_lista_de_hoy(web_client):
    _setup(web_client)
    out = _say("/habitos", "h1")
    assert "·" in out and "Leer" in out and "Ejercicio" in out
    assert _hechos() == {}


def test_hecho_marca_uno_y_no_desmarca_el_otro(web_client):
    _setup(web_client)
    assert "Leer" in _say("/hecho leer", "h2")
    assert "Ejercicio" in _say("ya hice ejercicio", "h3")
    hechos = _hechos()
    assert hechos["leer"] is True and hechos["ejercicio"] is True
    assert hechos["oracion"] is False


def test_ya_lei_por_similitud(web_client):
    _setup(web_client)
    out = _say("ya leí", "h4")
    assert "Leer" in out and _hechos()["leer"] is True


def test_varios_candidatos_piden_boton_y_no_marcan(web_client):
    _setup(web_client)
    out = _say("/hecho ora", "h5")
    assert "varios" in out and _hechos() == {}
    elegido = _say("", "h6", callback_id="cb", callback_data="k:oracion_noche", answer_fn=lambda _i: None)
    assert "noche" in elegido.lower()
    hechos = _hechos()
    assert hechos["oracion_noche"] is True and hechos["oracion"] is False


def test_habito_inexistente_no_escribe(web_client):
    _setup(web_client)
    out = _say("/hecho volar", "h7")
    assert "No encontré" in out and _hechos() == {}


def test_deshacer_solo_el_ultimo(web_client):
    _setup(web_client)
    _say("/hecho leer", "h8")
    _say("/hecho ejercicio", "h9")
    assert "Deshice" in _say("/deshacer", "h10")
    hechos = _hechos()
    assert hechos["leer"] is True and hechos["ejercicio"] is False


def test_teclado_depende_de_finanzas(web_client):
    from app.database import autenticar_usuario
    from app.telegram import BTN_HABITOS, BTN_SALDO, reply_keyboard

    _setup(web_client)
    uid = int(autenticar_usuario("tg_admin", "password1")["id"])
    con = [b["text"] for b in reply_keyboard(uid)["keyboard"][0]]
    assert [BTN_HABITOS, BTN_SALDO] == [t for t in con if t in (BTN_HABITOS, BTN_SALDO)] or (
        BTN_SALDO in con and BTN_HABITOS in con
    )
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    sin = [b["text"] for b in reply_keyboard(uid)["keyboard"][0]]
    assert BTN_HABITOS in sin and BTN_SALDO not in sin


def test_boton_habitos_lista(web_client):
    _setup(web_client)
    assert "Hábitos de hoy" in _say("✅ Hábitos", "h11")
