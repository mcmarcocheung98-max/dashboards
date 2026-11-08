# AI Model Iteration (`/ai-models`)

The question: **for the leading model families (OpenAI GPT, Anthropic Claude, Google Gemini, Meta Llama and Muse, xAI Grok, DeepSeek, Alibaba Qwen, Moonshot Kimi, Mistral, Zhipu GLM), how fast is each iterating, how much compute went into each generation, how useful is each, how do export controls bear on them, and what does each cost to train and to run?** Not investment advice.

Code: `app/topics/ai_models.py` (data), `app/static/topics/ai-models.js` (cards), `tests/test_ai_models.py` (fixtures, `smoke_patch()`). Built 8 Nov 2026 at the owner's request ("build an AI model iteration dashboard to compare model development between the top models, the computing power, utility, sanctions, cost of development and deployment").

## Tabs and sources

| Tab | Card | Source | Automated? | Cadence |
|---|---|---|---|---|
| Overview | Frontier Arena score, months since the last compute record, cheapest frontier-tier price, Chinese share of the top 20 (follows the timeline) | the other tabs | yes | – |
| Overview | Release timeline across families | `releases.csv` | hand-entered | each major release |
| Iteration | Releases per family per year, days between releases, open-weights share, context windows | `releases.csv` | hand-entered | each major release |
| Compute | Training compute per model (log, by developer), the frontier record, compute per family over its generations, hardware where known | Epoch AI notable models CSV (`epoch.ai/data/notable_ai_models.csv`), fetched once a day by the Compute dashboard (`compute_chips.epoch_models`, CC-BY) | yes | daily check |
| Compute | US vs China frontier | the same file through `china_us_tech.parse_epoch` (single-country models) | yes | daily check |
| Utility | LMArena text top 20 and the score trajectory per family | `arena.csv` (dated top-20 snapshots) plus `china-us-tech/leaderboard.csv` (best US vs best Chinese model per snapshot) | hand-entered | weekly |
| Utility | Artificial Analysis Intelligence Index | `index.csv` | hand-entered (the API needs a key: see Gaps) | as entered |
| Utility | Benchmark table (GPQA Diamond, SWE-bench Verified, FrontierMath) | `benchmarks.csv` | hand-entered until Epoch's Benchmarking Hub CSV answers from the server (see Gaps) | as entered |
| Utility | OpenRouter token rankings | `openrouter_share.csv` | hand-entered | weekly |
| Utility | Wikipedia pageviews per family | Wikimedia REST API, monthly per article, the article named in `families.csv` | yes | daily |
| Sanctions | Export-control timeline with the chips each rule covers | `china-us-tech/controls.csv` (shared) joined by date to `chips_covered.csv` | hand-entered | as rules change |
| Sanctions | Chinese vs US frontier compute against the rule dates | Epoch (as above) | yes | daily check |
| Sanctions | What each Chinese lab reports training on | `china_hardware.csv` | hand-entered | as reported |
| Cost | Training cost per model and per exaFLOP | Epoch's `Training compute cost (2023 USD)` column (its "cost of frontier training runs" estimates, CC-BY) | yes | daily check |
| Cost | Disclosed and reported training costs | `costs.csv` | hand-entered | as reported |
| Cost | Hyperscaler capex, last four quarters | SEC EDGAR through `compute_chips._capex` | yes | quarterly |
| Cost | Deployment prices now, and a price log | OpenRouter models API (`openrouter.ai/api/v1/models`, no key): per-token prices and context lengths of every model from the tracked vendors; each day's prices are appended to `<SNAPSHOT_DIR>/ai-models/prices.csv` on the volume, so a history accrues | yes | daily |
| Cost | Launch list prices since 2023, price per Arena point, the calculator | `prices.csv` (list price per million tokens at launch) and OpenRouter's current list | hand-entered + automated | each launch |

## Method: how the numbers are built

