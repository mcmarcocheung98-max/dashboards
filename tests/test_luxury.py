"""Luxury Tracker (app/topics/luxury.py): hand-entered prices, premiums, baskets, heat, ROI, readings and signals, on fixtures (no network)."""
import json

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import luxury as M

TODAY = pd.Timestamp("2026-11-07")


def _fred(sid: str, start: str, n: int, v0: float, step: float, freq: str = "MS") -> str:
    idx = pd.date_range(start, periods=n, freq=freq)
    return "observation_date," + sid + "\n" + "\n".join(f"{d.date()},{v0 + i * step:.4f}" for i, d in enumerate(idx)) + "\n"


FIX = {"CPIAUCSL": _fred("CPIAUCSL", "2015-01-01", 142, 230, 0.8), "GBRCPIALLMINMEI": _fred("GBRCPIALLMINMEI", "2015-01-01", 142, 100, 0.3),
       "DEXUSUK": _fred("DEXUSUK", "2015-01-01", 3100, 1.30, 0.0, "B"), "DEXSZUS": _fred("DEXSZUS", "2015-01-01", 3100, 0.90, 0.0, "B"),
       "DEXUSEU": _fred("DEXUSEU", "2015-01-01", 3100, 1.10, 0.0, "B"), "SP500": _fred("SP500", "2016-11-07", 2600, 2100, 2.0, "B")}


def wiki_json(url: str) -> str:
    """Monthly pageviews for any article: a level from the title, a yearly cycle, a 2022 hump and a recent fade for Rolex articles."""
    import re
    m = re.search(r"/per-article/en\.wikipedia/all-access/user/([^/]+)/monthly/(\d{8})\d*/(\d{8})", url)
    assert m, url
    title = m.group(1)
    level = 20000 + sum(ord(c) for c in title) % 9000
    months = pd.date_range(pd.Timestamp(m.group(2)), pd.Timestamp(m.group(3)), freq="MS")
    items = []
    for i, d in enumerate(months):
        v = level * (1 + 0.15 * ((i % 12) / 11)) * (1.6 if d.year == 2022 else 1) * (0.8 if title.startswith("Rolex") and d.year == 2026 else 1)
        items.append({"project": "en.wikipedia", "article": title, "granularity": "monthly", "timestamp": d.strftime("%Y%m%d00"), "access": "all-access", "agent": "user", "views": int(v)})
    return json.dumps({"items": items})


def fake_fetch(url, ttl=0, **k):
    for sid, text in FIX.items():
        if url.endswith("id=" + sid):
            return text
    if "/metrics/pageviews/" in url:
        return wiki_json(url)
    raise ConnectionError("fixture: no such source " + url)


def smoke_patch():
    """Used by scripts/smoke.py: FRED answers from the fixtures above; the hand-entered CSVs are the committed ones."""
    M.fetch = fake_fetch
    M._now = lambda: TODAY


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "_now", lambda: TODAY)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


def test_topic_is_registered():
    t = topics.REGISTRY["luxury"]
    assert [k for k, _ in t.tabs] == ["overview", "watches", "bags", "roi", "heat", "liquidity", "fees"] and set(t.slow) <= set(M.ENDPOINTS)
    assert topics.category("luxury") == "Money & markets" and "FRED" in json.dumps(M.SOURCES)
    assert "Not investment advice" in M.NOTES and "Not investment advice" in M.FOOTER
    for name in ("fred cpi us", "fred cpi uk", "fred gbpusd", "fred chfusd", "fred sp500"):
        assert name in topics.PROBE_URLS


