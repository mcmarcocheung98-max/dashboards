"""Routes, registry, the fetch-with-snapshot fallback, hand-entered series, and every dashboard's payloads on fixtures (no network)."""
import json
import time

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B


@pytest.fixture
def snapdir(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    yield tmp_path / "snaps"
    cache._cache.clear()
    B.STALE.clear()


def test_registry_is_complete():
    assert set(topics.REGISTRY) == {"housing", "ai", "robotaxi", "btc-cycles"}
    for slug, t in topics.REGISTRY.items():
        m = topics.meta(slug)
        eps = topics.endpoints(slug)
        assert m["title"] and m["tabs"] and m["sources"]
        assert set(t.slow) <= set(eps), slug
        assert {k for k, _ in t.tabs} <= set(eps), f"{slug}: every tab needs an endpoint of the same name"
        js = (B.MANUAL_DIR.parent / "app/static/topics" / f"{slug}.js").read_text()
        assert "window.TOPIC" in js and all(f"async {k}(" in js for k, _ in t.tabs), slug


def test_fetch_serves_the_snapshot_when_the_source_is_down(snapdir, monkeypatch):
    calls = []

    def dl(url, *a, **k):
        calls.append(url)
        if len(calls) > 1:
            raise ConnectionError("down")
        return "date,value\n2024-01-01,1\n2024-02-01,2\n" * 5
    monkeypatch.setattr(B, "_download", dl)
    url = "https://example.test/x.csv"
    t1 = B.fetch(url, ttl=0)                      # downloaded and snapshotted
    assert snapdir.exists() and not B.STALE
    t2 = B.fetch(url, ttl=0)                      # source down: snapshot, marked stale
    assert t2 == t1 and url in B.STALE
    assert B.stale_info([url]) == {url: time.strftime("%Y-%m-%d")}
    assert B.fetch(url, ttl=3600) == t1           # in memory now
    with pytest.raises(ConnectionError):
        B.fetch("https://example.test/never.csv", ttl=0)   # no snapshot either: the error reaches _part
    out = {}
    B._part(out, "k", lambda: B.fetch("https://example.test/never.csv", ttl=0))
    assert out == {"k": None, "k_error": "ConnectionError"}


def test_manual_series_and_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "MANUAL_DIR", tmp_path)
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "one.csv").write_text("date,value,source,note\n# a comment line, with commas, is skipped\n2024-02-01,2,https://a.example/x,\n2024-01-01,1.5,https://b.example/y,n\n")
    (tmp_path / "t" / "many.csv").write_text("date,series,value,source,note\n2024-01-01,A,1,s,\n2024-01-01,B,,s,blank value dropped\n2024-02-01,A,3,s,\n")
    s = B.manual("t", "one")
    assert list(s) == [1.5, 2.0] and s.index[0] == pd.Timestamp("2024-01-01")
    m = B.manual("t", "many")
    assert set(m) == {"A", "B"} and list(m["A"]) == [1.0, 3.0] and m["B"].empty
    assert B.manual_sources("t", "one")[0] == {"source": "https://a.example/x", "date": "2024-02-01"}
    assert B.manual("t", "missing").empty and B.manual_rows("t", "missing") == []


def test_seed_files_parse_and_cite():
    for slug in topics.REGISTRY:
        for f in (B.MANUAL_DIR / slug).glob("*.csv"):
            rows = B.manual_rows(slug, f.stem)
            for r in rows:
                pd.Timestamp(r["date"])
                assert r.get("source"), f"{f}: every hand-entered row cites a source"


# ------------------------------------------------------------------ each module on fixtures (no network)
HPI = "Period,Average price All property types,Index All property types,Percentage change (yearly) All property types,Sales volume,Average price Detached houses,Average price Semi-detached houses,Average price Terraced houses,Average price Flats and maisonettes\n" + \
      "\n".join(f"{2010 + i // 12}-{i % 12 + 1:02d},{300000 + i * 1000},{100 + i},{2.0},{8000 - i},{600000},{400000},{350000},{250000}" for i in range(180))
