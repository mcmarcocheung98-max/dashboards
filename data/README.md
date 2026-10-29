# Hand-entered data and dashboard guides

One folder per dashboard: its CSVs (points with no free API, one cited row each) and a README on what the page shows, where every number comes from and how to keep it current.

| Page | URL | Guide |
|---|---|---|
| Housing: London, US & Hong Kong | `/housing` | [housing/README.md](housing/README.md) |
| Autonomous Car Adoption | `/robotaxi` | [robotaxi/README.md](robotaxi/README.md) |
| AI: Jobs & Adoption | `/ai` | [ai/README.md](ai/README.md) |
| BTC Cycles & Sector Rotation | `/btc-cycles` | [btc-cycles/README.md](btc-cycles/README.md) |

`/` is the index. Each page's data is at `/api/<slug>/<name>` (JSON).

## How they work

- **Code.** One Python module per dashboard in `app/topics/` (what to fetch, what to compute), one script per dashboard in `app/static/topics/<slug>.js` (the tabs and cards), and the shared page `app/static/topic.html`. `app/topics/_base.py` holds the fetching and the CSV reader; `app/server.py` is the web server.
- **Automated data** is downloaded at most once a day and the computed page data is cached for six hours. A background warmer recomputes expired data every ten minutes, so visitors never wait.
- **Snapshots.** Every download is also written to `the snapshot folder (`SNAPSHOT_DIR`, `/app/snapshots` on Railway)` on the Railway volume. If a source is down, the last copy is served and the card shows "Source not reachable right now: showing the last copy from <date>". A card whose source has never been reachable shows "not available right now".
- **Hand-entered data** lives in the CSV files in these folders, one row per point, each with the source it was copied from. Adding a point is one committed line; Railway redeploys and the page updates. The files are documented in each dashboard's README.

## CSV format

Single series: `date,value,source,note`. Several series in one file: `date,series,value,source,note`. Dates are `YYYY-MM-DD`. A line starting with `#` in the date column is a comment. A row with an empty value is ignored (useful as a placeholder). The `source` should be the page the number was read from, not a search result. Put `verify` in `note` for a figure copied from memory or a secondary report; the page shows notes next to each row.

## Checking the sources

```
pytest -m network tests/test_sources.py
```

fetches every live source with no cache and says which one changed or went away. Run it from a machine with ordinary internet access (the Railway container is in the US; a UK site that refuses it shows up as a stale card on the page, not as an error here).

To preview locally:

```
python -m app.server
```

then open `http://localhost:8080/d`.

## What comes next

The order of work and the per-dashboard backlog are in [docs/ROADMAP.md](../docs/ROADMAP.md). The rules for changes are below.

## Adding a dashboard

1. `app/topics/<name>.py` with `ENDPOINTS = {tab: function}`, `SOURCES` and `NOTES` (copy `robotaxi.py` for a mostly hand-entered one, `ai_jobs.py` for an automated one).
2. `app/static/topics/<slug>.js` with `window.TOPIC = { VIEWS }`, one async function per tab.
3. One `Topic(...)` line in `app/topics/__init__.py`. The index page, routes, meta, warmer and tests pick it up from there.
4. A folder here with its CSVs and a README like the others.

## Contributing

The working rules for every dashboard change (from the roadmap, Phase 3).

- **Branches and commits.** Branch `dash/<slug>-<what>` (scheduled runs use `sched/dash-<slug>-<what>`). One dashboard change per branch and commit. Commit prefix `feat(dash-<slug>)`, `fix(dash-<slug>)`, `data(dash-<slug>)` for CSV-only changes, `chore(dash)` for shared plumbing.
- **Stay inside one dashboard.** A change to a dashboard touches only its module (`app/topics/<module>.py`), its script (`app/static/topics/<slug>.js`), its folder here and its tests. Shared helpers in `app/topics/_base.py` or `app/static/topic.html` change in their own commit, with every page re-opened in the browser.
- **Every new series has** a `SOURCES` entry, a fixture in `tests/test_topics.py`, a line in the dashboard README's source table, and a licence note if it is not OGL, CC BY or public domain.
- **Hand-entered rows cite the primary source.** A figure copied from memory or a secondary report is marked `verify` in `note` and is cleared against its source within a week, or removed.
- **Verify three ways before merging:** `pytest -q` green (fixtures, no network); `pytest -m network tests/test_sources.py` from a normal network for any changed source; `python scripts/smoke.py` (every tab in headless Chromium, no JavaScript errors), plus a look at phone width (390px) after any change to `topic.html`.
- **Monthly maintenance** (first weekend of the month, about 20 minutes): run the network test, add the month's Ramp AI Index and Census BTOS points, scan operator blogs for robotaxi ride announcements, check `/api/health`. The daily `source-health` issue catches anything in between.
