"""
The belt network (audit section 5): every lineal belt on the three sites in one place.

    api/network.json   every belt (16 pro leagues + college football + men's and women's college
                       basketball): holder, colors, reign, state and next game. Read by
                       network-bar.js on all three sites, and by anyone else (CORS is open).
    network-bar.js     the footer "Belt network" row, hydrated client-side from network.json,
                       with the build-time links as the fallback. Copied as-is into the other repos.
    /all/              "Every belt right now": one card per belt, soonest belt game first.
    /today/            every belt game today and over the next week, across every sport.

The college belts come from each site's api/current.json at build time (plus school colors from
the College Basketball Belt's team list). Everything degrades to plain links if a fetch fails.
"""

import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import features as F

SITE = "https://beltholders.com"
COLLEGE = [
    # key, sport, name, short, site url, api url, badge, feed
    ("cfb", "College football", "The College Football Belt", "College football", "https://collegefootballbelt.com/",
     "https://collegefootballbelt.com/api/current.json", None, "https://collegefootballbelt.com/feed.xml"),
    ("cbb", "College basketball", "The College Basketball Belt", "Men's college hoops", "https://collegebasketballbelt.com/",
     "https://collegebasketballbelt.com/api/current.json", "https://collegebasketballbelt.com/badge.svg",
     "https://collegebasketballbelt.com/feed.xml"),
    ("wcbb", "College basketball", "The Women's College Basketball Belt", "Women's college hoops", "https://collegebasketballbelt.com/women/",
     "https://collegebasketballbelt.com/women/api/current.json", "https://collegebasketballbelt.com/women/badge.svg",
     "https://collegebasketballbelt.com/women/feed.xml"),
]
_CACHE = {}


def fetch(url):
    if url in _CACHE:
        return _CACHE[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "beltholders.com build"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _CACHE[url] = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 -- a sister site being down must never break this build
        _CACHE[url] = None
    return _CACHE[url]


def school_colors():
    teams = fetch("https://raw.githubusercontent.com/rjr5021/college-basketball-belt/main/data/teams.json") or []
    return {t.get("school"): (t.get("primaryColor"), t.get("secondaryColor")) for t in teams if t.get("school")}


def _hex(c, fallback):
    return f"#{c.lstrip('#')}" if c else fallback


def college_belts():
    colors = school_colors()
    out = []
    for key, sport, name, short, site, api, badge, feed in COLLEGE:
        j = fetch(api) or {}
        h = j.get("holder")
        p, s = colors.get(h, (None, None))
        ng = j.get("next_game") or {}
        nxt = j.get("next") if isinstance(j.get("next"), dict) and "opponent_short" in j["next"] else None
        if not nxt and ng.get("date"):
            nxt = {"date": ng["date"], "time_et": None, "opponent": ng.get("opponent"), "opponent_short": ng.get("opponent"),
                   "home": bool(ng.get("is_home")), "neutral": bool(ng.get("neutral")), "venue": ng.get("venue_name"),
                   "tv": ng.get("tv"), "win_prob": None, "url": site + ("next/" if key != "cfb" else "")}
            if ng.get("raw_date") and not ng.get("start_time_tbd"):
                try:
                    t = datetime.fromisoformat(ng["raw_date"].replace("Z", "+00:00"))
                    nxt["time_et"] = t.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M")
                except ValueError:
                    pass
        out.append({
            "key": key, "sport": sport, "name": name, "short": short, "site": site.split("//")[1].split("/")[0], "url": site,
            "holder": h, "holder_short": h, "colors": [_hex(p, "#211a12"), _hex(s, "#a97f38")],
            "since": j.get("since"), "defenses": j.get("defenses"), "reign_no": j.get("team_reign_number") or j.get("reign"),
            "state": j.get("state") or ("in_season_next_game" if nxt else "offseason_schedule_pending"),
            "next": nxt, "badge": badge, "og_image": None, "feed": feed, "ok": bool(h),
        })
    return out


def pro_belts(datas):
    from leagues import LIVE
    out = []
    for lg in LIVE:
        d = datas[lg["key"]]
        cur = d["current"]
        p, s = lg["team_colors"](cur["team"])
        st = F.belt_state(lg, d)
        nxt = F.next_payload(lg, d, SITE)
        out.append({
            "key": lg["key"], "sport": lg.get("sport", ""), "name": lg["long_name"], "short": lg["name"], "site": "beltholders.com",
            "url": f"{SITE}/{lg['key']}/", "holder": lg["team_name"](cur["team"]), "holder_short": lg["short_name"](cur["team"]),
            "colors": [p, s or "#a97f38"], "since": cur["start_date"], "defenses": cur.get("defenses", 0), "reign_no": cur["reign_no"],
            "state": st["state"], "status": d.get("status"), "data_ok": not st.get("delayed"),
            "next": nxt, "badge": f"{SITE}/{lg['key']}/badge.svg", "og_image": f"{SITE}/{lg['key']}/og.png",
            "feed": f"{SITE}/{lg['key']}/feed.xml", "ok": True,
        })
    return out


def belts(datas):
    if "belts" not in _CACHE:
        _CACHE["belts"] = pro_belts(datas) + college_belts()
    return _CACHE["belts"]


def build_network_json(S, datas):
    doc = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "about": f"{SITE}/all/", "sites": ["https://beltholders.com", "https://collegefootballbelt.com", "https://collegebasketballbelt.com"],
           "belts": belts(datas)}
    S.write("api/network.json", json.dumps(doc, indent=1))
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "network-bar.js"), encoding="utf-8") as f:
        S.write("network-bar.js", f.read())


# ------------------------------------------------------------------ pages --

def _when(b, today):
    n = b.get("next")
    return (n["date"], n.get("time_et") or "99:99") if n else ("9999", "")


