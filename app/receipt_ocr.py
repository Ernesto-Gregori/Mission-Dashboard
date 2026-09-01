"""
Extracción de recibos / transferencias vía modelo de visión (Groq).

Fase 2a: prompt + parseo + validación. La UI de confirmación viene después.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

# ── Modelo / límites ──────────────────────────────────────────
VISION_MODEL_DEFAULT = "qwen/qwen3.6-27b"
MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 75
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB crudo antes de comprimir

TIPOS_VALIDOS = frozenset({"recibo", "transferencia"})

EXTRACTION_SYSTEM = (
    "Eres un extractor de datos de comprobantes de El Salvador. "
    "Analizas fotos de recibos/facturas de supermercado o comercio, "
    "y capturas de pantalla de transferencias bancarias. "
    "Respondes SOLO JSON válido (sin markdown, sin texto extra)."
)

EXTRACTION_PROMPT = """Analiza la imagen y extrae un comprobante.

Devuelve EXACTAMENTE este JSON (usa null si no se lee con claridad):
{
  "tipo": "recibo" | "transferencia" | null,
  "comercio": "string | null",
  "fecha": "YYYY-MM-DD | null",
  "monto_total": number | null,
  "metodo_pago": "string | null",
  "items": [
    {
      "nombre": "string",
      "cantidad": number,
      "precio_unitario": number,
      "precio_total": number
    }
  ],
  "error": null | "imagen_ilegible" | "no_es_comprobante"
}

