"""NBA Odds (app/topics/nba_odds.py): the maths, the parsers, flags, closing lines, settlement, the credit budget and the payloads, on
fixtures shaped like The Odds API v4, NBA.com and ESPN responses. Live calls are marked network."""
from __future__ import annotations

import json
import os
import statistics
import time

import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import nba_odds as M

NOW = int(time.time())
H = 3600


def _iso(t: float) -> str:
    return pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _book(key, title, upd, h2h=None, spread=None, total=None):
    mk = []
    if h2h:
        mk.append({"key": "h2h", "last_update": _iso(upd), "outcomes": [{"name": n, "price": p} for n, p in h2h]})
    if spread:
        mk.append({"key": "spreads", "last_update": _iso(upd), "outcomes": [{"name": n, "price": p, "point": pt} for n, p, pt in spread]})
    if total:
        mk.append({"key": "totals", "last_update": _iso(upd), "outcomes": [{"name": n, "price": p, "point": pt} for n, p, pt in total]})
    return {"key": key, "title": title, "last_update": _iso(upd), "markets": mk}


BOS, NYK, LAL, DEN = "Boston Celtics", "New York Knicks", "Los Angeles Lakers", "Denver Nuggets"


def odds_raw(now: float = NOW, lad_bos: float = 2.10, pin_age: int = 60, live_game: bool = True, t0: float = NOW, drift: float = 0.0) -> list:
    """Game 1 (pre-game, tips in 2 hours): Ladbrokes Celtics 2.10 against a fair ~51%, so EV ~ +7%. Game 2: live, Ladbrokes fair-ish."""
    g1 = {"id": "g1", "sport_key": "basketball_nba", "commence_time": _iso(t0 + 2 * H), "home_team": BOS, "away_team": NYK, "bookmakers": [
        _book("ladbrokes_uk", "Ladbrokes", now - 30, h2h=[(BOS, lad_bos), (NYK, 1.72)], spread=[(BOS, 1.95, -1.5), (NYK, 1.87, 1.5)],
              total=[("Over", 1.91, 221.5), ("Under", 1.91, 221.5)]),
        _book("pinnacle", "Pinnacle", now - pin_age, h2h=[(BOS, round(1.96 + drift, 3)), (NYK, round(1.92 - drift, 3))], spread=[(BOS, 1.93, -1.5), (NYK, 1.97, 1.5)],
              total=[("Over", 1.95, 221.5), ("Under", 1.95, 221.5)]),
        _book("betfair_ex_uk", "Betfair", now - pin_age, h2h=[(BOS, 2.0), (NYK, 2.02)]),
        _book("williamhill", "William Hill", now - 50, h2h=[(BOS, 1.95), (NYK, 1.85)]),
        _book("onexbet", "1xBet", now - 50, h2h=[(BOS, 2.30), (NYK, 1.60)]),
    ]}
    out = [g1]
    if live_game:
        out.append({"id": "g2", "sport_key": "basketball_nba", "commence_time": _iso(t0 - H), "home_team": DEN, "away_team": LAL, "bookmakers": [
            _book("ladbrokes_uk", "Ladbrokes", now - 20, h2h=[(DEN, 1.50), (LAL, 2.60)], total=[("Over", 1.90, 230.5), ("Under", 1.90, 230.5)]),
            _book("pinnacle", "Pinnacle", now - 30, h2h=[(DEN, 1.55), (LAL, 2.55)], total=[("Over", 1.93, 230.5), ("Under", 1.93, 230.5)]),
        ]})
    return out


def scores_raw(now: float = NOW, final: bool = False) -> list:
    return [{"id": "g2", "sport_key": "basketball_nba", "commence_time": _iso(now - H), "completed": final, "home_team": DEN, "away_team": LAL,
             "scores": [{"name": DEN, "score": "64"}, {"name": LAL, "score": "60"}], "last_update": _iso(now)},
            {"id": "g1", "sport_key": "basketball_nba", "commence_time": _iso(now + 2 * H), "completed": False, "home_team": BOS, "away_team": NYK, "scores": None}]


SCOREBOARD = {"scoreboard": {"gameDate": "2026-10-28", "games": [
    {"gameId": "1", "gameStatus": 2, "gameStatusText": "Q3 5:12", "period": 3, "gameClock": "PT05M12.00S",
     "homeTeam": {"teamName": "Nuggets", "teamCity": "Denver", "teamTricode": "DEN", "score": 64},
     "awayTeam": {"teamName": "Lakers", "teamCity": "Los Angeles", "teamTricode": "LAL", "score": 60}},
    {"gameId": "2", "gameStatus": 1, "gameStatusText": "7:30 pm ET", "period": 0, "gameClock": "",
     "homeTeam": {"teamName": "Celtics", "teamCity": "Boston", "teamTricode": "BOS", "score": 0},
     "awayTeam": {"teamName": "Knicks", "teamCity": "New York", "teamTricode": "NYK", "score": 0}}]}}


