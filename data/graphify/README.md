# Graphify Map (`/graphify`)

How this site's own knowledge graph is built, what it shows, and the tokens it saves a Claude session. Module `app/topics/graphify_map.py`,
page `app/static/topics/graphify.js`. Category: About this site.

## Files

| File | What | Refresh |
|---|---|---|
| `map.json` | The graph summarised: clusters (name, size, files, top members), cluster-to-cluster link weights, the 30 most connected nodes and which clusters reach them, link types and confidence counts, cross-file inferred "surprises", and every node and link in compact form | `python scripts/graphify_export.py` after `/graphify` (docs included) or `graphify update .` (code only) |
| `savings.json` | Token benchmark: ten real questions from this project, each answered by `graphify query` (capped at 1,500 tokens) against reading the files a search for its keywords would point to; plus graphify's own corpus-vs-query benchmark | `python scripts/graphify_export.py --bench` (needs the `graphify` command, about a minute) |

Both files are exports of `graphify-out/`, which stays out of git. The Map tab shows the commit the map was built from.

## Tabs

- **Map**: one dot per cluster, sized by members and coloured by dashboard; cluster-to-cluster links; click a cluster for its files and most connected members.
- **Token savings**: for each task, tokens with the map against tokens without it; a price slider turns that into a cost per 100 tasks.
- **How it works**: detect, AST extraction (no model), doc extraction (Claude agents), build and cluster, report and query, with this repo's numbers.
- **God nodes**: the most connected functions and which clusters reach them.
- **Audit trail**: link types, and EXTRACTED / INFERRED / AMBIGUOUS counts.
- **Explorer**: search any node and see its one-step neighbourhood.
- **In practice**: the CLAUDE.md rule and the graphify commands.

## Readings

`nodes` (neutral), `inferred_share` (neutral) and `avg_saving` (+1 when the average saving is 90% or more). They move only when the
export is refreshed.

## Method notes

Tokens are counted as characters divided by four, the usual rule of thumb; real tokenisers vary by about 20% either way. "Without the map"
means every file containing the task's keywords, read whole: that is what a session does when it greps and then reads. It does not count
the tokens the session spends reasoning, which are the same either way.

## Daily tokens tab (`usage.json`, `scripts/graphify_usage.py`)

Tokens the sessions' model processed each day, and the tokens graphify saved.

- **Measured, dev agent:** the parent session's own transcript, day by day (new input, cache writes, cache reads, output; a response
  split over several transcript lines counted once) and its graphify lookups (`graphify query`, `explain` and `path` in Bash calls).
- **Measured, dashboard sessions:** each morning the dev agent reads the running totals in each active session's latest run record;
  the change since the previous snapshot is that session's use, put on the day it was read. The first snapshot (6 Nov 2026) is only
  a starting point, so the dashboard sessions appear in the daily chart from 7 Nov; the By session table shows their totals since
  they started, with the cost at list price.
- **Saved tokens** = lookups x the median saving per question in `savings.json` (about 113k tokens). Lookups are counted only in the
  dev agent's transcript; the dashboard sessions' are estimated at the dev agent's rate of lookups per token since graphify was
  installed (30 Oct), shown as a separate dashed line. Conservative: a file not read also stays out of every later turn's cache
  reads, which is not counted.
- Most of each day's tokens are cache reads: the conversation re-read on every turn. The line "new input and output" leaves them out.
