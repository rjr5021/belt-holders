"""
MLB adapter for the Belt Holders engine.

Games come from data/mlb/games.csv and data/mlb/upcoming.json, refreshed by
update_data.py:

  * Retrosheet game logs (via the Chadwick Bureau's GitHub mirror): every
    National League game since 1876, every American League game since 1901,
    interleague games, and every postseason game (World Series since 1903,
    plus wild card, division and championship series).
  * MLB's Stats API for seasons Retrosheet hasn't published yet (the current
    one), plus the upcoming schedule.

  The information used here was obtained free of charge from and is
  copyrighted by Retrosheet. Interested parties may contact Retrosheet at
  www.retrosheet.org.

Rules (shown on /rules/):

  * The belt starts with the first National League game: Boston 6,
    Philadelphia 5, April 22, 1876.
  * A win over the holder moves it: regular season, tiebreaker games and
    the postseason.
  * A tie (a game called with the score level, common before lights) is a
    successful defense. Forfeits go to the team awarded the win.
  * NL and AL only. The other major leagues of the 1800s and 1910s, and the
    Negro Leagues, never played the holder in an official game, so they
    never had a shot at the belt.
  * The belt follows the franchise through moves and renames.
"""

import os

from league_common import read_games_csv, read_upcoming, recent_teams, season_status

KEY = "mlb"
NAME = "MLB"
LONG_NAME = "The MLB Belt"
FIRST_SEASON = 1876
TIE_RULE = "holder"
DATA_DIR = os.path.join("data", "mlb")

