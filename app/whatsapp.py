"""WhatsApp Cloud API (Meta) — briefing, gastos, tareas y audio.

Trade-off (Fase 5):
- Meta Cloud API: webhook HMAC nativo, costo/msg bajo, alta más lenta
  (Business Manager). Elegido: dashboard privado, mismo patrón que Lemon.
- Twilio / 360dialog / Gupshup: sandbox en horas, markup por mensaje,
  otro vendor. Quedan como plan B si el alta de Meta se traba.

Un número no vinculado NUNCA ejecuta acciones: solo instrucciones de vínculo.
El canal respeta plan Premium/Familia y tiene rate-limit propio por teléfono
(no bypasea el de login). Groq cuenta en uso_ia del billing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.logging_config import get_logger
from app.timezone_config import hoy as _hoy, iso_ahora

log = get_logger("whatsapp")

BRIEFING_WORDS = ("briefing", "agenda", "resumen", "foco", "hoy qué", "que hay hoy")
CODE_RE = re.compile(r"^\s*(\d{6})\s*$")
AMOUNT_RE = re.compile(
    r"(?:\$\s*)?(\d+(?:[.,]\d{1,2})?)\s*(?:pesos|mxn|\$)?\s*(?:en|de)?\s*(.+)$",
    re.I,
)
GRAPH_BASE = "https://graph.facebook.com/v21.0"


def ensure_whatsapp_schema() -> None:
    from app.db.core import ejecutar

    for sql in (
        """
        CREATE TABLE IF NOT EXISTS whatsapp_links (
            user_id INTEGER PRIMARY KEY,
            phone TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0,
            verify_hash TEXT,
            verify_expires TEXT,
            linked_at TEXT
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_phone ON whatsapp_links(phone)",
        """
        CREATE TABLE IF NOT EXISTS whatsapp_seen (
            wamid TEXT PRIMARY KEY,
            phone TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS whatsapp_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            evento_id INTEGER,
            phone TEXT NOT NULL,
            titulo TEXT,
            fire_at TEXT NOT NULL,
            sent_at TEXT
        )
        """,
    ):
        try:
            ejecutar(sql)
        except Exception as e:
            log.debug("ensure_whatsapp_schema: %s", e)


def _secret(name: str, default: str = "") -> str:
    from app.secrets import get_secret

    return (get_secret(name, default) or "").strip()


def verify_token_ok(token: str | None) -> bool:
    expected = _secret("WHATSAPP_VERIFY_TOKEN")
    return bool(expected) and hmac.compare_digest(expected, (token or "").strip())


def verify_signature(raw_body: bytes, header: str | None, secret: str | None = None) -> bool:
    secret = (secret if secret is not None else _secret("WHATSAPP_APP_SECRET")).strip()
    if not secret or not header:
        return False
    got = header.split("=", 1)[-1].strip()
    expect = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(got, expect)


