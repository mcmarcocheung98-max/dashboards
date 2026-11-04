# China vs US Tech (`/china-us-tech`)

**The question:** who leads in each layer of the tech stack, and where is the gap closing?

Code: `app/topics/china_us_tech.py` (data), `app/static/topics/china-us-tech.js` (cards), `tests/test_china_us_tech.py` (fixtures and `smoke_patch()`).
Data for each tab: `/api/china-us-tech/<overview|models|research|ev|chips|markets>`. `/api/china-us-tech/layout` (not a tab) shows what the
server gets back from every automated source (status, size, first 300 characters), so you can check reachability from Railway with
Actions > show-json.

## Leans: what +1 and -1 mean

**+1 means China gaining relative to the US; -1 means the US gaining; 0 means the reading stayed inside its band.** A lean describes the
*direction of the latest move*, not who leads: the US can lead a layer while its reading leans +1 because the gap narrowed.

| Tab | Reading (`key`) | Value | +1 when | -1 when |
|---|---|---|---|---|
| AI models | `models_share` | China's share of US + China notable models, last full year (%) | share is 3 points or more above the average of the 3 years before | 3 points or more below |
| AI models | `compute_gap` | log10(largest US training run ÷ largest Chinese run), single-country models | gap shrank by 0.1 orders of magnitude or more over a year | grew by 0.1 or more |
| AI models | `arena_gap` | best US minus best Chinese Arena score at the latest snapshot | gap narrowed by more than 5 points since the snapshot before | widened by more than 5 |
| Patents & research | `pct_gap` | China minus US PCT applications, latest year | China's margin widened by more than 500 | narrowed by more than 500 |
| Patents & research | `cited_share` | China's share of US + China AI papers with >100 citations, latest year at least two years old (%) | share rose more than 2 points over three years | fell more than 2 points |
| EVs & batteries | `ev_share_gap` | EV share of new cars, China minus US (points) | China's lead widened by more than a point | narrowed by more than a point |
| EVs & batteries | `battery_china` | Chinese makers' share of EV battery installations (%) | rose more than a point on the year | fell more than a point |
| EVs & batteries | `byd_tesla` | BYD ÷ Tesla battery-electric deliveries | ratio rose more than 0.05 | fell more than 0.05 |
| Chips trade | `node_gap` | years SMIC reached its newest node after TSMC | half a year or more shorter than at the node before | half a year or more longer |
| Chips trade | `controls` | US and allied export-control steps in the last 12 months, net (-1 tighten, +1 ease) | easings outnumber tightenings | tightenings outnumber easings |
| Chips trade | `ic_imports` | China's IC imports vs the year before (%) | imports fell more than 5% (less dependence) | rose more than 5% |
| Markets | `rel_1y` | China tech ADR basket vs US tech basket, last 12 months (%) | China's basket beat the US basket by more than 5% | lagged by more than 5% |

The Overview tab shows the same rows with the leader of each layer. `READINGS()` reads only the cached tab payloads (the warmer keeps
every tab but Overview computed), so the daily snapshot never triggers a download. Caveat on `ic_imports`: imports also fall in a chip
downturn (2023), so read it next to the node gap and the controls timeline.

