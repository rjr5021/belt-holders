"""
League registry. Each live league is a module with a LEAGUE dict (see
league_nfl.py for the contract). Leagues that are announced but not built
yet are listed in COMING so the homepage board can show them.
"""

import os

import league_mlb as mlb
import league_more as more
import league_nba as nba
import league_nfl as nfl
import league_nhl as nhl

# Leagues added in October 2026 go live once their game file exists (new_leagues.py).
_NEW = [getattr(more, n) for n in ("WNBA", "MLS", "NWSL", "PWHL", "WCBB", "CFL", "EPL", "LALIGA", "SERIEA",
                                   "BUNDESLIGA", "LIGUE1", "EREDIVISIE", "INTL") if hasattr(more, n)]
LIVE = [nfl.LEAGUE, nba.LEAGUE, nhl.LEAGUE, mlb.LEAGUE] + [
    lg for lg in _NEW if os.path.exists(os.path.join("data", lg["key"], "games.csv"))]

# Shown on the homepage board until their adapters exist.
COMING = []

PRIMARY = ["nfl", "nba", "nhl", "mlb"]
GROUPS = [("More North American leagues", ["cfl", "mls", "wnba", "nwsl", "pwhl", "wcbb"]),
          ("European soccer", ["epl", "laliga", "seriea", "bundesliga", "ligue1", "eredivisie"]),
          ("International", ["intl"])]
ORDER = PRIMARY + [k for _, ks in GROUPS for k in ks if any(lg["key"] == k for lg in LIVE)]


def by_key(key):
    for lg in LIVE:
        if lg["key"] == key:
            return lg
    return None
