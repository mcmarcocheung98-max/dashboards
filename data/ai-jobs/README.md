# AI Jobs vs Law & Finance (`/ai-jobs`)

Whether AI hiring is growing at the expense of the professions: Indeed job postings for software and data roles (where AI jobs sit) against legal, banking and finance, accounting and insurance, in the US and UK; the share of all postings that mention AI; and payroll headcount in those industries. Almost all automated.

## What it shows

| Tab | Cards | Series |
|---|---|---|
| Openings | Sector table (US / UK switch) | Postings index now, vs February 2020, vs a year ago, for six sectors |
| | Job postings by sector | Software Development, Data & Analytics, Legal, Banking & Finance, Accounting, Insurance, and all postings (1 Feb 2020 = 100) |
| | Share of all job postings that mention AI, by country | US, UK, Canada, Germany, France, Australia, Ireland, Italy, Netherlands, with a latest / year-ago table |
| Headcount | US payroll employment | Legal services; finance & insurance; securities & investments; computer systems design; all private, with yearly and since-2020 change |
| | Headcount since February 2020 (= 100) | The same five, indexed |
| | Change on a year earlier | The same five, % |
| | UK workforce jobs | Legal and financial services from `uk_headcount.csv` (empty until filled) |
| AI vs the professions | AI-related vs law & finance postings | Average of the two AI sectors against the average of the four professions |
| | The ratio | AI-sector index ÷ professions index |
| | AI mentions as a share of all postings | The AI share for the chosen country |

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Postings index by sector, US and UK | [Indeed Hiring Lab Job Postings Index](https://github.com/hiring-lab/job_postings_tracker), files `US/job_postings_by_sector_US.csv` and `GB/job_postings_by_sector_GB.csv`; aggregate files for "all postings" | Daily data, refreshed weekly | Automated |
| AI share of postings, by country | [Indeed Hiring Lab AI Tracker](https://github.com/hiring-lab/ai-tracker), file `AI_posting.csv` | Daily data, refreshed monthly | Automated |
| US payroll employment | BLS Current Employment Statistics via FRED: [CES6054110001](https://fred.stlouisfed.org/series/CES6054110001) legal services, CES5552000001 finance and insurance, CES5552300001 securities and investments, CES6054150001 computer systems design, CES0500000001 all private; seasonally adjusted, thousands | Monthly, first Friday | Automated (FRED's CSV, fetched with curl because FRED rejects Python's HTTP client) |
| UK workforce jobs | [ONS JOBS03](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/workforcejobsbyindustryjobs03), legal activities and financial & insurance activities, thousands | Quarterly | Hand-entered: `uk_headcount.csv` |

Indeed data is CC BY 4.0 and must credit Indeed Hiring Lab (the footer does). BLS data is public domain; ONS data is Open Government Licence v3.0.

## How it is calculated

- Indeed's index is seasonally adjusted postings relative to 1 February 2020 = 100, 7-day average; the page shows weekly averages to keep it light.
- **AI share** is the share of postings whose text includes AI terms (machine learning, data science, generative AI and similar). It counts mentions, not AI engineering jobs: a legal job asking for familiarity with AI tools counts.
- **The ratio** is the mean of the two AI-sector indexes divided by the mean of the four profession indexes. Above 1: software and data postings have held up better than the professions since February 2020; below 1: the opposite.
- **Since 2020** on the Headcount tab is against February 2020, the pre-pandemic month Indeed also uses, so the two tabs line up.

## Keeping it up to date

**Automated:** Indeed's files and FRED are fetched daily. Indeed's sector file is about 12 MB; it is filtered to the six sectors on the server. If Indeed renames a sector, it disappears from the table; the names are listed in `SECTORS` in `app/topics/ai_jobs.py`.

**`uk_headcount.csv`** (`date,series,value,source,note`): each quarter, open the ONS JOBS03 workbook, copy the UK total for "Legal activities" (SIC 69.1) and "Financial and insurance activities" (SIC K) in thousands; `date` is the first month of the quarter. Example:

```
2025-06-01,Legal activities,360,https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/workforcejobsbyindustryjobs03,Jun 2025 release
```

The two seed rows have empty values on purpose and are ignored until filled.

## Checking it

```
pytest -m network tests/test_sources.py -k "indeed or fred"
```

Local preview: `python -m app.server`, then open `/ai-jobs`.

## Known gaps

- UK headcount is hand-entered and empty until filled; the card says so.
- "Openings" are Indeed postings, not all vacancies; Indeed's own methodology notes apply.
- There is no separate "AI occupation" series: the AI share counts mentions in any posting, and the software + data sectors are a proxy for where AI roles are advertised. Lightcast and LinkedIn publish narrower AI-occupation counts, but not as free time series.
- FRED's CSV endpoint was not reachable from the build environment; the first deploy should confirm the Headcount tab fills.
