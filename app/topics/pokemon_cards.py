"""Pokémon Card Market (/pokemon-cards): is the market overheating or cooling?

heat       the composite: each signal as a z-score against its own last 3 years (at least 1 year), averaged and clipped to -2 (cold)
           ... +2 (overheated); which signals drive it now, each signal's own gauge, the composite month by month
prices     equal-weight indices of three baskets (vintage WotC holos, modern chase / alt-art cards, sealed products) from PriceCharting's
           monthly price history (TCGplayer's sales history when PriceCharting cannot be read), and the basket itself (basket.csv)
overheat   30- and 90-day momentum, breadth (share above the 200-day average), sealed price / MSRP, new-set booster box premium,
           PSA grading volume (hand-entered), search interest (hand-entered), TCGplayer units sold, sell-out and scalping news (hand-entered)
cooldown   the same market read for signs of a turn: momentum and breadth rolling over, sealed premium compressing, listings rising
           faster than sales, the PSA 10 premium shrinking, search fading, reprint announcements
grading    PSA 10 / raw price ratio over time (PriceCharting), population counts for key cards and PSA volumes (hand-entered)
regions    US (TCGplayer, USD) vs UK/EU (Cardmarket, EUR and GBP) for the same cards (TCGdex, else pokemontcg.io), Japan (hand-entered JPY set
           prices) and Hong Kong shop notes: where the market is hottest

Downloads are slow and paced (BACKGROUND fill(), like btc_cycles): PriceCharting and TCGplayer pages one at a time, PACE seconds apart,
each at most once per MAX_AGE. Pages only read what the fill already has. A daily log of current prices and listings (TCGdex,
TCGplayer) is kept on the snapshot volume so day-by-day history builds up from launch.

Leans in READINGS(): +1 means the signal is heating (above its own history), -1 cooling, 0 neutral (data/pokemon-cards/README.md).
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote, quote_plus

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from ._base import DAY, _pts, _r, cached_only, fetch, manual_rows, manual_sources

SLUG = "pokemon-cards"
TOPIC = Topic(SLUG, "Pokémon Card Market",
              "Is the Pokémon card market overheating or cooling? A composite heat score from momentum, breadth, sealed premiums, grading, "
              "search interest and sales, with price indices for vintage, modern and sealed, grading ratios, and the US, UK/EU and Japan/HK.",
              "pokemon_cards", (("heat", "Heat gauge"), ("prices", "Prices"), ("overheat", "Overheat signals"), ("cooldown", "Cooldown signals"),
                                ("grading", "Grading"), ("regions", "US / UK / HK")),
              ("heat", "prices", "overheat", "cooldown", "grading", "regions"), icon="cards", order=35)

PC_BASE = "https://www.pricecharting.com"
PC_SEARCH = PC_BASE + "/search-products?type=prices&q={q}"
TCGDEX = "https://api.tcgdex.net/v2/en/cards/{id}"
PTCG = "https://api.pokemontcg.io/v2/cards?q={q}&select=id,name,number,rarity,set,tcgplayer,cardmarket&pageSize=250"
TCG_HISTORY = "https://infinite-api.tcgplayer.com/price/history/{pid}/detailed?range=annual"
TCG_DETAILS = "https://mp-search-api.tcgplayer.com/v2/product/{pid}/details"
FX = "https://api.frankfurter.app/latest?from=USD&to=EUR,GBP,JPY,HKD"
FX_FALLBACK = "https://open.er-api.com/v6/latest/USD"
# PriceCharting answers 400 "unauthorized request" (JSON) to the shared UA's Accept (csv, json): ask for a web page
PC_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
TCG_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.tcgplayer.com", "Referer": "https://www.tcgplayer.com/"}

PACE = 8.0                       # seconds between downloads from the same shop site in the background fill
MAX_AGE = {"pc": 3 * DAY, "tcg": 20 * 3600, "ptcg": 20 * 3600, "tcgdex": 20 * 3600, "fx": 20 * 3600}
WINDOW_DAYS = 3 * 365            # z-scores against the last 3 years ...
MIN_N = {"M": 12, "W": 52, "E": 4}   # ... with at least a year of monthly (M) or weekly (W) points, or 4 earlier sets (E)
MIN_N_SIGNAL = {"search": 8, "psa_volume": 8, "sales": 26}   # hand-entered series may be quarterly; TCGplayer gives one year of weeks
SEGMENTS = (("vintage", "Vintage WotC holos"), ("modern", "Modern chase / alt-art"), ("sealed", "Sealed products"))

SOURCES = [{"name": "PriceCharting: monthly price history per card and product, ungraded and PSA 10", "url": "https://www.pricecharting.com/category/pokemon-cards", "cadence": "every 3 days"},
           {"name": "TCGdex API: TCGplayer market and Cardmarket trend prices per card (pokemontcg.io when TCGdex misses)", "url": "https://tcgdex.dev/", "cadence": "daily"},
           {"name": "TCGplayer: sales history (units sold) and current listings", "url": "https://www.tcgplayer.com/", "cadence": "daily"},
           {"name": "Frankfurter (ECB reference rates): USD to EUR, GBP, JPY, HKD", "url": "https://www.frankfurter.app/", "cadence": "daily"},
           {"name": "Hand-entered, cited per row: Google Trends, PSA / GemRate grading volumes and populations, Japanese prices (Yuyutei, Snkrdunk), "
                    "HK shop notes, sell-out, scalping and reprint news", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/pokemon-cards",
            "cadence": "monthly / as it happens"}]
NOTES = ("The heat score compares each signal with its own last three years, so +2 means 'far hotter than usual for this signal', not 'prices "
         "will fall'. Prices are market prices for near-mint raw cards and sealed products in USD unless stated. Baskets are equal-weight and "
         "chain-linked, so a card joining or leaving does not move the index. Rows marked 'verify' were entered from memory and still need "
         "checking against the cited page. Not investment advice.")

# ------------------------------------------------------------------ the signals: key -> (label, sign, frequency, plain words)
SIGNALS = {
    "mom30": ("30-day momentum", +1, "M", "Change in the whole basket over the last month. Fast rises mean buyers are chasing; a market that "
              "keeps rising month after month, far above its usual pace, is the first sign of froth."),
    "mom90": ("90-day momentum", +1, "M", "Change over three months: slower and steadier than the 30-day reading, so it shows the trend rather than one hot release."),
    "breadth": ("Breadth (share above 200-day average)", +1, "M", "Share of the basket trading above its own 200-day (7-month) average. "
                "Near 100% means everything is rising at once, which is how manias look; a falling share while the index still rises means a few cards carry it."),
    "sealed_msrp": ("Sealed price / MSRP", +1, "M", "Median sealed product price as a multiple of its retail price. Sealed is what speculators stack; "
                    "a high multiple says people are buying to hold, not to open."),
    "new_set": ("New-set booster box premium", +1, "E", "Booster box price a few weeks after release as a multiple of MSRP, for each new set. "
                "Boxes normally trade near or below MSRP after release; boxes selling well above it at launch mean demand outruns the print run."),
    "psa10_ratio": ("PSA 10 premium over raw", +1, "M", "Median PSA 10 price divided by the raw (ungraded) price. Collectors pay up for perfect copies "
                    "when money is loose; the premium shrinks first when it is not."),
    "psa_volume": ("PSA grading volume", +1, "M", "Pokémon cards graded per month (hand-entered). A grading boom means people expect to sell at a profit after fees and waiting."),
    "search": ("Search interest ('pokemon cards')", +1, "M", "Google Trends, US, monthly (hand-entered). New buyers search first; spikes mark when the general public joins."),
    "sales": ("TCGplayer units sold", +1, "W", "Units of the basket's cards sold on TCGplayer per week. Rising turnover with rising prices is real demand."),
    "news": ("Sell-out and scalping news", +1, "M", "Dated, cited reports of sell-outs, purchase limits and scalping in the last 90 days (hand-entered)."),
    "reprints": ("Reprint announcements", -1, "M", "Dated, cited reprint and restock announcements in the last 90 days. Reprints add supply: they cool sealed prices."),
    "overhang": ("Listings vs sales (supply overhang)", -1, "D", "30-day change in TCGplayer listings minus the change in units sold. Listings piling up faster than "
                 "sales means holders want out: a cooling sign."),
}


def _now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None).normalize()


def _f(v):
    try:
        v = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


# ------------------------------------------------------------------ the basket and hand-entered files
def basket() -> list[dict]:
    out = []
    for r in manual_rows(SLUG, "basket"):
        if r.get("key") and r.get("segment") in dict(SEGMENTS):
            out.append({**r, "msrp": _f(r.get("msrp_usd"))})
    return out


def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: r["date"])


def hand(name: str) -> dict[str, pd.Series]:
    s = B.manual(SLUG, name)
    return s if isinstance(s, dict) else ({"value": s} if len(s) else {})


def cited(*names) -> list[dict]:
    out = [x for n in names for x in manual_sources(SLUG, n)]
    return sorted(out, key=lambda x: x["date"], reverse=True)[:12]


# ------------------------------------------------------------------ parsers
def parse_pc_chart(html: str) -> dict[str, pd.Series]:
    """PriceCharting product page: VGPC.chart_data = {"used": [[ms, cents], ...], "manualonly": ...}. For cards 'used' is ungraded and
    'manualonly' PSA 10 ('graded' is grade 9); for sealed products 'used' is the price. Monthly USD series, zeros dropped."""
    m = re.search(r"VGPC\.chart_data\s*=\s*(\{.*?\})\s*;", html, re.S)
    if not m:
        raise ValueError("PriceCharting: no chart_data on the page (layout changed?)")
    j = json.loads(m.group(1))
    out = {}
    for k, pts in j.items():
        s = pd.Series({pd.to_datetime(int(t), unit="ms").to_period("M").to_timestamp(): v / 100 for t, v in (pts or []) if v and float(v) > 0}, dtype=float)
        if len(s):
            out[k] = s[~s.index.duplicated(keep="last")].sort_index()
    if not out:
        raise ValueError("PriceCharting: chart_data is empty")
    return out


def parse_pc_search(html: str) -> str | None:
    """The first product link on a PriceCharting search results page (/game/<console>/<product>)."""
    m = re.search(r'href="(?:https://www\.pricecharting\.com)?/game/(pokemon-[^"/?#]+/[^"?#]+)[?#"]', html)
    return m.group(1) if m else None


TCG_VARIANTS = ("holofoil", "unlimitedHolofoil", "1stEditionHolofoil", "normal", "reverseHolofoil", "1stEdition", "unlimited")


def parse_ptcg(j: dict, variants: dict | None = None) -> dict[str, dict]:
    """pokemontcg.io /v2/cards: per card id the TCGplayer market price (USD, the variant asked for or the first present) and Cardmarket's
    trend and 1/7/30-day averages (EUR)."""
    out = {}
    for c in (j or {}).get("data") or []:
        tp = (c.get("tcgplayer") or {}).get("prices") or {}
        want = (variants or {}).get(c.get("id"))
        order = ([want] if want else []) + [v for v in TCG_VARIANTS if v != want] + [v for v in tp if v not in TCG_VARIANTS]
        var = next((v for v in order if isinstance(tp.get(v), dict) and (_f(tp[v].get("market")) or _f(tp[v].get("mid")))), None)
        cm = (c.get("cardmarket") or {}).get("prices") or {}
        out[c["id"]] = {"name": c.get("name"), "set": (c.get("set") or {}).get("name"), "tcg_variant": var,
                        "tcg": (_f(tp[var].get("market")) or _f(tp[var].get("mid"))) if var else None,
                        "tcg_url": (c.get("tcgplayer") or {}).get("url"), "tcg_updated": (c.get("tcgplayer") or {}).get("updatedAt"),
                        "cm_trend": _f(cm.get("trendPrice")), "cm_avg1": _f(cm.get("avg1")), "cm_avg7": _f(cm.get("avg7")), "cm_avg30": _f(cm.get("avg30")),
                        "cm_low": _f(cm.get("lowPrice")), "cm_url": (c.get("cardmarket") or {}).get("url"), "cm_updated": (c.get("cardmarket") or {}).get("updatedAt")}
    return out


TCGDEX_VARIANTS = ("holofoil", "unlimited-holofoil", "unlimitedHolofoil", "normal", "1st-edition-holofoil", "1stEditionHolofoil", "reverse-holofoil")


def parse_tcgdex(j: dict, want: str | None = None) -> dict:
    """TCGdex /v2/en/cards/<id>: pricing.cardmarket {trend, avg1, avg7, avg30, low} in EUR and pricing.tcgplayer.<variant>
    {productId, marketPrice, midPrice} in USD; the same fields as parse_ptcg plus the TCGplayer product id."""
    pr = (j or {}).get("pricing") or {}
    cm, tp = pr.get("cardmarket") or {}, pr.get("tcgplayer") or {}
    order = ([want] if want else []) + [v for v in TCGDEX_VARIANTS if v != want] + [v for v in tp if v not in TCGDEX_VARIANTS]
    var = next((v for v in order if isinstance(tp.get(v), dict) and (_f(tp[v].get("marketPrice")) or _f(tp[v].get("midPrice")))), None)
    pid = (tp.get(var) or {}).get("productId") if var else None
    if not pid:
        pid = next((v.get("thirdParty", {}).get("tcgplayer") for v in (j or {}).get("variants_detailed") or [] if (v.get("thirdParty") or {}).get("tcgplayer")), None)
    if not cm and not var:
        raise ValueError("TCGdex: no pricing for " + str((j or {}).get("id")))
    return {"name": (j or {}).get("name"), "set": ((j or {}).get("set") or {}).get("name"), "tcg_variant": var,
            "tcg": (_f(tp[var].get("marketPrice")) or _f(tp[var].get("midPrice"))) if var else None, "tcg_pid": str(int(pid)) if _f(pid) else None,
            "tcg_url": f"https://www.tcgplayer.com/product/{int(pid)}" if _f(pid) else None, "tcg_updated": str(tp.get("updated") or "")[:10] or None,
            "cm_trend": _f(cm.get("trend")), "cm_avg1": _f(cm.get("avg1")), "cm_avg7": _f(cm.get("avg7")), "cm_avg30": _f(cm.get("avg30")), "cm_low": _f(cm.get("low")),
            "cm_url": f"https://www.cardmarket.com/en/Pokemon/Products?idProduct={cm['idProduct']}" if cm.get("idProduct") else None,
            "cm_updated": str(cm.get("updated") or "")[:10] or None, "from": "TCGdex"}


def tcgdex_url(item: dict) -> str | None:
    i = (item.get("tcgdex_id") or item.get("ptcg_id") or "").strip()
    return TCGDEX.format(id=i) if i else None


def parse_tcg_history(j: dict) -> pd.DataFrame:
    """TCGplayer price history (range=annual): one result per SKU with weekly buckets {bucketStartDate, marketPrice, quantitySold,
    transactionCount}. Returns weekly rows: price (of the SKU that sold most) and units sold (all SKUs)."""
    res = (j or {}).get("result") or []
    if not res:
        raise ValueError("TCGplayer history: no results")
    frames, best, best_n = [], None, -1
    for r in res:
        b = pd.DataFrame(r.get("buckets") or [])
        if b.empty or "bucketStartDate" not in b:
            continue
        b.index = pd.to_datetime(b["bucketStartDate"]).dt.normalize()
        q = pd.to_numeric(b.get("quantitySold"), errors="coerce").fillna(0)
        frames.append(q)
        n = _f(r.get("totalQuantitySold")) or float(q.sum())
        if n > best_n:
            best, best_n = pd.to_numeric(b.get("marketPrice"), errors="coerce"), n
    if best is None:
        raise ValueError("TCGplayer history: no buckets")
    qty = pd.concat(frames, axis=1).sum(axis=1)
    df = pd.DataFrame({"price": best.replace(0, np.nan), "qty": qty}).sort_index()
    return df[~df.index.duplicated(keep="last")]


def parse_tcg_details(j: dict) -> dict:
    """TCGplayer product details: listings, sellers and market price under whichever key names the API uses."""
    j = (j or {}).get("results", [j])[0] if isinstance((j or {}).get("results"), list) and j.get("results") else (j or {})
    pick = lambda *ks: next((_f(j[k]) for k in ks if k in j and _f(j[k]) is not None), None)
    return {"listings": pick("listings", "totalListings", "listingCount", "listingsCount"), "sellers": pick("sellers", "sellerCount", "totalSellers"),
            "market": pick("marketPrice", "market"), "median": pick("medianPrice", "median"), "lowest": pick("lowestPrice", "lowPrice", "lowest")}


def parse_fx(j: dict) -> dict:
    r = (j or {}).get("rates") or {}
    out = {k: _f(r.get(k)) for k in ("EUR", "GBP", "JPY", "HKD")}
    if not out["EUR"] or not out["GBP"]:
        raise ValueError("FX: no EUR or GBP rate")
    return {**out, "date": (j or {}).get("date") or (j or {}).get("time_last_update_utc", "")[:16]}


# ------------------------------------------------------------------ where each item's data lives
def pc_url(item: dict) -> str | None:
    res = _resolved().get(item["key"], {})
    if res.get("pc"):
        return res["pc"]
    p = (item.get("pricecharting") or "").strip().strip("/")
    return f"{PC_BASE}/game/{p}" if p else None


def tcg_id(item: dict) -> str | None:
    return (item.get("tcgplayer_id") or "").strip() or _resolved().get(item["key"], {}).get("tcg")


def ptcg_url(items: list[dict]) -> str | None:
    ids = sorted({i["ptcg_id"] for i in items if i.get("ptcg_id")})
    return PTCG.format(q=quote("(" + " OR ".join(f"id:{x}" for x in ids) + ")")) if ids else None


def _resolved_file():
    return B.SNAP_DIR / SLUG / "resolved.json"


def _resolved() -> dict:
    try:
        return json.loads(_resolved_file().read_text())
    except (OSError, ValueError):
        return {}


def _save_resolved(d: dict) -> None:
    f = _resolved_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=1, sort_keys=True))


def http_get(url: str, timeout: int = 30, headers: dict | None = None) -> tuple[int, str, str, list[str]]:
    """(status, final url, body, redirect chain) with plain requests, for finding a product's address; not snapshotted."""
    import requests
    r = requests.get(url, headers={**B.UA, **(headers or PC_HEADERS)}, timeout=timeout, allow_redirects=True)
    return r.status_code, r.url, r.text, [h.headers.get("location", "") for h in r.history] + [r.url]


