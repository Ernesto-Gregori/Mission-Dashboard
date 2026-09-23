"""CRUD Salud — registros diarios, promedios y correlaciones simples."""
from __future__ import annotations

import json
from datetime import timedelta

from app.db.core import ejecutar, ejecutar_cached, invalidate_data_caches
from app.tenant import uid
from app.timezone_config import date, datetime, hoy as _hoy


ZONAS_LISTA = [
    "Pecho",
    "Espalda",
    "Hombros",
    "Bíceps",
    "Tríceps",
    "Core/Abdomen",
    "Piernas",
    "Glúteos",
    "Cuerpo completo",
]

TIPOS_EJERCICIO = [
    "Calistenia",
    "Caminata",
    "Carrera",
    "Gimnasio",
    "Entrenamiento fuerza",
    "Yoga",
    "Ciclismo",
    "Natación",
    "Otro",
]


def guardar_registro_salud(fecha, datos: dict) -> bool:
    """
    UPSERT por (user_id, fecha).
    fecha → str ISO; numéricos tipados; listas → JSON.
    """
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    zonas = datos.get("zonas_musculares", [])
    sesiones = datos.get("sesiones_json", [])

    def _int(v):
        return int(v) if v is not None and v != "" else None

    def _float(v):
        return float(v) if v is not None and v != "" else None

    campos = [
        "user_id",
        "fecha",
        "horas_sueno",
        "calidad_sueno",
        "hora_dormir",
        "hora_despertar",
        "energia_manana",
        "energia_tarde",
        "energia_noche",
        "hizo_ejercicio",
        "tipo_ejercicio",
        "duracion_minutos",
        "intensidad",
        "notas_ejercicio",
        "zonas_musculares",
        "sesiones_json",
        "calorias_fit",
        "pasos_fit",
        "fc_promedio_fit",
        "fc_maxima_fit",
        "fuente_datos",
        "productividad_percibida",
    ]
    valores = [
        uid(),
        fecha_iso,
        _float(datos.get("horas_sueno")),
        _int(datos.get("calidad_sueno")),
        str(datos.get("hora_dormir") or ""),
        str(datos.get("hora_despertar") or ""),
        _int(datos.get("energia_manana")),
        _int(datos.get("energia_tarde")),
        _int(datos.get("energia_noche")),
        1 if datos.get("hizo_ejercicio") else 0,
        str(datos.get("tipo_ejercicio") or "") or None,
        _int(datos.get("duracion_minutos")),
        _int(datos.get("intensidad")),
        str(datos.get("notas_ejercicio") or "") or None,
        json.dumps(zonas) if isinstance(zonas, list) else zonas,
        json.dumps(sesiones) if isinstance(sesiones, list) else sesiones,
        _float(datos.get("calorias_fit")),
        _int(datos.get("pasos_fit")),
        _int(datos.get("fc_promedio_fit")),
        _int(datos.get("fc_maxima_fit")),
        str(datos.get("fuente_datos") or "manual"),
        _int(datos.get("productividad_percibida")),
    ]
    placeholders = ", ".join(["?"] * len(valores))
    set_cols = [c for c in campos if c not in ("user_id", "fecha")]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in set_cols)
    try:
        ejecutar(
            f"""INSERT INTO registros_salud
                ({', '.join(campos)})
                VALUES ({placeholders})
                ON CONFLICT(user_id, fecha) DO UPDATE SET {set_clause}""",
            valores,
        )
        try:
            invalidate_data_caches()
        except Exception:
            pass
        return True
    except Exception:
        return False


def obtener_registro_salud(fecha) -> dict | None:
    fecha_iso = str(fecha) if not isinstance(fecha, str) else fecha
    rows = ejecutar(
        "SELECT * FROM registros_salud WHERE fecha = ? AND user_id = ?",
        [fecha_iso, uid()],
        fetchall=True,
    )
    return rows[0] if rows else None


def obtener_registros_rango(dias: int = 14) -> list:
    fecha_desde = (_hoy() - timedelta(days=dias)).isoformat()
    return (
        ejecutar_cached(
            """
            SELECT * FROM registros_salud
            WHERE fecha >= ? AND user_id = ? ORDER BY fecha DESC
            """,
            (fecha_desde, uid()),
        )
        or []
    )


