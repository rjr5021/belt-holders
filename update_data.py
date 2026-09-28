#!/usr/bin/env python3
"""
Refresh the game files that the NHL and NBA adapters read:

    data/nhl/games.csv   data/nhl/upcoming.json
    data/nba/games.csv   data/nba/upcoming.json
    data/mlb/games.csv   data/mlb/upcoming.json

These are committed to the repo. The first run backfills every season (a few
minutes); after that each run only refetches the current season, so the
2-hourly workflow stays light on the sources.

    python3 update_data.py            # both leagues
    python3 update_data.py nhl        # one league
    python3 update_data.py nba --full # force a full backfill

Sources (no API keys):
  NHL  api.nhle.com/stats/rest/en/game   every NHL game since 1917, one request per season
  NBA  FiveThirtyEight nbaallelo.csv     1946-47 through 2014-15 (frozen)
       data.nba.com full schedules       2015-16 through 2024-25 (frozen)
       ESPN scoreboard, one day per call 2025-26 onward, plus the upcoming schedule
  MLB  Retrosheet game logs (GitHub mirror) every NL/AL game 1876 on + postseason
       MLB Stats API                     seasons Retrosheet hasn't published yet, plus upcoming

The NFL adapter reads its sources directly and isn't handled here.
"""

import csv
import io
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = timezone(timedelta(hours=-5))

# ESPN turns away requests from data centers that send a custom User-Agent
# (browser-style or bot-style); the plain Python default gets through.
# NBA.com's static files want the browser one.
UA = None  # Python's default "Python-urllib/3.x" -- the one ESPN verifiably accepts
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
FIELDS = ["id", "date", "season", "season_type", "home", "away", "home_points", "away_points",
          "neutral", "note", "source"]


def get(url, tries=4, as_json=True, ua=UA):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua} if ua else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8")
            return json.loads(body) if as_json else body
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["date"], r["season_type"] != "regular", str(r["id"])))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {len(rows):,} games -> {path}")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    print(f"  wrote {len(obj)} upcoming -> {path}")


def today_et():
    return datetime.now(ET).date()


# ===================================================================== NHL ==

NHL_API = "https://api.nhle.com/stats/rest/en/game?cayenneExp=season={s}"
NHL_FINAL_STATES = {5, 6, 7}
NHL_UPCOMING_STATES = {1, 2, 8, 9}  # FUT, PRE, TBD, PPD


def nhl_note(g):
    p = g.get("period") or 3
    if p <= 3:
        return ""
    season = int(str(g["season"])[:4])
    if p == 5 and season >= 2005 and g.get("gameType") == 2:
        return "SO"
    return "OT" if p == 4 else f"{p - 3}OT"


def nhl_fetch_season(start_year):
    code = f"{start_year}{start_year + 1}"
    data = get(NHL_API.format(s=code))["data"]
    done, upcoming = [], []
    for g in data:
        if g.get("gameType") not in (2, 3):   # 1 preseason, 4 all-star, 12+ special events
            continue
        row = {
            "id": g["id"], "date": g["gameDate"], "season": start_year,
            "season_type": "regular" if g["gameType"] == 2 else "postseason",
            "home": g["homeTeamId"], "away": g["visitingTeamId"], "neutral": "",
            "source": "nhl",
        }
        st = g.get("gameStateId")
        if st in NHL_FINAL_STATES:
            row.update(home_points=g["homeScore"], away_points=g["visitingScore"], note=nhl_note(g))
            done.append(row)
        elif st in NHL_UPCOMING_STATES:
            t = (g.get("easternStartTime") or "")[11:16]
            upcoming.append({**row, "start_et": t or None})
    return done, upcoming


def update_nhl(full=False):
    print("[nhl] updating")
    path = os.path.join("data", "nhl", "games.csv")
    rows = [] if full else read_csv(path)
    if rows:
        latest = max(int(r["season"]) for r in rows)
        seasons = [latest, latest + 1]
        rows = [r for r in rows if int(r["season"]) < latest]
    else:
        seasons = list(range(1917, today_et().year + 1))
    upcoming = []
    for s in seasons:
        done, up = nhl_fetch_season(s)
        rows += done
        upcoming += up
        if done or up:
            print(f"  {s}-{str(s + 1)[2:]}: {len(done)} final, {len(up)} upcoming")
        time.sleep(0.3)
    write_csv(path, rows)
    today = today_et().isoformat()
    upcoming = sorted((u for u in upcoming if u["date"] >= today), key=lambda u: (u["date"], u.get("start_et") or ""))
    write_json(os.path.join("data", "nhl", "upcoming.json"), upcoming)


