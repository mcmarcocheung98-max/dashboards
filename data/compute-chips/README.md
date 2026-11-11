# AI Compute, Power & Chips (`/compute-chips`)

The question: **is power or chips the binding limit on AI, and does Taiwan's share of leading-edge chipmaking actually fall?** Covers the US, UK, Hong Kong and China (with the world for scale).

Code: `app/topics/compute_chips.py` (data), `app/static/topics/compute-chips.js` (cards), `tests/test_compute_chips.py` (fixtures, `smoke_patch()`).

## Tabs and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| Overview | One headline number from each tab | the other tabs | yes | – |
| Power | Data-centre electricity, TWh a year, with outlooks | IEA *Energy and AI* (Apr 2025), LBNL *2024 US Data Center Energy Usage Report*, DESNZ *Data centre electricity consumption in Great Britain, 2020–2024* (Energy Trends, Jun 2026), NESO FES | hand-entered: `dc_power.csv`, `dc_power_outlook.csv` | when a new report is published (IEA yearly, LBNL every few years, NESO FES each July) |
| Power | Data centres' share of total demand | the TWh above ÷ Ember yearly demand for the same year | the share is computed; demand automated from Ember, with `demand.csv` as the fallback | Ember updates yearly (spring) |
| Power | Total electricity demand | Ember yearly full release, long format (`storage.googleapis.com/emb-prod-bkt-publicdata/public-downloads/yearly_full_release_long_format.csv`) | yes. The ~40 MB file is streamed and only the `Demand`/`TWh` rows for USA, GBR, CHN, HKG and World are kept, cached and snapshotted | daily check |
| Power | Largest AI supercomputer by power, and power by country | Epoch AI GPU clusters (`epoch.ai/data/gpu_clusters.csv`) | yes | daily check |
| Capex | Quarterly capex of Microsoft, Alphabet, Amazon, Meta, Oracle | SEC EDGAR companyfacts JSON (`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`), tags `PaymentsToAcquirePropertyPlantAndEquipment` (Amazon: `PaymentsToAcquireProductiveAssets`). Each file is cut down to these tags before caching | yes | daily check; new quarters about 5 weeks after quarter end |
| Compute | Frontier training compute, growth a year, models over 1e25 FLOP by country | Epoch AI notable models (`epoch.ai/data/notable_ai_models.csv`) | yes | daily check |
| Chips | Quarterly revenue: Nvidia, AMD | SEC EDGAR companyfacts (`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`) | yes | quarterly |
| Chips | Quarterly revenue: TSMC (USD), ASML (EUR), SMIC (USD) | company IR pages | hand-entered: `chip_revenue.csv` | each results day (mid-Jan/Apr/Jul/Oct for TSMC and ASML; SMIC about 6 weeks after quarter end) |
| Chips | Share prices rebased to 100: NVDA, TSM, ASML, AMD, AVGO, MU, INTC | Nasdaq quote API (`_base.nasdaq_daily`) | yes | daily |
| Supply chain | <10nm capacity share by country, 2022 and 2032 projection | SIA/BCG *Emerging Resilience in the Semiconductor Supply Chain* (May 2024) | hand-entered: `capacity_share.csv` | when SIA/BCG publish an update |
| Supply chain | Fab milestones (TSMC Arizona, JASM Kumamoto, ESMC Dresden, Rapidus, Intel Ohio) | company press releases | hand-entered: `fabs.csv` | as announced |
| Supply chain | Export-control timeline (US, Netherlands, Japan, China; Hong Kong under the China rules) | BIS, MOFCOM, METI, Dutch government, company filings | hand-entered: `export_controls.csv` | as announced |

How the numbers are built:

- **EDGAR quarters.** Cash flows are filed year to date, so a quarter is the year-to-date figure minus the one a quarter shorter with the same start; Q4 is the 10-K year minus nine months. A later filing (a restatement) replaces an earlier one. Fiscal quarters are placed in the calendar quarter that holds most of them (period end minus 45 days): Oracle's quarter to end-August is Q3, Nvidia's to late October Q3. The SEC answers 403 unless the User-Agent has the form `Name email`. From Railway, `Dashboards admin@<site domain>` answers and a descriptive User-Agent with a URL does not. Set `SEC_UA` on Railway to use a real contact address.
- **Frontier models.** A model counts as frontier when it is in the top ten by training compute of everything released up to its date. Growth a year is the slope of log10(compute) of frontier models since 2018.
- **Share of electricity.** Data-centre TWh ÷ total demand for the same year. Ember wins over `demand.csv` for every year it has.

## Hand-entered files

All use the repository's CSV format (`date,series,value,source,note`, or the columns shown). Yearly figures are dated 1 January of the year; quarterly revenue is dated at the quarter end.

