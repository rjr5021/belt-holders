#!/usr/bin/env python3
"""
NBA player box scores for belt games, from Eoin Moore's CC0 Kaggle dataset
"Historical NBA Data and Player Box Scores" (every game since 1947,
updated nightly):
https://www.kaggle.com/datasets/eoinamoore/historical-nba-data-and-player-box-scores

Runs in GitHub Actions with KAGGLE_USERNAME / KAGGLE_KEY secrets. Downloads
Games.csv and PlayerStatistics.csv, matches every NBA belt game (from
data/nba/lineage.json) to the dataset's game by date and final score, and
keeps only those games' player lines:

    data/nba/box/belt_box.json   {belt game n: {"gid", "players": [...]}}

Each player row: [personId, name, side ("h"/"a"), minutes, pts, reb, ast,
stl, blk, fgm, fga, tpm, tpa, ftm, fta].  Missing stats are null (early
seasons didn't track rebounds, steals, blocks, etc.).

    python3 nba_boxscores.py            # download + rebuild
    python3 nba_boxscores.py --local D  # use CSVs already in folder D
"""

import csv
import io
import json
import os
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import date, timedelta

DATASET = "eoinamoore/historical-nba-data-and-player-box-scores"
OUT = os.path.join("data", "nba", "box", "belt_box.json")
csv.field_size_limit(10 ** 8)


def fetch(dest):
    os.makedirs(dest, exist_ok=True)
    for f in ("Games.csv", "PlayerStatistics.csv"):
        if os.path.exists(os.path.join(dest, f)):
            continue
        subprocess.run(["kaggle", "datasets", "download", "-d", DATASET, "-f", f, "-p", dest, "--force"], check=True)
        z = os.path.join(dest, f + ".zip")
        if os.path.exists(z):
            with zipfile.ZipFile(z) as zz:
                zz.extractall(dest)
            os.remove(z)
    print("files:", os.listdir(dest))


def pick(row, *names):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


def num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f.is_integer() else round(f, 1)


def main():
    src = sys.argv[sys.argv.index("--local") + 1] if "--local" in sys.argv else "kaggle_nba"
    if "--local" not in sys.argv:
        fetch(src)
    with open(os.path.join("data", "nba", "lineage.json")) as f:
        d = json.load(f)
    belt = [bg for bg in d["belt_games"]]

    # --- index the dataset's games by date -> [(gid, home pts, away pts)]
    games = defaultdict(list)
    with open(os.path.join(src, "Games.csv"), newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        print("Games.csv columns:", r.fieldnames)
        for row in r:
            gid = pick(row, "gameId", "GAME_ID", "game_id")
            dt = (pick(row, "gameDate", "gameDateTimeEst", "GAME_DATE", "date") or "")[:10]
            hs, as_ = num(pick(row, "homeScore", "home_score", "PTS_home")), num(pick(row, "awayScore", "away_score", "PTS_away"))
            if gid and dt and hs is not None and as_ is not None:
                games[dt].append((gid, hs, as_))
    print(f"indexed {sum(len(v) for v in games.values()):,} games")

    # --- match belt games by date (+/- 1 day for time zones) and score
    match = {}
    for bg in belt:
        hp, ap = (int(x) for x in bg["score"].split("-"))
        dd = date.fromisoformat(bg["date"])
        found = None
        for off in (0, -1, 1):
            for gid, hs, as_ in games.get((dd + timedelta(days=off)).isoformat(), []):
                if (hs, as_) == (hp, ap):
                    found = (gid, "same")
                elif (hs, as_) == (ap, hp):
                    found = (gid, "flip")   # neutral/home-flag differences
                if found:
                    break
            if found:
                break
        if found:
            match[str(found[0])] = (bg["n"], found[1])
    print(f"matched {len(match):,} of {len(belt):,} belt games")

    # --- stream player lines for matched games
    out = defaultdict(lambda: {"players": []})
    with open(os.path.join(src, "PlayerStatistics.csv"), newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        print("PlayerStatistics.csv columns:", r.fieldnames)
        for row in r:
            gid = pick(row, "gameId", "GAME_ID", "game_id")
            if gid not in match:
                continue
            n, orient = match[gid]
            home = str(pick(row, "home", "isHome") or "").strip().lower() in ("1", "true", "1.0", "home")
            side = "h" if home else "a"
            if orient == "flip":
                side = "a" if side == "h" else "h"
            name = (pick(row, "firstName") or "") + " " + (pick(row, "lastName") or "")
            name = name.strip() or pick(row, "playerName", "PLAYER_NAME") or "?"
            mins = pick(row, "numMinutes", "minutes", "MIN")
            if isinstance(mins, str) and ":" in mins:
                a, b_ = mins.split(":")[:2]
                mins = round(int(a) + int(b_) / 60, 1) if a.isdigit() and b_.isdigit() else None
            else:
                mins = num(mins)
            out[n]["gid"] = gid
            out[n]["players"].append([
                pick(row, "personId", "PLAYER_ID", "playerId"), name, side, mins,
                num(pick(row, "points", "PTS")), num(pick(row, "reboundsTotal", "REB", "rebounds")),
                num(pick(row, "assists", "AST")), num(pick(row, "steals", "STL")), num(pick(row, "blocks", "BLK")),
                num(pick(row, "fieldGoalsMade", "FGM")), num(pick(row, "fieldGoalsAttempted", "FGA")),
                num(pick(row, "threePointersMade", "FG3M")), num(pick(row, "threePointersAttempted", "FG3A")),
                num(pick(row, "freeThrowsMade", "FTM")), num(pick(row, "freeThrowsAttempted", "FTA"))])
    import box_store
    res = {str(k): v for k, v in sorted(out.items())}
    box_store.save_all("nba", res, {str(bg["n"]): bg["season"] for bg in belt},
                       {"source": f"https://www.kaggle.com/datasets/{DATASET}", "license": "CC0"})
    first = min((int(k) for k in res), default=None)
    print(f"wrote box scores for {len(res):,} belt games ({sum(len(v['players']) for v in res.values()):,} player lines)"
          + (f"; earliest belt game with a box score: #{first}" if first else ""))


if __name__ == "__main__":
    main()
