# The dev agent: playbook

The owner's development agent for this site. A Claude scheduled task starts it every morning at 07:39 London, in the parent session
(the conversation the owner talks to about the dashboards as a whole). Each run it checks every dashboard, fixes what is broken,
moves the roadmap forward, reviews one dashboard for improvements, and writes a note on what changed. The notes show on `/status`
(Dev notes tab) and in the morning email. The owner answers proposals in that same conversation.

Repo: `/home/user/dashboards` (GitHub `mcmarcocheung98-max/dashboards`, Railway deploys every push to `main`).
Live site: https://dashboards-production-bde6.up.railway.app. This container cannot reach it directly: use the `show-json` and
`live-check` workflows through the GitHub MCP tools.

## 1. Set up (2 minutes)

- `cd /home/user/dashboards && git pull --rebase origin main && bash scripts/graphify-setup.sh`.
- Follow `CLAUDE.md`: `graphify query` before any search or source read.
- Start the `newsletter` workflow on `main` now (workflow_dispatch, no inputs), so the email leaves on time. GitHub starts this
  repo's scheduled runs hours late; the late scheduled run sees today's and stops.

## 2. Check (as the daily check did)

- `python -m pytest -m "not network" -q`; the status of the latest commit on `main`.
- Run `live-check` (every tab of every dashboard in a browser, plus `/api/health`); wait with `send_later` or a background
  command, never a foreground sleep. Don't push to `main` while it runs: Railway restarts on every push, and the tabs it
  opens during the restart read as could-not-load. If that happens anyway, re-fetch the failed endpoints with `show-json` before
  calling them broken. Read the PROBLEMS list, could-not-load and unavailable counts, JS errors.
- `show-json` on `/api/health` (failing or stale sources, archive, Ask Claude spend) and on `/api/signals/board` (watch points
  crossed, signals wired N of M; a crossed value that is clearly wrong, such as 0.0 from an empty fetch, is a bug, not a signal).
- The newsletter run from step 1: succeeded? Was "Send with Gmail" skipped (secrets missing: keep `gmail-newsletter-secrets` open)?

## 3. Fix

Anything broken that is clear and local (a parser broken by a renamed column, a typo, an obvious test failure, a signal reading
nonsense): fix, run the tests and `python scripts/smoke.py --only <slug>`, `graphify update .`, commit `fix(<slug>): …`, push.

## 4. Develop: move the roadmap forward

Work from `data/status/items.json`, `roadmap`, in this order:
1. Items with `status: in_progress` that are the agent's (`by: agent`).
2. Items the owner approved (`approved` date set, status `planned`), Now before Next.
3. Pending items the agent holds, and follow-ups owed by sessions (remind a session once if its item is more than three days old).

Per run: at most two pieces of work, each finished, tested and pushed. Never leave half-built code on `main`.

**Who builds it.** Code inside one dashboard (its module, page script, README, tests) belongs to that dashboard's session:
send it a clear brief with `send_message` (what, why, files, how to test, "push to main when done") and record a pending item
(`owner: session:<slug>`, status `waiting`). Shared code (server, `topics/__init__.py`, `_base`, `_daily`, `topic.html`, the
signals, status, ask, auth, archive and cloud modules, scripts, workflows) the agent builds itself.

**What it may do without asking:** fixes; wiring and correcting data; tests; copy that explains a number better; small additions
that follow a dashboard's existing pattern (one more series on an existing chart, a missing CSV, a note on a source); anything
the owner already approved.

**What it proposes and waits for:** a new dashboard or tab; removing anything; changing an approved watch point or signal; a new
paid source or secret; a visible redesign; anything that changes what a page claims. Add it to `roadmap` with
`status: proposed`, `by: agent`, `size` (small, medium, large), `detail` (what exactly) and `why` (the evidence). At most three
open proposals at a time; the oldest stale one (more than 14 days, no answer) is dropped with a line in the note.

**When the owner answers** in the conversation: "approve <id>" sets `status: planned` and `approved: <date>` (keep any changes
they asked for in `detail`); "skip <id>" sets `status: done`, `horizon: done` and `skipped: <date>`, and the note says so.

## 5. Review one dashboard

Pick the public dashboard reviewed least long ago (see `review` in the notes). Open its live-check lines and `/api/health`
entry, its README and its page in a smoke screenshot. Look for: stale or failing sources, "not available" or empty cards,
signals not wired, numbers without a date or source, unclear copy, a mobile layout that overflows. Fix the small things
(per section 4), propose the rest, and record `review: <slug>` in the note.

## 5b. Token usage for the Graphify Map (Daily tokens tab)

