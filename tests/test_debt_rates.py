"""Global Debt & Rates (/debt-rates): parsers and payloads on fixtures shaped like each source; live checks are marked network."""
import json

import numpy as np
import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import debt_rates as D

NOW = pd.Timestamp.now().normalize()


# ------------------------------------------------------------------ fixtures in each source's own layout
def imf_json(ind: str) -> dict:
    base = {"GGXWDG_NGDP": {"USA": 60, "GBR": 40, "HKG": 1, "CHN": 25}, "GGXCNL_NGDP": {"USA": -5, "GBR": -4, "HKG": 1, "CHN": -3},
            "GGXONLB_NGDP": {"USA": -2, "GBR": -1.5, "HKG": 0.5, "CHN": -2}, "GGR_NGDP": {"USA": 30, "GBR": 38, "HKG": 20, "CHN": 27},
            "NGDP_RPCH": {"USA": 2, "GBR": 1.2, "HKG": 2.5, "CHN": 5}, "PCPIPCH": {"USA": 2.3, "GBR": 2.5, "HKG": 1.8, "CHN": 0.5}}[ind]
    rise = {"GGXWDG_NGDP": 2.0, "GGXCNL_NGDP": -0.05, "GGXONLB_NGDP": 0.02}.get(ind, 0)
    vals = {iso: {str(y): round(v + rise * (y - 2000), 2) for y in range(2000, NOW.year + 6)} for iso, v in base.items()}
    vals["WEOWORLD"] = {"2020": 1.0}
    return {"values": {ind: vals}, "api": {"version": "1"}}


def penny_json() -> dict:
    days = pd.date_range("2000-01-03", NOW, freq="7D")
    return {"data": [{"record_date": str(t.date()), "tot_pub_debt_out_amt": str(5.6e12 + i * 2.7e10), "debt_held_public_amt": str(3.4e12 + i * 2.1e10)}
                     for i, t in enumerate(days)]}


MTS_ROWS = [(10, 1, "Receipts"), (20, 2, "Individual Income Taxes"), (120, 2, "Total"), (130, 1, "Net Outlays"), (140, 2, "National Defense"),
            (230, 2, "Education, Training, Employment, and Social Services"), (320, 2, "Net Interest"), (340, 2, "Total")]


def mts_json() -> dict:
    out = []
    for i, t in enumerate(pd.date_range("2014-10-31", NOW - pd.DateOffset(months=1), freq="ME")):
        amt = {"Individual Income Taxes": 200e9, 120: 300e9 + i * 1.2e9, "National Defense": 55e9 + i * 0.1e9,
               "Education, Training, Employment, and Social Services": 10e9 + 3e9 * np.sin(i), "Net Interest": 20e9 + i * 0.5e9, 340: 380e9 + i * 2e9}
        for line, lvl, desc in MTS_ROWS:
            v = amt.get(line, amt.get(desc))
            out.append({"record_date": str(t.date()), "classification_desc": desc, "line_code_nbr": str(line),
                        "current_month_rcpt_outly_amt": "null" if v is None else f"{v:.2f}"})
    return {"data": out}


def avg_rate_json() -> dict:
    return {"data": [{"record_date": str(t.date()), "security_desc": "Total Marketable", "avg_interest_rate_amt": f"{1.5 + 0.02 * i:.3f}"}
                     for i, t in enumerate(pd.date_range("2001-01-31", NOW, freq="ME"))]}


