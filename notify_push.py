#!/usr/bin/env python3
"""7.14: tell the belt-picks Worker about every belt's current reign so it can push "X takes the belt"
to that belt's subscribers (and to the every-belt list). The Worker de-dupes by belt + reign index, so
this runs on every deploy and only the reigns it has not seen trigger a notification.

Env: PICKS_API (the Worker's URL), NOTIFY_KEY (its secret). Both absent = nothing happens."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

from leagues import LIVE

API = (os.environ.get("PICKS_API") or "https://belt-picks.rjr5021.workers.dev").rstrip("/")
KEY = os.environ.get("NOTIFY_KEY") or ""
SITE = "https://beltholders.com"


def post(payload):
    req = urllib.request.Request(f"{API}/notify", data=json.dumps(payload).encode(), method="POST",
                                 headers={"content-type": "application/json", "x-notify-key": KEY})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    if not API or not KEY or "PLACEHOLDER" in API:
        print("notify_push: PICKS_API/NOTIFY_KEY not set, skipping")
        return
    sent = 0
    for lg in LIVE:
        p = os.path.join("data", lg["key"], "lineage.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        cur = d.get("current") or {}
        if not cur.get("team") or not cur.get("start_date"):
            continue
        if (date.today() - date.fromisoformat(cur["start_date"])).days > 3:
            continue        # old news: only a reign that started in the last three days is announced
        name = cur.get("name") or lg["team_name"](cur["team"], cur.get("season"))
        reign = f"{cur.get('index', '')}-{cur['start_date']}"
        won = f" Beat {lg['team_name'](cur['won_from'], cur.get('season'))} {cur.get('won_score', '').replace('-', '–')}." if cur.get("won_from") else ""
        title = f"{name} {'take' if not lg.get('singular') else 'takes'} the {lg['name']} belt"
        body = f"{won} Reign no. {cur.get('reign_no', '?')} for the {lg.get('unit_one', 'team')}; the belt's {cur.get('index', '?')}th holder.".strip()
        url = f"{SITE}/{lg['key']}/"
        for belt in (f"bh:{lg['key']}", "all"):
            try:
                r = post({"belt": belt, "reign": f"{lg['key']}-{reign}" if belt == "all" else reign, "title": title, "body": body, "url": url})
                if r.get("queued"):
                    sent += 1
                    print(f"[{lg['key']}] {belt}: queued {r['queued']} ({title})")
            except urllib.error.HTTPError as ex:   # the body says whether it was the Worker (JSON) or Cloudflare's edge (HTML)
                detail = ex.read(300).decode("utf-8", "replace").strip().replace("\n", " ")
                print(f"[{lg['key']}] {belt}: HTTP {ex.code}: {detail[:200]}")
            except Exception as ex:  # noqa: BLE001 -- never fail the deploy over a notification
                print(f"[{lg['key']}] {belt}: {type(ex).__name__}: {ex}")
    print(f"notify_push: {sent} notifications queued")


if __name__ == "__main__":
    main()