Reglas:
- Si la imagen está borrosa, cortada o no es un recibo/transferencia: tipo=null y error="imagen_ilegible" o "no_es_comprobante".
- "recibo": factura/ticket de tienda. Incluye ítems de línea si se ven; si no hay detalle, items=[].
- "transferencia": captura de banco/app. items=[] casi siempre. comercio = banco o beneficiario si aparece.
- monto_total en dólares (número, no string). Sin símbolo $.
- fecha solo YYYY-MM-DD; si el formato es dudoso → null.
- No inventes montos ni productos que no se vean.
- metodo_pago: efectivo, tarjeta, transferencia, u otro texto corto si aparece; si no → null.
"""


@dataclass
class ReceiptItemDraft:
    nombre: str
    cantidad: float
    precio_unitario: Optional[float]
    precio_total: Optional[float]


@dataclass
class ExtractionResult:
    ok: bool
    tipo: Optional[str] = None
    comercio: Optional[str] = None
    fecha: Optional[str] = None
    monto_total: Optional[float] = None
    metodo_pago: Optional[str] = None
    items: list[ReceiptItemDraft] = field(default_factory=list)
    raw: Optional[dict] = None
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tipo": self.tipo,
            "comercio": self.comercio,
            "fecha": self.fecha,
            "monto_total": self.monto_total,
            "metodo_pago": self.metodo_pago,
            "items": [
                {
                    "nombre": i.nombre,
                    "cantidad": i.cantidad,
                    "precio_unitario": i.precio_unitario,
                    "precio_total": i.precio_total,
                }
                for i in self.items
            ],
            "raw": self.raw,
            "error": self.error,
            "warnings": list(self.warnings),
        }


def vision_model() -> str:
    return (os.environ.get("GROQ_VISION_MODEL") or VISION_MODEL_DEFAULT).strip()


def compress_image_bytes(
    data: bytes,
    *,
    max_side: int = MAX_IMAGE_SIDE,
    quality: int = JPEG_QUALITY,
) -> tuple[bytes, str]:
    """
    Redimensiona y comprime a JPEG para bajar costo/latencia de la API.
    Retorna (bytes, mime).
    """
    from PIL import Image

    if not data:
        raise ValueError("imagen vacía")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"imagen demasiado grande (máx {MAX_UPLOAD_BYTES} bytes)")

    img = Image.open(BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    w, h = img.size
    scale = min(1.0, float(max_side) / max(w, h))
    if scale < 1.0:
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )

    out = BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def _strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _as_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_fecha(val: Any) -> tuple[Optional[str], Optional[str]]:
    """Retorna (fecha_iso | None, warning | None)."""
    if val is None or val == "":
        return None, None
    s = str(val).strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s, None
    except ValueError:
        return None, f"Fecha no válida o no ISO (recibido: {s!r}); se deja vacía."


def parse_and_validate_extraction(text: str) -> ExtractionResult:
    """Parsea la respuesta del modelo y valida campos."""
    cleaned = _strip_json_fence(text)
    if not cleaned:
        return ExtractionResult(ok=False, error="Respuesta vacía del modelo de visión.")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Intentar primer objeto {...}
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not m:
            return ExtractionResult(
                ok=False, error="No se pudo parsear JSON de la respuesta OCR."
            )
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return ExtractionResult(
                ok=False, error="JSON inválido en la respuesta OCR."
            )

    if not isinstance(data, dict):
        return ExtractionResult(ok=False, error="La respuesta OCR no es un objeto JSON.")

    err_flag = data.get("error")
    if err_flag in ("imagen_ilegible", "no_es_comprobante"):
        label = (
            "La imagen es ilegible."
            if err_flag == "imagen_ilegible"
            else "La imagen no parece un recibo ni una transferencia válida."
        )
        return ExtractionResult(ok=False, error=label, raw=data)

    tipo = data.get("tipo")
    if tipo is not None:
        tipo = str(tipo).strip().lower() or None
    if tipo not in TIPOS_VALIDOS:
        return ExtractionResult(
            ok=False,
            error="No se reconoció un recibo o transferencia válido.",
            raw=data,
        )

    monto = _as_float(data.get("monto_total"))
    if monto is None or monto <= 0:
        return ExtractionResult(
            ok=False,
            error="No se pudo leer un monto total válido.",
            raw=data,
        )

    warnings: list[str] = []
    fecha, fecha_warn = _parse_fecha(data.get("fecha"))
    if fecha_warn:
        warnings.append(fecha_warn)

    comercio = data.get("comercio")
    if comercio is not None:
        comercio = str(comercio).strip() or None

    metodo = data.get("metodo_pago")
    if metodo is not None:
        metodo = str(metodo).strip() or None

    items: list[ReceiptItemDraft] = []
    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        warnings.append("Campo items inválido; se ignora.")
        raw_items = []

    for row in raw_items:
        if not isinstance(row, dict):
            continue
        nombre = str(row.get("nombre") or "").strip()
        if not nombre:
            continue
        cant = _as_float(row.get("cantidad"))
        if cant is None or cant <= 0:
            cant = 1.0
        pu = _as_float(row.get("precio_unitario"))
        pt = _as_float(row.get("precio_total"))
        items.append(
            ReceiptItemDraft(
                nombre=nombre,
                cantidad=cant,
                precio_unitario=pu,
                precio_total=pt,
            )
        )

    if tipo == "transferencia" and items:
        warnings.append(
            "Transferencia con líneas de ítem; se conservan pero suele ser inusual."
        )

    if items:
        suma = sum(
            (i.precio_total if i.precio_total is not None else 0.0) for i in items
        )
        if suma > 0:
            diff = abs(suma - monto)
            if diff > 0.5 and diff / monto > 0.05:
                warnings.append(
                    f"La suma de ítems (${suma:.2f}) no cuadra con el total "
                    f"(${monto:.2f}); revisa antes de guardar."
                )

    return ExtractionResult(
        ok=True,
        tipo=tipo,
        comercio=comercio,
        fecha=fecha,
        monto_total=monto,
        metodo_pago=metodo,
        items=items,
        raw=data,
        warnings=warnings,
    )


def _llamar_vision_groq(*, image_b64: str, mime: str) -> Optional[str]:
    """Llama a Groq vision. Separado para poder mockear en tests."""
    from app import ai_client

    if not ai_client._hay_cuota():
        return None
    try:
        from app.billing import cuota_ia_ok, registrar_llamada_ia

        if not cuota_ia_ok():
            return None
    except Exception:
        pass

    client = ai_client._get_client()
    if not client:
        return None

    data_url = f"data:{mime};base64,{image_b64}"
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    try:
        create_kwargs: dict[str, Any] = {
            "model": vision_model(),
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
        }
        try:
            response = client.chat.completions.create(**create_kwargs)
        except TypeError:
            create_kwargs.pop("reasoning_effort", None)
            response = client.chat.completions.create(**create_kwargs)
        ai_client._registrar_llamada()
        try:
            from app.billing import registrar_llamada_ia

            registrar_llamada_ia()
        except Exception:
            pass
        ai_client._estado["conexion_ok"] = True
        return response.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower():
            ai_client._registrar_error_429(65)
        else:
            ai_client._estado["conexion_ok"] = False
        print(f"[receipt_ocr] vision error: {err[:160]}")
        return None


def extract_from_image(image_bytes: bytes) -> ExtractionResult:
    """
    Pipeline completo: comprimir → visión → parse/validate.

    No guarda en BD: la UI debe mostrar confirmación antes de persistir.
    """
    try:
        compressed, mime = compress_image_bytes(image_bytes)
    except Exception as e:
        return ExtractionResult(ok=False, error=f"No se pudo procesar la imagen: {e}")

    b64 = base64.b64encode(compressed).decode("ascii")
    text = _llamar_vision_groq(image_b64=b64, mime=mime)
    if not text:
        return ExtractionResult(
            ok=False,
            error=(
                "No hubo respuesta del modelo de visión. "
                "Revisa GROQ_API_KEY / cuota o reintenta."
            ),
        )
    return parse_and_validate_extraction(text)
