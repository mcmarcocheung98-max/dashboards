"""NBA Odds: Ladbrokes Value (/nba-odds, private): Ladbrokes' NBA prices against a fair line from the sharp books, pre-game and live.

today     value bets sorted by EV, and each game's moneyline, spread and total at Ladbrokes against fair, with Ladbrokes' margin, the
          move since the open, the best price across UK books and the full Kelly fraction (the page turns it into a quarter-Kelly stake)
live      games in progress (score, clock), current odds against fair, and the bets that newly crossed the threshold this game
moves     each game's price history at Ladbrokes, Pinnacle and the Betfair Exchange, from the first poll through tip-off and live
results   every flagged bet with its price, closing line value against the sharp close, the result, and running ROI and CLV; plus the
          bets the user placed (stored on the volume)
teams     form, rest days, back-to-backs and injuries for tonight's teams: context only, never used in EV
sim       the synthetic lab (nba_sim.py): how live odds move on simulated games, the live win-probability model trained on them, and
          where and at what polling cadence the pipeline's flags are really exploitable; its fitted model gives the Live tab's "model fair"

Prediction markets ride along as the crowd's price: Polymarket's NBA game markets and Kalshi's NBA series (free, live) are matched to
each game by team and date and carried as pseudo-books (`polymarket`, `kalshi`) through the same rows, history and Line moves tab; a
column on Today and Live compares Ladbrokes with them, and NBA_FAIR_CROWD=1 lets them into the fair median next to the sharps.
All odds come from The Odds API v4 (paid key in ODDS_API_KEY). Ladbrokes has no public feed and is not scraped. Polling runs only in the
background thread started by BACKGROUND and writes snapshots under SNAPSHOT_DIR/nba-odds/; page requests read those files and never call
the Odds API. The credit budget (ODDS_MONTHLY_BUDGET) is enforced in decide(): one pull at 10:00 UK, every 30 minutes from 3 hours before
the first tip-off, every 5 minutes while a game is live, all stretched by pace() when the month's spend runs ahead of the budget.

Fair probability: the bookmaker margin is removed from Pinnacle's prices and from the Betfair Exchange's prices after commission
(multiplicative, or the power method with NBA_DEVIG=power), and the median of the fresh ones is taken. EV = Ladbrokes decimal x fair - 1.
Maths, not tips: nothing is placed anywhere.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import threading
import time
from pathlib import Path

import pandas as pd
import requests

from . import _base as B
from ._base import HOUR, _r, fetch_json, manual_rows
from . import Topic

log = logging.getLogger("dashboards.nba_odds")

SLUG = "nba-odds"
_TABS = (("today", "Today"), ("live", "Live"), ("moves", "Line moves"), ("results", "Results & CLV"), ("teams", "Teams"), ("sim", "Simulator"))
_BLURB = ("Ladbrokes' NBA moneylines, spreads and totals against a fair line from Pinnacle and the Betfair Exchange, pre-game and live: "
          "the bets priced above fair each day, how the lines moved, and whether the flagged value beat the closing line.")
try:
    TOPIC = Topic(SLUG, "NBA Odds: Ladbrokes Value", _BLURB, "nba_odds", _TABS, ("teams",), icon="chart", order=95, private=True)
except TypeError:            # the shared private gate is not on main yet: stay unlisted and unserved (and the poller off) until it is
    TOPIC = None

API = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"
REGIONS = "uk,eu"
MARKETS = ("h2h", "spreads", "totals")
LAD = "ladbrokes_uk"
PINNACLE = "pinnacle"
EXCHANGE = "betfair_ex_uk"
SHARPS = (PINNACLE, EXCHANGE)
# prediction markets, carried as pseudo-books (the crowd's moneyline, no margin: a two-outcome market normalised to sum to 1), free and
# live; next to Ladbrokes and the sharps on every tab, in the fair median only with NBA_FAIR_CROWD=1 (see data/nba-odds/README.md)
POLY, KALSHI = "polymarket", "kalshi"
CROWD = (POLY, KALSHI)
CROWD_TITLES = {POLY: "Polymarket (crowd)", KALSHI: "Kalshi (crowd)"}
HISTORY_BOOKS = (LAD, PINNACLE, EXCHANGE, POLY, KALSHI)
GAMMA_NBA = "https://gamma-api.polymarket.com/events?closed=false&tag_slug=nba&limit=100&order=startDate&ascending=true"
KALSHI_NBA = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=open&limit=200"
CROWD_TTL_PRE, CROWD_TTL_LIVE = 600, 60
# UK books for the best price: keys listed by The Odds API for its uk region (bookmaker-apis page); any other key ending in _uk that a
# response carries joins them, as do keys in NBA_UK_BOOKS. Exchanges are left out (the Exchange is a sharp input, not a book to beat).
UK_BOOKS = (LAD, "williamhill", "paddypower", "skybet", "betvictor", "coral")
NBA_SCOREBOARD = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
NBA_SCHEDULE = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
UK, ET = "Europe/London", "America/New_York"

MORNING_HOUR = 10                 # the daily pull, UK time
PRE_WINDOW = 3 * HOUR             # from this long before the first tip-off ...
PRE_EVERY = 30 * 60               # ... every 30 minutes
LIVE_EVERY = 5 * 60               # while any game is live
GAME_LENGTH = 3.5 * HOUR          # a game with no score yet is treated as live this long after tip-off
FRESH_PRE, FRESH_LIVE = 600, 120  # a sharp line older than this (seconds) cannot make a value bet
TICK = 30                         # the poller wakes this often to check whether a pull is due
RESERVE = 200                     # credits never spent, whatever the budget says
KEEP_DAYS = 60                    # price history kept per game

NBA_NICKNAMES = ("Trail Blazers", "76ers", "Hawks", "Celtics", "Nets", "Hornets", "Bulls", "Cavaliers", "Mavericks", "Nuggets", "Pistons", "Warriors",
                 "Rockets", "Pacers", "Clippers", "Lakers", "Grizzlies", "Heat", "Bucks", "Timberwolves", "Pelicans", "Knicks", "Thunder", "Magic",
                 "Suns", "Kings", "Spurs", "Raptors", "Jazz", "Wizards")

SOURCES = [{"name": "The Odds API v4 (Ladbrokes, Pinnacle, Betfair Exchange and the UK books: moneyline, spread, total; scores)", "url": "https://the-odds-api.com/liveapi/guides/v4/",
            "cadence": "10:00 UK, every 30 min from 3 h before tip-off, every 5 min live, within a monthly credit budget"},
           {"name": "Polymarket NBA game markets (Gamma API, tag nba) and Kalshi's NBA game series: the crowd's moneyline, pre-game and live", "url": "https://polymarket.com/sports/nba",
            "cadence": "with each pull; every minute on the Live tab"},
           {"name": "NBA.com live scoreboard and season schedule (cdn.nba.com)", "url": "https://www.nba.com/schedule", "cadence": "every minute live; schedule every 6 hours"},
           {"name": "ESPN public scoreboard and injuries (fallback and injuries)", "url": "https://www.espn.com/nba/injuries", "cadence": "hourly"},
           {"name": "Hand-entered injuries where no feed answers (data/nba-odds/injuries.csv)", "url": "", "cadence": "as entered"}]
NOTES = ("Fair = the bookmaker margin removed from Pinnacle's and the Betfair Exchange's prices (after commission); EV = Ladbrokes price x fair "
         "probability - 1. A value bet needs EV of at least MIN_EV and a sharp line under 10 minutes old (2 live). Maths, not tips. "
         "For analysis only. Bookmaker limits apply. 18+. BeGambleAware.org.")


# ------------------------------------------------------------------ settings (env, read at call time so tests and Railway can change them)
def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def api_key() -> str:
    return os.environ.get("ODDS_API_KEY", "").strip()


def min_ev() -> float:
    return _env_f("MIN_EV", 0.02)


def budget() -> float:
    return _env_f("ODDS_MONTHLY_BUDGET", 19000)


def commission() -> float:
    return _env_f("BETFAIR_COMMISSION", 0.05)


def devig_method() -> str:
    return "power" if os.environ.get("NBA_DEVIG", "").lower() == "power" else "mult"


def reset_day() -> int:
    return int(min(28, max(1, _env_f("ODDS_RESET_DAY", 1))))


def props_markets() -> list[str]:
    return [m.strip() for m in os.environ.get("NBA_PROPS_MARKETS", "").split(",") if m.strip()]


def fair_crowd() -> bool:
    return os.environ.get("NBA_FAIR_CROWD", "") not in ("", "0", "false", "no")


def kalshi_series() -> str:
    return os.environ.get("NBA_KALSHI_SERIES", "KXNBAGAME").strip()


def uk_books(seen=()) -> set[str]:
    extra = {b.strip() for b in os.environ.get("NBA_UK_BOOKS", "").split(",") if b.strip()}
    return set(UK_BOOKS) | extra | {k for k in seen if k.endswith("_uk") and "_ex_" not in k}


# ------------------------------------------------------------------ time
def _ts(iso) -> int | None:
    if iso in (None, ""):
        return None
    try:
        return int(pd.Timestamp(iso).timestamp())
    except (ValueError, TypeError):
        return None


def _local(t: float, tz: str) -> pd.Timestamp:
    return pd.Timestamp(t, unit="s", tz="UTC").tz_convert(tz)


def uk_date(t: float) -> str:
    return _local(t, UK).strftime("%Y-%m-%d")


def slate_date(t: float) -> str:
    """The NBA's own day (US Eastern) of a tip-off: tonight's games in London's small hours belong to the evening before."""
    return _local(t, ET).strftime("%Y-%m-%d")


