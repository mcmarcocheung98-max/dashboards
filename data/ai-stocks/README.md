# AI Stocks: the setup after the dip (`/ai-stocks`)

**The question:** after the recent pullback in AI stocks, how deep is the dip, is it washing out or still breaking down, and what has
happened after dips like this before?

**Not investment advice.** The page shows where prices stand against their own history. It makes no buy or sell call, and the
"After past dips" tab is a handful of past episodes, not a forecast.

Asked for by the owner on 5 Nov 2026 ("start a stock dashboard for AI stock setup after the dip we see in the market, find metrics like
we do with other dashboard, build signals"). Category: Money & markets.

Code: `app/topics/ai_stocks.py` (data), `app/static/topics/ai-stocks.js` (cards), `tests/test_ai_stocks.py` (fixtures and `smoke_patch()`).
Data for each tab: `/api/ai-stocks/<setup|drawdown|trend|dips|fear|fundamentals>`. `/api/ai-stocks/layout` (not a tab) shows what the
server gets back from each source (FRED and Cboe VIX, Nasdaq for a stock and an ETF, EDGAR), with FRED also tried through curl.

## Tabs, cards and sources

| Tab | Cards | Source | Automated? | Cadence |
|---|---|---|---|---|
| Setup | one card per stock: drawdown from its 52-week high, % above or below its 50- and 200-day averages, RSI 14; the basket against QQQ and SPY; "where we are" | Nasdaq quote API (`_base.nasdaq_daily`; 13 stocks as `stocks`, QQQ/SPY/SMH as `etf`) | yes | daily |
| Drawdown | basket and per-stock drawdown from the running peak since 2020; the current dip; every basket drawdown over 10% | same | yes | daily |
| Trend & breadth | share of the basket above its 50- and 200-day averages; basket RSI 14; basket with its 50- and 200-day averages; the 50/200 crosses | same | yes | daily |
| After past dips | for each basket drawdown of 15% or more: returns 1, 3 and 6 months after the 15% point and after the bottom; median and range | same | yes | daily |
| Fear & relative | VIX; AI basket ÷ QQQ; SMH ÷ SPY; 3- and 12-month returns side by side | FRED `VIXCLS` (CSV through curl), Cboe `VIX_History.csv` when FRED fails; Nasdaq | yes | daily |
| Fundamentals | revenue growth on a year per company and for the basket; hyperscaler capex (trailing four quarters) and its growth | SEC EDGAR companyfacts; capex from `compute_chips._capex()` (imported, not re-downloaded) | yes | quarterly |

The basket: NVDA, AVGO, AMD, TSM, ASML, MU, ARM, MSFT, GOOGL, AMZN, META, ORCL, PLTR. Benchmarks: QQQ, SPY, and SMH for semiconductors.
Yahoo is not used: it answers Railway with 429.

## Method

- **The basket** is an equal-weight index rebalanced daily: each trading day's return is the average of the members' daily returns
  (members with a close that day and the day before), chained, and rebased to 100 on the first trading day of 2020. Prices are
  closes without dividends. Prices are fetched from 2019 so the 200-day averages exist from the start; charts start in 2020.
  Arm listed on 14 September 2023 and joins the basket the day after its first close, so before that the basket has 12 members.
- **Drawdown** is the fall from the running peak since 2 January 2020 (0 at a new high). The **52-week high** on Setup is the highest
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
- **The "where we are" line** on Setup is built from the same figures: depth (within 5% = near the high; 5-10% a pullback; 10-20% a
  correction; deeper a bear market), then washout (breadth under 20% or RSI under 30), or still breaking down (a new 20-day low below the
  50-day average), or stopped making new lows, or back above the 50-day; then VIX; then, when the basket is 15% or more below its
  high, the median and range of past 3-month returns after the 15% point.

## Caveats and gaps

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

## Signals (`data/signals/watchlist.json`, proposed)

Five watch points, marked `"proposed": true` until the owner approves them; the signals board shows them either way. `SIGNALS()` reads
only the cached tab payloads, and each row's `crossed` comes from its own rule:

| Key | Value | Crossed when (the rule) | Lean |
|---|---|---|---|
| `basket_drawdown` | basket drawdown from its high (%) | below -20% (a bear market), or back within -5% **after** a dip of 10% or more in the last 3 months (dip repaired; a basket that never left its high is not "repaired") | +1 within 5% of the high, -1 more than 10% below |
| `breadth_50d` | share of the basket above its 50-day average (%) | below 20% (washout), or above 60% **after** being below 40% in the last 3 months (recovery broadening) | +1 above 60%, -1 below 40% |
| `rsi_basket` | basket RSI 14 | below 30 (oversold) or above 70 | +1 above 60, -1 below 40 |
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
| Trend & breadth | `rsi_basket` | above 60 | below 40 |
| Trend & breadth | `cross` | 50-day above the 200-day | 50-day below |
| After past dips | `past_dips` | (context only, lean 0) | |
| Fear & relative | `vix` | below 20 | above 25 |
| Fear & relative | `ai_vs_qqq` | AI ahead by more than 3 points over 3 months | behind by more than 3 |
| Fundamentals | `revenue_yoy` | basket revenue growth sped up by more than 2 points on the quarter before | slowed by more than 2 |

## Upkeep

Nothing is hand-entered. To change the basket, edit `BASKET` (and `REV_CIKS` for US GAAP filers) in `app/topics/ai_stocks.py`; the
index, breadth and episodes follow. The forward-return table grows by itself as new drawdowns finish.