def test_items_and_files_have_the_starter_set():
    ids = {i["id"] for i in M.items()}
    assert {"sub-126610ln", "gmt-126710blnr", "gmt-126710blro", "daytona-126500ln", "dj41-126334", "explorer-124270", "op41-124300", "daydate-228238"} <= ids
    assert {"celine-ava-triomphe", "ysl-le57-smooth", "lv-alma-bb-mono", "hermes-birkin25-togo", "chanel-cf-medium-caviar"} <= ids
    assert all(i["category"] in ("watch", "bag") and i["source"] and i["wiki"] for i in M.items())
    used = {r["item"] for r in M.rows("retail")} | {r["item"] for r in M.rows("resale")}
    assert used <= ids, used - ids                                     # every price row names a known item
    for r in M.rows("retail") + M.rows("resale"):
        assert M._f(r["price"]) and r["source"].startswith("http") and (r.get("currency") or "GBP") in ("GBP", "USD", "EUR", "CHF", "HKD")
    for r in M.rows("resale"):
        assert r["kind"] in ("asking", "sold") and r["condition"]
    assert {f["platform"] for f in M.fees()} >= {"Chrono24", "Vestiaire Collective", "The RealReal", "eBay US"}
    assert all(f["source"].startswith("http") for f in M.fees())
    assert M.items(with_watchlist=True) == M.items()                    # watchlist.csv holds only the comment row so far


def test_parsers():
    s = M.parse_fred(FIX["CPIAUCSL"])
    assert len(s) == 142 and s.index[0] == pd.Timestamp("2015-01-01")
    ons = '"Title","CPI INDEX 00: ALL ITEMS 2015=100"\n"CDID","D7BT"\n"2015","100.0"\n"2015 Q1","99.5"\n"2015 JAN","99.3"\n"2015 FEB","99.5"\n' + "\n".join(f'"2016 {m}","10{i}"' for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]))
    o = M.parse_ons(ons)
    assert len(o) == 14 and o.index[0] == pd.Timestamp("2015-01-01") and o.iloc[-1] == 1011
    with pytest.raises(ValueError):
        M.parse_fred("a,b\n")


def test_fx_and_conversion(mocked):
    FX = M.fx()
    assert not FX["fallback"] and abs(M.to_gbp(1300, "USD", pd.Timestamp("2022-06-15"), FX) - 1000) < 1
    assert abs(M.to_gbp(100, "GBP", pd.Timestamp("2022-06-15"), FX) - 100) < 1e-9
    chf = M.to_gbp(117, "CHF", pd.Timestamp("2022-06-15"), FX)
    assert abs(chf - 100) < 1
    assert abs(M.to_gbp(1000, "EUR", TODAY, FX) - 846.15) < 1


