"""
NFL adapter for the Belt Holders engine.

Everything league-specific lives here: where the games come from, how the
raw rows become the engine's game schema, which teams count, and how each
franchise is named and colored. build_lineages.py and build_site.py never
look inside a league -- they only use the LEAGUE dict and the functions
below, so adding the NBA/NHL/MLB later means adding one more file like
this one.

Data sources (both plain CSVs on raw.githubusercontent.com, no API key):

  * 1920-2020: FiveThirtyEight's nfl-elo-game repo, data/nfl_games.csv --
    every NFL (plus AFL and AAFC) game since 1920, franchise-consistent
    team codes. Frozen; it stopped updating after the 2020 season.
  * 2021-present: nflverse/nfldata data/games.csv -- schedule + results,
    refreshed daily during the season, with kickoff times and spreads for
    upcoming games.

Rules (documented on the site's /rules/ page):

  * The belt starts with the league's first game on record (Sept 26, 1920:
    Rock Island Independents 48, St. Paul Ideals 0 -- St. Paul was not an
    APFA member, so the first league game is used instead; see
    APFA_1920_MEMBERS).
  * A win over the holder moves the belt, regular season or playoffs.
  * A tie is a successful defense.
  * The belt follows a franchise through relocations and renames.
  * A holder whose franchise folds or goes dark: the shared engine's
    vacancy rule -- the belt reverts to the most recent earlier holder
    that is still playing (the same rule the College Football Belt uses).
"""

import csv
import io
import os
import urllib.request
from datetime import date

KEY = "nfl"
NAME = "NFL"
LONG_NAME = "The NFL Belt"
FIRST_SEASON = 1920
TIE_RULE = "holder"
DATA_DIR = os.path.join("data", "nfl")

URL_538 = "https://raw.githubusercontent.com/fivethirtyeight/nfl-elo-game/master/data/nfl_games.csv"
URL_NFLVERSE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
LAST_538_SEASON = 2020

# nflverse uses the CURRENT city code; 538 uses one code per franchise.
NFLVERSE_TO_FRANCHISE = {"LA": "LAR", "STL": "LAR", "LV": "OAK", "SD": "LAC", "WAS": "WSH"}

# The 14 clubs that played the 1920 APFA season. 538's 1920 file also
# carries exhibition games against independent clubs (Wheeling, St. Paul,
# ...); a belt game needs two league members.
APFA_1920_MEMBERS = {"AKR", "BFF", "CBD", "ARI", "CHT", "CTI", "COL", "DAY",
                     "CHI", "DHR", "HAM", "MUN", "RCH", "RII"}

