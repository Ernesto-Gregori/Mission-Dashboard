#!/usr/bin/env python3
"""
Polling opcional de Google Calendar → Turso.

Uso (cron cada 10-15 min / Railway cron):
  python scripts/run_calendar_sync.py

No usa Calendar watch/webhook. Ver app/calendar_sync.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    from datetime import timedelta

    from app.billing import plan_vigente, puede_google
    from app.calendar_sync import pull_range
    from app.db.core import ejecutar, ensure_database
    from app.tenant import set_current_user
    from app.timezone_config import hoy as _hoy

    ensure_database()
    rows = (
        ejecutar(
            """
            SELECT id, username, rol, plan, plan_expira_en, activo
            FROM usuarios
            WHERE COALESCE(activo, 1) = 1
            """,
            fetchall=True,
        )
        or []
    )
    inicio = _hoy() - timedelta(days=7)
    fin = _hoy() + timedelta(days=21)
    n = 0
    for u in rows:
        if not puede_google(plan_vigente(u)):
            continue
        set_current_user(u)
        try:
            pull_range(inicio, fin, user_id=int(u["id"]), force=True)
            n += 1
        except Exception as e:
            print(f"sync user={u.get('username')}: {e}", file=sys.stderr)
    print(f"calendar_sync: {n} usuarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
