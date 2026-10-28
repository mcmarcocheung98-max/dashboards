# Pokémon Card Market (`/pokemon-cards`)

**The question:** is the Pokémon card market overheating or cooling?

Ten tabs. Data at `/api/pokemon-cards/<heat|prices|overheat|cooldown|grading|psa9|pikachu|charizard|psyduck|regions>`. `/api/pokemon-cards/basket` lists the basket and the product addresses the server found for each item. `/api/pokemon-cards/layout` (not a tab) shows what the server gets back from every source, PriceCharting, pokemontcg.io, TCGplayer, Cardmarket, Yuyutei, Snkrdunk, eBay, Google Trends, PSA and GemRate included (status, final address, the first 600 characters, and the start of PriceCharting's `chart_data`). Read it with Actions → show-json.

Not investment advice.

## Sources and cadence

| Tab | What | Source | Automated? | Cadence |
|---|---|---|---|---|
| Prices, signals, grading | Monthly price history per card and product: ungraded (`used`) and PSA 10 (`manualonly`) | PriceCharting product page, `VGPC.chart_data` (cents, one point a month) | yes, from the path in `basket.csv`; if that page has no chart, the first PriceCharting search result | every 3 days per page, 8 s apart |
| Prices (fallback), overheat, regions | Market price and units sold per card, one year of buckets per condition | TCGplayer `infinite-api.tcgplayer.com/price/history/<id>/detailed?range=annual` | yes; product id from `basket.csv`, else TCGdex, else the redirect of `prices.pokemontcg.io/tcgplayer/<id>` | daily, 8 s apart |
| Cooldown | Current listings and sellers per card | TCGplayer `mp-search-api.tcgplayer.com/v2/product/<id>/details` (`listings`, `sellers`, `marketPrice`) | yes, logged once a day | daily |
| Regions, daily chart | TCGplayer market (USD), TCGplayer product id, and Cardmarket trend and 1/7/30-day averages (EUR) per card | TCGdex `api.tcgdex.net/v2/en/cards/<id>` (`pricing.tcgplayer`, `pricing.cardmarket`); pokemontcg.io `/v2/cards?q=(id:… OR id:…)` only when TCGdex misses most cards | yes, logged once a day | daily, one card per request, 8 s apart |
| Regions | USD to EUR, GBP, JPY, HKD | Frankfurter (ECB reference rates); open.er-api.com if it fails | yes | daily |
| Overheat, cooldown | Google Trends, US, "pokemon cards" (0–100) | trends.google.com | hand-entered: `trends.csv` (`date,value,source,note`) | monthly |
| Overheat, grading | PSA Pokémon cards graded per month; PSA turnaround days | GemRate, PSA | hand-entered: `psa.csv` (`date,series,value,source,note`; a series name containing "graded" feeds the signal) | monthly |
| Grading | PSA / CGC population of key cards | PSA and CGC population reports | hand-entered: `pop.csv` (`date,series,value,source,note`, series = card and grade) | monthly |
| Overheat, cooldown | Sell-outs, purchase limits, scalping; reprints and restocks | news and company posts | hand-entered: `events.csv` (`date,kind,region,event,source,note`; kind is `sellout`, `scalping`, `limit`, `reprint` or `restock`) | as they happen |
| Overheat | New-set booster box premium for sets not in the basket | PriceCharting, TCGplayer | hand-entered: `newset.csv` (`date` = release, `series` = set, `value` = box price / MSRP 2–10 weeks after release) | per set |
| US / UK / HK | Japanese set prices (JPY) | Yuyutei, Snkrdunk | hand-entered: `japan.csv` (`date,series,value,source,note`) until a feed answers the server | monthly |
| US / UK / HK | Hong Kong shop notes | shop pages and posts | hand-entered: `hk.csv` (`date,shop,area,note,source`) | as noted |

Every download happens in the background job `fill()` (every 6 hours, like `btc_cycles`): one site request at a time, `PACE` = 8 seconds apart, and a page whose disk snapshot is younger than its `MAX_AGE` is not downloaded again. Pages only read what the fill already has, so a slow or blocked shop never holds a page up. The fill also appends today's prices and listings to `daily.csv` on the snapshot volume (`/app/snapshots/pokemon-cards/`), so day-by-day history builds from launch; `resolved.json` next to it keeps the PriceCharting page and TCGplayer id found for each item.

eBay sold listings, Cardmarket's own pages, Google Trends, PSA and Snkrdunk usually refuse cloud servers; `/layout` checks them from Railway, and the hand-entered files stand in. FRED and Yahoo are not used (they time out or return 429 from Railway).

**Checked on the server** (`/api/pokemon-cards/layout` from Railway, 2026-10-26):

| Source | Answer | Used? |
|---|---|---|
| PriceCharting product page | 200 with `VGPC.chart_data` (monthly, cents; keys `used`, `cib`, `new`, `graded`, `boxonly`, `manualonly`) **only with an HTML `Accept` header**: the shared UA's `text/csv,application/json` gets 400 `{"error":"unauthorized request"}` | yes (`PC_HEADERS`) |
| PriceCharting search | 200 (HTML with `/game/...` links; JSON when asked for JSON) | fallback for a wrong path |
| TCGplayer price history, product details | 200 JSON as parsed (`result[].buckets[]`; `listings`, `sellers`, `marketPrice`) | yes |
| prices.pokemontcg.io TCGplayer link | 200 after redirects to `tcgplayer.com/product/<id>` | fallback for TCGplayer ids |
| TCGdex | 200 JSON with `pricing.cardmarket` and `pricing.tcgplayer` | yes, primary for current prices |
| pokemontcg.io API | 500 / 502 (Cloudflare: origin bad gateway), batch and single card | only when TCGdex misses |
| Frankfurter, open.er-api.com | 200 | yes |
| Cardmarket, PSA, GemRate | 403 Cloudflare challenge | no: hand-entered / via TCGdex |
| eBay sold listings | 403 | no |
| Google Trends | 429 | no: hand-entered |
| Yuyutei | 200, but no prices found in the HTML by a simple yen pattern | not yet: hand-entered `japan.csv` |
| Snkrdunk | 200 for the English home page; no price feed found | no |
| tcgcsv.com | 200 (TCGplayer groups) | not used; a possible source for sealed TCGplayer prices |

First live reading after the fill (2026-10-26): heat score −0.17 (neutral), down from +0.84 in March 2026; 9 of 12 signals scored. live-check drew all six tabs from live data. `/api/health` lists only sources downloaded since the last restart, so right after a redeploy that finds fresh snapshots on the volume it can show 0 sources for this dashboard: that is not a failure.

## Price paired with volume

Volume comes from two places. **TCGplayer units sold** per week (raw copies, one year, from the price-history API) is drawn as bars under the price line on the Prices tab (whole basket) and on every card of the character tabs. **PriceCharting's stated sales per month** for each grade (the `volume: N sales per day|week|month|year` row under its price table, which counts eBay, TCGplayer, Fanatics, Goldin and other sold listings) is shown per card and per grade, and logged once a day (`vol_raw`, `vol_9`, `vol_10` in `daily.csv`) so a volume history builds up from launch.

## Character tabs: Pikachu, Charizard, Psyduck (`characters.csv`)

Columns: `date` (release), `key`, `character` (`pikachu`, `charizard` or `psyduck`), `name`, `set`, `pricecharting`, `ptcg_id`, `tcgdex_id`, `tcgplayer_id`, `source`, `note`. Five Pikachu cards (Base Set, Jungle, Vivid Voltage VMAX rainbow, 151 illustration rare, Surging Sparks SIR), seven Charizard (Base Set, Team Rocket Dark, Neo Destiny Shining, Skyridge, Brilliant Stars alt art, Obsidian Flames and 151 SIRs) and three Psyduck (Fossil unlimited and 1st Edition, 151 illustration rare). All ids and paths are from memory and marked `verify`; a wrong PriceCharting path falls back to PriceCharting search (see `/api/pokemon-cards/basket` → `resolved`). Add a row to add a card. These cards are not in the heat-score basket.

Each tab shows a chain-linked raw index of its cards with the summed TCGplayer units per week, and per card: raw, Grade 9 and PSA 10 prices (monthly, log scale), sales per month per grade, the last PSA 9 and PSA 10 sale, raw TCGplayer price with units per week, and which grade is the better market to trade.

## PSA 9 vs PSA 10 (`psa9` tab)

Every card with graded prices (the basket's cards and the character cards, each PriceCharting page once):

| Measure | From |
|---|---|
| Sales per month per grade | PriceCharting's volume row; when missing, the rate implied by its listed sold sales (count over the days they span) |
| Price noise | median absolute log distance of each sold price in the last 90 days from their median: a stand-in for the bid-ask spread |
| Volatility | standard deviation of monthly log changes over the last 2 years, annualised |
| 12-month return | PriceCharting's monthly series per grade |
| PSA 9 sales per PSA 10 sale, PSA 10 / PSA 9 price | the two above |

**Which grade to trade:** PSA 10 when it sells at least twice a week (8+ a month); PSA 9 when it sells at least twice as often as PSA 10 and at least weekly (4+ a month); otherwise "thin" (neither sells weekly). The tab's answer counts the cards each way and gives the median card's turnover ratio and price ratio. PriceCharting's "Grade 9" is any grader's 9 (mostly PSA), and its volumes are its own estimates from the listings it tracks. Server check (2026-10-28): Base Set Charizard showed Grade 9 at 1 sale a day and PSA 10 at 1 a month. Not investment advice.

## The basket (`basket.csv`)

30 bellwethers: 8 vintage WotC holos (Base Set Charizard, Blastoise, Venusaur, Mewtwo; Fossil Gengar; Team Rocket Dark Charizard; Neo Genesis Lugia; Neo Destiny Shining Charizard), 11 modern chase and alt-art cards (Evolving Skies Umbreon and Rayquaza VMAX, Fusion Strike Gengar VMAX, Brilliant Stars Charizard V, Lost Origin Giratina V, Obsidian Flames and 151 Charizard ex, 151 Mew ex, Twilight Masquerade Greninja ex, Surging Sparks Pikachu ex, Prismatic Evolutions Umbreon ex) and 11 sealed products (booster boxes and elite trainer boxes from Base Set to Mega Evolution, each with its MSRP).

Columns: `date` (release), `key`, `name`, `set`, `segment` (`vintage`, `modern`, `sealed`), `kind`, `msrp_usd` (sealed), `pricecharting` (path after `/game/`), `pc_field` (`used` = ungraded or the sealed price), `ptcg_id` (pokemontcg.io id, also the TCGdex id unless `tcgdex_id` says otherwise: Scarlet & Violet sets are `sv03.5-199` there), `tcgdex_id`, `variant` (TCGplayer price key, blank = first of holofoil, unlimited, normal, 1st edition), `tcgplayer_id` (blank = found automatically), `source`, `note`. To add an item, add a row; to drop one, delete it: the indices are chain-linked, so neither moves them.

## The heat score

1. Each signal is a series (monthly unless stated). Its **z-score** at each date is (value − mean) / standard deviation of its own values in the 3 years up to that date, needing at least a year of points (12 monthly, 52 weekly, but 26 for TCGplayer units sold, whose history is one year long; 8 for the hand-entered search and PSA series, which may be quarterly), clipped to ±3. The new-set premium is scored against earlier sets (at least 4, over up to 9 years, because sets come a few a year).
2. **Heat** = z × direction: +1 for signals where high means hot, −1 for reprints and the supply overhang, where high means cooling.
3. The **score** is the mean heat of the signals that have a current reading (monthly signals read within 120 days, weekly 45, daily 10, new-set 400), needing at least 3, clipped to **−2 … +2**. The month-by-month line does the same each month, carrying a signal forward up to 3 months.
4. Words: +1 or more **overheated**, +0.5 running hot, −0.5 to +0.5 neutral, −0.5 cooling, −1 or less **cold**.

| Signal | Built from | Direction |
|---|---|---|
| 30-day momentum | whole-basket index, 1-month change (the data are monthly) | heats |
| 90-day momentum | 3-month change | heats |
| Breadth | share of items above their 7-month (≈200-day) average, needs 3 items | heats |
| Sealed / MSRP | median sealed price / MSRP, products already released, needs 2 | heats |
| New-set premium | booster box price at the first month-end 2–10 weeks after release / MSRP (plus `newset.csv`) | heats |
| PSA 10 premium | median PSA 10 / ungraded price across cards, needs 3 | heats |
| PSA grading volume | `psa.csv` "graded" series, 3-month average | heats |
| Search interest | `trends.csv` | heats |
| TCGplayer units sold | weekly units sold, all basket cards with a TCGplayer id (last, unfinished week dropped) | heats |
| Sell-out and scalping news | `events.csv` rows of kind sellout, scalping or limit in the 90 days to each month end | heats |
| Reprint announcements | `events.csv` rows of kind reprint or restock in the last 90 days | cools |
| Supply overhang | 30-day % change in summed TCGplayer listings minus 30-day % change in units sold (needs 31 days of `daily.csv`) | cools |

The **index** is equal-weight and chain-linked: each month's change is the mean log change of the items priced in both months (single moves capped at ±150 log points), so a card joining or leaving does not jump it. A month with no PriceCharting sale keeps the last price for up to two months. When PriceCharting cannot be read for an item, its monthly series comes from TCGplayer's weekly history instead (one year only).

The **cooldown checklist** (Cooldown tab): 90-day momentum 5+ points below its 6-month peak with a negative last month; breadth down 15+ points in 3 months; sealed / MSRP down more than 0.1x in 3 months; listings growing 10+ points faster than sales over 30 days; PSA 10 / raw down more than 0.5x in 6 months; search down 10+ points in 3 months; at least one reprint or restock announcement in 90 days.

GBP and EUR come from TCGdex's Cardmarket prices; Cardmarket itself refuses the server.

**Where is it hottest** (US / UK / HK tab): the region with the highest momentum. US: 30-day change of the TCGplayer price, basket median (from the daily log once it has 30 days, else TCGplayer's 4-week change). UK/EU: the same for Cardmarket's trend price (until then the 7-day vs 30-day average). Japan: 3-month change of the hand-entered set prices, median. GBP is the EUR price converted at ECB rates.

## READINGS: what +1 and −1 mean

**+1 = heating, −1 = cooling, 0 = neutral.** Each reading comes from the cached tab data only.

| Tab | Key | Reading | +1 | −1 |
|---|---|---|---|---|
| heat | `composite` | heat score | +0.5 or above | −0.5 or below |
| overheat | `mom30`, `mom90`, `breadth`, `sealed_msrp`, `new_set`, `psa_volume`, `search`, `sales`, `news` | each signal's heat (z × direction) | heat ≥ +0.5 | heat ≤ −0.5 |
| cooldown | `reprints`, `overhang` | heat of the two cooling signals (so many reprints read −1) | heat ≥ +0.5 | heat ≤ −0.5 |
| grading | `psa10_ratio` | heat of the PSA 10 premium | heat ≥ +0.5 | heat ≤ −0.5 |
| cooldown | `cooling_signs` | cooling signs met | never | at least half of the known signs met |
| prices | `index_3m` | whole-basket 3-month change | +5% or more | −5% or less |
| prices | `vintage_12m`, `modern_12m`, `sealed_12m` | each basket's 12-month change | +10% or more | −10% or less |
| regions | `mom_us`, `mom_uk`, `mom_japan` | each region's momentum | +3% or more | −3% or less |
| pikachu, charizard, psyduck | `<who>_3m` | that character's raw index, 3-month change | +5% or more | −5% or less |
| pikachu, charizard, psyduck | `<who>_units` | TCGplayer units sold, last 4 weeks | 15% more than the 4 weeks before | 15% fewer |
| psa9 | `psa9_liquidity`, `psa10_premium` | PSA 9 sales per PSA 10 sale; PSA 10 / PSA 9 price (median card) | always 0: liquidity, not heat | always 0 |

## Hand-entered rows: all marked `verify`

**Every hand-entered row was entered from memory and says `verify` in its note.** Check each against its cited page, then fix the value or drop `verify`. Least certain:

- `trends.csv`: quarterly values read off the Google Trends chart from memory; replace with the monthly CSV export (Explore → "pokemon cards", United States, 2004–present → download) and keep adding a row a month;
- `basket.csv`: pokemontcg.io ids and PriceCharting paths (a wrong path falls back to PriceCharting search; check `/api/pokemon-cards/basket` → `resolved`), the 2025 release dates and every MSRP (36 packs × $3.99 for Sword & Shield boxes, × $4.49 for Scarlet & Violet, $49.99 ETBs, Base Set at $3.29 a pack);
- `events.csv`: the March 2021 reprint statement and the June 2023 Japanese 151 dates are approximate;
- `pop.csv`: one row (1st Edition Base Charizard PSA 10 = 121).

Empty and waiting for rows: `psa.csv` (monthly PSA Pokémon cards graded, e.g. from GemRate, and turnaround), `japan.csv`, `hk.csv`, `newset.csv`. Until `psa.csv` has 8 points, the PSA volume signal shows "no data yet" and is left out of the score. `trends.csv` stops in May 2025, so the search signal shows "last reading … days old" and is left out of the score until newer rows are added.

## Requests for shared code

- `app/topics/__init__.py` `CATEGORIES`: add `"pokemon-cards"` to the "Money & markets" slugs. Until then the index lists it under "More" (the brief expected it under "Money & markets", but the category list is shared code).