def schedule(now: float = NOW) -> dict:
    """Celtics played last night (a back-to-back tonight); Knicks two nights ago."""
    day = lambda d, h, a, hs, as_, st=3: {"gameId": f"{h}{d}", "gameStatus": st, "gameDateTimeUTC": _iso(now - d * 86400),
                                          "homeTeam": {"teamName": h, "teamCity": "", "score": hs}, "awayTeam": {"teamName": a, "teamCity": "", "score": as_}}
    games = [day(1, "Celtics", "Heat", 110, 100), day(2, "Knicks", "Bulls", 99, 101), day(3, "Celtics", "Bulls", 120, 95), day(5, "Nets", "Knicks", 90, 100),
             day(-0.08, "Celtics", "Knicks", 0, 0, 1)]
    return {"leagueSchedule": {"seasonYear": "2026-27", "gameDates": [{"gameDate": "x", "games": games}]}}


INJ = {"injuries": [{"displayName": "Boston Celtics", "injuries": [{"athlete": {"displayName": "Jayson Tatum"}, "status": "Out", "shortComment": "Achilles", "date": "2026-10-20T00:00Z"}]}]}


def poly_nba(now: float = NOW) -> list:
    """Gamma NBA events: the moneyline of Lakers @ Nuggets (crowd 36/64 by the bid-ask middle) plus a spread market to ignore, and an
    unrelated game."""
    mk = lambda q, outs, prices, **k: {"question": q, "outcomes": json.dumps(outs), "outcomePrices": json.dumps(prices), "closed": False, "active": True,
                                       "liquidityNum": 52000.0, "volume24hr": 131000.0, "gameStartTime": _iso(now - H), **k}
    return [{"slug": "nba-lal-den-2026-10-28", "title": "Lakers vs. Nuggets", "startDate": _iso(now - H), "tags": [{"slug": "nba"}, {"slug": "sports"}],
             "markets": [mk("Lakers vs. Nuggets", ["Lakers", "Nuggets"], ["0.37", "0.63"], bestBid=0.35, bestAsk=0.37),
                         mk("Spread: Lakers (+3.5)", ["Yes", "No"], ["0.5", "0.5"])]},
            {"slug": "nba-mia-chi", "title": "Heat vs. Bulls", "startDate": _iso(now + 5 * H), "tags": [{"slug": "nba"}],
             "markets": [mk("Heat vs. Bulls", ["Heat", "Bulls"], ["0.55", "0.45"])]},
            {"slug": "nba-closed", "title": "Lakers vs. Nuggets", "startDate": _iso(now - 20 * 86400), "tags": [{"slug": "nba"}],
             "markets": [mk("Lakers vs. Nuggets", ["Lakers", "Nuggets"], ["0.9", "0.1"], closed=True)]}]


def kalshi_nba(now: float = NOW) -> dict:
    mk = lambda t, sub, last, bid, ask: {"ticker": "KXNBAGAME-26OCT28LALDEN-" + t, "event_ticker": "KXNBAGAME-26OCT28LALDEN", "title": "Los Angeles Lakers vs Denver Nuggets Winner?",
                                         "yes_sub_title": sub, "status": "active", "last_price_dollars": last, "yes_bid_dollars": bid, "yes_ask_dollars": ask,
                                         "volume_fp": "12000", "volume_24h_fp": "3000", "close_time": _iso(now + 3 * H), "expected_expiration_time": _iso(now + 3 * H)}
    return {"markets": [mk("LAL", "Los Angeles Lakers", "0.40", "0.39", "0.41"), mk("DEN", "Denver Nuggets", "0.62", "0.61", "0.63"),
                        {"ticker": "KXNBAGAME-X-BOS", "event_ticker": "KXNBAGAME-X", "title": "Boston Celtics vs New York Knicks Winner?", "yes_sub_title": "Boston Celtics",
                         "status": "active", "last_price_dollars": "0.5", "volume_fp": "1", "close_time": _iso(now + 4 * H)}]}      # one side only: no pair


def fake_fetch_json(url, ttl=0, **kw):
    if "gamma-api.polymarket.com" in url:
        return poly_nba()
    if "kalshi.com" in url:
        return kalshi_nba()
    if "todaysScoreboard" in url:
        return SCOREBOARD
    if "scheduleLeague" in url:
        return schedule()
    if "injuries" in url:
        return INJ
    raise ConnectionError("fixture: no such source")


