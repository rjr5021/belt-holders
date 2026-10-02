"""
NBA adapter for the Belt Holders engine.

Games come from data/nba/games.csv and data/nba/upcoming.json, refreshed by
update_data.py from three sources stitched end to end:

  * 1946-47 to 2014-15: FiveThirtyEight's NBA Elo archive (BAA seasons
    included, since the NBA counts them; ABA games are not).
  * 2015-16 to 2024-25: NBA.com's full-season schedule files.
  * 2025-26 onward: ESPN's public scoreboard, plus the upcoming schedule.

Each source names teams its own way, so everything is mapped to one code per
franchise here, following the NBA's official franchise histories (the
Charlotte Hornets own 1988-2002; the Pelicans start in 2002).

Rules (shown on /rules/):

  * The belt starts with the first game in league history: New York
    Knicks 68, Toronto Huskies 66, Nov. 1, 1946.
  * A win over the holder moves the belt: regular season, NBA Cup
    championship, play-in or playoffs. Preseason and All-Star games don't count.
  * The belt follows the franchise through moves and renames.
  * A folded holder: the shared vacancy rule.
"""

import os

from league_common import read_games_csv, read_upcoming, recent_teams, season_label, season_status

KEY = "nba"
NAME = "NBA"
LONG_NAME = "The NBA Belt"
FIRST_SEASON = 1946
TIE_RULE = "holder"
DATA_DIR = os.path.join("data", "nba")

# FiveThirtyEight team_id -> (franchise, name that era)
CODES_538 = {
    "TRH": ("TRH", "Toronto Huskies"), "PIT": ("PIT", "Pittsburgh Ironmen"), "CLR": ("CLR", "Cleveland Rebels"),
    "DTF": ("DTF", "Detroit Falcons"), "STB": ("STB", "St. Louis Bombers"), "CHS": ("CHS", "Chicago Stags"),
    "PRO": ("PRO", "Providence Steamrollers"), "WSC": ("WSC", "Washington Capitols"),
    "BLB": ("BLB", "Baltimore Bullets"), "INJ": ("INJ", "Indianapolis Jets"), "AND": ("AND", "Anderson Packers"),
    "DNN": ("DNN", "Denver Nuggets"), "SHE": ("SHE", "Sheboygan Red Skins"), "WAT": ("WAT", "Waterloo Hawks"),
    "INO": ("INO", "Indianapolis Olympians"),
    "BOS": ("BOS", "Boston Celtics"), "NYK": ("NYK", "New York Knicks"),
    "PHW": ("GSW", "Philadelphia Warriors"), "SFW": ("GSW", "San Francisco Warriors"), "GSW": ("GSW", "Golden State Warriors"),
    "MNL": ("LAL", "Minneapolis Lakers"), "LAL": ("LAL", "Los Angeles Lakers"),
    "ROC": ("SAC", "Rochester Royals"), "CIN": ("SAC", "Cincinnati Royals"), "KCO": ("SAC", "Kansas City-Omaha Kings"),
    "KCK": ("SAC", "Kansas City Kings"), "SAC": ("SAC", "Sacramento Kings"),
    "FTW": ("DET", "Fort Wayne Pistons"), "DET": ("DET", "Detroit Pistons"),
    "SYR": ("PHI", "Syracuse Nationals"), "PHI": ("PHI", "Philadelphia 76ers"),
    "TRI": ("ATL", "Tri-Cities Blackhawks"), "MLH": ("ATL", "Milwaukee Hawks"), "STL": ("ATL", "St. Louis Hawks"),
    "ATL": ("ATL", "Atlanta Hawks"),
    "CHP": ("WAS", "Chicago Packers"), "CHZ": ("WAS", "Chicago Zephyrs"), "BAL": ("WAS", "Baltimore Bullets"),
    "CAP": ("WAS", "Capital Bullets"), "WSB": ("WAS", "Washington Bullets"), "WAS": ("WAS", "Washington Wizards"),
    "SDR": ("HOU", "San Diego Rockets"), "HOU": ("HOU", "Houston Rockets"),
    "SEA": ("OKC", "Seattle SuperSonics"), "OKC": ("OKC", "Oklahoma City Thunder"),
    "BUF": ("LAC", "Buffalo Braves"), "SDC": ("LAC", "San Diego Clippers"), "LAC": ("LAC", "Los Angeles Clippers"),
    "NOJ": ("UTA", "New Orleans Jazz"), "UTA": ("UTA", "Utah Jazz"),
    "NYN": ("BKN", "New York Nets"), "NJN": ("BKN", "New Jersey Nets"), "BRK": ("BKN", "Brooklyn Nets"),
    "CHH": ("CHA", "Charlotte Hornets"), "CHA": ("CHA", "Charlotte Bobcats"), "CHO": ("CHA", "Charlotte Hornets"),
    "NOH": ("NOP", "New Orleans Hornets"), "NOK": ("NOP", "New Orleans/Oklahoma City Hornets"),
    "NOP": ("NOP", "New Orleans Pelicans"),
    "VAN": ("MEM", "Vancouver Grizzlies"), "MEM": ("MEM", "Memphis Grizzlies"),
    "CHI": ("CHI", "Chicago Bulls"), "MIL": ("MIL", "Milwaukee Bucks"), "PHO": ("PHX", "Phoenix Suns"),
    "CLE": ("CLE", "Cleveland Cavaliers"), "POR": ("POR", "Portland Trail Blazers"), "DEN": ("DEN", "Denver Nuggets"),
    "IND": ("IND", "Indiana Pacers"), "SAS": ("SAS", "San Antonio Spurs"), "DAL": ("DAL", "Dallas Mavericks"),
    "MIA": ("MIA", "Miami Heat"), "ORL": ("ORL", "Orlando Magic"), "MIN": ("MIN", "Minnesota Timberwolves"),
    "TOR": ("TOR", "Toronto Raptors"),
}

