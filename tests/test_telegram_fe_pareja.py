"""Telegram v2 · oración, pareja y rutina. Sin comando de devocional."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _rows(table: str) -> list:
    from app.db.core import ejecutar

    return ejecutar(f"SELECT * FROM {table}", fetchall=True) or []


def _say(text: str, uid: str, **kw) -> str:
    from app.telegram import handle_inbound

    kw.setdefault("parse_fn", lambda t: {"intent": "unknown"})
    return handle_inbound("42", text=text, update_id=uid, send_fn=lambda c, b: None, **kw)


def _setup(client, mods=None):
    _onboard(client)
    client.post(
        "/app/coach/activar",
        data={"modulos": mods or ["agenda", "teologia", "matrimonio", "salud"]},
        follow_redirects=False,
    )
    _link_admin("42")


def test_orar_listar_y_respondida_confirma(web_client):
    _setup(web_client)
    assert "mamá" in _say("/orar salud de mamá", "p1")
    assert _rows("pedidos_oracion")[0]["estado"] == "Activo"
    lista = _say("/oraciones", "p2")
    assert "1. salud de mamá" in lista
    pregunta = _say("/respondida 1", "p3")
    assert "respondido" in pregunta and _rows("pedidos_oracion")[0]["estado"] == "Activo"
    assert "Cancelado" in _say("no", "p4")
    assert _rows("pedidos_oracion")[0]["estado"] == "Activo"
    assert "respondido" in _say("/respondida 1", "p5")
    assert "Marqué" in _say("sí", "p6")
    assert _rows("pedidos_oracion")[0]["estado"] == "Respondido"


def test_orar_sin_texto_y_modulo_apagado(web_client):
    _setup(web_client, ["agenda"])
    assert "apagado" in _say("/orar salud", "p7")
    assert _rows("pedidos_oracion") == []


def test_nota_y_conexion(web_client):
    _setup(web_client)
    assert "café" in _say("/nota le gusta el café", "n1")
    nota = _rows("matrimonio_notas")[0]
    assert nota["categoria"] == "Conversaciones_Pendientes"
    assert "30" in _say("/conexion 30", "n2")
    hab = _rows("matrimonio_habitos")[0]
    assert int(hab["tiempo_calidad_minutos"]) == 30
    assert hab["tipo_conexion"] == "Otro" and hab["iniciado_por"] == "Yo"
    assert "Deshice" in _say("/deshacer", "n3")
    assert _rows("matrimonio_notas") == []
    assert len(_rows("matrimonio_habitos")) == 1


def test_conexion_sin_minutos(web_client):
    _setup(web_client)
    assert "minutos" in _say("/conexion", "n4").lower()
    assert _rows("matrimonio_habitos") == []


def test_modulo_matrimonio_apagado(web_client):
    _setup(web_client, ["agenda"])
    assert "apagado" in _say("/nota un secreto", "n5")
    assert _rows("matrimonio_notas") == []


def test_rutina_vacia_y_con_plan(web_client):
    from app.database import autenticar_usuario
    from app.db.exercises import guardar_routine
    from app.tenant import set_current_user
    from app.timezone_config import hoy

    _setup(web_client)
    assert "no tenés" in _say("/rutina", "r1").lower()
    set_current_user(autenticar_usuario("tg_admin", "password1"))
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    guardar_routine(int(autenticar_usuario("tg_admin", "password1")["id"]), 3, 40, [], {dias[hoy().weekday()]: "pierna"})
    out = _say("/rutina", "r2")
    assert "40" in out and "pierna" in out


def test_no_hay_comando_devocional(web_client):
    _setup(web_client)
    assert "no entendí" in _say("/devocional juan 3", "d1").lower()
    assert _rows("devocionales") == []
