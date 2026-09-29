#!/usr/bin/env python3
"""
MLB player box scores for belt games, from MLB's Stats API
(statsapi.mlb.com). Each season's schedule is fetched once (one call) to map
belt games to MLB game ids by date and final score; box scores are then
fetched a chunk per run (MAX_PER_RUN), newest first, and kept forever.

    data/mlb/box/belt_box.json   {belt game n: {"gid", "players": [...]}}
    data/mlb/box/pk_map.json     {belt game n: MLB game id or null}

Row: [player_id, name, side h/a, AB, R, H, HR, RBI, BB, SO, IP, HA, ER, K, BBA]
"""

import json
import os
import time
import urllib.request
from collections import defaultdict

BOX = os.path.join("data", "mlb", "box", "belt_box.json")
PKS = os.path.join("data", "mlb", "box", "pk_map.json")
SCHED = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={y}-02-01&endDate={y}-12-15&gameType=R,F,D,L,W,S"
BOXURL = "https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"
MAX_PER_RUN = int(os.environ.get("MLB_BOX_MAX", "1500"))
# Oldest season to fetch (BH-2/BH-15): matches features.BOX_PAGES_FROM["mlb"]; older box
# scores wouldn't be rendered, and each season adds to the repo and the site budget.
FROM_SEASON = int(os.environ.get("MLB_BOX_FROM", "1988"))
DEADLINE = time.time() + 60 * float(os.environ.get("BOX_MINUTES", "25"))   # stop and save before the job's time limit
ORDER = ["AB", "R", "H", "HR", "RBI", "BB", "SO", "IP", "HA", "ER", "K", "BBA"]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.loads(r.read().decode())
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


def load(p, default):
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else round(f, 1)


def main():
    with open(os.path.join("data", "mlb", "lineage.json")) as f:
        d = json.load(f)
    pks = load(PKS, {})
    import box_store
    games = box_store.load_all("mlb")
    # ---- map belt games to MLB game ids, a season at a time
    need = defaultdict(list)
    for bg in d["belt_games"]:
        if str(bg["n"]) in pks:
            continue
        gid = str(bg.get("game_id") or "")
        tail = gid.rsplit("-", 1)[-1]
        if tail.isdigit() and len(tail) >= 5:          # MLB API games carry the id already
            pks[str(bg["n"])] = int(tail)
        elif bg["season"] >= FROM_SEASON:
            need[bg["season"]].append(bg)
    def save():
        os.makedirs(os.path.dirname(BOX), exist_ok=True)
        with open(PKS, "w") as f:
            json.dump(pks, f, separators=(",", ":"))
        box_store.save_all("mlb", games, {str(bg["n"]): bg["season"] for bg in d["belt_games"]},
                           {"source": "https://statsapi.mlb.com", "cols": ORDER})

    for y in sorted(need, reverse=True):
        if time.time() > DEADLINE:
            print("time budget reached while mapping seasons; the rest next run")
            break
        j = get(SCHED.format(y=y))
        if not j:
            print(f"{y}: schedule unavailable; will retry next run")
            continue
        by = defaultdict(list)
        for dt in (j or {}).get("dates", []):
            for g in dt.get("games", []):
                t = g.get("teams") or {}
                hs, as_ = (t.get("home") or {}).get("score"), (t.get("away") or {}).get("score")
                if hs is not None and as_ is not None:
                    by[dt["date"]].append((g["gamePk"], hs, as_))
        for bg in need[y]:
            hp, ap = (int(x) for x in bg["score"].split("-"))
            hit = next((pk for pk, hs, as_ in by.get(bg["date"], []) if (hs, as_) == (hp, ap)), None)
            if hit is None:
                hit = next((pk for pk, hs, as_ in by.get(bg["date"], []) if (hs, as_) == (ap, hp)), None)
            pks[str(bg["n"])] = hit
        print(f"{y}: mapped {sum(1 for bg in need[y] if pks.get(str(bg['n'])))} of {len(need[y])}")
        time.sleep(0.1)
    # ---- box scores, newest first
    todo = [bg for bg in reversed(d["belt_games"]) if str(bg["n"]) not in games and pks.get(str(bg["n"])) and bg["season"] >= FROM_SEASON]
    print(f"{len(games):,} box scores on file, {len(todo):,} to fetch; this run: up to {MAX_PER_RUN}")
    for i, bg in enumerate(todo[:MAX_PER_RUN]):
        if time.time() > DEADLINE:
            print(f"time budget reached after {i} box scores; the rest next run")
            break
        if i and i % 200 == 0:
            save()
        pk = pks[str(bg["n"])]
        j = get(BOXURL.format(pk=pk))
        if j is None:
            continue          # couldn't reach it: try again next run
        players = []
        for side, key in (("h", "home"), ("a", "away")):
            for p in ((j.get("teams") or {}).get(key) or {}).get("players", {}).values():
                st = p.get("stats") or {}
                bat, pit = st.get("batting") or {}, st.get("pitching") or {}
                if not bat and not pit:
                    continue
                person = p.get("person") or {}
                players.append([person.get("id"), person.get("fullName") or "?", side,
                                num(bat.get("atBats")), num(bat.get("runs")), num(bat.get("hits")), num(bat.get("homeRuns")),
                                num(bat.get("rbi")), num(bat.get("baseOnBalls")), num(bat.get("strikeOuts")),
                                num(pit.get("inningsPitched")), num(pit.get("hits")), num(pit.get("earnedRuns")),
                                num(pit.get("strikeOuts")), num(pit.get("baseOnBalls"))])
        games[str(bg["n"])] = {"gid": pk, "players": players}
        time.sleep(0.05)
    save()
    have = [int(k) for k, v in games.items() if v["players"]]
    print(f"{len(have):,} belt games with box scores" + (f"; earliest #{min(have)}" if have else ""))


if __name__ == "__main__":
    main()