# ===================================================================== NBA ==

URL_538 = "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv"
URL_NBA_SCHED = "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{y}/league/00_full_schedule.json"
URL_ESPN_DAY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
URL_ESPN_TEAM = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{t}/schedule?season={y}&seasontype=2"
NBA_FIRST_ESPN_SEASON = 2025          # 2025-26; data.nba.com's feed stops updating after 2024-25
NBA_SCHED_SEASONS = range(2015, 2025)  # 2015-16 .. 2024-25


def nba_538():
    text = get(URL_538, as_json=False)
    rows = []
    for x in csv.DictReader(io.StringIO(text)):
        if x["lg_id"] != "NBA" or x["_iscopy"] != "0":
            continue
        m, d, y = (int(v) for v in x["date_game"].split("/"))
        home, away = x["team_id"], x["opp_id"]
        hp, ap = int(x["pts"]), int(x["opp_pts"])
        if x["game_location"] == "A":
            home, away, hp, ap = away, home, ap, hp
        rows.append({
            "id": x["game_id"], "date": f"{y:04d}-{m:02d}-{d:02d}", "season": int(x["year_id"]) - 1,
            "season_type": "postseason" if x["is_playoffs"] == "1" else "regular",
            "home": home, "away": away, "home_points": hp, "away_points": ap,
            "neutral": "1" if x["game_location"] == "N" else "", "note": "", "source": "538",
        })
    print(f"  538: {len(rows):,} games 1946-47 to 2014-15")
    return rows


NBA_TYPES = {"002": "regular", "004": "postseason", "005": "postseason", "006": "regular"}  # 005 play-in, 006 NBA Cup final


def nba_sched_season(y):
    j = get(URL_NBA_SCHED.format(y=y), ua=BROWSER_UA)
    rows = []
    for mon in j["lscd"]:
        for g in mon["mscd"]["g"]:
            st = NBA_TYPES.get(g["gid"][:3])
            if not st or str(g.get("st")) != "3":
                continue
            if not g["h"].get("s") or not g["v"].get("s"):
                continue
            rows.append({
                "id": g["gid"], "date": (g.get("etm") or g["gdte"])[:10], "season": y, "season_type": st,
                "home": g["h"]["ta"], "away": g["v"]["ta"],
                "home_points": int(g["h"]["s"]), "away_points": int(g["v"]["s"]),
                "neutral": "1" if g["gid"][:3] == "006" else "", "note": "", "source": "nba",
            })
    return rows


def _espn_spread(comp, home, away):
    try:
        o = (comp.get("odds") or [])[0]
    except IndexError:
        return None
    det = (o.get("details") or "").strip()
    if not det:
        return None
    if det.upper() in ("EVEN", "PK", "PICK"):
        return 0.0
    parts = det.split()
    if len(parts) != 2:
        return None
    try:
        v = abs(float(parts[1]))
    except ValueError:
        return None
    if parts[0] == home:
        return v
    if parts[0] == away:
        return -v
    return None


def nba_espn_day(d):
    j = get(URL_ESPN_DAY.format(d=d.strftime("%Y%m%d")))
    done, upcoming = [], []
    for ev in j.get("events", []):
        stype = (ev.get("season") or {}).get("type")
        if stype == 1:  # preseason
            continue
        comp = ev["competitions"][0]
        teams = {c["homeAway"]: c for c in comp["competitors"]}
        if "home" not in teams or "away" not in teams:
            continue
        h, a = teams["home"], teams["away"]
        start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        season_year = (ev.get("season") or {}).get("year")
        row = {
            "id": f"espn-{ev['id']}", "date": start.date().isoformat(),
            "season": (season_year - 1) if season_year else (start.year if start.month >= 8 else start.year - 1),
            "season_type": "postseason" if stype in (3, 5) else "regular",
            "home": h["team"]["abbreviation"], "away": a["team"]["abbreviation"],
            "neutral": "1" if comp.get("neutralSite") else "", "source": "espn",
        }
        status = ev["status"]["type"]
        if status.get("completed"):
            try:
                row.update(home_points=int(h["score"]), away_points=int(a["score"]))
            except (KeyError, ValueError, TypeError):
                continue
            per = ev["status"].get("period") or 4
            row["note"] = "" if per <= 4 else ("OT" if per == 5 else f"{per - 4}OT")
            done.append(row)
        elif status.get("state") == "pre":
            row["start_et"] = None if status.get("name") == "STATUS_TBD" else start.strftime("%H:%M")
            row["venue"] = ((comp.get("venue") or {}).get("fullName")) or None
            row["spread"] = _espn_spread(comp, row["home"], row["away"])
            upcoming.append(row)
    return done, upcoming


