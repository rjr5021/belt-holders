#!/usr/bin/env python3
"""
Build the static beltholders.com site from data/<league>/lineage.json.

    python3 build_lineages.py && python3 build_site.py

Output goes to site/ (served by GitHub Pages). Pages:

    /                       the network: every league's belt at a glance
    /<league>/              current holder, next defense, chain of custody
    /<league>/history/      every reign
    /<league>/records/      leaderboards
    /<league>/teams/        every franchise that has held it
    /<league>/teams/<slug>/ one franchise's belt history
    /rules/  /about/  /privacy/  /404.html  /feed.xml  /sitemap.xml
"""

import html
import json
import os
import re
import shutil
import sys
import unicodedata

import features
from datetime import date, datetime

from leagues import COMING, GROUPS, LIVE, ORDER, PRIMARY

SITE_URL = "https://beltholders.com"
OUT = "site"
ADSENSE_PUBLISHER_ID = ""        # "pub-3317069252410560" once beltholders.com is approved
GOATCOUNTER_CODE = "beltholders"
STYLES_VERSION = "6"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

e = html.escape


# ------------------------------------------------------------- helpers ---

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def d_short(iso, year=False):
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{MONTHS[m-1]} {d}" + (f", {y}" if year else "")


def d_long(iso):
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{MONTHS_LONG[m-1]} {d}, {y}"


def weekday(iso):
    return WEEKDAYS[date.fromisoformat(iso[:10]).weekday()]


def kickoff_12h(hhmm):
    if not hhmm:
        return "Time TBA"
    h, m = (int(x) for x in hhmm.split(":")[:2])
    ap = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {ap} ET"


def fit(name):
    """CSS custom property for fit-to-width display type: the longest word's length."""
    return f"--fit:{max(len(w) for w in name.split())}"


def ordinal(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def plural(n, word, pl=None):
    return f"{n:,} {word if n == 1 else (pl or word + 's')}"


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexc):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def darken(hexc, f=0.72):
    h = hexc.lstrip("#")
    r, g, b = (int(int(h[i:i + 2], 16) * f) for i in (0, 2, 4))
    return f"#{r:02x}{g:02x}{b:02x}"


def plate(primary, secondary):
    """Colors for a holder-colored plate: (top, bottom, ink, accent)."""
    top, bottom = primary, darken(primary)
    ink = "#ffffff" if contrast("#ffffff", bottom) >= contrast("#111111", top) else "#111111"
    accent = secondary if secondary and min(contrast(secondary, top), contrast(secondary, bottom)) >= 3 else (
        "#f0c65a" if ink == "#ffffff" and min(contrast("#f0c65a", top), contrast("#f0c65a", bottom)) >= 3 else ink)
    return top, bottom, ink, accent


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


# ------------------------------------------------------------- chrome ----

LOGO = ('<svg width="40" height="24" viewBox="0 0 40 24" fill="none" aria-hidden="true">'
        '<rect x="0" y="9" width="40" height="6" fill="#a97f38"/>'
        '<rect x="3" y="6" width="7" height="12" fill="#a97f38" stroke="#211a12" stroke-width="1.2"/>'
        '<rect x="30" y="6" width="7" height="12" fill="#a97f38" stroke="#211a12" stroke-width="1.2"/>'
        '<path d="M15 1 H25 L28 4 V20 L25 23 H15 L12 20 V4 Z" fill="#211a12" stroke="#a97f38" stroke-width="2"/>'
        '<path d="M20 7 L21.4 10.6 L25 10.8 L22.2 13 L23.2 16.6 L20 14.6 L16.8 16.6 L17.8 13 L15 10.8 L18.6 10.6 Z" fill="#a97f38"/></svg>')


NOINDEX = set()      # paths written with a noindex robots tag; build_sitemap leaves them out (BH-1)


TITLE_SUFFIX = " | Belt Holders"
TITLE_MAX = 65


