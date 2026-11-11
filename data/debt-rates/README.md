# Global Debt & Rates (`/debt-rates`)

**The question:** which country hits fiscal stress first (US, UK, Hong Kong, China), and when does interest overtake defence or education spending?

Code: `app/topics/debt_rates.py` (data), `app/static/topics/debt-rates.js` (cards), `tests/test_debt_rates.py` (fixtures and `smoke_patch()`).
Data for each tab: `/api/debt-rates/<debt|interest|yields|policy|stress>`. `/api/debt-rates/layout` (not a tab) shows what the server gets back from every source (status, size, first 300 characters), so you can check reachability from Railway with Actions > show-json.

## Tabs, cards and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| Debt | General government gross debt, % GDP, actual + projection | IMF WEO via DataMapper, `GGXWDG_NGDP`, read from `imf.csv` | **copy** (imf.org refuses Railway) | refresh after each April and October WEO |
| Debt | US federal debt outstanding (total, held by the public) | Treasury Fiscal Data, `debt_to_penny` | yes | daily (shown month-end) |
| Debt | UK public sector net debt, % GDP | ONS PUSF series HF6X (website CSV download) | yes | monthly, ~3 weeks after month-end |
| Interest | US net interest vs defence vs education, rolling 12 months; fiscal-year bars; year interest passed defence | Monthly Treasury Statement table 9 (Fiscal Data `mts_table_9`) | yes | monthly, ~8th business day |
| Interest | Interest ÷ revenue: US (MTS net interest ÷ total receipts), UK (ONS NMFX central government debt interest ÷ ANBT public sector current receipts) | MTS; ONS PUSF | yes | monthly |
| Interest | Average rate on marketable Treasury debt | Fiscal Data `avg_interest_rates`, "Total Marketable" | yes | monthly |
| Interest | General government net interest, % GDP and % revenue | IMF Fiscal Monitor: `GGXONLB_G01_GDP_PT` − `GGXCNL_G01_GDP_PT`, ÷ `GGR_G01_GDP_PT`, from `imf.csv` | **copy** | twice a year |
| Interest | UK, Hong Kong, China: interest vs defence vs education | `spending.csv` | **hand-entered** | yearly, after each budget / outturn |
| Interest | CBO projections: net interest vs defense, % GDP | `cbo.csv` | **hand-entered** | each CBO Budget and Economic Outlook |
| Yields | 10-year yields: US, UK, HK, China | US: home.treasury.gov par curve CSV (one file a year since 2000); UK: BoE IADB `IUDMNPY` (falls back to `IUDMNZC`); HK: `hk_10y.csv` (EFN 10-year to 2015 copied from the HKMA EFBN API, then HKGB); China: `cn_10y.csv` | US/UK yes; HK and China **from CSV** | daily / as entered |
| Yields | Real 10-year: US TIPS, UK index-linked | Treasury real yield curve CSV; BoE IADB `IUDMRZC` (falls back to `IUDMRPY`) | yes | daily |
| Policy | Fed range and EFFR | NY Fed API (`effr/search.json`); `fed_target.csv` before the API's range data | API yes; pre-2016 **hand-entered** | daily |
| Policy | Bank Rate | BoE IADB `IUDBEDR` | yes | on change |
| Policy | HKMA base rate | computed from the HKMA formula's Fed term: Fed lower bound + 0.5, from March 2009 (the HIBOR term needs the HKMA API, which refuses Railway; it has not set the rate since 2009) | derived | monthly |
| Policy | PBoC 7-day reverse repo, 1-year LPR | `pboc.csv` | **hand-entered** | on change |
| Policy & CPI | CPI inflation, year on year: US, UK, Hong Kong, China | US: CPI-U all items NSA from Treasury's TIPS reference CPI on Fiscal Data (`tips_cpi_data_detail`, CUSIP 912810FQ6, from Feb 2008): the reference CPI on the 1st of month M is CPI-U for M−3 by definition, and the last published day gives M−2. BLS refuses Railway (403 on its bulk files on 2026-10-26; its API's 25-a-day quota goes to the ai dashboard); UK: ONS D7G7; HK: C&SD table 510-60001 (composite CPI); China: `cn_cpi.csv` | US/UK/HK yes; China **hand-entered** | monthly (China yearly) |
| Policy & CPI | Real policy rate = policy rate − CPI | computed | derived | monthly |
| Policy & CPI | FOMC rate decisions (each change in the target or the top of the range) | computed from the Fed range (NY Fed API from July 2000, `fed_target.csv` before) | derived | on change |
| FOMC & odds | Next FOMC meetings | `fomc.csv` | **hand-entered** | yearly, when the Fed publishes the calendar |
| FOMC & odds | Polymarket odds: every open event tagged `fed-rates` (Fed decisions, number of cuts, 10-year yield ranges), each outcome's chance = price of its Yes share; daily price history of the next Fed-decision event's outcomes | Polymarket Gamma API (`gamma-api.polymarket.com/events?tag_slug=fed-rates`; events under $100k traded are left out, the rest sorted by volume; the history is the next 'Fed Decision in …' event) and CLOB API (`clob.polymarket.com/prices-history`) | yes | hourly (payload cached 30 minutes) |
| FOMC history & odds | Kalshi odds per rate level for the next meetings, and Polymarket vs Kalshi on the next decision | Kalshi trade API v2, series `KXFED` (one market per 'upper bound above X%' strike; level chance = difference of neighbouring strikes, rescaled to sum to 1) | yes | hourly |
| FOMC history & odds | Every Fed move of the last 20 years with the 10-year yield, US CPI and the events around it; rate cycles (runs of moves in one direction, split by an 18-month pause) with the 10-year's change; computed insights | target history (NY Fed + `fed_target.csv`), Treasury curve, CPI, `fomc_events.csv` | computed + **hand-entered context** | on change |
| Debt | US marketable debt by maturity: bills share, bills vs notes/bonds/TIPS/FRNs; average maturity by country | Fiscal Data MSPD table 1 (`v1/debt/mspd/mspd_table_1`, monthly from 2001); `maturity.csv` | US yes; averages **hand-entered** | monthly |
| Fed & Treasury buying | Fed holdings (Treasuries, MBS, bills), Fed share of marketable Treasuries, QE/QT programmes with the change in holdings and in the 10-year over each, Treasury buybacks by type | NY Fed SOMA summary (`markets.newyorkfed.org/api/soma/summary.json`, weekly), MSPD, Fiscal Data `buybacks_operations`; `qe_programs.csv` | yes; programme dates **hand-entered** | weekly / per operation |
| Stress | Scorecard: debt, interest/revenue, r, g, r − g, debt-stabilising primary balance, IMF primary balance, gap | `imf.csv` (`NGDP_RPCH`, `PCPIPCH`, `GGXONLB_G01_GDP_PT`), latest 10-year yields | partly (IMF copy; China and HK yields from CSV) | |
| Stress | 10-year minus policy rate (term-premium proxy), US 10y − 2y | from the series above | yes | |
| Stress | Auction tails, downgrades, market stress | `stress_events.csv` | **hand-entered** notes | as events happen |

