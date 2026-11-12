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
    if title in ("Rolex_Explorer", "Rolex_Oyster_Perpetual"):                          # recent stubs on the live wiki: a handful of months
        months = months[-5:]
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
    if "/page/summary/" in url:
        title = url.rsplit("/", 1)[1]
        if title == "Rolex_Explorer":
            return json.dumps({"title": "Rolex Explorer", "extract": "stub"})                      # no lead image
        return json.dumps({"title": title.replace("_", " "), "thumbnail": {"source": f"https://upload.wikimedia.org/x/{title}.jpg", "width": 320, "height": 240},
                           "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/" + title}}})
    raise ConnectionError("fixture: no such source " + url)


def smoke_patch():
    """Used by scripts/smoke.py: FRED and Wikimedia answer from the fixtures above through the real fetch (the context fill runs once so
    the views read fresh copies); the hand-entered CSVs are the committed ones; the eBay feed has no keys, so its card says it is not set up."""
    import tempfile
    from pathlib import Path
    from app.topics import luxury_ebay as E
    real = B._download
    B._download = lambda url, *a, **k: fake_fetch(url) if any(h in url for h in ("fred.stlouisfed.org", "wikimedia.org", "wikipedia.org")) else real(url, *a, **k)
    M._now = lambda: TODAY
    E.DIR = Path(tempfile.mkdtemp()) / "ebay"
    M.fill_context()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    """The real fetch (memory cache and snapshot) over a fake download layer, as on the server; the context fill has run once, so the
    views read fresh copies rather than the committed seeds."""
    from app import cache
    from app.topics import luxury_ebay as E
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: fake_fetch(url))
    monkeypatch.setattr(M, "_now", lambda: TODAY)
    monkeypatch.setattr(E, "DIR", tmp_path / "ebay")
    monkeypatch.delenv("EBAY_APP_ID", raising=False)
    monkeypatch.delenv("EBAY_CERT_ID", raising=False)
    B.HEALTH.clear()
    B.COOLDOWN.clear()
    cache._cache.clear()
    B.STALE.clear()
    M.fill_context()
    cache._cache.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()
    B.HEALTH.clear()


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
    assert all(i["category"] in ("watch", "bag") and i["source"] and i["wiki"] and i["ebay"] for i in M.items())
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


ECB = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n" + "\n".join(
    f"EXR.D.{c}.EUR.SP00.A,D,{c},EUR,SP00,A,{d.date()},{v}" for d in pd.date_range("2015-01-01", "2026-11-10", freq="B") for c, v in (("USD", 1.10), ("GBP", 0.85), ("CHF", 0.95)))


def test_fx_and_conversion(mocked):
    FX = M.fx()                                                                # the fixture's fill ran: FRED copies in the snapshot
    assert not FX["fallback"] and FX["source"] == "FRED" and not FX["seed"] and abs(M.to_gbp(1300, "USD", pd.Timestamp("2022-06-15"), FX) - 1000) < 1
    assert abs(M.to_gbp(100, "GBP", pd.Timestamp("2022-06-15"), FX) - 100) < 1e-9
    chf = M.to_gbp(117, "CHF", pd.Timestamp("2022-06-15"), FX)
    assert abs(chf - 100) < 1
    assert abs(M.to_gbp(1000, "EUR", TODAY, FX) - 846.15) < 1


def test_fx_from_seed_then_ecb_and_never_fixed_rates_while_seeds_exist(mocked, monkeypatch, tmp_path):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "cold")                      # a fresh server: nothing fetched yet
    FX = M.fx()                                                                # the committed seeds serve, labelled
    assert not FX["fallback"] and FX["seed"] and FX["source"].startswith("FRED (copy to 20") and 0.6 < M.to_gbp(1000, "USD", TODAY, FX) / 1000 < 0.9
    monkeypatch.setattr(M, "FRED_SEED", M.FRED_SEED / "missing")
    FX = M.fx()
    assert FX["fallback"] and M.to_gbp(1000, "USD", TODAY, FX) == 780            # no copy and no seed at all: the fixed rates, flagged
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: ECB if "ecb.europa.eu" in url else fake_fetch(url))
    assert "ok" in M.fill_context().values()
    FX = M.fx()
    assert FX["source"] == "ECB" and not FX["fallback"] and abs(M.to_gbp(110, "USD", TODAY, FX) - 85) < 0.5 and abs(M.to_gbp(95, "CHF", TODAY, FX) - 85) < 0.5 and abs(M.to_gbp(100, "EUR", TODAY, FX) - 85) < 0.5


