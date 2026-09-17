"""Scrapers de supermercados SV."""
from app.scrapers.runner import SCRAPERS, run_all_registered, run_scraper

__all__ = ["SCRAPERS", "run_scraper", "run_all_registered"]
