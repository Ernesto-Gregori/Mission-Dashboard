"""Telegram v2 · finanzas: rubro real, saldo, ingreso, gastos, vencimientos, borrar."""
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


def _setup(client):
    _onboard(client)
    _link_admin("42")


def test_gasto_infiere_subcategoria_real(web_client):
    _setup(web_client)
    out = _say("/gasto 12.50 uber", "f1")
    assert "Transporte" in out and "Cambiar" not in out and "por defecto" not in out
    row = _rows("gastos_sobres")[0]
    assert row["sobre"] == "Supervivencia" and row["subcategoria"] == "Transporte"
    assert float(row["monto"]) == 12.5


def test_gasto_sin_rubro_avisa_y_cambia_con_boton(web_client):
    _setup(web_client)
    out = _say("/gasto 8 algo", "f2")
    assert "por defecto" in out and "Otro" in out
    row = _rows("gastos_sobres")[0]
    assert row["subcategoria"] == "Otro_Supervivencia"
    from app.telegram_actions.finanzas import catalogo

    idx = next(i for i, (_s, sub) in enumerate(catalogo()) if sub == "Comida")
    out = _click(f"c:{row['id']}:{idx}", "f3")
    assert "Comida" in out
    assert _rows("gastos_sobres")[0]["subcategoria"] == "Comida"


def test_modulo_finanzas_apagado_no_escribe(web_client):
    _setup(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    out = _say("/gasto 35 super", "f4")
    assert "apagado" in out and _rows("gastos_sobres") == []
    assert "Saldo" not in _say("/saldo", "f5") or "apagado" in _say("/saldo", "f6")


def test_ingreso_y_reemplazo(web_client):
    _setup(web_client)
    assert "800" in _say("/ingreso 800", "i1")
    assert _rows("gastos_sobres") == []
    pregunta = _say("/ingreso 900", "i2")
    assert "reemplazo" in pregunta and "800" in pregunta
    from app.db.finanzas import obtener_ingreso
    from app.timezone_config import hoy

    dia = hoy()
    from app.database import autenticar_usuario
    from app.tenant import set_current_user

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    assert obtener_ingreso(dia.month, dia.year) == 800
    assert "900" in _say("sí", "i3")
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    assert obtener_ingreso(dia.month, dia.year) == 900


def test_ingreso_sin_monto_no_escribe(web_client):
    _setup(web_client)
    assert "monto" in _say("/ingreso", "i4").lower()


def test_saldo_muestra_semaforo(web_client):
    _setup(web_client)
    _say("/ingreso 1000", "s1")
    _say("/gasto 100 super", "s2")
    out = _say("/saldo", "s3")
    assert "Ingreso $1000" in out and "Gastado $100" in out and "🟢" in out


def test_gastos_y_borrar_con_confirmacion(web_client):
    _setup(web_client)
    _say("/gasto 35 super", "g1")
    _say("/gasto 8 cafe", "g2")
    lista = _say("/gastos", "g3")
    assert lista.startswith("1.") or "\n1." in lista
    assert "35" in lista and "8" in lista
    assert "¿Borro el gasto 1?" in _say("/borrar 1", "g4")
    assert len(_rows("gastos_sobres")) == 2
    assert _say("no", "g5").startswith("Cancelado")
    assert len(_rows("gastos_sobres")) == 2
    _say("/borrar 1", "g6")
    assert "Borré" in _say("sí", "g7")
    assert len(_rows("gastos_sobres")) == 1


def test_borrar_sin_lista_no_escribe(web_client):
    _setup(web_client)
    _say("/gasto 35 super", "b1")
    out = _say("/borrar 1", "b2")
    assert "No encuentro" in out
    assert len(_rows("gastos_sobres")) == 1


def test_vencimientos_proximos_7(web_client):
    _setup(web_client)
    from app.database import autenticar_usuario
    from app.presupuesto import agregar_recurrente
    from app.tenant import set_current_user
    from app.timezone_config import hoy

    set_current_user(autenticar_usuario("tg_admin", "password1"))
    agregar_recurrente("Internet", "factura", 25, hoy().day, "Supervivencia")
    agregar_recurrente("Lejano", "factura", 10, (hoy().day + 10 - 1) % 28 + 1, "Supervivencia")
    out = _say("/vencimientos", "v1")
    assert "Internet" in out and "$25.00" in out