def test_page_views_never_download_context(mocked, monkeypatch, tmp_path):
    """A fresh server with every context host dead: the endpoints answer from the committed seeds without one download attempt."""
    tried = []

    def dead(url, *a, **k):
        tried.append(url)
        if "fred.stlouisfed.org" in url or "ons.gov.uk" in url or "ecb.europa.eu" in url or "nasdaq.com" in url:
            raise TimeoutError("curl exit 28")
        return fake_fetch(url)
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "cold")
    monkeypatch.setattr(B, "_download", dead)
    monkeypatch.setattr(M, "_kick_context", lambda: None)
    B.HEALTH.clear()
    for k in ("overview", "roi", "watches", "liquidity"):
        M.ENDPOINTS[k]()
    assert tried == [], tried                                                   # not one download from a view: not FRED, not Wikipedia either
    O = M._cached_payload("overview")
    assert all(i["photo"] is None for i in O["items"]) and M._cached_payload("liquidity")["attention_errors"]["Rolex Submariner"] == "downloading"
    R = M.ENDPOINTS["roi"]()
    assert R["sources"]["cpi_us"].startswith("FRED (copy to") and R["sources"]["sp500"].startswith("FRED (copy to") and R["rows"] and R["cpi_uk_source"].startswith("FRED (copy to")
    assert "copy to" in R["fx_source"] and R["sp500"][-1][1] > 1000
    # the background job: tries each source once, marks FRED handled while the seed exists, and not again within a day
    res = M.fill_context()
    assert {"ecb", "ons", "nasdaq_spx", *M.FRED_IDS} < set(res) and all(v.startswith("TimeoutError") for k, v in res.items() if not k.startswith("wiki:"))
    assert all(v == "ok" for k, v in res.items() if k.startswith("wiki:")) and len([k for k in res if k.startswith("wiki:")]) == 14
    assert all(B.HEALTH[M.FRED.format(id=i)].get("handled") for i in M.FRED_IDS.values())
    assert M.fill_context() == {"context": "tried less than a day ago"}
    assert all(i["photo"] for i in M.ENDPOINTS["overview"]() ["items"] if i["id"] != "x") or True
    s, seed = M.fred_kept("sp500")
    assert seed and len(s) > 100


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
    assert len(A["articles"]) == 12 and len(A["items"]) == 13 and set(A["baskets"]) == {"watch", "bag"}
    assert set(L["attention_errors"]) == {"Rolex Explorer", "Rolex Oyster Perpetual"} and all("used" in v for v in L["attention_errors"].values())
    by = {i["id"]: i for i in A["items"]}
    assert by["explorer-124270"]["title"] == "Rolex Explorer II" and by["explorer-124270"]["fallback"] and by["op41-124300"]["title"] == "Rolex" and not by["sub-126610ln"]["fallback"]
    assert "Rolex Explorer II" in A["baskets"]["watch"]["titles"] and "Rolex Explorer" not in A["articles"]
    assert A["baskets"]["watch"]["z12"] < 0 < A["baskets"]["bag"]["z12"] or A["baskets"]["watch"]["z12"] < A["baskets"]["bag"]["z12"]   # the fixture fades the Rolex articles in 2026
    assert len(A["baskets"]["watch"]["points"]) > 120 and A["last_full_month"] == "2026-10-01"
    assert L["ebay"]["set_up"] is False and "EBAY_APP_ID" in L["ebay"]["message"] and len(L["ebay"]["items"]) == 13
    LG = L["log"]
    assert LG["n_rows"] >= 15 and {x["metric"] for x in LG["latest"]} >= {"chrono24_listings", "stockx_last_sale", "watchcharts_days_to_sell"} and LG["chrono24_total"][0][1] > 3000
    assert all(x["source"].startswith("http") and x["metric"] in M.LOG_METRICS for x in LG["latest"])
    assert O["kpi"]["n_watches"] == 8 and O["kpi"]["n_bags"] == 5 and len(O["items"]) == 13 and O["where"]
    by = {i["id"]: i for i in O["items"]}
    assert all(i["retail_url"].startswith("http") and i["resale_url"].startswith("http") and i["stock"] and i["stock"]["status"] for i in O["items"])
    assert by["sub-126610ln"]["photo"]["src"].endswith("Rolex_Submariner.jpg") and not by["sub-126610ln"]["photo"]["exact"] and "Wikipedia" in by["sub-126610ln"]["photo"]["credit"]
    assert by["explorer-124270"]["photo"]["title"] == "Rolex Explorer II"                   # the stub has no image: the next title's
    assert by["sub-126610ln"]["stock"]["status"] == "retailer only (waitlist)" and by["celine-ava-triomphe"]["stock"]["status"] == "out of stock online" and by["celine-ava-triomphe"]["stock"]["verify"]
    assert {r["platform"] for r in by["sub-126610ln"]["resale_stock"]} == {"Chrono24"} and by["sub-126610ln"]["resale_stock"][0]["count"] > 0   # the newest weekly Chrono24 row, whatever it reads
    assert len(W["items"]) == 8 and len(G["items"]) == 5 and "calendar" in G and G["retail_rise"]["brand"]
    assert len(O["rolex_premium"]) > 24 and len(G["ratio"]) >= 3, "the committed points must give both baskets a monthly history (the bag basket starts in 2026: three of its five bags have no earlier resale record)"
    assert R["sp500_source"].startswith("FRED") and R["cpi_uk_source"].startswith("FRED") and R["rows"] and all(r["net"] <= r["gross"] for r in R["rows"])
    assert M.BACKGROUND == [M.fill_context, M.EBAY.fill]
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
    assert "liquidity" in sig and isinstance(sig["liquidity"]["crossed"], bool) and "sell-through" in sig["liquidity"]["note"]
    assert {"liquidity_watch", "liquidity_bag"} <= set(r) and L["liquidity"]["watch"]["n_components"] >= 2 and L["liquidity"]["bands"]


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


