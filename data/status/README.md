# Actions & Roadmap (`/status`)

The site's own to-do list: action items only the owner can do, pending work in the dashboard sessions and the parent session, the
roadmap, and the daily check's log. Module `app/topics/status.py`, page `app/static/topics/status.js`, data `items.json`. Category: About this site.

## items.json

| List | One item | Who edits it |
|---|---|---|
| `actions` | `id`, `title`, `detail` (what it unblocks and how to do it), `area`, `priority` high/medium/low, `since`, `status` open/done, `done` date, `link` | The daily check closes what it sees resolved in `/api/health` and adds new ones; the parent session and the owner by hand |
| `pending` | `id`, `title`, `detail`, `owner` (`parent`, `routine`, `sessions`, or `session:<slug>`), `status` in_progress/waiting/blocked/done, `since` | The daily check records handoffs; sessions report progress through the parent |
| `roadmap` | `id`, `title`, `detail`, `area`, `horizon` now/next/later/done, `status` planned/in_progress/done, `done` date | The parent session, from `docs/ROADMAP.md` and the owner's asks |
| `log` | `date`, `run` scheduled/manual, `result` ok/problems/did_not_run, `summary`, `fixed` (commit hashes), `handed` (session names) | The daily check appends one entry per run |

`updated` is the date of the last edit. Dates are ISO (`YYYY-MM-DD`); the page shows ages from them.

## Readings

`open_actions` (−1 while any high-priority action is open), `pending` (neutral), `roadmap_done` (+1) and `last_check` (+1 when the last
run was ok, −1 otherwise).

## Method

Items are written by people and sessions, not computed; the page only sorts and counts them. Close an action by setting `status` to
`done` and `done` to the date rather than deleting it, so the Done list keeps the history.

## Also on each daily check: signals and the newsletter (added 3 Nov 2026)

The morning check reads this file, so these steps live here as well as in its prompt.

- Read `/api/signals/board` (show-json workflow). Report every watch point crossed (dashboard, signal, value, watch point) and how
  many approved signals are wired (`totals.wired` of `totals.signals`). From 6 Nov, remind the session of any dashboard whose signals
  are still "not wired yet", in one line, pointing to `data/signals/README.md`. Mark `p-signals-wiring` done once all are wired.
- Check that morning's `newsletter` workflow run (07:35 UTC). If it failed, read the log and fix it when small. If "Send with Gmail"
  was skipped, the secrets are still missing: keep `gmail-newsletter-secrets` open. Close it on the first run whose send step ran.
- In the report: the watch points crossed, signals wired (N of M), and whether the newsletter went out.