def page(title, body, *, path, description, active=None, og_image="/og.png", jsonld=None, robots=None, og_title=None):
    if robots and "noindex" in robots:
        NOINDEX.add(path)
    nav = []
    for key in PRIMARY:
        live = any(lg["key"] == key for lg in LIVE)
        label = key.upper()
        cls = ' class="on"' if active == key else ""
        if live:
            nav.append(f'<a href="/{key}/"{cls}>{label}</a>')
        else:
            nav.append(f'<span class="soon" title="Coming soon">{label}</span>')
    if len(LIVE) > len(PRIMARY):
        nav.append(f'<a href="/leagues/"{" class=on" if active == "leagues" or (active and active not in PRIMARY and active in ORDER) else ""}>All leagues</a>')
    nav.append(f'<a href="/rules/"{" class=on" if active == "rules" else ""}>Rules</a>')
    nav.append(f'<a href="/about/"{" class=on" if active == "about" else ""}>About</a>')
    if og_image == "/og.png" and active in [lg["key"] for lg in LIVE]:
        og_image = f"/{active}/og.png"
    canonical = SITE_URL + path
    ads = (f'<meta name="google-adsense-account" content="ca-{ADSENSE_PUBLISHER_ID}">'
           f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-{ADSENSE_PUBLISHER_ID}" crossorigin="anonymous"></script>'
           if ADSENSE_PUBLISHER_ID else "")
    goat = (f'<script data-goatcounter="https://{GOATCOUNTER_CODE}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
            if GOATCOUNTER_CODE else "")
    if path == "/":
        # BH-16/CBB-8/NET-4: Organization + WebSite (with the site search) on the homepage, sameAs the network
        site_ld = [{"@type": "Organization", "@id": SITE_URL + "/#org", "name": 'Belt Holders', "url": SITE_URL + "/",
                    "logo": SITE_URL + "/icon-512.png", "sameAs": ['https://x.com/thebeltholders', 'https://www.instagram.com/thebeltholders', 'https://collegefootballbelt.com', 'https://collegebasketballbelt.com']},
                   {"@type": "WebSite", "@id": SITE_URL + "/#site", "name": 'Belt Holders', "url": SITE_URL + "/", "publisher": {"@id": SITE_URL + "/#org"},
                    "potentialAction": {"@type": "SearchAction", "target": SITE_URL + "/search/?q={query}", "query-input": "required name=query"}}]
        extra = [dict(x) for x in (jsonld if isinstance(jsonld, list) else [jsonld] if jsonld else [])]
        for x in extra:
            x.pop("@context", None)
        jsonld = {"@context": "https://schema.org", "@graph": site_ld + extra}
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    full_title = og_title or (title if "Belt Holders" in title else f"{title} · Belt Holders")   # og:title keeps the long form
    # BH-10: the <title> gets the " | Belt Holders" suffix only while it stays within 65 characters
    tag_title = title if ("Belt Holders" in title or len(title) + len(TITLE_SUFFIX) > TITLE_MAX) else title + TITLE_SUFFIX
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(tag_title)}</title>
<meta name="description" content="{e(description)}">
{f'<meta name="robots" content="{robots}">' + chr(10) if robots else ""}<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Belt Holders">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE_URL}{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@thebeltholders">
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/favicon.png" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#211a12">
<link rel="alternate" type="application/rss+xml" title="Belt Holders — title changes" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800;900&family=Spectral:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="/styles.css?v={STYLES_VERSION}">
<script>try{{var t=localStorage.getItem('belt-theme');if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
{ads}{goat}{ld}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top">
  <a class="brand" href="/">{LOGO}<span>Belt Holders</span></a>
  <nav class="primary mono" aria-label="Leagues">{"".join(nav)}</nav>
  <div class="topright"><button class="themebtn" type="button" aria-label="Toggle dark mode" onclick="var r=document.documentElement,d=r.dataset.theme==='dark'||(!r.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);r.dataset.theme=d?'light':'dark';try{{localStorage.setItem('belt-theme',r.dataset.theme);}}catch(e){{}}"><svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z"/></svg></button><a class="searchlink" href="/search/" aria-label="Search"><svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="7" cy="7" r="5"/><path d="M11 11 L15 15"/></svg></a><a class="pill mono" href="#alerts">Get belt alerts</a></div>
</header>
<main id="main">
{body}
</main>
{alerts_block()}
<footer class="foot mono">
  <div class="links"><a href="https://collegefootballbelt.com">collegefootballbelt.com</a><a href="https://collegebasketballbelt.com">collegebasketballbelt.com</a><a href="https://x.com/thebeltholders">@thebeltholders</a><a href="https://instagram.com/thebeltholders">Instagram</a></div>
  <div class="links"><a href="/privacy/">Privacy</a><a href="mailto:hello@beltholders.com">Contact</a><a href="/feed.xml">RSS</a><a href="/embed/">Embed a badge</a><span>Not affiliated with any league or team.</span></div>
</footer>
</body>
</html>
"""


def alerts_block():
    feed = f"{SITE_URL}/feed.xml"
    return f"""<section id="alerts" class="alerts" aria-label="Belt alerts">
  <div>
    <h2 class="disp">Know the second a belt changes hands</h2>
    <p>One email per title change. Nothing else.</p>
  </div>
  <form class="alert-form" action="https://blogtrottr.com" method="post" target="_blank">
    <input type="hidden" name="lang" value="en_US">
    <input type="hidden" name="btr_url" value="{feed}">
    <input type="hidden" name="schedule_type" value="0">
    <label for="alert-email" class="sr">Email address</label>
    <input id="alert-email" type="email" name="btr_email" placeholder="you@example.com" required>
    <button type="submit" class="mono">Sign me up</button>
  </form>
</section>"""


# ------------------------------------------------------------- pieces ----

def holder_plate_big(lg, data):
    cur = data["current"]
    p, s = lg["team_colors"](cur["team"])
    top, bottom, ink, accent = plate(p, s)
    won = ""
    if cur.get("won_from"):
        won = (f'Took the belt from {e(lg["team_name"](cur["won_from"]))}, '
               f'{won_score_text(cur)}, on {d_long(cur["start_date"])}.')
    elif cur.get("reclaimed_after"):
        won = f"Reclaimed the belt on {d_long(cur['start_date'])} after {e(lg['team_name'](cur['reclaimed_after']))} went dark."
    ng = data.get("next_game")
    nxt = ""
    if ng:
        where = "at" if not ng["holder_home"] else "vs."
        spread = ""
        if ng.get("spread") is not None:
            fav = ng["home"] if ng["spread"] > 0 else ng["away"]
            spread = f"{fav} −{abs(ng['spread']):g}" if ng["spread"] else "Pick ’em"
        prob = (data.get("preview") or {}).get("holder_win_prob")
        nxt_first = "First defense" if cur.get("defenses", 0) == 0 else "Next defense"
        won += f" {nxt_first} {weekday(ng['date'])}, {d_short(ng['date'])}."
        cp, cs = lg["team_colors"](ng["challenger"])
        nxt = f"""<aside class="upnext">
      <div class="kicker">Up next · title defense</div>
      <div class="matchup">
        <div><i style="background:{s or accent}"></i><b class="disp">{e(lg['short_name'](cur['team']))}</b><small>Holder</small></div>
        <span class="disp at">{where}</span>
        <div class="r"><i style="background:{cp}"></i><b class="disp">{e(lg['short_name'](ng['challenger']))}</b><small>Challenger</small></div>
      </div>
      <div class="meta mono"><span>{weekday(ng['date'])} {d_short(ng['date'])} · {kickoff_12h(ng.get('kickoff'))}</span><span>{e(spread)}</span></div>
      {f'<div class="meta mono"><span>{e(ng["stadium"])}</span></div>' if ng.get("stadium") else ""}
      {f'<div class="meta mono"><span>Chance to defend: {round(prob * 100)}%</span><a href="/{lg["key"]}/outlook/">Belt tree →</a></div>' if prob is not None else ""}
      <a class="mono prevlink" href="/{lg['key']}/next/">Game preview →</a>
    </aside>"""
    if not ng:
        import features
        won += " " + e(features.belt_state(lg, data)["line"])
    days = cur["days"]
    return f"""<section class="plate" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="plate-grid">
    <div class="plate-main">
      <div class="kicker dot">Current holder · {ordinal(cur['reign_no'])} reign</div>
      <h1 class="disp holder" style="{fit(cur['name'])}">{e(cur['name'])}</h1>
      <p class="lede">{won}</p>
      <div class="stats">
        <div><b class="disp">{days:,}</b><span class="mono">{"Day" if days == 1 else "Days"} held</span></div>
        <div><b class="disp">{cur.get('defenses', 0)}</b><span class="mono">{"Defense" if cur.get('defenses', 0) == 1 else "Defenses"}</span></div>
        <div><b class="disp">{cur['reign_no']}</b><span class="mono">Reigns all-time</span></div>
      </div>
    </div>
    {nxt}
  </div>
</section>"""


def season_text(lg, r):
    """'1977' for the NFL, '1976–77' for leagues whose seasons span two years."""
    season = r.get("season") or int(r["start_date"][:4])
    fn = lg.get("season_label")
    return fn(season) if fn else str(season)


def won_score_text(r):
    """The score of the game that started reign `r`, winner first."""
    hp, ap = (int(x) for x in r["won_score"].split("-"))
    return f"{max(hp, ap)}–{min(hp, ap)}"


def chain_rows(lg, reigns, n=8, compact=False):
    rows = []
    for r in list(reversed(reigns))[:n]:
        p, _ = lg["team_colors"](r["team"])
        how = ""
        if r.get("won_from"):
            how = f"Beat {e(lg['team_name'](r['won_from'], r.get('season', int(r['start_date'][:4]))))} {won_score_text(r)}"
        elif r.get("reclaimed_after"):
            how = f"Reclaimed after {e(lg['team_name'](r['reclaimed_after']))} folded"
        elif r["index"] == 1:
            how = "Won the first league game"
        if r.get("end_date"):
            span = f"{d_short(r['start_date'])} – {d_short(r['end_date'], True)}" if r["start_date"][:4] != r["end_date"][:4] else f"{d_short(r['start_date'])} – {d_short(r['end_date'])}, {r['end_date'][:4]}"
            tail = f"{plural(r['days'], 'day')} · {r.get('defenses', 0)} def."
        else:
            span = f"{d_short(r['start_date'], True)} –"
            tail = "Holding"
        rows.append(f"""<li><i style="background:{p}"></i><div><a class="disp" href="/{lg['key']}/teams/{slug(lg['team_name'](r['team']))}/">{e(r['name'])}</a><small>{how}</small></div><span class="mono when">{span}</span><span class="mono tail">{tail}</span></li>""")
    return f'<ol class="chain">{"".join(rows)}</ol>'


def record_card(title, rows):
    lis = "".join(f'<li><span>{i}. {e(name)}</span><b class="mono">{val}</b></li>' for i, (name, val) in enumerate(rows, 1))
    return f'<div class="card"><div class="kicker">{e(title)}</div><ol class="lb">{lis}</ol></div>'


# ------------------------------------------------------------- pages -----

def league_tile(lg, d, small=False):
    key = lg["key"]
    cur = d["current"]
    p, s = lg["team_colors"](cur["team"])
    top, bottom, ink, accent = plate(p, s)
    ng = d.get("next_game")
    st = features.belt_state(lg, d)
    foot = (f'<span class="disp">{"at" if not ng["holder_home"] else "vs."} {e(lg["short_name"](ng["challenger"]))}</span><span class="mono">{weekday(ng["date"])} {d_short(ng["date"])}</span>'
            if ng else f'<span class="disp">{e(st["foot"])}</span><span class="mono">{e(st["sub"])}</span>')
    how = (f"Beat {e(lg['team_name'](cur['won_from']))} {won_score_text(cur)}, {d_short(cur['start_date'])}."
           if cur.get("won_from") else f"Holding since {d_short(cur['start_date'], True)}.")
    return f"""<a class="tile{' small' if small else ''}" href="/{key}/" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="tile-head"><span class="disp">{lg['name']}</span><span class="mono status{' frozen' if st['state'] == 'postseason_holder_out' else ''}{' delayed' if st.get('delayed') else ''}"{(' title="' + e(st.get('reason', '')) + '"') if st.get('delayed') else ''}><i></i>{e(st['pill'])}</span></div>
  <div class="tile-body"><div class="mono k">Holder · {ordinal(cur['reign_no'])} reign</div><div class="disp name" style="{fit(cur['name'])}">{e(cur['name'])}</div><p>{how}</p></div>
  <div class="tile-foot">{foot}</div>
</a>"""


def more_leagues(datas):
    out = []
    for label, keys in GROUPS:
        ts = [league_tile(lg, datas[lg["key"]], small=True) for k in keys for lg in LIVE if lg["key"] == k]
        if ts:
            out.append(f'<div class="head sub-head"><h2 class="disp">{e(label)}</h2></div><div class="tiles small">{"".join(ts)}</div>')
    return "".join(out)


def build_leagues_page(datas):
    main = "".join(league_tile(lg, datas[lg["key"]], small=True) for k in PRIMARY for lg in LIVE if lg["key"] == k)
    body = f"""<section class="wrap block">
  <div class="head"><h1 class="disp">Every belt we track</h1><span class="mono note">{len(LIVE)} leagues</span></div>
  <p class="intro">One belt per league, passed from team to team since each league's first game. Pick a league.</p>
  <div class="head sub-head"><h2 class="disp">The big four</h2></div><div class="tiles small">{main}</div>
  {more_leagues(datas)}
</section>"""
    write("leagues/index.html", page("Every league's belt", body, path="/leagues/", active="leagues",
                                     description="Every lineal championship belt on Belt Holders: NFL, NBA, NHL, MLB, MLS, WNBA, NWSL, PWHL, the CFL, Europe's top soccer leagues and international soccer."))


def _health():
    try:
        with open(os.path.join("data", "health.json")) as f:
            return json.load(f).get("leagues", {})
    except (OSError, ValueError):
        return {}


HEALTH = _health()


def frozen_note(datas):
    """BH-12: one line on the homepage when a belt is frozen (its holder is out while the league plays on)."""
    fz = [(lg, datas[lg["key"]]) for lg in LIVE if features.belt_state(lg, datas[lg["key"]])["state"] == "postseason_holder_out"]
    if not fz:
        return ""
    bits = [f'<a href="/{lg["key"]}/">{e(lg["name"])}</a> ({e(lg["short_name"](d["current"]["team"]))})' for lg, d in fz]
    lst = bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]
    return (f'<p class="mono note frozen-note">Belt frozen: {lst} {"is" if len(bits) == 1 else "are"} done for the season, '
            f'so {"that belt carries" if len(bits) == 1 else "those belts carry"} over to next season.</p>')


def build_home(datas):
    tiles = []
    for key in PRIMARY:
        lg = next((l for l in LIVE if l["key"] == key), None)
        if lg:
            d = datas[key]
            cur = d["current"]
            p, s = lg["team_colors"](cur["team"])
            top, bottom, ink, accent = plate(p, s)
            ng = d.get("next_game")
            st = features.belt_state(lg, d)
            foot = (f'<span class="disp">{"at" if not ng["holder_home"] else "vs."} {e(lg["short_name"](ng["challenger"]))}</span><span class="mono">{weekday(ng["date"])} {d_short(ng["date"])}</span>'
                    if ng else f'<span class="disp">{e(st["foot"])}</span><span class="mono">{e(st["sub"])}</span>')
            how = (f"Beat {e(lg['team_name'](cur['won_from']))} {won_score_text(cur)}, {d_short(cur['start_date'])}."
                   if cur.get("won_from") else f"Holding since {d_short(cur['start_date'], True)}.")
            tiles.append(f"""<a class="tile" href="/{key}/" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="tile-head"><span class="disp">{lg['name']}</span><span class="mono status{' frozen' if st['state'] == 'postseason_holder_out' else ''}{' delayed' if st.get('delayed') else ''}"{(' title="' + e(st.get('reason', '')) + '"') if st.get('delayed') else ''}><i></i>{e(st['pill'])}</span></div>
  <div class="tile-body"><div class="mono k">Holder · {ordinal(cur['reign_no'])} reign</div><div class="disp name" style="{fit(cur['name'])}">{e(cur['name'])}</div><p>{how}</p></div>
  <div class="tile-foot">{foot}</div>
</a>""")
        else:
            c = next(x for x in COMING if x["key"] == key)
            tiles.append(f"""<div class="tile soon">
  <div class="tile-head"><span class="disp">{c['name']}</span><span class="mono status">{e(c['status'])}</span></div>
  <div class="tile-body"><div class="mono k">Since {c['first_season']}</div><div class="disp name">Coming soon</div><p>{e(c['blurb'])}</p></div>
  <div class="tile-foot"><span class="disp">Get the alert</span><span class="mono">→</span></div>
</div>""")

    # latest title changes, all live leagues, newest first
    changes = []
    for lg in LIVE:
        d = datas[lg["key"]]
        for r in d["reigns"]:
            if r.get("won_from"):
                changes.append((r["start_date"], lg, r))
    changes.sort(key=lambda x: x[0], reverse=True)
    feed_rows = "".join(
        f"""<li><span class="mono lg">{lg['name']}</span><i style="background:{lg['team_colors'](r['team'])[0]}"></i><div><b class="disp">{e(r['name'])}</b> beat {e(lg['team_name'](r['won_from'], r.get('season', int(r['start_date'][:4]))))} {won_score_text(r)} and took the belt</div><span class="mono when">{d_short(r['start_date'], True)}</span></li>"""
        for _, lg, r in changes[:6])

    nfl = datas.get("nfl")
    rec = nfl["records"] if nfl else None
    nums = ""
    if rec:
        import league_nfl as NFL
        md = rec["most_days"][0]
        mr = rec["most_reigns"][0]
        nums = f"""<div class="numbers">
    <div><b class="disp">{len(nfl['reigns']):,}</b><span class="mono">Reigns since {NFL.FIRST_SEASON}</span></div>
    <div><b class="disp">{mr[1]}</b><span class="mono">Reigns for the {e(NFL.short_name(mr[0]))}, the most</span></div>
    <div><b class="disp">{md[1]:,}</b><span class="mono">Days the {e(NFL.short_name(md[0]))} have held it</span></div>
    <div><b class="disp">{rec['playoff_changes']}</b><span class="mono">Title changes in the playoffs</span></div>
  </div>"""

    body = f"""<section class="hero wrap">
  <div class="hero-grid">
    <div><div class="kicker">Lineal championships · every league</div><h1 class="disp">Beat the champ.<br>Take the belt.</h1></div>
    <div class="hero-side"><p>Every league crowns one champion a year. We track the other one: a belt passed hand to hand since each league's first game, changing owners the moment somebody beats whoever's holding it.</p>
      <div class="btns"><a class="btn dark mono" href="/rules/">How it works</a><a class="btn mono" href="#alerts">Get belt alerts</a></div></div>
  </div>
  <div class="tiles">{"".join(tiles)}</div>
  {frozen_note(datas)}
  {more_leagues(datas)}
  {college_strip()}
</section>
<section class="wrap block">
  <div class="head"><h2 class="disp">Latest title changes</h2><span class="mono note">Every league, newest first</span></div>
  <ol class="feed">{feed_rows}</ol>
</section>
{home_extras(datas)}
<section class="rules-band">
  <div class="wrap rules-grid">
    <div><div class="kicker">The rules, short version</div><h2 class="disp">One belt.<br>Every game.<br>Win and it's yours.</h2><a class="mono more" href="/rules/">Read the full ruleset →</a></div>
    <div class="steps">
      <div><b class="disp">01</b><h3 class="disp">It starts at game one</h3><p>The winner of each league's first game picks up the belt. Everything since is one unbroken line.</p></div>
      <div><b class="disp">02</b><h3 class="disp">Beat the holder, take it</h3><p>Regular season or playoffs, home or away. A win over the holder is the only way the belt moves.</p></div>
      <div><b class="disp">03</b><h3 class="disp">Ties go to the champ</h3><p>A tie is a successful defense. A holder whose season is over keeps the belt until it plays again. If a holder's franchise folds, the belt goes back to the last holder still playing.</p></div>
    </div>
  </div>
</section>
<section class="wrap block">
  <div class="head"><h2 class="disp">The record books</h2><div class="tabs mono">{"".join(f'<a href="/{k}/records/" class="{"on" if k == "nfl" else ""}">{e(next(l["name"] for l in LIVE if l["key"] == k))}</a>' for k in ORDER if any(l["key"] == k for l in LIVE))}</div></div>
  {nums}
</section>"""
    write("index.html", page("Belt Holders — the lineal championship belt for every league", body, path="/",
                             description="Who holds the lineal championship belt in the NFL, NBA, NHL, MLB, MLS, WNBA, Premier League and more. Beat the champ, take the belt — tracked game by game since each league began."))


def college_strip():
    """The two college belts (sister sites) as holder-colored tiles, like the
    league board. Holders and next games come from each site's
    api/current.json; school colors from the College Basketball Belt repo's
    team list (every Division I school). Falls back to plain ink tiles."""
    import urllib.request

    def fetch(url):
        try:          # HTTPS only now that every sister site enforces it (BH-16)
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    teams = fetch("https://raw.githubusercontent.com/rjr5021/college-basketball-belt/main/data/teams.json") or []
    colors = {t.get("school"): (t.get("primaryColor"), t.get("secondaryColor")) for t in teams if t.get("school")}
    cards = []
    for label, site, api in (("College football", "https://collegefootballbelt.com/", "https://collegefootballbelt.com/api/current.json"),
                             ("College basketball", "https://collegebasketballbelt.com/", "https://collegebasketballbelt.com/api/current.json"),
                             ("Women's college hoops", "https://collegebasketballbelt.com/women/", "https://collegebasketballbelt.com/women/api/current.json")):
        j = fetch(api) or {}
        h = j.get("holder")
        p_, s_ = colors.get(h, (None, None))
        p_ = f"#{p_.lstrip('#')}" if p_ else "#211a12"
        s_ = f"#{s_.lstrip('#')}" if s_ else None
        top, bottom, ink, accent = plate(p_, s_)
        domain = site.split("//")[1].split("/")[0]
        ngd = (j.get("next_game") or {}).get("date")
        st = ""
        if ngd:
            out = (date.fromisoformat(ngd) - date.today()).days
            st = "In season" if out <= 14 else f"Opens {d_short(ngd)}"
        status = f'<span class="mono status"><i></i>{st}</span>' if st else ""
        if h:
            bits = []
            if j.get("team_reign_number"):
                bits.append(f"{ordinal(j['team_reign_number'])} reign")
            k = "Holder" + (f" · {bits[0]}" if bits else "")
            since = f"Holding since {d_short(j['since'], True)}" if j.get("since") else ""
            if j.get("defenses") is not None:
                since += f" · {plural(j['defenses'], 'defense')}"
            ng = j.get("next_game") or {}
            if ng.get("opponent") and ng.get("date"):
                where = "vs." if ng.get("is_home") or ng.get("neutral") else "at"
                foot = f'<span class="disp">{where} {e(ng["opponent"])}</span><span class="mono">{weekday(ng["date"])} {d_short(ng["date"])}</span>'
            else:
                foot = f'<span class="disp">{domain}</span><span class="mono">→</span>'
            body = f'<div class="mono k">{k}</div><div class="disp name" style="{fit(h)}">{e(h)}</div><p>{since}.</p>'
        else:
            body = f'<div class="mono k">The lineal title</div><div class="disp name">{label} belt</div><p>Who holds it right now.</p>'
            foot = f'<span class="disp">{domain}</span><span class="mono">→</span>'
        cards.append(f"""<a class="tile college-tile" href="{site}" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="tile-head"><span class="disp">{label}</span>{status}</div>
  <div class="tile-body">{body}</div>
  <div class="tile-foot">{foot}</div>
</a>""")
    return f'<div class="head sub-head"><h2 class="disp">College</h2></div><div class="colleges">{"".join(cards)}</div>'


def home_extras(datas):
    import site_extras
    today = date.today()
    otd = site_extras.otd_home(site_extras.otd_items(datas), today)
    stories = "".join(f'<a class="storycard" href="/{lg["key"]}/stories/{sl_}/"><span class="mono lg">{lg["name"]}</span><b class="disp">{e(t)}</b></a>'
                      for lg in LIVE for sl_, t in [("longest-reigns", f"The longest reigns in {lg['name']} belt history")])
    return otd + f'<section class="wrap block"><div class="head"><h2 class="disp">Stories</h2><a class="mono more" href="/stories/">All stories →</a></div><div class="storygrid">{stories}</div></section>'


def build_league(lg, d):
    key = lg["key"]
    rec = d["records"]
    name = lg["team_name"]
    cur = d["current"]
    cards = "".join([
        record_card("Most days holding the belt", [(name(t), f"{v:,}") for t, v in rec["most_days"][:5]]),
        record_card("Most defenses in one reign", [(f"{r['name']}, {season_text(lg, r)}", r["defenses"]) for r in rec["longest_reigns"][:5]]),
        record_card("Most reigns", [(name(t), v) for t, v in rec["most_reigns"][:5]]),
    ])
    import sys
    import features
    features.init(sys.modules[__name__], lambda x: "/" + x["key"])
    body = f"""{subnav(lg, "current")}
{features.live_box(lg, d)}
{holder_plate_big(lg, d)}
{features.latest_recap_card(lg, d)}
<section class="wrap split">
  <div>
    <div class="head"><h2 class="disp">Chain of custody</h2><a class="mono more" href="/{key}/history/">All {len(d['reigns']):,} reigns →</a></div>
    {chain_rows(lg, d['reigns'], 8)}
  </div>
  <div class="records-col"><h2 class="disp">Records</h2>{cards}<a class="mono more" href="/{key}/records/">Every record →</a></div>
</section>
{first_game_block(lg, d)}"""
    ld = {"@context": "https://schema.org", "@type": "SportsTeam", "name": cur["name"], "sport": lg.get("sport", ""),
          "award": f"{lg['long_name']} (lineal), {ordinal(cur['reign_no'])} reign since {cur['start_date']}"}
    write(f"{key}/index.html", page(f"{lg['long_name']}: {cur['name']} {features.verb(lg, 'hold', 'holds')} it", body, path=f"/{key}/", active=key,
                                     description=f"{cur['name']} {features.verb(lg, 'hold', 'holds')} the lineal {lg['name']} championship belt. Chain of custody, records and the next title defense, tracked since {lg['first_season']}.",
                                     jsonld=ld))


def first_game_block(lg, d):
    fg = d.get("first_game")
    if not fg:
        return ""
    n = lg["team_name"]
    w = fg["new_holder"]
    l = fg["opponent"]
    return f"""<section class="wrap block origin">
  <div class="kicker">Where it started · {d_long(fg['date'])}</div>
  <p class="big">{e(n(w, fg['season']))} {won_score_text({'won_score': fg['score']})} {e(n(l, fg['season']))}. The first {lg['name']} game on record, and the first reign of {plural(len(d['reigns']), 'reign')}.</p>
</section>"""


def subnav(lg, on):
    key = lg["key"]
    items = [("current", f"/{key}/", "Current"), ("next", f"/{key}/next/", "Next defense"),
             ("outlook", f"/{key}/outlook/", "Outlook"),
             ("history", f"/{key}/history/", "Full history"), ("seasons", f"/{key}/seasons/", "Seasons"),
             ("records", f"/{key}/records/", "Records"), ("teams", f"/{key}/teams/", "Teams"),
             ("rivalries", f"/{key}/rivalries/", "Rivalries"), ("compare", f"/{key}/compare/", "Compare"),
             ("stories", f"/{key}/stories/", "Stories"), ("more", f"/{key}/more/", "More")]
    links = "".join(f'<a href="{h}"{" class=on" if k == on else ""}>{t}</a>' for k, h, t in items)
    return f'<nav class="subnav mono" aria-label="{lg["name"]} sections"><span>{e(lg["long_name"])}</span>{links}</nav>'


def reign_link(lg, d, r):
    import site_extras
    d.setdefault("_bg", {bg["n"]: bg for bg in d["belt_games"]})
    return site_extras.reign_url(lg, d, r)


def build_history(lg, d):
    key = lg["key"]
    rows = []
    last_decade = None
    for r in reversed(d["reigns"]):
        dec = int(r["start_date"][:3] + "0")
        if dec != last_decade:
            rows.append(f'<tr class="dec" id="d{dec}"><th colspan="5" class="disp">{dec}s</th></tr>')
            last_decade = dec
        p, _ = lg["team_colors"](r["team"])
        how = (f"beat {e(lg['team_name'](r['won_from'], r.get('season', int(r['start_date'][:4]))))} {won_score_text(r)}" if r.get("won_from")
               else ("reclaimed (previous holder folded)" if r.get("reclaimed_after") else "first game"))
        flag = " · vacated" if r.get("vacated") else ""
        rows.append(f"""<tr><td class="mono n"><a href="{reign_link(lg, d, r)}">{r['index']}</a></td><td><i style="background:{p}"></i><a href="/{key}/teams/{slug(lg['team_name'](r['team']))}/">{e(r['name'])}</a><small>{how}{flag}</small></td>
<td class="mono">{d_short(r['start_date'], True)}</td><td class="mono">{d_short(r['end_date'], True) if r.get('end_date') else 'Holding'}</td><td class="mono r">{r.get('defenses', 0)} · {r['days']:,}d</td></tr>""")
    decades = sorted({int(r["start_date"][:3] + "0") for r in d["reigns"]}, reverse=True)
    jump = "".join(f'<a href="#d{x}">{x}s</a>' for x in decades)
    body = f"""{subnav(lg, "history")}
<section class="wrap block">
  <div class="head"><h1 class="disp">Every {lg['name']} reign</h1><span class="mono note">{len(d['reigns']):,} reigns · {d['records']['belt_games']:,} belt games since {lg['first_season']}</span></div>
  <nav class="jump mono" aria-label="Jump to decade">{jump}</nav>
  <div class="tablewrap"><table class="history">
    <thead><tr><th class="mono">#</th><th class="mono">Holder</th><th class="mono">Won</th><th class="mono">Lost</th><th class="mono r">Def. · days</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
</section>"""
    write(f"{key}/history/index.html", page(f"{lg['long_name']}: every reign since {lg['first_season']}", body,
                                            path=f"/{key}/history/", active=key,
                                            description=f"The complete lineal {lg['name']} championship history: all {len(d['reigns']):,} reigns since {lg['first_season']}."))


def build_records(lg, d):
    key = lg["key"]
    rec = d["records"]
    name = lg["team_name"]
    cards = "".join([
        record_card("Most days holding the belt (all reigns)", [(name(t), f"{v:,}") for t, v in rec["most_days"]]),
        record_card("Most reigns", [(name(t), v) for t, v in rec["most_reigns"]]),
        record_card("Most defenses in one reign", [(f"{r['name']}, {season_text(lg, r)}", r["defenses"]) for r in rec["longest_reigns"]]),
        record_card("Most successful defenses (all reigns)", [(name(t), v) for t, v in rec["most_defenses_total"]]),
        record_card("Most defenses in one season", [(f"{name(x['team'], x['season'])}, {season_text(lg, x)}", x["defenses"]) for x in rec.get("most_defenses_season", [])]),
        record_card("Most belt games played", [(name(t), f"{v:,}") for t, v in rec.get("most_belt_games", [])]),
        record_card("Busiest seasons (title changes)", [(season_text(lg, {"season": s_, "start_date": str(s_)}), v) for s_, v in rec.get("busiest_seasons", [])]),
        record_card("Longest current droughts", [(name(x["team"]), f"{x['days']:,} days") for x in rec.get("droughts", [])]),
        record_card("Most title takeovers from one team", [(f"{name(x['winner'])} from {name(x['loser'])}", x["times"]) for x in rec.get("top_takeovers", [])]),
    ])
    body = f"""{subnav(lg, "records")}
<section class="wrap block">
  <div class="head"><h1 class="disp">{lg['name']} belt records</h1><span class="mono note">Through {d_long(d['generated'])}</span></div>
  <div class="numbers">
    <div><b class="disp">{len(d['reigns']):,}</b><span class="mono">Reigns</span></div>
    <div><b class="disp">{rec['belt_games']:,}</b><span class="mono">Belt games</span></div>
    <div><b class="disp">{rec['programs']}</b><span class="mono">Franchises have held it</span></div>
    <div><b class="disp">{rec['playoff_changes']}</b><span class="mono">Title changes in the playoffs</span></div>
  </div>
  {f'<p class="intro">Never held the {lg["name"]} belt: {", ".join(name(t) for t in rec["never_held"])}.</p>' if rec.get("never_held") else ""}
  <div class="cards4">{cards}</div>
</section>"""
    write(f"{key}/records/index.html", page(f"{lg['name']} belt records", body, path=f"/{key}/records/", active=key,
                                            description=f"Lineal {lg['name']} championship records: most days held, most reigns, longest reigns."))


def build_teams(lg, d):
    import site_extras
    key = lg["key"]
    by = {}
    for r in d["reigns"]:
        by.setdefault(r["team"], []).append(r)
    cards = []
    for team, rs in sorted(by.items(), key=lambda kv: -sum(r["days"] for r in kv[1])):
        tname = lg["team_name"](team)
        p, s = lg["team_colors"](team)
        days = sum(r["days"] for r in rs)
        last = rs[-1]
        cards.append(f'<a class="teamcard" href="/{key}/teams/{slug(tname)}/"><i style="background:{p}"></i><b class="disp">{e(tname)}</b><span class="mono">{plural(len(rs), "reign")} · {days:,} days · last {last["start_date"][:4]}</span></a>')
        build_team(lg, d, team, rs)
    body = f"""{subnav(lg, "teams")}
<section class="wrap block">
  <div class="head"><h1 class="disp">Every franchise that has held the {lg['name']} belt</h1><span class="mono note">{len(by)} franchises · sorted by days held</span></div>
  <div class="teamgrid">{"".join(cards)}</div>
</section>
{site_extras.challengers_section(lg, d)}"""
    write(f"{key}/teams/index.html", page(f"{lg['name']} belt: every team", body, path=f"/{key}/teams/", active=key,
                                          description=f"Every franchise that has held the lineal {lg['name']} championship belt, and every one still waiting for it."))


def build_team(lg, d, team, rs):
    key = lg["key"]
    tname = lg["team_name"](team)
    p, s = lg["team_colors"](team)
    top, bottom, ink, accent = plate(p, s)
    days = sum(r["days"] for r in rs)
    defs = sum(r.get("defenses", 0) for r in rs)
    holding = rs[-1] is d["reigns"][-1] or (rs[-1].get("end_date") is None)
    rows = "".join(
        f"""<li><i style="background:{p}"></i><div><span class="disp">{ordinal(r['reign_no'])} reign · {e(r['name'])}</span><small>{('Beat ' + e(lg['team_name'](r['won_from'], r.get('season', int(r['start_date'][:4])))) + ' ' + won_score_text(r)) if r.get('won_from') else ('Reclaimed' if r.get('reclaimed_after') else 'First game')}{(' · lost to ' + e(lg['team_name'](r['lost_to'], (r.get('end_season') or r.get('season') or int(r['start_date'][:4]))))) if r.get('lost_to') else ''}</small></div><span class="mono when">{d_short(r['start_date'], True)} – {d_short(r['end_date'], True) if r.get('end_date') else 'now'}</span><span class="mono tail">{plural(r['days'], 'day')} · {r.get('defenses', 0)} def.</span></li>"""
        for r in reversed(rs))
    body = f"""{subnav(lg, "teams")}
<section class="plate slim" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="wrap-in">
    <div class="kicker dot">{'Current holder' if holding else lg['long_name']}</div>
    <h1 class="disp holder" style="{fit(tname)}">{e(tname)}</h1>
    <div class="stats"><div><b class="disp">{len(rs)}</b><span class="mono">Reigns</span></div><div><b class="disp">{days:,}</b><span class="mono">Days held</span></div><div><b class="disp">{defs}</b><span class="mono">Defenses</span></div><div><b class="disp">{rs[0]['start_date'][:4]}</b><span class="mono">First reign</span></div></div>
  </div>
</section>
<section class="wrap block"><div class="head"><h2 class="disp">Every reign</h2></div><ol class="chain">{rows}</ol></section>
{team_extras_html(lg, d, team)}"""
    write(f"{key}/teams/{slug(tname)}/index.html", page(f"{tname} and the {lg['name']} belt", body,
                                                         path=f"/{key}/teams/{slug(tname)}/", active=key,
                                                         description=f"{tname}: {plural(len(rs), 'reign')} with the lineal {lg['name']} championship belt, {days:,} days held."))


def team_extras_html(lg, d, team):
    import site_extras
    d.setdefault("_bg", {bg["n"]: bg for bg in d["belt_games"]})
    return site_extras.team_extras(lg, d, team)


# Women's college basketball moved to collegebasketballbelt.com/women/ in September 2026.
# The old /wcbb/ pages become redirects; anything else under /wcbb/ is caught by the 404
# page. Season pages were numbered by starting year here and by ending year there, and
# belt game numbers there don't count the 1986 final that opens the belt.
WCBB_NEW = "https://collegebasketballbelt.com/women/"
WCBB_MOVED_JS = """<script>(function(){var p=location.pathname;if(p.indexOf('/wcbb/')!==0)return;var r=p.slice(6);
var m=r.match(/^seasons\\/(\\d{4})\\/?$/);if(m)r='seasons/'+(+m[1]+1)+'/';
m=r.match(/^games\\/(\\d+)\\/?$/);if(m)r=(+m[1]>1)?'games/'+(m[1]-1)+'/':'';
location.replace('""" + WCBB_NEW + """'+r+location.hash);})();</script>"""


def build_wcbb_redirects():
    for sub in ("", "history/", "records/", "teams/", "seasons/", "rivalries/", "compare/", "next/", "outlook/", "more/",
                "champions/", "timeline/", "what-if/", "losers-belt/", "data/", "schedule/", "standings/", "on-date/",
                "decades/", "trivia/", "daily/", "states/", "map/", "web/", "splits/", "heartbreak/", "lean/",
                "defend-or-dethrone/", "degrees/", "my-team/", "conferences/"):
        to = WCBB_NEW + sub
        write(f"wcbb/{sub}index.html", f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>The Women's College Basketball Belt has moved</title><link rel="canonical" href="{to}">
<meta name="robots" content="noindex"><meta http-equiv="refresh" content="0; url={to}"></head>
<body><p>The Women's College Basketball Belt now lives at <a href="{to}">{to}</a>.</p></body></html>""")


def build_static_pages(datas):
    nfl = datas.get("nfl")
    fg = nfl["first_game"] if nfl else None
    nfl_line = ""
    if fg:
        import league_nfl as NFL
        nfl_line = (f"<p><b>NFL.</b> The belt starts with the first league game on record: {e(NFL.team_name(fg['new_holder'], 1920))} "
                    f"{won_score_text({'won_score': fg['score']})} {e(NFL.team_name(fg['opponent'], 1920))} on {d_long(fg['date'])}. Games from 1920 count "
                    f"only between clubs that were members of the league that season. AFL (1960–69) and AAFC (1946–49) games are included, "
                    f"so those teams could only reach the belt by beating an NFL holder. Franchise histories follow the team through moves "
                    f"and renames (the Rams are one franchise from Cleveland to St. Louis to Los Angeles).</p>")
    other_notes = "".join(lg["rules_note"](datas[lg["key"]].get("first_game"), lg["team_name"])
                          for lg in LIVE if lg.get("rules_note"))
    rules = f"""<section class="wrap prose">
<div class="kicker">The ruleset</div>
<h1 class="disp">How the belt works</h1>
<p>A lineal championship works like a boxing title: to become the champion, you have to beat the champion. Every league on this site has exactly one belt, and it has been passed from team to team, game by game, since that league's first game.</p>
<h2 class="disp">The rules every league shares</h2>
<ol>
<li><b>It starts at game one.</b> The winner of a league's first game picks up the belt.</li>
<li><b>Beat the holder, take the belt.</b> Any game counts — regular season or playoffs, home, away or neutral. Preseason and exhibition games don't.</li>
<li><b>Ties go to the champ.</b> A tie is a successful defense. Overtime and shootout wins are wins.</li>
<li><b>The belt follows the franchise.</b> Relocations and renames don't reset anything.</li>
<li><b>The season ends, the belt stays.</b> A holder whose season is over, whether it missed the playoffs or ran out of games, keeps the belt until it plays again. The belt is frozen until then and opens the next season with that team.</li>
<li><b>Folded holders.</b> If the holder's franchise folds or stops playing, the belt goes back to the most recent earlier holder that is still playing, the same rule our sister site, the College Football Belt, uses.</li>
</ol>
<h2 class="disp">League notes</h2>
{nfl_line}
{other_notes}
<h2 class="disp">Sources</h2>
<p>NFL results from 1920–2020 come from FiveThirtyEight's public NFL game archive; 2021 onward from the open nflverse project. {" ".join(lg["sources"] for lg in LIVE if lg.get("sources"))} The data is updated automatically every couple of hours.</p>
</section>"""
    write("rules/index.html", page("How the belt works", rules, path="/rules/", active="rules",
                                   description="The Belt Holders ruleset: how a lineal championship belt starts, moves and survives ties and folded franchises."))
    about = """<section class="wrap prose">
<div class="kicker">About</div>
<h1 class="disp">About Belt Holders</h1>
<p>Belt Holders tracks the lineal championship belt in professional sports: one title per league, passed from team to team only by beating whoever holds it. It's a companion to the <a href="https://collegefootballbelt.com">College Football Belt</a>, which has tracked the same idea in college football since 1869, and the <a href="https://collegebasketballbelt.com">College Basketball Belt</a>.</p>
<p>The site is independent and fan-run. It isn't affiliated with the NFL, NBA, NHL, MLB, or any team. Team names are used only to identify the teams.</p>
<p>Spot something wrong? Email <a href="mailto:hello@beltholders.com">hello@beltholders.com</a> or find us at <a href="https://x.com/thebeltholders">@thebeltholders</a>.</p>
</section>"""
    write("about/index.html", page("About", about, path="/about/", active="about",
                                   description="About Belt Holders, the lineal championship belt tracker for pro sports."))
    ads_text = ("<p>This site shows ads served by Google AdSense. Google and its partners use cookies to serve ads based on your visits to this and other sites. "
                "You can opt out of personalized advertising at <a href=\"https://adssettings.google.com\">Google's Ad Settings</a>. Visitors in the EEA and UK are asked for consent first.</p>"
                if ADSENSE_PUBLISHER_ID else "<p>This site doesn't show ads yet. If that changes, this section will describe what the ad provider collects and how to opt out.</p>")
    privacy = f"""<section class="wrap prose">
<div class="kicker">Privacy</div>
<h1 class="disp">Privacy policy</h1>
<p>Last updated {d_long(date.today().isoformat())}.</p>
<h2 class="disp">What we collect</h2>
<p>Nothing that identifies you. There are no accounts and no forms that send data to us. The email alert form sends your address to Blogtrottr, a third-party service, which emails you when our title-change feed updates; their privacy policy covers that address.</p>
<h2 class="disp">Analytics</h2>
<p>{"We use GoatCounter, a privacy-friendly analytics service that doesn't use cookies or collect personal data, to count page views." if GOATCOUNTER_CODE else "We don't run analytics yet."}</p>
<h2 class="disp">Advertising</h2>
{ads_text}
<h2 class="disp">Contact</h2>
<p><a href="mailto:hello@beltholders.com">hello@beltholders.com</a></p>
</section>"""
    write("privacy/index.html", page("Privacy", privacy, path="/privacy/", description="Belt Holders privacy policy."))
    notfound = """<section class="wrap prose"><div class="kicker">404</div><h1 class="disp">That page lost the belt</h1><p>It's not here anymore. Try the <a href="/">homepage</a> or the <a href="/nfl/">NFL belt</a>.</p></section>"""
    write("404.html", page("Page not found", notfound + WCBB_MOVED_JS, path="/404.html", description="Page not found.", robots="noindex"))
    build_wcbb_redirects()


def build_feed(datas):
    items = []
    for lg in LIVE:
        d = datas[lg["key"]]
        for r in d["reigns"][-40:]:
            if not r.get("won_from"):
                continue
            title = f"{lg['name']}: {r['name']} beat {lg['team_name'](r['won_from'])} {won_score_text(r)} and take the belt"
            dt = datetime.fromisoformat(r["start_date"] + "T23:00:00")
            items.append((dt, f"""<item><title>{e(title)}</title><link>{SITE_URL}/{lg['key']}/</link><guid isPermaLink="false">{lg['key']}-{r['index']}-{r['start_date']}</guid><pubDate>{dt.strftime('%a, %d %b %Y %H:%M:%S')} -0400</pubDate><description>{e(title)}. {ordinal(r['reign_no'])} reign for the franchise.</description></item>"""))
    items.sort(key=lambda x: x[0], reverse=True)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Belt Holders — title changes</title><link>{SITE_URL}/</link><description>Every time a lineal championship belt changes hands.</description><language>en-us</language>
{"".join(x for _, x in items[:40])}
</channel></rss>"""
    write("feed.xml", xml)


SITEMAP_MAX = 45000      # the protocol allows 50,000 URLs per file


def _is_noindex(path):
    with open(path, encoding="utf-8") as f:
        head = f.read(4000)
    return 'name="robots" content="noindex' in head


def _lastmods(datas):
    """URL -> YYYY-MM-DD from the data: a game's date, a reign's end, a season's last belt
    game, a team's latest belt game; league hubs change with every build."""
    out = {}
    for lg in LIVE:
        d = datas.get(lg["key"])
        if not d:
            continue
        k = lg["key"]
        gen = d.get("generated") or date.today().isoformat()
        out[f"/{k}/"] = gen
        last_season, last_team = {}, {}
        for bg in d["belt_games"]:
            out[f"/{k}/games/{bg['n']}/"] = bg["date"]
            last_season[bg["season"]] = bg["date"]
            for t in (bg.get("holder"), bg["opponent"]):
                if t:
                    last_team[t] = bg["date"]
        for sn, dt in last_season.items():
            out[f"/{k}/seasons/{sn}/"] = dt
        for r in d["reigns"]:
            out[f"/{k}/reigns/{r['index']}/"] = r.get("end_date") or gen
        cur = d["reigns"][-1]["team"] if d["reigns"] else None
        for t, dt in last_team.items():
            out[f"/{k}/teams/{slug(lg['team_name'](t))}/"] = gen if t == cur else dt
    return out


def build_sitemap(datas=None):
    """A sitemap index (BH-1): sitemap.xml lists sitemaps/<league>.xml and sitemaps/site.xml,
    each under 45,000 URLs. Pages carrying a noindex robots tag and the /wcbb/ redirect stubs
    stay out; <lastmod> comes from the data where the page has a natural date."""
    from xml.sax.saxutils import escape
    lm = _lastmods(datas or {})
    groups = {}
    for root, _, files in os.walk(OUT):
        if "index.html" not in files:
            continue
        rel = os.path.relpath(root, OUT).replace(os.sep, "/")
        u = "/" if rel == "." else f"/{rel}/"
        if u.startswith("/wcbb/") or _is_noindex(os.path.join(root, "index.html")):
            continue
        first = u.strip("/").split("/")[0]
        key = first if any(lg["key"] == first for lg in LIVE) else "site"
        groups.setdefault(key, []).append(u)
    today = date.today().isoformat()
    index = []
    for key in sorted(groups):
        urls = sorted(groups[key])
        for part in range(0, len(urls), SITEMAP_MAX):
            chunk = urls[part:part + SITEMAP_MAX]
            name = key if part == 0 else f"{key}-{part // SITEMAP_MAX + 1}"
            body = "".join(f"<url><loc>{escape(SITE_URL + u)}</loc>" + (f"<lastmod>{lm[u]}</lastmod>" if u in lm else "") + "</url>"
                           for u in chunk)
            write(f"sitemaps/{name}.xml", '<?xml version="1.0" encoding="UTF-8"?>'
                  f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>')
            newest = max((lm[u] for u in chunk if u in lm), default=today)
            index.append(f"<sitemap><loc>{escape(SITE_URL)}/sitemaps/{name}.xml</loc><lastmod>{newest}</lastmod></sitemap>")
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>'
          f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{"".join(index)}</sitemapindex>')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    write("CNAME", "beltholders.com\n")
    if ADSENSE_PUBLISHER_ID:
        write("ads.txt", f"google.com, {ADSENSE_PUBLISHER_ID}, DIRECT, f08c47fec0942fa0\n")


def build_api(datas):
    """api/current.json: every league's holder, for the sister sites (the College
    Football Belt footer reads it at build time) and anyone else."""
    out = {"site": SITE_URL, "generated": date.today().isoformat(), "leagues": {}}
    for lg in LIVE:
        d = datas[lg["key"]]
        cur, ng = d["current"], d.get("next_game")
        out["leagues"][lg["key"]] = {
            "name": lg["name"], "holder": lg["team_name"](cur["team"]), "short": lg["short_name"](cur["team"]),
            "since": cur["start_date"], "defenses": cur.get("defenses", 0), "reign": cur["reign_no"],
            "url": f"{SITE_URL}/{lg['key']}/", "state": features.belt_state(lg, d)["state"], "data_ok": (d.get("_health") or {}).get("ok", True),
            "next": ({"date": ng["date"], "opponent": lg["team_name"](ng["challenger"]), "home": ng["holder_home"]} if ng else None),
        }
    write("api/current.json", json.dumps(out, indent=1))


def build_meta_files(datas):
    names = [lg["name"] for lg in LIVE]
    lines = ["# Belt Holders", "", f"> Lineal championship belts for {len(LIVE)} leagues: {', '.join(names[:-1])} and {names[-1]}. The belt passes to whoever beats the holder, game by game, back to each league's first game. Updated every two hours.", ""]
    for lg in LIVE:
        d = datas[lg["key"]]
        cur = d["current"]
        lines += [f"## {lg['long_name']}", f"- Current holder: {cur['name']} (since {cur['start_date']}, {plural(cur.get('defenses', 0), 'defense')})",
                  f"- [Current holder and next defense]({SITE_URL}/{lg['key']}/)", f"- [Every reign]({SITE_URL}/{lg['key']}/history/)",
                  f"- [Records]({SITE_URL}/{lg['key']}/records/)", f"- [Data downloads (CSV)]({SITE_URL}/{lg['key']}/data/)", ""]
    lines += ["## Other", f"- [Rules]({SITE_URL}/rules/)", f"- [JSON API]({SITE_URL}/api/current.json)", "- Sister sites: https://collegefootballbelt.com, https://collegebasketballbelt.com (men's and women's belts)"]
    write("llms.txt", "\n".join(lines) + "\n")
    write("manifest.json", json.dumps({"name": "Belt Holders", "short_name": "Belt Holders", "start_url": "/", "display": "standalone",
                                       "background_color": "#e7e2d5", "theme_color": "#211a12",
                                       "icons": [{"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                                                 {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}, indent=1))


def copy_assets():
    for f in ("styles.css", "favicon.png", "favicon.ico", "apple-touch-icon.png", "icon-512.png", "og.png", "tablekit.js"):
        shutil.copy(f, os.path.join(OUT, f))


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    datas = {}
    missing = [lg["key"] for lg in LIVE if not os.path.exists(os.path.join("data", lg["key"], "lineage.json"))]
    if missing:
        print("no lineage yet, skipping:", missing)
        LIVE[:] = [lg for lg in LIVE if lg["key"] not in missing]
    import features
    features.init(sys.modules[__name__], lambda x: "/" + x["key"])
    for lg in LIVE:
        with open(os.path.join("data", lg["key"], "lineage.json")) as f:
            datas[lg["key"]] = json.load(f)
        features.plan_game_pages(lg, datas[lg["key"]])      # which games get their own page (BH-2)
        datas[lg["key"]]["_health"] = HEALTH.get(lg["key"])
    build_home(datas)
    build_leagues_page(datas)
    for lg in LIVE:
        d = datas[lg["key"]]
        build_league(lg, d)
        build_history(lg, d)
        build_records(lg, d)
        build_teams(lg, d)
    import site_extras
    site_extras.build_all(datas)
    build_static_pages(datas)
    build_api(datas)
    build_feed(datas)
    build_meta_files(datas)
    build_sitemap(datas)
    copy_assets()
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"Built {n} files into {OUT}/")


if __name__ == "__main__":
    main()