# ---------------------------------------------------------------- teams --
# (name, primary, secondary). Active franchises use today's name; the
# era-specific name comes from era_name() below.
TEAMS = {
    "ARI": ("Arizona Cardinals", "#97233f", "#ffb612"),
    "ATL": ("Atlanta Falcons", "#a71930", "#000000"),
    "BAL": ("Baltimore Ravens", "#241773", "#9e7c0c"),
    "BUF": ("Buffalo Bills", "#00338d", "#c60c30"),
    "CAR": ("Carolina Panthers", "#0085ca", "#101820"),
    "CHI": ("Chicago Bears", "#0b162a", "#c83803"),
    "CIN": ("Cincinnati Bengals", "#fb4f14", "#000000"),
    "CLE": ("Cleveland Browns", "#311d00", "#ff3c00"),
    "DAL": ("Dallas Cowboys", "#003594", "#869397"),
    "DEN": ("Denver Broncos", "#fb4f14", "#002244"),
    "DET": ("Detroit Lions", "#0076b6", "#b0b7bc"),
    "GB": ("Green Bay Packers", "#203731", "#ffb612"),
    "HOU": ("Houston Texans", "#03202f", "#a71930"),
    "IND": ("Indianapolis Colts", "#002c5f", "#a2aaad"),
    "JAX": ("Jacksonville Jaguars", "#006778", "#d7a22a"),
    "KC": ("Kansas City Chiefs", "#e31837", "#ffb81c"),
    "LAC": ("Los Angeles Chargers", "#0080c6", "#ffc20e"),
    "LAR": ("Los Angeles Rams", "#003594", "#ffa300"),
    "MIA": ("Miami Dolphins", "#008e97", "#fc4c02"),
    "MIN": ("Minnesota Vikings", "#4f2683", "#ffc62f"),
    "NE": ("New England Patriots", "#002244", "#c60c30"),
    "NO": ("New Orleans Saints", "#9a7d4e", "#101820"),
    "NYG": ("New York Giants", "#0b2265", "#a71930"),
    "NYJ": ("New York Jets", "#125740", "#ffffff"),
    "OAK": ("Las Vegas Raiders", "#000000", "#a5acaf"),
    "PHI": ("Philadelphia Eagles", "#004c54", "#a5acaf"),
    "PIT": ("Pittsburgh Steelers", "#101820", "#ffb612"),
    "SEA": ("Seattle Seahawks", "#002244", "#69be28"),
    "SF": ("San Francisco 49ers", "#aa0000", "#b3995d"),
    "TB": ("Tampa Bay Buccaneers", "#d50a0a", "#34302b"),
    "TEN": ("Tennessee Titans", "#0c2340", "#4b92db"),
    "WSH": ("Washington Commanders", "#5a1414", "#ffb612"),
    # Defunct franchises (NFL, AAFC, early APFA)
    "AKR": ("Akron Pros", None, None), "BFF": ("Buffalo All-Americans", None, None),
    "CBD": ("Canton Bulldogs", None, None), "CHT": ("Chicago Tigers", None, None),
    "CTI": ("Cleveland Tigers", None, None), "COL": ("Columbus Panhandles", None, None),
    "DAY": ("Dayton Triangles", None, None), "DHR": ("Detroit Heralds", None, None),
    "HAM": ("Hammond Pros", None, None), "MUN": ("Muncie Flyers", None, None),
    "RCH": ("Rochester Jeffersons", None, None), "RII": ("Rock Island Independents", None, None),
    "CCL": ("Cincinnati Celts", None, None), "ECG": ("Evansville Crimson Giants", None, None),
    "LOU": ("Louisville Brecks", None, None), "MNN": ("Minneapolis Marines", None, None),
    "DTI": ("Detroit Tigers", None, None), "NG1": ("New York Brickley Giants", None, None),
    "TON": ("Tonawanda Kardex", None, None), "SEN": ("Washington Senators", None, None),
    "RAC": ("Racine Legion", None, None), "TOL": ("Toledo Maroons", None, None),
    "MIL": ("Milwaukee Badgers", None, None), "OOR": ("Oorang Indians", None, None),
    "DUL": ("Duluth Eskimos", None, None), "SLA": ("St. Louis All-Stars", None, None),
    "CIB": ("Cleveland Bulldogs", None, None), "FYJ": ("Frankford Yellow Jackets", None, None),
    "KEN": ("Kenosha Maroons", None, None), "KCB": ("Kansas City Cowboys", None, None),
    "DPN": ("Detroit Panthers", None, None), "PTB": ("Pottsville Maroons", None, None),
    "PRV": ("Providence Steam Roller", None, None), "LAB": ("Los Angeles Buccaneers", None, None),
    "BRL": ("Brooklyn Lions", None, None), "HRT": ("Hartford Blues", None, None),
    "NYA": ("New York Yankees", None, None), "DWL": ("Detroit Wolverines", None, None),
    "TOR": ("Orange Tornadoes", None, None), "SIS": ("Staten Island Stapletons", None, None),
    "BKN": ("Brooklyn Dodgers", None, None), "CLI": ("Cleveland Indians", None, None),
    "RED": ("Cincinnati Reds", None, None), "GUN": ("St. Louis Gunners", None, None),
    "STG": ("Phil-Pitt Steagles", None, None), "CRP": ("Card-Pitt", None, None),
    "BYK": ("Boston Yanks", None, None), "MSA": ("Miami Seahawks", None, None),
    "BBA": ("Buffalo Bills (AAFC)", None, None), "BDA": ("Brooklyn Dodgers (AAFC)", None, None),
    "NAA": ("New York Yankees (AAFC)", None, None), "CRA": ("Chicago Rockets", None, None),
    "LDA": ("Los Angeles Dons", None, None), "BCL": ("Baltimore Colts (1947–50)", None, None),
    "NYY": ("New York Yanks", None, None), "DTX": ("Dallas Texans", None, None),
}
DEFUNCT_COLORS = ("#5b5140", "#cfc4ad")

# (last season, name) breakpoints for franchises that moved or renamed.
_ERAS = {
    "ARI": [(1959, "Chicago Cardinals"), (1987, "St. Louis Cardinals"), (1993, "Phoenix Cardinals")],
    "CHI": [(1920, "Decatur Staleys"), (1921, "Chicago Staleys")],
    "DET": [(1933, "Portsmouth Spartans")],
    "WSH": [(1932, "Boston Braves"), (1936, "Boston Redskins"), (2019, "Washington Redskins"),
            (2021, "Washington Football Team")],
    "PIT": [(1939, "Pittsburgh Pirates")],
    "LAR": [(1945, "Cleveland Rams"), (1994, "Los Angeles Rams"), (2015, "St. Louis Rams")],
    "IND": [(1983, "Baltimore Colts")],
    "LAC": [(1960, "Los Angeles Chargers"), (2016, "San Diego Chargers")],
    "OAK": [(1981, "Oakland Raiders"), (1994, "Los Angeles Raiders"), (2019, "Oakland Raiders")],
    "TEN": [(1996, "Houston Oilers"), (1998, "Tennessee Oilers")],
    "KC": [(1962, "Dallas Texans")],
    "NE": [(1970, "Boston Patriots")],
    "NYJ": [(1962, "New York Titans")],
}


