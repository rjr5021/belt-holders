"""
Adapters for the leagues added in October 2026. Each is built by make() from
a small table: the league's game files (written by new_leagues.py), how raw
team names/ids map to one code per franchise, display names and colors.

Soccer rules (shown on /rules/): a draw is a successful defense; in a knockout
game decided on penalties the shootout winner takes (or keeps) the belt. A
holder that drops out of the league (relegation) vacates the belt, which goes
back to the most recent earlier holder still in the league -- the same rule
the conference belts use.
"""

import json
import os
import re

from league_common import read_games_csv, read_upcoming, recent_teams, season_label, season_status

DEFUNCT = ("#5b5140", "#cfc4ad")


def _auto_short(name):
    s = re.sub(r"^(AFC|AC|AS|ACF|SSC|US|FC|SC|RC|CA|CD|SBV|PEC|NEC|OGC|VfB|VfL|TSG|FSV|SV|1\.)\s+", "", name)
    s = re.sub(r"\s+(FC|AFC|CF|SC|UD|Calcio|CFC|AC|HSC|BC)$", "", s)
    return s.strip() or name


def make(key, name, long_name, sport, first_season, *, teams=None, aliases=None, display=None, tie_rule="holder",
         gap_days=200, label=season_label, rules="", sources="", time_word="Kickoff", unit="clubs",
         post_word="postseason", champions_note=None, names_file=None, era=None, keep=None):
    teams = teams or {}          # code -> (primary, secondary[, short]), or a function of the code
    aliases = aliases or {}      # raw team value in the files -> code
    display = display or {}      # code -> display name
    data_dir = os.path.join("data", key)
    _names = {}

    def code(raw, season=None):
        raw = str(raw)
        if callable(aliases):
            return aliases(raw, season)
        return aliases.get(raw, raw)

    def _load_names():
        if names_file and not _names:
            p = os.path.join(data_dir, names_file)
            if os.path.exists(p):
                with open(p) as f:
                    _names.update(json.load(f))

    def load_games(refresh=True):
        rows = read_games_csv(os.path.join(data_dir, "games.csv"))
        games = []
        for x in rows:
            h, a = code(x["home"], int(x["season"])), code(x["away"], int(x["season"]))
            if keep and not (keep(h, x) and keep(a, x)):
                continue
            if x.get("home_name"):
                _names.setdefault(h, x["home_name"])
            if x.get("away_name"):
                _names.setdefault(a, x["away_name"])
            games.append({"id": x["id"], "date": x["date"], "season": int(x["season"]), "week": None,
                          "season_type": x["season_type"] or "regular", "home": h, "away": a,
                          "home_points": int(x["home_points"]), "away_points": int(x["away_points"]),
                          "neutral": x.get("neutral") == "1", "note": x.get("note") or ""})
        upcoming = []
        for u in read_upcoming(os.path.join(data_dir, "upcoming.json")):
            us = int(u.get("season") or u["date"][:4])
            h, a = code(u["home"], us), code(u["away"], us)
            if keep and not (keep(h, u) and keep(a, u)):
                continue
            upcoming.append({"id": u["id"], "date": u["date"], "season": int(u.get("season") or u["date"][:4]),
                             "season_type": u.get("season_type") or "regular", "home": h, "away": a,
                             "neutral": u.get("neutral") == "1", "kickoff": u.get("start_et")})
        games.sort(key=lambda g: (g["date"], g["season_type"] != "regular", str(g["id"])))
        return games, upcoming

    def team_name(c, season=None):
        if era and season is not None:
            n = era(c, season)
            if n:
                return n
        if c in display:
            return display[c]
        _load_names()
        return _names.get(c, c)

    def short_name(c):
        t = teams(c) if callable(teams) else teams.get(c)
        if t and len(t) > 2 and t[2]:
            return t[2]
        return _auto_short(team_name(c))

    def team_colors(c):
        t = teams(c) if callable(teams) else teams.get(c)
        return (t[0], t[1]) if t and t[0] else DEFUNCT

    lg = {
        "key": key, "name": name, "long_name": long_name, "first_season": first_season, "tie_rule": tie_rule,
        "sport": sport, "load_games": load_games, "recent_teams": recent_teams, "team_name": team_name,
        "team_colors": team_colors, "short_name": short_name, "season_status": season_status,
        "season_label": label, "live": True, "gap_days": gap_days, "rules_note": lambda *a, **k: rules,
        "sources": sources, "time_word": time_word, "unit": unit, "post_word": post_word, "post_tag": post_word,
        "unit_one": {"clubs": "club", "nations": "nation", "teams": "team"}.get(unit, unit.rstrip("s")),
        # club and national-team names read as singular ("Bayern Munich defends"); nicknames as plural ("the Aces defend")
        "singular": unit in ("clubs", "nations"),
    }
    if champions_note:
        lg["champions_note"] = champions_note
    return lg


SOCCER_RULES = ("A draw is a successful defense. In a knockout game settled on penalties, the shootout winner takes "
                "(or keeps) the belt. A holder that drops out of the league, by relegation, vacates the belt, which "
                "goes back to the most recent earlier holder still in the league.")
ESD = ('<a href="https://github.com/jalapic/engsoccerdata">engsoccerdata</a> (James Curley, GPL)')
OPENF = '<a href="https://github.com/openfootball/football.json">openfootball</a> (public domain)'

