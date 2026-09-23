"""Sync bidireccional Calendar ↔ Dashboard (Fase 4).

Inbound: polling (list + persist), no Google Calendar watch/webhook.
Watch exigiría un endpoint público y renovar el canal ~cada 7 días; este
app es FastAPI request-driven en Railway, de un solo tenant privado.
Pull al abrir Foco/Planificador/Agenda (throttle) y opcionalmente
`scripts/run_calendar_sync.py` por cron.

Outbound: create/update/delete inmediato de `eventos_calendario`.

Conflict rule: newest timestamp wins.
Compara `eventos_calendario.actualizado_en` vs Google event `updated`.
Si empatan o falta el timestamp de Google, gana local (eco de un push).
Borrados de Google: solo si `status=cancelled` (no por ausencia en la
ventana, para no borrar un evento que se movió de día).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy, iso_ahora

log = get_logger("calendar_sync")

POLL_MIN_SECONDS = 45
HORA_HABITO_VACIA = {"", "—", "-", "n/a", "na", "none"}


def ensure_calendar_sync_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS calendar_sync_state (
            user_id INTEGER PRIMARY KEY,
            last_poll_at TEXT,
            last_error TEXT,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE eventos_calendario ADD COLUMN actualizado_en TEXT",
        "ALTER TABLE eventos_calendario ADD COLUMN google_updated TEXT",
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.debug("ensure_calendar_sync_schema: %s", e)


def _uid(user_id: int | None = None) -> int:
    if user_id is not None:
        return int(user_id)
    from app.tenant import uid

    return int(uid())


def parse_ts(value: Any) -> datetime | None:
    """Parse ISO/RFC3339 timestamps to aware UTC datetime."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if "T" not in raw and " " in raw:
        raw = raw.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def newer_side(local_iso: str | None, google_iso: str | None) -> str:
    """Conflict rule: newest timestamp wins. Tie → local.

    Returns 'local', 'google', or 'equal'.
    """
    local_dt = parse_ts(local_iso)
    google_dt = parse_ts(google_iso)
    if local_dt is None and google_dt is None:
        return "equal"
    if local_dt is None:
        return "google"
    if google_dt is None:
        return "local"
    if local_dt > google_dt:
        return "local"
    if google_dt > local_dt:
        return "google"
    return "equal"


def _hora_habito(valor: Any) -> str | None:
    raw = str(valor or "").strip()
    if raw.lower() in HORA_HABITO_VACIA:
        return None
    if len(raw) >= 4 and raw[0].isdigit():
        return raw[:5]
    return None


def pull_range(
    fecha_inicio,
    fecha_fin,
    *,
    user_id: int | None = None,
    force: bool = False,
    list_events: Callable | None = None,
    push_event: Callable | None = None,
) -> dict:
    """Trae eventos de Google y los persiste en `eventos_calendario`."""
    ensure_calendar_sync_schema()
    from app.db.core import ejecutar, invalidate_data_caches

    uid_i = _uid(user_id)
    now = iso_ahora()
    if not force:
        state = (
            ejecutar(
                "SELECT last_poll_at FROM calendar_sync_state WHERE user_id = ?",
                [uid_i],
                fetchall=True,
            )
            or []
        )
        last = parse_ts(state[0]["last_poll_at"]) if state else None
        if last is not None:
            age = datetime.now(timezone.utc) - last
            if age.total_seconds() < POLL_MIN_SECONDS:
                return {"skipped": True, "reason": "throttle", "pulled": 0, "updated": 0, "deleted": 0}

    if list_events is None:
        from app.google_calendar import calendar_disponible, obtener_eventos_google

        if not calendar_disponible():
            _touch_state(uid_i, error="calendar_unavailable")
            return {"skipped": True, "reason": "unavailable", "pulled": 0, "updated": 0, "deleted": 0}

        def list_events(inicio, fin):
            return obtener_eventos_google(inicio, fin, include_deleted=True) or []

    try:
        remotos = list_events(fecha_inicio, fecha_fin) or []
    except Exception as e:
        log.warning("pull_range list failed: %s", e)
        _touch_state(uid_i, error=str(e)[:180])
        return {"skipped": True, "reason": "list_error", "pulled": 0, "updated": 0, "deleted": 0}

    locales = (
        ejecutar(
            """
            SELECT id, fecha, hora_inicio, hora_fin, titulo, descripcion, tipo, color,
                   google_id, fuente, actualizado_en, google_updated
            FROM eventos_calendario
            WHERE user_id = ? AND google_id IS NOT NULL AND google_id != ''
            """,
            [uid_i],
            fetchall=True,
        )
        or []
    )
    by_gid = {str(r["google_id"]): r for r in locales if r.get("google_id")}

    pulled = updated = deleted = pushed = 0
    for g in remotos:
        gid = str(g.get("google_id") or "")
        if not gid:
            continue
        status = str(g.get("status") or "confirmed").lower()
        local = by_gid.get(gid)
        if status in ("cancelled", "canceled"):
            if local and newer_side(local.get("actualizado_en"), g.get("updated")) != "local":
                ejecutar(
                    "DELETE FROM eventos_calendario WHERE id = ? AND user_id = ?",
                    [int(local["id"]), uid_i],
                )
                deleted += 1
            elif local and push_event:
                try:
                    push_event(local)
                    pushed += 1
                except Exception as e:
                    log.warning("re-push after cancelled: %s", e)
            continue

        payload = _from_google(g)
        if local is None:
            _insert_from_google(uid_i, payload)
            pulled += 1
            continue

        side = newer_side(local.get("actualizado_en"), payload.get("google_updated"))
        if side == "google":
            _update_from_google(uid_i, int(local["id"]), payload)
            updated += 1
        elif side == "local" and push_event:
            try:
                push_event(local)
                pushed += 1
            except Exception as e:
                log.warning("push stale google: %s", e)

    _touch_state(uid_i, error="")
    try:
        invalidate_data_caches()
    except Exception:
        pass
    log.info(
        "pull_range user=%s pulled=%s updated=%s deleted=%s pushed=%s",
        uid_i,
        pulled,
        updated,
        deleted,
        pushed,
    )
    return {
        "skipped": False,
        "pulled": pulled,
        "updated": updated,
        "deleted": deleted,
        "pushed": pushed,
        "at": now,
    }


