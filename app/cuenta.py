"""Preferencias de la cuenta: módulos, ritual, dinero, rueda y exportación."""
from __future__ import annotations

import json
import re
from datetime import date

from app.templates import MODULE_TEMPLATES, SUPERFICIES

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_DIAS = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")
MONEDAS = (("USD", "$"), ("EUR", "€"), ("MXN", "$"), ("GTQ", "Q"), ("CRC", "₡"), ("COP", "$"))
METODOS = (("sobres", "Sobres"), ("porcentajes", "Porcentajes"))
FRECUENCIAS = (
    ("diaria", "Todos los días"),
    ("lun,mar,mie,jue,vie", "Entre semana"),
    ("sab,dom", "Fin de semana"),
    ("lun", "Solo los lunes"),
)
DIAS_HABITO = (
    ("lun", "Lun"),
    ("mar", "Mar"),
    ("mie", "Mié"),
    ("jue", "Jue"),
    ("vie", "Vie"),
    ("sab", "Sáb"),
    ("dom", "Dom"),
)
RITUAL_A = "Gratitud"
RITUAL_B = "Intención"
HORA_DESDE = 6
HORA_HASTA = 22
_SECRETOS = {"password_hash", "salt", "token_json", "verify_hash"}


def asegurar_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        "ALTER TABLE user_prefs ADD COLUMN moneda TEXT DEFAULT 'USD'",
        "ALTER TABLE user_prefs ADD COLUMN metodo TEXT DEFAULT 'sobres'",
        "ALTER TABLE user_prefs ADD COLUMN ritual_a TEXT",
        "ALTER TABLE user_prefs ADD COLUMN ritual_b TEXT",
        "ALTER TABLE user_prefs ADD COLUMN hora_desde INTEGER",
        "ALTER TABLE user_prefs ADD COLUMN hora_hasta INTEGER",
        "ALTER TABLE user_prefs ADD COLUMN rueda_json TEXT",
        "ALTER TABLE user_prefs ADD COLUMN salud_json TEXT",
        "ALTER TABLE user_prefs ADD COLUMN idioma TEXT",
        "ALTER TABLE habitos_config ADD COLUMN frecuencia TEXT DEFAULT 'diaria'",
        """
        CREATE TABLE IF NOT EXISTS finanzas_categorias (
            user_id INTEGER NOT NULL,
            clave TEXT NOT NULL,
            nombre TEXT NOT NULL,
            emoji TEXT,
            orden INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, clave)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS login_intentos (
            username TEXT PRIMARY KEY,
            fails INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception:
            pass


def _uid(user_id: int | None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def _fila_prefs(user_id: int) -> dict:
    from app.db.core import ejecutar

    asegurar_schema()
    rows = ejecutar(
        "SELECT * FROM user_prefs WHERE user_id = ?",
        [user_id],
        fetchall=True,
    ) or []
    return dict(rows[0]) if rows else {}


def leer_prefs(user_id: int | None = None) -> dict:
    uid_i = _uid(user_id)
    row = _fila_prefs(uid_i)
    moneda = (row.get("moneda") or "USD").upper()
    if moneda not in {c for c, _ in MONEDAS}:
        moneda = "USD"
    metodo = row.get("metodo") or "sobres"
    if metodo not in {m for m, _ in METODOS}:
        metodo = "sobres"
    try:
        desde = int(row.get("hora_desde") if row.get("hora_desde") is not None else HORA_DESDE)
    except (TypeError, ValueError):
        desde = HORA_DESDE
    try:
        hasta = int(row.get("hora_hasta") if row.get("hora_hasta") is not None else HORA_HASTA)
    except (TypeError, ValueError):
        hasta = HORA_HASTA
    desde = min(22, max(0, desde))
    hasta = min(24, max(desde + 1, hasta))
    return {
        "moneda": moneda,
        "metodo": metodo,
        "ritual_a": (row.get("ritual_a") or RITUAL_A)[:40],
        "ritual_b": (row.get("ritual_b") or RITUAL_B)[:40],
        "hora_desde": desde,
        "hora_hasta": hasta,
        "rueda": _json_dict(row.get("rueda_json")),
        "salud": _json_lista(row.get("salud_json")),
        "idioma": idioma_guardado(uid_i),
    }


def idioma_guardado(user_id: int | None = None) -> str:
    raw = str(_fila_prefs(_uid(user_id)).get("idioma") or "").strip().lower()[:2]
    return raw if raw in ("es", "en") else ""


def guardar_idioma(user_id: int, idioma: str) -> None:
    from app.db.core import ejecutar

    asegurar_schema()
    lang = idioma if idioma in ("es", "en") else "es"
    ejecutar(
        """
        INSERT INTO user_prefs (user_id, week_start, idioma)
        VALUES (?, 'lun', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            idioma = excluded.idioma,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [int(user_id), lang],
    )


