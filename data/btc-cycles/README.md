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

**`scenarios.json`**: the BTC levels per scenario with a `why` each; change them and every coin's projection follows.

**`evidence.csv`** (`date,series,value,source,note`): one row per published reading. Series names the page looks for, exactly: `RWA on-chain value ex-stablecoins (USD)`, `Prediction-market monthly volume (USD)`, `x402 cumulative payment volume (USD)`, `Launchpad launches per day`, `Perp-DEX share of global futures (%)`, `Hyperliquid TVL (USD)`, `Google Trends: sector search index`. The seed rows are the doc's own figures with the doc's sources; one prediction-market row is a zero placeholder to be filled, and the 2023 perp-share row is dated approximately (`verify`).

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
- The first visit after a deploy can take up to a minute on the Candidates tab while 28 coins are fetched 2.2 s apart; the warmer does this in the background from the second minute, so later visits are instant.
- Prediction markets (rank 4) have no liquid token and no row; ASTER, LIT, XPL, SKY, SYRUP and PLUME ids are marked `verify`.
