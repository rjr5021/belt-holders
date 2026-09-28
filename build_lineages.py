#!/usr/bin/env python3
"""
Compute every live league's belt lineage with the shared engine and write
data/<league>/lineage.json for build_site.py.

    python3 build_lineages.py            # fetch fresh data, rebuild all leagues
    python3 build_lineages.py --offline  # use the cached CSVs only

The engine (belt_engine.py) is the same file the College Football Belt
uses -- copy it over whenever the football repo's copy changes.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

import belt_engine
import belt_extras as X
import belt_models as M
from leagues import LIVE


def days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def build(league, refresh=True, today=None):
    today = today or date.today().isoformat()
    games, upcoming = league["load_games"](refresh=refresh)
    first_date = games[0]["date"]
    belt_games, reigns, vacancies = belt_engine.resolve_vacancies(
        games, league["tie_rule"], None, None, league["recent_teams"](games), today,
        gap_threshold_days=league.get("gap_days", belt_engine.GAP_THRESHOLD_DAYS),
        first_game_date=first_date)
    season_by_date = {}
    for g in games:
        season_by_date.setdefault(g["date"], g["season"])

    def season_at(d):
        if d in season_by_date:
            return season_by_date[d]
        earlier = [x for x in season_by_date if x <= d]
        return season_by_date[max(earlier)] if earlier else games[0]["season"]

    # --- tidy the reigns: numbering, lengths, era names --------------------
    counts = Counter()
    for r in reigns:
        counts[r["team"]] += 1
        r["reign_no"] = counts[r["team"]]
        end = r.get("end_date") or today
        r["days"] = max(0, days_between(r["start_date"], end))
        r["season"] = season_at(r["start_date"])
        r["end_season"] = season_at(r["end_date"]) if r.get("end_date") else None
        r["name"] = league["team_name"](r["team"], r["season"])
    for i, r in enumerate(reigns):
        r["index"] = i + 1

    current = reigns[-1]
    holder = current["team"]

    # --- the holder's next game ------------------------------------------
    next_game = None
    for g in upcoming:
        if holder in (g["home"], g["away"]) and g["date"] >= today:
            next_game = {**g, "holder": holder,
                         "challenger": g["away"] if g["home"] == holder else g["home"],
                         "holder_home": g["home"] == holder}
            break

    # --- records -----------------------------------------------------------
    total_days, n_reigns, n_def = defaultdict(int), Counter(), Counter()
    for r in reigns:
        total_days[r["team"]] += r["days"]
        n_reigns[r["team"]] += 1
        n_def[r["team"]] += r.get("defenses", 0)
    playoff_changes = sum(1 for bg in belt_games
                          if bg["outcome"] == "changed" and bg["season_type"] != "regular")
    records = {
        "most_days": sorted(total_days.items(), key=lambda kv: -kv[1])[:10],
        "most_reigns": n_reigns.most_common(10),
        "most_defenses_total": n_def.most_common(10),
        "longest_reigns": [
            {"team": r["team"], "name": r["name"], "start_date": r["start_date"], "season": r["season"],
             "end_date": r.get("end_date"), "defenses": r.get("defenses", 0), "days": r["days"]}
            for r in sorted(reigns, key=lambda r: (-r.get("defenses", 0), -r["days"]))[:10]],
        "playoff_changes": playoff_changes,
        "belt_games": len(belt_games),
        "programs": len(n_reigns),
    }

    recent = league["recent_teams"](games)
    X.annotate(league, games, belt_games, reigns)
    records.update(X.extra_records(league, belt_games, reigns, recent, today))
    # --- models: Elo, chance to defend, belt tree, outlook, champions, Losers Belt
    ratings, hfa = M.elo(league["key"], games)
    fut = [g for g in upcoming if g["date"] >= today]
    tree = M.belt_tree(holder, fut, ratings, hfa, 4, today) if fut else None
    reg = [g for g in fut if g.get("season_type", "regular") == "regular"]
    look = M.outlook(holder, reg, ratings, hfa, today=today) if reg else None
    preview = X.preview(league, games, belt_games, reigns, next_game, today)
    if preview and next_game:
        preview["holder_win_prob"] = round(M.win_prob(ratings, hfa, next_game["home"], next_game["away"],
                                                      next_game.get("neutral"), holder=holder), 3)
    top_elo = sorted(((t, round(v)) for t, v in ratings.items() if t in recent), key=lambda x: -x[1])
    models = {
        "elo": {t: round(v) for t, v in ratings.items() if t in recent},
        "elo_rank": top_elo, "hfa": hfa, "tree": tree, "outlook": look,
        "standings": M.standings(games, reigns),
        "champions": M.champions(games, reigns),
        "schedule": [[g["date"], g["home"], g["away"], g.get("kickoff") or g.get("start_et"), g.get("season_type", "regular"),
                      round(M.win_prob(ratings, hfa, g["home"], g["away"], g.get("neutral"), holder=holder), 3)]
                     for g in fut if holder in (g["home"], g["away"])][:40],
        "meet": {t: [g["date"], g["home"]] for g in reversed(fut) if holder in (g["home"], g["away"])
                 for t in [g["away"] if g["home"] == holder else g["home"]]},
        "what_if": M.what_if(league["key"], games, belt_games, reigns, league["tie_rule"], recent, today,
                              league.get("gap_days", belt_engine.GAP_THRESHOLD_DAYS)),
        "losers": M.losers(league["key"], games, league["tie_rule"], recent, today,
                           league.get("gap_days", belt_engine.GAP_THRESHOLD_DAYS)),
    }
    out = {
        "models": models,
        "seasons": X.seasons(league, games, belt_games, reigns, today),
        "rivalries": X.rivalries(league, belt_games),
        "preview": preview,
        "league": league["key"], "name": league["name"], "long_name": league["long_name"],
        "generated": today, "first_game": belt_games[0] if belt_games else None,
        "reigns": reigns, "belt_games": belt_games, "vacancies": vacancies,
        "current": current, "next_game": next_game,
        "status": league["season_status"](today, upcoming), "records": records,
    }
    os.makedirs(os.path.join("data", league["key"]), exist_ok=True)
    path = os.path.join("data", league["key"], "lineage.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"[{league['key']}] {len(reigns)} reigns, {len(belt_games)} belt games, "
          f"{len(vacancies)} vacancies; holder {current['name']} since {current['start_date']}"
          + (f"; next {next_game['date']} vs {next_game['challenger']}" if next_game else ""))
    return out


def main():
    refresh = "--offline" not in sys.argv
    for league in LIVE:
        build(league, refresh=refresh)


if __name__ == "__main__":
    main()