def update_nba(full=False):
    print("[nba] updating")
    path = os.path.join("data", "nba", "games.csv")
    rows = [] if full else read_csv(path)
    today = today_et()
    if not rows:
        rows = nba_538()
        for y in NBA_SCHED_SEASONS:
            try:
                got = nba_sched_season(y)
                print(f"  data.nba.com {y}-{str(y + 1)[2:]}: {len(got):,} games")
            except Exception as e:  # fall back to ESPN day by day for that season
                print(f"  data.nba.com {y} failed ({e}); using ESPN")
                got = []
                d = date(y, 10, 1)
                while d <= date(y + 1, 7, 1):
                    got += nba_espn_day(d)[0]
                    d += timedelta(days=1)
                    time.sleep(0.15)
                print(f"  ESPN {y}-{str(y + 1)[2:]}: {len(got):,} games")
            rows += got
            time.sleep(0.3)
        start = date(NBA_FIRST_ESPN_SEASON, 10, 1)
    else:
        espn_dates = [r["date"] for r in rows if r["source"] == "espn"]
        start = (date.fromisoformat(max(espn_dates)) - timedelta(days=3)) if espn_dates else date(NBA_FIRST_ESPN_SEASON, 10, 1)
        rows = [r for r in rows if not (r["source"] == "espn" and r["date"] >= start.isoformat())]
    # completed games: start .. today
    d, n = start, 0
    while d <= today:
        done, _ = nba_espn_day(d)
        rows += done
        n += len(done)
        d += timedelta(days=1)
        time.sleep(0.15)
    print(f"  ESPN {start}..{today}: {n:,} games")
    # dedupe (same game id)
    seen, uniq = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    write_csv(path, uniq)
    # upcoming: walk forward until every team has a game on the books (or 45 days)
    upcoming, teams_seen = [], set()
    d = today
    while d <= today + timedelta(days=45):
        done, up = nba_espn_day(d)
        upcoming += up
        teams_seen |= {t for u in up for t in (u["home"], u["away"])}
        if len(teams_seen) >= 30:
            break
        d += timedelta(days=1)
        time.sleep(0.15)
    # the rest of the season, team by team (the day scan above only reaches a few game days
    # ahead; season odds need every remaining game). Day-scan rows win: they carry spreads.
    have = {u["id"] for u in upcoming}
    season_end_year = today.year + 1 if today.month >= 7 else today.year
    for tid in range(1, 31):
        try:
            j = get(URL_ESPN_TEAM.format(t=tid, y=season_end_year))
        except Exception as ex:
            print(f"  ESPN team {tid} schedule failed: {ex}")
            continue
        for ev in j.get("events", []):
            try:
                comp = ev["competitions"][0]
                if (comp.get("status") or ev.get("status") or {}).get("type", {}).get("state") != "pre":
                    continue
                teams = {c["homeAway"]: c for c in comp["competitors"]}
                start = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
                row = {"id": f"espn-{ev['id']}", "date": start.date().isoformat(), "season": season_end_year - 1,
                       "season_type": "postseason" if (ev.get("seasonType") or {}).get("type") in (3, 5) else "regular",
                       "home": teams["home"]["team"]["abbreviation"], "away": teams["away"]["team"]["abbreviation"],
                       "neutral": "1" if comp.get("neutralSite") else "", "source": "espn",
                       "start_et": start.strftime("%H:%M"), "venue": (comp.get("venue") or {}).get("fullName"), "spread": None}
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if row["id"] not in have and row["date"] >= today.isoformat():
                have.add(row["id"])
                upcoming.append(row)
        time.sleep(0.15)
    upcoming.sort(key=lambda u: (u["date"], u.get("start_et") or ""))
    write_json(os.path.join("data", "nba", "upcoming.json"), upcoming)


# ===================================================================== MLB ==

RETRO = "https://raw.githubusercontent.com/chadwickbureau/retrosheet/master"
MLB_API = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={y}&gameType=R,F,D,L,W")
MLB_POST_FILES = ["GLWC", "GLDV", "GLLC", "GLWS"]  # wild card, division, LCS, World Series