class Resp:
    def __init__(self, body, status=200, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body


def make_api(now_fn=lambda: NOW, used0: int = 1000, kw_fn=lambda: {}, **kw):
    """A fake requests.get for The Odds API: odds cost 6 credits, scores 1 (2 with daysFrom); records every call."""
    st = {"used": used0, "calls": []}

    def get(url, params=None, headers=None, timeout=None):
        assert params.get("apiKey") == "test-key"
        st["calls"].append((url, dict(params)))
        cost = 6 if url.endswith("/odds") else 2 if "daysFrom" in params else 1
        st["used"] += cost
        body = odds_raw(now_fn(), **{**kw, **kw_fn()}) if url.endswith("/odds") else scores_raw(now_fn())
        return Resp(body, 200, {"x-requests-used": str(st["used"]), "x-requests-remaining": str(20000 - st["used"]), "x-requests-last": str(cost)})
    return get, st


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    get, st = make_api()
    monkeypatch.setattr(M.requests, "get", get)
    cache._cache.clear()
    yield st
    cache._cache.clear()


def smoke_patch() -> None:
    """Used by scripts/smoke.py: a fake Odds API and NBA feeds, and a few pulls so every tab has data (flags, history, a settled result)."""
    import tempfile
    from pathlib import Path
    M.DIR = Path(tempfile.mkdtemp())          # this dashboard's files only: the shared B.SNAP_DIR stays where the other dashboards put it
    os.environ["ODDS_API_KEY"] = "test-key"
    M.fetch_json = fake_fetch_json
    clock = {"t": NOW - 6 * H, "k": 0}
    get, _ = make_api(lambda: clock["t"], kw_fn=lambda: {"lad_bos": (2.20, 2.15, 2.10, 2.10, 2.05, 2.10, 2.12, 2.10)[clock["k"]], "drift": 0.01 * clock["k"]})
    M.requests.get = get
    for k in range(8):
        clock["t"], clock["k"] = NOW - (7 - k) * 45 * 60, k
        M.poll_once("pre-game", clock["t"])
    st = M.load_state()
    st["results"]["g0"] = {"completed": True, "home": BOS, "away": NYK, "home_score": 110.0, "away_score": 100.0}
    st["flags"].append({"id": "g0|h2h|Boston Celtics||1", "key": "g0|h2h|Boston Celtics|", "event_id": "g0", "game": f"{NYK} @ {BOS}", "home": BOS, "away": NYK,
                        "commence": NOW - 30 * H, "market": "h2h", "name": BOS, "point": None, "label": "Celtics to win", "live": False, "price": 2.0,
                        "fair_p": 0.52, "ev": 0.04, "appeared": NOW - 33 * H, "status": "gone", "gone": NOW - 30 * H, "why": "tipped off", "max_ev": 0.04})
    st["close_pre"]["g0|h2h|Boston Celtics|"] = {"p": 0.55, "lad": 1.85, "t": NOW - 30 * H}
    M.settle(st, NOW)
    M.save_state(st)
    M.record_bet({"game": f"{NYK} @ {BOS}", "event_id": "g0", "market": "h2h", "name": BOS, "price": 2.0, "stake": 10})


# ------------------------------------------------------------------ maths
def test_devig_multiplicative_and_power_sum_to_one_and_differ_on_longshots():
    m = M.devig([1.30, 3.80])
    p = M.devig([1.30, 3.80], "power")
    assert abs(sum(m) - 1) < 1e-9 and abs(sum(p) - 1) < 1e-9
    assert abs(m[0] - (1 / 1.3) / (1 / 1.3 + 1 / 3.8)) < 1e-12
    assert p[0] > m[0] and p[1] < m[1]                       # the power method takes more off the long shot
    assert M.devig([2.0, 2.0], "power") == pytest.approx([0.5, 0.5])


def test_margin_ev_kelly_and_commission():
    assert M.margin([1.91, 1.91]) == pytest.approx(2 / 1.91 - 1)
    assert M.ev(2.10, 0.5) == pytest.approx(0.05)
    assert M.kelly(2.10, 0.5) == pytest.approx((1.1 * 0.5 - 0.5) / 1.1)
    assert M.kelly(1.80, 0.5) == 0.0
    assert M.net_of_commission(3.0, 0.05) == pytest.approx(2.9)


def test_parse_odds_and_groups():
    g = M.parse_odds(odds_raw())[0]
    assert g["home"] == BOS and g["commence"] == NOW + 2 * H
    lad = M.lad_book(g["books"])
    assert lad["title"] == "Ladbrokes"
    sp = M.groups("spreads", lad["markets"]["spreads"]["outcomes"])
    assert len(sp) == 1 and {o["point"] for o in sp[0]} == {-1.5, 1.5}
    assert M.label("spreads", BOS, -1.5) == "Celtics -1.5" and M.label("totals", "Over", 221.5) == "Over 221.5"


def test_evaluate_fair_is_median_of_fresh_sharps_and_flags_value():
    games = M.parse_odds(odds_raw())
    rows = M.evaluate(games, {}, NOW)
    r = next(r for r in rows if r["key"] == "g1|h2h|Boston Celtics|")
    pin = M.devig([1.96, 1.92])[0]
    exch = M.devig([M.net_of_commission(2.0, 0.05), M.net_of_commission(2.02, 0.05)])[0]
    assert r["fair_p"] == pytest.approx((pin + exch) / 2, abs=1e-5)
    assert r["ev"] == pytest.approx(2.10 * r["fair_p"] - 1, abs=1e-4)
    assert r["value"] and r["fresh"] and not r["live"]
    assert r["best"]["key"] == "ladbrokes_uk" and r["best"]["price"] == 2.10       # 1xBet (eu, not UK) is not a UK book
    assert r["margin"] == pytest.approx(1 / 2.10 + 1 / 1.72 - 1, abs=1e-5)
    live = next(r for r in rows if r["event_id"] == "g2" and r["market"] == "h2h")
    assert live["live"]


def test_stale_sharp_line_cannot_make_value():
    rows = M.evaluate(M.parse_odds(odds_raw(pin_age=900)), {}, NOW)
    r = next(r for r in rows if r["key"] == "g1|h2h|Boston Celtics|")
    assert r["fair_p"] is not None and not r["fresh"] and not r["value"]
    rows = M.evaluate(M.parse_odds(odds_raw(pin_age=200)), {}, NOW)              # 200 s: fresh pre-game ...
    assert next(r for r in rows if r["key"] == "g1|h2h|Boston Celtics|")["fresh"]
    live = [r for r in M.evaluate(M.parse_odds(odds_raw()), {}, NOW + 150) if r["event_id"] == "g2"]
    assert live and not any(r["fresh"] for r in live)                            # ... but 2 minutes is the limit live


def test_min_ev_from_env(monkeypatch):
    monkeypatch.setenv("MIN_EV", "0.2")
    rows = M.evaluate(M.parse_odds(odds_raw()), {}, NOW)
    assert not any(r["value"] for r in rows)


# ------------------------------------------------------------------ flags, closing line, results
def test_flag_appears_then_is_struck_out_when_price_moves_or_fair_catches_up():
    flags = []
    rows = M.evaluate(M.parse_odds(odds_raw()), {}, NOW)
    M.update_flags(flags, rows, NOW)
    f = next(f for f in flags if f["key"] == "g1|h2h|Boston Celtics|")
    assert f["status"] == "active" and f["appeared"] == NOW and f["price"] == 2.10
    rows2 = M.evaluate(M.parse_odds(odds_raw(NOW + 300, lad_bos=1.95)), {}, NOW + 300)
    M.update_flags(flags, rows2, NOW + 300)
    assert f["status"] == "gone" and f["why"].startswith("price moved to 1.95") and f["gone"] == NOW + 300
    rows3 = M.evaluate(M.parse_odds(odds_raw(NOW + 600)), {}, NOW + 600)         # back to 2.10: the same flag again
    M.update_flags(flags, rows3, NOW + 600)
    assert f["status"] == "active" and sum(x["key"] == f["key"] for x in flags) == 1


def test_flag_struck_when_sharp_goes_stale_and_when_game_tips_off():
    flags = []
    M.update_flags(flags, M.evaluate(M.parse_odds(odds_raw()), {}, NOW), NOW)
    M.update_flags(flags, M.evaluate(M.parse_odds(odds_raw(NOW, pin_age=2000)), {}, NOW), NOW + 1)
    f = next(f for f in flags if f["key"] == "g1|h2h|Boston Celtics|")
    assert f["why"] == "sharp line stale"
    flags = []
    M.update_flags(flags, M.evaluate(M.parse_odds(odds_raw()), {}, NOW), NOW)
    later = NOW + 2 * H + 60                                                  # the game has started: the same key is now a live row
    M.update_flags(flags, M.evaluate(M.parse_odds(odds_raw(later, t0=NOW)), {}, later), later)
    pre = next(f for f in flags if f["key"] == "g1|h2h|Boston Celtics|" and not f["live"])
    assert pre["status"] == "gone" and pre["why"] == "tipped off"


def test_clv_and_settlement():
    st = {"flags": [], "results": {}, "placed": []}
    rows = M.evaluate(M.parse_odds(odds_raw()), {}, NOW)
    M.update_flags(st["flags"], rows, NOW)
    M.record_close(st, rows, NOW)
    M.settle(st, NOW)
    f = next(f for f in st["flags"] if f["key"] == "g1|h2h|Boston Celtics|")
    assert f.get("clv") is None                                              # not tipped off yet: no close
    st["close_pre"][f["key"]] = {"p": 0.55, "lad": 1.85, "t": NOW + H}
    st["results"]["g1"] = {"completed": True, "home": BOS, "away": NYK, "home_score": 101.0, "away_score": 99.0}
    M.settle(st, NOW + 5 * H)
    assert f["clv"] == pytest.approx(2.10 * 0.55 - 1) and f["result"] == "win" and f["profit"] == pytest.approx(1.10)
    sp = next(f for f in st["flags"] if f["market"] == "spreads") if any(f["market"] == "spreads" for f in st["flags"]) else None
    res = st["results"]["g1"]
    assert M.outcome({"market": "spreads", "name": BOS, "point": -1.5}, res) == "win"
    assert M.outcome({"market": "spreads", "name": BOS, "point": -2.0}, res) == "push"
    assert M.outcome({"market": "spreads", "name": NYK, "point": 1.5}, res) == "loss"
    assert M.outcome({"market": "totals", "name": "Under", "point": 221.5}, res) == "win"
    assert M.outcome({"market": "h2h", "name": NYK, "point": None}, {**res, "completed": False}) is None
    assert sp is None or sp["result"] in ("win", "loss", "push")


def test_track_roi_and_clv30():
    day = 86400
    flags = [{"appeared": NOW - 3 * day, "profit": 1.0, "clv": 0.03, "result": "win"}, {"appeared": NOW - 2 * day, "profit": -1.0, "clv": -0.01, "result": "loss"},
             {"appeared": NOW - day, "profit": None, "clv": 0.02, "result": None}]
    t = M.track(flags)
    assert t["roi"][-1][1] == 0.0 and t["settled"] == 2 and t["clv_all"] == pytest.approx(0.04 / 3, abs=1e-5)
    assert t["clv30"][-1][1] == pytest.approx(0.04 / 3, abs=1e-5) and t["beat_close"] == pytest.approx(2 / 3, abs=1e-4)


# ------------------------------------------------------------------ schedule and budget
def _uk(h, m=0):
    """A unix time today at h:m UK."""
    return int(pd.Timestamp.now(tz=M.UK).normalize().replace(hour=h, minute=m).timestamp())


def _game(commence):
    return {"id": "x", "home": BOS, "away": NYK, "commence": commence, "books": {}}


def test_decide_morning_pregame_live_and_idle(monkeypatch):
    monkeypatch.setenv("ODDS_MONTHLY_BUDGET", "1e9")
    assert M.decide({"quota": {}}, [], {}, _uk(9, 59)) is None                           # before 10:00, nothing on
    assert M.decide({"quota": {}}, [], {}, _uk(10, 0)) == "10:00 pull"
    done = {"quota": {}, "morning": M.uk_date(_uk(10))}
    tip = _uk(23, 30)
    assert M.decide({**done, "last_poll": _uk(10)}, [_game(tip)], {}, tip - 4 * H) is None           # more than 3 h before tip-off
    assert M.decide({**done, "last_poll": _uk(10)}, [_game(tip)], {}, tip - 3 * H) == "pre-game"
    assert M.decide({**done, "last_poll": tip - 3 * H}, [_game(tip)], {}, tip - 3 * H + 29 * 60) is None
    assert M.decide({**done, "last_poll": tip - 3 * H}, [_game(tip)], {}, tip - 3 * H + 30 * 60) == "pre-game"
    assert M.decide({**done, "last_poll": tip + 60}, [_game(tip)], {}, tip + 4 * 60) is None          # live: every 5 minutes
    assert M.decide({**done, "last_poll": tip + 60}, [_game(tip)], {}, tip + 6 * 60) == "live"
    final = {"x": {"completed": True}}
    assert M.decide({**done, "last_poll": tip + 60}, [_game(tip)], final, tip + 3 * H) is None        # over: back to idle


def test_pace_slows_down_and_stops_on_budget(monkeypatch):
    t = _uk(22)
    tips = [_uk(23, 30), _uk(23, 30) + 3 * H]
    monkeypatch.setenv("ODDS_MONTHLY_BUDGET", "19000")
    start, end = M.period_bounds(t)
    days = max(0.25, (end - t) / 86400)                                   # same floor as pace(): on the last day of a month only hours are left
    need = M.est_day_cost(tips, 6)
    assert M.pace({"quota": {"used": 0, "remaining": 20000}}, t, tips) == 1.0 or need > 19000 / days
    tight = 19000 - need * days / 3                                        # a third of what the rest of the month needs
    f = M.pace({"quota": {"used": tight, "remaining": 20000 - tight}}, t, tips)
    assert f == pytest.approx(3, rel=0.01)
    assert M.pace({"quota": {"used": 19000, "remaining": 1000}}, t, tips) == float("inf")
    assert M.pace({"quota": {"used": 100, "remaining": 150}}, t, tips) == float("inf")             # the reserve is never spent
    st = {"quota": {"used": 19000, "remaining": 1000}, "morning": None}
    assert M.decide(st, [], {}, _uk(10, 5)) is None and st["pace"] is None
    f2 = M.pace({"quota": {"used": tight, "remaining": 20000 - tight}}, t, tips)
    st = {"quota": {"used": tight, "remaining": 20000 - tight}, "morning": M.uk_date(t), "last_poll": tips[0] + 60}
    assert M.decide(st, [_game(tips[0])], {}, tips[0] + 6 * 60) is None                           # 5 min stretched by the pace
    assert M.decide(st, [_game(tips[0])], {}, tips[0] + 60 + int(300 * f2) + 1) == "live"


def test_typical_month_fits_the_default_budget():
    """Ten games from 00:00 to 03:30 UK every night: 30 days at full cadence stay under 19,000 credits."""
    tips = [_uk(0), _uk(3, 30)]
    assert 30 * M.est_day_cost(tips, 6) < 19000


def test_period_bounds_reset_day():
    t = pd.Timestamp("2026-10-28T12:00Z").timestamp()
    s, e = M.period_bounds(t, 15)
    assert pd.Timestamp(s, unit="s").strftime("%m-%d") == "10-15" and pd.Timestamp(e, unit="s").strftime("%m-%d") == "11-15"
    s, e = M.period_bounds(t, 1)
    assert pd.Timestamp(e, unit="s").strftime("%m-%d") == "11-01"


# ------------------------------------------------------------------ the pull and the payloads
def test_poll_once_writes_snapshots_tracks_quota_and_never_leaks_the_key(mocked):
    r = M.poll_once("10:00 pull", NOW)
    assert r["games"] == 2 and r["value"] >= 1 and "error" not in r
    st = M.load_state()
    assert st["quota"]["used"] == mocked["used"] and st["quota"]["remaining"] == 20000 - mocked["used"] and st["quota"]["odds_cost"] == 6
    assert st["morning"] == M.uk_date(NOW)
    odds_call = mocked["calls"][0]
    assert odds_call[1]["regions"] == "uk,eu" and odds_call[1]["markets"] == "h2h,spreads,totals" and odds_call[1]["oddsFormat"] == "decimal"
    assert any("daysFrom" in c[1] for c in mocked["calls"])                    # the morning pull fetches finals
    for f in (B.SNAP_DIR / "nba-odds").rglob("*"):
        if f.is_file():
            assert "test-key" not in f.read_text()
    for name, fn in M.ENDPOINTS.items():
        assert "test-key" not in json.dumps(B.json_safe(fn())), name
    assert M.read_history("g1")


def test_errors_do_not_carry_the_url(mocked, monkeypatch):
    monkeypatch.setattr(M.requests, "get", lambda *a, **k: Resp({"message": "bad key"}, 401, {}))
    r = M.poll_once("10:00 pull", NOW)
    assert r["error"] == "HTTP 401" and M.load_state()["error"] == "HTTP 401"
    monkeypatch.delenv("ODDS_API_KEY")
    assert M.poll_once("x", NOW)["error"] == "ODDS_API_KEY is not set"


def test_page_requests_never_call_the_odds_api(mocked, monkeypatch):
    M.poll_once("pre-game", NOW)
    calls = len(mocked["calls"])
    monkeypatch.setattr(M.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("page called the Odds API")))
    for fn in M.ENDPOINTS.values():
        fn()
    M.READINGS()
    assert len(mocked["calls"]) == calls