def uk_clock(t: float) -> str:
    return _local(t, UK).strftime("%H:%M")


# ------------------------------------------------------------------ the maths
def implied(odds) -> list[float]:
    return [1.0 / o for o in odds]


def margin(odds) -> float | None:
    """The bookmaker's overround on one market: sum of 1/odds - 1 (0.045 = 4.5%)."""
    odds = [o for o in odds if o and o > 1]
    return sum(implied(odds)) - 1 if len(odds) >= 2 else None


def devig(odds, method: str = "mult") -> list[float]:
    """Fair probabilities from one market's prices. mult: each 1/odds over their sum. power: p_i = (1/odds_i)^k with k such that they sum
    to 1 (takes more margin off long shots, the favourite-longshot bias)."""
    q = implied(odds)
    s = sum(q)
    if method != "power":
        return [x / s for x in q]
    lo, hi = 0.01, 50.0
    for _ in range(100):
        k = (lo + hi) / 2
        if sum(x ** k for x in q) > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    p = [x ** k for x in q]
    return [x / sum(p) for x in p]


def net_of_commission(odds: float, c: float) -> float:
    """What an exchange back bet pays after commission on winnings: 1 + (odds - 1)(1 - c)."""
    return 1 + (odds - 1) * (1 - c)


def ev(price: float, fair_p: float) -> float:
    return price * fair_p - 1


def kelly(price: float, fair_p: float) -> float:
    """Full Kelly fraction of bankroll, (b p - q) / b with b = price - 1; 0 when there is no edge. The page shows a quarter of it."""
    b = price - 1
    if b <= 0:
        return 0.0
    return max(0.0, (b * fair_p - (1 - fair_p)) / b)


# ------------------------------------------------------------------ The Odds API response -> games
def parse_odds(raw: list) -> list[dict]:
    """[{id, home, away, commence, books: {key: {title, last_update, markets: {mkt: {last_update, outcomes: [{name, price, point}]}}}}}]"""
    out = []
    for e in raw or []:
        books = {}
        for b in e.get("bookmakers") or []:
            mk = {}
            for m in b.get("markets") or []:
                outs = [{"name": o.get("name"), "price": float(o["price"]), "point": None if o.get("point") is None else float(o["point"])}
                        for o in m.get("outcomes") or [] if o.get("price")]
                if outs:
                    mk[m.get("key")] = {"last_update": _ts(m.get("last_update")) or _ts(b.get("last_update")), "outcomes": outs}
            if mk:
                books[b.get("key")] = {"title": b.get("title") or b.get("key"), "last_update": _ts(b.get("last_update")), "markets": mk}
        out.append({"id": e.get("id"), "home": e.get("home_team"), "away": e.get("away_team"), "commence": _ts(e.get("commence_time")), "books": books})
    return out


def parse_scores(raw: list) -> dict:
    """{event id: {completed, home, away, home_score, away_score, commence, last_update}}"""
    out = {}
    for e in raw or []:
        sc = {s.get("name"): s.get("score") for s in e.get("scores") or []}
        num = lambda v: None if v in (None, "") else float(v)
        out[e.get("id")] = {"completed": bool(e.get("completed")), "home": e.get("home_team"), "away": e.get("away_team"),
                            "home_score": num(sc.get(e.get("home_team"))), "away_score": num(sc.get(e.get("away_team"))),
                            "commence": _ts(e.get("commence_time")), "last_update": _ts(e.get("last_update"))}
    return out


def lad_book(books: dict) -> dict | None:
    """Ladbrokes by its key, else by its title (in case the key ever changes)."""
    if LAD in books:
        return books[LAD]
    return next((b for b in books.values() if str(b.get("title", "")).lower().startswith("ladbrokes")), None)


def _okey(market: str, name: str, point) -> str:
    return f"{market}|{name}|{'' if point is None else f'{point:g}'}"


def groups(market: str, outcomes: list[dict]) -> list[list[dict]]:
    """A market's outcomes split into the sets that add up to one event: h2h whole; a spread pairs +x with -x; a total pairs Over and
    Under on the same line."""
    if market == "h2h":
        return [outcomes]
    by: dict = {}
    for o in outcomes:
        if o["point"] is None:
            continue
        by.setdefault(abs(o["point"]) if market == "spreads" else o["point"], []).append(o)
    return [g for g in by.values() if len(g) == 2]


def fair_from(market: str, mk: dict, method: str, comm: float | None = None) -> dict[str, float]:
    """{outcome key: fair probability} from one sharp book's market; comm = exchange commission (prices taken net of it first)."""
    out = {}
    for g in groups(market, mk["outcomes"]):
        if len(g) < 2 or any(o["price"] <= 1 for o in g):
            continue
        prices = [net_of_commission(o["price"], comm) if comm else o["price"] for o in g]
        for o, p in zip(g, devig(prices, method)):
            out[_okey(market, o["name"], o["point"])] = p
    return out


def is_live(game: dict, scores: dict, now: float) -> bool:
    s = scores.get(game["id"])
    if s and s.get("completed"):
        return False
    if not game.get("commence") or game["commence"] > now:
        return False
    return bool(s and s.get("home_score") is not None) or now - game["commence"] < GAME_LENGTH


def evaluate(games: list[dict], scores: dict, now: float, opens: dict | None = None) -> list[dict]:
    """One row per Ladbrokes outcome: price, fair (median of the fresh sharp books), EV, value flag, margin, best UK price, move since open."""
    method, comm, opens = devig_method(), commission(), opens or {}
    seen = {k for g in games for k in g["books"]}
    ukb = uk_books(seen)
    rows = []
    for g in games:
        if (scores.get(g["id"]) or {}).get("completed"):
            continue
        lad = lad_book(g["books"])
        if not lad:
            continue
        live = is_live(g, scores, now)
        limit = FRESH_LIVE if live else FRESH_PRE
        for market in MARKETS:
            lm = lad["markets"].get(market)
            if not lm:
                continue
            sharp = {}
            inputs = [(PINNACLE, None), (EXCHANGE, comm)] + ([(b, None) for b in CROWD] if fair_crowd() else [])
            for key, c in inputs:
                sm = (g["books"].get(key) or {}).get("markets", {}).get(market)
                if sm:
                    age = now - (sm["last_update"] or now)
                    sharp[key] = {"fair": fair_from(market, sm, method, c), "age": max(0, int(age)), "fresh": age < limit}
            lad_margin = {}
            for grp in groups(market, lm["outcomes"]):
                m = margin([o["price"] for o in grp])
                for o in grp:
                    lad_margin[_okey(market, o["name"], o["point"])] = m
            for o in lm["outcomes"]:
                k = _okey(market, o["name"], o["point"])
                have = {b: s for b, s in sharp.items() if k in s["fair"]}
                fresh = {b: s for b, s in have.items() if s["fresh"]}
                use = fresh or have
                fair_p = statistics.median([s["fair"][k] for s in use.values()]) if use else None
                best = None
                for bk, book in g["books"].items():
                    if bk not in ukb:
                        continue
                    for bo in (book["markets"].get(market) or {}).get("outcomes", []):
                        if bo["name"] == o["name"] and bo["point"] == o["point"] and (best is None or bo["price"] > best["price"]):
                            best = {"price": bo["price"], "book": book["title"], "key": bk}
                e = ev(o["price"], fair_p) if fair_p else None
                op = opens.get(f"{g['id']}|{k}")
                crowd = {}
                for b in CROWD:
                    cb = g["books"].get(b)
                    co = next((x for x in ((cb or {}).get("markets", {}).get(market) or {}).get("outcomes", []) if x["name"] == o["name"] and x["point"] == o["point"]), None)
                    if co:
                        crowd[b] = {"p": _r(1 / co["price"], 4), "ev": _r(ev(o["price"], 1 / co["price"]), 4), "age": int(now - (cb["last_update"] or now)),
                                    **{x: (cb.get("meta") or {}).get(x) for x in ("url", "liq", "vol24", "bid", "ask")}}
                rows.append({"crowd": crowd,"event_id": g["id"], "game": f"{g['away']} @ {g['home']}", "home": g["home"], "away": g["away"], "commence": g["commence"],
                             "live": live, "market": market, "name": o["name"], "point": o["point"], "key": f"{g['id']}|{k}",
                             "label": label(market, o["name"], o["point"]), "lad": o["price"], "lad_age": int(now - (lm["last_update"] or now)),
                             "fair_p": _r(fair_p, 5), "fair_odds": _r(1 / fair_p, 3) if fair_p else None, "ev": _r(e, 5),
                             "kelly": _r(kelly(o["price"], fair_p), 5) if fair_p else None, "margin": _r(lad_margin.get(k), 5),
                             "fresh": bool(fresh), "sharp": {b: {"p": _r(s["fair"][k], 5), "age": s["age"], "fresh": s["fresh"]} for b, s in have.items()},
                             "best": best, "open": op[1] if op else None, "open_t": op[0] if op else None,
                             "move": _r(o["price"] - op[1], 3) if op else None,
                             "value": bool(e is not None and fresh and e >= min_ev())})
    return rows


