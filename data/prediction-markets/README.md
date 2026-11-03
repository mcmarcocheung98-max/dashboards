# Prediction Markets (`/prediction-markets`)

**The question:** what does the money say will happen, where did the odds move, and how well have these markets called things before?

Code: `app/topics/prediction_markets.py` (data), `app/static/topics/prediction-markets.js` (cards), `tests/test_prediction_markets.py` (fixtures in each
source's own layout and `smoke_patch()`). Data for each tab: `/api/prediction-markets/<overview|markets|categories|venues|regions|accuracy>`.
`/api/prediction-markets/layout` (not a tab) shows what the server gets back from every source (status, size, first 300 characters), plus how many
rows the daily log and the calibration sample hold. Read it from Railway's network with Actions > show-json.

Not investment or betting advice. A price is what traders pay for a share that pays $1 if the event happens, not a forecast by this site.

## Tabs, cards and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| Overview | Biggest movers, 24 hours and 7 days | Polymarket Gamma `/events` (open, by 24-hour volume, 3 pages of 100, plus the top 50 under each tag in `POLY_TAGS`): each market's `oneDayPriceChange` / `oneWeekPriceChange`, in points. A mover must have traded $25k in the day ($100k in the week); one market per event | yes | hourly |
| Overview | Most traded markets and events, last 24 hours | Gamma `volume24hr`, `volumeNum`, `liquidityNum` | yes | hourly |
| Overview | Traded in the last 24 hours, by category (bars) and over time (lines) | Gamma event tags mapped to six categories (`CATEGORIES` in the module); the line is the daily log | yes; the history is **logged by this server** | daily |
| Markets | Odds history of each watchlist market | Polymarket CLOB `/prices-history?interval=max&fidelity=1440` (daily) | yes | hourly |
| Markets | Money behind the moves: volume traded each day, liquidity | the daily log (Gamma has no history of either: the day's change in all-time volume, and the liquidity read once a day) | **logged** | daily |
| Categories | Totals and the most traded markets per category; 24-hour volume and liquidity by category over time | Gamma; the daily log | yes / **logged** | hourly / daily |
| Cross-venue | The same question on Polymarket, Kalshi, Manifold and PredictIt, with the gap (highest minus lowest price, real-money venues and all) | Gamma; Kalshi `trade-api/v2/markets?series_ticker=…` (`last_price_dollars`, or the bid/ask middle; `volume_fp`); Manifold `v0/search-markets` (`probability`; play money); PredictIt `api/marketdata/all/` (`lastTradePrice`) | yes; each venue's price **logged** daily for the history | hourly / daily |
| US / UK / HK | Watchlist rows by region, their Polymarket histories and other venues, and the most traded other markets under each region's tags | as above; region tags in `REGION_TAGS` | yes | hourly |
| Accuracy | Calibration (price 30 and 7 days before resolution against how often Yes happened), Brier scores, by category, big misses | Gamma `/events?closed=true` (the 200 most traded closed events of the last year with their markets and tags; resolved Yes/No markets with $50k+ traded and a final price of exactly 1 or 0) and each market's daily CLOB history (`interval=max`; a 40-day start/end window answers 400) | yes: a **paced background job** adds up to 120 markets a run to `resolved.json` on the volume | every 6 hours |

Every chart's card says what it shows. Changes are in points of probability (0.62 → 0.65 is +3 points).

## The watchlist (`watchlist.csv`)

`date,key,label,category,region,polymarket,pick,kalshi,manifold,predictit,source,note`: one row per question. Rows find their market on
each venue by **keywords**, so the next Fed meeting or a new contract is picked up without editing the file:

- `polymarket`: words that must all appear in the event title, question or outcome of an open two-outcome market in the pool, each at
  the start of a word (`boe` does not match "Nijboer"; `democrat` matches "Democratic"); `a/b` means either, `_` stands for a space
  (`no_change`), `!word` means the word must not appear (`cpi !china`).
- `kalshi`: `SERIES:keywords`, e.g. `KXFEDDECISION:hold/maintain` (keywords matched on the market title, its Yes subtitle and its ticker, so `CONTROLH:2026` picks the 2026 House race).
- `manifold`: `search term:keywords` (open binary markets only).
- `predictit`: keywords on the market and contract name.
- `pick`: `volume` (the most traded match) or `soonest` (the one that closes first: the next meeting, the next print).
- `category`: politics, macro, crypto, ai, sports, geo. `region`: US, UK, HK or blank.

The Markets and Cross-venue tabs show what each row matched; check it before reading the number. Rows whose keywords or Kalshi series came from
memory say **verify** in the note; when a match looks wrong, tighten the keywords and change the note to say when it was checked. Every row
cites a source (the venue page).

## What is logged, and where

The background jobs (`BACKGROUND` in the module) run when the server starts and every 6 hours:

- `log_today()` writes `SNAP_DIR/prediction-markets/daily.csv` once per UTC day: each watchlist row's price on each venue, its Polymarket all-time
  volume and liquidity, and each category's 24-hour volume, all-time volume and liquidity. The cross-venue, volume and category lines start on
  the day of the first deploy and grow a point a day.
- `fill_accuracy()` keeps `SNAP_DIR/prediction-markets/resolved.json`: resolved markets with their price 30 and 7 days before they closed.

Both live on the Railway volume and go into the month-end archive with the other snapshots.

## What changed since yesterday (READINGS)

One reading per watchlist market: its Polymarket probability (%), **lean +1 when the odds rose over 24 hours, −1 when they fell** (by half a
point or more), 0 otherwise. The three biggest moves say "biggest mover: ±x pts in 24 hours" in the note. Read from the cached Markets payload
only.

## Signals (`SIGNALS()`, approved 3 Nov 2026)

The four approved in `data/signals/watchlist.json`, read from cached data only (the watchlist rows in memory, the daily log, `resolved.json`);
`crossed` is this module's own test:

| Key | Value | Crossed when |
|---|---|---|
| `biggest_move` | the largest 24-hour change in a watchlist market's Polymarket price, in points (lean = its sign) | 10 points or more either way |
| `venue_gap` | the largest gap between Polymarket and Kalshi among watchlist questions matched on both | above 5 points |
| `volume` | the watchlist markets' 24-hour volume now, against the average logged day of the last 30 (each market's logged 24-hour volume; before 3 Nov, the day's change in its all-time volume) | twice the average or more, with 5+ logged days |
| `calibration` | Brier score of the price 30 days before resolution, by month resolved (months with 10+ markets) | higher in each of the last two complete months than the month before (three back-to-back months; a month under 10 markets breaks the run) |

## Pacing and limits

Downloads to the same host wait `PACE` (0.5 s) after the previous one and are cached an hour (a snapshot on the volume is served if a source
is down). A cold start makes about 15 Gamma calls, one CLOB call per watchlist row, one Kalshi call per series, one Manifold search per row and
one PredictIt call. Kalshi volume is in contracts of $1. Manifold is play money (mana). PredictIt caps positions at $850, so its prices can sit
apart from the others.

## Top card

Every tab with time charts builds its top card with `followHead` from `topic.html`: hovering a chart shows that day's figures (each the same
series its chart draws, with the change over the week before), a click keeps the day, "Back to latest" returns. Accuracy has no time chart,
so its card shows the latest sample.

## Requests for shared code

None open.
