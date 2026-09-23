"""CRUD finanzas (ingreso mensual y gastos por sobre)."""
from __future__ import annotations

from app.db.core import ejecutar, invalidate_data_caches

def guardar_ingreso(mes: int, anio: int, monto: float, notas: str = "") -> bool:
    from app.tenant import uid
    try:
        ejecutar("""
            INSERT INTO ingreso_mensual (user_id, mes, anio, monto_total, notas)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, mes, anio)
            DO UPDATE SET monto_total = ?, notas = ?
        """, [uid(), mes, anio, monto, notas, monto, notas])
        try:
            invalidate_data_caches()
        except NameError:
            pass
        try:
            from app.audit import registrar

            registrar(
                "guardar_ingreso",
                "ingreso_mensual",
                f"{mes}-{anio}",
                {"mes": mes, "anio": anio, "monto": monto},
            )
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            ejecutar("""
                DELETE FROM ingreso_mensual
                WHERE user_id = ? AND mes = ? AND anio = ?
            """, [uid(), mes, anio])
            ejecutar("""
                INSERT INTO ingreso_mensual (user_id, mes, anio, monto_total, notas)
                VALUES (?, ?, ?, ?, ?)
            """, [uid(), mes, anio, monto, notas])
            try:
                invalidate_data_caches()
            except NameError:
                pass
            try:
                from app.audit import registrar

                registrar(
                    "guardar_ingreso",
                    "ingreso_mensual",
                    f"{mes}-{anio}",
                    {"mes": mes, "anio": anio, "monto": monto},
                )
            except Exception:
                pass
            return True
        except Exception as e2:
            print(f"Error guardando ingreso: {e} / {e2}")
            return False

def obtener_ingreso(mes: int, anio: int) -> float:
    from app.tenant import uid
    rows = ejecutar("""
        SELECT monto_total FROM ingreso_mensual
        WHERE user_id = ? AND mes = ? AND anio = ?
    """, [uid(), mes, anio], fetchall=True) or []
    return float(rows[0]["monto_total"]) if rows else 0.0

def agregar_gasto_sobre(
    fecha,
    sobre: str,
    subcategoria: str,
    descripcion: str,
    monto: float,
    es_fijo: bool = False,
    notas: str = "",
    *,
    comercio: str | None = None,
    metodo_pago: str | None = None,
    origen: str = "manual",
    imagen_url: str | None = None,
    raw_ocr_data: str | None = None,
    ocr_estado: str = "ninguno",
) -> int:
    from app.tenant import uid
    gid = ejecutar("""
        INSERT INTO gastos_sobres
            (user_id, fecha, sobre, subcategoria, descripcion, monto, es_fijo, notas,
             comercio, metodo_pago, origen, imagen_url, raw_ocr_data, ocr_estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        uid(), str(fecha), sobre, subcategoria, descripcion, monto,
        1 if es_fijo else 0, notas,
        comercio, metodo_pago, origen or "manual",
        imagen_url, raw_ocr_data, ocr_estado or "ninguno",
    ])
    try:
        invalidate_data_caches()
    except NameError:
        pass
    try:
        from app.audit import registrar

        registrar(
            "agregar_gasto",
            "gastos_sobres",
            gid,
            {
                "fecha": str(fecha),
                "sobre": sobre,
                "subcategoria": subcategoria,
                "monto": monto,
                "origen": origen or "manual",
            },
        )
    except Exception:
        pass
    return gid

def obtener_gastos_sobre(mes=None, anio=None, sobre=None, limite=100) -> list:
    from app.tenant import uid
    query = "SELECT * FROM gastos_sobres WHERE user_id = ?"
    params = [uid()]

    if mes and anio:
        query += """ AND strftime('%m', fecha) = ?
                    AND strftime('%Y', fecha) = ?"""
        params.extend([f"{mes:02d}", str(anio)])
    if sobre:
        query += " AND sobre = ?"
        params.append(sobre)

    query += " ORDER BY fecha DESC, creado_en DESC LIMIT ?"
    params.append(limite)

    return ejecutar(query, params, fetchall=True) or []

def actualizar_gasto_sobre(gasto_id: int, **kwargs) -> bool:
    from app.tenant import uid
    campos_permitidos = {
        'fecha', 'sobre', 'subcategoria',
        'descripcion', 'monto', 'es_fijo', 'notas',
        'comercio', 'metodo_pago', 'origen',
        'imagen_url', 'raw_ocr_data', 'ocr_estado',
    }
    campos = {}
    for k, v in kwargs.items():
        if k not in campos_permitidos or v is None:
            continue
        if k == 'fecha':
            campos[k] = str(v)
        elif k == 'es_fijo':
            campos[k] = 1 if v else 0
        else:
            campos[k] = v
    if not campos:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in campos)
    try:
        ejecutar(
            f"UPDATE gastos_sobres SET {set_clause} WHERE id = ? AND user_id = ?",
            list(campos.values()) + [gasto_id, uid()]
        )
        rows = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        if rows:
            try:
                invalidate_data_caches()
            except NameError:
                pass
            try:
                from app.audit import registrar

                registrar(
                    "actualizar_gasto",
                    "gastos_sobres",
                    gasto_id,
                    campos,
                )
            except Exception:
                pass
        return bool(rows)
    except Exception as e:
        print(f"Error actualizando gasto: {e}")
        return False

def eliminar_gasto_sobre(gasto_id: int) -> bool:
    from app.tenant import uid
    try:
        antes = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        if not antes:
            return False
        ejecutar(
            "DELETE FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()]
        )
        despues = ejecutar(
            "SELECT id FROM gastos_sobres WHERE id = ? AND user_id = ?",
            [gasto_id, uid()], fetchall=True
        ) or []
        ok = not despues
        if ok:
            try:
                invalidate_data_caches()
            except NameError:
                pass
            try:
                from app.audit import registrar

                registrar("eliminar_gasto", "gastos_sobres", gasto_id)
            except Exception:
                pass
        return ok
    except Exception as e:
        print(f"Error eliminando gasto: {e}")
        return False

def obtener_tipos_bloque() -> list:
    """
    Obtiene los tipos únicos ya usados en BD
    más los defaults, sin duplicados.
    """
    defaults = ['Instituto', 'Programacion', 'Biblioteca', 'Personal']
    try:
        from app.tenant import uid
        rows = ejecutar("""
            SELECT DISTINCT tipo FROM bloques_fijos
            WHERE user_id = ? AND tipo IS NOT NULL
            ORDER BY tipo
        """, [uid()], fetchall=True) or []
        en_bd = [row["tipo"] for row in rows]
        return list(dict.fromkeys(defaults + en_bd))
    except Exception:
        return defaults

