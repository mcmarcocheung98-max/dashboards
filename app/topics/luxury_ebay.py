"""eBay Browse API feed for the Luxury Tracker (helper module; the dashboard is luxury.py).

Once a day, for every item in data/luxury/items.csv with an `ebay` query: the active fixed-price listings on eBay UK that match it
(count, median and lowest asking price in GBP), kept as one line a day per item in SNAPSHOT_DIR/luxury/ebay_daily.csv so history
accrues from the day the keys are set. Free with a developer key: EBAY_APP_ID and EBAY_CERT_ID (a client-credentials token, about two
hours, refreshed as needed). Until the keys are set every call says so and the card reads "not set up yet (EBAY_APP_ID)", as Ask Claude
does for its key. Sold prices are not read: eBay's Marketplace Insights API is restricted (apply if the owner wants it; see the README).

fill() is luxury.py's BACKGROUND job (the server runs it at start and every 6 hours); pages only read the daily file.
"""
from __future__ import annotations

import base64
import csv
import json
import os
import statistics
import time
from pathlib import Path

import pandas as pd
import requests

from . import _base as B
from ._base import _r

DASHBOARD = "luxury"
SLUG = "luxury"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
MARKETPLACE = "EBAY_GB"
CATEGORY_IDS = {"watch": "31387", "bag": "169291"}        # eBay UK: Wristwatches; Women's Bags & Handbags
LIMIT = 200                                                # listings read per item per day (one page)
PACE = 1.0                                                 # seconds between calls
DIR: Path | None = None                                    # tests and smoke point the files elsewhere
FILE = "ebay_daily.csv"
HEAD = ["date", "item", "count", "median", "low", "currency", "n_read"]
_token: dict = {"value": None, "until": 0.0}
_last_call = 0.0


def keys() -> tuple[str, str]:
    return os.environ.get("EBAY_APP_ID", "").strip(), os.environ.get("EBAY_CERT_ID", "").strip()


def set_up() -> bool:
    a, c = keys()
    return bool(a and c)


class NotSetUp(RuntimeError):
    pass


def _dir() -> Path:
    return DIR or B.SNAP_DIR / SLUG


