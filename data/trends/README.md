# Search & Social Trends (`/trends`)

**The question:** what are people paying attention to, and is it rising or fading? And does attention to each of this site's themes
move with that theme's own numbers?

Six tabs. Data at `/api/trends/<overview|search|social|rising|regions|reality>`. `/api/trends/layout` (not a tab) shows what the server
gets back from every source (Wikimedia, the MediaWiki title API in English and Chinese, HN Algolia, Bluesky, Reddit's three addresses,
GitHub, Google Trends, this site's own API), the title each article resolved to, how many days of pageviews are stored per topic,
what the last background run could not get, and every time series found in each other dashboard's payload (to fix a path in
`reality.csv`). Read it with Actions → show-json.

Not investment advice.

## What each tab shows

| Tab | Top card (follows the timeline) | Charts and tables |
|---|---|---|
| Overview | The six biggest theme attention indices | Attention index per theme (weekly, log scale, 100 = usual); fastest-rising topics this week (z-score bars); rising and fading tables; themes with links to their dashboards |
| Search | Weekly views of all tracked topics, and the three most-viewed topics | All topics' weekly views; the five most-viewed; one small chart per theme; Google Trends (hand-entered); breakouts in the last 30 days; every topic with the article title the server resolved |
| Social | HN stories and comments a week, the biggest Bluesky keyword, the most-starred AI repo | HN stories and comments per week (top six topics and the total); HN table vs 4 and 13 weeks; Bluesky posts a day; GitHub stars; Reddit subscribers and active users |
| Rising & fading | The attention z-score of the biggest movers | Weekly z-scores of the four fastest-accelerating and three fastest-fading topics; last week vs its 13-week average for every topic; 4-week average crossing the 13-week (up and down) |
| US / UK / HK | Attention index of English Wikipedia (global), UK pages and Chinese Wikipedia | The three indices; English vs Chinese per theme; the UK and Chinese pages with their z-scores; Google Trends by region (hand-entered) |
| Attention vs reality | Each theme's Wikipedia views a day (monthly) | Per theme: attention (left axis) against that dashboard's headline series (right axis), correlation of levels and of 3-month changes, and the lag (−3 to +3 months) where the changes line up best |

Hover a chart to see that date's figures in the top card, click to keep the date, "Back to latest" to return. Every figure in the top
card is the same series a chart on that tab draws.

## The measures

- **Weekly views:** daily Wikipedia pageviews (users only: Wikimedia excludes bots and crawlers) summed Monday to Sunday; a week counts once all seven days are in.
- **Attention z-score:** `(log(1 + views this week) − mean of the previous 52 weeks) / their standard deviation` (sd floored at 0.05), once a topic has 26 weeks of history. Log, so a small topic doubling counts as much as a big one doubling.
- **Attention index:** each week's views as a share of the topic's own average over the previous 52 weeks, ×100; a theme's or region's index is the geometric mean over its topics (a week needs at least half of them).
- **Breakout:** a day at least twice the topic's median of the previous 8 weeks and more than 4 robust deviations (1.4826 × MAD of log views) above it.
- **Acceleration:** last week's views over the average of the 4 (and 13) weeks before it, minus 1. **Crossing:** the 4-week average moved above (up) or below (down) the 13-week average in the last two weeks.
- **Attention vs reality:** monthly averages of the theme's daily views (the month in progress is left out) against the other series' last value in each month; correlation of log levels and of 3-month log changes; the lag where `corr(change in attention, change in the series k months later)` is largest in size. Positive lag = attention moves first.

## READINGS (what changed since yesterday)

One reading per tracked topic: its attention z-score (the latest full week). **Lean +1** when z ≥ +1 (attention rising, unusually high for that topic), **−1** when z ≤ −1 (fading), 0 between. English-Wikipedia topics are filed under Overview, UK and Chinese pages under US / UK / HK. Read from the cached Overview payload only.

## Sources and cadence

| What | Source | Automated? | Cadence |
|---|---|---|---|
| Daily pageviews per article, English and Chinese Wikipedia, from 2016 | Wikimedia REST API `metrics/pageviews/per-article/<lang>.wikipedia/all-access/user/<title>/daily/<from>/<to>` | yes; the history is downloaded once, then only the last two weeks again | daily, 0.3 s apart |
| Article titles after redirects and Chinese script conversion | MediaWiki `api.php?action=query&redirects=1&converttitles=1`, 40 titles a request | yes | monthly |
| HN stories and comments per topic per week | `hn.algolia.com/api/v1/search_by_date?query=…&tags=story|comment&numericFilters=created_at_i…` (nbHits) | yes; 26 weeks kept, complete weeks not asked again except the last two | daily, 0.4 s apart |
| Bluesky posts per keyword per day | `api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=…&since=…&until=…` (up to 5 pages of 100) | yes, logged once a day, topics with `social=y` | daily, 1 s apart |
| Reddit subscribers and active users | `www.reddit.com`, then `old.reddit.com`, then `api.reddit.com` `/r/<sub>/about.json` | yes, logged once a day; **hand-entered** in `reddit.csv` when the server is refused | daily, 3 s apart |
| GitHub stars and forks | `api.github.com/repos/<repo>` (60 requests an hour unauthenticated; 10 a day used) | yes, logged once a day | daily |
| Google Trends | trends.google.com | **hand-entered**: `gtrends.csv` | monthly |
| The other dashboards' headline series | this site's `/api/<slug>/<endpoint>` (the server itself; set `TRENDS_SITE` to read another copy of the site) | yes, through `fetch` with a snapshot | twice a day |

