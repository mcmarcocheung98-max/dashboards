# Longevity & Biotech (`/longevity`)

**The question:** do healthy life years start rising again, and does biotech deliver it?

Five tabs. Data at `/api/longevity/<lifespan|causes|glp1|approvals|markets>`. `/api/longevity/layout` (not a tab) shows what the server gets back from each live source (status, size, start of body). Read it with Actions → show-json.

## Sources and cadence

| Tab | What | Source | Automated? | Cadence |
|---|---|---|---|---|
| Lifespan | Life expectancy at birth, US, UK, Hong Kong, China, 1960 on | World Bank API `SP.DYN.LE00.IN` (carries Hong Kong) | yes | yearly, about 18 months behind |
| Lifespan | Healthy life expectancy (HALE) and life expectancy, US, UK, China | WHO xMart API `xmart-api-public.who.int/DATA_/RELAY_WHS`, indicators `WHOSIS_000002`, `WHOSIS_000001`, one request per place (no Hong Kong) | yes | every few years (to 2021 now) |
| Lifespan | National life expectancy | CDC NCHS (US), ONS national life tables (UK, three-year periods by sex), C&SD/DH (HK by sex), NHC (China) | hand-entered: `life_expectancy.csv` | yearly |
| Lifespan | England healthy life expectancy (male, female) | ONS health state life expectancies | hand-entered: `healthy.csv` | yearly (three-year periods) |
| Causes | US age-adjusted death rates, 12 months ending each quarter: heart disease, cancer, Alzheimer disease, drug overdose, all causes | CDC NCHS VSRR quarterly provisional estimates, `data.cdc.gov/resource/489q-934x.json` (Socrata) | yes | quarterly |
| Causes | Chance of dying aged 30–70 from the four main NCDs (SDG 3.4.1), US, UK, China | WHO xMart `NCDMORT3070` | yes | every few years |
| Causes | England & Wales drug poisoning deaths; dementia and Alzheimer's share of deaths | ONS | hand-entered: `causes_uk.csv` | yearly |
| Causes | Hong Kong deaths by cause | CHP | hand-entered: `causes_hk.csv` (placeholders, empty) | yearly |
| GLP-1 | NHS England items dispensed and net ingredient cost: semaglutide, tirzepatide, liraglutide, dulaglutide | NHSBSA Prescription Cost Analysis, monthly tables `PCA_YYYYMM` from January 2021, summed by `BNF_CHEMICAL_SUBSTANCE` with CKAN `datastore_search_sql` (`opendata.nhsbsa.net`) | yes | monthly, about 2 months behind |
| GLP-1 | Eli Lilly revenue (USD; annual and quarterly), Novo Nordisk revenue (DKK; annual) | SEC EDGAR companyconcept: Lilly `us-gaap/Revenues` (2007 on; Lilly has no `RevenueFromContractWithCustomerExcludingAssessedTax` concept), Novo `ifrs-full/Revenue` from the 20-F | yes | quarterly / yearly |
| GLP-1 | Brand sales: Mounjaro, Zepbound (USD bn), Ozempic, Wegovy (DKK bn) | company annual reports | hand-entered: `products.csv` | yearly |
| GLP-1 | Uptake surveys (KFF, Gallup), UK private use estimate | as cited per row | hand-entered: `uptake.csv` | as published |
| Approvals | FDA CDER novel drug approvals per year | FDA "Novel Drug Approvals" pages | hand-entered: `fda_novel.csv` | yearly (add each January) |
| Approvals | Cell and gene therapy approvals | FDA CBER approved products list, MHRA | hand-entered: `cgt.csv` (`date,name,agency,kind,source,note`) | as approved |
| Approvals | Regulatory milestones (FDA, MHRA, NICE, NHS England, NMPA) | as cited per row | hand-entered: `milestones.csv` (`date,agency,event,source,note`) | as they happen |
| Markets | XBI, IBB, SPY (ETFs), LLY, NVO, daily closes since 2016 | Nasdaq quote API (`assetclass=etf` / `stocks`) | yes | daily |

FRED, Yahoo and Stooq are not used: from Railway they time out, return 429 or are blocked. Checked from Railway on 2026-10-26 (`/api/longevity/layout`): WHO's GHO OData API (`ghoapi.azureedge.net`) answers 500 to every request, so WHO data comes from the xMart API; OpenPrescribing answers 403 (a Cloudflare challenge), so prescriptions come from NHSBSA's own open-data portal. World Bank, CDC Socrata, SEC (with a `Name email` User-Agent) and Nasdaq answer.