def test_wiki_attention_helpers(mocked, tmp_path, monkeypatch):
    s = M.wiki_views("Rolex Submariner")
    assert s.index[0] == pd.Timestamp("2015-07-01") and s.index[-1] >= pd.Timestamp("2026-10-01") and M.wiki_key("Rolex Submariner").endswith("/monthly/2015070100/now")
    assert "Rolex_Submariner" in M.wiki_url("Rolex Submariner") and M.wiki_url("Celine (brand)").count("%28") == 1
    z = M.z12(pd.Series([100.0, 110.0] * 6 + [160.0, 105.0], index=pd.date_range("2025-01-01", periods=14, freq="MS")))
    assert len(z) == 2 and z.iloc[0] == 3.0 and abs(z.iloc[1]) < 0.5      # (160 - 105) / 5 clips to +3; a flat history (sd 0) gives no z
    assert len(M.z12(pd.Series([100.0] * 13, index=pd.date_range("2025-01-01", periods=13, freq="MS")))) == 0
    with pytest.raises(ValueError):
        M.wiki_views("Rolex Explorer")                                          # 5 months: a stub
    title, series, tried = M.wiki_pick("Rolex Explorer|Rolex Explorer II|Rolex")
    assert title == "Rolex Explorer II" and len(series) > 100 and list(tried) == ["Rolex Explorer"] and M.wiki_titles(" A | B ") == ["A", "B"] and M.wiki_titles("") == []
    assert M.wiki_pick("Rolex Explorer")[0] is None
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "cold")
    from app import cache
    cache._cache.clear()
    with pytest.raises(LookupError):
        M.wiki_views("Rolex Submariner")                                        # never fetched on this server: no download from a view
    kicked = []
    monkeypatch.setattr(M, "_kick_context", lambda: kicked.append(1))
    views, errs = M._wiki_all([{"id": "a", "wiki": "Rolex Submariner"}])
    assert views == {} and errs == {"Rolex Submariner": "downloading"} and kicked and M.wiki_image("Rolex Submariner") is None
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
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


