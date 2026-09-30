#!/usr/bin/env python3
"""
NET-2: catch data feeds that stopped quietly. Every fetch step in the workflows is
continue-on-error, so a blocked source used to freeze a belt while the site kept
saying "In season". Run after the data updates and before build_site.py:

    python check_freshness.py          # writes data/health.json, prints a summary

A league is flagged "delayed" when
  * a game on its schedule is from yesterday or earlier (checked from 9 a.m. Eastern, so
    last night's late games have finished) with no result, and no result at all has come
    in since that date (a single postponed game doesn't trip it), or
  * it's in season, results were coming in, and the newest is more than STALE_DAYS old
    (a season opener after a summer break doesn't trip it).
build_site.py shows a "Data delayed" pill on that league's tile and page and puts the
flag in api/current.json; the deploy workflow opens (or comments on) a GitHub issue.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

STALE_DAYS = 16          # longer than any in-season gap (international breaks, All-Star breaks)


def overdue_cutoff(now_et):
    """Scheduled games on or before this date should have a result by now: yesterday once
    it's 9 a.m. Eastern (every game from last night is over), otherwise the day before."""
    return now_et.date() - timedelta(days=1 if now_et.hour >= 9 else 2)


def check(lg, today, cutoff=None):
    try:
        games, upcoming = lg["load_games"](refresh=False)
    except TypeError:
        games, upcoming = lg["load_games"]()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"couldn't load games: {type(e).__name__}"}
    newest = max((g["date"] for g in games), default="")
    cutoff = cutoff or (today - timedelta(days=2))
    overdue = sorted(g["date"] for g in upcoming if g["date"] <= cutoff.isoformat())
    status = lg["season_status"](today.isoformat(), [g for g in upcoming if g["date"] >= today.isoformat()])
    if overdue and newest < overdue[0]:
        return {"ok": False, "newest_result": newest,
                "reason": f"{len(overdue)} scheduled game(s) since {overdue[0]} have no result, and nothing newer has come in"}
    # in season, results have been arriving, and then stopped for longer than any normal break
    if (status == "In season" and newest and newest < (today - timedelta(days=STALE_DAYS)).isoformat()
            and any(g["date"] > (today - timedelta(days=STALE_DAYS * 3)).isoformat() for g in games)):
        return {"ok": False, "newest_result": newest, "reason": f"in season, but the newest result is from {newest}"}
    return {"ok": True, "newest_result": newest}


def main():
    from leagues import LIVE
    now_et = datetime.now(ZoneInfo("America/New_York"))
    today = now_et.date()
    out = {"checked": today.isoformat(), "leagues": {}}
    for lg in LIVE:
        out["leagues"][lg["key"]] = check(lg, today, overdue_cutoff(now_et))
    bad = {k: v for k, v in out["leagues"].items() if not v["ok"]}
    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "health.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    for k, v in out["leagues"].items():
        print(f"{'ok     ' if v['ok'] else 'DELAYED'} {k:11} newest result {v.get('newest_result', '?')}" + ("" if v["ok"] else f" -- {v['reason']}"))
    if bad and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### Data delayed\n" + "".join(f"- **{k}**: {v['reason']}\n" for k, v in bad.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