## Tabs, cards and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| AI models | Notable models per year by country; China's share; open-weight models; largest training run by country; top runs | Epoch AI `notable_ai_models.csv` (country of each developing organisation; a joint US-China model counts for both in counts, and is left out of the compute frontier) | yes | Epoch updates weekly |
| AI models | Best US vs best Chinese model, Arena score | `leaderboard.csv` | **hand-entered** | add a snapshot every month or two from lmarena.ai |
| Patents & research | PCT applications by origin; China minus US | `pct.csv` (WIPO PCT Yearly Review / press release) | **hand-entered** | yearly: provisional figures in February/March, final in the Yearly Review |
| Patents & research | AI papers and highly cited AI papers (>100 citations) by country of the authors' institutions | OpenAlex works API, concept `C154945302` (Artificial intelligence), `group_by=publication_year`, one call per country (US, CN, GB, HK) | yes | daily (OpenAlex refreshes continuously) |
| Patents & research | The 100 most-cited AI papers by country | `top_cited.csv` (Stanford AI Index) | **hand-entered** | each April |
| EVs & batteries | Electric share of new car sales; electric cars sold | IEA Global EV Outlook through Our World in Data (`electric-car-sales-share`, `electric-car-sales` grapher CSVs); `ev_share.csv` fills years OWID lacks and is the only source for Hong Kong | yes (OWID); Hong Kong **hand-entered** | yearly (GEVO, May) |
| EVs & batteries | China NEV exports | `ev_exports.csv` (CAAM) | **hand-entered** | yearly (monthly if you want more detail: add rows dated the 1st) |
| EVs & batteries | BYD vs Tesla BEV deliveries | `byd_tesla.csv` (Tesla quarterly delivery releases; BYD monthly volume filings on HKEX, stock 1211) | **hand-entered** | yearly |
| EVs & batteries | Battery makers' share; by home country | `battery_share.csv` (SNE Research; `country` column groups the makers) | **hand-entered** | yearly (SNE publishes in February) |
| Chips trade | China IC imports and exports, yearly | `ic_trade.csv` (GACC, HS 8542) | **hand-entered** | yearly |
| Chips trade | China IC imports per month | `ic_imports_monthly.csv` (GACC monthly "major imports" table) | **hand-entered**, empty for now | monthly: add one row per month and the chart appears |
| Chips trade | SMIC vs TSMC node gap | `node_gap.csv` (pairs rows by node; TSMC 16nm is entered as 14) | **hand-entered** | when a new node is confirmed (TechInsights teardowns) |
| Chips trade | Export-control timeline | `controls.csv` (`direction`: -1 tightens China's access, +1 eases it, 0 China's own counter-measures) | **hand-entered** | as rules are published |
| Chips trade | SMIC and Huawei milestones | `milestones.csv` | **hand-entered** | as events happen |
| Markets | US tech basket (AAPL, MSFT, NVDA, GOOGL, AMZN, META) vs US-listed Chinese tech (BABA, PDD, JD, BIDU, NTES) and KWEB; ratio; calendar-year returns | Nasdaq quote API (stocks via the shared `nasdaq_daily`; KWEB with `assetclass=etf`) | yes | daily |
| Markets | Hang Seng TECH yearly return | `hstech.csv`: iShares Hang Seng TECH ETF calendar-year return (HKD), a stand-in for the index | **hand-entered** | each January |
| Markets | Where tech lists: London, Hong Kong, New York | `listings.csv` | **hand-entered** | as events happen |

Each chart's card says what it shows and what 5-, 10- and 20-year question it answers.

## Hand-entered files

