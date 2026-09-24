"""Telegram v2 · briefing por módulos. Fe, pareja y salud quedan fuera salvo opt-in."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say() -> str:
    from app.telegram import handle_inbound

    return handle_inbound(
        "42", text="/briefing", update_id="bf", send_fn=lambda c, b: None, parse_fn=lambda t: {"intent": "unknown"}
    )


def _uid() -> int:
    from app.database import autenticar_usuario

    return int(autenticar_usuario("tg_admin", "password1")["id"])


def _como_user():
    from app.database import autenticar_usuario
    from app.tenant import set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))


def test_por_defecto_omite_fe_pareja_y_salud(web_client):
    _onboard(web_client)
    _link_admin("42")
    _como_user()
    from app.db.teologia import agregar_pedido
    from app.timezone_config import hoy

    agregar_pedido("Salud de mamá", "", "Familia", 3, [hoy().weekday() + 1])
    out = _say()
    assert out.startswith("Foco ")
    assert "Agenda:" in out and "Hábitos" in out
    assert "Oración" not in out and "Pareja" not in out and "Salud:" not in out


def test_opt_in_muestra_oracion_y_enfoque(web_client):
    _onboard(web_client)
    web_client.post(
        "/app/coach/activar",
        data={"modulos": ["agenda", "salud", "finanzas", "teologia", "deep_work"]},
    )
    _link_admin("42")
    _como_user()
    from app.db.deep_work import crear_bloque
    from app.db.teologia import agregar_pedido
    from app.db.telegram_state import guardar_briefing_extra
    from app.timezone_config import hoy

    agregar_pedido("Salud de mamá", "", "Familia", 3, [hoy().weekday() + 1])
    crear_bloque("Estudio", "09:00", "11:00", [hoy().weekday() + 1], "Estudio", "#58a6ff")
    assert guardar_briefing_extra(_uid(), ["teologia"]) is True
    assert guardar_briefing_extra(_uid(), ["no-existe"]) is False
    out = _say()
    assert "Oración: Salud de mamá" in out
    assert "Enfoque: 09:00 Estudio" in out
    assert "Salud:" not in out


def test_finanzas_muestra_sobre_y_vencimiento(web_client):
    _onboard(web_client)
    _link_admin("42")
    _como_user()
    from app.presupuesto import agregar_recurrente
    from app.timezone_config import hoy

    agregar_recurrente("Internet", "factura", 25, hoy().day)
    out = _say()
    assert "Internet" in out and "Vencimientos" in out
