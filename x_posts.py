#!/usr/bin/env python3
"""
Belt-game posts for @thebeltholders on X (2026-09-30, Bob: preview / start / end
posts, kept to a sensible volume across all the pro belts).

What it posts, per enabled league (X_LEAGUES, default "nhl"):
  * one "belts on the line today" post each morning listing every enabled belt game
    that day, with the start time and the holder's chance to defend;
  * a start post only for leagues in X_START_LEAGUES (default "nfl");
  * one "belt in danger" post when the holder is trailing late (or the game goes to
    sudden-death overtime);
  * an end post for every belt game: a short line for a defense, the full treatment
    (card image) for a title change.
X bills a post with a link at about 13x a plain one, so only the morning post, start
posts and title changes carry a link to the site; danger posts and defenses don't.

Where the facts come from:
  * which belts are on the line today, holders, defenses, start times and win
    probabilities: the live site's https://beltholders.com/api/network.json;
  * the game itself (state, clock, score): ESPN's public scoreboard, the same feed
    the site's live score box reads.

    python x_posts.py            # one pass: morning post if due, then any game updates
    python x_posts.py --watch    # keep polling while a belt game is live (the workflow)

Posting needs X_API_KEY / X_API_KEY_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET
(the @thebeltholders app, as repository secrets) AND X_LIVE=1. Without both, every
post is printed instead ("dry run"), so the whole thing can be tested safely.
State (what has been posted) lives in data/x/state.json, committed after each post.
"""

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SITE = "https://beltholders.com"
ET = ZoneInfo("America/New_York")
STATE = os.path.join("data", "x", "state.json")
LEAGUES = [x for x in os.environ.get("X_LEAGUES", "nhl").replace(",", " ").split() if x]
START_LEAGUES = set(os.environ.get("X_START_LEAGUES", "nfl").replace(",", " ").split())
DIGEST_FROM, DIGEST_UNTIL = 9, 13          # ET hours the morning post may go out ...
# ... or later, as long as no belt game has started yet. GitHub's scheduler can skip whole
# hours (2026-10-03: no run between 4 AM and 2:18 PM ET), and a missed 9-1 window used to
# mean no morning post at all; it now goes out on the first run before puck drop.
WATCH_BEFORE = timedelta(minutes=20)        # start watching this long before a game
WATCH_MAX = timedelta(hours=5, minutes=30)  # a job never runs longer than this
POLL = 60                                   # seconds between scoreboard checks while live
REQUIRED = ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
LIVE = os.environ.get("X_LIVE") == "1" and all(os.environ.get(k) for k in REQUIRED)

ESPN = {"nfl": "football/nfl", "nba": "basketball/nba", "nhl": "hockey/nhl", "mlb": "baseball/mlb",
        "wnba": "basketball/wnba", "mls": "soccer/usa.1", "nwsl": "soccer/usa.nwsl", "epl": "soccer/eng.1",
        "laliga": "soccer/esp.1", "seriea": "soccer/ita.1", "bundesliga": "soccer/ger.1", "ligue1": "soccer/fra.1",
        "eredivisie": "soccer/ned.1", "cfl": "football/cfl"}
SPORT = {"nfl": "football", "cfl": "football", "nba": "basketball", "wnba": "basketball", "nhl": "hockey",
         "pwhl": "hockey", "mlb": "baseball"}          # everything else: soccer
EMOJI = {"football": "\U0001F3C8", "basketball": "\U0001F3C0", "hockey": "\U0001F3D2", "baseball": "⚾", "soccer": "⚽"}
SINGULAR = {"mls", "nwsl", "epl", "laliga", "seriea", "bundesliga", "ligue1", "eredivisie", "intl"}  # club names take "defends"
TWEET_MAX = 280


# ------------------------------------------------------------------ helpers --

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; beltholders.com X posts)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    print(f"  GET failed: {url} ({err})")
    return None


def now_et():
    return datetime.now(ET)


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\b(fc|cf|afc|sc|the)\b|[^a-z0-9]", "", s)


def tweet_length(text):
    """X counts every URL as 23 characters."""
    return len(re.sub(r"https?://\S+", "x" * 23, text))