# NBA.com tricodes (2015-16 on) and ESPN abbreviations -> franchise
MODERN = {
    "ATL": "ATL", "BOS": "BOS", "BKN": "BKN", "CHA": "CHA", "CHI": "CHI", "CLE": "CLE", "DAL": "DAL",
    "DEN": "DEN", "DET": "DET", "GSW": "GSW", "GS": "GSW", "HOU": "HOU", "IND": "IND", "LAC": "LAC",
    "LAL": "LAL", "MEM": "MEM", "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NOP": "NOP", "NO": "NOP",
    "NYK": "NYK", "NY": "NYK", "OKC": "OKC", "ORL": "ORL", "PHI": "PHI", "PHX": "PHX", "POR": "POR",
    "SAC": "SAC", "SAS": "SAS", "SA": "SAS", "TOR": "TOR", "UTA": "UTA", "UTAH": "UTA", "WAS": "WAS",
    "WSH": "WAS",
}

TEAMS = {
    "ATL": ("Atlanta Hawks", "Hawks", "#c8102e", "#fdb927"),
    "BOS": ("Boston Celtics", "Celtics", "#007a33", "#ba9653"),
    "BKN": ("Brooklyn Nets", "Nets", "#111111", "#ffffff"),
    "CHA": ("Charlotte Hornets", "Hornets", "#1d1160", "#00788c"),
    "CHI": ("Chicago Bulls", "Bulls", "#ce1141", "#111111"),
    "CLE": ("Cleveland Cavaliers", "Cavaliers", "#860038", "#fdbb30"),
    "DAL": ("Dallas Mavericks", "Mavericks", "#00538c", "#b8c4ca"),
    "DEN": ("Denver Nuggets", "Nuggets", "#0e2240", "#fec524"),
    "DET": ("Detroit Pistons", "Pistons", "#c8102e", "#1d42ba"),
    "GSW": ("Golden State Warriors", "Warriors", "#1d428a", "#ffc72c"),
    "HOU": ("Houston Rockets", "Rockets", "#ce1141", "#111111"),
    "IND": ("Indiana Pacers", "Pacers", "#002d62", "#fdbb30"),
    "LAC": ("Los Angeles Clippers", "Clippers", "#c8102e", "#1d428a"),
    "LAL": ("Los Angeles Lakers", "Lakers", "#552583", "#fdb927"),
    "MEM": ("Memphis Grizzlies", "Grizzlies", "#5d76a9", "#12173f"),
    "MIA": ("Miami Heat", "Heat", "#98002e", "#f9a01b"),
    "MIL": ("Milwaukee Bucks", "Bucks", "#00471b", "#eee1c6"),
    "MIN": ("Minnesota Timberwolves", "Timberwolves", "#0c2340", "#78be20"),
    "NOP": ("New Orleans Pelicans", "Pelicans", "#0c2340", "#c8102e"),
    "NYK": ("New York Knicks", "Knicks", "#006bb6", "#f58426"),
    "OKC": ("Oklahoma City Thunder", "Thunder", "#007ac1", "#ef3b24"),
    "ORL": ("Orlando Magic", "Magic", "#0077c0", "#c4ced4"),
    "PHI": ("Philadelphia 76ers", "76ers", "#006bb6", "#ed174c"),
    "PHX": ("Phoenix Suns", "Suns", "#1d1160", "#e56020"),
    "POR": ("Portland Trail Blazers", "Trail Blazers", "#e03a3e", "#111111"),
    "SAC": ("Sacramento Kings", "Kings", "#5a2d81", "#63727a"),
    "SAS": ("San Antonio Spurs", "Spurs", "#111111", "#c4ced4"),
    "TOR": ("Toronto Raptors", "Raptors", "#ce1141", "#111111"),
    "UTA": ("Utah Jazz", "Jazz", "#002b5c", "#f9a01b"),
    "WAS": ("Washington Wizards", "Wizards", "#002b5c", "#e31837"),
    # no longer playing
    "TRH": ("Toronto Huskies", "Huskies", None, None), "PIT": ("Pittsburgh Ironmen", "Ironmen", None, None),
    "CLR": ("Cleveland Rebels", "Rebels", None, None), "DTF": ("Detroit Falcons", "Falcons", None, None),
    "STB": ("St. Louis Bombers", "Bombers", None, None), "CHS": ("Chicago Stags", "Stags", None, None),
    "PRO": ("Providence Steamrollers", "Steamrollers", None, None),
    "WSC": ("Washington Capitols", "Capitols", None, None),
    "BLB": ("Baltimore Bullets (1947–54)", "Bullets", None, None),
    "INJ": ("Indianapolis Jets", "Jets", None, None), "AND": ("Anderson Packers", "Packers", None, None),
    "DNN": ("Denver Nuggets (1949–50)", "Nuggets", None, None),
    "SHE": ("Sheboygan Red Skins", "Red Skins", None, None), "WAT": ("Waterloo Hawks", "Hawks", None, None),
    "INO": ("Indianapolis Olympians", "Olympians", None, None),
}
DEFUNCT_COLORS = ("#5b5140", "#cfc4ad")

