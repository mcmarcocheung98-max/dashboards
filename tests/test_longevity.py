"""Longevity & Biotech on fixtures (no network): the World Bank, WHO xMart, CDC, NHSBSA, EDGAR and Nasdaq parsers, every payload,
READINGS and the seed files. smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import longevity as M


# ------------------------------------------------------------------ fixtures
def wb_json():
    rows = []
    for iso, base in (("USA", 76.0), ("GBR", 78.0), ("HKG", 80.0), ("CHN", 70.0)):
        for y in range(1990, 2024):
            v = base + (y - 1990) * 0.12 - (1.5 if y in (2020, 2021) and iso == "USA" else 0)
            rows.append({"indicator": {"id": "SP.DYN.LE00.IN"}, "country": {"id": iso[:2]}, "countryiso3code": iso, "date": str(y), "value": v})
    rows.append({"countryiso3code": "USA", "date": "2024", "value": None})
    return [{"page": 1, "pages": 1, "per_page": 20000, "total": len(rows)}, rows]


def xmart_json(code: str, m49: str):
    """WHO xMart RELAY_WHS rows: the value in AMOUNT_N (years) or RATE_PER_100_N (%), three sexes; nothing for Hong Kong (344)."""
    if m49 == "344":
        return {"@odata.context": "x", "value": []}
    base = {"WHOSIS_000001": 77.0, "WHOSIS_000002": 66.0, "NCDMORT3070": 16.0}[code]
    step = {"WHOSIS_000001": 0.15, "WHOSIS_000002": 0.1, "NCDMORT3070": -0.2}[code]
    d = {"840": 0.0, "826": 1.0, "156": -2.0}[m49]
    col = "RATE_PER_100_N" if code == "NCDMORT3070" else "AMOUNT_N"
    rows = []
    for y in range(2000, 2022):
        for sex in ("TOTAL", "MALE", "FEMALE"):
            rows.append({"IND_CODE": code, "DIM_TIME": str(y), "DIM_TIME_TYPE": "YEAR", "DIM_GEO_CODE_M49": m49, "DIM_SEX": sex, "TEXT_N": None, "AMOUNT_N": None,
                         "RATE_PER_100_N": None, col: base + d + (y - 2000) * step + (0 if sex == "TOTAL" else 3)})
    return {"@odata.context": "x", "value": rows}


def cdc_json():
    rows = []
    rates = {"Heart disease": 170.0, "Cancer": 145.0, "Alzheimer disease": 30.0, "Drug overdose": 25.0, "All causes": 730.0, "Suicide": 14.0}
    for y in range(2019, 2026):
        for q in range(1, 5):
            i = (y - 2019) * 4 + q
            for cause, r in rates.items():
                for period in ("12 months ending with quarter", "3-month period"):
                    for rt in ("Age-adjusted", "Crude"):
                        v = r * (1 - 0.004 * i) if cause != "Drug overdose" else r + (8 if 2021 <= y <= 2023 else -4 if y >= 2024 else 0)
                        rows.append({"year_and_quarter": f"{y} Q{q}", "time_period": period, "cause_of_death": cause, "rate_type": rt,
                                     "unit": "Deaths per 100,000", "rate_overall": f"{v + (0 if rt == 'Age-adjusted' else 20):.1f}"})
    return rows


PCA_MONTHS = [f"PCA_{t:%Y%m}" for t in pd.date_range("2021-01-01", "2026-08-01", freq="MS")]


def pca_package():
    return {"success": True, "result": {"name": "prescription-cost-analysis-pca-monthly-data",
                                        "resources": [{"name": n} for n in PCA_MONTHS] + [{"name": "PCA metadata"}]}}


def pca_sql(table: str):
    i = PCA_MONTHS.index(table)
    recs = []
    for d, k in (("Semaglutide", 3.0), ("Tirzepatide", 0.5), ("Liraglutide", 1.0), ("Dulaglutide", 1.5)):
        if d == "Tirzepatide" and i < 36:
            continue
        recs.append({"CHEM": d, "items": str(int(k * 10000 * (1 + i / 30))), "nic": k * 1e6 * (1 + i / 25)})
    return {"help": "x", "success": True, "result": {"help": "y", "success": "true", "result": {"records": recs, "fields": []}}}     # as NHSBSA nests it


def concept_json(firm):
    unit = "USD" if firm == "lilly" else "DKK"
    facts = []
    for y in range(2018, 2026):
        base = (25e9 if unit == "USD" else 120e9) * (1.12 ** (y - 2018))
        facts.append({"start": f"{y}-01-01", "end": f"{y}-12-31", "val": base, "fy": y, "fp": "FY", "form": "10-K" if unit == "USD" else "20-F", "filed": f"{y + 1}-02-15"})
        if unit == "USD":
            for q in range(3):
                facts.append({"start": str(pd.Timestamp(f"{y}-01-01") + pd.DateOffset(months=3 * q))[:10],
                              "end": str((pd.Timestamp(f"{y}-01-01") + pd.DateOffset(months=3 * q + 3)) - pd.Timedelta(days=1))[:10],
                              "val": base / 4 * (0.9 + 0.05 * q), "form": "10-Q", "filed": f"{y}-{3 * q + 4:02d}-30"})
    return {"cik": 1, "taxonomy": "x", "tag": "Revenues", "units": {unit: facts}}


def nasdaq_json(sym):
    days = pd.bdate_range("2016-01-04", "2026-10-23")
    g = {"XBI": 0.00015, "IBB": 0.0001, "SPY": 0.0004, "LLY": 0.0009, "NVO": 0.0005}[sym]
    rows = [{"date": t.strftime("%m/%d/%Y"), "close": f"${60 * (1 + g) ** i * (1 + 0.1 * ((i // 300) % 2)):,.2f}", "volume": "1,000"} for i, t in enumerate(days)]
    return {"data": {"symbol": sym, "tradesTable": {"rows": list(reversed(rows))}}, "status": {"rCode": 200}}


def fake_fetch_json(url, ttl=0, **k):
    if "worldbank" in url:
        return wb_json()
    if "xmart" in url:
        from urllib.parse import unquote
        f = unquote(url)
        return xmart_json(f.split("IND_CODE eq '")[1].split("'")[0], f.split("M49 eq '")[1].split("'")[0])
    if "data.cdc.gov" in url:
        return cdc_json()
    if "package_show" in url:
        return pca_package()
    if "datastore_search_sql" in url:
        from urllib.parse import unquote
        t = unquote(url).split("FROM `")[1].split("`")[0]
        assert "resource_id=" + t in url
        if t == "PCA_202203":
            raise ConnectionError("one month down")
        return pca_sql(t)
    if "data.sec.gov" in url:
        if "RevenueFromContract" in url:
            raise ConnectionError("404")
        return concept_json("lilly" if "CIK0000059478" in url else "novo")
    if "nasdaq" in url:
        return nasdaq_json(url.split("/quote/")[1].split("/")[0])
    raise ConnectionError(url)


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above."""
    M.fetch_json = fake_fetch_json


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ tests
def test_topic_is_registered():
    from app import topics
    t = topics.REGISTRY["longevity"]
    assert t.module == "longevity" and [k for k, _ in t.tabs] == ["lifespan", "causes", "glp1", "approvals", "markets"]
    assert topics.meta("longevity")["sources"]


