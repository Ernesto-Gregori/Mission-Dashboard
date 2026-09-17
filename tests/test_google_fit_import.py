"""Importación Google Fit: aggregate int millis, fuentes y avisos Health Connect."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.google_fit import (
    _aggregate_body,
    _parse_hr_summary_point,
    _scopes_faltantes,
    _sum_best_int,
    obtener_datos_dia,
    obtener_ejercicio,
    obtener_frecuencia_cardiaca,
    obtener_sueno,
)


def test_aggregate_body_usa_int_no_string():
    body = _aggregate_body("com.google.step_count.delta", 1000, 2000)
    assert isinstance(body["startTimeMillis"], int)
    assert isinstance(body["endTimeMillis"], int)
    assert body["startTimeMillis"] == 1000
    assert body["bucketByTime"]["durationMillis"] == 86400000
    assert body["aggregateBy"][0]["dataTypeName"] == "com.google.step_count.delta"
    assert "dataSourceId" not in body["aggregateBy"][0]

    body2 = _aggregate_body(
        "com.google.step_count.delta",
        1,
        2,
        data_source_id="derived:com.google.step_count.delta:com.google.android.gms:estimated_steps",
    )
    assert (
        body2["aggregateBy"][0]["dataSourceId"]
        == "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
    )


def test_scopes_faltantes():
    full = SimpleNamespace(
        scopes=[
            "https://www.googleapis.com/auth/fitness.activity.read",
            "https://www.googleapis.com/auth/fitness.sleep.read",
            "https://www.googleapis.com/auth/fitness.heart_rate.read",
        ]
    )
    assert _scopes_faltantes(full) == []

    partial = SimpleNamespace(
        scopes=["https://www.googleapis.com/auth/fitness.activity.read"]
    )
    faltan = _scopes_faltantes(partial)
    assert any("sleep" in s for s in faltan)
    assert any("heart_rate" in s for s in faltan)

    empty = SimpleNamespace(scopes=[])
    assert _scopes_faltantes(empty) == []


def test_parse_hr_summary_avg_max():
    out = {"fc_promedio": None, "fc_maxima": None}
    ok = _parse_hr_summary_point(
        {"value": [{"fpVal": 72.4}, {"fpVal": 140.1}, {"fpVal": 50.0}]},
        out,
    )
    assert ok
    assert out["fc_promedio"] == 72
    assert out["fc_maxima"] == 140


def test_sum_best_int_elige_mayor_fuente():
    service = MagicMock()

    def _agg(**kwargs):
        body = kwargs["body"]
        src = (body["aggregateBy"][0] or {}).get("dataSourceId")
        n = 0 if src is None else 8500 if "estimated" in str(src) else 100
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {
            "bucket": [
                {
                    "dataset": [
                        {"point": [{"value": [{"intVal": n}]}]}
                    ]
                }
            ]
        }
        return mock_exec

    service.users.return_value.dataset.return_value.aggregate.side_effect = _agg
    total = _sum_best_int(
        service,
        "com.google.step_count.delta",
        1,
        2,
        (None, "derived:x:estimated_steps", "derived:x:other"),
    )
    assert total == 8500


def _mock_fit_service_empty():
    service = MagicMock()
    # sessions.list → vacío
    service.users.return_value.sessions.return_value.list.return_value.execute.return_value = {
        "session": []
    }
    # aggregate → vacío
    service.users.return_value.dataset.return_value.aggregate.return_value.execute.return_value = {
        "bucket": []
    }
    # dataSources.list → sin tipos Fit nativos (simula solo Health Connect en UI)
    service.users.return_value.dataSources.return_value.list.return_value.execute.return_value = {
        "dataSource": []
    }
    # datasets.get → vacío
    service.users.return_value.dataSources.return_value.datasets.return_value.get.return_value.execute.return_value = {
        "point": []
    }
    return service


def test_obtener_datos_dia_aviso_health_connect(monkeypatch):
    service = _mock_fit_service_empty()
    monkeypatch.setattr("app.google_fit.get_fit_service", lambda: service)
    monkeypatch.setattr(
        "app.google_fit._get_credentials",
        lambda: SimpleNamespace(
            scopes=[
                "https://www.googleapis.com/auth/fitness.activity.read",
                "https://www.googleapis.com/auth/fitness.sleep.read",
                "https://www.googleapis.com/auth/fitness.heart_rate.read",
            ]
        ),
    )

    datos = obtener_datos_dia(date(2026, 9, 17))
    assert datos.get("error") is None
    avisos = " ".join(datos.get("avisos_fit") or [])
    assert "Health Connect" in avisos
    assert datos.get("pasos") in (None, 0)
    assert datos.get("horas_sueno") is None


def test_obtener_ejercicio_pasos_desde_aggregate(monkeypatch):
    service = MagicMock()
    service.users.return_value.sessions.return_value.list.return_value.execute.return_value = {
        "session": []
    }

    def _agg(**kwargs):
        body = kwargs["body"]
        dtype = body["aggregateBy"][0]["dataTypeName"]
        src = body["aggregateBy"][0].get("dataSourceId")
        mock_exec = MagicMock()
        if dtype == "com.google.step_count.delta" and src and "estimated" in src:
            mock_exec.execute.return_value = {
                "bucket": [
                    {"dataset": [{"point": [{"value": [{"intVal": 6234}]}]}]}
                ]
            }
        elif dtype == "com.google.calories.expended":
            mock_exec.execute.return_value = {
                "bucket": [
                    {"dataset": [{"point": [{"value": [{"fpVal": 210.5}]}]}]}
                ]
            }
        else:
            mock_exec.execute.return_value = {"bucket": []}
        return mock_exec

    service.users.return_value.dataset.return_value.aggregate.side_effect = _agg
    # dataset fallback no necesario
    service.users.return_value.dataSources.return_value.list.return_value.execute.return_value = {
        "dataSource": []
    }

    out = obtener_ejercicio(date(2026, 9, 17), service)
    assert out["pasos"] == 6234
    assert out["hizo_ejercicio"] is True  # >= 5000 → caminata estimada
    assert out["tipo_ejercicio"] == "Caminata"
    assert out["calorias"] == 210


def test_obtener_sueno_desde_sesion(monkeypatch):
    service = MagicMock()
    # Noche que termina el 17: dormí 23:00 del 16 → 07:00 del 17 (UTC-6)
    # Usamos millis absolutos coherentes con TZ_LOCAL
    from datetime import datetime, timezone, timedelta

    tz = timezone(timedelta(hours=-6))
    inicio = datetime(2026, 9, 16, 23, 0, tzinfo=tz)
    fin = datetime(2026, 9, 17, 7, 0, tzinfo=tz)
    service.users.return_value.sessions.return_value.list.return_value.execute.return_value = {
        "session": [
            {
                "activityType": 72,
                "startTimeMillis": str(int(inicio.timestamp() * 1000)),
                "endTimeMillis": str(int(fin.timestamp() * 1000)),
            }
        ]
    }
    out = obtener_sueno(date(2026, 9, 17), service)
    assert out["horas_sueno"] == 8.0
    assert out["hora_dormir"] == "23:00"
    assert out["hora_despertar"] == "07:00"
    assert out["_fuente"] == "sessions"


def test_obtener_fc_usa_int_millis_en_aggregate(monkeypatch):
    service = MagicMock()
    bodies = []

    def _agg(**kwargs):
        bodies.append(kwargs["body"])
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {
            "bucket": [
                {
                    "dataset": [
                        {
                            "point": [
                                {
                                    "value": [
                                        {"fpVal": 68.0},
                                        {"fpVal": 120.0},
                                        {"fpVal": 55.0},
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return mock_exec

    service.users.return_value.dataset.return_value.aggregate.side_effect = _agg
    out = obtener_frecuencia_cardiaca(date(2026, 9, 17), service)
    assert out["fc_promedio"] == 68
    assert out["fc_maxima"] == 120
    assert bodies
    assert isinstance(bodies[0]["startTimeMillis"], int)
    assert isinstance(bodies[0]["endTimeMillis"], int)
