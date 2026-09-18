"""WhatsApp Cloud API webhook — sin sesión (firma HMAC)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.logging_config import get_logger
from app.secrets import get_secret
from app.whatsapp import extract_inbound, handle_inbound, verify_signature, verify_token_ok

router = APIRouter(tags=["whatsapp"])
log = get_logger("whatsapp_webhook")


@router.get("/whatsapp/webhook")
def whatsapp_verify(request: Request):
    """Handshake de Meta: hub.mode=subscribe + hub.verify_token → hub.challenge."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and verify_token_ok(token) and challenge:
        return PlainTextResponse(str(challenge), status_code=200)
    raise HTTPException(403, "Verify token inválido")


@router.post("/whatsapp/webhook")
async def whatsapp_inbound(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    secret = (get_secret("WHATSAPP_APP_SECRET") or "").strip()
    if not secret:
        log.error("webhook whatsapp: falta WHATSAPP_APP_SECRET")
        raise HTTPException(500, "Falta WHATSAPP_APP_SECRET")
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256, secret):
        log.warning("webhook whatsapp: firma inválida")
        raise HTTPException(403, "Firma inválida")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(400, f"JSON inválido: {e}") from e
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON inválido")

    n = 0
    for item in extract_inbound(payload):
        handle_inbound(
            item["phone"],
            text=item.get("text") or "",
            audio_id=item.get("audio_id") or "",
            wamid=item.get("wamid") or "",
        )
        n += 1
    return JSONResponse({"ok": True, "handled": n})
