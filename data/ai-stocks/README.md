# AI Stocks: the setup after the dip (`/ai-stocks`)

**The question:** after the recent pullback in AI stocks, how deep is the dip, is it washing out or still breaking down, and what has
happened after dips like this before?

**Not investment advice.** The page shows where prices stand against their own history. It makes no buy or sell call, and the
"After past dips" tab is a handful of past episodes, not a forecast.

Asked for by the owner on 5 Nov 2026 ("start a stock dashboard for AI stock setup after the dip we see in the market, find metrics like
we do with other dashboard, build signals"). Category: Money & markets.

Extended on 5-6 Nov 2026 at the owner's request: "include sandisk, nebius, bloom, marvell, oracle, iren, applive, AMD, rocket lab,
nvidia" (the **Owner's picks** group below; "applive" is read as **AppLovin**, ticker APP, the closest listed name and an AI
advertising stock that fits the list; tell us if another company was meant), and "take inspiration of this page" (a third-party quant dashboard: we
take its ideas, a setup score with a backtest, institutional holdings from 13F filings and insider trades from Form 4, and build them
from our own sources; we never call that page's API).

Code: `app/topics/ai_stocks.py` (data), `app/static/topics/ai-stocks.js` (cards), `tests/test_ai_stocks.py` (fixtures and `smoke_patch()`).
Data for each tab: `/api/ai-stocks/<setup|drawdown|trend|dips|fear|fundamentals>`. `/api/ai-stocks/layout` (not a tab) shows what the
server gets back from each source (FRED and Cboe VIX, Nasdaq for a stock and an ETF, EDGAR), with FRED also tried through curl.

## Tabs, cards and sources

| Tab | Cards | Source | Automated? | Cadence |
|---|---|---|---|---|
| Setup | one card per stock, in two groups (the AI basket and the owner's picks): drawdown from its 52-week high, % above or below its 50- and 200-day averages, RSI 14; both indexes against QQQ and SPY; "where we are" | Nasdaq quote API (`_base.nasdaq_daily`; 20 stocks as `stocks`, QQQ/SPY/SMH as `etf`) | yes | daily |
| Drawdown | basket and per-stock drawdown from the running peak since 2020; the current dip; every basket drawdown over 10%; the owner's picks index and each pick over its own history | same | yes | daily |
| Trend & breadth | share of the basket above its 50- and 200-day averages; basket RSI 14; basket with its 50- and 200-day averages; the 50/200 crosses | same | yes | daily |
| After past dips | for each basket drawdown of 15% or more: returns 1, 3 and 6 months after the 15% point and after the bottom; median and range | same | yes | daily |
| Fear & relative | VIX; AI basket ÷ QQQ; SMH ÷ SPY; 3- and 12-month returns side by side | FRED `VIXCLS` (CSV through curl), Cboe `VIX_History.csv` when FRED fails; Nasdaq | yes | daily |
| Fundamentals | revenue growth on a year per company and for the basket; hyperscaler capex (trailing four quarters) and its growth | SEC EDGAR companyfacts; capex from `compute_chips._capex()` (imported, not re-downloaded) | yes | quarterly |

The basket: NVDA, AVGO, AMD, TSM, ASML, MU, ARM, MSFT, GOOGL, AMZN, META, ORCL, PLTR. Benchmarks: QQQ, SPY, and SMH for semiconductors.

**Owner's picks**, a second group shown on Setup and Drawdown with its own equal-weight index: SNDK (SanDisk), NBIS (Nebius), BE (Bloom
Energy), MRVL (Marvell), ORCL (Oracle), IREN, APP (AppLovin), AMD, RKLB (Rocket Lab), NVDA. Oracle, AMD and Nvidia are in both groups;
the core 13 are unchanged. Every ticker was checked against Nasdaq's quote API on 6 Nov 2026 (all ten answer with daily closes).
Yahoo is not used: it answers Railway with 429.

## Method

- **The basket** is an equal-weight index rebalanced daily: each trading day's return is the average of the members' daily returns
  (members with a close that day and the day before), chained, and rebased to 100 on the first trading day of 2020. Prices are
  closes without dividends. Prices are fetched from 2019 so the 200-day averages exist from the start; charts start in 2020.
  Arm listed on 14 September 2023 and joins the basket the day after its first close, so before that the basket has 12 members.
- **The owner's picks index** uses the same method, but a stock joins it from its **first full month** of trading: its returns count
  from the first trading day of the month after it listed (SanDisk from March 2025, Nebius from November 2024, IREN from December
  2021, AppLovin from May 2021, Rocket Lab from September 2021). Closes before a company traded as itself are dropped: Nasdaq's
  history for NBIS runs back through Yandex (suspended in February 2022, its last price repeated until the Nebius relisting on
  21 October 2024), RKLB's through the Vector Acquisition SPAC (Rocket Lab from 25 August 2021), and SanDisk's starts with
  when-issued trading (counted from 24 February 2025, its first regular-way day after the spin-off from Western Digital).
- **Drawdown** is the fall from the running peak since 2 January 2020 (0 at a new high). Each stock's drawdown counts over its own
  history: from 2020, or from its own first close when it listed later (Arm, and among the picks SanDisk, Nebius, IREN, AppLovin
  and Rocket Lab), so a young stock's peak is its own, not a price from before it existed. The **52-week high** on Setup is the highest
  close of the last 252 trading days, so a stock's 52-week drawdown can be shallower than its drawdown since 2020.
- **Averages** are simple 50- and 200-day averages of closes. **RSI 14** is Wilder's (exponential smoothing with alpha 1/14), the same
  as the altcoin signals; 100 when there were no down days.
- **Breadth** is the share of members above their own 50-day (or 200-day) average, among the members that have that average yet.
- **Episodes:** a drawdown runs from a peak to the next close above it (or to today when it has not recovered). Days to bottom and days
  to recover are calendar days: peak to trough, and trough to the new high.
- **After past dips:** for every finished basket drawdown of 15% or more, two anchors: the first close 15% below the peak, and the
  bottom. Forward returns are over 21, 63 and 126 trading days (1, 3 and 6 months) from that close. The current drawdown, when it is
  15% or deeper, is shown in the table but left out of the median and range (its future is not known). "Further fall" is how much
  lower the bottom was than the 15% point.
- **Relative returns:** 3 months = 63 trading days, 12 months = 252. AI vs QQQ is the basket's return minus QQQ's, in percentage
  points; the ratio charts divide one by the other and rebase to 100 in January 2020.
- **Revenue growth:** quarterly revenue from 10-Q and 10-K facts (`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`,
  `SalesRevenueNet`; Q4 is the 10-K year minus the first three quarters), mapped to calendar quarters like compute_chips (Nvidia's
  quarter to late October is Q3). The basket figure sums the revenue of the companies that reported both that quarter and the same
  quarter a year before, against that same set a year earlier, so a late filer does not show as a fall.
- **AI Setup Score (0-100), the headline of Setup.** Five parts, each the day's percentile rank against its own daily history since
  2 January 2020 (higher = more euphoric): the basket's drawdown from its high (0 at a high ranks highest), the share of the 13 above
  their 50-day average, the basket's RSI 14, VIX inverted (a low VIX ranks high), and the basket's 63-day return minus QQQ's. The
  score is the mean of the parts a day has (at least three; VIX is carried over a market holiday for up to 5 days), then a 5-day
  moving mean. **0 is fear or washout, 100 is euphoria.** Bands: 0-10 washout (dark green, "past bottoms"), 10-20 fear (light
  green), 20-50 soft (grey), 50-80 neutral, 80-90 warm (orange), 90-100 stretched (red, "drawdown risk"). The sentence under the
  gauge is the band-statistics row for today's band.
  - **Whipsaw:** Setup counts how often the band changed in the last 90 calendar days, and the same count for a score built from
    VIX alone (its percentile, smoothed the same way). A VIX-only score jumps between bands within days; averaging five parts and
    smoothing over five days keeps ours steadier. On live data (4 Nov 2026) it was 5 changes against 9 for VIX alone.
  - **Episodes:** an episode starts on the first day in the band (below 10, or 90 and above), at least 30 calendar days after the
    last day in that band. Washout rows show the best gain: the highest close in the next 126 and 252 trading days (6 and 12
    months) against the close that day. Stretched rows show the worst fall: the lowest close in the next 90 calendar days (0 when it
    never closed lower). A horizon that has not passed yet shows its value "so far". `data/ai-stocks/events.csv` (date,name,note)
    names an episode starting within 30 days of a date in it; the file is optional, and adding a line names an episode.
  - **Band statistics:** for every day in each band since 2020, the forward 1-, 3- and 6-month basket returns (21, 63, 126 trading
    days), counted only where the horizon has passed: the median, and the hit rate (share of days the basket was higher). Days
    next to each other overlap heavily, so the **episodes** column (30-day rule, per band) is the real number of independent samples.
  - **Hindsight:** the ranks use the whole history since 2020, including days after the one being scored. The backtest describes
    how the bands lined up with what followed; it is not a rule anyone could have traded at the time, and not a forecast.
- **The "where we are" line** on Setup is built from the same figures: depth (within 5% = near the high; 5-10% a pullback; 10-20% a
  correction; deeper a bear market), then washout (breadth under 20% or RSI under 30), or still breaking down (a new 20-day low below the
  50-day average), or stopped making new lows, or back above the 50-day; then VIX; then, when the basket is 15% or more below its
  high, the median and range of past 3-month returns after the 15% point.

## Caveats and gaps

- **The AI Setup Score is small-sample history.** Since 2020 there are a handful of washout and stretched episodes; the band
  statistics count thousands of overlapping days but only a few independent episodes. Not a forecast, not investment advice.

- **Small sample.** Since 2020 the basket has had only a few drawdowns of 15% or more (2020, 2022, 2024, 2025 on recent data). A
  median of four numbers is not a statistic to lean on; the range matters as much. History, not a forecast.
- **Survivorship.** The basket is today's AI leaders, picked in 2026. Their past drawdowns recovered partly because these are the
  companies that did well; a basket picked in 2020 would look worse.
- **Valuation multiples are left out.** No free source reachable from Railway gives forward P/E or EV/sales history for these names
  (Yahoo answers 429, the others need a paid key). Revenue growth stands in for "is the business still growing".
- **TSMC, ASML and Arm** are left out of revenue growth: they file 20-F and 6-K under IFRS, and EDGAR's companyfacts has no quarterly
  revenue facts for them. Their prices are in every other tab.
- **Capex** is cash spent on property and equipment by Microsoft, Alphabet, Amazon, Meta and Oracle, all businesses, not only AI
  (see the AI Compute, Power & Chips dashboard).
- **VIX from FRED** has timed out from Railway for other series (see `ai_jobs.py`); when it fails, Cboe's own history file is used and
  the FRED failure is marked handled in `/api/health`. Check with `/api/probe` (`fred vix`, `cboe vix history`) or `/api/ai-stocks/layout`.

## Signals (`data/signals/watchlist.json`, approved 6 Nov 2026)

Five watch points, approved by the owner on 6 Nov 2026, including the two "back to" rules below (a repaired dip counts only after a dip of 10% or more in the last 3 months; breadth back above 60% only after being below 40%). `setup_score` replaced `rsi_basket` when the score was built (approved with them), keeping five. `SIGNALS()` reads
only the cached tab payloads, and each row's `crossed` comes from its own rule:

| Key | Value | Crossed when (the rule) | Lean |
|---|---|---|---|
| `basket_drawdown` | basket drawdown from its high (%) | below -20% (a bear market), or back within -5% **after** a dip of 10% or more in the last 3 months (dip repaired; a basket that never left its high is not "repaired") | +1 within 5% of the high, -1 more than 10% below |
| `breadth_50d` | share of the basket above its 50-day average (%) | below 20% (washout), or above 60% **after** being below 40% in the last 3 months (recovery broadening) | +1 above 60%, -1 below 40% |
| `setup_score` | AI Setup Score, 0-100 | below 10 (washout) or 90 and above (stretched) | +1 above 80, -1 below 20 |
| `vix` | VIX | above 30 (fear), or below 20 while it was above 25 at some point in the last month | +1 below 20, -1 above 25 |
| `ai_vs_qqq` | AI basket minus QQQ, 3-month return (points) | a gap of 10 points or more either way | +1 when AI leads by more than 3 points, -1 when it lags by more |

## Readings (what changed since yesterday)

Leans: **+1 = the setup reads healthier** (shallower drawdown, broader trend, calmer VIX, AI ahead), **-1 = more stress**. A lean
describes the numbers, not a trade.

| Tab | Key | +1 when | -1 when |
|---|---|---|---|
| Setup | `above200` | more than 60% of the 13 stocks above their 200-day average | fewer than 40% |
| Drawdown | `basket_drawdown` | within 5% of the high | more than 10% below |
| Trend & breadth | `breadth_50d` | above 60% | below 40% |
| Setup | `setup_score` | AI Setup Score above 80 | below 20 |
| Trend & breadth | `rsi_basket` | above 60 | below 40 |
| Trend & breadth | `cross` | 50-day above the 200-day | 50-day below |
| After past dips | `past_dips` | (context only, lean 0) | |
| Fear & relative | `vix` | below 20 | above 25 |
| Fear & relative | `ai_vs_qqq` | AI ahead by more than 3 points over 3 months | behind by more than 3 |
| Fundamentals | `revenue_yoy` | basket revenue growth sped up by more than 2 points on the quarter before | slowed by more than 2 |

## Upkeep

Nothing is hand-entered. To change the basket, edit `BASKET` (and `REV_CIKS` for US GAAP filers) in `app/topics/ai_stocks.py`; the
index, breadth and episodes follow. The owner's picks are `PICKS`; a stock that listed after 2019 also needs its first day as itself
in `LISTED`. The forward-return table grows by itself as new drawdowns finish.