def calcular_promedios(registros: list) -> dict:
    if not registros:
        return {}

    def avg(key):
        vals = [r[key] for r in registros if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    dias_ejercicio = sum(1 for r in registros if r.get("hizo_ejercicio"))
    return {
        "total_dias": len(registros),
        "dias_ejercicio": dias_ejercicio,
        "pct_ejercicio": dias_ejercicio / len(registros) * 100,
        "avg_energia_manana": avg("energia_manana"),
        "avg_energia_tarde": avg("energia_tarde"),
        "avg_energia_noche": avg("energia_noche"),
        "avg_sueno": avg("horas_sueno"),
        "avg_calidad_sueno": avg("calidad_sueno"),
        "avg_productividad": avg("productividad_percibida"),
    }


def analizar_correlacion_simple(registros: list) -> tuple:
    if len(registros) < 4:
        return None, "Se necesitan al menos 4 días de datos"

    por_fecha = {r["fecha"]: r for r in registros}
    ejercicio_si = []
    ejercicio_no = []

    for r in registros:
        fecha = datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        if fecha.weekday() == 2:
            jueves = (fecha + timedelta(days=1)).isoformat()
            if jueves in por_fecha and por_fecha[jueves].get("productividad_percibida"):
                target = por_fecha[jueves]["productividad_percibida"]
                (ejercicio_si if r.get("hizo_ejercicio") else ejercicio_no).append(target)

    if not ejercicio_si or not ejercicio_no:
        return None, "Necesitas miércoles con y sin ejercicio para comparar"

    prom_con = sum(ejercicio_si) / len(ejercicio_si)
    prom_sin = sum(ejercicio_no) / len(ejercicio_no)
    diff = prom_con - prom_sin
    return {
        "promedio_con_ejercicio": prom_con,
        "promedio_sin_ejercicio": prom_sin,
        "diferencia": diff,
        "pct_mejora": (diff / prom_sin * 100) if prom_sin > 0 else 0,
        "muestras_con": len(ejercicio_si),
        "muestras_sin": len(ejercicio_no),
    }, None


def construir_contexto_salud(registros: list, stats: dict) -> str:
    if not registros or not stats:
        return "Sin datos de salud registrados aún."

    hoy_local = _hoy()
    lineas = [
        f"Período: últimos {stats['total_dias']} días",
        f"Ejercicio: {stats['dias_ejercicio']}/{stats['total_dias']} días ({stats['pct_ejercicio']:.0f}%)",
        f"Sueño promedio: {stats['avg_sueno']:.1f}h (calidad: {stats['avg_calidad_sueno']:.1f}/10)",
        f"Energía mañana: {stats['avg_energia_manana']:.1f}/10",
        f"Energía tarde:  {stats['avg_energia_tarde']:.1f}/10",
        f"Productividad:  {stats['avg_productividad']:.1f}/10",
    ]

    for r in registros[:3]:
        ej = (
            f"✓ {r.get('tipo_ejercicio', 'ejercicio')} {r.get('duracion_minutos', 0)}min"
            if r.get("hizo_ejercicio")
            else "✗ sin ejercicio"
        )
        lineas.append(
            f"  {r['fecha']}: {ej}, "
            f"sueño {r.get('horas_sueno') or '-'}h, "
            f"energía {r.get('energia_manana') or '-'}/10, "
            f"productividad {r.get('productividad_percibida') or '-'}/10"
        )

    inicio_sem = hoy_local - timedelta(days=hoy_local.weekday())
    _ = inicio_sem  # reservado para expansiones
    return "\n".join(lineas)


TIPOS_OBJETIVO = ("ejercicio", "pasos", "sueno")
OBJETIVO_LABELS = {
    "ejercicio": "Hacer ejercicio",
    "pasos": "Pasos mínimos",
    "sueno": "Horas de sueño",
}


def ensure_salud_objetivo_schema() -> None:
    from app.db.core import ejecutar

    try:
        ejecutar(
            """
            CREATE TABLE IF NOT EXISTS salud_objetivo (
                user_id INTEGER PRIMARY KEY,
                tipo TEXT NOT NULL DEFAULT 'ejercicio',
                valor REAL NOT NULL DEFAULT 1,
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def obtener_objetivo(user_id: int | None = None) -> dict:
    ensure_salud_objetivo_schema()
    uid_i = int(user_id) if user_id is not None else uid()
    rows = (
        ejecutar(
            "SELECT tipo, valor FROM salud_objetivo WHERE user_id = ?",
            [uid_i],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return {"tipo": "ejercicio", "valor": 1.0, "label": OBJETIVO_LABELS["ejercicio"]}
    tipo = str(rows[0].get("tipo") or "ejercicio")
    if tipo not in TIPOS_OBJETIVO:
        tipo = "ejercicio"
    try:
        valor = float(rows[0].get("valor") or 1)
    except Exception:
        valor = 1.0
    if tipo == "ejercicio":
        valor = 1.0
    return {"tipo": tipo, "valor": valor, "label": OBJETIVO_LABELS.get(tipo, tipo)}


def guardar_objetivo(tipo: str, valor: float | int | None = None, user_id: int | None = None) -> dict:
    ensure_salud_objetivo_schema()
    uid_i = int(user_id) if user_id is not None else uid()
    t = tipo if tipo in TIPOS_OBJETIVO else "ejercicio"
    if t == "ejercicio":
        v = 1.0
    elif t == "pasos":
        v = max(1000.0, float(valor or 8000))
    else:
        v = min(12.0, max(4.0, float(valor or 7)))
    ejecutar(
        """
        INSERT INTO salud_objetivo (user_id, tipo, valor)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            tipo = excluded.tipo,
            valor = excluded.valor,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [uid_i, t, v],
    )
    return obtener_objetivo(uid_i)


def registro_cumple_objetivo(reg: dict | None, objetivo: dict | None = None) -> bool:
    if not reg:
        return False
    obj = objetivo or obtener_objetivo()
    tipo = obj.get("tipo") or "ejercicio"
    valor = float(obj.get("valor") or 1)
    if tipo == "pasos":
        try:
            return int(reg.get("pasos_fit") or 0) >= valor
        except Exception:
            return False
    if tipo == "sueno":
        h = reg.get("horas_sueno")
        try:
            return h is not None and h != "" and float(h) >= valor
        except Exception:
            return False
    return bool(reg.get("hizo_ejercicio"))


def calcular_racha_objetivo(user_id: int | None = None) -> int:
    """Días consecutivos cumpliendo el objetivo. Si hoy no hay registro, arranca ayer."""
    obj = obtener_objetivo(user_id)
    regs = {str(r["fecha"]): r for r in obtener_registros_rango(60)}
    hoy = _hoy()
    start = hoy
    if str(hoy) not in regs:
        start = hoy - timedelta(days=1)
    racha = 0
    d = start
    for _ in range(60):
        iso = d.isoformat()
        if registro_cumple_objetivo(regs.get(iso), obj):
            racha += 1
            d = d - timedelta(days=1)
        else:
            break
    return racha


def serie_progreso(dias: int = 7, user_id: int | None = None) -> list[dict]:
    obj = obtener_objetivo(user_id)
    n = max(1, min(int(dias), 60))
    regs = {str(r["fecha"]): r for r in obtener_registros_rango(n)}
    hoy = _hoy()
    out = []
    meta = float(obj.get("valor") or 1) or 1.0
    for i in range(n - 1, -1, -1):
        d = hoy - timedelta(days=i)
        iso = d.isoformat()
        r = regs.get(iso)
        cumple = registro_cumple_objetivo(r, obj)
        valor = None
        if r:
            if obj["tipo"] == "pasos":
                valor = r.get("pasos_fit")
            elif obj["tipo"] == "sueno":
                valor = r.get("horas_sueno")
            else:
                valor = 1 if r.get("hizo_ejercicio") else 0
        try:
            num = float(valor) if valor is not None else 0.0
        except Exception:
            num = 0.0
        pct = 100.0 if cumple and obj["tipo"] == "ejercicio" else min(100.0, (num / meta) * 100.0)
        if not cumple and obj["tipo"] == "ejercicio":
            pct = 12.0 if r else 8.0
        out.append(
            {
                "fecha": iso,
                "label": d.strftime("%d/%m"),
                "cumple": cumple,
                "valor": valor,
                "pct": round(pct, 1),
            }
        )
    return out