def _from_google(g: dict) -> dict:
    return {
        "google_id": g.get("google_id"),
        "fecha": g.get("fecha"),
        "hora_inicio": g.get("hora_inicio"),
        "hora_fin": g.get("hora_fin"),
        "titulo": g.get("titulo") or "Sin título",
        "descripcion": g.get("descripcion") or "",
        "tipo": g.get("tipo") or "Personal",
        "color": g.get("color") or "#58a6ff",
        "fuente": "google_calendar",
        "google_updated": g.get("updated") or g.get("google_updated") or "",
        "actualizado_en": g.get("updated") or g.get("google_updated") or iso_ahora(),
    }


def _insert_from_google(uid_i: int, payload: dict) -> None:
    from app.db.core import ejecutar

    ejecutar(
        """
        INSERT INTO eventos_calendario
            (user_id, fecha, hora_inicio, hora_fin, titulo, descripcion,
             tipo, color, google_id, fuente, actualizado_en, google_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uid_i,
            payload["fecha"],
            payload.get("hora_inicio"),
            payload.get("hora_fin"),
            payload["titulo"],
            payload.get("descripcion") or "",
            payload.get("tipo") or "Personal",
            payload.get("color") or "#58a6ff",
            payload["google_id"],
            "google_calendar",
            payload.get("actualizado_en") or iso_ahora(),
            payload.get("google_updated") or "",
        ],
    )


def _update_from_google(uid_i: int, evento_id: int, payload: dict) -> None:
    from app.db.core import ejecutar

    ejecutar(
        """
        UPDATE eventos_calendario
           SET fecha=?, hora_inicio=?, hora_fin=?, titulo=?, descripcion=?,
               tipo=?, color=?, fuente='google_calendar',
               actualizado_en=?, google_updated=?
         WHERE id=? AND user_id=?
        """,
        [
            payload["fecha"],
            payload.get("hora_inicio"),
            payload.get("hora_fin"),
            payload["titulo"],
            payload.get("descripcion") or "",
            payload.get("tipo") or "Personal",
            payload.get("color") or "#58a6ff",
            payload.get("actualizado_en") or iso_ahora(),
            payload.get("google_updated") or "",
            evento_id,
            uid_i,
        ],
    )


def _touch_state(uid_i: int, error: str = "") -> None:
    from app.db.core import ejecutar

    ejecutar(
        """
        INSERT INTO calendar_sync_state (user_id, last_poll_at, last_error, actualizado_en)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_poll_at=excluded.last_poll_at,
            last_error=excluded.last_error,
            actualizado_en=excluded.actualizado_en
        """,
        [uid_i, iso_ahora(), error or None, iso_ahora()],
    )


def items_foco(fecha: str | None = None, user_id: int | None = None) -> list[dict]:
    """Eventos del día + hábitos con hora + entrenamiento, mezclados."""
    from app.db.core import ejecutar

    uid_i = _uid(user_id)
    dia = fecha or str(_hoy())
    items: list[dict] = []

    eventos = (
        ejecutar(
            """
            SELECT id, fecha, hora_inicio, hora_fin, titulo, descripcion, tipo, color,
                   google_id, COALESCE(fuente, 'local') AS fuente
            FROM eventos_calendario
            WHERE user_id = ? AND fecha = ?
            ORDER BY hora_inicio
            """,
            [uid_i, dia],
            fetchall=True,
        )
        or []
    )
    for e in eventos:
        fuente = str(e.get("fuente") or "local")
        origen = "google" if fuente in ("google_calendar", "google") or e.get("google_id") else "local"
        items.append({**dict(e), "origen": origen, "kind": "evento"})

    habitos = (
        ejecutar(
            """
            SELECT c.clave, c.label, c.emoji, c.hora,
                   COALESCE(d.completado, 0) AS completado
            FROM habitos_config c
            LEFT JOIN habitos_diarios_v2 d
              ON d.user_id = c.user_id AND d.habito_clave = c.clave AND d.fecha = ?
            WHERE c.user_id = ? AND COALESCE(c.activo, 1) = 1
            ORDER BY c.orden, c.label
            """,
            [dia, uid_i],
            fetchall=True,
        )
        or []
    )
    for h in habitos:
        hora = _hora_habito(h.get("hora"))
        items.append(
            {
                "id": None,
                "kind": "habito",
                "origen": "local",
                "titulo": f"{h.get('emoji') or '⭐'} {h.get('label') or h.get('clave')}",
                "hora_inicio": hora,
                "hora_fin": None,
                "fecha": dia,
                "google_id": None,
                "fuente": "habito",
                "completado": bool(int(h.get("completado") or 0)),
                "color": "#3fb950",
            }
        )

    salud = (
        ejecutar(
            """
            SELECT hizo_ejercicio, notas_ejercicio
            FROM registros_salud
            WHERE user_id = ? AND fecha = ?
            LIMIT 1
            """,
            [uid_i, dia],
            fetchall=True,
        )
        or []
    )
    if salud:
        row = salud[0]
        hecho = bool(int(row.get("hizo_ejercicio") or 0))
        nota = str(row.get("notas_ejercicio") or "").strip()
        items.append(
            {
                "id": None,
                "kind": "entrenamiento",
                "origen": "local",
                "titulo": "Entrenamiento" + (" hecho" if hecho else " pendiente"),
                "hora_inicio": None,
                "hora_fin": None,
                "fecha": dia,
                "google_id": None,
                "fuente": "salud",
                "completado": hecho,
                "color": "#f0883e",
                "descripcion": nota,
            }
        )

    citas = (
        ejecutar(
            """
            SELECT id, fecha, hora AS hora_inicio, titulo
            FROM matrimonio_citas
            WHERE user_id = ? AND fecha = ?
            ORDER BY hora
            """,
            [uid_i, dia],
            fetchall=True,
        )
        or []
    )
    for c in citas:
        items.append(
            {
                **dict(c),
                "kind": "matrimonio",
                "origen": "matrimonio",
                "hora_fin": None,
                "google_id": None,
                "fuente": "matrimonio",
                "color": "#a371f7",
            }
        )

    from datetime import date as _date

    from app.db.deep_work import bloques_en_rango

    dia_d = _date.fromisoformat(dia)
    for b in bloques_en_rango(dia_d, dia_d, uid_i):
        items.append(
            {
                "id": None,
                "kind": "enfoque",
                "origen": "enfoque",
                "titulo": b["nombre"],
                "hora_inicio": (b.get("hora_inicio") or "")[:5] or None,
                "hora_fin": (b.get("hora_fin") or "")[:5] or None,
                "fecha": dia,
                "google_id": None,
                "fuente": "deep_work",
                "completado": b["estado"] == "Completado",
                "color": b.get("color") or "#58a6ff",
            }
        )

    def _key(it: dict):
        return (it.get("hora_inicio") or "99:99", it.get("titulo") or "")

    items.sort(key=_key)
    return items


def pull_today(user_id: int | None = None, force: bool = False) -> dict:
    dia = _hoy()
    return pull_range(dia, dia, user_id=user_id, force=force)
