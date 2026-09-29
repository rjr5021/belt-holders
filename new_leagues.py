#!/usr/bin/env python3
"""
Game files for the leagues added in October 2026. Writes, per league,

    data/<key>/games.csv      every completed game (same columns as update_data.py)
    data/<key>/upcoming.json  the scheduled games we know about

    python3 new_leagues.py              # every league
    python3 new_leagues.py epl wnba     # some of them

Sources (all free, no keys):
  European top flights  engsoccerdata (github.com/jalapic/engsoccerdata, GPL) through 2024-25,
                        then openfootball/football.json (public domain) for later seasons
  International         github.com/martj42/international_results (CC0), men's full internationals since 1872
  PWHL                  github.com/sportsdataverse/fastRhockey-pwhl-raw (MIT), every game since 2024
  WNBA                  sportsdataverse wehoop (CC BY 4.0): WNBA Stats game logs 1997-2001,
                        ESPN-based schedules 2002 on; ESPN scoreboard for the latest days and upcoming
  MLS                   engsoccerdata 1996-2016; American Soccer Analysis API 2017 on; ESPN for upcoming
  NWSL                  ESPN scoreboard (usa.nwsl), 2013 on
  Women's college bb    Massey Ratings 1997-98 to 2001-02; sportsdataverse wehoop (ESPN) 2002-03 on

Team names are kept as each source's "current name" for a franchise, mapped to
one code per franchise in the league adapters.
"""

import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = timezone(timedelta(hours=-5))

FIELDS = ["id", "date", "season", "season_type", "home", "away", "home_points", "away_points",
          "neutral", "note", "source", "home_name", "away_name", "home_abbr", "away_abbr"]
RAW = "https://raw.githubusercontent.com"


def get(url, as_json=False, tries=4, ua=None):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua} if ua else {})
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
            if url.endswith(".parquet"):
                return body
            body = body.decode("utf-8", errors="replace")
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 * (i + 1))
    print("  failed:", url, last)
    return None