def _card(S, b, today):
    e = S.e
    top, bottom, ink, accent = S.plate(b["colors"][0], b["colors"][1])
    n = b.get("next")
    if n:
        where = "vs." if n["home"] or n["neutral"] else "at"
        days = (date.fromisoformat(n["date"]) - today).days
        when = "Today" if days == 0 else "Tomorrow" if days == 1 else f"{S.weekday(n['date'])} {S.d_short(n['date'])}"
        foot = f'<span class="disp">{where} {e(n["opponent_short"] or n["opponent"] or "")}</span><span class="mono" data-date="{n["date"]}">{when}</span>'
    else:
        foot = f'<span class="disp">{"Frozen" if b["state"] == "postseason_holder_out" else "Offseason"}</span><span class="mono">{e(b["site"])}</span>'
    since = f"Since {S.d_short(b['since'], True)}" if b.get("since") else ""
    if b.get("defenses") is not None:
        since += f" · {S.plural(b['defenses'], 'defense')}"
    return f"""<a class="tile small" href="{b['url']}" style="--top:{top};--bottom:{bottom};--ink:{ink};--accent:{accent}">
  <div class="tile-head"><span class="disp">{e(b['short'])}</span><span class="mono status"><i></i>{e(b['sport'])}</span></div>
  <div class="tile-body"><div class="mono k">Holder</div><div class="disp name" style="{S.fit(b['holder_short'] or b['short'])}">{e(b['holder_short'] or '—')}</div><p>{since}</p></div>
  <div class="tile-foot">{foot}</div>
</a>"""


ESPN_EXTRA = {"cfb": "football/college-football", "cbb": "basketball/mens-college-basketball",
              "wcbb": "basketball/womens-college-basketball"}


def _espn_path(key):
    return F.ESPN.get(key) or ESPN_EXTRA.get(key)


def _game_row(S, b, today):
    e = S.e
    n = b["next"]
    names = [x for x in (b.get("holder"), b.get("holder_short"), n.get("opponent"), n.get("opponent_short")) if x]
    live = (f' data-espn="{_espn_path(b["key"])}" data-names="{e("|".join(names))}"') if _espn_path(b["key"]) else ""
    where = "vs." if n["home"] or n["neutral"] else "at"
    t = S.kickoff_12h(n.get("time_et")) if n.get("time_et") else "Time TBA"
    odds = f'{round(n["win_prob"] * 100)}% to defend' if n.get("win_prob") is not None else ""
    tv = e(n["tv"]) if n.get("tv") else ""
    return (f'<tr data-date="{n["date"]}"{live}><td class="mono">{t}</td><td><span class="mono lg">{e(b["short"])}</span></td>'
            f'<td><i style="background:{b["colors"][0]}"></i><b>{e(b["holder_short"])}</b> {where} {e(n["opponent_short"] or n["opponent"] or "")}'
            f'<span class="mono livescore"></span></td>'
            f'<td class="mono">{odds}</td><td class="mono">{tv}</td><td class="r"><a class="mono" href="{n["url"]}">Preview →</a></td></tr>')


TODAY_JS = """<script>(function(){try{var p=new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York"}).format(new Date());
document.querySelectorAll("[data-day]").forEach(function(s){if(s.dataset.day<p)s.remove();});
var t=document.querySelector("[data-day='"+p+"'] h2");if(t)t.textContent="Today";
var tm=new Date(Date.parse(p+"T12:00:00Z")+864e5).toISOString().slice(0,10),u=document.querySelector("[data-day='"+tm+"'] h2");if(u)u.textContent="Tomorrow";
/* Phase 4 (audit 7.1): live scores for today's belt games, from ESPN's public scoreboards */
var rows=[].slice.call(document.querySelectorAll("tr[data-espn][data-date='"+p+"']"));if(!rows.length||!window.fetch)return;
var low=function(x){return String(x||"").toLowerCase();},paths={};rows.forEach(function(r){(paths[r.dataset.espn]=paths[r.dataset.espn]||[]).push(r);});
function tick(){Object.keys(paths).forEach(function(path){fetch("https://site.api.espn.com/apis/site/v2/sports/"+path+"/scoreboard?dates="+p.replace(/-/g,"")+"&limit=400").then(function(r){return r.json();}).then(function(j){
paths[path].forEach(function(row){var names=row.dataset.names.split("|").map(low);(j.events||[]).some(function(ev){var c=ev.competitions[0].competitors;
var hit=function(x){var tm=x.team||{};return [tm.displayName,tm.shortDisplayName,tm.name,tm.location].some(function(n){return names.indexOf(low(n))>=0;});};
if(!(hit(c[0])&&hit(c[1])))return false;var st=ev.status.type;if(st.state==="pre")return true;
var sc=c.map(function(x){return (x.team.abbreviation||x.team.shortDisplayName)+" "+x.score;}).join(" \u2013 ");
row.querySelector(".livescore").textContent=" \u00b7 "+(st.state==="in"?"LIVE ":"")+sc+" \u00b7 "+(st.shortDetail||"");row.classList.toggle("islive",st.state==="in");return true;});});}).catch(function(){});});}
tick();setInterval(tick,60000);}catch(e){}})();</script>"""


def build_pages(S, datas):
    today = date.today()
    bs = sorted(belts(datas), key=lambda b: _when(b, today))
    playing = [b for b in bs if b.get("next") and b["next"]["date"] <= (today + timedelta(days=7)).isoformat()]
    cards = "".join(_card(S, b, today) for b in bs)
    frozen = [b for b in bs if b["state"] == "postseason_holder_out"]
    body = f"""<section class="wrap block">
  <div class="kicker">The belt network</div>
  <div class="head"><h1 class="disp">Every belt right now</h1><span class="mono note">{len(bs)} lineal belts · {len(playing)} on the line this week</span></div>
  <p class="intro">Every lineal championship we track, on one page: the {len(bs) - 3} pro leagues here at Belt Holders, plus the college football belt and the men's and women's college basketball belts. Soonest belt game first.{(' Frozen right now: ' + ', '.join(S.e(b['short']) + ' (' + S.e(b['holder_short']) + ')' for b in frozen) + ', done for the season but still holding.') if frozen else ''}</p>
  <div class="tiles small">{cards}</div>
  <p class="mono more"><a href="/today/">Belt games today and this week →</a> · <a href="/network/doubles/">Double belts →</a> · <a href="/network/cities/">Belt cities →</a> · <a href="/all/feed.xml">Every title change (RSS)</a> · <a href="/api/network.json">network.json</a></p>
</section>
{widgets_html(S, datas, today)}"""
    S.write("all/index.html", S.page("Every belt right now", body, path="/all/", active="leagues",
                                     description=f"All {len(bs)} lineal championship belts on one page: NFL, NBA, NHL, MLB, soccer, college football and college basketball. Who holds each one and when it's next on the line."))
    by_day = {}
    for b in playing:
        by_day.setdefault(b["next"]["date"], []).append(b)
    days = []
    for dstr in sorted(by_day):
        rows = "".join(_game_row(S, b, today) for b in sorted(by_day[dstr], key=lambda b: b["next"].get("time_et") or "99"))
        days.append(f'<section class="block" data-day="{dstr}"><h2 class="disp sub">{S.weekday(dstr)}, {S.d_long(dstr)}</h2>'
                    f'<div class="tablewrap"><table class="history"><thead><tr><th class="mono">ET</th><th class="mono">Belt</th><th class="mono">Game</th>'
                    f'<th class="mono">Defend odds</th><th class="mono">TV</th><th><span class="sr">Preview</span></th></tr></thead><tbody>{rows}</tbody></table></div></section>')
    body = f"""<section class="wrap block">
  <div class="kicker">The belt network</div>
  <div class="head"><h1 class="disp">Belt games this week</h1><span class="mono note">Every sport · times Eastern</span></div>
  <p class="intro">Every game in the next seven days where a lineal belt is on the line, across the pro leagues and college football and basketball. A holder's next game is only a belt game while it keeps winning, so later dates can change.</p>
  {''.join(days) if days else '<p class="intro">No belt games on the schedule this week.</p>'}
  <p class="mono more"><a href="/all/">Every belt right now →</a></p>
</section>{TODAY_JS}"""
    S.write("today/index.html", S.page("Belt games today and this week", body, path="/today/", active="leagues",
                                       description="Every lineal championship belt game today and this week across the NFL, NBA, NHL, MLB, soccer and college sports: times, TV and each holder's chance to defend."))