# ---------------------------------------------------------------- England
EPL = make("epl", "Premier League", "The English Football Belt", "Soccer", 1888, teams={
    "Arsenal": ("#ef0107", "#063672"), "Aston Villa": ("#670e36", "#95bfe5"), "AFC Bournemouth": ("#da291c", "#111111", "Bournemouth"),
    "Brentford": ("#e30613", "#140e0c"), "Brighton & Hove Albion": ("#0057b8", "#ffffff", "Brighton"),
    "Chelsea": ("#034694", "#dba111"), "Coventry City": ("#59cbe8", "#1d1d1b", "Coventry"),
    "Crystal Palace": ("#1b458f", "#c4122e"), "Everton": ("#003399", "#ffffff"), "Fulham": ("#111111", "#cc0000"),
    "Hull City": ("#f5a12d", "#111111", "Hull"), "Ipswich Town": ("#0044a9", "#ffffff", "Ipswich"),
    "Leeds United": ("#1d428a", "#ffcd00", "Leeds"), "Liverpool": ("#c8102e", "#00b2a9"),
    "Manchester City": ("#6cabdd", "#1c2c5b", "Man City"), "Manchester United": ("#da291c", "#fbe122", "Man United"),
    "Newcastle United": ("#241f20", "#ffffff", "Newcastle"), "Nottingham Forest": ("#dd0000", "#ffffff", "Forest"),
    "Sunderland": ("#eb172b", "#111111"), "Tottenham Hotspur": ("#132257", "#ffffff", "Tottenham"),
    "West Ham United": ("#7a263a", "#1bb1e7", "West Ham"), "Wolverhampton Wanderers": ("#fdb913", "#231f20", "Wolves"),
    "Leicester City": ("#003090", "#fdbe11", "Leicester"), "Southampton": ("#d71920", "#130c0e"),
    "Burnley": ("#6c1d45", "#99d6ea"), "Sheffield United": ("#ee2737", "#111111", "Sheffield Utd"),
    "Blackburn Rovers": ("#009ee0", "#ffffff", "Blackburn"), "Sheffield Wednesday": ("#0e00f7", "#ffffff", "Sheffield Wed"),
    "Preston North End": ("#ffffff", "#0b2b55", "Preston"), "Huddersfield Town": ("#0e63ad", "#ffffff", "Huddersfield"),
    "Derby County": ("#ffffff", "#111111", "Derby"), "West Bromwich Albion": ("#122f67", "#ffffff", "West Brom"),
    "Bolton Wanderers": ("#263c7e", "#ffffff", "Bolton"), "Portsmouth": ("#001489", "#ffffff"),
    "Middlesbrough": ("#e11b22", "#ffffff"), "Norwich City": ("#00a650", "#fff200", "Norwich"),
    "Stoke City": ("#e03a3e", "#1b449c", "Stoke"), "Watford": ("#fbee23", "#ed2127"),
}, rules=f"<p><b>Premier League.</b> The belt starts with the first Football League game in 1888 and follows England's top flight: the First Division until 1992, the Premier League since. {SOCCER_RULES}</p>",
    sources=f"English top-flight results since 1888 come from {ESD}, and from {OPENF} since 2025–26.")

# ------------------------------------------------------------------ Spain
LALIGA = make("laliga", "La Liga", "The La Liga Belt", "Soccer", 1928, teams={
    "Real Madrid": ("#febe10", "#00529f"), "FC Barcelona": ("#a50044", "#004d98", "Barcelona"),
    "Atletico Madrid": ("#cb3524", "#262f61", "Atlético"), "Athletic Bilbao": ("#ee2523", "#ffffff", "Athletic"),
    "Real Sociedad": ("#0067b1", "#ffffff"), "Real Betis": ("#00954c", "#ffffff", "Betis"), "Sevilla FC": ("#d4021d", "#ffffff", "Sevilla"),
    "Valencia CF": ("#ee3524", "#111111", "Valencia"), "Villarreal CF": ("#ffe667", "#005187", "Villarreal"),
    "Celta Vigo": ("#8ac3ee", "#e5254e", "Celta"), "CA Osasuna": ("#d91a21", "#0a346f", "Osasuna"),
    "CD Alaves": ("#0761af", "#ffffff", "Alavés"), "Getafe CF": ("#005999", "#ffffff", "Getafe"),
    "Rayo Vallecano": ("#e53027", "#ffffff", "Rayo"), "Espanyol Barcelona": ("#007fc8", "#ffffff", "Espanyol"),
    "Elche CF": ("#05642c", "#ffffff", "Elche"), "Levante UD": ("#004d98", "#b4053f", "Levante"),
    "Deportivo La Coruna": ("#1b4eb0", "#ffffff", "Deportivo"), "Malaga CF": ("#0f5bad", "#ffffff", "Málaga"),
    "Racing Santander": ("#008f47", "#ffffff", "Racing"), "Real Oviedo": ("#0053a0", "#ffffff", "Oviedo"),
    "Girona FC": ("#cd2534", "#ffffff", "Girona"), "RCD Mallorca": ("#e20613", "#111111", "Mallorca"),
    "UD Las Palmas": ("#fcd200", "#0053a0", "Las Palmas"), "Real Valladolid": ("#921b88", "#ffffff", "Valladolid"),
    "Real Zaragoza": ("#0063a5", "#ffffff", "Zaragoza"),
}, display={"Deportivo La Coruna": "Deportivo La Coruña", "Malaga CF": "Málaga CF", "CD Malaga": "CD Málaga",
            "Atletico Madrid": "Atlético Madrid", "CD Alaves": "Deportivo Alavés", "Espanyol Barcelona": "Espanyol"},
    rules=f"<p><b>La Liga.</b> The belt starts with Spain's first league game in February 1929. {SOCCER_RULES}</p>",
    sources=f"La Liga results since 1929 come from {ESD}, and from {OPENF} since 2025–26.")