def write(key, rows, upcoming):
    folder = os.path.join("data", key)
    os.makedirs(folder, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["date"], r["season_type"] != "regular", str(r["id"])))
    with open(os.path.join(folder, "games.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    upcoming = sorted(upcoming, key=lambda u: (u["date"], u.get("start_et") or ""))
    with open(os.path.join(folder, "upcoming.json"), "w", encoding="utf-8") as f:
        json.dump(upcoming, f, indent=1)
    print(f"[{key}] {len(rows):,} games ({rows[0]['date'] if rows else '-'} to {rows[-1]['date'] if rows else '-'}), {len(upcoming)} upcoming")


def read_existing(key):
    p = os.path.join("data", key, "games.csv")
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def today_et():
    return datetime.now(ET).date()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|afc|cf|sc|ac|as|ssc|us|rc|sd|ud|cd|club|de|futbol|calcio|1\.|bv|sv|vfb|vfl|tsg|fsv|ogc|stade|olympique|sporting)\b", " ", s)
    s = re.sub(r"\b(19|18|20)\d\d\b|\b\d+\b", " ", s)
    return re.sub(r"[^a-z]", "", s)


# ================================================================ Europe ==

FIRST_DATED = {"ligue1": 1937}   # engsoccerdata gives 1932-33 to 1936-37 placeholder dates, so game order is unknown
EUROPE = {  # key: (engsoccerdata file, top-tier filter, openfootball code)
    "epl": ("england", lambda r: r["tier"] == "1", "en.1"),
    "laliga": ("spain", lambda r: r["tier"] == "1", "es.1"),
    "seriea": ("italy", lambda r: r["tier"] == "1", "it.1"),
    "bundesliga": ("germany", lambda r: r["tier"] == "1", "de.1"),
    "ligue1": ("france", lambda r: r["tier"] == "1", "fr.1"),
    "eredivisie": ("holland", lambda r: r.get("tier", "1") == "1", "nl.1"),
}
# openfootball names our history file spells differently (checked by hand)
OF_FIX = {"Málaga CF": "Malaga CF", "Real Racing Club de Santander": "Racing Santander",
          "ES Troyes AC": "ESTAC Troyes", "RC Deportivo La Coruña": "Deportivo La Coruna",
          "Le Mans FC": "Le Mans UC 72", "AC Pisa 1909": "Pisa SC", "US Sassuolo Calcio": "Sassuolo Calcio",
          "SV 07 Elversberg": "SV Elversberg", "1. FC Köln": "1. FC Koln", "SC Cambuur-Leeuwarden": "SC Cambuur",
          "Telstar 1963": "Telstar"}


def _of_season(y):
    return f"{y}-{str(y + 1)[2:]}"


def _of_matches(code, y):
    j = get(f"{RAW}/openfootball/football.json/master/{_of_season(y)}/{code}.json", as_json=True)
    return (j or {}).get("matches") or []


def _of_score(m):
    s = m.get("score")
    if isinstance(s, list) and len(s) == 2:
        return s
    if isinstance(s, dict):
        return s.get("ft") or s.get("et")
    return None


def update_europe(key):
    fname, top, code = EUROPE[key]
    text = get(f"{RAW}/jalapic/engsoccerdata/master/data-raw/{fname}.csv")
    if not text:
        raise RuntimeError("engsoccerdata unavailable")
    hist = []
    all_names = set()
    for r in csv.DictReader(io.StringIO(text)):
        all_names |= {r["home"], r["visitor"]}
        if not top(r) or r["hgoal"] in ("", "NA") or int(r["Season"]) < FIRST_DATED.get(key, 0):
            continue
        hist.append(r)
    last_season = max(int(r["Season"]) for r in hist)
    rows = [{"id": f"esd-{i}", "date": r["Date"], "season": int(r["Season"]), "season_type": "regular",
             "home": r["home"], "away": r["visitor"], "home_points": int(r["hgoal"]), "away_points": int(r["vgoal"]),
             "neutral": "", "note": "", "source": "engsoccerdata"} for i, r in enumerate(hist)]
    # ---- openfootball names -> engsoccerdata names, learned from the last season both have
    by = defaultdict(list)
    for r in hist:
        if int(r["Season"]) == last_season:
            by[(r["Date"], int(r["hgoal"]), int(r["vgoal"]))].append(r)
    votes = defaultdict(Counter)
    for m in _of_matches(code, last_season):
        s = _of_score(m)
        if not s:
            continue
        c = by.get((m["date"], s[0], s[1]), [])
        if len(c) == 1:
            votes[m["team1"]][c[0]["home"]] += 1
            votes[m["team2"]][c[0]["visitor"]] += 1
    mapping = {k: v.most_common(1)[0][0] for k, v in votes.items()}
    by_norm = defaultdict(set)
    for n in all_names:
        by_norm[norm(n)].add(n)

    def name(of):
        if of in OF_FIX:
            return OF_FIX[of]
        if of in mapping:
            return mapping[of]
        if of in all_names:
            return of
        plain = re.sub(r"\s+(FC|AFC|CF)$", "", of).strip()
        if plain in all_names:
            return plain
        c = by_norm.get(norm(of))
        if c and len(c) == 1:
            return next(iter(c))
        # "Coventry City FC" -> "Coventry City": only when exactly one name fits
        fits = [n for n in all_names if len(norm(n)) >= 5 and (norm(of).startswith(norm(n)) or norm(n).startswith(norm(of)))]
        if len(fits) == 1:
            return fits[0]
        return plain

    upcoming = []
    today = today_et().isoformat()
    y = last_season + 1
    unknown = set()
    while y <= today_et().year:
        ms = _of_matches(code, y)
        if not ms:
            y += 1
            continue
        for i, m in enumerate(ms):
            if m.get("status") in ("canceled", "cancelled", "postponed"):
                continue
            h, a = name(m["team1"]), name(m["team2"])
            for of, n in ((m["team1"], h), (m["team2"], a)):
                if of not in mapping and of not in OF_FIX:
                    unknown.add((of, n))
            s = _of_score(m)
            if s:
                rows.append({"id": f"of-{y}-{i}", "date": m["date"], "season": y, "season_type": "regular",
                             "home": h, "away": a, "home_points": int(s[0]), "away_points": int(s[1]),
                             "neutral": "", "note": "", "source": "openfootball"})
            elif m["date"] >= today:
                upcoming.append({"id": f"of-{y}-{i}", "date": m["date"], "season": y, "season_type": "regular",
                                 "home": h, "away": a, "start_et": m.get("time")})
        y += 1
    if unknown:
        print(f"  [{key}] names matched by spelling:", sorted(unknown))
    write(key, rows, upcoming)


# ========================================================= International ==

def update_intl():
    text = get(f"{RAW}/martj42/international_results/master/results.csv")
    shoot = get(f"{RAW}/martj42/international_results/master/shootouts.csv") or ""
    if not text:
        raise RuntimeError("international results unavailable")
    pens = {}
    for r in csv.DictReader(io.StringIO(shoot)):
        pens[(r["date"], r["home_team"], r["away_team"])] = r["winner"]
    raw = list(csv.DictReader(io.StringIO(text)))
    # FIFA-style teams only: a side counts once it has played a World Cup qualifier or finals match
    fifa = {t for r in raw if r["tournament"] in ("FIFA World Cup qualification", "FIFA World Cup")
            for t in (r["home_team"], r["away_team"])}
    rows, upcoming = [], []
    today = today_et().isoformat()
    for i, r in enumerate(raw):
        h, a = r["home_team"], r["away_team"]
        if h not in fifa or a not in fifa:
            continue
        base = {"id": f"int-{i}", "date": r["date"], "season": int(r["date"][:4]),
                "season_type": "postseason" if r["tournament"] != "Friendly" else "regular",
                "home": h, "away": a, "neutral": "1" if r["neutral"].upper() == "TRUE" else ""}
        if r["home_score"] in ("", "NA"):
            if r["date"] >= today:
                upcoming.append({**base, "start_et": None, "tournament": r["tournament"]})
            continue
        hp, ap = int(r["home_score"]), int(r["away_score"])
        note = r["tournament"]
        w = pens.get((r["date"], h, a))
        if hp == ap and w in (h, a):
            # a shootout win counts as the win (the score stays level; 'pens' marks it)
            note = f"{r['tournament']}; {w} won on penalties"
            hp, ap = (hp + 1, ap) if w == h else (hp, ap + 1)
            base["note_pen"] = "1"
        rows.append({**base, "home_points": hp, "away_points": ap, "note": note, "source": "martj42"})
    write("intl", rows, upcoming)


# ================================================================== PWHL ==

def update_pwhl():
    import pyarrow.parquet as pq
    body = get(f"{RAW}/sportsdataverse/fastRhockey-pwhl-raw/main/pwhl/pwhl_schedule_master.parquet")
    if not body:
        raise RuntimeError("PWHL schedule unavailable")
    t = pq.read_table(io.BytesIO(body)).to_pylist()
    rows, upcoming = [], []
    today = today_et()
    for r in t:
        season = int(r["season"])            # 2026 = the 2025-26 season
        try:
            md = datetime.strptime(r["game_date"].split(", ", 1)[1] + " 2000", "%b %d %Y")
        except (ValueError, IndexError):
            continue
        y = season - 1 if md.month >= 8 else season
        d = date(y, md.month, md.day).isoformat()
        st = (r.get("game_status") or "").strip()
        base = {"id": f"pwhl-{r['game_id']}", "date": d, "season": season - 1,
                "season_type": "postseason" if r.get("game_type") == "playoffs" else "regular",
                "home": r["home_team_id"], "away": r["away_team_id"], "neutral": ""}
        if st.startswith("Final") and str(r.get("home_score") or "").isdigit():
            note = "SO" if "SO" in st else ("OT" if "OT" in st else "")
            rows.append({**base, "home_points": int(r["home_score"]), "away_points": int(r["away_score"]),
                         "note": note, "source": "fastRhockey"})
        elif d >= today.isoformat():
            upcoming.append({**base, "start_et": None})
    write("pwhl", rows, upcoming)


# ========================================================== ESPN helpers ==

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d}&limit=500"