def test_payloads(mocked):
    M.poll_once("pre-game", NOW - 600)
    M.poll_once("live", NOW)
    t = M.today()
    assert t["value"] and t["value"][0]["ev"] >= t["value"][-1]["ev"]
    assert t["credits"]["remaining"] is not None and t["credits"]["key_set"] and t["credits"]["budget"] == 19000
    assert any(g["id"] == "g1" for g in t["games"])
    lv = M.live()
    g2 = next(g for g in lv["games"] if g["id"] == "g2")
    assert g2["home_score"] == 64 and g2["clock"] == "5:12" and g2["period"] == 3
    mv = M.moves()
    g1 = next(g for g in mv["games"] if g["id"] == "g1")
    assert any("ladbrokes_uk" in s["books"] and "pinnacle" in s["books"] for s in g1["series"])
    tm = M.teams()
    cel = next(x for x in tm["teams"] if x["team"] == "Celtics")
    assert cel["b2b"] is True and cel["injuries"][0]["player"] == "Jayson Tatum" and cel["w"] == 2
    kn = next(x for x in tm["teams"] if x["team"] == "Knicks")
    assert kn["rest"] == 1 and kn["b2b"] is False
    res = M.results()
    assert res["flags"] and "track" in res
    for fn in M.ENDPOINTS.values():
        B.json_safe(fn())
    rd = M.READINGS()
    assert {r["key"] for r in rd} == {"value_n", "best_ev", "live_flags", "clv30"}
    assert next(r for r in rd if r["key"] == "value_n")["lean"] == 1


