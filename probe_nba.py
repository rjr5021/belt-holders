"""One-off: which NBA data sources answer from GitHub's servers?"""
import json, urllib.request
CH = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
NBA_H = {"User-Agent": CH, "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en-US,en;q=0.9", "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
tests = [
    ("espn site.api default UA", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20251022", {}),
    ("espn site.api curl UA", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20251022", {"User-Agent": "curl/8.5.0"}),
    ("espn site.web.api", "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20251022", {}),
    ("espn cdn core", "https://cdn.espn.com/core/nba/scoreboard?xhr=1&dates=20251022", {}),
    ("espn core api", "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events?dates=20251022", {}),
    ("espn team schedule", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/13/schedule?season=2026", {}),
    ("nba cdn schedule", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json", NBA_H),
    ("nba cdn schedule _1", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json", NBA_H),
    ("nba cdn today", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", NBA_H),
    ("stats.nba leaguegamelog", "https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=ASC&LeagueID=00&PlayerOrTeam=T&Season=2025-26&SeasonType=Regular%20Season&Sorter=DATE", NBA_H),
    ("data.nba.com 2025", "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/2025/league/00_full_schedule.json", {"User-Agent": CH}),
    ("data.nba.com 2026", "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/2026/league/00_full_schedule.json", {"User-Agent": CH}),
]
for name, url, h in tests:
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            print(f"OK  {r.status} {len(body):>9,}  {name}  {body[:120]!r}")
    except Exception as e:
        print(f"ERR {getattr(e, 'code', '')} {name}: {str(e)[:120]}")