# ----------------------------------------------- network on this day / stories / feed --

COLLEGE_GAMES = [
    # label, api, game url maker
    ("College football", "https://collegefootballbelt.com/api/games.json",
     lambda g: f"https://collegefootballbelt.com/games/{g['game_id']}.html" if g.get("game_id") else "https://collegefootballbelt.com/"),
    ("Men's college hoops", "https://collegebasketballbelt.com/api/games.json",
     lambda g: f"https://collegebasketballbelt.com/seasons/{g['season']}/#g{g['n']}"),
    ("Women's college hoops", "https://collegebasketballbelt.com/women/api/games.json",
     lambda g: f"https://collegebasketballbelt.com/women/seasons/{g['season']}/#g{g['n']}"),
]


def _winner_first(score):
    try:
        a, b = (int(x) for x in str(score).split("-")[:2])
    except (TypeError, ValueError):
        return str(score or "").replace("-", "–")
    return f"{max(a, b)}–{min(a, b)}"


def college_changes():
    """{mm-dd: [{date, html}]}: every title change on the three college belts (audit 5.5)."""
    if "otd" in _CACHE:
        return _CACHE["otd"]
    import html as H
    by = {}
    for label, api, link in COLLEGE_GAMES:
        j = fetch(api) or {}
        for g in j.get("belt_games") or []:
            if g.get("outcome") != "changed":
                continue
            w = g.get("new_holder_name") or g.get("new_holder")
            l = g.get("holder_name") or g.get("holder")
            if not (w and l) or not isinstance(w, str):
                continue
            line = (f'<li><span class="mono lg">{H.escape(label)}</span><i style="background:var(--brass)"></i>'
                    f'<div>{H.escape(w)} beat {H.escape(l)} {_winner_first(g.get("score"))} and took the belt</div>'
                    f'<a class="mono when" href="{link(g)}">{g["date"][:4]}</a></li>')
            by.setdefault(g["date"][5:10], []).append({"date": g["date"], "html": line, "belt": label, "w": w, "l": l,
                                                       "score": _winner_first(g.get("score")), "url": link(g)})
    for k in by:
        by[k].sort(key=lambda x: x["date"], reverse=True)
    _CACHE["otd"] = by
    return by


def otd_extra(k):
    return college_changes().get(k, [])


def network_stories():
    out = []
    idx = fetch("https://collegefootballbelt.com/search-index.json") or []
    for x in idx:
        if x.get("t") == "Story" and x.get("u"):
            out.append({"belt": "College football", "title": x["n"], "url": "https://collegefootballbelt.com/" + x["u"]})
    for belt, api in (("Men's college hoops", "https://collegebasketballbelt.com/stories/index.json"),
                      ("Women's college hoops", "https://collegebasketballbelt.com/women/stories/index.json")):
        for x in fetch(api) or []:
            if x.get("url") and x.get("title"):
                out.append({"belt": belt, "title": x["title"], "dek": x.get("dek"), "url": x["url"]})
    return out