def label(market: str, name: str, point) -> str:
    nick = nickname(name) if market != "totals" else name
    if market == "h2h":
        return f"{nick} to win"
    if point is None:
        return nick
    return f"{nick} {point:+g}" if market == "spreads" else f"{name} {point:g}"


def nickname(team: str | None) -> str:
    team = team or ""
    return next((n for n in NBA_NICKNAMES if team.endswith(n)), team)


# ------------------------------------------------------------------ flags: when a bet crosses the threshold, and when it stops
def update_flags(flags: list[dict], rows: list[dict], now: float) -> list[dict]:
    """New value rows become flags (appeared now); active flags whose row is no longer value are struck out with the reason. A flag that
    blinks off and back at the same price in the same phase (pre-game or live) is the same flag again, not a new one."""
    by_key = {(r["key"], r["live"]): r for r in rows}
    active = {(f["key"], f["live"]): f for f in flags if f["status"] == "active"}
    for r in rows:
        if not r["value"]:
            continue
        f = active.get((r["key"], r["live"]))
        if f is None:
            again = next((x for x in reversed(flags) if x["key"] == r["key"] and x["live"] == r["live"] and x["price"] == r["lad"]
                          and x["status"] == "gone" and now - (x.get("gone") or 0) < 3 * HOUR), None)
            if again:
                again.update(status="active", gone=None, why=None)
                f = again
            else:
                f = {"id": f"{r['key']}|{int(now)}", "key": r["key"], "event_id": r["event_id"], "game": r["game"], "home": r["home"], "away": r["away"],
                     "commence": r["commence"], "market": r["market"], "name": r["name"], "point": r["point"], "label": r["label"], "live": r["live"],
                     "price": r["lad"], "fair_p": r["fair_p"], "ev": r["ev"], "appeared": int(now), "status": "active", "gone": None, "why": None,
                     "max_ev": r["ev"]}
                flags.append(f)
        f.update(last_seen=int(now), last_price=r["lad"], last_fair=r["fair_p"], last_ev=r["ev"], max_ev=max(f.get("max_ev") or -9, r["ev"] or -9))
    for (k, was_live), f in active.items():
        r = by_key.get((k, was_live))
        if r is not None and r["value"]:
            continue
        f["status"], f["gone"] = "gone", int(now)
        if r is None and not was_live and (k, True) in by_key:
            f["why"] = "tipped off"
            r = by_key[(k, True)]
        elif r is None:
            f["why"] = "off the board"
        elif r["lad"] < f["price"] - 1e-9:
            f["why"] = f"price moved to {r['lad']:g}"
        elif not r["fresh"]:
            f["why"] = "sharp line stale"
        else:
            f["why"] = f"sharp line caught up (fair {1 / r['fair_p']:.2f})" if r["fair_p"] else "no fair line"
        if r is not None:
            f.update(last_price=r["lad"], last_fair=r["fair_p"], last_ev=r["ev"])
    return flags


def record_close(state: dict, rows: list[dict], now: float) -> None:
    """The closing line: the last fair probability (and Ladbrokes price) seen before tip-off for pre-game keys, and the last one seen while
    the game was on for live keys. Each poll overwrites, so what is left when the game starts (or ends) is the close."""
    for r in rows:
        if r["fair_p"] is None:
            continue
        state.setdefault("close_live" if r["live"] else "close_pre", {})[r["key"]] = {"p": r["fair_p"], "lad": r["lad"], "t": int(now)}


def outcome(f: dict, res: dict) -> str | None:
    """win / loss / push for a flag against a final score, None while the game is not final."""
    if not res or not res.get("completed") or res.get("home_score") is None or res.get("away_score") is None:
        return None
    hs, as_ = res["home_score"], res["away_score"]
    if f["market"] == "h2h":
        if hs == as_:
            return "push"
        return "win" if f["name"] == (res["home"] if hs > as_ else res["away"]) else "loss"
    if f["market"] == "spreads":
        mine, theirs = (hs, as_) if f["name"] == res["home"] else (as_, hs)
        d = mine + (f["point"] or 0) - theirs
    else:
        d = (hs + as_ - (f["point"] or 0)) * (1 if f["name"] == "Over" else -1)
    return "win" if d > 0 else "push" if d == 0 else "loss"


def profit(result: str | None, price: float, stake: float = 1.0) -> float | None:
    return None if result is None else stake * (price - 1) if result == "win" else 0.0 if result == "push" else -stake


def settle(state: dict, now: float) -> None:
    """Fill each flag's closing line value (once its line has closed) and result (once the game is final)."""
    res = state.get("results", {})
    for f in state.get("flags", []):
        closes = state.get("close_live" if f["live"] else "close_pre", {})
        c = closes.get(f["key"])
        started = f.get("commence") and f["commence"] <= now
        closed = (f["live"] and (res.get(f["event_id"]) or {}).get("completed")) or (not f["live"] and started)
        if c and closed and f.get("clv") is None:
            f.update(close_p=c["p"], close_odds=_r(1 / c["p"], 3), close_lad=c["lad"], clv=_r(f["price"] * c["p"] - 1, 5))
        if f.get("result") is None:
            r = outcome(f, res.get(f["event_id"]))
            if r:
                f.update(result=r, profit=profit(r, f["price"]))
    for b in state.get("placed", []):
        if b.get("result") is None and b.get("event_id") in res and b.get("market") in MARKETS:
            r = outcome(b, res[b["event_id"]])
            if r:
                b.update(result=r, profit=_r(profit(r, b["price"], b.get("stake") or 0), 2))


# ------------------------------------------------------------------ files on the volume (SNAPSHOT_DIR/nba-odds)
_lock = threading.RLock()


DIR: Path | None = None            # set to keep this dashboard's files elsewhere (smoke runs) without moving the shared SNAP_DIR


def _dir() -> Path:
    return DIR or B.SNAP_DIR / SLUG


def _read(name: str, default):
    f = _dir() / name
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".tmp")
    tmp.write_text(json.dumps(obj, default=str, allow_nan=False))
    tmp.replace(d / name)


def load_state() -> dict:
    s = _read("state.json", {})
    for k, v in (("flags", []), ("opens", {}), ("hist_last", {}), ("close_pre", {}), ("close_live", {}), ("results", {}), ("quota", {}),
                 ("log", []), ("placed", [])):
        s.setdefault(k, v)
    return s


def save_state(s: dict) -> None:
    _write("state.json", s)


def append_history(state: dict, games: list[dict], now: float) -> int:
    """One line per price change, per game file: [t, book, market, name, point, price]; Ladbrokes, Pinnacle and the Exchange only."""
    hd = _dir() / "history"
    hd.mkdir(parents=True, exist_ok=True)
    n = 0
    for g in games:
        lines = []
        for bk in HISTORY_BOOKS:
            book = g["books"].get(bk) if bk != LAD else lad_book(g["books"])
            for market, mk in ((book or {}).get("markets") or {}).items():
                for o in mk["outcomes"]:
                    k = f"{g['id']}|{bk}|{_okey(market, o['name'], o['point'])}"
                    if state["hist_last"].get(k) != o["price"]:
                        state["hist_last"][k] = o["price"]
                        lines.append(json.dumps([int(now), bk, market, o["name"], o["point"], o["price"]]))
                    if bk == LAD:
                        state["opens"].setdefault(f"{g['id']}|{_okey(market, o['name'], o['point'])}", [int(now), o["price"]])
        if lines:
            with (hd / f"{g['id']}.jsonl").open("a") as fh:
                fh.write("\n".join(lines) + "\n")
            n += len(lines)
    return n


