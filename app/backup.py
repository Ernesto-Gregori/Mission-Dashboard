"""
backup.py — Exportación simple de backup (SQLite local o dump vía SELECT).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.logging_config import get_logger

log = get_logger("backup")

BACKUP_DIR = Path(__file__).parent.parent / "data" / "backups"

# Tablas sensibles / de negocio a exportar en JSON (Turso o SQLite)
TABLAS_BACKUP = [
    "usuarios",
    "user_modulos",
    "habitos_config",
    "habitos_diarios_v2",
    "ingreso_mensual",
    "gastos_sobres",
    "bitacora_semanal",
    "bloques_fijos",
    "sesiones_completadas",
    "devocionales",
    "pedidos_oracion",
    "libros",
    "resaltados",
    "registros_salud",
    "sandbox_ideas",
    "sandbox_snippets",
    "sandbox_sesiones",
    "matrimonio_citas",
    "matrimonio_notas",
    "matrimonio_habitos",
    "eventos_calendario",
]


def exportar_backup_json(tag: str = "") -> Path | None:
    """
    Exporta filas de tablas clave a un JSON timestamped en data/backups/.
    Funciona con SQLite local y Turso (vía ejecutar).
    """
    from app.database import ejecutar, DB_PATH, usar_turso

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    out = BACKUP_DIR / f"backup{suffix}_{stamp}.json"

    payload = {
        "creado_en": datetime.now(timezone.utc).isoformat(),
        "motor": "turso" if usar_turso() else "sqlite",
        "tablas": {},
    }

    for table in TABLAS_BACKUP:
        try:
            rows = ejecutar(f"SELECT * FROM {table}", fetchall=True) or []
            # Convertir a dicts serializables
            clean = []
            for r in rows:
                if hasattr(r, "keys"):
                    clean.append({k: r[k] for k in r.keys()})
                elif isinstance(r, dict):
                    clean.append(r)
            payload["tablas"][table] = clean
        except Exception as e:
            log.warning("backup: no se pudo exportar %s: %s", table, e)
            payload["tablas"][table] = {"_error": str(e)}

    try:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        log.info("Backup JSON escrito: %s", out)
    except Exception as e:
        log.exception("No se pudo escribir backup: %s", e)
        return None

    # Copia del .db local si existe (extra)
    try:
        if DB_PATH.exists() and not usar_turso():
            dest = BACKUP_DIR / f"mission{suffix}_{stamp}.db"
            shutil.copy2(DB_PATH, dest)
            log.info("Copia SQLite: %s", dest)
    except Exception as e:
        log.warning("No se pudo copiar mission.db: %s", e)

    return out