def _fetch_text(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "beltholders.com build"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None


_NET_ITEMS = None


def network_items(out="site"):
    """Every title change on every belt, newest first, merged from the three sites' feeds:
    [(when, site label, title, link, guid, description)]. Fetched once per build."""
    global _NET_ITEMS
    if _NET_ITEMS is not None:
        return _NET_ITEMS
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    sources = [("Belt Holders", open(os.path.join(out, "feed.xml"), encoding="utf-8").read() if os.path.exists(os.path.join(out, "feed.xml")) else None),
               ("College Football Belt", _fetch_text("https://collegefootballbelt.com/feed.xml")),
               ("College Basketball Belt", _fetch_text("https://collegebasketballbelt.com/feed.xml")),
               ("Women's College Basketball Belt", _fetch_text("https://collegebasketballbelt.com/women/feed.xml"))]
    items = []
    for label, xml in sources:
        if not xml:
            continue
        try:
            root = ET.fromstring(xml.encode("utf-8"))
        except ET.ParseError:
            continue
        for it in root.iter("item"):
            t, l, d = it.findtext("title") or "", it.findtext("link") or "", it.findtext("pubDate") or ""
            g = it.findtext("guid") or l
            try:
                when = parsedate_to_datetime(d)
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            items.append((when, label, t, l, g, it.findtext("description") or ""))
    items.sort(key=lambda x: x[0], reverse=True)
    _NET_ITEMS = items
    return items


def build_network_feed(S, out="site", limit=100):
    """/all/feed.xml: every title change on every belt, merged from the three sites' feeds."""
    import html as H
    items = network_items(out)
    body = "".join(
        f"<item><title>{H.escape(t)}</title><link>{H.escape(l)}</link><guid isPermaLink=\"false\">{H.escape(g)}</guid>"
        f"<pubDate>{w.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate><category>{H.escape(lab)}</category>"
        f"<description>{H.escape(ds)}</description></item>"
        for w, lab, t, l, g, ds in items[:limit])
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    S.write("all/feed.xml", '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>Every belt: title changes across the belt network</title><link>{SITE}/all/</link>"
            "<description>Every lineal title change on every belt: the pro leagues on Belt Holders, college football and men's and women's college basketball.</description>"
            f"<lastBuildDate>{now}</lastBuildDate>{body}</channel></rss>")
    return len(items)


# ------------------------------------------------------ cross-league stories --
# 6.3 (audit #2): stories that only make sense across leagues, at /stories/<slug>/.

LOCKOUTS = [  # league, label, first day without games, first day back
    ("nhl", "the 2004–05 NHL lockout (the whole season)", "2004-09-16", "2005-10-05"),
    ("nhl", "the 2012–13 NHL lockout", "2012-09-16", "2013-01-19"),
    ("nhl", "the 1994–95 NHL lockout", "1994-10-01", "1995-01-20"),
    ("nba", "the 2011 NBA lockout", "2011-07-01", "2011-12-25"),
    ("nba", "the 1998–99 NBA lockout", "1998-07-01", "1999-02-05"),
    ("mlb", "the 1994–95 baseball strike (no World Series)", "1994-08-12", "1995-04-25"),
    ("mlb", "the 2022 MLB lockout", "2021-12-02", "2022-04-07"),
    ("nfl", "the 1987 NFL strike", "1987-09-23", "1987-10-25"),
    ("nfl", "the 1982 NFL strike", "1982-09-21", "1982-11-21"),
    ("wnba", "the 2020 WNBA bubble season start", "2020-05-15", "2020-07-25"),
]


WORLD_CUP_WINNERS = {1930: "Uruguay", 1934: "Italy", 1938: "Italy", 1950: "Uruguay", 1954: "Germany", 1958: "Brazil", 1962: "Brazil", 1966: "England",
                     1970: "Brazil", 1974: "Germany", 1978: "Argentina", 1982: "Italy", 1986: "Argentina", 1990: "Germany", 1994: "Brazil", 1998: "France",
                     2002: "Brazil", 2006: "Italy", 2010: "Spain", 2014: "Germany", 2018: "France", 2022: "Argentina"}


def cross_stories(S, datas):
    """[(slug, title, dek, html)] for the network-wide stories."""
    from leagues import LIVE
    e = S.e
    by = {lg["key"]: lg for lg in LIVE}
    out = []
    # ---- 1. belts that lived through a lockout
    rows = []
    for key, label, start, back in LOCKOUTS:
        lg, d = by.get(key), datas.get(key)
        if not lg or not d:
            continue
        r = next((x for x in d["reigns"] if x["start_date"] <= start and (not x.get("end_date") or x["end_date"] >= start)), None)
        if not r:
            continue
        kept = (not r.get("end_date")) or r["end_date"] > back
        after = next((x for x in d["reigns"] if x["index"] == r["index"] + 1), None)
        quiet = (date.fromisoformat(back) - date.fromisoformat(start)).days
        rows.append((lg, r, label, start, back, kept, after, quiet))
    if rows:
        trs = "".join(f'<tr><td><span class="mono lg">{e(lg["name"])}</span> {e(label)}</td><td><i style="background:{lg["team_colors"](r["team"])[0]}"></i><a href="{F.reign_link(lg, d, r) if (d := datas[lg["key"]]) else "#"}">{e(r["name"])}</a><small>since {S.d_short(r["start_date"], True)}</small></td>'
                      f'<td class="mono r">{quiet:,}</td><td>{("Kept it: the first game back was a defense" if kept else "Lost it in the first game back to " + e(lg["team_name"](after["team"])) + (", " + S.won_score_text(after) if after.get("won_score") else "")) if after or kept else "Still holding"}</td></tr>'
                      for lg, r, label, start, back, kept, after, quiet in rows)
        kept_n = sum(1 for x in rows if x[5])
        html = f"""<p>A lockout or a strike freezes the belt with whoever has it: no games, no title defenses, and the days keep counting toward the reign. Here is every work stoppage in the pro belts' records, who was holding the belt when the games stopped, how long the belt sat idle, and what happened in the first game back. The holder kept it in {kept_n} of {len(rows)}.</p>
<div class="tablewrap"><table class="history keep3"><thead><tr><th class="mono">Stoppage</th><th class="mono">Holder going in</th><th class="mono r">Idle days</th><th class="mono">First game back</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="mono note">Idle days run from the first missed day to the first day with a game. The 2004–05 NHL season was cancelled outright, so that belt sat for more than a year.</p>"""
        out.append(("lockouts", "Belts that lived through a lockout", f"Every work stoppage in the pro belts' history: who was holding the belt, how long it sat idle, and whether they kept it when play resumed. The holder kept it {kept_n} times out of {len(rows)}.", html))
    # ---- 2. relegated with the belt
    rel = []
    for key in ("epl", "laliga", "seriea", "bundesliga", "ligue1", "eredivisie"):
        lg, d = by.get(key), datas.get(key)
        if not lg or not d:
            continue
        for v in d.get("vacancies") or []:
            rel.append((v["effective_date"], lg, v))
    rel.sort(key=lambda x: x[0], reverse=True)
    if rel:
        trs = "".join(f'<tr><td class="mono">{S.d_short(dt, True)}</td><td><span class="mono lg">{e(lg["name"])}</span></td><td><i style="background:{lg["team_colors"](v["team"])[0]}"></i>{F.tlink(lg, v["team"])}<small>held it since {S.d_short(v["reign_started"], True)}</small></td><td>{F.tlink(lg, v["reverted_to"])}</td></tr>'
                      for dt, lg, v in rel)
        html = f"""<p>Only in soccer can a champion leave the league. When a club holding a belt is relegated, it can't defend it, so the belt reverts to the most recent earlier holder still in the division, the same rule the college belts use when a program drops down. {len(rel)} times a holder has left the division with the belt across the European leagues we track (relegation, and in 1915 the league shutting down for the war); the most recent was {e(rel[0][1]["team_name"](rel[0][2]["team"]))} in the {e(rel[0][1]["name"])} in {rel[0][0][:4]}.</p>
<div class="tablewrap"><table class="history keep3"><thead><tr><th class="mono">Reverted</th><th class="mono">League</th><th class="mono">Went down holding it</th><th class="mono">Belt went back to</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="mono note">A reversion is dated the day after the relegated holder's last match. Clubs that disappeared for other reasons (war years, folded clubs) are listed too when the record shows a holder leaving the league.</p>"""
        out.append(("relegated", "Relegated with the belt", f"{len(rel)} times a holder has left the division with a belt, and who the belt went back to.", html))
    # ---- 3. the belt at the World Cup
    lg, d = by.get("intl"), datas.get("intl")
    if lg and d:
        wc = [bg for bg in d["belt_games"] if (bg.get("note") or "") == "FIFA World Cup"]
        # the champions model takes the last match by date, which the 1950 final group breaks; the winners are fixed history
        champs = {c["season"]: c for c in (d.get("models") or {}).get("champions") or []}
        for y, w in WORLD_CUP_WINNERS.items():
            champs[y] = {"season": y, "champion": w}
        years = sorted({bg["season"] for bg in wc})
        trs = []
        for y in years:
            gs = [bg for bg in wc if bg["season"] == y]
            first, last = gs[0], gs[-1]
            into = first.get("holder") or first["new_holder"]
            left = last["new_holder"]
            changes = [bg for bg in gs if bg["outcome"] == "changed"]
            champ = (champs.get(y) or {}).get("champion")
            path = " → ".join([lg["short_name"](into)] + [lg["short_name"](bg["new_holder"]) for bg in changes])
            trs.append(f'<tr><td class="mono"><a href="{F.b(lg)}/seasons/{y}/">{y}</a></td><td><i style="background:{lg["team_colors"](into)[0]}"></i>{F.tlink(lg, into)}</td><td>{e(path) if changes else "kept it all tournament"}</td><td><i style="background:{lg["team_colors"](left)[0]}"></i>{F.tlink(lg, left)}</td><td>{(F.tlink(lg, champ) + (" ✓" if champ == left else "")) if champ else "—"}</td><td class="mono r">{len(gs)}</td></tr>')
        matched = sum(1 for y in years if (champs.get(y) or {}).get("champion") and champs[y]["champion"] == [bg for bg in wc if bg["season"] == y][-1]["new_holder"])
        if trs:
            html = f"""<p>The International belt doesn't stop for the World Cup; the holder's World Cup matches are title defenses like any other. Here is every tournament the belt has been to: who carried it in, how it moved during the tournament, who carried it out, and whether that was the team lifting the trophy. The belt left the tournament with the champion {matched} times in {len(years)}.</p>
<div class="tablewrap"><table class="history keep3"><thead><tr><th class="mono">World Cup</th><th class="mono">Carried it in</th><th class="mono">How it moved</th><th class="mono">Carried it out</th><th class="mono">Champion</th><th class="mono r">Belt games</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>
<p class="mono note">A World Cup without the holder in the field leaves the belt frozen for the month; those tournaments don't appear here.</p>"""
            out.append(("world-cup", "The belt at the World Cup", f"Every World Cup the International belt has been to, how it moved, and whether it left with the champion ({matched} of {len(years)}).", html))
    return out


# ------------------------------------------------------- the weekly digest --
# Feature 7.10 (audit #2): /digest/ -- "Every belt this week": the title changes across all three
# sites, every pro belt's holder as the week ends, the belt games played and the ones coming up
# with TV, as one page per ISO week (the current week at /digest/, the last 26 at /digest/<week>/)
# and an RSS feed (/digest/feed.xml) an RSS-to-email service turns into the weekly mail.

DIGEST_WEEKS = 26


def _week_bounds(d):
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def build_digest(S, datas, out="site"):
    from leagues import LIVE
    e = S.e
    today = date.today()
    this_start, _ = _week_bounds(today)
    items = network_items(out)
    weeks = []
    for k in range(DIGEST_WEEKS + 1):
        start = this_start - timedelta(weeks=k)
        end = start + timedelta(days=6)
        key = f"{start.isocalendar()[0]}-W{start.isocalendar()[1]:02d}"
        # ---- title changes: pro belts from the lineages, the college belts from their feeds
        changes = []
        for lg in LIVE:
            d = datas[lg["key"]]
            for r in d["reigns"]:
                if start.isoformat() <= r["start_date"] <= end.isoformat() and r.get("won_from"):
                    changes.append((r["start_date"], lg["name"], f"{r['name']} beat {lg['team_name'](r['won_from'], r['season'])} {S.won_score_text(r)} and took the {lg['name']} belt",
                                    F.news_href(lg, d, r), lg["team_colors"](r["team"])[0]))
        for when, label, t, l, g, ds in items:
            if label == "Belt Holders":
                continue
            dd = when.astimezone(ZoneInfo("America/New_York")).date()
            if start <= dd <= end:
                changes.append((dd.isoformat(), label, t, l, "#a97f38"))
        changes.sort(key=lambda x: x[0], reverse=True)
        # ---- belt games played this week (pro), closest calls
        played, closest = 0, []
        for lg in LIVE:
            d = datas[lg["key"]]
            for bg in d["belt_games"]:
                if start.isoformat() <= bg["date"] <= end.isoformat():
                    played += 1
                    if bg["outcome"] != "changed" and bg.get("holder") and bg.get("margin") is not None and not bg["outcome"].endswith("(tie)"):
                        closest.append((bg["margin"], bg["date"], lg, bg))
        closest.sort(key=lambda x: (x[0], x[1]))
        # ---- holders as the week ends
        holders = []
        for lg in LIVE:
            d = datas[lg["key"]]
            r = next((x for x in reversed(d["reigns"]) if x["start_date"] <= end.isoformat()), None)
            if r:
                holders.append((lg, r))
        # ---- coming up (current week only): each belt's next game with TV
        upcoming = []
        if k == 0:
            for b in belts(datas):
                n = b.get("next")
                if n and n.get("date") and n["date"] <= (today + timedelta(days=7)).isoformat():
                    upcoming.append((n["date"], b, n))
            upcoming.sort(key=lambda x: (x[0], x[2].get("time_et") or "99"))
        weeks.append({"key": key, "start": start, "end": end, "changes": changes, "played": played, "closest": closest[:5], "holders": holders, "upcoming": upcoming})

    def render(w, current):
        start, end = w["start"], w["end"]
        label = f"{S.d_short(start.isoformat(), False)} – {S.d_short(end.isoformat(), True)}"
        ch = "".join(f'<li><span class="mono lg">{e(lab)}</span><i style="background:{c}"></i><div><a href="{u}"><b class="disp">{e(t)}</b></a></div><span class="mono when">{S.d_short(dt, True)}</span></li>'
                     for dt, lab, t, u, c in w["changes"])
        ch_html = f'<ul class="feed news">{ch}</ul>' if ch else '<p class="intro">No belt changed hands this week.</p>'
        hold = "".join(f'<a class="chip" style="--c:{lg["team_colors"](r["team"])[0]}" href="/{lg["key"]}/">{e(lg["name"])}: {e(lg["short_name"](r["team"]))}</a>' for lg, r in w["holders"])
        cl = "".join(f'<tr><td class="mono">{S.d_short(bg["date"], True)}</td><td><span class="mono lg">{e(lg["name"])}</span> {e(lg["team_name"](bg["holder"], bg["season"]))} held off {e(lg["team_name"](bg["opponent"], bg["season"]))} {e(F._winner_score(bg))}{" (OT)" if bg.get("ot") else ""}</td><td class="r"><a class="mono" href="{F.game_url(lg, bg)}">Game →</a></td></tr>'
                     for m, dt, lg, bg in w["closest"])
        up = "".join(f'<tr><td class="mono">{S.d_short(dt, False)}{(" · " + S.kickoff_12h(n["time_et"])) if n.get("time_et") else ""}</td><td><span class="mono lg">{e(b["short"])}</span> <b>{e(b["holder_short"])}</b> {"vs." if n.get("home") or n.get("neutral") else "at"} {e(n.get("opponent_short") or n.get("opponent") or "")}</td><td class="mono">{e(n["tv"]) if n.get("tv") else ""}</td><td class="r"><a class="mono" href="{n["url"]}">Preview →</a></td></tr>'
                     for dt, b, n in w["upcoming"])
        nav = ""
        i = next(j for j, x in enumerate(weeks) if x["key"] == w["key"])
        older = weeks[i + 1] if i + 1 < len(weeks) else None
        newer = weeks[i - 1] if i else None
        nav = ('<nav class="pager mono">' + (f'<a href="/digest/{older["key"]}/">← Week of {S.d_short(older["start"].isoformat())}</a>' if older else "<span></span>")
               + '<a href="/digest/">This week</a>' + (f'<a href="/digest/{newer["key"]}/">Week of {S.d_short(newer["start"].isoformat())} →</a>' if newer and not current else "<span></span>") + "</nav>")
        body = f"""<section class="wrap block">
  <div class="kicker">The weekly digest · every belt</div>
  <div class="head"><h1 class="disp">{"This week in the belts" if current else "The belts, week of " + S.d_short(start.isoformat())}</h1><span class="mono note">{e(label)}</span></div>
  <p class="intro">{S.plural(len(w['changes']), 'title change')} across the belt network and {S.plural(w['played'], 'pro belt game')} this week. <a href="/digest/feed.xml">Get this as a weekly email (RSS)</a> · <a href="/all/">every belt right now →</a></p>
  <h2 class="disp sub">Changed hands</h2>
  {ch_html}
  {f'<h2 class="disp sub">Coming up</h2><div class="tablewrap"><table class="history"><thead><tr><th class="mono">When</th><th class="mono">Belt game</th><th class="mono">TV</th><th></th></tr></thead><tbody>{up}</tbody></table></div>' if up else ''}
  {f'<h2 class="disp sub">Closest calls</h2><div class="tablewrap"><table class="history"><thead><tr><th class="mono">Date</th><th class="mono">Defense</th><th></th></tr></thead><tbody>{cl}</tbody></table></div>' if cl else ''}
  <h2 class="disp sub">Holding as the week ends</h2>
  <div class="strip">{hold}</div>
  {nav}
</section>"""
        return body, label

    for i, w in enumerate(weeks):
        body, label = render(w, i == 0)
        if i == 0:
            S.write("digest/index.html", S.page("This week in the belts: every title change, every league", body, path="/digest/", active="leagues",
                                               description=f"The weekly belt digest: every lineal title change across the pro leagues, college football and college basketball, the belt games coming up with TV, and who holds each belt ({label})."))
        S.write(f"digest/{w['key']}/index.html", S.page(f"The belts, week of {S.d_short(w['start'].isoformat(), True)}", body, path=f"/digest/{w['key']}/", active="leagues",
                                                        description=f"Every belt title change and belt game in the week of {S.d_long(w['start'].isoformat())}, across the belt network.",
                                                        robots="noindex,follow" if i == 0 else None))
    # the feed: one item per completed week (the current week joins it on Monday), summary text
    import html as H
    its = []
    for w in weeks[1:13]:
        summ = (f"{len(w['changes'])} title change{'s' if len(w['changes']) != 1 else ''}: " + "; ".join(t for _, _, t, _, _ in w["changes"][:12])) if w["changes"] else "No belt changed hands."
        dt = datetime.combine(w["end"], datetime.min.time()).replace(tzinfo=ZoneInfo("America/New_York"))
        its.append(f"<item><title>The belts, week of {H.escape(S.d_short(w['start'].isoformat(), True))}</title><link>{SITE}/digest/{w['key']}/</link>"
                   f"<guid isPermaLink=\"true\">{SITE}/digest/{w['key']}/</guid><pubDate>{dt.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
                   f"<description>{H.escape(summ)}</description></item>")
    S.write("digest/feed.xml", '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>The weekly belt digest</title>'
            f'<link>{SITE}/digest/</link><description>Every belt, every week: title changes across the belt network and the belt games ahead.</description>'
            + "".join(its) + "</channel></rss>")
    return len(weeks)


def build_network_ics(S, datas, out="site"):
    """/all/belt.ics (feature 7.11, audit #2): one calendar subscription with every belt game on every
    belt -- the pro leagues' events from this build, plus the college sites' belt.ics feeds fetched at
    build time (their VEVENT blocks are copied through unchanged, alarms included)."""
    import re as _re
    from leagues import LIVE
    events = []
    for lg in LIVE:
        events += (datas.get(lg["key"]) or {}).get("_ics_events") or []
    for url in ("https://collegefootballbelt.com/belt.ics", "https://collegebasketballbelt.com/belt.ics",
                "https://collegebasketballbelt.com/women/belt.ics"):
        txt = _fetch_text(url)
        if txt:
            events += ["\r\n".join(l for l in blk.replace("\r\n", "\n").split("\n") if l.strip())
                       for blk in _re.findall(r"BEGIN:VEVENT.*?END:VEVENT", txt, _re.S)]
    cal = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Belt Holders//Every belt//EN", "CALSCALE:GREGORIAN",
                       "X-WR-CALNAME:Every belt game (the belt network)", "X-WR-TIMEZONE:America/New_York",
                       "X-WR-CALDESC:Every lineal-belt title defense across the belt network: the pro leagues on beltholders.com\\, college football and men's and women's college basketball. One subscription instead of nineteen.",
                       "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H", *events, "END:VCALENDAR"]) + "\r\n"
    S.write("all/belt.ics", cal)
    return len(events)


