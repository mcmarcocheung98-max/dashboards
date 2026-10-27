# Ask Claude

Every tab of every dashboard has an **Ask Claude** panel fixed at the top right (a pill that opens a bottom sheet on a phone). It
stays in place while you scroll and switch tabs, keeps the conversation for that dashboard while the browser tab is open, and
answers from the page's own data: the tab's data, the dashboard's readings, what flipped since yesterday, and the day kept on the
top card. Code: `app/ask.py` (server) and the `askPanel` block in `app/static/topic.html`.

## Set-up

Railway › dashboards service › Variables:

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. The same key as the trading bot (or `${{<bot service>.ANTHROPIC_API_KEY}}`). |
| `ASK_MODEL` | `claude-sonnet-5-5` | Any Claude model id. |
| `ASK_DAILY_USD` | `2.00` | Spend cap for the whole site per UTC day; the panel pauses until tomorrow when it is reached. |
| `ASK_PER_HOUR` / `ASK_PER_DAY` | `6` / `20` | Questions per visitor. |
| `ASK_PRICE_IN` / `ASK_PRICE_OUT` | `3` / `15` | Dollars per million input / output tokens, used for the spend estimate. Set them to the model's actual prices. |

Without the key the panel says "Ask Claude is not set up yet" and the pages work as before.

## Privacy and cost

- Visitors are counted by a salted hash of their IP; the IP is never stored. Question text is never stored or logged (only its
  length, the tokens and the cost).
- A question counts against the limits when it is sent; if Claude fails to answer it does not count.
- `/api/health` › `ask` shows today's questions, visitors and estimated spend. Each answer is capped at 700 tokens.
