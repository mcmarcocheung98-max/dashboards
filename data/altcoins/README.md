# Altcoin Study (`/altcoins`)

The four BTC Cycles candidates (HYPE, ENA, SOL, NEAR) in full, the memecoin basket and meme season, and a buy zone for every coin, on one
dashboard. It replaces the separate pages `/hype`, `/ena`, `/sol`, `/near` and `/memecoins`, which now redirect to the matching tab.

## Tabs

| Tab | What it shows |
|---|---|
| Buy zones | Every coin's zone (top, mid, floor), where today's price sits against it, what set the top, the 30-day move and RSI 14; sorted in-zone first |
| Volume zones | Per coin (pick one): daily candles with the big-volume days marked and the support / resistance zones they left, what the coin did after its own big days and zone retests, and a table of every coin against its zones |
| Signals | Twenty daily signals on top of the volume zones, each scored −1 to +1, weighted by their record across every coin and summed into one final signal per coin; a table of all coins, each coin's 20 signals with weights, the score day by day and a walk-forward backtest of trading it |
| HYPE, ENA, SOL, NEAR | One tab per candidate: its signal board (below), price against BTC, RSI, market cap, the case for it, its buy zone on a price chart, then Fundamentals (fees, TVL, supply and unlocks against price, the multiples, the unlock schedule) and the Projection (bear / base / bull to end-2028) |
| ENA unlocks | ENA's full unlock schedule (past and ahead), the next unlock, what the price did before / into / after every unlock against an ordinary day, simple short-before / buy-after rules with costs and a placebo, and a date check of each listed day against volume |
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

## The coin signal board rule (`app/topics/_coin_board.py`)

The trading bot's BTC spot signal, rebuilt per coin. Each gauge scores a day from +1 (in its buy zone, where past lows sat) to −1 (in its
sell zone, near past tops), 0 between, with a straight ramp through each zone; the score is the weighted average of the gauges with data that
day (valuation gauges count double; at least four gauges or no score), read at the BTC board's levels: ≥ +0.5 STRONG BUY, ≥ +0.2 BUY,
≤ −0.2 SELL, ≤ −0.5 STRONG SELL.

| Gauge | Group | Buy zone (+1 at) | Sell zone (−1 at) | Source |
|---|---|---|---|---|
| Price / 200-day average | valuation ×2 | < 0.8 (0.6) | > 1.6 (2.4) | the BTC Mayer zones 0.8 / 2.4, widened for altcoin swings |
| Price-to-fees vs its 1-year median | valuation ×2 | < 0.75 (0.5) | > 1.5 (2.5) | own; market cap / annualised 30-day fees (DefiLlama) |
| Market cap / TVL vs its 1-year median | valuation ×2 | < 0.75 (0.5) | > 1.5 (2.5) | own; DefiLlama TVL |
| Price / 1-year high | valuation ×2 | < 50% (30%) | > 90% (100%) | own |
| RSI 14, daily | momentum | < 35 (25) | > 65 (80) | contrarian, as the BTC board's Fear and Greed |
| Supply unlocking in the next 30 days, % of circulating | supply | – | > 2% (8%) | sell side only; the unlock file (ENA) or DefiLlama's curve |
| BTC price / its 200-day average | market | < 1.0 (0.8) | > 1.8 (2.4) | the BTC Mayer zones: altcoins bottom and top with BTC |
| Volume zone the price sits in | volume zones | inside resistance = +1 | inside support = −1 | the flipped zone signal (record at 7-30 days: t 3.5-5.6) |
| Twenty-signal final score, 7 days | volume zones | the score itself | the score itself | the Signals tab, walk-forward weights |

