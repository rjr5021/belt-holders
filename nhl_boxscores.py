#!/usr/bin/env python3
"""
NHL player stat lines for belt games, from the NHL's own game-center box
scores (api-web.nhle.com/v1/gamecenter/<id>/boxscore). Our NHL game ids are
the NHL's, so no matching is needed. The first runs backfill a chunk at a
time (MAX_PER_RUN); after that each run only fetches new belt games.

    data/nhl/box/belt_box.json   {belt game n: {"gid", "players": [...]}}

Row: [player_id, name, side h/a, G, A, PTS, +/-, PIM, SOG, HIT, SV, SA]
Games the NHL has no player stats for are stored with an empty list so they
aren't asked for again.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = os.path.join("data", "nhl", "box", "belt_box.json")
URL = "https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore"
MAX_PER_RUN = int(os.environ.get("NHL_BOX_MAX", "1500"))
DEADLINE = time.time() + 60 * float(os.environ.get("BOX_MINUTES", "25"))   # stop and save before the job's time limit
ORDER = ["G", "A", "PTS", "PM", "PIM", "SOG", "HIT", "SV", "SA"]


UA = {"User-Agent": "Mozilla/5.0 (compatible; beltholders.com box scores; +https://beltholders.com/about/)",
      "Accept": "application/json"}
ERRORS = []


def get(url, tries=3):
    # BH-15: the NHL API turns away Python's default user agent, so every request in CI failed
    # quietly and nothing was ever saved. Send a real UA and keep the last error for the log.
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            ERRORS.append(f"HTTP {e.code}")
            time.sleep(2 * (i + 1))
        except Exception as e:  # noqa: BLE001
            ERRORS.append(type(e).__name__ + ": " + str(e)[:80])
            time.sleep(2 * (i + 1))
    return False          # couldn't reach it (not a 404): try again next run


def n_(v):
    return v if isinstance(v, (int, float)) else None


def rows(team_block, side):
    out = []
    for grp in ("forwards", "defense"):
        for p in team_block.get(grp) or []:
            nm = (p.get("name") or {}).get("default") or "?"
            out.append([p.get("playerId"), nm, side, n_(p.get("goals")), n_(p.get("assists")), n_(p.get("points")),
                        n_(p.get("plusMinus")), n_(p.get("pim")), n_(p.get("sog")), n_(p.get("hits")), None, None])
    for p in team_block.get("goalies") or []:
        nm = (p.get("name") or {}).get("default") or "?"
        sa = p.get("shotsAgainst")
        if isinstance(sa, str) and "/" in sa:
            sv, sa = (int(x) for x in sa.split("/")[:2])
        else:
            sv = p.get("saves")
        out.append([p.get("playerId"), nm, side, n_(p.get("goals")), n_(p.get("assists")), n_(p.get("points")),
                    None, n_(p.get("pim")), None, None, n_(sv), n_(sa)])
    return [r for r in out if r[0] is not None]


def main():
    with open(os.path.join("data", "nhl", "lineage.json")) as f:
        d = json.load(f)
    import box_store
    games = box_store.load_all("nhl")
    todo = [bg for bg in reversed(d["belt_games"]) if str(bg["n"]) not in games and str(bg.get("game_id", "")).isdigit()]
    print(f"{len(games):,} on file, {len(todo):,} to fetch; this run: up to {MAX_PER_RUN}")
    got = failed = 0
    season_of = {str(bg["n"]): bg["season"] for bg in d["belt_games"]}
    meta = {"source": "https://api-web.nhle.com", "cols": ORDER}
    for i, bg in enumerate(todo[:MAX_PER_RUN]):
        if time.time() > DEADLINE:
            print(f"time budget reached after {i} games; the rest next run")
            break
        if i and i % 200 == 0:
            box_store.save_all("nhl", games, season_of, meta)
        gid = bg["game_id"]
        j = get(URL.format(gid=gid))
        if j is False:
            failed += 1
            continue
        pbg = (j or {}).get("playerByGameStats") or {}
        players = rows(pbg.get("homeTeam") or {}, "h") + rows(pbg.get("awayTeam") or {}, "a")
        games[str(bg["n"])] = {"gid": gid, "players": players}
        got += bool(players)
        time.sleep(0.05)
    box_store.save_all("nhl", games, season_of, meta)
    with_players = [int(k) for k, v in games.items() if v["players"]]
    print(f"fetched this run (with players: {got}); {len(with_players):,} belt games have box scores"
          + (f"; earliest belt game with one: #{min(with_players)}" if with_players else ""))
    if failed:
        print(f"{failed} requests failed; last errors: {sorted(set(ERRORS[-20:]))}")
    if failed and not got and todo:
        print("::error::NHL box scores: every request failed this run (see errors above)")
        sys.exit(1)


if __name__ == "__main__":
    main()