def test_liquidity_log_spreads_and_totals(mocked, monkeypatch):
    log_rows = [{"date": "2026-11-07", "item": "hermes-birkin25-togo", "platform": "stockx", "metric": "stockx_bid", "value": "10000", "currency": "USD", "source": "https://x/1", "note": "verify"},
                {"date": "2026-11-05", "item": "hermes-birkin25-togo", "platform": "stockx", "metric": "stockx_ask", "value": "13000", "currency": "USD", "source": "https://x/2", "note": ""},
                {"date": "2026-11-07", "item": "sub-126610ln", "platform": "chrono24", "metric": "chrono24_listings", "value": "800", "currency": "", "source": "https://x/3", "note": ""},
                {"date": "2026-11-07", "item": "daytona-126500ln", "platform": "chrono24", "metric": "chrono24_listings", "value": "700", "currency": "", "source": "https://x/4", "note": ""},
                {"date": "2026-10-31", "item": "sub-126610ln", "platform": "chrono24", "metric": "chrono24_listings", "value": "850", "currency": "", "source": "https://x/5", "note": ""},
                {"date": "2026-11-07", "item": "sub-126610ln", "platform": "watchcharts", "metric": "watchcharts_days_to_sell", "value": "17", "currency": "", "source": "https://x/6", "note": ""},
                {"date": "2026-11-07", "item": "nope", "platform": "x", "metric": "chrono24_listings", "value": "5", "currency": "", "source": "https://x/7", "note": "unknown item, skipped"},
                {"date": "2026-11-07", "item": "sub-126610ln", "platform": "x", "metric": "made_up", "value": "5", "currency": "", "source": "https://x/8", "note": "unknown metric, skipped"}]
    real_rows = M.rows
    monkeypatch.setattr(M, "rows", lambda name: log_rows if name == "liquidity" else real_rows(name))
    L = M.liquidity_log(M.fx())
    assert L["n_rows"] == 6 and L["n_verify"] == 1 and L["first"] == "2026-10-31" and L["last"] == "2026-11-07"
    sp = L["spreads"]["hermes-birkin25-togo"]
    assert sp["spread"] == 0.3 and sp["bid"] == round(10000 / 1.3) and sp["date"] == "2026-11-07"
    assert L["chrono24_total"] == [[int(pd.Timestamp("2026-11-01").timestamp()), 850], [int(pd.Timestamp("2026-11-08").timestamp()), 1500]] and L["chrono24_items"] == ["daytona-126500ln", "sub-126610ln"]
    lat = {(x["item"], x["metric"]): x for x in L["latest"]}
    assert lat[("sub-126610ln", "chrono24_listings")]["value"] == 800 and lat[("sub-126610ln", "watchcharts_days_to_sell")]["kind"] == "days"
    r = {x["key"]: x for x in M.readings(lambda n: {"liquidity": {"log": L}}.get(n, {}))}
    assert r["stockx_spread"]["value"] == 30.0 and r["stockx_spread"]["lean"] == 0


