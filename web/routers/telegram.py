"""Telegram Bot API webhook — sin sesión (secret_token)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.logging_config import get_logger
from app.secrets import get_secret
from app.telegram import extract_inbound, handle_inbound, verify_webhook_secret

router = APIRouter(tags=["telegram"])
log = get_logger("telegram_webhook")


@router.post("/telegram/webhook")
async def telegram_inbound(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
):
    secret = (get_secret("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if not secret:
        log.error("webhook telegram: falta TELEGRAM_WEBHOOK_SECRET")
        raise HTTPException(500, "Falta TELEGRAM_WEBHOOK_SECRET")
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

    n = 0
    for item in extract_inbound(payload):
        handle_inbound(
            item["chat_id"],
            text=item.get("text") or "",
            voice_id=item.get("voice_id") or "",
            update_id=item.get("update_id") or "",
            username=item.get("username") or "",
        )
        n += 1
    return JSONResponse({"ok": True, "handled": n})
