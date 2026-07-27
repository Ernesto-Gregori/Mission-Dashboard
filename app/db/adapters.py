"""SQLite date/datetime adapters (Python 3.12+)."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime


def adapt_date(val):
    """Adaptador para fechas en SQLite"""
    return val.isoformat()


def adapt_datetime(val):
    """Adaptador para datetimes en SQLite"""
    return val.isoformat()


sqlite3.register_adapter(date, adapt_date)
sqlite3.register_adapter(datetime, adapt_datetime)


def convert_date(val):
    """Conversor de fechas desde SQLite"""
    return datetime.fromisoformat(val.decode()).date()


def convert_datetime(val):
    """Conversor de datetimes desde SQLite"""
    return datetime.fromisoformat(val.decode())


sqlite3.register_converter("DATE", convert_date)
sqlite3.register_converter("TIMESTAMP", convert_datetime)
