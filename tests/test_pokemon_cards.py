"""Pokémon Card Market on fixtures (no network): the PriceCharting, pokemontcg.io, TCGplayer and FX parsers, the chain-linked index,
rolling z-scores, the composite, every tab payload, READINGS and the seed files. smoke_patch() points the module's fetchers at the same
fixtures for scripts/smoke.py."""
import json
import math

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import pokemon_cards as M

TODAY = pd.Timestamp("2026-10-26")


# ------------------------------------------------------------------ fixtures
def _path(t: pd.Timestamp, seg: str, k: int) -> float:
    """A price path with a 2021 bubble, a 2022-23 slump and a 2025-26 run-up; vintage, modern and sealed differ a little."""
    y = t.year + (t.month - 1) / 12
    trend = 1 + 0.08 * (y - 2015)
    bubble = 1.2 * math.exp(-((y - 2021.2) ** 2) / 0.15) + 0.7 * math.exp(-((y - 2026.6) ** 2) / 0.4)
    wiggle = 0.03 * math.sin(k + y * 3)
    base = {"vintage": 300, "modern": 120, "sealed": 200}[seg] * (1 + 0.15 * k)
    return base * (trend + bubble + wiggle) * (1.1 if seg == "sealed" else 1)


def _months(item):
    start = max(pd.Timestamp("2015-01-01"), pd.Timestamp(item["date"]).to_period("M").to_timestamp())
    return pd.date_range(start, TODAY, freq="MS")


def pc_html(item, k=0):
    ms = _months(item)
    used = [[int(t.timestamp() * 1000), int(_path(t, item["segment"], k) * 100)] for t in ms]
    psa = [[a, int(v * (4 + 2 * math.exp(-((t.year - 2021) ** 2)))) if item["segment"] != "sealed" else 0] for (a, v), t in zip(used, ms)]
    data = {"used": used, "cib": [[a, 0] for a, _ in used], "graded": [[a, v * 2] for a, v in used], "manualonly": psa}
    return f"<html><script>VGPC.product = {{id: 1}};\nVGPC.chart_data = {json.dumps(data)};\nVGPC.other = 1;</script></html>"


def ptcg_json():
    data = []
    for k, i in enumerate(M.basket()):
        if not i.get("ptcg_id"):
            continue
        usd = _path(TODAY, i["segment"], k)
        data.append({"id": i["ptcg_id"], "name": i["name"], "set": {"name": i["set"]}, "tcgplayer": {"url": f"https://prices.pokemontcg.io/tcgplayer/{i['ptcg_id']}",
                     "updatedAt": "2026/10/25", "prices": {"holofoil": {"low": usd * 0.8, "mid": usd, "market": usd}}},
                     "cardmarket": {"url": f"https://prices.pokemontcg.io/cardmarket/{i['ptcg_id']}", "updatedAt": "2026/10/25",
                                    "prices": {"trendPrice": usd * 0.9, "avg1": usd * 0.92, "avg7": usd * 0.91, "avg30": usd * 0.86, "lowPrice": usd * 0.7}}})
    return {"data": data, "page": 1, "count": len(data)}


