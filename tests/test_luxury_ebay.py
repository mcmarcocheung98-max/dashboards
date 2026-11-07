"""The eBay Browse feed of the Luxury Tracker (app/topics/luxury_ebay.py) on fixtures: token, search parsing, the daily file, the payload."""
import json

import pandas as pd
import pytest

from app.topics import luxury_ebay as E


def token_json(url, data, headers, timeout=30):
    assert url == E.TOKEN_URL and data["grant_type"] == "client_credentials" and headers["Authorization"].startswith("Basic ")
    return {"access_token": "tok-123", "expires_in": 7200, "token_type": "Application Access Token"}


def search_json(url, params, headers, timeout=30):
    assert url == E.SEARCH_URL and headers["Authorization"] == "Bearer tok-123" and headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_GB"
    q = params["q"]
    base = 9000 if "Rolex" in q else 1200
    items = [{"itemId": f"v1|{i}|0", "title": q + " " + str(i), "price": {"value": str(base + i * 100), "currency": "GBP"}, "buyingOptions": ["FIXED_PRICE"], "condition": "Pre-owned"} for i in range(7)]
    items.append({"itemId": "v1|x|0", "title": "auction", "price": {"value": "1", "currency": "GBP"}, "buyingOptions": ["AUCTION"]})
    items.append({"itemId": "v1|y|0", "title": "usd", "price": {"value": "5000", "currency": "USD"}, "buyingOptions": ["FIXED_PRICE"]})
    return {"total": 42 if "Rolex" in q else 9, "itemSummaries": items}


@pytest.fixture
def ebay(tmp_path, monkeypatch):
    monkeypatch.setenv("EBAY_APP_ID", "app")
    monkeypatch.setenv("EBAY_CERT_ID", "cert")
    monkeypatch.setattr(E, "DIR", tmp_path / "ebay")
    monkeypatch.setattr(E, "post", token_json)
    monkeypatch.setattr(E, "get", search_json)
    monkeypatch.setattr(E, "PACE", 0)
    E._token.update(value=None, until=0.0)
    yield
    E._token.update(value=None, until=0.0)


ITEMS = [{"id": "w1", "name": "W1", "category": "watch", "ebay": "Rolex 126610LN"}, {"id": "b1", "name": "B1", "category": "bag", "ebay": "Hermes Birkin 25 Togo"}, {"id": "n1", "name": "N1", "category": "bag", "ebay": ""}]


def test_not_set_up(tmp_path, monkeypatch):
    monkeypatch.delenv("EBAY_APP_ID", raising=False)
    monkeypatch.delenv("EBAY_CERT_ID", raising=False)
    monkeypatch.setattr(E, "DIR", tmp_path / "ebay")
    assert not E.set_up() and E.fill(ITEMS) == {"ebay": "not set up yet (EBAY_APP_ID)"}
    with pytest.raises(E.NotSetUp):
        E.token()
    p = E.payload(ITEMS)
    assert p["set_up"] is False and "EBAY_APP_ID" in p["message"] and p["days"] == 0 and p["items"]["w1"]["latest"] is None


def test_parse_search_counts_fixed_price_gbp_only():
    r = E.parse_search(search_json(E.SEARCH_URL, {"q": "Rolex 126610LN"}, {"Authorization": "Bearer tok-123", "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB"}))
    assert r == {"count": 42, "n_read": 7, "median": 9300, "low": 9000, "currency": "GBP"}
    assert E.parse_search({}) == {"count": 0, "n_read": 0, "median": None, "low": None, "currency": "GBP"}


def test_fill_once_a_day_and_payload(ebay):
    out = E.fill(ITEMS, today="2026-11-07")
    assert out == {"w1": "ok", "b1": "ok", "n1": "no ebay query"}
    d = E.read_daily()
    assert len(d) == 2 and set(d["item"]) == {"w1", "b1"} and int(d[d["item"] == "w1"]["count"].iloc[0]) == 42
    assert E.fill(ITEMS, today="2026-11-07") == out and len(E.read_daily()) == 2          # a second run the same day reads nothing
    E.fill(ITEMS, today="2026-11-08")
    E.fill(ITEMS, today="2027-11-09")
    p = E.payload(ITEMS)
    assert p["set_up"] and p["days"] == 3 and p["first"] == "2026-11-07" and p["last"] == "2027-11-09"
    w = p["items"]["w1"]
    assert len(w["count"]) == 3 and w["latest"]["count"] == 42 and w["latest"]["median"] == 9300 and w["latest"]["low"] == 9000 and w["count_1y"] == 0.0
    assert p["categories"]["watch"]["latest"]["count"] == 42 and p["categories"]["bag"]["count"][-1][1] == 9 and p["items"]["n1"]["latest"] is None
    assert E._token["value"] == "tok-123"


def test_token_refresh_and_errors(ebay, monkeypatch):
    assert E.token() == "tok-123" and E.token() == "tok-123"
    E._token["until"] = 0
    monkeypatch.setattr(E, "post", lambda *a, **k: {"error": "invalid_client"})
    with pytest.raises(RuntimeError):
        E.token()
    E._token.update(value="tok-123", until=9e12)
    monkeypatch.setattr(E, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    out = E.fill(ITEMS, today="2026-11-10")
    assert out["w1"].startswith("ConnectionError") and len(E.read_daily()) == 0
