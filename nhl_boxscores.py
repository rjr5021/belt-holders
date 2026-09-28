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
import urllib.request

OUT = os.path.join("data", "nhl", "box", "belt_box.json")
URL = "https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore"
MAX_PER_RUN = int(os.environ.get("NHL_BOX_MAX", "1500"))
ORDER = ["G", "A", "PTS", "PM", "PIM", "SOG", "HIT", "SV", "SA"]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


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
    data = {"source": "https://api-web.nhle.com", "cols": ORDER, "games": {}}
    if os.path.exists(OUT):
        with open(OUT) as f:
            data = json.load(f)
    games = data["games"]
    todo = [bg for bg in reversed(d["belt_games"]) if str(bg["n"]) not in games and str(bg.get("game_id", "")).isdigit()]
    print(f"{len(games):,} on file, {len(todo):,} to fetch; this run: up to {MAX_PER_RUN}")
    got = 0
    for bg in todo[:MAX_PER_RUN]:
        gid = bg["game_id"]
        j = get(URL.format(gid=gid))
        pbg = (j or {}).get("playerByGameStats") or {}
        players = rows(pbg.get("homeTeam") or {}, "h") + rows(pbg.get("awayTeam") or {}, "a")
        games[str(bg["n"])] = {"gid": gid, "players": players}
        got += bool(players)
        time.sleep(0.05)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    with_players = [int(k) for k, v in games.items() if v["players"]]
    print(f"fetched {min(len(todo), MAX_PER_RUN)} (with players: {got}); {len(with_players):,} belt games have box scores"
          + (f"; earliest belt game with one: #{min(with_players)}" if with_players else ""))


if __name__ == "__main__":
    main()
