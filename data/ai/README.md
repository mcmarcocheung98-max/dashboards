# AI: Jobs & Adoption (`/ai`)

One dashboard for two questions: is AI hiring growing at the expense of law and finance (jobs half), and how fast are firms and people taking up AI tools and agents (adoption half). It replaces the separate `/ai-jobs` and `/ai-adoption` pages; their old links redirect here.

Tabs: Openings · Headcount · Pay · AI vs the professions · Firms adopting · Users · Agents · Skills demand.

## Added in the merge

| What | Where | Source | How |
|---|---|---|---|
| US pay in the same industries (hourly earnings, yearly growth, premium over all private-sector pay) | Pay tab | BLS CES via FRED, the `...03` series: CES6054110003, CES5552000003, CES5552300003, CES6054150003, CES0500000003 | Automated |
| UK and Hong Kong pay | Pay tab | ONS EARN03; C&SD Labour Earnings Survey | Hand-entered: `pay_uk_hk.csv` |
| Hong Kong headcount (financing & insurance, professional services) | Headcount tab | C&SD quarterly employment | Hand-entered: `hk_headcount.csv` |
| IT Systems & Solutions in the AI group | AI vs the professions, toggle | Indeed sector file | Automated |
| US firms expecting to use AI within six months | Firms adopting | Census BTOS National workbook, same parser with the "six months" question | Automated, with `btos_ai_expect_us.csv` as the hand-entered fallback |
| UK and Hong Kong share of firms using AI | Firms adopting | ONS BICS; HKPC / C&SD surveys | Hand-entered: `firm_adoption_uk_hk.csv` |

Indeed's postings index does not cover Hong Kong, so the Openings and ratio tabs switch between the US and UK only.

The new hand-entered files ship with headers and instructions only: there is no free feed, and I did not seed figures I could not check. Fill them from the named sources.

# Jobs half

Whether AI hiring is growing at the expense of the professions: Indeed job postings for software and data roles (where AI jobs sit) against legal, banking and finance, accounting and insurance, in the US and UK; the share of all postings that mention AI; and payroll headcount in those industries. Almost all automated.

### What it shows

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

### Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Postings index by sector, US and UK | [Indeed Hiring Lab Job Postings Index](https://github.com/hiring-lab/job_postings_tracker), files `US/job_postings_by_sector_US.csv` and `GB/job_postings_by_sector_GB.csv`; aggregate files for "all postings" | Daily data, refreshed weekly | Automated |
| AI share of postings, by country | [Indeed Hiring Lab AI Tracker](https://github.com/hiring-lab/ai-tracker), file `AI_posting.csv` | Daily data, refreshed monthly | Automated |
| US payroll employment | BLS Current Employment Statistics via FRED: [CES6054110001](https://fred.stlouisfed.org/series/CES6054110001) legal services, CES5552000001 finance and insurance, CES5552300001 securities and investments, CES6054150001 computer systems design, CES0500000001 all private; seasonally adjusted, thousands | Monthly, first Friday | Automated (FRED's CSV, fetched with curl because FRED rejects Python's HTTP client) |
| UK workforce jobs | [ONS JOBS03](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/workforcejobsbyindustryjobs03), legal activities and financial & insurance activities, thousands | Quarterly | Hand-entered: `uk_headcount.csv` |

Indeed data is CC BY 4.0 and must credit Indeed Hiring Lab (the footer does). BLS data is public domain; ONS data is Open Government Licence v3.0.

### How it is calculated

- Indeed's index is seasonally adjusted postings relative to 1 February 2020 = 100, 7-day average; the page shows weekly averages to keep it light.
- **AI share** is the share of postings whose text includes AI terms (machine learning, data science, generative AI and similar). It counts mentions, not AI engineering jobs: a legal job asking for familiarity with AI tools counts.
- **The ratio** is the mean of the two AI-sector indexes divided by the mean of the four profession indexes. Above 1: software and data postings have held up better than the professions since February 2020; below 1: the opposite.
- **Since 2020** on the Headcount tab is against February 2020, the pre-pandemic month Indeed also uses, so the two tabs line up.

### Keeping it up to date

**Automated:** Indeed's files and FRED are fetched daily. Indeed's sector file is about 12 MB; it is filtered to the six sectors on the server. If Indeed renames a sector, it disappears from the table; the names are listed in `SECTORS` in `app/topics/ai_jobs.py`.

**`uk_headcount.csv`** (`date,series,value,source,note`): each quarter, open the ONS JOBS03 workbook, copy the UK total for "Legal activities" (SIC 69.1) and "Financial and insurance activities" (SIC K) in thousands; `date` is the first month of the quarter. Example:

```
2025-06-01,Legal activities,360,https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/workforcejobsbyindustryjobs03,Jun 2025 release
```

The two seed rows have empty values on purpose and are ignored until filled.

### Checking it

```
pytest -m network tests/test_sources.py -k "indeed or fred"
```

Local preview: `python -m app.server`, then open `/ai`.

### Known gaps

- UK headcount is hand-entered and empty until filled; the card says so.
- "Openings" are Indeed postings, not all vacancies; Indeed's own methodology notes apply.
- There is no separate "AI occupation" series: the AI share counts mentions in any posting, and the software + data sectors are a proxy for where AI roles are advertised. Lightcast and LinkedIn publish narrower AI-occupation counts, but not as free time series.
- FRED's CSV endpoint was not reachable from the build environment; the first deploy should confirm the Headcount tab fills.

# Adoption half

How fast businesses and people are taking up AI tools and agents: the Census Bureau's fortnightly survey of US businesses, paid-subscription data, reported user numbers, a timeline of agent launches, and the share of job postings that mention AI. Half automated, half hand-entered from announcements.

### What it shows

| Tab | Cards | Series |
|---|---|---|
| Firms | Headline figures | Share of US businesses using AI now and a year earlier, the change, share paying for AI tools |
| | Share of US businesses that used AI in the last two weeks | Census BTOS national figure; Ramp AI Index |
| | By sector | Latest BTOS share per sector (empty until the sector file is filled) |
| Users | Reported users | One line per product, joining announcements |
| | Announcements | Every row of `users.csv` with its source |
| Agents | Launches by year | Count of rows in `agent_milestones.csv` per year |
| | Timeline | Agent products and protocols, newest first, each linked to its announcement |
| Skills demand | Share of job postings mentioning AI, by country | Indeed AI Tracker, monthly average |
| | Latest | Share now, a year ago, two years ago, per country |

### Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Businesses using AI (national) | [US Census Bureau, Business Trends and Outlook Survey](https://www.census.gov/hfp/btos/), question "In the last two weeks, did this business use Artificial Intelligence in producing goods or services?", share answering yes | Every two weeks | Automated from the National workbook when its layout is recognised, plus `btos_ai_use_us.csv` by hand (the two are merged; a hand-entered date wins over an automated one) |
| Businesses using AI, by sector | Same survey, Sector workbook | Every two weeks | Hand-entered: `btos_ai_use_by_sector.csv` |
| Businesses paying for AI tools | [Ramp AI Index](https://ramp.com/data): share of US businesses on Ramp's card platform with a paid AI subscription | Monthly | Hand-entered: `ramp_ai_index.csv` |
| Reported users | Company announcements and press reports | As announced | Hand-entered: `users.csv` |
| Agent launches | Company announcements | As announced | Hand-entered: `agent_milestones.csv` |
| AI share of job postings | [Indeed Hiring Lab AI Tracker](https://github.com/hiring-lab/ai-tracker), CC BY 4.0 | Monthly refresh, daily data | Automated (shared with `/ai-jobs`) |

US federal data is public domain. Indeed data must be credited to Indeed Hiring Lab, which the footer does.

### How it is calculated

- **Change** on the Firms tab is the latest share minus the share closest to a year earlier, in percentage points.
- **Users** lines join announcement points; they say nothing about the months between announcements. A row with value 0 is a launch marker and is not drawn.
- **Launches by year** simply counts timeline rows.
- **AI share** is the monthly average of Indeed's daily series.

### Keeping it up to date

**Automated:** the Indeed tracker and the BTOS workbook are fetched daily. The BTOS workbook parser looks for the AI question's "Yes" row; if Census changes the layout, the automated part silently drops out and the hand-entered file carries the chart, so keep that file current anyway.

**`btos_ai_use_us.csv`** (`date,value,source,note`): every fortnight, open [census.gov/hfp/btos](https://www.census.gov/hfp/btos/) → Survey Data → National, find the AI question, copy the "Yes" percentage for the latest reference period. Date = the reference period's end date. Example:

```
2025-09-07,9.7,https://www.census.gov/hfp/btos/,
```

The seed rows all carry `seed value - verify` in `note`: they are rounded figures from Census releases and press coverage. Replace each with the workbook's exact value and clear the note.

**`btos_ai_use_by_sector.csv`** (`date,series,value,source,note`): same workbook, Sector tab; `series` is the sector name as Census writes it (e.g. `Information`, `Professional, Scientific, and Technical Services`). Empty on purpose until filled.

**`ramp_ai_index.csv`** (`date,value,source,note`): the latest monthly figure from [ramp.com/data](https://ramp.com/data). Empty on purpose until filled.

**`users.csv`** (`date,series,value,source,note`): one row per announcement; `series` is the product and metric (`ChatGPT weekly active users`), `value` in users, `source` the announcement or a report quoting it.

**`agent_milestones.csv`** (`date,event,company,kind,source,note`): one row per launch; `kind` is free text used as a label (`agents`, `coding agents`, `protocol`, `tools`).

### Checking it

```
pytest -m network tests/test_sources.py -k "btos or indeed"
```

Local preview: `python -m app.server`, then open `/ai`.

### Known gaps

- The BTOS workbook parser is best-effort and was written without access to the live workbook; until it is confirmed on Railway, treat the national chart as hand-entered.
- Ramp and sector files are empty; their cards say so.
- Usage surveys with a consistent series (Stanford AI Index, McKinsey's annual survey) are not included; they would fit `users.csv` or a new file with the same format.
- "Agent adoption" has no public time series yet; the timeline is a list of launches, not a measure of use.
