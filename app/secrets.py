"""
secrets.py — Lectura unificada de secrets para FastAPI.

Orden:
  1. Variables de entorno / .env
  2. Archivo .streamlit/secrets.toml (migración; solo lectura de archivo, sin paquete streamlit)
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
        load_dotenv()
    except Exception:
        pass


@lru_cache(maxsize=1)
def _secrets_toml() -> dict:
    """Parsea .streamlit/secrets.toml si existe (TOML plano + tablas)."""
    path = _ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            return _parse_toml_simple(path.read_text(encoding="utf-8"))
    try:
        with path.open("rb") as f:
            return tomllib.load(f) or {}
    except Exception:
        return {}


def _parse_toml_simple(text: str) -> dict:
    """Fallback mínimo KEY = \"value\" (sin tablas anidadas profundas)."""
    out: dict = {}
    section = out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            section = out.setdefault(name, {})
            if not isinstance(section, dict):
                section = {}
                out[name] = section
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        section[k] = v
    return out


def get_secret(name: str, default: str = "") -> str:
    """Obtiene un secret string por nombre (p.ej. GROQ_API_KEY)."""
    _load_dotenv()

    # 1) Entorno
    env = os.getenv(name)
    if env and env.strip():
        return env.strip()

    # 2) secrets.toml (migración; lectura de archivo)
    data = _secrets_toml()
    if name in data and data[name] is not None:
        return str(data[name]).strip()
    return default


def get_secret_section(name: str) -> dict:
    """Tabla TOML (p.ej. google_oauth) desde .streamlit/secrets.toml."""
    _load_dotenv()
    data = _secrets_toml()
    section = data.get(name)
    return dict(section) if isinstance(section, dict) else {}


def clear_secrets_cache() -> None:
    _secrets_toml.cache_clear()
