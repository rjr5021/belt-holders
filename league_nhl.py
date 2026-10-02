"""
NHL adapter for the Belt Holders engine.

Games come from data/nhl/games.csv and data/nhl/upcoming.json, which
update_data.py refreshes from the NHL's own stats API (every regular-season
and playoff game since the league's first night, Dec. 19, 1917).

Rules (shown on /rules/):

  * The belt starts with the first NHL game on record: Montreal Canadiens 7,
    Ottawa Senators 4, Dec. 19, 1917 (game 1 of that night's two).
  * A win over the holder moves the belt, regular season or playoffs.
    Overtime and shootout wins count as wins -- the result the NHL puts in
    the standings is the result the belt uses.
  * A tie (possible until 2004-05) is a successful defense.
  * Only games between two NHL clubs count, so the Stanley Cup Finals against
    Pacific Coast and Western league champions (1918-1926) don't.
  * The belt follows a franchise through moves and renames, as the NHL
    records its franchises (Utah is its own franchise, as the league has it).
  * A folded holder: the shared vacancy rule -- the belt goes back to the most
    recent earlier holder still playing.
"""

import os

from league_common import read_games_csv, read_upcoming, recent_teams, season_label, season_status

KEY = "nhl"
NAME = "NHL"
LONG_NAME = "The NHL Belt"
FIRST_SEASON = 1917
TIE_RULE = "holder"
DATA_DIR = os.path.join("data", "nhl")

# NHL stats-API team id -> (franchise code, name in that era)
IDS = {
    8: ("MTL", "Montréal Canadiens"), 41: ("MWN", "Montreal Wanderers"),
    36: ("SEN", "Ottawa Senators"), 45: ("SEN", "St. Louis Eagles"),
    42: ("HAM", "Quebec Bulldogs"), 37: ("HAM", "Hamilton Tigers"),
    57: ("TOR", "Toronto Arenas"), 58: ("TOR", "Toronto St. Patricks"), 10: ("TOR", "Toronto Maple Leafs"),
    6: ("BOS", "Boston Bruins"), 43: ("MMR", "Montreal Maroons"),
    44: ("NYA", "New York Americans"), 51: ("NYA", "Brooklyn Americans"),
    38: ("PIR", "Pittsburgh Pirates"), 39: ("PIR", "Philadelphia Quakers"),
    3: ("NYR", "New York Rangers"), 16: ("CHI", "Chicago Blackhawks"),
    40: ("DET", "Detroit Cougars"), 50: ("DET", "Detroit Falcons"), 17: ("DET", "Detroit Red Wings"),
    46: ("CLE", "Oakland Seals"), 56: ("CLE", "California Golden Seals"), 49: ("CLE", "Cleveland Barons"),
    26: ("LAK", "Los Angeles Kings"), 31: ("DAL", "Minnesota North Stars"), 25: ("DAL", "Dallas Stars"),
    4: ("PHI", "Philadelphia Flyers"), 5: ("PIT", "Pittsburgh Penguins"), 19: ("STL", "St. Louis Blues"),
    7: ("BUF", "Buffalo Sabres"), 23: ("VAN", "Vancouver Canucks"),
    47: ("CGY", "Atlanta Flames"), 20: ("CGY", "Calgary Flames"), 2: ("NYI", "New York Islanders"),
    48: ("NJD", "Kansas City Scouts"), 35: ("NJD", "Colorado Rockies"), 1: ("NJD", "New Jersey Devils"),
    15: ("WSH", "Washington Capitals"), 22: ("EDM", "Edmonton Oilers"),
    34: ("CAR", "Hartford Whalers"), 12: ("CAR", "Carolina Hurricanes"),
    32: ("COL", "Quebec Nordiques"), 21: ("COL", "Colorado Avalanche"),
    33: ("ARI", "Winnipeg Jets"), 27: ("ARI", "Phoenix Coyotes"), 53: ("ARI", "Arizona Coyotes"),
    28: ("SJS", "San Jose Sharks"), 9: ("OTT", "Ottawa Senators"), 14: ("TBL", "Tampa Bay Lightning"),
    24: ("ANA", "Anaheim Ducks"), 13: ("FLA", "Florida Panthers"), 18: ("NSH", "Nashville Predators"),
    11: ("WPG", "Atlanta Thrashers"), 52: ("WPG", "Winnipeg Jets"),
    29: ("CBJ", "Columbus Blue Jackets"), 30: ("MIN", "Minnesota Wild"),
    54: ("VGK", "Vegas Golden Knights"), 55: ("SEA", "Seattle Kraken"),
    59: ("UTA", "Utah Hockey Club"), 68: ("UTA", "Utah Mammoth"),
}

