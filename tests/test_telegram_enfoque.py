"""Telegram v2 · /enfoque marca el bloque de hoy."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str, **kw) -> str:
    from app.telegram import handle_inbound

    kw.setdefault("parse_fn", lambda t: {"intent": "unknown"})
    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None, **kw)


def _setup(client):
    _onboard(client)
    client.post("/app/coach/activar", data={"modulos": ["agenda", "salud", "finanzas", "deep_work"]})
    _link_admin("42")
    from app.database import autenticar_usuario
    from app.db.deep_work import crear_bloque
    from app.tenant import set_current_user
    from app.timezone_config import hoy

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    return crear_bloque("Estudio", "09:00", "11:00", [hoy().weekday() + 1], "Estudio", "#58a6ff")


def _estado(bloque_id: int) -> str:
    from app.database import autenticar_usuario
    from app.db.deep_work import bloques_para_fecha
    from app.tenant import set_current_user
    from app.timezone_config import hoy

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    bloque = next(b for b in bloques_para_fecha(str(hoy())) if int(b["id"]) == int(bloque_id))
    return bloque["estado"]


def test_lista_y_marca_completado(web_client):
    bid = _setup(web_client)
    out = _say("/enfoque", "e1")
    assert "Estudio" in out and "Pendiente" in out
    assert "Completado" in _say("", "e2", callback_id="cb", callback_data=f"e:{bid}:c", answer_fn=lambda _i: None)
    assert _estado(bid) == "Completado"


def test_parcial_y_postergado(web_client):
    bid = _setup(web_client)
    _say("", "e3", callback_id="cb", callback_data=f"e:{bid}:p", answer_fn=lambda _i: None)
    assert _estado(bid) == "Parcial"
    _say("", "e4", callback_id="cb2", callback_data=f"e:{bid}:o", answer_fn=lambda _i: None)
    assert _estado(bid) == "Postergado"


def test_modulo_apagado_no_escribe(web_client):
    bid = _setup(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    assert "apagado" in _say("/enfoque", "e5")
    assert "apagado" in _say("", "e6", callback_id="cb", callback_data=f"e:{bid}:c", answer_fn=lambda _i: None)
    assert _estado(bid) == "Pendiente"


def test_boton_de_otro_bloque_no_escribe(web_client):
    _setup(web_client)
    out = _say("", "e7", callback_id="cb", callback_data="e:99999:c", answer_fn=lambda _i: None)
    assert "no es de hoy" in out
