"""Search & Social Trends (/trends): what people are reading, searching and posting about, and whether it is rising or fading.

overview   each tracked topic's attention z-score (its latest full week of Wikipedia pageviews against its own previous year) and an
           attention index per theme of the other dashboards on this site (AI, bitcoin, Pokémon cards, robotaxis, housing, climate, ...)
search     weekly Wikipedia pageviews (Wikimedia REST API, daily, free) for the topics in data/trends/topics.csv, hand-entered Google
           Trends points (gtrends.csv), and breakouts: days far above a topic's own recent normal
social     Hacker News stories and comments per topic per week (Algolia), Bluesky posts per day (public searchPosts), Reddit subscribers
           and active users (about.json, else reddit.csv), GitHub stars of the main AI repos
rising     each week against its 4- and 13-week averages, and the topics whose 4-week average crossed the 13-week one
regions    English Wikipedia (global), UK-specific pages, Chinese Wikipedia (zh, read in Hong Kong, Taiwan and abroad), Google Trends by region
reality    each theme's attention against that dashboard's own headline series, read over HTTP from this site's /api/<slug>/<name>

Downloads are slow and paced (BACKGROUND fill(), like pokemon_cards): one request at a time per site, PACE seconds apart. Wikipedia
history is kept in one store on the snapshot volume and only the last few weeks are downloaded again; HN weekly counts are kept once a
week is complete; Bluesky, Reddit and GitHub give only today's number, so a daily log builds their history from launch. Pages only read
what the fill stored. Sources are filed in /api/health under stable addresses (one per source), not one per download.

Leans in READINGS(): +1 when a topic's attention z-score is +1 or more (rising), -1 at -1 or less (fading) (data/trends/README.md).
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from urllib.parse import quote

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, MANUAL_DIR, _pts, _r, cached_only, fetch, manual, manual_sources

SLUG = "trends"
TOPIC = Topic(SLUG, "Search & Social Trends",
              "What people are reading, searching and posting about: Wikipedia pageviews, Hacker News, Bluesky, Reddit and GitHub for about 40 topics, "
              "which are rising or fading this week, the US, UK and Chinese-language views, and attention set against each dashboard's own numbers.",
              "trends", (("overview", "Overview"), ("search", "Search"), ("social", "Social"), ("rising", "Rising & fading"), ("regions", "US / UK / HK"),
                         ("reality", "Attention vs reality")),
              ("overview", "search", "social", "rising", "regions", "reality"), icon="trend", order=60)

WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{title}/daily/{a}/{b}"
WIKI_TITLES = "https://{lang}.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1&converttitles=1&titles={titles}"
HN = "https://hn.algolia.com/api/v1/search_by_date?query={q}&tags={tag}&numericFilters=created_at_i%3E%3D{a},created_at_i%3C{b}&hitsPerPage=1"
# public.api.bsky.app answers 403 to Railway; the AppView host answers (checked with /layout, 2026-10-26)
BSKY = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={q}&sort=latest&since={a}&until={b}&limit=100"
REDDIT = ("https://www.reddit.com/r/{sub}/about.json", "https://old.reddit.com/r/{sub}/about.json", "https://api.reddit.com/r/{sub}/about")
GITHUB = "https://api.github.com/repos/{repo}"
GTRENDS = ("https://trends.google.com/trends/api/explore?hl=en-US&tz=0&req=%7B%22comparisonItem%22%3A%5B%7B%22keyword%22%3A%22bitcoin%22%2C%22geo%22%3A%22%22%2C"
           "%22time%22%3A%22today%205-y%22%7D%5D%2C%22category%22%3A0%2C%22property%22%3A%22%22%7D")
# Wikimedia asks API clients to say who they are; Reddit wants the same
BOT = {"User-Agent": "dashboards-trends/1.0 (https://github.com/mcmarcocheung98-max/dashboards)", "Accept": "application/json"}
# one stable address per source for /api/health (the downloads themselves change address every day)
HEALTH_KEYS = {"wiki_en": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia",
               "wiki_zh": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/zh.wikipedia",
               "titles": "https://en.wikipedia.org/w/api.php?action=query", "hn": "https://hn.algolia.com/api/v1/search_by_date",
               "bsky": "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", "reddit": "https://www.reddit.com/r/<sub>/about.json",
               "github": "https://api.github.com/repos/<repo>"}

PACE = {"wiki": 0.3, "hn": 0.4, "bsky": 1.0, "reddit": 3.0, "github": 1.5, "site": 0.5}
WIKI_START = pd.Timestamp("2016-01-01")
WIKI_REFETCH_DAYS = 14          # Wikimedia revises the last few days; download again from two weeks before the last stored day
HN_WEEKS = 26                   # weekly HN counts kept for the last half year; complete weeks are not downloaded again
BSKY_PAGES = 5                  # at most 500 posts counted per keyword per day ("500+")
YEAR, MIN_WEEKS = 52, 26        # z-scores against the previous 52 weeks, once there are at least 26
Z_LEAN = 1.0

THEMES = {"ai": ("AI", "ai"), "bitcoin": ("Bitcoin & crypto", "btc-cycles"), "pokemon": ("Pokémon cards", "pokemon-cards"), "robotaxi": ("Robotaxis", "robotaxi"),
          "housing": ("Housing", "housing"), "climate": ("Climate", "climate"), "prediction": ("Prediction markets", "debt-rates"), "space": ("Space", "space"),
          "chips": ("Chips & compute", "compute-chips"), "china": ("China tech", "china-us-tech"), "longevity": ("Longevity & GLP-1", "longevity"),
          "rates": ("Rates & the economy", "debt-rates"), "demographics": ("Demographics", "demographics")}
REGIONS = (("global", "English Wikipedia (global, US-led)"), ("uk", "UK-specific pages (English Wikipedia)"), ("zh", "Chinese Wikipedia (HK, Taiwan, diaspora)"))

SOURCES = [{"name": "Wikimedia REST API: daily pageviews per article, English and Chinese Wikipedia (users, all access)", "url": "https://wikimedia.org/api/rest_v1/", "cadence": "daily"},
           {"name": "Hacker News search (Algolia): stories and comments per topic per week", "url": "https://hn.algolia.com/api", "cadence": "daily"},
           {"name": "Bluesky API (app.bsky.feed.searchPosts): posts per keyword per day", "url": "https://docs.bsky.app/docs/api/app-bsky-feed-search-posts", "cadence": "daily"},
           {"name": "Reddit about.json: subreddit subscribers and active users", "url": "https://www.reddit.com/dev/api/", "cadence": "daily, hand-entered when blocked"},
           {"name": "GitHub REST API: stars of the main AI repositories", "url": "https://docs.github.com/en/rest/repos/repos", "cadence": "daily"},
           {"name": "This site's own dashboards (/api/<slug>/<name>) for the attention-vs-reality series", "url": "/", "cadence": "twice a day"},
           {"name": "Hand-entered, cited per row: Google Trends points (world, US, UK, HK), Reddit counts when the server is blocked",
            "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/trends", "cadence": "monthly / as needed"}]
NOTES = ("Attention is measured mainly by Wikipedia pageviews (people looking a subject up), with Hacker News, Bluesky, Reddit and GitHub as the social "
         "side. A z-score of +2 means this week's views are two standard deviations above the topic's own previous year (on a log scale), so a small "
         "topic doubling counts as much as a big one doubling. Wikipedia is a proxy for search interest, not search itself: Google Trends points are "
         "hand-entered and cited; rows marked 'verify' were entered from memory. Not investment advice.")


# ------------------------------------------------------------------ the hand-entered lists
def _csv(name: str) -> list[dict]:
    f = MANUAL_DIR / SLUG / f"{name}.csv"
    if not f.exists():
        return []
    with f.open(newline="", encoding="utf-8") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]


def topics_list() -> list[dict]:
    return [r for r in _csv("topics") if r.get("key") and r.get("article") and r.get("lang") in ("en", "zh")]


def repos() -> list[dict]:
    return [r for r in _csv("repos") if r.get("repo")]


def subreddits() -> list[dict]:
    return [r for r in _csv("subreddits") if r.get("subreddit")]


def reality_rows() -> list[dict]:
    return [r for r in _csv("reality") if r.get("theme") and r.get("slug") and r.get("endpoint")]


def _empty() -> pd.Series:
    return pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None).normalize()


def site() -> str:
    """This site, for reading the other dashboards' series: TRENDS_SITE if set, else the server itself."""
    return (os.environ.get("TRENDS_SITE") or f"http://127.0.0.1:{os.environ.get('PORT', '8080')}").rstrip("/")


