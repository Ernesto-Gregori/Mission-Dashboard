"""Presupuesto: reparto del ingreso en los 3 sobres y vencimientos recurrentes.

Única fuente de porcentajes: `presupuesto_config`. Los "métodos" (3 sobres,
50/30/20) son presets de esos mismos porcentajes, no sistemas aparte.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from app.db.schema import SOBRES_CONFIG
from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy

log = get_logger("presupuesto")

SOBRES = tuple(SOBRES_CONFIG)

# Columnas históricas de presupuesto_config (nombres 50/30/20) → sobre.
_COLUMNA_SOBRE = {
    "Supervivencia": "pct_necesidades",
    "Futuro_Hogar": "pct_ahorro",
    "Ministerio_Extras": "pct_deseos",
}

PRESETS = {
    "sobres": {
        "label": "3 sobres",
        "ratios": {"Supervivencia": 65, "Futuro_Hogar": 20, "Ministerio_Extras": 15},
    },
    "503020": {
        "label": "50/30/20",
        "ratios": {"Supervivencia": 50, "Futuro_Hogar": 20, "Ministerio_Extras": 30},
    },
}
RATIOS_DEFAULT = PRESETS["sobres"]["ratios"]

# Alias en lenguaje natural (Telegram / IA) → (sobre, subcategoría por defecto).
CATEGORIA_A_SOBRE = {
    "necesidades": ("Supervivencia", "Otro_Supervivencia"),
    "deseos": ("Ministerio_Extras", "Personal"),
    "ahorro": ("Futuro_Hogar", "Otro_Ahorro"),
}

SUBCATEGORIAS_LABELS = {
    "Tarjeta_MSI": "💳 Tarjeta MSI",
    "Deuda_Fija": "📋 Deuda Fija",
    "Comida": "🍽️ Comida",
    "Transporte": "🚌 Transporte",
    "Servicios": "💡 Servicios",
    "Otro_Supervivencia": "📦 Otro",
    "Ahorro_Emergencia": "🛡️ Ahorro Emergencia",
    "Fondo_Renta": "🏠 Fondo Renta",
    "Otro_Ahorro": "💾 Otro Ahorro",
    "Libros_Cursos": "📚 Libros / Cursos",
    "Cita_Esposa": "💑 Cita con Esposa",
    "Ofrenda_Diezmo": "⛪ Ofrenda / Diezmo",
    "Personal": "👤 Personal",
}

TIPOS_RECURRENTES = ("ingreso", "suscripcion", "factura", "deuda", "ahorro")
TIPO_META = {
    "ingreso": {"label": "Ingreso", "emoji": "💵", "color": "#3fb950"},
    "suscripcion": {"label": "Suscripción", "emoji": "🔁", "color": "#58a6ff"},
    "factura": {"label": "Factura", "emoji": "🧾", "color": "#f0883e"},
    "deuda": {"label": "Deuda", "emoji": "📉", "color": "#f85149"},
    "ahorro": {"label": "Ahorro", "emoji": "🏦", "color": "#56d364"},
}


def ensure_presupuesto_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS presupuesto_config (
            user_id INTEGER PRIMARY KEY,
            pct_necesidades INTEGER NOT NULL DEFAULT 50,
            pct_deseos INTEGER NOT NULL DEFAULT 30,
            pct_ahorro INTEGER NOT NULL DEFAULT 20,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS presupuesto_recurrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN (
                'ingreso', 'suscripcion', 'factura', 'deuda', 'ahorro'
            )),
            monto REAL NOT NULL DEFAULT 0,
            dia INTEGER NOT NULL CHECK(dia >= 1 AND dia <= 31),
            notas TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_presupuesto_rec_user
        ON presupuesto_recurrentes(user_id, dia)
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.warning("ensure_presupuesto_schema: %s", e)


def _uid(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def obtener_ratios(user_id: int | None = None) -> dict[str, int]:
    """Porcentaje del ingreso asignado a cada sobre (suman 100)."""
    ensure_presupuesto_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            """
            SELECT pct_necesidades, pct_deseos, pct_ahorro
            FROM presupuesto_config WHERE user_id = ?
            """,
            [_uid(user_id)],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return dict(RATIOS_DEFAULT)
    return {s: int(rows[0][_COLUMNA_SOBRE[s]]) for s in SOBRES}


def validar_ratios(ratios: dict) -> tuple[bool, str, dict[str, int]]:
    clean: dict[str, int] = {}
    for s in SOBRES:
        try:
            clean[s] = int(ratios.get(s))
        except (TypeError, ValueError):
            return False, "Cada porcentaje debe ser un número entero.", clean
        if clean[s] < 0 or clean[s] > 100:
            return False, "Cada porcentaje debe estar entre 0 y 100.", clean
    if sum(clean.values()) != 100:
        return False, "Los tres porcentajes deben sumar 100.", clean
    return True, "", clean


def guardar_ratios(ratios: dict, user_id: int | None = None) -> tuple[bool, str]:
    ok, msg, clean = validar_ratios(ratios)
    if not ok:
        return False, msg
    ensure_presupuesto_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    ejecutar(
        """
        INSERT INTO presupuesto_config
            (user_id, pct_necesidades, pct_deseos, pct_ahorro)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            pct_necesidades = excluded.pct_necesidades,
            pct_deseos = excluded.pct_deseos,
            pct_ahorro = excluded.pct_ahorro,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [
            _uid(user_id),
            clean["Supervivencia"],
            clean["Ministerio_Extras"],
            clean["Futuro_Hogar"],
        ],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True, "Reparto guardado."