# ------------------------------------------------------------------ Italy
SERIEA = make("seriea", "Serie A", "The Serie A Belt", "Soccer", 1929, teams={
    "Juventus": ("#111111", "#ffffff"), "Inter": ("#0068a8", "#111111"), "AC Milan": ("#fb090b", "#111111", "Milan"),
    "SSC Napoli": ("#12a0d7", "#ffffff", "Napoli"), "AS Roma": ("#8e1f2f", "#f0bc42", "Roma"), "Lazio Roma": ("#87d8f7", "#ffffff", "Lazio"),
    "Atalanta": ("#1e71b8", "#111111"), "ACF Fiorentina": ("#482e92", "#ffffff", "Fiorentina"), "Bologna FC": ("#1a2f48", "#a21c26", "Bologna"),
    "Torino FC": ("#8a1e03", "#ffffff", "Torino"), "Genoa CFC": ("#ad1919", "#0b2544", "Genoa"), "Udinese Calcio": ("#111111", "#ffffff", "Udinese"),
    "Cagliari Calcio": ("#a50044", "#004d98", "Cagliari"), "Como Calcio": ("#003f7d", "#ffffff", "Como"), "Parma FC": ("#fcd116", "#0055a4", "Parma"),
    "US Lecce": ("#ffd600", "#e30613", "Lecce"), "Sassuolo Calcio": ("#00a752", "#111111", "Sassuolo"), "AC Monza": ("#e2001a", "#ffffff", "Monza"),
    "AC Venezia": ("#ff6600", "#00754a", "Venezia"), "Frosinone Calcio": ("#ffe100", "#0055a4", "Frosinone"),
    "US Cremonese": ("#e2001a", "#9b9b9b", "Cremonese"), "Pisa SC": ("#111111", "#0065b3", "Pisa"), "Hellas Verona": ("#002a5c", "#ffd700", "Verona"),
    "Empoli FC": ("#00579c", "#ffffff", "Empoli"), "Sampdoria": ("#1b5497", "#ffffff"),
}, display={"Lazio Roma": "Lazio", "Inter": "Inter Milan"},
    rules=f"<p><b>Serie A.</b> The belt starts with the first round of the single-table Serie A in October 1929. {SOCCER_RULES}</p>",
    sources=f"Serie A results since 1929 come from {ESD}, and from {OPENF} since 2025–26.")

# ---------------------------------------------------------------- Germany
BUNDESLIGA = make("bundesliga", "Bundesliga", "The Bundesliga Belt", "Soccer", 1963, teams={
    "Bayern Munchen": ("#dc052d", "#0066b2", "Bayern"), "Borussia Dortmund": ("#fde100", "#111111", "Dortmund"),
    "Bayer Leverkusen": ("#e32221", "#111111", "Leverkusen"), "RasenBallsport Leipzig": ("#dd0741", "#001f47", "Leipzig"),
    "Eintracht Frankfurt": ("#e1000f", "#111111", "Frankfurt"), "VfB Stuttgart": ("#e32219", "#ffffff", "Stuttgart"),
    "SC Freiburg": ("#111111", "#e2001a", "Freiburg"), "Bor. Monchengladbach": ("#111111", "#00a650", "Gladbach"),
    "Werder Bremen": ("#1d9053", "#ffffff", "Bremen"), "VfL Wolfsburg": ("#65b32e", "#ffffff", "Wolfsburg"),
    "1899 Hoffenheim": ("#1c63b7", "#ffffff", "Hoffenheim"), "FC Augsburg": ("#ba3733", "#46714d", "Augsburg"),
    "1. FSV Mainz 05": ("#c3141e", "#ffffff", "Mainz"), "1. FC Union Berlin": ("#eb1923", "#ffec00", "Union Berlin"),
    "1. FC Koln": ("#ed1c24", "#ffffff", "Köln"), "FC Schalke 04": ("#004d9d", "#ffffff", "Schalke"),
    "Hamburger SV": ("#0a3f86", "#ffffff", "Hamburg"), "SC Paderborn 07": ("#005ca9", "#111111", "Paderborn"),
    "SV Elversberg": ("#111111", "#ffffff", "Elversberg"), "VfL Bochum": ("#005ca9", "#ffffff", "Bochum"),
    "1. FC Heidenheim": ("#e30613", "#003a79", "Heidenheim"), "Hertha BSC": ("#005ca9", "#ffffff", "Hertha"),
}, display={"Bayern Munchen": "Bayern Munich", "1. FC Koln": "1. FC Köln", "Bor. Monchengladbach": "Borussia Mönchengladbach",
            "RasenBallsport Leipzig": "RB Leipzig", "1899 Hoffenheim": "TSG Hoffenheim", "Borussia Monchengladbach": "Borussia Mönchengladbach"},
    rules=f"<p><b>Bundesliga.</b> The belt starts with the Bundesliga's first matchday in August 1963. {SOCCER_RULES}</p>",
    sources=f"Bundesliga results since 1963 come from {ESD}, and from {OPENF} since 2025–26.")

# ----------------------------------------------------------------- France
LIGUE1 = make("ligue1", "Ligue 1", "The Ligue 1 Belt", "Soccer", 1938, teams={
    "Paris Saint-Germain": ("#004170", "#da291c", "PSG"), "Olympique Marseille": ("#2faee0", "#ffffff", "Marseille"),
    "Olympique Lyon": ("#1b3a8c", "#da0812", "Lyon"), "AS Monaco": ("#e51b22", "#ffffff", "Monaco"), "Lille OSC": ("#e01e13", "#20325f", "Lille"),
    "OGC Nice": ("#c70f17", "#111111", "Nice"), "RC Lens": ("#fae100", "#e30613", "Lens"), "Stade Rennes": ("#e13327", "#111111", "Rennes"),
    "RC Strasbourg": ("#009fe3", "#ffffff", "Strasbourg"), "Stade Brest": ("#e30613", "#ffffff", "Brest"), "Toulouse FC": ("#5b3c8e", "#ffffff", "Toulouse"),
    "AJ Auxerre": ("#1b4b9a", "#ffffff", "Auxerre"), "Angers SCO": ("#111111", "#ffffff", "Angers"), "Le Havre AC": ("#3e8cc9", "#0a2240", "Le Havre"),
    "FC Lorient": ("#f58220", "#111111", "Lorient"), "FC Metz": ("#8e1b3a", "#ffffff", "Metz"), "Paris FC": ("#1d2f5c", "#ffffff"),
    "ESTAC Troyes": ("#0076c0", "#ffffff", "Troyes"), "Le Mans UC 72": ("#e30613", "#fcd116", "Le Mans"), "FC Nantes": ("#fcd405", "#00843d", "Nantes"),
    "AS Saint-Etienne": ("#00a650", "#ffffff", "Saint-Étienne"), "Girondins Bordeaux": ("#1c2c5b", "#ffffff", "Bordeaux"),
    "Montpellier HSC": ("#f36f21", "#1b3a8c", "Montpellier"), "Stade Reims": ("#e3001b", "#ffffff", "Reims"),
}, display={"AS Saint-Etienne": "AS Saint-Étienne", "Le Mans UC 72": "Le Mans"},
    rules=f"<p><b>Ligue 1.</b> The belt starts with the 1937–38 French first division, the first season with a full, dated fixture list in the archive (earlier seasons' games carry placeholder dates, so their order is unknown). {SOCCER_RULES}</p>",
    sources=f"French top-flight results since 1937–38 come from {ESD}, and from {OPENF} since 2025–26.")