def espn_day(path, d, groups=None):
    """(completed rows, upcoming rows) for one day from ESPN's scoreboard."""
    url = ESPN.format(path=path, d=d.strftime("%Y%m%d")) + (f"&groups={groups}" if groups else "")
    j = get(url, as_json=True) or {}
    done, up = [], []
    for ev in j.get("events", []):
        comp = ev["competitions"][0]
        teams = {c["homeAway"]: c for c in comp["competitors"]}
        if "home" not in teams or "away" not in teams:
            continue
        h, a = teams["home"], teams["away"]
        start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        stype = (ev.get("season") or {}).get("type")
        row = {"id": f"espn-{ev['id']}", "date": start.date().isoformat(),
               "season_type": "postseason" if stype in (3, 5) else "regular",
               "home": h["team"].get("displayName") or h["team"].get("name"),
               "away": a["team"].get("displayName") or a["team"].get("name"),
               "home_id": h["team"].get("id"), "away_id": a["team"].get("id"),
               "home_abbr": h["team"].get("abbreviation"), "away_abbr": a["team"].get("abbreviation"),
               "neutral": "1" if comp.get("neutralSite") else "", "source": "espn",
               "season_year": (ev.get("season") or {}).get("year"), "stype": stype}
        status = ev["status"]["type"]
        if status.get("completed"):
            try:
                hp, ap = int(h["score"]), int(a["score"])
            except (KeyError, ValueError, TypeError):
                continue
            name = status.get("name") or ""
            note = ""
            if name == "STATUS_FINAL_PEN" or h.get("shootoutScore") is not None:
                hs, as_ = h.get("shootoutScore"), a.get("shootoutScore")
                note = "pens"
                if hs is not None and as_ is not None and hp == ap:
                    hp, ap = (hp + 1, ap) if hs > as_ else (hp, ap + 1)
            elif "OT" in (status.get("shortDetail") or "") or name == "STATUS_FINAL_AET":
                note = "OT"
            row.update(home_points=hp, away_points=ap, note=note)
            done.append(row)
        elif status.get("state") == "pre":
            row["start_et"] = None if status.get("name") == "STATUS_TBD" else start.strftime("%H:%M")
            up.append(row)
    return done, up


