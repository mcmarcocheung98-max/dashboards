# Demographics & Ageing (`/demographics`)

The question this page answers: **who pays for pensions in 2045, and which of the US, UK, Hong Kong and China shrinks fastest?** It puts births, ageing, migration and the workforce for the four side by side, from 1950 to 2100. Then it sets the number of people of working age per pensioner in 2045 against what each government says pensions will cost.

## What it shows

| Tab | Card | What it answers (5 / 10 / 20 years) |
|---|---|---|
| Births | Fertility rate 1950–2100 (UN) | Is the post-2015 fall levelling off? Does anyone get back above 1.5? Today's births are most of the 2045 workforce |
| | Fertility rate as each statistics office publishes it | Recent direction; whether official rates fall below the UN's projection |
| | Births per year, 2019 = 100 (CDC, ONS, C&SD, NBS) | Has the post-Covid drop reversed? School intakes; workforce entrants in the mid-2040s |
| | Births per year 1950–2100 (UN, log scale) | The size of each cohort, and what the UN assumes after 2050 |
| Ageing | Old-age dependency (65+ per 100 aged 15–64) 1950–2100 | Pace as the boomers (China: the 1960s cohort) pass 65; whether HK and China overtake the UK; the 2045 ratio itself |
| | Median age 1950–2100 | The steady rise; HK and China past 50; how far apart the US and East Asia end up |
| | National projections (ONS, Census, C&SD) | A check on the UN's projections |
| Migration | Net migration per 1,000 people 1950–2100 (UN) | The UK surge unwinding, HK's 2020–22 outflow reversing; whether migration offsets low births; the 2045 workforce gap |
| | Net migration, thousands (UN) | Scale |
| | National counts (ONS LTIM, Census NIM, C&SD net movement and one-way permits) | The latest official figures |
| Workforce | People aged 15–64, 2025 = 100, 1950–2100 | Who has already peaked; US and UK growth only through migration; the 2045 base that pays |
| | People 15–64 per person 65+ | When each crosses 2 |
| | Labour force participation, 15+ and 15–64 (ILO modelled, World Bank) | How far older workers and women offset ageing; the room left |
| Pensions | Who pays in 2045 | Workers per 65+ in 2025 and 2045; working-age change to 2045, ranked fastest-shrinking first; pension spend in 2045 where an agency projects it |
| | Public pension spending, % of GDP (OBR, CBO; China verify) | The triple lock and the 2034 US trust-fund date; pension-age changes; the 2045 share of GDP |

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| TFR, births, median age, net migration (count and per 1,000), population | [UN World Population Prospects 2024](https://population.un.org/wpp/downloads), `WPP2024_Demographic_Indicators_Medium.csv.gz` | Every two years (next: WPP 2026) | Automated |
| Population by five-year age group (dependency ratio, people 15–64) | WPP 2024, `WPP2024_PopulationByAge5GroupSex_Medium.csv.gz` | Every two years | Automated |
| Dependency ratio and people 15–64 to 2050 (fallback when the WPP age file cannot be read) | World Bank Population Estimates and Projections API (source 40: `SP.POP.DPND.OL`, `SP.POP.1564.TO`) | Yearly | Automated |
| Labour force participation | World Bank WDI API (`SL.TLF.CACT.ZS`, `SL.TLF.ACTI.ZS`: ILO modelled estimates) | Yearly | Automated |
| National births | CDC NCHS (US), ONS (England and Wales), C&SD (Hong Kong), NBS (China) | Yearly | Hand-entered: `births.csv` |
| National fertility rates | CDC NCHS, ONS, C&SD; China: the 2020 census only | Yearly | Hand-entered: `tfr.csv` |
| Net migration | ONS LTIM (UK), Census Bureau Vintage estimates (US), C&SD population estimates (HK net movement, one-way permit holders) | Twice a year (ONS, C&SD), yearly (Census) | Hand-entered: `migration.csv` |
| Pension spending, % of GDP | OBR Fiscal risks and sustainability (UK state pension), CBO Long-Term Budget Outlook (US Social Security), China basic pension funds | Yearly | Hand-entered: `pensions.csv` |
| National population projections | ONS, US Census Bureau, C&SD | Every 2–5 years | Hand-entered: `projections.csv` |

UN and World Bank data are CC BY 3.0 IGO / CC BY 4.0. ONS and OBR data are under the Open Government Licence. US federal data is public domain.

**Places.** WPP's "China" is the mainland, without Hong Kong, Macao or Taiwan. The UK's national births and fertility figures are for England and Wales, which ONS publishes; Scotland and Northern Ireland publish their own. Every series names its place.

## How it is calculated

- **Estimates and projections.** WPP 2024 estimates run to 2023 and the medium projection runs from 2024. The page draws estimates solid and the projection dashed, joined at 2023. Every annual point is dated 1 July, including hand-entered calendar-year figures.
- **Old-age dependency** is people 65+ per 100 aged 15–64, summed from the five-year age groups. That is the World Bank's definition. The UN's own headline uses 25–64 or 20–64, so its figures are higher.
- **Births index**: each country's births divided by its 2019 births.
- **The answer card.** People 15–64 per person 65+ is 100 ÷ dependency, for 2025 and 2045. The rows are ranked by the change in people aged 15–64 from 2025 to 2045, smallest (fastest shrinking) first. Pension spend in 2045 is a straight line between the agency's published points either side of 2045. The UK's points (OBR: about 5% now, 7.7% in the early 2070s) are some 50 years apart, so its 2045 figure is a rough guide. A place with no published projection either side of 2045 shows "–". Hong Kong has no state pension (the MPF is employer-funded and private).

## Keeping it up to date

**Automated (WPP).** Each WPP file is streamed and decompressed while it is read: the age file is tens of MB and is never held in memory whole. Only the four places' rows are kept. The reduction is stored as `wpp-<hash>.csv` in the snapshot folder and reused for 30 days, then downloaded again. When the UN site is down, the last reduction is served and the card shows its date. When WPP 2026 is released, change `WPP_IND` and `WPP_AGE` in `app/topics/demographics.py` (the file names carry the year) and `CUT` (the last estimate year). If the UN renames a column, the card says "not available right now (ValueError)". The parser needs `ISO3_code` and `Time`, plus `TFR` and `MedianAgePop` (indicators) or `AgeGrpStart` and `PopTotal` (ages).

**Automated (World Bank).** The JSON API is fetched daily, cached and snapshotted like every other source.

**Hand-entered files** use `date,series,value,source,note`. `date` is `YYYY-07-01` for a calendar year, the end of the 12 months for migration, and the fiscal year's midpoint for pensions. `series` is the place exactly as the page names it (`US`, `UK`, `Hong Kong`, `China`) in `births.csv` and `tfr.csv`. In `pensions.csv` it starts with the place and a space (`UK state pension (OBR)`), because that prefix links it to the answer card.

| File | Add a row when |
|---|---|
| `births.csv`, `tfr.csv` | CDC NCHS final births (July–Sept), ONS births in England and Wales (summer), C&SD vital statistics (Feb and Aug), NBS communiqué (January) |
| `migration.csv` | ONS LTIM (May and November), Census Vintage estimates (December), C&SD mid-year and year-end population (August and February) |
| `pensions.csv` | OBR Fiscal risks and sustainability (July), CBO Long-Term Budget Outlook (March) |
| `projections.csv` | A new national projection round |

**Rows to verify.** `verify` in a row's note means it was written from memory or copied from a press report. The page shows the note next to the row, and each one needs checking against the agency's own table. On 26 Oct 2026 these rows were checked against the agency's release or an official reply: US births and TFR 2023–24 (NCHS Data Brief 535, NVSR 75-2), England and Wales births and TFR 2023–24 (ONS 2024 refreshed populations), Hong Kong TFR 2024 (LegCo reply, 16 Jul 2025), C&SD mid-2025 migration rows, ONS LTIM YE June 2024 and June 2025, OBR state pension (about 5% now, 7.7% early 2070s), and CBO Social Security 5.2% (2025) and 6.1% (2055). China births for 2024 and 2025 (9.54m and 7.92m) come from Caixin's report of the NBS release. Everything else is still marked `verify`. Several C&SD and NBS rows cite the agency's home page rather than the exact table, because the table address could not be checked from here; replace each with the table page when you verify the row.

## What changed since yesterday (`READINGS()`)

`READINGS()` reads only the tab payloads the warmer has already cached and never downloads. **+1 means easier to pay for pensions (more births, workers or inflows; fewer pensioners per worker; a smaller pension bill), −1 harder, 0 in between.**

| Tab | Reading (one per place or series) | Lean |
|---|---|---|
| Births | Latest official fertility rate | Direction since the previous official figure |
| Ageing | People 65+ per 100 aged 15–64 in 2045 (UN) | +1 at 35 or below, −1 at 50 or above (fewer than two workers per pensioner) |
| Migration | Latest national net migration count (natural change left out) | Direction since the previous figure |
| Workforce | Change in people aged 15–64, 2025 to 2045 (UN) | +1 above +2%, −1 below −2% |
| Pensions | The place shrinking fastest (0); public pension spend in 2045, % GDP | +1 at 5% or below, −1 at 7% or above |

Most of these move only when a row is added or the UN publishes a new round, so a flip usually means new data, not a new day.

## Checking it

```
python -m pytest tests/test_demographics.py -q                 # fixtures, no network
python -m pytest -m network tests/test_demographics.py -q      # the live WPP and World Bank files
python scripts/smoke.py --only demographics
```

`/api/health` lists the two WPP files and the World Bank URLs under `demographics`.

## Requests for shared code

- `PROBE_URLS` in `app/topics/__init__.py` could add `https://api.worldbank.org/v2/country/USA/indicator/SP.POP.TOTL?format=json` and the WPP indicators file. `/api/probe` and the probe-here workflow would then show whether Railway and GitHub reach them before a deploy.
- `scripts/smoke.py` hard-codes `/opt/pw-browsers/chromium-1194`. Reading `PLAYWRIGHT_CHROMIUM_EXECUTABLE` (or globbing `chromium-*`) would let it run in containers with a newer Chromium without pinning the Python Playwright version.
