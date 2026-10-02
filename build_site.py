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
SITE_NAME = "Belt Holders"
OUT = "site"
OWNER = "R&O Holdings LLC"      # the company that owns and operates the site (formed 2026-09-29)
ADSENSE_PUBLISHER_ID = ""        # "pub-3317069252410560" once beltholders.com is approved
GOATCOUNTER_CODE = "beltholders"
STYLES_VERSION = "12"
# 7.15 / 7.14: the belt-picks Cloudflare Worker (global Beat-the-lean leaderboard + web push). Empty = off.
PICKS_API = os.environ.get("PICKS_API", "https://belt-picks.rjr5021.workers.dev")
PICKS_SITE = {"*": "bh"}
PUSH_PUBLIC_KEY = "BEwm5LoAu5EOVoMq8prjAcv1D1PIShNARTz3d7R5Z7mH9OEpKaqq97pQWqlpAnXe7vWsNoJ7lM42-1y_vdgepow"

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
    if not hhmm or hhmm == "00:00":      # N-2: the midnight placeholder means the time isn't set
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

# NET-6: a BreadcrumbList on every inner page, built from the path. A segment gets a crumb only when it
# names a league or one of these sections (each has its own index page; main() checks that they exist).
CRUMB_SECTIONS = {"games": "Belt games", "players": "Players", "teams": "Teams", "reigns": "Reigns", "seasons": "Seasons",
                  "rivalries": "Rivalries", "history": "History", "decades": "Decades", "losers-belt": "Losers belt",
                  "leagues": "Leagues", "stories": "Stories", "on-this-day": "On this day"}
CRUMB_REFS = set()


def auto_crumbs(path, title):
    segs = [x for x in path.strip("/").split("/") if x]
    if not segs or path.endswith(".html"):
        return None
    names = {lg["key"]: f"{lg['name']} belt" for lg in LIVE}
    items, acc = [("Belt Holders", "/")], ""
    for i, sg in enumerate(segs[:-1]):
        acc += "/" + sg
        label = names.get(sg) if i == 0 else CRUMB_SECTIONS.get(sg)
        if i == 0 and not label:
            label = CRUMB_SECTIONS.get(sg)
        if label:
            items.append((label, acc + "/"))
            CRUMB_REFS.add(acc + "/")
    items.append((title, path))
    return {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": SITE_URL + u}
                                                           for i, (n, u) in enumerate(items)]}


def ld_graph(jsonld, path, title, extra_top=()):
    """All of a page's JSON-LD in one @graph, plus the automatic breadcrumbs when the page has none."""
    items = [dict(x) for x in (jsonld if isinstance(jsonld, list) else [jsonld] if jsonld else [])]
    for x in items:
        x.pop("@context", None)
    if path != "/" and not any(x.get("@type") == "BreadcrumbList" for x in items):
        bc = auto_crumbs(path, title)
        if bc:
            items.append(bc)
    items = list(extra_top) + items
    return {"@context": "https://schema.org", "@graph": items} if items else None


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
        nav.append(f'<a href="/leagues/"{" class=on" if active == "leagues" or (active and active not in PRIMARY and active in ORDER) else ""}><span class="lw">All </span>leagues</a>')
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
        site_ld = [{"@type": "Organization", "@id": SITE_URL + "/#org", "name": OWNER, "alternateName": 'Belt Holders', "url": SITE_URL + "/",
                    "logo": SITE_URL + "/icon-512.png", "sameAs": ['https://x.com/thebeltholders', 'https://www.instagram.com/thebeltholders', 'https://collegefootballbelt.com', 'https://collegebasketballbelt.com']},
                   {"@type": "WebSite", "@id": SITE_URL + "/#site", "name": 'Belt Holders', "url": SITE_URL + "/", "publisher": {"@id": SITE_URL + "/#org"},
                    "potentialAction": {"@type": "SearchAction", "target": SITE_URL + "/search/?q={query}", "query-input": "required name=query"}}]
    else:
        site_ld = []
    jsonld = ld_graph(jsonld, path, title, site_ld)
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
<link rel="preconnect" href="https://a.espncdn.com">
<link rel="preload" href="/fonts/big-shoulders-display-latin-800-normal.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/fonts/spectral-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/fonts/ibm-plex-mono-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
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
{alerts_block(path)}
<footer class="foot mono">
  <div class="belt-network" data-belt-network data-site="bh"><span class="nk">The belt network</span><a href="https://collegefootballbelt.com/"><b>College football</b></a><a href="https://collegebasketballbelt.com/"><b>Men's college hoops</b></a><a href="https://collegebasketballbelt.com/women/"><b>Women's college hoops</b></a><a class="all" href="/all/">Every belt →</a></div>
  <div class="links"><a href="https://collegefootballbelt.com">collegefootballbelt.com</a><a href="https://collegebasketballbelt.com">collegebasketballbelt.com</a><a href="https://x.com/thebeltholders">@thebeltholders</a><a href="https://x.com/CollegeFBBelt">@CollegeFBBelt</a><a href="https://x.com/CollegeBBBelt">@CollegeBBBelt</a><a href="https://instagram.com/thebeltholders">Instagram</a></div>
  <div class="links"><a href="/privacy/">Privacy</a><a href="mailto:hello@beltholders.com">Contact</a><a href="/feed.xml">RSS</a><a href="/embed/">Embed a badge</a><span>Not affiliated with any league or team.</span></div>
  <div class="links"><span>&copy; {date.today().year} R&amp;O Holdings LLC. All rights reserved.</span></div>
