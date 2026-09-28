"""El proceso web manda briefings y recordatorios. En Railway no hay cron aparte."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

log = logging.getLogger("mission.telegram")

INTERVAL_S = 15 * 60
_started = False
_lock = threading.Lock()


def run_telegram_jobs_once() -> tuple[int, int]:
    from app.telegram import send_due_reminders, send_morning_briefings

    briefings = send_morning_briefings()
    reminders = send_due_reminders()
    log.info("telegram jobs briefing=%s reminders=%s", briefings, reminders)
    return briefings, reminders


def scheduler_enabled() -> bool:
    if os.environ.get("MISSION_TG_SCHEDULER", "1") == "0":
        return False
    return "pytest" not in sys.modules


def start_telegram_jobs() -> None:
    global _started
    if not scheduler_enabled():
        return
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_loop, name="telegram-jobs", daemon=True).start()


def _loop() -> None:
    while True:
        try:
            run_telegram_jobs_once()
        except Exception:
            log.exception("telegram jobs failed")
        time.sleep(INTERVAL_S)
