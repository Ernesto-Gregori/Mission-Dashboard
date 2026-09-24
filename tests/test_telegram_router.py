"""Telegram v2 · registro de acciones, router de intención y envío partido."""
from __future__ import annotations

import logging

import pytest

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _say(text: str, uid: str, parse_fn=None, chat: str = "42") -> str:
    from app.telegram import handle_inbound

    return handle_inbound(chat, text=text, update_id=uid, send_fn=lambda c, b: None, parse_fn=parse_fn)


@pytest.fixture()
def linked(web_client):  # noqa: F811 — _onboard activa agenda + salud
    _onboard(web_client)
    _link_admin("42")
    return web_client


@pytest.fixture()
def fake_actions(monkeypatch):
    """Dos acciones de prueba: una de un módulo activo (salud) y otra de uno apagado (biblioteca)."""
    from app import telegram_actions as acciones
    from app.telegram_actions import Accion, Respuesta

    calls: list[tuple[str, dict]] = []

    def make(clave: str, modulo: str) -> Accion:
        return Accion(
            clave=clave,
            comandos=(f"/{clave}",),
            modulo=modulo,
            ejecutar=lambda ctx, datos: calls.append((clave, datos)) or Respuesta(f"hecho {clave}"),
            llm_campos=f"campos de {clave}",
            parse=lambda args: {"x": args} if args else None,
            validar=lambda data: {"x": 1} if data.get("intent") == clave else None,
            uso=f"uso de {clave}",
        )

    monkeypatch.setattr(
        acciones, "REGISTRO", acciones.REGISTRO + [make("pulso", "salud"), make("leer", "biblioteca")]
    )
    return calls


# ── Registro y módulos ──────────────────────────────────────────────


def test_command_of_inactive_module_writes_nothing(linked, fake_actions):
    out = _say("/leer dune 40", "m1")
    assert "apagado" in out and "no guardé nada" in out
    assert fake_actions == []


def test_command_of_active_module_runs(linked, fake_actions):
    assert _say("/pulso 4", "m2") == "hecho pulso"
    assert fake_actions == [("pulso", {"x": "4", "_texto": "4"})]


def test_command_without_args_shows_usage(linked, fake_actions):
    assert _say("/pulso", "m3") == "uso de pulso"
    assert fake_actions == []


def test_llm_intent_for_inactive_module_is_ignored(linked, fake_actions):
    out = _say("terminé el capítulo", "m4", parse_fn=lambda t: {"intent": "leer"})
    assert "no entendí" in out.lower()
    assert fake_actions == []


def test_unknown_command_does_not_call_llm(linked):
    calls = []
    out = _say("/nada 35 super", "m5", parse_fn=lambda t: calls.append(t) or {"intent": "gasto", "monto": 35})
    assert "no entendí" in out.lower()
    assert calls == []
    assert _rows("gastos_sobres") == []


def test_prompt_lists_only_active_modules_with_weekday(linked, fake_actions, monkeypatch):
    from datetime import date

    from app.telegram import parse_intent

    prompts = []
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: True)
    monkeypatch.setattr(
        "app.ai_client.chat_simple", lambda msg, contexto="", max_tokens=500: prompts.append((msg, max_tokens)) or "{}"
    )
    monkeypatch.setattr("app.telegram._hoy", lambda: date(2026, 9, 25))
    from app.database import autenticar_usuario
    from app.tenant import clear_current_user, set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    try:
        assert parse_intent("hola") == {"intent": "unknown"}
    finally:
        clear_current_user()
    prompt, max_tokens = prompts[0]
    assert "- pulso: campos de pulso" in prompt
    assert "leer" not in prompt
    assert "gasto" in prompt and "tarea" in prompt
    assert "viernes 2026-09-25" in prompt
    assert max_tokens <= 200


# ── Validación del JSON del LLM ─────────────────────────────────────


@pytest.mark.parametrize(
    "llm",
    [
        {"intent": "gasto", "monto": "abc", "descripcion": "x"},
        {"intent": "gasto", "monto": -5},
        {"intent": "tarea", "titulo": "X", "fecha": "el viernes", "hora_inicio": "17:00"},
        {"intent": "tarea", "titulo": "X", "fecha": "2026-09-25", "hora_inicio": "25:99"},
        {"intent": "borrar_todo"},
        "no soy un dict",
    ],
)
def test_invalid_llm_output_writes_nothing(linked, llm):
    out = _say("algo raro", "v1", parse_fn=lambda t: llm)
    assert "no entendí" in out.lower()
    assert _rows("gastos_sobres") == []
    assert _rows("eventos_calendario") == []


def test_valid_llm_gasto_uses_llm_category(linked):
    out = _say("un cine con amigos", "v2", parse_fn=lambda t: {"intent": "gasto", "monto": 9, "categoria": "deseos"})
    assert out.startswith("Anoté $9.00")
    rows = _rows("gastos_sobres")
    assert len(rows) == 1 and rows[0]["descripcion"] == "un cine con amigos"


def test_groq_offline_fallback_text_is_unknown(linked, monkeypatch):
    monkeypatch.setattr("app.ai_client.api_key_configurada", lambda: True)
    monkeypatch.setattr("app.ai_client.chat_simple", lambda *a, **k: "🤖 Modo offline activo.")
    assert "no entendí" in _say("hola", "o1").lower()
    assert "Anoté $35.00" in _say("35 en super", "o2")
    assert "Foco" in _say("/briefing", "o3")


def test_groq_without_key_is_not_called(linked, monkeypatch):
    calls = []
    monkeypatch.setattr("app.ai_client.chat_simple", lambda *a, **k: calls.append(1) or "{}")
    _say("hola", "o4")
    assert calls == []


# ── Envío partido (C5) ──────────────────────────────────────────────


def test_split_message_respects_telegram_limit():
    from app.telegram import TG_MAX_MESSAGE, split_message

    body = "\n".join(f"línea {i} " + "x" * 90 for i in range(120))
    chunks = split_message(body)
    assert len(chunks) > 1
    assert all(len(c) <= TG_MAX_MESSAGE for c in chunks)
    assert "\n".join(chunks) == body


def test_split_message_without_newlines_and_empty():
    from app.telegram import split_message

    assert split_message("   ") == []
    chunks = split_message("y" * 9000, limit=4096)
    assert [len(c) for c in chunks] == [4096, 4096, 808]


def test_send_text_sends_chunks_keyboard_only_on_last(monkeypatch):
    from app import telegram as tg

    calls = []
    monkeypatch.setattr(tg, "_secret", lambda name, default="": "123:test")
    monkeypatch.setattr(tg, "_api", lambda method, payload=None, **kw: calls.append(payload) or {"ok": True})
    assert tg.send_text("42", "a" * 5000, reply_markup={"k": 1}) is True
    assert len(calls) == 2
    assert "reply_markup" not in calls[0] and calls[1]["reply_markup"] == {"k": 1}


# ── Observabilidad ──────────────────────────────────────────────────


def test_log_line_has_action_but_no_personal_text(linked, caplog):
    caplog.set_level(logging.INFO, logger="telegram")
    _say("35 en supermercado secreto", "l1", chat="42")
    lines = [r.getMessage() for r in caplog.records if r.name.endswith("telegram")]
    summary = [line for line in lines if "accion=" in line]
    assert summary and "accion=gasto" in summary[-1] and "ok=True" in summary[-1]
    assert "chat=42" in summary[-1]
    assert not any("secreto" in line for line in lines)
