"""Telegram Bot API — transporte, vínculo, seguridad y router de intención.

Las acciones (briefing, gasto, tarea…) viven en ``app/telegram_actions/``.

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
import time
from datetime import datetime, timedelta
from typing import Callable
from urllib import request as urlrequest

from app import telegram_actions as acciones
from app.db import telegram_state as state
from app.logging_config import get_logger
from app.telegram_actions import Accion, Contexto, Respuesta
from app.telegram_actions.briefing import normalize
from app.timezone_config import hoy as _hoy, iso_ahora

log = get_logger("telegram")

LINK_TTL_MIN = 10
REMINDER_HORIZON_H = 24
MAX_TEXT_CHARS = 1000
LLM_MAX_TOKENS = 200
TG_MAX_MESSAGE = 4096
MAX_CHUNKS = 5
CODE_RE = re.compile(r"^\s*(\d{6})\s*$")
START_RE = re.compile(r"^/start(?:\s+|_)(\d{6})\s*$", re.I)
NO_ENTENDI = (
    "No entendí, así que no guardé nada.\n"
    "Probá: «35 en super», «/tarea mañana 5pm llamar al banco» o /briefing.\n"
    "/ayuda muestra todos los comandos."
)
API_BASE = "https://api.telegram.org"

BTN_BRIEFING = "📋 Briefing"
BTN_SALDO = "💸 Saldo"
BTN_HABITOS = "✅ Hábitos"
BTN_AYUDA = "❓ Ayuda"


def reply_keyboard(user_id: int | None = None) -> dict:
    from app.onboarding import modulo_activo

    fila = [{"text": BTN_BRIEFING}]
    if user_id is not None and modulo_activo("finanzas", user_id):
        fila.append({"text": BTN_SALDO})
    fila.append({"text": BTN_HABITOS})
    fila.append({"text": BTN_AYUDA})
    return {"keyboard": [fila], "resize_keyboard": True, "is_persistent": True}
BOT_COMMANDS = [
    {"command": "start", "description": "Vincular o ver el menú"},
    {"command": "briefing", "description": "Foco del día: agenda, hábitos y gastos"},
    {"command": "hoy", "description": "Lo mismo que /briefing"},
    {"command": "gasto", "description": "Anotar un gasto. Ej: /gasto 35 super"},
    {"command": "ingreso", "description": "Anotar el ingreso del mes. Ej: /ingreso 800"},
    {"command": "saldo", "description": "Ingreso, gastado y disponible por sobre"},
    {"command": "gastos", "description": "Últimos gastos, con número para /borrar"},
    {"command": "habitos", "description": "Hábitos de hoy"},
    {"command": "hecho", "description": "Marcar un hábito. Ej: /hecho leer"},
    {"command": "tarea", "description": "Crear una tarea. Ej: /tarea mañana 5pm banco"},
    {"command": "agenda", "description": "Agenda de hoy, mañana o la semana"},
    {"command": "sueno", "description": "Anotar el sueño. Ej: /sueno 7.5 calidad 4"},
    {"command": "salud", "description": "Resumen de salud de 7 días"},
    {"command": "enfoque", "description": "Bloques de enfoque de hoy"},
    {"command": "silencio", "description": "Pausar el briefing de la mañana"},
    {"command": "alma", "description": "Hablar con Alma. Ej: /alma cómo viene mi semana"},
    {"command": "coach", "description": "Briefing del coach, con su cupo semanal"},
    {"command": "semana", "description": "Resumen de la semana"},
    {"command": "deshacer", "description": "Deshacer lo último que guardé"},
    {"command": "ayuda", "description": "Cómo usar el bot"},
]


def help_text(*, linked: bool = True) -> str:
    body = (
        "Comandos:\n"
        "• /briefing — foco del día (agenda, hábitos, gastos)\n"
        "• /hoy — lo mismo que /briefing\n"
        "• /gasto 35 super — anotar un gasto\n"
        "• /ingreso 800 — ingreso del mes\n"
        "• /saldo — ingreso, gastado y disponible\n"
        "• /gastos — últimos 7, con número\n"
        "• /borrar 2 — borrar uno de la lista (pide confirmación)\n"
        "• /vencimientos — próximos 7 días\n"
        "• /habitos — hábitos de hoy\n"
        "• /hecho leer — marcar uno (o «ya leí»)\n"
        "• /tarea mañana 5pm banco — crear una tarea (va a Calendar si está vinculado)\n"
        "• /agenda [hoy|mañana|semana] — la agenda, con número\n"
        "• /sueno 7.5 calidad 4 — sueño de anoche\n"
        "• /energia 4 — energía (1 a 5); /energia tarde 3\n"
        "• /ejercicio pierna 45 min\n"
        "• /salud — resumen de 7 días\n"
        "• /enfoque — bloques de hoy; botones Completado, Parcial, Postergado\n"
        "• /silencio [días] — pausa el briefing de la mañana; /silencio 0 lo reanuda\n"
        "• /alma cómo viene mi semana — Alma (no se activa sola)\n"
        "• /coach — briefing del coach, respetando el cupo\n"
        "• /semana — resumen de la semana\n"
        "• /mover 2 18:00 — cambiar la hora (pide confirmación)\n"
        "• /cancelar 2 — borrar el evento (pide confirmación)\n"
        "• /deshacer — borrar lo último que guardé (hasta 30 min)\n"
        "• /ayuda — este mensaje\n\n"
        "También sirve texto suelto («35 en super») o una nota de voz.\n"
        "Desvincular: en la app → Usuarios → Telegram (no por el chat)."
    )
    if linked:
        return body
    return (
        "Este chat no está vinculado a Mission Dashboard.\n"
        "Entrá a la app → Usuarios → Telegram, generá un código y pulsá Start "
        "(o mandá el código de 6 dígitos).\n\n"
        + body
    )


def _command_parts(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if raw in (BTN_BRIEFING, "Briefing"):
        return "/briefing", ""
    if raw in (BTN_SALDO, "Saldo"):
        return "/saldo", ""
    if raw in (BTN_HABITOS, "Hábitos", "Habitos"):
        return "/habitos", ""
    if raw in (BTN_AYUDA, "Ayuda"):
        return "/ayuda", ""
    if not raw.startswith("/"):
        return "", raw
    first, _, rest = raw.partition(" ")
    cmd = first.split("@", 1)[0].lower()
    return cmd, rest.strip()


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
            sent_at TEXT,
            hora TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tg_remind_fire ON telegram_reminders(sent_at, fire_at)",
        """
        DELETE FROM telegram_reminders
         WHERE evento_id IS NOT NULL
           AND id NOT IN (
               SELECT MIN(id) FROM telegram_reminders
                WHERE evento_id IS NOT NULL
                GROUP BY user_id, evento_id, fire_at
           )
        """,
        "ALTER TABLE telegram_reminders ADD COLUMN hora TEXT",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tg_remind_evento
            ON telegram_reminders(user_id, evento_id, fire_at)
            WHERE evento_id IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS telegram_prefs (
            user_id INTEGER PRIMARY KEY,
            recordatorio_min INTEGER,
            briefing_extra TEXT,
            briefing_activo INTEGER NOT NULL DEFAULT 0,
            briefing_hora TEXT,
            silencio_hasta TEXT,
            ultimo_briefing TEXT
        )
        """,
        "ALTER TABLE telegram_prefs ADD COLUMN briefing_extra TEXT",
        "ALTER TABLE telegram_prefs ADD COLUMN briefing_activo INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE telegram_prefs ADD COLUMN briefing_hora TEXT",
        "ALTER TABLE telegram_prefs ADD COLUMN silencio_hasta TEXT",
        "ALTER TABLE telegram_prefs ADD COLUMN ultimo_briefing TEXT",
        """
        CREATE TABLE IF NOT EXISTS telegram_refs (
            chat_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            n INTEGER NOT NULL,
            entidad_id INTEGER NOT NULL,
            creado_en TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id, tipo, n)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS telegram_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            accion TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            expira_en TEXT NOT NULL,
            creado_en TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tg_pending_chat ON telegram_pending(chat_id, id)",
        """
        CREATE TABLE IF NOT EXISTS telegram_last_action (
            chat_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            accion TEXT NOT NULL,
            entidad_id INTEGER NOT NULL,
            resumen TEXT,
            expira_en TEXT NOT NULL,
            creado_en TEXT NOT NULL
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.debug("ensure_telegram_schema: %s", e)


def _secret(name: str, default: str = "") -> str:
    from app.secrets import get_secret

    return (get_secret(name, default) or "").strip()


def webhook_secret() -> str:
    """Secret_token de Telegram. Si no hay TELEGRAM_WEBHOOK_SECRET, se deriva de SESSION_SECRET."""
    explicit = _secret("TELEGRAM_WEBHOOK_SECRET")
    if explicit:
        cleaned = "".join(ch for ch in explicit if ch.isalnum() or ch in "_-")
        return cleaned[:256]
    session = _secret("SESSION_SECRET")
    if not session:
        return ""
    return hashlib.sha256(f"tg-webhook:{session}".encode("utf-8")).hexdigest()


def public_base_url() -> str:
    """https público: APP_URL o RAILWAY_PUBLIC_DOMAIN."""
    import os

    app = _secret("APP_URL").rstrip("/")
    if app.startswith("https://"):
        return app
    domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL") or "").strip()
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    if domain:
        return f"https://{domain}"
    return app


def verify_webhook_secret(header: str | None, expected: str | None = None) -> bool:
    secret = (expected if expected is not None else webhook_secret()).strip()
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
    from app.timezone_config import ahora

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (ahora() + timedelta(minutes=LINK_TTL_MIN)).isoformat(timespec="seconds")
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
    from app.timezone_config import ahora

    digest = _hash_code(m.group(1))
    now = ahora()
    # Tope superior: descarta vencimientos más lejanos que el TTL (p. ej. códigos viejos en UTC).
    rows = (
        ejecutar(
            """
            SELECT * FROM telegram_links
             WHERE verified = 0 AND verify_hash = ?
               AND verify_expires >= ? AND verify_expires <= ?
             ORDER BY user_id LIMIT 1
            """,
            [
                digest,
                now.isoformat(timespec="seconds"),
                (now + timedelta(minutes=LINK_TTL_MIN)).isoformat(timespec="seconds"),
            ],
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
    return True, (
        "Listo, Telegram vinculado.\n"
        + help_text(linked=True)
    )


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
    """Normaliza un Update (mensaje o botón inline) a
    {chat_id, username, update_id, text, voice_id, callback_id, callback_data}."""
    cq = payload.get("callback_query")
    if isinstance(cq, dict) and cq:
        return _extract_callback(payload, cq)
    msg = payload.get("message") or payload.get("edited_message") or {}
    if not isinstance(msg, dict) or not msg:
        return []
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return []
    if chat.get("type") != "private":
        log.info("telegram ignora chat no privado type=%s chat=%s", chat.get("type"), chat_id[-4:])
        return []
    from_u = msg.get("from") or {}
    item = {
        "chat_id": chat_id,
        "username": str(from_u.get("username") or ""),
        "update_id": str(payload.get("update_id") or msg.get("message_id") or ""),
        "text": str(msg.get("text") or msg.get("caption") or ""),
        "voice_id": "",
        "callback_id": "",
        "callback_data": "",
    }
    voice = msg.get("voice") or msg.get("audio") or {}
    if isinstance(voice, dict):
        item["voice_id"] = str(voice.get("file_id") or "")
    return [item]


def _extract_callback(payload: dict, cq: dict) -> list[dict]:
    chat = (cq.get("message") or {}).get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id or chat.get("type") != "private":
        return []
    return [
        {
            "chat_id": chat_id,
            "username": str((cq.get("from") or {}).get("username") or ""),
            "update_id": str(payload.get("update_id") or ""),
            "text": "",
            "voice_id": "",
            "callback_id": str(cq.get("id") or ""),
            "callback_data": str(cq.get("data") or "")[:64],
        }
    ]


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


def send_text(
    chat_id: str,
    body: str,
    send_fn: Callable | None = None,
    *,
    reply_markup: dict | None = None,
) -> bool:
    chunks = split_message(body)
    if not chunks:
        return False
    if send_fn is not None:
        for chunk in chunks:
            send_fn(chat_id, chunk)
        return True
    if not _secret("TELEGRAM_BOT_TOKEN"):
        log.info("telegram send skipped (no token) chars=%d", sum(len(c) for c in chunks))
        return False
    try:
        for i, chunk in enumerate(chunks):
            payload: dict = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            _api("sendMessage", payload)
        return True
    except Exception as e:
        log.warning("telegram send failed: %s", type(e).__name__)
        return False


def split_message(body: str, limit: int = TG_MAX_MESSAGE) -> list[str]:
    """Texto plano en trozos ≤ limit (tope de Telegram), cortando en saltos de línea si se puede."""
    text = (body or "").strip()
    chunks: list[str] = []
    while text and len(chunks) < MAX_CHUNKS:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit + 1)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return chunks


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


def answer_callback_query(callback_id: str) -> None:
    """Cierra el «cargando» del botón inline. Telegram lo exige aunque no haya texto."""
    if not callback_id or not _secret("TELEGRAM_BOT_TOKEN"):
        return
    try:
        _api("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception as e:
        log.warning("telegram answerCallbackQuery: %s", type(e).__name__)


def register_bot_commands() -> bool:
    """Publica el menú / del bot (setMyCommands). No exige HTTPS."""
    if not _secret("TELEGRAM_BOT_TOKEN"):
        return False
    try:
        data = _api("setMyCommands", {"commands": BOT_COMMANDS})
        ok = bool(data.get("ok"))
        log.info("telegram setMyCommands → %s", data.get("description") or ok)
        return ok
    except Exception as e:
        log.warning("telegram setMyCommands: %s", e)
        return False


def register_webhook(app_url: str = "") -> bool:
    """setWebhook con secret_token. No falla el arranque si Telegram no responde."""
    token = _secret("TELEGRAM_BOT_TOKEN")
    secret = webhook_secret()
    base = (app_url or public_base_url()).rstrip("/")
    if not token or not secret or not base.startswith("https://"):
        return False
    url = f"{base}/telegram/webhook"
    try:
        data = _api(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        ok = bool(data.get("ok"))
        log.info("telegram setWebhook %s → %s", url, data.get("description") or ok)
        register_bot_commands()
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
    callback_id: str = "",
    callback_data: str = "",
    answer_fn: Callable | None = None,
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
    if callback_id:
        (answer_fn or answer_callback_query)(callback_id)
    if update_id and not _mark_seen(update_id, chat_id):
        return ""

    def reply(body: str, *, keyboard: bool = False, botones: list | None = None) -> str:
        uid_kb = int(link["user_id"]) if keyboard and link and link.get("user_id") else None
        markup = reply_keyboard(uid_kb) if keyboard else None
        if botones:
            filas = [
                [{"text": t, "callback_data": d} for t, d in botones[i : i + 2]]
                for i in range(0, len(botones), 2)
            ]
            markup = {"inline_keyboard": filas}
        send_text(chat_id, body, send_fn=send_fn, reply_markup=markup)
        return body

    link = find_link_by_chat(chat_id)
    if not link or int(link.get("verified") or 0) != 1:
        code = _extract_code(text)
        pending = _find_pending_by_code(code) if code else None
        if pending:
            ok, msg = _complete_link(pending, chat_id, username)
            return reply(msg, keyboard=ok)
        cmd, _rest = _command_parts(text)
        if cmd in ("/start", "/ayuda", "/help") or not (text or "").strip():
            return reply(help_text(linked=False), keyboard=False)
        return reply(
            "Este Telegram no está vinculado a Mission Dashboard. "
            "Entrá a la app → Usuarios → Telegram, generá un código y pulsá Start en el bot "
            "(o mandá el código de 6 dígitos). /ayuda cuenta qué puede hacer el bot."
        )

    user = _user_by_id(int(link["user_id"]))
    if not user:
        return reply("Tu cuenta está inactiva.")

    from app.billing import plan_vigente, puede_telegram

    if not puede_telegram(plan_vigente(user)):
        return reply("Telegram requiere plan Premium o Familia. Activalo en /app/billing — no ejecuté ninguna acción.")

    set_current_user(user)
    started = time.monotonic()
    accion, ok = "", False
    try:
        body = (text or "").strip()[:MAX_TEXT_CHARS]
        if voice_id and not body:
            accion = "voz"
            body = _transcribe_inbound(voice_id, transcribe_fn, download_fn)[:MAX_TEXT_CHARS]
            if not body:
                return reply("No pude transcribir el audio. Probá en texto o /ayuda.")
        ctx = Contexto(user=user, chat_id=chat_id, parse_fn=parse_fn)
        resp = _route_callback(ctx, callback_data) if callback_data else _route(ctx, body)
        accion, ok = resp.accion, True
        return reply(resp.texto, keyboard=resp.teclado, botones=resp.botones)
    except Exception as e:
        log.exception("telegram handle: %s", type(e).__name__)
        return reply("Hubo un error procesando el mensaje. No se guardó nada.")
    finally:
        clear_current_user()
        log.info(
            "telegram chat=%s accion=%s ok=%s ms=%d",
            chat_id[-4:],
            accion or "-",
            ok,
            (time.monotonic() - started) * 1000,
        )


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


def _route(ctx: Contexto, body: str) -> Respuesta:
    """(1) comando → (2) botón → (3) patrón determinístico → (4) LLM → (5) heurística / no entendí."""
    cmd, rest = _command_parts(body)
    if cmd in ("/ayuda", "/help"):
        return Respuesta(help_text(linked=True), accion="ayuda", teclado=True)
    if cmd == "/start":
        return Respuesta("Ya estás vinculado.\n" + help_text(linked=True), accion="start", teclado=True)
    if cmd == "/deshacer":
        return _deshacer(ctx)
    if not cmd and state.hay_pendiente(ctx.user_id, ctx.chat_id):
        respuesta = _normalize_yes_no(body)
        if respuesta is not None:
            return _resolve_pending(ctx, None, respuesta)
    if cmd:
        acc = acciones.por_comando(cmd)
        if acc is None:
            return Respuesta(NO_ENTENDI, accion="desconocido")
        return _run_command(ctx, acc, rest)
    if not body:
        return Respuesta(NO_ENTENDI, accion="desconocido")

    disponibles = acciones.activas(ctx.user_id)
    for acc in disponibles:
        datos = acc.patron(body)
        if datos is not None:
            return _run(ctx, acc, datos, body)

    parsed = _parse(ctx, body)
    acc = acciones.por_clave(str(parsed.get("intent") or ""))
    if acc is not None and acc in disponibles:
        datos = acc.validar(parsed)
        if datos is not None:
            return _run(ctx, acc, datos, body)

    for acc in disponibles:
        datos = acc.heuristica(body)
        if datos is not None:
            return _run(ctx, acc, datos, body)
    return Respuesta(NO_ENTENDI, accion="desconocido")


def _run_command(ctx: Contexto, acc: Accion, rest: str) -> Respuesta:
    if not acciones.disponible(acc, ctx.user_id):
        return _modulo_apagado(acc)
    datos = None
    if rest and acc.llm_campos:
        datos = acc.validar(_parse(ctx, rest))
    if datos is None:
        datos = acc.parse(rest)
    if datos is None:
        return Respuesta(acc.uso or NO_ENTENDI, accion=acc.clave)
    return _run(ctx, acc, datos, rest)


def _run(ctx: Contexto, acc: Accion, datos: dict, texto: str, *, confirmado: bool = False) -> Respuesta:
    from app.audit import registrar

    if not acciones.disponible(acc, ctx.user_id):
        return _modulo_apagado(acc)
    datos = {**datos, "_texto": texto}
    pregunta = acc.confirmar(ctx, datos) if acc.confirmar and not confirmado else None
    if pregunta:
        pid = state.crear_pendiente(ctx.user_id, ctx.chat_id, acc.clave, datos)
        return Respuesta(
            f"{pregunta}\n¿Lo guardo? Tocá un botón o respondé «sí» / «no» "
            f"(vence en {state.PENDING_TTL_MIN} min).",
            accion=f"{acc.clave}:confirmar",
            botones=[("✅ Sí", f"p:{pid}:si"), ("✖️ No", f"p:{pid}:no")],
        )
    resp = acc.ejecutar(ctx, datos)
    resp.accion = resp.accion or acc.clave
    if resp.entidad_id is not None:
        registrar(f"telegram_{acc.clave}", acc.clave, resp.entidad_id, {"chat": ctx.chat_id[-4:]})
        if acc.deshacer is not None:
            state.registrar_ultima(ctx.user_id, ctx.chat_id, acc.clave, resp.entidad_id, resp.resumen)
            resp.texto += "\n¿Error? /deshacer"
    return resp


YES_WORDS = frozenset({"si", "dale", "confirmo", "confirmar"})
NO_WORDS = frozenset({"no", "cancelar", "cancela", "cancelo"})
CALLBACK_RE = re.compile(r"^p:(\d{1,12}):(si|no)$")


def _normalize_yes_no(text: str) -> bool | None:
    norm = normalize(text)
    if norm in YES_WORDS:
        return True
    if norm in NO_WORDS:
        return False
    return None


def _route_callback(ctx: Contexto, data: str) -> Respuesta:
    enfoque = re.match(r"^e:(\d{1,12}):([cpo])$", data or "")
    if enfoque:
        from app.telegram_actions.enfoque import marcar_bloque

        if not acciones.disponible(acciones.por_clave("enfoque"), ctx.user_id):
            return _modulo_apagado(acciones.por_clave("enfoque"))
        return marcar_bloque(int(enfoque.group(1)), enfoque.group(2))
    habito = re.match(r"^k:([a-z0-9_]{1,20})$", data or "")
    if habito:
        from app.audit import registrar
        from app.telegram_actions.habitos import marcar_desde_boton

        resp = marcar_desde_boton(ctx, habito.group(1))
        if resp.resumen:
            registrar("telegram_habito", "habito", resp.resumen, {"chat": ctx.chat_id[-4:]})
            state.registrar_ultima(ctx.user_id, ctx.chat_id, "habito", 0, resp.resumen)
            resp.texto += "\n¿Error? /deshacer"
        return resp
    cambio = re.match(r"^c:(\d{1,12}):(\d{1,2})$", data or "")
    if cambio:
        from app.telegram_actions.finanzas import cambiar_subcategoria

        return cambiar_subcategoria(ctx, int(cambio.group(1)), int(cambio.group(2)))
    m = CALLBACK_RE.match(data or "")
    if not m:
        return Respuesta("Ese botón ya no sirve. No guardé nada.", accion="callback")
    return _resolve_pending(ctx, int(m.group(1)), m.group(2) == "si")


def _resolve_pending(ctx: Contexto, pending_id: int | None, si: bool) -> Respuesta:
    got = state.tomar_pendiente(ctx.user_id, ctx.chat_id, pending_id)
    acc = acciones.por_clave(got[0]) if got else None
    if got is None or acc is None:
        return Respuesta("Esa confirmación ya no está disponible. No guardé nada.", accion="confirmar")
    _clave, payload = got
    if payload is None:
        return Respuesta(
            f"Esa confirmación venció ({state.PENDING_TTL_MIN} min). No guardé nada; mandalo de nuevo.",
            accion=f"{acc.clave}:vencido",
        )
    if not si:
        return Respuesta("Cancelado. No guardé nada.", accion=f"{acc.clave}:cancelado")
    return _run(ctx, acc, payload, str(payload.get("_texto") or ""), confirmado=True)


def _deshacer(ctx: Contexto) -> Respuesta:
    from app.audit import registrar

    last = state.tomar_ultima(ctx.user_id, ctx.chat_id)
    acc = acciones.por_clave(str(last["accion"])) if last else None
    if not last or acc is None or acc.deshacer is None:
        return Respuesta(
            f"No hay nada para deshacer (solo la última acción, hasta {state.DESHACER_TTL_MIN} min).",
            accion="deshacer",
        )
    ok = acc.deshacer(ctx, int(last["entidad_id"]), str(last.get("resumen") or ""))
    registrar("telegram_deshacer", acc.clave, last["entidad_id"], {"ok": ok, "chat": ctx.chat_id[-4:]})
    if not ok:
        return Respuesta(f"No pude deshacer: {last['resumen']}. Revisalo en la app.", accion="deshacer")
    return Respuesta(f"Deshice: {last['resumen']}.", accion="deshacer")


def _modulo_apagado(acc: Accion) -> Respuesta:
    return Respuesta(
        f"El módulo «{acc.modulo}» está apagado, así que no guardé nada. "
        "Activalo en la app → Coach → Módulos.",
        accion=acc.clave,
    )


def _parse(ctx: Contexto, text: str) -> dict:
    parsed = ctx.parse_fn(text) if ctx.parse_fn is not None else parse_intent(text)
    return parsed if isinstance(parsed, dict) else {}


DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def build_intent_prompt(text: str, disponibles: list[Accion]) -> str:
    dia = _hoy()
    lineas = [f"- {a.clave}: {a.llm_campos}" for a in disponibles if a.llm_campos]
    claves = "|".join([a.clave for a in disponibles if a.llm_campos] + ["unknown"])
    return (
        "Clasificá el mensaje del usuario de un dashboard personal. "
        f"Respondé SOLO un JSON con la clave intent ({claves}) y los campos de esa acción:\n"
        + "\n".join(lineas)
        + '\nSi no encaja claramente con ninguna, respondé {"intent": "unknown"}.\n'
        f"Hoy es {DIAS_SEMANA[dia.weekday()]} {dia.isoformat()}. Mensaje: {text[:400]}"
    )


def parse_intent(text: str) -> dict:
    """Una llamada a Groq. Sin clave o con Groq caído → unknown (chat_simple devuelve texto, no JSON)."""
    from app import ai_client

    if not ai_client.api_key_configurada():
        return {"intent": "unknown"}
    disponibles = acciones.activas()
    raw = ai_client.chat_simple(
        build_intent_prompt(text, disponibles),
        contexto="Sos un parser. Solo JSON válido, sin markdown.",
        max_tokens=LLM_MAX_TOKENS,
    ) or ""
    return _extract_json(raw) or {"intent": "unknown"}


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


def schedule_reminder(
    user_id: int,
    evento_id: int | None,
    fecha: str,
    hora: str,
    titulo: str,
    chat_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Un recordatorio por evento + fire_at (hora local). Si el evento se movió, reemplaza el pendiente."""
    ensure_telegram_schema()
    from app.db.core import ejecutar

    lead = state.recordatorio_min(user_id)
    if lead <= 0:
        return False
    try:
        start = datetime.fromisoformat(f"{fecha}T{str(hora)[:5]}:00")
    except ValueError:
        return False
    if now is not None and start <= now:
        return False
    fire = (start - timedelta(minutes=lead)).isoformat(timespec="seconds")
    if evento_id is not None:
        rows = ejecutar(
            "SELECT fire_at FROM telegram_reminders WHERE user_id = ? AND evento_id = ?",
            [int(user_id), int(evento_id)],
            fetchall=True,
        ) or []
        if any(str(r["fire_at"]) == fire for r in rows):
            return False
        cancel_reminders(user_id, int(evento_id))
    ejecutar(
        """
        INSERT INTO telegram_reminders (user_id, evento_id, chat_id, titulo, hora, fire_at, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        [int(user_id), evento_id, str(chat_id), titulo[:80], str(hora)[:5], fire],
    )
    return True


def sync_event_reminders(*, now: datetime | None = None) -> int:
    """Crea recordatorios para eventos con hora de cualquier fuente (web, Google, Telegram).

    Solo chats vinculados con plan vigente. Idempotente: correrlo dos veces no duplica.
    """
    ensure_telegram_schema()
    from app.billing import plan_vigente, puede_telegram
    from app.db.agenda import eventos_con_hora
    from app.db.core import ejecutar
    from app.tenant import clear_current_user, set_current_user
    from app.timezone_config import ahora

    now = now or ahora()
    hasta = (now + timedelta(hours=REMINDER_HORIZON_H)).date().isoformat()
    links = ejecutar(
        "SELECT user_id, chat_id FROM telegram_links WHERE verified = 1 AND chat_id IS NOT NULL AND chat_id != ''",
        fetchall=True,
    ) or []
    n = 0
    for link in links:
        user = _user_by_id(int(link["user_id"]))
        if not user or not puede_telegram(plan_vigente(user)):
            continue
        if state.recordatorio_min(int(user["id"])) <= 0:
            ejecutar(
                "DELETE FROM telegram_reminders WHERE user_id = ? AND sent_at IS NULL",
                [int(user["id"])],
            )
            continue
        set_current_user(user)
        try:
            eventos = eventos_con_hora(now.date().isoformat(), hasta)
        finally:
            clear_current_user()
        for ev in eventos:
            n += schedule_reminder(
                int(user["id"]),
                int(ev["id"]),
                str(ev["fecha"]),
                str(ev["hora_inicio"]),
                str(ev.get("titulo") or "evento"),
                str(link["chat_id"]),
                now=now,
            )
        ejecutar(
            """
            DELETE FROM telegram_reminders
             WHERE user_id = ? AND sent_at IS NULL AND evento_id IS NOT NULL
               AND evento_id NOT IN (
                   SELECT id FROM eventos_calendario
                    WHERE user_id = ? AND hora_inicio IS NOT NULL AND hora_inicio != ''
               )
            """,
            [int(user["id"]), int(user["id"])],
        )
    return n


def cancel_reminders(user_id: int, evento_id: int) -> None:
    ensure_telegram_schema()
    from app.db.core import ejecutar

    ejecutar(
        "DELETE FROM telegram_reminders WHERE user_id = ? AND evento_id = ? AND sent_at IS NULL",
        [int(user_id), int(evento_id)],
    )


def send_due_reminders(
    *,
    now: datetime | None = None,
    send_fn: Callable | None = None,
) -> int:
    ensure_telegram_schema()
    from app.db.core import ejecutar
    from app.timezone_config import ahora

    # fire_at se guarda en hora local (TZ_LOCAL): comparar contra UTC los dispara 6 h antes.
    stamp = (now or ahora()).isoformat(timespec="seconds")
    rows = (
        ejecutar(
            """
            SELECT id, chat_id, titulo, hora, fire_at FROM telegram_reminders
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
            "⏰ Recordatorio: "
            + (f"{r['hora']} · " if r.get("hora") else "")
            + f"{r.get('titulo') or 'evento'}.",
            send_fn=send_fn,
        )
        if ok or send_fn is not None:
            ejecutar(
                "UPDATE telegram_reminders SET sent_at = ? WHERE id = ?",
                [iso_ahora(), int(r["id"])],
            )
            n += 1
    return n


def send_morning_briefings(*, now: datetime | None = None, send_fn: Callable | None = None) -> int:
    """Envía el briefing del día a quien lo activó. Una vez por usuario y día. Apagado por defecto."""
    ensure_telegram_schema()
    from app.billing import plan_vigente, puede_telegram
    from app.db.core import ejecutar
    from app.db.telegram_state import marcar_briefing_enviado, prefs_briefing
    from app.telegram_actions.briefing import build_briefing
    from app.timezone_config import ahora

    now = now or ahora()
    dia = now.date().isoformat()
    hhmm = now.strftime("%H:%M")
    links = ejecutar(
        "SELECT user_id, chat_id FROM telegram_links WHERE verified = 1 AND chat_id IS NOT NULL AND chat_id != ''",
        fetchall=True,
    ) or []
    n = 0
    for link in links:
        user = _user_by_id(int(link["user_id"]))
        if not user or not puede_telegram(plan_vigente(user)):
            continue
        prefs = prefs_briefing(int(user["id"]))
        if not prefs["activo"] or prefs["hora"] > hhmm or prefs["ultimo"] == dia:
            continue
        if prefs["silencio_hasta"] and prefs["silencio_hasta"] >= dia:
            continue
        from app.tenant import clear_current_user, set_current_user

        set_current_user(user)
        try:
            texto = build_briefing(int(user["id"]))
        finally:
            clear_current_user()
        if send_text(str(link["chat_id"]), texto, send_fn=send_fn):
            marcar_briefing_enviado(int(user["id"]), dia)
            n += 1
    return n
