"""
League registry. Each live league is a module with a LEAGUE dict (see
league_nfl.py for the contract). Leagues that are announced but not built
yet are listed in COMING so the homepage board can show them.
"""

import league_mlb as mlb
import league_nba as nba
import league_nfl as nfl
import league_nhl as nhl

LIVE = [nfl.LEAGUE, nba.LEAGUE, nhl.LEAGUE, mlb.LEAGUE]

# Shown on the homepage board until their adapters exist.
COMING = []

ORDER = ["nfl", "nba", "nhl", "mlb"]


def by_key(key):
    for lg in LIVE:
        if lg["key"] == key:
            return lg
    return None
