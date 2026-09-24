#!/usr/bin/env python3
"""
Briefing de la mañana por Telegram. Apagado por defecto: cada usuario lo activa
en /app/usuarios?tab=telegram (hora local, default 07:00).

Idempotente por usuario y día. Solo chats vinculados, verificados y con plan vigente.
/silencio lo pausa.

Uso (cron cada 15 min / Railway cron):
  python scripts/run_telegram_briefings.py
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
    from app.db.core import ensure_database
    from app.telegram import send_morning_briefings

    ensure_database()
    n = send_morning_briefings()
    print(f"telegram_briefings: {n} enviados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