Each chart's card says what it shows and what 5-, 10- and 20-year question it answers.

## Hand-entered files

- `imf.csv`: `date,series,value,source,note` with series `<ISO> <indicator>` (USA, GBR, HKG, CHN; indicators as above), dated 1 January of each
  year; this calendar year onwards is drawn as projection. imf.org answers GitHub runners but refuses the Railway server (HTTP 403,
  checked with `/api/debt-rates/layout` on 2026-10-26), so the page reads this copy. **US and UK rows were copied exactly from the API
  on 2026-10-26** (Actions > show-json on `https://www.imf.org/external/datamapper/api/v1/<indicator>`). The API ignores its country
  filter and the job log is cut at about 300k characters; entities are sorted by name, so the end of the log (United Kingdom,
  United States) survives and China and Hong Kong do not. **China and Hong Kong rows were copied exactly from the IMF SDMX API on
  2026-11-11** (show-json on `https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/%2B/<ISO>.<code>.A?format=sdmx-json&attributes=none`,
  one country and one indicator per query: the API honours only the first indicator in a key). The SDMX WEO dataflow carries the
  balance, primary balance and revenue as `GGXCNL_NGDP`, `GGXONLB_NGDP` and `GGR_NGDP`; those rows keep the page's `_G01_GDP_PT`
  series names and say the WEO code in `note`. Refresh all rows after each WEO (April, October). `pytest -m network tests/test_debt_rates.py -k imf` compares the copy with the live API from a machine that can
  reach it.

All rows carry a `source` URL. Rows whose `note` says **verify** were written from memory (or from a search summary) and must be checked against the cited page; replace the value and drop `verify` once checked.

