"""Foto de un recibo: OCR, borrador y confirmación. No guarda hasta el sí."""
from __future__ import annotations

from app.receipt_service import TELEGRAM_MAX_PHOTO_BYTES
from app.telegram_actions.base import Accion, Contexto, Respuesta
from app.telegram_actions.finanzas import _deshacer


def _pregunta(datos: dict) -> str:
    draft = datos.get("draft") or datos
    monto = float(draft.get("monto_total") or 0)
    comercio = draft.get("comercio") or draft.get("descripcion") or "el comprobante"
    return f"Leí ${monto:.2f} en «{comercio}»."


def _confirmar(_ctx: Contexto, datos: dict) -> str | None:
    return _pregunta(datos)


def _ejecutar(_ctx: Contexto, datos: dict) -> Respuesta:
    from app.receipt_service import guardar_confirmado

    draft = dict(datos.get("draft") or datos)
    monto = float(draft.get("monto_total") or 0)
    gid, _matches = guardar_confirmado(
        draft,
        {
            "fecha": draft.get("fecha"),
            "sobre": draft.get("sobre"),
            "subcategoria": draft.get("subcategoria"),
            "descripcion": draft.get("descripcion"),
            "comercio": draft.get("comercio"),
            "metodo_pago": draft.get("metodo_pago"),
            "origen": draft.get("origen"),
            "monto_total": monto,
            "items": draft.get("lineas") or [],
        },
    )
    desc = draft.get("descripcion") or "recibo"
    return Respuesta(
        f"Anoté ${monto:.2f} en «{desc}».",
        entidad_id=int(gid),
        resumen=f"recibo ${monto:.2f} «{desc}»",
    )


def desde_foto(ctx: Contexto, raw: bytes, size: int = 0) -> Respuesta:
    from app.billing import cuota_ia_ok
    from app.onboarding import modulo_activo
    from app.receipt_service import ScanError, armar_borrador
    from app.telegram import _modulo_apagado, _run

    if not modulo_activo("finanzas", ctx.user_id):
        return _modulo_apagado(RECIBO)
    peso = size or len(raw or b"")
    if peso > TELEGRAM_MAX_PHOTO_BYTES:
        return Respuesta("La foto supera 5 MB. No leí nada.", accion="recibo")
    if not raw:
        return Respuesta("No pude bajar la foto. No leí nada.", accion="recibo")
    if len(raw) > TELEGRAM_MAX_PHOTO_BYTES:
        return Respuesta("La foto supera 5 MB. No leí nada.", accion="recibo")
    if not cuota_ia_ok(ctx.user_id):
        return Respuesta("Se agotó el cupo de IA de este mes. No leí el recibo.", accion="recibo")
    try:
        draft = armar_borrador(ctx.user_id, raw, "telegram.jpg")
    except ScanError as e:
        return Respuesta(f"{e} No guardé nada.", accion="recibo")
    except Exception:
        return Respuesta("No pude guardar la foto. No leí nada.", accion="recibo")
    return _run(ctx, RECIBO, {"draft": draft}, "foto", confirmado=False)


RECIBO = Accion(
    clave="recibo",
    modulo="finanzas",
    ejecutar=_ejecutar,
    confirmar=_confirmar,
    deshacer=_deshacer,
)
