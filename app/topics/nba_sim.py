"""Synthetic live-odds lab for /nba-odds (helper module, DASHBOARD = "nba-odds"; no page of its own).

Before a single real credit is spent, this answers three questions on made-up games whose true probabilities are known:

  1. How do live odds move?  Games are simulated possession by possession from a pre-game spread and total (team strength, pace,
     a little catch-up by the trailing side, overtime). The true home win probability at any second follows from the simulator's own
     possession law. A sharp book (Pinnacle-like: 2.5% margin, reprices seconds after every score) and a slow book (Ladbrokes-like:
     6% margin, reprices `lag` seconds after a score, suspends briefly on each score, moves only when the fair line has shifted
     `sticky` points, and now and then stops updating for a couple of minutes) are run over every game.
  2. Train the model.  A live win-probability model, P(home) = Phi((lead + a * m * f + c) / (sigma * sqrt(f))) with f the fraction of
     the game left and m the pre-game expected home margin, is fitted by maximum likelihood on the simulated OUTCOMES (never on the
     true probabilities), on 70% of the games, and scored on the rest: log loss and a calibration table. The same fit runs unchanged
     on real games once there are enough of them (data/nba-odds/README.md). The fitted parameters give the Live tab's "model fair".
  3. Where is the exploitable price?  The dashboard's own pipeline (nba_odds.devig / ev) is run on snapshots taken at a polling
     cadence (300 s as the real poller, 60 s, 15 s). A flag is a Ladbrokes price with EV >= threshold against the sharp fair. Every
     flag is settled at the game's real outcome and scored against the TRUE probability (the edge that was really there), by quarter,
     lead, seconds since the last score, during a feed hiccup or not, and by cadence x threshold.

Everything here is synthetic: the bookmaker behaviour is a stylised guess with the parameters below, not Ladbrokes' real trading rules.
The results say what kind of edge the pipeline can catch and at what cadence, not that any such edge exists at Ladbrokes.
Rows within a game are correlated, so the fit needs hundreds of games to settle: the default is 800 (about 15 s).
Run from the command line for the report: python -m app.topics.nba_sim [--games 800] [--seed 7] [--lag 25].
"""
from __future__ import annotations

import json
import math
import sys
import time

import numpy as np

from . import _base as B
from ._base import _r

DASHBOARD = "nba-odds"

REG = 48 * 60                  # seconds of regulation
PERIOD = 12 * 60
OT = 5 * 60
DEFAULTS = {
    "games": 800, "seed": 7, "cadences": (300, 60, 15), "min_evs": (0.01, 0.02, 0.03, 0.05),
    "pace_mean": 100.0, "pace_sd": 4.0, "catch_up": 0.004,                    # possessions per team; ppp change per point behind
    "sharp": {"margin": 0.025, "lag": 4.0, "timer": 20.0, "noise": 0.008},
    "lad": {"margin": 0.06, "lag": 25.0, "timer": 60.0, "sticky": 0.02, "suspend": 8.0, "noise": 0.01, "hiccup_p": 0.12, "hiccup_len": 150.0},
}
P3, P1 = 0.10, 0.08                                                           # share of possessions ending in a 3 or a single free throw
BINS_LEAD = ((0, 3, "0-3"), (4, 7, "4-7"), (8, 12, "8-12"), (13, 99, "13+"))
BINS_SINCE = ((0, 10, "0-10 s"), (10, 30, "10-30 s"), (30, 60, "30-60 s"), (60, 180, "1-3 min"), (180, 9e9, "3 min+"))


# ------------------------------------------------------------------ the normal CDF without scipy (Abramowitz & Stegun 7.1.26, |err| < 1.5e-7)
def phi(z):
    z = np.asarray(z, dtype=float)
    t = 1.0 / (1.0 + 0.3275911 * np.abs(z) / math.sqrt(2))
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1.0 - poly * np.exp(-z * z / 2)
    return 0.5 * (1.0 + np.sign(z) * erf)


# ------------------------------------------------------------------ one game, possession by possession
def points_probs(ppp: float) -> tuple[float, float, float, float]:
    """P(0), P(1), P(2), P(3) points on a possession with mean `ppp`; threes and single free throws at fixed shares."""
    p2 = min(0.8, max(0.05, (ppp - 3 * P3 - P1) / 2))
    return max(0.0, 1 - p2 - P3 - P1), P1, p2, P3


