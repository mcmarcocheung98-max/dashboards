# Memecoins (`/memecoins`)

The largest memecoins as one basket, measured against BTC: prices and momentum per coin, and a mechanical "meme season" reading.

## What it shows

| Tab | Cards | Series |
|---|---|---|
| Basket | Headline figures | Basket market cap, coins in, how many beat BTC over 90 days, the strongest against BTC |
| | The basket (sortable) | Per coin: price, 24h, 7-day, 30-day and 1-year change, distance from the 1-year high, market cap and share of the basket, RSI 14 in USD and against BTC, 90 days against BTC, beta to BTC |
| | Rebased | Every coin and BTC rebased to 100 a year ago (log) |
| | Sparklines | 90 days per coin |
| Meme season | Reading | Meme season / in between / out of season, with the figures behind it |
| | Basket ÷ BTC | Total basket market cap ÷ BTC market cap (log): rising = memes beating BTC |
| | RSI, equal weight, market caps | RSI 14 of basket ÷ BTC; an equal-weight basket against BTC; both market caps |
| | Memecoins' share of crypto | CoinGecko's "Meme" category market cap ÷ total crypto market cap, logged daily from the first deploy |

## The season rule

Meme season: the basket ÷ BTC is up 25% or more over 90 days, or its RSI 14 is 70 or more. Out of season: it is down 25% or more and its
RSI is under 50. In between otherwise. `HOT` and `COLD` in `app/topics/memecoins.py`. A mechanical reading, not a forecast.

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Each coin's daily price and market cap, 365 days | [CoinGecko](https://www.coingecko.com/en/categories/meme-token) `coins/{id}/market_chart` | Daily | Automated, paced with the BTC Cycles fill (one CoinGecko call at a time) |
| BTC daily price and market cap | CoinGecko `coins/bitcoin/market_chart` (shared with BTC Cycles) | Daily | Automated |
| Meme sector and total crypto market cap | CoinGecko `coins/categories` (`meme-token`) and `global` | Logged once a day | Automated; no free history, so the log starts at first deploy |
| The basket | `coins.csv` | As edited | Hand-maintained. `verify` = CoinGecko id copied from memory; confirm with `pytest -m network tests/test_memecoins.py` and clear the mark |
