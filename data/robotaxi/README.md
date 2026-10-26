# Autonomous Cars & Energy Transition (`/robotaxi`)

Driverless ride-hailing: how many paid rides operators give, where they run a public service, and the crash reports they file. Operators announce numbers rather than publish feeds, so most of this page is hand-entered with a source per point; the safety data is automated from NHTSA.

## What it shows

| Tab | Cards | Series |
|---|---|---|
| Rides | Headline figures | Latest paid rides a week per operator |
| | Paid driverless rides per week, as announced | One line per operator (`rides.csv`) |
| | Fully driverless rides per quarter | Bars per operator that reports quarterly (`rides_quarterly.csv`) |
| | Announcements | Every row with its source |
| Footprint | Headline figures | Cities per operator |
| | Cities with public driverless rides, cumulative | Running count per operator over time |
| | Where | City, operator, date opened to the public, source (`cities.csv`) |
| Safety | Crash reports per month | All reports filed by automated-driving-system operators under NHTSA's Standing General Order, with the 12-month total |
| | Last 12 months by reporting entity | Bars for the six most frequent reporters, the rest grouped |

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Paid rides per week | Operator blog posts, investor calls, press reports | As announced | Hand-entered: `rides.csv` |
| Rides per quarter | Operator earnings releases (Baidu for Apollo Go) | Quarterly | Hand-entered: `rides_quarterly.csv` |
| Cities | Operator announcements | As announced | Hand-entered: `cities.csv` |
| Crash reports | [NHTSA Standing General Order 2021-01, ADS incident reports](https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting), CSV | Monthly | Automated |
| Crash reports before June 2025 | The same order's archive file (`Archive-2021-2025/SGO-2021-01_Incident_Reports_ADS.csv`): NHTSA moved reports filed under the earlier versions of the order there when the third amendment took effect on 16 Jun 2025 | Fixed | Automated, fetched monthly |
| Driverless miles | Waymo safety hub and posts | Quarterly, about three months after each cut-off | Hand-entered: `miles.csv` |

NHTSA data is public domain.

## How it is calculated

- Ride lines join announcement points; nothing is interpolated.
- Cumulative cities count rows in `cities.csv` per operator in date order.
- Crash reports are counted once per report ID (operators file several versions of one report), by the month in the "Incident Date" column, from July 2021 when the order took effect. Every reportable incident counts, however minor and whoever caused it, so the count rises with miles driven: read it as exposure as much as safety.

## Keeping it up to date

**Automated:** the NHTSA CSV is fetched daily and snapshotted. Both NHTSA files are read and each report ID counted once; if the archive cannot be loaded, the per-mile table is hidden (reports to date would be undercounted) and the page says so. If NHTSA renames a column, the card says "not available right now (ValueError)"; the parser in `app/topics/robotaxi.py` looks for columns containing "Reporting Entity", "Incident Date" and "Report ID".

**`rides.csv`** (`date,series,value,source,note`): one row per announcement of a weekly paid-ride figure; `series` is the operator, `value` rides per week, `date` the announcement date. Example:

```
2025-04-24,Waymo,250000,https://techcrunch.com/2025/04/24/waymo-is-now-giving-250000-paid-robotaxi-rides-every-week/,
```

**`rides_quarterly.csv`** (`date,series,value,source,note`): operators that report a quarterly total; `date` is the first day of the quarter.

**`cities.csv`** (`date,operator,city,country,source,note`): a city counts when a fully driverless service is open to the general public (not employees or an invite list); note pilots in `note`.

Checked on 25 Oct 2026: Waymo's 50,000 is dated to its 9 May 2024 post. The 175,000 (Dec 2024) and 450,000 (Oct 2025) rows were removed: no Waymo or Alphabet source exists for either (the 450,000 comes from a leaked investor letter). Waymo's 500,000 (Mar 2026) and Baidu's weekly figures from its quarterly results were added. Pony.ai, WeRide and Zoox publish no rides-a-week figure yet: Pony.ai and WeRide report orders per vehicle per day and robotaxi revenue, Zoox cumulative riders. Baidu's Q2 2026 quarter is derived from its interim report (H1 minus Q1) and stays marked `verify` until a release states it.

**`miles.csv`** (`date,series,value,source,note`): cumulative rider-only miles; `date` is the data cut-off the operator states (Waymo: "through June 2026"), not the publish date. `series` is the operator name, matched to every NHTSA reporting entity that starts with it, case-insensitive (`Waymo` matches `Waymo LLC`). Waymo updates its safety hub (waymo.com/safety/impact) about three months after each quarter. Only operators whose ADS crash reports and published miles cover the same vehicles belong here: Tesla (reports include rides with a safety monitor; FSD miles are driver assistance) and Zoox (reports include its safety-driver test fleet) are left out, with the reason in the file's header.