- `spending.csv`: `date,series,value,source,note`. Series are `<country> <item>` with country `UK`, `Hong Kong` or `China` (the page splits on the first space, so write `Hong Kong education`). Items: `interest`, `defence`, `education`, and forecasts such as `interest (OBR forecast)` (shown dashed). Units: £bn (UK, fiscal year ending 31 March, HM Treasury PESA), HK$bn (HKSAR Budget, year ending 31 March), CN¥bn (MoF national general public budget, calendar year). **All rows are currently `verify`.** Update each summer (PESA) and after each Budget.
- `cbo.csv`: CBO baseline, % of GDP, US fiscal years. Update when CBO publishes (usually January/February). **verify.**
- `cn_10y.csv`: China 10-year government bond yield, year-end, % (ChinaBond). Add a row each month or quarter if you want more detail. **verify.**
- `hk_10y.csv`: Exchange Fund Note 10-year month-end yields, Oct 1996 to Feb 2015, **copied from the HKMA API on 2026-10-26** (it refuses Railway with HTTP 405), then HKGB 10-year yields after the notes stopped: tender average yields from HKMA press releases, or year-end secondary yields (**verify**).
- `pboc.csv`: PBoC 1-year LPR and 7-day reverse repo, one row per change. Changes after May 2025 are not entered yet: check pbc.gov.cn and chinamoney.com.cn. **verify.**
- `fed_target.csv`: Fed target (to Dec 2008) and upper bound of the range (from Dec 2008), one row per change, for the years before the NY Fed API reports the range. **verify** against the FOMC open market operations history.
- `fomc_events.csv`: `date,event,source,note,emergency`: what the Fed was reacting to (crises, data, QE announcements), each linked to its source; `emergency = yes` marks a move between scheduled meetings. A decision shows every event from 45 days before it. The September 2026 hike has no context yet: add the FOMC statement's reason.
- `qe_programs.csv`: `date,end,name,kind,what,source,note`: QE1-3, Twist, QT1-2, reserve-management purchases and Treasury buybacks. Rows marked verify (end of QE1, Covid QE size, end of QT2, the 2025 bill purchases, the buyback start) are from memory.
- `maturity.csv`: average maturity by country (US, UK, China, HK), all **verify**.
- `fomc.csv`: `date,meeting,source,note`, one row per scheduled FOMC meeting, dated the decision day (second day). 2026 entered from memory (**verify**); add the next year's dates when the Fed publishes them.
- `cn_cpi.csv`: China CPI, annual average year-on-year %, NBS (**verify**). Monthly rows can be added (date = the month).
- `stress_events.csv`: `date,country,event,source,note`, notable auction tails, downgrades and market stress. Add a row when an auction tails noticeably (the TreasuryDirect result against the when-issued yield) or a rating changes.

## Tabs

Interest rates & CPI (first), FOMC history & odds, Debt, Interest cost, Yields, Fed & Treasury buying, Stress. Each tab ends with "What each
number on this tab means", a folded glossary of every metric on it (in `app/static/topics/debt-rates.js`, `GLOSS`).

## What changed since yesterday (READINGS)

`READINGS()` reports the headline readings from the cached tab payloads. **lean +1 means less fiscal stress (shown green by the shared card), -1 more (red)**: US and UK debt % of GDP (-1 at 100% or more, +1 at 60% or less; China and HK lean 0), US debt added a day (-1 at $6bn or more, +1 at $3bn or less), US interest
share of receipts (-1 at 15% or more, +1 at 10% or less), US interest above defence (-1), UK interest share (-1 at 10%, +1 at 7%),
US and UK 10-year yields (-1 at 4.5% or more, +1 at 3% or less), each country's stress gap (-1 above +0.5 points of GDP, +1 below
-0.5) and the US and UK 10-year minus policy spread (-1 at 1.5 points or more, +1 at zero or below). US and UK CPI inflation (-1 at 3% or more, +1 at 2% or less), the US bills share (-1 at 22% or more, +1 at 15% or less), the Fed's share of marketable Treasuries (-1 at 15% or less, +1 at 20% or more). Policy rates, the Polymarket odds for the next Fed decision, the HK and China CPI and the HK and China
yields are reported with lean 0.

## Caveats

- IMF net interest = primary balance − overall balance. For Hong Kong it is negative (net interest income on reserves); China's covers the official budget only.
- The stress scorecard uses today's 10-year yield as `r` (marginal cost) rather than the average effective rate on the stock of debt, so it shows where debt dynamics are heading rather than this year's arithmetic.
- US federal education (MTS function 500) includes student-loan re-estimates and is volatile; most US education is state and local.
- UK interest (NMFX) is central government gross interest payable, including the RPI uplift on index-linked gilts and before Asset Purchase Facility transfers.
- Reachability from Railway is checked with `/api/debt-rates/layout`. On 2026-10-26 Railway reached Fiscal Data, home.treasury.gov, the NY Fed, the BoE IADB (IUDMRPY is not a valid code; IUDMRZC is used) and the ONS; imf.org refused it (403) and so did the HKMA API (405). Both answer GitHub runners.

## Requests for shared code

None. (The IMF copy would be easier to refresh with a workflow that saves the DataMapper JSON as an artifact, since show-json logs cut off long responses. A request, not needed for the page to work.)
