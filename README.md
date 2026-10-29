# Dashboards

Public, read-only data dashboards, each on its own page:

| Dashboard | Page | What it tracks |
|---|---|---|
| Housing: London, US & Hong Kong | `/housing` | London prices (as paid and in today's money), boroughs, types, sales, rents, rates and affordability; London vs the US (Case-Shiller) and Hong Kong (RVD) |
| Autonomous Car Adoption | `/robotaxi` | Paid driverless rides by operator, cities, rules and pilots in the US, UK, HK and China, crash reports per mile, and a Tesla tab (price, deliveries, FSD, Robotaxi, Cybercab) |
| AI: Jobs & Adoption | `/ai` | AI openings vs law and finance (US, UK), headcount and pay (US, UK, HK), firms and people adopting AI tools and agents, AI share of job postings. Replaces `/ai-jobs` and `/ai-adoption`, which redirect here |
| BTC Cycles & Sector Rotation | `/btc-cycles` | Four Bitcoin cycles, the altcoin sectors that won each, winner metrics, 2026–27 candidates and signals, checked daily against live data |
| Memecoins | `/memecoins` | Dogecoin, Shiba Inu, Pepe, Bonk, dogwifhat and Trump as one basket: prices, momentum against BTC, and whether it is meme season |

`/` lists them. Data is at `/api/<slug>/<name>` (JSON). Every dashboard has a guide in `data/<slug>/README.md`: what each card shows, where every number comes from, and how to keep it current.

## How it works

- **Free sources only**, fetched at most once a day and cached. UK House Price Index, ONS, Bank of England, Indeed Hiring Lab, BLS via FRED, US Census, NHTSA, Coin Metrics, DefiLlama, CoinGecko.
- **Snapshots.** Every download is written to a persistent folder. If a source is down, the last copy is served and the card says "showing the last copy from <date>". Nothing blanks because a government site had a bad night.
- **Hand-entered data** (announcements, surveys without an API) lives in `data/<slug>/*.csv`, one row per point with the source it came from. Adding a point is one committed line; the next deploy shows it.
- **One module per dashboard** in `app/topics/`, one script per dashboard in `app/static/topics/`, a shared page shell in `app/static/topic.html`, and a 150-line server in `app/server.py`. No build step, no database.

## Run it locally

```
pip install -r requirements.txt
python -m app.server
```

Open `http://localhost:8080/`. Snapshots go to `./snapshots/` (set `SNAPSHOT_DIR` to change it). `WARM=0` turns the background warmer off.

## Tests

```
pytest -q                                   # unit tests on fixtures, no network (GitHub Actions runs these)
pytest -m network tests/test_sources.py     # fetches every live source: run by hand to see what changed or went away
```

## Checking that it works

- `python scripts/smoke.py` opens every tab of every dashboard in headless Chromium against a local server fed with the test fixtures, checks for JavaScript errors and that the shared date axis moves every chart, and saves screenshots to `smoke-shots/`.
- `python scripts/smoke.py --live https://<domain>` does the same against the deployed site with real data. On GitHub: Actions → **live-check** → Run workflow; it also prints `/api/health`.
- `/api/health` on the site lists every data source used since the last restart, per dashboard: fresh, stale (serving its last good copy) or failing. The index page shows the counts under each dashboard.
- Actions → **source-health** runs daily at 07:17 UTC and keeps one issue labelled `source-health` open while any source has served a copy older than 3 days or failed for more than a day with nothing to show; it closes the issue when all are healthy. Set the repository variable `DASHBOARDS_URL` if the domain changes.

## Private dashboards

A dashboard declared with `Topic(..., private=True)` is left off the index and opens only with a passcode: set
`PRIVATE_PASSCODE` on the Railway service, open the page and type it once (the browser stays unlocked for 30 days; "Lock" in
the footer signs out; changing the passcode signs every browser out). Its data, script and Ask Claude answers are refused
without it, `/api/health` shows only its counts, and the public `/api/archive.zip` leaves it out (the OneDrive copy keeps it).
Add the same value as the GitHub secret `PRIVATE_PASSCODE` so the live check can open it.

## Ask Claude

Every tab has an Ask Claude panel at the top right that answers from the page's own data. Anyone can ask, within per-visitor
limits and a daily spend cap; it needs `ANTHROPIC_API_KEY` on the Railway service. See [docs/ASK.md](docs/ASK.md).

## Month-end archive

On the last day of every month the server copies one zip of every dashboard (all data, the daily snapshots, the hand-entered
files) to OneDrive under `Dashboards/Archive/YYYY-MM/`, with the same rclone set-up as the trading bot (Railway variable
`ONEDRIVE_RCLONE_CONF`). Setup and contents: [docs/ARCHIVE.md](docs/ARCHIVE.md).
The same zip is at `/api/archive.zip` on the live site.

## Deploy on Railway

1. Railway → New Project → Deploy from GitHub repo → this repository. Railway reads `railway.json` and builds the `Dockerfile`.
2. Service → Settings → Volumes → Add volume, mount path `/app/snapshots`. This keeps the last good copy of every source across redeploys.
3. Service → Settings → Networking → Generate Domain (port 8080). That domain is the public link: `https://<domain>/` and `https://<domain>/housing` and so on.
4. No environment variables are required. Optional: `WARM=0` to turn off the background warmer, `SNAPSHOT_DIR` if you mount the volume elsewhere.
5. After the first deploy, open every page and run the network test from your own machine; cards saying "not available right now" are sources the server could not reach (Railway runs in the US; some UK sites refuse it, see the housing guide).

Every push to `main` redeploys.

## Adding a dashboard

A module in `app/topics/` with `ENDPOINTS`, `SOURCES` and `NOTES`; a script in `app/static/topics/<slug>.js` with `window.TOPIC = { VIEWS }`; one `Topic(...)` line in `app/topics/__init__.py`; a `data/<slug>/` folder with its CSVs and README. The index, routes, warmer and tests pick it up from the registry. The order of work and the per-dashboard backlog are in `docs/ROADMAP.md`.

## Licences of the data

UK government data (Land Registry, ONS, Bank of England) is under the Open Government Licence v3.0. Indeed Hiring Lab data is CC BY 4.0 and credited on each page. US federal data (BLS, Census, NHTSA) is public domain. Hand-entered points cite their source on the page.