def team_name(code, season=None):
    """The franchise's name in `season` (today's name when season is None)."""
    if season is not None:
        for last, name in _ERAS.get(code, []):
            if season <= last:
                return name
    return TEAMS.get(code, (code, None, None))[0]


def team_colors(code):
    _, p, s = TEAMS.get(code, (code, None, None))
    return (p, s) if p else DEFUNCT_COLORS


def short_name(code):
    """'Jaguars' from 'Jacksonville Jaguars' -- nickname for tight spaces."""
    name = team_name(code)
    if code in ("WSH",):
        return "Commanders"
    return name.split()[-1] if " " in name else name


def is_active(code):
    return TEAMS.get(code, (None, None, None))[1] is not None


# ---------------------------------------------------------------- games --

def _fetch(url, cache_path, refresh=True):
    if refresh:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                text = r.read().decode("utf-8")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(text)
            return text
        except Exception as e:  # network trouble: fall back to the last good copy
            print(f"[nfl] fetch failed for {url}: {e} -- using cached copy")
    with open(cache_path, encoding="utf-8") as f:
        return f.read()


def load_games(refresh=True):
    """Every completed game in the engine's schema, oldest first, plus the
    upcoming (unplayed) schedule for the current season."""
    t538 = _fetch(URL_538, os.path.join(DATA_DIR, "cache_538.csv"), refresh)
    tnv = _fetch(URL_NFLVERSE, os.path.join(DATA_DIR, "cache_nflverse.csv"), refresh)
    games, upcoming = [], []
    for i, x in enumerate(csv.DictReader(io.StringIO(t538))):
        season = int(x["season"])
        if season > LAST_538_SEASON:
            continue
        home, away = x["team1"], x["team2"]
        if season == 1920 and not (home in APFA_1920_MEMBERS and away in APFA_1920_MEMBERS):
            continue
        games.append({
            "id": f"538-{i}", "date": x["date"], "season": season, "week": None,
            "season_type": "postseason" if x["playoff"] not in ("", "0") else "regular",
            "home": home, "away": away,
            "home_points": int(x["score1"]), "away_points": int(x["score2"]),
            "neutral": x["neutral"] == "1",
        })
    for x in csv.DictReader(io.StringIO(tnv)):
        season = int(x["season"])
        if season <= LAST_538_SEASON:
            continue
        home = NFLVERSE_TO_FRANCHISE.get(x["home_team"], x["home_team"])
        away = NFLVERSE_TO_FRANCHISE.get(x["away_team"], x["away_team"])
        row = {
            "id": x["game_id"], "date": x["gameday"], "season": season,
            "week": int(x["week"]) if x["week"] else None,
            "season_type": "regular" if x["game_type"] == "REG" else "postseason",
            "home": home, "away": away, "neutral": x["location"] == "Neutral",
            "kickoff": x.get("gametime") or None,  # ET, 24h
            "spread": float(x["spread_line"]) if x.get("spread_line") else None,  # + = home favored
            "stadium": x.get("stadium") or None,
        }
        if x["home_score"] == "" or x["away_score"] == "":
            upcoming.append(row)
            continue
        row["home_points"], row["away_points"] = int(x["home_score"]), int(x["away_score"])
        games.append(row)
    games.sort(key=lambda g: (g["date"], g["season_type"] != "regular", str(g["id"])))
    upcoming.sort(key=lambda g: (g["date"], g.get("kickoff") or ""))
    return games, upcoming


def recent_teams(games, today=None):
    """Franchises that have played in the current or previous season --
    the roster a vacated belt may pass to at the end of the data."""
    latest = max(g["season"] for g in games)
    return {t for g in games if g["season"] >= latest - 1 for t in (g["home"], g["away"])}


def season_status(today=None, upcoming=None):
    """'In season' / 'Offseason' label for the network board."""
    today = today or date.today().isoformat()
    if upcoming:
        days_out = (date.fromisoformat(upcoming[0]["date"]) - date.fromisoformat(today)).days
        return "In season" if days_out <= 14 else "Offseason"
    return "Offseason"


LEAGUE = {
    "key": KEY, "name": NAME, "long_name": LONG_NAME, "first_season": FIRST_SEASON,
    "tie_rule": TIE_RULE, "sport": "American football", "load_games": load_games, "recent_teams": recent_teams,
    "team_name": team_name, "team_colors": team_colors, "short_name": short_name,
    "season_status": season_status, "live": True,
    # 7.3 (audit #2): the same belt started at an era boundary
    "alt_starts": [{"season": 1970, "label": "since the 1970 merger", "why": "The NFL and AFL merged into one league for the 1970 season; this belt starts with that season's first game."},
                   {"season": 1966, "label": "since the first Super Bowl season", "why": "The first Super Bowl season, 1966: the belt starts with the first game of the year that ended in Super Bowl I."}],
}
