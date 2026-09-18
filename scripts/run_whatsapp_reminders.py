#!/usr/bin/env python3
"""
Envía recordatorios de WhatsApp 30 min antes de la tarea.

Uso (cron cada 5-10 min / Railway cron):
  python scripts/run_whatsapp_reminders.py
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
    from app.whatsapp import send_due_reminders

    ensure_database()
    n = send_due_reminders()
    print(f"whatsapp_reminders: {n} enviados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