def test_fx_falls_back_when_fred_never_answered(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")))
    FX = M.fx()
    assert FX["fallback"] and M.to_gbp(1000, "USD", TODAY, FX) == 780


def test_premium_basket_and_heat(mocked):
    steps = pd.Series({pd.Timestamp("2020-01-01"): 7000.0, pd.Timestamp("2022-01-01"): 8000.0, pd.Timestamp("2024-01-01"): 9000.0})
    res = pd.Series({pd.Timestamp("2020-06-01"): 9000.0, pd.Timestamp("2022-03-01"): 16000.0, pd.Timestamp("2024-06-01"): 10000.0, pd.Timestamp("2026-06-01"): 8500.0})
    p = M.premium_series(res, steps)
    assert abs(p.iloc[0] - 9000 / 7000 + 1) < 1e-9 and abs(p.iloc[-1] - 8500 / 9000 + 1) < 1e-9
    assert M.retail_at(steps, pd.Timestamp("2021-12-31")) == 7000 and M.retail_at(steps, pd.Timestamp("2019-01-01")) is None
    assert M.change_over(res, 1, 120) is None                             # no point within 120 days of a year before the last
    assert M.change_over(res, 2, 180) == round(8500 / 10000 - 1, 4)
    views = [{"id": f"w{i}", "name": f"w{i}", "category": "watch", "retail_points": M._pts(steps * (1 + i / 10), 0), "resale_series": M._pts(res * (1 + i / 10), 0)} for i in range(5)]
    bk = M.basket("watch", views)
    assert len(bk["premium"]) > 30 and bk["premium"].max() > 0.9 and bk["premium"].iloc[-1] < 0 and bk["need"] == 4
    assert bk["share_above"].iloc[-1] == 0 and 0.99 < bk["index"].iloc[0] / 100 < 1.01 and bk["index"].iloc[-1] < bk["index"].max()
    h = M.heat("watch", bk)
    assert h["score"] is not None and -2 <= h["score"] <= 2 and h["verdict"] in ("cold", "cooling", "neutral", "running hot", "overheated")
    assert {c["key"] for c in h["components"]} == {"level", "change_1y", "breadth", "indices"} and len(h["history"]) > 12
    assert "Watches" in h["words"] and "below retail" in h["words"]
    assert M.verdict(1.2) == "overheated" and M.verdict(-0.6) == "cooling" and M.verdict(None) == "not enough data yet" and M.lean(0.7) == 1 and M.lean(-0.7) == -1


def test_chain_index_and_rolling_z():
    df = pd.DataFrame({"a": [100, 110, None, 121], "b": [50, 55, 60.5, None], "c": [10, 11, 12.1, 13.31]}, index=pd.date_range("2024-01-31", periods=4, freq="ME"))
    idx = M.chain_index(df, min_items=2)
    assert abs(idx.iloc[1] - 110) < 1e-6 and abs(idx.iloc[2] - 121) < 1e-6 and abs(idx.iloc[-1] - 121) < 1e-6   # month 4: one item priced in both months, so the index holds
    z = M.rolling_z(pd.Series(range(20), index=pd.date_range("2024-01-31", periods=20, freq="ME"), dtype=float), min_n=12)
    assert len(z) == 9 and z.iloc[-1] > 1


def test_roi_rows_and_fees(mocked):
    views = [{"id": "w", "name": "W", "category": "watch", "retail_points": [[int(pd.Timestamp("2020-01-01").timestamp()), 7000], [int(pd.Timestamp("2023-01-01").timestamp()), 9000]],
              "latest": {"price": 10000, "kind": "sold", "date": "2026-10-01"}}]
    fee = [{"platform": "Chrono24", "seller_pct": 6.95, "payout_days": 7, "verify": True}]
    spx = M.parse_fred(FIX["SP500"])
    cpi = M.parse_fred(FIX["GBRCPIALLMINMEI"])
    rows = M.roi_rows(views, fee, spx, cpi)
    assert [r["buy_date"][:4] for r in rows] == [str(y) for y in range(2020, 2027)]
    r0 = rows[0]
    assert r0["buy_price"] == 7000 and r0["net"] == round(10000 * (1 - 0.0695)) and abs(r0["ret"] - (r0["net"] / 7000 - 1)) < 1e-3
    assert r0["annual"] is not None and r0["spx"] > 0 and r0["cpi"] > 0 and r0["real"] < r0["ret"]
    assert rows[3]["buy_price"] == 9000
    assert M.annualised(0.5, 10) is None and M.annualised(-1.2, 400) is None and M.net_after_fee(1000, {"platform": "x", "seller_pct": 10})["net"] == 900


def test_payloads_readings_and_signals(mocked):
    assert M.READINGS() == [] and M.SIGNALS() == []                       # nothing cached yet
    for k in M.ENDPOINTS:
        d = M.ENDPOINTS[k]()
        B.json_safe(d)
    O, W, G, R, H, F, L = (M.ENDPOINTS[k]() for k in ("overview", "watches", "bags", "roi", "heat", "fees", "liquidity"))
    A = L["attention"]
    assert len(A["articles"]) == 12 and len(A["items"]) == 13 and set(A["baskets"]) == {"watch", "bag"} and not L["attention_errors"]
    assert A["baskets"]["watch"]["z12"] < 0 < A["baskets"]["bag"]["z12"] or A["baskets"]["watch"]["z12"] < A["baskets"]["bag"]["z12"]   # the fixture fades the Rolex articles in 2026
    assert len(A["baskets"]["watch"]["points"]) > 120 and A["last_full_month"] == "2026-10-01"
    assert O["kpi"]["n_watches"] == 8 and O["kpi"]["n_bags"] == 5 and len(O["items"]) == 13 and O["where"]
    assert len(W["items"]) == 8 and len(G["items"]) == 5 and "calendar" in G and G["retail_rise"]["brand"]
    assert len(O["rolex_premium"]) > 24 and len(G["ratio"]) >= 3, "the committed points must give both baskets a monthly history (the bag basket starts in 2026: three of its five bags have no earlier resale record)"
    assert R["sp500_source"] == "FRED" and R["cpi_uk_source"] == "FRED" and R["rows"] and all(r["net"] <= r["gross"] for r in R["rows"])
    assert H["watch"]["score"] is not None and H["bag"]["score"] is not None and H["score"] is not None and F["fees"]
    r = {x["key"]: x for x in M.READINGS()}
    assert {"rolex_premium", "bags_ratio", "heat_watch", "heat_bag", "attention_watch", "attention_bag"} <= set(r) and all(x["tab"] in {t for t, _ in topics.REGISTRY["luxury"].tabs} and x["lean"] in (-1, 0, 1) for x in r.values())
    sig = {x["key"]: x for x in M.SIGNALS()}
    wl = json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["luxury"]
    assert set(sig) == {w["key"] for w in wl} and all(w.get("approved") and not w.get("proposed") for w in wl)   # approved by the owner on 7 Nov 2026
    assert all(isinstance(x["crossed"], bool) and x["lean"] in (-1, 0, 1) for x in sig.values())
    p = sig["rolex_premium"]["value"]
    assert sig["rolex_premium"]["crossed"] == (p < 0 or p > 50)
    assert sig["rolex_1y"]["crossed"] == (abs(sig["rolex_1y"]["value"]) >= 15)
    assert sig["bags_ratio"]["crossed"] == (sig["bags_ratio"]["value"] < 0.5 or sig["bags_ratio"]["value"] > 1.0)
    assert sig["retail_rise"]["crossed"] == (sig["retail_rise"]["value"] is not None and sig["retail_rise"]["value"] > 10)
    assert sig["heat"]["crossed"] == (sig["heat"]["value"] > 1.5 or sig["heat"]["value"] < -1)


def test_signal_tests_at_the_edges(monkeypatch):
    pay = {"overview": {"kpi": {"rolex_premium": -0.05, "rolex_1y": -0.2, "bags_ratio": 0.45}}, "heat": {"score": 1.6}, "bags": {"retail_rise": {"brand": "Chanel", "value": 0.12}}}
    monkeypatch.setattr(M, "_cached_payload", lambda n: pay.get(n, {}))
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert all(sig[k]["crossed"] for k in ("rolex_premium", "rolex_1y", "bags_ratio", "retail_rise", "heat")) and sig["retail_rise"]["note"] == "Chanel"
    pay["overview"]["kpi"] = {"rolex_premium": 0.1, "rolex_1y": 0.05, "bags_ratio": 0.8}
    pay["heat"]["score"], pay["bags"]["retail_rise"]["value"] = 0.2, 0.05
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert not any(sig[k]["crossed"] for k in sig) and sig["rolex_premium"]["lean"] == 1 and sig["bags_ratio"]["lean"] == 0


def test_routes(mocked):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            page = await c.get("/luxury")
            js = await c.get("/luxury.js")
            fees = await c.get("/api/luxury/fees")
            method = await c.get("/api/luxury/method")
            return page.status, js.status, fees.status, (await fees.json())["fees"][0]["platform"], method.status, (await method.json())
    ps, js, fs, plat, ms, method = asyncio.run(go())
    assert ps == 200 and js == 200 and fs == 200 and plat and ms == 200
    assert any("method" in s["title"].lower() or "calculat" in s["title"].lower() for s in method["sections"]), "the README's Method section feeds the Method tab"


def test_retail_rise_needs_a_price_dated_a_year_ago(monkeypatch):
    monkeypatch.setattr(M, "_now", lambda: TODAY)
    ts = lambda d: int(pd.Timestamp(d).timestamp())
    views = [{"id": "sparse", "name": "Sparse", "brand": "Sparse", "category": "bag", "retail_points": [[ts("2021-11-01"), 1410], [ts("2026-08-01"), 1755]]},
             {"id": "fresh", "name": "Fresh", "brand": "Fresh", "category": "bag", "retail_points": [[ts("2025-10-01"), 1000], [ts("2026-04-01"), 1120]]},
             {"id": "held", "name": "Held", "brand": "Held", "category": "bag", "retail_points": [[ts("2024-01-01"), 500], [ts("2026-01-01"), 520]]}]
    cal, rr = M.retail_calendar(views)
    by = rr["by_brand"]
    assert by["Sparse"]["rise_12m"] is None and by["Sparse"]["since"] == {"value": round(1755 / 1410 - 1, 4), "date": "2021-11-01"}   # +24% over 4.75 years, not "12 months"
    assert by["Fresh"]["rise_12m"] == 0.12 and by["Fresh"]["since"]["date"] == "2025-10-01"
    assert by["Held"]["rise_12m"] == 0.0 and by["Held"]["since"] == {"value": 0.04, "date": "2024-01-01"}       # the Jan 2026 row is 10 months old: no rise in the window
    assert rr["brand"] == "Fresh" and rr["value"] == 0.12 and rr["note"] is None
    row = next(c for c in cal if c["brand"] == "Sparse")
    assert row["rise_12m"] is None and row["n_12m"] == 0 and row["years"]["2026"] == round(1755 / 1410 - 1, 4)
    cal, rr = M.retail_calendar(views[:1])
    assert rr["brand"] is None and rr["value"] is None and "no brand" in rr["note"]
    monkeypatch.setattr(M, "_cached_payload", lambda n: {"bags": {"retail_rise": rr}}.get(n, {}))
    sig = {s["key"]: s for s in M.SIGNALS()}
    assert sig["retail_rise"]["value"] is None and sig["retail_rise"]["crossed"] is False and "no" in sig["retail_rise"]["note"]


def test_wiki_attention_helpers(mocked):
    s = M.wiki_views("Rolex Submariner")
    assert s.index[0] == pd.Timestamp("2015-07-01") and s.index[-1] >= pd.Timestamp("2026-10-01") and M.wiki_key("Rolex Submariner").endswith("/monthly/2015070100/now")
    assert "Rolex_Submariner" in M.wiki_url("Rolex Submariner") and M.wiki_url("Celine (brand)").count("%28") == 1
    z = M.z12(pd.Series([100.0, 110.0] * 6 + [160.0, 105.0], index=pd.date_range("2025-01-01", periods=14, freq="MS")))
    assert len(z) == 2 and z.iloc[0] == 3.0 and abs(z.iloc[1]) < 0.5      # (160 - 105) / 5 clips to +3; a flat history (sd 0) gives no z
    assert len(M.z12(pd.Series([100.0] * 13, index=pd.date_range("2025-01-01", periods=13, freq="MS")))) == 0
    a = M.attention({"Rolex Submariner": s, "Birkin bag": M.wiki_views("Birkin bag")}, [{"id": "a", "name": "A", "category": "watch", "wiki": "Rolex Submariner"}, {"id": "b", "name": "B", "category": "bag", "wiki": "Birkin bag"}, {"id": "c", "name": "C", "category": "bag", "wiki": "Missing"}])
    assert a["items"][2]["last"] is None and a["items"][0]["last"]["month"] == "2026-10-01" and a["baskets"]["watch"]["titles"] == ["Rolex Submariner"]
    assert abs(sum(p[1] for p in a["baskets"]["bag"]["points"]) / len(a["baskets"]["bag"]["points"]) - 100) < 1


def test_auction_lots_estimates_and_sell_through(mocked, monkeypatch):
    lots_rows = [{"date": "2022-05-08", "house": "Phillips", "sale": "Geneva XV", "lot": "12", "item": "daytona-126500ln", "price": "60000", "currency": "CHF", "basis": "with premium", "est_low": "30000", "est_high": "50000", "sold": "yes", "source": "https://x/1", "note": ""},
                 {"date": "2022-05-08", "house": "Phillips", "sale": "Geneva XV", "lot": "13", "item": "sub-126610ln", "price": "18000", "currency": "CHF", "basis": "with premium", "est_low": "15000", "est_high": "25000", "sold": "yes", "source": "https://x/2", "note": "verify"},
                 {"date": "2022-05-08", "house": "Phillips", "sale": "Geneva XV", "lot": "14", "item": "gmt-126710blro", "price": "", "currency": "CHF", "basis": "", "est_low": "20000", "est_high": "30000", "sold": "no", "source": "https://x/3", "note": "bought in"},
                 {"date": "2024-11-10", "house": "Christie's", "sale": "Rare Watches", "lot": "5", "item": "daytona-126500ln", "price": "32000", "currency": "USD", "basis": "hammer", "est_low": "30000", "est_high": "40000", "sold": "yes", "source": "https://x/4", "note": ""},
                 {"date": "2024-11-12", "house": "Christie's", "sale": "Handbags HK", "lot": "7", "item": "hermes-birkin25-togo", "price": "150000", "currency": "HKD", "basis": "with premium", "est_low": "120000", "est_high": "180000", "sold": "yes", "source": "https://x/5", "note": ""}]
    sales_rows = [{"date": "2022-05-08", "house": "Phillips", "sale": "Geneva XV", "category": "watch", "offered": "200", "sold": "200", "total": "35m", "currency": "CHF", "source": "https://x/s1", "note": ""},
                  {"date": "2024-11-12", "house": "Christie's", "sale": "Handbags HK", "category": "bag", "offered": "250", "sold": "190", "total": "", "currency": "HKD", "source": "https://x/s2", "note": "verify"}]
    real_rows = M.rows
    monkeypatch.setattr(M, "rows", lambda name: {"auctions": lots_rows, "auction_sales": sales_rows}.get(name, real_rows(name)))
    FX = M.fx()
    lots = M.auction_lots(FX)
    assert [l["lot"] for l in lots] == ["12", "13", "14", "5", "7"] and lots[2]["price"] is None and not lots[2]["sold"] and lots[1]["verify"]
    assert abs(lots[0]["price"] - 60000 / 1.17) < 60 and abs(lots[0]["vs_estimate"] - 0.5) < 1e-6 and lots[0]["category"] == "watch" and lots[4]["category"] == "bag"
    assert lots[4]["price"] == 10 * 150000 // 100 or lots[4]["price"] == 15000        # HKD has no FRED fixing: the fallback 0.10
    ve = M.vs_estimate_series(lots)
    assert len(ve["watch"]["lots"]) == 2 and ve["watch"]["latest"] == round(32000 / 35000 - 1, 4) and set(ve["watch"]["by_item"]) == {"daytona-126500ln", "sub-126610ln"}
    assert len(ve["watch"]["half_year_median"]) == 2 and ve["bag"]["latest"] == 0.0
    st = M.sell_through(lots)
    w = st["watch"]
    assert w["latest"] is None or w["points"], w
    assert [s["basis"] for s in w["sales"]] == ["house count"] and w["sales"][0]["rate"] == 1.0 and w["lots_sold_share"] == 0.75 and w["n_lots"] == 4
    assert st["bag"]["sales"][0]["rate"] == 0.76 and st["bag"]["latest"] == 0.76 and st["bag"]["sales"][0]["verify"]
    # three lots of one sale with no house count: a sample-based rate, marked so
    lots_rows[3]["house"], lots_rows[3]["sale"], lots_rows[3]["date"] = "Phillips", "Geneva XV", "2022-05-08"
    sales_rows.pop(0)
    lots = M.auction_lots(FX)
    st = M.sell_through(lots)
    assert st["watch"]["sales"][0]["basis"] == "from lots entered" and st["watch"]["sales"][0]["offered"] == 4 and st["watch"]["sales"][0]["rate"] == 0.75
    r = {x["key"]: x for x in M.readings(lambda n: {"liquidity": {"auctions": {"sell_through": st}}}.get(n, {}))}
    assert r["sell_through_watch"]["value"] == 75.0 and r["sell_through_watch"]["lean"] == 0 and r["sell_through_bag"]["lean"] == 0