</footer>
<script src="/network-bar.js" defer></script>
<script>if("serviceWorker" in navigator)addEventListener("load",function(e){{navigator.serviceWorker.register("/sw.js").catch(Boolean);}});</script>
</body>
</html>
"""


def alerts_block(path="/"):
    """The footer signup: one Blogtrottr form, with a choice of feed -- the title-change feed (one email per
    change) or the weekly digest feed (feature 7.10; one email a week). The digest pages pre-select the digest."""
    feed = f"{SITE_URL}/feed.xml"
    digest = f"{SITE_URL}/digest/feed.xml"
    weekly = path.startswith("/digest/")
    return f"""<section id="alerts" class="alerts" aria-label="Belt alerts">
  <div>
    <h2 class="disp">Know the second a belt changes hands</h2>
    <p>One email per title change, or one a week with every belt in it. Nothing else.</p>
  </div>
  <form class="alert-form" action="https://blogtrottr.com" method="post" target="_blank">
    <input type="hidden" name="lang" value="en_US">
    <input type="hidden" name="schedule_type" value="0">
    <label for="alert-what" class="sr">What to send</label>
    <select id="alert-what" name="btr_url" class="mono">
      <option value="{feed}"{"" if weekly else " selected"}>Every title change</option>
      <option value="{digest}"{" selected" if weekly else ""}>The weekly digest</option>
    </select>
    <label for="alert-email" class="sr">Email address</label>
    <input id="alert-email" type="email" name="btr_email" placeholder="you@example.com" required>
    <button type="submit" class="mono">Sign me up</button>
  </form>
  <p class="mono note net-feed">Or follow every belt at once: <a href="/all/feed.xml">the belt network feed</a> (RSS) · <a href="/digest/">the weekly digest</a> · <a href="/all/belt.ics">every belt game on your calendar</a> (one subscription, all leagues and the college belts).{push_button(path)}</p>