- **Families.** `families.csv` names each family, its developer and country, the English Wikipedia article whose pageviews stand for attention to it, the OpenRouter vendor prefix (`anthropic/`, `deepseek/`...) and a pattern matched against Epoch's organisation field (`Google|DeepMind` → Gemini). Everything else joins on `family`.
- **Release cadence.** Days between a family's consecutive rows in `releases.csv`; the median over all rows and over the trailing 12 months. The `release_cadence` signal is the median over the families of each family's trailing-12-month median. `releases.csv` holds flagship and mid-tier releases and notable reasoning models, not every variant, so the cadence is of major releases.
- **Open-weights share.** Rows with `open = yes` divided by all rows in the year, for all families and for the US and China separately.
- **Frontier compute record.** Epoch's notable models sorted by publication date; a step each time the largest training run to date grew. `record_age_months` is the months since the last step. Compute per family: the largest run so far by that family's organisations.
- **US vs China frontier.** The same file through `china_us_tech.parse_epoch`, single-country models only, the running maximum per country; the gap is log10(US max / China max) in orders of magnitude.
- **Arena snapshots.** `arena.csv` holds, per snapshot date, the rows of the top 20 whose score a source gave (rank, model, family, country, score, open weights). Top score, Chinese share and the best open model's gap are computed over the rows entered, and the page says how many of the 20 are entered. LMArena rescales scores over time, so read gaps and trends, not levels.
- **Price matching.** A model name from `arena.csv`, `prices.csv` or OpenRouter is reduced to letters and digits after dropping a vendor prefix, a date suffix (`-2025-04-16`, `-0528`) and bracketed variants (`(Max)`, `(thinking)`), so `Claude Opus 5.5 (Max)`, `anthropic/claude-opus-5.5` and `Claude Opus 5.5` are one model. OpenRouter's current list wins over a hand-entered launch price for the same model on the latest snapshot; earlier snapshots use launch prices.
- **Cheapest frontier-tier price.** Per snapshot, among models within 50 Arena points of the top, the lowest output price per million tokens. **Price per Arena point** divides a model's output price by its score (the page shows it per 100 points). The calculator multiplies the visitor's monthly input and output tokens by a model's prices in the browser; nothing is stored.
- **Training cost per exaFLOP.** Epoch's cost estimate divided by training compute in units of 1e18 FLOP.
- **Readings** (what changed since yesterday): top Arena score (+1 when higher than at the snapshot before), cheapest frontier-tier price (+1 when cheaper), Chinese share of the top 20 (+1 when it rose).

## Caveats

- **Benchmarks saturate and get gamed**, and labs report their own numbers with different scaffolds and compute budgets. `benchmarks.csv` keeps the figure, the source and the note; prefer Epoch's independent runs when they answer.
- **Arena scores move with the voters** and with LMArena's style control and rescaling; a model's score a year ago is not comparable with today's level. The snapshots are secondary copies until checked on arena.ai.
- **Epoch's compute and cost figures are estimates** with stated uncertainty (an order of magnitude on some), under CC-BY; the page credits Epoch AI.
- **Export-control dates are effective dates** (publication in the Federal Register), not announcement dates, unless the note says otherwise.
- **Prices** are list prices at launch per million tokens for the standard tier; long-context, batch, cached and off-peak rates differ. DeepSeek's and Google's launch rates were promotional and rose later (noted per row). Open-weights models have no list price: a hosted provider's price is used and marked as such.
- **Disclosed training costs** count different things: DeepSeek-V3's $5.576M is the final run at a rental rate and excludes research, ablations, data and staff; Llama 3.1 405B disclosed GPU-hours and the dollar figure here is derived at $2 per GPU-hour; the AI Index figures are Epoch estimates. `basis` says which.
- **The network this was built on** reached only package registries and a few US data hosts, so every 2026 row comes from web-search summaries of secondary trackers rather than the vendor page; those rows carry `verify`.

## Hand-entered files

