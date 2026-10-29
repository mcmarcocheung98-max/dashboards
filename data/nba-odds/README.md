# NBA Odds: Ladbrokes Value (`/nba-odds`, private)

Ladbrokes' NBA prices against a fair line taken from the sharp books, pre-game and live: which bets are priced above fair, how the lines
moved, and whether the flagged "value" beat the closing line. Maths on prices, not tips. Nothing is placed anywhere.

For analysis only. Bookmaker limits apply. 18+. [BeGambleAware.org](https://www.begambleaware.org/).

Code: `app/topics/nba_odds.py` (data, maths, poller), `app/static/topics/nba-odds.js` (tabs), `tests/test_nba_odds.py` (fixtures and `smoke_patch()`).

## Where the numbers come from

| What | Source | How often |
|---|---|---|
| Ladbrokes, Pinnacle, Betfair Exchange and UK book prices: moneyline (`h2h`), spread, total | [The Odds API v4](https://the-odds-api.com/liveapi/guides/v4/) `GET /v4/sports/basketball_nba/odds?regions=uk,eu&markets=h2h,spreads,totals&oddsFormat=decimal` | see the budget below |
| Scores and finals (settles flags) | The Odds API `GET /v4/sports/basketball_nba/scores` (1 credit; `daysFrom=2` at 10:00 and after a game ends, 2 credits) | with each pull while a game is on |
| Live clock and period | NBA.com `cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json`, else ESPN's public scoreboard | page request, cached 1 minute (free) |
| Form, rest days, back-to-backs | NBA.com season schedule `scheduleLeagueV2_1.json`, else ESPN's scoreboard over the last 30 days | every 6 hours (free) |
| Injuries | ESPN's public injuries feed, plus `injuries.csv` here | hourly (free) |
| Player props | The Odds API `events/{id}/odds`, **off by default** (quota-heavy): set `NBA_PROPS_MARKETS` (e.g. `player_points`) to fetch them once per game in its first pre-game pull | on demand |

Ladbrokes has no public feed, and scraping it breaks its terms, so it is not scraped: its prices come only through The Odds API.

Bookmaker keys (from The Odds API's bookmaker list): `ladbrokes_uk`, `pinnacle` (eu region), `betfair_ex_uk`; UK books for the best
price: `williamhill`, `paddypower`, `skybet`, `betvictor`, `coral`, plus any key ending `_uk` in a response (exchanges excluded), plus
`NBA_UK_BOOKS`. The Today tab lists every key the latest pull returned, so a missing book can be added by its exact key. Ladbrokes is also
found by its title if its key ever changes. `pytest -m network tests/test_nba_odds.py` (6 credits) prints the keys the API actually sends.

## The method

- **Fair probability.** Remove the margin from Pinnacle's prices, and from the Betfair Exchange's back prices after commission
  (`1 + (odds − 1)(1 − c)`, `BETFAIR_COMMISSION`, default 0.05). Multiplicative (each 1/odds over their sum) by default, or the power
  method with `NBA_DEVIG=power` (p = (1/odds)^k, k so they sum to 1; takes more off long shots). When both books are fresh, the median of
  the two (the mean, for two). A spread or total needs the sharp book on the **same line**; there is no interpolation between lines.
- **EV** = Ladbrokes decimal × fair − 1. A **value bet** needs EV ≥ `MIN_EV` (default 0.02) and at least one sharp line updated less
  than 10 minutes ago pre-game, 2 minutes live (each market's `last_update` from the API). A stale-only fair is shown but never flags.
- **Also shown:** Ladbrokes' margin per market (sum of 1/odds − 1); the move since the open (the first Ladbrokes price this server saw);
  the best price across UK books; the full Kelly fraction `(b·p − q)/b`, of which the page stakes a quarter of the bankroll you type in
  (kept in your browser's localStorage only).
- **Flags.** Every pull recomputes EV. A bet that newly crosses the threshold is flagged with its time and price ("appeared 20:41 UK,
  EV +4.1%"); it is struck out with the reason when Ladbrokes moves the price, the sharp line catches up, the sharp line goes stale, the
  market comes off, or the game tips off (a pre-game flag; the live market then flags on its own). A flag that blinks off and back at
  the same price within 3 hours is the same flag.
- **Closing line value.** CLV = flagged Ladbrokes price × the sharp fair probability at the close − 1. Pre-game the close is the last fair
  line before tip-off; live, the last fair line before the final. Positive average CLV over many bets is the honest test of whether the
  value is real; ROI over a few weeks is mostly noise. ROI is 1 unit per flag at the flagged price.

## The credit budget (enforced in `decide()` and `pace()`)

- One pull at **10:00 UK**; every **30 minutes** from **3 hours** before the first tip-off still to come; every **5 minutes** while a
  game is live (a game with no final is treated as live for 3.5 hours after tip-off).
- Each odds pull costs markets × regions = 3 × 2 = **6 credits** (read back from `x-requests-last`). A typical night (tip-offs from
  00:00 to 03:30 UK) costs about 560 credits by the module's own estimate, so 30 such nights (about 16,800) fit the default budget.
- `x-requests-used` and `x-requests-remaining` are recorded on every call. If the rest of the month at full cadence would overspend
  `ODDS_MONTHLY_BUDGET` (default 19,000), every interval is stretched by the ratio (the "pace" on the page). At the budget, or with fewer
  than 200 credits left, pulls stop until the reset (`ODDS_RESET_DAY`, default the 1st; set it to your plan's billing day).
- Only the background thread calls The Odds API. Page requests read the snapshot files; a test checks it.
- A 401 (bad key) waits 6 hours before trying again, a 429 ten minutes. The key is never logged, stored or sent to the page; errors carry
  only the HTTP status.

## Files on the volume (`SNAPSHOT_DIR/nba-odds/`)

- `latest.json`: the last pull: games with every book's prices, scores, live game ids, the computed rows.
- `state.json`: quota, the pull log, flags (with close, CLV, result), opening prices, closing lines, finals, and the bets you placed.
- `history/<event id>.jsonl`: one line per price change at Ladbrokes, Pinnacle and the Exchange (`[t, book, market, name, point, price]`),
  kept 60 days.
- `props.json`: player props, when switched on.
- `sim.json`: the synthetic lab's last run (the Simulator tab and the Live tab's model column).

## Settings (Railway variables)

| Variable | Default | |
|---|---|---|
| `ODDS_API_KEY` | none | required; without it nothing is pulled and the page says so |
| `ODDS_MONTHLY_BUDGET` | 19000 | credits this dashboard may use per billing month |
| `ODDS_RESET_DAY` | 1 | day of the month the plan's credits reset |
| `MIN_EV` | 0.02 | threshold for a value bet |
| `BETFAIR_COMMISSION` | 0.05 | Exchange commission on winnings |
| `NBA_DEVIG` | mult | `power` for the power method |
| `NBA_UK_BOOKS` | none | extra bookmaker keys for the best UK price, comma-separated |
| `NBA_PROPS_MARKETS` | none | e.g. `player_points,player_rebounds`; costs markets × 2 credits per game |

## Hand-entered injuries (`injuries.csv`)

`date,team,player,status,source,note`: one row per report the ESPN feed misses, team by its full or short name, `source` a URL. Context
only: injuries, rest and form never enter the fair line or EV.

## The Simulator tab (`app/topics/nba_sim.py`, synthetic data only)

Before a real credit is spent, the lab answers three questions on made-up games whose true probabilities are known:

1. **How do live odds move?** Games are played possession by possession from a made-up spread and total (pace, a little catch-up by
   the trailing side, overtime; final margins spread about 10-11 points around the spread, like the NBA). A sharp book (2.5% margin,
   reprices 4 s after every score) and a slow book (6% margin, reprices 25 s after a score and every 60 s, only when the fair line has
   moved 2 points, suspended 8 s after each score, a stuck feed for 2½ minutes in 12% of games) are run over every game. The slow book's
   rules are stylised guesses in `DEFAULTS`, **not Ladbrokes' trading rules**.
2. **Train the model.** `P(home) = Φ((lead + a·m·f + c) / (σ·√f))`, f the fraction of the game left, m the pre-game expected home
   margin, fitted by maximum likelihood on the simulated **outcomes** (never on the true probabilities) of 70% of the games and scored
   on the other 30% (log loss against the base rate, Brier, a calibration table). Rows within a game are correlated, so the fit needs
   hundreds of games: the default run is 800 (about 15 s). The fitted parameters give the **Model % · EV** column on the Live tab, a
   second opinion on each moneyline that never raises a flag. Retrain on real games when the poller has logged a few hundred
   (`history/` holds every price; the scores are in `state.json`): same `fit()` on rows of (lead, pre-game margin, fraction left, won).
3. **Where is the exploitable price?** The dashboard's own `devig` / `ev` run on snapshots at three polling cadences (300 s as the real
   poller, 60 s, 15 s). Every flag (EV ≥ threshold against the sharp fair, one bet per price run) is settled at the game's outcome and
   scored against the **true** probability, by quarter, lead, seconds since the last score, odds, side, feed state, and cadence ×
   threshold.

What the default run shows (synthetic, so a statement about the pipeline, not about Ladbrokes):

- The edge lives in the **10-30 seconds after a score**, when the sharp book has moved and the slow one has not, and in **Q4**
  (the same lag is worth more when a basket moves the probability more). Flags 30 s or more after a score have **negative** true
  edge: they are the sharp book's own noise, not a stale price.
- Flags at **leads of 13+** and at **odds above 4.00** have no real edge either; the EV shown against the sharp fair (about +12%)
  overstates the true edge (about +7%) everywhere, because the sharp fair is itself noisy.
- At the poller's **5-minute cadence** fewer than one flag a game lands in a lag window, so the realised ROI is noise at any sample
  size the budget allows; at 60 s there are 3-4 a game and at 15 s a dozen. A faster live cadence costs credits in proportion
  (6 a pull), so a 1-minute live cadence for an hour of play is about 360 credits a night.

`python -m app.topics.nba_sim --games 800 --lag 40 --sticky 0.03 --hiccup 0.2` prints the whole report for other assumptions;
`--save` writes it to the volume for the tab. The background job runs the default once and again when the file is a week old
(`sim.json`). Tests: `tests/test_nba_sim.py` (the analytic truth is checked against Monte Carlo rollouts).

## Readings ("what changed since yesterday")

Value bets today, best EV today, live flags on, and the 30-day average CLV. Lean +1 = better for the bettor (value found; CLV above 0).

## Requests for shared code

1. **Private pages** (in progress by the parent session): `Topic(..., private=True)` and the `PRIVATE_PASSCODE` cookie gate on the page, its
   JS and `/api/nba-odds/*`. Until `Topic` has a `private` field, this module sets `TOPIC = None`: the dashboard is neither listed nor
   served and its poller does not start, so nothing is ever public.
2. **POST for private dashboards**: route `POST /api/<slug>/<name>` (JSON body, behind the same gate, private dashboards only) to
   `module.ACTIONS[name](body)`; `ValueError` → 400. This module defines `ACTIONS = {"bets": record_bet}` for the placed-bets tracker on
   the Results tab (`{"delete": id}` removes one). Until it exists the page saves placed bets in the browser and says so.
3. **Footer**: the shell's footer says "Nothing here is investment advice". This dashboard adds its own fixed footer
   ("For analysis only. Bookmaker limits apply. 18+. BeGambleAware.org."); a `footer` field on `META` would let the shell show it instead.
4. **Network access** for checks from a dev session: `api.the-odds-api.com`, `cdn.nba.com` and `site.api.espn.com` (fixtures stand in
   until then).