def espn_range(path, start, end, groups=None, pause=0.12):
    done, up = [], []
    d = start
    while d <= end:
        x, y = espn_day(path, d, groups)
        done += x
        up += y
        d += timedelta(days=1)
        time.sleep(pause)
    return done, up


def merge(old, new, key="id"):
    seen = {r[key]: r for r in old}
    for r in new:
        seen[r[key]] = r
    return list(seen.values())


# ================================================================== WNBA ==

SDV = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"


def update_wnba():
    rows = read_existing("wnba")
    today = today_et()
    if not rows:
        # 1997-2001: WNBA Stats team game logs (team rows have no player_id)
        for y in range(1997, 2002):
            t = get(f"{SDV}/wnba_stats_player_game_logs/player_game_logs_{y}.csv")
            if not t:
                print("  WNBA stats logs missing for", y)
                continue
            games = defaultdict(dict)
            for r in csv.DictReader(io.StringIO(t)):
                if r.get("player_id") not in ("", "NA", None):
                    continue
                m = r.get("matchup") or ""
                team = m.split()[0] if m else r.get("team_abbreviation")
                home = " vs. " in m
                games[r["game_id"]][("h" if home else "a")] = (team, int(float(r["pts"])), r["game_date"][:10],
                                                                "postseason" if "playoff" in (r.get("season_type") or "").lower() else "regular")
            n = 0
            for gid, g in games.items():
                if "h" not in g or "a" not in g:
                    continue
                (ht, hp, d, st), (at, ap, _, _) = g["h"], g["a"]
                rows.append({"id": f"wnbas-{gid}", "date": d, "season": y, "season_type": st, "home": ht, "away": at,
                             "home_points": hp, "away_points": ap, "neutral": "", "note": "", "source": "wnbastats"})
                n += 1
            print(f"  WNBA {y}: {n} games")
        for y in range(2002, today.year + 1):
            t = get(f"{SDV}/espn_wnba_schedules/wnba_schedule_{y}.csv")
            if not t:
                continue
            n = 0
            for r in csv.DictReader(io.StringIO(t)):
                if r.get("status_type_completed", "").upper() not in ("TRUE", "1") or r.get("home_score") in ("", "NA"):
                    continue
                if str(r.get("season_type")) not in ("2", "3"):
                    continue
                rows.append({"id": f"espn-{r['game_id'] if 'game_id' in r else r['id']}", "date": (r.get("game_date") or r.get("date"))[:10],
                             "season": y, "season_type": "postseason" if str(r.get("season_type")) == "3" else "regular",
                             "home": r.get("home_abbreviation") or r.get("home_display_name"),
                             "away": r.get("away_abbreviation") or r.get("away_display_name"),
                             "home_points": int(float(r["home_score"])), "away_points": int(float(r["away_score"])),
                             "neutral": "1" if str(r.get("neutral_site")).upper() == "TRUE" else "", "note": "", "source": "espn"})
                n += 1
            print(f"  WNBA {y}: {n} games (ESPN schedule file)")
    # the latest two weeks and the upcoming month from ESPN's scoreboard
    done, up = espn_range("basketball/wnba", today - timedelta(days=14), today + timedelta(days=45))
    for r in done:
        r["season"] = int(r["date"][:4])
        r["home"], r["away"] = _espn_abbr(r, "home"), _espn_abbr(r, "away")
    for r in up:
        r["season"] = int(r["date"][:4])
        r["home"], r["away"] = _espn_abbr(r, "home"), _espn_abbr(r, "away")
    rows = _dedupe_espn(rows, done)
    write("wnba", rows, [u for u in up if u["date"] >= today.isoformat()])


