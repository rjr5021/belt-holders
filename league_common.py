"""
Helpers shared by the league adapters that read the committed game files
written by update_data.py (data/<league>/games.csv + upcoming.json).
"""

import csv
import json
import os
from datetime import date


def read_games_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_upcoming(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def recent_teams(games, today=None):
    """Franchises that played in the latest or previous season with a
    completed game -- the roster a vacated belt may pass to at the end of
    the data."""
    latest = max(g["season"] for g in games)
    return {t for g in games if g["season"] >= latest - 1 for t in (g["home"], g["away"])}


def season_status(today=None, upcoming=None):
    """Label for the network board: 'In season', 'Opens Oct 20' or 'Offseason'."""
    today = today or date.today().isoformat()
    if upcoming:
        first = upcoming[0]["date"]
        days_out = (date.fromisoformat(first) - date.fromisoformat(today)).days
        if days_out <= 14:
            return "In season"
        if days_out <= 60:
            m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            y, mo, d = (int(x) for x in first.split("-"))
            return f"Opens {m[mo - 1]} {d}"
    return "Offseason"


def season_label(start_year):
    """1917 -> '1917–18'."""
    return f"{start_year}–{str(start_year + 1)[2:]}"