# ------------------------------------------------------------------ prediction markets as the crowd's price
def test_parse_poly_nba_keeps_moneylines_only_and_uses_the_bid_ask_middle():
    ms = M.parse_poly_nba(poly_nba())
    assert [sorted(m["teams"]) for m in ms] == [["Lakers", "Nuggets"], ["Bulls", "Heat"]]        # the spread market and the closed event are dropped
    lal = ms[0]
    assert lal["teams"]["Lakers"] == pytest.approx(0.36) and lal["teams"]["Nuggets"] == pytest.approx(0.64)
    assert lal["url"] == "https://polymarket.com/event/nba-lal-den-2026-10-28" and lal["liq"] == 52000 and lal["start"] == NOW - H
    assert ms[1]["teams"]["Heat"] == pytest.approx(0.55)


def test_parse_kalshi_nba_pairs_the_two_yes_markets():
    ms = M.parse_kalshi_nba(kalshi_nba())
    assert len(ms) == 1 and ms[0]["teams"]["Lakers"] == pytest.approx(0.40 / 1.02) and ms[0]["teams"]["Nuggets"] == pytest.approx(0.62 / 1.02)
    assert ms[0]["vol24"] == 6000 and ms[0]["bid"] == 0.39 and ms[0]["url"].startswith("https://kalshi.com/markets/kxnbagame")