def preset_de(ratios: dict) -> str | None:
    for key, p in PRESETS.items():
        if all(int(ratios.get(s, -1)) == p["ratios"][s] for s in SOBRES):
            return key
    return None


def resumen_mes(mes: int, anio: int, user_id: int | None = None) -> dict:
    """Ingreso del mes repartido en sobres según los ratios vs gasto real."""
    from app.db.finanzas import obtener_gastos_sobre, obtener_ingreso

    ratios = obtener_ratios(user_id)
    ingreso = float(obtener_ingreso(mes, anio) or 0)
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=500)
    total_gastado = sum(float(g.get("monto") or 0) for g in gastos)

    sobres: dict[str, dict] = {}
    for key, config in SOBRES_CONFIG.items():
        propios = [g for g in gastos if g.get("sobre") == key]
        gastado = sum(float(g.get("monto") or 0) for g in propios)
        presupuesto = ingreso * ratios[key] / 100.0
        por_subcat: dict[str, float] = {}
        for g in propios:
            sub = str(g.get("subcategoria") or "")
            por_subcat[sub] = por_subcat.get(sub, 0.0) + float(g.get("monto") or 0)
        fijos = sum(float(g.get("monto") or 0) for g in propios if g.get("es_fijo"))
        sobres[key] = {
            **config,
            "key": key,
            "pct": ratios[key],
            "presupuesto": presupuesto,
            "gastado": gastado,
            "disponible": presupuesto - gastado,
            "pct_usado": (gastado / presupuesto * 100) if presupuesto > 0 else 0,
            "cantidad_gastos": len(propios),
            "por_subcat": por_subcat,
            "fijos": fijos,
            "variables": gastado - fijos,
        }

    por_destino: dict[str, float] = {}
    for g in gastos:
        sub = str(g.get("subcategoria") or g.get("descripcion") or "")
        dest = SUBCATEGORIAS_LABELS.get(sub, sub)
        por_destino[dest] = por_destino.get(dest, 0.0) + float(g.get("monto") or 0)
    destinos = sorted(por_destino.items(), key=lambda x: x[1], reverse=True)[:8]

    return {
        "ingreso": ingreso,
        "mes": mes,
        "anio": anio,
        "ratios": ratios,
        "preset": preset_de(ratios),
        "sobres": sobres,
        "gastos": gastos,
        "total_gastado": total_gastado,
        "total_disponible": ingreso - total_gastado,
        "pct_global": (total_gastado / ingreso * 100) if ingreso > 0 else 0,
        "sin_ingreso": ingreso == 0,
        "stacked": [
            {
                "key": s["key"],
                "label": s["nombre"].capitalize(),
                "color": s["color"],
                "monto": s["gastado"],
                "pct": (s["gastado"] / total_gastado * 100) if total_gastado > 0 else 0,
            }
            for s in sobres.values()
        ],
        "chart": [
            {
                "nombre": nombre,
                "monto": monto,
                "pct": (monto / total_gastado * 100) if total_gastado > 0 else 0,
            }
            for nombre, monto in destinos
        ],
    }