def guardar_prefs(
    user_id: int,
    *,
    moneda: str,
    metodo: str,
    ritual_a: str,
    ritual_b: str,
    hora_desde: int,
    hora_hasta: int,
    rueda: dict[str, str],
    salud: list[str],
    idioma: str | None = None,
) -> None:
    from app.db.core import ejecutar

    asegurar_schema()
    prefs = leer_prefs(user_id)
    moneda = (moneda or prefs["moneda"]).upper()
    if moneda not in {c for c, _ in MONEDAS}:
        moneda = "USD"
    if metodo not in {m for m, _ in METODOS}:
        metodo = "sobres"
    hora_desde = min(22, max(0, int(hora_desde)))
    hora_hasta = min(24, max(hora_desde + 1, int(hora_hasta)))
    if idioma:
        lang = idioma if idioma in ("es", "en") else "es"
    else:
        lang = idioma_guardado(user_id) or "es"
    ejecutar(
        """
        INSERT INTO user_prefs (
            user_id, week_start, moneda, metodo, ritual_a, ritual_b,
            hora_desde, hora_hasta, rueda_json, salud_json, idioma
        )
        VALUES (?, 'lun', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            moneda = excluded.moneda,
            metodo = excluded.metodo,
            ritual_a = excluded.ritual_a,
            ritual_b = excluded.ritual_b,
            hora_desde = excluded.hora_desde,
            hora_hasta = excluded.hora_hasta,
            rueda_json = excluded.rueda_json,
            salud_json = excluded.salud_json,
            idioma = excluded.idioma,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [
            user_id,
            moneda,
            metodo,
            (ritual_a or RITUAL_A).strip()[:40],
            (ritual_b or RITUAL_B).strip()[:40],
            hora_desde,
            hora_hasta,
            json.dumps(rueda, ensure_ascii=False),
            json.dumps(salud, ensure_ascii=False),
            lang,
        ],
    )


def moneda_simbolo(user_id: int | None = None) -> str:
    codigo = leer_prefs(user_id)["moneda"]
    return dict(MONEDAS).get(codigo, "$")


def horas_plan(user_id: int | None = None) -> tuple[int, int]:
    prefs = leer_prefs(user_id)
    return prefs["hora_desde"], prefs["hora_hasta"]


def ritual_etiquetas(user_id: int | None = None) -> tuple[str, str]:
    prefs = leer_prefs(user_id)
    return prefs["ritual_a"], prefs["ritual_b"]


_RUEDA_MIN = 3
_RUEDA_MAX = 12
_RUEDA_EXTRA_MAX = 4


_NOMBRE_AREA = {"fe": "Espiritualidad", "matrimonio": "Vínculos"}


def _nombre_area(clave: str, nombre: str, overrides: dict) -> str:
    propio = overrides.get(clave)
    if isinstance(propio, str) and propio.strip():
        return propio.strip()[:40]
    return _NOMBRE_AREA.get(clave, nombre)


def _ocultas_rueda(raw: dict) -> list[str]:
    from app.rueda import CLAVES

    ocultas = raw.get("_ocultas")
    if not isinstance(ocultas, list):
        return []
    permitidas = set(CLAVES)
    out: list[str] = []
    for item in ocultas:
        clave = str(item)
        if clave in permitidas and clave not in out:
            out.append(clave)
    return out


def _extras_rueda(raw: dict) -> list[tuple[str, str, str]]:
    from app.rueda import CLAVE_AREA, CLAVES

    extra = raw.get("_extra")
    if not isinstance(extra, list):
        return []
    base = set(CLAVES)
    out: list[tuple[str, str, str]] = []
    vistos: set[str] = set()
    for item in extra:
        if not isinstance(item, dict):
            continue
        clave = str(item.get("clave") or "")
        nombre = str(item.get("nombre") or "").strip()[:40]
        emoji = str(item.get("emoji") or "•").strip()[:4] or "•"
        if not CLAVE_AREA.fullmatch(clave) or clave in base or clave in vistos or not nombre:
            continue
        vistos.add(clave)
        out.append((clave, nombre, emoji))
        if len(out) >= _RUEDA_EXTRA_MAX:
            break
    return out


def _clave_area(nombre: str, ocupadas: set[str]) -> str | None:
    import unicodedata

    from app.rueda import CLAVE_AREA

    bruto = unicodedata.normalize("NFKD", nombre or "")
    bruto = "".join(ch for ch in bruto if not unicodedata.combining(ch))
    base = re.sub(r"[^a-z0-9]+", "", bruto.lower())[:20]
    if not base or not base[0].isalpha():
        return None
    clave = base
    n = 2
    while clave in ocupadas or not CLAVE_AREA.fullmatch(clave):
        sufijo = str(n)
        clave = (base[: 20 - len(sufijo)] + sufijo)[:20]
        n += 1
        if n > 30:
            return None
    return clave


def areas_rueda(user_id: int | None = None) -> tuple[tuple[str, str, str], ...]:
    from app.rueda import AREAS

    uid_i = _uid(user_id)
    raw = leer_prefs(uid_i)["rueda"]
    overrides = {k: v for k, v in raw.items() if isinstance(v, str)}
    ocultas = set(_ocultas_rueda(raw))
    out = []
    for clave, nombre, emoji in AREAS:
        if clave in ocultas:
            continue
        out.append((clave, _nombre_area(clave, nombre, overrides), emoji))
    out.extend(_extras_rueda(raw))
    if len(out) < _RUEDA_MIN:
        out = [
            (clave, _nombre_area(clave, nombre, overrides), emoji)
            for clave, nombre, emoji in AREAS
        ]
    return tuple(out[:_RUEDA_MAX])


def catalogo_areas_rueda(user_id: int | None = None) -> list[dict]:
    """Cada radio que Configuración puede mostrar u ocultar."""
    from app.rueda import AREAS

    uid_i = _uid(user_id)
    raw = leer_prefs(uid_i)["rueda"]
    overrides = {k: v for k, v in raw.items() if isinstance(v, str)}
    ocultas = set(_ocultas_rueda(raw))
    filas = []
    for clave, nombre, emoji in AREAS:
        filas.append({
            "clave": clave,
            "nombre": _nombre_area(clave, nombre, overrides),
            "emoji": emoji,
            "activo": clave not in ocultas,
        })
    for clave, nombre, emoji in _extras_rueda(raw):
        filas.append({"clave": clave, "nombre": nombre, "emoji": emoji, "activo": True})
    return filas


def rueda_desde_eleccion(
    prev: dict,
    *,
    activas: list[str],
    nueva: str,
    nueva_emoji: str,
    etiquetas: dict[str, str],
) -> tuple[dict | None, str | None]:
    """Arma rueda_json. None y un mensaje si quedan menos de 3 o más de 12."""
    from app.rueda import AREAS, CLAVES

    prev = prev if isinstance(prev, dict) else {}
    base = list(CLAVES)
    extras_prev = _extras_rueda(prev)
    conocidas = set(base) | {clave for clave, _, _ in extras_prev}
    on = {str(item) for item in activas or [] if str(item) in conocidas}
    ocultas = [clave for clave in base if clave not in on]
    extras = []
    for clave, nombre, emoji in extras_prev:
        if clave not in on:
            continue
        texto = str(etiquetas.get(clave) or "").strip()[:40]
        extras.append((clave, texto or nombre, emoji))
    nombre_nuevo = (nueva or "").strip()[:40]
    if nombre_nuevo:
        if len(extras) >= _RUEDA_EXTRA_MAX:
            return None, "La rueda admite hasta 12 áreas."
        clave = _clave_area(nombre_nuevo, set(base) | {c for c, _, _ in extras})
        if not clave:
            return None, "La rueda admite hasta 12 áreas."
        emoji = (nueva_emoji or "").strip()[:4] or "•"
        extras.append((clave, nombre_nuevo, emoji))
    visibles = (len(base) - len(ocultas)) + len(extras)
    if visibles < _RUEDA_MIN:
        return None, "Deja al menos 3 áreas en la rueda."
    if visibles > _RUEDA_MAX:
        return None, "La rueda admite hasta 12 áreas."
    rueda: dict = {}
    for clave, _nombre, _emoji in AREAS:
        texto = str(etiquetas.get(clave) or "").strip()[:40]
        if texto:
            rueda[clave] = texto
        elif isinstance(prev.get(clave), str) and str(prev.get(clave)).strip():
            rueda[clave] = str(prev[clave]).strip()[:40]
    if ocultas:
        rueda["_ocultas"] = ocultas
    if extras:
        rueda["_extra"] = [
            {"clave": clave, "nombre": nombre, "emoji": emoji}
            for clave, nombre, emoji in extras
        ]
    return rueda, None


def rueda_conservando_estructura(prev: dict, etiquetas: dict[str, str]) -> dict:
    """Un guardado viejo, sin el formulario de áreas, no borra radios ocultos ni añadidos."""
    from app.rueda import AREAS

    prev = prev if isinstance(prev, dict) else {}
    rueda: dict = {}
    for clave, _nombre, _emoji in AREAS:
        texto = str(etiquetas.get(clave) or "").strip()[:40]
        if texto:
            rueda[clave] = texto
    if isinstance(prev.get("_ocultas"), list):
        rueda["_ocultas"] = prev["_ocultas"]
    if isinstance(prev.get("_extra"), list):
        rueda["_extra"] = prev["_extra"]
    return rueda


def metricas_salud(user_id: int | None = None) -> set[str]:
    todas = {"sueno", "energia_manana", "energia_tarde", "energia_noche"}
    elegidas = leer_prefs(user_id)["salud"]
    if not elegidas:
        return todas
    return {m for m in elegidas if m in todas} or todas


def _json_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _json_lista(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def guardar_modulos(
    user_id: int,
    *,
    activos: set[str],
    tope: int | None,
) -> str | None:
    """Activa o apaga sin borrar datos. Devuelve un error o None."""
    from app.db.core import ejecutar, invalidate_data_caches
    from app.multiuser import _ensure_user_modulos_table
    from app.onboarding import listar_modulos_usuario

    _ensure_user_modulos_table(ejecutar)
    validas = set(MODULE_TEMPLATES) | set(SUPERFICIES)
    activos = {c for c in activos if c in validas}
    vida = [c for c in activos if c in MODULE_TEMPLATES]
    if tope is not None and len(vida) > int(tope):
        return f"Tu plan permite máximo {int(tope)} áreas."

    actuales = {r["modulo"]: r for r in listar_modulos_usuario(user_id)}
    orden = 0
    for clave in list(MODULE_TEMPLATES) + list(SUPERFICIES):
        orden += 1
        activo = 1 if clave in activos else 0
        previo = actuales.get(clave) or {}
        cfg = _json_dict(previo.get("config_json"))
        ejecutar(
            """
            INSERT INTO user_modulos (user_id, modulo, activo, config_json, orden)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, modulo) DO UPDATE SET
                activo = excluded.activo,
                config_json = excluded.config_json,
                orden = excluded.orden
            """,
            [user_id, clave, activo, json.dumps(cfg, ensure_ascii=False), orden],
        )
    invalidate_data_caches()
    return None


def catalogo_sobres(user_id: int | None = None) -> dict:
    from app.db.core import ejecutar
    from app.db.schema import SOBRES_CONFIG

    asegurar_schema()
    uid_i = _uid(user_id)
    rows = ejecutar(
        """
        SELECT clave, nombre, emoji, orden
        FROM finanzas_categorias
        WHERE user_id = ?
        ORDER BY orden, nombre
        """,
        [uid_i],
        fetchall=True,
    ) or []
    if not rows:
        return dict(SOBRES_CONFIG)
    out = {}
    for row in rows:
        clave = str(row.get("clave") or "")
        if not _IDENT.match(clave):
            continue
        base = SOBRES_CONFIG.get(clave, {})
        out[clave] = {
            "nombre": (row.get("nombre") or clave)[:40],
            "emoji": (row.get("emoji") or base.get("emoji") or "💰")[:4],
            "descripcion": base.get("descripcion") or "",
            "color": base.get("color") or "#58a6ff",
            "subcategorias": list(base.get("subcategorias") or ["General"]),
        }
    return out or dict(SOBRES_CONFIG)


def sobre_permitido(clave: str, user_id: int | None = None) -> bool:
    return clave in catalogo_sobres(user_id)


def guardar_categorias(user_id: int, categorias: list[tuple[str, str]]) -> None:
    from app.db.core import ejecutar, invalidate_data_caches
    from app.db.schema import SOBRES_CONFIG

    asegurar_schema()
    limpias = []
    vistas = set()
    for clave, nombre in categorias:
        clave = re.sub(r"[^A-Za-z0-9_]", "", (clave or ""))[:32]
        nombre = (nombre or "").strip()[:40]
        if not clave or not nombre or clave in vistas:
            continue
        vistas.add(clave)
        emoji = (SOBRES_CONFIG.get(clave) or {}).get("emoji") or "💰"
        limpias.append((clave, nombre, emoji))
    if not limpias:
        return
    ejecutar("DELETE FROM finanzas_categorias WHERE user_id = ?", [user_id])
    for i, (clave, nombre, emoji) in enumerate(limpias, start=1):
        ejecutar(
            """
            INSERT INTO finanzas_categorias (user_id, clave, nombre, emoji, orden)
            VALUES (?, ?, ?, ?, ?)
            """,
            [user_id, clave, nombre, emoji, i],
        )
    invalidate_data_caches()


def clave_categoria(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", (nombre or "").strip())
    return base.strip("_")[:32]


def frecuencia_desde_eleccion(seleccion: str, dias: list[str] | None = None) -> str | None:
    """Un preset, o los días marcados. None si «días concretos» queda vacío."""
    sel = (seleccion or "").strip().lower()
    presets = {k for k, _ in FRECUENCIAS}
    if sel == "custom":
        elegidos = [clave for clave, _ in DIAS_HABITO if clave in set(dias or [])]
        if not elegidos:
            return None
        if len(elegidos) == len(DIAS_HABITO):
            return "diaria"
        return ",".join(elegidos)
    if sel in presets:
        return sel
    return "diaria"


def dias_de_frecuencia(frecuencia: str | None) -> set[str]:
    freq = (frecuencia or "diaria").strip().lower()
    if freq in ("", "diaria"):
        return {clave for clave, _ in DIAS_HABITO}
    if freq == "semanal":
        return {"lun"}
    return {p.strip() for p in freq.split(",") if p.strip() in {c for c, _ in DIAS_HABITO}}


def habito_toca(frecuencia: str | None, dia: date) -> bool:
    freq = (frecuencia or "diaria").strip().lower()
    if freq in ("", "diaria"):
        return True
    clave = _DIAS[dia.weekday()]
    if freq == "semanal":
        return dia.weekday() == 0
    partes = {p.strip() for p in freq.split(",") if p.strip()}
    return clave in partes


def exportar_datos(user_id: int) -> dict:
    from app.db.core import ejecutar

    asegurar_schema()
    payload = {"user_id": int(user_id), "tablas": {}}
    usuario = ejecutar(
        "SELECT * FROM usuarios WHERE id = ?",
        [user_id],
        fetchall=True,
    ) or []
    if usuario:
        fila = {k: v for k, v in dict(usuario[0]).items() if k not in _SECRETOS}
        payload["tablas"]["usuarios"] = [fila]
    for nombre in _tablas_con_user_id(ejecutar):
        if nombre == "usuarios":
            continue
        rows = ejecutar(
            f"SELECT * FROM {nombre} WHERE user_id = ?",
            [user_id],
            fetchall=True,
        ) or []
        payload["tablas"][nombre] = [
            {k: v for k, v in dict(r).items() if k not in _SECRETOS} for r in rows
        ]
    return payload


def borrar_cuenta(user_id: int, password: str) -> tuple[bool, str]:
    from app.db.core import ejecutar, invalidate_data_caches
    from app.db.usuarios import verificar_password

    rows = ejecutar(
        "SELECT password_hash, salt FROM usuarios WHERE id = ?",
        [user_id],
        fetchall=True,
    ) or []
    if not rows or not verificar_password(password or "", rows[0]["password_hash"], rows[0]["salt"]):
        return False, "La contraseña no coincide."
    for nombre in _tablas_con_user_id(ejecutar):
        if nombre == "usuarios":
            continue
        ejecutar(f"DELETE FROM {nombre} WHERE user_id = ?", [user_id])
    ejecutar("DELETE FROM usuarios WHERE id = ?", [user_id])
    invalidate_data_caches()
    return True, "Cuenta eliminada."


def _tablas_con_user_id(ejecutar) -> list[str]:
    tablas = ejecutar(
        "SELECT name FROM sqlite_master WHERE type = 'table'",
        fetchall=True,
    ) or []
    out = []
    for row in tablas:
        nombre = str(row.get("name") or "")
        if not _IDENT.match(nombre) or nombre.startswith("sqlite_"):
            continue
        cols = ejecutar(f"PRAGMA table_info({nombre})", fetchall=True) or []
        if any(str(c.get("name")) == "user_id" for c in cols):
            out.append(nombre)
    return out
