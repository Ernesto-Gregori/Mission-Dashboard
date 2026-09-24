"""/ayuda por módulo, solo si está activo. El menú / cabe en 10."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None)


def test_menu_tiene_diez(web_client):
    from app.telegram import BOT_COMMANDS

    assert len(BOT_COMMANDS) <= 10
    nombres = {c["command"] for c in BOT_COMMANDS}
    assert {"start", "briefing", "hoy", "gasto", "tarea", "ayuda"} <= nombres


def test_ayuda_modulo_activo_sale_del_registro(web_client):
    _onboard(web_client)
    _link_admin("42")
    out = _say("/ayuda finanzas", "a1")
    assert "/gasto" in out and "/precio" in out
    assert "apagado" not in out


def test_ayuda_modulo_apagado_no_lista(web_client):
    _onboard(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    _link_admin("42")
    out = _say("/ayuda finanzas", "a2")
    assert "apagado" in out and "/gasto" not in out


def test_ayuda_tema_desconocido(web_client):
    _onboard(web_client)
    _link_admin("42")
    assert "no conozco" in _say("/ayuda cocina", "a3").lower()