ONS = lambda v0: {"months": [{"date": f"{2010 + i // 12} {m}", "value": str(v0 + i)} for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"] * 15)]}
BOE = "DATE,IUDBEDR\n05 Mar 2009,0.5\n02 Nov 2017,0.75\n16 Dec 2021,0.25\n03 Aug 2023,5.25\n01 Aug 2024,5.0\n"


def test_housing_payloads(snapdir, monkeypatch):
    from app.topics import housing as H
    monkeypatch.setattr(H, "fetch", lambda url, ttl, **k: HPI if "ukhpi" in url else BOE)
    monkeypatch.setattr(H, "fetch_json", lambda url, ttl, **k: ONS(100) if "L522" in url else ONS(500))
    p, m, a = H._prices_now(), H._market_now(), H._afford_now()
    for d in (p, m, a):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert p["now"]["avg"] == 479000 and p["london_real"][-1][1] == 479000 and p["london_real"][0][1] > 300000   # real terms: past prices inflated
    assert len(m["by_type"]) == 4 and m["now"]["types"]["Detached"] == 600000 and m["now"]["volume_12m"] < m["now"]["volume_12m_prev"]
    assert a["now"]["bank_rate"] == 5.0 and 5 < a["now"]["price_to_earnings"] < 20 and a["now"]["mortgage"] > 1000
    assert a["bank_rate"][0][1] == 0.5 and all(t % 86400 == 0 for t, _ in a["bank_rate"])     # one point per month start


def test_housing_parsers_cope_with_layout_drift():
    from app.topics.housing import parse_boe, parse_hpi, parse_ons
    d = parse_hpi("Period,Average price All property types,Sales volume\n2020-01,500000,100\n2020-02,510000,110\n2021-02,520000,90\n")
    assert d["pc_ann"].notna().sum() == 1 and d["avg_detached"].isna().all()             # yearly change computed when the column is missing
    assert parse_ons({"months": [{"date": "2024 JAN", "value": "1.5"}, {"date": "bad", "value": "2"}]}).tolist() == [1.5]
    assert parse_boe(" DATE , IUDBEDR \n01 Feb 2024,5.25\n").iloc[0] == 5.25


IND = "date,jobcountry,indeed_job_postings_index,variable,display_name\n" + "\n".join(
    f"{d.date()},US,{100 + i * (1 if n == 'Legal' else -1) * 0.1:.2f},{v},{n}" for i, d in enumerate(pd.date_range("2020-02-01", periods=800))
    for n in ("Software Development", "Data & Analytics", "Legal", "Banking & Finance", "Accounting", "Insurance") for v in ("total postings", "new postings"))
AGG = "date,jobcountry,indeed_job_postings_index_SA,indeed_job_postings_index_NSA,variable\n" + "\n".join(f"{d.date()},US,{100 + i * .01:.2f},100,total postings" for i, d in enumerate(pd.date_range("2020-02-01", periods=800)))
AIS = "date,jobcountry,AI_share_postings\n" + "\n".join(f"{d.date()},{cc},{2 + i * .003 * (2 if cc == 'US' else 1):.3f}" for i, d in enumerate(pd.date_range("2019-01-01", periods=2800)) for cc in ("US", "GB", "DE"))
FRED = "observation_date,CES6054110001\n" + "\n".join(f"{d.date()},{1100 + i * .5:.1f}" for i, d in enumerate(pd.date_range("2010-01-01", periods=190, freq="MS")))


def test_ai_jobs_payloads(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS if "ai-tracker" in url else FRED if "fred" in url else AGG if "aggregate" in url else IND)
    o, h, r = J._openings_now(), J._headcount_now(), J._ratio_now()
    for d in (o, h, r):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert set(o["US"]["sectors"]) == set(J.SECTORS["ai"] + J.SECTORS["professions"]) and o["US"]["latest"]["Legal"]["index"] > 100 > o["US"]["latest"]["Software Development"]["index"]
    assert o["ai_share_latest"]["US"]["share"] > o["ai_share_latest"]["US"]["year_ago"]
    assert set(h["US"]["levels"]) == set(J.US_SERIES) and h["US"]["latest"]["Legal services"]["since_2020"] > 0 and h["as_of"]
    assert r["US"]["ai_over_professions"][-1][1] < 1 < r["US"]["ai_over_professions"][0][1] + 0.01
    assert len(json.dumps(o)) < 400_000                      # weekly / monthly resampling keeps the page light


def test_ai_adoption_payloads(snapdir, monkeypatch):
    from app.topics import ai_adoption as A, ai_jobs as J
    monkeypatch.setattr(A, "fetch", lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("blocked")))    # BTOS workbook unreachable: hand-entered points carry the chart
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS)
    f, u, g, s = A._firms_now(), A._users_now(), A._agents_now(), A._skills_now()
    for d in (f, u, g, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert f["btos_us"] and f["now"]["btos"] and f["cited"]
    assert u["rows"][0]["date"] >= u["rows"][-1]["date"] and any(v for v in u["series"].values())
    assert g["rows"] and g["by_year"] and set(s["share"]) == {"US", "GB", "DE"}


def test_btos_workbook_parser():
    import io
    from app.topics.ai_adoption import parse_btos
    pytest.importorskip("openpyxl")
    frame = pd.DataFrame([["Question", "Answer", "2024-01-14", "2024-01-28", "2024-02-11"],
                          ["In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?", "Yes", "5.1", "5.3", "5.4"],
                          ["In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?", "No", "90", "90", "90"]])
    buf = io.BytesIO()
    frame.to_excel(buf, index=False, header=False)
    s = parse_btos(buf.getvalue())
    assert s.tolist() == [5.1, 5.3, 5.4] and s.index[-1] == pd.Timestamp("2024-02-11")


SGO = "Report ID,Report Version,Reporting Entity,Incident Date,Incident Time (24:00)\n" + "\n".join(
    f"R{i},1,{'Waymo LLC' if i % 3 else 'Cruise LLC'},{m.strftime('%b-%Y').upper()},12:00" for i, m in enumerate(pd.date_range("2021-07-01", periods=40, freq="MS").repeat(3))) + "\nR0,2,Cruise LLC,JUL-2021,12:00\n"


def test_robotaxi_payloads(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)
    r, f, s = R._rides_now(), R._footprint_now(), R._safety_now()
    for d in (r, f, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert r["weekly"]["Waymo"] and r["latest"]["Waymo"]["value"] > 0 and r["quarterly"]
    assert f["operators"] and f["cumulative"]["Waymo"][-1][1] == f["by_operator"]["Waymo"] and f["rows"][0]["date"] >= f["rows"][-1]["date"]
    assert s["reports"]["n"] == 120 and set(s["reports"]["entities"]) == {"Waymo LLC", "Cruise LLC"}           # a second version of a report is not a second incident
    assert len(s["reports"]["months"]) == 40 and s["reports"]["total_12m"][-1][1] == 36


# ------------------------------------------------------------------ the routes
def test_routes(snapdir, monkeypatch):
    pytest.importorskip("aiohttp")
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            idx = await c.get("/")
            assert idx.status == 200 and "Dashboards" in await idx.text() and idx.headers["X-Frame-Options"] == "DENY"
            assert (await c.get("/healthz")).status == 200
            j = await (await c.get("/api/index")).json()
            assert [d["slug"] for d in j["dashboards"]] == list(topics.REGISTRY)
            page = await c.get("/housing")
            assert page.status == 200 and "window.TOPIC.VIEWS" in await page.text()
            js = await c.get("/housing.js")
            assert js.status == 200 and "window.TOPIC" in await js.text()
            assert (await c.get("/nope")).status == 404 and (await c.get("/nope.js")).status == 404
            assert (await c.get("/..%2Fserver.py")).status == 404
            meta = await (await c.get("/api/housing/meta")).json()
            assert meta["title"] == "Housing: London, US & Hong Kong" and meta["tabs"][0] == ["prices", "Prices"] and meta["sources"]
            assert (await c.get("/api/housing/nope")).status == 404 and (await c.get("/api/nope/meta")).status == 404
            red = await c.get("/ai-jobs", allow_redirects=False)
            assert red.status == 301 and red.headers["Location"] == "/ai#openings"
            assert (await c.get("/ai-adoption", allow_redirects=False)).headers["Location"] == "/ai#firms"
            assert (await c.get("/ai")).status == 200 and (await c.get("/ai.js")).status == 200
            r = await c.get("/api/robotaxi/safety")
            assert r.status == 200 and (await r.json())["reports"]["n"] == 120
    asyncio.run(go())


# ------------------------------------------------------------------ BTC cycles: the doc as data + the live layer on fixtures
def _cm():
    days = pd.date_range("2010-07-18", "2026-10-20")
    import math
    px = [10 ** (0.5 + 3.2 * (1 - math.exp(-i / 1500))) * (1 + 0.6 * math.sin(i / 230)) for i in range(len(days))]
    return {"data": [{"asset": "btc", "time": d.strftime("%Y-%m-%dT00:00:00.000000000Z"), "PriceUSD": f"{v:.2f}"} for d, v in zip(days, px)]}


def _llama(url):
    days = pd.date_range("2024-01-01", "2026-10-20")
    ts = [int(d.timestamp()) for d in days]
    if "historicalChainTvl" in url:
        return [{"date": t, "tvl": 1e11 + i * 1e7} for i, t in enumerate(ts)]
    if "stablecoincharts" in url:
        return [{"date": t, "totalCirculatingUSD": {"peggedUSD": 2e11 + i * 1e8}} for i, t in enumerate(ts)]
    if "summary/fees" in url:
        return {"totalDataChart": [[t, 1e6 + i * 1e3] for i, t in enumerate(ts)]}
    if "overview/derivatives" in url:
        return {"totalDataChart": [[t, 1e10] for t in ts], "protocols": [{"name": "Hyperliquid", "total30d": 3e11}, {"name": "Aster", "total30d": 1e11}]}
    if "protocol/hyperliquid" in url:
        return {"tvl": [{"date": t, "totalLiquidityUSD": 4e9 + i * 1e6} for i, t in enumerate(ts)]}
    if "api/v3/global" in url:
        return {"data": {"market_cap_percentage": {"btc": 59.4}, "total_volume": {"usd": 9.1e10}}}
    if "market_chart" in url:
        return {"total_volumes": [[t * 1000, 1.2e10] for t in ts[-365:]]}
    raise AssertionError(url)


def test_btc_cycles_payloads(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: _cm() if "coinmetrics" in url else _llama(url))
    monkeypatch.setattr(C, "DOM_LOG", snapdir / "dom.csv")
    cy, se, me, ca, si = C._cycles_now(), C._sectors_now(), C._metrics_now(), C._candidates_now(), C._signals_now()
    for d in (cy, se, me, ca, si):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], [k for k in d if k.endswith("_error")]
    # the doc's content is all there
    R = C.research()
    assert R["title"].startswith("BTC Cycles") and len(R["cycles"]) == 4 and len(R["candidates"]["rows"]) == 8 and len(R["signals"]["items"]) == 6
    assert len(R["cross_cycle"]["rows"]) == 15 and len(R["metrics"]["rows"]) == 9 and len(R["sources"]["items"]) == 21
    assert all(set(r) >= set(c["columns"]) | {"_multiples"} for c in R["cycles"] for r in c["rows"])
    assert se["cycles"][1]["rows"][0]["_multiples"] == [{"label": "ETH", "x": 180.0}, {"label": "NEO", "x": 1900.0}]
    # live layer
    assert set(cy["overlay"]) == {"Cycle 1 (2012)", "Cycle 2 (2016)", "Cycle 3 (2020)", "Cycle 4 (2024)"}
    for pts in cy["overlay"].values():
        assert any(p[0] == 0 and abs(p[1] - 1) < 1e-6 for p in pts) and pts[0][0] >= -550 and pts[-1][0] <= 730
    assert all(p[1] <= 0 for p in cy["drawdown"]) and cy["now"]["days_since_halving"] == (pd.Timestamp("2026-10-20") - pd.Timestamp("2024-04-19")).days
    assert len(cy["halvings"]) == 4 and len(cy["markers"]) == 8
    assert me["latest"]["stablecoins"] > 2e11 and me["perp_top"][0]["name"] == "Hyperliquid" and abs(me["perp_top"][0]["share_30d"] - 0.75) < 1e-6
    assert ca["evidence"]["RWA on-chain value ex-stablecoins (USD)"][-1][1] == 38.6e9
    states = {s["signal"][:20]: s["state"] for s in si["status"]}
    assert states["Stablecoin supply up"] == "firing" and states["BTC spot volume sust"] == "firing" and states["New issuance primiti"] == "firing"
    assert states["BTC dominance rollin"] == "not yet" and (snapdir / "dom.csv").exists()
    assert len(C.dominance_log()) == 1 and C.coingecko_global()["dominance"] == 59.4 and len(C.dominance_log()) == 1   # one row per day


def test_btc_cycles_without_price_feed_still_serves_the_research(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(C, "DOM_LOG", snapdir / "dom.csv")
    cy, si = C._cycles_now(), C._signals_now()
    B.json_safe(cy); B.json_safe(si)
    assert cy["price_error"] == "ConnectionError" and cy["research"]["anatomy"]["rows"] and cy["now"] is None
    assert len(si["status"]) == 6 and all(s["state"] in ("firing", "not yet", "watch", "no data") for s in si["status"])


def test_btc_cycles_helpers():
    from app.topics.btc_cycles import halving_overlay, rising_weeks
    s = pd.Series(range(1, 200), index=pd.date_range("2026-01-01", periods=199))
    assert rising_weeks(s) >= 8
    s2 = pd.concat([s, pd.Series([1.0], index=[s.index[-1] + pd.Timedelta(days=1)])])
    assert rising_weeks(s2) == 0
    px = pd.Series(1.0, index=pd.date_range("2024-01-01", "2024-12-31"))
    ov = halving_overlay(px)
    assert list(ov) == ["Cycle 4 (2024)"] and all(p[1] == 1.0 for p in ov["Cycle 4 (2024)"])


def _chart(mult=1.0, start=60000.0, n=365, seed=1):
    import math
    rng = np.random.default_rng(seed)
    days = pd.date_range("2025-10-25", periods=n)
    btc = [start]
    for _ in range(n - 1):
        btc.append(btc[-1] * math.exp(rng.normal(0, 0.03)))
    px = [(b / btc[0]) ** mult * 10 for b in btc]
    ms = [int(d.timestamp() * 1000) for d in days]
    return {"btc": {"prices": [[t, v] for t, v in zip(ms, btc)], "market_caps": [[t, v * 2e7] for t, v in zip(ms, btc)], "total_volumes": [[t, 1e10] for t in ms]},
            "coin": {"prices": [[t, v] for t, v in zip(ms, px)], "market_caps": [[t, v * 1e8] for t, v in zip(ms, px)], "total_volumes": [[t, 1e8] for t in ms]}}


def test_btc_cycles_coins(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    charts = _chart(mult=2.0)
    import json as _json
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    monkeypatch.setattr(C, "PACE", 0)
    assert C._coins_now()["coins"][0]["error"].startswith("loading")          # before the background fill: pending, not an error
    assert set(C.fill_coins().values()) == {"ok"}
    k = C._coins_now()
    B.json_safe(k)
    assert len(k["coins"]) == len(C.coins_list()) == 28 and all("kpi" in c for c in k["coins"]) and k["btc_now"] > 0
    hype = next(c for c in k["coins"] if c["ticker"] == "HYPE")
    assert hype["links"]["coinmarketcap"].endswith("/hyperliquid/") and hype["links"]["defillama"].endswith("/hyperliquid") and len(hype["spark"]) == 90
    assert abs(hype["kpi"]["beta"] - 2.0) < 0.05 and 0 <= hype["kpi"]["rsi"] <= 100 and 0 <= hype["kpi"]["rsi_vs_btc"] <= 100
    f = C._coin_now("HYPE")
    B.json_safe(f)
    assert len(f["projection"]) == 2 and all(p["bear"] < p["base"] < p["bull"] for p in f["projection"])
    sc = C.scenarios()["scenarios"][0]["base"]["btc"]
    assert abs(f["projection"][0]["base"] - f["kpi"]["price"] * (sc / k["btc_now"]) ** f["kpi"]["beta"]) < 1e-3 * f["kpi"]["price"]
    assert f["implied_mcap_base"][0]["mcap"] > 0 and set(f["series"]) == {"price", "btc_indexed", "ratio", "rsi", "rsi_vs_btc", "market_cap"}
    assert all(0 <= v <= 100 for _, v in f["series"]["rsi_vs_btc"] if v is not None)
    with pytest.raises(ValueError):
        C._coin_now("NOPE")
    # a coin whose fetch fails is listed with its error, the rest still come through
    from app import cache
    cache._cache.clear()
    import shutil
    shutil.rmtree(snapdir, ignore_errors=True)

    def flaky(url, *a, **kw):
        if "zcash" in url:
            raise RuntimeError("curl exit 0, HTTP 429: 'rate limited'")
        return _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"])
    monkeypatch.setattr(B, "_download", flaky)
    res = C.fill_coins(pause_on_limit=0)
    assert res["ZEC"].startswith("RuntimeError") and res["SOL"] == "ok"
    k2 = C._coins_now()
    zec = next(c for c in k2["coins"] if c["ticker"] == "ZEC")
    assert zec["error"].startswith("loading") and sum("kpi" in c for c in k2["coins"]) == 27


def test_btc_cycles_rsi_and_beta_edges():
    from app.topics.btc_cycles import beta_to_btc, rsi
    up = pd.Series(np.linspace(1, 2, 90), index=pd.date_range("2026-01-01", periods=90))
    assert rsi(up).dropna().iloc[-1] > 95
    flat = pd.Series(1.0, index=up.index)
    assert beta_to_btc(up, flat) is None                          # BTC never moves: no beta
    assert beta_to_btc(up ** 5, up) == 3.0 and beta_to_btc(up ** 0.1, up) == 0.5     # clipped to [0.5, 3]


def test_btc_cycles_coin_notes(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    notes = C.coin_notes()["coins"]
    assert {c["ticker"] for c in C.coins_list()} == set(notes)
    assert all(n["narrative"] and n["standout"] and n["thesis"] for n in notes.values())
    charts = _chart(mult=2.5)
    import json as _json
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    monkeypatch.setattr(C, "PACE", 0)
    C.fill_coins()
    k = C._coins_now()
    hype = next(c for c in k["coins"] if c["ticker"] == "HYPE")
    assert hype["notes"]["thesis"] and any("High beta" in t for t in hype["now"]) and any("Market cap rank" in t for t in hype["now"])
    assert C._coin_now("SOL")["notes"]["narrative"].startswith("Solana")
    assert C.stands_out({"rsi_vs_btc": 75, "beta": 0.6, "from_high": -0.8}, []) == [
        "Running hot against BTC (RSI vs BTC 75).", "80% below its 1-year high.", "Low beta (0.6): has moved less than BTC, so its projection band is narrow."]


# ------------------------------------------------------------------ ETF and MSTR tabs
def _farside_html(n=720):
    days = pd.bdate_range("2024-01-11", periods=n)
    cols = ["IBIT", "FBTC", "BITB", "ARKB", "BTCO", "EZBC", "BRRR", "HODL", "BTCW", "GBTC", "BTC"]
    rows = "".join("<tr><td>" + d.strftime("%d %b %Y") + "</td>" + "".join(f"<td>{'(12.5)' if c == 'GBTC' else '-' if c == 'BTCW' else f'{10 + i % 7:.1f}'}</td>" for c in cols) + "<td>0</td></tr>"
                   for i, d in enumerate(days))
    return ("<html><body><table class='nav'><tr><td>menu</td></tr></table><table class='etf'><thead><tr><th></th>" + "".join(f"<th>{c}</th>" for c in cols)
            + "<th>Total</th></tr></thead><tbody>" + rows + "<tr><td>Total</td>" + "<td>1</td>" * 12 + "</tr></tbody></table></body></html>")


def _bitbo_page(n=720):
    ms = [int(d.timestamp() * 1000) for d in pd.bdate_range("2024-01-11", periods=n)]
    return "var historyBtc = [" + ",".join(f"[getPreviousBusinessDay({t}), truncate({100 + i % 9 - 4}, 2)]" for i, t in enumerate(ms)) + "]; var mergedHistoryBtc = [];"


def _mstr_json():
    days = pd.date_range("2020-08-11", "2026-10-20", freq="W")
    pts, hold = [], 21454
    for i, d in enumerate(days):
        if i % 5 == 0:
            hold += 1000
        pts.append({"d": str(d.date()), "mstr": 13 + i * 0.4, "btc": 11000 + i * 250, "hold": hold, "basic": 95_000_000 + i * 200_000, "dil": 1})
    return {"note": "fixture", "points": pts}


def _yahoo(start=10.0, n=400, seed=2):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp("2026-10-20"), periods=n)
    px = start * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    return {"chart": {"result": [{"timestamp": [int(d.timestamp()) for d in days], "indicators": {"quote": [{"close": list(px)}]}}]}}


def test_btc_etf_and_mstr(snapdir, monkeypatch):
    from app.topics import btc_cycles as C, btc_flows as F
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: _cm())
    monkeypatch.setattr(F, "fetch", lambda url, ttl, **k: _farside_html() if "farside" in url else _bitbo_page())
    monkeypatch.setattr(F, "fetch_json", lambda url, ttl, **k: _mstr_json() if "mstr-nav" in url else _yahoo(150 if "MSTR" in url else 60000 if "BTC-USD" in url else 1.0))
    e = F._etf_now()
    B.json_safe(e)
    assert not [k for k in e if k.endswith("_error")], [k for k in e if k.endswith("_error")]
    assert e["kpi"]["since_launch_usd_m"] > 0 and e["table"][0]["ticker"] != "GBTC" and next(r for r in e["table"] if r["ticker"] == "GBTC")["since_launch"] < 0
    assert e["kpi"]["streak"] > 0 and "Others" in e["cum_by_issuer"] and e["cum_btc"][-1][1] > 0 and e["milestones"][0]["date"] == "2024-01-10"
    assert "Hong Kong spot ETFs (BTC)" in e["intl"]
    m = F._mstr_now()
    B.json_safe(m)
    assert m["kpi"]["purchases"] > 50 and m["purchases"][0]["date"] > m["purchases"][-1]["date"] and m["kpi"]["approx_avg_cost"] > 0
    assert m["price_source"] == "Yahoo daily closes" and -1 <= m["kpi"]["corr90"] <= 1 and m["mnav"][-1][1] > 0
    assert {t["country"] for t in m["treasuries"]} == {"UK", "HK"} and all("price" in t for t in m["treasuries"])


def test_farside_parser_rejects_a_changed_page():
    from app.topics.btc_flows import parse_farside, _num
    assert _num("(12.5)") == -12.5 and _num("-") == 0 and _num("1,234.5") == 1234.5
    with pytest.raises(ValueError):
        parse_farside("<table><tr><td>nothing</td></tr></table>")
    df = parse_farside(_farside_html(80))
    assert len(df) == 80 and df["GBTC"].iloc[0] == -12.5 and df["BTCW"].iloc[0] == 0


def test_ai_merged_endpoints(snapdir, monkeypatch):
    from app.topics import ai, ai_jobs as J
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS if "ai-tracker" in url else FRED if "fred" in url else AGG if "aggregate" in url else IND)
    assert {"openings", "headcount", "wages", "ratio", "firms", "users", "agents", "skills"} <= set(ai.ENDPOINTS)
    w = J._wages_now()
    B.json_safe(w)
    assert set(w["levels"]) == set(J.US_WAGES) and "All private" not in w["premium"] and w["as_of"]
    assert all(sid.endswith("03") for sid in J.US_WAGES.values())
    h = J._headcount_now()
    assert "HK" in h and h["HK"] == {}
    r = J._ratio_now()
    assert r["US"]["ai_wide_index"] and r["US"]["ai_wide_over_professions"]


# ------------------------------------------------------------------ housing: boroughs, fixed rate, US and HK
def _rvd_xls():
    import io
    rows = [["Private Domestic - Price Indices (1999 = 100)", None, None]]
    for y in range(2010, 2027):
        for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
            rows.append([y if i == 0 else None, m, 200 + (y - 2010) * 10 + i])
    buf = io.BytesIO(); pd.DataFrame(rows).to_excel(buf, index=False, header=False)
    return buf.getvalue().decode("latin-1")


HIBOR = {"result": {"records": [{"end_of_month": f"{y}-{m:02d}", "ir_1m": 1 + (y - 2015) * 0.2} for y in range(2015, 2027) for m in range(1, 13)]}}


def housing_mocks(monkeypatch):
    from app.topics import housing as H
    def fetch(url, ttl, **k):
        if "ukhpi" in url:
            return HPI
        if "rvd.gov.hk" in url:
            return _rvd_xls()
        if "fred" in url:
            return FRED
        return BOE
    monkeypatch.setattr(H, "fetch", fetch)
    monkeypatch.setattr(H, "fetch_json", lambda url, ttl, **k: HIBOR if "hkma" in url else ONS(100) if "L522" in url else ONS(500))
    monkeypatch.setattr(H, "PACE", 0)
    return H


def test_housing_boroughs_global_and_fixed_rate(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    b, g, a = H._boroughs_now(), H._global_now(), H._afford_now()
    for d in (b, g, a):
        B.json_safe(d)
    assert len(b["rows"]) == 33 and not b["errors"] and {"Kensington and Chelsea", "City of Westminster", "Richmond upon Thames"} <= {r["borough"] for r in b["rows"]}
    assert not [k for k in g if k.endswith("_error")], [k for k in g if k.endswith("_error")]
    assert set(g["us"]) == set(H.US_HPI) and g["hk"] and set(g["rates"]) == {"UK 2-year fixed (75% LTV)", "US 30-year fixed", "HK 1-month HIBOR"}
    assert {r["market"] for r in g["table"]} >= {"London", "Hong Kong (RVD)"}
    assert a["mortgage_basis"].startswith("the Bank of England's quoted 2-year fixed") and a["fixed_2y"]
    assert len(H.parse_rvd(_rvd_xls().encode("latin-1"))) == 17 * 12


def test_robotaxi_tesla_rate_and_rules(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)
    monkeypatch.setattr(R, "fetch_json", lambda url, ttl, **k: _yahoo(250))
    t, f, s = R._tesla_now(), R._footprint_now(), R._safety_now()
    for d in (t, f, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], [k for k in d if k.endswith("_error")]
    assert t["kpi"]["deliveries_last"] > 0 and t["tsla"] and {"UK", "HK"} <= set(t["fsd_markets"]) and t["milestones"][0]["date"] >= t["milestones"][-1]["date"]
    assert {r["market"] for r in f["regulation"]} >= {"US", "UK", "HK", "China"}
    w = [x for x in s["reports"]["rate"] if x["operator"] == "Waymo LLC"]
    assert w and all(x["per_million"] >= 0 for x in w)


def test_source_health(snapdir, monkeypatch):
    pytest.importorskip("aiohttp")
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    from app.topics import robotaxi as R
    B.HEALTH.clear()
    calls = {"n": 0}

    def dl(url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return SGO
        raise ConnectionError("down")
    monkeypatch.setattr(B, "_download", dl)
    monkeypatch.setattr(R, "fetch", B.fetch)                    # the real fetch, over the fake download
    R.sgo()                                                     # works, snapshot written
    from app import cache
    cache._cache.clear()
    R.sgo()                                                     # fails, served from the snapshot
    h = topics.health()
    rt = h["dashboards"]["robotaxi"]
    assert rt["stale"] == 1 and rt["sources"][0]["host"] == "static.nhtsa.gov" and rt["sources"][0]["error"] == "ConnectionError: down"
    assert set(topics.REGISTRY) <= set(h["dashboards"])
    B.HEALTH[R.SGO]["fail"] = B.HEALTH[R.SGO]["fail"]
    B.STALE[R.SGO] -= 5 * 86400                                  # snapshot five days old: past the 3-day threshold
    assert topics.health()["dashboards"]["robotaxi"]["sources"][0]["alert"]

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            j = await (await c.get("/api/health")).json()
            assert "robotaxi" in j["dashboards"] and j["thresholds"]["stale_days"] == 3
    asyncio.run(go())
    B.HEALTH.clear()