def _retro_rows(text, season_type, leagues_only=True):
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 15:
            continue
        if leagues_only and not (r[4] in ("NL", "AL") and r[7] in ("NL", "AL")):
            continue
        d = r[0]
        date_iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        try:
            vs, hs = int(r[9]), int(r[10])
        except ValueError:
            continue
        forfeit = (r[14] or "").strip()
        note = ""
        if forfeit == "V":
            vs, hs, note = 9, 0, "forfeit"
        elif forfeit == "H":
            vs, hs, note = 0, 9, "forfeit"
        rows.append({
            "id": f"{date_iso}-{r[1] or '0'}-{r[6]}", "date": date_iso, "season": int(d[:4]),
            "season_type": season_type, "home": r[6], "away": r[3],
            "home_points": hs, "away_points": vs, "neutral": "", "note": note, "source": "retro",
        })
    return rows


def _retro_season(y):
    for name in (f"GL{y}.TXT", f"gl{y}.txt", f"GL{y}.txt", f"gl{y}.TXT"):
        try:
            return get(f"{RETRO}/seasons/{y}/{name}", as_json=False, tries=1)
        except RuntimeError:
            continue
    return None


def _mlb_api_season(y):
    j = get(MLB_API.format(y=y))
    done, upcoming = [], []
    for day in j.get("dates", []):
        for g in day.get("games", []):
            st = g.get("status", {})
            detail = st.get("detailedState", "")
            h, a = g["teams"]["home"], g["teams"]["away"]
            start = datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")).astimezone(ET)
            row = {
                "id": f"{g.get('officialDate', day['date'])}-{g.get('gameNumber', 1)}-{g['gamePk']}",
                "date": g.get("officialDate") or day["date"], "season": int(g.get("season", y)),
                "season_type": "regular" if g.get("gameType") == "R" else "postseason",
                "home": f"m{h['team']['id']}", "away": f"m{a['team']['id']}",
                "neutral": "", "source": "mlbapi",
            }
            if st.get("abstractGameState") == "Final" and "score" in h and "score" in a \
                    and not detail.startswith(("Postponed", "Cancelled", "Suspended")):
                row.update(home_points=int(h["score"]), away_points=int(a["score"]), note="")
                done.append(row)
            elif st.get("abstractGameState") == "Preview" and not detail.startswith(("Postponed", "Cancelled")):
                row["start_et"] = None if st.get("startTimeTBD") else start.strftime("%H:%M")
                row["venue"] = (g.get("venue") or {}).get("name")
                row["series"] = g.get("seriesDescription")
                row["if_necessary"] = g.get("ifNecessary") == "Y"
                upcoming.append(row)
    return done, upcoming


def update_mlb(full=False):
    print("[mlb] updating")
    path = os.path.join("data", "mlb", "games.csv")
    rows = [] if full else read_csv(path)
    this_year = today_et().year
    if not rows:
        last_retro = None
        for y in range(1876, this_year + 1):
            text = _retro_season(y)
            if text is None:
                if y >= this_year - 1:
                    break
                print(f"  Retrosheet {y}: missing")
                continue
            got = _retro_rows(text, "regular")
            rows += got
            last_retro = y
            time.sleep(0.1)
        print(f"  Retrosheet regular seasons through {last_retro}: {len(rows):,} games")
        for f in MLB_POST_FILES:
            got = [r for r in _retro_rows(get(f"{RETRO}/gamelog/{f}.TXT", as_json=False), "postseason", leagues_only=False)
                   if r["season"] <= last_retro]
            print(f"  Retrosheet {f}: {len(got)} games")
            rows += got
    retro_last = max(int(r["season"]) for r in rows if r["source"] == "retro")
    rows = [r for r in rows if r["source"] != "mlbapi"]
    upcoming = []
    for y in range(retro_last + 1, this_year + 1):
        try:
            done, up = _mlb_api_season(y)
        except Exception as e:  # keep the Retrosheet history even if the live feed is down
            print(f"  MLB API {y} failed: {e}")
            continue
        rows += done
        upcoming += up
        print(f"  MLB API {y}: {len(done):,} final, {len(up)} upcoming")
    write_csv(path, rows)
    today = today_et().isoformat()
    upcoming = sorted((u for u in upcoming if u["date"] >= today), key=lambda u: (u["date"], u.get("start_et") or ""))
    write_json(os.path.join("data", "mlb", "upcoming.json"), upcoming)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = "--full" in sys.argv
    leagues = args or ["nhl", "nba", "mlb"]
    failed = []
    for lg in leagues:
        try:
            {"nhl": update_nhl, "nba": update_nba, "mlb": update_mlb}[lg](full=full)
        except Exception as e:  # keep the last good files; the build still runs
            print(f"[{lg}] update failed: {e}")
            failed.append(lg)
    if failed and len(failed) == len(leagues):
        sys.exit(1)


if __name__ == "__main__":
    main()
