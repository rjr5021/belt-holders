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


def main():
    with open(os.path.join("data", "nfl", "lineage.json")) as f:
        d = json.load(f)
    want = {}                      # (season, week, nflverse team) -> (n, side)
    seasons = set()
    for bg in d["belt_games"]:
        gid = str(bg.get("game_id") or "")
        parts = gid.split("_")
        if bg["season"] < 1999 or len(parts) != 4:
            continue
        s, w, away, home = int(parts[0]), int(parts[1]), parts[2], parts[3]
        want[(s, w, home)] = (bg["n"], "h", gid)
        want[(s, w, away)] = (bg["n"], "a", gid)
        seasons.add(s)
    print(f"{len(want) // 2} belt games since 1999 across {len(seasons)} seasons")
    out = {}
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
            texts = None
            break
    if texts is None:
        print("per-season files missing; trying the all-years file")
        t = get(URL_ALL)
        texts = [t] if t else []
        dt = get(URL_DEF)
        if dt:
            texts.append(dt)
    first = True
    for t in texts:
        r = csv.DictReader(io.StringIO(t))
        if first:
            print("columns:", r.fieldnames)
            first = False
        for row in r:
            try:
                s, w = int(row.get("season") or 0), int(row.get("week") or 0)
            except ValueError:
                continue
            team = pick(row, ("team", "recent_team", "player_team")) or ""
            hit = want.get((s, w, team))
            if not hit:
                continue
            n, side, gid = hit
            pid = pick(row, ("player_id", "gsis_id")) or "?"
            name = pick(row, ("player_display_name", "player_name")) or "?"
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
