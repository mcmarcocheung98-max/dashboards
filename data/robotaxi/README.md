# Autonomous Car Adoption (`/robotaxi`)

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

NHTSA data is public domain.

## How it is calculated

- Ride lines join announcement points; nothing is interpolated.
- Cumulative cities count rows in `cities.csv` per operator in date order.
- Crash reports are counted once per report ID (operators file several versions of one report), by the month in the "Incident Date" column, from July 2021 when the order took effect. Every reportable incident counts, however minor and whoever caused it, so the count rises with miles driven: read it as exposure as much as safety.

## Keeping it up to date

**Automated:** the NHTSA CSV is fetched daily and snapshotted. If NHTSA renames a column, the card says "not available right now (ValueError)"; the parser in `app/topics/robotaxi.py` looks for columns containing "Reporting Entity", "Incident Date" and "Report ID".

**`rides.csv`** (`date,series,value,source,note`): one row per announcement of a weekly paid-ride figure; `series` is the operator, `value` rides per week, `date` the announcement date. Example:

```
2025-04-24,Waymo,250000,https://techcrunch.com/2025/04/24/waymo-is-now-giving-250000-paid-robotaxi-rides-every-week/,
```

**`rides_quarterly.csv`** (`date,series,value,source,note`): operators that report a quarterly total; `date` is the first day of the quarter.

**`cities.csv`** (`date,operator,city,country,source,note`): a city counts when a fully driverless service is open to the general public (not employees or an invite list); note pilots in `note`.

Rows marked `verify` in `note` and worth clearing against the source: Waymo 50,000 (May 2024, date), Waymo 175,000 (December 2024) and 450,000 (October 2025), Tesla Austin (invite-only with a safety monitor at the time of writing).

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
| Footprint & rules | California driverless trips per quarter | CPUC spreadsheets | Hand-entered: `cpuc_trips.csv` (the files move between addresses, so not automated) |
| Rides | Room for Baidu Apollo Go, Pony.ai, WeRide, Zoox and Tesla weekly figures | Operator announcements | Hand-entered rows in `rides.csv` |

Tesla deliveries and production (Q1 2023 onwards) were checked on 25 Oct 2026 against Tesla's quarterly production and deliveries releases; each row cites the copy Tesla files with the SEC (Form 8-K, exhibit 99.1), because ir.tesla.com is not reachable from every network. Add a quarter by copying the totals from the new release (out on about the 2nd of the month after the quarter). FSD (Supervised) miles are the round figures @Tesla posts (lower bounds: "over 10 billion"). Milestones cite Tesla's quarterly Update where it reports the event, otherwise the press report the date was taken from; rows still marked `verify` say which part (usually the exact day) is unconfirmed.

## Known gaps

- China (Baidu, Pony.ai, WeRide) is covered only by Baidu's quarterly figure and two cities.
- Tesla's robotaxi numbers are not published; the Austin row is a marker, not a count.
