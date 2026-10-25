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

The order of work, the rules for changes and the per-dashboard backlog are in [docs/Dashboards_Roadmap.md](../../docs/Dashboards_Roadmap.md).

## Adding a dashboard

1. `app/topics/<name>.py` with `ENDPOINTS = {tab: function}`, `SOURCES` and `NOTES` (copy `robotaxi.py` for a mostly hand-entered one, `ai_jobs.py` for an automated one).
2. `app/static/topics/<slug>.js` with `window.TOPIC = { VIEWS }`, one async function per tab.
3. One `Topic(...)` line in `app/topics/__init__.py`. The index page, routes, meta, warmer and tests pick it up from there.
4. A folder here with its CSVs and a README like the others.