def read(url: str) -> str:
    """What the background fill downloaded for url (memory, else disk). LookupError when it never has."""
    return cached_only(url)


# ------------------------------------------------------------------ the background fill (slow, paced; the only place that downloads)
_last = {"pc": 0.0, "tcg": 0.0, "tcgdex": 0.0}


def _pace(site: str) -> None:
    wait = PACE - (time.time() - _last[site])
    if wait > 0:
        time.sleep(wait)
    _last[site] = time.time()


def polite(url: str, site: str | None, max_age: float, **kw) -> str:
    """Download url unless a disk snapshot younger than max_age exists (then use it), pacing requests to the same site."""
    snap = B._snap(url)
    if snap.exists() and time.time() - snap.stat().st_mtime < max_age:
        try:
            return read(url)
        except LookupError:
            pass
    if site:
        _pace(site)
    return fetch(url, max_age, **kw)


def _resolve_pc(item: dict, res: dict) -> str | None:
    """The PriceCharting page for an item: the path in basket.csv when it has a chart, else the first search result. Kept for 30 days."""
    r = res.setdefault(item["key"], {})
    if r.get("pc") and time.time() - r.get("pc_at", 0) < 30 * DAY:
        return r["pc"]
    cand = pc_url({**item, "key": "\0"})
    try:
        if cand:
            _pace("pc")
            code, final, body, _ = http_get(cand)
            if code == 200 and "chart_data" in body:
                r.update(pc=final if "/game/" in final else cand, pc_at=time.time(), pc_how="basket path")
                return r["pc"]
        _pace("pc")
        code, final, body, _ = http_get(PC_SEARCH.format(q=quote_plus(f"{item['name']} {item.get('set', '')}".strip())))
        if code == 200 and "chart_data" in body and "/game/" in final:
            r.update(pc=final, pc_at=time.time(), pc_how="search (one match)")
        else:
            path = parse_pc_search(body) if code == 200 else None
            if path:
                r.update(pc=f"{PC_BASE}/game/{path}", pc_at=time.time(), pc_how="search (first result)")
    except Exception as e:
        r["pc_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return r.get("pc") or cand


def _resolve_tcg(item: dict, ptcg: dict, res: dict) -> str | None:
    """TCGplayer product id from pokemontcg.io's price link (prices.pokemontcg.io/tcgplayer/<id> redirects to the product page)."""
    if tcg_id(item):
        return tcg_id(item)
    r = res.setdefault(item["key"], {})
    p = ptcg.get(item.get("ptcg_id")) or {}
    if p.get("tcg_pid"):
        r["tcg"] = p["tcg_pid"]
        return r["tcg"]
    link = p.get("tcg_url") or (f"https://prices.pokemontcg.io/tcgplayer/{item['ptcg_id']}" if item.get("ptcg_id") else None)
    if not link or r.get("tcg_tried", 0) > time.time() - 7 * DAY:
        return None
    r["tcg_tried"] = time.time()
    try:
        _, _, _, chain = http_get(link)
        m = next((re.search(r"product(?:/|%2F)(\d+)", u) for u in chain if re.search(r"product(?:/|%2F)(\d+)", u)), None)
        if m:
            r["tcg"] = m.group(1)
    except Exception as e:
        r["tcg_error"] = f"{type(e).__name__}: {str(e)[:80]}"
    return r.get("tcg")


def _log_file():
    return B.SNAP_DIR / SLUG / "daily.csv"


def log_today(rows_: list[tuple], today: str | None = None) -> int:
    """Append today's (key, field, value) rows to the daily log once a day per key and field."""
    today = today or str(_now().date())
    f = _log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    have = set()
    if f.exists():
        have = {tuple(line.split(",")[:3]) for line in f.read_text().splitlines()[1:] if line.startswith(today)}
    new = [(today, k, fld, v) for k, fld, v in rows_ if v is not None and (today, k, fld) not in have]
    if new:
        with f.open("a") as fh:
            if f.stat().st_size == 0:
                fh.write("date,key,field,value\n")
            fh.writelines(f"{d},{k},{fld},{_r(v, 4)}\n" for d, k, fld, v in new)
    return len(new)


def daily_log() -> dict[str, pd.DataFrame]:
    """field -> DataFrame (date x item key) from the daily log."""
    f = _log_file()
    if not f.exists():
        return {}
    d = pd.read_csv(f)
    if d.empty:
        return {}
    d["date"] = pd.to_datetime(d["date"])
    return {fld: g.pivot_table(index="date", columns="key", values="value", aggfunc="last").sort_index() for fld, g in d.groupby("field")}


def fill() -> dict:
    """Background job: FX, TCGdex (one call per card; pokemontcg.io in one call when TCGdex misses most), then each item's PriceCharting page and TCGplayer history and
    listings, one at a time. Logs today's prices and listings. Returns {what: 'ok' | error}."""
    done, items, res = {}, basket(), _resolved()

    def step(name, fn):
        try:
            fn()
            done[name] = "ok"
        except Exception as e:
            done[name] = f"{type(e).__name__}: {str(e)[:80]}"
    step("fx", lambda: _fx(live=True))
    ptcg: dict = {}

    cards = [i for i in items if i.get("ptcg_id")]
    for i in cards:            # TCGdex first (pokemontcg.io answered 500/502 from Railway in October 2026)
        def dex(i=i):
            ptcg[i["ptcg_id"]] = parse_tcgdex(json.loads(polite(tcgdex_url(i), "tcgdex", MAX_AGE["tcgdex"], min_bytes=200)), i.get("variant") or None)
        step(f"tcgdex {i['key']}", dex)

    def get_ptcg():
        missing = [i for i in cards if i["ptcg_id"] not in ptcg]
        u = ptcg_url(missing)
        if u:
            got = parse_ptcg(json.loads(polite(u, None, MAX_AGE["ptcg"], min_bytes=200)), {i["ptcg_id"]: i.get("variant") for i in missing})
            ptcg.update({k: v for k, v in got.items() if k not in ptcg})
    if len([i for i in cards if i["ptcg_id"] not in ptcg]) * 2 > len(cards):     # only when TCGdex missed most cards
        step("pokemontcg.io", get_ptcg)
    log = []
    for i in items:
        p = ptcg.get(i.get("ptcg_id")) or {}
        log += [(i["key"], k, p.get(k)) for k in ("tcg", "cm_trend", "cm_avg1", "cm_avg7", "cm_avg30")]
    for i in items:
        def pc(i=i):
            u = _resolve_pc(i, res)
            if not u:
                raise LookupError("no PriceCharting page")
            parse_pc_chart(polite(u, "pc", MAX_AGE["pc"], min_bytes=500, headers=PC_HEADERS))
        step(f"pc {i['key']}", pc)
        pid = _resolve_tcg(i, ptcg, res)
        if pid:
            step(f"tcg history {i['key']}", lambda pid=pid: parse_tcg_history(json.loads(polite(TCG_HISTORY.format(pid=pid), "tcg", MAX_AGE["tcg"], headers=TCG_HEADERS))))

            def det(i=i, pid=pid):
                d = parse_tcg_details(json.loads(polite(TCG_DETAILS.format(pid=pid), "tcg", MAX_AGE["tcg"], headers=TCG_HEADERS, min_bytes=20)))
                log.extend((i["key"], k, d.get(k)) for k in ("listings", "sellers", "market"))
            step(f"tcg listings {i['key']}", det)
        _save_resolved(res)              # after each item: a redeploy mid-fill keeps what was found
    try:
        done["log"] = f"{log_today(log)} rows"
    except OSError as e:
        done["log"] = f"{type(e).__name__}"
    from ..cache import _cache
    for k in [k for k in _cache if k.startswith(f"topic:{SLUG}:")]:      # the next page view rebuilds from the fresh data
        _cache.pop(k, None)
    return done


BACKGROUND = [fill]


# ------------------------------------------------------------------ reading what the fill has
def _fx(live: bool = False) -> dict:
    for u in (FX, FX_FALLBACK):
        try:
            return parse_fx(json.loads(polite(u, None, MAX_AGE["fx"], min_bytes=30) if live else read(u)))
        except Exception:
            continue
    raise LookupError("no exchange rates yet")


def item_series(item: dict) -> dict:
    """{'raw': monthly USD, 'psa10': monthly USD or None, 'src': where from, 'url'}: PriceCharting, else TCGplayer's weekly history."""
    u = pc_url(item)
    if u:
        try:
            ch = parse_pc_chart(read(u))
            field = (item.get("pc_field") or "used").strip()
            raw = ch.get(field) if field in ch else next((ch[k] for k in ("used", "new", "cib") if k in ch), None)
            if raw is not None and len(raw):
                return {"raw": raw, "psa10": ch.get("manualonly") if item["segment"] != "sealed" else None, "src": "PriceCharting", "url": u}
        except (LookupError, ValueError):
            pass
    pid = tcg_id(item)
    if pid:
        try:
            h = parse_tcg_history(json.loads(read(TCG_HISTORY.format(pid=pid))))
            raw = h["price"].dropna().resample("MS").last().dropna()
            if len(raw):
                return {"raw": raw, "psa10": None, "src": "TCGplayer", "url": f"https://www.tcgplayer.com/product/{pid}"}
        except (LookupError, ValueError):
            pass
    return {"raw": pd.Series(dtype=float), "psa10": None, "src": None, "url": u}


def tcg_weekly(item: dict) -> pd.DataFrame | None:
    pid = tcg_id(item)
    if not pid:
        return None
    try:
        return parse_tcg_history(json.loads(read(TCG_HISTORY.format(pid=pid))))
    except (LookupError, ValueError):
        return None


def ptcg_now() -> dict:
    """Current TCGplayer and Cardmarket prices per pokemontcg.io id: TCGdex, else pokemontcg.io (whatever the fill has)."""
    items = [i for i in basket() if i.get("ptcg_id")]
    out = {}
    for i in items:
        try:
            out[i["ptcg_id"]] = parse_tcgdex(json.loads(read(tcgdex_url(i))), i.get("variant") or None)
        except (LookupError, ValueError):
            pass
    u = ptcg_url([i for i in items if i["ptcg_id"] not in out])
    if u:
        try:
            got = parse_ptcg(json.loads(read(u)), {i["ptcg_id"]: i.get("variant") for i in items})
            out.update({k: v for k, v in got.items() if k not in out})
        except (LookupError, ValueError):
            pass
    return out


def panel(field: str = "raw", start: str = "2014-01-01") -> tuple[pd.DataFrame, list[dict]]:
    """Monthly prices, one column per basket item (USD), and the items with where their data came from."""
    cols, meta = {}, []
    for i in basket():
        s = item_series(i)
        x = s.get(field)
        if x is not None and len(x):
            cols[i["key"]] = x[x.index >= pd.Timestamp(start)]
        meta.append({**i, "src": s["src"], "url": s["url"]})
    df = pd.DataFrame(cols).sort_index()
    if len(df):
        last = _now().to_period("M").to_timestamp()
        df = df[df.index <= last].ffill(limit=2)          # a month with no sale keeps the last price for up to two months
    return df, meta


def chain_index(df: pd.DataFrame, min_items: int = 3) -> pd.Series:
    """Equal-weight chain-linked index (100 at its first month with min_items prices): each month's change is the mean log change of the
    items priced in both months, so an item joining or leaving does not move it. Single-month moves are capped at +-150 log points."""
    if df.empty:
        return pd.Series(dtype=float)
    r = np.log(df).diff().clip(-1.5, 1.5)
    n = r.notna().sum(axis=1)
    m = r.mean(axis=1).where(n >= min_items)
    have = df.notna().sum(axis=1)
    start = have[have >= min_items].index.min() if (have >= min_items).any() else None
    if start is None:
        return pd.Series(dtype=float)
    m = m[m.index >= start].fillna(0)
    m.iloc[0] = 0.0
    return 100 * np.exp(m.cumsum())


def rolling_z(s: pd.Series, min_n: int = 12, window_days: int = WINDOW_DAYS) -> pd.Series:
    """Each point against the points of the window_days before it (itself included): (x - mean) / std, needing min_n points; clipped to +-3."""
    s = s.dropna().sort_index()
    out = {}
    for t, v in s.items():
        w = s[(s.index > t - pd.Timedelta(days=window_days)) & (s.index <= t)]
        if len(w) < min_n:
            continue
        sd = float(w.std(ddof=0))
        out[t] = 0.0 if sd == 0 else float(np.clip((v - w.mean()) / sd, -3, 3))
    return pd.Series(out, dtype=float)


def _events(kinds: tuple, months: pd.DatetimeIndex) -> pd.Series:
    ds = [pd.Timestamp(r["date"]) for r in rows("events") if r.get("kind", "").lower() in kinds]
    if not ds:
        return pd.Series(dtype=float)
    first = min(ds).to_period("M").to_timestamp()
    idx = months[months >= first] if len(months) else pd.date_range(first, _now(), freq="MS")
    ends = {t: t + pd.offsets.MonthEnd(0) for t in idx}
    return pd.Series({t: float(sum(e - pd.Timedelta(days=90) < d <= e for d in ds)) for t, e in ends.items()}, dtype=float)


def new_set_premiums(items: list[dict], prices: pd.DataFrame) -> list[dict]:
    """For each booster box with a release date and MSRP: its price in the first month-end at least two weeks after release, / MSRP.
    Hand-entered rows in newset.csv (date = release, value = multiple) are added for sets outside the basket."""
    out = []
    for i in items:
        if i["segment"] != "sealed" or "box" not in (i.get("kind") or "").lower() or "booster" not in (i.get("kind") or "").lower() or not i["msrp"] or i["key"] not in prices:
            continue
        rel = pd.Timestamp(i["date"])
        s = prices[i["key"]].dropna()
        s = s[(s.index + pd.offsets.MonthEnd(0) >= rel + pd.Timedelta(days=14)) & (s.index <= rel + pd.Timedelta(days=75))]
        if len(s):
            out.append({"date": i["date"], "set": i.get("set") or i["name"], "multiple": _r(s.iloc[0] / i["msrp"], 3), "price": _r(s.iloc[0], 2), "msrp": i["msrp"], "from": "PriceCharting"})
    have = {o["set"] for o in out}
    for r in rows("newset"):
        if r.get("series") not in have and _f(r.get("value")):
            out.append({"date": r["date"], "set": r["series"], "multiple": _f(r["value"]), "price": None, "msrp": None, "from": r.get("source")})
    return sorted(out, key=lambda o: o["date"])


def signal_series() -> dict:
    """Every signal as a series (monthly unless stated) with its rolling z-score, plus the pieces the tabs draw."""
    df, meta = panel("raw")
    p10, _ = panel("psa10")
    items = {i["key"]: i for i in meta}
    idx = chain_index(df)
    seg_idx = {k: chain_index(df[[c for c in df if items[c]["segment"] == k]], 2) for k, _ in SEGMENTS}
    sig: dict[str, pd.Series] = {}
    if len(idx):
        sig["mom30"] = idx.pct_change(1, fill_method=None).dropna()
        sig["mom90"] = idx.pct_change(3, fill_method=None).dropna()
        avg = df.rolling(7, min_periods=5).mean()
        above = (df > avg).astype(float).where(avg.notna() & df.notna())
        n = above.notna().sum(axis=1)
        sig["breadth"] = (above.sum(axis=1) / n).where(n >= 3).dropna()
    sealed = [k for k in df if items[k]["segment"] == "sealed" and items[k]["msrp"]]
    if sealed:
        mult = pd.DataFrame({k: df[k] / items[k]["msrp"] for k in sealed})
        # only products already on sale count (a box priced before its release date is a pre-order)
        mult = mult.where(pd.DataFrame({k: mult.index >= pd.Timestamp(items[k]["date"]).to_period("M").to_timestamp() for k in sealed}, index=mult.index))
        sig["sealed_msrp"] = mult.median(axis=1).where(mult.notna().sum(axis=1) >= 2).dropna()
    ns = new_set_premiums(list(items.values()), df)
    if ns:
        sig["new_set"] = pd.Series({pd.Timestamp(o["date"]): o["multiple"] for o in ns}, dtype=float).groupby(level=0).mean()
    both = [k for k in p10 if k in df]
    if both:
        ratio = pd.DataFrame({k: p10[k] / df[k] for k in both}).replace([np.inf, -np.inf], np.nan)
        sig["psa10_ratio"] = ratio.median(axis=1).where(ratio.notna().sum(axis=1) >= 3).dropna()
    H = hand("psa")
    vol = next((v for k, v in H.items() if "graded" in k.lower()), None)
    if vol is not None and len(vol):
        sig["psa_volume"] = vol.rolling(3, min_periods=1).mean()
    T = hand("trends")
    tr = T.get("value") if "value" in T else next(iter(T.values()), None)
    if tr is not None and len(tr):
        sig["search"] = tr
    weekly = [w for w in (tcg_weekly(i) for i in meta) if w is not None]
    if weekly:
        q = pd.concat([w["qty"] for w in weekly], axis=1).sum(axis=1, min_count=1).dropna()
        if len(q) > 2:
            sig["sales"] = q.iloc[:-1]                       # the current week is not over
    months = idx.index if len(idx) else pd.DatetimeIndex([])
    news = _events(("sellout", "scalping", "limit"), months)
    if len(news):
        sig["news"] = news
    rep = _events(("reprint", "restock"), months)
    if len(rep):
        sig["reprints"] = rep
    L = daily_log()
    if "listings" in L and len(L["listings"]) >= 31:
        li = L["listings"].sum(axis=1, min_count=1)
        sold = pd.concat([w["qty"] for w in weekly], axis=1).sum(axis=1).resample("D").ffill() / 7 if weekly else None
        lc = li.pct_change(30, fill_method=None)
        if sold is not None and len(sold):
            sc = sold.rolling(30, min_periods=20).sum().pct_change(30, fill_method=None).reindex(lc.index).ffill()
            sig["overhang"] = (lc - sc).dropna()
        else:
            sig["overhang"] = lc.dropna()
    z = {}
    for k, s in sig.items():
        _, _, freq, _ = SIGNALS[k]
        z[k] = rolling_z(s, MIN_N_SIGNAL.get(k, MIN_N.get(freq, 60)), WINDOW_DAYS if freq != "E" else 3 * WINDOW_DAYS)
    return {"sig": sig, "z": z, "index": idx, "seg_index": seg_idx, "prices": df, "psa10": p10, "items": items, "meta": meta, "new_set": ns}


FRESH_DAYS = {"M": 120, "W": 45, "D": 10, "E": 400}


def current(S: dict) -> list[dict]:
    """Each signal now: raw value, z, heat contribution (z x sign), the date it was read."""
    out = []
    for k, (label, sign, freq, words) in SIGNALS.items():
        s, z = S["sig"].get(k), S["z"].get(k)
        row = {"key": k, "label": label, "sign": sign, "freq": freq, "words": words, "value": None, "z": None, "heat": None, "date": None, "status": "no data yet"}
        if s is not None and len(s.dropna()):
            row["value"], row["date"] = _r(s.dropna().iloc[-1], 4), str(s.dropna().index[-1].date())
            row["status"] = "building history"
        if z is not None and len(z):
            age = (_now() - z.index[-1]).days
            if age <= FRESH_DAYS[freq]:
                row.update(z=_r(z.iloc[-1], 2), heat=_r(float(np.clip(z.iloc[-1] * sign, -3, 3)), 2), status="ok")
            else:
                row["status"] = f"last reading {age} days old"
        out.append(row)
    return out


def composite(S: dict) -> pd.Series:
    """Month by month: the mean of the signals' heat (z x sign), each carried forward at most 3 months; needs 3 signals; clipped to +-2."""
    cols = {}
    for k, z in S["z"].items():
        if len(z):
            m = (z * SIGNALS[k][1]).resample("MS").last()
            if SIGNALS[k][2] == "E":
                m = m.reindex(pd.date_range(m.index[0], _now(), freq="MS")).ffill(limit=12)
            cols[k] = m
    if not cols:
        return pd.Series(dtype=float)
    d = pd.DataFrame(cols).sort_index().ffill(limit=3)
    d = d[d.index <= _now()]
    return d.mean(axis=1).where(d.notna().sum(axis=1) >= 3).clip(-2, 2).dropna()


def verdict(x) -> str:
    if x is None:
        return "not enough data yet"
    return "overheated" if x >= 1 else "running hot" if x >= 0.5 else "cold" if x <= -1 else "cooling" if x <= -0.5 else "neutral"


def lean(z, cut: float = 0.5) -> int:
    return 0 if z is None else 1 if z >= cut else -1 if z <= -cut else 0


# ------------------------------------------------------------------ tab payloads
def _signals_cached():
    from ..cache import _cached
    return _cached(f"topic:{SLUG}:signals", 1800, signal_series)


def _heat_now() -> dict:
    S = _signals_cached()
    cur = current(S)
    live = [c for c in cur if c["heat"] is not None]
    score = _r(float(np.clip(np.mean([c["heat"] for c in live]), -2, 2)), 2) if len(live) >= 3 else None
    comp = composite(S)
    drivers = sorted(live, key=lambda c: -abs(c["heat"]))[:3]
    return {"score": score, "verdict": verdict(score), "n": len(live), "signals": cur, "drivers": [c["key"] for c in drivers],
            "history": _pts(comp, 3), "z": {k: _pts(z, 3) for k, z in S["z"].items() if len(z)},
            "as_of": str(S["index"].index[-1].date()) if len(S["index"]) else None, "stale": B.stale_info([pc_url(i) for i in basket() if pc_url(i)])}


def _price_table(S: dict) -> list[dict]:
    df, out = S["prices"], []
    for i in S["meta"]:
        s = df[i["key"]].dropna() if i["key"] in df else pd.Series(dtype=float)
        p10 = S["psa10"][i["key"]].dropna() if i["key"] in S["psa10"] else pd.Series(dtype=float)

        def chg(n):
            return _r(s.iloc[-1] / s.iloc[-1 - n] - 1, 4) if len(s) > n and s.iloc[-1 - n] else None
        avg7 = s.iloc[-7:].mean() if len(s) >= 5 else None
        out.append({"key": i["key"], "name": i["name"], "set": i.get("set"), "segment": i["segment"], "kind": i.get("kind"), "release": i["date"],
                    "price": _r(s.iloc[-1], 2) if len(s) else None, "date": str(s.index[-1].date()) if len(s) else None,
                    "m1": chg(1), "m3": chg(3), "m12": chg(12), "vs200": _r(s.iloc[-1] / avg7 - 1, 4) if avg7 else None,
                    "psa10": _r(p10.iloc[-1], 2) if len(p10) else None, "msrp": i["msrp"], "x_msrp": _r(s.iloc[-1] / i["msrp"], 3) if len(s) and i["msrp"] else None,
                    "src": i["src"], "url": i["url"], "ptcg_id": i.get("ptcg_id"), "tcgplayer_id": tcg_id(i), "note": i.get("note", "")})
    return out


def _prices_now() -> dict:
    S = _signals_cached()
    seg = {name: _pts(s, 2) for (k, name) in SEGMENTS for s in [S["seg_index"].get(k)] if s is not None and len(s)}
    idx = S["index"]
    k = {}
    if len(idx):
        k = {"index": _r(idx.iloc[-1], 1), "m1": _r(idx.pct_change(1, fill_method=None).iloc[-1], 4), "m3": _r(idx.pct_change(3, fill_method=None).iloc[-1], 4) if len(idx) > 3 else None,
             "m12": _r(idx.pct_change(12, fill_method=None).iloc[-1], 4) if len(idx) > 12 else None, "from_high": _r(idx.iloc[-1] / idx.max() - 1, 4), "high_date": str(idx.idxmax().date())}
        for key, _ in SEGMENTS:
            s = S["seg_index"].get(key)
            if s is not None and len(s) > 12:
                k[key + "_m12"] = _r(s.iloc[-1] / s.iloc[-13] - 1, 4)
                k[key + "_m3"] = _r(s.iloc[-1] / s.iloc[-4] - 1, 4)
    L = daily_log()
    daily = {}
    if "tcg" in L and len(L["tcg"]) >= 2:
        daily["TCGplayer market (US, basket median vs first day)"] = _pts((L["tcg"] / L["tcg"].bfill().iloc[0]).median(axis=1) * 100, 2)
    if "cm_trend" in L and len(L["cm_trend"]) >= 2:
        daily["Cardmarket trend (EU, basket median vs first day)"] = _pts((L["cm_trend"] / L["cm_trend"].bfill().iloc[0]).median(axis=1) * 100, 2)
    return {"all": _pts(idx, 2), "segments": seg, "kpi": k, "table": _price_table(S), "daily": daily,
            "as_of": str(idx.index[-1].date()) if len(idx) else None, "stale": B.stale_info([pc_url(i) for i in basket() if pc_url(i)])}


def _events_rows(kinds: tuple) -> list[dict]:
    return [r for r in reversed(rows("events")) if r.get("kind", "").lower() in kinds]


def _overheat_now() -> dict:
    S = _signals_cached()
    cur = {c["key"]: c for c in current(S)}
    keys = ("mom30", "mom90", "breadth", "sealed_msrp", "new_set", "psa_volume", "search", "sales", "news")
    return {"signals": [cur[k] for k in keys], "series": {k: _pts(S["sig"][k], 4) for k in keys if k in S["sig"]},
            "z": {k: _pts(S["z"][k], 3) for k in keys if k in S["z"] and len(S["z"][k])}, "new_set": S["new_set"],
            "sealed": [r for r in _price_table(S) if r["segment"] == "sealed"], "news": _events_rows(("sellout", "scalping", "limit")),
            "cited": cited("trends", "psa", "events", "newset"), "as_of": str(S["index"].index[-1].date()) if len(S["index"]) else None}


def _change(s: pd.Series | None, months: int):
    if s is None or len(s.dropna()) <= months:
        return None
    s = s.dropna()
    t = s.index[-1] - pd.DateOffset(months=months)
    p = s[s.index <= t]
    return _r(s.iloc[-1] - p.iloc[-1], 4) if len(p) else None


def cooling_checks(S: dict) -> list[dict]:
    """Signs of a turn, each met (True), not (False) or unknown (None)."""
    # only signals read recently: an old hand-entered series must not count as fading
    sig = {k: v for k, v in S["sig"].items() if len(v.dropna()) and (_now() - v.dropna().index[-1]).days <= FRESH_DAYS[SIGNALS[k][2]]}
    m90, br, sm, pr, se = sig.get("mom90"), sig.get("breadth"), sig.get("sealed_msrp"), sig.get("psa10_ratio"), sig.get("search")
    m30 = sig.get("mom30")
    peak = float(m90.iloc[-6:].max()) if m90 is not None and len(m90) >= 6 else None

    def chk(key, label, value, met, rule, fmt="pct"):
        return {"key": key, "label": label, "value": value, "met": None if value is None or met is None else bool(met), "rule": rule, "fmt": fmt}
    now90 = _r(m90.iloc[-1], 4) if m90 is not None and len(m90) else None
    now30 = _r(m30.iloc[-1], 4) if m30 is not None and len(m30) else None
    d_br, d_sm, d_pr, d_se = _change(br, 3), _change(sm, 3), _change(pr, 6), _change(se, 3)
    ov = sig.get("overhang")
    rep = sig.get("reprints")
    return [chk("momentum_rollover", "90-day momentum, now vs its 6-month peak", now90, None if peak is None or now30 is None else (now90 < peak - 0.05 and now30 < 0),
                "met when 90-day momentum is 5+ points below its 6-month peak and the last month fell"),
            chk("breadth_falling", "Breadth, change over 3 months (points)", d_br, None if d_br is None else d_br <= -0.15, "met when the share above the 200-day average fell 15+ points", "pp"),
            chk("sealed_compress", "Sealed price / MSRP, change over 3 months", d_sm, None if d_sm is None else d_sm < -0.1, "met when the multiple fell by more than 0.1x", "x"),
            chk("overhang", "Listings minus sales, 30-day change", _r(ov.iloc[-1], 4) if ov is not None and len(ov) else None,
                None if ov is None or not len(ov) else ov.iloc[-1] > 0.1, "met when listings grew 10+ points faster than units sold"),
            chk("psa10_shrink", "PSA 10 / raw ratio, change over 6 months", d_pr, None if d_pr is None else d_pr < -0.5, "met when the ratio fell by more than 0.5x", "x"),
            chk("search_fading", "Search interest, change over 3 months (index points)", d_se, None if d_se is None else d_se <= -10, "met when Google Trends fell 10+ points", "n"),
            chk("reprints", "Reprint / restock announcements, last 90 days", _r(rep.iloc[-1], 0) if rep is not None and len(rep) else None,
                None if rep is None or not len(rep) else rep.iloc[-1] >= 1, "met when at least one was announced", "n")]


def _cooldown_now() -> dict:
    S = _signals_cached()
    sig = S["sig"]
    checks = cooling_checks(S)
    m90 = sig.get("mom90")
    return {"checks": checks, "met": sum(1 for c in checks if c["met"]), "known": sum(1 for c in checks if c["met"] is not None),
            "series": {k: _pts(sig[k], 4) for k in ("mom30", "mom90", "breadth", "sealed_msrp", "psa10_ratio", "search", "overhang") if k in sig},
            "peak90": _pts(m90.rolling(6, min_periods=1).max(), 4) if m90 is not None else [],
            "reprints": _events_rows(("reprint", "restock")), "cited": cited("events", "trends"),
            "as_of": str(S["index"].index[-1].date()) if len(S["index"]) else None}


def _grading_now() -> dict:
    S = _signals_cached()
    df, p10, items = S["prices"], S["psa10"], S["items"]
    ratio = {}
    for seg, name in SEGMENTS[:2]:
        ks = [k for k in p10 if k in df and items[k]["segment"] == seg]
        if ks:
            r = pd.DataFrame({k: p10[k] / df[k] for k in ks}).replace([np.inf, -np.inf], np.nan)
            ratio[name] = _pts(r.median(axis=1).where(r.notna().sum(axis=1) >= 2).dropna(), 3)
    table = []
    for k in p10:
        if k not in df:
            continue
        r = (p10[k] / df[k]).replace([np.inf, -np.inf], np.nan).dropna()
        if not len(r):
            continue
        r12 = r[r.index <= r.index[-1] - pd.DateOffset(months=12)]
        table.append({"key": k, "name": items[k]["name"], "set": items[k].get("set"), "segment": items[k]["segment"], "psa10": _r(p10[k].dropna().iloc[-1], 2),
                      "raw": _r(df[k].dropna().iloc[-1], 2), "ratio": _r(r.iloc[-1], 2), "ratio_12m": _r(r12.iloc[-1], 2) if len(r12) else None})
    pop = hand("pop")
    growth = {}
    for name, s in pop.items():
        if len(s) >= 2:
            t = s.index[-1] - pd.DateOffset(months=12)
            prev = s[s.index <= t]
            growth[name] = {"now": _r(s.iloc[-1], 0), "date": str(s.index[-1].date()), "yoy": _r(s.iloc[-1] / prev.iloc[-1] - 1, 4) if len(prev) and prev.iloc[-1] else None}
    psa = hand("psa")
    return {"ratio": ratio, "ratio_all": _pts(S["sig"]["psa10_ratio"], 3) if "psa10_ratio" in S["sig"] else [], "table": sorted(table, key=lambda r: -(r["ratio"] or 0)),
            "pop": {k: _pts(v, 0) for k, v in pop.items()}, "pop_growth": growth, "psa": {k: _pts(v, 1) for k, v in psa.items()},
            "cited": cited("pop", "psa"), "as_of": str(df.index[-1].date()) if len(df) else None}


def _regions_now() -> dict:
    items = basket()
    P = ptcg_now()
    try:
        fx = _fx()
    except LookupError:
        fx = None
    L = daily_log()
    logged = {k: v.ffill().iloc[-1] for k, v in L.get("market", pd.DataFrame()).items()} if "market" in L else {}
    cards = []
    for i in items:
        p = dict(P.get(i.get("ptcg_id")) or {})
        if not p.get("tcg") and _f(logged.get(i["key"])):         # no TCGdex / pokemontcg.io price: TCGplayer's own market price from the daily log
            p["tcg"] = _f(logged[i["key"]])
        if not p.get("tcg") and not p.get("cm_trend"):
            continue
        eur = p.get("cm_trend") or p.get("cm_avg30")
        usd_eu = eur / fx["EUR"] if eur and fx else None
        w = tcg_weekly(i)
        us30 = None
        if w is not None and len(w["price"].dropna()) > 5:
            s = w["price"].dropna()
            prev = s[s.index <= s.index[-1] - pd.Timedelta(days=28)]
            us30 = _r(s.iloc[-1] / prev.iloc[-1] - 1, 4) if len(prev) else None
        cards.append({"key": i["key"], "name": i["name"], "set": i.get("set"), "segment": i["segment"], "usd": p.get("tcg"), "eur": eur,
                      "gbp": _r(eur / fx["EUR"] * fx["GBP"], 2) if eur and fx else None, "eu_in_usd": _r(usd_eu, 2),
                      "eu_vs_us": _r(usd_eu / p["tcg"] - 1, 4) if usd_eu and p.get("tcg") else None,
                      "eu_7v30": _r(p["cm_avg7"] / p["cm_avg30"] - 1, 4) if p.get("cm_avg7") and p.get("cm_avg30") else None,
                      "us_30d": us30, "tcg_url": p.get("tcg_url"), "cm_url": p.get("cm_url")})
    med = lambda k: _r(float(np.median([c[k] for c in cards if c[k] is not None])), 4) if any(c[k] is not None for c in cards) else None

    def log_mom(field, days=30):
        if field not in L or len(L[field]) < days // 2:
            return None
        d = L[field]
        prev = d[d.index <= d.index[-1] - pd.Timedelta(days=days)]
        if not len(prev):
            return None
        return _r(float((d.iloc[-1] / prev.iloc[-1] - 1).median()), 4)
    jp = hand("japan")
    jp_chg = []
    for name, s in jp.items():
        prev = s[s.index <= s.index[-1] - pd.DateOffset(months=3)]
        if len(prev) and prev.iloc[-1]:
            jp_chg.append(s.iloc[-1] / prev.iloc[-1] - 1)
    us = next((m for m in (log_mom("tcg"), log_mom("market"), med("us_30d")) if m is not None), None)
    regions = [{"region": "US (TCGplayer)", "mom": us, "basis": "30-day change, basket median"},
               {"region": "UK / EU (Cardmarket)", "mom": log_mom("cm_trend") if log_mom("cm_trend") is not None else med("eu_7v30"),
                "basis": "30-day change of the trend price once a month of daily log exists; until then the 7-day vs 30-day average"},
               {"region": "Japan (hand-entered)", "mom": _r(float(np.median(jp_chg)), 4) if jp_chg else None, "basis": "3-month change, median of the entered sets"}]
    known = [r for r in regions if r["mom"] is not None]
    hottest = max(known, key=lambda r: r["mom"])["region"] if known else None
    return {"cards": cards, "fx": fx, "kpi": {"eu_vs_us": med("eu_vs_us"), "eu_7v30": med("eu_7v30"), "us_30d": med("us_30d")}, "regions": regions, "hottest": hottest,
            "japan": {k: _pts(v, 0) for k, v in jp.items()}, "hk": list(reversed(rows("hk"))), "cited": cited("japan", "hk"),
            "as_of": next((c for c in [(P.get(i.get("ptcg_id")) or {}).get("tcg_updated") for i in items] if c), None)}


def _basket_now() -> dict:
    return {"items": [{k: i.get(k) for k in ("key", "name", "set", "segment", "kind", "date", "msrp_usd", "pricecharting", "ptcg_id", "tcgdex_id", "tcgplayer_id", "source", "note")}
                      for i in basket()], "resolved": _resolved()}


# ------------------------------------------------------------------ READINGS
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


TAB_OF = {"mom30": "overheat", "mom90": "overheat", "breadth": "overheat", "sealed_msrp": "overheat", "new_set": "overheat", "psa_volume": "overheat",
          "search": "overheat", "sales": "overheat", "news": "overheat", "reprints": "cooldown", "overhang": "cooldown", "psa10_ratio": "grading"}


def readings(got) -> list[dict]:
    """The composite and every signal (heat = z x sign; +1 heating, -1 cooling), the cooling checklist, index momentum and the hottest region."""
    out = []

    def add(tab, key, label, value, ln, note):
        if value is not None:
            out.append({"tab": tab, "key": key, "label": label, "value": value, "lean": ln, "note": note})
    H = got("heat")
    add("heat", "composite", "Heat score (-2 cold ... +2 overheated)", H.get("score"), lean(H.get("score")), f"{verdict(H.get('score'))}; +1 at +0.5 or above, -1 at -0.5 or below")
    for c in H.get("signals") or []:
        add(TAB_OF[c["key"]], c["key"], c["label"] + " (heat z)", c["heat"], lean(c["heat"]),
            f"value {c['value']} on {c['date']}; +1 when 0.5 sd hotter than its last 3 years, -1 when 0.5 sd cooler")
    C = got("cooldown")
    if C.get("known"):
        add("cooldown", "cooling_signs", f"Cooling signs met (of {C['known']})", C.get("met"), -1 if C["met"] * 2 >= C["known"] else 0,
            "-1 when at least half the known cooling signs are met")
    K = got("prices").get("kpi") or {}
    add("prices", "index_3m", "Whole-basket index, 3-month change", K.get("m3"), lean(K.get("m3"), 0.05), "+1 when up 5% or more in three months, -1 when down 5% or more")
    for seg, name in SEGMENTS:
        v = K.get(seg + "_m12")
        add("prices", f"{seg}_12m", f"{name} index, 12-month change", v, lean(v, 0.10), "+1 when up 10% or more on a year, -1 when down 10% or more")
    R = got("regions")
    for r in R.get("regions") or []:
        if r["mom"] is not None:
            add("regions", "mom_" + r["region"].split()[0].lower().replace("/", ""), r["region"] + ": momentum", r["mom"], lean(r["mom"], 0.03),
                r["basis"] + "; +1 at +3% or more, -1 at -3% or less")
    return out


def READINGS() -> list[dict]:
    """Every signal and the composite from the cached tab payloads only (nothing is fetched)."""
    return readings(_cached_payload)


# ------------------------------------------------------------------ the probe
def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, type, size, first 600 characters), to check the parsers and see
    which shops answer a cloud server. Read it with Actions > show-json on /api/pokemon-cards/layout."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    items = basket()
    first = next((i for i in items if i.get("pricecharting")), {})
    sealed = next((i for i in items if i["segment"] == "sealed" and i.get("pricecharting")), {})
    urls = {"pokemontcg.io": ptcg_url(items[:3]) or PTCG.format(q="id:base1-4"),
            "pricecharting card": f"{PC_BASE}/game/{first.get('pricecharting', 'pokemon-base-set/charizard-4')}",
            "pricecharting sealed": f"{PC_BASE}/game/{sealed.get('pricecharting', 'pokemon-evolving-skies/booster-box')}",
            "pricecharting search": PC_SEARCH.format(q="charizard+base+set"),
            "pokemontcg.io tcgplayer link": "https://prices.pokemontcg.io/tcgplayer/base1-4",
            "pokemontcg.io one card": "https://api.pokemontcg.io/v2/cards/base1-4", "pokemontcg.io simple query": PTCG.format(q="id:base1-4"),
            "tcgdex card": TCGDEX.format(id="base1-4"), "tcgdex modern card": TCGDEX.format(id="swsh7-215"), "tcgdex sv card": TCGDEX.format(id="sv03.5-199"),
            "tcgplayer history": TCG_HISTORY.format(pid="42382"), "tcgplayer details": TCG_DETAILS.format(pid="42382"),
            "tcgcsv groups": "https://tcgcsv.com/tcgplayer/3/groups", "frankfurter": FX, "er-api": FX_FALLBACK,
            "cardmarket": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard-V1-BS4",
            "yuyutei": "https://yuyu-tei.jp/sell/poc/s/search?search_word=%E3%83%AA%E3%82%B6%E3%83%BC%E3%83%89%E3%83%B3",
            "snkrdunk": "https://snkrdunk.com/en/", "ebay sold": "https://www.ebay.com/sch/i.html?_nkw=pokemon+booster+box&LH_Sold=1&LH_Complete=1",
            "google trends": "https://trends.google.com/trends/api/explore?hl=en-US&tz=0&req=%7B%22comparisonItem%22%3A%5B%7B%22keyword%22%3A%22pokemon%20cards%22%2C%22geo%22%3A%22US%22%2C%22time%22%3A%22today%205-y%22%7D%5D%7D",
            "psa pop": "https://www.psacard.com/pop/tcg-cards/1999/pokemon-game/57801", "gemrate": "https://www.gemrate.com/"}

    def one(item):
        k, u = item
        h = {**B.UA, **(TCG_HEADERS if "tcgplayer" in k and "link" not in k else PC_HEADERS if "pricecharting" in k or k in ("yuyutei", "snkrdunk") else {})}
        try:
            r = requests.get(u, headers=h, timeout=30, stream=True, allow_redirects=True)
            head = r.raw.read(2000000 if "pricecharting card" in k else 200000, decode_content=True).decode("utf-8", "replace")
            r.close()
            sold = {}
            if k == "pricecharting card":       # the sold-listings tables per grade, for a sales-volume parser
                for m in re.finditer(r'<div[^>]+(?:id|class)="[^"]*completed-auctions-([\w-]+)[^"]*"', head):
                    seg = head[m.start():m.start() + 60000]
                    end = seg.find("completed-auctions-", 40)
                    seg = seg[:end] if end > 0 else seg
                    sold[m.group(1)] = {"rows": seg.count("<tr"), "head": seg[:700], "first_row": (re.search(r"<tr[^>]*>(?:(?!</tr>).){0,1500}</tr>", seg[300:], re.S) or [""])[0][:1500]}
                sold["_ids"] = sorted(set(re.findall(r'id="([^"]*(?:auction|sold|sales|volume)[^"]*)"', head)))[:40]
                i = head.find('class="sales_volume"')
                sold["_volume_row"] = head[max(0, i - 300):i + 2500] if i >= 0 else None
                g = head.find("completed-auctions-graded")
                r9 = head.find('<td class="date"', g) if g >= 0 else -1
                sold["_graded_row"] = head[max(0, r9 - 200):r9 + 2200] if r9 >= 0 else None
                pr = head.find('class="population-report"')
                sold["_pop"] = re.sub(r"\s+", " ", head[pr:pr + 6000]) if pr >= 0 else None
                pt = head.find('id="price_data"')
                sold["_price_table"] = re.sub(r"\s+", " ", head[pt:pt + 5000]) if pt >= 0 else None
            chart = re.search(r"VGPC\.chart_data\s*=\s*(\{.{0,300})", head, re.S)
            try:
                j = json.loads(head)
                keys = {"keys": sorted(j)[:60] if isinstance(j, dict) else None}
                if k in ("tcgplayer details", "tcgdex card"):
                    keys["json"] = {a: b for a, b in j.items() if a not in ("customAttributes", "description")}
            except ValueError:
                keys = {}
            yen = re.findall(r"([0-9,]{3,9})\s*円", head)[:10] if k == "yuyutei" else None
            return k, {"status": r.status_code, "final": r.url, "type": r.headers.get("content-type", ""), "bytes_read": len(head), "start": head[:600], **keys,
                       **({"yen": yen, "card_blocks": re.findall(r'<div[^>]+class="[^"]*card-product[^"]*"[^>]*>.{0,600}', head, re.S)[:2]} if k == "yuyutei" else {}),
                       **({"chart_data": chart.group(1), "chart_keys": re.findall(r'"(\w+)":\[\[', head[chart.start():chart.start() + 400000])} if chart else {}), **({"sold": sold} if sold else {}), **({"search_first": parse_pc_search(head)} if "search" in k else {})}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        out = dict(ex.map(one, urls.items()))
    out["_resolved"] = _resolved()
    return out


def _cached_ep(name, fn, ttl=3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


ENDPOINTS = {"heat": _cached_ep("heat", _heat_now), "prices": _cached_ep("prices", _prices_now), "overheat": _cached_ep("overheat", _overheat_now),
             "cooldown": _cached_ep("cooldown", _cooldown_now), "grading": _cached_ep("grading", _grading_now), "regions": _cached_ep("regions", _regions_now),
             "basket": _cached_ep("basket", _basket_now, 600), "layout": _cached_ep("layout", _layout_now, 1800)}