# ------------------------------------------------------------ Netherlands
EREDIVISIE = make("eredivisie", "Eredivisie", "The Eredivisie Belt", "Soccer", 1956, teams={
    "AFC Ajax": ("#d2122e", "#ffffff", "Ajax"), "PSV Eindhoven": ("#ed1c24", "#ffffff", "PSV"), "Feyenoord": ("#ee1c25", "#111111"),
    "AZ Alkmaar": ("#e30613", "#ffffff", "AZ"), "FC Twente": ("#e30613", "#ffffff", "Twente"), "FC Utrecht": ("#e30613", "#ffffff", "Utrecht"),
    "sc Heerenveen": ("#005baa", "#ffffff", "Heerenveen"), "FC Groningen": ("#00a650", "#ffffff", "Groningen"),
    "Sparta Rotterdam": ("#e30613", "#ffffff", "Sparta"), "NEC Nijmegen": ("#d1181f", "#00843d", "NEC"),
    "Go Ahead Eagles": ("#e30613", "#fcd116", "Go Ahead"), "PEC Zwolle": ("#0068b3", "#ffffff", "Zwolle"),
    "Fortuna Sittard": ("#fdd100", "#00843d", "Fortuna"), "Willem II": ("#e30613", "#0061a8"), "SBV Excelsior": ("#e30613", "#111111", "Excelsior"),
    "SC Cambuur": ("#fdd100", "#1a4b9b", "Cambuur"), "Telstar": ("#ffffff", "#e30613"), "ADO Den Haag": ("#fdd100", "#00843d", "ADO"),
    "FC Volendam": ("#f58220", "#111111", "Volendam"), "Heracles Almelo": ("#111111", "#ffffff", "Heracles"),
    "NAC Breda": ("#fdd100", "#111111", "NAC"), "Vitesse": ("#fdd100", "#111111"),
}, rules=f"<p><b>Eredivisie.</b> The belt starts with the Eredivisie's first season, 1956–57. {SOCCER_RULES}</p>",
    sources=f"Eredivisie results since 1956 come from {ESD}, and from {OPENF} since 2025–26.")

# ---------------------------------------------------------- International
INTL_COLORS = {
    "England": ("#ffffff", "#ce1124"), "Scotland": ("#0065bf", "#ffffff"), "Wales": ("#c8102e", "#00ab39"), "Northern Ireland": ("#00843d", "#ffffff"),
    "Republic of Ireland": ("#169b62", "#ffffff"), "France": ("#002395", "#ed2939"), "Germany": ("#111111", "#dd0000"), "Italy": ("#0066b2", "#ffffff"),
    "Spain": ("#c60b1e", "#ffc400"), "Portugal": ("#006600", "#ff0000"), "Netherlands": ("#ff6f00", "#21468b"), "Belgium": ("#e30613", "#111111"),
    "Brazil": ("#ffdf00", "#009c3b"), "Argentina": ("#75aadb", "#ffffff"), "Uruguay": ("#5cbfeb", "#111111"), "Chile": ("#d52b1e", "#0039a6"),
    "Colombia": ("#fcd116", "#003893"), "Mexico": ("#006847", "#ce1126"), "United States": ("#0a3161", "#b31942"), "Canada": ("#d80621", "#ffffff"),
    "Croatia": ("#ff0000", "#ffffff"), "Serbia": ("#c6363c", "#0c4076"), "Hungary": ("#ce2939", "#477050"), "Austria": ("#ed2939", "#ffffff"),
    "Czech Republic": ("#d7141a", "#11457e"), "Poland": ("#dc143c", "#ffffff"), "Sweden": ("#006aa7", "#fecc00"), "Denmark": ("#c60c30", "#ffffff"),
    "Norway": ("#ba0c2f", "#00205b"), "Switzerland": ("#d52b1e", "#ffffff"), "Russia": ("#d52b1e", "#0039a6"), "Ukraine": ("#0057b7", "#ffd700"),
    "Turkey": ("#e30a17", "#ffffff"), "Greece": ("#0d5eaf", "#ffffff"), "Japan": ("#000555", "#bc002d"), "South Korea": ("#cd2e3a", "#0047a0"),
    "Australia": ("#ffcd00", "#00843d"), "Nigeria": ("#008751", "#ffffff"), "Senegal": ("#00853f", "#fdef42"), "Morocco": ("#c1272d", "#006233"),
    "Egypt": ("#ce1126", "#111111"), "Cameroon": ("#007a5e", "#ce1126"), "Ghana": ("#006b3f", "#fcd116"), "Iran": ("#239f40", "#da0000"),
    "Saudi Arabia": ("#006c35", "#ffffff"), "Paraguay": ("#d52b1e", "#0038a8"), "Peru": ("#d91023", "#ffffff"), "Ecuador": ("#ffdd00", "#034ea2"),
    "Scotland ": ("#0065bf", "#ffffff"),
}
INTL = make("intl", "International", "The International Football Belt", "Soccer", 1873, teams=INTL_COLORS, gap_days=1100,
            label=lambda y: str(y), unit="nations", post_word="World Cup",
            champions_note="Here the champion is the World Cup winner, in World Cup years.",
            rules=("<p><b>International.</b> The men's international belt starts with the first decisive international, "
                   "England 4–2 Scotland at the Kennington Oval on March 8, 1873 (the first, in Glasgow in 1872, was a 0–0 draw), and counts every full international between "
                   "national teams that have played World Cup qualifying: friendlies, qualifiers and tournaments alike. "
                   "A draw is a successful defense, and a shootout winner takes (or keeps) the belt. It follows the same "
                   "idea as the Unofficial Football World Championships.</p>"),
            sources=('International results since 1872 come from Mart Jürisoo\'s <a href="https://github.com/martj42/international_results">'
                     'international football results</a> (CC0).'))

