"""Search & Social Trends on fixtures (no network): the Wikimedia, MediaWiki, HN, Bluesky, Reddit and GitHub parsers, the paced fill and
its store, weekly z-scores, acceleration and crossings, breakouts, the theme indices, reading other dashboards' series, every tab
payload, READINGS and the seed files. smoke_patch() points the module's downloads at the same fixtures for scripts/smoke.py. Live
calls are marked network."""
import functools
import json
import math
import re
import zlib
from urllib.parse import unquote

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import trends as M

TODAY = pd.Timestamp("2026-10-26")          # a Monday: the last full week ends Sunday 25 October
RISING = {"Polymarket", "Waymo", "Pokémon Trading Card Game"}       # a spike in the last weeks
FADING = {"Solana (blockchain platform)"}


def _seed(s: str) -> int:
    return zlib.crc32(s.encode()) % 1000


def views(title: str, t: pd.Timestamp) -> int:
    """A daily pageview path: a level per article, a weekly cycle, slow waves, a 2017 and 2021 crypto hump, and recent spikes or fades."""
    k = _seed(title)
    y = t.year + t.dayofyear / 365.25
    base = 2000 + 40 * k
    wave = 1 + 0.25 * math.sin(y * 2.1 + k) + 0.08 * math.sin(t.dayofweek)
    hump = 1 + (2.5 * math.exp(-((y - 2017.95) ** 2) / 0.02) + 1.5 * math.exp(-((y - 2021.3) ** 2) / 0.05) if "比特币" in title or "Bitcoin" in title else 0)
    days_left = (TODAY - t).days
    if title in RISING and days_left < 20:
        hump *= 2.2 + (1.5 if days_left == 5 else 0)
    if title in FADING and days_left < 30:
        hump *= 0.45
    noise = 1 + 0.05 * math.sin(t.dayofyear * 7.3 + k)
    return int(base * wave * hump * noise)


@functools.lru_cache(maxsize=None)
def wiki_json(url: str) -> dict:
    m = re.search(r"/per-article/(\w+)\.wikipedia/all-access/user/([^/]+)/daily/(\d{8})/(\d{8})", url)
    lang, title, a, b = m.group(1), unquote(m.group(2)).replace("_", " "), pd.Timestamp(m.group(3)), pd.Timestamp(m.group(4))
    if title == "Kalshi":
        raise RuntimeError("404 Client Error: Not Found for url")
    start = max(a, pd.Timestamp("2022-12-01") if title == "ChatGPT" else a)
    days = pd.date_range(start, min(b, TODAY - pd.Timedelta(days=1)))
    return {"items": [{"project": f"{lang}.wikipedia", "article": title.replace(" ", "_"), "granularity": "daily", "timestamp": d.strftime("%Y%m%d00"),
                       "access": "all-access", "agent": "user", "views": views(title, d)} for d in days]}


@functools.lru_cache(maxsize=None)
def wiki_text(url: str) -> str:
    return json.dumps(wiki_json(url))


def titles_json(url: str) -> dict:
    asked = unquote(re.search(r"[?&]titles=([^&]+)", url).group(1)).split("|")
    norm, redir, pages = [], [], []
    for t in asked:
        if t == "AI agent":
            redir.append({"from": t, "to": "Intelligent agent"})
            pages.append({"title": "Intelligent agent", "pageid": 1})
        elif t == "Housing crisis in the United Kingdom":
            pages.append({"title": t, "missing": True})
        elif t == "宝可梦":
            norm.append({"from": t, "to": "寶可夢"})                       # a script variant: the stored title is traditional
            pages.append({"title": "寶可夢", "pageid": 2})
        else:
            pages.append({"title": t, "pageid": 3})
    return {"batchcomplete": True, "query": {"converted": norm, "redirects": redir, "pages": pages}}


