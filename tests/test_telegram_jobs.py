"""El proceso web dispara el briefing; no hace falta un cron externo."""
from __future__ import annotations


def test_una_pasada_llama_briefing_y_recordatorios(monkeypatch):
    from app import telegram_jobs

    calls = []
    monkeypatch.setattr("app.telegram.send_morning_briefings", lambda: calls.append("b") or 2)
    monkeypatch.setattr("app.telegram.send_due_reminders", lambda: calls.append("r") or 1)
    assert telegram_jobs.run_telegram_jobs_once() == (2, 1)
    assert calls == ["b", "r"]


def test_no_arranca_bajo_pytest():
    from app.telegram_jobs import scheduler_enabled, start_telegram_jobs

    assert scheduler_enabled() is False
    start_telegram_jobs()
