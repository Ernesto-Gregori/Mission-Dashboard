"""Google OAuth callback (Fit + Calendar) — sin auth previa.

El state firmado lleva user_id; la cookie de sesión puede haberse perdido
al salir a Google (mismo patrón que Streamlit).
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["oauth"])


@router.get("/oauth/google/callback")
def google_oauth_callback(request: Request):
    err = request.query_params.get("error")
    if err:
        return RedirectResponse(
            f"/app/m/salud?tab=hoy&google=denied&msg={quote(str(err)[:80])}",
            status_code=303,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return RedirectResponse(
            "/app/m/salud?tab=hoy&google=err&msg=Falta%20code%20o%20state",
            status_code=303,
        )

    from app.google_fit import intercambiar_oauth_code

    session_uid = request.session.get("user_id")
    ok, msg = intercambiar_oauth_code(
        str(code),
        str(state),
        session_uid=int(session_uid) if session_uid is not None else None,
    )
    if ok:
        # Si no hay sesión, el token ya quedó guardado por user_id del state;
        # el usuario solo necesita volver a iniciar sesión.
        if session_uid is None:
            return RedirectResponse(
                "/login?google=ok",
                status_code=303,
            )
        return RedirectResponse("/app/m/salud?tab=hoy&google=ok", status_code=303)
    return RedirectResponse(
        f"/app/m/salud?tab=hoy&google=err&msg={quote((msg or 'error')[:120])}",
        status_code=303,
    )
