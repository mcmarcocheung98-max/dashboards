# Housing: London, US & Hong Kong (`/housing`)

What London homes cost, how that compares with the rest of the UK and with inflation, how many change hands, and what buyers can afford at today's rates. London is automated from UK public data; the US comes from FRED; Hong Kong from the Rating and Valuation Department and the HKMA. Rents and, if its workbook cannot be read, the Hong Kong index are hand-entered.

## What it shows

| Tab | Cards | Series |
|---|---|---|
| Prices | Headline figures | London average price, change on a year ago, distance from the peak, 5- and 10-year change |
| | London average price: as paid, and in today's money | Average price; the same restated in the latest month's money using CPIH |
| | London vs the UK | House price index for London and for the UK (January 2015 = 100) |
| | Change on a year earlier | Yearly % change, London and UK |
| Types & volume | Headline figures | Latest average by property type; sales last month and last 12 months |
| | Average price by property type | Detached, semi-detached, terraced, flat / maisonette |
| | Change on a year earlier, by type | Yearly % change per type |
| | Sales volume | Completed sales per month and the rolling 12-month total |
| Rates & affordability | Headline figures | Bank Rate, price-to-earnings ratio, highest ratio seen, illustrative monthly mortgage |
| | Price ÷ pay | London average price divided by UK average annual regular pay |
| | Bank Rate | Bank of England base rate, by month |
| | Illustrative mortgage | Monthly repayment on 75% of the average London price over 25 years at Bank Rate + 1.5 points, against pay ÷ 12 |

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Average price, index, yearly change, sales volume, by property type (London and UK) | [UK House Price Index](https://landregistry.data.gov.uk/app/ukhpi), HM Land Registry with ONS, Registers of Scotland and Land & Property Services NI; CSV download for the London and United Kingdom regions | Monthly, published about six weeks after the month, revised later | Automated |
| CPIH, all items, 2015 = 100 | [ONS series L522, dataset MM23](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/l522/mm23) | Monthly | Automated (ONS API) |
| Average weekly earnings, regular pay, whole economy, seasonally adjusted | [ONS series KAB9, dataset LMS](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kab9/lms) | Monthly | Automated (ONS API) |
| Bank Rate | [Bank of England database, series IUDBEDR](https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp) | On each change | Automated |

All four are public sector information licensed under the Open Government Licence v3.0; the page footer says so.

## How it is calculated

- **Today's money**: each month's average price × (latest CPIH ÷ that month's CPIH).
- **Yearly change** is the UK HPI's own figure where the download has it; otherwise the price against the same month a year earlier.
- **Price to earnings**: London average price ÷ (UK weekly regular pay × 52). The pay figure is UK-wide, so London's true ratio is higher (roughly a fifth); the trend, not the level, is the point.
- **Illustrative mortgage**: 75% loan-to-value, 25-year repayment, interest at Bank Rate + 1.5 points in that month. A gauge of how prices and rates combine, not a quote: real mortgage rates follow swap rates, not only Bank Rate.
- **Bank Rate by month** is the rate in force on the first of each month.
- **Sales, last 12 months** compares the latest 12 months with the 12 before. The latest two or three months are always revised upward as late registrations arrive.

## Keeping it up to date

Nothing to do: all four sources are fetched automatically, at most once a day, and the page data is recomputed every six hours. If a card says "Source not reachable right now: showing the last copy from <date>", the source was down or refused the request and the last snapshot (`the snapshot folder (`SNAPSHOT_DIR`, `/app/snapshots` on Railway)` on the Railway volume) is being shown; it clears itself when the source is back. If a card says "not available right now", the source has never been reached from the server: run the check below from a UK or EU machine to tell a changed download format from a site that blocks US servers.

## Checking it

```
pytest -m network tests/test_sources.py -k "hpi or ons or bank"
```

Local preview: `python -m app.server`, then open `/housing`.

## Where the data actually comes from (checked from the Railway server, Oct 2026)

The first live check showed three sources refusing the server, so the dashboard now uses their reachable equivalents:

| Wanted | Refused | Used instead |
|---|---|---|
| UK HPI per region and borough | landregistry.data.gov.uk per-region download (HTTP 403 to cloud servers) | The monthly UK HPI full file from publicdata.landregistry.gov.uk (~33 MB, every region and borough in one file; the newest month is found automatically) |
| CPIH and average weekly earnings | ONS timeseries API (retired: HTTP 404) | The same series as CSV from the ONS website (`/generator?format=csv`) |
| US 30-year mortgage rate | FRED (times out from cloud servers) | Freddie Mac's PMMS workbook |
| US house prices (Case-Shiller) | FRED | FHFA house price indexes: US purchase-only (monthly, seasonally adjusted), New York and San Francisco metro divisions (quarterly) |
| Hong Kong HIBOR | HKMA API with a 1,000-record page (HTTP 405) | The same API, 100 records a page |

## Added in round 3

| Tab or card | What | Source | How |
|---|---|---|---|
| Prices · Rents | London average monthly private rent | ONS Price Index of Private Rents | Hand-entered: `rents.csv` (no stable series id on the ONS API) |
| Boroughs | All 33 London boroughs: average price, change on a year, 5-year change, sortable; yearly change as bars; the three most and least expensive indexed to 2015 | UK HPI per local authority (one download per borough, paced 0.4 s, cached a day) | Automated |
| Rates & affordability | Bank of England quoted 2-year fixed mortgage rate at 75% LTV (series IUMBV34) next to Bank Rate; the mortgage illustration now uses it, falling back to Bank Rate + 1.5 points before the series starts | Bank of England database | Automated |
| London vs US vs HK | House prices rebased to Jan 2015 = 100: London (UK HPI), US national, New York and San Francisco (FHFA house price indexes), Hong Kong (RVD private domestic index); latest table; borrowing costs: UK 2-year fixed, US 30-year fixed (MORTGAGE30US), HK 1-month HIBOR | FRED, RVD workbook, HKMA open API | Automated; `hk_price_index.csv` is the hand-entered fallback for Hong Kong |

The RVD workbook URL (`his_data_4.xls`) and its layout are the least certain part: the network test checks it, and the card says "not available" if neither the workbook nor the CSV has data.

## Known gaps

- The UK HPI is about two months behind the market and its latest months are provisional.
- Pay is UK-wide, not London (see above). London earnings exist in ONS's ASHE tables but only yearly.
- The Land Registry, ONS and Bank of England sites may refuse requests from Railway's US servers; the page would then show the stale note until a snapshot exists. If that happens on first deploy, the fix is to fetch once from elsewhere and copy the snapshot files to the volume, or to route those downloads through a UK proxy.