All rows carry a `source` URL. **Rows whose `note` says `verify` were written from memory or from a secondary summary (a search result,
a news site) and must be checked against the cited page**; replace the value and drop `verify` once checked. Rows checked against a
primary or close-to-primary page on 2026-10-26: PCT 2024 and 2025 for China, US, Japan, Korea and Germany (WIPO); CAAM 2025 NEV
exports (via CnEVPost); SNE Research 2025 shares and the 2024 CATL, BYD and LGES shares (via CnEVPost). Checked against the primary page on 2026-11-01: `hstech.csv` 2021-2025 (BlackRock's 3067 factsheet,
as at 30 Sep 2026; the earlier search-summary values were wrong and were replaced) and `top_cited.csv` 2023 (AI Index 2025
chapter 1, Figure 1.1.11). `battery_share.csv` 2020-2024 checked on 2026-11-01 against SNE Research's year-end releases as
reported by TheElec (2020), InsideEVs (2020 BYD GWh; 2021 table) and CnEVPost (2022-2024); every value matched and none changed.
SNE's own 2024 release gave CATL 37.9, BYD 17.2 and LGES 10.8; the file keeps the restated 38.0, 16.9 and 10.9 from the 2025 release
so 2024 and 2025 compare on the same basis. `byd_tesla.csv` 2019-2025 checked on 2026-11-02: Tesla against its Q4 delivery releases
(ir.tesla.com for 2025; Electrive and InsideEVs reports of the releases for 2019-2024), BYD passenger BEVs against CnEVPost's December
reports of BYD's HKEX filings; every value matched and none changed. Tesla's 2020 figure is the release's 499,550, not the 10-K's later
499,647. `ev_exports.csv` 2020-2024 checked on 2026-11-02 against CAAM's figures (China Securities Journal for 2021, Caixin for 2022,
CGTN for 2023 and 2024); 2021-2024 matched. 2020 was wrong (0.223) and is now 0.077: CAAM published no 2020 total in its 2021 release,
so the value is implied by 0.31 million in 2021 being up 304.6%. `controls.csv` (all 16 rows) checked on 2026-11-02 against the Federal
Register, BIS press releases, Nvidia's 8-K, MOFCOM and law-firm or news reports of each step; dates and directions matched. The 30 Jun 2020
row was reworded: that step only suspended Hong Kong's better-than-China licence exceptions; Hong Kong was treated as China from
23 Dec 2020. `ev_share.csv` checked on 2026-11-03 (26 of 29 rows): China, US and World against the IEA's Global EV Outlook text
(2022 press release, 2023, 2024 and 2025 editions), UK 2019-2021 against SMMT's plug-in shares and 2022-2024 against the IEA, Hong Kong
2020-2023 against the LegCo Environmental Affairs Panel paper and LCQ3 of 22 May 2024. World 2019 and 2020 are now 2.5 and 4.1 (were 2.6
and 4); Hong Kong 2020-2023 are now 12.4, 24.4, 52.8 and 64.6 (were 14, 25, 53 and 64; 2020 was the one real error). Where the IEA gives
only wording ("close to 50%", "more than 10%") the row is kept and the wording is in its note. China 2019-2020 (the IEA gives only "under
6% between 2018 and 2020") and Hong Kong 2024 (about 70% in news reports, no government table found) stay `verify`. `ic_trade.csv` checked on 2026-11-03 (18 of 19 rows) against customs figures as reported by the NDRC, Beijing Youth
Daily, Yicai, Xinhua Silk Road, SCMP, DIGITIMES and TrendForce; imports 2021 is now 432.5 (was 432.6) and exports 2023 is now 136.0 (was
136.2), the rest matched. Exports 2020 is implied by 2021's 153.8 being up 31.9%. Imports 2025 (a yuan figure converted by a secondary
source) stays `verify`. `node_gap.csv` (all 8 rows) checked on 2026-11-03: TSMC against its 3nm press release, earnings-call remarks (16FF+ Q2 2015, N7 April 2018, N5 Q2 2020) and its Q4 2025 2nm update; SMIC 14nm against its Q4 2019 results; the 7nm and N+3 finds against TechInsights. Values unchanged; the N+3 row moved to 11 Dec 2025 (TechInsights' post date, was 10 Dec), and its note says TechInsights finds N+3 well short of commercial 5nm, so pairing it with TSMC 5nm flatters SMIC. `leaderboard.csv` checked on 2026-11-04 (4 of 12 rows): lmarena.ai and its Hugging Face space cannot be read from the build servers, so the check uses two dated copies of the leaderboard file: the LMSYS release of 10 Jun 2024 (DataLearner's mirror; GPT-4o 1287 matched, Yi-Large-preview is 1239, was 1240) and the 17 Jul 2025 update of the chatbot-arena-elo dataset (Gemini-2.5-Pro is 1474, was 1470; DeepSeek-R1-0528 1424 matched). Those rows moved from 30 Jun to the snapshot dates. The Dec 2024, Jan 2025, Dec 2025 and Jul 2026 rows stay `verify`: the dataset's dated commits (20241230, 20250128) hold them but could not be opened this run. `listings.csv` (all 10 rows) checked on 2026-11-04 against the PCAOB release, the HFCAA record and dated news reports (Al Jazeera, SCMP, IPOScoop, Irish Times, Yicai, Payment Expert) and law-firm summaries of the HKEX and FCA rules; each row now cites the page it was checked on. Wise moved to 28 Jul 2025 (the shareholder vote; 11 Jun was only the proposal); Alibaba's raise is US$11.3bn, about US$13bn only with the over-allotment; the Didi row says it announced delisting in Dec 2021; the Zhipu row gives both debut days (8 and 9 Jan 2026). Everything else is `verify`.