def link(url, campaign):
    return f"{url}{'&' if '?' in url else '?'}utm_source=x&utm_medium=social&utm_campaign={campaign}"


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def time_12h(hhmm):
    if not hhmm:
        return "time TBA"
    h, m = (int(x) for x in hhmm.split(":")[:2])
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'} ET"


def verb(lg, plural_form, singular_form):
    return singular_form if lg in SINGULAR else plural_form


# -------------------------------------------------------------------- state --

def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"digest": "", "games": {}, "log": []}


def save_state(st):
    if not LIVE:
        return
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    st["log"] = st.get("log", [])[-60:]
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    if os.environ.get("GITHUB_ACTIONS"):
        # commit right away, so a job that gets cut off never posts the same thing twice
        subprocess.run(["git", "add", STATE], check=False)
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "commit", "-q", "-m", "X posts state [skip ci]"], check=False)
            for i in range(4):
                if subprocess.run(["git", "pull", "-q", "--rebase", "-X", "theirs"]).returncode == 0 and \
                        subprocess.run(["git", "push", "-q"]).returncode == 0:
                    break
                subprocess.run(["git", "rebase", "--abort"], stderr=subprocess.DEVNULL)
                time.sleep(5 * (i + 1))


def sync_remote(st):
    """Merge in what main already records as posted. Runs pile up behind the one
    watching a live game (concurrency x-posts), and a queued scheduled run checks
    out the commit from when it was *scheduled*, so its copy of state.json can be
    missing the final the watcher just posted. This is the last check before any
    post goes out. (2026-10-02: the SJS-FLA final posted twice, at 12:57 and
    12:58 AM ET, run #111 after the watcher.)"""
    if not (LIVE and os.environ.get("GITHUB_ACTIONS")):
        return st
    try:
        branch = os.environ.get("GITHUB_REF_NAME") or "main"
        if subprocess.run(["git", "fetch", "-q", "origin", branch], timeout=60).returncode:
            return st
        out = subprocess.run(["git", "show", f"origin/{branch}:{STATE}"], capture_output=True, text=True, timeout=30)
        if out.returncode:
            return st
        remote = json.loads(out.stdout)
        if (remote.get("digest") or "") > (st.get("digest") or ""):
            st["digest"] = remote["digest"]
        for key, flags in (remote.get("games") or {}).items():
            mine = st.setdefault("games", {}).setdefault(key, {})
            for k, v in flags.items():
                mine.setdefault(k, v)
    except Exception as e:  # noqa: BLE001
        print(f"  (couldn't read the state on main: {e})")
    return st


# --------------------------------------------------------------------- post --

_client = {}