# ------------------------------------------------ Phase 4: cross-belt widgets --

def widgets_html(S, datas, today=None, moved_card=True):
    """Audit 7.20 on the homepage and /all/: belts that moved this week, the longest current
    reigns across every belt, and this week's upset watch (holders under 40% to defend).
    B-4 (audit #2): the homepage already lists the latest title changes right below this block,
    so it passes moved_card=False and gets the next belt games on the line instead."""
    from leagues import LIVE
    e = S.e
    today = today or date.today()
    week_ago = (today - timedelta(days=7)).isoformat()
    moved = []
    for lg in LIVE:
        for r in datas[lg["key"]]["reigns"]:
            if r.get("won_from") and r["start_date"] >= week_ago:
                moved.append((r["start_date"], lg["name"], lg["short_name"](r["team"]), lg["short_name"](r["won_from"]),
                              f"/{lg['key']}/"))
    for items in college_changes().values():
        for x in items:
            if x["date"] >= week_ago:
                moved.append((x["date"], x["belt"], x["w"], x["l"], x["url"]))
    moved.sort(reverse=True)
    bs = belts(datas)
    longest = sorted((b for b in bs if b.get("since")), key=lambda b: b["since"])[:5]
    week = (today + timedelta(days=7)).isoformat()
    upsets = sorted((b for b in bs if b.get("next") and b["next"].get("win_prob") is not None
                     and b["next"]["date"] <= week and b["next"]["win_prob"] < 0.4), key=lambda b: b["next"]["win_prob"])
    li = lambda rows: "".join(rows) or '<li><span class="mono">Nothing yet this week.</span></li>'
    c1 = li(f'<li><span><b>{e(w)}</b> took the {e(belt)} belt from {e(l)}</span><a class="mono" href="{u}">{S.d_short(dt)}</a></li>'
            for dt, belt, w, l, u in moved[:6])
    c2 = li(f'<li><span><b>{e(b["holder_short"])}</b> · {e(b["short"])}</span><b class="mono">{(today - date.fromisoformat(b["since"])).days:,} days</b></li>'
            for b in longest)
    c3 = li(f'<li><span><b>{e(b["holder_short"])}</b> ({e(b["short"])}) {"vs." if b["next"]["home"] or b["next"]["neutral"] else "at"} {e(b["next"]["opponent_short"] or "")}</span>'
            f'<b class="mono">{round(b["next"]["win_prob"] * 100)}% to defend</b></li>' for b in upsets[:6])
    if moved_card:
        first = f'<div class="card"><div class="kicker">Belts that moved this week</div><ol class="lb">{c1}</ol></div>'
    else:
        soon = sorted((b for b in bs if b.get("next") and b["next"].get("date") and b["next"]["date"] >= today.isoformat()),
                      key=lambda b: (b["next"]["date"], b["next"].get("time_et") or "99"))[:6]
        c0 = li(f'<li><span><b>{e(b["holder_short"])}</b> ({e(b["short"])}) {"vs." if b["next"]["home"] or b["next"]["neutral"] else "at"} {e(b["next"]["opponent_short"] or "")}</span>'
                f'<a class="mono" href="{b["next"]["url"]}">{S.d_short(b["next"]["date"])}</a></li>' for b in soon)
        first = f'<div class="card"><div class="kicker">Next on the line</div><ol class="lb">{c0}</ol></div>'
    return f"""<section class="wrap block">
  <div class="head"><h2 class="disp">Across every belt</h2><span class="mono note">All 19 belts, updated every two hours</span></div>
  <div class="three">
    {first}
    <div class="card"><div class="kicker">Longest current reigns</div><ol class="lb">{c2}</ol></div>
    <div class="card"><div class="kicker">Upset watch: under 40% to defend</div><ol class="lb">{c3}</ol></div>
  </div>
</section>"""