# ------------------------------------------------------------------- PWHL
PWHL_IDS = {"1": "BOS", "2": "MIN", "3": "MTL", "4": "NY", "5": "OTT", "6": "TOR", "8": "SEA", "9": "VAN"}
PWHL_TEAMS = {"BOS": ("#154734", "#ffffff", "Boston"), "MIN": ("#2e1a47", "#a77bca", "Minnesota"), "MTL": ("#862633", "#e8dcc4", "Montréal"),
              "NY": ("#00b2a9", "#1e3a5f", "New York"), "OTT": ("#a6192e", "#111111", "Ottawa"), "TOR": ("#307fe2", "#111111", "Toronto"),
              "SEA": ("#0b5563", "#e3b33d", "Seattle"), "VAN": ("#0f4d3a", "#d4b36a", "Vancouver")}
PWHL_NAMES = {"BOS": "Boston Fleet", "MIN": "Minnesota Frost", "MTL": "Montréal Victoire", "NY": "New York Sirens",
              "OTT": "Ottawa Charge", "TOR": "Toronto Sceptres", "SEA": "Seattle Torrent", "VAN": "Vancouver Goldeneyes"}


def _pwhl_era(c, season):
    if season is not None and int(season) < 2024:   # 2024 season (Jan-May 2024) was played under city names
        return {"BOS": "PWHL Boston", "MIN": "PWHL Minnesota", "MTL": "PWHL Montréal", "NY": "PWHL New York",
                "OTT": "PWHL Ottawa", "TOR": "PWHL Toronto"}.get(c)
    return None


PWHL = make("pwhl", "PWHL", "The PWHL Belt", "Ice hockey", 2023, teams=PWHL_TEAMS, aliases=PWHL_IDS,
            display=PWHL_NAMES, era=_pwhl_era, gap_days=330, time_word="Puck drop", unit="teams",
            rules=("<p><b>PWHL.</b> The belt starts with the league's first game, New York at Toronto on January 1, 2024. "
                   "Overtime and shootout wins count as wins.</p>"),
            sources=('PWHL results come from the <a href="https://github.com/sportsdataverse/fastRhockey-pwhl-raw">fastRhockey</a> '
                     'project (sportsdataverse, MIT), which archives the league\'s own game data.'))

# ------------------------------------------------------------------- WNBA
WNBA_NOT_TEAMS = {"ALL", "CLA", "COL", "COOP", "DEL", "EAST", "WEST", "PAR", "STE", "USA", "WIL", "WNBASTARS", "SPO"}
WNBA_ALIASES = {"CONN": "CON", "CT": "CON", "ORL": "CON", "DET": "DAL", "TUL": "DAL", "LAS": "LA", "LOS": "LA",
                "UTA": "LV", "UTH": "LV", "SAS": "LV", "SA": "LV", "NYL": "NY", "PHO": "PHX", "WSH": "WAS"}


def _wnba_code(raw, season):
    if raw == "POR" and season is not None and season <= 2002:
        return "POR1"          # the first Portland Fire, 2000-02 (today's Fire began in 2026)
    return WNBA_ALIASES.get(raw, raw)


WNBA_TEAMS = {"ATL": ("#c8102e", "#418fde", "Dream"), "CHI": ("#418fde", "#ffcd00", "Sky"), "CON": ("#f05023", "#0a2240", "Sun"),
              "DAL": ("#002b5c", "#c4d600", "Wings"), "IND": ("#002d62", "#e03a3e", "Fever"), "LA": ("#552583", "#fdb927", "Sparks"),
              "LV": ("#111111", "#c8102e", "Aces"), "MIN": ("#0c2340", "#78be20", "Lynx"), "NY": ("#6eceb2", "#111111", "Liberty"),
              "PHX": ("#201747", "#e56020", "Mercury"), "SEA": ("#2c5234", "#fbe122", "Storm"), "WAS": ("#0c2340", "#c8102e", "Mystics"),
              "GS": ("#6f2da8", "#111111", "Valkyries"), "TOR": ("#6d2c41", "#d9b99b", "Tempo"), "POR": ("#c8102e", "#111111", "Fire"),
              "CHA": (None, None, "Sting"), "CLE": (None, None, "Rockers"), "HOU": (None, None, "Comets"), "MIA": (None, None, "Sol"),
              "SAC": (None, None, "Monarchs"), "POR1": (None, None, "Fire")}
WNBA_NAMES = {"ATL": "Atlanta Dream", "CHI": "Chicago Sky", "CON": "Connecticut Sun", "DAL": "Dallas Wings", "IND": "Indiana Fever",
              "LA": "Los Angeles Sparks", "LV": "Las Vegas Aces", "MIN": "Minnesota Lynx", "NY": "New York Liberty",
              "PHX": "Phoenix Mercury", "SEA": "Seattle Storm", "WAS": "Washington Mystics", "GS": "Golden State Valkyries",
              "TOR": "Toronto Tempo", "POR": "Portland Fire", "CHA": "Charlotte Sting", "CLE": "Cleveland Rockers",
              "HOU": "Houston Comets", "MIA": "Miami Sol", "SAC": "Sacramento Monarchs", "POR1": "Portland Fire"}


def _wnba_era(c, season):
    s = int(season)
    if c == "CON" and s <= 2002:
        return "Orlando Miracle"
    if c == "DAL":
        return "Detroit Shock" if s <= 2009 else "Tulsa Shock" if s <= 2015 else None
    if c == "LV":
        return "Utah Starzz" if s <= 2002 else "San Antonio Silver Stars" if s <= 2013 else "San Antonio Stars" if s <= 2017 else None
    return None


WNBA = make("wnba", "WNBA", "The WNBA Belt", "Basketball", 1997, teams=WNBA_TEAMS, aliases=_wnba_code,
            display=WNBA_NAMES, era=_wnba_era, keep=lambda c, x: c not in WNBA_NOT_TEAMS, gap_days=400,
            label=lambda y: str(y), time_word="Tip-off", unit="teams", post_word="playoffs",
            rules=("<p><b>WNBA.</b> The belt starts with the league's first game, New York at Los Angeles on June 21, 1997, "
                   "and counts every regular-season, Commissioner's Cup and playoff game (not All-Star games). "
                   "Overtime wins count as wins.</p>"),
            sources=('WNBA results come from the <a href="https://github.com/sportsdataverse/wehoop">wehoop</a> project '
                     '(sportsdataverse, CC BY 4.0): WNBA Stats game logs for 1997–2001 and ESPN schedules since 2002, '
                     'with the latest games from ESPN.'))