def _espn_abbr(r, side):
    return r.get(f"{side}_abbr") or r[side]


def _dedupe_espn(rows, new):
    """Replace rows with the same id; drop a schedule-file row that matches a scoreboard row by date+teams."""
    keyed = {(r["date"], r["home"], r["away"]) for r in new}
    rows = [r for r in rows if (r["date"], r["home"], r["away"]) not in keyed]
    return merge(rows, new)


# =================================================================== MLS ==

ASA = "https://app.americansocceranalysis.com/api/v1/{lg}/{what}"


def _asa_games(lg, first_season):
    teams = {t["team_id"]: t["team_name"] for t in (get(ASA.format(lg=lg, what="teams"), as_json=True) or [])}
    rows = []
    for y in range(first_season, today_et().year + 1):
        got = get(ASA.format(lg=lg, what="games") + f"?season_name={y}", as_json=True) or []
        n = 0
        for g in got:
            if g.get("home_score") is None or g.get("away_score") is None:
                continue
            dt = datetime.fromisoformat(str(g["date_time_utc"]).replace("Z", "+00:00").replace(" UTC", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = dt.astimezone(ET).date().isoformat()
            hp, ap = int(g["home_score"]), int(g["away_score"])
            note = ""
            if g.get("penalties") and g.get("home_penalties") is not None:
                note = "pens"
                if hp == ap:
                    hp, ap = (hp + 1, ap) if g["home_penalties"] > g["away_penalties"] else (hp, ap + 1)
            elif g.get("extra_time"):
                note = "AET"
            rows.append({"id": f"asa-{g['game_id']}", "date": d, "season": y,
                         "season_type": "postseason" if g.get("knockout_game") else "regular",
                         "home": teams.get(g["home_team_id"], g["home_team_id"]),
                         "away": teams.get(g["away_team_id"], g["away_team_id"]),
                         "home_points": hp, "away_points": ap, "neutral": "", "note": note, "source": "asa"})
            n += 1
        print(f"  {lg.upper()} {y}: {n} games (ASA)")
        time.sleep(1)
    return rows


def update_mls():
    today = today_et()
    rows = read_existing("mls")
    if not rows:
        t = get(f"{RAW}/jalapic/engsoccerdata/master/data-raw/mls.csv")
        for i, r in enumerate(csv.DictReader(io.StringIO(t or ""))):
            if r["hgoal"] in ("", "NA"):
                continue
            hp, ap = int(r["hgoal"]), int(r["vgoal"])
            note = ""
            if r.get("hgoalaet") not in ("", "NA", None):
                hp, ap, note = int(r["hgoalaet"]), int(r["vgoalaet"]), "AET"
            if r.get("hpen") not in ("", "NA", None) and hp == ap:
                note = "pens"
                hp, ap = (hp + 1, ap) if int(r["hpen"]) > int(r["vpen"]) else (hp, ap + 1)
            rows.append({"id": f"esd-{i}", "date": r["Date"], "season": int(r["Season"]),
                         "season_type": "regular" if r["round"] == "regular" else "postseason",
                         "home": r["home"], "away": r["visitor"], "home_points": hp, "away_points": ap,
                         "neutral": "1" if r["round"] == "mls_final" else "", "note": note, "source": "engsoccerdata"})
        rows += _asa_games("mls", 2017)
    else:
        rows = [r for r in rows if not (r["source"] == "asa" and int(r["season"]) >= today.year)]
        rows += [r for r in _asa_games("mls", today.year)]
    _, up = espn_range("soccer/usa.1", today, today + timedelta(days=45))
    up = [{**u, "season": int(u["date"][:4])} for u in up]
    write("mls", rows, up)


# ================================================================== NWSL ==

def update_nwsl():
    today = today_et()
    rows = read_existing("nwsl")
    if not rows:
        start = date(2013, 4, 1)
    else:
        start = today - timedelta(days=21)
        rows = [r for r in rows if r["date"] < start.isoformat()]
    done, up = [], []
    d = start
    while d <= today + timedelta(days=45):
        if d.month in (1, 2) and d < today:          # offseason
            d = date(d.year, 3, 1)
            continue
        x, y = espn_day("soccer/usa.nwsl", d)
        done += x
        up += y
        d += timedelta(days=1)
        time.sleep(0.1)
    for r in done:
        r["season"] = int(r["date"][:4])
    rows = merge(rows, done)
    write("nwsl", rows, [{**u, "season": int(u["date"][:4])} for u in up if u["date"] >= today.isoformat()])


# ============================================== Women's college basketball ==

def update_wcbb():
    """ESPN (via sportsdataverse wehoop) from 2002-03. The belt starts with the reigning
    champion: UConn beat Oklahoma 82-70 in the 2002 NCAA final, so that game opens the file."""
    today = today_et()
    rows = read_existing("wcbb")
    cur = today.year + 1 if today.month >= 8 else today.year        # season 2027 = 2026-27
    seasons = range(2003, cur + 1) if not rows else [cur - 1, cur] if today.month <= 4 else [cur]
    keep = [r for r in rows if int(r["season"]) not in seasons]
    got = []
    for y in seasons:
        t = None
        for tag, fname in (("espn_womens_college_basketball_schedules", f"wbb_schedule_{y}.csv"),
                           ("espn_wbb_schedules", f"wbb_schedule_{y}.csv")):
            t = get(f"{SDV}/{tag}/{fname}")
            if t:
                break
        if not t:
            print("  no WBB schedule file for", y)
            continue
        n = 0
        for r in csv.DictReader(io.StringIO(t)):
            if str(r.get("status_type_completed", "")).upper() not in ("TRUE", "1") or r.get("home_score") in ("", "NA"):
                continue
            st = str(r.get("season_type"))
            if st not in ("2", "3"):
                continue
            gid = r.get("game_id") or r.get("id")
            got.append({"id": f"espn-{gid}", "date": (r.get("game_date") or r.get("date"))[:10], "season": y - 1,
                        "season_type": "postseason" if st == "3" else "regular",
                        "home": r.get("home_id"), "away": r.get("away_id"),
                        "home_name": r.get("home_location") or r.get("home_display_name"),
                        "away_name": r.get("away_location") or r.get("away_display_name"),
                        "home_points": int(float(r["home_score"])), "away_points": int(float(r["away_score"])),
                        "neutral": "1" if str(r.get("neutral_site")).upper() == "TRUE" else "", "note": "", "source": "espn"})
            n += 1
        print(f"  WBB {y - 1}-{str(y)[2:]}: {n} games")
    if not rows:
        got.append({"id": "seed-2002", "date": "2002-03-31", "season": 2001, "season_type": "postseason",
                    "home": "41", "away": "201", "home_name": "UConn", "away_name": "Oklahoma",
                    "home_points": 82, "away_points": 70, "neutral": "1", "note": "2002 NCAA final", "source": "seed"})
    rows = keep + got
    done, up = espn_range("basketball/womens-college-basketball", today - timedelta(days=3), today + timedelta(days=30), groups="50")
    for r in done + up:
        r["season"] = today.year if today.month >= 8 else today.year - 1
        r["home_name"], r["away_name"] = r["home"], r["away"]
        r["home"], r["away"] = r["home_id"], r["away_id"]
    rows = merge(rows, done)
    names = {}
    for r in rows + up:
        for s in ("home", "away"):
            if r.get(f"{s}_name"):
                names[str(r[s])] = r[f"{s}_name"]
    write("wcbb", rows, [u for u in up if u["date"] >= today.isoformat()])
    with open(os.path.join("data", "wcbb", "names.json"), "w") as f:
        json.dump(names, f, indent=0, sort_keys=True)


UPDATERS = {"epl": lambda: update_europe("epl"), "laliga": lambda: update_europe("laliga"),
            "seriea": lambda: update_europe("seriea"), "bundesliga": lambda: update_europe("bundesliga"),
            "ligue1": lambda: update_europe("ligue1"), "eredivisie": lambda: update_europe("eredivisie"),
            "intl": update_intl, "pwhl": update_pwhl, "wnba": update_wnba,
            "mls": update_mls, "nwsl": update_nwsl, "wcbb": update_wcbb}


def main():
    keys = [a for a in sys.argv[1:] if not a.startswith("-")] or list(UPDATERS)
    failed = []
    for k in keys:
        try:
            UPDATERS[k]()
        except Exception as e:  # keep the last good files
            print(f"[{k}] update failed: {e}")
            failed.append(k)
    if failed and len(failed) == len(keys):
        sys.exit(1)


if __name__ == "__main__":
    main()
