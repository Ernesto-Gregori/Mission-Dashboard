"""Telegram v2 · ideas y lectura."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _say(text: str, uid: str, chat: str = "42", **kw) -> str:
    from app.telegram import handle_inbound

    kw.setdefault("parse_fn", lambda t: {"intent": "unknown"})
    return handle_inbound(chat, text=text, update_id=uid, send_fn=lambda c, b: None, **kw)


def _click(data: str, uid: str) -> str:
    return _say("", uid, callback_id="cb", callback_data=data, answer_fn=lambda _i: None)


def _setup(client, mods=None):
    _onboard(client)
    client.post(
        "/app/coach/activar",
        data={"modulos": mods or ["agenda", "sandbox", "biblioteca"]},
        follow_redirects=False,
    )
    _link_admin("42")


def test_idea_sin_texto_no_escribe(web_client):
    _setup(web_client)
    out = _say("/idea", "i1")
    assert "ejemplo" in out.lower()
    assert _rows("sandbox_ideas") == []


def test_idea_default_otros_y_deshacer(web_client):
    _setup(web_client)
    out = _say("/idea armar un estante", "i2")
    assert "Otros" in out and "estante" in out
    row = _rows("sandbox_ideas")[0]
    assert row["dominio"] == "Otros" and row["estado"] == "Idea"
    assert int(row["prioridad"]) == 3 and int(row["motivacion"]) == 3
    assert "Deshice" in _say("/deshacer", "i3")
    assert _rows("sandbox_ideas") == []


def test_idea_dominio_y_desconocido(web_client):
    _setup(web_client)
    out = _say("/idea script de backup #programacion", "i4")
    assert "Programacion" in out
    assert _rows("sandbox_ideas")[0]["dominio"] == "Programacion"
    assert "no conozco" in _say("/idea otra #hogar", "i5").lower()
    assert len(_rows("sandbox_ideas")) == 1
    lista = _say("/ideas", "i6")
    assert "script de backup" in lista and "Programacion" in lista


def test_modulo_sandbox_apagado(web_client):
    _setup(web_client, ["agenda"])
    assert "apagado" in _say("/idea una idea", "i7")
    assert _rows("sandbox_ideas") == []


def test_leer_pagina_y_ambiguedad(web_client):
    from app.database import autenticar_usuario
    from app.db.biblioteca import crear_libro_manual
    from app.tenant import set_current_user

    _setup(web_client)
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    crear_libro_manual("El Hobbit", estado="leyendo")
    crear_libro_manual("Romanos", estado="leyendo")
    crear_libro_manual("Romanos comentado", estado="catalogado")
    out = _say("/leer El Hobbit 40", "l1")
    assert "El Hobbit" in out and "40" in out
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    hobbit = next(r for r in _rows("libros") if r["titulo"] == "El Hobbit")
    assert int(hobbit["pagina_actual"]) == 40
    pregunta = _say("/leer roma 12", "l2")
    assert "varios" in pregunta
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    assert all(int(r["pagina_actual"] or 0) != 12 for r in _rows("libros") if "Romanos" in r["titulo"])
    out = _click("b:1:12", "l3")
    assert "página 12" in out
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    romanos = [r for r in _rows("libros") if "Romanos" in r["titulo"]]
    assert sorted(int(r["pagina_actual"] or 0) for r in romanos) == [0, 12]
    assert "Leyendo" in _say("/leyendo", "l4") and "El Hobbit" in _say("/leyendo", "l5")


def test_leer_sin_pagina_no_escribe(web_client):
    _setup(web_client)
    assert "página" in _say("/leer El Hobbit", "l6").lower()
    assert _rows("libros") == []


def test_modulo_biblioteca_apagado(web_client):
    _setup(web_client, ["agenda"])
    assert "apagado" in _say("/leyendo", "l7")
