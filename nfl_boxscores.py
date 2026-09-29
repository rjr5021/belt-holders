#!/usr/bin/env python3
"""
NFL player stat lines for belt games since 1999, from nflverse's free weekly
player stats (https://github.com/nflverse/nflverse-data, CC-BY 4.0).

Matches each belt game by its nflverse game id (season_week_away_home) and
keeps both teams' player lines:

    data/nfl/box/belt_box.json   {belt game n: {"gid", "players": [...]}}

Row: [player_id, name, side h/a, CMP, ATT, PYD, PTD, INT, CAR, RYD, RTD,
REC, TGT, RECYD, RECTD, TKL, SCK, DINT, FGM, FGA]
"""

import csv
import io
import json
import os
import urllib.request
from datetime import date, timedelta

OUT = os.path.join("data", "nfl", "box", "belt_box.json")
URLS = [
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{y}.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_{y}.csv",
]
URL_ALL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
URL_DEF = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_def.csv"
COLS = {
    "CMP": ("completions",), "ATT": ("attempts",), "PYD": ("passing_yards",), "PTD": ("passing_tds",),
    "INT": ("passing_interceptions", "interceptions"), "CAR": ("carries",), "RYD": ("rushing_yards",),
    "RTD": ("rushing_tds",), "REC": ("receptions",), "TGT": ("targets",), "RECYD": ("receiving_yards",),
    "RECTD": ("receiving_tds",), "TKL": ("def_tackles_solo", "def_tackles"), "SCK": ("def_sacks",),
    "DINT": ("def_interceptions",), "FGM": ("fg_made",), "FGA": ("fg_att",),
}
ORDER = list(COLS)
NV = {"LA": "LAR", "STL": "LAR", "LV": "OAK", "SD": "LAC", "WAS": "WSH"}


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.read().decode("utf-8")
    except Exception as e:  # noqa: BLE001
        print("  miss", url, e)
        return None


def num(v):
    if v in (None, "", "NA"):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f.is_integer() else round(f, 1)


def pick(row, names):
    for n in names:
        if n in row and row[n] not in ("", "NA", None):
            return row[n]
    return None


SCHED = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"


def main():
    with open(os.path.join("data", "nfl", "lineage.json")) as f:
        d = json.load(f)
    # ---- nflverse's schedule: match each belt game by date (+/- 1 day) and final score
    t = get(SCHED)
    if not t:
        print("no nflverse schedule; nothing to do")
        return
    by = {}
    games = {}
    for row in csv.DictReader(io.StringIO(t)):
        if not row.get("home_score") or int(row.get("season") or 0) < 1999:
            continue
        hs, as_ = int(row["home_score"]), int(row["away_score"])
        games[row["game_id"]] = row
        for k in (-1, 0, 1):
            dd = (date.fromisoformat(row["gameday"]) + timedelta(days=k)).isoformat()
            by.setdefault((dd, max(hs, as_), min(hs, as_)), []).append(row)
    want = {}                    # nflverse game_id -> (belt n, flipped?)
    by_team = {}                 # (season, week, nflverse team) -> nflverse game_id
    seasons = set()
    for bg in d["belt_games"]:
        if bg["season"] < 1999:
            continue
        hp, ap = (int(x) for x in bg["score"].split("-"))
        cands = by.get((bg["date"], max(hp, ap), min(hp, ap)), [])
        if len(cands) != 1:
            continue
        row = cands[0]
        flipped = (int(row["home_score"]), int(row["away_score"])) != (hp, ap)
        want[row["game_id"]] = (bg["n"], flipped)
        for side in ("home_team", "away_team"):
            by_team[(int(row["season"]), int(row["week"]), row[side])] = row["game_id"]
        seasons.add(int(row["season"]))
    print(f"{len(want)} belt games since 1999 matched to nflverse games across {len(seasons)} seasons")
    texts = []
    for y in sorted(seasons):
        t = None
        for u in URLS:
            t = get(u.format(y=y))
            if t:
                break
        if t:
            texts.append(t)
        else:
            print("  no player file for", y)
    if not texts:
        print("per-season files missing; trying the all-years file")
        t = get(URL_ALL)
        texts = [t] if t else []
        dt = get(URL_DEF)
        if dt:
            texts.append(dt)
    out = {}
    first = True
    for t in texts:
        r = csv.DictReader(io.StringIO(t))
        if first:
            print("columns:", r.fieldnames[:14], "...")
            first = False
        for row in r:
            team = pick(row, ("team", "recent_team", "player_team")) or ""
            gid = row.get("game_id")
            if not gid:
                try:
                    gid = by_team.get((int(row.get("season") or 0), int(row.get("week") or 0), team))
                except ValueError:
                    gid = None
            hit = want.get(gid)
            if not hit:
                continue
            n, flipped = hit
            side = "h" if team == games[gid]["home_team"] else "a"
            if flipped:
                side = "a" if side == "h" else "h"
            pid = pick(row, ("player_id", "gsis_id"))
            name = pick(row, ("player_display_name", "player_name"))
            if not pid or pid in ("?", "0") or not name or name in ("?", "Team"):
                continue      # team-total rows ("Team") and rows with no player id (BH-5)
            stats = [num(pick(row, COLS[c])) for c in ORDER]
            g = out.setdefault(str(n), {"gid": gid, "players": {}})
            prev = g["players"].get(pid)
            if prev:   # merge (e.g. the separate defense file)
                prev[3:] = [a if a is not None else b for a, b in zip(prev[3:], stats)]
            elif any(v for v in stats):
                g["players"][pid] = [pid, name, side] + stats
    for g in out.values():
        g["players"] = list(g["players"].values())
    import box_store
    box_store.save_all("nfl", out, {str(bg["n"]): bg["season"] for bg in d["belt_games"]},
                       {"source": "https://github.com/nflverse/nflverse-data", "license": "CC-BY 4.0", "cols": ORDER})
    print(f"wrote {len(out)} belt games, {sum(len(g['players']) for g in out.values()):,} player lines")


if __name__ == "__main__":
    main()