def hn_json(url: str) -> dict:
    q = unquote(re.search(r"query=([^&]+)", url).group(1))
    a = int(re.search(r"created_at_i%3E%3D(\d+)", url).group(1))
    wk = (a - int(pd.Timestamp("2026-01-05").timestamp())) // (7 * 86400)
    n = 5 + _seed(q) % 40 + (wk % 4) + (12 if q in ("polymarket", "waymo") and wk > 38 else 0)
    return {"hits": [{"title": "x"}], "nbHits": n * (9 if "tags=comment" in url else 1), "page": 0, "hitsPerPage": 1}


def bsky_json(url: str) -> dict:
    page = 2 if "cursor=c2" in url else 1 if "cursor=c1" in url else 0
    q = unquote(re.search(r"q=([^&]+)", url).group(1))
    if q == "bitcoin" and page < 4:          # a big one: more than five pages, so it is capped
        return {"posts": [{"uri": f"at://{k}"} for k in range(100)], "cursor": f"c{page + 1}" if page < 2 else "c1"}
    return {"posts": [{"uri": f"at://{k}"} for k in range(100 if page == 0 else 20 + _seed(q) % 50)], "cursor": "c1" if page == 0 else None}


def reddit_json(url: str) -> dict:
    if "www.reddit.com" in url:
        raise RuntimeError("HTTP 403: blocked")           # the first address refuses cloud servers; old.reddit answers
    sub = re.search(r"/r/([^/]+)/about", url).group(1)
    return {"kind": "t5", "data": {"display_name": sub, "subscribers": 100000 + 3000 * _seed(sub), "active_user_count": 300 + _seed(sub)}}


def github_json(url: str) -> dict:
    repo = url.split("/repos/")[1]
    return {"full_name": repo, "stargazers_count": 20000 + 150 * _seed(repo), "forks_count": 3000 + _seed(repo)}


def site_points(start: str, freq: str, f) -> list:
    ix = pd.date_range(start, TODAY, freq=freq)
    return [[int(t.timestamp()), round(f(t), 2)] for t in ix]


def site_json(url: str) -> dict:
    """The other dashboards' payloads, only the parts read here."""
    path = url.split("/api/", 1)[1]
    btc = lambda t: 1000 * math.exp(0.35 * (t.year + t.dayofyear / 365 - 2016)) * (1 + 0.6 * math.sin(t.year + t.dayofyear / 58))
    return {"btc-cycles/cycles": {"price": site_points("2016-01-03", "W-SUN", btc), "price_recent": [], "as_of": "2026-10-25"},
            "pokemon-cards/prices": {"all": site_points("2016-01-01", "MS", lambda t: 100 + 8 * (t.year - 2016) + 60 * math.exp(-((t.year + t.month / 12 - 2021.2) ** 2) / 0.2))},
            "robotaxi/tesla": {"tsla": site_points("2020-01-01", "B", lambda t: 100 + 50 * math.sin(t.dayofyear / 40) + 20 * (t.year - 2020))},
            "housing/prices": {"london_real": site_points("2016-01-01", "MS", lambda t: 450000 + 1000 * (t.year - 2016) * 12)},
            "ai/openings": {"US": {"all": site_points("2020-02-02", "W-SUN", lambda t: 100), "sectors": {}},
                            "ai_share": {"US": site_points("2020-02-01", "MS", lambda t: 0.5 + 0.1 * (t.year - 2020))}},
            "space/satellites": {"active": {"cumulative_starlink": site_points("2019-05-01", "MS", lambda t: 60 * ((t.year - 2019) * 12 + t.month))}},
            "climate/temperature": {"monthly": {"GISTEMP": site_points("1880-01-01", "MS", lambda t: 0.2 + 0.02 * (t.year - 1980))}},
            }.get(path, {"nothing": "here"})


def fake_download(url, site_=None, headers=None, timeout=30):
    if "/metrics/pageviews/" in url:
        return wiki_text(url)
    if "/w/api.php" in url:
        return json.dumps(titles_json(url))
    if "hn.algolia.com" in url:
        return json.dumps(hn_json(url))
    if "searchPosts" in url:
        return json.dumps(bsky_json(url))
    if "reddit.com" in url:
        return json.dumps(reddit_json(url))
    if "api.github.com" in url:
        return json.dumps(github_json(url))
    raise ConnectionError(f"fixture: no route for {url}")