# ------------------------------------------------------------------ the store (snapshot volume, data/trends/... is only configuration)
def _dir():
    return B.SNAP_DIR / SLUG


def load(name: str, default=None):
    try:
        return json.loads((_dir() / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def save(name: str, obj) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{name}.json.tmp"
    tmp.write_text(json.dumps(obj, sort_keys=True))
    tmp.replace(d / f"{name}.json")


def _log_file():
    return _dir() / "log.csv"


def log_today(rows: list[tuple], today: str | None = None) -> int:
    """Append today's (source, key, field, value) rows to the daily log; the first value of a UTC day is kept."""
    today = today or str(_now().date())
    f = _log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    have = set()
    if f.exists():
        have = {tuple(line.split(",")[:4]) for line in f.read_text().splitlines()[1:] if line.startswith(today)}
    new = [(today, s, k, fld, v) for s, k, fld, v in rows if v is not None and (today, s, k, fld) not in have]
    if new:
        head = not f.exists() or f.stat().st_size == 0
        with f.open("a") as fh:
            if head:
                fh.write("date,source,key,field,value\n")
            fh.writelines(f"{d},{s},{k},{fld},{_r(v, 2)}\n" for d, s, k, fld, v in new)
    return len(new)


def daily_log(source: str, field: str) -> pd.DataFrame:
    """date x key for one source and field of the daily log."""
    f = _log_file()
    if not f.exists():
        return pd.DataFrame()
    d = pd.read_csv(f, dtype={"key": str})
    d = d[(d["source"] == source) & (d["field"] == field)]
    if d.empty:
        return pd.DataFrame()
    d["date"] = pd.to_datetime(d["date"])
    return d.pivot_table(index="date", columns="key", values="value", aggfunc="last").sort_index()


# ------------------------------------------------------------------ parsers
def parse_wiki(j: dict) -> dict[str, int]:
    """Wikimedia per-article pageviews: {"items": [{"timestamp": "2026010100", "views": n}, ...]} -> {"2026-01-01": n}."""
    items = (j or {}).get("items")
    if items is None:
        raise ValueError("Wikimedia: no items")
    return {f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}": int(i["views"]) for i in items if i.get("timestamp") and i.get("views") is not None}


def parse_titles(j: dict) -> dict[str, str]:
    """MediaWiki query with redirects and title conversion: asked title -> the stored article's title (missing pages left out)."""
    q = (j or {}).get("query") or {}
    hop = {}
    for k in ("normalized", "converted", "redirects"):
        for x in q.get(k) or []:
            hop[x["from"]] = x["to"]
    pages = {p["title"] for p in q.get("pages") or [] if not p.get("missing") and not p.get("invalid")}
    out = {}
    for asked in list(hop) + list(pages):
        t, seen = asked, set()
        while t in hop and t not in seen:
            seen.add(t)
            t = hop[t]
        if t in pages:
            out[asked] = t
    return out


def parse_hn(j: dict) -> int:
    n = (j or {}).get("nbHits")
    if n is None:
        raise ValueError("HN: no nbHits")
    return int(n)


def parse_reddit(j: dict) -> dict:
    d = (j or {}).get("data") or {}
    if not d:
        raise ValueError("Reddit: no data")
    act = d.get("active_user_count", d.get("accounts_active"))
    return {"subscribers": d.get("subscribers"), "active": act}


def parse_github(j: dict) -> dict:
    if "stargazers_count" not in (j or {}):
        raise ValueError("GitHub: no stargazers_count")
    return {"stars": j["stargazers_count"], "forks": j.get("forks_count"), "name": j.get("full_name")}


def wiki_url(lang: str, title: str, a: pd.Timestamp, b: pd.Timestamp) -> str:
    return WIKI.format(lang=lang, title=quote(title.replace(" ", "_"), safe=""), a=a.strftime("%Y%m%d"), b=b.strftime("%Y%m%d"))


# ------------------------------------------------------------------ the background fill (slow, paced; the only place that downloads)
_last: dict[str, float] = {}


def _pace(site_: str) -> None:
    wait = PACE.get(site_, 1) - (time.time() - _last.get(site_, 0))
    if wait > 0:
        time.sleep(wait)
    _last[site_] = time.time()


def download(url: str, site_: str, headers: dict | None = None, timeout: int = 30) -> str:
    """One paced download, not snapshotted (the store is the snapshot); replaced by fixtures in the tests."""
    _pace(site_)
    return B._download(url, timeout, False, headers)


def _health(results: dict[str, list]) -> None:
    """File each source under its stable address: fresh when any of its downloads worked in this fill, else stale (since its last
    good fill) or failing."""
    state = load("state")
    ok_at = state.setdefault("ok", {})
    now = time.time()
    for src, outcomes in results.items():
        if not outcomes or src not in HEALTH_KEYS:
            continue
        url = HEALTH_KEYS[src]
        h = B.HEALTH.setdefault(url, {"module": "trends", "ok": None, "fail": None, "error": None})
        errs = [o for o in outcomes if o is not True]
        if len(errs) < len(outcomes):
            ok_at[src] = now
            h.update(ok=now, error=None)
            B.STALE.pop(url, None)
        else:
            h.update(fail=now, error=str(errs[0])[:160])
            if ok_at.get(src):
                h["ok"] = h["ok"] or ok_at[src]
                B.STALE[url] = ok_at[src]
    save("state", state)


def _resolve_titles(items: list[dict], res: dict, out: dict) -> None:
    """Each article's stored title (after redirects and Chinese script conversion), asked once a month, 40 titles per request."""
    for lang in ("en", "zh"):
        todo = [i["article"] for i in items if i["lang"] == lang and time.time() - res.get(f"{lang}:{i['article']}", {}).get("at", 0) > 30 * DAY]
        for k in range(0, len(todo), 40):
            chunk = todo[k:k + 40]
            try:
                got = parse_titles(json.loads(download(WIKI_TITLES.format(lang=lang, titles=quote("|".join(chunk), safe="")), "wiki", BOT)))
                for t in chunk:
                    res[f"{lang}:{t}"] = {"title": got.get(t), "at": time.time()} if got.get(t) else {"title": None, "at": time.time(), "missing": True}
                out["titles"].append(True)
            except Exception as e:
                out["titles"].append(f"{type(e).__name__}: {str(e)[:100]}")


def fill_wiki(items: list[dict], out: dict, done: dict) -> None:
    store, res = load("wiki"), load("titles")
    _resolve_titles(items, res, out)
    save("titles", res)
    end = _now() - pd.Timedelta(days=1)
    for i in items:
        rec = store.setdefault(i["key"], {"days": {}})
        if time.time() - max(rec.get("at", 0), rec.get("tried", 0)) < 20 * 3600:      # once a day, failures included
            continue
        r = res.get(f"{i['lang']}:{i['article']}", {})
        if r.get("missing"):
            done[f"wiki {i['key']}"] = "no such article (check the title in topics.csv)"
            continue
        rec["tried"] = time.time()
        title = r.get("title") or i["article"]
        days = rec["days"]
        if rec.get("title") != title:        # a different article than the stored one: start again
            days.clear()
        a = max(WIKI_START, pd.Timestamp(max(days)) - pd.Timedelta(days=WIKI_REFETCH_DAYS)) if days else WIKI_START
        try:
            got = parse_wiki(json.loads(download(wiki_url(i["lang"], title, a, end), "wiki", BOT, timeout=60)))
            days.update(got)
            rec.update(title=title, lang=i["lang"], at=time.time())
            out[f"wiki_{i['lang']}"].append(True)
            done.setdefault(f"wiki {i['key']}", "ok")
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:100]}"
            # a 404 is this article (wrong title or no views yet), not the source being down
            out[f"wiki_{i['lang']}"].append(True if "404" in msg else msg)
            done[f"wiki {i['key']}"] = msg
    save("wiki", store)