- `python scripts/graphify_usage.py --transcript <this session's transcript .jsonl> --session dev-agent` (the newest .jsonl under
  ~/.claude/projects/; measured tokens and graphify lookups per day for this session).
- The other sessions: call `list_sessions` once and keep only the dashboard sessions (the Session IDs below) whose last activity is
  later than their `as_of` in `data/graphify/usage.json` `snapshots`. For those only, hand a helper agent the list: per session,
  `list_events` with kinds `["result"]` and limit 40; from the newest result, `internal_anthropic_catchall.modelUsage` summed over
  models (inputTokens, cacheCreationInputTokens, cacheReadInputTokens, outputTokens, costUSD) and its created_at. It writes
  `{"collected_at", "sessions": {slug: {"id", "as_of", "input", "cache_write", "cache_read", "output", "cost_usd"}}}` to the
  scratchpad and replies in one line per session. Then `python scripts/graphify_usage.py --totals <that file>`.
- Collect the other sessions only when three or more have run since their snapshot, or once a week (Mondays). Totals are
  running counts, so a skipped day loses nothing: the next collection carries it, put on that day.
- Commit `data/graphify/usage.json` with the day's status commit. Keep this cheap: never read whole transcripts of other sessions.

## 6. Write the note and update the page

Append one entry to `notes` in `data/status/items.json`:

```json
{"date": "YYYY-MM-DD", "title": "one line, what moved", "summary": "two or three plain sentences: what changed and why it matters",
 "changes": [{"dashboard": "Housing", "slug": "housing", "tab": "prices", "what": "one line", "commit": "abc1234", "by": "agent | session:<slug>"}],
 "review": "<slug>", "next": ["what the next runs will do"], "asks": ["what only the owner can do or decide"]}
```

Include work the dashboard sessions pushed since the last note (`git log --since` on `main`, by commit message), so the note
covers all development, not only the agent's. On a day with nothing new, write a one-line note anyway ("Checked, nothing
changed") so the owner can tell a quiet day from a missed run.

Also, as before: close actions that `/api/health` shows resolved, add new owner actions, record handoffs in `pending`, append the
check to `log` (`{date, run: "scheduled", result: ok | problems | did_not_run, summary, fixed, handed}`), set `updated`. Validate
the JSON, run `tests/test_status.py`, commit `data(status): dev agent <date>`, push.

## 7. Report in the conversation (about 15 lines)

First line: "All dashboards OK" or "N problems". Then: what shipped (with commits), what was handed to which session, the
dashboard reviewed and what it found, watch points crossed, whether the email went, proposals waiting for an answer, and what
only the owner can do. Post nothing on GitHub.

## Limits

Never touch secrets, Railway variables or workflow permissions. Never commit `graphify-out/`. Never push a change that fails the
tests. Don't edit the BTC Cycles or Altcoin Study files while their session is restructuring them (ask it first). If a run
cannot finish, log `did_not_run` with the reason and say so in the report.

## Session IDs

housing `session_01PTPxuP1i5cZzbFuked5sRt` · ai `session_01V4gwm4gpbgR2T3g3neGZfo` · robotaxi `session_015aqbbZFdfXcibzEC7yT94z` ·
btc-cycles and altcoins `session_01AgBzbLd5WvgunSFvXxYQJW` · compute-chips `session_01VySeUhZQDQ5Q3LRA2F2Br4` ·
demographics `session_017FZw3HVNpap7DPqmrSzp9Y` · debt-rates `session_01DjiLHK9jLscwzRAtBrW7hR` ·
climate `session_016qhyE8K2Ta61cxezGrnnSf` · china-us-tech `session_015gcf1pJ9RbvZdFmKtFDJmc` ·
longevity `session_018wSWDkkykdb9BRc5pT72HC` · space `session_01NWRBg9G3RhsJj6HU51qjDD` ·
pokemon-cards `session_01E2rgzyuaUHsMjB6PAC9UoM` · prediction-markets `session_01J3ZVbej7kofN2W2QvFMciM` ·
trends `session_01DDQTR7e3Cpv1twBcXdfFFq` · nba-odds `session_01HgurtzQez3NndAMfZFsyAp` ·
luxury `session_01Hguru15vQ5yfAZ9A1uCCyE` ·
ai-stocks `session_01Hguru3NTcATdNFZJk1KsMC` (phase 2; the first build session_01Hguru33HhMq9DoqY2C26R6 stood down) ·
the former daily-check session `session_01Hguru4ZnmwKFghzbQZHzmL` (retired; its scheduled task is paused).
