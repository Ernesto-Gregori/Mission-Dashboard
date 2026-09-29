"""El bot habla inglés solo si la cuenta lo eligió. El texto de origen sigue en español."""
from __future__ import annotations

from datetime import datetime

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def test_el_texto_plano_traduce_linea_a_linea_y_deja_el_dato():
    from app.i18n import traducir_plano

    gasto = "Anoté $35.00 en «café con María» → 🍽️ Comida (Supervivencia)."
    assert "café con María" in traducir_plano(gasto, "en")
    assert "Food" in traducir_plano(gasto, "en")
    assert "Survival" in traducir_plano(gasto, "en")
    assert "Anoté" not in traducir_plano(gasto, "en")
    assert traducir_plano(gasto, "es") == gasto
    assert traducir_plano(gasto, "") == gasto
    assert traducir_plano("Pareja", "en") == "Pareja"
    assert traducir_plano("Relaciones: sin cita hoy.", "en") == "Relationships: no date today."
    assert traducir_plano("⏰ Recordatorio: 10:00 · Dentista.", "en") == "⏰ Reminder: 10:00 · Dentista."
    menu = "Menú:\n• /briefing — foco del día"
    en = traducir_plano(menu, "en")
    assert "Menu:" in en
    assert "focus for the day" in en
    assert "/briefing" in en


def test_yes_y_el_boton_en_ingles_siguen_siendo_comandos():
    from app.telegram import _command_parts, _normalize_yes_no

    assert _normalize_yes_no("yes") is True
    assert _normalize_yes_no("sí") is True
    assert _normalize_yes_no("no") is False
    assert _command_parts("💸 Balance") == ("/saldo", "")
    assert _command_parts("💸 Saldo") == ("/saldo", "")
    assert _command_parts("✅ Habits") == ("/habitos", "")
    assert _command_parts("❓ Help") == ("/ayuda", "")


def test_el_bot_sigue_en_espanol_por_defecto(web_client):
    from app.telegram import handle_inbound

    _onboard(web_client)
    _link_admin("42")
    sent = []
    out = handle_inbound("42", text="/ayuda", update_id="es1", send_fn=lambda c, b: sent.append(b))
    assert "Menú:" in out
    assert sent and "Menú:" in sent[0]
    assert "Menu:" not in sent[0]


def test_el_bot_responde_en_ingles_si_la_cuenta_lo_eligio(web_client):
    from app.cuenta import guardar_idioma
    from app.telegram import handle_inbound

    _onboard(web_client)
    uid = _link_admin("42")
    guardar_idioma(uid, "en")
    sent = []
    out = handle_inbound("42", text="/ayuda", update_id="en1", send_fn=lambda c, b: sent.append(b))
    assert "Menú:" in out
    assert sent and "Menu:" in sent[0]
    assert "Menú:" not in sent[0]
    assert "/briefing" in sent[0]
    assert "focus for the day" in sent[0]


def test_el_teclado_sale_en_ingles(web_client, monkeypatch):
    from app.cuenta import guardar_idioma
    from app import telegram as tg

    _onboard(web_client)
    uid = _link_admin("99")
    guardar_idioma(uid, "en")
    calls = []
    monkeypatch.setattr(tg, "_secret", lambda name, default="": "123:test")
    monkeypatch.setattr(tg, "_api", lambda method, payload=None, **kw: calls.append(payload) or {"ok": True})
    assert tg.send_text("99", "Menú:", reply_markup=tg.reply_keyboard(uid), user_id=uid)
    textos = [b["text"] for b in calls[-1]["reply_markup"]["keyboard"][0]]
    assert calls[-1]["text"] == "Menu:"
    assert "💸 Balance" in textos
    assert "❓ Help" in textos
    assert "✅ Habits" in textos
    assert "💸 Saldo" not in textos


def test_el_menu_de_comandos_sigue_el_idioma(web_client, monkeypatch):
    from app.cuenta import guardar_idioma
    from app import telegram as tg

    _onboard(web_client)
    uid = _link_admin("42")
    guardar_idioma(uid, "en")
    calls = []
    monkeypatch.setattr(tg, "_api", lambda method, payload=None, **kw: calls.append(payload) or {"ok": True})
    tg._COMANDOS_CHAT.clear()
    tg.handle_inbound("42", text="/ayuda", update_id="cmd-en", send_fn=lambda _c, _b: None)
    menus = [c for c in calls if c and c.get("commands")]
    desc = {c["command"]: c["description"] for c in menus[-1]["commands"]}
    assert desc["briefing"] == "Focus for the day"
    assert desc["gasto"].startswith("Log an expense")
    assert "/gasto" in desc["gasto"]


def test_recordatorio_en_ingles_conserva_el_titulo(web_client):
    from app.cuenta import guardar_idioma
    from app.telegram import schedule_reminder, send_due_reminders

    _onboard(web_client)
    uid = _link_admin("42")
    guardar_idioma(uid, "en")
    schedule_reminder(uid, 1, "2030-01-10", "10:00", "Dentista", "42")
    sent = []
    assert send_due_reminders(now=datetime(2030, 1, 10, 9, 30), send_fn=lambda c, b: sent.append(b)) == 1
    assert sent == ["⏰ Reminder: 10:00 · Dentista."]
