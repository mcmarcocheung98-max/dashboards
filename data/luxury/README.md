# Luxury Tracker: watches and bags on the second-hand market (`/luxury`)

**The question:** for each item, what does it cost new today, what does it sell for second-hand, and what return (or loss) would a buyer at retail see after platform fees, over time.

Seven tabs. Data at `/api/luxury/<overview|watches|bags|roi|heat|liquidity|fees>`; `/api/luxury/items` lists the items and the owner's watchlist. Started 7 Nov 2026 from the owner's request: "a luxury brand tracker dashboard, for watches like Rolex and designer bags, study second hand market data and roi on items", with three product links (Celine Ava 193952BZJ.04LU, Saint Laurent Le 5 à 7 6572282R20W1000, Louis Vuitton Alma BB M46990).

**Not investment advice.** The page gives no buy or sell calls; a return shown is what a past buyer would have seen, not a forecast.

## Sources and cadence

| Tab | What | Source | Automated? | Cadence |
|---|---|---|---|---|
| all | The items: eight Rolex steel-sports references (and the gold Day-Date as the precious-metal contrast), the owner's three bags, and two reference bags with long resale records (Hermès Birkin 25 Togo, Chanel Classic Flap medium caviar) | `items.csv` (`date` = launch, `id`, `brand`, `model`, `reference`, `category` watch/bag, `currency`, `source` = brand page, `note`) | hand-entered | as items are added |
| Overview, Watches, Bags, ROI | Official list prices as they changed | brand sites and the price-list articles that record each change (Watchfinder, Chrono24 magazine, WatchPro; PurseBop, Handbagholic, PurseBlog, Sotheby's) | hand-entered: `retail.csv` (`date,item,price,currency,source,note`) | at each price change (Rolex: January and sometimes mid-year; Chanel and Hermès: yearly; Louis Vuitton: several times a year) |
| Overview, Watches, Bags, ROI, Heat | Resale asking and sold prices | Chrono24, WatchCharts, Bob's Watches, Watchfinder, Subdial; Vestiaire Collective, Fashionphile, Rebag, The RealReal, Sotheby's, Bonhams, Bagista, StockX, eBay, and the articles that quote them | hand-entered: `resale.csv` (`date,item,condition,price,currency,platform,kind,source,note`; `condition` new/unworn, very good, good; `kind` asking or sold) | at least yearly per item, monthly where a figure is published |
| Heat | Public resale indices' headline figures | Chrono24 ChronoPulse, WatchCharts, Subdial, Bob's Watches / Morgan Stanley, Rebag Clair, The RealReal, Knight Frank Luxury Investment Index, Bernstein's auction tracker | hand-entered: `indices.csv` (`date,series,category,value,unit,source,note`; `unit` level, pct for a published 12-month change, or pts for a premium in percentage points) | as published |
| Fees, ROI | Platform fee schedules | each platform's own fee page | hand-entered: `fees.csv` (`date,platform,kind,seller_pct,seller_text,buyer_pct,buyer_text,authentication,payout_days,region,source,note`) | when a schedule changes |
| ROI, all tabs (FX) | US CPI, UK CPI, USD / CHF / EUR to GBP, the S&P 500 | ECB daily reference rates (`data-api.ecb.europa.eu`, USD/GBP/CHF per EUR) for FX first; FRED (`CPIAUCSL`, `GBRCPIALLMINMEI`, `DEXUSUK`, `DEXSZUS`, `DEXUSEU`, `SP500`); ONS `D7BT` for UK CPI when it answers (FRED's copy of the OECD series stops in March 2025); Nasdaq's index quote for the S&P 500 when FRED fails | yes, but **never during a page view**: `fill_context` (BACKGROUND, at most once a day, a marker on the volume) downloads them; a view reads memory, then the snapshot, then the committed seed in `data/luxury/fred/` (cut to monthly points from 2015, labelled "copy to <date>"); a FRED failure is marked handled on `/api/health` while the seed serves | daily, in the background |
| Liquidity | Attention: monthly pageviews of each item's English Wikipedia article since July 2015 (a demand proxy) | Wikimedia REST API per-article pageviews, monthly granularity, users, all access (the `wiki` column of `items.csv` names the article; the same parser and bot header as the Trends dashboard) | yes, by `fill_context` in the background (never during a view; a snapshot per article; an article never fetched reads "downloading" and starts the fill) | daily |
| Liquidity | Auction results: one row per lot at Phillips, Christie's, Sotheby's, Bonhams | the houses' public results pages and the write-ups that quote them | hand-entered: `auctions.csv` (`date,house,sale,lot,item,price,currency,basis,est_low,est_high,sold,source,note`; `basis` hammer or with premium; a lot with no price is bought in) | after each sale |
| Liquidity | Sell-through per sale (lots sold / offered) | the houses' sale results | hand-entered: `auction_sales.csv` (`date,house,sale,category,offered,sold,total,currency,source,note`) | after each sale |
| Liquidity | eBay UK active listings per item: count, median and lowest asking price (GBP), one snapshot a day | eBay Browse API `item_summary/search` (marketplace EBAY_GB, categories Wristwatches 31387 and Women's Bags & Handbags 169291; the `ebay` column of `items.csv` is the query), client-credentials token from `EBAY_APP_ID` + `EBAY_CERT_ID` (free developer key, set on Railway) | yes: `luxury_ebay.fill` is the dashboard's BACKGROUND job, one search per item per day, appended to `SNAPSHOT_DIR/luxury/ebay_daily.csv` on the volume (like nba-odds' state) | daily, from the day the keys are set |
| Liquidity | The weekly log: Chrono24 listing count per reference, StockX last sale, highest bid and lowest ask per bag, WatchCharts median days to sell, Fashionphile sold counts where visible, Watchfinder stock | the platforms' public pages, read by hand (nothing scraped) | hand-entered: `liquidity.csv` (`date,item,platform,metric,value,currency,source,note`; `source` is the URL; metrics `chrono24_listings`, `chrono24_price`, `stockx_last_sale`, `stockx_bid`, `stockx_ask`, `fashionphile_sold_count`, `fashionphile_listings`, `watchcharts_days_to_sell`, `watchcharts_listings`, `watchfinder_stock`) | weekly: the dev agent's weekly step appends a row per reading |
| Overview | Whether the brand site has the item in stock (and in what form it is sold) | the brand's product page, read by hand on the date shown (the brand sites refuse servers; Rolex sells only through retailers, Hermès and Chanel only in boutiques) | hand-entered: `stock.csv` (`date,item,channel,status,quantity,source,note`; `channel` retail; the newest row per item shows) | weekly, with the log |
| Overview | Each item's photo | the lead image of the item's Wikipedia article (free licence) through the page-summary API, credited and linked to the article; an `image` URL in `items.csv` overrides it (for the exact reference) | yes, by `fill_context` in the background, snapshotted (a view shows no photo until the first fill); `image` hand-entered | daily |
| Overview | Links to the retail and resale pages | `items.csv`: `source` is the brand page, `resale_url` the public resale page (Chrono24's reference page for watches; a Vestiaire or Fashionphile search for bags) | hand-entered | as items are added |
| – | `watchlist.csv` | the owner's additions, same shape as `items.csv`; shown under `/api/luxury/items`, moved to `items.csv` to join a basket | hand-entered | – |

None of the brand sites or resale platforms has a free API, and most refuse servers or forbid scraping in their terms, so nothing is scraped: every price is a dated, cited row. The FRED series are in `PROBE_URLS` (`/api/probe`) so the daily check sees from the server whether they answer. FRED times out from Railway (Nov 2026), so a page view never waits for it: the committed copies in `data/luxury/fred/` (one file per series, monthly from 2015; refresh them now and then with the snippet in Upkeep) serve until the background job gets a download, the ROI tab labels them "copy to <date>", and `/api/health` shows the FRED failures as handled.

## Method: how premiums, baskets, fees and ROI are calculated

**Currency.** Everything is shown in GBP. A row in USD, CHF or EUR is converted at the mean FRED fixing of its month (`DEXUSUK` is USD per GBP; `DEXSZUS` CHF per USD; `DEXUSEU` USD per EUR). If FRED has never answered, fixed approximate rates (USD 0.78, CHF 0.88, EUR 0.86 per unit) are used and the page says so. Hermès does not publish a UK list price, so the Birkin's retail rows are the EU list in euros.

**Item cards** (Overview): the photo is the Wikipedia article's lead image unless `items.csv` has an `image` link (the article's image is the model, not this exact reference, and says so; the retail page link shows the exact one). "Brand site" is the newest `stock.csv` row for the item: a status read by hand on the brand's page on that date ("in stock", "out of stock online", "retailer only (waitlist)", "boutique only", "discontinued", "unknown" when the page could not be read). "Second-hand stock" is the listing count on Chrono24 (and WatchCharts, Fashionphile, Watchfinder where logged) from the weekly log, and on eBay UK from the daily feed once its keys are set, each with its date and link.

**Retail** is a step: the list price in force on any date is the last `retail.csv` row on or before it. A row dated the day it was seen (not the day it changed) is marked `verify` and says so.

**Premium to retail** at a resale point = resale price ÷ the list price in force that day − 1. On one date a sold point stands before an asking one. An item's **latest resale** is its newest point; if that point is an asking price and a sold point exists within 90 days of it, the sold point stands instead ("sold if known, else asking"). **1-year and 3-year change** compare the latest point with the point nearest to one (three) years earlier, within 180 days; otherwise blank.

**Baskets**, month by month from December 2019: for every item, its last resale point within 550 days (18 months: hand-entered points come about yearly) against the list price then in force. The **Rolex basket premium** is the median across references (needs 4 of 8); the **bag basket ratio** is the median resale ÷ retail (needs 3 of 5). The **resale index** is equal-weight and chain-linked as in the Pokémon dashboard: each month's change is the mean log change of the items priced in both months (single moves capped at ±150 log points), so an item joining or leaving does not jump it. **Share above retail** is the share of priced items whose premium is positive.

**Retail price inflation** (Bags tab): per brand per year, the list price at the end of the year against the end of the year before, mean across the brand's items here (a partial current year runs to today). The **12-month rise** (and the `retail_rise` signal, across all brands including Rolex) is kept honest: the latest list price against a list price dated 9 to 15 months earlier (the row nearest to a year ago), mean across the brand's items that have one; a brand with no row in that window gets no 12-month figure, the card says "no price a year ago", and it cannot cross the signal. The longer rise stays visible as "since <date>": the latest price against the price in force a year ago, dated by the row that set it (so a list with a gap, like the Le 5 à 7's between Nov 2021 and Aug 2026, shows its whole rise with its real span).

**Fees.** `seller_pct` is the blended seller rate on a £5,000–£10,000 item (the tiers are in `seller_text`); buyout houses have no fee, their margin sits inside the offer. The ROI tab's default platform is Chrono24 for watches and Vestiaire Collective for bags.

**ROI.** For a buyer at retail on a date: bought at the list price then in force; sold today at the item's latest resale point; fee = gross × the platform's seller rate; net = gross − fee; return = net ÷ buy price − 1; annualised = (1 + return)^(365.25 ÷ days) − 1 (blank under 30 days or on a total loss). The S&P 500 is its price change over the same dates (dividends left out); UK CPI the index change; the real return = (1 + return) ÷ (1 + CPI change) − 1. The table uses 1 January of each year from 2020 (or launch, if later); the calculator takes any item, date, price and platform, computed in the browser, nothing stored. Shipping, insurance, servicing, VAT and duty are not deducted.

**Attention** (Liquidity tab): monthly views of each item's English Wikipedia article (`wiki` in `items.csv`; two GMT-Master II references share one article, the Alma BB has none so Louis Vuitton's article stands for it, the Le 5 à 7 and the Ava use their brands' articles). A `wiki` cell may list several titles separated by `|` in order of preference: the first with at least 24 months of pageviews is used and the stubs before it are reported, not errors (the "Rolex Explorer" and "Rolex Oyster Perpetual" articles are recent stubs, so the Explorer falls back to the Explorer II family article and the Oyster Perpetual to the Rolex brand article, both marked "fallback" on the page). Per article: the last full month, its change on a year, and a **12-month z** (the last full month against the mean and standard deviation of the 12 months before it, clipped to ±3). Per basket: each article's views as a share of its own whole-history mean, averaged across the basket's articles, ×100, and the same 12-month z on that line. People look a watch or bag up before they buy or sell, so this is a demand proxy, not a price or a sale count.

**Auction results** (Liquidity tab): each lot's price (hammer, or with the buyer's premium where that is what the house publishes; `basis` says which) in GBP at the month's rate against the midpoint of its pre-sale estimate, minus one; sold lots only in the series, with a median per half-year per category. **Sell-through** per sale = lots sold ÷ lots offered from `auction_sales.csv` (the house's own count); a sale with no such row but three or more lots entered gets a sample rate marked "from lots entered". The category series carries each sale's rate to its month end (mean when two sales fall in a month). Near 100% means a bidder for everything; under 70% means lots bought in. A liquidity measure, not a price.

**eBay listings** (Liquidity tab): once a day per item, the Browse API's count of active fixed-price GBP listings on eBay UK matching the item's `ebay` query in its category, with the median and lowest asking price of the first 200 by price. Each day is one line in `ebay_daily.csv` on the data volume, so history accrues from the day the keys are set; the tab sums the counts per basket and takes the median of medians. Until `EBAY_APP_ID` and `EBAY_CERT_ID` are set the card says "not set up yet (EBAY_APP_ID)", as Ask Claude does for its key, and the job does nothing. **Sold prices** are not read: eBay's Marketplace Insights API (`buy/marketplace_insights`, 90 days of sold items) is restricted to approved applications; the owner can apply through the eBay developer programme if wanted, and the sell-through (sold ÷ active) would then join this tab. A rising listing count against a falling premium is the "sellers stuck" sign the liquidity signal watches.

**The weekly log** (Liquidity tab): one row per reading in `liquidity.csv`; money metrics are converted to GBP at the month's rate. The **StockX bid-ask spread** per bag = lowest ask ÷ highest bid − 1, needing both within 14 days (a tight spread is a liquid market; a wide one, bids far below asks, is sellers waiting). The **Chrono24 listing count** is summed over the references logged, week by week, as a supply series; **days to sell** (WatchCharts' median days on market) is the most direct liquidity measure here. Readings dated the day they were seen are marked verify when the page's own date is unknown.

## The heat score

One score for watches and one for bags, like the Pokémon dashboard's, on −2 (cold) … +2 (overheated). Four components, each clipped to ±2, and the score is their mean (at least two needed), month by month, each carried forward up to 3 months:

| Component | Built from | Scale |
|---|---|---|
| Premium vs its own history | the basket premium as a z-score against its last 3 years (needs 12 months), clipped to ±3 | the z itself, clipped to ±2 |
| 1-year change in resale prices | the resale index, change on a year | ±15% = ±1 |
| Share of items above retail | share of the basket's items selling above list | (share − 0.5) × 4: all above = +2, none = −2 |
| Public indices' direction | each public index for the category scored on its own change on a year (the nearest earlier point to a year before, within 120 days), then the mean across indices; a `pct` series is chained into a level first; a `pts` series (a premium quoted in percentage points) scores its difference | ±10% = ±1 (levels); ±5 points = ±1 (`pts`) |

Words: +1 or more **overheated**, +0.5 running hot, −0.5 to +0.5 neutral, −0.5 cooling, −1 or less **cold**. The overview's "where the market is" line is each category's words plus whether its basket trades above, around or below retail. The luxury-wide score (the `heat` signal) is the mean of the two.

## The liquidity score

One score per market on −2 (stuck) … +2 (tight), like the heat score: five components each clipped to ±2, the score their mean (at least two present).

| Component | Built from | Scale |
|---|---|---|
| Supply | the basket's listing count against its own history as a z-score, sign flipped (more listings than usual = looser): eBay UK daily counts once 60 days exist, else the Chrono24 weekly total once 8 weeks exist | −z, clipped |
| Bid-ask spread | median StockX lowest ask ÷ highest bid − 1 across the bags with both (bags only) | 0% = +2, 10% = +1, 20% = 0, 30% = −1 |
| Auction sell-through | the latest sale's lots sold ÷ offered | 95% = +1, 85% = 0, 75% = −1 |
| Days to sell | WatchCharts' median days on market across the references logged in the last 60 days (watches) | 20 days = +1, 30 = 0, 40 = −1 |
| Attention | the basket's Wikipedia 12-month z | the z, clipped |

Words: +1 **tight** (few listings, narrow spreads, everything sells), +0.5 liquid, −0.5 to +0.5 normal, −0.5 loosening, −1 **stuck** (listings pile up, spreads widen, lots bought in). The luxury-wide score (the `liquidity` signal's value) is the mean of the two.

## READINGS and signals: what +1 and −1 mean

**+1 = heating, −1 = cooling, 0 = neutral**, from cached tab data only.

| Tab | Key | Reading | +1 | −1 |
|---|---|---|---|---|
| overview | `rolex_premium` | Rolex basket premium to retail, % | above +2% | below −2% |
| overview | `bags_ratio` | bag basket resale ÷ retail | 1.0 or more | under 0.7 |
| heat | `heat_watch`, `heat_bag` | each heat score | +0.5 or above | −0.5 or below |
| liquidity | `attention_watch`, `attention_bag` | each basket's Wikipedia attention, 12-month z | +1 sd or above | −1 sd or below |
| liquidity | `sell_through_watch`, `sell_through_bag` | auction sell-through, latest sale (%) | 90% or more | under 70% |
| liquidity | `ebay_listings_watch`, `ebay_listings_bag` | active eBay UK listings per basket (once two days of snapshots exist) | never (a count) | never |
| liquidity | `liquidity_watch`, `liquidity_bag` | each liquidity score | +0.5 or above | −0.5 or below |
| liquidity | `stockx_spread` | bags: StockX bid-ask spread, median of the bags with both (%) | under 10% | over 30% |

Signals (`data/signals/watchlist.json`, approved by the owner on 7 Nov 2026): `rolex_premium` (watch: below 0% or above +50%), `rolex_1y` (a 15% move either way), `bags_ratio` (below 0.5 or above 1.0), `retail_rise` (any brand above 10% in 12 months), `heat` (above +1.5 or below −1), and the sixth, `liquidity` (approved 7 Nov 2026 with the free data route): listings up 50% on a year with the premium falling (sellers stuck), or auction sell-through below 70%; its value is the luxury-wide liquidity score.

## Caveats

- **Sparse points.** A premium is one hand-entered point against the list price that day, not a daily market; a month with no point within 18 months drops the item from the basket, so the lines step and gap.
- **Asking vs sold.** Asking prices run above sold prices, by 10–20% on watches and more on bags; the cards say which kind the latest point is.
- **Condition, box and papers.** A full-set unworn watch and a worn one without papers can differ by 15–25%; bag conditions by more. Points carry a condition column; the baskets mix them.
- **Which price for a bag with no UK list.** The Birkin's retail is the EU list in euros converted at the month's rate; Chanel and Hermès lists differ by country by 10–20%, and the UK often sits between the EU and the US.
- **VAT and import duty.** Goods sent into Great Britain from abroad attract import VAT at 20% on the full value and, above £135 a consignment, customs duty at the tariff rate (leather bags about 2%, EU-origin 0%; mechanical watches a small per-item rate), second-hand from a private seller included ([gov.uk](https://www.gov.uk/goods-sent-from-abroad/tax-and-duty)). A US-platform price in GBP here is before any of that.
- **Authentication and fees.** The ROI deducts the seller's commission only; buyer-side fees, shipping, insurance, servicing and a buyout house's margin are left out, so a buyout offer will be below the "net" shown.
- **Aggregated series.** A platform's yearly average across sizes and ages (SACLÀB's Chanel series) is kept in `indices.csv`, not as a resale point; a derived resale row (a published ratio times the list price) says so in its note.
- **Predecessor references.** The Daytona 126500LN's rows before March 2023 are the 116500LN it replaced; the Alma BB's rows before 2024 are the earlier code M53152 of the same bag.

## Hand-entered rows marked `verify`

A row whose note contains `verify` was entered from an article or a search excerpt, not confirmed on the cited page (in the session that built this, the brand sites and platforms were not reachable from the server, so every fee row and many price rows are marked). Check each against its cited page, then fix the value or drop `verify`. The overview's top card counts them. Least certain: the day a current list price took effect (rows dated the day they were seen), undated resale listings (dated the day seen, "date approximate"), the Hermès UK list (conflicting reports), the Saint Laurent UK list between 2022 and 2025 (no rows found), and the Rebag 2023 brand figures implied from the 2024 report.

## Upkeep

- A new list price: one row in `retail.csv` dated the day it took effect.
- A new resale point: one row in `resale.csv`; prefer sold prices with a URL that shows the sale, and note the condition.
- A new item: a row in `watchlist.csv` (shown under `/api/luxury/items`), moved to `items.csv` once it has retail and resale rows, so it joins the basket and the tests.
- Fee changes: edit the platform's row in `fees.csv` and date it.
- The FRED seeds (`fred/*.csv`): from a machine FRED answers, download `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>` for each ID in `FRED_IDS`, keep rows from 2015 (FX as monthly means, the S&P 500 as the last close of each month plus the latest 40 days), and commit; the first two columns are `observation_date,<ID>`.