**`regulation.csv`** (`date,market,event,source,note`): one row per law, licence or pilot. UK rows cite gov.uk, legislation.gov.uk or the operator's release; Hong Kong rows cite the government press release (info.gov.hk). Those releases often leave out the licence holder, which the Transport Department's AV pilot licence table names (td.gov.hk/en/public_services/taoav). Checked on 25 Oct 2026: no UK APS permit had been reported issued, and the Wayve/Uber London rides run with a licensed driver on board.

**CPUC trips (automated):** the quarterly-reporting page is read daily and every zip whose address contains "deploy" is opened (pilot zips, with a safety driver, are skipped). Each zip, about 60 MB, holds a month-level CSV (`…_AV_Month_Part0…csv`: `TCPID,Year,Month,TotalTrips,…`, numbers with thousands commas); the card sums `TotalTrips` into quarters, complete quarters only. Only the month rows are kept, as `cpuc-<hash>.json` in the snapshot folder, so each zip is downloaded once; at most three new zips are read per refresh, so a fresh volume fills in within the hour. Carriers are named from their CPUC id (`PSG0038152` Waymo, `PSG0039080` Cruise; add others to `CARRIERS` in `robotaxi.py`). Waymo files about five weeks after each quarter (Q2 2026 on 3 Aug 2026). If the CPUC renames the month file's columns, the card says "not available right now (ValueError)". Zips from before 2025 use a different layout and quarter boundaries, and may add nothing.

**Tesla vs the share price** (Tesla tab, last card): Pearson correlations between each quarterly series in `tesla.csv` and TSLA, computed by `tesla_vs_price` in `robotaxi.py`. Four comparisons: level against the quarter-end close; change on a year against TSLA's change on a year; change on the quarter against that quarter's return; and, for figures in the production and deliveries release (deliveries, production, storage), the change against TSLA's close-to-close move on release day (the 2nd of the following month, or the next trading day). Volumes and revenue are compared by % change; margins, EPS and cash flow, which can be negative, by change in level. A comparison needs 6 quarters. Add a metric by adding its rows to `tesla.csv` and a line to `CORR_METRICS`.

