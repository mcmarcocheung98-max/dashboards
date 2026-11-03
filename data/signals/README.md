# Signals (`/signals`) and the daily newsletter

One place for the owner's approved signal per dashboard, its watch point, and whether it is crossed. Module `app/topics/signals.py`
on top of `app/signals.py`; page `app/static/topics/signals.js`; the approved list in `watchlist.json`. Category: Signals (first on the
index page). The front page shows each dashboard's top line from `/api/signals/front`.

## The approved list

`watchlist.json`: per dashboard slug, `[{key, signal, watch}]`, approved by the owner on 3 Nov 2026 (BTC Cycles, Altcoin Study and
Memecoins deliberately left out for now). Changing a watch point is an edit to this file. The two crypto
dashboards are also left off the board, the front-page line and the email (`SKIP` in `app/signals.py`) until their signals are approved.

## How a dashboard wires its signals

Add `SIGNALS()` to the dashboard module, next to `READINGS()`, returning one row per key in its watchlist entry:

```python
def SIGNALS():
    d = cached_payload("prices")          # read what the endpoints already cache; never download here
    yoy = d["now"]["yoy"]
    return [{"key": "price_yoy", "tab": "prices", "label": "London price change on a year", "value": yoy, "unit": "%",
             "lean": 1 if yoy > 0 else -1, "watch": "turns negative, or passes +5%", "crossed": yoy < 0 or yoy > 5}]
```

- `value` is the current figure (number or short text), `unit` an optional suffix, `lean` +1/0/−1 as the dashboard defines it.
- `crossed` is the dashboard's own test of its watch point; `note` (optional) says why.
- A key missing from `SIGNALS()` shows as "not wired yet"; extra rows beyond the list are shown too.
- Cheap: it runs on every board build (cached five minutes) and at the daily snapshot.

## Endpoints

| Endpoint | What |
|---|---|
| `/api/signals/board` | every dashboard: approved rows merged with its `SIGNALS()`, its first three readings, wired and crossed counts |
| `/api/signals/front` | one line per dashboard for the index page: a crossed watch point, else the first wired signal, else the first reading |
| `/api/signals/flips` | readings that flipped since yesterday, across dashboards (from each dashboard's daily snapshot) |
| `/api/signals/newsletter` | today's email: `subject`, `html` (inline styles, email-safe), `text` |
| `/newsletter` | the same email as a page, for preview and for the workflow to fetch |

## The newsletter

`.github/workflows/newsletter.yml` runs at 07:35 UTC: it fetches `/api/signals/newsletter`, attaches the HTML and text to the run, and
sends it through Gmail SMTP when the repository secrets `MAIL_USERNAME`, `MAIL_PASSWORD` (a Gmail app password) and `NEWSLETTER_TO`
are set. Sections: watch points crossed, one signal per dashboard, what flipped since yesterday, and the owner's open action items.

## Readings

`crossed` (−1 while any watch point is crossed) and `wired` (neutral).
