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

- China: Baidu's quarterly and weekly figures and two cities; Pony.ai and WeRide publish no ride counts, only per-vehicle orders and revenue.
- Tesla's robotaxi numbers are not published; the Austin row is a marker, not a count.
