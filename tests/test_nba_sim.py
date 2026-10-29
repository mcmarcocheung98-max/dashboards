"""The synthetic live-odds lab (app/topics/nba_sim.py): the simulator's calibration, its analytic truth against Monte Carlo rollouts, the
model fit, the bookmaker step functions, the flag scoring, and the live model used by the Live tab. No network anywhere."""
from __future__ import annotations

import numpy as np
import pytest

from app.topics import _base as B
from app.topics import nba_odds as O
from app.topics import nba_sim as S


@pytest.fixture
def snaps(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    from app import cache
    cache._cache.clear()
    yield
    cache._cache.clear()


def test_phi_matches_the_normal_cdf():
    import math
    for z in (-3, -1, -0.3, 0, 0.5, 1.96, 3):
        assert abs(float(S.phi(z)) - 0.5 * (1 + math.erf(z / math.sqrt(2)))) < 2e-7


def test_game_is_calibrated_to_its_spread_and_total():
    rng = np.random.default_rng(1)
    gs = [S.sim_game(rng, -5.5, 226.0) for _ in range(600)]
    margins = np.array([g["home"] - g["away"] for g in gs])
    totals = np.array([g["home"] + g["away"] for g in gs])
    assert abs(margins.mean() - 5.5) < 1.5                     # the home side wins by the spread on average
    assert abs(totals.mean() - 226) < 3
    assert 9 < margins.std() < 14                              # an NBA-like spread of final margins (the catch-up term keeps it under the iid 15)
    assert all(g["home"] != g["away"] for g in gs)             # overtime settles every game
    assert all(g["end"] >= S.REG and (g["end"] - S.REG) % S.OT == 0 for g in gs)
    ev = gs[0]["events"]
    assert ev[0] == (0.0, 0, 0) and all(a[0] < b[0] for a, b in zip(ev, ev[1:]))


def test_truth_matches_monte_carlo_rollouts():
    rng = np.random.default_rng(3)
    for spread, total in ((-6.5, 230.0), (3.0, 220.0)):
        g = S.sim_game(rng, spread, total)
        for t in (0, 600, 1500, 2400, 2800):
            an, mc = S.truth(g, t), S.rollout(rng, g, t, 3000)
            assert abs(an - mc) < 0.03, (spread, t, an, mc)
    assert S.truth(g, g["end"]) in (0.0, 1.0)


def test_state_period_and_fraction():
    g = {"events": [(0.0, 0, 0), (30.0, 2, 0), (45.5, 2, 3)]}
    assert S.state_at(g, 10) == (0, 0, 10) and S.state_at(g, 44) == (2, 0, 14) and S.state_at(g, 100)[:2] == (2, 3)
    assert S.period_at(0) == 1 and S.period_at(719) == 1 and S.period_at(720) == 2 and S.period_at(2879) == 4 and S.period_at(2880) == 5 and S.period_at(3200) == 6
    assert S.frac_left(0) == 1 and abs(S.frac_left(1440) - 0.5) < 1e-9 and 0 < S.frac_left(2900) < 0.1


def test_books_lag_stick_and_suspend():
    rng = np.random.default_rng(5)
    g = S.sim_game(rng, -2.5, 228.0)
    sharp = S.book_series(rng, g, 4.0, 20.0, 0.0, 0.0, 0.025)
    lad = S.book_series(rng, g, 25.0, 60.0, 0.02, 0.0, 0.06)
    assert len(lad) < len(sharp)                               # a sticky, slower book reprices less often
    t1 = g["events"][5][0]                                     # right after the fifth score
    assert S.suspended(g, t1 + 1, 8.0) and not S.suspended(g, t1 + 9, 8.0)
    # between the score and the slow book's reprice, its price still reflects the state before the score
    before = S.price_at(lad, t1 - 0.1)
    assert S.price_at(lad, t1 + 10)[0] == before[0]
    oh, oa = S._odds(0.6, 0.06)
    assert abs(1 / oh + 1 / oa - 1.06) < 0.01                 # the overround is the margin
    for row in sharp:
        assert row[2] > 1 and row[3] > 1


def test_fit_recovers_a_sensible_model_and_scores_a_holdout():
    rng = np.random.default_rng(11)
    rows = []
    for gi in range(150):
        spread = float(np.round(rng.normal(-2.5, 6.0) * 2) / 2)
        g = S.sim_game(rng, spread, 226.0)
        for k in range(1, int(g["end"] // 60)):
            t = 60.0 * k
            hs, as_, _ = S.state_at(g, t)
            rows.append((gi, hs - as_, -spread, S.frac_left(t), int(g["home_won"])))
    m = S.fit(rows, rng)
    assert 10 < m["sigma"] < 24 and 0.4 <= m["a"] <= 2.4
    assert m["logloss"] < m["logloss_base"] - 0.08              # the model beats the base rate clearly
    assert sum(c["n"] for c in m["calibration"]) == m["rows_test"]
    pred_hi = [c for c in m["calibration"] if c["pred"] > 0.8]
    assert pred_hi and all(c["actual"] > 0.6 for c in pred_hi)


def test_run_scores_flags_and_finds_the_lag_window(snaps):
    out = S.run(games=120, seed=2)
    assert out["n_games"] == 120 and out["model"]["sigma"] > 0 and out["example"]["truth"]
    B.json_safe(out)
    cad = {(r["cadence"], r["min_ev"]): r for r in out["cadence"]}
    assert cad[(15, 0.02)]["n"] > cad[(60, 0.02)]["n"] > cad[(300, 0.02)]["n"]      # faster polling catches more of the same edges
    assert cad[(15, 0.02)]["n"] >= cad[(15, 0.05)]["n"]
    assert cad[(15, 0.02)]["true_edge"] > 0.03                  # against a lagging, sticky book the caught edge is real on average
    reg = out["regimes"]["15"]
    since = {r["label"]: r for r in reg["since_score"]}
    assert since["10-30 s"]["n"] > since["1-3 min"]["n"]        # the edge lives in the window between the sharp's and the slow book's reprice
    mv = out["moves"]
    s = {r["label"]: r for r in mv["since_score"]}
    assert s["10-30 s"]["lad_gap"] > (s["3 min+"]["lad_gap"] or s["1-3 min"]["lad_gap"])     # the slow book trails the truth right after a score, not later
    assert s["0-10 s"]["lad_off"] > 0.5                         # and is suspended most of that first window
    S.save(out)
    assert S.load()["n_games"] == 120
    out["cfg"] = S._cfg_json(S.DEFAULTS)
    S.save(out)
    assert S.ensure()["sim"] == "ok"                            # a fresh file with the default config: nothing to do


def test_no_lag_no_edge(snaps):
    """A book that reprices as fast as the sharp one and never sticks leaves nothing to catch beyond noise."""
    out = S.run(games=60, seed=4, cfg={"lad": {"lag": 4.0, "timer": 20.0, "sticky": 0.0, "hiccup_p": 0.0}})
    cad = {(r["cadence"], r["min_ev"]): r for r in out["cadence"]}
    assert cad[(15, 0.03)]["n"] < 0.2 * 60 * 15                 # a handful of noise flags, not a flood
    base = S.run(games=60, seed=4)
    assert cad[(15, 0.02)]["n"] < {(r["cadence"], r["min_ev"]): r for r in base["cadence"]}[(15, 0.02)]["n"]


def test_live_model_and_pregame_spread(snaps):
    params = {"sigma": 15.0, "a": 1.0, "c": 0.0}
    p = S.live_model_p(10, 3, "6:00", -4.5, params)
    assert 0.8 < p < 0.98
    assert S.live_model_p(-10, 3, "6:00", -4.5, params) < 0.3
    assert S.live_model_p(0, 1, "12:00", -4.5, params) > 0.5 > S.live_model_p(0, 1, "12:00", 4.5, params)
    assert S.live_model_p(3, 4, "0:00", 0.0, params) == 1.0 and S.live_model_p(-2, 5, "0:00", 0.0, params) == 0.0
    assert S.live_model_p(3, None, "6:00", 0.0, params) is None and S.live_model_p(3, 2, "6:00", None, params) is None
    assert S.live_model_p(3, 2, "bad", 0.0, params) is None
    st = {"close_pre": {"g1|spreads|Boston Celtics|-3.5": {}, "g1|spreads|New York Knicks|3.5": {}}, "opens": {}}
    assert O.pregame_spread("g1", "Boston Celtics", st) == -3.5
    assert O.pregame_spread("g1", "Boston Celtics", {"close_pre": {}, "opens": {"g1|spreads|Boston Celtics|-2.5": [0, 1.9]}}) == -2.5
    assert O.pregame_spread("g2", "Boston Celtics", st) is None
    g = {"id": "g1", "home": "Boston Celtics", "away": "New York Knicks", "home_score": 60.0, "away_score": 50.0, "period": 3, "clock": "6:00",
         "markets": {"h2h": [{"name": "Boston Celtics", "lad": 1.3}, {"name": "New York Knicks", "lad": 3.6}]}}
    m = O.model_fair(g, st, params)
    assert m and 0.8 < m["p_home"] < 0.98 and m["spread"] == -3.5 and g["markets"]["h2h"][0]["model_ev"] == pytest.approx(1.3 * m["p_home"] - 1, abs=1e-3)
    assert O.model_fair(g, st, {}) is None


def test_sim_endpoint_runs_once_and_is_json(snaps):
    d = O.ENDPOINTS["sim"]()
    assert d["n_games"] == 120 and d["cadence"]
    B.json_safe(d)
    assert S.load()["n_games"] == 120                           # saved, so the next call reads the file
    assert O.run_sim()["sim"] == "ok"


def test_report_and_cli(snaps, capsys):
    assert S.main(["--games", "20", "--seed", "9", "--lag", "40"]) == 0
    out = capsys.readouterr().out
    assert "20 synthetic games" in out and "Cadence x threshold" in out and "Regimes" in out
