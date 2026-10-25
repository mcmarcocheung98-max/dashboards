# BTC Cycles & Sector Rotation (`/btc-cycles`)

A dashboard built on the research doc "BTC Cycles & Sector Rotation: 2013–2026 and the 2026–27 Setup": four Bitcoin cycles, which altcoin sectors won each one, what the winners had in common, the ranked candidates for 2026–27, and the six signals the doc says to watch. The doc's tables are rendered as they stand; a live layer adds the price history and the measurable series so the thesis can be checked against the market every day.

## What it shows

| Tab | Cards | Series |
|---|---|---|
| Cycles | Headline figures | BTC price, distance from the Oct 2025 peak and Jun 2026 low, vs 200-day average, days since and until a halving |
| | Bottom line | The doc's two summary paragraphs |
| | BTC since 2010 (log) | Weekly closes, 200-day average, the doc's peak and low markers, halving dates |
| | Each cycle from its halving | Price ÷ price on halving day, by days before and after, one line per cycle |
| | Drawdown | Distance below the running high |
| | Cycle anatomy table | The doc's cycle 1–5 table |
| Sectors | Cycle 1 / 2 / 3 / 4 | That cycle's sector table from the doc, and its peak multiples as a log-scale bar chart |
| | Cross-cycle comparison | The doc's 15-row table |
| Winner metrics | Live cards | DeFi TVL, stablecoin supply, Hyperliquid TVL, Hyperliquid 30-day revenue, perp-DEX 30-day volume, perp DEXs by volume |
| | Metrics table | The doc's "common metrics of cycle winners" |
| Candidates 2026–27 | Projection method | The BTC scenario levels for end-2027 and end-2028 with the reasoning behind each |
| | One row per candidate coin, grouped by the doc's rank | Links to CoinMarketCap, DefiLlama and CoinGecko; price, 24h and 1-year change, market cap, RSI 14, RSI of the coin ÷ BTC ratio, beta to BTC, 90-day performance vs BTC, base-case price for end-2027 and end-2028; a 90-day sparkline; and on "Show charts": price with BTC rebased (log), RSI vs BTC, market cap, and the projection band with a bear / base / bull table and implied market cap |
| | The doc's ranked table | Folded under a button |
| | Sector evidence | Hand-entered series for sectors without a liquid token (RWA value, prediction-market volume, x402, perp share) |
| ETFs | Headline figures | Net flows since launch, BTC taken in, last 30 days, last day, in/out streak, IBIT's share |
| | Daily and rolling 30-day flows | Bars, green in and red out |
| | Cumulative flows | In US$ against the BTC price, and in BTC |
| | By issuer | Cumulative flows per fund and a table: since launch, last 30 trading days, last day, best and worst day |
| | Hong Kong and UK | BTC held by Hong Kong spot ETFs and UK ETNs (hand-entered) and a milestones table |
| Strategy (MSTR) | Headline figures | BTC held, share of supply, value, approximate average cost, mNAV, 90-day correlation and beta with BTC, purchases |
| | Charts | BTC held, mNAV, MSTR vs BTC rebased, correlation and beta, BTC per 1,000 shares |
| | Every purchase | Date, BTC added, holdings after, BTC price that day, approximate dollars |
| | UK and HK treasury companies | The Smarter Web Company and Boyaa Interactive: price, correlation with BTC, holdings (hand-entered) |
| Signals | Status table | The doc's six signals, each with a mechanical status on today's data, or "hand-entered" |
| | Volume and dominance | BTC spot volume vs the $10bn line; dominance logged daily since deploy |
| | The doc's text | Signals in order, timing on the halving clock, what could break the pattern |

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Every table and paragraph | The research doc, copied into `research.json` | As the doc is revised | Hand-maintained file |
| BTC daily price since 2010 | [Coin Metrics community data](https://coinmetrics.io/community-network-data/), `PriceUSD` | Daily | Automated |
| DeFi TVL (all chains) | [DefiLlama](https://defillama.com) `historicalChainTvl` | Daily | Automated |
| Stablecoin supply | DefiLlama `stablecoincharts/all` | Daily | Automated |
| Hyperliquid TVL and daily revenue | DefiLlama `protocol/hyperliquid`, `summary/fees/hyperliquid` | Daily | Automated |
| Perp-DEX volume, total and by protocol | DefiLlama `overview/derivatives` | Daily | Automated |
| BTC dominance and total market volume | [CoinGecko](https://www.coingecko.com/en/global-charts) `global` | Logged once a day | Automated; no free history, so the log starts at first deploy |
| US spot ETF flows per issuer, US$ | [Farside](https://farside.co.uk/bitcoin-etf-flow-all-data/) daily table | Daily | Automated (HTML parse) |
| US spot ETF flows in BTC | [bitbo](https://bitbo.io/treasuries/etf-flows/) | Daily | Automated |
| Strategy holdings and share counts | [mstr-nav-tracker dataset](https://github.com/jefferych1/mstr-nav-tracker), built from SEC filings | As Strategy reports | Automated |
| MSTR share price | Yahoo Finance chart API, else [Nasdaq's quote API](https://www.nasdaq.com/market-activity/stocks/mstr/historical) | Daily | Automated |
| UK and HK treasury share prices (SWC.L, 0434.HK) | Yahoo, else CNBC chart bars (`ts-api.cnbc.com`; Stooq answers Railway with an HTML page, so it is not used); if neither answers the card shows holdings only and says so | Daily | Automated |
| HK ETF and UK ETN holdings; UK and HK treasury holdings; ETF milestones | Issuer and company pages | As published | Hand-entered: `etf_holdings.csv`, `treasuries.csv`, `etf_milestones.csv` |
| BTC spot volume, last 365 days | CoinGecko `coins/bitcoin/market_chart` | Daily | Automated |
| Each candidate coin's price and market cap, 365 days | CoinGecko `coins/{id}/market_chart`, ids in `coins.csv` | Daily, one request per coin, paced 2.2 s apart | Automated |
| RWA value, prediction-market volume, x402 volume, launches per day, perp-DEX share, Google Trends | The pages the doc cites | As published | Hand-entered: `evidence.csv` |

Coin Metrics community data is free for non-commercial use with attribution. DefiLlama and CoinGecko public endpoints are free with rate limits; everything is fetched at most once a day.

## How it is calculated

- **Each cycle from its halving**: price on each day divided by the price on the halving day, from 550 days before to 730 days after, sampled every third day.
- **Drawdown** is price ÷ running maximum − 1, weekly.
- **Rolling 30-day** revenue and volume are sums of DefiLlama's daily figures, shown weekly.
- **RSI 14** uses Wilder's smoothing on daily closes. **RSI vs BTC** is the same RSI on the coin ÷ BTC price ratio, so it reads the coin's strength against Bitcoin rather than against the dollar.
- **Beta to BTC** is the slope of the coin's daily log returns on BTC's over the last 365 days, clipped to 0.5–3.0.
- **Projection** for each scenario: price now × (BTC scenario ÷ BTC now) ^ beta. The BTC levels and the reasoning are in `scenarios.json`: end-2027 as the "2019 / 2023" year (bear = the doc's NYDIG retest depth, base = June 2026 low × 1.95, bull = × 2.55), end-2028 as the halving year (× 2, × 4, × 6.5). Implied market cap = projected price × today's circulating supply. It is mechanical and says nothing about a coin's own fundamentals, unlocks or survival.
- **Signal statuses** apply the doc's rule to today's data: launches per day > 1,000 (hand-entered); stablecoin supply up for 8 or more consecutive weeks; Hyperliquid revenue over the last 90 days above the 90 days before while BTC is down over 90 days; BTC spot volume 30-day average ≥ $10bn; dominance 3 points below the highest logged reading when that high was ≥ 58%; Google Trends is hand-entered and marked "watch". Statuses are mechanical and say nothing about what to do.

## Keeping it up to date

**The research** is `research.json`. Each tab's tables and paragraphs come from it, so revising the doc means editing the matching entry: `bottom_line`, `anatomy`, `cycles[n]` (rows are objects keyed by the column names; `_multiples` is parsed from the "Peak multiple" column and drives the bar chart), `cross_cycle`, `metrics`, `candidates`, `signals`, `sources`, and `markers` / `cycle_peak` / `cycle_low` for the chart annotations. Update `as_of` when you do. Inline links are written as `[text](url)`.

**Automated series** need nothing. A card saying "showing the last copy from" means the API was down and the snapshot is shown.

**`coins.csv`** (`rank,sector,ticker,name,coingecko_id,cmc_slug,defillama_slug,note`): one row per candidate coin. `coingecko_id` is what the data is fetched by; the two slugs build the links (leave blank for no page). Rows marked `verify` carry an id copied from memory: run the network test below, which tries every id, and fix any that fail. Adding a coin is one row.

**`coin_notes.json`**: per ticker, `narrative` (why it fits its sector), `standout` (the metric the doc highlights) and `thesis` (what the projection assumes and what would break it). Editorial, written from the doc; rewrite freely. The "Today" line under each coin is computed from live data (RSI vs BTC extremes, 90-day strength against the other candidates, distance from the 1-year high, beta, market-cap rank).

**`scenarios.json`**: the BTC levels per scenario with a `why` each; change them and every coin's projection follows.

**`evidence.csv`** (`date,series,value,source,note`): one row per published reading. Series names the page looks for, exactly: `RWA on-chain value ex-stablecoins (USD)`, `Prediction-market monthly volume (USD)`, `x402 cumulative payment volume (USD)`, `Launchpad launches per day`, `Perp-DEX share of global futures (%)`, `Hyperliquid TVL (USD)`, `Google Trends: sector search index`. The seed rows are the doc's own figures with the doc's sources; one prediction-market row is a zero placeholder to be filled, and the 2023 perp-share row is dated approximately (`verify`).

**Dates**: every time chart on a tab shares one date axis. The range bar (3M to All) sets them all; dragging or zooming any chart moves the rest. Projections keep their 2027-28 end.

**`etf_holdings.csv`** (`date,series,value,source,note`): BTC held by non-US funds; series `Hong Kong spot ETFs (BTC)` or `UK ETNs (BTC)`. One cited reading so far (HK, 3 May 2024, from the first three days' inflows); the memory seed for mid-2025 had no source and was removed. Trackers (bitcointreasuries.net, bold.report, bitbo) disagree fund by fund, so add later points from the funds' HKEX filings or a dated report. No UK ETN holdings figure is published in one place yet; UK issuers' factsheets give per-product BTC.

**`treasuries.csv`** (`date,company,country,yahoo,btc_held,source,note`): one row per disclosed holding of a UK or HK company; `yahoo` is the Yahoo ticker (`.L` London, `.HK` Hong Kong), from which the CNBC symbol is derived (`SWC-GB`; `434-HK`, CNBC drops the leading zero). Hover the "Holdings only" line on a card to see what each price source answered. Rows cite the company's own RNS (FCA National Storage Mechanism or Investegate) or HKEX announcement.

**`etf_milestones.csv`** (`date,event,market,source,note`): dated events shown on the ETFs tab, each cited to the regulator's or exchange's own release, or to the report that dates it.

**Source notes (Oct 2026).** DefiLlama's perp-volume endpoints became paid (HTTP 402), so the page shows Hyperliquid's fees and all-chain spot DEX volume instead, both free. CoinGecko limits free calls to a few a minute, so coin data is filled by a background job 13 seconds apart every six hours; a coin not reached yet says "loading in the background". Yahoo refuses cloud servers, so stock prices fall back to Nasdaq's quote API (US tickers) and CNBC (London and Hong Kong), and MSTR uses BTC prices from Coin Metrics.

## Checking it

```
pytest -m network tests/test_sources.py -k "coinmetrics or llama or coingecko"   # the coin test takes about a minute: one paced request per coin
```

Local preview: `python -m app.server`, then open `/btc-cycles`.

## Known gaps

- Dominance has no free history, so its chart grows from the first deploy; the "rolling over from a new high" signal is meaningful only after a few months of log.
- The doc's signal 2 is per-chain stablecoin supply; the page uses the total. DefiLlama's per-chain endpoints could replace it.
- Google Trends has no stable free API; the sixth signal is hand-entered.
- Spot + ETF volume (the doc's signal 4) is approximated by CoinGecko's all-exchange spot volume.
- Pre-2024 sector figures are the doc's approximations and are labelled so.
- After a deploy the background fill takes about 7 minutes (28 coins, 13 s apart, longer after a 429); until a coin is reached its row says "loading in the background". Live check 25 Oct 2026 23:21 UTC (Actions > live-check, then show-json on `/api/health` and `/api/btc-cycles/coins`): all 28 coins filled, every CoinGecko source fresh, every tab OK; the only "not available" cards were the two UK/HK treasury prices on the MSTR tab.
- Prediction markets (rank 4) have no liquid token and no row; ASTER, LIT, XPL, SKY, SYRUP and PLUME ids are marked `verify`.
