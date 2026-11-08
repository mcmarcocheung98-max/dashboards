"""AI Stocks: the setup after the dip (/ai-stocks) on fixtures: Nasdaq closes, FRED/Cboe VIX and EDGAR companyfacts, no network.
smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import asyncio
import json

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B
from app.topics import ai_stocks as M
from app.topics import compute_chips as CC
from tests import test_compute_chips as TC

DAYS = pd.bdate_range("2019-01-02", "2026-11-04")
# market path: up-trend with drawdowns in 2020 (-30%), 2022 (-45%), mid-2024 (-18%), spring 2025 (-28%) and a dip now (Oct-Nov 2026)
SHOCKS = [("2020-02-20", "2020-03-20", -0.35, 60), ("2022-01-01", "2022-10-14", -0.50, 250), ("2024-07-10", "2024-08-07", -0.20, 50),
          ("2025-02-19", "2025-04-08", -0.32, 70), ("2026-10-01", "2026-11-04", -0.17, 0)]


def market() -> pd.Series:
    t = np.arange(len(DAYS))
    logp = 0.0009 * t + 0.01 * np.sin(t / 9)
    s = pd.Series(logp, index=DAYS)
    for a, b, depth, rec in SHOCKS:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        fall = (DAYS >= a) & (DAYS <= b)
        k = np.cumsum(fall) / max(1, fall.sum())
        hit = np.log(1 + depth)
        drop = np.where(DAYS < a, 0.0, np.where(DAYS <= b, hit * k, hit))
        if rec:
            after = (DAYS > b)
            j = np.cumsum(after)
            drop = np.where(after, hit * np.clip(1 - j / rec, 0, 1), drop)
        s = s + drop
    return s


MKT = market()


def closes(sym: str) -> pd.Series:
    rng = np.random.default_rng(sum(map(ord, sym)))
    beta = 0.7 + (sum(map(ord, sym)) % 9) / 10
    noise = np.cumsum(rng.normal(0, 0.008, len(DAYS)))
    s = pd.Series(np.exp(beta * MKT.values + noise) * (20 + len(sym) * 15), index=DAYS)
    return s[s.index >= "2023-09-14"] if sym == "ARM" else s


def nasdaq_json(sym: str) -> dict:
    s = closes(sym) if sym not in ("QQQ", "SPY", "SMH") else pd.Series(np.exp({"QQQ": 0.8, "SPY": 0.55, "SMH": 1.1}[sym] * MKT.values) * 300, index=DAYS)
    return {"data": {"tradesTable": {"rows": [{"date": d.strftime("%m/%d/%Y"), "close": f"${v:,.2f}"} for d, v in s.items()][::-1]}}}


def vix_csv(cboe: bool = False) -> str:
    v = 15 + 25 * np.clip(-(MKT - MKT.cummax()) * 2.5, 0, 2)
    if cboe:
        return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(f"{d.strftime('%m/%d/%Y')},{x:.2f},{x + 1:.2f},{x - 1:.2f},{x:.2f}" for d, x in v.items())
    rows = [f"{d.date()},{x:.2f}" for d, x in v.items()]
    rows[5] = rows[5].split(",")[0] + ",."                                # FRED marks holidays with '.'
    return "observation_date,VIXCLS\n" + "\n".join(rows)


def revenue_facts(cik: int) -> str:
    return TC.companyfacts(1 + cik % 7, "Revenues", year_to_date=False)


# ---- EDGAR fixtures: each fund's submissions, filing index and 13F information table (two quarters)
FUND_CIKS = [int(r["cik"]) for r in B.manual_rows("ai-stocks", "funds")]
CUSIP = {v: k for k, v in M.cusip_map().items()}                         # ticker -> a CUSIP (GOOGL: class C, the later row)


def holdings(cik: int, q: int) -> list[tuple]:
    """(cusip, name, shares, value, putCall) rows of fund `cik` in quarter q (0 = latest, 1 = the one before)."""
    rng = np.random.default_rng(cik + q)
    tickers = list(M.STOCKS)
    held = [s for i, s in enumerate(tickers) if (cik + i + q) % 3]                # a different set each quarter: New and Sold
    rows = [(CUSIP[s], M.NAMES[s].upper(), float(rng.integers(1, 50) * 1000), float(rng.integers(1, 500) * 1e5), "") for s in held]
    rows += [("000000AA0", "NVIDIA CORP", 5000.0, 9e6, ""),                       # the right name, a wrong CUSIP: never counted
             (CUSIP["NVDA"], "NVIDIA CORPORATION", 100.0, 7e6, "Call"),          # an option row: not a holding
             ("12345X101", "OTHER CO", 100.0, 3e8, "")]
    return rows


def infotable_xml(rows) -> str:
    one = lambda c, n, sh, v, pc: (f"<infoTable><nameOfIssuer>{n}</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{c}</cusip><value>{v:.0f}</value>"
                                   f"<shrsOrPrnAmt><sshPrnamt>{sh:.0f}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>"
                                   + (f"<putCall>{pc}</putCall>" if pc else "") + "<investmentDiscretion>SOLE</investmentDiscretion></infoTable>")
    return ('<?xml version="1.0"?><informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
            + "".join(one(*r) for r in rows) + "</informationTable>")


QUARTERS = [("2026-06-30", "2026-08-14"), ("2026-03-31", "2026-05-15"), ("2025-12-31", "2026-02-13")]


def submissions(cik: int) -> str:
    rows = [("13F-HR", f"0000000000-26-{cik % 1000:03d}{i}00", f, q, "primary_doc.xml") for i, (q, f) in enumerate(QUARTERS)]
    rows.insert(0, ("13F-HR/A", f"0000000000-26-{cik % 1000:03d}900", "2026-09-02", QUARTERS[0][0], "primary_doc.xml"))   # an amendment: skipped
    rows.append(("SC 13G", "0000000000-26-000001", "2026-01-01", "", "x.htm"))
    cols = ["form", "accessionNumber", "filingDate", "reportDate", "primaryDocument"]
    return json.dumps({"name": f"FUND {cik}", "filings": {"recent": {c: [r[i] for r in rows] for i, c in enumerate(cols)}}})


TODAY = pd.Timestamp.now().normalize()
ago = lambda n: str((TODAY - pd.Timedelta(days=n)).date())
# each company's Form 4 filings: (accession tail, filed days ago, issuer CIK or None = the company, owner, role xml, plan box, footnote, [(code, days ago, shares, price)])
DIRECTOR = "<isDirector>1</isDirector><isOfficer>0</isOfficer>"
CFO = "<isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Financial Officer</officerTitle>"
FORM4 = {
    "NVDA": [("01", 3, None, "DOE JANE", DIRECTOR, "0", "", [("P", 4, 1000, 150.0)]),
             ("02", 12, None, "ROE RICHARD", CFO, "0", "", [("P", 14, 500, 160.0), ("S", 14, 100, 161.0)]),          # a cluster with Jane Doe
             ("03", 20, None, "HUANG J", "<isOfficer>1</isOfficer><officerTitle>CEO</officerTitle>", "1", "", [("S", 21, 50000, 170.0), ("G", 21, 9, 0.0)]),
             ("04", 30, None, "KRESS C", CFO, "0", "Sold under a Rule 10b5-1 trading plan adopted in May.", [("S", 31, 2000, 165.0)]),
             ("05", 150, None, "OLD BUYER", DIRECTOR, "0", "", [("P", 151, 100, 100.0)]),                              # older than 90 days
             ("06", 5, 999999, "NVIDIA CORP", "<isTenPercentOwner>1</isTenPercentOwner>", "0", "", [("P", 6, 1e6, 10.0)])],  # Nvidia buying another stock
    "AMD": [("01", 50, None, "SMITH A", DIRECTOR, "0", "", [("P", 50, 300, 200.0)])],
}


def form4_xml(sym: str, row) -> str:
    acc, filed, issuer, owner, rel, plan, foot, txns = row
    tx = "".join(f"<nonDerivativeTransaction><securityTitle><value>Common</value></securityTitle><transactionDate><value>{ago(d)}</value></transactionDate>"
                 f"<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{c}</transactionCode></transactionCoding>"
                 f"<transactionAmounts><transactionShares><value>{sh}</value></transactionShares><transactionPricePerShare><value>{px}</value></transactionPricePerShare>"
                 f"<transactionAcquiredDisposedCode><value>{'A' if c == 'P' else 'D'}</value></transactionAcquiredDisposedCode></transactionAmounts></nonDerivativeTransaction>"
                 for c, d, sh, px in txns)
    return (f'<?xml version="1.0"?><ownershipDocument><schemaVersion>X0609</schemaVersion><documentType>4</documentType>'
            f"<issuer><issuerCik>{issuer or M.CIKS[sym]:010d}</issuerCik><issuerTradingSymbol>{sym}</issuerTradingSymbol></issuer>"
            f"<reportingOwner><reportingOwnerId><rptOwnerCik>0000000001</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>"
            f"<reportingOwnerRelationship>{rel}</reportingOwnerRelationship></reportingOwner><aff10b5One>{plan}</aff10b5One>"
            f"<nonDerivativeTable>{tx}<nonDerivativeHolding><securityTitle><value>Common</value></securityTitle></nonDerivativeHolding></nonDerivativeTable>"
            + (f'<footnotes><footnote id="F1">{foot}</footnote></footnotes>' if foot else "") + "</ownershipDocument>")


def company_submissions(cik: int) -> str:
    sym = next(s for s, c in M.CIKS.items() if c == cik)
    rows = [("4", f"0000000001-26-{cik % 10000:04d}{r[0]}", ago(r[1]), "", f"xslF345X06/form4_{r[0]}.xml") for r in FORM4.get(sym, [])]
    rows.append(("10-Q", "0000000001-26-000099", ago(10), ago(40), "q.htm"))
    cols = ["form", "accessionNumber", "filingDate", "reportDate", "primaryDocument"]
    return json.dumps({"name": sym, "filings": {"recent": {c: [r[i] for r in rows] for i, c in enumerate(cols)}}})


def panel_facts(cik: int) -> str:
    """companyfacts for the stock panel: income statement in 3-month facts, cash flows year to date, equity and debt at period ends."""
    g = {}
    for tag, scale, ytd in (("Revenues", 10, False), ("GrossProfit", 6, False), ("OperatingIncomeLoss", 3, False), ("NetIncomeLoss", 2, False),
                            ("NetCashProvidedByUsedInOperatingActivities", 3, True), ("PaymentsToAcquirePropertyPlantAndEquipment", 1, True)):
        g[tag] = json.loads(TC.companyfacts(scale, tag, year_to_date=ytd))["facts"]["us-gaap"][tag]
    eps = json.loads(TC.companyfacts(1e-9, "EarningsPerShareDiluted", year_to_date=False))["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD"]
    g["EarningsPerShareDiluted"] = {"units": {"USD/shares": eps}}
    ends = [e for y in range(2019, 2027) for e in (f"{y}-03-31", f"{y}-06-30", f"{y}-09-30", f"{y}-12-31") if e <= "2026-06-30"]
    g["StockholdersEquity"] = {"units": {"USD": [{"end": e, "val": 80e9 + i * 1e9, "filed": e, "form": "10-Q"} for i, e in enumerate(ends)]}}
    g["LongTermDebt"] = {"units": {"USD": [{"end": e, "val": 20e9, "filed": e, "form": "10-Q"} for e in ends]}}
    return json.dumps({"cik": cik, "facts": {"us-gaap": g, "dei": {}}})


def edgar_fixture(url: str) -> str:
    if "/companyfacts/" in url:
        return panel_facts(int(url.rsplit("CIK", 1)[1].split(".")[0]))
    if "/submissions/CIK" in url:
        cik = int(url.rsplit("CIK", 1)[1].split(".")[0])
        return company_submissions(cik) if cik in M.CIKS.values() else submissions(cik)
    if "/form4_" in url:
        cik, acc = url.split("/data/")[1].split("/")[:2]
        sym = next(s for s, c in M.CIKS.items() if c == int(cik))
        return form4_xml(sym, next(r for r in FORM4[sym] if acc.endswith(r[0])))
    if url.endswith("index.json"):
        return json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "infotable.xml"}, {"name": "x-index.html"}]}})
    if url.endswith("infotable.xml"):
        cik, acc = url.split("/data/")[1].split("/")[:2]
        return infotable_xml(holdings(int(cik), int(acc[-3])))
    raise ConnectionError("fixture: unknown EDGAR url " + url)


def is_edgar(url: str) -> bool:
    return "sec.gov/submissions" in url or "/Archives/edgar/" in url or "/companyfacts/" in url


def patch_download(set_attr=setattr):
    """EDGAR answers from the fixtures at the download level, so the real fetch keeps memory and disk copies as on the server."""
    real = B._download
    set_attr(B, "_download", lambda url, *a, **k: edgar_fixture(url) if is_edgar(url) else real(url, *a, **k))


def fake_fetch(url, ttl=0, **k):
    if is_edgar(url) and ("/companyfacts/" not in url or k.get("key", "").endswith("#panel")):
        return B.fetch(url, ttl, **k)
    if "fredgraph" in url:
        return vix_csv()
    if "cboe" in url:
        return vix_csv(cboe=True)
    if "companyfacts" in url:
        text = revenue_facts(int(url.rsplit("CIK", 1)[1].split(".")[0]))
        return k["reduce"](text) if k.get("reduce") else text
    raise ConnectionError("fixture: unknown url " + url)


def fake_fetch_json(url, ttl=0, **k):
    if "api.nasdaq.com" in url:
        return nasdaq_json(url.split("/quote/")[1].split("/")[0])
    raise ConnectionError("fixture: unknown url " + url)


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above (capex through compute_chips' fixtures)."""
    M.fetch = fake_fetch
    M.fetch_json = fake_fetch_json
    M.EDGAR_PACE = 0
    patch_download()
    TC.smoke_patch()
    M.fill_13f()                                                       # what the background jobs would have kept
    M.fill_insiders()


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(M, "EDGAR_PACE", 0)
    patch_download(monkeypatch.setattr)
    monkeypatch.setattr(CC, "_get", TC.fake_get)
    monkeypatch.setattr(CC, "fetch", TC.fake_fetch)
    monkeypatch.setattr(CC, "fetch_json", TC.fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ pure pieces
def test_registered():
    t = topics.REGISTRY["ai-stocks"]
    assert t.module == "ai_stocks" and {k for k, _ in t.tabs} == {"setup", "drawdown", "trend", "dips", "fear", "fundamentals", "institutions", "insiders"} <= set(M.ENDPOINTS)
    assert M.fill_13f in M.BACKGROUND and M.fill_insiders in M.BACKGROUND
    assert topics.category("ai-stocks") == "Money & markets"
    m = topics.meta("ai-stocks")
    assert m["sources"] and "Not investment advice" in m["notes"] and "Not investment advice" in m["footer"] and m["method"]


def test_basket_index_is_equal_weight_and_joins_late_members():
    d = pd.bdate_range("2019-12-30", periods=6)
    a = pd.Series([10, 10, 11, 11, 11, 11.0], index=d)       # +10% on day 3
    b = pd.Series([50, 50, 50, 45, 45, 45.0], index=d)       # -10% on day 4
    c = pd.Series([7, 14.0], index=d[4:])                   # lists on day 5, doubles on day 6
    s = M.basket_index({"A": a, "B": b, "C": c})
    assert s.loc["2020-01-01"] == pytest.approx(100) and s.loc["2019-12-31"] == pytest.approx(100 / 1.05)   # A's +10% that day, averaged with B's 0
    assert s.iloc[-2] / s.iloc[-3] == pytest.approx(1.0)     # C's first close is not a return
    assert s.iloc[-1] / s.iloc[-2] == pytest.approx(1 + 1.0 / 3)


def test_full_months_joins_picks_from_their_first_full_month():
    s = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2025-02-24", periods=40))
    j = M.full_months(s)
    assert j.index[0] == pd.Timestamp("2025-02-28") and j.index[1] == pd.Timestamp("2025-03-03")   # base: the last close before March
    old = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2019-01-02", periods=40))
    assert M.full_months(old).equals(old)
    on_first = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2025-04-01", periods=40))
    assert M.full_months(on_first).index[0] == pd.Timestamp("2025-04-01")


def test_drawdown_and_episodes():
    d = pd.bdate_range("2020-01-01", periods=12)
    s = pd.Series([100, 110, 99, 88, 90, 112, 105, 100, 95, 92, 93, 94.0], index=d)
    dd = M.drawdown(s)
    assert dd.iloc[1] == 0 and dd.iloc[3] == pytest.approx(88 / 110 - 1)
    eps = M.episodes(s, -0.10)
    assert len(eps) == 2
    first, cur = eps
    assert first["depth"] == pytest.approx(-0.2, abs=1e-4) and first["recovered"] == str(d[5].date()) and first["cross15"] == str(d[3].date())
    assert first["days_to_bottom"] == (d[3] - d[1]).days and first["days_to_recover"] == (d[5] - d[3]).days and not first["ongoing"]
    assert cur["ongoing"] and cur["recovered"] is None and cur["days_to_recover"] is None and cur["cross15"] == str(d[8].date())


def test_breadth_and_rsi():
    d = pd.bdate_range("2019-01-01", periods=300)
    up = pd.Series(np.linspace(10, 30, 300), index=d)
    down = pd.Series(np.linspace(30, 10, 300), index=d)
    b = M.breadth({"NVDA": up, "AMD": down}, 50)
    assert b.iloc[-1] == pytest.approx(0.5) and b.index[0] == d[49]
    assert M.rsi(up).iloc[-1] > 90 and M.rsi(down).iloc[-1] < 10


def test_parse_vix_both_layouts():
    f, c = M.parse_vix(vix_csv()), M.parse_vix(vix_csv(cboe=True))
    assert len(f) == len(DAYS) - 1 and len(c) == len(DAYS) and f.index.is_monotonic_increasing
    assert f.iloc[-1] == pytest.approx(c.iloc[-1])
    with pytest.raises(ValueError):
        M.parse_vix("a,b\n1,2")


def test_score_parts_rank_each_component_against_its_own_history():
    d = pd.bdate_range("2020-01-01", periods=300)
    idx = pd.Series(np.linspace(100, 200, 300), index=d)                    # rising all the way: a new high every day
    b50 = pd.Series(np.linspace(0, 1, 300), index=d)
    r = pd.Series(np.linspace(20, 80, 300), index=d)
    vix = pd.Series(np.linspace(40, 10, 300), index=d)                      # falling VIX reads as euphoria (inverted)
    qqq = pd.Series(np.linspace(100, 150, 300), index=d)
    parts = M.score_parts(idx, b50, r, vix, qqq)
    assert list(parts.columns) == ["dd", "b50", "rsi", "vix", "rel"]
    assert parts["b50"].iloc[-1] > 99 and parts["b50"].iloc[0] < 1 and parts["vix"].iloc[-1] > 99
    sc = M.setup_score(parts)
    assert sc.index[0] == d[M.SMOOTH - 1] and 0 <= sc.min() and sc.max() <= 100      # four parts from day one; rel joins after 63 days
    assert M.setup_score(parts[["dd", "b50"]]).empty                                     # fewer than three parts: no score
    assert sc.iloc[-1] > 65 and sc.iloc[-1] > sc.iloc[70]                                 # dd ties at 0 (a high every day) rank 50


def test_bands_whipsaw_and_episodes():
    assert [M.band_of(v) for v in (0, 9.99, 10, 19.9, 20, 50, 80, 89.9, 90, 100)] == \
        ["washout", "washout", "fear", "fear", "soft", "neutral", "warm", "warm", "stretched", "stretched"]
    d = pd.bdate_range("2024-01-01", periods=200)
    sc = pd.Series(50.0, index=d)
    sc.iloc[10:13] = 5                                                      # washout
    sc.iloc[25] = 8                                                         # back within 30 days: the same episode
    sc.iloc[80:82] = 7                                                      # a new one
    sc.iloc[150] = 95
    starts = M.band_runs(sc, lambda v: v < 10)
    assert starts == [d[10], d[80]]
    assert M.band_changes(sc, 90) == 2                                      # 50 -> 95 -> 50 in the last 90 days
    idx = pd.Series(np.linspace(100, 300, 200), index=d)
    idx.iloc[151:160] = 120                                                 # a fall after the stretched day
    E = M.score_episodes(sc, idx)
    assert [e["date"] for e in E["green"]] == [str(d[80].date()), str(d[10].date())]
    g = E["green"][-1]
    assert g["best6m"] == pytest.approx(idx.iloc[11:137].max() / idx.iloc[10] - 1, abs=1e-4) and not g["partial6m"] and g["partial12m"]
    r = E["red"][0]
    assert r["worst90d"] == pytest.approx(120 / idx.iloc[150] - 1, abs=1e-4) and r["partial"] is True          # 90 days not passed yet


def test_band_stats_and_sentence():
    d = pd.bdate_range("2021-01-01", periods=400)
    sc = pd.Series(np.where(np.arange(400) < 200, 5.0, 60.0), index=d)
    idx = pd.Series(np.linspace(100, 200, 400), index=d)
    st = {r["band"]: r for r in M.band_stats(sc, idx)}
    assert st["washout"]["days"] == 200 and st["washout"]["episodes"] == 1 and st["washout"]["3m"]["hit"] == 1.0
    assert st["neutral"]["6m"]["n"] == 200 - 126 and st["stretched"]["days"] == 0 and st["stretched"]["1m"]["median"] is None
    s = M.band_sentence(list(st.values()), "washout")
    assert "200 trading days" in s and "not a forecast" in s and "buy" not in s.lower()
    assert "No day" in M.band_sentence(list(st.values()), "stretched")


def test_events_name_episodes(mocked):
    ev = M._events()
    assert any(n.startswith("Covid") for _, n in ev) and M._event_name(pd.Timestamp("2020-03-20"), ev).startswith("Covid")
    assert M._event_name(pd.Timestamp("2021-07-01"), ev) is None


def test_reduce_13f_matches_by_cusip_only_and_keeps_options_apart():
    rows = holdings(1067983, 0)
    out = json.loads(M.reduce_13f(M.cusip_map())(infotable_xml(rows)))
    assert out["rows"] == len(rows) and out["total"] == pytest.approx(sum(r[3] for r in rows))     # the total counts every row
    held = {s for s in M.STOCKS if any(r[0] == CUSIP[s] and not r[4] for r in rows)}
    assert set(out["hold"]) == held
    if "NVDA" in held:                                                      # the decoy named NVIDIA CORP with another CUSIP is not added
        nv = [r for r in rows if r[0] == CUSIP["NVDA"] and not r[4]][0]
        assert out["hold"]["NVDA"]["shares"] == nv[2]
    assert out["options"]["NVDA"] == 7e6
    by_name = M.reduce_13f({})(infotable_xml(rows))                         # an empty map: nothing is matched, whatever the names say
    assert json.loads(by_name)["hold"] == {}
    two = infotable_xml([(CUSIP["MSFT"], "MICROSOFT CORP", 10.0, 100.0, ""), (CUSIP["MSFT"], "MICROSOFT CORP", 5.0, 50.0, ""),
                         ("02079K305", "ALPHABET INC", 1.0, 10.0, ""), ("02079K107", "ALPHABET INC", 2.0, 20.0, "")])
    h = json.loads(M.reduce_13f(M.cusip_map())(two))["hold"]
    assert h["MSFT"] == {"shares": 15.0, "value": 150.0} and h["GOOGL"] == {"shares": 3.0, "value": 30.0}   # rows summed; class A and C


def test_cusip_map_is_complete_and_unique():
    rows = B.manual_rows("ai-stocks", "cusips")
    assert set(M.cusip_map().values()) == set(M.STOCKS) and len({r["cusip"] for r in rows}) == len(rows)
    assert all(len(r["cusip"]) == 9 and r["source"].startswith("https://www.sec.gov/") for r in rows)
    assert len(M.funds()) == 10 and len({f["cik"] for f in M.funds()}) == 10


def test_classify_new_added_trimmed_sold():
    prev = {"A": {"shares": 100, "value": 1000}, "B": {"shares": 50, "value": 500}, "C": {"shares": 10, "value": 100}, "D": {"shares": 5, "value": 50}}
    now = {"A": {"shares": 150, "value": 1800}, "B": {"shares": 20, "value": 300}, "D": {"shares": 5, "value": 80}, "E": {"shares": 7, "value": 70}}
    c = {x["ticker"]: x for x in M.classify(prev, now)}
    assert {k: v["tag"] for k, v in c.items()} == {"A": "Added", "B": "Trimmed", "C": "Sold", "E": "New"}     # D unchanged: not listed
    assert c["A"]["usd"] == 600 and c["B"]["usd"] == -450 and c["C"]["usd"] == -100 and c["E"]["usd"] == 70  # shares x this quarter's price
    cards = [{"short": "F1", "changes": M.classify(prev, now)}, {"short": "F2", "changes": [{"ticker": "C", "tag": "New", "usd": 900}]}]
    cs = M.consensus(cards)
    assert [r["ticker"] for r in cs][:2] == ["A", "E"] and next(r for r in cs if r["ticker"] == "C")["net"] == 0
    assert next(r for r in cs if r["ticker"] == "C")["net_usd"] == 800 and cs[-1]["ticker"] == "B"


def test_institutions_tab_reads_only_what_the_background_job_kept(mocked, monkeypatch):
    p = M._institutions_now()
    assert not p["funds"] and set(p["errors"].values()) == {"not fetched yet"}               # a page view never downloads
    calls = []
    real = M.fetch
    monkeypatch.setattr(M, "fetch", lambda url, *a, **k: calls.append(url) or real(url, *a, **k))
    assert set(M.fill_13f().values()) == {"ok"}
    assert len(calls) == 10 * 5                                             # submissions, then index + table for two quarters
    calls.clear()
    M.fill_13f()
    assert calls == []                                                      # kept copies younger than their TTL: nothing downloaded
    p = M._institutions_now()
    assert len(p["funds"]) == 10 and not p["errors"]
    f = p["funds"][0]
    assert f["quarter"] == "2026-06-30" and f["prev_quarter"] == "2026-03-31" and f["filed"] == "2026-08-14"   # the amendment is skipped
    assert f["link"].endswith("-index.htm") and f["total"] > f["ai_value"] > 0 and len(f["top"]) <= 3
    assert {c["tag"] for x in p["funds"] for c in x["changes"]} == {"New", "Added", "Trimmed", "Sold"}
    assert p["consensus"] == sorted(p["consensus"], key=lambda r: (-r["net"], -r["net_usd"]))
    assert 0 <= p["net_adding"] <= p["with_change"] == 10
    B.json_safe(p)


def test_reduce_form4_keeps_purchases_and_sales_with_roles_and_plans():
    f = json.loads(M.reduce_form4(form4_xml("NVDA", FORM4["NVDA"][2])))
    assert f["issuer"] == M.CIKS["NVDA"] and f["owners"] == [{"name": "HUANG J", "role": "CEO"}] and f["plan"] is True
    assert [x["code"] for x in f["txns"]] == ["S"]                          # the gift (G) is not an open-market trade
    f = json.loads(M.reduce_form4(form4_xml("NVDA", FORM4["NVDA"][3])))
    assert f["plan"] is True and f["owners"][0]["role"] == "Chief Financial Officer"   # 10b5-1 named in a footnote
    f = json.loads(M.reduce_form4(form4_xml("NVDA", FORM4["NVDA"][0])))
    assert f["plan"] is False and f["owners"][0]["role"] == "Director" and f["txns"][0] == {"code": "P", "date": ago(4), "shares": 1000.0, "price": 150.0}


def test_plan_detection_box_footnote_remarks():
    real = "The reported transaction was effected pursuant to a Rule 10b5-1 trading plan adopted by the Reporting Person on June 16, 2026."
    row = lambda foot: ("09", 3, None, "KRESS COLETTE", CFO, "0", foot, [("S", 4, 1000, 220.0)])     # Nvidia, Sep 2026 (real footnote text)
    plan = lambda xml: json.loads(M.reduce_form4(xml))["plan"]
    assert plan(form4_xml("NVDA", row(real)))
    assert plan(form4_xml("NVDA", row("Sold under a RULE 10B5-1(c) trading arrangement.")))
    assert plan(form4_xml("NVDA", row("Plan under Rule 10b5\u20111.")))
    no_plan = form4_xml("NVDA", row("Represents weighted average sales price. The shares were sold at prices ranging from $220.60 to $221.28."))
    assert not plan(no_plan)                                     # Mark Stevens' sales of Sep 2026: no box, no plan footnote, no remarks
    assert plan(no_plan.replace("</ownershipDocument>", "<remarks>All sales pursuant to a 10b5-1 plan.</remarks></ownershipDocument>"))


def test_insiders_tab_and_clusters(mocked):
    p = M._insiders_now()
    assert not p["stocks"] and "not fetched yet" in set(p["errors"].values())           # a page view never downloads
    assert set(M.fill_insiders().values()) == {"ok"}
    p = M._insiders_now()
    assert not p["errors"] and set(p["foreign"]) == {"TSM", "ASML", "ARM"} and "TSM" not in p["stocks"]
    buys = p["buys"]
    assert [(b["sym"], b["name"]) for b in buys] == [("NVDA", "DOE JANE"), ("NVDA", "ROE RICHARD"), ("AMD", "SMITH A")]   # newest first; old and non-issuer left out
    assert buys[0]["cluster"] and buys[1]["cluster"] and not buys[2]["cluster"]           # two NVDA insiders within 30 days
    assert buys[0]["value"] == 150000 and buys[0]["link"].endswith("-index.htm")
    s = p["stocks"]["NVDA"]["sales"]
    assert s["n"] == 3 and s["insiders"] == 3 and s["plan_n"] == 2 and s["value"] == 100 * 161 + 50000 * 170 + 2000 * 165
    assert s["plan_value"] == 50000 * 170 + 2000 * 165
    assert p["buys30"] == 2 and p["clusters30"] == ["NVDA"]
    B.json_safe(p)


def test_flag_clusters_needs_two_insiders():
    b = lambda n, d: {"sym": "X", "name": n, "date": d}
    rows = M.flag_clusters([b("A", "2026-01-01"), b("A", "2026-01-10"), b("B", "2026-03-01"), b("C", "2026-03-30")])
    assert [r["cluster"] for r in rows] == [False, False, True, True]


def test_stock_fundamentals(mocked):
    M.fill_insiders()
    c = M._companies_now()
    assert not c["errors"] and c["stocks"]["TSM"]["foreign"] and "IFRS" in c["stocks"]["ASML"]["why"]
    f = c["stocks"]["NVDA"]
    assert f["available"] and f["period_end"] == "2026-06-30" and f["form"] == "10-Q"
    m = {k: v["v"] for k, v in f["metrics"].items()}
    assert m["gross_margin"] == pytest.approx(0.6) and m["op_margin"] == pytest.approx(0.3) and m["rev_growth"] > 0 and m["eps_growth"] > 0
    assert m["fcf"] == pytest.approx(2 * sum(1 + 0.04 * (12 * 4 + q) for q in range(-2, 2)), rel=1e-3)   # (3 - 1) x the quarterly base, $bn
    assert m["debt_equity"] == pytest.approx(20 / (80 + 29), abs=1e-3) and 0 < m["roe"] < 1
    assert all(len(v["spark"]) >= 8 for v in f["metrics"].values())
    B.json_safe(c)


def test_fundamentals_of_says_when_there_are_no_us_gaap_facts():
    r = M.fundamentals_of(json.dumps({"taxonomies": ["ifrs-full"], "facts": {}}))
    assert r["available"] is False and "no US GAAP" in r["why"]


# ------------------------------------------------------------------ endpoints on fixtures
def test_setup(mocked):
    p = M.ENDPOINTS["setup"]()
    assert len(p["cards"]) == 13 and {c["sym"] for c in p["cards"]} == set(M.BASKET)
    c = p["cards"][0]
    assert c["dd52"] <= 0 and c["vs50"] is not None and 0 <= c["rsi"] <= 100
    assert set(p["lines"]) == {"AI basket", "Owner's picks", "QQQ", "SPY"} and p["lines"]["AI basket"][0][1] == 100
    assert p["now"]["dd"] < -0.1 and p["vix_source"] == "FRED" and "below its high" in p["where"]
    assert "buy" not in p["where"].lower() and "sell" not in p["where"].lower()
    assert [c["sym"] for c in p["pick_cards"]] == list(M.PICKS) and "Owner's picks" in p["lines"]
    assert p["picks_now"]["since"]["SNDK"] == "2025-03-03" and p["picks_now"]["since"]["NBIS"] == "2024-11-01"
    assert p["picks_dd"][-1][1] <= 0 and p["picks_now"]["n"] == 10
    st = p["strip"]
    assert [x["sym"] for x in st[:3]] == ["SPY", "QQQ", "SMH"] and {x["sym"] for x in st} == set(M.STOCKS) | {"SPY", "QQQ", "SMH"}
    assert all("form4" in x and f"CIK={M.CIKS[x['sym']]:010d}" in x["form4"] for x in st if x["group"] != "index")
    assert next(x for x in st if x["sym"] == "NVDA")["both"] and abs(st[0]["day"]) < 0.2
    S = p["score_now"]
    assert 0 <= S["v"] <= 100 and S["band"] == M.band_of(S["v"]) and set(S["parts"]) == set(M.SCORE_PARTS) and "not a forecast" in S["sentence"]
    assert p["score"][-1][1] == S["v"] and len(p["band_stats"]) == 6 and sum(r["days"] for r in p["band_stats"]) == len(p["score"])
    assert isinstance(S["changes90"], int) and S["vix_only_changes90"] is not None
    assert {"green", "red"} == set(p["score_episodes"]) and p["score_episodes"]["green"]          # the fixture's 2020 crash is a washout
    B.json_safe(p)


def test_vix_falls_back_to_cboe_and_marks_fred_handled(mocked, monkeypatch):
    def no_fred(url, ttl=0, **k):
        if "fredgraph" in url:
            B.HEALTH[url] = {"module": "ai_stocks", "ok": None, "fail": time_now(), "error": "Timeout"}
            raise TimeoutError("fred")
        return fake_fetch(url, ttl, **k)
    monkeypatch.setattr(M, "fetch", no_fred)
    s, src = M.vix()
    assert src == "Cboe" and len(s) > 100 and B.HEALTH[M.FRED_VIX].get("handled_how")


def time_now():
    import time
    return time.time()


def test_drawdown_tab(mocked):
    p = M.ENDPOINTS["drawdown"]()
    assert len(p["stocks"]) == 13 and p["basket"][-1][1] < 0
    eps = p["episodes"]
    assert all(e["depth"] <= -0.10 for e in eps) and sum(e["ongoing"] for e in eps) == 1
    assert p["current"]["episode"]["ongoing"] and p["current"]["peak"] >= "2026-09-01"
    closed = [e for e in eps if not e["ongoing"]]
    assert len(closed) >= 3 and all(e["days_to_recover"] is not None for e in closed)
    assert set(p["pick_stocks"]) == set(M.PICKS) and p["picks_basket"][-1][1] <= 0 and p["picks_current"]["dd"] <= 0
    assert p["pick_since"]["NBIS"] == "2024-10-21" and p["pick_since"]["RKLB"] == "2021-08-25"      # own history: from the listing
    assert p["pick_since"]["NVDA"] == "2020-01-01"
    B.json_safe(p)


def test_trend_tab(mocked):
    p = M.ENDPOINTS["trend"]()
    assert all(0 <= v <= 1 for _, v in p["breadth50"]) and p["now"]["state"] in ("golden", "death")
    assert p["crosses"] and {x["kind"] for x in p["crosses"]} <= {"golden", "death"}
    assert p["crosses"] == sorted(p["crosses"], key=lambda x: x["date"], reverse=True)
    B.json_safe(p)


def test_dips_tab(mocked):
    p = M.ENDPOINTS["dips"]()
    assert p["n"] >= 3 and p["threshold"] == -0.15
    for r in p["rows"]:
        assert r["depth"] <= -0.15 and r["cross15"] <= r["trough"] and r["further"] <= 0
    cur = [r for r in p["rows"] if r["ongoing"]]
    assert cur and cur[0]["cross"]["6m"] is None                              # the future is not known yet
    s = p["cross"]["3m"]
    assert s["n"] == p["n"] and s["min"] <= s["median"] <= s["max"]
    B.json_safe(p)


def test_fear_tab(mocked):
    p = M.ENDPOINTS["fear"]()
    assert p["vix"] and p["ai_qqq"][0][1] == 100 and p["smh_spy"][0][1] == 100
    r = p["relative"]["AI basket vs QQQ"]
    assert set(r) == {"3m", "12m"} and r["3m"]["gap"] == pytest.approx(100 * (r["3m"]["a"] - r["3m"]["b"]), abs=0.06)
    assert p["vix_now"]["max_1m"] >= p["vix_now"]["v"]
    B.json_safe(p)


def test_fundamentals_tab(mocked):
    p = M.ENDPOINTS["fundamentals"]()
    assert set(p["revenue_yoy"]) == set(M.REV_CIKS) and p["basket_yoy"] and p["capex_ttm"] and p["capex_yoy"]
    assert set(p["left_out"]) == {"TSM", "ASML", "ARM"} and not p["errors"]
    B.json_safe(p)


def test_revenue_uses_its_own_cache_key_not_compute_chips_capex_copy(mocked):
    CC._capex()                                                             # caches Microsoft's companyfacts cut down to capex tags
    s = M.revenue(M.REV_CIKS["MSFT"])
    assert len(s) > 20 and s.iloc[-1] > 0


def test_readings_and_signals(mocked):
    assert M.SIGNALS() == [] and M.READINGS() == []                         # nothing cached: nothing downloaded
    M.fill_13f()
    M.fill_insiders()
    for k in ("setup", "drawdown", "trend", "dips", "fear", "fundamentals", "institutions", "insiders"):
        M.ENDPOINTS[k]()
    r = M.READINGS()
    assert {x["tab"] for x in r} == {t for t, _ in topics.REGISTRY["ai-stocks"].tabs} and all(x["lean"] in (-1, 0, 1) for x in r)
    sig = {x["key"]: x for x in M.SIGNALS()}
    wl = json.loads((B.MANUAL_DIR / "signals" / "watchlist.json").read_text())["ai-stocks"]
    assert set(sig) == {w["key"] for w in wl} and all(w.get("approved") and not w.get("proposed") for w in wl)
    assert all(isinstance(x["crossed"], bool) and x["lean"] in (-1, 0, 1) for x in sig.values())
    dd = sig["basket_drawdown"]["value"]
    assert not sig["basket_drawdown"]["crossed"] or dd < -20 or dd >= -5
    assert sig["setup_score"]["crossed"] == (sig["setup_score"]["value"] < 10 or sig["setup_score"]["value"] >= 90) and "rsi_basket" not in sig
    assert sig["ai_vs_qqq"]["crossed"] == (abs(sig["ai_vs_qqq"]["value"]) >= 10)


def test_signal_tests_at_the_edges(monkeypatch):
    day = 86400
    pts = lambda vals: [[1_700_000_000 + i * day, v] for i, v in enumerate(vals)]
    pay = {"setup": {"dd": pts([-0.12] * 30 + [-0.04]), "breadth50": pts([0.3] * 30 + [0.65]), "vix": pts([28] * 20 + [19]), "score": pts([30, 9.9])},
           "trend": {"now": {"rsi": 72}}, "fear": {"relative": {"AI basket vs QQQ": {"3m": {"a": 0.02, "b": 0.13, "gap": -11.0}}}}}
    monkeypatch.setattr(M, "_cached_payload", lambda n: pay.get(n, {}))
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert all(sig[k]["crossed"] for k in ("basket_drawdown", "breadth_50d", "setup_score", "vix", "ai_vs_qqq"))
    pay["setup"]["score"] = pts([95, 90.0])
    assert {x["key"]: x for x in M.SIGNALS()}["setup_score"]["crossed"]                                 # 90 counts as stretched
    pay["setup"] = {"dd": pts([-0.03] * 31), "breadth50": pts([0.7] * 31), "vix": pts([21] * 21), "score": pts([10.0, 89.9])}  # at a high all along
    pay["trend"] = {"now": {"rsi": 55}}
    sig = {x["key"]: x for x in M.SIGNALS()}
    assert not any(sig[k]["crossed"] for k in ("basket_drawdown", "breadth_50d", "setup_score", "vix"))


def test_every_endpoint_through_the_server(mocked):
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            for name in ("setup", "drawdown", "trend", "dips", "fear", "fundamentals", "institutions", "insiders", "companies", "meta"):
                r = await c.get(f"/api/ai-stocks/{name}")
                assert r.status == 200, name
            r = await c.get("/ai-stocks")
            assert r.status == 200
    asyncio.run(go())


@pytest.mark.network
def test_live_sources():
    assert len(M.nasdaq("NVDA")) > 1000 and len(M.nasdaq("SMH", "etf")) > 1000
    for s in M.PICKS:
        assert len(M.nasdaq(s)) > 100, s
    assert len(M.vix()[0]) > 1000


def test_combined_backtest_on_dips(mocked):
    """Core basket and core + picks as one index, both backtests rerun on each."""
    p = M.ENDPOINTS["dips"]()
    X = p["compare"]
    assert set(X["combined_members"]) == set(M.STOCKS) and len(X["combined_members"]) == 20
    for k in ("core", "combined"):
        g = X[k]
        assert g["dd"] and g["worst"] <= g["dd_now"] <= 0 and g["band_stats"] and "score_episodes" in g
        assert all(r["depth"] <= -0.15 for r in g["rows"]) and g["cross"]["3m"]["n"] == g["n"]
    assert X["core"]["n"] == p["n"] and X["core"]["cross"] == p["cross"]           # the core rerun matches the tab's own study
    assert X["combined"]["dd"] != X["core"]["dd"]
    assert "SNDK" in X["combined_since"] and "MSFT" not in X["combined_since"]
    B.json_safe(p)