def tcg_history(pid: int):
    weeks = pd.date_range(TODAY - pd.Timedelta(days=364), TODAY, freq="7D")
    skus = []
    for s, cond in enumerate(("Near Mint", "Lightly Played")):
        skus.append({"skuId": pid * 10 + s, "variant": "Holofoil", "condition": cond, "totalQuantitySold": str(200 - 150 * s),
                     "buckets": [{"bucketStartDate": str(w.date()), "marketPrice": f"{(50 + pid % 7) * (1 + j / 100) * (1 - 0.2 * s):.2f}",
                                  "quantitySold": str(3 + (j % 5) + (j // 10) - s), "transactionCount": "2"} for j, w in enumerate(weeks)]})
    return {"count": len(skus), "result": skus}


FX_JSON = {"amount": 1.0, "base": "USD", "date": "2026-10-23", "rates": {"EUR": 0.92, "GBP": 0.79, "JPY": 151.2, "HKD": 7.78}}


def fake_fetch(url, ttl=0, **k):
    if "pricecharting.com/game/" in url:
        items = M.basket()
        n = next((n for n, i in enumerate(items) if url.endswith(i["pricecharting"])), 0)
        return pc_html(items[n], n)
    if "api.pokemontcg.io" in url:
        return json.dumps(ptcg_json())
    if "price/history" in url:
        return json.dumps(tcg_history(int(url.split("/history/")[1].split("/")[0])))
    if "/details" in url:
        pid = int(url.split("/product/")[1].split("/")[0])
        return json.dumps({"productId": pid, "marketPrice": 55.0, "listings": 40 + pid % 9, "sellers": 20})
    if "frankfurter" in url or "er-api" in url:
        return json.dumps(FX_JSON)
    raise ConnectionError(f"fixture: no {url}")


def fake_read(url):
    try:
        return fake_fetch(url)
    except ConnectionError as e:
        raise LookupError(str(e))


def fake_http_get(url, timeout=30):
    if "prices.pokemontcg.io/tcgplayer/" in url:
        pid = 1000 + sum(map(ord, url.rsplit("/", 1)[1])) % 900
        return 200, f"https://www.tcgplayer.com/product/{pid}/x", "", ["https://tcgplayer.pxf.io/c/1/2?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F" + str(pid), f"https://www.tcgplayer.com/product/{pid}/x"]
    body = fake_fetch(url)
    return 200, url, body, [url]


def seed_log(days=60):
    """A daily log of the last `days` days: listings rising faster than prices."""
    items = M.basket()
    for d in pd.date_range(TODAY - pd.Timedelta(days=days - 1), TODAY):
        rows = []
        for k, i in enumerate(items):
            if i.get("ptcg_id"):
                rows += [(i["key"], "tcg", 100 + k + (d - TODAY).days * 0.1), (i["key"], "cm_trend", 90 + k + (d - TODAY).days * 0.05),
                         (i["key"], "listings", 40 + k + (d - TODAY).days * 0.5)]
        M.log_today(rows, str(d.date()))


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above; the fill runs once, with no pauses."""
    M.fetch = fake_fetch
    M.cached_only = fake_read
    M.http_get = fake_http_get
    M._now = lambda: TODAY
    M.PACE = 0
    seed_log()
    M.fill()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "cached_only", fake_read)
    monkeypatch.setattr(M, "http_get", fake_http_get)
    monkeypatch.setattr(M, "_now", lambda: TODAY)
    monkeypatch.setattr(M, "PACE", 0)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ parsers
def test_pricecharting_chart_parser():
    item = M.basket()[0]
    ch = M.parse_pc_chart(pc_html(item))
    assert {"used", "graded", "manualonly"} <= set(ch) and "cib" not in ch            # all-zero series dropped
    assert ch["used"].index[0] == pd.Timestamp("2015-01-01") and ch["used"].iloc[0] > 100       # cents -> dollars
    with pytest.raises(ValueError):
        M.parse_pc_chart("<html>no chart</html>")


def test_pricecharting_search_parser():
    html = '<tr><td><a href="/game/pokemon-base-set/charizard-4">Charizard #4</a></td></tr><a href="/game/pokemon-jungle/x-1">'
    assert M.parse_pc_search(html) == "pokemon-base-set/charizard-4"
    assert M.parse_pc_search('<a href="https://www.pricecharting.com/game/pokemon-fossil/gengar-5?q=1">') == "pokemon-fossil/gengar-5"
    assert M.parse_pc_search("<p>nothing</p>") is None


def test_ptcg_parser_picks_the_variant():
    j = {"data": [{"id": "base1-4", "name": "Charizard", "set": {"name": "Base"}, "tcgplayer": {"url": "u", "prices": {
        "1stEditionHolofoil": {"market": 9000}, "unlimitedHolofoil": {"market": 400, "mid": 420}}}, "cardmarket": {"prices": {"trendPrice": 350.5, "avg7": 340, "avg30": 300}}},
        {"id": "x-1", "name": "Nothing", "tcgplayer": {}, "cardmarket": {}}]}
    p = M.parse_ptcg(j)
    assert p["base1-4"]["tcg"] == 400 and p["base1-4"]["tcg_variant"] == "unlimitedHolofoil" and p["base1-4"]["cm_trend"] == 350.5
    assert M.parse_ptcg(j, {"base1-4": "1stEditionHolofoil"})["base1-4"]["tcg"] == 9000
    assert p["x-1"]["tcg"] is None and p["x-1"]["cm_trend"] is None


def test_tcgplayer_parsers():
    h = M.parse_tcg_history(tcg_history(42382))
    assert len(h) == 53 and h["qty"].iloc[0] == 3 + 2 and h["price"].iloc[0] == pytest.approx((50 + 42382 % 7))      # NM sold most
    with pytest.raises(ValueError):
        M.parse_tcg_history({"result": []})
    assert M.parse_tcg_details({"listings": 12, "sellers": "5", "marketPrice": 3.5}) == {"listings": 12, "sellers": 5, "market": 3.5, "median": None, "lowest": None}
    assert M.parse_tcg_details({"results": [{"totalListings": 7}]})["listings"] == 7


def test_fx_parser():
    assert M.parse_fx(FX_JSON)["GBP"] == 0.79
    assert M.parse_fx({"result": "success", "rates": {"EUR": 0.9, "GBP": 0.8}, "time_last_update_utc": "Mon, 26 Oct 2026"})["EUR"] == 0.9
    with pytest.raises(ValueError):
        M.parse_fx({"rates": {}})


# ------------------------------------------------------------------ the maths
def test_chain_index_ignores_items_joining():
    idx = pd.date_range("2020-01-01", periods=4, freq="MS")
    df = pd.DataFrame({"a": [10, 11, 12.1, 13.31], "b": [20, 22, 24.2, 26.62], "c": [float("nan"), float("nan"), 500, 550]}, index=idx)
    s = M.chain_index(df, min_items=2)
    assert s.iloc[0] == 100 and s.iloc[-1] == pytest.approx(133.1, rel=1e-6)          # c joining at 500 did not jump the index
    assert M.chain_index(df, min_items=5).empty


def test_rolling_z():
    s = pd.Series([1.0] * 20 + [5.0], index=pd.date_range("2020-01-01", periods=21, freq="MS"))
    z = M.rolling_z(s)
    assert z.index[0] == pd.Timestamp("2020-12-01") and z.iloc[0] == 0 and z.iloc[-1] == 3        # clipped
    assert M.rolling_z(s.iloc[:5]).empty


def test_verdict_and_lean():
    assert M.verdict(1.2) == "overheated" and M.verdict(0.6) == "running hot" and M.verdict(0) == "neutral" and M.verdict(-0.7) == "cooling" and M.verdict(-1.5) == "cold"
    assert M.lean(0.6) == 1 and M.lean(-0.6) == -1 and M.lean(0.1) == 0 and M.lean(None) == 0


def test_daily_log_once_a_day(mocked):
    assert M.log_today([("a", "tcg", 1.0), ("a", "cm_trend", None)], "2026-10-25") == 1
    assert M.log_today([("a", "tcg", 2.0)], "2026-10-25") == 0
    M.log_today([("a", "tcg", 3.0)], "2026-10-26")
    assert M.daily_log()["tcg"]["a"].tolist() == [1.0, 3.0]


# ------------------------------------------------------------------ the fill and every payload
def test_fill_resolves_and_logs(mocked):
    done = M.fill()
    assert done["fx"] == "ok" and done["pokemontcg.io"] == "ok"
    assert all(v == "ok" for k, v in done.items() if k.startswith(("pc ", "tcg ")))
    res = M._resolved()
    assert res["base-charizard"]["pc_how"] == "basket path" and res["base-charizard"]["tcg"]
    assert "tcg listings base-charizard" in done and not any(k.startswith("tcg") and "box" in k for k in done)     # sealed has no ptcg id
    assert "listings" in M.daily_log()


def test_payloads(mocked):
    seed_log()
    M.fill()
    for name in M.ENDPOINTS:
        if name != "layout":
            B.json_safe(M.ENDPOINTS[name]())
    H = M.ENDPOINTS["heat"]()
    assert H["score"] is not None and -2 <= H["score"] <= 2 and H["verdict"] != "not enough data yet" and H["history"]
    keys = {c["key"]: c for c in H["signals"]}
    for k in ("mom30", "mom90", "breadth", "sealed_msrp", "psa10_ratio", "sales"):
        assert keys[k]["status"] == "ok", (k, keys[k])
    assert keys["psa_volume"]["status"] == "no data yet" and H["drivers"]
    P = M.ENDPOINTS["prices"]()
    assert set(P["segments"]) == {n for _, n in M.SEGMENTS} and len(P["table"]) == len(M.basket()) and P["kpi"]["m12"] is not None and P["daily"]
    assert all(r["src"] == "PriceCharting" for r in P["table"])
    O = M.ENDPOINTS["overheat"]()
    assert O["new_set"] and all(o["multiple"] > 0 for o in O["new_set"]) and O["news"]
    C = M.ENDPOINTS["cooldown"]()
    assert C["known"] >= 5 and {c["key"] for c in C["checks"]} >= {"momentum_rollover", "overhang", "reprints"}
    assert next(c for c in C["checks"] if c["key"] == "overhang")["met"] is True          # fixture listings rise much faster than units sold
    G = M.ENDPOINTS["grading"]()
    assert G["ratio"] and G["table"] and G["table"][0]["ratio"] > 1
    R = M.ENDPOINTS["regions"]()
    assert R["cards"] and R["fx"]["EUR"] == 0.92 and R["hottest"] and R["kpi"]["eu_vs_us"] is not None
    c = R["cards"][0]
    assert c["gbp"] == pytest.approx(c["eur"] / 0.92 * 0.79, rel=1e-3)


def test_pricecharting_missing_falls_back_to_tcgplayer(mocked, monkeypatch):
    M.fill()
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(M, "cached_only", lambda url: (_ for _ in ()).throw(LookupError("x")) if "pricecharting" in url else fake_read(url))
    s = M.item_series(M.basket()[0])
    assert s["src"] == "TCGplayer" and len(s["raw"]) >= 12
    sealed = next(i for i in M.basket() if i["segment"] == "sealed")
    assert M.item_series(sealed)["src"] is None


def test_readings_from_cached_payloads(mocked):
    seed_log()
    M.fill()
    assert M.READINGS() == []                                   # nothing cached: nothing read, nothing fetched
    for name in ("heat", "prices", "cooldown", "regions"):
        M.ENDPOINTS[name]()
    r = M.READINGS()
    tabs = {t for t, _ in M.TOPIC.tabs}
    assert {x["tab"] for x in r} <= tabs and {"heat", "overheat", "cooldown", "prices", "regions", "grading"} <= {x["tab"] for x in r}
    comp = next(x for x in r if x["key"] == "composite")
    assert comp["lean"] == M.lean(comp["value"]) and all(x["lean"] in (-1, 0, 1) for x in r)
    assert len({x["key"] for x in r}) == len(r)


def test_empty_basket_does_not_crash(mocked, monkeypatch):
    monkeypatch.setattr(M, "basket", lambda: [])
    for name in M.ENDPOINTS:
        if name != "layout":
            B.json_safe(M.ENDPOINTS[name]())
    assert M.ENDPOINTS["heat"]()["score"] is None


def test_registered_and_seed_files():
    t = topics.REGISTRY["pokemon-cards"]
    assert t.tabs[0][0] == "heat" and set(t.slow) <= set(M.ENDPOINTS)
    items = M.basket()
    assert 20 <= len(items) <= 35 and len({i["key"] for i in items}) == len(items)
    assert {i["segment"] for i in items} == {"vintage", "modern", "sealed"}
    assert all(i["msrp"] for i in items if i["segment"] == "sealed") and all(i.get("ptcg_id") for i in items if i["segment"] != "sealed")
    for name in ("basket", "events", "trends", "pop", "psa", "newset", "japan", "hk"):
        for r in M.rows(name):
            pd.Timestamp(r["date"])
            assert r.get("source"), (name, r)
    assert {r["kind"] for r in M.rows("events")} <= {"sellout", "scalping", "limit", "reprint", "restock"}


@pytest.mark.network
def test_live_sources():
    """Run by hand: pokemontcg.io and one PriceCharting page parse as the fixtures assume."""
    import requests
    j = requests.get(M.ptcg_url(M.basket()[:2]), headers=B.UA, timeout=60).json()
    assert M.parse_ptcg(j)
    html = requests.get(M.pc_url(M.basket()[0]), headers=B.UA, timeout=60).text
    assert len(M.parse_pc_chart(html)["used"]) > 24
