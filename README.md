# Dashboards

Public, read-only data dashboards, each on its own page:

| Dashboard | Page | What it tracks |
|---|---|---|
| Housing: London, US & Hong Kong | `/housing` | London prices (as paid and in today's money), boroughs, types, sales, rents, rates and affordability; London vs the US (Case-Shiller) and Hong Kong (RVD) |
| Autonomous Car Adoption | `/robotaxi` | Paid driverless rides by operator, cities with public service, NHTSA crash reports |
| AI: Jobs & Adoption | `/ai` | AI openings vs law and finance (US, UK), headcount and pay (US, UK, HK), firms and people adopting AI tools and agents, AI share of job postings. Replaces `/ai-jobs` and `/ai-adoption`, which redirect here |
| BTC Cycles & Sector Rotation | `/btc-cycles` | Four Bitcoin cycles, the altcoin sectors that won each, winner metrics, 2026–27 candidates and signals, checked daily against live data |

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