# Retrosheet team code -> franchise
RETRO = {
    "BSN": "ATL", "MLN": "ATL", "ATL": "ATL", "CHN": "CHC", "CIN": "CIN", "PHI": "PHI", "PIT": "PIT",
    "BRO": "LAD", "LAN": "LAD", "NY1": "SF", "SFN": "SF", "SLN": "STL", "NYN": "NYM", "HOU": "HOU",
    "MON": "WSH", "WAS": "WSH", "SDN": "SD", "FLO": "MIA", "MIA": "MIA", "COL": "COL", "ARI": "ARI",
    "MIL": "MIL", "SE1": "MIL",
    "NYA": "NYY", "BOS": "BOS", "CHA": "CWS", "CLE": "CLE", "DET": "DET",
    "MLA": "BAL", "SLA": "BAL", "BAL": "BAL", "PHA": "ATH", "KC1": "ATH", "OAK": "ATH", "ATH": "ATH",
    "WS1": "MIN", "MIN": "MIN", "WS2": "TEX", "TEX": "TEX", "LAA": "LAA", "CAL": "LAA", "ANA": "LAA",
    "KCA": "KC", "SEA": "SEA", "TOR": "TOR", "TBA": "TB",
    # franchises that no longer exist
    "HAR": "HAR", "LS1": "LS1", "NY3": "NY3", "PHN": "PHN", "SL3": "SL3", "IN1": "IN1", "ML2": "ML2",
    "PRO": "PRO", "BFN": "BFN", "CL2": "CL2", "SR1": "SR1", "TRN": "TRN", "CN1": "CN1", "CN4": "CN4",
    "WOR": "WOR", "DTN": "DTN", "SL5": "SL5", "KCN": "KCN", "WS8": "WS8", "IN3": "IN3", "CL4": "CL4",
    "BLN": "BLN", "LS3": "LS3", "WSN": "WSN", "BLA": "BLA",
}
# MLB Stats API team id -> franchise
API = {108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN", 114: "CLE", 115: "COL",
       116: "DET", 117: "HOU", 118: "KC", 119: "LAD", 120: "WSH", 121: "NYM", 133: "ATH", 134: "PIT",
       135: "SD", 136: "SEA", 137: "SF", 138: "STL", 139: "TB", 140: "TEX", 141: "TOR", 142: "MIN",
       143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL"}

TEAMS = {
    "ARI": ("Arizona Diamondbacks", "D-backs", "#a71930", "#e3d4ad"),
    "ATH": ("Athletics", "Athletics", "#003831", "#efb21e"),
    "ATL": ("Atlanta Braves", "Braves", "#13274f", "#ce1141"),
    "BAL": ("Baltimore Orioles", "Orioles", "#df4601", "#111111"),
    "BOS": ("Boston Red Sox", "Red Sox", "#bd3039", "#0c2340"),
    "CHC": ("Chicago Cubs", "Cubs", "#0e3386", "#cc3433"),
    "CIN": ("Cincinnati Reds", "Reds", "#c6011f", "#111111"),
    "CLE": ("Cleveland Guardians", "Guardians", "#00385d", "#e50022"),
    "COL": ("Colorado Rockies", "Rockies", "#333366", "#c4ced4"),
    "CWS": ("Chicago White Sox", "White Sox", "#27251f", "#c4ced4"),
    "DET": ("Detroit Tigers", "Tigers", "#0c2340", "#fa4616"),
    "HOU": ("Houston Astros", "Astros", "#002d62", "#eb6e1f"),
    "KC": ("Kansas City Royals", "Royals", "#004687", "#bd9b60"),
    "LAA": ("Los Angeles Angels", "Angels", "#ba0021", "#c4ced4"),
    "LAD": ("Los Angeles Dodgers", "Dodgers", "#005a9c", "#ef3e42"),
    "MIA": ("Miami Marlins", "Marlins", "#00a3e0", "#ef3340"),
    "MIL": ("Milwaukee Brewers", "Brewers", "#12284b", "#ffc52f"),
    "MIN": ("Minnesota Twins", "Twins", "#002b5c", "#d31145"),
    "NYM": ("New York Mets", "Mets", "#002d72", "#ff5910"),
    "NYY": ("New York Yankees", "Yankees", "#0c2340", "#c4ced3"),
    "PHI": ("Philadelphia Phillies", "Phillies", "#e81828", "#002d72"),
    "PIT": ("Pittsburgh Pirates", "Pirates", "#27251f", "#fdb827"),
    "SD": ("San Diego Padres", "Padres", "#2f241d", "#ffc425"),
    "SEA": ("Seattle Mariners", "Mariners", "#0c2c56", "#005c5c"),
    "SF": ("San Francisco Giants", "Giants", "#fd5a1e", "#27251f"),
    "STL": ("St. Louis Cardinals", "Cardinals", "#c41e3a", "#0c2340"),
    "TB": ("Tampa Bay Rays", "Rays", "#092c5c", "#8fbce6"),
    "TEX": ("Texas Rangers", "Rangers", "#003278", "#c0111f"),
    "TOR": ("Toronto Blue Jays", "Blue Jays", "#134a8e", "#e8291c"),
    "WSH": ("Washington Nationals", "Nationals", "#ab0003", "#14225a"),
    # gone
    "HAR": ("Hartford Dark Blues", "Dark Blues", None, None), "LS1": ("Louisville Grays", "Grays", None, None),
    "NY3": ("New York Mutuals", "Mutuals", None, None), "PHN": ("Philadelphia Athletics (1876)", "Athletics", None, None),
    "SL3": ("St. Louis Brown Stockings", "Brown Stockings", None, None), "IN1": ("Indianapolis Blues", "Blues", None, None),
    "ML2": ("Milwaukee Grays", "Grays", None, None), "PRO": ("Providence Grays", "Grays", None, None),
    "BFN": ("Buffalo Bisons", "Bisons", None, None), "CL2": ("Cleveland Blues (1879–84)", "Blues", None, None),
    "SR1": ("Syracuse Stars", "Stars", None, None), "TRN": ("Troy Trojans", "Trojans", None, None),
    "CN1": ("Cincinnati Reds (1876–80)", "Reds", None, None), "CN4": ("Cincinnati Stars", "Stars", None, None),
    "WOR": ("Worcester Worcesters", "Worcesters", None, None), "DTN": ("Detroit Wolverines", "Wolverines", None, None),
    "SL5": ("St. Louis Maroons", "Maroons", None, None), "KCN": ("Kansas City Cowboys", "Cowboys", None, None),
    "WS8": ("Washington Nationals (1886–89)", "Nationals", None, None), "IN3": ("Indianapolis Hoosiers", "Hoosiers", None, None),
    "CL4": ("Cleveland Spiders", "Spiders", None, None), "BLN": ("Baltimore Orioles (1892–99)", "Orioles", None, None),
    "LS3": ("Louisville Colonels", "Colonels", None, None), "WSN": ("Washington Senators (1892–99)", "Senators", None, None),
    "BLA": ("Baltimore Orioles (1901–02)", "Orioles", None, None),
}
DEFUNCT_COLORS = ("#5b5140", "#cfc4ad")

# (last season, name) breakpoints, oldest first
ERAS = {
    "ATL": [(1882, "Boston Red Caps"), (1906, "Boston Beaneaters"), (1910, "Boston Doves"), (1911, "Boston Rustlers"),
            (1935, "Boston Braves"), (1940, "Boston Bees"), (1952, "Boston Braves"), (1965, "Milwaukee Braves")],
    "CHC": [(1889, "Chicago White Stockings"), (1897, "Chicago Colts"), (1902, "Chicago Orphans")],
    "LAD": [(1898, "Brooklyn Bridegrooms"), (1910, "Brooklyn Superbas"), (1913, "Brooklyn Dodgers"),
            (1931, "Brooklyn Robins"), (1957, "Brooklyn Dodgers")],
    "SF": [(1884, "New York Gothams"), (1957, "New York Giants")],
    "STL": [(1898, "St. Louis Browns"), (1899, "St. Louis Perfectos")],
    "PHI": [(1889, "Philadelphia Quakers")],
    "PIT": [(1890, "Pittsburgh Alleghenys")],
    "NYY": [(1912, "New York Highlanders")],
    "BOS": [(1907, "Boston Americans")],
    "CLE": [(1901, "Cleveland Blues"), (1902, "Cleveland Bronchos"), (1914, "Cleveland Naps"), (2021, "Cleveland Indians")],
    "BAL": [(1901, "Milwaukee Brewers"), (1953, "St. Louis Browns")],
    "ATH": [(1954, "Philadelphia Athletics"), (1967, "Kansas City Athletics"), (2024, "Oakland Athletics")],
    "MIN": [(1960, "Washington Senators")],
    "TEX": [(1971, "Washington Senators")],
    "LAA": [(1964, "Los Angeles Angels"), (1996, "California Angels"), (2004, "Anaheim Angels"),
            (2015, "Los Angeles Angels of Anaheim")],
    "HOU": [(1964, "Houston Colt .45s")],
    "WSH": [(2004, "Montreal Expos")],
    "MIL": [(1969, "Seattle Pilots")],
    "MIA": [(2011, "Florida Marlins")],
    "TB": [(2007, "Tampa Bay Devil Rays")],
}


def team_name(code, season=None):
    if season is not None:
        for last, name in ERAS.get(code, []):
            if int(season) <= last:
                return name
    return TEAMS.get(code, (code,))[0]


def short_name(code):
    return TEAMS.get(code, (code, code))[1]


def team_colors(code):
    t = TEAMS.get(code)
    return (t[2], t[3]) if t and t[2] else DEFUNCT_COLORS


def _franchise(raw):
    if raw.startswith("m") and raw[1:].isdigit():
        return API.get(int(raw[1:]))
    return RETRO.get(raw)


def load_games(refresh=True):
    games, skipped = [], 0
    for x in read_games_csv(os.path.join(DATA_DIR, "games.csv")):
        h, a = _franchise(x["home"]), _franchise(x["away"])
        if not h or not a:
            skipped += 1
            continue
        games.append({
            "id": x["id"], "date": x["date"], "season": int(x["season"]), "week": None,
            "season_type": x["season_type"], "home": h, "away": a,
            "home_points": int(x["home_points"]), "away_points": int(x["away_points"]),
            "neutral": False, "note": x.get("note") or "",
        })
    if skipped:
        print(f"[mlb] skipped {skipped} games with unmapped teams")
    upcoming = []
    for u in read_upcoming(os.path.join(DATA_DIR, "upcoming.json")):
        h, a = _franchise(u["home"]), _franchise(u["away"])
        if h and a:
            upcoming.append({"id": u["id"], "date": u["date"], "season": u["season"],
                             "season_type": u["season_type"], "home": h, "away": a, "neutral": False,
                             "kickoff": u.get("start_et"), "stadium": u.get("venue")})
    games.sort(key=lambda g: (g["date"], g["season_type"] != "regular", g["id"]))
    return games, upcoming


def rules_note(first_game, name):
    return ("<p><b>MLB.</b> The belt starts with the first National League game: Boston beat Philadelphia 6–5 on "
            "April 22, 1876. National League games count from 1876, American League games from 1901, plus "
            "interleague games and the whole postseason, so the belt couldn't cross into the American League "
            "until the 1903 World Series. Tie games, called for darkness or weather before the lights era, are "
            "successful defenses; forfeits go to the team awarded the win. The other major leagues of the 1800s "
            "and 1910s, and the Negro Leagues, never played the holder in an official game, so they never had a "
            "shot at it. Franchises follow the team through moves and renames: the Braves are one franchise from "
            "Boston to Milwaukee to Atlanta.</p>")


SOURCES = ("MLB results through last season come from Retrosheet: the information used here was obtained free of "
           "charge from and is copyrighted by Retrosheet (www.retrosheet.org). The current season comes from MLB's "
           "public Stats API.")

LEAGUE = {
    "key": KEY, "name": NAME, "long_name": LONG_NAME, "first_season": FIRST_SEASON,
    "tie_rule": TIE_RULE, "sport": "Baseball", "load_games": load_games, "recent_teams": recent_teams,
    "team_name": team_name, "team_colors": team_colors, "short_name": short_name,
    "season_status": season_status, "live": True,
    "rules_note": rules_note, "sources": SOURCES, "time_word": "First pitch",
}