Every download happens in the background job `fill()` (every 6 hours, like the other paced dashboards): one request at a time per
site, `PACE` seconds apart. Pages only read what the fill stored. The store lives on the snapshot volume in `/app/snapshots/trends/`:
`wiki.json` (daily views per topic), `titles.json`, `hn.json`, `log.csv` (Bluesky, Reddit and GitHub, one row per day, since launch) and
`state.json` (what the last run got). In `/api/health` each source is listed once, under a stable address, not once per download:
fresh when any of its downloads worked in the last run, stale (since its last good run) when none did.

**Checked on the server (2026-10-26, `/api/trends/layout` from Railway):**

- Wikimedia pageviews (English and Chinese) and the MediaWiki title API: **200**. Every article resolved except 香港房地產 (no such page on Chinese Wikipedia; removed). Redirects followed: Zoox (company) → Zoox, Mortgage loan → Mortgage, Zoopla → Houseful (company), Stamp Duty Land Tax → Stamp duty in the United Kingdom, Housing crisis in the United Kingdom → Affordability of housing in the United Kingdom, 宝可梦 → 宝可梦系列, 恒生指数 → 恒生指數; 宝可梦集换式卡牌游戏 and 气候变化 converted to their traditional-script titles.
- HN Algolia: **200** (its nbHits is marked non-exhaustive for large counts: treat big weekly numbers as estimates).
- GitHub API: **200** (60 requests an hour unauthenticated).
- Bluesky: `public.api.bsky.app` answers **403** to Railway. `api.bsky.app` answered 200 to a bare search, but **403** to the searches the fill makes (with `sort`, `since`, `until`) on the first run. Unauthenticated search looks closed to this server; the Bluesky card stays empty until it opens again or an app password is configured (not done: it would need a shared secret).
- Second run (19:26 UTC): HN 84 of 84 requests answered and GitHub 10 of 10; the HN backfill continues over the next runs.
- Attention vs reality: every other dashboard's payload was read from the server. The paths in `reality.csv` were set from `/layout` → `_reality_paths`: housing has no nominal London series (`london_real`, in today's money), AI uses `ai_share.US`, chips `chips.prices.NVDA`, space `satellites` → `active.cumulative_starlink`, rates `nominal.US`.
- Reddit: **403** on `www`, `old` and `api.reddit.com`. Counts come only from `reddit.csv` until that changes; the fill stops asking after two refusals a run.
- Bluesky and Reddit in `/api/health` (31 Oct 2026): while every answer in a run is a 401/403 refusal, both are filed as `failing` with `handled` (the reason, also shown on the Social tab's card) and raise no source-health alert; any other error (a changed format, a timeout) alerts as before. Re-check the two with `/layout` now and then: if either answers again, the counts resume on their own.
- Google Trends: **429**. Hand-entered only.
- This site's own API at `http://127.0.0.1:8080`: **200**.

## The files here

- `topics.csv`: `key,label,theme,region,lang,article,query,social,source,note`. `theme` is one of `ai, bitcoin, pokemon, robotaxi, housing, climate, prediction, space, chips, china, longevity, rates, demographics`; `region` is `global` (English Wikipedia), `uk` (UK-specific English pages) or `zh` (Chinese Wikipedia); `article` is the Wikipedia title (redirects and, for Chinese, simplified or traditional script are resolved by the server); `query` is the Hacker News and Bluesky search term (blank: not searched); `social=y` also counts it on Bluesky. Titles marked `verify` were written from memory: `/api/trends/layout` → `_titles` shows what each resolved to (null = no such page).
- `repos.csv`: `repo,label,source,note`, the GitHub repositories whose stars are logged.
- `subreddits.csv`: `subreddit,theme,source,note`.
- `reddit.csv`: hand-entered Reddit counts, `date,series,value,source,note` with series `<subreddit>|subscribers` or `<subreddit>|active`. They fill in days the server could not read.
- `gtrends.csv`: hand-entered Google Trends points, `date,series,value,source,note` with series `<keyword>|<geo>` (`world`, `US`, `GB`, `HK`, …). The source is the Google Trends explore page the value was read from (its window decides what 100 means). Rows written from memory say `verify` in the note.
- `reality.csv`: `theme,slug,endpoint,path,label,log,source,note`. `path` is a dotted path into that endpoint's JSON to a list of `[unix seconds, value]` points; `*` takes the longest series under what came before (`monthly.*`). `log=y` draws the series on a log scale. A wrong path shows the series that do exist on the card and in `/layout`.

## Adding a topic

One line in `topics.csv`; the next background run downloads its whole history. A topic needs 26 weeks of views before it has a
z-score, which Wikipedia's history gives at once (unless the article is new).

## Requests for shared code

None needed. Two notes for whoever maintains the shared files:

- `_base.fetch` keys its snapshot and `/api/health` entry by URL, so a source whose address carries a date range (Wikimedia, HN, Bluesky) would leave one snapshot file and one health row per day. This dashboard downloads with `_base._download` and keeps its own store instead, filing one health entry per source in `_base.HEALTH` / `_base.STALE` under a stable address. A `fetch(..., key=...)` argument for a stable snapshot and health key would let it use the shared path.
- `/api/trends/reality` reads the other dashboards through the server's own HTTP API at `http://127.0.0.1:$PORT`. If that ever becomes a problem (a slow cold endpoint), a shared `topics.read_payload(slug, name)` that returns an endpoint's cached payload would be the in-process alternative without importing other modules.
