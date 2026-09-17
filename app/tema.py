"""Tema claro/oscuro persistido por usuario y cookie."""
from __future__ import annotations

from urllib.parse import urlparse

from app.logging_config import get_logger

log = get_logger("tema")

TEMAS = ("dark", "light")
COOKIE = "mission_theme"


def ensure_tema_schema() -> None:
    from app.db.core import ejecutar

    try:
        ejecutar("ALTER TABLE user_prefs ADD COLUMN theme TEXT DEFAULT 'dark'")
    except Exception:
        pass
    try:
        ejecutar(
            """
            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY,
                week_start TEXT NOT NULL DEFAULT 'lun',
                theme TEXT NOT NULL DEFAULT 'dark',
                actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception as e:
        log.warning("ensure_tema_schema: %s", e)


def normalizar(valor: str | None) -> str:
    v = (valor or "").strip().lower()
    return v if v in TEMAS else "dark"


def obtener_tema(user_id: int | None = None) -> str:
    ensure_tema_schema()
    if user_id is None:
        return "dark"
    from app.db.core import ejecutar

    try:
        rows = (
            ejecutar(
                "SELECT theme FROM user_prefs WHERE user_id = ?",
                [int(user_id)],
                fetchall=True,
            )
            or []
        )
    except Exception:
        return "dark"
    if not rows:
        return "dark"
    return normalizar(rows[0].get("theme"))


def guardar_tema(valor: str, user_id: int | None = None) -> str:
    tema = normalizar(valor)
    if user_id is None:
        return tema
    ensure_tema_schema()
    from app.db.core import ejecutar

    ejecutar(
        """
        INSERT INTO user_prefs (user_id, week_start, theme)
        VALUES (?, 'lun', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            theme = excluded.theme,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        [int(user_id), tema],
    )
    return tema


def tema_para_request(request) -> str:
    session_t = None
    try:
        session_t = request.session.get("theme")
    except Exception:
        pass
    cookie_t = None
    try:
        cookie_t = request.cookies.get(COOKIE)
    except Exception:
        pass
    user = getattr(getattr(request, "state", None), "user", None)
    db_t = None
    if user and user.get("id") is not None:
        db_t = obtener_tema(int(user["id"]))
    return normalizar(session_t or cookie_t or db_t or "dark")


def next_seguro(request, raw: str | None = None) -> str:
    candidato = (raw or "").strip()
    if not candidato:
        ref = request.headers.get("referer") or ""
        candidato = urlparse(ref).path or "/app"
        q = urlparse(ref).query
        if q:
            candidato = f"{candidato}?{q}"
    if not candidato.startswith("/") or candidato.startswith("//"):
        return "/app"
    if candidato.startswith("/\\") or "\\" in candidato:
        return "/app"
    return candidato


def aplicar_cookie(response, tema: str) -> None:
    response.set_cookie(
        COOKIE,
        normalizar(tema),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        path="/",
    )
