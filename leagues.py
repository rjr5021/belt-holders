"""
League registry. Each live league is a module with a LEAGUE dict (see
leagues/nfl.py for the contract). Leagues that are announced but not built
yet are listed in COMING so the homepage board can show them.
"""

import league_nfl as nfl

LIVE = [nfl.LEAGUE]

# Shown on the homepage board until their adapters exist.
COMING = [
    {"key": "nba", "name": "NBA", "first_season": 1946, "status": "Arrives this winter",
     "blurb": "Every game since 1946, box scores and the full chain of custody."},
    {"key": "nhl", "name": "NHL", "first_season": 1917, "status": "Arrives this winter",
     "blurb": "Every game since 1917, including what a shootout does to the belt."},
    {"key": "mlb", "name": "MLB", "first_season": 1876, "status": "Opening Day",
     "blurb": "162 games a year means the belt never sits still."},
]

ORDER = ["nfl", "nba", "nhl", "mlb"]


def by_key(key):
    for lg in LIVE:
        if lg["key"] == key:
            return lg
    return None