def digits_only(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def normalize_phone(raw: str) -> str:
    d = digits_only(raw)
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 10:
        d = "52" + d
    return d


def phone_candidates(raw: str) -> list[str]:
    d = normalize_phone(raw)
    out: list[str] = []
    for c in (d, digits_only(raw)):
        if c and c not in out:
            out.append(c)
    if d.startswith("521") and len(d) >= 12:
        alt = "52" + d[3:]
        if alt not in out:
            out.append(alt)
    elif d.startswith("52") and not d.startswith("521") and len(d) == 12:
        alt = "521" + d[2:]
        if alt not in out:
            out.append(alt)
    return out


def _hash_code(code: str) -> str:
    pepper = _secret("SESSION_SECRET") or _secret("WHATSAPP_APP_SECRET") or "dev"
    return hashlib.sha256(f"{pepper}:{code}".encode("utf-8")).hexdigest()


def _user_by_id(user_id: int) -> dict | None:
    from app.db.core import ejecutar

    rows = ejecutar(
        "SELECT * FROM usuarios WHERE id = ? AND COALESCE(activo, 1) = 1",
        [int(user_id)],
        fetchall=True,
    )
    return rows[0] if rows else None


def link_status(user_id: int) -> dict | None:
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    rows = (
        ejecutar(
            "SELECT * FROM whatsapp_links WHERE user_id = ?",
            [int(user_id)],
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def find_link_by_phone(phone: str) -> dict | None:
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    cands = phone_candidates(phone)
    if not cands:
        return None
    placeholders = ",".join("?" * len(cands))
    rows = (
        ejecutar(
            f"SELECT * FROM whatsapp_links WHERE phone IN ({placeholders})",
            cands,
            fetchall=True,
        )
        or []
    )
    return rows[0] if rows else None


def start_link(user_id: int, phone_raw: str) -> tuple[bool, str, str | None]:
    """Genera código de 6 dígitos. El código se muestra en la UI (y se puede mandar por WA)."""
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    phone = normalize_phone(phone_raw)
    if len(phone) < 10:
        return False, "Número inválido.", None
    existing = find_link_by_phone(phone)
    if existing and int(existing.get("verified") or 0) == 1 and int(existing["user_id"]) != int(user_id):
        return False, "Ese número ya está vinculado a otra cuenta.", None
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None).isoformat(timespec="seconds")
    ejecutar("DELETE FROM whatsapp_links WHERE user_id = ?", [int(user_id)])
    if existing and int(existing.get("verified") or 0) == 0:
        ejecutar(
            "DELETE FROM whatsapp_links WHERE user_id = ?",
            [int(existing["user_id"])],
        )
    try:
        ejecutar(
            """
            INSERT INTO whatsapp_links
                (user_id, phone, verified, verify_hash, verify_expires, linked_at)
            VALUES (?, ?, 0, ?, ?, NULL)
            """,
            [int(user_id), phone, _hash_code(code), expires],
        )
    except Exception as e:
        log.warning("start_link insert: %s", e)
        return False, "No se pudo guardar el vínculo.", None
    from app.audit import registrar

    registrar("whatsapp_link_start", "whatsapp_links", user_id, {"phone_suffix": phone[-4:]})
    return True, "Código generado. Vence en 10 minutos.", code


def confirm_link(user_id: int, code: str) -> tuple[bool, str]:
    row = link_status(user_id)
    if not row:
        return False, "No hay un vínculo pendiente."
    ok, msg = _try_verify_row(row, code)
    return ok, msg


def unlink(user_id: int) -> None:
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    ejecutar("DELETE FROM whatsapp_links WHERE user_id = ?", [int(user_id)])
    from app.audit import registrar

    registrar("whatsapp_unlink", "whatsapp_links", user_id, None)


def _try_verify_row(row: dict, code: str) -> tuple[bool, str]:
    from app.db.core import ejecutar

    raw = (code or "").strip()
    m = CODE_RE.match(raw)
    if not m:
        return False, "El código debe ser de 6 dígitos."
    exp = row.get("verify_expires") or ""
    try:
        if datetime.fromisoformat(str(exp)) < datetime.now(timezone.utc).replace(tzinfo=None):
            return False, "El código venció. Generá uno nuevo."
    except Exception:
        return False, "El código venció. Generá uno nuevo."
    if _hash_code(m.group(1)) != str(row.get("verify_hash") or ""):
        return False, "Código incorrecto."
    ejecutar(
        """
        UPDATE whatsapp_links
           SET verified = 1, verify_hash = NULL, verify_expires = NULL, linked_at = ?
         WHERE user_id = ?
        """,
        [iso_ahora(), int(row["user_id"])],
    )
    from app.audit import registrar

    registrar("whatsapp_link_ok", "whatsapp_links", row["user_id"], None)
    return True, "Número vinculado."


def _mark_seen(wamid: str, phone: str) -> bool:
    """False si ya se vio (duplicado)."""
    if not wamid:
        return True
    from app.db.core import ejecutar

    try:
        ejecutar(
            "INSERT INTO whatsapp_seen (wamid, phone) VALUES (?, ?)",
            [wamid, phone],
        )
        return True
    except Exception:
        return False


def extract_inbound(payload: dict) -> list[dict]:
    """Normaliza el JSON de Cloud API a {phone, wamid, text, audio_id}."""
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                phone = digits_only(str(msg.get("from") or ""))
                item = {
                    "phone": phone,
                    "wamid": str(msg.get("id") or ""),
                    "text": "",
                    "audio_id": "",
                }
                mtype = str(msg.get("type") or "text")
                if mtype == "text":
                    item["text"] = str((msg.get("text") or {}).get("body") or "")
                elif mtype in ("audio", "voice"):
                    media = msg.get("audio") or msg.get("voice") or {}
                    item["audio_id"] = str(media.get("id") or "")
                elif mtype == "button":
                    item["text"] = str((msg.get("button") or {}).get("text") or "")
                else:
                    item["text"] = str(msg.get("type") or "")
                if phone:
                    out.append(item)
    return out


def send_text(phone: str, body: str, send_fn: Callable | None = None) -> bool:
    text = (body or "").strip()[:3500]
    if not text:
        return False
    if send_fn is not None:
        send_fn(phone, text)
        return True
    token = _secret("WHATSAPP_TOKEN")
    phone_id = _secret("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        log.info("whatsapp send skipped (no token): %s", text[:80])
        return False
    from urllib import request as urlrequest

    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": digits_only(phone),
            "type": "text",
            "text": {"body": text, "preview_url": False},
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        f"{GRAPH_BASE}/{phone_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            resp.read()
        return True
    except Exception as e:
        log.warning("whatsapp send failed: %s", e)
        return False


def _download_media(media_id: str) -> bytes:
    token = _secret("WHATSAPP_TOKEN")
    if not token or not media_id:
        return b""
    from urllib import request as urlrequest

    meta_req = urlrequest.Request(
        f"{GRAPH_BASE}/{media_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlrequest.urlopen(meta_req, timeout=20) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        url = meta.get("url") or ""
        if not url:
            return b""
        bin_req = urlrequest.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlrequest.urlopen(bin_req, timeout=40) as resp:
            data = resp.read(6_000_000)
        return data
    except Exception as e:
        log.warning("whatsapp media: %s", e)
        return b""


def handle_inbound(
    phone: str,
    *,
    text: str = "",
    audio_id: str = "",
    wamid: str = "",
    send_fn: Callable | None = None,
    transcribe_fn: Callable | None = None,
    parse_fn: Callable | None = None,
    download_fn: Callable | None = None,
) -> str:
    """Procesa un mensaje. Retorna la respuesta enviada (o '')."""
    from app.rate_limit import whatsapp_permitido
    from app.tenant import clear_current_user, set_current_user

    ensure_whatsapp_schema()
    phone = digits_only(phone)
    if not phone:
        return ""
    if not whatsapp_permitido(phone):
        log.info("whatsapp rate-limit phone=...%s", phone[-4:])
        return ""
    if wamid and not _mark_seen(wamid, phone):
        return ""

    def reply(body: str) -> str:
        send_text(phone, body, send_fn=send_fn)
        return body

    link = find_link_by_phone(phone)
    if not link or int(link.get("verified") or 0) != 1:
        if link and CODE_RE.match((text or "").strip()):
            ok, msg = _try_verify_row(link, text)
            if ok:
                # WhatsApp from may differ (521 vs 52); store the inbound phone.
                from app.db.core import ejecutar

                ejecutar(
                    "UPDATE whatsapp_links SET phone = ? WHERE user_id = ?",
                    [phone, int(link["user_id"])],
                )
                return reply("Listo, número vinculado. Mandá «briefing», un gasto («35 en super») o una tarea.")
            return reply(msg)
        return reply(
            "Este WhatsApp no está vinculado a Mission Dashboard. "
            "Entrá a la app → Usuarios → WhatsApp, cargá este número y mandá el código de 6 dígitos."
        )

    user = _user_by_id(int(link["user_id"]))
    if not user:
        return reply("Tu cuenta está inactiva.")

    from app.billing import plan_vigente, puede_whatsapp

    if not puede_whatsapp(plan_vigente(user)):
        return reply("WhatsApp requiere plan Premium o Familia. Activalo en /app/billing — no ejecuté ninguna acción.")

    token = set_current_user(user)
    try:
        body = (text or "").strip()
        if audio_id and not body:
            body = _transcribe_inbound(audio_id, transcribe_fn, download_fn)
            if not body:
                return reply("No pude transcribir el audio. Probá en texto.")
        if not body:
            return reply("No entendí el mensaje. Probá «briefing», «35 en super» o «mañana 5pm llamar al banco».")
        return reply(_dispatch(user, body, phone, parse_fn=parse_fn))
    except Exception as e:
        log.exception("whatsapp handle: %s", e)
        return reply("Hubo un error procesando el mensaje. No se guardó nada.")
    finally:
        clear_current_user()


def _transcribe_inbound(
    audio_id: str,
    transcribe_fn: Callable | None,
    download_fn: Callable | None,
) -> str:
    import tempfile
    from pathlib import Path

    data = (download_fn or _download_media)(audio_id)
    if not data:
        return ""
    if transcribe_fn is not None:
        return (transcribe_fn(data) or "").strip()
    suffix = ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
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


def _dispatch(user: dict, text: str, phone: str, parse_fn: Callable | None = None) -> str:
    low = text.lower().strip()
    if any(w in low for w in BRIEFING_WORDS) or low in ("hoy", "agenda"):
        return build_briefing(int(user["id"]))

    parsed = None
    if parse_fn is not None:
        parsed = parse_fn(text)
    else:
        parsed = parse_intent(text)

    intent = (parsed or {}).get("intent") or "unknown"
    if intent == "briefing":
        return build_briefing(int(user["id"]))
    if intent == "gasto":
        return _apply_gasto(parsed, text)
    if intent == "tarea":
        return _apply_tarea(parsed, text, phone, int(user["id"]))
    # Heurística si Groq no clasificó
    if AMOUNT_RE.search(text):
        return _apply_gasto(_heuristic_gasto(text), text)
    return _apply_tarea(_heuristic_tarea(text), text, phone, int(user["id"]))


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
    if not data:
        return {"intent": "unknown"}
    return data


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
    desc = str(parsed.get("descripcion") or original).strip()[:120] or "Gasto WhatsApp"
    agregar_gasto_sobre(str(_hoy()), sobre, sub, desc, monto, origen="whatsapp")
    return f"Gasté {monto:g} en «{desc}» → {cat}."


def _apply_tarea(parsed: dict, original: str, phone: str, user_id: int) -> str:
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
            "descripcion": "vía WhatsApp",
            "tipo": "Personal",
            "color": COLORES_TIPO.get("Personal", "#58a6ff"),
            "fuente": "local",
        },
        sync_google=True,
    )
    schedule_reminder(user_id, eid, fecha, hora, titulo, phone)
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
        bits = []
        for e in evs[:8]:
            bits.append(f"{(e.get('hora_inicio') or '—')[:5]} {e.get('titulo')}")
        lineas.append("Agenda: " + "; ".join(bits))
    else:
        lineas.append("Agenda: sin eventos.")
    ent = next((i for i in items if i.get("kind") == "entrenamiento"), None)
    if ent:
        lineas.append(str(ent.get("titulo")))
    from datetime import timedelta as _td

    corte = (hoy_fn() - _td(days=7)).isoformat()
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
    phone: str,
) -> None:
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    try:
        fire = datetime.fromisoformat(f"{fecha}T{hora[:5]}:00") - timedelta(minutes=30)
    except Exception:
        return
    ejecutar(
        """
        INSERT INTO whatsapp_reminders (user_id, evento_id, phone, titulo, fire_at, sent_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        [int(user_id), evento_id, digits_only(phone), titulo[:80], fire.isoformat(timespec="seconds")],
    )


def send_due_reminders(
    *,
    now: datetime | None = None,
    send_fn: Callable | None = None,
) -> int:
    ensure_whatsapp_schema()
    from app.db.core import ejecutar

    stamp = (now or datetime.now(timezone.utc).replace(tzinfo=None)).isoformat(timespec="seconds")
    rows = (
        ejecutar(
            """
            SELECT id, phone, titulo, fire_at FROM whatsapp_reminders
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
            r["phone"],
            f"Recordatorio: {r.get('titulo') or 'tarea'} (en ~30 min).",
            send_fn=send_fn,
        )
        if ok or send_fn is not None:
            ejecutar(
                "UPDATE whatsapp_reminders SET sent_at = ? WHERE id = ?",
                [iso_ahora(), int(r["id"])],
            )
            n += 1
    return n