def post(text, image=None, kind=""):
    """Post to X (or print, in a dry run). Returns True when it went out."""
    n = tweet_length(text)
    if n > TWEET_MAX:
        print(f"  !! {kind} post is {n} characters; trimming")
        text = text[:TWEET_MAX - 1] + "…"
    if not LIVE:
        print(f"\n--- [dry run] {kind} post ({n} chars){' + image ' + image if image else ''} ---\n{text}\n---")
        return True
    import tweepy
    if not _client:
        _client["v2"] = tweepy.Client(consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_KEY_SECRET"],
                                      access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"])
        _client["v1"] = tweepy.API(tweepy.OAuth1UserHandler(os.environ["X_API_KEY"], os.environ["X_API_KEY_SECRET"],
                                                            os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_TOKEN_SECRET"]))
    media = None
    if image and os.path.exists(image):
        try:
            media = [_client["v1"].media_upload(image).media_id]
        except Exception as e:  # noqa: BLE001  -- post without the card rather than not at all
            print(f"  card upload failed ({e}); posting text only")
    try:
        _client["v2"].create_tweet(text=text, media_ids=media)
        print(f"  posted {kind}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  !! post failed ({kind}): {e}")
        return False


# --------------------------------------------------------------------- data --

def todays_belt_games(day):
    """The enabled belts with a game on `day` (ET), from the live site."""
    net = get(f"{SITE}/api/network.json") or {}
    out = []
    for b in net.get("belts") or []:
        nx = b.get("next") or {}
        if b.get("key") in LEAGUES and b.get("ok") and nx.get("date") == day.isoformat():
            out.append({"lg": b["key"], "belt": b.get("short") or b["key"].upper(), "name": b.get("name"),
                        "holder": b["holder"], "holder_short": b.get("holder_short") or b["holder"],
                        "defenses": int(b.get("defenses") or 0), "since": b.get("since"), "reign_no": b.get("reign_no"),
                        "opponent": nx.get("opponent"), "opponent_short": nx.get("opponent_short") or nx.get("opponent"),
                        "home": bool(nx.get("home")), "neutral": bool(nx.get("neutral")), "time_et": nx.get("time_et"),
                        "tv": nx.get("tv"), "win_prob": nx.get("win_prob"), "url": b.get("url") or f"{SITE}/{b['key']}/",
                        "next_url": nx.get("url"), "colors": b.get("colors") or []})
    return out


def espn_event(g, day):
    """This belt game on ESPN's scoreboard: {state, period, clock, holder_score, opp_score, ...} or None."""
    path = ESPN.get(g["lg"])
    if not path:
        return None
    j = get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={day.strftime('%Y%m%d')}&limit=400")
    hk, ok = {fold(g["holder"]), fold(g["holder_short"])}, {fold(g["opponent"]), fold(g["opponent_short"])}
    for ev in (j or {}).get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        if len(teams) != 2:
            continue

        def names(t):
            tm = t.get("team") or {}
            return {fold(tm.get(k)) for k in ("displayName", "shortDisplayName", "name", "location") if tm.get(k)}
        h = next((t for t in teams if names(t) & hk), None)
        o = next((t for t in teams if t is not h and names(t) & ok), None)
        if not h or not o:
            continue
        st = (comp.get("status") or ev.get("status") or {})
        typ = st.get("type") or {}
        return {"id": ev.get("id"), "state": typ.get("state"), "completed": bool(typ.get("completed")),
                "detail": typ.get("shortDetail") or typ.get("detail") or "", "period": st.get("period") or 0,
                "clock": st.get("displayClock") or "", "hs": int(float(h.get("score") or 0)), "os": int(float(o.get("score") or 0)),
                "o_color": "#" + ((o.get("team") or {}).get("color") or "333333"),
                "o_alt": "#" + ((o.get("team") or {}).get("alternateColor") or "d6b06a"),
                "start": ev.get("date")}
    return None


def clock_minutes(clock):
    try:
        if ":" in clock:
            m, s = clock.split(":")[:2]
            return int(m) + int(float(s)) / 60
        return float(re.sub(r"[^0-9.]", "", clock) or 0)
    except ValueError:
        return 99


def in_danger(lg, ev):
    """The holder is trailing late, or it's sudden death."""
    sport = SPORT.get(lg, "soccer")
    p, left = ev["period"], clock_minutes(ev["clock"])
    trailing = ev["hs"] < ev["os"]
    if sport == "hockey":
        return (p == 3 and trailing and left <= 10) or (p >= 4 and ev["hs"] == ev["os"])
    if sport == "basketball":
        return p >= 4 and trailing and left <= 5
    if sport == "football":
        return p >= 4 and trailing and left <= 5
    if sport == "baseball":
        return p >= 8 and trailing
    return trailing and clock_minutes(ev["clock"]) >= 75       # soccer: the clock counts up


# -------------------------------------------------------------------- posts --

def digest_text(games):
    lines = []
    for g in games:
        where = "vs." if g["home"] or g["neutral"] else "at"
        prob = f" ({round(g['win_prob'] * 100)}% to defend)" if g.get("win_prob") is not None else ""
        lines.append(f"{EMOJI[SPORT.get(g['lg'], 'soccer')]} {g['belt']}: {g['holder_short']} {where} {g['opponent_short']}, {time_12h(g['time_et'])}{prob}")
    head = "\U0001F3C6 Belts on the line today\n\n"
    tail = "\n\n" + link(f"{SITE}/today/", "digest")
    shown = list(lines)
    while shown and tweet_length(head + "\n".join(shown) + tail) > TWEET_MAX:
        shown.pop()
    more = len(lines) - len(shown)
    body = "\n".join(shown) + (f"\n+{more} more" if more else "")
    return head + body + tail


def start_text(g):
    where = "vs." if g["home"] or g["neutral"] else "at"
    return (f"{EMOJI[SPORT.get(g['lg'], 'soccer')]} UNDERWAY — the {g['belt']} belt is on the line\n\n"
            f"{g['holder']} {where} {g['opponent']}.\n\n"
            f"{g['holder_short']}: {ordinal(g['defenses'] + 1)} defense of the reign.\n\n"
            + link(g["next_url"] or g["url"], "live-start"))


def danger_text(g, ev):
    if ev["hs"] == ev["os"]:
        head = f"\U0001F6A8 SUDDEN DEATH — next goal decides the {g['belt']} belt"
    else:
        head = f"\U0001F6A8 BELT IN DANGER — {g['holder_short']} {verb(g['lg'], 'trail', 'trails')} late"
    return f"{head}\n\n{g['holder_short']} {ev['hs']}, {g['opponent_short']} {ev['os']} ({ev['detail']})."


def end_text(g, ev):
    note = ""
    m = re.search(r"\b(OT|SO|\d?OT)\b", ev["detail"] or "")
    if m:
        note = f" ({m.group(1)})"
    url = link(g["url"], "live-final")
    if ev["hs"] > ev["os"] or (ev["hs"] == ev["os"] and "SO" not in note):
        n = g["defenses"] + 1
        if ev["hs"] == ev["os"]:
            return (f"\U0001F6E1️ FINAL — a draw, and {g['holder']} {verb(g['lg'], 'keep', 'keeps')} the {g['belt']} belt\n\n"
                    f"{g['holder_short']} {ev['hs']}, {g['opponent_short']} {ev['os']}. Defense #{n} of the reign.")
        return (f"\U0001F6E1️ FINAL — {g['holder']} {verb(g['lg'], 'defend', 'defends')} the {g['belt']} belt\n\n"
                f"{g['holder_short']} {ev['hs']}, {g['opponent_short']} {ev['os']}{note}. Defense #{n} of the reign.")
    days = (date.fromisoformat(ev["day"]) - date.fromisoformat(g["since"])).days if g.get("since") else None
    who = g["holder_short"] + ("'" if g["holder_short"].endswith("s") else "'s")
    defs = "without a successful defense" if not g["defenses"] else f"with {g['defenses']} defense{'s' if g['defenses'] != 1 else ''}"
    reign = f"\n\nThe {who} reign ends after {days} day{'s' if days != 1 else ''}, {defs}." if days is not None else ""
    if g["lg"] in SINGULAR:
        reign = reign.replace("The ", "", 1)
    return (f"\U0001F3C6 NEW CHAMPION — the {g['belt']} belt has changed hands\n\n"
            f"{g['opponent']} {ev['os']}, {g['holder']} {ev['hs']}{note}.{reign}\n\n{url}")


def champion_card(g, ev):
    try:
        import og_images
        path = os.path.join("/tmp", f"x-card-{g['lg']}.png")
        og_images.card(path, g["belt"], g["opponent"], ev["day"], 0, ev["o_color"], ev["o_alt"], "beltholders.com",
                       kicker="NEW CHAMPION")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"  no card ({e})")
        return None


# ---------------------------------------------------------------------- run --

def digest_window_open(n, day, games):
    """The morning post may go out from DIGEST_FROM until the day's first belt game starts
    (or until DIGEST_UNTIL when no start time is known)."""
    if n.hour < DIGEST_FROM:
        return False
    starts = [datetime.combine(day, datetime.strptime(g["time_et"], "%H:%M").time(), ET)
              for g in games if g.get("time_et")]
    if not starts:
        return n.hour < DIGEST_UNTIL
    return n < min(starts)


def one_pass(st, day):
    """Returns True while any of today's belt games still needs watching."""
    n = now_et()
    games = todays_belt_games(day)
    # keep today's games in the state: after a title change the site's "next game"
    # moves on, but the end post still has to go out
    known = st.setdefault("today", {})
    if known.get("day") != day.isoformat():
        known.clear()
        known["day"] = day.isoformat()
        known["games"] = []
    for g in games:
        if not any(x["lg"] == g["lg"] for x in known["games"]):
            known["games"].append(g)
    games = known["games"]

    if games and st.get("digest") != day.isoformat() and digest_window_open(n, day, games) \
            and sync_remote(st).get("digest") != day.isoformat():
        if post(digest_text(games), kind="morning"):
            st["digest"] = day.isoformat()
            st.setdefault("log", []).append([n.isoformat(timespec="minutes"), "digest", len(games)])
            save_state(st)

    watching = False
    for g in games:
        key = f"{g['lg']}|{day.isoformat()}|{fold(g['holder'])}|{fold(g['opponent'])}"
        done = st.setdefault("games", {}).setdefault(key, {})
        if done.get("end"):
            continue
        start = datetime.combine(day, datetime.strptime(g["time_et"] or "19:00", "%H:%M").time(), ET)
        if n < start - WATCH_BEFORE:
            continue            # not yet: the next scheduled run (every 15 minutes) picks it up
        ev = espn_event(g, day)
        if not ev:
            print(f"  {key}: not on ESPN's scoreboard yet")
            watching = True
            continue
        ev["day"] = day.isoformat()
        print(f"  {key}: {ev['state']} {ev['detail']} {g['holder_short']} {ev['hs']}-{ev['os']}")
        if ev["state"] == "in" and not done.get("start") and g["lg"] in START_LEAGUES \
                and not sync_remote(st)["games"][key].get("start"):
            if post(start_text(g), kind=f"{g['lg']} start"):
                done["start"] = n.isoformat(timespec="minutes")
                save_state(st)
        if ev["state"] == "in" and not done.get("danger") and in_danger(g["lg"], ev) \
                and not sync_remote(st)["games"][key].get("danger"):
            if post(danger_text(g, ev), kind=f"{g['lg']} danger"):
                done["danger"] = n.isoformat(timespec="minutes")
                save_state(st)
        if ev["state"] == "post" and ev["completed"]:
            if sync_remote(st)["games"][key].get("end"):
                print(f"  {key}: final already posted (by another run)")
                continue
            changed = ev["os"] > ev["hs"]
            if post(end_text(g, ev), image=champion_card(g, ev) if changed else None, kind=f"{g['lg']} final"):
                done["end"] = n.isoformat(timespec="minutes")
                st.setdefault("log", []).append([done["end"], g["lg"], "change" if changed else "defense", ev["hs"], ev["os"]])
                save_state(st)
            continue
        if ev["state"] == "post":      # postponed / cancelled: nothing to post
            done["end"] = "no-result"
            save_state(st)
            continue
        watching = True
    return watching


def check():
    """--check: sign in with the X secrets and print which account they post as. Posts nothing."""
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing secrets: {', '.join(missing)}")
    import tweepy
    me = tweepy.Client(consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_KEY_SECRET"],
                       access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"]).get_me()
    name = me.data.username
    print(f"The X secrets post as @{name}. X_LIVE variable is {os.environ.get('X_LIVE_VAR') or 'not set'} (1 = posting on).")
    if name.lower() != "thebeltholders":
        sys.exit("!! That isn't @thebeltholders: re-run x_authorize.py logged in as @thebeltholders and update the secrets.")


def main():
    if "--check" in sys.argv:
        return check()
    watch = "--watch" in sys.argv
    print(f"X posts: leagues {LEAGUES}, {'LIVE' if LIVE else 'dry run'}")
    st = sync_remote(load_state())
    began = datetime.now(timezone.utc)
    while True:
        day = now_et().date()
        # just after midnight, last night's late games are still "today" for the belts
        if now_et().hour < 4:
            day -= timedelta(days=1)
        busy = one_pass(st, day)
        if not watch or not busy or datetime.now(timezone.utc) - began > WATCH_MAX:
            break
        time.sleep(POLL)


if __name__ == "__main__":
    main()
