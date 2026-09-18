"""Telegram Bot API — briefing, gastos, tareas y audio.

Sustituye WhatsApp Cloud API (Meta): BotFather, gratis, opt-in (el bot
no escribe a extraños). Un chat no vinculado NUNCA ejecuta acciones.
Plan Premium/Familia. Rate-limit propio por chat_id (no bypasea login).
Groq cuenta en uso_ia. Recordatorios: telegram_reminders + cron.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib import request as urlrequest

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy, iso_ahora

log = get_logger("telegram")

BRIEFING_WORDS = ("briefing", "agenda", "resumen", "foco", "hoy qué", "que hay hoy")
CODE_RE = re.compile(r"^\s*(\d{6})\s*$")
START_RE = re.compile(r"^/start(?:\s+|_)(\d{6})\s*$", re.I)
AMOUNT_RE = re.compile(
    r"(?:\$\s*)?(\d+(?:[.,]\d{1,2})?)\s*(?:pesos|mxn|\$)?\s*(?:en|de)?\s*(.+)$",
    re.I,
)
API_BASE = "https://api.telegram.org"


def ensure_telegram_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS telegram_links (
            user_id INTEGER PRIMARY KEY,
            chat_id TEXT,
            tg_username TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            verify_hash TEXT,
            verify_expires TEXT,
            linked_at TEXT
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_chat
            ON telegram_links(chat_id)
            WHERE chat_id IS NOT NULL AND chat_id != ''
        """,
        """
        CREATE TABLE IF NOT EXISTS telegram_seen (
            update_id TEXT PRIMARY KEY,
            chat_id TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS telegram_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            evento_id INTEGER,
            chat_id TEXT NOT NULL,
            titulo TEXT,
            fire_at TEXT NOT NULL,
            sent_at TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tg_remind_fire ON telegram_reminders(sent_at, fire_at)",
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.debug("ensure_telegram_schema: %s", e)


def _secret(name: str, default: str = "") -> str:
    from app.secrets import get_secret

    return (get_secret(name, default) or "").strip()


def verify_webhook_secret(header: str | None, expected: str | None = None) -> bool:
    secret = (expected if expected is not None else _secret("TELEGRAM_WEBHOOK_SECRET")).strip()
    got = (header or "").strip()
    if not secret or not got:
        return False
    return hmac.compare_digest(secret, got)


def _hash_code(code: str) -> str:
    pepper = _secret("SESSION_SECRET") or _secret("TELEGRAM_WEBHOOK_SECRET") or "dev"
    return hashlib.sha256(f"{pepper}:{code}".encode("utf-8")).hexdigest()


def _user_by_id(user_id: int) -> dict | None:
    from app.db.core import ejecutar

    rows = ejecutar(
        "SELECT * FROM usuarios WHERE id = ? AND COALESCE(activo, 1) = 1",
        [int(user_id)],
        fetchall=True,
    )
    return rows[0] if rows else None


def bot_username() -> str:
    name = _secret("TELEGRAM_BOT_USERNAME").lstrip("@")
    if name:
        return name
    token = _secret("TELEGRAM_BOT_TOKEN")
    if not token:
        return ""
    try:
        data = _api("getMe")
        uname = str((data.get("result") or {}).get("username") or "")
        return uname
    except Exception as e:
        log.debug("getMe: %s", e)
        return ""


def deep_link(code: str) -> str:
    uname = bot_username()
    if not uname or not code:
        return ""
    return f"https://t.me/{uname}?start={code}"


def link_status(user_id: int) -> dict | None:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            "SELECT * FROM telegram_links WHERE user_id = ?",
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def find_link_by_chat(chat_id: str) -> dict | None:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    cid = str(chat_id or "").strip()
    if not cid:
        return None
    rows = (
        ejecutar(
            "SELECT * FROM telegram_links WHERE chat_id = ?",
            [cid],
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def start_link(user_id: int) -> tuple[bool, str, str | None]:
    """Genera código de 6 dígitos. El vínculo se completa desde Telegram (/start)."""
    ensure_telegram_schema()
    from app.db.core import ejecutar

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None).isoformat(timespec="seconds")
    ejecutar("DELETE FROM telegram_links WHERE user_id = ? AND COALESCE(verified, 0) = 0", [int(user_id)])
    existing = link_status(user_id)
    if existing and int(existing.get("verified") or 0) == 1:
        ejecutar("DELETE FROM telegram_links WHERE user_id = ?", [int(user_id)])
    try:
        ejecutar(
            """
            INSERT INTO telegram_links
                (user_id, chat_id, tg_username, verified, verify_hash, verify_expires, linked_at)
            VALUES (?, NULL, NULL, 0, ?, ?, NULL)
            """,
            [int(user_id), _hash_code(code), expires],
        )
    except Exception as e:
        log.warning("start_link insert: %s", e)
        return False, "No se pudo guardar el vínculo.", None
    from app.audit import registrar

    registrar("telegram_link_start", "telegram_links", user_id, None)
    return True, "Código generado. Vence en 10 minutos.", code


def unlink(user_id: int) -> None:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    ejecutar("DELETE FROM telegram_links WHERE user_id = ?", [int(user_id)])
    from app.audit import registrar

    registrar("telegram_unlink", "telegram_links", user_id, None)


def _find_pending_by_code(code: str) -> dict | None:
    from app.db.core import ejecutar

    m = CODE_RE.match((code or "").strip())
    if not m:
        return None
    digest = _hash_code(m.group(1))
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    rows = (
        ejecutar(
            """
            SELECT * FROM telegram_links
             WHERE verified = 0 AND verify_hash = ? AND verify_expires >= ?
             ORDER BY user_id LIMIT 1
            """,
            [digest, now],
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def _complete_link(row: dict, chat_id: str, username: str = "") -> tuple[bool, str]:
    from app.db.core import ejecutar

    cid = str(chat_id or "").strip()
    if not cid:
        return False, "Chat inválido."
    taken = find_link_by_chat(cid)
    if taken and int(taken["user_id"]) != int(row["user_id"]):
        return False, "Ese Telegram ya está vinculado a otra cuenta."
    ejecutar(
        """
        UPDATE telegram_links
           SET verified = 1, chat_id = ?, tg_username = ?,
               verify_hash = NULL, verify_expires = NULL, linked_at = ?
         WHERE user_id = ?
        """,
        [cid, (username or "")[:64], iso_ahora(), int(row["user_id"])],
    )
    from app.audit import registrar

    registrar("telegram_link_ok", "telegram_links", row["user_id"], None)
    return True, "Listo, Telegram vinculado. Mandá «briefing», un gasto («35 en super») o una tarea."


def _extract_code(text: str) -> str:
    raw = (text or "").strip()
    m = START_RE.match(raw)
    if m:
        return m.group(1)
    m = CODE_RE.match(raw)
    return m.group(1) if m else ""


def _mark_seen(update_id: str, chat_id: str) -> bool:
    if not update_id:
        return True
    from app.db.core import ejecutar

    try:
        ejecutar(
            "INSERT INTO telegram_seen (update_id, chat_id) VALUES (?, ?)",
            [str(update_id), str(chat_id)],
        )
        return True
    except Exception:
        return False


def extract_inbound(payload: dict) -> list[dict]:
    """Normaliza un Update de Telegram a {chat_id, username, update_id, text, voice_id}."""
    msg = payload.get("message") or payload.get("edited_message") or {}
    if not isinstance(msg, dict) or not msg:
        return []
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return []
    from_u = msg.get("from") or {}
    item = {
        "chat_id": chat_id,
        "username": str(from_u.get("username") or ""),
        "update_id": str(payload.get("update_id") or msg.get("message_id") or ""),
        "text": str(msg.get("text") or msg.get("caption") or ""),
        "voice_id": "",
    }
    voice = msg.get("voice") or msg.get("audio") or {}
    if isinstance(voice, dict):
        item["voice_id"] = str(voice.get("file_id") or "")
    return [item]


def _api(method: str, payload: dict | None = None, *, timeout: int = 20) -> dict:
    token = _secret("TELEGRAM_BOT_TOKEN")
    if not token:
        return {}
    url = f"{API_BASE}/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def send_text(chat_id: str, body: str, send_fn: Callable | None = None) -> bool:
    text = (body or "").strip()[:3500]
    if not text:
        return False
    if send_fn is not None:
        send_fn(chat_id, text)
        return True
    if not _secret("TELEGRAM_BOT_TOKEN"):
        log.info("telegram send skipped (no token): %s", text[:80])
        return False
    try:
        _api("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        return True
    except Exception as e:
        log.warning("telegram send failed: %s", e)
        return False


def _download_voice(file_id: str) -> bytes:
    if not file_id or not _secret("TELEGRAM_BOT_TOKEN"):
        return b""
    try:
        meta = _api("getFile", {"file_id": file_id})
        path = str((meta.get("result") or {}).get("file_path") or "")
        if not path:
            return b""
        token = _secret("TELEGRAM_BOT_TOKEN")
        req = urlrequest.Request(f"{API_BASE}/file/bot{token}/{path}")
        with urlrequest.urlopen(req, timeout=40) as resp:
            return resp.read(6_000_000)
    except Exception as e:
        log.warning("telegram media: %s", e)
        return b""


def register_webhook(app_url: str = "") -> bool:
    """setWebhook con secret_token. No falla el arranque si Telegram no responde."""
    token = _secret("TELEGRAM_BOT_TOKEN")
    secret = _secret("TELEGRAM_WEBHOOK_SECRET")
    base = (app_url or _secret("APP_URL")).rstrip("/")
    if not token or not secret or not base.startswith("https://"):
        return False
    url = f"{base}/telegram/webhook"
    try:
        data = _api(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret,
                "allowed_updates": ["message"],
            },
        )
        ok = bool(data.get("ok"))
        log.info("telegram setWebhook %s → %s", url, data.get("description") or ok)
        return ok
    except Exception as e:
        log.warning("telegram setWebhook: %s", e)
        return False


def handle_inbound(
    chat_id: str,
    *,
    text: str = "",
    voice_id: str = "",
    update_id: str = "",
    username: str = "",
    send_fn: Callable | None = None,
    transcribe_fn: Callable | None = None,
    parse_fn: Callable | None = None,
    download_fn: Callable | None = None,
) -> str:
    from app.rate_limit import telegram_permitido
    from app.tenant import clear_current_user, set_current_user

    ensure_telegram_schema()
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return ""
    if not telegram_permitido(chat_id):
        log.info("telegram rate-limit chat=%s", chat_id[-4:])
        return ""
    if update_id and not _mark_seen(update_id, chat_id):
        return ""

    def reply(body: str) -> str:
        send_text(chat_id, body, send_fn=send_fn)
        return body

    link = find_link_by_chat(chat_id)
    if not link or int(link.get("verified") or 0) != 1:
        code = _extract_code(text)
        pending = _find_pending_by_code(code) if code else None
        if pending:
            ok, msg = _complete_link(pending, chat_id, username)
            return reply(msg if ok else msg)
        return reply(
            "Este Telegram no está vinculado a Mission Dashboard. "
            "Entrá a la app → Usuarios → Telegram, generá un código y pulsá Start en el bot "
            "(o mandá el código de 6 dígitos)."
        )

    user = _user_by_id(int(link["user_id"]))
    if not user:
        return reply("Tu cuenta está inactiva.")

    from app.billing import plan_vigente, puede_telegram

    if not puede_telegram(plan_vigente(user)):
        return reply("Telegram requiere plan Premium o Familia. Activalo en /app/billing — no ejecuté ninguna acción.")

    token = set_current_user(user)
    try:
        body = (text or "").strip()
        if voice_id and not body:
            body = _transcribe_inbound(voice_id, transcribe_fn, download_fn)
            if not body:
                return reply("No pude transcribir el audio. Probá en texto.")
        if not body:
            return reply("No entendí el mensaje. Probá «briefing», «35 en super» o «mañana 5pm llamar al banco».")
        if body.startswith("/"):
            cmd = body.split()[0].lower()
            if cmd in ("/briefing", "/hoy", "/agenda"):
                return reply(build_briefing(int(user["id"])))
            if cmd == "/start":
                return reply("Ya estás vinculado. Mandá «briefing», un gasto o una tarea.")
        return reply(_dispatch(user, body, chat_id, parse_fn=parse_fn))
    except Exception as e:
        log.exception("telegram handle: %s", e)
        return reply("Hubo un error procesando el mensaje. No se guardó nada.")
    finally:
        clear_current_user()


def _transcribe_inbound(
    voice_id: str,
    transcribe_fn: Callable | None,
    download_fn: Callable | None,
) -> str:
    import tempfile
    from pathlib import Path

    data = (download_fn or _download_voice)(voice_id)
    if not data:
        return ""
    if transcribe_fn is not None:
        return (transcribe_fn(data) or "").strip()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as fh:
        fh.write(data)
        path = Path(fh.name)
    try:
        from app.exercise_ai import transcribe_audio

        return (transcribe_audio(path) or "").strip()
    except Exception as e:
        log.warning("stt: %s", e)
        return ""
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _dispatch(user: dict, text: str, chat_id: str, parse_fn: Callable | None = None) -> str:
    low = text.lower().strip()
    if any(w in low for w in BRIEFING_WORDS) or low in ("hoy", "agenda"):
        return build_briefing(int(user["id"]))

    parsed = parse_fn(text) if parse_fn is not None else parse_intent(text)
    intent = (parsed or {}).get("intent") or "unknown"
    if intent == "briefing":
        return build_briefing(int(user["id"]))
    if intent == "gasto":
        return _apply_gasto(parsed, text)
    if intent == "tarea":
        return _apply_tarea(parsed, text, chat_id, int(user["id"]))
    if AMOUNT_RE.search(text):
        return _apply_gasto(_heuristic_gasto(text), text)
    return _apply_tarea(_heuristic_tarea(text), text, chat_id, int(user["id"]))


def parse_intent(text: str) -> dict:
    from app.ai_client import chat_simple

    prompt = (
        "Clasificá el mensaje del usuario de un dashboard personal. "
        "Respondé SOLO un JSON con claves: intent (gasto|tarea|briefing|unknown), "
        "monto (número o null), categoria (necesidades|deseos|ahorro o null), "
        "descripcion, titulo, fecha (YYYY-MM-DD o null), hora_inicio (HH:MM o null), "
        "hora_fin (HH:MM o null). Hoy es "
        f"{_hoy().isoformat()}. Mensaje: {text[:400]}"
    )
    raw = chat_simple(
        prompt,
        contexto="Sos un parser. Solo JSON válido, sin markdown.",
    ) or ""
    data = _extract_json(raw)
    return data or {"intent": "unknown"}


def _extract_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _heuristic_gasto(text: str) -> dict:
    m = AMOUNT_RE.search(text.strip())
    if not m:
        return {"intent": "unknown"}
    monto = float(m.group(1).replace(",", "."))
    desc = (m.group(2) or "gasto").strip()[:80]
    cat = "necesidades"
    low = text.lower()
    if any(w in low for w in ("cafe", "cine", " ocio", "gusto", "netflix")):
        cat = "deseos"
    if any(w in low for w in ("ahorro", "inver")):
        cat = "ahorro"
    return {"intent": "gasto", "monto": monto, "categoria": cat, "descripcion": desc}


def _heuristic_tarea(text: str) -> dict:
    from app.timezone_config import hoy as hoy_fn

    fecha = hoy_fn()
    low = text.lower()
    if "mañana" in low or "manana" in low:
        fecha = fecha + timedelta(days=1)
    hora = None
    hm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
    if hm:
        h = int(hm.group(1))
        mi = int(hm.group(2) or 0)
        ap = (hm.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        hora = f"{h:02d}:{mi:02d}"
    titulo = re.sub(r"mañana|manana|\d{1,2}(?::\d{2})?\s*(am|pm)?", "", text, flags=re.I)
    titulo = " ".join(titulo.split()).strip() or text[:80]
    return {
        "intent": "tarea",
        "titulo": titulo[:80],
        "fecha": fecha.isoformat(),
        "hora_inicio": hora or "09:00",
        "hora_fin": None,
    }


def _apply_gasto(parsed: dict, original: str) -> str:
    from app.database import agregar_gasto_sobre
    from app.presupuesto import CATEGORIA_A_SOBRE

    if not parsed or parsed.get("intent") not in ("gasto", None):
        parsed = _heuristic_gasto(original)
    try:
        monto = float(str(parsed.get("monto") or "0").replace(",", "."))
    except Exception:
        monto = 0.0
    if monto <= 0:
        return "No pude sacar el monto. Ejemplo: «35 en supermercado»."
    cat = str(parsed.get("categoria") or "necesidades")
    if cat not in CATEGORIA_A_SOBRE:
        cat = "necesidades"
    sobre, sub = CATEGORIA_A_SOBRE[cat]
    desc = str(parsed.get("descripcion") or original).strip()[:120] or "Gasto Telegram"
    agregar_gasto_sobre(str(_hoy()), sobre, sub, desc, monto, origen="telegram")
    return f"Gasté {monto:g} en «{desc}» → {cat}."


def _apply_tarea(parsed: dict, original: str, chat_id: str, user_id: int) -> str:
    from app.database import COLORES_TIPO, guardar_evento

    if not parsed or parsed.get("intent") in (None, "unknown"):
        parsed = _heuristic_tarea(original)
    titulo = str(parsed.get("titulo") or original).strip()[:80] or "Tarea"
    fecha = str(parsed.get("fecha") or _hoy())
    hora = str(parsed.get("hora_inicio") or "09:00")[:5]
    fin = str(parsed.get("hora_fin") or "")[:5]
    if not fin:
        try:
            h, m = int(hora[:2]), int(hora[3:5] or 0)
            end_m = h * 60 + m + 60
            fin = f"{end_m // 60:02d}:{end_m % 60:02d}"
        except Exception:
            fin = "10:00"
    eid = guardar_evento(
        {
            "fecha": fecha,
            "hora_inicio": hora,
            "hora_fin": fin,
            "titulo": titulo,
            "descripcion": "vía Telegram",
            "tipo": "Personal",
            "color": COLORES_TIPO.get("Personal", "#58a6ff"),
            "fuente": "local",
        },
        sync_google=True,
    )
    schedule_reminder(user_id, eid, fecha, hora, titulo, chat_id)
    return f"Tarea creada: {titulo} el {fecha} a las {hora} (sync Calendar si está vinculado)."


def build_briefing(user_id: int) -> str:
    from app.calendar_sync import items_foco
    from app.db.core import ejecutar
    from app.timezone_config import hoy as hoy_fn

    dia = str(hoy_fn())
    items = items_foco(dia, user_id=user_id)
    lineas = [f"Foco {dia}"]
    hab = [i for i in items if i.get("kind") == "habito"]
    if hab:
        bits = []
        for h in hab[:8]:
            mark = "✓" if h.get("completado") else "·"
            bits.append(f"{mark} {h.get('titulo')}")
        lineas.append("Hábitos: " + "; ".join(bits))
    evs = [i for i in items if i.get("kind") in ("evento", "matrimonio")]
    if evs:
        bits = [f"{(e.get('hora_inicio') or '—')[:5]} {e.get('titulo')}" for e in evs[:8]]
        lineas.append("Agenda: " + "; ".join(bits))
    else:
        lineas.append("Agenda: sin eventos.")
    ent = next((i for i in items if i.get("kind") == "entrenamiento"), None)
    if ent:
        lineas.append(str(ent.get("titulo")))
    corte = (hoy_fn() - timedelta(days=7)).isoformat()
    gastos = (
        ejecutar(
            """
            SELECT descripcion, monto, sobre FROM gastos_sobres
            WHERE user_id = ? AND fecha >= ?
            ORDER BY fecha DESC, id DESC LIMIT 5
            """,
            [int(user_id), corte],
            fetchall=True,
        )
        or []
    )
    if gastos:
        bits = [f"{g.get('monto'):g} {g.get('descripcion')}" for g in gastos]
        lineas.append("Gastos 7d: " + "; ".join(bits))
    else:
        lineas.append("Gastos 7d: ninguno.")
    return "\n".join(lineas)[:1500]


def schedule_reminder(
    user_id: int,
    evento_id: int | None,
    fecha: str,
    hora: str,
    titulo: str,
    chat_id: str,
) -> None:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    try:
        fire = datetime.fromisoformat(f"{fecha}T{hora[:5]}:00") - timedelta(minutes=30)
    except Exception:
        return
    ejecutar(
        """
        INSERT INTO telegram_reminders (user_id, evento_id, chat_id, titulo, fire_at, sent_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        [int(user_id), evento_id, str(chat_id), titulo[:80], fire.isoformat(timespec="seconds")],
    )


def send_due_reminders(
    *,
    now: datetime | None = None,
    send_fn: Callable | None = None,
) -> int:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    stamp = (now or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat(timespec="seconds")
    rows = (
        ejecutar(
            """
            SELECT id, chat_id, titulo, fire_at FROM telegram_reminders
            WHERE sent_at IS NULL AND fire_at <= ?
            ORDER BY fire_at LIMIT 50
            """,
            [stamp],
            fetchall=True,
        )
        or []
    )
    n = 0
    for r in rows:
        ok = send_text(
            r["chat_id"],
            f"Recordatorio: {r.get('titulo') or 'tarea'} (en ~30 min).",
            send_fn=send_fn,
        )
        if ok or send_fn is not None:
            ejecutar(
                "UPDATE telegram_reminders SET sent_at = ? WHERE id = ?",
                [iso_ahora(), int(r["id"])],
            )
            n += 1
    return n
