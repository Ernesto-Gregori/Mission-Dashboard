"""
security.py — Helpers de endurecimiento (XSS, validación).
"""
from __future__ import annotations

import html
import re

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")


def esc(value) -> str:
    """Escape HTML para sinks con unsafe_allow_html / st.html."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def username_valido(username: str) -> bool:
    return bool(USERNAME_RE.match((username or "").strip().lower()))
