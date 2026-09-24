"""Telegram v2 · salud: escritura parcial y comandos /sueno /energia /ejercicio /salud."""
from __future__ import annotations

from tests.test_telegram import _link_admin, _onboard, web_client  # noqa: F401


def _say(text: str, uid: str) -> str:
    from app.telegram import handle_inbound

    return handle_inbound(
        "42",
        text=text,
        update_id=uid,
        send_fn=lambda c, b: None,
        parse_fn=lambda t: {"intent": "unknown"},
    )


def _user():
    from app.database import autenticar_usuario
    from app.tenant import set_current_user

    return set_current_user(autenticar_usuario("tg_admin", "password1"))


def _setup(client):
    _onboard(client)
    _link_admin("42")
    _user()


def test_parcial_no_borra_el_resto_del_dia(web_client):
    _setup(web_client)
    from app.db.salud import actualizar_registro_salud_parcial, guardar_registro_salud, obtener_registro_salud
    from app.timezone_config import hoy

    dia = str(hoy())
    assert guardar_registro_salud(dia, {"horas_sueno": 6, "hizo_ejercicio": True, "tipo_ejercicio": "pecho"})
    assert actualizar_registro_salud_parcial(dia, {"energia_manana": 4})
    row = obtener_registro_salud(dia)
    assert float(row["horas_sueno"]) == 6
    assert int(row["hizo_ejercicio"]) == 1
    assert row["tipo_ejercicio"] == "pecho"
    assert int(row["energia_manana"]) == 4


def test_guardar_directo_si_borra(web_client):
    """Documenta el bug que la función parcial evita."""
    _setup(web_client)
    from app.db.salud import guardar_registro_salud, obtener_registro_salud
    from app.timezone_config import hoy

    dia = str(hoy())
    guardar_registro_salud(dia, {"horas_sueno": 8, "hizo_ejercicio": True})
    guardar_registro_salud(dia, {"energia_manana": 3})
    row = obtener_registro_salud(dia)
    assert row["horas_sueno"] is None
    assert int(row["hizo_ejercicio"]) == 0


def test_comandos_fusionan(web_client):
    _setup(web_client)
    assert "7.5" in _say("/sueno 7.5 calidad 4", "s1")
    assert "4/5" in _say("/energia 4", "s2")
    assert "pierna" in _say("/ejercicio pierna 45 min", "s3")
    from app.db.salud import obtener_registro_salud
    from app.timezone_config import hoy

    _user()
    row = obtener_registro_salud(str(hoy()))
    assert float(row["horas_sueno"]) == 7.5
    assert int(row["calidad_sueno"]) == 4
    assert int(row["energia_manana"]) == 4
    assert int(row["hizo_ejercicio"]) == 1
    assert row["tipo_ejercicio"] == "pierna"
    assert int(row["duracion_minutos"]) == 45
    resumen = _say("/salud", "s4")
    assert "7.5" in resumen and "Racha" in resumen


def test_argumentos_invalidos_no_escriben(web_client):
    _setup(web_client)
    assert "horas" in _say("/sueno", "s5").lower()
    assert "1 al 5" in _say("/energia 9", "s6")
    assert "qué hiciste" in _say("/ejercicio", "s7")
    from app.db.salud import obtener_registro_salud
    from app.timezone_config import hoy

    _user()
    assert obtener_registro_salud(str(hoy())) is None


def test_modulo_apagado_no_escribe(web_client):
    _setup(web_client)
    web_client.post("/app/coach/activar", data={"modulos": ["agenda"]})
    out = _say("/sueno 8", "s8")
    assert "apagado" in out
    from app.db.salud import obtener_registro_salud
    from app.timezone_config import hoy

    _user()
    assert obtener_registro_salud(str(hoy())) is None
