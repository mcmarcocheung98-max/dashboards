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

## Known gaps

- No miles-driven series, so crash reports are not a rate. Waymo publishes rider-only miles irregularly; a `miles.csv` in the same format would allow reports per million miles.
- California's CPUC publishes quarterly driverless trip counts as spreadsheets; not automated yet.
- China (Baidu, Pony.ai, WeRide) is covered only by Baidu's quarterly figure and two cities.
- Tesla's robotaxi numbers are not published; the Austin row is a marker, not a count.