# ------------------------------------------------ Women's college basketball
_WCBB_COLORS = {}
_WCBB_COUNTS = {}


def _wcbb_colors(c):
    if not _WCBB_COLORS:
        p = os.path.join("data", "wcbb", "colors.json")
        if os.path.exists(p):
            with open(p) as f:
                _WCBB_COLORS.update(json.load(f))
        _WCBB_COLORS.setdefault("_", None)
    t = _WCBB_COLORS.get(str(c))
    if not t:
        return None
    return (t[0], t[1], t[2] if len(t) > 2 else "")


def _wcbb_keep(c, x):
    """Division I teams only: ESPN's files include each D-I team's games against lower-division
    opponents, who play a handful of D-I games a season at most."""
    if not _WCBB_COUNTS:
        from collections import Counter
        n = Counter()
        for r in read_games_csv(os.path.join("data", "wcbb", "games.csv")):
            n[(str(r["home"]), str(r["season"]))] += 1
            n[(str(r["away"]), str(r["season"]))] += 1
        _WCBB_COUNTS.update(n)
        _WCBB_COUNTS.setdefault(("_", "_"), 0)
    s = str(x.get("season") or "")
    got = _WCBB_COUNTS.get((str(c), s), 0)
    last = _WCBB_COUNTS.get("_max")
    if last is None:
        last = _WCBB_COUNTS["_max"] = max(int(k[1]) for k in _WCBB_COUNTS if isinstance(k, tuple) and k[1] != "_")
    if s and int(s) >= last and got < 12:
        # the season underway: judge by last completed season too
        got = max(got, _WCBB_COUNTS.get((str(c), str(int(s) - 1)), 0), _WCBB_COUNTS.get((str(c), str(last)), 0))
    # the hand-built 1986-2002 chain lists only the holder's games, every one of them against a D-I team
    return got >= 12 or x.get("source") in ("seed", "hist")


def _wcbb_era(c, season):
    """Names the 1986-2002 chain's teams went by then (ESPN's files from 2002 on use today's names)."""
    if int(season) > 2001:
        return None
    return {"2433": "Northeast Louisiana", "309": "Southwestern Louisiana", "2623": "Southwest Missouri State",
            "292": "Texas-Pan American", "2031": "Arkansas-Little Rock"}.get(str(c))


WCBB = make("wcbb", "NCAAW", "The Women's College Basketball Belt", "Basketball", 1985, teams=_wcbb_colors,
            names_file="names.json", keep=_wcbb_keep, era=_wcbb_era, gap_days=400, time_word="Tip-off", unit="teams",
            post_word="NCAA tournament",
            rules=("<p><b>Women's college basketball.</b> The belt starts with the reigning national champion: Texas, "
                   "which finished 34–0 by beating USC 97–81 in the 1986 NCAA final, carries it into the 1986–87 season. "
                   "It counts every game between Division I teams, including conference tournaments and the NCAA "
                   "tournament. Overtime wins count as wins.</p>"
                   "<p>The line from 1986–87 through the 2002 final (UConn 82, Oklahoma 70) was traced game by game from "
                   "school media guides and record books, box scores and student newspapers. It lists every game the "
                   "holder played; four wins whose scores haven't turned up yet (Arizona State over Oregon and Oregon "
                   "State in February 1992, Creighton over Bradley and Northern Iowa in January 1994) are left out, which "
                   "doesn't change who held the belt.</p>"),
            sources=('Women\'s college basketball results from 2002–03 on come from ESPN, via the '
                     '<a href="https://github.com/sportsdataverse/wehoop">wehoop</a> project (sportsdataverse, CC BY 4.0). '
                     'The 1986–2002 belt line was compiled from schools\' published media guides, record books and box '
                     'scores (Louisiana Tech, Tennessee, Virginia, USC, North Carolina, Stanford and many more), '
                     'The Stanford Daily archives and other student newspapers, and Wikipedia season pages.'))
WCBB["full_from"] = "2002-11-01"     # before this only the belt holder's games are listed

# -------------------------------------------------------------------- CFL
CFL_TEAMS = {"BC": ("#f15a24", "#111111", "Lions"), "CGY": ("#c8102e", "#111111", "Stampeders"), "EDM": ("#2b5134", "#f2b21b", "Edmonton"),
             "SSK": ("#006341", "#ffffff", "Roughriders"), "WPG": ("#041e42", "#b9975b", "Blue Bombers"),
             "HAM": ("#ffb819", "#111111", "Tiger-Cats"), "TOR": ("#002f65", "#6cace4", "Argonauts"),
             "MTL": ("#0a2e5c", "#c8102e", "Alouettes"), "OTT": ("#c8102e", "#111111", "Redblacks"),
             "OTR": (None, None, "Rough Riders"), "REN": (None, None, "Renegades"), "SAC": (None, None, "Gold Miners"),
             "LV": (None, None, "Posse"), "BAL": (None, None, "Stallions"), "SHR": (None, None, "Pirates"),
             "BIR": (None, None, "Barracudas"), "MEM": (None, None, "Mad Dogs")}
CFL_NAMES = {"BC": "BC Lions", "CGY": "Calgary Stampeders", "EDM": "Edmonton Elks", "SSK": "Saskatchewan Roughriders",
             "WPG": "Winnipeg Blue Bombers", "HAM": "Hamilton Tiger-Cats", "TOR": "Toronto Argonauts", "MTL": "Montreal Alouettes",
             "OTT": "Ottawa Redblacks", "OTR": "Ottawa Rough Riders", "REN": "Ottawa Renegades", "SAC": "Sacramento Gold Miners",
             "LV": "Las Vegas Posse", "BAL": "Baltimore Stallions", "SHR": "Shreveport Pirates", "BIR": "Birmingham Barracudas",
             "MEM": "Memphis Mad Dogs"}


