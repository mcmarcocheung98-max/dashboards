# Altcoin Study (`/altcoins`)

The four BTC Cycles candidates (HYPE, ENA, SOL, NEAR) in full, the memecoin basket and meme season, and a buy zone for every coin, on one
dashboard. It replaces the separate pages `/hype`, `/ena`, `/sol`, `/near` and `/memecoins`, which now redirect to the matching tab.

## Tabs

| Tab | What it shows |
|---|---|
| Buy zones | Every coin's zone (top, mid, floor), where today's price sits against it, what set the top, the 30-day move and RSI 14; sorted in-zone first |
| HYPE, ENA, SOL, NEAR | One tab per candidate: price against BTC, RSI, market cap, the case for it, its buy zone on a price chart, then Fundamentals (fees, TVL, supply and unlocks against price, the multiples, the unlock schedule) and the Projection (bear / base / bull to end-2028) |
| Memecoins | The basket of six memecoins (see `data/memecoins/README.md`) |
| Meme season | The basket against BTC and the season reading (see `data/memecoins/README.md`) |

## The buy zone rule (`app/topics/altcoins.py`, `buy_zone`)

- **Top**: the coin's 200-day average price. For the four candidates, half the base-case price at end-2028 instead when that is lower, so
  the base case at least doubles from the top of the zone (`VALUE_MULT = 2`). Memecoins have no projection, so their top is the average alone.
- **Floor**: the lowest daily close of the last 365 days. **Mid**: half-way, for staged entries.
- **Status**: *in zone* at or below the top; *above zone*, with the fall needed to reach the top; *no zone* when the top is under the
  year's low (the base case does not double from any price of the last year).

Mechanical and recomputed from each day's prices; research, not investment advice. A coin falling hard sits "in zone" for a long time,
which is why the 30-day move and RSI are shown beside it. Each coin's status is a daily reading, so "What changed since yesterday" flags a coin
entering or leaving its zone.

## Where the numbers come from

Nothing is downloaded by this dashboard itself. The candidates' prices, market caps, fees, TVL and unlocks come with BTC Cycles' background
fill (CoinGecko, DefiLlama; `data/btc-cycles/README.md`), the projection levels from `data/btc-cycles/scenarios.json`, and the memecoins'
prices from the memecoin fill (CoinGecko; `data/memecoins/README.md`).

## Adding a coin

A candidate: add its ticker to `CANDIDATES` in `app/topics/altcoins.py` (it must be a row in `data/btc-cycles/coins.csv`), a tab
function in `VIEWS` in `app/static/topics/altcoins.js`, and its link in `PAGES` in `btc-cycles.js`. A memecoin: a row in `data/memecoins/coins.csv`.
