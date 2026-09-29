# Belt Holders

The lineal championship belt for every pro league — beltholders.com.

A win over the holder takes the belt; ties are defenses; the belt follows a
franchise through moves. The full ruleset is on the site's /rules/ page.

## How it works

```
league_<league>.py    where a league's games come from + team names/colors
leagues.py            which leagues are live, and which are "coming soon"
belt_engine.py        the belt walk + vacancy rules (shared with the College Football Belt repo)
build_lineages.py     runs the engine for every live league -> data/<league>/lineage.json
build_site.py         static site -> site/
styles.css, *.png     stylesheet, favicon, touch icon, share card (from generate_assets.py)
```

```
python build_lineages.py        # fetch fresh data (no API keys needed for the NFL)
python build_site.py            # write site/
python -m http.server -d site   # preview at http://localhost:8000
```

GitHub Actions (`.github/workflows/deploy.yml`) runs both steps every two
hours and on every push, and deploys `site/` to GitHub Pages.

## Adding a league

Copy `league_nfl.py`, point `load_games()` at the new league's data, fill in
team names and colors, and add its `LEAGUE` dict to `LIVE` in `leagues.py`
(and remove it from `COMING`). Nothing else changes.

## Data

- NFL 1920–2020: FiveThirtyEight's public NFL game archive (`fivethirtyeight/nfl-elo-game`).
- NFL 2021–present: the open nflverse project (`nflverse/nfldata`).

## Settings in build_site.py

- `ADSENSE_PUBLISHER_ID` — set to `pub-3317069252410560` once the site is
  approved in AdSense (adds the ad script and ads.txt).
- `GOATCOUNTER_CODE` — set once a GoatCounter site exists.

## Site budget

GitHub Pages refuses a published site over 1 GB and times out deployments after 10 minutes.
`deploy.yml` fails the build when `site/` passes 900 MB on disk (the "Site size guard" step
prints the size in each run's summary). The levers, all in `features.py` (shared with the
College Basketball Belt repo):

- `MIN_PLAYER_GAMES` (3): players with fewer belt games are table rows, not pages.
- Game pages: only title changes that opened a reign of 5+ defenses, the current reign or
  the first game on record, games with a box score, and games with a recap get
  `games/<n>/`. Every other belt game is the `#g<n>` anchor on its season page
  (`plan_game_pages`).
- `BOX_PAGES_FROM` ({"mlb": 1988}): older box scores aren't rendered, and
  `mlb_boxscores.py` stops its backfill at the same season (`MLB_BOX_FROM`).

On 2026-09-29 these took the site from 1,002 MB / 51,807 files to about 744 MB / 29,900 files.