def test_parsers():
    le = M.parse_wb(wb_json())
    assert set(le) == {"US", "UK", "Hong Kong", "China"} and le["US"].index[-1] == pd.Timestamp("2023-07-01")
    h = M.parse_xmart(xmart_json("WHOSIS_000002", "826"))
    assert len(h) == 22 and h.iloc[0] == pytest.approx(67.0)          # both sexes only
    assert M.parse_xmart(xmart_json("NCDMORT3070", "840")).iloc[-1] == pytest.approx(16 - 21 * 0.2)
    assert M.parse_xmart({"value": []}).empty
    assert M.pca_months(pca_package())[0] == "PCA_202101" and "PCA metadata" not in M.pca_months(pca_package())
    assert M.parse_pca(pca_sql("PCA_202608"))["tirzepatide"][0] > 0
    assert M.parse_pca({"success": True, "result": {"records": [{"chem": "Semaglutide", "items": 5, "nic": 1.0}]}}) == {"semaglutide": (5.0, 1.0)}
    with pytest.raises(ValueError):
        M.parse_pca({"success": False, "error": {"message": "bad sql"}})
    c = M.parse_cdc(cdc_json())
    assert set(c) == {"heart", "cancer", "alzheimer", "overdose", "all"}
    assert c["heart"].index[-1] == pd.Timestamp("2025-12-31") and c["heart"].iloc[0] == pytest.approx(170 * 0.996, abs=0.06)
    with pytest.raises(ValueError):
        M.parse_cdc([{"foo": 1}])
    assert M._quarter_end("Q3 2024") == pd.Timestamp("2024-09-30")
    a, q = M.parse_concept(concept_json("lilly"), "USD")
    assert len(a) == 8 and len(q) == 32
    assert q[pd.Timestamp("2025-12-31")] == pytest.approx(a.iloc[-1] - sum(a.iloc[-1] / 4 * (0.9 + 0.05 * i) for i in range(3)))
    a2, q2 = M.parse_concept(concept_json("novo"), "DKK")
    assert len(a2) == 8 and q2.empty