# --------------------------------------------- Phase 4: doubles and cities --

def _intervals(reigns, today):
    for r in reigns:
        s = r.get("start_date")
        if not s:
            continue
        yield s, (r.get("end_date") or today.isoformat())


def build_doubles(S, today=None):
    """Audit 5.6: schools that held two college belts at once (football, men's and women's
    basketball), from the three sites' api/reigns.json."""
    e = S.e
    today = today or date.today()
    srcs = [("Football", "https://collegefootballbelt.com/api/reigns.json"),
            ("Men's hoops", "https://collegebasketballbelt.com/api/reigns.json"),
            ("Women's hoops", "https://collegebasketballbelt.com/women/api/reigns.json")]
    norm = lambda n: re.sub(r"[^a-z0-9]+", "-", (n or "").lower()).strip("-")
    by = {}
    got = 0
    for belt, api in srcs:
        j = fetch(api) or {}
        rs = j.get("reigns") or []
        got += bool(rs)
        for r in rs:
            name = r.get("name") or r.get("team")
            by.setdefault(norm(name), {"name": name, "belts": {}})["belts"].setdefault(belt, []).append(r)
    if got < 2:        # the sister sites didn't answer this build: keep the URL alive, out of the index
        S.write("network/doubles/index.html", S.page("Double belts: schools that held two at once",
                """<section class="wrap prose"><div class="kicker">The belt network</div><h1 class="disp">Double belts</h1>
<p>Schools that held two lineal college belts at once. The college sites didn't answer this build, so the list is back on the next one.</p>
<p><a href="/all/">Every belt right now →</a></p></section>""", path="/network/doubles/", active="leagues",
                description="Schools that held two lineal college belts at once.", robots="noindex,follow"))
        return 0
    rows, now = [], []
    for k, x in by.items():
        bl = list(x["belts"].items())
        for i in range(len(bl)):
            for j in range(i + 1, len(bl)):
                (b1, r1), (b2, r2) = bl[i], bl[j]
                for s1, e1 in _intervals(r1, today):
                    for s2, e2 in _intervals(r2, today):
                        lo, hi = max(s1, s2), min(e1, e2)
                        if lo <= hi:
                            days = (date.fromisoformat(hi) - date.fromisoformat(lo)).days + 1
                            rows.append((days, x["name"], b1, b2, lo, hi))
                            if hi >= today.isoformat():
                                now.append((x["name"], b1, b2, lo))
    rows.sort(key=lambda r: (-r[0], r[4]))
    schools = len({r[1] for r in rows})
    trs = "".join(f'<tr><td>{e(n)}</td><td class="mono">{e(a)} + {e(b)}</td><td class="mono">{S.d_short(lo, True)}</td>'
                  f'<td class="mono">{"now" if hi >= today.isoformat() else S.d_short(hi, True)}</td><td class="mono r">{d:,}</td></tr>'
                  for d, n, a, b, lo, hi in rows)
    lede = ("Right now: " + "; ".join(f"{e(n)} holds the {e(a).lower()} and {e(b).lower()} belts, together since {S.d_long(lo)}" for n, a, b, lo in now) + "."
            if now else "Nobody holds two college belts at the moment.")
    body = f"""<section class="wrap block">
  <div class="kicker">The belt network</div>
  <div class="head"><h1 class="disp">Double belts</h1><span class="mono note">{len(rows)} stretches · {schools} schools</span></div>
  <p class="intro">Schools that held two lineal college belts at the same time: the College Football Belt, and the men's and women's College Basketball Belts. {lede}</p>
  <div class="tablewrap"><table class="history"><thead><tr><th class="mono">School</th><th class="mono">Belts</th><th class="mono">From</th><th class="mono">To</th><th class="mono r">Days</th></tr></thead><tbody>{trs}</tbody></table></div>
  <p class="mono more"><a href="/all/">Every belt right now →</a> · <a href="/network/cities/">Belt cities →</a></p>
</section>"""
    S.write("network/doubles/index.html", S.page("Double belts: schools that held two at once", body, path="/network/doubles/", active="leagues",
                                                 description=f"{schools} schools have held two lineal college belts at once, football and basketball. Every overlap, longest first."))
    return len(rows)