def treasury_csv(y: int, real: bool) -> str:
    days = pd.bdate_range(f"{y}-01-02", min(pd.Timestamp(f"{y}-12-31"), NOW))
    if not len(days):
        return ""
    if real:
        head, row = "Date,5 YR,7 YR,10 YR,20 YR,30 YR", lambda i, t: f"{t:%m/%d/%Y},1.0,1.2,{0.5 + (y - 2003) * 0.08 + 0.001 * i:.2f},1.5,1.6"
    else:
        head = "Date,1 Mo,2 Mo,3 Mo,6 Mo,1 Yr,2 Yr,3 Yr,5 Yr,7 Yr,10 Yr,20 Yr,30 Yr"
        row = lambda i, t: f"{t:%m/%d/%Y},4.1,4.1,4.0,3.9,3.8,{2.0 + (y - 2000) * 0.07:.2f},3.6,3.7,3.9,{2.5 + (y - 2000) * 0.08 + 0.001 * i:.2f},4.6,4.7"
    return "\n".join([head] + [row(i, t) for i, t in enumerate(reversed(days))])


def boe_csv(code: str, since: int) -> str:
    days = pd.bdate_range(f"{since}-01-02", NOW, freq="5B")
    level = {"IUDBEDR": 3.0, "IUDMNPY": 3.5, "IUDMNZC": 3.5, "IUDMRZC": 0.3, "IUDMRPY": 0.3}[code]
    return f"DATE,{code}\n" + "\n".join(f"{t:%d %b %Y},{level + np.sin(i / 60):.4f}" for i, t in enumerate(days))


def ons_csv(sid: str) -> str:
    months = pd.date_range("1997-04-01", NOW - pd.DateOffset(months=2), freq="MS")
    lvl = {"hf6x": 40, "nmfx": 3000, "anbt": 50000, "d7g7": 2.5}[sid]
    meta = '"Title","x"\n"CDID","' + sid.upper() + '"\n"1997","1"\n"1997 Q2","2"\n'
    return meta + "\n".join(f'"{t.year} {t.strftime("%b").upper()}","{lvl * (1 + i / 400):.1f}"' for i, t in enumerate(months))


def hkma_json(path: str, offset: int) -> dict:
    months = list(reversed(pd.date_range("2000-01-01", NOW, freq="MS")))
    recs = []
    for t in months[offset:offset + 100]:
        if "efbn" in path:
            recs.append({"end_of_month": t.strftime("%Y-%m"), "efn_2y": 2.0, "efn_10y": (3.0 if t.year < 2015 else None)})
        else:
            recs.append({"end_of_month": t.strftime("%Y-%m"), "ir_overnight": 1.0, "ir_1m": 1.5})
    return {"header": {"success": True}, "result": {"datasize": len(recs), "records": recs}}


def nyfed_json() -> dict:
    days = pd.bdate_range("2016-03-01", NOW, freq="5B")
    return {"refRates": [{"effectiveDate": str(t.date()), "type": "EFFR", "percentRate": 0.4 + i * 0.004, "targetRateFrom": round(0.25 + i * 0.004, 2),
                          "targetRateTo": round(0.5 + i * 0.004, 2)} for i, t in enumerate(reversed(days))]}


CPI_U = {pd.Timestamp("2008-02-01") + pd.DateOffset(months=i): round(211.693 * 1.0025 ** i, 3) for i in range(240)}


def tips_json() -> dict:
    """Fiscal Data TIPS table for one CUSIP: daily reference CPI, the 1st of month M = CPI-U of M-3, straight line within the month;
    published to the end of the month after the latest CPI-U's reference month (latest CPI here: two months ago)."""
    last = (NOW - pd.DateOffset(months=2)).normalize().replace(day=1)
    rows = []
    for m in pd.date_range("2008-05-01", last + pd.DateOffset(months=2), freq="MS"):
        a, b = CPI_U.get(m - pd.DateOffset(months=3)), CPI_U.get(m - pd.DateOffset(months=2))
        if a is None or m - pd.DateOffset(months=3) > last:
            break
        for day in range(1, m.days_in_month + 1):
            if b is None or m - pd.DateOffset(months=2) > last:
                if day > 1:
                    break
                v = a
            else:
                v = a + (b - a) * (day - 1) / m.days_in_month
            rows.append({"index_date": str((m + pd.Timedelta(days=day - 1)).date()), "ref_cpi": f"{v:.5f}"})
    return {"data": rows}