def poss_var(ppp: float) -> float:
    p0, p1, p2, p3 = points_probs(ppp)
    m = p1 + 2 * p2 + 3 * p3
    return p1 + 4 * p2 + 9 * p3 - m * m


def sim_game(rng: np.random.Generator, spread: float, total: float, cfg: dict = DEFAULTS) -> dict:
    """spread is the home spread (-3.5: home favoured by 3.5). Returns events [(t, home, away)] (t in seconds; the first is 0:0 at 0),
    `end` (seconds, including overtime), the per-team pace and points per possession used, and who won."""
    pace = max(80.0, rng.normal(cfg["pace_mean"], cfg["pace_sd"]))
    margin = -spread
    # the catch-up term damps the favourite's edge (an AR(1) in the margin: see truth()), so the per-pair points difference d is set
    # such that the expected final margin is still the spread: d (1 - r^pace) / (1 - r) = margin
    r = 1 - 2 * cfg["catch_up"]
    d = margin * (1 - r) / (1 - r ** pace) if cfg["catch_up"] else margin / pace
    ppp_h, ppp_a = total / (2 * pace) + d / 2, total / (2 * pace) - d / 2
    secs_per_poss = REG / (2 * pace)
    t, hs, as_, end = 0.0, 0, 0, float(REG)
    home_ball = rng.random() < 0.5
    events = [(0.0, 0, 0)]
    while True:
        t += rng.uniform(0.4, 1.6) * secs_per_poss
        if t >= end:
            if hs == as_:
                t, end = end, end + OT
                continue
            break
        ppp = (ppp_h if home_ball else ppp_a) + cfg["catch_up"] * ((as_ - hs) if home_ball else (hs - as_))
        pts = int(rng.choice(4, p=points_probs(max(0.5, ppp))))
        if pts:
            if home_ball:
                hs += pts
            else:
                as_ += pts
            events.append((round(t, 1), hs, as_))
        home_ball = not home_ball
    return {"spread": spread, "total": total, "pace": pace, "ppp_h": ppp_h, "ppp_a": ppp_a, "events": events, "end": end,
            "home": hs, "away": as_, "home_won": hs > as_}


def state_at(g: dict, t: float) -> tuple[int, int, float]:
    """(home, away, seconds since the last score) at time t."""
    ev = g["events"]
    lo, hi = 0, len(ev) - 1
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if ev[mid][0] <= t:
            lo = mid
        else:
            hi = mid - 1
    return ev[lo][1], ev[lo][2], t - ev[lo][0]