METRO = {"Brooklyn": "New York", "Newark": "New York", "East Rutherford": "New York", "Foxborough": "Boston",
         "Landover": "Washington", "Sunrise": "Miami", "Anaheim": "Los Angeles", "Oakland": "San Francisco Bay Area",
         "San Francisco": "San Francisco Bay Area", "San Jose": "San Francisco Bay Area", "Arlington": "Dallas",
         "Glendale": "Phoenix", "Tempe": "Phoenix", "Inglewood": "Los Angeles", "Frisco": "Dallas"}


def build_cities(S, datas, today=None):
    """Audit 5.6: which cities hold the most pro belts right now, and ever."""
    from leagues import LIVE
    e = S.e
    today = today or date.today()
    days, now, spans = {}, {}, []
    for lg in LIVE:
        d = datas[lg["key"]]
        for r in d["reigns"]:
            season = r.get("season") or int(r["start_date"][:4])
            pl = F._place(lg, r["team"], season)
            if not pl:
                continue
            city = METRO.get(pl[0], pl[0])
            end = r.get("end_date") or today.isoformat()
            days.setdefault(city, {}).setdefault(lg["name"], 0)
            days[city][lg["name"]] += r.get("days") or 0
            spans.append((city, r["start_date"], end, lg["name"]))
            if not r.get("end_date"):
                now.setdefault(city, []).append((lg["name"], lg["short_name"](r["team"])))
    if not days:
        return 0
    # most belts held at once, per city (sweep over start/end events)
    best = {}
    ev = {}
    for city, s0, e0, lgn in spans:
        ev.setdefault(city, []).extend([(s0, 1, lgn), (e0, -1, lgn)])     # [start, end): the day a belt moves counts once
    for city, xs in ev.items():
        xs.sort(key=lambda x: (x[0], x[1]))
        cur = 0
        for dt, step, lgn in xs:
            cur += step
            if cur > best.get(city, (0, ""))[0]:
                best[city] = (cur, dt)
    tot = sorted(((sum(v.values()), c) for c, v in days.items()), reverse=True)[:25]
    rows = "".join(f'<tr><td class="mono n">{i}</td><td>{e(c)}</td><td class="mono r">{t:,}</td><td class="mono r">{best.get(c, (0,))[0]}</td>'
                   f'<td class="mono">{S.d_short(best[c][1], True) if c in best else ""}</td><td class="mono">{e(", ".join(sorted(days[c], key=lambda k: -days[c][k])[:4]))}</td></tr>'
                   for i, (t, c) in enumerate(tot, 1))
    nowrows = sorted(now.items(), key=lambda kv: -len(kv[1]))
    nl = "".join(f'<li><span><b>{e(c)}</b>: {e(", ".join(f"{a} ({b})" for a, b in v))}</span><b class="mono">{len(v)}</b></li>' for c, v in nowrows[:10])
    body = f"""<section class="wrap block">
  <div class="kicker">The belt network</div>
  <div class="head"><h1 class="disp">Belt cities</h1><span class="mono note">North American pro leagues</span></div>
  <p class="intro">Where the pro belts live: the cities holding the most belts right now, and the ones that have held them longest across every league, with the most belts each city ever held at once. Suburban stadiums count for their metro area.</p>
  <div class="card"><div class="kicker">Right now</div><ol class="lb">{nl}</ol></div>
  <h2 class="disp sub">All-time, by days held</h2>
  <div class="tablewrap"><table class="history"><thead><tr><th class="mono">#</th><th class="mono">City</th><th class="mono r">Days held</th><th class="mono r">Most at once</th><th class="mono">First reached</th><th class="mono">Leagues</th></tr></thead><tbody>{rows}</tbody></table></div>
  <p class="mono more"><a href="/all/">Every belt right now →</a> · <a href="/network/doubles/">Double belts →</a></p>
</section>"""
    S.write("network/cities/index.html", S.page("Belt cities: where the pro belts live", body, path="/network/cities/", active="leagues",
                                                description="Which cities hold the most lineal pro championship belts right now, and which have held them longest across the NFL, NBA, NHL, MLB and more."))
    return len(tot)