**Sell signal, two levels** (the BTC board's shape; altcoins have no halving clock, so the top-season check is dropped): *take profit* when the
score is ≤ −0.2; *sell, trend break* when a valuation gauge was fully in its sell zone in the last 4 months AND the price is below its 20-week
average AND the score is not a buy. **Action words**: BUY at ≥ +0.5, SELL at either sell level, else HOLD. Information only.

The tab also shows why the score is what it is (what pushes it each way, what moved since the day before, the distance to the next level),
the price levels that would move the price-based gauges into their zones, and the coin's median move over the next 30 / 90 / 180 days after
each zone, over the coin's own Hyperliquid history.

### Caveats

- Every zone is hand-set. The BTC board's are the commonly published ones checked over four cycles; here a coin has one to three years of history
  and most zones are the BTC ones widened, so the record-by-zone table is the only check on them. Read it before the label.
- Fees and TVL come from the fundamentals fill (400 days) and market cap from CoinGecko (365 days), so the valuation multiples exist for about a
  year and their "own median" is short. Coins without fees or TVL (memecoins have none; they have no board) simply lose those gauges.
- The volume-zone gauges were flipped on 30 Oct 2026 on the same data they are now scored on (see the signals section).

## The volume-zone rule (`app/topics/_volume_zones.py`)

- **Big-volume day**: USD volume at least 3x the median of the previous 60 closed days (nothing is known early; the first 20 days of a
  market have no median and are never big days). An up close makes it a **buy day**, a down close a **sell day**.
- **Zone**: the big day's open-to-close range, where most of that volume changed hands. A buy day's zone is **support**, a sell day's
  **resistance**. Live from the next day; it ends when a close goes 1 ATR (14-day) through its far side, or after 180 days.
- **Retest**: the first day price comes back into a live zone from the right side (into support from above, into resistance from below).
- **Where it sits** (the table and "What changed"): inside a support zone or within 3% above it = +1; inside resistance or within 3% below it = -1; else 0.
- **After big days / retests**: the coin's average close-to-close move 7 and 30 days later, buy and sell days apart, next to its average day.

Candles are Hyperliquid's daily perp candles (the whole history of each market, up to 5,000 days; k-prefixed markets quote 1,000 tokens and are
scaled back), so volume is perp volume in dollars, not spot. Coins without a Hyperliquid market show "not on Hyperliquid". Same method as the
trading bot's basket-wide study (trading-system repo, `docs/Alt_Volume_Zones_Study.xlsx`), which is where the rules are judged with costs,
out-of-sample periods and a luck test; this page only describes one coin's own history.

## The signal weighting rule and backtest method (`app/topics/_signals.py`)

Twenty signals, each a daily score from −1 (sell) to +1 (buy) from the coin's own Hyperliquid candles, BTC's, the zones above and (ENA) the
unlock schedule; nothing uses a later day. **Volume zones**: inside a zone (support +1 / resistance −1); near a zone (within 3%, closer =
stronger); first retest of a zone; retest on under 0.7x the usual volume; live support zones within 10% below minus resistance zones within
10% above; a big-volume close through a zone; a failed break (back on the right side within 3 days). **Volume**: a big day today; big buy
minus big sell days over 30 days (3 = full score); an absorption wick (big volume, close in the top quarter after a lower low, or the mirror);
a big day that is coin-specific (BTC had an ordinary day); a big buy day while BTC fell (or sell day while it rose); 20-day volume 30% over
the 60-day with price up (or down). **Price**: trend (close over the 50-day over the 200-day, or the reverse); RSI 14 (30 → +1, 70 → −1);
30-day momentum (±20% = full score); place in the 1-year range (bottom tenth +1, top tenth −1); price 20%+ under its 200-day average (+1) to
50%+ over (−1). **Market**: BTC above or below its 200-day average. **Supply**: 1-7 days after an unlock of 1%+ of circulating (+1), the 3 days
before (−1); coins without a schedule use the 26th-6th month-turn (−1).

Two signs were flipped on 30 Oct 2026 after the first live fit: *inside a zone* now reads +1 in live resistance and −1 in live support, and
*place in the 1-year range* reads +1 near the 1-year high and −1 near the low (the 52-week-high effect). Both had a significantly negative record
at 7 days (rank correlation −0.048 and −0.045, t ≈ −3), so their record since that date is in-sample for the flip and should be read as such.

**Weighting rule.** Each signal is judged on the return over the next 7 days by default; the page also fits and backtests the whole thing
on 14 and 30 days (the "Judge on" switch and the horizon table), with the same trading rule. Its weight is its Spearman rank correlation with that return over
every coin's history pooled, kept only when positive, at least 1.5 standard errors from zero and measured on 100+ active coin-days, and the kept
correlations are scaled to sum to 1 with no single signal above 40% (equal weights if nothing qualifies, and the page says so). Final score = Σ weight × signal, clipped to ±1. Strong buy ≥ +0.5, lean buy ≥ +0.2,
lean sell ≤ −0.2, strong sell ≤ −0.5.

**Backtest method (walk-forward).** Weights are first fitted once 180 days of pooled history exist and re-fitted every 30 days, each time on
rows whose 7-day return was already known; every day's score uses the latest weights fitted before it. Trading it: position at each close from
that day's score (long above +0.2, short below −0.2, else flat), earning the next day's close-to-close move, 0.095% each way on every change,
funding not included; also long-only. A short that loses more than 100% in one day ends the account at zero and the curve stays there. Reported per coin and as medians across coins, next to holding the coin over the same days.

### Caveats

