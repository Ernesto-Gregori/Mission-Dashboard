"""El bot nombra las áreas y las pantallas como la app."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None)


def test_ayuda_acepta_el_nombre_visible_y_la_clave(web_client):
    _onboard(web_client)
    _link_admin("42")
    por_nombre = _say("/ayuda dinero", "v1")
    por_clave = _say("/ayuda finanzas", "v2")
    assert "/gasto" in por_nombre
    assert por_nombre == por_clave
    assert "apagada" not in por_nombre


def test_el_area_apagada_dice_su_nombre_y_donde_prenderla(web_client):
    _onboard(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]}, follow_redirects=False)
    _link_admin("42")
    out = _say("/ayuda dinero", "v3")
    assert "El área «Dinero» está apagada." in out
    assert "Cuenta → Configuración" in out
    assert "módulo" not in out.lower()
    assert "finanzas" not in out


def test_el_menu_senala_las_pantallas_de_la_app(web_client):
    _onboard(web_client)
    _link_admin("42")
    out = _say("/ayuda", "v4")
    assert "/ayuda dinero" in out
    assert "Cuenta → Configuración → Conexiones" in out
    assert "Usuarios → Telegram" not in out
    assert "finanzas" not in out


def test_estado_lista_nombres_no_claves(web_client):
    _onboard(web_client)
    _link_admin("42")
    out = _say("/estado", "v5")
    assert "Áreas:" in out
    for nombre in ("Dinero", "Cuerpo", "Revisión semanal"):
        assert nombre in out
    for clave in ("finanzas", "salud", "agenda", "deep_work"):
        assert clave not in out


def test_la_rutina_vacia_apunta_a_cuerpo(web_client):
    _onboard(web_client)
    _link_admin("42")
    out = _say("/rutina", "v6")
    assert "Cuerpo → Rutina" in out
    assert "en Salud" not in out


def test_el_ingles_traduce_el_nombre_del_area():
    from app.i18n import traducir_plano

    apagada = (
        "El área «Dinero» está apagada. "
        "Se prende en la app, en Cuenta → Configuración. No listo comandos."
    )
    en = traducir_plano(apagada, "en")
    assert "Money" in en
    assert "Account → Settings" in en
    assert "module" not in en.lower()

    guardada = (
        "El área «Cuerpo» está apagada, así que no guardé nada. "
        "Actívala en la app, en Cuenta → Configuración."
    )
    assert "Body" in traducir_plano(guardada, "en")
    assert traducir_plano("Áreas: Dinero, Cuerpo", "en") == "Areas: Money, Body"
    assert traducir_plano("Áreas: ninguna", "en") == "Areas: none"
    assert traducir_plano("Cuerpo: sin registro hoy.", "en") == "Body: no log today."
    assert traducir_plano("Relaciones: sin cita hoy.", "en") == "Relationships: no date today."
