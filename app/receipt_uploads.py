"""Persistencia local de fotos de recibos (servidor casero / demo)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.db.core import DB_PATH
from app.receipt_ocr import compress_image_bytes

UPLOADS_ROOT = None  # resuelto en runtime vía _uploads_root()


def _uploads_root() -> Path:
    """data/uploads/receipts junto a mission.db (o carpeta de la BD de test)."""
    root = DB_PATH.parent / "uploads" / "receipts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_user_dir(user_id: int) -> Path:
    d = _uploads_root() / str(int(user_id))
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_receipt_image(user_id: int, raw: bytes, filename: str | None = None) -> str:
    """
    Comprime y guarda. Retorna clave lógica:
    data/uploads/receipts/{uid}/{uuid}.jpg
    """
    if not raw:
        raise ValueError("archivo vacío")
    compressed, _mime = compress_image_bytes(raw)
    name = f"{uuid.uuid4().hex}.jpg"
    path = _safe_user_dir(user_id) / name
    path.write_bytes(compressed)
    return f"data/uploads/receipts/{int(user_id)}/{name}"


def resolve_upload_path(rel_path: str, user_id: int) -> Path | None:
    """Solo archivos del propio usuario bajo uploads/receipts/{uid}/."""
    if not rel_path:
        return None
    rel = rel_path.replace("\\", "/").lstrip("/")
    m = re.match(
        rf"^(?:data/)?uploads/receipts/{int(user_id)}/([A-Za-z0-9._-]+)$",
        rel,
    )
    if not m:
        # También aceptar solo el filename vía ruta construida por el router
        m2 = re.match(r"^([A-Za-z0-9._-]+)$", rel)
        if not m2:
            return None
        name = m2.group(1)
    else:
        name = m.group(1)
    full = (_safe_user_dir(user_id) / name).resolve()
    root = _safe_user_dir(user_id).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return None
    if not full.is_file():
        return None
    return full