| File | Rows | Columns |
|---|---|---|
| `dc_power.csv` | data-centre electricity, TWh, by region and year | date, series (US, China, UK, World), value, source, note |
| `dc_power_outlook.csv` | published projections, each with its starting year so the dashed line has two points | date, series, value, source, note |
| `demand.csv` | fallback total demand, TWh, used only where Ember has no figure | date, series, value, source, note |
| `chip_revenue.csv` | TSMC, ASML (EUR), SMIC quarterly revenue in billions | date, series, value, source, note |
| `capacity_share.csv` | % of world <10nm capacity by region, 2022 and 2032 | date, series, value, source, note |
| `fabs.csv` | fab milestones | date, site, country, event, source, note |
| `export_controls.csv` | export-control steps | date, market, event, source, note |

**Every row marked `verify` was entered from memory** when the dashboard was built (the build machine could not reach the sources). Check each against its cited page and remove `verify` from the note, or correct the value. The Power rows were checked on 6 Nov 2026: US 2014 and 2023 confirmed (2014 corrected to 58 TWh), UK replaced by DESNZ's Great Britain estimate (4.5 TWh in 2024, 4.1 in 2023; it counts only colocation, managed and hyperscale sites, so it is lower than the old 7 TWh), US 2018 and the three IEA rows still `verify` because the LBNL PDF and iea.org could not be opened. The TSMC rows were checked on 7 Nov 2026 against TSMC's results pages and earnings releases: 4Q23, 2Q24, 4Q24, 1Q25 and 3Q25 confirmed as entered; the other six (1Q23 to 3Q23, 1Q24, 3Q24, 2Q25) were checked on 8 Nov 2026 against their own earnings releases (SEC 6-K) and also match as entered, so no TSMC row is marked `verify` any more. SMIC was checked on 9 Nov 2026 against its own results announcements on HKEX (4Q23 and 1Q25, which also print the prior and year-ago quarters): 3Q23, 4Q23, 1Q24, 4Q24 and 1Q25 match as entered; later the same day 1Q23, 2Q23 and 2Q24 were matched against their own HKEX announcements and 3Q24 against SMIC's release text, all as entered; 2Q25 and 3Q25 were matched on 10 Nov 2026 against the quarterly table in SMIC's 2025 annual report (HKEX, 8 Apr 2026), so no SMIC row is marked `verify` any more. The export-control rows were checked on 10 Nov 2026 by finding each official release by its title (no page could be opened from that run): the six US rules of Oct 2022, Oct 2023, Dec 2024, Jan 2025, Apr 2025 (Nvidia's 8-K) and May 2025 now cite the exact BIS, Federal Register or SEC page and are cleared; the Hong Kong row was corrected (30 Jun 2020 was the suspension of licence exceptions; Hong Kong was treated as China from the 23 Dec 2020 rule); China's two MOFCOM steps, Japan, the Netherlands and the Aug 2025 H20 licences stay `verify` because no official page was found. The SIA/BCG capacity shares were checked on 11 Nov 2026 against the report PDF (BCG's copy; Exhibit 6, p.14): only the text extracted, not the chart, so US 2022 = 0% is cleared from the p.13 text and the other eleven stay `verify`. The text questions two seeds: it says <10nm logic was 'almost 100%' in South Korea and Taiwan in 2022 (China 8% may be too high) and that Europe and Japan host '~12%' in 2032 (Japan 12% plus Europe 2% may double-count). Most uncertain elsewhere: the SIA/BCG shares other than Taiwan's 69% → 47% and the US's 0% → 28%, and the exact dates of some fab milestones.

## Gaps

- **Hong Kong data-centre electricity.** No official series exists. CLP and HK Electric do not break out data centres, and EMSD's *Hong Kong Energy End-use Data* folds them into commercial use. The Power tab says so. If EMSD or the Digital Policy Office publishes a figure, add it to `dc_power.csv` as series `Hong Kong` and `demand.csv` (Hong Kong total, about 45 TWh, from EMSD), and the share appears without a code change.
- **UK data-centre outlook.** NESO's FES 2025 data workbook has a data-centre demand line by pathway; add it to `dc_power_outlook.csv` as `UK (NESO ...)`.
- **SMIC share price** is listed in Hong Kong (0981.HK) and is not on Nasdaq. Yahoo is blocked from Railway, so it is not drawn.

## Requests for shared code

- `data/README.md` lists the dashboards in a table: add the row `| AI Compute, Power & Chips | /compute-chips | [compute-chips/README.md](compute-chips/README.md) |`. The root `README.md` table also needs this dashboard.
- `_base.fetch` keeps the whole body in memory and on disk. Large files (Ember's yearly CSV, EDGAR companyfacts) need it cut down first, so this module has its own `slim_fetch`: the same cache, snapshot, stale and `/api/health` behaviour, with a `keep(line)` filter or `reduce(text)` hook. A `reduce=` parameter on `_base.fetch` would let it go.
- `PROBE_URLS` could add `"ember yearly"`, `"epoch notable"` and `"sec companyfacts"` (with the SEC User-Agent) so `/api/probe` shows them.