| File | Rows | Columns |
|---|---|---|
| `families.csv` | one per family | date (first release), family, developer, country, wiki, openrouter, epoch_org, source, note |
| `releases.csv` | major releases since Nov 2022 | date, family, model, developer, country, open (yes/no), context (tokens), modalities, flagship (yes/no), source, note |
| `arena.csv` | LMArena text top-20 rows per snapshot | date, rank, model, family, developer, country, score, open, source, note |
| `index.csv` | Artificial Analysis Intelligence Index points | date, model, family, developer, country, value, version, open, source, note |
| `openrouter_share.csv` | OpenRouter top models by tokens, weekly | date (week end), model, family, developer, country, tokens_t (trillion tokens), share (% of the top 20, if given), source, note |
| `benchmarks.csv` | benchmark scores | date, model, family, benchmark, value (%), source, note |
| `chips_covered.csv` | the chips each export-control step covers; `date` must match a `china-us-tech/controls.csv` row | date, rule, chips, status, source, note |
| `china_hardware.csv` | hardware each lab reports training on (two US rows for scale) | date, lab, country, model, hardware, count, gpu_hours, source, note |
| `costs.csv` | disclosed, reported, estimated or derived training costs, USD million | date, model, family, developer, country, value, basis, source, note |
| `prices.csv` | list prices at launch, USD per million tokens | date, model, family, developer, country, input, output, context, source, note |

**Every row marked `verify`** was entered from memory or from a secondary summary found by web search (the build machine could not open the vendor pages, Wikipedia, Epoch or the leaderboard sites). Check each against its cited page and remove `verify`, or correct it. Anthropic's current prices (Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5) were read from claude.com/pricing on 8 Nov 2026; the January 2026 BIS rule was read from the Federal Register listing.

Weekly upkeep: add the current Arena top 20 to `arena.csv` (one row per model, the same date), the OpenRouter top 10 by tokens to `openrouter_share.csv`, and any new release to `releases.csv` with its launch price in `prices.csv`.

## Signals (proposed, awaiting the owner's approval)

`data/signals/watchlist.json` has an `ai-models` entry with `"proposed": true` on each row:

| Key | Signal | Watch |
|---|---|---|
| `frontier_record_age` | months since the last frontier training-compute record (Epoch) | above 12 months |
| `price_per_point` | cheapest price per million output tokens within 50 Arena points of the top | falls by half on a year, or rises |
| `open_gap` | best open-weights model's Arena gap to the top | under 20 points, or over 100 |
| `china_share_top20` | Chinese developers' share of the Arena top 20 | above 40% or below 10% |
| `release_cadence` | median days between a family's releases, trailing 12 months | under 60 days |

## Gaps

- **Artificial Analysis API.** `https://artificialanalysis.ai/api/v2/data/llms/models` gives the index and prices per model with a free key. Proposed: the owner registers a key and sets `AA_API_KEY` on Railway; until then `index.csv` is hand-entered. The layout endpoint (`/api/ai-models/layout`) probes the host.
- **Epoch Benchmarking Hub.** The hub offers CSV downloads (`epoch.ai/benchmarks/use-this-data`) but the file address could not be read from here. The layout endpoint probes a candidate address; when the real one is known, add a fetch in `_utility_now` and let `benchmarks.csv` fall back.
- **Arena top 20 is partial.** Only rows with a sourced score are entered (8 for Nov 2026), so the Chinese share and the open gap are over the rows entered; the page says so. The weekly snapshot fills it.
- **Gemini 4 Carbon** had no published price on 8 Nov 2026; **Muse Wonder**'s release date was not found.

## Requests for shared code

- `compute_chips.parse_epoch` now also returns `params`, `hardware`, `hw_qty`, `cost`, `open` and `base` where Epoch has them, and `compute_chips.epoch_models()` returns the parsed file; `china_us_tech.controls_rows()` and `china_us_tech.leaderboard_rows()` expose the shared hand-entered timelines. Two 2026 steps (15 Jan 2026 H200 rule, 1 Jun 2026 guidance) were added to `china-us-tech/controls.csv`.
- `PROBE_URLS` could add `"openrouter models"` and `"wikimedia monthly"` so `/api/probe` shows them next to `"epoch notable"`.
