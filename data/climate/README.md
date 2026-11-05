# Climate Signals (`/climate`)

**The question:** how fast are physical changes, and what they cost, compounding? Global temperature against the 1.5 °C line, CO₂ and methane, sea level and sea ice, hot days and record highs in Hong Kong, London and New York, and disaster losses in the US, China and worldwide.

Code: `app/topics/climate.py` (data), `app/static/topics/climate.js` (cards), `tests/test_climate.py` (fixtures and `smoke_patch()`).
Data for each tab: `/api/climate/<temperature|co2|sea|heat|costs>`. `/api/climate/layout` (not a tab) shows what the server gets back from every source (status, size, first 600 characters), so reachability and file layouts can be checked from Railway with Actions > show-json.

## Tabs, cards and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| Temperature | Monthly global anomaly vs 1850–1900, three datasets, 1.5 °C and 2 °C lines | NASA GISTEMP v4 `GLB.Ts+dSST.csv` (rebased from 1951–80 to its 1880–1900 mean); Copernicus ERA5 Climate Pulse daily CSV (monthly means of days; 1991–2020 anomaly + 0.88 °C, the C3S offset); Met Office HadCRUT5 summary monthly CSV (rebased from 1961–90 to 1850–1900) | yes | GISTEMP and HadCRUT monthly; ERA5 daily (2-day lag) |
| Temperature | 12-month mean, yearly means; KPIs: warming rate over the last 20 years, year the 30-year trend reaches 1.5 °C, warmest year | computed from the above | yes | |
| Temperature | ERA5 daily: this year against last year, the three warmest years and the 1991–2020 average | Climate Pulse | yes | daily |
| CO₂ | Mauna Loa monthly mean and seasonally adjusted | NOAA GML `co2_mm_mlo.csv` | yes | monthly, ~5th |
| CO₂ | Yearly growth (bars) and the last 12 months | NOAA GML `co2_gr_mlo.csv`; 12-month change of the seasonally adjusted series | yes | yearly / monthly |
| CO₂ | Global methane | NOAA GML `ch4_mm_gl.csv` | yes | monthly, ~3-month lag |
| CO₂ | Fossil CO₂ emissions and per person: China, US, UK, Hong Kong, world | Global Carbon Budget through Our World in Data's `owid-co2-data.csv` (GitHub) | yes | yearly, after each Global Carbon Budget (November) |
| Sea level & ice | Global mean sea level | NOAA STAR Laboratory for Satellite Altimetry `slr_sla_gbl_free_ref_90.csv` (falls back to `keep` and the older `txj1j2` names) | yes | about monthly |
| Sea level & ice | Tide gauges vs 1991–2020: New York (Battery, PSMSL 12), Newlyn (202), Hong Kong (North Point, 333) | PSMSL monthly RLR files | yes | yearly |
| Sea level & ice | Yearly minimum extent, Arctic and Antarctic; daily extent this year against 1981–2010 and 2011–2020 | NSIDC Sea Ice Index (G02135) daily CSVs, v4.0 (v3.0 as fallback) | yes | daily |
| Local heat | Hot days a year: Hong Kong ≥33 °C (HKO "very hot day"), London ≥30 °C, New York ≥32.2 °C (90 °F); hot nights (HK ≥28 °C, NY ≥24 °C, London ≥20 °C) | HKO open data `CLMMAXT` / `CLMMINT` (Observatory HQ since 1884); NOAA NCEI Access Data Service, GHCN-Daily `USW00094728` (Central Park, from 1869) and `UKM00003772` (Heathrow) | yes | daily |
| Local heat | Calendar-day record highs and lows a year; share of records that were highs, 10 years summed | computed from the daily series, counted from 30 years after each station starts | yes | |
| Local heat | Average daily maximum, yearly; Heathrow since 1948 | the above; Met Office historic station data `heathrowdata.txt` | yes | monthly |
| Costs | Insured natural-catastrophe and total insured losses, with a log-linear trend | `insured_losses.csv` (Swiss Re sigma) | **hand-entered** | yearly, sigma "Natural catastrophes" (March/April) |
| Costs | US billion-dollar disasters a year (and CPI-adjusted cost when the archive file answers) | NCEI `events-US-1980-2024.csv` when reachable, else `billion_dollar.csv` | archive yes, fallback **hand-entered** | ended: NOAA stopped the series after 2024 |
| Costs | China direct economic losses from natural disasters | `china_losses.csv` (Ministry of Emergency Management) | **hand-entered** | yearly, January |
| Costs | Notable events (US, UK, Hong Kong, China) | `events.csv` | **hand-entered** | as events happen |

Each chart's card says what it shows and what 5-, 10- and 20-year question it answers.

## Hand-entered files

Every row carries a `source` URL. Rows whose `note` says **verify** were written from memory and must be checked against the cited page; replace the value and drop `verify` once checked. **All rows in `insured_losses.csv`, `billion_dollar.csv` and `china_losses.csv` are currently `verify`.**