- The signal definitions and thresholds were chosen by hand, and the weights adapt, so the out-of-sample figure is honest about the weights
  but not about the design: a first pass, not a verified edge. The trading bot's repo runs the same study on the Binance basket with its
  luck tests before anything is traded.
- Hyperliquid histories are short (HYPE from late 2024, most others from 2023), so the first fit uses a few hundred coin-days and early weights
  swing. Perp volume, not spot.
- Twenty signals on ten correlated coins: some weights will be noise, and the final signal leans on momentum-type signals in trends. Read the
  per-coin hit rate and the weight list, not just the label.

## The unlock study method (`app/topics/_unlocks.py`)

- **Schedule**: `data/altcoins/unlocks/ENA.csv`, one row per tranche (`date, ena_m, pct_supply, category, kind, confidence, use, source, note`).
  Same-day tranches are summed into one unlock day. Rows with `use=0` are listed for completeness and never counted: the StablecoinX lock-up
  waiver (sales still need the Foundation's consent), the season-3 airdrop (amount unpublished) and the 275M item some trackers show for
  1 Nov 2026. `confidence` is high (two independent sources agree), medium (one source, or an inferred date) or low; the study uses medium and high.
- **% of circulating** = the day's amount against everything unlocked before it: what the market has to absorb relative to what already trades.
  Big = 5% or more (the 5 Mar 2025 cliff, the season-2 airdrop, the 5 Oct 2026 investor acceleration); the monthly team + investor tranches are
  1-5%; the Foundation's 40.6M a month is under 1%.
- **Event study**: close-to-close moves around each unlock day inside the Hyperliquid price history: the week before (close 8 days before to
  the day before), into the day, and 1 / 3 / 7 / 14 days after, against ENA's average move over the same windows on every day.
- **Rules**: enter and exit at daily closes (the dates are known in advance, so entering before an unlock uses nothing unknown); 0.045% fee
  + 0.05% slippage per side, funding not included; one position at a time. Judged before and from 1 Jul 2025 (the halves the trading bot's
  studies use), with a placebo: the share of 300 random date sets of the same size that did as well.
- **Date check**: trackers disagree whether the 2025-26 monthly tranches land on the 2nd or the 5th; the highest-volume day within +-4 days of
  each listed date is shown, so a wrong day stands out.

### Caveats

- About 30 unlock days in two and a half years of prices, ten rule settings: one or two will look good by luck. A rule needs both halves
  positive and a low placebo p before it means anything, and even then it is a hint to watch, not a signal the bot trades.
- The October 2026 acceleration's size was never published by the Foundation (~1.4B before OTC buy-outs); the CSV carries the derived figure
  with medium confidence. Unlocked tokens are not necessarily sold: recipients may hold, sell OTC or hedge with perps before the date.
- Volume zones and unlock markers use perp candles; the other tabs use CoinGecko spot prices, so a close can differ by a few tenths of a percent.

## Where the numbers come from

The candidates' prices, market caps, fees, TVL and the DefiLlama unlock curve come with BTC Cycles' background fill (CoinGecko, DefiLlama;
`data/btc-cycles/README.md`), the projection levels from `data/btc-cycles/scenarios.json`, and the memecoins' prices from the memecoin fill
(CoinGecko; `data/memecoins/README.md`). The Volume zones and ENA unlocks tabs download Hyperliquid's daily candles themselves (one POST per
coin to `api.hyperliquid.xyz/info`, cached for 6 hours, kept as a snapshot). The ENA schedule is hand-entered in `data/altcoins/unlocks/ENA.csv`
from the Binance Launchpool announcement (initial supply), Ethena's tokenomics docs (allocations, vesting start), crypto.news / Bitget /
ChainCatcher (the 5 Mar 2025 cliff), Tokenomist and TradingView / CoinMarketCal calendars (monthly tranches), the Ethena Foundation's 27 Aug 2026
announcement with CoinMarketCap / KuCoin / Bitbase coverage (October 2026 acceleration and StablecoinX waiver) and app.tokenomics.com (the 1 Nov 2026 item).

## Adding an unlock schedule for another coin

One CSV per coin in `data/altcoins/unlocks/<TICKER>.csv` with the ENA file's columns (the amount column is named `<ticker>_m`, in millions).
The Volume zones chart marks the coin's unlock days as soon as the file exists; the ENA unlocks tab is ENA only (`UNLOCK_COIN` in `altcoins.py`).

## Adding a coin

A candidate: add its ticker to `CANDIDATES` in `app/topics/altcoins.py` (it must be a row in `data/btc-cycles/coins.csv`), a tab
function in `VIEWS` in `app/static/topics/altcoins.js`, and its link in `PAGES` in `btc-cycles.js`. A memecoin: a row in `data/memecoins/coins.csv`.
