# AI: Jobs & Adoption (`/ai`)

One dashboard for two questions: is AI hiring growing at the expense of law and finance (jobs half), and how fast are firms and people taking up AI tools and agents (adoption half). It replaces the separate `/ai-jobs` and `/ai-adoption` pages; their old links redirect here.

Tabs: Openings · Headcount · Pay · AI vs the professions · Firms adopting · Users · Agents · Skills demand.

## Source note (Oct 2026)

FRED times out from cloud servers (Railway and GitHub alike), so US employment and pay now come from the BLS public API v1 (no key; two queries a day cover all ten series, 2010 to now). Same BLS series ids as before.

The build container cannot reach ONS, C&SD, Census or Ramp. The parsers were written against what the Railway server saw there in Oct 2026 (read through a temporary `/api/ai/layout` probe, now removed); each one's docstring records the layout it expects.

**UK firms using AI** (ONS BICS): share using at least one AI technology = 100% − "does not currently use" − "not sure", weighted, dated at the end of the survey period. Wave 165 (21 Sep–4 Oct 2026) gives 29.7% of all businesses and 38.1% of those with 10+ employees, which matches ONS's published "around 3 in 10".

## Added in the merge

| What | Where | Source | How |
|---|---|---|---|
| US pay in the same industries (hourly earnings, yearly growth, premium over all private-sector pay) | Pay tab | BLS CES via FRED, the `...03` series: CES6054110003, CES5552000003, CES5552300003, CES6054150003, CES0500000003 | Automated |
| UK and Hong Kong pay | Pay tab | ONS EARN03; C&SD Labour Earnings Survey | Hand-entered: `pay_uk_hk.csv` |
| Hong Kong headcount (financing & insurance; professional, scientific & technical; information & communications) | Headcount tab | [C&SD table 215-16001](https://www.censtatd.gov.hk/en/web_table.html?id=215-16001) via its JSON API (`api/get.php?id=215-16001&lang=en&full_series=1`), persons engaged, quarterly from 2000 | Automated (Oct 2026); `hk_headcount.csv` overrides a quarter |
| London employees by borough and sector, heatmap (legal 691, accounting 692, financial services 64, insurance 65, finance support 66, software & IT 62, information services 63, all jobs) | Headcount tab | [ONS BRES open access via Nomis](https://www.nomisweb.co.uk/datasets/newbrespub), dataset `NM_189_1`, geography `2013265927TYPE424` (the 33 London boroughs), employees, yearly from 2015 | Automated (Oct 2026). Year buttons; shade by employees or by change on a year / since 2019. ONS rounds the figures and suppresses some (shown as –) |
| IT Systems & Solutions and Scientific Research & Development in the AI group | AI vs the professions, toggle | Indeed sector file (both sectors exist in the US and GB files) | Automated |
| US firms expecting to use AI within six months | Firms adopting | Census BTOS National workbook, same parser with the "six months" question | Automated, with `btos_ai_expect_us.csv` as the hand-entered fallback |
| UK share of firms using AI (all businesses; 10+ employees) | Firms adopting | [ONS BICS](https://www.ons.gov.uk/economy/economicoutputandproductivity/output/datasets/businessinsightsandimpactontheukeconomy), sheet `AI Current Usage TS (WTD)` of the newest wave workbook that carries the AI questions (about every sixth wave; the sheet holds the whole series from Sep 2023) | Automated (Oct 2026); `firm_adoption_uk_hk.csv` for extra or Hong Kong points |

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
| | UK employee jobs | Financial & insurance (SIC K) and legal & accounting (SIC 69), thousands, with the change on the same quarter a year earlier |
| AI vs the professions | AI-related vs law & finance postings | Average of the two AI sectors against the average of the four professions |
| | The ratio | AI-sector index ÷ professions index |
| | AI mentions as a share of all postings | The AI share for the chosen country |

### Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Postings index by sector, US and UK | [Indeed Hiring Lab Job Postings Index](https://github.com/hiring-lab/job_postings_tracker), files `US/job_postings_by_sector_US.csv` and `GB/job_postings_by_sector_GB.csv`; aggregate files for "all postings" | Daily data, refreshed weekly | Automated |
| AI share of postings, by country | [Indeed Hiring Lab AI Tracker](https://github.com/hiring-lab/ai-tracker), file `AI_posting.csv` | Daily data, refreshed monthly | Automated |
| US payroll employment | BLS Current Employment Statistics via FRED: [CES6054110001](https://fred.stlouisfed.org/series/CES6054110001) legal services, CES5552000001 finance and insurance, CES5552300001 securities and investments, CES6054150001 computer systems design, CES0500000001 all private; seasonally adjusted, thousands | Monthly, first Friday | Automated (FRED's CSV, fetched with curl because FRED rejects Python's HTTP client) |
| UK employee jobs | [ONS JOBS03: Employee jobs by industry](https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/employeejobsbyindustryjobs03), newest workbook (`jobs03<mon><yyyy>.xls`) linked from the dataset page; financial & insurance = divisions 64 + 65 + 66 (section K), legal & accounting = division 69; UK, thousands, not seasonally adjusted | Quarterly (Mar, Jun, Sep, Dec releases) | Automated (Oct 2026, parser not yet checked on the live workbook); `uk_headcount.csv` adds or overrides a quarter |

Indeed data is CC BY 4.0 and must credit Indeed Hiring Lab (the footer does). BLS data is public domain; ONS data is Open Government Licence v3.0.

### How it is calculated

- Indeed's index is seasonally adjusted postings relative to 1 February 2020 = 100, 7-day average; the page shows weekly averages to keep it light.
- **AI share** is the share of postings whose text includes AI terms (machine learning, data science, generative AI and similar). It counts mentions, not AI engineering jobs: a legal job asking for familiarity with AI tools counts.
- **The ratio** is the mean of the two AI-sector indexes divided by the mean of the four profession indexes. Above 1: software and data postings have held up better than the professions since February 2020; below 1: the opposite.
- **Since 2020** on the Headcount tab is against February 2020, the pre-pandemic month Indeed also uses, so the two tabs line up.

### Keeping it up to date

**Automated:** Indeed's files and FRED are fetched daily. Indeed's sector file is about 12 MB; it is filtered to the six sectors on the server. If Indeed renames a sector, it disappears from the table; the names are listed in `SECTORS` in `app/topics/ai_jobs.py`.

**UK employee jobs (JOBS03)** are read from the newest workbook each day. The parser looks, on the all-employees sheet, for the header row carrying the SIC 2007 division codes and for rows labelled with a quarter ("Jun 2026"); it was written without seeing the live file (ONS is unreachable from the build container), so the network test `test_ons_jobs03` is the check. JOBS03 is published as a legacy `.xls`, which pandas reads only with `xlrd` (see Requests for shared code): until that is installed the card shows hand-entered quarters, if any, and names the reason. JOBS03 is at division level, so legal (69.1) is not separated from accounting (69.2); the London heatmap (BRES) does separate them.

**`uk_headcount.csv`** (`date,series,value,source,note`): only for a quarter the workbook lacks or gets wrong. `date` is the quarter's reference month (March, June, September, December), series `Financial & insurance` or `Legal & accounting`, value in thousands, source the JOBS03 workbook. A row here wins over the automated figure. The file has no rows.

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
| | By sector | Latest BTOS share per NAICS sector, highest first (full sector name on tap) |
| Users | Reported users | One line per product, joining announcements |
| | Announcements | Every row of `users.csv` with its source |
| Agents | Launches by year | Count of rows in `agent_milestones.csv` per year; a filter above it (All, or one `kind`: agents, coding agents, protocol, tools…, with counts) narrows the bars and the timeline |
| | Timeline | Agent products and protocols, newest first, each linked to its announcement |
| Skills demand | Share of job postings mentioning AI, by country | Indeed AI Tracker, monthly average |
| | Latest | Share now, a year ago, two years ago, per country |

### Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Businesses using AI (national) | [US Census Bureau, Business Trends and Outlook Survey](https://www.census.gov/hfp/btos/), question "In the last two weeks, did this business use Super Intelligence or SI (formerly referred to as Artificial Intelligence or AI) in any of its business functions?" (wording since the period ending 16 Nov 2025), share answering yes | Every two weeks | Automated from the National workbook; `btos_ai_use_us.csv` adds a missing period by hand (a hand-entered date wins) |
| Businesses using AI, by sector | Same survey, [Sector workbook](https://www.census.gov/hfp/btos/downloads/Sector.xlsx) | Every two weeks | Automated (Nov 2026): the AI question's "Yes" rows per NAICS code, dated from the National workbook's reference dates; `btos_ai_use_by_sector.csv` adds or overrides a (sector, period) |
| Businesses paying for AI tools | [Ramp AI Index](https://ramp.com/data/ai-index): share of US businesses on Ramp with an observed payment for an AI product or service in the month | Monthly | Automated (Oct 2026) from the records the page embeds: the overall series is the set with exactly `date_month, adoption_rate_pct, mom_change_pp, yoy_change_pp` (Jul 2023 onward); `ramp_ai_index.csv` overrides a month |
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

**Automated:** the Indeed tracker, the BTOS workbook, the Ramp page and the ONS BICS workbooks are fetched daily; when one fails, the last good copy on the snapshot volume is served with a "stale since" note. If a layout changes, the parser raises, `/api/health` shows the source as failing, and the parser's docstring says what it expected.

**`btos_ai_use_us.csv`** (`date,value,source,note`): only for a period the National workbook lacks; copy the "Yes" share from a Census release and cite it. Date = the reference period's end date.

The nine seed rows (Sep 2023 to Sep 2025, 3.7% to 9.7%) were removed in Oct 2026. They were rounded figures from memory, and they belong to the earlier wording ("use Artificial Intelligence in producing goods or services"). The live workbook has only the current wording ("Super Intelligence or SI (formerly ... AI) in any of its business functions"), from the period ending 16 Nov 2025, at 17.3% and rising to 24.6% (period ending 4 Oct 2026). The two wordings are not one series, so the chart starts in Nov 2025, and "a year earlier" appears once a year of the new wording exists.

**`btos_ai_use_by_sector.csv`** (`date,series,value,source,note`): only for a period the Sector workbook lacks or gets wrong; `series` is the NAICS sector name the page uses (e.g. `Information`, `Professional, Scientific, and Technical Services`; codes map to names in `NAICS` in `ai_adoption.py`).

**`ramp_ai_index.csv`** (`date,value,source,note`): only to override a month the page gets wrong or lacks; date = first of the month.

**`users.csv`** (`date,series,value,source,note`): one row per announcement; `series` is the product and metric (`ChatGPT weekly active users`), `value` in users, `source` the announcement or a report quoting it.

**`agent_milestones.csv`** (`date,event,company,kind,source,note`): one row per launch; `kind` is free text used as a label (`agents`, `coding agents`, `protocol`, `tools`).

### Checking it

```
pytest -m network tests/test_sources.py -k "btos or indeed"     # includes the Sector workbook
```

Local preview: `python -m app.server`, then open `/ai`.

### Known gaps

- The BTOS workbook parser was rewritten against the live workbook (Oct 2026, via `/api/ai/layout`): sheet `Response Estimates`, period codes as columns, dates from `Collection and Reference Dates`.
- The Sector workbook parser (Nov 2026) was written for the National workbook's layout plus a `Sector` (or `NAICS`) column, without a live copy to hand (census.gov refused the build environment). If the layout differs, `/api/health` shows `Sector.xlsx` failing, the card says "Not read yet", and `pytest -m network tests/test_sources.py -k sector` names what it found. Ramp's figures cover businesses on Ramp's platform, which lean towards tech and finance, so they run well above the Census share.
- Usage surveys with a consistent series (Stanford AI Index, McKinsey's annual survey) are not included; they would fit `users.csv` or a new file with the same format.
- "Agent adoption" has no public time series yet; the timeline is a list of launches, not a measure of use.

# What changed since yesterday (`READINGS()` in `app/topics/ai.py`)

The server saves the readings once a day; the Overview lists the ones whose lean flipped, and each tab shows its own row of squares. Readings come from cached payloads only, so they never trigger a download.

**+1 = the balance is moving towards AI**: more postings mention AI, AI-sector postings gain on law and finance, tech pay outgrows legal pay, the professions' headcount shrinks, more firms use or pay for AI, a new user high, more agent launches. **-1 = the reverse. 0 = steady** (inside the threshold).

| Tab | Key | Reading | Lean |
|---|---|---|---|
| Openings | `ai_share_us`, `ai_share_gb` | Share of postings mentioning AI | ±0.2 points on a year |
| AI vs the professions | `ai_over_prof_us` | AI-sector ÷ law & finance postings index | ±0.02 on 13 weeks |
| Headcount | `us_legal_yoy`, `us_finance_yoy`, `hk_finance_yoy` | Jobs, change on a year | +1 if down 0.5% or more, -1 if up 0.5% or more |
| Pay | `pay_tech_minus_legal` | Computer systems design minus legal services pay growth | ±0.5 points |
| Firms adopting | `btos_us`, `ramp_us`, `uk_firms` | Share of firms using / paying for AI | ±0.5 points on about 12–13 weeks |
| Users | `chatgpt_wau` | ChatGPT weekly users, latest announced | +1 on a new high |
| Agents | `launches_12m` | Launches in the 12 months to the latest | vs the 12 months before |
| Skills demand | `countries_rising` | Countries where the AI share rose on a year | +1 if more than half, -1 if fewer than half |

# Requests for shared code

- **`app/topics/_base.py` `fetch()`: let a caller validate a reply before it replaces the snapshot.** Today any 200 reply over `min_bytes` overwrites the disk copy. BLS answers an over-limit request with HTTP 200 and `{"status": "REQUEST_NOT_PROCESSED", ...}`, so on 26 Oct 2026 the good BLS data was replaced by an error body and the Headcount and Pay tabs lost their US data. A `validate=callable` argument (raise to reject: keep the old snapshot, mark it stale) would cover this for every dashboard. Until then `ai_jobs._bls_query` keeps its own last-good copy (`bls-good-*.json` beside the snapshots). The same check would also stop a restart from re-downloading when the snapshot is less than `ttl` old, which matters for rate-limited APIs.
- **`xlrd>=2.0` in requirements.txt** (also asked for by housing, 25 Oct 2026; done 31 Oct 2026). ONS publishes JOBS03 (UK employee jobs by industry, Headcount tab) only as a legacy `.xls` (`jobs03sep2026.xls`, 15 Sep 2026); without `xlrd` `pd.read_excel` cannot open it and the UK card falls back to `uk_headcount.csv`.