def test_payloads(mocked):
    for name, fn in M.ENDPOINTS.items():
        if name == "layout":
            continue
        out = B.json_safe(fn())
        assert not [k for k in out if k.endswith("_error")], (name, {k: v for k, v in out.items() if k.endswith("_error")})
    L = M.ENDPOINTS["lifespan"]()
    assert set(L["hale"]["hale"]) == {"US", "UK", "China"}                          # WHO has no Hong Kong
    assert L["kpi"]["Hong Kong"]["value"] == pytest.approx(80 + 33 * 0.12) and L["kpi"]["US"]["vs_2019"] > 0
    assert L["hale"]["gap"]["US"][-1][1] == pytest.approx(11 + 21 * 0.05)
    G = M.ENDPOINTS["glp1"]()
    assert set(G["nhs"]["items"]) == {"Semaglutide", "Tirzepatide", "Liraglutide", "Dulaglutide"} and G["nhs"]["kpi"]["yoy_12m"] > 0
    assert G["nhs"]["missing"] == {"PCA_202203": "ConnectionError"} and G["nhs"]["kpi"]["month"] == "2026-08-01"
    assert G["revenue"]["Eli Lilly"]["annual"][-1][0] == 2025 and G["revenue"]["Novo Nordisk"]["unit"] == "DKK"
    A = M.ENDPOINTS["approvals"]()
    assert A["kpi"]["record"] == 59 and A["cgt_by_year"]["years"][0] == 2017 and sum(A["cgt_by_year"]["counts"]["FDA"]) >= 25
    K = M.ENDPOINTS["markets"]()
    assert set(K["rebased"]) == set(M.TICKERS) and K["stats"]["XBI"]["r1y"] is not None


def test_readings(mocked):
    assert M.READINGS() == []                              # nothing cached yet: nothing to report, nothing fetched
    for name in ("lifespan", "causes", "glp1", "approvals", "markets"):
        M.ENDPOINTS[name]()
    rs = M.READINGS()
    tabs = {r["tab"] for r in rs}
    assert tabs == {"lifespan", "causes", "glp1", "approvals", "markets"}
    assert all(r["lean"] in (-1, 0, 1) for r in rs) and len({r["key"] for r in rs}) == len(rs)
    lean = {r["key"]: r["lean"] for r in rs}
    assert lean["le_US"] == 1 and lean["us_heart"] == 1 and lean["us_overdose"] == 0
    assert lean["ncd_US"] == 1 and lean["nhs_items"] == 1 and lean["rev_eli"] == 1
    assert lean["up_US adult obesity rate (Gallup self-report %)"] == 1           # obesity fell: +1
    assert lean["xbi_vs_spy"] == -1
    B.json_safe(rs)


def test_one_dead_source_blanks_one_chart(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch_json", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")) if "xmart" in url else fake_fetch_json(url))
    L = M.ENDPOINTS["lifespan"]()
    assert L["hale"] is None and L["hale_error"] == "ConnectionError" and L["le"]["US"]


def test_cdc_falls_back_to_every_column(mocked, monkeypatch):
    def f(url, ttl=0, **k):
        if "$select" in url:
            raise ValueError("400: no such column")
        return fake_fetch_json(url)
    monkeypatch.setattr(M, "fetch_json", f)
    assert "heart" in M.cdc()


def test_seed_files():
    for name in ("life_expectancy", "healthy", "causes_uk", "products", "uptake", "fda_novel"):
        rs = B.manual_rows("longevity", name)
        assert rs, name
        for r in rs:
            pd.Timestamp(r["date"])
            float(r["value"])
            assert r["source"].startswith("http"), (name, r)
            assert "verify" in r["note"] or "placeholder" in r["note"], (name, r)     # nothing here was checked against the page yet
    for name in ("cgt", "milestones", "causes_hk"):
        for r in B.manual_rows("longevity", name):
            pd.Timestamp(r["date"])
            assert r["source"].startswith("http"), (name, r)


@pytest.mark.network
def test_live_sources():
    import json
    assert len(M.parse_wb(json.loads(B._download(M.WB_LE)))) == 4
    assert len(M.parse_xmart(json.loads(B._download(M.xmart_url(M.WHO_HALE, "826"))))) > 10
    assert "heart" in M.parse_cdc(json.loads(B._download(M.CDC_Q_SLIM)))
    months = M.pca_months(json.loads(B._download(M.PCA_PKG)))
    assert "semaglutide" in M.parse_pca(json.loads(B._download(M.pca_url(months[-1]))))