def test_match_crowd_by_teams_and_date():
    games = M.parse_odds(odds_raw())
    ms = M.parse_poly_nba(poly_nba())
    by = M.match_crowd(games, ms)
    assert set(by) == {"g2"} and by["g2"]["teams"]["Nuggets"] == pytest.approx(0.64)
    far = [dict(m, start=NOW - 3 * 86400) for m in ms]
    assert M.match_crowd(games, far) == {}


def test_attach_crowd_and_evaluate_columns(mocked, monkeypatch):
    games = M.parse_odds(odds_raw())
    assert M.attach_crowd(games, NOW, 60) == 2
    g2 = next(g for g in games if g["id"] == "g2")
    assert g2["books"]["polymarket"]["title"] == "Polymarket (crowd)" and g2["books"]["kalshi"]["markets"]["h2h"]["outcomes"][0]["name"] == DEN
    assert g2["books"]["polymarket"]["markets"]["h2h"]["outcomes"][0]["price"] == pytest.approx(1 / 0.64, abs=1e-3)
    rows = M.evaluate(games, {}, NOW)
    den = next(r for r in rows if r["event_id"] == "g2" and r["name"] == DEN)
    assert den["crowd"]["polymarket"]["p"] == pytest.approx(0.64, abs=1e-3) and den["crowd"]["polymarket"]["ev"] == pytest.approx(1.5 * 0.64 - 1, abs=1e-3)
    assert den["crowd"]["kalshi"]["p"] == pytest.approx(0.62 / 1.02, abs=1e-3) and den["crowd"]["polymarket"]["url"]
    assert "polymarket" not in den["sharp"]                          # crowd prices are not in the fair unless asked
    pin = M.devig([1.55, 2.55])[0]
    assert den["fair_p"] == pytest.approx(pin, abs=1e-4)
    monkeypatch.setenv("NBA_FAIR_CROWD", "1")
    rows = M.evaluate(games, {}, NOW)
    den = next(r for r in rows if r["event_id"] == "g2" and r["name"] == DEN)
    assert set(den["sharp"]) == {"pinnacle", "polymarket", "kalshi"}
    assert den["fair_p"] == pytest.approx(statistics.median([pin, 0.64, 0.62 / 1.02]), abs=1e-3)
    g1 = next(r for r in rows if r["event_id"] == "g1" and r["market"] == "h2h")
    assert g1["crowd"] == {}                                           # no market for that game: nothing claimed
    assert not any(r["crowd"] for r in rows if r["market"] != "h2h")  # the crowd has a moneyline only


