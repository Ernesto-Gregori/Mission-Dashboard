"""Presupuesto 50/30/20 derivado de ingresos y gastos de Finanzas."""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy

log = get_logger("presupuesto")

CATEGORIAS = ("necesidades", "deseos", "ahorro")
RATIOS_DEFAULT = {"necesidades": 50, "deseos": 30, "ahorro": 20}

SOBRE_A_CATEGORIA = {
    "Supervivencia": "necesidades",
    "Ministerio_Extras": "deseos",
    "Futuro_Hogar": "ahorro",
}
CATEGORIA_A_SOBRE = {
    "necesidades": ("Supervivencia", "Otro_Supervivencia"),
    "deseos": ("Ministerio_Extras", "Personal"),
    "ahorro": ("Futuro_Hogar", "Otro_Ahorro"),
}

TIPOS_RECURRENTES = ("ingreso", "suscripcion", "factura", "deuda", "ahorro")
TIPO_META = {
    "ingreso": {"label": "Ingreso", "emoji": "💵", "color": "#3fb950"},
    "suscripcion": {"label": "Suscripción", "emoji": "🔁", "color": "#58a6ff"},
    "factura": {"label": "Factura", "emoji": "🧾", "color": "#f0883e"},
    "deuda": {"label": "Deuda", "emoji": "📉", "color": "#f85149"},
    "ahorro": {"label": "Ahorro", "emoji": "🏦", "color": "#56d364"},
}
CATEGORIA_META = {
    "necesidades": {
        "label": "Necesidades",
        "emoji": "🏠",
        "color": "#f85149",
        "descripcion": "Supervivencia — vivienda, comida, deudas fijas",
    },
    "deseos": {
        "label": "Deseos",
        "emoji": "✨",
        "descripcion": "Ministerio y extras — ocio, ofrendas, personal",
        "color": "#58a6ff",
    },
    "ahorro": {
        "label": "Ahorro",
        "emoji": "🌱",
        "descripcion": "Futuro y hogar — no tocar",
        "color": "#3fb950",
    },
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


def obtener_ratios(user_id: int | None = None) -> dict:
    ensure_presupuesto_schema()
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    rows = (
        ejecutar(
            """
            SELECT pct_necesidades, pct_deseos, pct_ahorro
            FROM presupuesto_config WHERE user_id = ?
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )
    if not rows:
        return dict(RATIOS_DEFAULT)
    r = rows[0]
    return {
        "necesidades": int(r["pct_necesidades"]),
        "deseos": int(r["pct_deseos"]),
        "ahorro": int(r["pct_ahorro"]),
    }


def validar_ratios(necesidades: int, deseos: int, ahorro: int) -> tuple[bool, str]:
    vals = (int(necesidades), int(deseos), int(ahorro))
    if any(v < 0 or v > 100 for v in vals):
        return False, "Cada porcentaje debe estar entre 0 y 100."
    if sum(vals) != 100:
        return False, "Los tres porcentajes deben sumar 100."
    return True, ""


def guardar_ratios(
    necesidades: int,
    deseos: int,
    ahorro: int,
    user_id: int | None = None,
) -> tuple[bool, str]:
    ok, msg = validar_ratios(necesidades, deseos, ahorro)
    if not ok:
        return False, msg
    ensure_presupuesto_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
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
        [uid_i, int(necesidades), int(deseos), int(ahorro)],
    )
    try:
        invalidate_data_caches()
    except Exception:
        pass
    return True, "Ratios guardados."


def categoria_de_sobre(sobre: str) -> str:
    return SOBRE_A_CATEGORIA.get(str(sobre or ""), "necesidades")


def resumen_mes(mes: int, anio: int, user_id: int | None = None) -> dict:
    """50/30/20 vs gasto real. Lee ingreso_mensual + gastos_sobres."""
    from app.db.finanzas import obtener_gastos_sobre, obtener_ingreso

    uid_i = _uid(user_id)
    ratios = obtener_ratios(uid_i)
    ingreso = float(obtener_ingreso(mes, anio) or 0)
    gastos = obtener_gastos_sobre(mes=mes, anio=anio, limite=500)
    gastado = {k: 0.0 for k in CATEGORIAS}
    por_destino: dict[str, float] = {}
    for g in gastos:
        cat = categoria_de_sobre(g.get("sobre"))
        monto = float(g.get("monto") or 0)
        gastado[cat] = gastado.get(cat, 0.0) + monto
        dest = str(g.get("subcategoria") or g.get("descripcion") or cat)
        por_destino[dest] = por_destino.get(dest, 0.0) + monto

    categorias = []
    total_gastado = sum(gastado.values())
    for key in CATEGORIAS:
        meta = CATEGORIA_META[key]
        pct = ratios[key]
        presupuesto = ingreso * pct / 100.0
        usado = gastado[key]
        categorias.append({
            "key": key,
            **meta,
            "pct": pct,
            "presupuesto": presupuesto,
            "gastado": usado,
            "disponible": presupuesto - usado,
            "pct_usado": (usado / presupuesto * 100) if presupuesto > 0 else 0,
        })

    destinos = sorted(por_destino.items(), key=lambda x: x[1], reverse=True)
    chart = []
    for nombre, monto in destinos[:8]:
        chart.append({
            "nombre": nombre,
            "monto": monto,
            "pct": (monto / total_gastado * 100) if total_gastado > 0 else 0,
        })
    stacked = []
    for key in CATEGORIAS:
        stacked.append({
            "key": key,
            "label": CATEGORIA_META[key]["label"],
            "color": CATEGORIA_META[key]["color"],
            "monto": gastado[key],
            "pct": (gastado[key] / total_gastado * 100) if total_gastado > 0 else 0,
        })

    return {
        "ingreso": ingreso,
        "mes": mes,
        "anio": anio,
        "ratios": ratios,
        "categorias": categorias,
        "total_gastado": total_gastado,
        "total_disponible": ingreso - total_gastado,
        "sin_ingreso": ingreso == 0,
        "gastos": gastos,
        "chart": chart,
        "stacked": stacked,
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
            "items": por_dia[d],
        })
    while len(celdas) % 7:
        celdas.append(None)
    semanas = [celdas[i:i + 7] for i in range(0, len(celdas), 7)]
    return {
        "mes": mes,
        "anio": anio,
        "semanas": semanas,
        "items": items,
        "tipos": [
            {"key": k, **TIPO_META[k]} for k in TIPOS_RECURRENTES
        ],
    }
