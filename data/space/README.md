# Space Economy (`/space`)

**The question:** when does orbit become routine infrastructure?

Five tabs. Data at `/api/space/<launches|cost|satellites|industry|ukhk>`. `/api/space/answer` is the routine-infrastructure checklist shown at the top of Launches. `/api/space/layout` (not a tab) shows what the server gets back from each live source (status, type, length, the first 1,200 characters). Read it with Actions → show-json.

## Sources and cadence

| Tab | What | Source | Automated? | Cadence |
|---|---|---|---|---|
| Launches | Orbital and deep-space launch attempts, 1957 on: date, provider (agency code), success | Jonathan McDowell's GCAT `tsv/launch/launch.tsv` (Launch_Code starting `O` or `D`; second letter `S` = success) | yes | GCAT updates about weekly |
| Launches | Provider names and countries | GCAT `tsv/tables/orgs.tsv` (Code → ShortName, StateCode) | yes (fallback names for 10 big providers in `space.py` if it fails) | rarely changes |
| Launches | Payload launch mass to orbit per year, Starlink split | GCAT `tsv/cat/satcat.tsv` (Type starting `P`, Mass, LDate) | yes | weekly |
| Cost to orbit | Cost per kg to LEO by rocket, by first flight | CSIS Aerospace Security estimates (2021 USD), list prices | hand-entered: `cost.csv` (`date,series,value,country,kind,price_musd,leo_kg,source,note`; `kind` is `flown` or `target`) | as published |
| Starlink & satellites | Active payloads by operator, owner and launch year | CelesTrak `pub/satcat.csv` (OPS_STATUS_CODE in `+ P B S X`, OBJECT_TYPE `PAY`, no DECAY_DATE) | yes | daily |
| Starlink & satellites | Starlink subscribers | SpaceX / Starlink announcements | hand-entered: `starlink.csv` | as announced |
| Industry | Global space economy (Space Foundation), government space budgets (OECD), UK space sector income (UK Space Agency), WEF/McKinsey 2035 projection | as cited per row | hand-entered: `economy.csv` | yearly |
| Industry | RKLB, ASTS, IRDM, PL (stocks), UFO and SPY (ETFs), daily closes since 2021 | Nasdaq quote API | yes | daily |
| UK, HK & China | UK launch attempts, spaceport licences, Hong Kong and China milestones | UK Space Agency, CAA, CNSA, CMSA, companies | hand-entered: `milestones.csv` (`date,place,kind,event,outcome,site,source,note`) | as they happen |
| UK, HK & China | China's launches per year by provider; commercial = not CASC | GCAT launch list | yes | weekly |

FRED, Yahoo and Stooq are not used: from Railway they time out, return 429 or are blocked.

**Checked on the server?** The machine that built this dashboard could not reach planet4589.org, celestrak.org or api.nasdaq.com, so the GCAT and CelesTrak parsers follow the published column names and are tested on fixtures only. The parsers look columns up by name, ignoring case. If a tab says "not available", open `/api/space/layout` and compare the header line with `parse_tsv` / `parse_celestrak` in `app/topics/space.py`.

## Hand-entered rows: all marked `verify`

**Every hand-entered row was entered from memory and says `verify` in its note.** Check each against its cited page, then fix the value or drop `verify`. Least certain:

- the CSIS per-kg figures for Ariane 5, Atlas V and Delta IV Heavy, and the Ariane 6 price;
- Starlink subscriber dates (the June 2021, mid-2025 and November 2025 rows) and anything after November 2025, which is not entered yet;
- Space Foundation totals before 2021 (the 2017 method change), the OECD budget figure and the UK Size and Health years;
- the HK rows (Golden Bauhinia launch date, the payload specialist announcement month) and the SaxaVord licence date.

Add a row to `milestones.csv` with `kind=launch`, `place=UK` and `site=SaxaVord` (or another UK site) when a UK vertical launch happens: the UK checklist row and the "days since" reading follow from it.

## The routine-infrastructure checklist

| Sign | Threshold | From |
|---|---|---|
| A launch a day worldwide | 365+ orbital attempts in the last 12 months | GCAT |
| Cheap access | cheapest flown cost under $1,000/kg | `cost.csv` |
| More than one supplier | the biggest provider besides SpaceX flies 52+ a year | GCAT |
| A fleet people rely on | 10,000+ active satellites | CelesTrak |
| Mass-market service | 10 million+ Starlink subscribers | `starlink.csv` |
| UK launch from home | at least one successful orbital launch from UK soil | `milestones.csv` |

## READINGS: what +1 and −1 mean

+1 means faster growth or cheaper access, −1 the opposite, 0 neither. Each reading is computed from the cached tab data only.

| Tab | Key | Reading | +1 | −1 |
|---|---|---|---|---|
| launches | `orbital_12m` | orbital launch attempts, last 12 months | up more than 5% on the 12 months before | down more than 5% |
| launches | `china_12m` | China's launches, last 12 months | up more than 5% | down more than 5% |
| launches | `non_spacex_12m` | launches by everyone but SpaceX, last 12 months | up more than 5% | down more than 5% |
| launches | `mass` | payload tonnes to orbit, last full year | up more than 10% on the year before | down more than 5% |
| launches | `routine` | checklist signs met | more than half met | never |
| cost | `cost_frontier` | cheapest flown $/kg among rockets first flown in the last 10 years | 20% cheaper than the best older rocket | more than 5% dearer |
| cost | `cost_10y` | change in the cheapest flown $/kg over 10 years | at least 25% cheaper | dearer |
| satellites | `active` | active satellites (value); lean from those launched in the last 12 months vs the 12 before | 5% more | 5% fewer |
| satellites | `starlink_share` | Starlink share of active satellites | below half | never (concentration is not a lean against growth) |
| satellites | `starlink_subs` | Starlink subscribers | up more than 50% on a year earlier (interpolated) | under 20% |
| industry | `economy` | global space economy, latest year | up more than 5% | shrank |
| industry | `stocks_vs_spy` | equal-weight 1-year return of RKLB, ASTS, IRDM, PL minus SPY's | beat by 5 points | lagged by 5 |
| industry | `ufo_200d` | UFO ETF vs its 200-day average | more than 2% above | more than 2% below |
| ukhk | `uk_last_attempt` | days since the last UK orbital attempt | an attempt in the last year | never |
| ukhk | `china_commercial` | China's non-CASC launches, last full year | up more than 10% | down more than 5% |

## Notes on the data

- **Country is the provider's**, from GCAT's organisation state code: Rocket Lab's New Zealand launches count for the US, Arianespace's Kourou launches for Europe. Europe is France, Germany, Italy and the ESA/EU codes.
- **Commercial China** is every Chinese provider whose name is not CASC, CALT, SAST or the PLA; GCAT's codes for the state firms may need adding to that list.
- **Active satellites counted by launch date** is a lower bound on the fleet at each past date, as satellites since retired are not counted.
- **Cost per kg** mixes CSIS's inflation-adjusted estimates with nominal list prices; it shows the order of magnitude, not a price index.
- **No Hong Kong or China space stocks** are on the Nasdaq API.

## Requests for shared code

- `PROBE_URLS` in `app/topics/__init__.py` could add `https://planet4589.org/space/gcat/tsv/launch/launch.tsv` and `https://celestrak.org/pub/satcat.csv`, so `/api/probe` checks them with the other sources. `/api/space/layout` covers it for now.