def listar_recurrentes(user_id: int | None = None) -> list:
    ensure_presupuesto_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    rows = (
        ejecutar(
            """
            SELECT * FROM presupuesto_recurrentes
            WHERE user_id = ? AND activo = 1
            ORDER BY dia, tipo, titulo
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )
    out = []
    for r in rows:
        item = dict(r) if not isinstance(r, dict) else r
        tipo = str(item.get("tipo") or "factura")
        item["meta"] = TIPO_META.get(tipo, TIPO_META["factura"])
        out.append(item)
    return out


def agregar_recurrente(
    titulo: str,
    tipo: str,
    monto: float,
    dia: int,
    notas: str = "",
    user_id: int | None = None,
) -> tuple[bool, str]:
    titulo = (titulo or "").strip()
    tipo = (tipo or "").strip().lower()
    if not titulo:
        return False, "El título es obligatorio."
    if tipo not in TIPOS_RECURRENTES:
        return False, "Tipo de vencimiento inválido."
    try:
        dia_i = int(dia)
        monto_f = float(monto)
    except (TypeError, ValueError):
        return False, "Día o monto inválido."
    if dia_i < 1 or dia_i > 31:
        return False, "El día debe estar entre 1 y 31."
    if monto_f < 0:
        return False, "El monto no puede ser negativo."
    ensure_presupuesto_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    ejecutar(
        """
        INSERT INTO presupuesto_recurrentes
            (user_id, titulo, tipo, monto, dia, notas, activo)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        [uid_i, titulo[:120], tipo, monto_f, dia_i, (notas or "")[:240]],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True, "Vencimiento guardado."


def eliminar_recurrente(rec_id: int, user_id: int | None = None) -> bool:
    ensure_presupuesto_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    ejecutar(
        """
        DELETE FROM presupuesto_recurrentes
        WHERE id = ? AND user_id = ?
        """,
        [int(rec_id), uid_i],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True


def _dia_en_mes(dia: int, anio: int, mes: int) -> int:
    ultimo = monthrange(anio, mes)[1]
    return min(max(1, int(dia)), ultimo)


def calendario_vencimientos(
    mes: int,
    anio: int,
    user_id: int | None = None,
    *,
    referencia: date | None = None,
) -> dict:
    """Grilla mensual con recurrentes coloreados por tipo."""
    items = listar_recurrentes(user_id)
    ultimo = monthrange(anio, mes)[1]
    primer = date(anio, mes, 1)
    # Lunes = 0 para alinear con el planificador
    offset = primer.weekday()
    hoy = referencia or _hoy()
    celdas: list[dict | None] = [None] * offset
    por_dia: dict[int, list] = {d: [] for d in range(1, ultimo + 1)}
    for r in items:
        d = _dia_en_mes(int(r.get("dia") or 1), anio, mes)
        por_dia[d].append(r)
    for d in range(1, ultimo + 1):
        fecha = date(anio, mes, d)
        celdas.append({
            "dia": d,
            "fecha": fecha,
            "es_hoy": fecha == hoy,
            "vencimientos": por_dia[d],
        })
    while len(celdas) % 7:
        celdas.append(None)
    semanas = [celdas[i:i + 7] for i in range(0, len(celdas), 7)]
    return {
        "mes": mes,
        "anio": anio,
        "semanas": semanas,
        "recurrentes": items,
        "tipos": [
            {"key": k, **TIPO_META[k]} for k in TIPOS_RECURRENTES
        ],
    }