def read_history(event_id: str) -> list[list]:
    f = _dir() / "history" / f"{os.path.basename(str(event_id))}.jsonl"
    try:
        return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def prune(state: dict, now: float) -> None:
    """Drop per-key memory of games over 3 days old and history files past KEEP_DAYS; flags and results are kept."""
    old = {g for g, s in state.get("games", {}).items() if (s or 0) < now - 3 * 86400}
    if old:
        for name in ("opens", "hist_last", "close_pre", "close_live"):
            state[name] = {k: v for k, v in state[name].items() if k.split("|", 1)[0] not in old}
        state["games"] = {g: s for g, s in state["games"].items() if g not in old}
    hd = _dir() / "history"
    if hd.exists():
        for f in hd.glob("*.jsonl"):
            if f.stat().st_mtime < now - KEEP_DAYS * 86400:
                f.unlink(missing_ok=True)


# ------------------------------------------------------------------ the Odds API client and the credit budget
class OddsError(RuntimeError):
    pass


def odds_get(path: str, params: dict, state: dict) -> list:
    """GET API + path with the key; records the quota headers in state['quota']. Errors never carry the URL (it holds the key)."""
    key = api_key()
    if not key:
        raise OddsError("ODDS_API_KEY is not set")
    h = B.HEALTH.setdefault(API + path, {"module": "nba_odds", "ok": None, "fail": None, "error": None})
    try:
        r = requests.get(API + path, params={**params, "apiKey": key}, headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as e:
        h.update(fail=time.time(), error=type(e).__name__)
        raise OddsError(f"network: {type(e).__name__}") from None
    q = state["quota"]
    for hk, sk in (("x-requests-remaining", "remaining"), ("x-requests-used", "used"), ("x-requests-last", "last")):
        v = r.headers.get(hk)
        if v not in (None, ""):
            try:
                q[sk] = float(v)
            except ValueError:
                pass
    q["at"] = int(time.time())
    if r.status_code != 200:
        h.update(fail=time.time(), error=f"HTTP {r.status_code}")
        raise OddsError(f"HTTP {r.status_code}")
    h.update(ok=time.time(), error=None)
    return r.json()


def period_bounds(now: float, day: int | None = None) -> tuple[float, float]:
    """Start and end (unix) of the credit month, which resets on ODDS_RESET_DAY (UTC)."""
    day = day or reset_day()
    t = pd.Timestamp(now, unit="s", tz="UTC")
    start = t.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
    if start > t:
        start = start - pd.DateOffset(months=1)
    return start.timestamp(), (start + pd.DateOffset(months=1)).timestamp()


def est_day_cost(tips: list[int], per_pull: float) -> float:
    """Credits a normal day costs at full cadence: the 10:00 pull, the pre-game pulls, the live pulls (odds plus a 1-credit score call)."""
    if not tips:
        return per_pull
    span = (max(tips) - min(tips)) / HOUR + GAME_LENGTH / HOUR * 0.75
    live = span * HOUR / LIVE_EVERY
    return per_pull * (1 + PRE_WINDOW / PRE_EVERY + live) + live + 4


def pace(state: dict, now: float, tips: list[int]) -> float:
    """How much to stretch the intervals (1 = full cadence) so the rest of the month fits the budget; inf when it is spent."""
    q = state["quota"]
    used = q.get("used") or 0
    left = min(budget() - used, (q["remaining"] - RESERVE) if q.get("remaining") is not None else float("inf"))
    if left <= 0:
        return float("inf")
    _, end = period_bounds(now)
    days = max(0.25, (end - now) / 86400)
    per_pull = q.get("odds_cost") or len(MARKETS) * len(REGIONS.split(","))
    need = est_day_cost(tips, per_pull)
    return max(1.0, need / (left / days))


def decide(state: dict, games: list[dict], scores: dict, now: float) -> str | None:
    """Why a pull is due now, or None. 10:00 UK once a day; every 30 min (stretched by pace) from 3 h before the first tip-off still to
    come; every 5 min (stretched) while a game is live. Nothing at all once the budget is spent."""
    upcoming = [g["commence"] for g in games if g.get("commence") and g["commence"] > now and g["commence"] - now < 30 * HOUR]
    live = any(is_live(g, scores, now) for g in games)
    tips = [g["commence"] for g in games if g.get("commence") and slate_date(g["commence"]) == slate_date(now)] or upcoming
    f = pace(state, now, tips)
    state["pace"] = None if f == float("inf") else round(f, 2)
    if f == float("inf"):
        return None
    last = state.get("last_poll") or 0
    uk = _local(now, UK)
    if uk.hour >= MORNING_HOUR and state.get("morning") != uk.strftime("%Y-%m-%d"):
        return "10:00 pull"
    if live and now - last >= LIVE_EVERY * f:
        return "live"
    if upcoming and now >= min(upcoming) - PRE_WINDOW and now - last >= PRE_EVERY * f:
        return "pre-game"
    return None


def poll_once(why: str = "manual", now: float | None = None) -> dict:
    """One pull: odds (and scores when a game is on or was), then fair lines, flags, closing lines, results, history; all to the volume."""
    now = now or time.time()
    with _lock:
        state = load_state()
        prev = _read("latest.json", {})
        res = {"why": why, "t": int(now)}
        try:
            u0 = state["quota"].get("used")
            raw = odds_get(f"/sports/{SPORT}/odds", {"regions": REGIONS, "markets": ",".join(MARKETS), "oddsFormat": "decimal", "dateFormat": "iso"}, state)
            if u0 is not None and state["quota"].get("used") is not None and state["quota"]["used"] > u0:
                state["quota"]["odds_cost"] = state["quota"]["used"] - u0
            elif state["quota"].get("last"):
                state["quota"]["odds_cost"] = state["quota"]["last"]
            games = parse_odds(raw)
        except OddsError as e:
            state["log"] = (state["log"] + [{**res, "error": str(e)}])[-60:]
            state["last_poll"] = int(now)
            state["error"] = str(e)
            save_state(state)
            return {**res, "error": str(e)}
        state.pop("error", None)
        scores = dict(prev.get("scores") or {})
        on = any(g["commence"] and g["commence"] <= now for g in games)
        try:
            attach_crowd(games, now, CROWD_TTL_LIVE if on else CROWD_TTL_PRE)
        except Exception as e:                      # free sources: never a reason to lose the pull
            res["crowd_error"] = type(e).__name__
        settle_due = state.get("settle_due") or why == "10:00 pull"
        if on or settle_due:
            try:
                params = {"daysFrom": 2} if settle_due else {}
                scores.update(parse_scores(odds_get(f"/sports/{SPORT}/scores", {**params, "dateFormat": "iso"}, state)))
                state["settle_due"] = False
            except OddsError as e:
                res["scores_error"] = str(e)
        was_live = set(prev.get("live_ids") or [])
        live_ids = [g["id"] for g in games if is_live(g, scores, now)]
        if was_live - set(live_ids):
            state["settle_due"] = True             # a game just ended: the next score call fetches finals
        state["results"].update({k: v for k, v in scores.items() if v.get("completed")})
        state.setdefault("games", {}).update({g["id"]: g["commence"] for g in games if g["commence"]})
        res["history"] = append_history(state, games, now)
        rows = evaluate(games, scores, now, state["opens"])
        update_flags(state["flags"], rows, now)
        record_close(state, rows, now)
        settle(state, now)
        props = _read("props.json", {})
        if props_markets() and why == "pre-game":
            props = fetch_props(state, games, now, props)
        if why == "10:00 pull":
            state["morning"] = uk_date(now)
        state["last_poll"] = int(now)
        res.update(games=len(games), value=sum(r["value"] for r in rows), live=len(live_ids), credits=state["quota"].get("remaining"))
        state["log"] = (state["log"] + [res])[-60:]
        prune(state, now)
        _write("latest.json", {"t": int(now), "games": games, "scores": scores, "live_ids": live_ids, "rows": rows,
                               "books_seen": {k: b["title"] for g in games for k, b in g["books"].items()}})
        save_state(state)
        return res


def fetch_props(state: dict, games: list[dict], now: float, props: dict) -> dict:
    """Player props (events/{id}/odds), only when NBA_PROPS_MARKETS lists markets: once per game, in its first pre-game window pull."""
    for g in games:
        if g["id"] in props or not g["commence"] or g["commence"] < now or g["commence"] - now > PRE_WINDOW:
            continue
        try:
            raw = odds_get(f"/sports/{SPORT}/events/{g['id']}/odds", {"regions": REGIONS, "markets": ",".join(props_markets()), "oddsFormat": "decimal"}, state)
            props[g["id"]] = {"t": int(now), "game": parse_odds([raw])[0] if raw else None}
        except OddsError as e:
            props[g["id"]] = {"t": int(now), "error": str(e)}
    _write("props.json", {k: v for k, v in props.items() if (v.get("t") or 0) > now - 3 * 86400})
    return props


# ------------------------------------------------------------------ prediction markets: the crowd's moneyline as pseudo-books
def parse_poly_nba(events: list) -> list[dict]:
    """Gamma NBA events -> [{teams: {nickname: p}, start, url, liq, vol24, bid, ask, updated}]: the moneyline market of each event (two
    outcomes that are NBA teams), prices normalised to sum to 1; bid/ask of the first outcome when the API sends them."""
    from .prediction_markets import _f, _jlist
    out = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        for m in e.get("markets") or []:
            if m.get("closed") or m.get("active") is False:
                continue
            outs, prices = [str(x) for x in _jlist(m.get("outcomes"))], [_f(x) for x in _jlist(m.get("outcomePrices"))]
            if len(outs) != 2 or len(prices) != 2 or None in prices:
                continue
            nicks = [nickname(o) for o in outs]
            if not all(n in NBA_NICKNAMES for n in nicks) or nicks[0] == nicks[1]:
                continue
            bid, ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
            p0 = (bid + ask) / 2 if bid is not None and ask is not None and 0 < bid <= ask < 1 else prices[0]
            p1 = prices[1] if bid is None or ask is None else 1 - p0
            tot = p0 + p1
            if tot <= 0 or p0 <= 0 or p1 <= 0:
                continue
            slug = e.get("slug") or ""
            out.append({"teams": {nicks[0]: p0 / tot, nicks[1]: p1 / tot}, "start": _ts(m.get("gameStartTime") or e.get("startDate") or e.get("endDate")),
                        "url": f"https://polymarket.com/event/{slug}" if slug else None, "liq": _f(m.get("liquidityNum")) if m.get("liquidityNum") is not None else _f(m.get("liquidity")),
                        "vol24": _f(m.get("volume24hr")), "bid": bid, "ask": ask, "updated": _ts(m.get("updatedAt")) })
            break                                              # one moneyline per event; spreads and totals are other markets of the same event
    return out


def parse_kalshi_nba(j: dict) -> list[dict]:
    """Kalshi's NBA game series -> [{teams: {nickname: p}, start, url, vol24, bid, ask}]: the two Yes markets of each event, one per team,
    normalised to sum to 1 (prediction_markets.parse_kalshi reads the prices: last trade, else the bid/ask middle)."""
    from .prediction_markets import parse_kalshi, _f
    by_event: dict = {}
    raw = {m.get("ticker"): m for m in (j or {}).get("markets") or []}
    for m in parse_kalshi(j):
        team = nickname(m["sub"]) or nickname(m["title"])
        if team not in NBA_NICKNAMES or not m["event"]:
            continue
        ev_ = by_event.setdefault(m["event"], {"teams": {}, "url": m["url"], "vol24": 0.0, "close": m["close"], "start": None, "bid": None, "ask": None})
        ev_["teams"][team] = m["yes"]
        ev_["vol24"] += m["vol24"] or 0.0
        r = raw.get(m["ticker"]) or {}
        ev_["start"] = ev_["start"] or _ts(r.get("expected_expiration_time") or r.get("close_time"))
        if ev_["bid"] is None:
            ev_["bid"], ev_["ask"] = _f(r.get("yes_bid_dollars")), _f(r.get("yes_ask_dollars"))
    out = []
    for ev_ in by_event.values():
        if len(ev_["teams"]) != 2:
            continue
        tot = sum(ev_["teams"].values())
        if tot <= 0:
            continue
        ev_["teams"] = {k: v / tot for k, v in ev_["teams"].items()}
        out.append(ev_)
    return out


def match_crowd(games: list[dict], markets: list[dict], window: float = 30 * HOUR) -> dict:
    """{event id: market} where the market's two teams are the game's and its start (or close) is within `window` of the tip-off."""
    out = {}
    for g in games:
        pair = {nickname(g["home"]), nickname(g["away"])}
        best = None
        for m in markets:
            if set(m["teams"]) != pair:
                continue
            gap = abs((m.get("start") or g["commence"] or 0) - (g["commence"] or 0))
            if gap <= window and (best is None or gap < best[0]):
                best = (gap, m)
        if best:
            out[g["id"]] = best[1]
    return out


def crowd_markets(ttl: float) -> dict[str, list[dict]]:
    """{polymarket: [...], kalshi: [...]} from the free APIs (each guarded: one down leaves the other)."""
    out = {}
    try:
        out[POLY] = parse_poly_nba(fetch_json(GAMMA_NBA, ttl, min_bytes=2, timeout=30))
    except Exception:
        out[POLY] = []
    try:
        out[KALSHI] = parse_kalshi_nba(fetch_json(KALSHI_NBA.format(series=kalshi_series()), ttl, min_bytes=2, timeout=30))
    except Exception:
        out[KALSHI] = []
    return out


def crowd_book(m: dict, g: dict, now: float) -> dict:
    """A pseudo-book in the shape parse_odds gives: the moneyline as decimal odds 1/p for each side."""
    outs = []
    for full in (g["home"], g["away"]):
        p = m["teams"].get(nickname(full))
        if p:
            outs.append({"name": full, "price": round(1 / p, 4), "point": None})
    t = int(m.get("updated") or now)
    return {"title": None, "last_update": t, "markets": {"h2h": {"last_update": t, "outcomes": outs}},
            "meta": {k: m.get(k) for k in ("url", "liq", "vol24", "bid", "ask")}}


def attach_crowd(games: list[dict], now: float, ttl: float) -> int:
    """Add the crowd pseudo-books to each matched game's books (in place); returns how many games got at least one."""
    n = 0
    for key, markets in crowd_markets(ttl).items():
        for gid, m in match_crowd(games, markets).items():
            g = next(x for x in games if x["id"] == gid)
            b = crowd_book(m, g, now)
            if b["markets"]["h2h"]["outcomes"]:
                b["title"] = CROWD_TITLES[key]
                g["books"][key] = b
                n += 1
    return n


def refresh_crowd(rows: list[dict], games: list[dict], now: float) -> None:
    """The Live tab's minute refresh: the crowd's latest prices on the snapshot's moneyline rows (the Odds API side stays as polled)."""
    gs = [dict(g, books={}) for g in games]
    attach_crowd(gs, now, CROWD_TTL_LIVE)
    books = {g["id"]: g["books"] for g in gs}
    for r in rows:
        if r["market"] != "h2h":
            continue
        for b in CROWD:
            cb = books.get(r["event_id"], {}).get(b)
            co = next((x for x in ((cb or {}).get("markets", {}).get("h2h") or {}).get("outcomes", []) if x["name"] == r["name"]), None)
            if co:
                r.setdefault("crowd", {})[b] = {"p": _r(1 / co["price"], 4), "ev": _r(ev(r["lad"], 1 / co["price"]), 4), "age": int(now - cb["last_update"]), **cb["meta"]}


# ------------------------------------------------------------------ the background poller
_thread: dict = {"t": None, "stop": threading.Event()}


def _loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            now = time.time()
            latest = _read("latest.json", {})
            with _lock:
                state = load_state()
                why = decide(state, latest.get("games") or [], latest.get("scores") or {}, now)
                state["next_check"] = int(now + TICK)
                save_state(state)
            if why:
                r = poll_once(why, now)
                log.info("nba-odds pull (%s): %s", why, {k: v for k, v in r.items() if k != "t"})
                if r.get("error", "").startswith("HTTP 401"):
                    stop.wait(6 * HOUR)        # a bad key: try again later rather than every tick
                elif r.get("error", "").startswith("HTTP 429"):
                    stop.wait(10 * 60)
        except Exception as e:             # the loop must outlive any one bad pull
            log.warning("nba-odds poller: %s", type(e).__name__)
        stop.wait(TICK)


def start_poller() -> dict:
    """BACKGROUND job: start the paced poller thread once (and again if it ever died). Returns at once."""
    if TOPIC is None:
        return {"poller": "off until private pages are supported"}
    if not api_key():
        return {"poller": "ODDS_API_KEY not set"}
    t = _thread["t"]
    if t is not None and t.is_alive():
        return {"poller": "ok"}
    _thread["stop"] = threading.Event()
    _thread["t"] = threading.Thread(target=_loop, args=(_thread["stop"],), name="nba-odds-poller", daemon=True)
    _thread["t"].start()
    return {"poller": "ok"}


def run_sim() -> dict:
    """BACKGROUND job: the synthetic lab (nba_sim.py), once, then again when its file is a week old."""
    from . import nba_sim
    return nba_sim.ensure()


BACKGROUND = [start_poller, run_sim]


# ------------------------------------------------------------------ NBA context (free sources; never in EV)
def nba_scoreboard() -> dict:
    """{nickname: {period, clock, status, home, away, home_score, away_score}} for today's games: NBA.com, else ESPN."""
    out = {}
    try:
        j = fetch_json(NBA_SCOREBOARD, 60)
        for g in (j.get("scoreboard") or {}).get("games") or []:
            clock = g.get("gameClock") or ""
            if clock.startswith("PT"):
                mm, _, ss = clock[2:].rstrip("S").partition("M")
                clock = f"{int(float(mm or 0))}:{int(float(ss or 0)):02d}"
            row = {"status": g.get("gameStatusText"), "period": g.get("period"), "clock": clock, "state": {1: "pre", 2: "in", 3: "post"}.get(g.get("gameStatus")),
                   "home": g["homeTeam"].get("teamName"), "away": g["awayTeam"].get("teamName"),
                   "home_score": g["homeTeam"].get("score"), "away_score": g["awayTeam"].get("score"), "source": "NBA.com"}
            out[row["home"]] = out[row["away"]] = row
        if out:
            return out
    except Exception:
        pass
    j = fetch_json(ESPN_SCOREBOARD, 60)
    for e in j.get("events") or []:
        st = e.get("status") or {}
        comp = ((e.get("competitions") or [{}])[0].get("competitors")) or []
        side = {c.get("homeAway"): c for c in comp}
        if "home" not in side or "away" not in side:
            continue
        nk = lambda c: nickname((c.get("team") or {}).get("displayName"))
        row = {"status": (st.get("type") or {}).get("shortDetail"), "period": st.get("period"), "clock": st.get("displayClock"), "state": (st.get("type") or {}).get("state"),
               "home": nk(side["home"]), "away": nk(side["away"]), "home_score": _num(side["home"].get("score")), "away_score": _num(side["away"].get("score")), "source": "ESPN"}
        out[row["home"]] = out[row["away"]] = row
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def season_games() -> list[dict]:
    """Every game this season: [{t, home, away, home_score, away_score, final}] by nickname. NBA.com schedule, else ESPN's scoreboard over
    the last 30 days."""
    try:
        j = fetch_json(NBA_SCHEDULE, 6 * HOUR, min_bytes=1000)
        out = []
        for d in (j.get("leagueSchedule") or {}).get("gameDates") or []:
            for g in d.get("games") or []:
                h, a = g.get("homeTeam") or {}, g.get("awayTeam") or {}
                if not h.get("teamName") or not a.get("teamName"):
                    continue
                out.append({"t": _ts(g.get("gameDateTimeUTC")), "home": h["teamName"], "away": a["teamName"], "home_score": h.get("score"),
                            "away_score": a.get("score"), "final": g.get("gameStatus") == 3})
        if out:
            return out
    except Exception:
        pass
    now = pd.Timestamp.now("UTC")
    rng = f"{(now - pd.Timedelta(days=30)).strftime('%Y%m%d')}-{(now + pd.Timedelta(days=2)).strftime('%Y%m%d')}"
    j = fetch_json(f"{ESPN_SCOREBOARD}?dates={rng}&limit=1000", 6 * HOUR)
    out = []
    for e in j.get("events") or []:
        comp = ((e.get("competitions") or [{}])[0].get("competitors")) or []
        side = {c.get("homeAway"): c for c in comp}
        if "home" not in side or "away" not in side:
            continue
        done = (((e.get("status") or {}).get("type")) or {}).get("completed")
        out.append({"t": _ts(e.get("date")), "home": nickname(side["home"]["team"]["displayName"]), "away": nickname(side["away"]["team"]["displayName"]),
                    "home_score": _num(side["home"].get("score")), "away_score": _num(side["away"].get("score")), "final": bool(done)})
    return out


def team_context(team: str, games: list[dict], tip: int | None) -> dict:
    """Last 10 results, streak, average margin, rest days before `tip`, back-to-back and 3-in-4 flags, for one team (nickname)."""
    mine = sorted((g for g in games if team in (g["home"], g["away"]) and g["t"]), key=lambda g: g["t"])
    done = [g for g in mine if g["final"] and g["home_score"] is not None and (tip is None or g["t"] < tip)]
    last10 = []
    for g in done[-10:]:
        us, them = (g["home_score"], g["away_score"]) if g["home"] == team else (g["away_score"], g["home_score"])
        last10.append({"t": g["t"], "opp": g["away"] if g["home"] == team else g["home"], "home": g["home"] == team, "won": us > them, "margin": us - them})
    streak = 0
    for x in reversed(last10):
        if streak == 0 or (streak > 0) == x["won"]:
            streak += 1 if x["won"] else -1
        else:
            break
    rest = b2b = three4 = None
    if tip and done:
        d_tip = pd.Timestamp(slate_date(tip))
        prev_days = [pd.Timestamp(slate_date(g["t"])) for g in done]
        rest = int((d_tip - prev_days[-1]).days) - 1
        b2b = rest == 0
        three4 = sum(1 for d in prev_days if (d_tip - d).days <= 3) >= 2
    return {"team": team, "w": sum(x["won"] for x in last10), "l": sum(not x["won"] for x in last10), "streak": streak,
            "avg_margin": _r(sum(x["margin"] for x in last10) / len(last10), 1) if last10 else None, "last10": last10, "rest": rest, "b2b": b2b, "three_in_four": three4}


def injuries() -> dict:
    """{nickname: [{player, status, note, date, source}]}: ESPN's injury report, plus hand-entered rows from data/nba-odds/injuries.csv."""
    out: dict = {}
    try:
        j = fetch_json(ESPN_INJURIES, HOUR)
        for t in j.get("injuries") or []:
            nk = nickname(t.get("displayName"))
            for i in t.get("injuries") or []:
                out.setdefault(nk, []).append({"player": (i.get("athlete") or {}).get("displayName"), "status": i.get("status"),
                                               "note": i.get("shortComment") or "", "date": (i.get("date") or "")[:10], "source": "ESPN"})
    except Exception:
        pass
    for r in manual_rows(SLUG, "injuries"):
        out.setdefault(nickname(r.get("team")), []).append({"player": r.get("player"), "status": r.get("status"), "note": r.get("note", ""),
                                                            "date": r["date"], "source": r.get("source", "")})
    return out


# ------------------------------------------------------------------ page payloads (snapshot files only; the Odds API is never called here)
def _latest() -> dict:
    return _read("latest.json", {})


def credits(state: dict, games: list[dict] = ()) -> dict:
    q = state.get("quota", {})
    now = time.time()
    _, end = period_bounds(now)
    tips = [g["commence"] for g in games if g.get("commence") and slate_date(g["commence"]) == slate_date(now)]
    f = pace({"quota": q}, now, tips) if q else None
    return {"remaining": q.get("remaining"), "used": q.get("used"), "budget": budget(), "per_pull": q.get("odds_cost"), "at": q.get("at"),
            "pace": None if f in (None, float("inf")) else round(f, 2), "stopped": f == float("inf"), "resets": time.strftime("%Y-%m-%d", time.gmtime(end)), "key_set": bool(api_key()),
            "last_poll": state.get("last_poll"), "error": state.get("error"), "log": state.get("log", [])[-12:]}


def _game_rows(rows: list[dict]) -> list[dict]:
    games: dict = {}
    for r in rows:
        g = games.setdefault(r["event_id"], {"id": r["event_id"], "game": r["game"], "home": r["home"], "away": r["away"], "commence": r["commence"],
                                             "live": r["live"], "markets": {}})
        g["markets"].setdefault(r["market"], []).append(r)
    return sorted(games.values(), key=lambda g: (g["commence"] or 0, g["game"]))


def _daily_flags(flags: list[dict], days: int = 120) -> dict:
    """Per UK day: flags raised and the best EV among them, as [[t, v]] for the charts."""
    by: dict = {}
    for f in flags:
        d = uk_date(f["appeared"])
        x = by.setdefault(d, {"n": 0, "best": None})
        x["n"] += 1
        x["best"] = max(x["best"] if x["best"] is not None else -9, f["ev"] or -9)
    ks = sorted(by)[-days:]
    t = lambda d: int(pd.Timestamp(d).timestamp())
    return {"count": [[t(d), by[d]["n"]] for d in ks], "best_ev": [[t(d), _r(by[d]["best"], 5)] for d in ks]}


def today() -> dict:
    lt, st = _latest(), load_state()
    now = time.time()
    rows = lt.get("rows") or []
    value = sorted((r for r in rows if r["value"] and not r["live"]), key=lambda r: -(r["ev"] or 0))
    slate = slate_date(now)
    todays = [g for g in _game_rows(rows) if g["commence"] and (slate_date(g["commence"]) == slate or g["commence"] > now)]
    return {"as_of": lt.get("t"), "slate": slate, "min_ev": min_ev(), "fresh_pre": FRESH_PRE, "fresh_live": FRESH_LIVE, "devig": devig_method(),
            "commission": commission(), "value": value, "games": todays, "credits": credits(st, lt.get("games") or []), "daily": _daily_flags(st.get("flags", [])),
            "fair_crowd": fair_crowd(),
            "books_seen": lt.get("books_seen") or {}, "props": _props_summary(), "updated": int(now)}


def _props_summary() -> list[dict]:
    out = []
    for gid, p in _read("props.json", {}).items():
        g = p.get("game")
        if not g:
            continue
        lad = lad_book(g["books"]) or {}
        for m, mk in (lad.get("markets") or {}).items():
            for o in mk["outcomes"]:
                out.append({"event_id": gid, "game": f"{g['away']} @ {g['home']}", "market": m, "name": o["name"], "point": o["point"], "lad": o["price"]})
    return out[:300]


def live() -> dict:
    lt, st = _latest(), load_state()
    now = time.time()
    rows = [r for r in lt.get("rows") or [] if r["live"]]
    try:
        board = nba_scoreboard()
        board_err = None
    except Exception as e:
        board, board_err = {}, type(e).__name__
    try:
        refresh_crowd(rows, [g for g in lt.get("games") or [] if g["id"] in {r["event_id"] for r in rows}], now)
    except Exception:
        pass
    scores = lt.get("scores") or {}
    games = []
    from . import nba_sim
    params = nba_sim.load().get("model") or {}
    for g in _game_rows(rows):
        s, b = scores.get(g["id"]) or {}, board.get(nickname(g["home"])) or {}
        g.update(home_score=s.get("home_score") if s.get("home_score") is not None else b.get("home_score"),
                 away_score=s.get("away_score") if s.get("away_score") is not None else b.get("away_score"),
                 clock=b.get("clock"), period=b.get("period"), status=b.get("status"), clock_source=b.get("source"))
        g["model"] = model_fair(g, st, params)
        games.append(g)
    recent = [f for f in st.get("flags", []) if f["live"] and (f["status"] == "active" or (f.get("gone") or 0) > now - 2 * HOUR)]
    recent.sort(key=lambda f: (f["status"] != "active", -(f.get("last_ev") or f["ev"] or 0)))
    return {"as_of": lt.get("t"), "games": games, "flags": recent, "min_ev": min_ev(), "fresh_live": FRESH_LIVE, "board_error": board_err, "fair_crowd": fair_crowd(),
            "credits": credits(st, lt.get("games") or []), "updated": int(now)}


def pregame_spread(gid: str, home: str, st: dict) -> float | None:
    """The home spread line at the pre-game close (Ladbrokes' key, which is what close_pre and opens are keyed by), else the open."""
    pre = f"{gid}|spreads|{home}|"
    for store in (st.get("close_pre", {}), st.get("opens", {})):
        for k in store:
            if k.startswith(pre) and k[len(pre):]:
                try:
                    return float(k[len(pre):])
                except ValueError:
                    continue
    return None


def model_fair(g: dict, st: dict, params: dict) -> dict | None:
    """The synthetic-trained live model's P(home) for a game in progress, and its EV against Ladbrokes' moneyline. A second opinion
    shown next to the sharp fair; it never raises a flag (see nba_sim.py)."""
    from . import nba_sim
    if not params or g.get("home_score") is None or g.get("away_score") is None:
        return None
    spread = pregame_spread(g["id"], g["home"], st)
    p = nba_sim.live_model_p(g["home_score"] - g["away_score"], g.get("period"), g.get("clock"), spread, params)
    if p is None:
        return None
    out = {"p_home": _r(p, 4), "odds_home": _r(1 / p, 3) if p > 0.001 else None, "odds_away": _r(1 / (1 - p), 3) if p < 0.999 else None, "spread": spread,
           "trained_on": "synthetic"}
    for r in g["markets"].get("h2h", []):
        side_p = p if r["name"] == g["home"] else 1 - p
        r["model_p"] = _r(side_p, 4)
        r["model_ev"] = _r(ev(r["lad"], side_p), 4)
    return out


def sim() -> dict:
    """The synthetic lab's last run (nba_sim.py); a short run on the spot the first time, so the tab is never empty."""
    from . import nba_sim
    out = nba_sim.load()
    if not out:
        out = nba_sim.run(games=120)
        nba_sim.save(out)
    return out


def moves() -> dict:
    """Per game of the last 3 days: price history at Ladbrokes, Pinnacle and the Exchange, per market outcome."""
    lt, st = _latest(), load_state()
    now = time.time()
    known = {g["id"]: g for g in lt.get("games") or []}
    ids = [g for g, t in sorted(st.get("games", {}).items(), key=lambda x: -(x[1] or 0)) if (t or 0) > now - 3 * 86400][:30]
    out = []
    for gid in ids:
        h = read_history(gid)
        if not h:
            continue
        series: dict = {}
        for t, bk, market, name, point, price in h:
            series.setdefault(_okey(market, name, point), {}).setdefault(bk, []).append([t, price])
        end = lt.get("t") if gid in known else max(x[0] for x in h)
        for books in series.values():            # history keeps changes only: carry each line flat to the latest pull that quoted the game
            for pts in books.values():
                if end and pts[-1][0] < end:
                    pts.append([end, pts[-1][1]])
        g = known.get(gid) or {}
        flag = next((f for f in st.get("flags", []) if f["event_id"] == gid), {})
        home, away = g.get("home") or flag.get("home"), g.get("away") or flag.get("away")
        out.append({"id": gid, "game": f"{away} @ {home}" if home else gid, "home": home, "away": away, "commence": st["games"].get(gid),
                    "series": [{"key": k, "market": k.split("|")[0], "label": label(k.split("|")[0], k.split("|")[1], _num(k.split("|")[2]) if k.split("|")[2] else None),
                                "books": v} for k, v in series.items()]})
    return {"as_of": lt.get("t"), "games": out, "books": {LAD: "Ladbrokes", PINNACLE: "Pinnacle", EXCHANGE: "Betfair Exchange (raw back price)",
                                                            POLY: "Polymarket (1 / crowd probability)", KALSHI: "Kalshi (1 / crowd probability)"}, "updated": int(now)}


def track(flags: list[dict], days: int = 400) -> dict:
    """Running ROI (1 unit per flag, settled flags) and CLV by UK day of the flag, and the 30-day average CLV."""
    by: dict = {}
    for f in sorted(flags, key=lambda f: f["appeared"]):
        d = uk_date(f["appeared"])
        x = by.setdefault(d, {"profit": 0.0, "n": 0, "clv": []})
        if f.get("profit") is not None:
            x["profit"] += f["profit"]
            x["n"] += 1
        if f.get("clv") is not None:
            x["clv"].append(f["clv"])
    roi, clv, clv30 = [], [], []
    cp = cn = 0
    days_sorted = sorted(by)[-days:]
    for d in days_sorted:
        t = int(pd.Timestamp(d).timestamp())
        cp += by[d]["profit"]
        cn += by[d]["n"]
        if cn:
            roi.append([t, _r(cp / cn, 5)])
        if by[d]["clv"]:
            clv.append([t, _r(sum(by[d]["clv"]) / len(by[d]["clv"]), 5)])
        win = [c for dd in days_sorted if pd.Timestamp(d) - pd.Timedelta(days=29) <= pd.Timestamp(dd) <= pd.Timestamp(d) for c in by[dd]["clv"]]
        if win:
            clv30.append([t, _r(sum(win) / len(win), 5)])
    settled = [f for f in flags if f.get("profit") is not None]
    withclv = [f for f in flags if f.get("clv") is not None]
    return {"roi": roi, "clv": clv, "clv30": clv30, "n": len(flags), "settled": len(settled),
            "wins": sum(f["result"] == "win" for f in settled), "profit": _r(sum(f["profit"] for f in settled), 3),
            "roi_all": _r(sum(f["profit"] for f in settled) / len(settled), 5) if settled else None,
            "clv_all": _r(sum(f["clv"] for f in withclv) / len(withclv), 5) if withclv else None,
            "beat_close": _r(sum(f["clv"] > 0 for f in withclv) / len(withclv), 4) if withclv else None}


def results() -> dict:
    st = load_state()
    flags = st.get("flags", [])
    placed = st.get("placed", [])
    pl = [b for b in placed if b.get("profit") is not None]
    staked = sum(b.get("stake") or 0 for b in pl)
    return {"flags": sorted(flags, key=lambda f: -f["appeared"])[:300], "track": track(flags), "pre": track([f for f in flags if not f["live"]]),
            "live": track([f for f in flags if f["live"]]), "placed": sorted(placed, key=lambda b: -(b.get("t") or 0)),
            "placed_summary": {"n": len(placed), "settled": len(pl), "staked": _r(staked, 2), "profit": _r(sum(b["profit"] for b in pl), 2),
                               "roi": _r(sum(b["profit"] for b in pl) / staked, 5) if staked else None},
            "updated": int(time.time())}


def teams() -> dict:
    lt = _latest()
    now = time.time()
    tonight = {}
    for g in lt.get("games") or []:
        if g.get("commence") and (slate_date(g["commence"]) == slate_date(now) or now < g["commence"] < now + 30 * HOUR):
            for side, opp in ((g["home"], g["away"]), (g["away"], g["home"])):
                tonight[nickname(side)] = {"tip": g["commence"], "opp": nickname(opp), "home": side == g["home"], "full": side}
    out = {"as_of": lt.get("t"), "updated": int(now)}
    try:
        season = season_games()
    except Exception as e:
        season, out["schedule_error"] = [], type(e).__name__
    names = sorted(tonight) or sorted({g["home"] for g in season} | {g["away"] for g in season})
    inj = injuries()
    out["teams"] = [{**team_context(n, season, (tonight.get(n) or {}).get("tip")), **(tonight.get(n) or {}), "injuries": inj.get(n, [])} for n in names]
    out["tonight"] = bool(tonight)
    out["injury_sources"] = sorted({i["source"] for v in inj.values() for i in v if i.get("source")})
    return out


def bets() -> dict:
    return {"placed": load_state().get("placed", [])}


# placed bets come from the page as JSON; only these fields are kept, and each is checked
BET_FIELDS = {"event_id": str, "game": str, "market": str, "name": str, "point": float, "price": float, "stake": float, "flag_id": str, "note": str, "result": str}


def record_bet(body: dict) -> dict:
    """Store one bet the user placed (POST /api/nba-odds/bets, behind the private gate): {event_id?, game, market, name, point?, price,
    stake, flag_id?, note?, result?}. With {"delete": id} removes that bet. Nothing is placed anywhere: this is a log."""
    if not isinstance(body, dict):
        raise ValueError("bad bet")
    with _lock:
        st = load_state()
        if body.get("delete"):
            st["placed"] = [b for b in st["placed"] if b.get("id") != str(body["delete"])]
            save_state(st)
            _uncache()
            return {"ok": True, "placed": st["placed"]}
        b = {}
        for k, typ in BET_FIELDS.items():
            v = body.get(k)
            if v in (None, ""):
                continue
            try:
                b[k] = typ(v) if typ is float else str(v)[:200]
            except (TypeError, ValueError):
                raise ValueError(f"bad {k}") from None
        if not b.get("price") or b["price"] <= 1 or b.get("stake") is None or b["stake"] < 0 or not b.get("name"):
            raise ValueError("a bet needs a selection, a price above 1 and a stake")
        if b.get("market") not in (None, "h2h", "spreads", "totals", "other"):
            raise ValueError("bad market")
        if b.get("result") not in (None, "win", "loss", "push"):
            raise ValueError("bad result")
        b.setdefault("market", "other")
        b["t"] = int(time.time())
        b["id"] = f"b{b['t']}{len(st['placed'])}"
        if b.get("result"):
            b["profit"] = _r(profit(b["result"], b["price"], b["stake"]), 2)
        st["placed"].append(b)
        settle(st, time.time())
        save_state(st)
    _uncache()
    return {"ok": True, "bet": b}


def _uncache() -> None:
    from ..cache import _cache
    for k in ("results", "bets"):
        _cache.pop(f"nba-odds:{k}", None)


ACTIONS = {"bets": record_bet}        # POST handlers, for the shared server once it routes POSTs to private dashboards (see data/nba-odds/README.md)


def READINGS() -> list[dict]:
    """Value bets today, best EV, live flags and the 30-day CLV trend; lean +1 = better for the bettor. Snapshot files only."""
    lt, st = _latest(), load_state()
    if not lt and not st.get("flags"):
        return []
    rows = lt.get("rows") or []
    value = [r for r in rows if r["value"] and not r["live"]]
    best = max((r["ev"] for r in value), default=None)
    live_n = sum(1 for f in st.get("flags", []) if f["live"] and f["status"] == "active")
    c30 = track(st.get("flags", []))["clv30"]
    c = c30[-1][1] if c30 else None
    sgn = lambda v: 0 if v is None else 1 if v > 0 else -1 if v < 0 else 0
    return [{"tab": "today", "key": "value_n", "label": "Value bets today", "value": len(value), "lean": 1 if value else 0},
            {"tab": "today", "key": "best_ev", "label": "Best EV today", "value": _r(best, 4), "lean": 1 if best is not None and best >= min_ev() else 0},
            {"tab": "live", "key": "live_flags", "label": "Live flags now", "value": live_n, "lean": 1 if live_n else 0},
            {"tab": "results", "key": "clv30", "label": "Average CLV, 30 days", "value": _r(c, 4), "lean": sgn(c), "note": "above 0: the flagged prices beat the sharp close"}]


def roi_since(flags: list[dict], since: float) -> tuple[float | None, int]:
    """ROI (1 unit a flag) of the flags raised since `since` that have settled, and how many."""
    done = [f for f in flags if f["appeared"] >= since and f.get("profit") is not None]
    return (sum(f["profit"] for f in done) / len(done) if done else None), len(done)


def SIGNALS() -> list[dict]:
    """The owner's approved watch points (data/signals/watchlist.json), from the snapshot files only; lean +1 = better for the bettor."""
    lt, st = _latest(), load_state()
    now = time.time()
    rows = lt.get("rows") or []
    value = [r for r in rows if r["value"] and not r["live"]]
    best = max((r["ev"] for r in value), default=None)
    flags = st.get("flags", [])
    c30 = track(flags)["clv30"]
    clv = c30[-1][1] if c30 and c30[-1][0] >= now - 31 * 86400 else None
    roi, n_roi = roi_since(flags, now - 30 * 86400)
    q = st.get("quota", {})
    _, end = period_bounds(now)
    days_left = (end - now) / 86400
    left = None if q.get("remaining") is None else max(0.0, min(q["remaining"], budget() - (q.get("used") or 0)))
    share = None if left is None else left / budget()
    sgn = lambda v: 0 if v is None else 1 if v > 0 else -1 if v < 0 else 0
    return [{"key": "value_bets", "tab": "today", "label": "Value bets today", "value": len(value) if lt else None, "lean": 1 if value else 0,
             "watch": "more than 5", "crossed": len(value) > 5, **({} if lt else {"note": "no odds pulled yet"})},
            {"key": "best_ev", "tab": "today", "label": "Best EV today", "value": None if best is None else _r(best * 100, 1), "unit": "%", "lean": 1 if best is not None else 0,
             "watch": "above +8%", "crossed": best is not None and best > 0.08},
            {"key": "clv_30d", "tab": "results", "label": "Average closing-line value, 30 days", "value": None if clv is None else _r(clv * 100, 2), "unit": "%", "lean": sgn(clv),
             "watch": "turns negative", "crossed": clv is not None and clv < 0, **({} if clv is not None else {"note": "no closed flags in the last 30 days"})},
            {"key": "roi_30d", "tab": "results", "label": "ROI, 30 days", "value": None if roi is None else _r(roi * 100, 1), "unit": "%", "lean": sgn(roi),
             "watch": "below -5%", "crossed": roi is not None and roi < -0.05, "note": f"{n_roi} settled flags, 1 unit each"},
            {"key": "credits", "tab": "today", "label": "API credits left this month", "value": None if share is None else _r(share * 100, 1), "unit": "%",
             "lean": 0 if share is None else 1 if share >= 0.15 else -1, "watch": "below 15% with more than a week to go",
             "crossed": share is not None and share < 0.15 and days_left > 7,
             "note": (f"{int(left)} of {int(budget())} left, {days_left:.0f} days to the reset" if left is not None else "no pull yet")}]


def _ep(name, fn, ttl=15):
    def go():
        from ..cache import _cached
        return _cached(f"nba-odds:{name}", ttl, fn)
    go.__name__ = name
    return go


ENDPOINTS = {"today": _ep("today", today), "live": _ep("live", live), "moves": _ep("moves", moves, 30), "results": _ep("results", results),
             "teams": _ep("teams", teams, 600), "sim": _ep("sim", sim, 600), "bets": bets}
