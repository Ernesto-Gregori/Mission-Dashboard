#!/usr/bin/env python3
"""
Batch opcional: genera briefing cruzado para usuarios con módulos activos.

Uso (cron semanal / Railway cron):
  python scripts/run_coach_briefings.py

Respeta cupo por plan (Free: 1/semana, Premium: 7/semana).
No fuerza si el cupo está agotado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    from app.billing import plan_vigente
    from app.coach_insights import generar_briefing
    from app.db.core import ejecutar, ensure_database
    from app.tenant import set_current_user

    ensure_database()
    rows = (
        ejecutar(
            """
            SELECT DISTINCT u.id, u.username, u.rol, u.plan
            FROM usuarios u
            JOIN user_modulos m ON m.user_id = u.id AND m.activo = 1
            WHERE COALESCE(u.activo, 1) = 1
              AND COALESCE(u.onboarding_completo, 0) = 1
            """,
            fetchall=True,
        )
        or []
    )
    ok_n = 0
    skip_n = 0
    for r in rows:
        user = dict(r)
        set_current_user(user)
        plan = plan_vigente(user)
        ok, msg, _ = generar_briefing(int(user["id"]), plan=plan)
        if ok:
            ok_n += 1
            print(f"[ok] user={user['id']} {user.get('username')}: {msg}")
        else:
            skip_n += 1
            print(f"[skip] user={user['id']} {user.get('username')}: {msg}")
    print(f"done ok={ok_n} skip={skip_n} total={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