def _weeks(n: int, now: pd.Timestamp) -> list[pd.Timestamp]:
    """The last n complete weeks, Monday starts (UTC)."""
    this_monday = now - pd.Timedelta(days=now.weekday())
    return [this_monday - pd.Timedelta(weeks=k) for k in range(n, 0, -1)]


def fill_hn(items: list[dict], out: dict, done: dict) -> None:
    store = load("hn")
    weeks = _weeks(HN_WEEKS, _now())
    keep = {str(w.date()) for w in weeks}
    for i in [i for i in items if i.get("query")]:
        rec = store.setdefault(i["key"], {})
        if rec.get("_q") != i["query"]:
            rec.clear()
            rec["_q"] = i["query"]
        for w in weeks:
            k = str(w.date())
            # complete weeks never change, except the last two (late comments, index lag)
            if k in rec and w < weeks[-2]:
                continue
            a, b = int(w.timestamp()), int((w + pd.Timedelta(weeks=1)).timestamp())
            try:
                st = parse_hn(json.loads(download(HN.format(q=quote(i["query"]), tag="story", a=a, b=b), "hn")))
                cm = parse_hn(json.loads(download(HN.format(q=quote(i["query"]), tag="comment", a=a, b=b), "hn")))
                rec[k] = [st, cm]
                out["hn"].append(True)
            except Exception as e:
                out["hn"].append(f"{type(e).__name__}: {str(e)[:100]}")
                done[f"hn {i['key']}"] = out["hn"][-1]
                break
        for k in [k for k in rec if k != "_q" and k not in keep]:
            rec.pop(k)
        save("hn", store)               # after each topic: the first backfill takes minutes and a redeploy must not lose it


