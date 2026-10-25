# Dashboards roadmap

How the four public dashboards (`/`) go from built to trusted and growing, in order. Principle: one branch and one commit per dashboard change, shared plumbing changed on its own, every change verified three ways (unit test on fixtures, live-source check, page opened in a browser). Each dashboard's own guide is in `data/<slug>/README.md`.

## Phase 0: ship what exists (first)

1. Create the Railway service from this repository (see README), let it deploy.
2. On the live domain open `/` and each of the four pages, every tab. Record in a short table (in the PR or a
   `docs/dashboards_launch.md`): tab → "live data" / "stale" / "not available".
3. Run `pytest -m network tests/test_sources.py` from a machine with normal internet. Expected unknowns:
   Land Registry CSV layout, ONS API, Bank of England CSV, FRED via curl, Census BTOS workbook, NHTSA CSV. Fix parsers
   in `app/topics/<module>.py` where the live format differs; each fix gets its fixture in
   `tests/test_topics.py` updated to the real header line.
4. Clear every row whose `note` says `verify` in `data/*/*.csv` against its cited source, or delete it.
5. If a UK site refuses Railway's US servers: fetch once from a UK machine and copy the snapshot files into
   the snapshot volume (`/app/snapshots` on Railway) and note it in that dashboard's README. A UK proxy is the longer-term fix only if this happens repeatedly.

Done when: every tab shows live or snapshot data, no "not available" card, no `verify` rows.

## Phase 1: make them self-reporting (done: /api/health, index counts, daily source-health issue, live-check workflow) (one small change to the shared plumbing)

Goal: nobody has to open four pages to know they are healthy.

- `app/topics/_base.py`: record per-source status (last success, last failure, error type) in a dict next
  to `STALE`; add `topics.health()` returning it for every registered dashboard.
- `/api/health` route in `app/server.py`, and a "Sources" line on the index page showing fresh / stale / failing counts per dashboard.
- An alert when any source has been stale for more than 3 days or failing for more than 1 day: a GitHub Actions job on a daily schedule that calls `/api/health` and opens an issue, so no extra process runs on Railway.
- Test: `tests/test_topics.py` gets one test that forces a failure and checks `health()` and the route.

Done when: a dead source shows up as an issue the next morning without anyone looking at the page.

## Phase 2: content, one dashboard at a time, in this order

Each item is one commit: module change + JS change + fixture test + README update + (if hand-entered) CSV rows.
Finish a dashboard's "next" list before starting the following dashboard, so each one reaches "complete" rather than all
four staying half done.

### 2a. London housing (fully automatable, finish first)
- Rents: ONS Price Index of Private Rents, London (monthly); card "Rents vs prices" on the Prices tab.
- Boroughs: UK HPI by local authority for the 33 London boroughs; new tab "Boroughs" with a sortable table
  (price, yearly change) and a small-multiples line chart. One download per borough is too many requests: use the
  full-file CSV once a day and filter.
- London earnings: ONS ASHE London median full-time pay (yearly) to correct the price-to-earnings ratio; keep the
  UK-wide monthly line as the trend.
- Mortgage rates: Bank of England quoted 2-year fixed 75% LTV rate (series IUMBV34) replacing "Bank Rate + 1.5" in
  the illustration.

### 2b. AI jobs vs law & finance (almost automatable)
- UK headcount: fill `uk_headcount.csv` from ONS JOBS03 for the last 12 quarters; or automate from the ONS API once a
  series id for the two industries is confirmed.
- Occupation view: Indeed's sector file also has "IT Systems & Solutions" and "Scientific Research & Development";
  add them to the AI group behind a toggle.
- Wages: BLS average hourly earnings for the same industries (FRED CES..03 series) as a third tab, since headcount
  without pay tells half the story.

### 2c. AI adoption (half hand-entered)
- Confirm or fix the BTOS workbook parser against the live file; fill the sector file for the latest period.
- Ramp AI Index: twelve monthly points; set a monthly reminder (below) to add the next.
- Add one survey series with a consistent method (the Census BTOS "expect to use AI in the next six months" question is
  in the same workbook, so it is free): "using now" vs "expect to use" on one chart.
- Agents: keep the timeline; add a `kind` filter on the page.

### 2d. Autonomous cars (mostly hand-entered)
- `miles.csv` (operator, cumulative rider-only miles, date, source) so crash reports become reports per million miles.
- CPUC quarterly driverless trip counts: try to automate from the published spreadsheet; fall back to hand entry.
- Rides per week for Baidu, Pony.ai, WeRide, Zoox, Tesla when they announce a weekly figure.

## Phase 3: working rules (write them into `data/README.md` as a "Contributing" section)

- Branch name `dash/<slug>-<what>`; commit prefix `feat(dash-<slug>)`, `fix(dash-<slug>)`, `data(dash-<slug>)` for
  CSV-only changes, `chore(dash)` for shared plumbing.
- A change to a dashboard touches only its module, its JS, its folder and its tests. Shared helpers in `_base.py` or
  `topic.html` change in their own commit, with all four pages re-opened in the browser.
- Every new series has: a `SOURCES` entry, a fixture in `tests/test_topics.py`, a line in the README's source table,
  and a licence note if it is not OGL, CC BY or public domain.
- Hand-entered rows always cite the primary source. A seed from memory is marked `verify` and must be cleared
  within a week or removed.
- Monthly maintenance (first weekend of the month, 20 minutes): run the network test, add the month's Ramp and BTOS
  points, scan operator blogs for ride announcements, check `/api/health`. Put it on the calendar; the Phase 1 alert
  line catches anything between.
- Review of the four pages at phone width after any change to `topic.html`.

## Phase 4: polish (after 2a and 2b are complete)

- Custom domain on Railway for the dashboards  so links do not
  carry the Railway subdomain.
- Open Graph title and description per page (from `meta`) so a shared link previews properly; consider removing
  `noindex` once the data is verified.
- "Download CSV" link per card (the payload is already the series; a small JS helper in `topic.html`).
- A short "Method" page per dashboard at `/<slug>#about`, rendered from the README's calculation section, so visitors
  see the caveats without GitHub.

## Verification (applies to every phase)

- `pytest -m "not network"` green; `pytest -m network tests/test_sources.py` green from a normal network.
- Headless browser pass: a smoke script (start the server, open every tab in headless Chromium, light and dark, 1000px and 390px, fail on any
  JS error) is added as `scripts/dashboard_smoke.py` in Phase 1 so it can be rerun before each merge.
- Live domain: each changed page opened, the new card seen with real data, the README updated in the same commit.