def test_poll_carries_the_crowd_into_history_and_moves(mocked):
    M.poll_once("live", NOW)
    lt = M._latest()
    assert lt["books_seen"]["polymarket"] == "Polymarket (crowd)"
    assert any(h[1] == "polymarket" for h in M.read_history("g2")) and any(h[1] == "kalshi" for h in M.read_history("g2"))
    mv = M.moves()
    g2 = next(g for g in mv["games"] if g["id"] == "g2")
    assert any("polymarket" in s["books"] for s in g2["series"]) and "polymarket" in mv["books"]
    lv = M.live()
    den = next(r for r in next(g for g in lv["games"] if g["id"] == "g2")["markets"]["h2h"] if r["name"] == DEN)
    assert den["crowd"]["polymarket"]["p"] == pytest.approx(0.64, abs=1e-3) and lv["fair_crowd"] is False
    for fn in M.ENDPOINTS.values():
        B.json_safe(fn())


def test_crowd_sources_down_do_not_break_the_pull(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch_json", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    r = M.poll_once("live", NOW)
    assert "error" not in r and r["games"] == 2
    assert "polymarket" not in M._latest()["books_seen"]


def test_signals_follow_the_watchlist(mocked, monkeypatch):
    import json as _j
    want = [r["key"] for r in _j.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["nba-odds"]]
    sig = M.SIGNALS()                                             # nothing pulled yet: every key, nothing crossed
    assert [r["key"] for r in sig] == want and not any(r["crossed"] for r in sig)
    B.json_safe(sig)
    M.poll_once("pre-game", NOW)
    by = {r["key"]: r for r in M.SIGNALS()}
    assert by["value_bets"]["value"] >= 1 and not by["value_bets"]["crossed"]
    assert by["best_ev"]["value"] > 0 and by["best_ev"]["crossed"] == (by["best_ev"]["value"] > 8)
    st = M.load_state()
    day = 86400
    st["flags"] = [{"appeared": NOW - 2 * day, "profit": -1.0, "result": "loss", "clv": -0.02, "live": False, "ev": 0.03, "status": "gone"},
                   {"appeared": NOW - 3 * day, "profit": 0.9, "result": "win", "clv": -0.01, "live": False, "ev": 0.03, "status": "gone"},
                   {"appeared": NOW - 60 * day, "profit": 5.0, "result": "win", "clv": 0.2, "live": False, "ev": 0.03, "status": "gone"}]
    st["quota"] = {"used": 17000, "remaining": 3000}
    M.save_state(st)
    by = {r["key"]: r for r in M.SIGNALS()}
    assert by["clv_30d"]["crossed"] and by["clv_30d"]["value"] < 0
    assert by["roi_30d"]["value"] == pytest.approx(-5.0) and not by["roi_30d"]["crossed"]      # (-1 + 0.9) / 2: the 60-day-old win is out
    _, end = M.period_bounds(time.time())
    assert by["credits"]["value"] == pytest.approx(2000 / 19000 * 100, abs=0.1) and by["credits"]["crossed"] == ((end - time.time()) / day > 7)


def test_smoke_patch_leaves_the_shared_snapshot_dir_alone(monkeypatch):
    before = B.SNAP_DIR
    monkeypatch.setattr(M, "DIR", None)
    monkeypatch.setattr(M, "fetch_json", M.fetch_json)
    monkeypatch.setattr(M.requests, "get", M.requests.get)
    monkeypatch.setenv("ODDS_API_KEY", "x")
    smoke_patch()
    assert B.SNAP_DIR == before and M.DIR != before and (M.DIR / "state.json").exists()


def test_scoreboard_falls_back_to_espn(monkeypatch):
    espn = {"events": [{"status": {"displayClock": "2:01", "period": 4, "type": {"state": "in", "shortDetail": "2:01 - 4th"}},
                        "competitions": [{"competitors": [{"homeAway": "home", "score": "99", "team": {"displayName": "Denver Nuggets"}},
                                                          {"homeAway": "away", "score": "97", "team": {"displayName": "Los Angeles Lakers"}}]}]}]}
    monkeypatch.setattr(M, "fetch_json", lambda url, ttl=0, **k: espn if "espn" in url else (_ for _ in ()).throw(ConnectionError()))
    b = M.nba_scoreboard()
    assert b["Nuggets"]["clock"] == "2:01" and b["Lakers"]["home_score"] == 99 and b["Nuggets"]["source"] == "ESPN"


def test_record_bet_validates_and_settles(mocked):
    with pytest.raises(ValueError):
        M.record_bet({"name": BOS, "price": 1.0, "stake": 5})
    with pytest.raises(ValueError):
        M.record_bet({"name": BOS, "price": 2.0, "stake": 5, "market": "<script>"})
    M.poll_once("pre-game", NOW)
    b = M.record_bet({"event_id": "g2", "game": "LAL @ DEN", "market": "h2h", "name": DEN, "price": 1.5, "stake": 20, "junk": "x"})["bet"]
    assert "junk" not in b and b["stake"] == 20
    st = M.load_state()
    st["results"]["g2"] = {"completed": True, "home": DEN, "away": LAL, "home_score": 110.0, "away_score": 100.0}
    M.settle(st, NOW)
    assert st["placed"][0]["result"] == "win" and st["placed"][0]["profit"] == 10.0
    M.save_state(st)
    assert M.results()["placed_summary"]["profit"] == 10.0
    M.record_bet({"delete": b["id"]})
    assert M.bets()["placed"] == []


def test_topic_is_private_or_unregistered():
    from app.topics import Topic
    if "private" in Topic.__dataclass_fields__:
        assert M.TOPIC is not None and M.TOPIC.private and M.TOPIC.slug == "nba-odds"
    else:
        assert M.TOPIC is None and M.start_poller()["poller"].startswith("off")


def test_injuries_csv_is_well_formed():
    rows = M.manual_rows("nba-odds", "injuries")
    for r in rows:
        assert r["team"] and r["player"] and r["status"] and r["source"].startswith("http")


# ------------------------------------------------------------------ live sources (run by hand)
@pytest.mark.network
def test_live_nba_cdn_and_espn():
    from app import cache
    cache._cache.clear()
    assert isinstance(M.nba_scoreboard(), dict)
    assert len(M.season_games()) > 100


@pytest.mark.network
def test_live_odds_api_bookmaker_keys():
    """Needs ODDS_API_KEY; costs 6 credits. Confirms the keys this module relies on are the ones the API sends."""
    if not M.api_key():
        pytest.skip("ODDS_API_KEY not set")
    st = {"quota": {}}
    raw = M.odds_get(f"/sports/{M.SPORT}/odds", {"regions": M.REGIONS, "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}, st)
    keys = {b["key"] for e in raw for b in e.get("bookmakers", [])}
    print("bookmaker keys seen:", sorted(keys), "quota:", st["quota"])
    if raw:
        assert M.LAD in keys and M.PINNACLE in keys