**Fundamentals signal and backtest** (Tesla tab): `tesla_signal` in `robotaxi.py`. Every series in `CORR_METRICS` votes +1 when its latest quarter beats the same quarter a year earlier and −1 when it is worse (deliveries, production, storage, revenue and FSD subscriptions by % change; margins, EPS and free cash flow by level). The signal is the mean of the votes, rebuilt on each day a figure becomes public, using only what was public that day: deliveries, production and storage on the 2nd of the month after the quarter, the financials 35 days after the quarter (`FIN_LAG`, later than Tesla's results, which come about 20–29 days after). Backtest: hold TSLA from the next trading day while the signal is above 0, otherwise cash earning nothing, 0.1% per switch (`COST`); against buy-and-hold from the same day. "Calls right" counts the periods where holding was followed by a rise, or cash by a fall. With about ten quarters of signal this describes what happened; it cannot show that the rule works, and the rule was picked after seeing the data.

## Energy tab

Code in `app/topics/robotaxi_energy.py` (a helper module of this dashboard; `ENDPOINTS["energy"]` in `robotaxi.py` calls it).

| Card | Source | How |
|---|---|---|
| Electric share of new cars, rolling 12 months (and the headline) | [Ember EV sales data](https://ember-energy.org/data/monthly-ev-sales-data/), CSV, CC BY 4.0: `monthly_ev_sales.csv`, drivetrain "Electric vehicle (BEV+PHEV)", columns `Share of registrations (%)` and `Rolling 12-month share of registrations (%)`; covers all four markets including Hong Kong | Automated, daily |
| Electric share of new cars, by year (each country's official measure) | SMMT (UK), CPCA (China), Cox Automotive / Kelley Blue Book and DOE / Argonne (US), HK government papers to LegCo and press releases | Hand-entered: `ev_share.csv`, one series per market and definition |
| Latest month or quarter | Same publishers | Hand-entered: `ev_latest.csv` |
| Wind and solar share of electricity, by year and by month | [Ember yearly](https://ember-energy.org/data/yearly-electricity-data/) and [monthly](https://ember-energy.org/data/monthly-electricity-data/) electricity data, CSV, CC BY 4.0 | Automated: `release_generation_yearly_global.csv` and `release_generation_monthly_global.csv`, daily |
| Cross-checks | EIA (US), DESNZ Energy Trends (UK), Ember's Global Electricity Review (China), HK government | Hand-entered: `power_checks.csv` |

- **Ember's Hong Kong** is "Hong Kong (SAR of China)": in the yearly power file and the EV file, not in the monthly power file. Macao and Taiwan are not matched.
- **Ember layout** (July 2026): one row per area, period (`Year` or `Date`) and `Electricity source`, with `Share of generation (%)` as a column. The parser keeps the rows for United States, United Kingdom, China and any area named Hong Kong, and adds Solar and Wind. If Ember renames a column, the card says "not available right now (ValueError)".
- **EV shares are not like for like:** the UK counts registrations, China counts retail sales including plug-in hybrids and range-extenders, the US counts light vehicles (Cox: battery-electric only), and Hong Kong counts private cars only. The series names say which.
- **Batteries** store electricity rather than generate it, so they are not in the generation shares. EIA's Electric Power Annual table 3.27 has US battery net generation (negative: charging losses) if a storage card is wanted later.
- **To update:** SMMT publishes on about the 5th of each month, CPCA in the second week, and Cox each quarter. Add the latest to `ev_latest.csv`, and in January add the full year to `ev_share.csv`. Hong Kong's 2026 figures are on the Ember chart (which compiles the Transport Department's registrations); the press figures since the tax concession ended on 31 Mar 2026 conflict, so the yearly hand-entered series stops at 2025.
- **Energy readings:** `ev_uk_bev`, `ev_china_nev`, `ws_china` and `ws_us` are +1 when the latest year's share is above the year before, and −1 when below.

## What changed since yesterday (READINGS)

`READINGS()` gives the shared "what changed" card these headline readings, from the cached tab payloads only. +1 means adoption is speeding up, safety is improving or TSLA is leaning up; −1 the opposite; 0 flat or unknown.

| Tab | Key | +1 when | −1 when |
|---|---|---|---|
| Rides | `waymo_weekly`, `baidu_quarterly` | latest figure above the previous one | below it |
| Footprint | `cities` | a city opened in the last 180 days | (never) |
| Footprint | `cpuc_waymo` | Waymo's latest CPUC quarter above the previous | below it |
| Footprint | `rules_90d` | a rule, licence or pilot in the last 90 days | (never) |
| Safety | `waymo_per_million` | reports per million miles lower than at the previous cut-off | higher |
| Tesla | `tsla_vs_200d` | TSLA above its 200-day average | below it |
| Tesla | `deliveries_yoy` | latest quarter's deliveries above a year earlier | below |
| Tesla | `fundamentals_signal` | the signal says hold TSLA | the signal is below 0 |

## Checking it

```
pytest -m network tests/test_sources.py -k nhtsa
```

Local preview: `python -m app.server`, then open `/robotaxi`.

## Added in round 3

| Tab | What | Source | How |
|---|---|---|---|
| Tesla | TSLA share price; quarterly deliveries; FSD (Supervised) cumulative miles; every autonomy milestone (Robotaxi, Cybercab, FSD by country including UK and Hong Kong status) | Nasdaq quote API (Yahoo refuses Railway); Tesla's quarterly production and deliveries releases (SEC 8-K copies), quarterly Updates and @Tesla posts | Price automated; the rest hand-entered: `tesla.csv`, `tesla_milestones.csv` |
| Safety | Crash reports per million driverless miles for operators that publish miles | NHTSA SGO counts ÷ `miles.csv` | Automated count, hand-entered miles |
| Footprint & rules | Laws, licences and pilots in the US, UK (Automated Vehicles Act, Wayve/Uber London pilot), Hong Kong (Baidu Apollo airport-area licence) and China | Government and operator pages | Hand-entered: `regulation.csv` |
| Footprint & rules | California completed driverless passenger trips per quarter | [CPUC AV quarterly reporting](https://www.cpuc.ca.gov/regulatory-services/licensing/transportation-licensing-and-analysis-branch/autonomous-vehicle-programs/quarterly-reporting): one deployment zip per carrier and quarter | Automated (see below); `cpuc_trips.csv` only for quarters the files miss |
| Rides | Room for Baidu Apollo Go, Pony.ai, WeRide, Zoox and Tesla weekly figures | Operator announcements | Hand-entered rows in `rides.csv` |

Tesla deliveries and production (Q1 2023 onwards) were checked on 25 Oct 2026 against Tesla's quarterly production and deliveries releases; each row cites the copy Tesla files with the SEC (Form 8-K, exhibit 99.1), because ir.tesla.com is not reachable from every network. Add a quarter by copying the totals from the new release (out on about the 2nd of the month after the quarter). FSD (Supervised) miles are the round figures @Tesla posts (lower bounds: "over 10 billion"). Milestones cite Tesla's quarterly Update where it reports the event, otherwise the press report the date was taken from; rows still marked `verify` say which part (usually the exact day) is unconfirmed.

## Known gaps

- China: Baidu's quarterly and weekly figures and two cities; Pony.ai and WeRide publish no ride counts, only per-vehicle orders and revenue.
- Tesla's robotaxi numbers are not published; the Austin row is a marker, not a count.