_ERA = {}


def _franchise(code, source):
    if source == "538":
        return CODES_538.get(code, (None, None))
    f = MODERN.get(code)
    return (f, TEAMS[f][0]) if f else (None, None)


def _load_eras():
    if _ERA:
        return
    path = os.path.join(DATA_DIR, "games.csv")
    if not os.path.exists(path):
        return
    for x in read_games_csv(path):
        s = int(x["season"])
        for side in ("home", "away"):
            f, name = _franchise(x[side], x["source"])
            if f:
                _ERA[(f, s)] = name


def team_name(code, season=None):
    if season is not None:
        _load_eras()
        n = _ERA.get((code, int(season)))
        if n:
            return n
    return TEAMS.get(code, (code,))[0]


def short_name(code):
    return TEAMS.get(code, (code, code))[1]


def team_colors(code):
    t = TEAMS.get(code)
    return (t[2], t[3]) if t and t[2] else DEFUNCT_COLORS


def load_games(refresh=True):
    rows = read_games_csv(os.path.join(DATA_DIR, "games.csv"))
    games, skipped = [], 0
    for x in rows:
        h, _ = _franchise(x["home"], x["source"])
        a, _ = _franchise(x["away"], x["source"])
        if not h or not a:
            skipped += 1
            continue
        games.append({
            "id": x["id"], "date": x["date"], "season": int(x["season"]), "week": None,
            "season_type": x["season_type"], "home": h, "away": a,
            "home_points": int(x["home_points"]), "away_points": int(x["away_points"]),
            "neutral": x["neutral"] == "1", "note": x.get("note") or "",
        })
    if skipped:
        print(f"[nba] skipped {skipped} games with non-NBA teams")
    upcoming = []
    for u in read_upcoming(os.path.join(DATA_DIR, "upcoming.json")):
        h, a = MODERN.get(u["home"]), MODERN.get(u["away"])
        if h and a:
            upcoming.append({"id": u["id"], "date": u["date"], "season": u["season"],
                             "season_type": u["season_type"], "home": h, "away": a,
                             "neutral": u.get("neutral") == "1", "kickoff": u.get("start_et"),
                             "spread": u.get("spread"), "stadium": u.get("venue")})
    games.sort(key=lambda g: (g["date"], g["season_type"] != "regular", str(g["id"])))
    return games, upcoming


def rules_note(first_game, name):
    return ("<p><b>NBA.</b> The belt starts with the first game in league history: the New York Knicks "
            "beat the Toronto Huskies 68–66 on November 1, 1946. The Basketball Association of America seasons "
            "(1946–49) count, as the NBA counts them; ABA games don't. Regular-season, NBA Cup, play-in and "
            "playoff games all count; preseason and All-Star games don't. Franchises follow the NBA's official "
            "histories: the Charlotte Hornets own the 1988–2002 Hornets years, and the Pelicans begin in 2002.</p>")


SOURCES = ("NBA results from 1946–47 through 2014–15 come from FiveThirtyEight's public NBA archive; 2015–16 "
           "through 2024–25 from NBA.com's season schedules; 2025–26 onward from ESPN's public scoreboard.")

LEAGUE = {
    "key": KEY, "name": NAME, "long_name": LONG_NAME, "first_season": FIRST_SEASON,
    "tie_rule": TIE_RULE, "sport": "Basketball", "load_games": load_games, "recent_teams": recent_teams,
    "team_name": team_name, "team_colors": team_colors, "short_name": short_name,
    "season_status": season_status, "season_label": season_label, "live": True,
    "rules_note": rules_note, "sources": SOURCES, "time_word": "Tip-off",
    "alt_starts": [{"season": 1976, "label": "since the 1976 ABA merger", "why": "Four ABA teams joined for 1976–77; this belt starts with that season's first game."},
                   {"season": 1949, "label": "since the NBA took its name", "why": "The BAA absorbed the NBL and became the NBA for 1949–50; this belt starts there instead of with the BAA's 1946 opener."}],
}