def csd_json() -> dict:
    ms = pd.date_range("1990-01-01", NOW - pd.DateOffset(months=1), freq="MS")
    rows = [{"freq": "M", "period": t.strftime("%Y%m"), "sv": "A_CM_1920", "svDesc": "Year-on-year % change", "figure": 1.5, "sd_value": ""} for t in ms]
    rows += [{"freq": "M", "period": t.strftime("%Y%m"), "sv": "B_CM_1920", "svDesc": "Year-on-year % change", "figure": 9.9, "sd_value": ""} for t in ms[-3:]]
    return {"header": {}, "dataSet": rows}


def poly_json() -> list:
    def mk(label, yes, closed=False):
        return {"question": f"Will the Fed {label}?", "groupItemTitle": label, "outcomes": '["Yes", "No"]', "outcomePrices": json.dumps([str(yes), str(round(1 - yes, 4))]),
                "clobTokenIds": json.dumps([f"tok-{label}", f"no-{label}"]), "volume": "12345.6", "closed": closed, "active": True}
    nxt = (NOW + pd.Timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
    return [{"title": "How many Fed rate cuts in 2026?", "slug": "how-many-fed-rate-cuts-in-2026", "endDate": "2026-12-31T00:00:00Z", "volume": "9000000",
             "markets": [mk("No cuts", 0.01), mk("3 cuts", 0.6), mk("4 cuts", 0.3), mk("old", 0.5, closed=True)]},
            {"title": "Fed decision in October?", "slug": "fed-decision-in-october", "endDate": nxt, "volume": "5000000",
             "markets": [mk("25 bps decrease", 0.83), mk("No change", 0.16), mk("50+ bps decrease", 0.01)]},
            {"title": "Hike 25 bps flips No change for October Fed?", "slug": "flips", "endDate": nxt, "volume": "3752",
             "markets": [mk("Yes", 0.01)]},
            {"title": "Fed decision in December?", "slug": "fed-decision-in-december", "endDate": "2026-12-09T00:00:00Z", "volume": "800000",
             "markets": [mk("No change", 0.6), mk("25 bps decrease", 0.4)]}]


def clob_json(token: str) -> dict:
    days = pd.date_range(NOW - pd.Timedelta(days=60), NOW, freq="12h")
    return {"history": [{"t": int(t.timestamp()), "p": round(0.5 + 0.3 * i / len(days), 3)} for i, t in enumerate(days)]}


def kalshi_json() -> dict:
    def ev(tag, close, above):
        return {"event_ticker": f"KXFED-{tag}", "title": f"Fed funds rate after {tag} meeting?", "markets": [
            {"floor_strike": k, "strike_type": "greater", "last_price_dollars": f"{p:.4f}", "yes_bid_dollars": "0", "yes_ask_dollars": "0",
             "volume_fp": "1000.5", "close_time": close} for k, p in above]}
    return {"events": [ev("26DEC", "2026-12-09T18:55:00Z", [(3.5, 0.99), (3.75, 0.97), (4.0, 0.75), (4.25, 0.05)]),
                       ev("26OCT", (NOW + pd.Timedelta(days=2)).strftime("%Y-%m-%dT18:55:00Z"), [(3.5, 0.99), (3.75, 0.98), (4.0, 0.07), (4.25, 0.01)])]}


def soma_json() -> dict:
    weeks = pd.date_range("2008-01-02", NOW, freq="7D")
    rows = []
    for i, t in enumerate(weeks):
        nb = 0.5e12 + i * 3e9 if t < pd.Timestamp("2022-06-01") else 3.5e12
        rows.append({"asOfDate": str(t.date()), "mbs": str(1e12 if t > pd.Timestamp("2009-06-01") else 0), "cmbs": "0", "tips": "1e11", "frn": "0",
                     "tipsInflationCompensation": "0", "notesbonds": str(nb), "bills": "2e11", "agencies": "0", "total": str(nb + 1.3e12)})
    return {"soma": {"summary": rows}}


def mspd_json() -> dict:
    rows = []
    for i, t in enumerate(pd.date_range("2001-01-31", NOW - pd.DateOffset(months=1), freq="ME")):
        vals = {"Bills": 1e6 + i * 2e4, "Notes": 2e6 + i * 4e4, "Bonds": 5e5 + i * 1e4, "Treasury Inflation-Protected Securities": 1e5, "Floating Rate Notes": 0}
        for k, v in vals.items():
            rows.append({"record_date": str(t.date()), "security_type_desc": "Marketable", "security_class_desc": k, "total_mil_amt": str(v)})
        rows.append({"record_date": str(t.date()), "security_type_desc": "Total Marketable", "security_class_desc": "_", "total_mil_amt": str(sum(vals.values()))})
    return {"data": rows}


def buybacks_json() -> dict:
    rows = [{"operation_date": str(t.date()), "operation_type": "Liquidity Support" if i % 3 else "Cash Management", "security_type": "Nominal Coupons",
             "maturity_bucket": "10Y to 20Y", "total_par_amt_accepted": "2000000000.00"} for i, t in enumerate(pd.date_range("2024-05-29", NOW - pd.Timedelta(days=3), freq="14D"))]
    rows.append({"operation_date": str((NOW + pd.Timedelta(days=1)).date()), "operation_type": "Liquidity Support", "security_type": "TIPS",
                 "maturity_bucket": "1Y to 10Y", "total_par_amt_accepted": "null"})
    return {"data": rows}


def fake_fetch(url, ttl=0, **k):
    if "treasury.gov/resource-center" in url:
        y = int(url.split("daily-treasury-rates.csv/")[1][:4])
        text = treasury_csv(y, "real_yield" in url)
        if not text:
            raise ConnectionError("fixture: no such year")
        return text
    if "bankofengland" in url:
        code = url.split("SeriesCodes=")[1].split("&")[0]
        return boe_csv(code, int(url.split("Datefrom=01/Jan/")[1][:4]))
    if "ons.gov.uk" in url:
        return ons_csv(url.split("/timeseries/")[1].split("/")[0])
    raise ConnectionError(f"fixture: no text for {url}")


def fake_fetch_json(url, ttl=0, **k):
    if "imf.org" in url:
        return imf_json(url.rsplit("/", 1)[1])
    if "tips_cpi_data" in url:
        return tips_json()
    if "debt_to_penny" in url:
        return penny_json()
    if "mts_table_9" in url:
        return mts_json()
    if "avg_interest_rates" in url:
        return avg_rate_json()
    if "hkma" in url:
        return hkma_json(url, int(url.split("offset=")[1]))
    if "censtatd" in url:
        return csd_json()
    if "kalshi" in url:
        return kalshi_json()
    if "soma/summary" in url:
        return soma_json()
    if "mspd_table_1" in url:
        return mspd_json()
    if "buybacks_operations" in url:
        return buybacks_json()
    if "gamma-api.polymarket" in url:
        return poly_json()
    if "clob.polymarket" in url:
        return clob_json(url.split("market=")[1].split("&")[0])
    if "newyorkfed" in url:
        return nyfed_json()
    raise ConnectionError(f"fixture: no JSON for {url}")


def smoke_patch() -> None:
    """scripts/smoke.py: every debt-rates source answered from the fixtures above."""
    D.fetch, D.fetch_json = fake_fetch, fake_fetch_json


@pytest.fixture
def fixtures(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(D, "fetch", fake_fetch)
    monkeypatch.setattr(D, "fetch_json", fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()


def _pts_of(s):
    return B._pts(s, 2)


# ------------------------------------------------------------------ parsers
def test_imf_parser_keeps_the_four_countries_and_ignores_the_rest():
    d = D.parse_imf(imf_json("GGXWDG_NGDP"), "GGXWDG_NGDP")
    assert set(d) == {"USA", "GBR", "HKG", "CHN"}
    assert d["USA"].index[0] == pd.Timestamp("2000-01-01") and d["USA"].iloc[0] == 60
    with pytest.raises(ValueError):
        D.parse_imf({"values": {"GGXWDG_NGDP": {"FRA": {"2020": 1}}}}, "GGXWDG_NGDP")


def test_mts9_tells_receipts_total_from_outlays_total():
    m = D.parse_mts9(mts_json())
    assert {"receipts", "outlays", "interest", "defence", "education"} <= set(m.columns)
    assert m["receipts"].iloc[0] == pytest.approx(300.0) and m["outlays"].iloc[0] == pytest.approx(380.0)
    assert m.index[0] == pd.Timestamp("2014-10-01") and m.index.freqstr == "MS"


def test_treasury_csv_nominal_and_real_layouts():
    n = D.parse_treasury_csv(treasury_csv(2020, False))
    r = D.parse_treasury_csv(treasury_csv(2020, True))
    assert set(n) == {"10y", "2y"} and set(r) == {"10y"}
    assert n["10y"].index.is_monotonic_increasing and n["10y"].index[0] == pd.Timestamp("2020-01-02")
    with pytest.raises(ValueError):
        D.parse_treasury_csv("Date,1 Mo\n01/02/2020,1.0")


def test_boe_parser_refuses_an_error_page():
    assert D.parse_boe(boe_csv("IUDBEDR", 2020)).iloc[0] == pytest.approx(3.0)
    with pytest.raises(ValueError):
        D.parse_boe("<html>Invalid series</html>" + " " * 100)


def test_ons_parser_monthly_and_quarterly():
    s = D.parse_ons(ons_csv("hf6x"))
    assert s.index[0] == pd.Timestamp("1997-04-01")
    q = D.parse_ons('"Title","x"\n"2020 Q1","1.5"\n"2020 Q2","2.5"\n')
    assert list(q.index.month) == [1, 4]
    with pytest.raises(ValueError):
        D.parse_ons('"Title","x"\n')


def test_first_above():
    t = pd.date_range("2015-01-01", periods=6, freq="YS")
    a, b = pd.Series([1, 2, 5, 4, 6, 7], t), pd.Series([3, 3, 3, 5, 5, 5], t)
    assert D.first_above(a, b) == "2019-01-01"
    assert D.first_above(b, a) is None
    assert D.first_above(a + 10, b) == "always"


def test_hkma_parser_reads_every_page():
    assert D.parse_hkma([hkma_json("er-ir", 0)], "ir_1m").iloc[-1] == 1.5


# ------------------------------------------------------------------ payloads
def test_every_endpoint_on_fixtures(fixtures):
    for name in ("debt", "interest", "yields", "policy", "odds", "qe", "stress"):
        p = D.ENDPOINTS[name]()
        B.json_safe(p)
        errs = {k: v for k, v in p.items() if k.endswith("_error")}
        assert not errs, (name, errs)


def test_debt_payload(fixtures):
    p = D.ENDPOINTS["debt"]()
    assert set(p["imf"]) == {"US", "UK", "Hong Kong", "China"}
    us = p["imf"]["US"]
    assert us["actual"] and us["proj"] and us["proj"][0] == us["actual"][-1]          # the dashed line starts at the last actual
    assert {r["country"] for r in p["table"]} == {"US", "UK", "Hong Kong", "China"}
    assert p["us_now"]["total"] > 5 and p["us_now"]["per_day_bn"] > 0


def test_interest_payload_and_crossing(fixtures):
    p = D.ENDPOINTS["interest"]()
    us = p["us"]
    assert us["rolling"]["interest"] and us["share"]
    assert all(a["fy"] for a in us["annual"])
    assert us["cross"]["defence"] is None or isinstance(us["cross"]["defence"], (int, str))
    # net interest = primary - overall balance, from the committed IMF copy
    imf = {k: dict(v) for k, v in B.manual(D.SLUG, "imf").items()}
    t = pd.Timestamp("2010-01-01")
    want = imf["USA GGXONLB_G01_GDP_PT"][t] - imf["USA GGXCNL_G01_GDP_PT"][t]
    got = dict(p["imf_gdp"]["US"]["actual"])[int(t.timestamp())]
    assert got == pytest.approx(want, abs=0.01) and 1 < got < 5
    assert "UK" in p["hand"] and "interest" in p["hand"]["UK"]
    assert p["uk_share"] and 0 < p["uk_share"][-1][1] < 100


def test_yields_policy_and_stress(fixtures):
    y = D.ENDPOINTS["yields"]()
    assert set(y["nominal"]) == {"US", "UK", "Hong Kong", "China"} and len(y["real"]) == 2
    hk = y["nominal"]["Hong Kong"]
    assert pd.Timestamp(hk[-1][0], unit="s").year >= 2026                # HKGB rows follow the EFN series
    pol = D.ENDPOINTS["policy"]()
    assert pol["fed"]["upper"][0][1] == 6.5                               # hand-entered target from 2000
    assert all(v is not None for v in pol["now"].values()), pol["now"]
    base = dict(pol["hk"])
    t = int(pd.Timestamp("2010-01-01").timestamp())
    assert base[t] == pytest.approx(0.5)                                  # Fed lower end (0) + 0.5
    hib = pd.Series(1.25, index=pd.date_range("2009-01-01", "2011-01-01", freq="MS"))
    assert dict(_pts_of(D.hk_base(hib)))[t] == pytest.approx(1.25)        # the HIBOR term wins when it is higher
    s = D.ENDPOINTS["stress"]()
    assert {r["country"] for r in s["score"]} == {"US", "UK", "Hong Kong", "China"}
    row = next(r for r in s["score"] if r["country"] == "US")
    assert row["pb_star"] == pytest.approx(row["debt"] * row["r_g"] / (100 + row["g"]), abs=0.02)
    assert s["events"] and s["spread"]


def test_fed_range_with_a_point_target_from_the_api(fixtures, monkeypatch):
    """The NY Fed API can give a pre-2008 single target as targetRateFrom alone, on days the hand-entered history also covers."""
    n = pd.DataFrame({"effr": [1.0, 1.1, 0.2], "lo": [1.0, 1.0, 0.0], "hi": [None, None, 0.25]},
                     index=pd.to_datetime(["2008-10-29", "2008-11-03", "2008-12-16"]))
    monkeypatch.setattr(D, "nyfed", lambda: n.copy())
    r = D.fed_range()
    assert not r.index.duplicated().any() and r.loc["2008-11-03", "hi"] == 1.0
    assert len(D.steps(r["lo"])) and len(D.hk_base())
    B.json_safe(D.ENDPOINTS["policy"]())


def test_cpi_parsers():
    s = D.parse_tips_cpi(tips_json())
    assert s.index[0] == pd.Timestamp("2008-02-01") and s.iloc[0] == pytest.approx(211.693)
    last = (NOW - pd.DateOffset(months=2)).normalize().replace(day=1)
    assert s.index[-1] == last and s.iloc[-1] == pytest.approx(CPI_U[last], abs=0.001)    # the newest month, read off the daily line
    h = D.parse_csd_cpi(csd_json())
    assert (h == 1.5).all()                                                             # the composite CPI (A_CM), not the others
    with pytest.raises(ValueError):
        D.parse_tips_cpi({"data": []})


def test_poly_parser_keeps_open_markets_and_reads_yes():
    ev = D.parse_poly(poly_json())
    assert [e["slug"] for e in ev][:2] == ["fed-decision-in-october", "flips"] and ev[-1]["slug"] == "how-many-fed-rate-cuts-in-2026"   # soonest first
    cuts = next(e for e in ev if e["slug"] == "how-many-fed-rate-cuts-in-2026")["markets"]
    assert "old" not in [m["label"] for m in cuts] and next(m for m in cuts if m["label"] == "3 cuts")["yes"] == 0.6
    assert ev[0]["markets"][0]["token"] == "tok-25 bps decrease"
    assert D.parse_poly([{"title": "x", "markets": [{"outcomes": "not json"}]}]) == []


def test_fomc_decisions_and_meetings(fixtures):
    dec = D.fomc_decisions()
    assert dec[-1]["date"] == "2001-01-03" and dec[-1]["bp"] == -50                       # oldest kept change in the hand history
    assert all(r["bp"] != 0 for r in dec) and dec == sorted(dec, key=lambda r: r["date"], reverse=True)
    m = D.next_meetings(pd.Timestamp("2026-10-26"))
    assert m[0]["date"] == "2026-10-28" and all(r["source"].startswith("http") for r in m)


def test_policy_and_odds_payloads(fixtures):
    p = D.ENDPOINTS["policy"]()
    assert set(p["cpi"]) == {"US", "UK", "Hong Kong", "China"} and not p["cpi_missing"]
    assert p["cpi"]["US"][-1][1] == pytest.approx((1.0025 ** 12 - 1) * 100, abs=0.01)
    assert pd.Timestamp(p["cpi"]["US"][0][0], unit="s") == pd.Timestamp("2009-02-01")      # a year after the first TIPS month
    assert set(p["real"]) >= {"US", "UK", "Hong Kong"} and p["decisions"]
    o = D.ENDPOINTS["odds"]()
    assert not {k for k in o if k.endswith("_error")}, o
    assert o["history"]["title"] == "Fed decision in October?" and set(o["history"]["lines"]) == {"25 bps decrease", "No change"}
    assert [e["slug"] for e in o["events"]] == ["how-many-fed-rate-cuts-in-2026", "fed-decision-in-october", "fed-decision-in-december"]   # by volume, side market dropped
    assert o["fed_now"] is not None
    B.json_safe(p), B.json_safe(o)


def test_kalshi_ladder_becomes_level_probabilities():
    ev = D.parse_kalshi(kalshi_json())
    assert [e["ticker"] for e in ev] == ["KXFED-26OCT", "KXFED-26DEC"]                  # next meeting first
    lv = {x["upper"]: x["p"] for x in ev[0]["levels"]}
    assert lv[4.0] == pytest.approx(0.91, abs=0.01) and lv[4.25] == pytest.approx(0.06, abs=0.01)   # P(above 3.75) - P(above 4.0) = 0.98 - 0.07
    assert sum(lv.values()) == pytest.approx(1.0, abs=0.001)


def test_fomc_history_cycles_and_insights(fixtures):
    h = D.fomc_history(years=30)
    assert h == sorted(h, key=lambda d: d["date"]) and all("events" in d and "y10" in d for d in h)
    leh = next(d for d in h if d["date"] == "2008-10-08")
    assert leh["emergency"] and any("Lehman" in e["event"] for e in leh["events"])       # context from fomc_events.csv, flagged off-meeting
    c = D.fomc_cycles(h)
    assert {x["direction"] for x in c} == {"hiking", "cutting"} and all(x["moves"] >= 1 and x["months"] >= 0 for x in c)
    ins = D.fomc_insights(h, c)
    assert ins and ins[0].startswith("Since 20") and any("cutting cycles opened" in t for t in ins)
    o = D.ENDPOINTS["odds"]()
    assert o["fomc"]["insights"] and o["fomc"]["decisions"][0]["date"] >= o["fomc"]["decisions"][-1]["date"] and o["kalshi"]


def test_qe_and_maturity(fixtures):
    q = D.ENDPOINTS["qe"]()
    assert not {k for k in q if k.endswith("_error")}, q
    assert q["share"] and 0 < q["share"][-1][1] < 100
    assert q["buybacks"]["ops"] > 10 and q["buybacks"]["next"] and set(q["buybacks"]["monthly"]) == {"Liquidity Support", "Cash Management"}
    covid = next(r for r in q["programmes"] if r["name"] == "Covid QE")
    assert covid["fed_change_tn"] is not None and covid["fed_change_tn"] > 0
    d = D.ENDPOINTS["debt"]()
    m = d["maturity"]["now"]
    assert 0 < m["bills_share"] < 100 and d["maturity_avg"]


def test_readings_come_from_the_cached_payloads(fixtures):
    assert D.READINGS() == []                                             # nothing computed yet: nothing to report, nothing fetched
    for name in ("debt", "interest", "yields", "policy", "odds", "qe", "stress"):
        D.ENDPOINTS[name]()
    rows = D.READINGS()
    keys = {r["key"] for r in rows}
    assert {r["tab"] for r in rows} == {"debt", "interest", "yields", "policy", "odds", "qe", "stress"}
    assert {"cpi_US", "next_25 bps decrease", "kalshi_hold", "fed_share", "us_bills_share"} <= keys
    assert {"debt_US", "us_per_day", "us_int_share", "us_int_vs_def", "y10_US", "gap_US", "spread_US"} <= keys
    assert all(r["lean"] in (-1, 0, 1) and r["tab"] in {"debt", "interest", "yields", "policy", "odds", "qe", "stress"} for r in rows)
    B.json_safe(rows)


def test_a_dead_source_blanks_one_chart(fixtures, monkeypatch):
    def no_penny(url, ttl=0, **k):
        if "debt_to_penny" in url:
            raise ConnectionError("down")
        return fake_fetch_json(url, ttl, **k)
    monkeypatch.setattr(D, "fetch_json", no_penny)
    p = D.ENDPOINTS["debt"]()
    assert p["us_total"] is None and p["us_total_error"] == "ConnectionError" and p["imf"]["US"]["actual"]


def test_imf_copy_covers_the_four_countries_and_the_scorecard_inputs():
    for key in D.IMF_IND:
        assert set(D.imf(key)) == {"USA", "GBR", "HKG", "CHN"}, key
    rows = B.manual_rows(D.SLUG, "imf")
    assert all("verify" in r["note"] for r in rows if r["series"][:3] in ("CHN", "HKG"))


def test_hand_entered_rows_cite_a_source():
    import csv
    for f in (B.MANUAL_DIR / "debt-rates").glob("*.csv"):
        rows = [r for r in csv.DictReader(f.open()) if r["date"] and not r["date"].startswith("#")]
        assert rows, f.name
        for r in rows:
            assert r["source"].startswith("http"), (f.name, r)
            pd.Timestamp(r["date"])


# ------------------------------------------------------------------ live (run by hand: pytest -m network tests/test_debt_rates.py)
@pytest.mark.network
@pytest.mark.parametrize("key", ["debt", "primary", "balance", "revenue", "growth", "inflation"])
def test_live_imf(key):
    """imf.org refuses the Railway server; run from a machine that can reach it, and compare with data/debt-rates/imf.csv."""
    live, copy = D.imf_live(key), D.imf(key)
    assert len(live) == 4
    for iso in ("USA", "GBR"):
        j = pd.concat([live[iso], copy[iso]], axis=1).dropna()
        assert (j.iloc[:, 0] - j.iloc[:, 1]).abs().max() < 0.5, (key, iso)


@pytest.mark.network
def test_live_fiscal_data():
    assert D.mts()["interest"].notna().sum() > 100
    assert D.penny()["tot_pub_debt_out_amt"].iloc[-1] > 30
    assert len(D.avg_rate()) > 100


@pytest.mark.network
def test_live_yields_and_rates():
    assert len(D.treasury("daily_treasury_yield_curve")["10y"]) > 4000
    assert len(D.boe("uk10", 2020)) > 100 and len(D.boe("uk10_real", 2020)) > 100
    assert D.ons("receipts").iloc[-1] > 10000
    assert len(D.nyfed()) > 1000
    assert len(D.hkma(D.HK_EFBN, "efn_10y")) > 50                    # HKMA refuses Railway; the page reads data/debt-rates/hk_10y.csv