def _pace() -> None:
    global _last_call
    wait = _last_call + PACE - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def post(url: str, data: dict, headers: dict, timeout: int = 30) -> dict:
    """One token request (replaced by fixtures in the tests)."""
    r = requests.post(url, data=data, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def get(url: str, params: dict, headers: dict, timeout: int = 30) -> dict:
    """One Browse API call (replaced by fixtures in the tests)."""
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def token() -> str:
    """A client-credentials application token, cached until shortly before it expires."""
    a, c = keys()
    if not (a and c):
        raise NotSetUp("not set up yet (EBAY_APP_ID)")
    if _token["value"] and _token["until"] > time.time() + 60:
        return _token["value"]
    auth = base64.b64encode(f"{a}:{c}".encode()).decode()
    j = post(TOKEN_URL, {"grant_type": "client_credentials", "scope": SCOPE}, {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"})
    if not j.get("access_token"):
        raise RuntimeError("eBay token: " + json.dumps(j)[:160])
    _token.update(value=j["access_token"], until=time.time() + float(j.get("expires_in", 7200)))
    return j["access_token"]


def parse_search(j: dict) -> dict:
    """item_summary/search -> the total count eBay reports, and the GBP asking prices of the fixed-price listings on the page."""
    prices = []
    for it in (j or {}).get("itemSummaries") or []:
        p = it.get("price") or {}
        if p.get("currency") not in (None, "GBP"):
            continue
        try:
            v = float(p.get("value"))
        except (TypeError, ValueError):
            continue
        if "FIXED_PRICE" in (it.get("buyingOptions") or ["FIXED_PRICE"]) and v > 0:
            prices.append(v)
    total = (j or {}).get("total")
    return {"count": int(total) if total is not None else len(prices), "n_read": len(prices), "median": _r(statistics.median(prices), 0) if prices else None,
            "low": _r(min(prices), 0) if prices else None, "currency": "GBP"}


def search(query: str, category: str) -> dict:
    """The active listings on eBay UK matching `query` in the category's eBay category, counted and priced."""
    _pace()
    params = {"q": query, "limit": str(LIMIT), "sort": "price", "filter": "buyingOptions:{FIXED_PRICE},priceCurrency:GBP,conditions:{NEW|USED|CERTIFIED_REFURBISHED}"}
    if CATEGORY_IDS.get(category):
        params["category_ids"] = CATEGORY_IDS[category]
    j = get(SEARCH_URL, params, {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE, "Accept": "application/json"})
    return parse_search(j)


def read_daily() -> pd.DataFrame:
    f = _dir() / FILE
    if not f.exists():
        return pd.DataFrame(columns=HEAD)
    d = pd.read_csv(f, dtype={"item": str})
    if d.empty:
        return pd.DataFrame(columns=HEAD)
    d["date"] = pd.to_datetime(d["date"])
    return d.drop_duplicates(["date", "item"], keep="last").sort_values(["item", "date"])


def append_daily(rows: list[dict]) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / FILE
    new = not f.exists()
    with f.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in HEAD})


def fill(its: list[dict] | None = None, today: str | None = None) -> dict:
    """BACKGROUND job: one search per item that has no row for today; returns {item: 'ok' | reason}. Does nothing without the keys."""
    if not set_up():
        return {"ebay": "not set up yet (EBAY_APP_ID)"}
    from . import luxury as L
    its = its if its is not None else L.items(with_watchlist=True)
    today = today or pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    have = read_daily()
    done = set(have[have["date"] == pd.Timestamp(today)]["item"]) if len(have) else set()
    out, rows = {}, []
    for i in its:
        q = (i.get("ebay") or "").strip()
        if not q:
            out[i["id"]] = "no ebay query"
            continue
        if i["id"] in done:
            out[i["id"]] = "ok"
            continue
        try:
            r = search(q, i["category"])
            rows.append({"date": today, "item": i["id"], **r})
            out[i["id"]] = "ok"
        except Exception as e:
            out[i["id"]] = f"{type(e).__name__}: {str(e)[:100]}"
    if rows:
        append_daily(rows)
    return out


def payload(its: list[dict] | None = None) -> dict:
    """What the Liquidity tab shows: per item the daily count, median and lowest ask; per category the summed count and the median of
    medians, day by day; the set-up state and the file's span."""
    from . import luxury as L
    its = its if its is not None else L.items(with_watchlist=True)
    d = read_daily()
    per, cats = {}, {}
    for i in its:
        x = d[d["item"] == i["id"]] if len(d) else d
        if not len(x):
            per[i["id"]] = {"name": i["name"], "category": i["category"], "query": i.get("ebay") or "", "count": [], "median": [], "low": [], "latest": None}
            continue
        s = lambda col: [[int(pd.Timestamp(t).timestamp()), _r(v, 0)] for t, v in zip(x["date"], x[col]) if pd.notna(v)]
        last = x.iloc[-1]
        per[i["id"]] = {"name": i["name"], "category": i["category"], "query": i.get("ebay") or "", "count": s("count"), "median": s("median"), "low": s("low"),
                        "latest": {"date": str(last["date"].date()), "count": int(last["count"]) if pd.notna(last["count"]) else None, "median": _r(last["median"], 0), "low": _r(last["low"], 0), "n_read": int(last["n_read"]) if pd.notna(last.get("n_read")) else None},
                        "count_1y": _r(float(last["count"]) / float(x[x["date"] <= last["date"] - pd.Timedelta(days=365)]["count"].iloc[-1]) - 1, 4) if len(x[x["date"] <= last["date"] - pd.Timedelta(days=365)]) and float(x[x["date"] <= last["date"] - pd.Timedelta(days=365)]["count"].iloc[-1]) else None}
    for cat, name in L.CATEGORIES:
        ids = [i["id"] for i in its if i["category"] == cat]
        x = d[d["item"].isin(ids)] if len(d) else d
        if not len(x):
            cats[cat] = {"name": name, "count": [], "median": []}
            continue
        g = x.groupby("date")
        cnt = g["count"].sum()
        med = g["median"].median()
        cats[cat] = {"name": name, "count": [[int(t.timestamp()), int(v)] for t, v in cnt.items()], "median": [[int(t.timestamp()), _r(v, 0)] for t, v in med.items() if pd.notna(v)],
                     "days": int(len(cnt)), "latest": {"date": str(cnt.index[-1].date()), "count": int(cnt.iloc[-1])}}
    return {"set_up": set_up(), "message": None if set_up() else "not set up yet (EBAY_APP_ID): add EBAY_APP_ID and EBAY_CERT_ID on Railway and the daily snapshots start",
            "items": per, "categories": cats, "days": int(d["date"].nunique()) if len(d) else 0, "first": str(d["date"].min().date()) if len(d) else None, "last": str(d["date"].max().date()) if len(d) else None,
            "marketplace": MARKETPLACE, "note": "active fixed-price listings on eBay UK matching each item's query (count as eBay reports it; median and lowest ask from the first " + str(LIMIT) + " by price); sold prices need eBay's restricted Marketplace Insights API"}
