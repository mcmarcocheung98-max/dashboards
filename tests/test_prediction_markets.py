"""Prediction Markets (/prediction-markets): parsers, keyword matching, the watchlist across venues, the daily log, calibration, every tab
payload and READINGS on fixtures shaped like each source (layouts read from the live APIs on 2026-10-26). Live checks are marked network.
smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import csv
import json

import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import prediction_markets as M

NOW = pd.Timestamp.now("UTC").tz_localize(None).normalize()
DAYS = 86400


# ------------------------------------------------------------------ fixtures in each source's own layout
def _mk(i, q, label, yes, d1=0.01, d7=0.03, vol=2e6, vol24=1e5, liq=5e4, end=None, closed=False):
    end = end or str((NOW + pd.Timedelta(days=60)).date())
    return {"id": str(i), "question": q, "groupItemTitle": label, "outcomes": '["Yes", "No"]', "outcomePrices": json.dumps([str(yes), str(round(1 - yes, 4))]),
            "clobTokenIds": json.dumps([f"tok{i}", f"no{i}"]), "volume": str(vol), "volumeNum": vol, "volume24hr": vol24, "volume1wk": vol24 * 5,
            "liquidity": str(liq), "liquidityNum": liq, "oneDayPriceChange": d1, "oneWeekPriceChange": d7, "endDate": end + "T00:00:00Z",
            "active": True, "closed": closed}


def _ev(slug, title, tags, markets, vol24=None):
    return {"id": slug, "slug": slug, "title": title, "endDate": markets[0]["endDate"], "volume": sum(m["volumeNum"] for m in markets) * 1.0,
            "volume24hr": vol24 if vol24 is not None else sum(m["volume24hr"] for m in markets), "liquidity": sum(m["liquidityNum"] for m in markets),
            "tags": [{"id": t, "slug": t, "label": t.title()} for t in tags], "markets": markets}


def poly_events() -> list:
    soon = str((NOW + pd.Timedelta(days=2)).date())
    dec = str((NOW + pd.Timedelta(days=44)).date())
    return [
        _ev("fed-decision-in-october-1", "Fed Decision in October?", ["economy", "fed-rates", "fed"], [
            _mk(1, "Will there be no change in Fed interest rates after the October 2026 meeting?", "No change", 0.92, d1=-0.02, d7=0.08, vol=2.2e7, vol24=3.9e6, liq=8e5, end=soon),
            _mk(2, "Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?", "25 bps decrease", 0.07, d1=0.02, vol=1.5e7, vol24=2e6, end=soon),
            _mk(3, "old", "old", 0.5, closed=True)]),
        _ev("fed-decision-in-december-1", "Fed Decision in December?", ["economy", "fed-rates"], [
            _mk(4, "Will the Fed decrease interest rates by 25 bps after the December 2026 meeting?", "25 bps decrease", 0.55, d1=0.06, d7=0.12, vol=6e6, vol24=4e5, end=dec),
            _mk(5, "Will there be no change in Fed interest rates after the December 2026 meeting?", "No change", 0.40, d1=-0.06, vol=5e6, vol24=3e5, end=dec)]),
        _ev("us-cpi-sept", "September CPI YoY", ["economy", "inflation", "cpi"], [_mk(6, "Will CPI YoY be above 3.0% in September?", "Above 3.0%", 0.33, end=soon)]),
        _ev("us-recession-2026", "US recession in 2026?", ["economy", "recession"], [_mk(7, "US recession in 2026?", "US recession in 2026?", 0.12, d1=-0.01)]),
        _ev("house-2026", "Which party will win the House in 2026?", ["politics", "midterms", "us-politics"], [
            _mk(8, "Will the Democratic Party win the House in 2026?", "Democratic", 0.78, d1=0.03, d7=-0.04, vol=4e7, vol24=2.5e6, liq=2e6),
            _mk(9, "Will the Republican Party win the House in 2026?", "Republican", 0.22, d1=-0.03, vol=3e7, vol24=2e6)]),
        _ev("senate-2026", "Which party will win the Senate in 2026?", ["politics", "midterms", "us-politics"], [
            _mk(10, "Will the Republican Party win the Senate in 2026?", "Republican", 0.70, d1=-0.04, vol=2.5e7, vol24=1.8e6)]),
        _ev("starmer-out-2026", "Starmer out in 2026?", ["politics", "uk", "uk-politics"], [_mk(11, "Starmer out as PM in 2026?", "Starmer out in 2026?", 0.31, d1=0.05, vol=3e6)]),
        _ev("boe-november", "Bank of England decision in November?", ["economy", "uk", "boe"], [
            _mk(12, "Will the Bank of England cut rates in November?", "Cut", 0.62, d1=0.04, end=str((NOW + pd.Timedelta(days=10)).date())),
            _mk(13, "Will the Bank of England hold rates in November?", "Hold", 0.37, end=str((NOW + pd.Timedelta(days=10)).date()))]),
        _ev("hsi-2026", "Hang Seng above 30,000 by year end?", ["hang-seng", "china", "economy"], [_mk(14, "Hang Seng above 30,000 on December 31?", "HSI", 0.28, vol=4e5, vol24=3e4)]),
        _ev("pboc-cut", "PBoC rate cut in 2026?", ["china", "pboc", "economy"], [_mk(15, "Will the PBoC cut rates by December 31?", "PBoC cut", 0.45, vol=2e5, vol24=2e4)]),
        _ev("china-taiwan-2026", "China invades Taiwan in 2026?", ["geopolitics", "china", "taiwan"], [_mk(16, "Will China invade Taiwan in 2026?", "China invades Taiwan", 0.04, d1=-0.005, vol=9e6)]),
        _ev("hk-election", "Hong Kong chief executive 2027?", ["hong-kong", "politics"], [_mk(26, "Will John Lee serve a second term?", "John Lee", 0.6, vol=1e5, vol24=5e3)]),
        _ev("btc-150k", "Bitcoin to $150k in 2026?", ["crypto", "bitcoin"], [_mk(17, "Will Bitcoin reach $150k in 2026?", "150k", 0.18, d1=-0.07, d7=-0.15, vol=1.2e7, vol24=9e5)]),
        _ev("best-ai-model", "Which company has the best AI model end of 2026?", ["ai", "tech"], [
            _mk(18, "Will OpenAI have the best AI model at the end of 2026?", "OpenAI", 0.35, d1=0.08, vol=8e6, vol24=6e5),
            _mk(19, "Will Google have the best AI model at the end of 2026?", "Google", 0.45, d1=-0.08, vol=7e6, vol24=5e5)]),
        _ev("ukraine-ceasefire", "Russia x Ukraine ceasefire in 2026?", ["geopolitics", "ukraine", "russia"], [_mk(20, "Russia x Ukraine ceasefire in 2026?", "ceasefire", 0.09, d1=-0.02, vol=3e7)]),
        _ev("world-series", "World Series Champion 2026", ["sports", "mlb", "baseball"], [
            _mk(21, "Will the Dodgers win the 2026 World Series?", "Dodgers", 0.58, d1=0.11, d7=0.2, vol=5e7, vol24=6e6, liq=1e6),
            _mk(22, "Will the Yankees win the 2026 World Series?", "Yankees", 0.42, d1=-0.11, vol=4e7, vol24=5e6)]),
        _ev("thin-market", "Thin market", ["sports"], [_mk(23, "A market nobody trades", "x", 0.5, d1=0.4, d7=0.4, vol=100, vol24=10, liq=10)]),
        _ev("eth-5k", "Ethereum above $5k?", ["crypto", "ethereum"], [_mk(24, "Ethereum above $5k on Dec 31?", "5k", 0.2, d1=-0.03, vol=3e6, vol24=2e5)]),
        _ev("no-tags", "Something else", [], [_mk(25, "Will something else happen?", "x", 0.3, vol24=4e4)]),
    ]


def clob_json(token: str) -> dict:
    if token.startswith("ctok"):                       # a resolved market (closed_markets): daily prices up to its close
        k = int(token.replace("ctok", ""))
        b = NOW - pd.Timedelta(days=5 + 4 * k)
        days = pd.date_range(b - pd.Timedelta(days=60), b, freq="1D")
        final = 1.0 if k % 3 else 0.0
        return {"history": [{"t": int(t.timestamp()), "p": round((0.35 + 0.4 * final) + (final - 0.5) * 0.4 * i / len(days), 3)} for i, t in enumerate(days)]}
    days = pd.date_range(NOW - pd.Timedelta(days=150), NOW, freq="1D")
    seed = sum(map(ord, token)) % 7
    return {"history": [{"t": int(t.timestamp()) + 3600, "p": round(0.3 + 0.05 * seed + 0.2 * (i / len(days)), 3)} for i, t in enumerate(days)]}


def closed_markets() -> list:
    out = []
    for k in range(1, 61):
        t = NOW - pd.Timedelta(days=5 + 4 * k)
        final = 1 if k % 3 else 0
        out.append({"id": f"c{k}", "question": f"Resolved question {k}?", "outcomes": '["Yes", "No"]', "outcomePrices": json.dumps([str(final), str(1 - final)]),
                    "clobTokenIds": json.dumps([f"ctok{k}", f"cno{k}"]), "volumeNum": 1e5 * k, "closedTime": t.strftime("%Y-%m-%d %H:%M:%S+00"),
                    "events": [{"tags": [{"slug": ["politics", "crypto", "sports"][k % 3]}]}]})
    out.append({"id": "multi", "question": "Three outcomes", "outcomes": '["A", "B", "C"]', "outcomePrices": '["1", "0", "0"]', "clobTokenIds": '["a", "b", "c"]',
                "volumeNum": 1e7, "closedTime": "2026-09-01 00:00:00+00"})
    out.append({"id": "void", "question": "Split at 50-50", "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]', "clobTokenIds": '["v", "w"]',
                "volumeNum": 1e7, "closedTime": "2026-09-01 00:00:00+00"})
    return out


def closed_events() -> list:
    """Closed Gamma events (the accuracy job's source): each event's tags, then its resolved markets."""
    ms = closed_markets()
    cats = {"politics": "politics", "crypto": "crypto", "sports": "sports"}
    out = []
    for slug in cats:
        group = [m for m in ms if (m.get("events") or [{"tags": [{"slug": "x"}]}])[0]["tags"][0]["slug"] == slug]
        out.append({"slug": f"closed-{slug}", "title": slug, "tags": [{"slug": slug}], "markets": [{k: v for k, v in m.items() if k != "events"} for m in group]})
    out.append({"slug": "closed-other", "title": "other", "tags": [], "markets": [m for m in ms if not m.get("events")]})
    return out


def kalshi_json(series: str) -> dict:
    def mk(t, sub, price, prev, vol, close):
        return {"ticker": t, "event_ticker": t.rsplit("-", 1)[0], "title": f"{series} {sub}", "yes_sub_title": sub, "status": "active",
                "last_price_dollars": f"{price:.4f}", "previous_price_dollars": f"{prev:.4f}", "yes_bid_dollars": f"{price - 0.01:.4f}",
                "yes_ask_dollars": f"{price + 0.01:.4f}", "volume_fp": f"{vol:.2f}", "volume_24h_fp": "100.00", "open_interest_fp": "50.00", "close_time": close + "T18:59:00Z"}
    soon, later = str((NOW + pd.Timedelta(days=2)).date()), str((NOW + pd.Timedelta(days=44)).date())
    if series == "KXFEDDECISION":
        return {"markets": [mk("KXFEDDECISION-26OCT-H0", "Hold", 0.90, 0.92, 5e6, soon), mk("KXFEDDECISION-26OCT-C25", "Cut 25bps", 0.09, 0.07, 3e6, soon),
                            mk("KXFEDDECISION-26DEC-C25", "Cut 25bps (December 2026)", 0.52, 0.47, 2e6, later), mk("KXFEDDECISION-26DEC-H0", "Hold (December)", 0.45, 0.5, 1e6, later)],
                "cursor": ""}
    if series == "CONTROLH":
        return {"markets": [mk("CONTROLH-2026-D", "Democrats", 0.75, 0.74, 9e6, "2026-11-04"), mk("CONTROLH-2026-R", "Republicans", 0.25, 0.26, 7e6, "2026-11-04")]}
    if series == "KXBTCMAXY":
        return {"markets": [mk("KXBTCMAXY-26-150", "Above $150,000", 0.15, 0.2, 4e5, "2026-12-31"), {"ticker": "dead", "status": "finalized"}]}
    return {"markets": [], "cursor": ""}


def manifold_json(term: str) -> list:
    base = {"outcomeType": "BINARY", "isResolved": False, "volume": 5000.0, "totalLiquidity": 500, "uniqueBettorCount": 40, "closeTime": int((NOW + pd.Timedelta(days=60)).timestamp() * 1000)}
    t = term.lower()
    if "house" in t:
        return [{**base, "id": "m1", "question": "Will Democrats win the House in 2026?", "probability": 0.81, "url": "https://manifold.markets/x/house"},
                {**base, "id": "m0", "question": "Which party wins the House?", "outcomeType": "MULTIPLE_CHOICE"}]
    if "december" in t:
        return [{**base, "id": "m2", "question": "Will the Fed cut at its December 2026 meeting?", "probability": 0.6, "url": "https://manifold.markets/x/dec"}]
    if "taiwan" in t:
        return [{**base, "id": "m3", "question": "Will China invade Taiwan before 2027?", "probability": 0.03, "url": "https://manifold.markets/x/tw"}]
    if "bitcoin" in t:
        return [{**base, "id": "m4", "question": "Bitcoin above 150k in 2026?", "probability": 0.12, "url": "https://manifold.markets/x/btc", "isResolved": True},
                {**base, "id": "m5", "question": "Bitcoin to 150k by end of 2026?", "probability": 0.14, "url": "https://manifold.markets/x/btc2"}]
    return []


def predictit_json() -> dict:
    return {"markets": [
        {"id": 1, "name": "Which party will win the 2026 U.S. House election?", "url": "https://www.predictit.org/markets/detail/1", "status": "Open",
         "contracts": [{"id": 11, "name": "Democratic", "status": "Open", "lastTradePrice": 0.74, "lastClosePrice": 0.73},
                       {"id": 12, "name": "Republican", "status": "Open", "lastTradePrice": 0.27, "lastClosePrice": 0.28}]},
        {"id": 2, "name": "Which party will win the 2026 U.S. Senate election?", "url": "https://www.predictit.org/markets/detail/2", "status": "Open",
         "contracts": [{"id": 21, "name": "Republican", "status": "Open", "lastTradePrice": 0.66, "lastClosePrice": 0.67},
                       {"id": 22, "name": "Democratic", "status": "Open", "lastTradePrice": 0.0, "lastClosePrice": None}]},
        {"id": 3, "name": "Closed market", "status": "Closed", "contracts": [{"name": "x", "lastTradePrice": 0.5}]}]}


def fake_fetch_json(url, ttl=0, **k):
    if "gamma-api.polymarket.com/events" in url and "closed=true" in url:
        return closed_events() if "offset=0" in url else []
    if "gamma-api.polymarket.com/events" in url:
        evs = poly_events()
        if "tag_slug=" in url:
            tag = url.split("tag_slug=")[1].split("&")[0]
            return [e for e in evs if any(t["slug"] == tag for t in e["tags"])]
        off = int(url.split("offset=")[1].split("&")[0])
        return evs if off == 0 else []
    if "prices-history" in url:
        assert "startTs=" not in url                   # Polymarket answers 400 to a 40-day window
        return clob_json(url.split("market=")[1].split("&")[0])
    if "kalshi.com" in url:
        return kalshi_json(url.split("series_ticker=")[1].split("&")[0])
    if "manifold.markets" in url:
        from urllib.parse import unquote
        return manifold_json(unquote(url.split("term=")[1].split("&")[0]))
    if "predictit.org" in url:
        return predictit_json()
    raise ConnectionError(f"fixture: no JSON for {url}")


def seed_log(days: int = 75) -> None:
    """A log as the background job would have written it over the last `days` days, so the time charts have a history."""
    f = M._log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    rows = [M.LOG_FIELDS]
    for i, t in enumerate(pd.date_range(NOW - pd.Timedelta(days=days), NOW - pd.Timedelta(days=1), freq="D")):
        d = str(t.date())
        for j, key in enumerate(("fed_next", "fed_dec_cut", "house_2026", "senate_2026", "btc_150k", "taiwan")):
            p = 0.3 + 0.05 * j + 0.002 * i
            rows += [[d, key, "poly", round(p, 4)], [d, key, "kalshi", round(p - 0.02, 4)], [d, key, "vol", 1e6 * (j + 1) + 2e4 * i * (j + 1)], [d, key, "liq", 5e4 + 100 * i]]
            if key in ("house_2026", "taiwan"):
                rows += [[d, key, "manifold", round(p + 0.03, 4)], [d, key, "predictit", round(p - 0.01, 4)]]
        for c, v in (("politics", 5e6), ("sports", 9e6), ("macro", 4e6), ("crypto", 3e6), ("geo", 1e6), ("ai", 8e5)):
            rows += [[d, f"cat:{c}", "vol24", v * (1 + 0.01 * i)], [d, f"cat:{c}", "volume", v * 30], [d, f"cat:{c}", "liq", v / 5]]
    with f.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


FIXTURE_WATCHLIST = """\
date,key,label,category,region,polymarket,pick,kalshi,manifold,predictit,source,note
2026-10-26,fed_next,Fed: no change at the next FOMC meeting,macro,US,fed_decision no_change,soonest,KXFEDDECISION:hold/maintain,,,https://polymarket.com/event/fed-decision-in-october-20260617190323537,Polymarket keywords checked against the Gamma API on 2026-10-26; Kalshi subtitle wording verify
2026-10-26,fed_dec_cut,Fed: a 25 bp cut in December,macro,US,fed_decision december 25_bp decrease/cut,volume,KXFEDDECISION:december cut 25,fed december 2026:december_meeting/december_2026_meeting cut,,https://polymarket.com/,verify: keywords from memory; check on the Markets tab that the matched question is the December meeting
2026-10-26,us_cpi,US CPI: the most traded CPI question,macro,US,cpi !china !uk !euro,soonest,,,,https://polymarket.com/,verify: keywords from memory; on 2026-10-26 a bare 'cpi' matched China's CPI. CPI markets are buckets (2.6% in October; above 3.9% in November) that differ by venue; so no cross-venue comparison (Kalshi KXCPIYOY dropped)
2026-10-26,us_recession,US recession in 2026,macro,US,recession 2026,volume,KXRECSSNBER:recession,us recession 2026:recession 2026,recession 2026,https://polymarket.com/,verify: keywords and Kalshi series ticker KXRECSSNBER from memory
2026-10-26,house_2026,Democrats win the House in the 2026 midterms,politics,US,house 2026 democrat,volume,CONTROLH:2026 democrat/2026-d,democrats win the house 2026:house democrat,house 2026 democrat,https://www.predictit.org/,verify: keywords from memory; Kalshi series CONTROLH answers from Railway (2026-10-26) and also lists 2028, hence the year
2026-10-26,senate_2026,Republicans keep the Senate in the 2026 midterms,politics,US,senate 2026 republican !balance !house,volume,CONTROLS:2026 republican/2026-r,republicans senate 2026:senate republican,senate 2026 republican,https://www.predictit.org/,verify: keywords from memory; Kalshi series CONTROLS answers from Railway (2026-10-26) and also lists 2028, hence the year; on 2026-10-26 Polymarket's 'Balance of Power: R Senate, R House' combination matched until !balance
2026-10-26,uk_starmer,Keir Starmer out as Prime Minister,politics,UK,starmer out/leave/resign,volume,,starmer:starmer out/leave/resign/prime_minister !if,starmer,https://polymarket.com/,verify: keywords from memory; no Polymarket match on 2026-10-26; conditional Manifold questions ('If Labour wins…') excluded
2026-10-26,uk_boe,Bank of England: the next rate decision,macro,UK,bank_of_england/boe,soonest,KXBOE:cut/hold,,,https://polymarket.com/,verify: keywords from memory (on 2026-10-26 'boe' inside 'Nijboer' matched a tennis match before keywords had to start a word); Kalshi series KXBOE returned no markets on 2026-10-26; Manifold dropped (its only open question was a different one: a rate rise in 2026)
2026-10-26,hk_hsi,Hang Seng Index: the most traded question,macro,HK,hang_seng,volume,,hang seng:hang_seng,,https://polymarket.com/,verify: keywords from memory ('hsi' matched 'Kuo Hsi' on 2026-10-26, so it is gone); may have no listed market
2026-10-26,cn_pboc,PBoC: rate cut,macro,HK,pboc/people's_bank/china_rate/china_interest,volume,,pboc:pboc/china,,https://polymarket.com/,verify: keywords from memory; may have no listed market
2026-10-26,taiwan,China invades or blockades Taiwan,geo,HK,china taiwan invade/invasion/blockade,volume,,china invade taiwan:taiwan 2026 !2027 !if,taiwan,https://polymarket.com/,verify: keywords from memory; conditional Manifold questions ('…if China invades') excluded after one matched on 2026-10-26
2026-10-26,btc_150k,Bitcoin reaches $150k,crypto,,bitcoin 150/150k/150_000/150000,volume,KXBTCMAXY:150,bitcoin 150k:bitcoin 150,,https://polymarket.com/,verify: keywords and Kalshi series ticker KXBTCMAXY from memory
2026-10-26,ai_model,Best AI model: the most traded question,ai,,best_ai/top_ai/ai_model,volume,,best ai model:best_ai,,https://polymarket.com/,verify: keywords from memory
2026-10-26,ukraine,Russia-Ukraine ceasefire,geo,,russia ukraine ceasefire,volume,,ukraine ceasefire:ceasefire 2026 !if,ukraine ceasefire,https://polymarket.com/,verify: keywords from memory
2026-10-26,world_series,World Series: the most traded team,sports,,world_series,volume,,,,https://polymarket.com/,verify: keywords from memory; the World Series is played in late October
"""


def fixture_watchlist() -> list[dict]:
    """The watchlist the fixture markets above were built for (the live list in data/prediction-markets/ changes as questions resolve)."""
    import io
    return [r for r in csv.DictReader(io.StringIO(FIXTURE_WATCHLIST)) if r.get("key")]


def smoke_patch() -> None:
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above, with a log and a calibration sample."""
    import tempfile
    from pathlib import Path
    own = Path(tempfile.mkdtemp())          # this dashboard's files stay put if another smoke_patch() moves the shared SNAP_DIR
    M._log_file = lambda: own / "daily.csv"
    M._acc_file = lambda: own / "resolved.json"
    M.fetch_json = fake_fetch_json
    M.watchlist = fixture_watchlist
    M.PACE = 0
    seed_log()
    M.fill_accuracy()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(M, "PACE", 0)
    monkeypatch.setattr(M, "watchlist", fixture_watchlist)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()


# ------------------------------------------------------------------ parsers and helpers
def test_poly_parser_keeps_open_markets_with_categories():
    evs, mks = M.parse_poly_events(poly_events())
    assert "3" not in {m["id"] for m in mks}                                   # closed market dropped
    fed = next(m for m in mks if m["id"] == "1")
    assert fed["yes"] == 0.92 and fed["d1"] == -0.02 and fed["cat"] == "macro" and fed["token"] == "tok1" and fed["two"]
    assert fed["url"] == "https://polymarket.com/event/fed-decision-in-october-1"
    cats = {e["slug"]: e["cat"] for e in evs}
    assert cats["world-series"] == "sports" and cats["btc-150k"] == "crypto" and cats["china-taiwan-2026"] == "geo"
    assert cats["house-2026"] == "politics" and cats["best-ai-model"] == "ai" and cats["no-tags"] == "other"
    assert M.parse_poly_events([{"title": "bad", "markets": [{"outcomes": '["Yes","No"]', "outcomePrices": '["x"]'}]}, "junk"]) == ([], [])


def test_keyword_matching():
    assert M.matches("Fed Decision in October? No change", "fed_decision no_change")
    assert M.matches("Will the Fed cut", "hike/cut fed")
    assert not M.matches("Fed Decision in October? 25 bps decrease", "fed_decision no_change")
    assert not M.matches("anything", "")
    assert not M.matches("Guayaquil: Ryan Nijboer vs Lorenzo Claverie", "bank_of_england/boe")      # live false match, 2026-10-26
    assert M.matches("Will the Democratic Party win?", "democrat") and M.matches("CONTROLH-2026-D", "2026-d")
    assert not M.matches("Will China's CPI rise?", "cpi !china") and M.matches("US CPI above 3%?", "cpi !china")
    assert not M.matches("x", "!china")                                                  # exclusions alone match nothing


def test_history_kalshi_manifold_predictit_parsers():
    h = M.parse_history({"history": [{"t": 1792454429, "p": 0.845}, {"t": 1792454500, "p": 0.85}, {"t": 1792540831, "p": 0.865}]})
    assert len(h) == 2 and h.iloc[0] == 0.85                                   # last point of each day
    k = M.parse_kalshi(kalshi_json("KXBTCMAXY"))
    assert len(k) == 1 and k[0]["yes"] == 0.15 and k[0]["prev"] == 0.2 and k[0]["url"] == "https://kalshi.com/markets/kxbtcmaxy"
    mid = M.parse_kalshi({"markets": [{"ticker": "A-1", "event_ticker": "A", "status": "active", "last_price_dollars": "0", "yes_bid_dollars": "0.30", "yes_ask_dollars": "0.40"}]})
    assert mid[0]["yes"] == 0.35
    mf = M.parse_manifold(manifold_json("bitcoin"))
    assert [m["id"] for m in mf] == ["m5"]                                     # resolved and multiple-choice markets dropped
    pi = M.parse_predictit(predictit_json())
    assert {p["title"] for p in pi} == {"Which party will win the 2026 U.S. House election?: Democratic", "Which party will win the 2026 U.S. House election?: Republican",
                                       "Which party will win the 2026 U.S. Senate election?: Republican"}


def test_closed_parser_and_price_before():
    c = M.parse_closed(closed_markets())
    assert len(c) == 60 and {r["outcome"] for r in c} == {0, 1}               # three-outcome and 50-50 markets left out
    hist = [{"t": 1000 * DAYS + 3600, "p": 0.2}, {"t": 1020 * DAYS, "p": 0.4}, {"t": 1029 * DAYS, "p": 0.7}]
    assert M.price_before(hist, 1050 * DAYS, 30) == 0.4
    assert M.price_before(hist, 1036 * DAYS, 7) == 0.7
    assert M.price_before(hist, 1100 * DAYS, 30) is None                       # nothing within three days of the date


def test_calibration_buckets_and_brier():
    recs = [{"p7": 0.95, "outcome": 1}] * 9 + [{"p7": 0.95, "outcome": 0}] + [{"p7": 0.05, "outcome": 0}] * 10 + [{"p7": None, "outcome": 1}]
    c = M.calibration(recs, "p7")
    assert c["n"] == 20 and [b["n"] for b in c["buckets"]] == [10, 10]
    assert c["buckets"][1]["freq"] == 0.9 and c["buckets"][0]["freq"] == 0.0
    assert c["brier"] == pytest.approx((9 * 0.05 ** 2 + 0.95 ** 2 + 10 * 0.05 ** 2) / 20, abs=1e-4)
    assert M.calibration([], "p30") == {"n": 0, "buckets": [], "brier": None}


def test_movers_need_volume_and_take_one_per_event():
    _, mks = M.parse_poly_events(poly_events())
    m = M.movers(mks, "d1", "vol24", M.MIN_VOL24)
    assert m[0]["label"] == "Dodgers" and "x" not in {r["label"] for r in m}  # the thin market's 40-point move is left out
    assert sum(r["event"] == "World Series Champion 2026" for r in m) == 1


# ------------------------------------------------------------------ watchlist and payloads
def test_watchlist_rows_resolve_on_each_venue(mocked):
    rows, why = M.rows_now()
    by = {r["key"]: r for r in rows}
    assert not why
    assert by["fed_next"]["poly"]["title"].startswith("Will there be no change") and by["fed_next"]["poly"]["end"] == str((NOW + pd.Timedelta(days=2)).date())
    assert by["fed_next"]["kalshi"]["ticker"] == "KXFEDDECISION-26OCT-H0"     # soonest: the next meeting, not December
    assert by["fed_dec_cut"]["poly"]["yes"] == 0.55 and by["fed_dec_cut"]["kalshi"]["ticker"] == "KXFEDDECISION-26DEC-C25" and by["fed_dec_cut"]["manifold"]["yes"] == 0.6
    h = by["house_2026"]
    assert h["poly"]["yes"] == 0.78 and h["kalshi"]["yes"] == 0.75 and h["manifold"]["yes"] == 0.81 and h["predictit"]["yes"] == 0.74
    assert h["gap"] == pytest.approx(0.04) and h["gap_all"] == pytest.approx(0.07) and h["venues"] == 4
    assert "Bank of England" in by["uk_boe"]["poly"]["title"] and by["hk_hsi"]["poly"]["yes"] == 0.28 and by["cn_pboc"]["poly"]["yes"] == 0.45
    assert by["world_series"]["poly"]["yes"] == 0.58 and by["world_series"]["kalshi"] is None


def test_every_tab_payload(mocked):
    seed_log()
    M.fill_accuracy()
    for name, fn in M.ENDPOINTS.items():
        if name == "layout":
            continue
        d = fn()
        B.json_safe(d)
        assert not any(k.endswith("_error") for k in d), (name, d)
    o = M.ENDPOINTS["overview"]()
    assert o["movers24"][0]["label"] == "Dodgers" and o["top"][0]["event"] == "World Series Champion 2026"
    assert {c["key"] for c in o["cats"]} >= {"sports", "politics", "macro", "crypto", "ai", "geo"} and o["cat_log"]["Sports"]
    m = M.ENDPOINTS["markets"]()
    fed = next(i for i in m["items"] if i["key"] == "fed_next")
    assert len(fed["hist"]) > 100 and fed["volume"] and fed["liq"] and m["cites"]
    v = M.ENDPOINTS["venues"]()
    assert v["items"][0]["key"] == "house_2026" and set(v["items"][0]["log"]) == {"poly", "kalshi", "manifold", "predictit"}
    r = M.ENDPOINTS["regions"]()
    regs = {x["key"]: x for x in r["regions"]}
    assert {w["key"] for w in regs["UK"]["watch"]} == {"uk_starmer", "uk_boe"} and any(l["event"].startswith("Hong Kong") for l in regs["HK"]["listed"])
    a = M.ENDPOINTS["accuracy"]()
    assert a["n"] == 60 and a["p7"]["n"] > 40 and a["p30"]["brier"] is not None and a["by_cat"]


def test_accuracy_fill_is_paced_in_batches_and_accumulates(mocked):
    assert M.fill_accuracy(max_new=10) == {"resolved": "10 added, 10 kept"}
    assert M.fill_accuracy(max_new=100) == {"resolved": "50 added, 60 kept"}
    assert M.fill_accuracy() == {"resolved": "0 added, 60 kept"}
    recs = M.read_resolved()
    assert all(r["p7"] is not None and r["p30"] is not None for r in recs)
    assert {r["cat"] for r in recs} == {"politics", "crypto", "sports"}


def test_closed_parser_takes_events_with_tags_and_old_records_get_a_category(mocked):
    c = M.parse_closed(closed_events())
    assert len(c) == 60 and {r["cat"] for r in c} == {"politics", "crypto", "sports"}
    assert len(M.parse_closed(closed_markets())) == 60                         # a bare /markets list still parses
    M.fill_accuracy(max_new=60)
    recs = M.read_resolved()
    for r in recs:
        r["cat"] = "other"                                                      # as saved before the events source
    M._acc_file().write_text(json.dumps(recs))
    assert M.fill_accuracy() == {"resolved": "0 added, 60 kept, 60 categorised"}
    assert {r["cat"] for r in M.read_resolved()} == {"politics", "crypto", "sports"}


def test_log_today_once_a_day(mocked):
    assert M.log_today("2026-10-25")["log"].endswith("rows")
    assert M.log_today("2026-10-25") == {"log": "exists"}
    M.log_today("2026-10-26")
    log = M.read_log()
    assert len(log[("house_2026", "poly")]) == 2 and ("cat:sports", "vol24") in log and ("fed_next", "vol") in log


def test_pool_survives_a_dead_tag_and_raises_when_all_fail(mocked, monkeypatch):
    def half(url, ttl=0, **k):
        if "tag_slug" in url:
            raise ConnectionError("down")
        return fake_fetch_json(url, ttl, **k)
    monkeypatch.setattr(M, "fetch_json", half)
    assert M.poly_pool()[1]
    from app import cache
    cache._cache.clear()
    monkeypatch.setattr(M, "fetch_json", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    with pytest.raises(ConnectionError):
        M.poly_pool()
    rows, why = M.rows_now()                                                   # the watchlist still answers, with what failed
    assert why["Polymarket"] == "ConnectionError" and all(r["poly"] is None for r in rows)
    o = M.ENDPOINTS["overview"]()
    assert o["pool_error"] == "ConnectionError"


def test_readings_from_cached_payload(mocked):
    assert M.READINGS() == []                                                  # nothing cached: nothing read, nothing fetched
    M.ENDPOINTS["markets"]()
    r = M.READINGS()
    tabs = {t for t, _ in topics.REGISTRY[M.SLUG].tabs}
    assert r and all(x["tab"] in tabs for x in r)
    by = {x["key"]: x for x in r}
    assert by["p_fed_next"]["value"] == 92.0 and by["p_fed_next"]["lean"] == -1 and by["p_house_2026"]["lean"] == 1
    assert sum("biggest mover" in x.get("note", "") for x in r) == 3 and "biggest mover" in by["p_btc_150k"]["note"]


def test_registry_and_seed_file():
    t = topics.REGISTRY[M.SLUG]
    assert t.module == "prediction_markets" and {k for k, _ in t.tabs} <= set(M.ENDPOINTS)
    rows = M.watchlist()
    assert len(rows) >= 12 and all(r["source"] for r in rows)
    assert {r["region"] for r in rows} >= {"US", "UK", "HK"} and {r["category"] for r in rows} >= {k for k, _, _, _ in M.CATEGORIES}
    for r in rows:
        assert r["category"] in M.CAT_LABEL and r.get("pick") in ("", "volume", "soonest", "favourite")
        assert r["source"].startswith(("https://polymarket.com/event/", "https://kalshi.com/markets/"))     # the market page it matched
        assert "verify" not in r.get("note", "")
        assert not r.get("kalshi") or ":" in r["kalshi"]
        assert not r.get("manifold") or ":" in r["manifold"]
    retired = B.manual_rows(M.SLUG, "retired")
    assert retired and all(r["source"] and r["outcome"] for r in retired)
    assert not {r["key"] for r in rows} & {r["key"] for r in retired}         # a question is live or retired, not both


# ------------------------------------------------------------------ live (run by hand)
@pytest.mark.network
def test_live_sources_answer():
    from app import cache
    cache._cache.clear()
    evs, mks = M.poly_pool()
    assert len(mks) > 50 and any(m["d1"] is not None for m in mks)
    assert len(M.poly_history(next(m["token"] for m in mks if m["token"]))) > 1
    assert M.kalshi_series("KXFEDDECISION")
    assert M.parse_predictit(M.get_json(M.PREDICTIT))
    assert isinstance(M.manifold_search("fed"), list)


# ------------------------------------------------------------------ signals (data/signals/watchlist.json)
def test_signals_wire_every_approved_key_from_cached_data(mocked):
    approved = [r["key"] for r in json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())[M.SLUG]]
    cold = M.SIGNALS()                                                          # nothing cached: rows say so, nothing downloads
    assert [s["key"] for s in cold] == approved and not any(s["crossed"] for s in cold)
    seed_log()
    M.fill_accuracy()
    M.rows_now()
    sig = {s["key"]: s for s in M.SIGNALS()}
    assert set(sig) == set(approved)
    for s in sig.values():
        assert {"key", "label", "tab", "value", "lean", "watch", "crossed"} <= set(s) and s["tab"] in M.ENDPOINTS
        B.json_safe(s)
    assert sig["biggest_move"]["value"] == 11.0 and sig["biggest_move"]["crossed"]          # the Dodgers, +11 points
    assert sig["venue_gap"]["value"] == 3.0 and not sig["venue_gap"]["crossed"]               # December cut 55% vs 52%, House 78% vs 75%
    assert sig["volume"]["value"] > 0 and "average" in sig["volume"]["note"]
    assert sig["calibration"]["value"] is None and "being built" in sig["calibration"]["note"]  # the fixture resolves 7-8 markets a month, under 10


def test_signal_watch_points(mocked, monkeypatch):
    from app import cache
    row = lambda d1, p, k: {"key": "x", "label": "X", "poly": {"yes": p, "d1": d1, "vol24": 3e6}, "kalshi": {"yes": k} if k is not None else None}
    def run(rows, recs=(), daily=None):
        cache._cache[f"{M.SLUG}:rows"] = (1e18, (rows, {}))
        monkeypatch.setattr(M, "read_resolved", lambda: list(recs))
        monkeypatch.setattr(M, "watchlist_daily_volume", lambda log=None: daily if daily is not None else pd.Series(dtype=float))
        return {s["key"]: s for s in M.SIGNALS()}
    s = run([row(0.099, 0.5, 0.55)])
    assert not s["biggest_move"]["crossed"] and not s["venue_gap"]["crossed"]               # 9.9 points; a 5.0-point gap is not above 5
    s = run([row(-0.10, 0.5, 0.56)])
    assert s["biggest_move"]["crossed"] and s["biggest_move"]["lean"] == -1 and s["venue_gap"]["crossed"]
    days = pd.Series([1e6] * 10, index=pd.date_range("2026-10-01", periods=10))
    s = run([row(0, .5, None)], daily=days)                                                   # $3m today against $1m a day: 3x
    assert s["volume"]["crossed"] and s["volume"]["note"].startswith("3.0x")
    assert run([row(0, .5, None)], daily=days * 2)["volume"]["crossed"] is False              # 1.5x
    assert run([row(0, .5, None)], daily=days.iloc[:4])["volume"]["crossed"] is False        # under five days: no verdict
    t = lambda y, m: int(pd.Timestamp(year=y, month=m, day=15).timestamp())
    recs = lambda brier_by_month: [{"closed": t(2026, m), "outcome": 0, "p30": b ** 0.5} for m, b in brier_by_month.items() for _ in range(10)]
    assert run([], recs({6: 0.02, 7: 0.03, 8: 0.05}))["calibration"]["crossed"]              # worse in July, worse again in August
    assert not run([], recs({6: 0.02, 7: 0.05, 8: 0.03}))["calibration"]["crossed"]
    assert run([], recs({7: 0.02, 8: 0.05}))["calibration"]["crossed"] is False             # one rise is not two
    assert run([], recs({5: 0.02, 7: 0.03, 8: 0.05}))["calibration"]["crossed"] is False     # June missing: not two months running


def test_favourite_pick_takes_the_leading_outcome():
    cands = [{"q": "a", "yes": 0.14, "vol": 9e6, "end": "2027-04-01"}, {"q": "b", "yes": 0.145, "vol": 1e6, "end": "2027-04-01"}]
    assert M._pick(cands, "favourite", "vol", "end")["q"] == "b"            # the highest priced, not the most traded
    assert M._pick(cands, "volume", "vol", "end")["q"] == "a"


def test_biggest_move_leaves_out_markets_that_are_settling(mocked):
    from app import cache
    far, soon = str((NOW + pd.Timedelta(days=30)).date()), str(NOW.date())
    row = lambda k, d1, yes, end: {"key": k, "label": k, "poly": {"yes": yes, "d1": d1, "end": end, "vol24": 1}, "kalshi": None}
    cache._cache[f"{M.SLUG}:rows"] = (1e18, ([row("resolved", -0.195, 0.004, far), row("last_day", 0.3, 0.6, soon), row("live", 0.04, 0.5, far)], {}))
    s = {x["key"]: x for x in M.SIGNALS()}["biggest_move"]
    assert s["value"] == 4.0 and not s["crossed"] and s["note"].startswith("live")
    cache._cache[f"{M.SLUG}:rows"] = (1e18, ([row("resolved", -0.195, 0.004, far)], {}))
    s = {x["key"]: x for x in M.SIGNALS()}["biggest_move"]
    assert s["value"] is None and not s["crossed"] and "last day" in s["note"]


def test_accuracy_lists_retired_watchlist_rows(mocked):
    d = M.ENDPOINTS["accuracy"]()
    assert d["retired"] and d["retired"][0]["outcome"] and d["retired"] == sorted(d["retired"], key=lambda r: r["date"], reverse=True)