</section>"""


def push_button(path="/"):
    """7.14: a web-push subscribe button for the belt the page belongs to (or every belt), when the Worker is configured."""
    if not (PICKS_API and PUSH_PUBLIC_KEY and "PLACEHOLDER" not in PICKS_API):
        return ""
    seg = path.strip("/").split("/")[0] if path else ""
    lg = next((x for x in LIVE if x["key"] == seg), None)
    belt = f"bh:{lg['key']}" if lg else "all"
    label = f"Push alerts: the {lg['name']} belt" if lg else "Push alerts: every belt"
    return (f' <button type="button" class="mono pushbtn" id="pushbtn" data-belt="{belt}" data-label="{e(label)}" hidden>{e(label)}</button>'
            f'<script>(function(){{var b=document.getElementById("pushbtn");if(!b||!("PushManager" in window)||!("serviceWorker" in navigator)||!("Notification" in window))return;'
            f'var API={json.dumps(PICKS_API)},PUB={json.dumps(PUSH_PUBLIC_KEY)},belt=b.dataset.belt,K="belt-push-"+belt;'
            'function u8(s){s=(s+"=".repeat((4-s.length%4)%4)).replace(/-/g,"+").replace(/_/g,"/");var r=atob(s),a=new Uint8Array(r.length);for(var i=0;i<r.length;i++)a[i]=r.charCodeAt(i);return a;}'
            'function paint(on){b.textContent=on?b.dataset.label.replace("Push alerts:","Push alerts on:")+" ✓":b.dataset.label;b.dataset.on=on?"1":"";}'
            'var on=false;try{on=!!localStorage.getItem(K);}catch(e){}paint(on);b.hidden=false;'
            'b.onclick=function(){navigator.serviceWorker.ready.then(function(reg){if(b.dataset.on){return reg.pushManager.getSubscription().then(function(sub){if(sub){fetch(API+"/unsubscribe",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({belt:belt,endpoint:sub.endpoint})});}'
            'try{localStorage.removeItem(K);}catch(e){}paint(false);});}'
            'return Notification.requestPermission().then(function(p){if(p!=="granted")return;return reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:u8(PUB)}).then(function(sub){return fetch(API+"/subscribe",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({belt:belt,sub:sub.toJSON()})}).then(function(r){if(r.ok){try{localStorage.setItem(K,"1");}catch(e){}paint(true);}});});});}).catch(function(){});};'
            '})();</script>')


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
    """'1977' for the NFL, '1976–77' for leagues whose seasons span two years; a reign that ran
    across seasons shows the span ('1971–74'), not just the season it started (audit #2, C-2)."""
    season = r.get("season") or int(r["start_date"][:4])
    fn = lg.get("season_label")
    first = fn(season) if fn else str(season)
    end = r.get("end_season")
    if end and end > season:
        last = fn(end) if fn else str(end)
        return f"{first.split('–')[0]}–{last[-2:]}" if len(first.split('–')[0]) == 4 and last[-2:].isdigit() else f"{first} to {last}"
    return first


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
    return f"""<a class="tile{' small' if small else ''}" data-key="{key}" href="/{key}/" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
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
  {features.home_live_script([(lg, datas[lg["key"]]) for lg in LIVE])}
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


def otd_extra(k):
    """site_extras hook: the college belts' title changes on a calendar date (network on-this-day)."""
    import network
    return network.otd_extra(k)


def network_stories():
    """site_extras hook: the college sites' stories, for /stories/."""
    import network
    return network.network_stories()


def cross_stories(datas):
    """site_extras hook (6.3): the stories that span leagues, written to /stories/<slug>/."""
    import network
    return network.cross_stories(sys.modules[__name__], datas)


def _network_widgets(datas):
    import network
    try:
        return network.widgets_html(sys.modules[__name__], datas, moved_card=False)
    except Exception as ex:  # noqa: BLE001 -- a widget must never take the homepage down
        print("network widgets skipped:", ex)
        return ""


def frozen_note(datas):
    """BH-12: one line on the homepage when a belt is frozen (its holder is out while the league plays on)."""
    fz = [(lg, datas[lg["key"]]) for lg in LIVE if features.belt_state(lg, datas[lg["key"]])["state"] == "postseason_holder_out"]
    if not fz:
        return ""
    bits = [f'<a href="/{lg["key"]}/">{e(lg["name"])}</a> ({e(lg["short_name"](d["current"]["team"]))})' for lg, d in fz]
    lst = bits[0] if len(bits) == 1 else ", ".join(bits[:-1]) + " and " + bits[-1]
    return (f'<p class="mono note frozen-note">Belt frozen: {lst} {"is" if len(bits) == 1 else "are"} done for the season, '
            f'so {"that belt carries" if len(bits) == 1 else "those belts carry"} over to next season.</p>')


def home_faq(datas):
    """Audit #2 (6.9): plain-language answers for the rich result, visible on the page and in FAQPage JSON-LD."""
    today = date.today()
    q = [("What is a lineal championship belt?",
          "A lineal championship belt is a title that changes hands only when the holder loses. Each league's belt starts with the winner of the league's "
          "first game, and it passes to whoever beats the holder, game by game: regular season, playoffs, home or away. Nothing is voted on. "
          "Belt Holders tracks one for every pro league, with the college belts on their sister sites.")]
    for key in PRIMARY:
        lg = next((l for l in LIVE if l["key"] == key), None)
        if not lg:
            continue
        d = datas[key]
        cur = d["current"]
        name = lg["team_name"](cur["team"])
        days = (today - date.fromisoformat(cur["start_date"])).days
        st = features.belt_state(lg, d)
        ng = d.get("next_game")
        took = (f"took it from {lg['team_name'](cur['won_from'])}, {won_score_text(cur)}, on {d_long(cur['start_date'])}" if cur.get("won_from")
                else f"picked it up on {d_long(cur['start_date'])}")
        nxt = ""
        if ng:
            where = "vs." if ng["holder_home"] else "at"
            nxt = f" The next belt game is {lg['short_name'](cur['team'])} {where} {lg['team_name'](ng['challenger'])} on {d_long(ng['date'])}."
        elif st["state"] == "postseason_holder_out":
            nxt = f" {lg['short_name'](cur['team'])} {verb_s(lg, 'are', 'is')} done for the season, so the belt carries over to next season."
        q.append((f"Who holds the {lg['name']} belt right now?",
                  f"{name} {verb_s(lg, 'hold', 'holds')} the {lg['name']} belt: {took}, with {plural(cur.get('defenses', 0), 'defense')} since "
                  f"({plural(days, 'day')} and counting, {features.poss(lg['short_name'](cur['team']))} {ordinal(cur['reign_no'])} reign).{nxt}"))
    q.append(("What happens when the holder's season ends?",
              "The belt waits. A holder that is eliminated, or whose league goes into its offseason, keeps the belt until its next game, so a belt can be "
              "\"frozen\" through a postseason the holder isn't in. If a franchise folds or drops out of the league, the belt goes back to the most recent "
              "earlier holder that is still playing."))
    q.append(("Do ties, overtime and shootouts count?",
              "A tie is a successful defense; the belt only moves on a loss. Overtime and shootout results count the way the league counts them. "
              "Preseason, exhibition and All-Star games don't count at all."))
    items = "".join(f'<div class="faq"><h3 class="disp">{e(qq)}</h3><p>{e(a)}</p></div>' for qq, a in q)
    html = f'<section class="wrap block"><div class="head"><div class="kicker">Straight answers</div><h2 class="disp">Belt FAQ</h2></div><div class="faqgrid">{items}</div></section>'
    ld = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": qq, "acceptedAnswer": {"@type": "Answer", "text": a}} for qq, a in q]}
    return html, ld


def verb_s(lg, plural_form, singular_form):
    return singular_form if lg.get("singular") else plural_form


def build_home(datas):
    faq_html, faq_ld = home_faq(datas)
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
            tiles.append(f"""<a class="tile" data-key="{key}" href="/{key}/" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
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
        f"""<li><span class="mono lg">{lg['name']}</span><i style="background:{lg['team_colors'](r['team'])[0]}"></i><div><b class="disp">{e(r['name'])}</b> beat {e(lg['team_name'](r['won_from'], r.get('season', int(r['start_date'][:4]))))} {won_score_text(r)} and took the belt{f' <a class="mono" href="{features.news_href(lg, datas[lg["key"]], r)}">Story →</a>' if "/news/" in features.news_href(lg, datas[lg["key"]], r) else ''}</div><span class="mono when">{d_short(r['start_date'], True)}</span></li>"""
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
  {features.home_live_script([(lg, datas[lg["key"]]) for lg in LIVE])}
  {frozen_note(datas)}
  <p class="mono more net-links"><a href="/all/">Every belt right now, college included →</a> · <a href="/today/">Belt games this week →</a> · <a href="/my-belts/">My belts →</a> · <a href="/digest/">This week's digest →</a> · <a href="/daily/">The Daily Belt →</a>{' · <a href="/leaderboard/">Beat the lean: leaderboard →</a>' if features.picks_api() else ''}</p>
  {more_leagues(datas)}
  {college_strip()}
</section>
{_network_widgets(datas)}
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
</section>
{faq_html}"""
    write("index.html", page("Belt Holders — the lineal championship belt for every league", body, path="/",
                             description="Who holds the lineal championship belt in the NFL, NBA, NHL, MLB, MLS, WNBA, Premier League and more. Beat the champ, take the belt — tracked game by game since each league began.",
                             jsonld=faq_ld))


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
    # B-5 (audit #2): one story per league, the kind rotating so the grid isn't sixteen "longest reigns" cards
    kinds = [("longest-reigns", lambda lg, d: f"The longest reigns in {lg['name']} belt history"),
             ("droughts", lambda lg, d: f"Waiting for the {lg['name']} belt: the longest droughts"),
             ("wildest-seasons", lambda lg, d: f"The {lg['name']} belt's wildest and quietest seasons"),
             ("rivalries", lambda lg, d: f"The rivalries that decided the {lg['name']} belt"),
             ("how-it-got-here", lambda lg, d: f"How the {lg['name']} belt got to {d['reigns'][-1]['name']}")]
    cards = []
    for i, lg in enumerate(LIVE):
        sl_, title = kinds[i % len(kinds)]
        cards.append(f'<a class="storycard" href="/{lg["key"]}/stories/{sl_}/"><span class="mono lg">{lg["name"]}</span><b class="disp">{e(title(lg, datas[lg["key"]]))}</b></a>')
    stories = "".join(cards)
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
             ("history", f"/{key}/history/", "Full history"), ("news", f"/{key}/news/", "News"), ("seasons", f"/{key}/seasons/", "Seasons"),
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
        cards.append(f'<a class="teamcard" href="/{key}/teams/{slug(tname)}/"><i style="background:{p}"></i><b class="disp">{e(tname)}</b><span class="mono">{plural(len(rs), "reign")} · {plural(days, "day")} · last {last["start_date"][:4]}</span></a>')
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
    <div class="stats"><div><b class="disp">{len(rs)}</b><span class="mono">{'Reign' if len(rs) == 1 else 'Reigns'}</span></div><div><b class="disp">{days:,}</b><span class="mono">Days held</span></div><div><b class="disp">{defs}</b><span class="mono">{'Defense' if defs == 1 else 'Defenses'}</span></div><div><b class="disp">{rs[0]['start_date'][:4]}</b><span class="mono">First reign</span></div></div>
  </div>
</section>
<section class="wrap block"><div class="head"><h2 class="disp">Every reign</h2></div><ol class="chain">{rows}</ol></section>
{team_extras_html(lg, d, team)}"""
    write(f"{key}/teams/{slug(tname)}/index.html", page(f"{tname} and the {lg['name']} belt", body,
                                                         path=f"/{key}/teams/{slug(tname)}/", active=key,
                                                         description=f"{tname}: {plural(len(rs), 'reign')} with the lineal {lg['name']} championship belt, {plural(days, 'day')} held."))


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
# B-2 (audit #2): player slugs changed when the NHL names were filled in ("g-howe-8448000" became
# "gordie-howe-8448000"). The id is the slug's tail, so an old URL is sent to the current slug.
PLAYER_MOVED_JS = """<script>(function(){var m=location.pathname.match(/^\\/([a-z0-9]+)\\/players\\/([a-z0-9-]+)\\/?$/);if(!m)return;
var lg=m[1],slug=m[2],parts=slug.split('-'),cands=[];
for(var i=1;i<=3&&i<parts.length;i++)cands.push(parts.slice(-i).join('-'));
fetch('/'+lg+'/players/ids.json').then(function(r){return r.json();}).then(function(ids){
for(var i=0;i<cands.length;i++){var s=ids[cands[i]];if(s&&s!==slug){location.replace('/'+lg+'/players/'+s+'/'+location.hash);return;}}}).catch(function(){});})();</script>"""


def build_my_belts(datas):
    """/my-belts/ (feature 7.13, audit #2): pick a team in every pro league once; one page shows every belt
    your teams hold or could win, the next shot and the odds, from each league's my-team/data.json."""
    teams = {}
    for lg in LIVE:
        d = datas[lg["key"]]
        recent = set((d.get("models") or {}).get("elo") or {})
        teams[lg["key"]] = {"name": lg["name"], "sport": lg.get("sport", ""), "teams": {t: lg["team_name"](t) for t in sorted(recent, key=lambda t: lg["team_name"](t))}}
    write("my-belts/teams.json", json.dumps(teams, separators=(",", ":")))
    groups = []
    for label, keys in [("The big four", PRIMARY)] + GROUPS:
        sel = "".join(
            f'<label><span class="mono">{e(next(l["name"] for l in LIVE if l["key"] == k))}</span><select data-lg="{k}"><option value="">—</option>'
            + "".join(f'<option value="{t}">{e(nm)}</option>' for t, nm in teams[k]["teams"].items()) + "</select></label>"
            for k in keys if k in teams)
        if sel:
            groups.append(f'<fieldset class="mb-group"><legend class="kicker">{e(label)}</legend>{sel}</fieldset>')
    body = f"""<section class="wrap block">
  <div class="head"><h1 class="disp">My belts</h1><span class="mono note">Pick once; this device remembers</span></div>
  <p class="intro">Your teams across every pro belt on one page: who holds each belt, your next shot at it and the odds. College football and college basketball have their own: <a href="https://collegefootballbelt.com/my-team.html">CFB My Team</a>, <a href="https://collegebasketballbelt.com/my-team/">men's hoops</a>, <a href="https://collegebasketballbelt.com/women/my-team/">women's hoops</a>.</p>
  <form class="mb-form mono" onsubmit="return false">{"".join(groups)}</form>
  <div id="mbout" class="mb-out"></div>
</section>
<script>
(function(){{
var K='belt-mybelts',O=document.getElementById('mbout'),sels=document.querySelectorAll('select[data-lg]'),picks={{}},cache={{}};
var MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fd(d){{var p=d.split('-');return MO[+p[1]-1]+' '+(+p[2])+', '+p[0];}}
function pc(p){{return p==null?'—':(p>0&&p<.01?'<1%':Math.round(p*100)+'%');}}
function days(d){{return Math.round((Date.now()-new Date(d+'T00:00:00'))/864e5);}}
function ink(h){{var c=(h||'#333').replace('#','');if(c.length===3)c=c.replace(/(.)/g,'$1$1');var r=parseInt(c.slice(0,2),16)/255,g=parseInt(c.slice(2,4),16)/255,b=parseInt(c.slice(4,6),16)/255;function f(v){{return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4);}}return (.2126*f(r)+.7152*f(g)+.0722*f(b))>.4?'#211a12':'#fff';}}
try{{picks=JSON.parse(localStorage.getItem(K)||'{{}}')||{{}};}}catch(e){{picks={{}};}}
sels.forEach(function(s){{if(picks[s.dataset.lg])s.value=picks[s.dataset.lg];s.onchange=function(){{if(s.value)picks[s.dataset.lg]=s.value;else delete picks[s.dataset.lg];try{{localStorage.setItem(K,JSON.stringify(picks));}}catch(e){{}}render();}};}});
function load(lg){{if(cache[lg])return Promise.resolve(cache[lg]);return fetch('/'+lg+'/my-team/data.json').then(function(r){{return r.json();}}).then(function(j){{cache[lg]=j;return j;}});}}
function render(){{
 var keys=Object.keys(picks);if(!keys.length){{O.innerHTML='<p class="mono note">Pick a team or two above.</p>';return;}}
 Promise.all(keys.map(load)).then(function(ds){{
  var holding=[],rest=[];
  keys.forEach(function(lg,i){{var x=ds[i][picks[lg]];if(!x)return;var name=document.querySelector('select[data-lg="'+lg+'"]').closest('label').querySelector('span').textContent;
   var s=[];
   if(x.holder)s.push('<b>Holds the belt</b>'+(x.last?' since '+fd(x.last[0]):'')+'.');
   else if(x.meet)s.push('Next shot: '+fd(x.meet[0])+' '+(x.meet[1]===picks[lg]?'at home':'on the road')+', if nobody takes it first.');
   else s.push('No game against the holder on the schedule yet.');
   if(x.odds!=null)s.push('Chance to hold it when the season ends: '+pc(x.odds)+'.');
   if(!x.holder&&x.last&&x.last[1])s.push(days(x.last[1]).toLocaleString()+' days since they last held it.');
   if(!x.holder&&!x.last)s.push('Never held it.');
   var card='<a class="tile small" href="/'+lg+'/" style="--top:'+x.color+';--bottom:'+x.color+';--ink:'+ink(x.color)+';--accent:'+ink(x.color)+'"><div class="tile-head"><span class="disp">'+name+'</span><span class="mono status"><i></i>'+(x.holder?'HOLDER':(x.meet?'NEXT SHOT '+x.meet[0].slice(5).replace('-','/'):'WAITING'))+'</span></div><div class="tile-body"><div class="disp name">'+x.name+'</div><p>'+s.join(' ')+'</p></div><div class="tile-foot"><span class="disp">'+x.reigns+' reign'+(x.reigns===1?'':'s')+' · '+x.days.toLocaleString()+' days held</span><span class="mono">→</span></div></a>';
   (x.holder?holding:rest).push(card);}});
  O.innerHTML='<div class="tiles small">'+holding.concat(rest).join('')+'</div>';
 }}).catch(function(){{O.innerHTML='<p class="mono note">The belt data did not load; try again in a minute.</p>';}});
}}
render();
}})();
</script>"""
    write("my-belts/index.html", page("My belts: your teams across every pro belt", body, path="/my-belts/", active="leagues",
                                      description="Pick your team in every pro league once and see which belts they hold, their next shot at each belt and the odds, all on one page."))


def build_ufwc_page(datas):
    """/intl/ufwc/ (feature 7.4, audit #2): how the International belt relates to the Unofficial Football
    World Championships and Nasazzi's Baton -- the established lineal titles people search for."""
    lg = next((l for l in LIVE if l["key"] == "intl"), None)
    d = datas.get("intl") if lg else None
    if not d:
        return
    cur = d["current"]
    nz = next((a for a in (d.get("models") or {}).get("alt_starts") or [] if a["key"] == "nasazzi"), None)
    nz_html = ""
    if nz:
        nz_html = (f"<p>Nasazzi's Baton, named for Uruguay's 1930 captain José Nasazzi, runs the same idea from the first World Cup final: Uruguay 4–2 Argentina in Montevideo on July 30, 1930. "
                   f"We run that line too, under our rules. It rejoined the main belt on {d_long(nz['rejoin'])}, {plural(len([x for x in nz['apart'] if x[2] < nz['rejoin']]), 'reign')} in, and has been the same belt ever since. "
                   f'<a href="/intl/eras/nasazzi/">The Baton line, and the record book since 1930 →</a></p>' if nz.get("rejoin") else
                   f'<p>Nasazzi\'s Baton runs the same idea from the first World Cup final in 1930. <a href="/intl/eras/nasazzi/">Our version of that line →</a></p>')
    body = f"""{subnav(lg, "more")}
<section class="wrap prose">
<div class="kicker">The International belt · the UFWC</div>
<h1 class="disp">The International belt and the Unofficial Football World Championships</h1>
<p>The Unofficial Football World Championships (UFWC) is the best-known lineal title in football: a championship that passes from nation to nation on the pitch, traced back by Paul Brown and the <a href="https://www.ufwc.co.uk/">ufwc.co.uk</a> community. Our International belt follows the same idea, so it's worth saying plainly where the two agree and where they can part.</p>
<h2 class="disp">Where they agree</h2>
<ol>
<li><b>The same first champion.</b> Both start with the first decisive international: England 4–2 Scotland at the Kennington Oval on March 8, 1873. The first international of all, Scotland 0–0 England in Glasgow in 1872, crowned nobody.</li>
<li><b>Beat the holder, take the title.</b> The holder's next full international is a title match, whatever the competition: friendly, qualifier or tournament.</li>
<li><b>Draws stay with the holder.</b> A drawn title match is a successful defense.</li>
<li><b>Extra time and penalties count.</b> A knockout match is decided by its final outcome, so a shootout winner takes (or keeps) the title.</li>
</ol>
<h2 class="disp">Where they can differ</h2>
<p>Which matches count. The UFWC follows the list of full international "A" matches as the governing bodies recognise them, and its keepers have had to rule on individual games over the years. Our belt is computed automatically, every few hours, from Mart Jürisoo's open dataset of international results, counting every match between national teams that have played World Cup qualifying. One disputed friendly in 150 years is enough to send the two titles down different roads for a while, and sometimes they are in different hands. Right now our belt says <b>{e(cur['name'])}</b>, holding since {d_long(cur['start_date'])} with {plural(cur.get('defenses', 0), 'defense')}; the UFWC's own site lists its current champion.</p>
<p>Neither is "official". Both are the same question asked of the record: who last beat the team that last beat the team that last beat the first winners?</p>
<h2 class="disp">Nasazzi's Baton</h2>
{nz_html}
<h2 class="disp">Follow the belt</h2>
<p><a href="/intl/">The current holder and next defense</a> · <a href="/intl/history/">every reign since 1873</a> · <a href="/intl/droughts/">days since each nation last held it</a> · <a href="/intl/feed.xml">RSS</a> · <a href="/intl/belt.ics">calendar</a>.</p>
</section>"""
    write("intl/ufwc/index.html", page("The International belt vs. the Unofficial Football World Championships", body, path="/intl/ufwc/", active="intl",
                                       description="How our International Football Belt relates to the Unofficial Football World Championships (UFWC) and Nasazzi's Baton: the same 1873 origin and rules, where the lines can differ, and who holds each today."))


def build_network_news(datas, limit=60):
    """/news/: the newest title changes on every pro belt, as links to the dated articles (feature 7.2).
    The matching feed is /all/feed.xml, whose items now link to the articles."""
    arts = [a for lg in LIVE for a in (datas[lg["key"]].get("_news") or [])]
    arts.sort(key=lambda a: a["date"], reverse=True)
    arts = arts[:limit]
    lis = "".join(f'<li><span class="mono lg">{e(a["league"])}</span><i style="background:{a["color"]}"></i><div><a href="{a["url"]}"><b class="disp">{e(a["title"])}</b></a><span>{e(a["dek"])}</span></div><span class="mono when">{d_short(a["date"], True)}</span></li>'
                  for a in arts)
    body = f"""<section class="wrap block">
  <div class="head"><h1 class="disp">Belt news</h1><span class="mono note">every pro belt · newest first</span></div>
  <p class="intro">Every time one of the pro belts changes hands, as a dated article: who took it, whose reign ended and what comes next. <a href="/all/feed.xml">RSS feed</a> · <a href="/all/">Every belt right now →</a></p>
  <ul class="feed news">{lis}</ul>
</section>"""
    write("news/index.html", page("Belt news: every title change, every league", body, path="/news/", active="leagues",
                                  description="Dated articles on every change of hands across the pro-league lineal championship belts: NFL, NBA, NHL, MLB, soccer and more."))


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
{__import__("site_extras").rulesets_html("pro")}
<h2 class="disp">Sources</h2>
<p>NFL results from 1920–2020 come from FiveThirtyEight's public NFL game archive; 2021 onward from the open nflverse project. {" ".join(lg["sources"] for lg in LIVE if lg.get("sources"))} The data is updated automatically every couple of hours.</p>
</section>"""
    write("rules/index.html", page("How the belt works", rules, path="/rules/", active="rules",
                                   description="The Belt Holders ruleset: how a lineal championship belt starts, moves and survives ties and folded franchises."))
    about = """<section class="wrap prose">
<div class="kicker">About</div>
<h1 class="disp">About Belt Holders</h1>
<p>Belt Holders tracks the lineal championship belt in professional sports: one title per league, passed from team to team only by beating whoever holds it. It's a companion to the <a href="https://collegefootballbelt.com">College Football Belt</a>, which has tracked the same idea in college football since 1869, and the <a href="https://collegebasketballbelt.com">College Basketball Belt</a>.</p>
<p>beltholders.com is operated by R&amp;O Holdings LLC. The site is independent and fan-run. It isn't affiliated with the NFL, NBA, NHL, MLB, or any team. Team names are used only to identify the teams.</p>
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
<p>Nothing that identifies you. There are no accounts and no forms that send data to us. The email signup form sends your address to Blogtrottr, a third-party service, which emails you when the feed you picked (our title-change feed, or the weekly digest feed) updates; their privacy policy covers that address.</p>
<h2 class="disp">Analytics</h2>
<p>{"We use GoatCounter, a privacy-friendly analytics service that doesn't use cookies or collect personal data, to count page views." if GOATCOUNTER_CODE else "We don't run analytics yet."}</p>
<h2 class="disp">Advertising</h2>
{ads_text}
<h2 class="disp">Contact</h2>
<p>beltholders.com is operated by {e(OWNER)}. Questions about this policy: <a href="mailto:hello@beltholders.com">hello@beltholders.com</a></p>
</section>"""
    write("privacy/index.html", page("Privacy", privacy, path="/privacy/", description="Belt Holders privacy policy."))
    notfound = """<section class="wrap prose"><div class="kicker">404</div><h1 class="disp">That page lost the belt</h1><p>It's not here anymore. Try the <a href="/">homepage</a> or the <a href="/nfl/">NFL belt</a>.</p></section>"""
    write("404.html", page("Page not found", notfound + WCBB_MOVED_JS + PLAYER_MOVED_JS, path="/404.html", description="Page not found.", robots="noindex"))
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
            # no <lastmod> for pre-1970 dates: Google reports them as "Invalid date"
            body = "".join(f"<url><loc>{escape(SITE_URL + u)}</loc>" + (f"<lastmod>{lm[u]}</lastmod>" if lm.get(u, "") >= "1970" else "") + "</url>"
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
            "since": cur["start_date"], "defenses": cur.get("defenses", 0), "reign": cur["reign_no"], "reign_no": cur["reign_no"],
            "holder_short": lg["short_name"](cur["team"]), "reigns_url": f"{SITE_URL}/{lg['key']}/api/reigns.json",
            "games_url": f"{SITE_URL}/{lg['key']}/api/games.json",
            "url": f"{SITE_URL}/{lg['key']}/", "state": features.belt_state(lg, d)["state"], "data_ok": (d.get("_health") or {}).get("ok", True),
            "next": features.next_payload(lg, d, SITE_URL),     # a superset of the old {date, opponent, home}
        }
    write("api/current.json", json.dumps(out, indent=1))
    write("api/openapi.json", json.dumps(openapi_spec(), indent=1))      # feature 7.8 (audit #2)


def openapi_spec():
    """An OpenAPI 3.1 description of the belt network's read-only JSON API (every endpoint is a static
    file regenerated by the builds), so the data shows up in API directories and dataset search."""
    keys = [lg["key"] for lg in LIVE]
    belt = {"type": "object", "properties": {
        "name": {"type": "string"}, "holder": {"type": "string"}, "holder_short": {"type": "string"}, "since": {"type": "string", "format": "date"},
        "defenses": {"type": "integer"}, "reign_no": {"type": "integer"}, "state": {"type": "string", "description": "in_season_next_game, offseason_schedule_pending, postseason_holder_out, ..."},
        "data_ok": {"type": "boolean"}, "url": {"type": "string", "format": "uri"},
        "next": {"type": ["object", "null"], "properties": {"date": {"type": "string", "format": "date"}, "time_et": {"type": ["string", "null"], "description": "HH:MM Eastern, null when not set"},
                 "opponent": {"type": "string"}, "opponent_short": {"type": "string"}, "home": {"type": "boolean"}, "neutral": {"type": "boolean"},
                 "venue": {"type": ["string", "null"]}, "city": {"type": ["string", "null"]}, "tv": {"type": ["string", "null"]}, "win_prob": {"type": ["number", "null"]}, "url": {"type": "string", "format": "uri"}}}}}
    reign = {"type": "object", "properties": {"index": {"type": "integer"}, "team": {"type": "string"}, "name": {"type": "string"}, "reign_no": {"type": "integer"},
             "start_date": {"type": "string", "format": "date"}, "end_date": {"type": ["string", "null"], "format": "date"}, "days": {"type": "integer"},
             "defenses": {"type": "integer"}, "won_from": {"type": ["string", "null"]}, "won_from_name": {"type": ["string", "null"]}, "opened_by": {"type": ["integer", "null"], "description": "belt game number that opened the reign"}}}
    game = {"type": "object", "properties": {"n": {"type": "integer"}, "date": {"type": "string", "format": "date"}, "season": {"type": "integer"}, "season_type": {"type": "string"},
            "holder": {"type": ["string", "null"]}, "holder_name": {"type": ["string", "null"]}, "opponent": {"type": "string"}, "opponent_name": {"type": "string"},
            "home": {"type": "string"}, "neutral": {"type": "boolean"}, "score": {"type": "string", "description": "home-away"}, "outcome": {"type": "string", "enum": ["established", "retained", "changed", "retained (tie)"]},
            "new_holder": {"type": "string"}, "new_holder_name": {"type": "string"}, "ot": {"type": "boolean"}}}
    paths = {
        "/api/current.json": {"get": {"summary": "Every pro belt's holder and next defense", "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {
            "site": {"type": "string"}, "generated": {"type": "string", "format": "date"}, "leagues": {"type": "object", "additionalProperties": belt}}}}}}}}},
        "/api/network.json": {"get": {"summary": "Every belt on all three sites (pro, college football, men's and women's college basketball)", "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {
            "generated": {"type": "string"}, "belts": {"type": "array", "items": {"allOf": [belt, {"type": "object", "properties": {"key": {"type": "string"}, "sport": {"type": "string"}, "site": {"type": "string"}, "short": {"type": "string"}, "colors": {"type": "array", "items": {"type": "string"}}, "badge": {"type": ["string", "null"]}, "feed": {"type": ["string", "null"]}, "ok": {"type": "boolean"}}}]}}}}}}}}}},
        "/{league}/api/reigns.json": {"get": {"summary": "Every reign of one belt", "parameters": [{"name": "league", "in": "path", "required": True, "schema": {"type": "string", "enum": keys}}],
                                       "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {"belt": {"type": "string"}, "generated_at": {"type": "string"}, "reigns": {"type": "array", "items": reign}}}}}}}}},
        "/{league}/api/games.json": {"get": {"summary": "Every belt game of one belt", "parameters": [{"name": "league", "in": "path", "required": True, "schema": {"type": "string", "enum": keys}}],
                                      "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {"belt": {"type": "string"}, "generated_at": {"type": "string"}, "belt_games": {"type": "array", "items": game}}}}}}}}},
        "/{league}/data/reigns.csv": {"get": {"summary": "Every reign as CSV", "parameters": [{"name": "league", "in": "path", "required": True, "schema": {"type": "string", "enum": keys}}], "responses": {"200": {"description": "OK", "content": {"text/csv": {}}}}}},
        "/{league}/data/belt-games.csv": {"get": {"summary": "Every belt game as CSV", "parameters": [{"name": "league", "in": "path", "required": True, "schema": {"type": "string", "enum": keys}}], "responses": {"200": {"description": "OK", "content": {"text/csv": {}}}}}},
        "/all/feed.xml": {"get": {"summary": "RSS: every title change on every belt", "responses": {"200": {"description": "OK", "content": {"application/rss+xml": {}}}}}},
        "/all/belt.ics": {"get": {"summary": "iCalendar: every upcoming belt game on every belt", "responses": {"200": {"description": "OK", "content": {"text/calendar": {}}}}}},
    }
    return {"openapi": "3.1.0",
            "info": {"title": "Belt Holders API", "version": date.today().isoformat(), "summary": "Lineal championship belts for every league, as static JSON, CSV, RSS and iCalendar.",
                     "description": "Read-only. Every file is regenerated by the site build every couple of hours; no keys, no rate limits beyond GitHub Pages' own. Data is CC BY 4.0: credit beltholders.com. The sister sites publish the same shapes at https://collegefootballbelt.com/api/current.json and https://collegebasketballbelt.com/api/current.json (women's belt under /women/api/).",
                     "contact": {"name": OWNER, "url": SITE_URL + "/about/"}, "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}},
            "servers": [{"url": SITE_URL}], "paths": paths}


def build_meta_files(datas):
    names = [lg["name"] for lg in LIVE]
    lines = ["# Belt Holders", "", f"> Lineal championship belts for {len(LIVE)} leagues: {', '.join(names[:-1])} and {names[-1]}. The belt passes to whoever beats the holder, game by game, back to each league's first game. Updated every two hours.", ""]
    for lg in LIVE:
        d = datas[lg["key"]]
        cur = d["current"]
        lines += [f"## {lg['long_name']}", f"- Current holder: {cur['name']} (since {cur['start_date']}, {plural(cur.get('defenses', 0), 'defense')})",
                  f"- [Current holder and next defense]({SITE_URL}/{lg['key']}/)", f"- [Every reign]({SITE_URL}/{lg['key']}/history/)",
                  f"- [Records]({SITE_URL}/{lg['key']}/records/)", f"- [Data downloads (CSV)]({SITE_URL}/{lg['key']}/data/)", ""]
    lines += ["## Other", f"- [Rules]({SITE_URL}/rules/)", f"- [JSON API]({SITE_URL}/api/current.json)", f"- [Every belt, all three sites (JSON)]({SITE_URL}/api/network.json)", f"- [Every belt right now]({SITE_URL}/all/)", "- Sister sites: https://collegefootballbelt.com, https://collegebasketballbelt.com (men's and women's belts)"]
    write("llms.txt", "\n".join(lines) + "\n")
    write("manifest.json", json.dumps({"name": "Belt Holders", "short_name": "Belt Holders", "start_url": "/", "display": "standalone",
                                       "background_color": "#e7e2d5", "theme_color": "#211a12",
                                       "icons": [{"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                                                 {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}, indent=1))


def build_offline():
    """/offline.html for the service worker (sw.js)."""
    body = """<section class="wrap prose"><div class="kicker">Offline</div><h1 class="disp">No connection</h1>
<p>You're offline, and this page isn't saved on this device yet. Pages you've already opened still work; the belts will be back when you are.</p>
<p><a href="/">Back to every belt →</a></p></section>"""
    write("offline.html", page("You're offline", body, path="/offline.html", description="You're offline.", robots="noindex"))


def copy_assets():
    for f in ("sw.js",) + ("styles.css", "favicon.png", "favicon.ico", "apple-touch-icon.png", "icon-512.png", "og.png", "tablekit.js"):
        shutil.copy(f, os.path.join(OUT, f))
    # N-6 (audit #2): the site serves its own fonts (the files the Instagram cards already use)
    os.makedirs(os.path.join(OUT, "fonts"), exist_ok=True)
    for f in os.listdir(os.path.join("ig_templates", "fonts")):
        if f.endswith(".woff2") or f == "OFL.txt":
            shutil.copy(os.path.join("ig_templates", "fonts", f), os.path.join(OUT, "fonts", f))


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    datas = {}
    missing = [lg["key"] for lg in LIVE if not os.path.exists(os.path.join("data", lg["key"], "lineage.json"))]
    if missing:
        print("no lineage yet, skipping:", missing)
        LIVE[:] = [lg for lg in LIVE if lg["key"] not in missing]
    only = {k for k in os.environ.get("BELT_ONLY", "").split(",") if k}      # local dev: BELT_ONLY=nhl,epl builds a subset
    if only:
        LIVE[:] = [lg for lg in LIVE if lg["key"] in only]
        PRIMARY[:] = [k for k in PRIMARY if k in only]
        ORDER[:] = [k for k in ORDER if k in only]
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
    import site_extras
    site_extras.build_all(datas)
    for lg in LIVE:
        build_teams(lg, datas[lg["key"]])      # after build_all: team pages list players from d["_players"] (audit #2, 6.2)
    build_network_news(datas)
    build_ufwc_page(datas)
    build_my_belts(datas)
    build_static_pages(datas)
    build_api(datas)
    import network                      # the belt network: api/network.json, network-bar.js, /all/, /today/
    network.build_network_json(sys.modules[__name__], datas)
    network.build_pages(sys.modules[__name__], datas)
    network.build_doubles(sys.modules[__name__])
    network.build_cities(sys.modules[__name__], datas)
    build_offline()
    build_feed(datas)
    build_meta_files(datas)
    network.build_network_feed(sys.modules[__name__], OUT)
    network.build_network_ics(sys.modules[__name__], datas, OUT)      # feature 7.11: /all/belt.ics
    network.build_digest(sys.modules[__name__], datas, OUT)            # feature 7.10: /digest/ and digest/feed.xml
    try:
        network.build_network_leaderboard(sys.modules[__name__], OUT)   # feature 7.15: /leaderboard/, every belt
    except Exception as ex:  # noqa: BLE001
        print(f"network leaderboard skipped: {ex}")
    try:
        network.build_network_daily(sys.modules[__name__], datas, OUT)  # feature 7.12: /daily/, five belts a day
    except Exception as ex:  # noqa: BLE001 -- a puzzle must never break the deploy
        print(f"network daily skipped: {ex}")
    build_sitemap(datas)
    copy_assets()
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print(f"Built {n} files into {OUT}/")
    gone = sorted(x for x in CRUMB_REFS if not os.path.exists(os.path.join(OUT, x.strip("/"), "index.html")))
    if gone:
        print(f"WARNING: {len(gone)} breadcrumb targets have no page: {gone[:8]}")
    import indexnow
    indexnow.write(OUT)


if __name__ == "__main__":
    main()