- `leaderboard.csv`: `date,series,value,model,source,note`, series `US best` / `China best`, value = Arena score of the top model of that
  country on the LMArena text leaderboard (default view) on that date. LMArena re-scales scores, so only compare the two on the same date.
- `pct.csv`: `date,series,value,source,note`, series = origin (China, US, Japan, Korea, Germany, UK), dated 1 January of the filing year.
  The UK 2023-24 rows are rough. Hong Kong is not entered yet (WIPO lists it as "China, Hong Kong SAR"): add it from the WIPO IP statistics data center.
- `top_cited.csv`: the AI Index count of the 100 most-cited AI papers by country (China excludes Hong Kong).
- `ev_share.csv`: fallback EV shares (%) for China, US, UK, World, and the only Hong Kong series (EPD/Transport Department: EV share of new private car first registrations).
- `ev_exports.csv` (million vehicles), `byd_tesla.csv` (vehicles), `battery_share.csv` (%), `ic_trade.csv` (USD bn), `hstech.csv` (%): one row per year, dated 1 January.
- `ic_imports_monthly.csv`: one row per month, dated the 1st, USD bn. The `#` line is a comment the loader skips.
- `controls.csv`, `milestones.csv`, `listings.csv`, `node_gap.csv`: one row per event; see the columns in each header.

## Caveats

- Country attribution follows the source: developer organisation (Epoch), applicant residence (WIPO), author institution (OpenAlex). Hong Kong is shown separately where the source separates it; in the AI Index it is separate from China.
- OpenAlex citation counts favour older papers; the share of highly cited papers compares the US and China within each year, and the reading skips the last two years.
- The Nasdaq baskets are price-only, equal-weighted buy and hold from January 2019. Tencent, Meituan and Xiaomi trade in Hong Kong and are not on Nasdaq's API, which is why the Hang Seng TECH return is entered by hand.
- Reachability from Railway, checked with `/api/china-us-tech/layout` on 2026-10-26: Epoch AI (CSV, 2.3 MB), Our World in Data (both grapher CSVs), OpenAlex (JSON) and the Nasdaq API (stocks and `assetclass=etf`) all answered 200. If one refuses the server later, its last snapshot is served and marked stale; with no snapshot the cards fall back to the hand-entered rows (EV shares) or say what is missing, and the rest of the page is unaffected.
- OpenAlex without an API key shares a small free daily budget with everyone on the same IP address (its reply says so). This page makes 8 grouped calls a day. If the budget runs out, the last snapshot is served. A key is not added because it would travel in the URL, and `/api/health` lists source URLs publicly.

## Requests for shared code

- `_base.nasdaq_daily` hard-codes `assetclass=stocks`; an `assetclass` argument would let ETFs (KWEB here) use it instead of the copy in `china_us_tech.nasdaq_etf`. A request, not needed for the page to work.
- A free, cloud-reachable source for the Hang Seng TECH index level (Hang Seng Indexes' site has no documented CSV) would replace `hstech.csv`. If one is found, adding it to `PROBE_URLS` would let `/api/probe` watch it.
