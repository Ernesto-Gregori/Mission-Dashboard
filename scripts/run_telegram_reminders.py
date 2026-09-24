#!/usr/bin/env python3
"""
Recordatorios de Telegram para eventos con hora (cualquier fuente: web, Google, bot).

Crea los que falten (anticipación por usuario en /app/usuarios?tab=telegram, default 30 min,
0 = apagados) y envía los vencidos. Idempotente.

Uso (cron cada 5-10 min / Railway cron):
  python scripts/run_telegram_reminders.py
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
    from app.telegram import send_due_reminders, sync_event_reminders

    ensure_database()
    creados = sync_event_reminders()
    n = send_due_reminders()
    print(f"telegram_reminders: {creados} nuevos, {n} enviados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