def count_bsky(q: str, day: pd.Timestamp) -> tuple[int, bool]:
    """Posts matching q on one UTC day, paging up to BSKY_PAGES; (count, capped)."""
    a, b = day.strftime("%Y-%m-%dT00:00:00Z"), (day + pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    n, cursor = 0, None
    for _ in range(BSKY_PAGES):
        url = BSKY.format(q=quote(q), a=a, b=b) + (f"&cursor={quote(cursor)}" if cursor else "")
        j = json.loads(download(url, "bsky", BOT))
        n += len(j.get("posts") or [])
        cursor = j.get("cursor")
        if not cursor or not j.get("posts"):
            return n, False
    return n, True


def fill_social(items: list[dict], out: dict, log: list, done: dict) -> None:
    yday = _now() - pd.Timedelta(days=1)
    for i in [i for i in items if i.get("social") == "y" and i.get("query")]:
        try:
            n, capped = count_bsky(i["query"], yday)
            log.append(("bsky", i["key"], "posts", n))
            if capped:
                log.append(("bsky", i["key"], "capped", 1))
            out["bsky"].append(True)
        except Exception as e:
            out["bsky"].append(f"{type(e).__name__}: {str(e)[:100]}")
            done[f"bsky {i['key']}"] = out["bsky"][-1]
            if len(out["bsky"]) >= 2 and not any(o is True for o in out["bsky"]):
                break                       # refused twice: the source is closed to this server, stop asking
    for s in subreddits():
        last = None
        for u in REDDIT:
            try:
                d = parse_reddit(json.loads(download(u.format(sub=s["subreddit"]), "reddit", BOT)))
                log.extend(("reddit", s["subreddit"], k, d[k]) for k in ("subscribers", "active") if d.get(k) is not None)
                last = True
                break
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:100]}"
        out["reddit"].append(last)
        if last is not True:
            done[f"reddit {s['subreddit']}"] = last
            if len(out["reddit"]) >= 2 and not any(o is True for o in out["reddit"]):
                break
    for r in repos():
        try:
            d = parse_github(json.loads(download(GITHUB.format(repo=r["repo"]), "github", {"Accept": "application/vnd.github+json", "User-Agent": BOT["User-Agent"]})))
            log.extend(("github", r["repo"], k, d[k]) for k in ("stars", "forks") if d.get(k) is not None)
            out["github"].append(True)
        except Exception as e:
            out["github"].append(f"{type(e).__name__}: {str(e)[:100]}")
            done[f"github {r['repo']}"] = out["github"][-1]


def reality_url(r: dict) -> str:
    return f"{site()}/api/{r['slug']}/{r['endpoint']}"


def fill_reality(done: dict) -> None:
    """The other dashboards' headline series, through this site's own API (fetch keeps a snapshot of each)."""
    for u in sorted({reality_url(r) for r in reality_rows()}):
        try:
            _pace("site")
            fetch(u, 12 * 3600, timeout=180, min_bytes=20)
            done[f"site {u.split('/api/')[1]}"] = "ok"
        except Exception as e:
            done[f"site {u.split('/api/')[1]}"] = f"{type(e).__name__}: {str(e)[:100]}"


def fill() -> dict:
    """Background job: Wikipedia titles and pageviews, HN weekly counts, Bluesky, Reddit and GitHub (logged once a day), the other
    dashboards' series. Returns {what: 'ok' | error}."""
    items, done, log = topics_list(), {}, []
    out: dict[str, list] = {k: [] for k in HEALTH_KEYS}
    def social():
        fill_social(items, out, log, done)
        done["log"] = f"{log_today(log)} rows"
    # quick steps first and each one saved as it ends: every push to main redeploys, and the HN backfill is the slow one
    for name, fn in (("wiki", lambda: fill_wiki(items, out, done)), ("reality", lambda: fill_reality(done)), ("social", social),
                     ("hn", lambda: fill_hn(items, out, done))):
        try:
            fn()
        except Exception as e:
            done[name] = f"{type(e).__name__}: {str(e)[:100]}"
        if name != "hn":
            _health({k: v for k, v in out.items() if v})
            _uncache()
    _health(out)
    state = load("state")
    state.update(fill_at=time.time(), fill={k: v for k, v in done.items() if v != "ok"}, counts={k: [sum(o is True for o in v), len(v)] for k, v in out.items()})
    save("state", state)
    _uncache()
    return done


def _uncache() -> None:
    from ..cache import _cache
    for k in [k for k in _cache if k.startswith(f"topic:{SLUG}:") and not k.endswith(":layout")]:   # the next view rebuilds from fresh data
        _cache.pop(k, None)


BACKGROUND = [fill]