## Hand-entered rows: all marked `verify`

The machine that built this dashboard could not reach any of the sources. **Every hand-entered row was entered from memory and says `verify` in its note.** Check each against its cited page, then fix the value or drop `verify`. Least certain:

- the FDA's 2025 novel approval count (46), and the 2025 cell and gene therapy dates;
- ONS UK life expectancy for 2018–20 and England healthy life expectancy for 2020–22;
- Hong Kong life expectancy for 2022 (a Covid year) and China's 2015–2024 NHC figures;
- the ONS dementia share of deaths and the November 2025 KFF poll figures;
- 2025 brand sales are not entered yet (Mounjaro, Zepbound, Ozempic, Wegovy): add them from the 2025 annual reports.

`causes_hk.csv` has two empty placeholder rows (not drawn). Fill it from the Centre for Health Protection's table of age-standardised death rates by leading cause.

## READINGS: what +1 and −1 mean

+1 means improving health or faster innovation, −1 the opposite, 0 neither. Each reading is computed from the cached tab data only.

| Tab | Key | Reading | +1 | −1 |
|---|---|---|---|---|
| lifespan | `le_<place>` | World Bank life expectancy, latest year | up more than 0.1 years over 3 years | down more than 0.1 |
| lifespan | `nat_<series>` | national life expectancy, latest | up more than 0.1 years over 3 years | down more than 0.1 |
| lifespan | `hale_<place>` | WHO healthy life expectancy, latest | up more than 0.2 years over 10 years | down more than 0.2 |
| lifespan | `hle_<series>` | England healthy life expectancy (ONS) | up more than 0.1 years on the period before | down more than 0.1 |
| causes | `us_<cause>` | US age-adjusted death rate, 12 months to the latest quarter (heart, cancer, alzheimer, overdose, all) | fell more than 1% on a year earlier | rose more than 1% |
| causes | `ncd_<place>` | WHO chance of dying 30–70 from NCDs | down more than 0.5 points over 10 years | up more than 0.5 |
| causes | `uk_<series>` | E&W drug deaths, dementia share | down more than 2% on the year before | up more than 2% |
| glp1 | `nhs_items` | NHS England GLP-1 items, last 12 months | up more than 10% on the 12 months before | fewer than the 12 months before |
| glp1 | `rev_eli`, `rev_novo` | revenue growth, latest quarter on a year earlier (Novo: latest year) | above 10% | shrinking |
| glp1 | `up_<series>` | survey uptake, latest vs the survey before | uptake up more than 0.5 points (obesity rate: down) | the reverse |
| approvals | `fda_novel` | FDA novel approvals, latest full year | 10% above the 10 years before | 10% below |
| approvals | `cgt` | cell and gene therapy approvals (FDA + MHRA), last full year | more than one above the 3 years before | more than one below |
| markets | `xbi_vs_spy` | XBI 1-year return minus SPY's | biotech beat the S&P 500 by 5 points | lagged by 5 |
| markets | `xbi_200d` | XBI against its 200-day average | more than 2% above | more than 2% below |
| markets | `xbi_peak` | XBI below its all-time peak | within 10% | more than 40% below |

## Notes on the data

- **Period life expectancy** reacts at once to a bad year (Covid, overdoses). It is not a forecast for anyone born that year.
- **WHO's HALE stops at 2021** and does not cover Hong Kong. England's ONS figure is the most recent official healthy-life check; it is self-reported health, so it moves with survey changes too.
- **NHS prescriptions undercount weight-loss use.** Most UK weight-loss injections are bought privately and do not appear in NHS data. Each month's PCA table is fetched once and kept (it does not change); the first load runs about 70 small SQL queries.
- **EDGAR quarters.** Q4 is the 10-K year less the three 10-Q quarters. A later filing (a restatement) replaces an earlier one. Novo Nordisk files a 20-F (annual, IFRS, DKK) and no XBRL quarters.
- **SEC User-Agent.** The SEC answers 403 unless the User-Agent reads `Name email`. Set `SEC_UA` on Railway to use a real contact.
- **No Hong Kong or China biotech index** is on the Nasdaq API, so the Markets tab is US-listed only.

## Requests for shared code

None yet.