- `insured_losses.csv`: `date,series,value,source,note`, series `nat cat` and `total`, USD bn, nominal as first reported in each year's sigma. Add a row each spring when Swiss Re publishes. Swiss Re also restates history in today's prices; if you switch to those, change every row and say so here.
- `billion_dollar.csv`: `date,series,value,...`, series `count`, events a year, CPI-adjusted (January 2025 release). My recollection of the early-year counts sums to an average of about 8.6 a year where NOAA's release said 9.0, so they are under by some events: check against the archived NCEI time-series page. Only used when the NCEI archive file does not answer.
- `china_losses.csv`: `date,value,source,note`, direct economic losses from natural disasters, CN¥ bn, from MEM's year-end national disaster situation release (published in 亿元: divide by 10).
- `events.csv`: `date,place,event,source,note`. Quote the event text when it contains a comma. Checked on 2026-11-05 (12 of 13 rows) against NCEI, NWS New York, HKO, gov.cn, the Met Office, Copernicus, China Daily (quoting the CMA), weather.com and Insurance Journal (quoting Swiss Re). Katrina is now framed as the costliest US hurricane ($201.3bn, 2024 dollars), Sandy's Battery level is 14.0 ft, Heathrow's 40.2 °C was dropped, and the 2022 China row now uses the CMA's 16.4 days above 35 °C (most since 1961) in place of "longest and most intense". 2017 as the costliest year stays `verify` (NCEI's yearly page could not be opened). AFP reports a new Hong Kong Observatory record of 36.9 °C on 9 Aug 2026; add it as a row once HKO's own page confirms it.

## Readings (what changed since yesterday)

`READINGS()` reads the tab payloads the warmer has already cached (`readings` in each payload) and never downloads. **+1 means improving or cooler, −1 worsening, 0 within the dead band.**

| Tab | Key | Reading | +1 | −1 | Dead band |
|---|---|---|---|---|---|
| Temperature | `t_r12` | Last 12 months vs 1850–1900 (ERA5, else GISTEMP, else HadCRUT5) | below 1.5 °C | above 1.5 °C | none |
| Temperature | `t_r12_change` | 12-month mean against a year earlier | cooler | warmer | ±0.03 °C |
| Temperature | `t_month_yoy` | Latest month against the same month a year earlier | cooler | warmer | ±0.05 °C |
| Temperature | `t_rate20` | Warming rate over the last 20 years | below 0.2 °C a decade | above | ±0.03 |
| CO₂ | `co2_growth` | Mauna Loa growth over the last 12 months against the 10-year average | slower | faster | ±0.15 ppm |
| CO₂ | `co2_ppm` | Latest monthly ppm | level falling | level rising | |
| CO₂ | `ch4_growth` | Methane growth over the last 12 months against the 10-year average | slower | faster | ±1 ppb |
| CO₂ | `emis_china`, `emis_world`, `emis_us` | Fossil CO₂ change in the latest year | fell | rose | ±0.25% |
| Sea level & ice | `gmsl_rate` | Global sea-level rise a year over the last 10 complete years against the 10 before | slower | faster | ±0.3 mm |
| Sea level & ice | `ice_north`, `ice_south` | Extent on the latest day against the 2011–2020 average for that date | more ice | less | ±0.1 million km² |
| Local heat | `hot_<city>` | Hot days this year so far against the 1991–2020 average to the same date (only while the station's data is under 20 days old) | fewer | more | ±max(1 day, 15%) |
| Local heat | `rec_<city>` | Calendar-day record highs : record lows over the last 365 days | more lows | more highs | none |
| Costs | `insured_vs_trend` | Latest year's insured nat-cat losses against the log-linear trend | below trend | above | ±10% |
| Costs | `billions` | US billion-dollar disasters in the latest year against the 10 years before | fewer | more | ±2 events |
| Costs | `china_losses` | China's direct losses in the latest year against the 5 years before | lower | higher | ±10% |

## Caveats

- 1.5 °C in the Paris Agreement is a 20-year average. A month, a 12-month window or a calendar year above it is a warning, not a breach. The trend-crossing year in the KPIs is a straight line through the last 30 yearly values, not a projection.
- GISTEMP starts in 1880, so its "pre-industrial" is 1880–1900; this reads a little cooler than 1850–1900 baselines (by about 0.05 °C).
- Tide gauges include vertical land motion; global satellite sea level does not.
- London hot days come from GHCN-Daily for Heathrow (`UKM00003772`, December 1948 on), the only GHCN station with daily maxima within about 25 km of central London. NCEI's copy stopped on 2025-08-24 (checked from Railway, October 2026), so London's counts end there and London gives no `hot_London` / `rec_London` reading while it is more than 20 days old. The Met Office monthly Heathrow file is current but has no daily values. See "Requests for shared code".
- Hot-day thresholds differ by city on purpose (each city's own convention); compare trends, not levels, across cities.
- Insured losses are nominal: part of the trend is inflation and more property in exposed places. NOAA's counts are CPI-adjusted, Swiss Re's here are not.
- Railway runs in the US. The Met Office and Copernicus are the sources most likely to refuse a cloud server; each feeds one line, so the rest still shows. Check `/api/climate/layout` after a deploy.

## Requests for shared code

None needed for the code. One data gap: a current daily maximum for London. The Met Office's daily station data (MIDAS Open via CEDA) needs a registered account, and ECA&D's per-station files are zips behind a form; if either can be fetched from Railway (a CEDA token as an environment variable, say), `station("London")` can take it with a parser and nothing shared changes.