# ------------------------------------------------------------------ the arithmetic
def daily(key: str, store: dict | None = None) -> pd.Series:
    rec = (store if store is not None else load("wiki")).get(key) or {}
    d = rec.get("days") or {}
    if not d:
        return _empty()
    s = pd.Series(d, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def weekly_full(s: pd.Series) -> pd.Series:
    """Weekly sums (weeks ending Sunday), complete weeks only."""
    s = s.dropna()
    if s.empty:
        return s
    g = s.resample("W-SUN")
    w, n = g.sum(), g.count()
    return w[n == 7]


def rolling_z(w: pd.Series, n: int = YEAR, min_n: int = MIN_WEEKS) -> pd.Series:
    """Each week's log views against the previous n weeks (mean and standard deviation, the sd floored at 0.05 so a flat topic does
    not explode)."""
    x = np.log1p(w.astype(float))
    prev = x.shift(1).rolling(n, min_periods=min_n)
    return ((x - prev.mean()) / prev.std().clip(lower=0.05)).dropna()


def index100(w: pd.Series, n: int = YEAR, min_n: int = MIN_WEEKS) -> pd.Series:
    """Each week as a share of the topic's own average over the previous n weeks, x100."""
    base = w.shift(1).rolling(n, min_periods=min_n).mean()
    return (100 * w / base).replace([np.inf, -np.inf], np.nan).dropna()


def geo_mean(frames: list[pd.Series]) -> pd.Series:
    """Geometric mean across series on their common dates (each must have a value that week)."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return _empty()
    d = pd.concat(frames, axis=1, sort=True)
    lg = np.log(d.where(d > 0))
    return np.exp(lg.mean(axis=1, skipna=True))[lg.notna().sum(axis=1) >= max(1, math.ceil(len(frames) / 2))]


def total(frames: list[pd.Series], min_count: int = 1) -> pd.Series:
    """Sum across series by date (a date needs at least min_count of them)."""
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, axis=1, sort=True).sum(axis=1, min_count=min_count).dropna() if frames else _empty()


def accel(w: pd.Series) -> dict:
    """Latest week against the 4 and 13 weeks before it, and whether the 4-week average crossed the 13-week one in the last two weeks."""
    if len(w) < 15:
        return {"a4": None, "a13": None, "cross": None, "cross_date": None}
    last = w.iloc[-1]
    a4 = last / w.iloc[-5:-1].mean() - 1 if w.iloc[-5:-1].mean() else None
    a13 = last / w.iloc[-14:-1].mean() - 1 if w.iloc[-14:-1].mean() else None
    gap = (w.rolling(4).mean() - w.rolling(13).mean()).dropna()
    cross = cross_date = None
    for k in (1, 2):
        if len(gap) > k and np.sign(gap.iloc[-k]) != np.sign(gap.iloc[-k - 1]) and gap.iloc[-k] != 0:
            cross, cross_date = ("up" if gap.iloc[-k] > 0 else "down"), str(gap.index[-k].date())
            break
    return {"a4": _r(a4, 4), "a13": _r(a13, 4), "cross": cross, "cross_date": cross_date}


def breakouts(s: pd.Series, days: int = 30, k: float = 4.0) -> list[dict]:
    """Days in the last `days` whose log views sit k robust deviations above the previous 8 weeks' median, and at least double it."""
    s = s.dropna()
    if len(s) < 70:
        return []
    x = np.log1p(s)
    med = x.shift(1).rolling(56, min_periods=40).median()
    mad = (x.shift(1) - med).abs().rolling(56, min_periods=40).median() * 1.4826
    score = (x - med) / mad.clip(lower=0.1)
    mult = s / np.expm1(med)
    hit = (score > k) & (mult >= 2)
    hit = hit[hit.index > s.index[-1] - pd.Timedelta(days=days)]
    return [{"date": str(t.date()), "views": int(s[t]), "multiple": _r(mult[t], 2), "score": _r(score[t], 2)} for t in hit[hit].index]


def topic_stats(items: list[dict], store: dict) -> list[dict]:
    """Per topic: the latest full week's views, z-score against its year, acceleration, crossings and breakouts."""
    out = []
    for i in items:
        s = daily(i["key"], store)
        w = weekly_full(s)
        z = rolling_z(w)
        rec = {k: i.get(k) for k in ("key", "label", "theme", "region", "lang", "article")}
        rec.update(title=(store.get(i["key"]) or {}).get("title"), week=str(w.index[-1].date()) if len(w) else None,
                   views=int(w.iloc[-1]) if len(w) else None, z=_r(z.iloc[-1], 2) if len(z) and z.index[-1] == w.index[-1] else None,
                   z_prev=_r(z.iloc[-2], 2) if len(z) > 1 else None, **accel(w), breakouts=breakouts(s))
        out.append(rec)
    return out


def _lean(z, t: float = Z_LEAN) -> int:
    return 0 if z is None else 1 if z >= t else -1 if z <= -t else 0


# ------------------------------------------------------------------ the other dashboards' series
def series_paths(j, prefix: str = "", out: list | None = None) -> list[tuple[str, int]]:
    """Every [[unix seconds, number], ...] list in a payload, as (dotted path, length)."""
    out = [] if out is None else out
    if isinstance(j, dict):
        for k, v in j.items():
            series_paths(v, f"{prefix}.{k}" if prefix else str(k), out)
    # unix seconds: a history starting before 1973 (temperatures since 1880, launches since 1957) has negative or small first times
    elif (isinstance(j, list) and len(j) >= 3 and all(isinstance(p, list) and len(p) == 2 and isinstance(p[0], (int, float)) for p in j[:5] + j[-1:])
          and j[-1][0] > 1e8):
        out.append((prefix, len(j)))
    return out


def pick(j, path: str) -> list | None:
    """The points at a dotted path; '*' as the last part (or the whole path) takes the longest series under what came before."""
    parts = [p for p in path.split(".") if p]
    cur = j
    for n, p in enumerate(parts):
        if p == "*":
            found = series_paths(cur)
            return pick(cur, max(found, key=lambda x: x[1])[0]) if found else None
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if series_paths(cur) else None


def to_series(points) -> pd.Series:
    s = pd.Series({pd.to_datetime(int(t), unit="s"): v for t, v in points or [] if v is not None}, dtype=float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def lead_lag(att: pd.Series, real: pd.Series, max_lag: int = 3) -> dict:
    """Monthly: correlation of log levels, of 3-month log changes, and the lag (months, + = attention moves first) where the changes
    line up best."""
    a, r = np.log(att.where(att > 0)).dropna(), np.log(real.where(real > 0)).dropna()
    both = pd.concat([a, r], axis=1, keys=["a", "r"], sort=True).dropna()
    if len(both) < 12:
        return {"n": len(both), "level": None, "change": None, "best_lag": None, "best_corr": None}
    da, dr = both["a"].diff(3), both["r"].diff(3)
    lags = {}
    for k in range(-max_lag, max_lag + 1):
        c = da.corr(dr.shift(-k))
        if c == c:
            lags[k] = c
    best = max(lags, key=lambda k: abs(lags[k])) if lags else None
    return {"n": len(both), "level": _r(both["a"].corr(both["r"]), 3), "change": _r(da.corr(dr), 3), "best_lag": best,
            "best_corr": _r(lags[best], 3) if best is not None else None, "lags": {str(k): _r(v, 3) for k, v in lags.items()}}


# ------------------------------------------------------------------ tab payloads (read the store only)
def _meta(state: dict) -> dict:
    return {"fill_at": state.get("fill_at"), "counts": state.get("counts", {}), "problems": dict(list((state.get("fill") or {}).items())[:30])}


def _as_of(stats: list[dict]) -> str | None:
    ws = [s["week"] for s in stats if s.get("week")]
    return max(ws) if ws else None


def _stale() -> dict:
    return {u: pd.Timestamp(B.STALE[u], unit="s").strftime("%Y-%m-%d") for u in HEALTH_KEYS.values() if u in B.STALE}


def _theme_index(items, store, region="global", since=None) -> dict[str, pd.Series]:
    out = {}
    for th in THEMES:
        ser = [index100(weekly_full(daily(i["key"], store))) for i in items if i["theme"] == th and i["region"] == region]
        g = geo_mean(ser)
        if len(g):
            out[th] = g if since is None else g[g.index >= since]
    return out


def _overview_now() -> dict:
    items, store = topics_list(), load("wiki")
    stats = topic_stats(items, store)
    glob = [s for s in stats if s["z"] is not None and s["region"] == "global"]
    since = WIKI_START + pd.Timedelta(weeks=YEAR)
    idx = _theme_index(items, store, since=since)
    themes = []
    for th, s in idx.items():
        zs = [x["z"] for x in stats if x["theme"] == th and x["region"] == "global" and x["z"] is not None]
        themes.append({"theme": th, "label": THEMES[th][0], "dashboard": THEMES[th][1], "index": _r(s.iloc[-1], 1), "z": _r(float(np.mean(zs)), 2) if zs else None,
                       "n": len(zs), "points": _pts(s, 1)})
    themes.sort(key=lambda t: -(t["index"] or 0))
    return {"topics": stats, "rising": sorted(glob, key=lambda s: -s["z"])[:12], "fading": sorted(glob, key=lambda s: s["z"])[:6], "themes": themes,
            "as_of": _as_of(stats), "stale": _stale(), "updated": int(time.time()), **_meta(load("state"))}


def _gtrends() -> dict:
    g = manual(SLUG, "gtrends")
    g = g if isinstance(g, dict) else {}
    return {k: _pts(v, 0) for k, v in g.items()}


def _search_now() -> dict:
    items, store = topics_list(), load("wiki")
    stats = {s["key"]: s for s in topic_stats(items, store)}
    since = _now() - pd.Timedelta(days=3 * 365)
    weekly = {i["key"]: weekly_full(daily(i["key"], store)) for i in items if i["region"] == "global"}
    groups = []
    for th, (label, dash) in THEMES.items():
        ks = [i for i in items if i["theme"] == th and i["region"] == "global" and len(weekly.get(i["key"], []))]
        if ks:
            groups.append({"theme": th, "label": label, "dashboard": dash,
                           "lines": [{"key": i["key"], "name": i["label"], "points": _pts(weekly[i["key"]][weekly[i["key"]].index >= since], 0)} for i in ks]})
    tot = total([w for w in weekly.values() if len(w)], min_count=max(1, sum(len(w) > 0 for w in weekly.values()) // 2))
    top = sorted([k for k in weekly if len(weekly[k])], key=lambda k: -weekly[k].iloc[-1])[:5]
    br = sorted([{**b, "key": k, "label": stats[k]["label"], "theme": stats[k]["theme"]} for k in stats for b in stats[k]["breakouts"]],
                key=lambda b: b["date"], reverse=True)
    return {"total": _pts(tot[tot.index >= since], 0), "top": [{"key": k, "name": stats[k]["label"], "points": _pts(weekly[k][weekly[k].index >= since], 0)} for k in top],
            "groups": groups, "breakouts": br[:40], "gtrends": _gtrends(), "gtrends_cited": manual_sources(SLUG, "gtrends")[:10],
            "table": sorted([{k: s[k] for k in ("key", "label", "theme", "region", "title", "week", "views", "z")} for s in stats.values()], key=lambda r: -(r["views"] or 0)),
            "as_of": _as_of(list(stats.values())), "stale": _stale(), "updated": int(time.time())}


def _social_now() -> dict:
    items, hn = topics_list(), load("hn")
    lab = {i["key"]: i["label"] for i in items}
    st, cm = {}, {}
    for k, rec in hn.items():
        if k not in lab:
            continue
        wk = {pd.Timestamp(d) + pd.Timedelta(days=6): v for d, v in rec.items() if d != "_q"}
        if wk:
            st[k] = pd.Series({d: v[0] for d, v in wk.items()}).sort_index()
            cm[k] = pd.Series({d: v[1] for d, v in wk.items()}).sort_index()
    order = sorted(st, key=lambda k: -st[k].iloc[-4:].sum())
    hn_rows = [{"key": k, "label": lab[k], "stories": int(st[k].iloc[-1]), "comments": int(cm[k].iloc[-1]), **{f"s_{n}": _r(st[k].iloc[-1] / st[k].iloc[-n - 1:-1].mean() - 1, 3)
               if len(st[k]) > n and st[k].iloc[-n - 1:-1].mean() else None for n in (4, 13)}} for k in order]
    tot_s, tot_c = total(list(st.values())), total(list(cm.values()))
    bs, capped = _cols(daily_log("bsky", "posts")), _cols(daily_log("bsky", "capped"))
    gh, ghf = _cols(daily_log("github", "stars")), _cols(daily_log("github", "forks"))
    hand = manual(SLUG, "reddit")
    hand = hand if isinstance(hand, dict) else {}
    rs, ra = _merge(_cols(daily_log("reddit", "subscribers")), hand, "subscribers"), _merge(_cols(daily_log("reddit", "active")), hand, "active")
    last = lambda d, k: _r(d[k].iloc[-1], 0) if k in d else None
    repo_lab = {r["repo"]: r["label"] for r in repos()}
    gh_rows = sorted([{"repo": k, "label": repo_lab.get(k, k), "stars": last(gh, k), "forks": last(ghf, k), "d7": gain(s, 7), "d30": gain(s, 30),
                       "since": str(s.index[0].date())} for k, s in gh.items()], key=lambda r: -(r["stars"] or 0))
    sub_theme = {s["subreddit"]: s.get("theme") for s in subreddits()}
    rd_rows = sorted([{"sub": k, "theme": sub_theme.get(k), "subscribers": last(rs, k), "active": last(ra, k), "d30": gain(s, 30), "date": str(s.index[-1].date())}
                      for k, s in rs.items()], key=lambda r: -(r["subscribers"] or 0))
    bs_rows = sorted([{"key": k, "label": lab.get(k, k), "posts": last(bs, k), "capped": bool(k in capped and capped[k].index[-1] == s.index[-1]),
                       "avg7": _r(s.iloc[-7:].mean(), 0), "date": str(s.index[-1].date())} for k, s in bs.items()], key=lambda r: -(r["posts"] or 0))
    return {"hn": {"stories": [{"key": k, "name": lab[k], "points": _pts(st[k], 0)} for k in order[:6]], "comments": [{"key": k, "name": lab[k], "points": _pts(cm[k], 0)} for k in order[:6]],
                   "total_stories": _pts(tot_s, 0), "total_comments": _pts(tot_c, 0), "rows": hn_rows},
            "bsky": {"lines": [{"key": r["key"], "name": r["label"], "points": _pts(bs[r["key"]], 0)} for r in bs_rows[:6]], "rows": bs_rows},
            "github": {"lines": [{"key": r["repo"], "name": r["label"], "points": _pts(gh[r["repo"]], 0)} for r in gh_rows[:6]], "rows": gh_rows},
            "reddit": {"lines": [{"key": r["sub"], "name": "r/" + r["sub"], "points": _pts(rs[r["sub"]], 0)} for r in rd_rows[:6]], "rows": rd_rows,
                       "cited": manual_sources(SLUG, "reddit")[:10]},
            "as_of": str(tot_s.index[-1].date()) if len(tot_s) else None, "stale": _stale(), "updated": int(time.time()), **_meta(load("state"))}


def _cols(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {k: df[k].dropna() for k in df.columns if df[k].notna().any()} if len(df) else {}


def _merge(cols: dict, hand: dict, fld: str) -> dict:
    """Hand-entered Reddit rows ("<sub>|subscribers" or "<sub>|active") fill in the days the server could not read."""
    cols = dict(cols)
    for name, s in hand.items():
        sub, _, f = name.partition("|")
        if (f or "subscribers") == fld and len(s):
            cols[sub] = cols[sub].combine_first(s) if sub in cols else s
    return cols


def gain(s: pd.Series, days: int):
    """Change over the last `days` days of a daily log series (None until it is that old)."""
    prev = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return _r(s.iloc[-1] - prev.iloc[-1], 0) if len(prev) else None


def _rising_now() -> dict:
    items, store = topics_list(), load("wiki")
    stats = topic_stats(items, store)
    since = _now() - pd.Timedelta(days=2 * 365)
    ranked = sorted([s for s in stats if s["a13"] is not None], key=lambda s: -s["a13"])
    pick_ = [s["key"] for s in ranked[:4]] + [s["key"] for s in ranked[-3:] if s["key"] not in [x["key"] for x in ranked[:4]]]
    lab = {s["key"]: s["label"] for s in stats}
    zl = [{"key": k, "name": lab[k], "points": _pts(rolling_z(weekly_full(daily(k, store)))[lambda z: z.index >= since], 2)} for k in pick_]
    return {"rows": ranked, "crossed_up": [s for s in stats if s["cross"] == "up"], "crossed_down": [s for s in stats if s["cross"] == "down"],
            "z_lines": zl, "as_of": _as_of(stats), "stale": _stale(), "updated": int(time.time())}


def _regions_now() -> dict:
    items, store = topics_list(), load("wiki")
    since = WIKI_START + pd.Timedelta(weeks=YEAR)
    reg = {}
    for r, label in REGIONS:
        g = geo_mean([index100(weekly_full(daily(i["key"], store))) for i in items if i["region"] == r])
        if len(g):
            reg[r] = {"label": label, "points": _pts(g[g.index >= since], 1), "now": _r(g.iloc[-1], 1)}
    en, zh = _theme_index(items, store, "global", since), _theme_index(items, store, "zh", since)
    pairs = [{"theme": th, "label": THEMES[th][0], "en": _pts(en[th], 1), "zh": _pts(zh[th], 1), "en_now": _r(en[th].iloc[-1], 1), "zh_now": _r(zh[th].iloc[-1], 1)}
             for th in THEMES if th in en and th in zh]
    stats = topic_stats([i for i in items if i["region"] != "global"], store)
    g = _gtrends()
    geo = {k: v for k, v in g.items() if "|" in k and k.split("|")[1].upper() in ("US", "GB", "UK", "HK", "CN", "TW")}
    return {"regions": reg, "pairs": pairs, "topics": stats, "gtrends": geo, "gtrends_cited": manual_sources(SLUG, "gtrends")[:10],
            "as_of": _as_of(stats), "stale": _stale(), "updated": int(time.time())}


def _reality_now() -> dict:
    items, store = topics_list(), load("wiki")
    out = []
    for r in reality_rows():
        th = r["theme"]
        row = {"theme": th, "label": THEMES.get(th, (th,))[0], "dashboard": r["slug"], "series": r.get("label"), "log": r.get("log") == "y", "path": r.get("path"),
               "source": r.get("source"), "note": r.get("note")}
        ks = [i["key"] for i in items if i["theme"] == th and i["region"] == "global"]
        frames = [daily(k, store) for k in ks]
        frames = [f for f in frames if len(f)]
        att = total(frames)
        att_m = att.resample("MS").mean().dropna() if len(att) else att
        if len(att_m) and att.index[-1] < att_m.index[-1] + pd.Timedelta(days=27):       # drop a month that is not yet finished
            att_m = att_m.iloc[:-1]
        row["attention"] = _pts(att_m, 0)
        try:
            j = json.loads(cached_only(reality_url(r)))
            pts = pick(j, r.get("path") or "*")
            if pts is None:
                row["error"] = f"no series at '{r.get('path')}'"
                row["paths"] = [p for p, _ in series_paths(j)][:20]
            else:
                real = to_series(pts)
                real = real[real.index >= WIKI_START - pd.DateOffset(years=1)]      # the pageviews start in 2016
                real_m = real.resample("MS").last().dropna()
                row["reality"] = _pts(real, 4)
                row["stats"] = lead_lag(att_m, real_m)
                row["as_of"] = str(real.index[-1].date()) if len(real) else None
        except LookupError:
            row["error"] = "not read yet: the background job reads the other dashboards a few minutes after a deploy"
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {str(e)[:100]}"
        out.append(row)
    return {"themes": out, "site": site(), "as_of": max([x["as_of"] for x in out if x.get("as_of")], default=None), "stale": _stale(), "updated": int(time.time())}


# ------------------------------------------------------------------ READINGS
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def readings(got) -> list[dict]:
    """One attention z-score per tracked topic: +1 at +1 or more (rising), -1 at -1 or less (fading). Global topics file under the
    Overview, UK and Chinese pages under US / UK / HK."""
    out = []
    for s in got("overview").get("topics") or []:
        if s.get("z") is None:
            continue
        out.append({"tab": "overview" if s["region"] == "global" else "regions", "key": f"z_{s['key']}", "label": f"{s['label']}: attention z-score",
                    "value": s["z"], "lean": _lean(s["z"]), "note": f"week to {s['week']}, {s['views']:,} views; +1 at z >= {Z_LEAN}, -1 at z <= -{Z_LEAN}"})
    return out


def READINGS() -> list[dict]:
    """From the cached Overview payload only (nothing is fetched or computed)."""
    return readings(_cached_payload)


# ------------------------------------------------------------------ the probe
def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, type, size, first 400 characters), the titles resolved for each
    article, what the last fill could not get, and the series paths found in each other dashboard's payload. Read it with Actions >
    show-json on /api/trends/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    now = _now()
    wk = _weeks(1, now)[0]
    urls = {"wikimedia en": wiki_url("en", "Bitcoin", now - pd.Timedelta(days=10), now - pd.Timedelta(days=1)),
            "wikimedia zh": wiki_url("zh", "比特币", now - pd.Timedelta(days=10), now - pd.Timedelta(days=1)),
            "wiki titles en": WIKI_TITLES.format(lang="en", titles=quote("AI agent|Solana (blockchain platform)|Zoox (company)|Housing crisis in the United Kingdom", safe="")),
            "wiki titles zh": WIKI_TITLES.format(lang="zh", titles=quote("比特币|深度求索|宝可梦|宝可梦集换式卡牌游戏|特斯拉公司|英伟达|恒生指数", safe="")),
            "hn algolia": HN.format(q="bitcoin", tag="story", a=int(wk.timestamp()), b=int((wk + pd.Timedelta(weeks=1)).timestamp())),
            "bluesky": BSKY.format(q="bitcoin", a=(now - pd.Timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"), b=now.strftime("%Y-%m-%dT00:00:00Z")),
            "bluesky public host": "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=bitcoin&limit=1",
            "reddit www": REDDIT[0].format(sub="Bitcoin"), "reddit old": REDDIT[1].format(sub="Bitcoin"), "reddit api": REDDIT[2].format(sub="Bitcoin"),
            "github": GITHUB.format(repo="pytorch/pytorch"), "google trends": GTRENDS, "own site": f"{site()}/api/index"}

    def one(item):
        k, u = item
        h = {**B.UA, **BOT} if not k.startswith("github") else {**BOT, "Accept": "application/vnd.github+json"}
        try:
            r = requests.get(u, headers=h, timeout=25)
            body = r.text
            return k, {"status": r.status_code, "url": u, "type": r.headers.get("content-type", ""), "bytes": len(r.content), "start": body[:400],
                       **({"ratelimit_remaining": r.headers.get("x-ratelimit-remaining")} if "ratelimit-remaining" in str(r.headers).lower() else {})}
        except Exception as e:
            return k, {"url": u, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = dict(ex.map(one, urls.items()))
    paths = {}
    for r in reality_rows():
        try:
            paths[f"{r['slug']}/{r['endpoint']}"] = series_paths(json.loads(cached_only(reality_url(r))))[:30]
        except Exception as e:
            paths[f"{r['slug']}/{r['endpoint']}"] = type(e).__name__
    store = load("wiki")
    out["_titles"] = {k: v.get("title") for k, v in load("titles").items()}
    out["_stored"] = {k: {"title": v.get("title"), "days": len(v.get("days") or {}), "last": max(v.get("days") or {"": 0})} for k, v in store.items()}
    out["_state"] = load("state")
    out["_reality_paths"] = paths
    return out


def _cached_ep(name, fn, ttl=3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"overview": _cached_ep("overview", _overview_now), "search": _cached_ep("search", _search_now), "social": _cached_ep("social", _social_now),
             "rising": _cached_ep("rising", _rising_now), "regions": _cached_ep("regions", _regions_now), "reality": _cached_ep("reality", _reality_now),
             "layout": _cached_ep("layout", _layout_now, 1800)}