def fake_fetch(url, ttl=0, **k):
    return json.dumps(site_json(url))


def fake_read(url):
    return json.dumps(site_json(url))


def seed_log(days: int = 70) -> None:
    """Earlier days of the daily log (Bluesky, Reddit, GitHub give only today's number), as if the dashboard had run since August."""
    rows = []
    for d in range(days, 0, -1):
        day = str((TODAY - pd.Timedelta(days=d)).date())
        for i in M.topics_list():
            if i.get("social") == "y":
                rows.append((day, "bsky", i["key"], "posts", 50 + _seed(i["key"]) % 300 + (d % 7) * 5 + (120 if i["key"] == "polymarket" and d < 10 else 0)))
        for s in M.subreddits():
            rows.append((day, "reddit", s["subreddit"], "subscribers", 100000 + 3000 * _seed(s["subreddit"]) - 40 * d))
        for r in M.repos():
            rows.append((day, "github", r["repo"], "stars", 20000 + 150 * _seed(r["repo"]) - 25 * d))
    f = M._log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w") as fh:
        fh.write("date,source,key,field,value\n")
        fh.writelines(f"{d},{s},{k},{fld},{v}\n" for d, s, k, fld, v in rows)


def _patch(set_):
    set_(M, "download", fake_download)
    set_(M, "fetch", fake_fetch)
    set_(M, "cached_only", fake_read)
    set_(M, "_now", lambda: TODAY)
    set_(M, "PACE", dict.fromkeys(M.PACE, 0))


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above; the fill runs once, with no pauses."""
    _patch(lambda mod, name, v: setattr(mod, name, v))
    seed_log()
    M.fill()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    _patch(monkeypatch.setattr)
    cache._cache.clear()
    B.STALE.clear()
    for u in M.HEALTH_KEYS.values():
        B.HEALTH.pop(u, None)
    yield
    cache._cache.clear()
    B.STALE.clear()


@pytest.fixture
def filled(mocked):
    seed_log()
    return M.fill()


# ------------------------------------------------------------------ parsers
def test_parse_wiki():
    j = {"items": [{"timestamp": "2026010100", "views": 12}, {"timestamp": "2026010200", "views": 30}]}
    assert M.parse_wiki(j) == {"2026-01-01": 12, "2026-01-02": 30}
    with pytest.raises(ValueError):
        M.parse_wiki({"type": "https://mediawiki.org/wiki/HyperSwitch/errors/not_found"})


def test_parse_titles_follows_redirects_and_variants():
    j = titles_json("https://zh.wikipedia.org/w/api.php?titles=" + "|".join(["宝可梦", "AI agent", "Housing crisis in the United Kingdom", "比特币"]))
    got = M.parse_titles(j)
    assert got["宝可梦"] == "寶可夢" and got["AI agent"] == "Intelligent agent" and got["比特币"] == "比特币"
    assert "Housing crisis in the United Kingdom" not in got


def test_parse_social():
    assert M.parse_hn({"nbHits": 42}) == 42
    with pytest.raises(ValueError):
        M.parse_hn({})
    assert M.parse_reddit({"data": {"subscribers": 10, "accounts_active": 3}}) == {"subscribers": 10, "active": 3}
    assert M.parse_github({"stargazers_count": 5, "forks_count": 1, "full_name": "a/b"})["stars"] == 5
    with pytest.raises(ValueError):
        M.parse_github({"message": "API rate limit exceeded"})


def test_wiki_url_encodes_titles():
    u = M.wiki_url("en", "Tesla, Inc.", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-31"))
    assert "/Tesla%2C_Inc./daily/20260101/20260131" in u
    assert "%2F" in M.wiki_url("en", "AC/DC", TODAY, TODAY)


# ------------------------------------------------------------------ arithmetic
def test_weekly_full_drops_partial_weeks():
    s = pd.Series(1.0, index=pd.date_range("2026-01-05", "2026-01-21"))          # Mon 5 Jan .. Wed 21 Jan
    w = M.weekly_full(s)
    assert list(w.index.strftime("%Y-%m-%d")) == ["2026-01-11", "2026-01-18"] and (w == 7).all()


def test_rolling_z_flags_a_jump():
    w = pd.Series([1000.0 + 10 * (k % 3) for k in range(60)] + [3000.0], index=pd.date_range("2025-01-05", periods=61, freq="W-SUN"))
    z = M.rolling_z(w)
    assert z.iloc[-1] > 5 and abs(z.iloc[-2]) < 2
    assert M.rolling_z(w.iloc[:20]).empty                                     # fewer than 26 weeks of history: no score


def test_accel_and_crossing():
    w = pd.Series([100.0] * 20 + [100, 100, 300, 400], index=pd.date_range("2025-01-05", periods=24, freq="W-SUN"))
    a = M.accel(w)
    assert a["a4"] > 1 and a["a13"] > 2
    flat_then_up = pd.Series([100.0] * 22 + [500.0], index=pd.date_range("2025-01-05", periods=23, freq="W-SUN"))
    assert M.accel(flat_then_up)["cross"] == "up"
    down = pd.Series([100.0] * 22 + [10.0], index=pd.date_range("2025-01-05", periods=23, freq="W-SUN"))
    assert M.accel(down)["cross"] == "down"
    assert M.accel(w.iloc[:10])["a4"] is None


def test_breakouts():
    ix = pd.date_range("2026-06-01", "2026-10-25")
    s = pd.Series(1000.0, index=ix) * (1 + 0.02 * np.sin(np.arange(len(ix))))
    s[pd.Timestamp("2026-10-20")] = 9000
    b = M.breakouts(s)
    assert [x["date"] for x in b] == ["2026-10-20"] and b[0]["multiple"] > 8
    assert M.breakouts(s.iloc[:30]) == []


def test_index100_and_geo_mean():
    w = pd.Series([100.0] * 52 + [200.0], index=pd.date_range("2025-01-05", periods=53, freq="W-SUN"))
    assert M.index100(w).iloc[-1] == 200
    g = M.geo_mean([pd.Series([100.0, 400.0], index=w.index[-2:]), pd.Series([100.0, 100.0], index=w.index[-2:])])
    assert list(g.round(6)) == [100.0, 200.0]


def test_pick_and_series_paths():
    j = {"a": {"b": [[1600000000, 1], [1600086400, 2], [1600172800, 3]]}, "c": [[1600000000, 1]] * 5, "d": "x"}
    assert M.pick(j, "a.b")[-1] == [1600172800, 3]
    assert len(M.pick(j, "*")) == 5 and M.pick(j, "a.*")[0][1] == 1
    assert M.pick(j, "nope") is None and M.pick(j, "d") is None
    assert dict(M.series_paths(j)) == {"a.b": 3, "c": 5}


def test_lead_lag_finds_the_lag():
    ix = pd.date_range("2018-01-01", periods=96, freq="MS")
    a = pd.Series(np.exp(np.sin(np.arange(96) / 5)), index=ix)
    r = pd.Series(np.exp(np.sin((np.arange(96) - 2) / 5)), index=ix)         # reality follows attention two months later
    st = M.lead_lag(a, r)
    assert st["best_lag"] == 2 and st["best_corr"] > 0.9 and st["n"] == 96
    assert M.lead_lag(a.iloc[:6], r.iloc[:6])["level"] is None


# ------------------------------------------------------------------ the fill and the store
def test_fill_builds_the_store(filled):
    store = M.load("wiki")
    assert len(store) >= 45
    assert store["agents"]["title"] == "Intelligent agent"                    # resolved through the redirect
    assert store["zh_pokemon"]["title"] == "寶可夢"
    assert min(store["bitcoin"]["days"]) == "2016-01-01" and max(store["bitcoin"]["days"]) == "2026-10-25"
    assert "kalshi" in str(filled) and "uk_housing" in str(filled)            # a 404 and a missing title are reported per topic
    hn = M.load("hn")
    assert len([k for k in hn["bitcoin"] if k != "_q"]) == M.HN_WEEKS
    log = pd.read_csv(M._log_file())
    assert {"bsky", "reddit", "github"} <= set(log["source"])
    assert ((log["source"] == "bsky") & (log["key"] == "bitcoin") & (log["field"] == "capped")).any()
    st = M.load("state")
    assert st["counts"]["wiki_en"][0] > 30 and st["counts"]["reddit"][0] == len(M.subreddits())


def test_fill_again_only_downloads_what_is_new(filled, monkeypatch):
    calls = []
    monkeypatch.setattr(M, "download", lambda url, *a, **k: calls.append(url) or fake_download(url, *a, **k))
    for rec in M.load("wiki").values():
        assert rec.get("at") or not rec.get("days")
    M.fill()
    assert not [u for u in calls if "/pageviews/" in u]                       # every article downloaded less than 20 hours ago
    hn = [u for u in calls if "algolia" in u]
    assert 0 < len(hn) <= 2 * 2 * len([i for i in M.topics_list() if i.get("query")])     # only the last two weeks again
    store = M.load("wiki")
    rec = store["bitcoin"]
    rec["at"] = rec["tried"] = 0
    M.save("wiki", store)
    calls.clear()
    M.fill()
    wiki = [u for u in calls if "/pageviews/" in u]
    assert len(wiki) == 1 and "/daily/20261011/" in wiki[0]                  # two weeks before the last stored day


def test_health_files_one_address_per_source(filled):
    h = topics.health()["dashboards"]["trends"]
    hosts = {s["url"] for s in h["sources"]}
    assert M.HEALTH_KEYS["wiki_en"] in hosts and M.HEALTH_KEYS["reddit"] in hosts
    assert not [u for u in hosts if "/daily/" in u]
    assert h["failing"] == 0


def test_health_stale_when_a_source_stops(filled, monkeypatch):
    monkeypatch.setattr(M, "download", lambda url, *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 429")) if "api.github.com" in url else fake_download(url, *a, **k))
    M.fill()
    assert M.HEALTH_KEYS["github"] in B.STALE
    gh = next(s for s in topics.health()["dashboards"]["trends"]["sources"] if s["url"] == M.HEALTH_KEYS["github"])
    assert gh["status"] == "stale" and "429" in gh["error"]


def test_bluesky_and_reddit_refusals_are_handled_not_alerts(mocked, monkeypatch):
    """As on Railway (Oct 2026): Bluesky's search and every Reddit host answer 403 and never answered before. Both stay 'failing'
    in /api/health, with the reason, but raise no alert; the Social tab carries the reason. Any other error still alerts."""
    import requests

    def refuse(url, *a, **k):
        if "searchPosts" in url:
            raise requests.HTTPError("403 Client Error: Forbidden for url: " + url)
        if "reddit.com" in url:
            raise requests.HTTPError("403 Client Error: Blocked for url: " + url)
        return fake_download(url, *a, **k)
    monkeypatch.setattr(M, "download", refuse)
    M.fill()
    src = {s["url"]: s for s in topics.health()["dashboards"]["trends"]["sources"]}
    for k in ("bsky", "reddit"):
        s = src[M.HEALTH_KEYS[k]]
        assert s["status"] == "failing" and not s["alert"] and s["handled"] == M.CLOSED[k] and "403" in s["error"]
    soc = M._social_now()
    assert soc["bsky"]["closed"] == M.CLOSED["bsky"] and soc["reddit"]["closed"] == M.CLOSED["reddit"] and soc["bsky"]["rows"] == []
    B.json_safe(soc)
    for u in M.HEALTH_KEYS.values():
        B.HEALTH.pop(u, None)
    monkeypatch.setattr(M, "download", lambda url, *a, **k: (_ for _ in ()).throw(ValueError("bad JSON")) if "searchPosts" in url else fake_download(url, *a, **k))
    M.fill()
    s = next(s for s in topics.health()["dashboards"]["trends"]["sources"] if s["url"] == M.HEALTH_KEYS["bsky"])
    assert s["alert"] and "handled" not in s


def test_log_today_keeps_the_first_value(mocked):
    assert M.log_today([("github", "a/b", "stars", 10)], "2026-10-01") == 1
    assert M.log_today([("github", "a/b", "stars", 11), ("github", "a/b", "forks", 2)], "2026-10-01") == 1
    assert M.daily_log("github", "stars").iloc[0, 0] == 10


# ------------------------------------------------------------------ payloads
def test_overview(filled):
    d = M.ENDPOINTS["overview"]()
    B.json_safe(d)
    assert d["as_of"] == "2026-10-25"
    top = [r["key"] for r in d["rising"][:3]]
    assert {"polymarket", "waymo", "ptcg"} & set(top)
    assert d["fading"][0]["key"] == "solana" and d["fading"][0]["z"] < -1
    assert all(r["region"] == "global" for r in d["rising"] + d["fading"])
    th = {t["theme"]: t for t in d["themes"]}
    assert {"ai", "bitcoin", "pokemon", "robotaxi", "housing", "climate", "prediction"} <= set(th)
    assert th["prediction"]["index"] > 120 and len(th["ai"]["points"]) > 300


def test_search(filled):
    d = M.ENDPOINTS["search"]()
    B.json_safe(d)
    assert len(d["total"]) > 100 and len(d["top"]) == 5
    assert {g["theme"] for g in d["groups"]} >= {"ai", "bitcoin"}
    assert any(b["key"] == "polymarket" for b in d["breakouts"])
    assert "bitcoin|world" in d["gtrends"] and d["gtrends_cited"]


def test_social(filled):
    d = M.ENDPOINTS["social"]()
    B.json_safe(d)
    assert len(d["hn"]["stories"]) == 6 and len(d["hn"]["total_stories"]) == M.HN_WEEKS
    assert d["hn"]["rows"][0]["stories"] > 0
    assert d["github"]["rows"][0]["d30"] == 25 * 30 and d["github"]["rows"][0]["since"] == "2026-08-17"
    assert d["reddit"]["rows"] and d["reddit"]["rows"][0]["active"]
    assert next(r for r in d["bsky"]["rows"] if r["key"] == "bitcoin")["capped"] is True


def test_social_hand_entered_reddit(filled, monkeypatch):
    hand = {"Bitcoin|subscribers": pd.Series([7.0e6], index=[pd.Timestamp("2026-05-01")]), "Fake|subscribers": pd.Series([5.0], index=[pd.Timestamp("2026-05-01")])}
    monkeypatch.setattr(M, "manual", lambda slug, name: hand if name == "reddit" else B.manual(slug, name))
    d = M._social_now()
    rows = {r["sub"]: r for r in d["reddit"]["rows"]}
    assert rows["Fake"]["subscribers"] == 5 and rows["Bitcoin"]["date"] == "2026-10-26"


def test_rising(filled):
    d = M.ENDPOINTS["rising"]()
    B.json_safe(d)
    assert d["rows"][0]["a13"] > d["rows"][-1]["a13"]
    assert d["rows"][-1]["key"] == "solana"
    assert len(d["z_lines"]) == 7 and all(len(z["points"]) > 50 for z in d["z_lines"])


def test_regions(filled):
    d = M.ENDPOINTS["regions"]()
    B.json_safe(d)
    assert set(d["regions"]) == {"global", "uk", "zh"}
    assert {p["theme"] for p in d["pairs"]} >= {"bitcoin", "ai", "pokemon"}
    assert all(t["region"] != "global" for t in d["topics"])


def test_reality(filled):
    d = M.ENDPOINTS["reality"]()
    B.json_safe(d)
    th = {t["theme"]: t for t in d["themes"]}
    assert th["bitcoin"]["stats"]["n"] > 100 and th["bitcoin"]["stats"]["level"] is not None
    assert th["ai"]["reality"] and th["climate"]["reality"]                     # dotted path and 'monthly.*'
    assert th["space"]["reality"] and th["climate"]["reality"][0][0] == int(pd.Timestamp("2015-01-01").timestamp())   # 1880 on, read from 2015
    assert "error" in th["rates"] and th["rates"]["paths"] == []                # a payload with no series says so
    last = pd.to_datetime(th["bitcoin"]["attention"][-1][0], unit="s")
    assert last == pd.Timestamp("2026-09-01")                                     # October is not finished


def test_readings(filled):
    M.ENDPOINTS["overview"]()
    r = M.READINGS()
    assert len(r) >= 45 and all(x["lean"] in (-1, 0, 1) for x in r)
    by = {x["key"]: x for x in r}
    assert by["z_solana"]["lean"] == -1 and by["z_polymarket"]["lean"] == 1
    assert by["z_zh_bitcoin"]["tab"] == "regions" and by["z_bitcoin"]["tab"] == "overview"
    from app.topics import _daily
    assert _daily._clean(r) and len(_daily._clean(r)) == len(r)


def test_readings_empty_without_cache(mocked):
    assert M.READINGS() == []


def test_endpoints_without_data(mocked):
    for k, fn in M.ENDPOINTS.items():
        if k != "layout":
            B.json_safe(fn())


# ------------------------------------------------------------------ the seed files and registration
def test_seed_files():
    items = M.topics_list()
    assert 50 <= len(items) <= 70 and len({i["key"] for i in items}) == len(items)
    assert len([i for i in items if i["region"] == "global"]) >= 38
    assert {i["region"] for i in items} == {"global", "uk", "zh"}
    assert all(i["theme"] in M.THEMES for i in items)
    assert all(i["source"].startswith(f"https://{i['lang']}.wikipedia.org/wiki/") for i in items)
    assert {r["theme"] for r in M.reality_rows()} <= set(M.THEMES)
    assert len(M.repos()) >= 8 and len(M.subreddits()) >= 10
    for name in ("gtrends", "reddit"):
        for r in B.manual_rows("trends", name):
            assert r["source"].startswith("http"), r
            float(r["value"])
            assert "|" in r["series"]


def test_registered():
    t = topics.REGISTRY["trends"]
    assert t.module == "trends" and [k for k, _ in t.tabs] == ["overview", "search", "social", "rising", "regions", "reality"]
    assert set(t.slow) <= set(M.ENDPOINTS)
    m = topics.meta("trends")
    assert m["sources"] and m["notes"]


# ------------------------------------------------------------------ live
@pytest.mark.network
def test_live_wikimedia():
    end = pd.Timestamp.now().normalize() - pd.Timedelta(days=2)
    j = json.loads(B._download(M.wiki_url("en", "Bitcoin", end - pd.Timedelta(days=7), end), 30, False, M.BOT))
    assert len(M.parse_wiki(j)) >= 5


@pytest.mark.network
def test_live_titles():
    j = json.loads(B._download(M.WIKI_TITLES.format(lang="zh", titles="比特币"), 30, False, M.BOT))
    assert M.parse_titles(j)


@pytest.mark.network
def test_live_hn():
    now = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    u = M.HN.format(q="bitcoin", tag="story", a=int((now - pd.Timedelta(days=7)).timestamp()), b=int(now.timestamp()))
    assert M.parse_hn(json.loads(B._download(u, 30, False, None))) > 0


@pytest.mark.network
def test_live_github():
    assert M.parse_github(json.loads(B._download(M.GITHUB.format(repo="pytorch/pytorch"), 30, False, M.BOT)))["stars"] > 50000