# franchise -> (today's name, short name, primary, secondary). None colors = gone.
TEAMS = {
    "ANA": ("Anaheim Ducks", "Ducks", "#f47a38", "#111111"),
    "BOS": ("Boston Bruins", "Bruins", "#111111", "#ffb81c"),
    "BUF": ("Buffalo Sabres", "Sabres", "#003087", "#ffb81c"),
    "CGY": ("Calgary Flames", "Flames", "#c8102e", "#f1be48"),
    "CAR": ("Carolina Hurricanes", "Hurricanes", "#ce1126", "#111111"),
    "CHI": ("Chicago Blackhawks", "Blackhawks", "#cf0a2c", "#111111"),
    "COL": ("Colorado Avalanche", "Avalanche", "#6f263d", "#236192"),
    "CBJ": ("Columbus Blue Jackets", "Blue Jackets", "#002654", "#ce1126"),
    "DAL": ("Dallas Stars", "Stars", "#006847", "#8f8f8c"),
    "DET": ("Detroit Red Wings", "Red Wings", "#ce1126", "#ffffff"),
    "EDM": ("Edmonton Oilers", "Oilers", "#041e42", "#ff4c00"),
    "FLA": ("Florida Panthers", "Panthers", "#041e42", "#c8102e"),
    "LAK": ("Los Angeles Kings", "Kings", "#111111", "#a2aaad"),
    "MIN": ("Minnesota Wild", "Wild", "#154734", "#a6192e"),
    "MTL": ("Montréal Canadiens", "Canadiens", "#af1e2d", "#192168"),
    "NSH": ("Nashville Predators", "Predators", "#041e42", "#ffb81c"),
    "NJD": ("New Jersey Devils", "Devils", "#ce1126", "#111111"),
    "NYI": ("New York Islanders", "Islanders", "#00539b", "#f47d30"),
    "NYR": ("New York Rangers", "Rangers", "#0038a8", "#ce1126"),
    "OTT": ("Ottawa Senators", "Senators", "#c52032", "#c2912c"),
    "PHI": ("Philadelphia Flyers", "Flyers", "#f74902", "#111111"),
    "PIT": ("Pittsburgh Penguins", "Penguins", "#111111", "#fcb514"),
    "SJS": ("San Jose Sharks", "Sharks", "#006d75", "#ea7200"),
    "SEA": ("Seattle Kraken", "Kraken", "#001628", "#99d9d9"),
    "STL": ("St. Louis Blues", "Blues", "#002f87", "#fcb514"),
    "TBL": ("Tampa Bay Lightning", "Lightning", "#002868", "#ffffff"),
    "TOR": ("Toronto Maple Leafs", "Maple Leafs", "#00205b", "#ffffff"),
    "UTA": ("Utah Mammoth", "Mammoth", "#1b1b1b", "#6cace3"),
    "VAN": ("Vancouver Canucks", "Canucks", "#00205b", "#00843d"),
    "VGK": ("Vegas Golden Knights", "Golden Knights", "#333f42", "#b4975a"),
    "WSH": ("Washington Capitals", "Capitals", "#041e42", "#c8102e"),
    "WPG": ("Winnipeg Jets", "Jets", "#041e42", "#ac162c"),
    # no longer playing
    "ARI": ("Arizona Coyotes", "Coyotes", None, None),
    "MWN": ("Montreal Wanderers", "Wanderers", None, None),
    "SEN": ("Ottawa Senators (1917)", "Senators", None, None),
    "HAM": ("Hamilton Tigers", "Tigers", None, None),
    "MMR": ("Montreal Maroons", "Maroons", None, None),
    "NYA": ("New York Americans", "Americans", None, None),
    "PIR": ("Pittsburgh Pirates", "Pirates", None, None),
    "CLE": ("Cleveland Barons", "Barons", None, None),
}
DEFUNCT_COLORS = ("#5b5140", "#cfc4ad")