def end_known_at(t: float) -> float:
    """The end of the game as it looks at time t: regulation, or the current overtime once the clock is past regulation."""
    return float(REG) if t < REG else REG + OT * (int((t - REG) // OT) + 1)


def truth(g: dict, t: float, cfg: dict = DEFAULTS) -> float:
    """True P(home wins) at time t from the simulator's own law. With the trailing side's catch-up, the margin after each home-away pair
    of possessions is M' = r M + d + e with r = 1 - 2 c, d = ppp_h - ppp_a and Var(e) = v (an AR(1)), so over the n pairs left the final
    margin is normal with mean M r^n + d (1 - r^n) / (1 - r) and variance v (1 - r^2n) / (1 - r^2). A tie goes to overtime: 50/50."""
    hs, as_, _ = state_at(g, t)
    lead = hs - as_
    if t >= g["end"]:
        return 1.0 if lead > 0 else 0.0 if lead < 0 else 0.5
    rem = max(0.0, end_known_at(t) - t)
    n = g["pace"] * rem / REG                                     # home-away pairs of possessions left
    d, v, r = g["ppp_h"] - g["ppp_a"], poss_var(g["ppp_h"]) + poss_var(g["ppp_a"]), 1 - 2 * cfg["catch_up"]
    if n < 1e-9:
        return 1.0 if lead > 0 else 0.0 if lead < 0 else 0.5
    if abs(1 - r) < 1e-9:
        mu, var = lead + d * n, v * n
    else:
        rn = r ** n
        mu, var = lead * rn + d * (1 - rn) / (1 - r), v * (1 - rn * rn) / (1 - r * r)
    sd = math.sqrt(var)
    return float(0.5 * (phi((mu + 0.5) / sd) + phi((mu - 0.5) / sd)))


def rollout(rng: np.random.Generator, g: dict, t: float, n: int = 4000, cfg: dict = DEFAULTS) -> float:
    """Monte Carlo P(home wins) from the state at t, by playing the rest of the game out n times (a check on truth(), used in tests)."""
    hs, as_, _ = state_at(g, t)
    pairs = int(round(g["pace"] * max(0.0, end_known_at(t) - t) / REG))
    M = np.full(n, float(hs - as_))
    for _ in range(pairs):
        for sign, ppp in ((1, g["ppp_h"]), (-1, g["ppp_a"])):
            eff = np.maximum(0.5, ppp - sign * cfg["catch_up"] * M)
            p2 = np.clip((eff - 3 * P3 - P1) / 2, 0.05, 0.8)
            p0 = np.maximum(0.0, 1 - p2 - P3 - P1)
            u = rng.random(n)
            pts = (u > p0).astype(float) + (u > p0 + P1) + (u > p0 + P1 + p2)
            M = M + sign * pts
    return float(np.mean(M > 0) + 0.5 * np.mean(M == 0))


def period_at(t: float) -> int:
    return min(4, int(t // PERIOD) + 1) if t < REG else 4 + int((t - REG) // OT) + 1


def frac_left(t: float) -> float:
    """Fraction of regulation left, as the model sees it (overtime counts as its own 5 minutes over 48)."""
    return max(0.0, end_known_at(t) - t) / REG


# ------------------------------------------------------------------ the two books as step functions over the game
def _odds(p: float, margin: float) -> tuple[float, float]:
    """Decimal odds on home and away with the overround split evenly."""
    p = min(0.995, max(0.005, p))
    return max(1.01, round(1 / (p + margin / 2), 2)), max(1.01, round(1 / (1 - p + margin / 2), 2))


def book_series(rng: np.random.Generator, g: dict, lag: float, timer: float, sticky: float, noise: float, margin: float,
                hiccup: tuple | None = None) -> list[tuple[float, float, float, float]]:
    """[(t, p_home_used, odds_home, odds_away)]: the price in force from t. Reprices `lag` s after each score and every `timer` s,
    but only when the fair line has moved `sticky` or more since the last price; nothing changes inside the hiccup window."""
    ticks = sorted({round(e[0] + lag, 1) for e in g["events"][1:]} | {float(k * timer) for k in range(int(g["end"] // timer) + 1)})
    out, last = [], None
    p0 = truth(g, 0.0) + rng.normal(0, noise)
    out.append((0.0, p0, *_odds(p0, margin)))
    last = p0
    for u in ticks:
        if u <= 0 or u >= g["end"]:
            continue
        if hiccup and hiccup[0] <= u < hiccup[1]:
            continue
        p = truth(g, u)
        if abs(p - last) >= sticky:
            p += rng.normal(0, noise)
            last = p
            out.append((u, p, *_odds(p, margin)))
    return out


def price_at(series: list, t: float):
    lo, hi = 0, len(series) - 1
    if t < series[0][0]:
        return series[0]
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if series[mid][0] <= t:
            lo = mid
        else:
            hi = mid - 1
    return series[lo]


def suspended(g: dict, t: float, secs: float) -> bool:
    _, _, since = state_at(g, t)
    return 0 <= since < secs and t > 0


# ------------------------------------------------------------------ the lab: simulate, snapshot, flag, settle
def run(games: int = DEFAULTS["games"], seed: int = DEFAULTS["seed"], cfg: dict | None = None, min_ev_default: float = 0.02) -> dict:
    from . import nba_odds as O
    cfg = {**DEFAULTS, **(cfg or {})}
    cfg["lad"] = {**DEFAULTS["lad"], **(cfg.get("lad") or {})}
    cfg["sharp"] = {**DEFAULTS["sharp"], **(cfg.get("sharp") or {})}
    rng = np.random.default_rng(seed)
    t0 = time.time()
    sims, rows, fit_rows, move_rows = [], [], [], []
    example = None
    for gi in range(games):
        spread = float(np.round(rng.normal(-2.5, 6.0) * 2) / 2)          # home favoured by 2.5 on average, half-point lines
        total = float(np.round(rng.normal(226, 8)))
        g = sim_game(rng, spread, total, cfg)
        g["i"] = gi
        hic = None
        if rng.random() < cfg["lad"]["hiccup_p"]:
            h0 = rng.uniform(PERIOD, REG - 2 * cfg["lad"]["hiccup_len"])
            hic = (h0, h0 + cfg["lad"]["hiccup_len"])
        sharp = book_series(rng, g, cfg["sharp"]["lag"], cfg["sharp"]["timer"], 0.0, cfg["sharp"]["noise"], cfg["sharp"]["margin"])
        lad = book_series(rng, g, cfg["lad"]["lag"], cfg["lad"]["timer"], cfg["lad"]["sticky"], cfg["lad"]["noise"], cfg["lad"]["margin"], hic)
        sims.append(g)
        m = -spread
        for k in range(1, int(g["end"] // 60)):                        # training rows: once a minute, never at 0 or the end
            t = 60.0 * k
            hs, as_, _ = state_at(g, t)
            f = frac_left(t)
            if f > 0:
                fit_rows.append((gi, hs - as_, m, f, int(g["home_won"])))
        for cad in cfg["cadences"]:
            off = rng.uniform(0, cad)
            t = off
            runs = {"home": None, "away": None}              # the Ladbrokes price last flagged per side: a run is one bet
            while t < g["end"]:
                hs, as_, since = state_at(g, t)
                tr = truth(g, t)
                sp = price_at(sharp, t)
                fair_h, fair_a = O.devig([sp[2], sp[3]])
                lp = None if suspended(g, t, cfg["lad"]["suspend"]) else price_at(lad, t)
                in_hic = bool(hic and hic[0] <= t < hic[1])
                if cad == 15:
                    move_rows.append((period_at(t), since, tr, sp[1], lp[1] if lp else None, in_hic))
                if lp:
                    for side, lo, fp, tp, won in (("home", lp[2], fair_h, tr, g["home_won"]), ("away", lp[3], fair_a, 1 - tr, not g["home_won"])):
                        e = O.ev(lo, fp)
                        if e < min(cfg["min_evs"]):
                            runs[side] = None
                            continue
                        first = runs[side] != lo
                        runs[side] = lo
                        rows.append({"cad": cad, "g": gi, "t": t, "q": period_at(t), "lead": abs(hs - as_), "since": since, "hic": in_hic,
                                     "side": side, "odds": lo, "ev": e, "true_edge": lo * tp - 1, "profit": (lo - 1) if won else -1.0,
                                     "first": first, "fair": fp, "truth": tp})
                t += cad
        score = sum(1 for r in rows if r["g"] == gi and r["cad"] == 15 and r["first"] and r["ev"] >= min_ev_default)
        if example is None or score > example["score"]:
            example = {"score": score, "g": g, "sharp": sharp, "lad": lad, "hic": hic}
    model = fit(fit_rows, rng)
    out = {"generated": int(time.time()), "n_games": games, "seed": seed, "cfg": _cfg_json(cfg), "took": round(time.time() - t0, 1),
           "model": model, "home_win_rate": _r(sum(g["home_won"] for g in sims) / games, 4),
           "avg_total": _r(sum(g["home"] + g["away"] for g in sims) / games, 1), "ot_share": _r(sum(g["end"] > REG for g in sims) / games, 4),
           "cadence": cadence_table(rows, cfg), "regimes": regimes(rows, cfg, min_ev_default), "moves": move_stats(move_rows),
           "example": example_trace(example, cfg) if example else None, "min_ev": min_ev_default}
    return out


def _cfg_json(cfg: dict) -> dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}


# ------------------------------------------------------------------ training: the live win-probability model
def model_p(lead, m, f, sigma: float, a: float, c: float):
    f = np.maximum(np.asarray(f, dtype=float), 1e-4)
    return np.clip(phi((np.asarray(lead, dtype=float) + a * np.asarray(m, dtype=float) * f + c) / (sigma * np.sqrt(f))), 1e-6, 1 - 1e-6)


def fit(rows: list, rng: np.random.Generator) -> dict:
    """Maximum likelihood over a grid for (sigma, a, c) on a 70% split of the games; log loss and calibration on the other 30%."""
    if not rows:
        return {}
    arr = np.array(rows, dtype=float)
    gids = np.unique(arr[:, 0])
    test_g = set(rng.choice(gids, size=max(1, int(0.3 * len(gids))), replace=False).tolist())
    is_test = np.array([g in test_g for g in arr[:, 0]])
    tr, te = arr[~is_test], arr[is_test]
    def search(sigmas, As, cs):
        best = None
        for sigma in sigmas:
            for a in As:
                for c in cs:
                    p = model_p(tr[:, 1], tr[:, 2], tr[:, 3], sigma, a, c)
                    ll = float(np.mean(tr[:, 4] * np.log(p) + (1 - tr[:, 4]) * np.log(1 - p)))
                    if best is None or ll > best[0]:
                        best = (ll, sigma, a, c)
        return best
    _, sigma, a, c = search(np.linspace(8, 24, 33), np.linspace(0.4, 2.4, 21), (-1.0, -0.5, 0.0, 0.5, 1.0))
    _, sigma, a, c = search(np.linspace(max(8, sigma - 0.5), min(24, sigma + 0.5), 11), np.linspace(max(0.4, a - 0.1), min(2.4, a + 0.1), 9),
                            np.linspace(max(-1, c - 0.5), min(1, c + 0.5), 11))
    p_te = model_p(te[:, 1], te[:, 2], te[:, 3], sigma, a, c)
    y = te[:, 4]
    logloss = float(-np.mean(y * np.log(p_te) + (1 - y) * np.log(1 - p_te)))
    base = float(np.mean(y))
    base_ll = float(-np.mean(y * np.log(base) + (1 - y) * np.log(1 - base)))
    edges = np.linspace(0, 1, 11)
    cal = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p_te >= lo) & (p_te < hi if hi < 1 else p_te <= hi)
        if m.sum():
            cal.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "pred": _r(float(p_te[m].mean()), 4), "actual": _r(float(y[m].mean()), 4)})
    brier = float(np.mean((p_te - y) ** 2))
    return {"sigma": round(float(sigma), 2), "a": round(float(a), 2), "c": round(float(c), 2), "rows_train": int(len(tr)), "rows_test": int(len(te)),
            "games_test": len(test_g), "logloss": round(logloss, 4), "logloss_base": round(base_ll, 4), "brier": round(brier, 4), "calibration": cal,
            "form": "P(home) = Phi((lead + a*m*f + c) / (sigma*sqrt(f))), f = fraction of the game left, m = pre-game expected home margin"}


# ------------------------------------------------------------------ scoring the flags
def _agg(rs: list[dict]) -> dict:
    n = len(rs)
    if not n:
        return {"n": 0, "ev": None, "true_edge": None, "roi": None, "se": None, "hit": None}
    pr = np.array([r["profit"] for r in rs])
    return {"n": n, "ev": _r(float(np.mean([r["ev"] for r in rs])), 4), "true_edge": _r(float(np.mean([r["true_edge"] for r in rs])), 4),
            "roi": _r(float(pr.mean()), 4), "se": _r(float(pr.std(ddof=1) / math.sqrt(n)), 4) if n > 1 else None,
            "hit": _r(float(np.mean([r["profit"] > 0 for r in rs])), 4), "odds": _r(float(np.mean([r["odds"] for r in rs])), 2)}


def cadence_table(rows: list[dict], cfg: dict) -> list[dict]:
    out = []
    for cad in cfg["cadences"]:
        for thr in cfg["min_evs"]:
            rs = [r for r in rows if r["cad"] == cad and r["first"] and r["ev"] >= thr]
            out.append({"cadence": cad, "min_ev": thr, **_agg(rs), "per_game": _r(len(rs) / cfg["games"], 3)})
    return out


def regimes(rows: list[dict], cfg: dict, thr: float) -> dict:
    out = {}
    for cad in cfg["cadences"]:
        rs = [r for r in rows if r["cad"] == cad and r["first"] and r["ev"] >= thr]
        bucket = lambda v, bins: next(l for lo, hi, l in bins if lo <= v <= hi) if bins is BINS_LEAD else next(l for lo, hi, l in bins if lo <= v < hi)
        out[str(cad)] = {
            "quarter": [{"label": f"Q{q}" if q <= 4 else f"OT{q - 4}", **_agg([r for r in rs if r["q"] == q])} for q in sorted({r["q"] for r in rs})],
            "lead": [{"label": l, **_agg([r for r in rs if bucket(r["lead"], BINS_LEAD) == l])} for _, _, l in BINS_LEAD],
            "since_score": [{"label": l, **_agg([r for r in rs if bucket(r["since"], BINS_SINCE) == l])} for _, _, l in BINS_SINCE],
            "hiccup": [{"label": "feed stuck", **_agg([r for r in rs if r["hic"]])}, {"label": "feed normal", **_agg([r for r in rs if not r["hic"]])}],
            "side": [{"label": s, **_agg([r for r in rs if r["side"] == s])} for s in ("home", "away")],
            "odds": [{"label": l, **_agg([r for r in rs if lo <= r["odds"] < hi])} for lo, hi, l in ((1, 1.5, "< 1.50"), (1.5, 2.2, "1.50-2.20"), (2.2, 4, "2.20-4.00"), (4, 99, "4.00+"))],
        }
    return out


def move_stats(mv: list) -> dict:
    """From the 15-second grid: how far each book sits from the truth, by seconds since the last score and by quarter."""
    if not mv:
        return {}
    arr = [(q, since, tr, sp, lp, hic) for q, since, tr, sp, lp, hic in mv]
    def gap(rs, idx):
        v = [abs(r[idx] - r[2]) for r in rs if r[idx] is not None]
        return _r(float(np.mean(v)), 4) if v else None
    by_since = [{"label": l, "n": sum(1 for r in arr if lo <= r[1] < hi), "sharp_gap": gap([r for r in arr if lo <= r[1] < hi], 3),
                 "lad_gap": gap([r for r in arr if lo <= r[1] < hi], 4), "lad_off": _r(float(np.mean([r[4] is None for r in arr if lo <= r[1] < hi])), 4) if any(lo <= r[1] < hi for r in arr) else None}
                for lo, hi, l in BINS_SINCE]
    by_q = [{"label": f"Q{q}" if q <= 4 else f"OT{q - 4}", "n": sum(1 for r in arr if r[0] == q), "sharp_gap": gap([r for r in arr if r[0] == q], 3), "lad_gap": gap([r for r in arr if r[0] == q], 4)}
            for q in sorted({r[0] for r in arr})]
    hic = [{"label": "feed stuck", "lad_gap": gap([r for r in arr if r[5]], 4), "n": sum(1 for r in arr if r[5])}, {"label": "feed normal", "lad_gap": gap([r for r in arr if not r[5]], 4), "n": sum(1 for r in arr if not r[5])}]
    big = [r for r in arr if r[4] is not None]
    return {"since_score": by_since, "quarter": by_q, "hiccup": hic,
            "lad_off_3pts": _r(float(np.mean([abs(r[4] - r[2]) >= 0.03 for r in big])), 4) if big else None,
            "lad_off_5pts": _r(float(np.mean([abs(r[4] - r[2]) >= 0.05 for r in big])), 4) if big else None}


def example_trace(ex: dict, cfg: dict) -> dict:
    g = ex["g"]
    pts_t, pts_s, pts_l, lead = [], [], [], []
    t = 0.0
    while t < g["end"]:
        hs, as_, _ = state_at(g, t)
        m = round(t / 60, 2)
        pts_t.append([m, _r(truth(g, t), 4)])
        pts_s.append([m, _r(price_at(ex["sharp"], t)[1], 4)])
        lp = None if suspended(g, t, cfg["lad"]["suspend"]) else price_at(ex["lad"], t)
        pts_l.append([m, _r(lp[1], 4) if lp else None])
        lead.append([m, hs - as_])
        t += 15
    return {"spread": g["spread"], "total": g["total"], "final": [g["home"], g["away"]], "end_min": round(g["end"] / 60, 1), "hiccup": [round(x / 60, 2) for x in ex["hic"]] if ex["hic"] else None,
            "truth": pts_t, "sharp": pts_s, "lad": pts_l, "lead": lead, "flags": ex["score"]}


# ------------------------------------------------------------------ the file on the volume, the background job, the live model
def _file():
    return B.SNAP_DIR / "nba-odds" / "sim.json"


def load() -> dict:
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def save(out: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, default=str, allow_nan=False))
    tmp.replace(f)


def ensure(max_age: float = 7 * 86400, **kw) -> dict:
    """BACKGROUND job for nba_odds: run the lab once (and again when the file is a week old or the defaults changed)."""
    cur = load()
    if cur and cur.get("cfg") == _cfg_json(DEFAULTS) and time.time() - cur.get("generated", 0) < max_age and not kw:
        return {"sim": "ok"}
    out = run(**kw)
    save(out)
    return {"sim": f"ran {out['n_games']} games in {out['took']} s"}


def live_model_p(lead: float, period: int | None, clock: str | None, home_spread: float | None, params: dict | None = None):
    """The trained model's P(home) for a real live game: lead, period and clock from the scoreboard, the pre-game home spread (its
    sharp close). None when there is no clock or no fitted model yet."""
    params = params or (load().get("model") or {})
    if not params or period is None or home_spread is None:
        return None
    try:
        mm, ss = (clock or "0:00").replace(".", ":").split(":")[:2]
        left_in_period = int(float(mm)) * 60 + int(float(ss))
    except ValueError:
        return None
    if period <= 4:
        rem = (4 - period) * PERIOD + left_in_period
    else:
        rem = left_in_period
    f = rem / REG
    if f <= 0:
        return 1.0 if lead > 0 else 0.0 if lead < 0 else 0.5
    return float(model_p(lead, -home_spread, f, params["sigma"], params["a"], params["c"]))


# ------------------------------------------------------------------ command line
def report(out: dict) -> str:
    m = out["model"]
    L = [f"{out['n_games']} synthetic games (seed {out['seed']}), {out['took']} s. Home win rate {out['home_win_rate']:.3f}, average total {out['avg_total']}, overtime {out['ot_share']:.1%}.",
         f"Model: sigma={m['sigma']} a={m['a']} c={m['c']}; hold-out log loss {m['logloss']} (always-base {m['logloss_base']}), Brier {m['brier']}.",
         "  calibration: " + ", ".join(f"{c['bin']}: {c['pred']:.2f}->{c['actual']:.2f} (n={c['n']})" for c in m["calibration"]),
         "", "Cadence x threshold (one bet per price run):"]
    for r in out["cadence"]:
        L.append(f"  every {r['cadence']:>3} s, EV>={r['min_ev']:.0%}: {r['n']:>5} flags ({r['per_game']}/game), mean EV {r['ev'] or 0:+.3f}, true edge {r['true_edge'] or 0:+.3f}, ROI {r['roi'] or 0:+.3f} +/- {r['se'] or 0:.3f}")
    L.append(f"\nRegimes at the dashboard threshold ({out['min_ev']:.0%}):")
    for cad, reg in out["regimes"].items():
        L.append(f"  cadence {cad} s")
        for name, rs in reg.items():
            L.append(f"    {name:12} " + " | ".join(f"{r['label']}: n={r['n']} edge {r['true_edge'] or 0:+.3f} roi {r['roi'] or 0:+.3f}" for r in rs))
    mv = out["moves"]
    L.append("\nHow far the books sit from the truth (mean |p - truth|, 15-s grid):")
    for r in mv["since_score"]:
        L.append(f"  {r['label']:>8} after a score: sharp {r['sharp_gap']}, Ladbrokes {r['lad_gap']} (suspended {(r['lad_off'] or 0):.0%} of the time)")
    L.append(f"  Ladbrokes >=3 pts off the truth {mv['lad_off_3pts']:.1%} of the time, >=5 pts {mv['lad_off_5pts']:.1%}.")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", type=int, default=DEFAULTS["games"]); ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--lag", type=float, help="seconds Ladbrokes takes to reprice after a score"); ap.add_argument("--sticky", type=float)
    ap.add_argument("--hiccup", type=float, help="probability per game of a stuck feed"); ap.add_argument("--save", action="store_true", help="write sim.json on the volume")
    a = ap.parse_args(argv)
    lad = {k: v for k, v in (("lag", a.lag), ("sticky", a.sticky), ("hiccup_p", a.hiccup)) if v is not None}
    out = run(a.games, a.seed, {"lad": lad} if lad else None)
    print(report(out))
    if a.save:
        save(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