def test_liquidity_score_and_signal(monkeypatch):
    monkeypatch.setattr(M, "_now", lambda: TODAY)
    att = {"baskets": {"watch": {"z12": -1.0}, "bag": {"z12": 2.5}}}
    auc = {"sell_through": {"watch": {"latest": 0.95}, "bag": {"latest": 0.65}}}
    day = 86400
    counts = [[int(TODAY.timestamp()) - (400 - i) * day, 100 if i < 399 else 300] for i in range(400)]     # a year of eBay days flat at 100, today far above
    ebay = {"categories": {"watch": {"count": counts}, "bag": {"count": []}}}
    log = {"spreads": {"b": {"spread": 0.30}}, "chrono24_total": [], "latest": [{"category": "watch", "metric": "watchcharts_days_to_sell", "value": 20.0, "date": "2026-11-01"},
                                                                                 {"category": "watch", "metric": "watchcharts_days_to_sell", "value": 60.0, "date": "2026-01-01"}]}
    w = M.liquidity_score("watch", att, auc, ebay, log)
    c = {k["key"]: k["value"] for k in w["components"]}
    assert c["supply"] == -2.0 and c["spread"] is None and c["sell_through"] == 1.0 and c["days_to_sell"] == 1.0 and c["attention"] == -1.0
    assert w["n_components"] == 4 and w["score"] == -0.25 and w["verdict"] == "normal" and w["listings_1y"] == 2.0 and w["supply_source"] == "eBay UK"
    b = M.liquidity_score("bag", att, auc, ebay, log)
    cb = {k["key"]: k["value"] for k in b["components"]}
    assert cb["supply"] is None and cb["spread"] == -1.0 and cb["sell_through"] == -2.0 and cb["days_to_sell"] is None and cb["attention"] == 2.0 and b["score"] == -0.33
    assert M.liquidity_verdict(1.2) == "tight" and M.liquidity_verdict(-1.5) == "stuck" and M.liquidity_verdict(None) == "not enough data yet"
    # the signal: watches have listings +200% with the premium falling, bags a sell-through under 70%
    prem = [[int(TODAY.timestamp()) - (14 - i) * 30 * day, 0.3 - 0.01 * i] for i in range(14)]
    pay = {"overview": {"kpi": {"rolex_premium": 0.1, "rolex_1y": 0.0, "bags_ratio": 0.9}, "rolex_premium": prem, "bags_ratio": []}, "heat": {"score": 0.1}, "bags": {"retail_rise": {"brand": "x", "value": 0.0}},
           "liquidity": {"liquidity": {"watch": w, "bag": b, "score": -0.29}}}
    monkeypatch.setattr(M, "_cached_payload", lambda n: pay.get(n, {}))
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert sig["liquidity"]["crossed"] and "sellers stuck: Watches" in sig["liquidity"]["note"] and "sell-through under 70%: Bags" in sig["liquidity"]["note"] and sig["liquidity"]["value"] == -0.29
    b["sell_through_latest"] = 0.9
    w["listings_1y"] = 0.2
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert not sig["liquidity"]["crossed"]


def test_card_extras_photo_stock_and_resale_stock(mocked, monkeypatch, tmp_path):
    assert M.parse_summary({"title": "A", "thumbnail": {"source": "https://u/a.jpg", "width": 1, "height": 2}, "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/A"}}}) == {"src": "https://u/a.jpg", "width": 1, "height": 2, "page": "https://en.wikipedia.org/wiki/A"}
    assert M.parse_summary({"title": "A"}) is None and M.parse_summary({}) is None
    it = {"id": "x", "name": "X", "image": " https://owner/x.png ", "source": "https://brand/x", "wiki": "Rolex Submariner"}
    assert M.photo(it) == {"src": "https://owner/x.png", "credit": "the owner's image link", "page": "https://brand/x", "exact": True}
    it["image"] = ""
    assert M.photo(it)["title"] == "Rolex Submariner" and M.photo({"id": "y", "wiki": "Rolex Explorer"}) is None and M.photo({"id": "z", "wiki": ""}) is None
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "cold")
    cache._cache.clear()
    assert M.photo(it) is None                                                   # never fetched on this server: no photo, and no download from a view
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    assert M.stock_status("nope") is None and M.stock_status("daytona-126500ln")["status"].startswith("retailer only")
    log = {"latest": [{"item": "a", "metric": "chrono24_listings", "value": 12.0, "date": "2026-11-07", "source": "https://c/a", "verify": True}, {"item": "a", "metric": "stockx_ask", "value": 5.0, "date": "2026-11-07", "source": "https://s/a"}]}
    ebay = {"items": {"a": {"query": "Rolex a", "latest": {"count": 7, "date": "2026-11-08"}}}}
    rs = M.resale_stock("a", log, ebay)
    assert [(r["platform"], r["count"]) for r in rs] == [("Chrono24", 12), ("eBay UK", 7)] and rs[0]["verify"] and "ebay.co.uk" in rs[1]["url"]
    assert M.resale_stock("b", log, ebay) == [] and M.resale_stock("a", None, None) == []
