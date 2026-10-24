# AI Tool & Agent Adoption (`/ai-adoption`)

How fast businesses and people are taking up AI tools and agents: the Census Bureau's fortnightly survey of US businesses, paid-subscription data, reported user numbers, a timeline of agent launches, and the share of job postings that mention AI. Half automated, half hand-entered from announcements.

## What it shows

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

## Where the numbers come from

| Series | Source | Cadence | How |
|---|---|---|---|
| Businesses using AI (national) | [US Census Bureau, Business Trends and Outlook Survey](https://www.census.gov/hfp/btos/), question "In the last two weeks, did this business use Artificial Intelligence in producing goods or services?", share answering yes | Every two weeks | Automated from the National workbook when its layout is recognised, plus `btos_ai_use_us.csv` by hand (the two are merged; a hand-entered date wins over an automated one) |
| Businesses using AI, by sector | Same survey, Sector workbook | Every two weeks | Hand-entered: `btos_ai_use_by_sector.csv` |
| Businesses paying for AI tools | [Ramp AI Index](https://ramp.com/data): share of US businesses on Ramp's card platform with a paid AI subscription | Monthly | Hand-entered: `ramp_ai_index.csv` |
| Reported users | Company announcements and press reports | As announced | Hand-entered: `users.csv` |
| Agent launches | Company announcements | As announced | Hand-entered: `agent_milestones.csv` |
| AI share of job postings | [Indeed Hiring Lab AI Tracker](https://github.com/hiring-lab/ai-tracker), CC BY 4.0 | Monthly refresh, daily data | Automated (shared with `/ai-jobs`) |

US federal data is public domain. Indeed data must be credited to Indeed Hiring Lab, which the footer does.

## How it is calculated

- **Change** on the Firms tab is the latest share minus the share closest to a year earlier, in percentage points.
- **Users** lines join announcement points; they say nothing about the months between announcements. A row with value 0 is a launch marker and is not drawn.
- **Launches by year** simply counts timeline rows.
- **AI share** is the monthly average of Indeed's daily series.

## Keeping it up to date

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

## Checking it

```
pytest -m network tests/test_sources.py -k "btos or indeed"
```

Local preview: `python -m app.server`, then open `/ai-adoption`.

## Known gaps

- The BTOS workbook parser is best-effort and was written without access to the live workbook; until it is confirmed on Railway, treat the national chart as hand-entered.
- Ramp and sector files are empty; their cards say so.
- Usage surveys with a consistent series (Stanford AI Index, McKinsey's annual survey) are not included; they would fit `users.csv` or a new file with the same format.
- "Agent adoption" has no public time series yet; the timeline is a list of launches, not a measure of use.
