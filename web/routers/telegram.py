"""Telegram Bot API webhook — sin sesión (secret_token)."""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger
from app.telegram import extract_inbound, handle_inbound, verify_webhook_secret, webhook_secret

router = APIRouter(tags=["telegram"])
log = get_logger("telegram_webhook")


@router.post("/telegram/webhook")
async def telegram_inbound(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
):
    secret = webhook_secret()
    if not secret:
        log.error("webhook telegram: falta TELEGRAM_WEBHOOK_SECRET o SESSION_SECRET")
        raise HTTPException(500, "Falta secreto de Telegram")
    if not verify_webhook_secret(x_telegram_bot_api_secret_token, secret):
        log.warning("webhook telegram: secret_token inválido")
        raise HTTPException(403, "Secret token inválido")
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(400, f"JSON inválido: {e}") from e
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON inválido")

    # handle_inbound es síncrono (Groq, Whisper, BD): corre en el threadpool después de
    # responder 200, así Telegram no reintenta por timeout. El dedupe por update_id cubre reintentos.
    n = 0
    for item in extract_inbound(payload):
        background_tasks.add_task(
            handle_inbound,
            item["chat_id"],
            text=item.get("text") or "",
            voice_id=item.get("voice_id") or "",
            update_id=item.get("update_id") or "",
            username=item.get("username") or "",
            callback_id=item.get("callback_id") or "",
            callback_data=item.get("callback_data") or "",
            photo_id=item.get("photo_id") or "",
            photo_size=int(item.get("photo_size") or 0),
        )
        n += 1
    return JSONResponse({"ok": True, "handled": n})
