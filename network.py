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


def build_network_feed(S, out="site", limit=100):
    """/all/feed.xml: every title change on every belt, merged from the three sites' feeds."""
    import html as H
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
