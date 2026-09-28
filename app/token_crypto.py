"""Cifra secretos en reposo. El prefijo enc:v1: separa el texto sellado del JSON legado."""
from __future__ import annotations

import base64
import hashlib
import os

PREFIJO = "enc:v1:"
_SAL = b"mission-oauth-token-v1"
_ITERACIONES = 200_000
_cache: dict[str, object] = {}


class TokenIlegible(Exception):
    """El sobre no abre. No incluye el secreto en el mensaje."""


def _secreto() -> str:
    return os.getenv("SESSION_SECRET") or os.getenv("APP_PASSWORD") or "dev-change-me"


def _fernet():
    secreto = _secreto()
    if _cache.get("secreto") == secreto and _cache.get("fernet") is not None:
        return _cache["fernet"]
    from cryptography.fernet import Fernet

    raw = hashlib.pbkdf2_hmac(
        "sha256",
        secreto.encode(),
        _SAL,
        _ITERACIONES,
        dklen=32,
    )
    fernet = Fernet(base64.urlsafe_b64encode(raw))
    _cache["secreto"] = secreto
    _cache["fernet"] = fernet
    return fernet


def sellar(texto: str) -> str:
    if texto.startswith(PREFIJO):
        return texto
    token = _fernet().encrypt(texto.encode())
    return PREFIJO + token.decode()


def abrir(texto: str) -> str:
    """Devuelve el texto plano. JSON legado pasa tal cual. Un sobre alterado falla cerrado."""
    if not texto.startswith(PREFIJO):
        return texto
    try:
        plano = _fernet().decrypt(texto[len(PREFIJO) :].encode())
    except Exception as exc:
        raise TokenIlegible() from exc
    return plano.decode()