_ERA = {}  # (franchise, season) -> name that season

# Renames the stats API hides behind one team id, so games.csv can't tell the eras apart:
# (franchise, first season, last season, name in those seasons). Seasons are start years.
RENAMES = [
    ("ANA", 1993, 2005, "Mighty Ducks of Anaheim"),   # Anaheim Ducks from 2006-07
    ("CHI", 1926, 1985, "Chicago Black Hawks"),       # one word from 1986-87
]


def _load_eras():
    if _ERA:
        return
    path = os.path.join(DATA_DIR, "games.csv")
    if not os.path.exists(path):
        return
    for x in read_games_csv(path):
        s = int(x["season"])
        for side in ("home", "away"):
            tid = int(x[side])
            if tid in IDS:
                code, name = IDS[tid]
                _ERA[(code, s)] = name


def team_name(code, season=None):
    if season is not None:
        s = int(season)
        for c, first, last, name in RENAMES:
            if c == code and first <= s <= last:
                return name
        _load_eras()
        n = _ERA.get((code, s))
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
        h, a = int(x["home"]), int(x["away"])
        if h not in IDS or a not in IDS:
            skipped += 1
            continue
        games.append({
            "id": int(x["id"]), "date": x["date"], "season": int(x["season"]), "week": None,
            "season_type": x["season_type"], "home": IDS[h][0], "away": IDS[a][0],
            "home_points": int(x["home_points"]), "away_points": int(x["away_points"]),
            "neutral": x["neutral"] == "1", "note": x.get("note") or "",
        })
    if skipped:
        print(f"[nhl] skipped {skipped} games against non-NHL clubs")
    upcoming = []
    for u in read_upcoming(os.path.join(DATA_DIR, "upcoming.json")):
        h, a = int(u["home"]), int(u["away"])
        if h in IDS and a in IDS:
            upcoming.append({"id": u["id"], "date": u["date"], "season": u["season"],
                             "season_type": u["season_type"], "home": IDS[h][0], "away": IDS[a][0],
                             "neutral": False, "kickoff": u.get("start_et")})
    games.sort(key=lambda g: (g["date"], g["season_type"] != "regular", g["id"]))
    return games, upcoming


def rules_note(first_game, name):
    return ("<p><b>NHL.</b> The belt starts with the league's first game: the Montreal Canadiens beat the "
            "Ottawa Senators 7–4 on December 19, 1917 (the first of that night's two games). Overtime and "
            "shootout wins count as wins, since that's the result the NHL puts in the standings; ties, "
            "possible until 2004–05, are successful defenses. Only games between two NHL clubs count, so "
            "the Stanley Cup Finals against Pacific Coast and Western league champions (1918–26) don't. "
            "Franchises follow the NHL's own records: the Toronto Arenas, St. Patricks and Maple Leafs are "
            "one franchise, and the Utah Mammoth are their own franchise, not the Coyotes.</p>")


SOURCES = "NHL results come from the NHL's own statistics API, every regular-season and playoff game since 1917."

LEAGUE = {
    "key": KEY, "name": NAME, "long_name": LONG_NAME, "first_season": FIRST_SEASON,
    "tie_rule": TIE_RULE, "sport": "Ice hockey", "load_games": load_games, "recent_teams": recent_teams,
    "team_name": team_name, "team_colors": team_colors, "short_name": short_name,
    "season_status": season_status, "season_label": season_label, "live": True,
    "gap_days": 800,  # the 2004-05 lockout wiped out a whole season
    "rules_note": rules_note, "sources": SOURCES, "time_word": "Puck drop",
    "alt_starts": [{"season": 1967, "label": "since the 1967 expansion", "why": "The league doubled from six teams to twelve for 1967–68; this belt starts with that season's first game."},
                   {"season": 1942, "label": "since the Original Six era began", "why": "From 1942–43 the NHL was the six-team league fans remember; this belt starts with that season's opener."}],
}