def _cfl_era(c, season):
    s = int(season)
    if c == "EDM":
        return "Edmonton Eskimos" if s <= 2019 else "Edmonton Football Team" if s == 2020 else None
    if c == "MTL" and 1982 <= s <= 1985:
        return "Montreal Concordes"
    if c == "BAL" and s == 1994:
        return "Baltimore CFLers"
    if c == "SAC" and s >= 1995:
        return "San Antonio Texans"
    return None


# Wikipedia's CFL team-season pages are complete enough to follow every game from CFL_START on; before
# that too many teams have no page. The belt opens with the previous Grey Cup, so the reigning champion
# carries it into CFL_START.
CFL_START = 1999


def _cfl_keep(c, x):
    s = int(x.get("season") or 0)
    return s >= CFL_START or (s == CFL_START - 1 and x.get("note") == "Grey Cup")


CFL = make("cfl", "CFL", "The CFL Belt", "Canadian football", CFL_START - 1, teams=CFL_TEAMS, display=CFL_NAMES, era=_cfl_era,
           keep=_cfl_keep, gap_days=330, label=lambda y: str(y), unit="teams", post_word="Grey Cup playoffs",
           rules=(f"<p><b>CFL.</b> The belt starts with the {CFL_START - 1} Grey Cup: the champion carries it into the "
                  f"{CFL_START} season, and it counts every regular-season and playoff game since, including the Grey Cup. "
                  "A tie is a successful defense. Teams that folded or moved (the Rough Riders, Renegades and the 1990s U.S. "
                  "teams) vacate the belt to the most recent earlier holder still playing.</p>"),
           sources=('CFL results come from the schedule tables on Wikipedia\'s team-season articles and the playoff brackets on '
                    'its season articles (<a href="https://en.wikipedia.org/wiki/List_of_Canadian_Football_League_seasons">list of CFL seasons</a>), '
                    'used under <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>; each game is '
                    'checked against both teams\' pages.'))


def _plain(s):
    import unicodedata
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().replace(".", "")


def _keyword_code(table):
    """Alias function for sources that spell clubs differently (ASA vs ESPN vs engsoccerdata)."""
    def code(raw, season=None):
        n = _plain(raw)
        for k, c in table:
            if k in n:
                return c(season) if callable(c) else c
        return raw
    return code


# -------------------------------------------------------------------- MLS
MLS_CODE = _keyword_code([
    ("atlanta", "ATL"), ("austin", "ATX"), ("chivas", "CHV"), ("montreal", "MTL"), ("impact", "MTL"), ("charlotte", "CLT"),
    ("chicago", "CHI"), ("colorado", "COL"), ("columbus", "CLB"), ("dc united", "DC"), ("d c united", "DC"),
    ("cincinnati", "CIN"), ("dallas", "DAL"), ("houston", "HOU"), ("inter miami", "MIA"), ("fusion", "MIF"),
    ("galaxy", "LA"), ("los angeles", "LAFC"), ("lafc", "LAFC"), ("minnesota", "MIN"), ("nashville", "NSH"),
    ("new england", "NE"), ("new york city", "NYC"), ("nycfc", "NYC"), ("red bull", "NY"), ("metrostars", "NY"),
    ("orlando", "ORL"), ("philadelphia", "PHI"), ("portland", "POR"), ("salt lake", "RSL"), ("san diego", "SD"),
    ("san jose", "SJ"), ("earthquakes", "SJ"), ("seattle", "SEA"), ("kansas city", "SKC"), ("sporting", "SKC"),
    ("st louis", "STL"), ("tampa", "TB"), ("toronto", "TOR"), ("vancouver", "VAN")])
MLS_TEAMS = {"ATL": ("#80000a", "#a19060", "Atlanta"), "ATX": ("#00b140", "#111111", "Austin"), "MTL": ("#0033a1", "#111111", "Montréal"),
             "CLT": ("#1a85c8", "#111111", "Charlotte"), "CHI": ("#c8102e", "#7ccdef", "Chicago"), "COL": ("#960a2c", "#9cc2ea", "Colorado"),
             "CLB": ("#fedd00", "#111111", "Columbus"), "DC": ("#111111", "#ef3e42", "D.C. United"), "CIN": ("#f05323", "#263b80", "Cincinnati"),
             "DAL": ("#e81f3e", "#2a4076", "Dallas"), "HOU": ("#ff6b00", "#101820", "Houston"), "MIA": ("#f7b5cd", "#231f20", "Inter Miami"),
             "LA": ("#00245d", "#ffd200", "Galaxy"), "LAFC": ("#111111", "#c39e6d", "LAFC"), "MIN": ("#111111", "#8cd2f4", "Minnesota"),
             "NSH": ("#ece83a", "#1f1646", "Nashville"), "NE": ("#0a2240", "#ce0e2d", "New England"), "NYC": ("#6cace4", "#041e42", "NYCFC"),
             "NY": ("#ed1e36", "#23326a", "Red Bulls"), "ORL": ("#633492", "#ffffff", "Orlando"), "PHI": ("#071b2c", "#b19b69", "Philadelphia"),
             "POR": ("#004812", "#d69a00", "Portland"), "RSL": ("#b30838", "#013a81", "Real Salt Lake"), "SD": ("#0b1f3a", "#a9a9a9", "San Diego"),
             "SJ": ("#0067b1", "#111111", "San Jose"), "SEA": ("#5d9741", "#005595", "Seattle"), "SKC": ("#93b1d7", "#002f65", "Sporting KC"),
             "STL": ("#dd004a", "#001f5b", "St. Louis"), "TOR": ("#b81137", "#455560", "Toronto"), "VAN": ("#00245e", "#9dc2ea", "Vancouver"),
             "CHV": (None, None, "Chivas USA"), "MIF": (None, None, "Miami Fusion"), "TB": (None, None, "Tampa Bay")}
MLS_NAMES = {"ATL": "Atlanta United", "ATX": "Austin FC", "MTL": "CF Montréal", "CLT": "Charlotte FC", "CHI": "Chicago Fire",
             "COL": "Colorado Rapids", "CLB": "Columbus Crew", "DC": "D.C. United", "CIN": "FC Cincinnati", "DAL": "FC Dallas",
             "HOU": "Houston Dynamo", "MIA": "Inter Miami", "LA": "LA Galaxy", "LAFC": "Los Angeles FC", "MIN": "Minnesota United",
             "NSH": "Nashville SC", "NE": "New England Revolution", "NYC": "New York City FC", "NY": "New York Red Bulls",
             "ORL": "Orlando City", "PHI": "Philadelphia Union", "POR": "Portland Timbers", "RSL": "Real Salt Lake",
             "SD": "San Diego FC", "SJ": "San Jose Earthquakes", "SEA": "Seattle Sounders", "SKC": "Sporting Kansas City",
             "STL": "St. Louis City SC", "TOR": "Toronto FC", "VAN": "Vancouver Whitecaps", "CHV": "Chivas USA",
             "MIF": "Miami Fusion", "TB": "Tampa Bay Mutiny"}


def _mls_era(c, season):
    s = int(season)
    if c == "NY":
        return "NY/NJ MetroStars" if s <= 1997 else "MetroStars" if s <= 2005 else None
    if c == "SKC":
        return "Kansas City Wiz" if s == 1996 else "Kansas City Wizards" if s <= 2010 else None
    if c == "DAL" and s <= 2004:
        return "Dallas Burn"
    if c == "SJ" and s <= 1999:
        return "San Jose Clash"
    if c == "MTL" and s <= 2020:
        return "Montreal Impact"
    return None


MLS = make("mls", "MLS", "The MLS Belt", "Soccer", 1996, teams=MLS_TEAMS, aliases=MLS_CODE, display=MLS_NAMES, era=_mls_era,
           gap_days=200, label=lambda y: str(y), post_word="playoffs",
           rules=("<p><b>MLS.</b> The belt starts with the league's first game, San Jose 1–0 D.C. United on April 6, 1996, "
                  "and counts every regular-season and playoff game. A draw is a successful defense; a game settled by a "
                  "shootout (MLS's tiebreaker from 1996 to 1999, and in the playoffs) goes to the shootout winner. "
                  "A club that folds vacates the belt to the most recent earlier holder still playing.</p>"),
           sources=(f"MLS results for 1996–2016 come from {ESD}; since 2017 from "
                    '<a href="https://app.americansocceranalysis.com/">American Soccer Analysis</a>; upcoming games from ESPN.'))

# ------------------------------------------------------------------- NWSL
NWSL_CODE = _keyword_code([
    ("angel city", "ACFC"), ("bay fc", "BAY"), ("breakers", "BOS1"), ("boston", "BOS"), ("chicago", "CHI"), ("red stars", "CHI"),
    ("denver", "DEN"), ("fc kansas city", "FCKC"), ("gotham", "NJY"), ("sky blue", "NJY"), ("houston", "HOU"),
    ("kansas city", "KC"), ("courage", "NC"), ("north carolina", "NC"), ("flash", "NC"), ("orlando", "ORL"),
    ("portland", "POR"), ("louisville", "LOU"), ("san diego", "SD"), ("reign", "SEA"), ("seattle", "SEA"),
    ("utah", lambda s: "UTA1" if s is not None and s <= 2020 else "UTA"), ("washington", "WAS"), ("spirit", "WAS")])
NWSL_TEAMS = {"ACFC": ("#231f20", "#e6a2a8", "Angel City"), "BAY": ("#0c2340", "#e24e33", "Bay FC"), "BOS": ("#0b2240", "#9ad3de", "Boston"),
              "CHI": ("#41b6e6", "#c8102e", "Chicago"), "DEN": ("#2a3b8f", "#f1b434", "Denver"), "NJY": ("#111111", "#a5d4ef", "Gotham"),
              "HOU": ("#f36f21", "#8ab7e9", "Houston"), "KC": ("#62cbc9", "#cf3339", "KC Current"), "NC": ("#00416b", "#ab0033", "Courage"),
              "ORL": ("#633492", "#63c7e8", "Orlando"), "POR": ("#971d1f", "#111111", "Thorns"), "LOU": ("#c5b4e3", "#0a2240", "Louisville"),
              "SD": ("#041e42", "#f58f7a", "Wave"), "SEA": ("#0a2240", "#c8a15a", "Reign"), "UTA": ("#fdb71a", "#1d2a54", "Utah"),
              "WAS": ("#111111", "#c8102e", "Spirit"), "BOS1": (None, None, "Breakers"), "FCKC": (None, None, "FC Kansas City"),
              "UTA1": (None, None, "Utah Royals")}
NWSL_NAMES = {"ACFC": "Angel City FC", "BAY": "Bay FC", "BOS": "Boston Legacy FC", "CHI": "Chicago Stars FC", "DEN": "Denver Summit FC",
              "NJY": "Gotham FC", "HOU": "Houston Dash", "KC": "Kansas City Current", "NC": "North Carolina Courage",
              "ORL": "Orlando Pride", "POR": "Portland Thorns FC", "LOU": "Racing Louisville FC", "SD": "San Diego Wave FC",
              "SEA": "Seattle Reign FC", "UTA": "Utah Royals", "WAS": "Washington Spirit", "BOS1": "Boston Breakers",
              "FCKC": "FC Kansas City", "UTA1": "Utah Royals FC"}


def _nwsl_era(c, season):
    s = int(season)
    if c == "NC" and s <= 2016:
        return "Western New York Flash"
    if c == "CHI" and s <= 2023:
        return "Chicago Red Stars"
    if c == "NJY" and s <= 2020:
        return "Sky Blue FC"
    if c == "SEA":
        return "Reign FC" if s == 2019 else "OL Reign" if 2020 <= s <= 2023 else None
    return None


NWSL = make("nwsl", "NWSL", "The NWSL Belt", "Soccer", 2013, teams=NWSL_TEAMS, aliases=NWSL_CODE, display=NWSL_NAMES, era=_nwsl_era,
            gap_days=200, label=lambda y: str(y), post_word="playoffs",
            rules=("<p><b>NWSL.</b> The belt starts with the league's first game in April 2013 and counts every regular-season, "
                   "playoff and Challenge Cup game ESPN lists. A draw is a successful defense; a game settled on penalties goes "
                   "to the shootout winner.</p>"),
            sources="NWSL results and upcoming games come from ESPN's public scoreboard.")
