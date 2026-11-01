"""Routes, registry, the fetch-with-snapshot fallback, hand-entered series, and every dashboard's payloads on fixtures (no network)."""
import json
import time

import numpy as np
import pandas as pd
import pytest

from app import topics
from app.topics import _base as B


@pytest.fixture
def snapdir(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    B.STALE.clear()
    from app import cache
    cache._cache.clear()
    yield tmp_path / "snaps"
    cache._cache.clear()
    B.STALE.clear()


def test_registry_discovers_modules(monkeypatch):
    import sys, types
    mod = types.ModuleType("app.topics.zz_example")
    mod.TOPIC = topics.Topic("zz-example", "Example", "x", "zz_example", (("a", "A"),), order=5)
    mod.DASHBOARD = None
    monkeypatch.setitem(sys.modules, "app.topics.zz_example", mod)
    monkeypatch.setattr(topics.pkgutil, "iter_modules", lambda path: [types.SimpleNamespace(name="zz_example"), types.SimpleNamespace(name="housing")])
    found = topics._discover()
    assert [t.slug for t in found] == ["zz-example"]


def test_registry_is_complete():
    assert {"housing", "ai", "robotaxi", "btc-cycles"} <= set(topics.REGISTRY)
    for slug, t in topics.REGISTRY.items():
        m = topics.meta(slug)
        eps = topics.endpoints(slug)
        assert m["title"] and m["tabs"] and m["sources"]
        assert set(t.slow) <= set(eps), slug
        assert {k for k, _ in t.tabs} <= set(eps), f"{slug}: every tab needs an endpoint of the same name"
        js = (B.MANUAL_DIR.parent / "app/static/topics" / topics.script(slug)).read_text()
        assert "window.TOPIC" in js and all(f"async {k}(" in js for k, _ in t.tabs), slug


def test_fetch_serves_the_snapshot_when_the_source_is_down(snapdir, monkeypatch):
    calls = []

    def dl(url, *a, **k):
        calls.append(url)
        if len(calls) > 1:
            raise ConnectionError("down")
        return "date,value\n2024-01-01,1\n2024-02-01,2\n" * 5
    monkeypatch.setattr(B, "_download", dl)
    url = "https://example.test/x.csv"
    t1 = B.fetch(url, ttl=0)                      # downloaded and snapshotted
    assert snapdir.exists() and not B.STALE
    t2 = B.fetch(url, ttl=0)                      # source down: snapshot, marked stale
    assert t2 == t1 and url in B.STALE
    assert B.stale_info([url]) == {url: time.strftime("%Y-%m-%d")}
    assert B.fetch(url, ttl=3600) == t1           # in memory now
    with pytest.raises(ConnectionError):
        B.fetch("https://example.test/never.csv", ttl=0)   # no snapshot either: the error reaches _part
    out = {}
    B._part(out, "k", lambda: B.fetch("https://example.test/never.csv", ttl=0))
    assert out == {"k": None, "k_error": "ConnectionError"}


def test_manual_series_and_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "MANUAL_DIR", tmp_path)
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "one.csv").write_text("date,value,source,note\n# a comment line, with commas, is skipped\n2024-02-01,2,https://a.example/x,\n2024-01-01,1.5,https://b.example/y,n\n")
    (tmp_path / "t" / "many.csv").write_text("date,series,value,source,note\n2024-01-01,A,1,s,\n2024-01-01,B,,s,blank value dropped\n2024-02-01,A,3,s,\n")
    s = B.manual("t", "one")
    assert list(s) == [1.5, 2.0] and s.index[0] == pd.Timestamp("2024-01-01")
    m = B.manual("t", "many")
    assert set(m) == {"A", "B"} and list(m["A"]) == [1.0, 3.0] and m["B"].empty
    assert B.manual_sources("t", "one")[0] == {"source": "https://a.example/x", "date": "2024-02-01"}
    assert B.manual("t", "missing").empty and B.manual_rows("t", "missing") == []


def test_seed_files_parse_and_cite():
    for slug in topics.REGISTRY:
        for f in (B.MANUAL_DIR / slug).glob("*.csv"):
            rows = B.manual_rows(slug, f.stem)
            for r in rows:
                pd.Timestamp(r["date"])
                assert r.get("source"), f"{f}: every hand-entered row cites a source"


# ------------------------------------------------------------------ each module on fixtures (no network)
def _full_file():
    """UK HPI full-file layout: one row per region per month (dd/mm/yyyy dates), for London, the UK and every borough."""
    from app.topics.housing import REGIONS
    head = "Date,RegionName,AreaCode,AveragePrice,Index,IndexSA,1m%Change,12m%Change,AveragePriceSA,SalesVolume,DetachedPrice,SemiDetachedPrice,TerracedPrice,FlatPrice"
    rows = [head]
    for k, r in enumerate(REGIONS + ["Wales", "Leeds"]):
        for i in range(180):
            rows.append(f"01/{i % 12 + 1:02d}/{2010 + i // 12},{r},E{k:08d},{300000 + i * 1000 + k * 5000},{100 + i},,,2.0,,{8000 - i},600000,400000,350000,250000")
    return "\n".join(rows)


HPI = _full_file()
ONS = lambda v0: "\n".join(['"Title","fixture"', '"CDID","X"', '"Unit","Index"'] + [f'"{2010 + i // 12} {m}","{v0 + i}"' for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"] * 15)])


def _pmms_xlsx():
    import io
    rows = [["Freddie Mac PMMS", None, None], ["Week", "30-yr FRM", "15-yr FRM"]] + [[d, 3 + i * 0.01, 2.5] for i, d in enumerate(pd.date_range("2015-01-01", periods=500, freq="W"))]
    buf = io.BytesIO(); pd.DataFrame(rows).to_excel(buf, index=False, header=False)
    return buf.getvalue().decode("latin-1")


def _fhfa_csv():
    rows = ["hpi_type,hpi_flavor,frequency,level,place_name,place_id,yr,period,index_nsa,index_sa,rstderr,note"]
    for y in range(2010, 2027):
        for m in range(1, 13):
            rows.append(f"traditional,purchase-only,monthly,USA or Census Division,United States,USA,{y},{m},{200 + (y - 2010) * 10 + m},{201 + (y - 2010) * 10 + m},,")
        for q in range(1, 5):
            rows.append(f'traditional,all-transactions,quarterly,MSA,"New York-Jersey City-White Plains, NY-NJ (MSAD)",35614,{y},{q},{300 + (y - 2010) * 8 + q},,,')
            rows.append(f'traditional,all-transactions,quarterly,MSA,"San Francisco-San Mateo-Redwood City, CA (MSAD)",41884,{y},{q},{400 + (y - 2010) * 9 + q},,,')
    return "\n".join(rows)


def housing_fetch(url, ttl, **k):
    if "publicdata.landregistry" in url:
        return HPI
    if "generator" in url:
        return ONS(100) if "l522" in url else ONS(500)
    if "rvd.gov.hk" in url:
        return _rvd_xls()
    if "freddiemac" in url:
        return _pmms_xlsx()
    if "fhfa" in url:
        return _fhfa_csv()
    if "fred" in url:
        return FRED
    if "nomisweb" in url:
        return NOMIS
    if "priceindexofprivaterents" in url:
        return _pipr_xlsx() if "file?uri" in url else PIPR_PAGE
    return BOE
PIPR_PAGE = ('<a href="/file?uri=/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics/16september2026/a.xlsx">'
             '<a href="/file?uri=/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics/21october2026/priceindexofprivaterentsukmonthlypricestatistics.xlsx">') * 40


def _pipr_xlsx():
    """The live layout (Oct 2026): title, note, header row, then one row per area and month; [x] where there is no value."""
    import io
    import openpyxl
    wb = openpyxl.Workbook(); wb.active.title = "Cover sheet"; ws = wb.create_sheet("Table 1")
    ws.append(["Price Index of Private Rents, UK: monthly price statistics"]); ws.append(["This worksheet contains one table."])
    ws.append(["Time period", "Area code", "Area name", "Region or country name", "Index", "Monthly change", "Annual change", "Rental price", "Index one bed",
               "Monthly change one bed", "Annual change one bed", "Rental price one bed", "Index two bed", "Monthly change two bed", "Annual change two bed", "Rental price two bed"])
    areas = [("K02000001", "United Kingdom", "[z]", 900), ("E92000001", "England", "[z]", 950), ("E12000007", "London", "[z]", 1600), ("E09000033", "Westminster", "London", 2500),
             ("E09000007", "Camden", "London", 2300), ("E09000001", "City of London", "London", "[x]")]
    for i, t in enumerate(pd.date_range("2015-01-01", "2026-09-01", freq="MS")):
        for code, name, reg, base in areas:
            rent = base if base == "[x]" else base + i * 5
            two = base if base == "[x]" else base + 400 + i * 5
            ws.append([t.to_pydatetime(), code, name, reg, 100, "[x]" if i == 0 else 0.3, "[x]" if i < 12 else 5.0, rent, 100, 0.3, 5.0, 1, 100, 0.3, 5.0, two])
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue().decode("latin-1")


NOMIS = ('"DATE_NAME","GEOGRAPHY_NAME","SEX_NAME","ITEM_NAME","PAY_NAME","OBS_VALUE"\n"1998","London","Full Time Workers","Median","Annual pay - gross",\n'
         + "".join(f'"{y}","London","Full Time Workers","Median","Annual pay - gross",{30000 + (y - 2000) * 1000}\n' for y in range(1999, 2026)))
BOE = "DATE,IUDBEDR\n05 Mar 2009,0.5\n02 Nov 2017,0.75\n16 Dec 2021,0.25\n03 Aug 2023,5.25\n01 Aug 2024,5.0\n"


def test_housing_payloads(snapdir, monkeypatch):
    from app.topics import housing as H
    monkeypatch.setattr(H, "fetch", housing_fetch)
    monkeypatch.setattr(H, "full_file_url", lambda: "http://publicdata.landregistry.gov.uk/x.csv")
    p, m, a = H._prices_now(), H._market_now(), H._afford_now()
    for d in (p, m, a):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert p["now"]["avg"] == 479000 and p["london_real"][-1][1] == 479000 and p["london_real"][0][1] > 300000   # real terms: past prices inflated
    assert len(m["by_type"]) == 4 and m["now"]["types"]["Detached"] == 600000 and m["now"]["volume_12m"] < m["now"]["volume_12m_prev"]
    assert a["now"]["bank_rate"] == 5.0 and 5 < a["now"]["price_to_earnings"] < 20 and a["now"]["mortgage"] > 1000
    assert a["bank_rate"][0][1] == 0.5 and all(t % 86400 == 0 for t, _ in a["bank_rate"])     # one point per month start


def test_housing_parsers_cope_with_layout_drift():
    from app.topics.housing import parse_boe, parse_full_file, parse_ons_csv, parse_pmms
    d = parse_full_file("Date,RegionName,AveragePrice,SalesVolume\n01/01/2020,London,500000,100\n01/02/2020,London,510000,110\n01/02/2021,London,520000,90\n01/02/2021,Leeds,1,1\n", ["London"])
    assert list(d) == ["London"] and len(d["London"]) == 14 and d["London"]["avg_detached"].isna().all()       # gaps kept, missing columns blank
    assert parse_ons_csv('"Title","x"\n"2024 JAN","1.5"\n"2024 FEB","1.6"\n"2024 Q1","9"').tolist() == [1.5, 1.6]
    with pytest.raises(ValueError):
        parse_ons_csv("This API has been decommissioned")
    assert parse_boe(" DATE , IUDBEDR \n01 Feb 2024,5.25\n").iloc[0] == 5.25
    assert len(parse_pmms(_pmms_xlsx().encode("latin-1"))) == 500


IND = "date,jobcountry,indeed_job_postings_index,variable,display_name\n" + "\n".join(
    f"{d.date()},US,{100 + i * {'Legal': 1, 'Scientific Research & Development': 2}.get(n, -1) * 0.1:.2f},{v},{n}" for i, d in enumerate(pd.date_range("2020-02-01", periods=800))
    for n in ("Software Development", "Data & Analytics", "IT Systems & Solutions", "Scientific Research & Development", "Legal", "Banking & Finance", "Accounting", "Insurance")
    for v in ("total postings", "new postings"))
AGG = "date,jobcountry,indeed_job_postings_index_SA,indeed_job_postings_index_NSA,variable\n" + "\n".join(f"{d.date()},US,{100 + i * .01:.2f},100,total postings" for i, d in enumerate(pd.date_range("2020-02-01", periods=800)))
AIS = "date,jobcountry,AI_share_postings\n" + "\n".join(f"{d.date()},{cc},{2 + i * .003 * (2 if cc == 'US' else 1):.3f}" for i, d in enumerate(pd.date_range("2019-01-01", periods=2800)) for cc in ("US", "GB", "DE"))
FRED = "observation_date,CES6054110001\n" + "\n".join(f"{d.date()},{1100 + i * .5:.1f}" for i, d in enumerate(pd.date_range("2010-01-01", periods=190, freq="MS")))


def _bls(body):
    """BLS API v1 response for the ids and years in the request body."""
    import json as _j
    a, b = int(body["startyear"]), min(int(body["endyear"]), 2026)
    series = []
    for sid in body["seriesid"]:
        base = 30.0 if sid.endswith("03") else 1100.0
        data = [{"year": str(y), "period": f"M{m:02d}", "value": f"{base + (y - 2010) * (0.6 if base < 100 else 6) + m * 0.05:.2f}"}
                for y in range(a, b + 1) for m in range(1, 13) if not (y == 2026 and m > 9)]
        series.append({"seriesID": sid, "data": data[::-1]})
    return _j.dumps({"status": "REQUEST_SUCCEEDED", "Results": {"series": series}})


def _csd_215_16001() -> str:
    """C&SD table 215-16001 as its API returns it (Oct 2026): one record per industry, period and statistic."""
    recs = []
    for i, per in enumerate(f"{y}{m:02d}" for y in range(2018, 2027) for m in (3, 6, 9, 12)):
        if per > "202606":
            break
        for ind, desc, base in (("", "Total", 2_800_000), ("ind_K", "K: Financing and insurance", 230_000), ("ind_M", "M: Professional, scientific and technical services", 150_000),
                                ("ind_J", "J: Information and communications", 105_000)):
            recs.append({"IND": ind, "INDDesc": desc, "freq": "M", "period": per, "sv": "PE", "svDesc": "No.", "figure": base + i * 500, "sd_value": ""})
            recs.append({"IND": ind, "INDDesc": desc, "freq": "M", "period": per, "sv": "PE", "svDesc": "Year-on-year % change", "figure": 0.9, "sd_value": ""})
            recs.append({"IND": ind, "INDDesc": desc, "freq": "M", "period": per, "sv": "VACR", "svDesc": "(%)", "figure": "", "sd_value": "[-\u00a732]"})
    return json.dumps({"header": {"status": {"name": "Success", "code": 0}}, "dataSet": recs})


def _bres_csv() -> str:
    """Nomis BRES open access CSV as served (Oct 2026): one row per year, borough and industry; a blank OBS_VALUE where suppressed."""
    from app.topics.ai_jobs import LONDON_SECTORS
    rows = ['"DATE_NAME","GEOGRAPHY_NAME","GEOGRAPHY_CODE","INDUSTRY","OBS_VALUE"']
    for y in range(2015, 2025):
        for i, (b, code) in enumerate((("City of London", "E09000001"), ("Westminster", "E09000033"), ("Camden", "E09000007"), ("Bexley", "E09000004"))):
            for k, name in LONDON_SECTORS.items():
                v = "" if (b == "Bexley" and name == "Insurance") else (100000 if name == "All jobs" else 5000) * (4 - i) + (y - 2015) * (300 if name == "Software & IT" else -50)
                rows.append(f'"{y}","{b}","{code}",{k},{v}')
    return "\n".join(rows) + "\n"


JOBS03_PAGE = ('<a href="/file?uri=%2Femploymentandlabourmarket%2Fpeopleinwork%2Femploymentandemployeetypes%2Fdatasets%2Femployeejobsbyindustryjobs03'
               '%2Fcurrent%2Fjobs03sep2026.xls">jobs03sep2026.xls (1.4 MB)</a> <a href="/file?uri=/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/'
               'datasets/employeejobsbyindustryjobs03/previous/v1/jobs03jun2026.xls">old</a>')


def _jobs03_xlsx(in_jobs=False) -> bytes:
    """A JOBS03-like workbook (layout assumed, not seen live: ONS is unreachable from the build container): a contents sheet, a
    sheet by sex, then the all-employees sheet with title lines, a section-letter row, a SIC division code row and one row per quarter."""
    import io
    divs = [f"{i:02d}" for i in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 62, 63, 64, 65, 66, 68, 69, 70)]
    def sheet(scale):
        rows = [["JOBS03: Employee jobs by industry"] + [""] * len(divs), ["United Kingdom, not seasonally adjusted, thousands"] + [""] * len(divs),
                ["", "Section"] + ["K" if c == "64" else "M" if c == "69" else "" for c in divs],
                ["", "SIC 2007 division"] + [int(c) if c in ("64", "69") else c for c in divs]]     # codes as numbers or text
        for i, q in enumerate(pd.date_range("2016-03-01", "2026-06-01", freq="3MS")):
            base = {"64": 500, "65": 100, "66": 450, "69": 560}
            vals = [(base.get(c, 50) + i * (2 if c == "69" else 1)) * scale * (1000 if in_jobs else 1) for c in divs]
            rows.append(["", q.strftime("%b %Y") + (" (p)" if i == 41 else "")] + vals)
        rows.append(["Source: Office for National Statistics"] + [""] * len(divs))
        return pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([["Contents"], ["1 Male"], ["2 Total"]]).to_excel(w, sheet_name="Contents", index=False, header=False)
        sheet(0.5).to_excel(w, sheet_name="1. Male", index=False, header=False)
        sheet(1).to_excel(w, sheet_name="2. Total", index=False, header=False)
    return buf.getvalue()


def jobs_fetch(url, ttl, **k):
    if url.endswith("employeejobsbyindustryjobs03"):
        return JOBS03_PAGE
    if "jobs03sep2026" in url:
        return _jobs03_xlsx().decode("latin-1")
    if "nomisweb" in url:
        return _bres_csv()
    if "censtatd" in url:
        return _csd_215_16001()
    if "api.bls.gov" in url:
        return _bls(k["post"])
    return AIS if "ai-tracker" in url else AGG if "aggregate" in url else IND


def test_ai_jobs_payloads(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    monkeypatch.setattr(J, "fetch", jobs_fetch)
    o, h, r = J._openings_now(), J._headcount_now(), J._ratio_now()
    for d in (o, h, r):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert set(o["US"]["sectors"]) == set(J.SECTORS["ai"] + J.SECTORS["ai_wide"] + J.SECTORS["professions"]) and o["US"]["latest"]["Legal"]["index"] > 100 > o["US"]["latest"]["Software Development"]["index"]
    assert o["ai_share_latest"]["US"]["share"] > o["ai_share_latest"]["US"]["year_ago"]
    assert set(h["US"]["levels"]) == set(J.US_SERIES) and h["US"]["latest"]["Legal services"]["since_2020"] > 0 and h["as_of"]
    assert r["US"]["ai_over_professions"][-1][1] < 1 < r["US"]["ai_over_professions"][0][1] + 0.01
    assert len(json.dumps(o)) < 400_000                      # weekly / monthly resampling keeps the page light
    assert h["UK"]["workbook"] == "jobs03sep2026.xls" and set(h["UK"]["levels"]) == set(J.UK_INDUSTRIES)


def test_ai_jobs_uk_headcount_from_jobs03(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    pytest.importorskip("openpyxl")
    assert J.jobs03_url(JOBS03_PAGE).endswith("%2Fcurrent%2Fjobs03sep2026.xls")
    for in_jobs in (False, True):                            # thousands, or plain jobs (divided by 1,000)
        s = J.parse_jobs03(_jobs03_xlsx(in_jobs))
        assert set(s) == {"Financial & insurance", "Legal & accounting"}
        f, l = s["Financial & insurance"], s["Legal & accounting"]
        assert f.index[0] == pd.Timestamp("2016-03-01") and f.index[-1] == pd.Timestamp("2026-06-01") and len(f) == 42
        assert f.iloc[0] == 1050 and f.iloc[-1] == 1050 + 3 * 41 and l.iloc[-1] == 560 + 2 * 41    # the "Total" sheet, K = 64+65+66
    monkeypatch.setattr(J, "fetch", jobs_fetch)
    hand = {"Legal & accounting": pd.Series({pd.Timestamp("2026-06-01"): 650.0})}          # a hand-entered quarter wins
    monkeypatch.setattr(J, "manual", lambda slug, name: hand if name == "uk_headcount" else pd.Series(dtype=float))
    u = J._headcount_now()["UK"]
    assert u["latest"]["Legal & accounting"]["level"] == 650 and u["latest"]["Financial & insurance"]["date"] == "2026-06-01"
    assert u["latest"]["Financial & insurance"]["yoy"] == round((1173 / 1161 - 1) * 100, 2) and u["workbook_error"] is None

    def blocked(url, ttl, **k):                              # ONS unreachable: hand-entered rows only, with the reason
        if "ons.gov.uk" in url:
            raise ConnectionError("blocked")
        return jobs_fetch(url, ttl, **k)
    monkeypatch.setattr(J, "fetch", blocked)
    from app import cache
    cache._cache.clear()
    u = J._headcount_now()["UK"]
    assert list(u["levels"]) == ["Legal & accounting"] and u["workbook"] is None and "blocked" in u["workbook_error"]
    monkeypatch.setattr(J, "manual", lambda slug, name: pd.Series(dtype=float))
    h = J._headcount_now()
    assert h["UK"] is None and h["UK_error"] == "ValueError" and h["US"]          # the card says not available


def test_ai_adoption_payloads(snapdir, monkeypatch):
    from app.topics import ai_adoption as A, ai_jobs as J
    pytest.importorskip("openpyxl")
    def fake(url, ttl, **k):
        if url == A.BTOS_XLSX:
            return btos_national_xlsx().decode("latin-1")
        if url == A.BTOS_SECTOR_XLSX:
            return btos_sector_xlsx().decode("latin-1")
        if url == A.RAMP_PAGE:
            return ramp_page()
        raise ConnectionError("blocked")                                         # ONS unreachable: the UK card says so
    monkeypatch.setattr(A, "fetch", fake)
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS)
    f, u, g, s = A._firms_now(), A._users_now(), A._agents_now(), A._skills_now()
    for d in (f, u, g, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert f["now"]["btos"] == 24.6 and f["as_of"] == "2026-10-11" and f["now"]["btos_year_ago"] is None and f["btos_expect"][-1][1] == 28.6
    assert f["now"]["ramp"] == 55.86 and len(f["ramp"]) == 39
    assert set(f["btos_sectors"]) == {"Information", "Manufacturing", "Professional, Scientific, and Technical Services"}
    assert f["btos_sectors"]["Information"][-1][1] == 41.2 and A.BTOS_SECTOR_XLSX not in f["stale"]
    assert f["uk_hk"] == {} and not [r for r in B.manual_rows("ai", "btos_ai_use_us") if "verify" in r.get("note", "")]
    assert u["rows"][0]["date"] >= u["rows"][-1]["date"] and any(v for v in u["series"].values())
    assert g["rows"] and g["by_year"] and set(s["share"]) == {"US", "GB", "DE"}
    assert sum(g["kinds"].values()) == len(g["rows"]) == sum(g["by_year"].values())     # the page's kind filter covers every row
    assert list(g["kinds"].values()) == sorted(g["kinds"].values(), reverse=True)


def test_btos_workbook_parser():
    import io
    from app.topics.ai_adoption import parse_btos
    pytest.importorskip("openpyxl")
    frame = pd.DataFrame([["Question", "Answer", "2024-01-14", "2024-01-28", "2024-02-11"],
                          ["In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?", "Yes", "5.1", "5.3", "5.4"],
                          ["In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?", "No", "90", "90", "90"]])
    buf = io.BytesIO()
    frame.to_excel(buf, index=False, header=False)
    s = parse_btos(buf.getvalue())
    assert s.tolist() == [5.1, 5.3, 5.4] and s.index[-1] == pd.Timestamp("2024-02-11")


def btos_national_xlsx() -> bytes:
    """The live National workbook layout (Oct 2026): period codes as columns, '%' strings, '.' for no estimate, and a dates sheet."""
    import io
    q7 = "In the last two weeks, did this business use Super Intelligence or SI (formerly referred to as Artificial Intelligence or AI) in any of its business functions?"
    q24 = "During the next six months, do you think this business will be using Super Intelligence or SI (formerly referred to as Artificial Intelligence or AI) in any of its business functions?"
    est = pd.DataFrame([["Question ID", "Question", "Answer ID", "Answer", "202621", "202620", "202319"],
                        ["3", "Overall, how would you describe this business's current performance?", "1", "Excellent", "14.6%", "14.7%", "9.8%"],
                        ["7", q7, "1", "Yes", "24.6%", "23.8%", "3.7%"], ["7", q7, "2", "No", "65.8%", "66.4%", "90.0%"],
                        ["24", q24, "1", "Yes", "28.6%", "27.7%", "."]])
    dates = pd.DataFrame({"Sample Year": [2, None, 4], "Smpdt": ["202319", "202620", "202621"],
                          "Ref End": ["2023-09-10", "2026-09-27", "2026-10-11"]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        est.to_excel(w, sheet_name="Response Estimates", index=False, header=False)
        dates.to_excel(w, sheet_name="Collection and Reference Dates", index=False)
    return buf.getvalue()


def btos_sector_xlsx(with_dates: bool = False) -> bytes:
    """The Sector workbook in the National layout plus a Sector column of NAICS codes (with a total row), '.' for no estimate."""
    import io
    q7 = "In the last two weeks, did this business use Super Intelligence or SI (formerly referred to as Artificial Intelligence or AI) in any of its business functions?"
    est = pd.DataFrame([["Sector", "Question ID", "Question", "Answer ID", "Answer", "202621", "202620", "202319"],
                        ["XX", "7", q7, "1", "Yes", "24.6%", "23.8%", "3.7%"],
                        ["51", "7", q7, "1", "Yes", "41.2%", "40.5%", "13.8%"], ["51", "7", q7, "2", "No", "50.1%", "51.0%", "80.0%"],
                        ["31-33", "7", q7, "1", "Yes", "15.0%", "14.1%", "."],
                        ["54", "7", q7, "1", "Yes", "36.0%", "35.2%", "8.9%"], ["54", "3", "Overall performance?", "1", "Yes", "9%", "9%", "9%"]])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        est.to_excel(w, sheet_name="Response Estimates", index=False, header=False)
        if with_dates:
            pd.DataFrame({"Smpdt": ["202319", "202620", "202621"], "Ref End": ["2023-09-10", "2026-09-27", "2026-10-11"]}).to_excel(
                w, sheet_name="Collection and Reference Dates", index=False)
    return buf.getvalue()


def test_btos_sector_parser():
    from app.topics.ai_adoption import _btos_ref_dates, parse_btos_sectors
    pytest.importorskip("openpyxl")
    import io
    ref = _btos_ref_dates(pd.ExcelFile(io.BytesIO(btos_national_xlsx())))
    s = parse_btos_sectors(btos_sector_xlsx(), ref)                             # dates borrowed from the National workbook
    assert set(s) == {"Information", "Manufacturing", "Professional, Scientific, and Technical Services"}   # the XX total is left out
    assert s["Information"].tolist() == [13.8, 40.5, 41.2] and s["Information"].index[-1] == pd.Timestamp("2026-10-11")
    assert s["Manufacturing"].tolist() == [14.1, 15.0]                           # '.' = no estimate
    assert parse_btos_sectors(btos_sector_xlsx(with_dates=True))["Information"].iloc[-1] == 41.2
    with pytest.raises(ValueError, match="reference dates"):
        parse_btos_sectors(btos_sector_xlsx())
    with pytest.raises(ValueError, match="Response Estimates"):
        parse_btos_sectors(bics_wave_xlsx(), ref)


def bics_wave_xlsx(with_ai: bool = True) -> bytes:
    """A BICS wave workbook as published (Oct 2026): title lines, then the table; fractions, [c] where suppressed."""
    import io
    head = ["Dates", "Wave", "Industry/Size Band", "Text generation using Large Language Models", "Other", "Not sure",
            "Business does not currently use artificial intelligence technologies"]
    rows = [["Question: Which of the following artificial intelligence technologies...", None, None, None, None, None, None],
            ["Back to Table of Contents", None, None, None, None, None, None], head]
    for dates, wave, no, unsure in (("21 September 2026 to 4 October 2026", "Wave 165", 0.641, 0.062), ("15 June 2026 to 28 June 2026", "Wave 159", 0.653, 0.058),
                                    ("18 September 2023 to 1 October 2023", "Wave 92", 0.837, 0.069)):
        rows += [[dates, wave, "Manufacturing", 0.1, "[c]", 0.037, 0.761], [dates, wave, "All businesses", 0.19, 0.022, unsure, no],
                 [dates, wave, "All size bands excluding 0 - 9", 0.2, "[c]", 0.111, 0.508 if wave == "Wave 165" else 0.6]]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        pd.DataFrame([["Read me"]]).to_excel(w, sheet_name="Read me", index=False, header=False)
        if with_ai:
            pd.DataFrame(rows).to_excel(w, sheet_name="AI Current Usage TS (WTD)", index=False, header=False)
    return buf.getvalue()


BICS_PAGE_HTML = "".join(f'<a href="/file?uri=/economy/x/businessinsightsandimpactontheukeconomy/bicswave{n}/bicswave{n}2final.xlsx">w</a>' for n in (164, 166, 165, 99)) + " " * 5000


def test_uk_firm_adoption_from_the_newest_bics_wave_with_ai_questions(snapdir, monkeypatch):
    pytest.importorskip("openpyxl")
    from app.topics import ai_adoption as A
    asked = []
    def fake(url, ttl, **k):
        asked.append(url)
        if url == A.BICS_PAGE:
            return BICS_PAGE_HTML
        return bics_wave_xlsx(with_ai="bicswave165" in url).decode("latin-1")
    monkeypatch.setattr(A, "fetch", fake)
    uk = A.firm_adoption_intl()
    assert [u.split("/")[-2] for u in asked[1:]] == ["bicswave166", "bicswave165"]          # newest first, stops at the first with the AI sheet
    s = uk["UK: all businesses (ONS BICS)"]
    assert s.index[-1] == pd.Timestamp("2026-10-04") and s.iloc[-1] == 29.7 and s.index[0] == pd.Timestamp("2023-10-01") and s.iloc[0] == 9.4
    assert uk["UK: 10+ employees (ONS BICS)"].iloc[-1] == 38.1
    f = A._firms_now()
    assert f["uk_hk"]["UK: all businesses (ONS BICS)"][-1][1] == 29.7 and f["uk_hk_latest"]["UK: all businesses (ONS BICS)"]["year_ago"] is None


def test_year_ago_needs_a_point_near_the_date():
    from app.topics.ai_adoption import _year_ago
    day = 86400
    live = [[1763251200, 17.3], [1791072000, 24.6]]                       # 16 Nov 2025 and 4 Oct 2026: 43 days off a year
    assert _year_ago(live, 21) is None and _year_ago(live) == 17.3
    assert _year_ago([[0, 5.0], [365 * day + 10 * day, 7.0]], 21) == 5.0 and _year_ago([]) is None


def test_btos_parser_reads_the_live_layout():
    from app.topics.ai_adoption import parse_btos
    pytest.importorskip("openpyxl")
    x = btos_national_xlsx()
    s = parse_btos(x)
    assert s.tolist() == [3.7, 23.8, 24.6] and s.index[0] == pd.Timestamp("2023-09-10") and s.index[-1] == pd.Timestamp("2026-10-11")
    e = parse_btos(x, "six months")
    assert e.tolist() == [27.7, 28.6]


SGO = "Report ID,Report Version,Reporting Entity,Incident Date,Incident Time (24:00)\n" + "\n".join(
    f"R{i},1,{'Waymo LLC' if i % 3 else 'Cruise LLC'},{m.strftime('%b-%Y').upper()},12:00" for i, m in enumerate(pd.date_range("2021-07-01", periods=40, freq="MS").repeat(3))) + "\nR0,2,Cruise LLC,JUL-2021,12:00\n"


def test_robotaxi_payloads(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)
    r, f, s = R._rides_now(), R._footprint_now(), R._safety_now()
    for d in (r, f, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert r["weekly"]["Waymo"] and r["latest"]["Waymo"]["value"] > 0 and r["quarterly"]
    assert f["operators"] and f["cumulative"]["Waymo"][-1][1] == f["by_operator"]["Waymo"] and f["rows"][0]["date"] >= f["rows"][-1]["date"]
    assert s["reports"]["n"] == 120 and set(s["reports"]["entities"]) == {"Waymo LLC", "Cruise LLC"}           # a second version of a report is not a second incident
    assert len(s["reports"]["months"]) == 40 and s["reports"]["total_12m"][-1][1] == 36


# ------------------------------------------------------------------ the routes
def test_routes(snapdir, monkeypatch):
    pytest.importorskip("aiohttp")
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            idx = await c.get("/")
            assert idx.status == 200 and "Dashboards" in await idx.text() and idx.headers["X-Frame-Options"] == "DENY"
            assert (await c.get("/healthz")).status == 200
            j = await (await c.get("/api/index")).json()
            assert sorted(d["slug"] for d in j["dashboards"]) == sorted(topics.public()) and j["categories"]
            page = await c.get("/housing")
            assert page.status == 200 and "window.TOPIC.VIEWS" in await page.text()
            js = await c.get("/housing.js")
            assert js.status == 200 and "window.TOPIC" in await js.text()
            assert (await c.get("/nope")).status == 404 and (await c.get("/nope.js")).status == 404
            assert (await c.get("/..%2Fserver.py")).status == 404
            meta = await (await c.get("/api/housing/meta")).json()
            assert meta["title"] == "Housing: London, US & Hong Kong" and meta["tabs"][0] == ["prices", "London"] and meta["sources"]
            assert (await c.get("/api/housing/nope")).status == 404 and (await c.get("/api/nope/meta")).status == 404
            red = await c.get("/ai-jobs", allow_redirects=False)
            assert red.status == 301 and red.headers["Location"] == "/ai#openings"
            assert (await c.get("/ai-adoption", allow_redirects=False)).headers["Location"] == "/ai#firms"
            assert (await c.get("/ai")).status == 200 and (await c.get("/ai.js")).status == 200
            r = await c.get("/api/robotaxi/safety")
            assert r.status == 200 and (await r.json())["reports"]["n"] == 120
    asyncio.run(go())


# ------------------------------------------------------------------ BTC cycles: the doc as data + the live layer on fixtures
def _cm():
    days = pd.date_range("2010-07-18", "2026-10-20")
    import math
    px = [10 ** (0.5 + 3.2 * (1 - math.exp(-i / 1500))) * (1 + 0.6 * math.sin(i / 230)) for i in range(len(days))]
    return {"data": [{"asset": "btc", "time": d.strftime("%Y-%m-%dT00:00:00.000000000Z"), "PriceUSD": f"{v:.2f}"} for d, v in zip(days, px)]}


def _llama(url):
    days = pd.date_range("2024-01-01", "2026-10-20")
    ts = [int(d.timestamp()) for d in days]
    if "historicalChainTvl" in url:
        return [{"date": t, "tvl": 1e11 + i * 1e7} for i, t in enumerate(ts)]
    if "stablecoincharts" in url:
        return [{"date": t, "totalCirculatingUSD": {"peggedUSD": 2e11 + i * 1e8}} for i, t in enumerate(ts)]
    if "summary/fees" in url:                    # revenue and fees share the fixture
        return {"totalDataChart": [[t, 1e6 + i * 1e3] for i, t in enumerate(ts)]}
    if "overview/dexs" in url:
        return {"totalDataChart": [[t, 1e10] for t in ts], "protocols": [{"name": "Hyperliquid", "total30d": 3e11}, {"name": "Aster", "total30d": 1e11}]}
    if "protocol/hyperliquid" in url:
        return {"tvl": [{"date": t, "totalLiquidityUSD": 4e9 + i * 1e6} for i, t in enumerate(ts)]}
    if "api/v3/global" in url:
        return {"data": {"market_cap_percentage": {"btc": 59.4}, "total_volume": {"usd": 9.1e10}}}
    if "market_chart" in url:
        return {"total_volumes": [[t * 1000, 1.2e10] for t in ts[-365:]]}
    raise AssertionError(url)


def test_btc_cycles_payloads(snapdir, monkeypatch):
    from app.topics import btc_cycles as _C
    monkeypatch.setattr(_C, "FUND_DIR", snapdir / "btc_fundamentals")          # per-coin fundamentals files stay in the test's folder
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: _cm() if "coinmetrics" in url else _llama(url))
    monkeypatch.setattr(C, "DOM_LOG", snapdir / "dom.csv")
    cy, se, me, ca, si = C._cycles_now(), C._sectors_now(), C._metrics_now(), C._candidates_now(), C._signals_now()
    for d in (cy, se, me, ca, si):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], [k for k in d if k.endswith("_error")]
    # the doc's content is all there
    R = C.research()
    assert R["title"].startswith("BTC Cycles") and len(R["cycles"]) == 4 and len(R["candidates"]["rows"]) == 8 and len(R["signals"]["items"]) == 6
    assert len(R["cross_cycle"]["rows"]) == 15 and len(R["metrics"]["rows"]) == 9 and len(R["sources"]["items"]) == 21
    assert all(set(r) >= set(c["columns"]) | {"_multiples"} for c in R["cycles"] for r in c["rows"])
    assert se["cycles"][1]["rows"][0]["_multiples"] == [{"label": "ETH", "x": 180.0}, {"label": "NEO", "x": 1900.0}]
    # live layer
    assert set(cy["overlay"]) == {"Cycle 1 (2012)", "Cycle 2 (2016)", "Cycle 3 (2020)", "Cycle 4 (2024)"}
    for pts in cy["overlay"].values():
        assert any(p[0] == 0 and abs(p[1] - 1) < 1e-6 for p in pts) and pts[0][0] >= -550 and pts[-1][0] <= 730
    assert all(p[1] <= 0 for p in cy["drawdown"]) and cy["now"]["days_since_halving"] == (pd.Timestamp("2026-10-20") - pd.Timestamp("2024-04-19")).days
    assert len(cy["halvings"]) == 4 and len(cy["markers"]) == 8
    assert me["latest"]["stablecoins"] > 2e11 and me["dex_top"][0]["name"] == "Hyperliquid" and abs(me["dex_top"][0]["share_30d"] - 0.75) < 1e-6
    assert ca["evidence"]["RWA on-chain value ex-stablecoins (USD)"][-1][1] == 38.6e9
    states = {s["signal"][:20]: s["state"] for s in si["status"]}
    assert states["Stablecoin supply up"] == "firing" and states["BTC spot volume sust"] == "firing" and states["New issuance primiti"] == "firing"
    assert states["BTC dominance rollin"] == "not yet" and (snapdir / "dom.csv").exists()
    assert len(C.dominance_log()) == 1 and C.coingecko_global()["dominance"] == 59.4 and len(C.dominance_log()) == 1   # one row per day


def test_btc_cycles_without_price_feed_still_serves_the_research(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(C, "DOM_LOG", snapdir / "dom.csv")
    cy, si = C._cycles_now(), C._signals_now()
    B.json_safe(cy); B.json_safe(si)
    assert cy["price_error"] == "ConnectionError" and cy["research"]["anatomy"]["rows"] and cy["now"] is None
    assert len(si["status"]) == 6 and all(s["state"] in ("firing", "not yet", "watch", "no data") for s in si["status"])


def test_btc_cycles_helpers():
    from app.topics.btc_cycles import halving_overlay, rising_weeks
    s = pd.Series(range(1, 200), index=pd.date_range("2026-01-01", periods=199))
    assert rising_weeks(s) >= 8
    s2 = pd.concat([s, pd.Series([1.0], index=[s.index[-1] + pd.Timedelta(days=1)])])
    assert rising_weeks(s2) == 0
    px = pd.Series(1.0, index=pd.date_range("2024-01-01", "2024-12-31"))
    ov = halving_overlay(px)
    assert list(ov) == ["Cycle 4 (2024)"] and all(p[1] == 1.0 for p in ov["Cycle 4 (2024)"])


def _chart(mult=1.0, start=60000.0, n=365, seed=1):
    import math
    rng = np.random.default_rng(seed)
    days = pd.date_range("2025-10-25", periods=n)
    btc = [start]
    for _ in range(n - 1):
        btc.append(btc[-1] * math.exp(rng.normal(0, 0.03)))
    px = [(b / btc[0]) ** mult * 10 for b in btc]
    ms = [int(d.timestamp() * 1000) for d in days]
    return {"btc": {"prices": [[t, v] for t, v in zip(ms, btc)], "market_caps": [[t, v * 2e7] for t, v in zip(ms, btc)], "total_volumes": [[t, 1e10] for t in ms]},
            "coin": {"prices": [[t, v] for t, v in zip(ms, px)], "market_caps": [[t, v * 1e8] for t, v in zip(ms, px)], "total_volumes": [[t, 1e8] for t in ms]}}


def test_btc_cycles_coins(snapdir, monkeypatch):
    from app.topics import btc_cycles as _C
    monkeypatch.setattr(_C, "FUND_DIR", snapdir / "btc_fundamentals")          # per-coin fundamentals files stay in the test's folder
    from app.topics import btc_cycles as C
    charts = _chart(mult=2.0)
    import json as _json
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    monkeypatch.setattr(C, "PACE", 0)
    assert C._coins_now()["coins"][0]["error"].startswith("loading")          # before the background fill: pending, not an error
    assert {v for k, v in C.fill_coins().items() if ":" not in k} == {"ok"}          # prices; ":fundamentals" entries are optional parts
    k = C._coins_now()
    B.json_safe(k)
    assert len(k["coins"]) == len(C.coins_list()) == 31 and all("kpi" in c for c in k["coins"]) and k["btc_now"] > 0
    hype = next(c for c in k["coins"] if c["ticker"] == "HYPE")
    assert hype["links"]["coinmarketcap"].endswith("/hyperliquid/") and hype["links"]["defillama"].endswith("/hyperliquid") and len(hype["spark"]) == 90
    assert abs(hype["kpi"]["beta"] - 2.0) < 0.05 and 0 <= hype["kpi"]["rsi"] <= 100 and 0 <= hype["kpi"]["rsi_vs_btc"] <= 100
    f = C._coin_now("HYPE")
    B.json_safe(f)
    assert len(f["projection"]) == 2 and all(p["bear"] < p["base"] < p["bull"] for p in f["projection"])
    sc = C.scenarios()["scenarios"][0]["base"]["btc"]
    assert abs(f["projection"][0]["base"] - f["kpi"]["price"] * (sc / k["btc_now"]) ** f["kpi"]["beta"]) < 1e-3 * f["kpi"]["price"]
    assert f["implied_mcap_base"][0]["mcap"] > 0 and set(f["series"]) == {"price", "btc_indexed", "ratio", "rsi", "rsi_vs_btc", "market_cap"}
    assert all(0 <= v <= 100 for _, v in f["series"]["rsi_vs_btc"] if v is not None)
    with pytest.raises(ValueError):
        C._coin_now("NOPE")
    # a coin whose fetch fails is listed with its error, the rest still come through
    from app import cache
    cache._cache.clear()
    import shutil
    shutil.rmtree(snapdir, ignore_errors=True)

    def flaky(url, *a, **kw):
        if "zcash" in url:
            raise RuntimeError("curl exit 0, HTTP 429: 'rate limited'")
        return _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"])
    monkeypatch.setattr(B, "_download", flaky)
    res = C.fill_coins(pause_on_limit=0)
    assert res["ZEC"].startswith("RuntimeError") and res["SOL"] == "ok"
    k2 = C._coins_now()
    zec = next(c for c in k2["coins"] if c["ticker"] == "ZEC")
    assert zec["error"].startswith("loading") and sum("kpi" in c for c in k2["coins"]) == 30


def test_btc_cycles_rsi_and_beta_edges():
    from app.topics.btc_cycles import beta_to_btc, rsi
    up = pd.Series(np.linspace(1, 2, 90), index=pd.date_range("2026-01-01", periods=90))
    assert rsi(up).dropna().iloc[-1] > 95
    flat = pd.Series(1.0, index=up.index)
    assert beta_to_btc(up, flat) is None                          # BTC never moves: no beta
    assert beta_to_btc(up ** 5, up) == 3.0 and beta_to_btc(up ** 0.1, up) == 0.5     # clipped to [0.5, 3]


def test_btc_cycles_coin_notes(snapdir, monkeypatch):
    from app.topics import btc_cycles as _C
    monkeypatch.setattr(_C, "FUND_DIR", snapdir / "btc_fundamentals")          # per-coin fundamentals files stay in the test's folder
    from app.topics import btc_cycles as C
    notes = C.coin_notes()["coins"]
    assert {c["ticker"] for c in C.coins_list()} == set(notes)
    assert all(n["narrative"] and n["standout"] and n["thesis"] for n in notes.values())
    charts = _chart(mult=2.5)
    import json as _json
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    monkeypatch.setattr(C, "PACE", 0)
    C.fill_coins()
    k = C._coins_now()
    hype = next(c for c in k["coins"] if c["ticker"] == "HYPE")
    assert hype["notes"]["thesis"] and any("High beta" in t for t in hype["now"]) and any("Market cap rank" in t for t in hype["now"])
    assert C._coin_now("SOL")["notes"]["narrative"].startswith("Solana")
    assert C.stands_out({"rsi_vs_btc": 75, "beta": 0.6, "from_high": -0.8}, []) == [
        "Running hot against BTC (RSI vs BTC 75).", "80% below its 1-year high.", "Low beta (0.6): has moved less than BTC, so its projection band is narrow."]


# ------------------------------------------------------------------ ETF and MSTR tabs
def _farside_html(n=720):
    days = pd.bdate_range("2024-01-11", periods=n)
    cols = ["IBIT", "FBTC", "BITB", "ARKB", "BTCO", "EZBC", "BRRR", "HODL", "BTCW", "GBTC", "BTC"]
    rows = "".join("<tr><td>" + d.strftime("%d %b %Y") + "</td>" + "".join(f"<td>{'(12.5)' if c == 'GBTC' else '-' if c == 'BTCW' else f'{10 + i % 7:.1f}'}</td>" for c in cols) + "<td>0</td></tr>"
                   for i, d in enumerate(days))
    return ("<html><body><table class='nav'><tr><td>menu</td></tr></table><table class='etf'><thead><tr><th></th>" + "".join(f"<th>{c}</th>" for c in cols)
            + "<th>Total</th></tr></thead><tbody>" + rows + "<tr><td>Total</td>" + "<td>1</td>" * 12 + "</tr></tbody></table></body></html>")


def _bitbo_page(n=720):
    ms = [int(d.timestamp() * 1000) for d in pd.bdate_range("2024-01-11", periods=n)]
    return "var historyBtc = [" + ",".join(f"[getPreviousBusinessDay({t}), truncate({100 + i % 9 - 4}, 2)]" for i, t in enumerate(ms)) + "]; var mergedHistoryBtc = [];"


def _mstr_json():
    days = pd.date_range("2020-08-11", "2026-10-20", freq="W")
    pts, hold = [], 21454
    for i, d in enumerate(days):
        if i % 5 == 0:
            hold += 1000
        pts.append({"d": str(d.date()), "mstr": 13 + i * 0.4, "btc": 11000 + i * 250, "hold": hold, "basic": 95_000_000 + i * 200_000, "dil": 1})
    return {"note": "fixture", "points": pts}


def _yahoo(start=10.0, n=400, seed=2):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp("2026-10-20"), periods=n)
    px = start * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    return {"chart": {"result": [{"timestamp": [int(d.timestamp()) for d in days], "indicators": {"quote": [{"close": list(px)}]}}]}}


def test_btc_etf_and_mstr(snapdir, monkeypatch):
    from app.topics import btc_cycles as C, btc_flows as F
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: _cm())
    monkeypatch.setattr(F, "fetch", lambda url, ttl, **k: _farside_html() if "farside" in url else _bitbo_page())
    monkeypatch.setattr(F, "fetch_json", lambda url, ttl, **k: _mstr_json() if "mstr-nav" in url else _yahoo(150 if "MSTR" in url else 60000 if "BTC-USD" in url else 1.0))
    e = F._etf_now()
    B.json_safe(e)
    assert not [k for k in e if k.endswith("_error")], [k for k in e if k.endswith("_error")]
    assert e["kpi"]["since_launch_usd_m"] > 0 and e["table"][0]["ticker"] != "GBTC" and next(r for r in e["table"] if r["ticker"] == "GBTC")["since_launch"] < 0
    assert e["kpi"]["streak"] > 0 and "Others" in e["cum_by_issuer"] and e["cum_btc"][-1][1] > 0 and e["milestones"][0]["date"] == "2024-01-10"
    assert "Hong Kong spot ETFs (BTC)" in e["intl"]
    m = F._mstr_now()
    B.json_safe(m)
    assert m["kpi"]["purchases"] > 50 and m["purchases"][0]["date"] > m["purchases"][-1]["date"] and m["kpi"]["approx_avg_cost"] > 0
    assert m["price_source"].startswith("daily closes") and -1 <= m["kpi"]["corr90"] <= 1 and m["mnav"][-1][1] > 0
    S = m["strategies"]
    assert "strategies_error" not in m and {c["rule"] for c in S["checklist"]} >= {"Premium extreme", "BTC trend", "Accretion floor", "Halving clock"}
    assert all(c["state"] in {"exit", "caution", "watch", "clear"} for c in S["checklist"]) and S["backtests"][0]["rule"] == "Hold MSTR" and S["research"]["sections"]
    nav, px = dict(m["nav_per_share"]), dict(m["mstr"])                 # price at mNAV 1: price / NAV per share is mNAV
    t = m["mnav"][-1][0]
    assert nav[t] > 0 and px[t] / nav[t] == pytest.approx(m["mnav"][-1][1], rel=0.01)
    assert {t["country"] for t in m["treasuries"]} == {"UK", "HK"} and all("price" in t for t in m["treasuries"])


def test_btc_treasury_prices_fall_back_from_yahoo(snapdir, monkeypatch):
    from app.topics import btc_cycles as C, btc_flows as F
    assert F.alt_symbols("SWC.L") == ["SWC-GB"] and F.alt_symbols("0434.HK") == ["434-HK", "0434-HK"] and F.alt_symbols("MSTR") == []
    days = pd.bdate_range(end="2026-10-20", periods=300)
    bars = lambda p0: {"barData": {"priceBars": [{"tradeTimeinMills": str(int(d.timestamp() * 1000)), "close": str(p0 + i / 1000)} for i, d in enumerate(days)]}}
    assert len(F.parse_cnbc(bars(2))) == 300 and F.parse_cnbc(bars(2)).iloc[-1] == pytest.approx(2.299) and F.parse_cnbc({}).empty

    def yahoo_429(url, ttl, **k):                    # as on Railway: Yahoo 429, CNBC answers SWC-GB and 434-HK, 0434-HK has no bars
        if "mstr-nav" in url:
            return _mstr_json()
        if "SWC-GB" in url:
            return bars(30)
        if "/434-HK/" in url:
            return bars(2)
        if "cnbc" in url:
            return {"barData": {"priceBars": []}}
        raise RuntimeError("429 Too Many Requests")
    monkeypatch.setattr(C, "fetch_json", lambda url, ttl, **k: _cm())
    monkeypatch.setattr(F, "fetch_json", yahoo_429)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    m = F._mstr_now()
    B.json_safe(m)
    t = {x["country"]: x for x in m["treasuries"]}
    assert t["UK"]["price_source"] == t["HK"]["price_source"] == "CNBC" and t["HK"]["price"][-1][1] == pytest.approx(2.299)
    assert len(t["HK"]["price_tried"]) == 1 and t["UK"]["held_value_usd"] > 0
    # nothing answers: holdings only, with what was tried
    monkeypatch.setattr(F, "fetch_json", lambda url, ttl, **k: _mstr_json() if "mstr-nav" in url else (_ for _ in ()).throw(RuntimeError("429")))
    from app.cache import _cache
    _cache.clear()
    hk = next(x for x in F._mstr_now()["treasuries"] if x["country"] == "HK")
    assert "price" not in hk and hk["price_error"].startswith("no price source") and len(hk["price_tried"]) == 3 and hk["rows"]


def test_btc_treasury_prefers_cnbc_over_an_old_yahoo_copy(snapdir, monkeypatch):
    from app.topics import btc_flows as F
    days = pd.bdate_range(end="2026-10-20", periods=300)
    cnbc = {"v": {"barData": {"priceBars": [{"tradeTimeinMills": str(int(d.timestamp() * 1000)), "close": "30"} for d in days]}}}

    def fj(url, ttl, key=None, **k):                 # as fetch does on a 429 with a snapshot: the old copy, STALE set under the key
        if "yahoo" in url:
            B.STALE[key] = time.time() - 9 * 86400
            return _yahoo(5.0, n=200)
        return cnbc["v"]
    monkeypatch.setattr(F, "fetch_json", fj)
    s, src, tried = F.stock_daily("SWC.L")
    assert src == "CNBC" and len(s) == 300 and "last good copy" in tried[0]
    from app.cache import _cache
    _cache.clear()
    cnbc["v"] = {"barData": {"priceBars": []}}
    s, src, tried = F.stock_daily("SWC.L")
    assert src == "Yahoo (last good copy)" and len(s) == 200 and len(tried) == 2


def test_farside_parser_rejects_a_changed_page():
    from app.topics.btc_flows import parse_farside, _num
    assert _num("(12.5)") == -12.5 and _num("-") == 0 and _num("1,234.5") == 1234.5
    with pytest.raises(ValueError):
        parse_farside("<table><tr><td>nothing</td></tr></table>")
    df = parse_farside(_farside_html(80))
    assert len(df) == 80 and df["GBTC"].iloc[0] == -12.5 and df["BTCW"].iloc[0] == 0


def test_ai_merged_endpoints(snapdir, monkeypatch):
    from app.topics import ai, ai_jobs as J
    monkeypatch.setattr(J, "fetch", jobs_fetch)
    assert {"openings", "headcount", "wages", "ratio", "firms", "users", "agents", "skills"} <= set(ai.ENDPOINTS)
    w = J._wages_now()
    B.json_safe(w)
    assert set(w["levels"]) == set(J.US_WAGES) and "All private" not in w["premium"] and w["as_of"] and w["missing"] == []
    assert all(sid.endswith("03") for sid in J.US_WAGES.values())
    h = J._headcount_now()
    hk = h["HK"]
    assert set(hk) == {"Financing & insurance", "Professional, scientific & technical", "Information & communications"}
    assert hk["Financing & insurance"][-1] == [int(pd.Timestamp("2026-06-01").timestamp()), 246.5] and len(hk["Financing & insurance"]) == 34
    r = J._ratio_now()
    assert r["US"]["ai_wide_index"] and r["US"]["ai_wide_over_professions"]
    assert J.SECTORS["ai_wide"] == ["IT Systems & Solutions", "Scientific Research & Development"]
    # R&D rises in the fixture while software, data and IT fall, so the wider group sits above the narrow one: (3 x -1 + 2) / 4 vs -1 per day
    assert r["US"]["ai_wide_index"][-1][1] > r["US"]["ai_index"][-1][1]


def ramp_page(months: int = 39) -> str:
    """The Ramp AI Index page as served (Oct 2026): records inside a Next.js script string, escaped quotes; the overall series plus
    breakdowns that carry an extra key (vendor, naics_sector, ...) and a Census comparison with question_version."""
    recs = []
    for i, d in enumerate(pd.date_range("2023-07-01", periods=months, freq="MS")):
        dm = str(d.date())
        recs += [{"date_month": dm, "adoption_rate_pct": round(24.53 + i * (55.86 - 24.53) / (months - 1), 2), "mom_change_pp": 0.8, "yoy_change_pp": None if i < 12 else 12.06},
                 {"date_month": dm, "vendor": "Anthropic", "adoption_rate_pct": 0.15 + i, "mom_change_pp": 0},
                 {"date_month": dm, "naics_sector": "Finance & Insurance", "adoption_rate_pct": 30.0, "mom_change_pp": 0},
                 {"date_month": dm, "adoption_rate_pct": 3.7, "mom_change_pp": None, "record_count": 2, "question_version": "pre_nov_2025_wording_change", "selection_note": None}]
    payload = ",".join(json.dumps(r, separators=(",", ":")) for r in recs).replace('"', '\\"')
    return '<html><meta name="description" content="In September 2026, 55.9% of U.S. businesses on Ramp paid for AI"/><script>self.__next_f.push([1,"' + payload + '"])</script>' + " " * 50000


def test_bls_over_the_daily_limit_keeps_the_last_good_reply(snapdir, monkeypatch):
    import os
    from app.topics import ai_jobs as J
    calls = []
    def fetch(url, ttl, **k):
        calls.append(url)
        return jobs_fetch(url, ttl, **k)
    monkeypatch.setattr(J, "fetch", fetch)
    assert J._wages_now()["as_of"] and len([c for c in calls if "bls" in c]) == 2
    J._wages_now()
    assert len([c for c in calls if "bls" in c]) == 2                    # a good reply under a day old: no new request (restarts are free)
    for f in snapdir.glob("bls-good-*"):
        os.utime(f, (time.time() - 2 * 86400,) * 2)
    from app import cache
    cache._cache.clear()
    over = json.dumps({"status": "REQUEST_NOT_PROCESSED", "message": ["Daily threshold for total number of requests allocated is reached."], "Results": {}})
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: over if "bls" in url else jobs_fetch(url, ttl, **k))
    w = J._wages_now()
    assert w["as_of"] and set(w["levels"]) == set(J.US_WAGES) and J.BLS in w["stale"]
    h = J._headcount_now()
    assert h["US"] and not h.get("US_error")

def test_pay_and_headcount_open_when_bls_is_down(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    over = json.dumps({"status": "REQUEST_NOT_PROCESSED", "message": ["Daily threshold reached."], "Results": {}})
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: over if "bls" in url else jobs_fetch(url, ttl, **k))
    w, h = J._wages_now(), J._headcount_now()
    B.json_safe(w)
    assert w["levels"] is None and w["levels_error"] and "REQUEST_NOT_PROCESSED" in w["bls_error"] and w["missing"] == [] and w["as_of"] is None
    assert h["US"] is None and h["HK"]


def test_ai_readings_from_cached_payloads(snapdir, monkeypatch):
    pytest.importorskip("openpyxl")
    from app.topics import ai, ai_adoption as A, ai_jobs as J
    from app.topics._daily import _clean
    assert ai.READINGS() == []                                             # nothing cached yet: nothing read, nothing fetched
    monkeypatch.setattr(J, "fetch", jobs_fetch)
    def fake(url, ttl, **k):
        if url == A.BTOS_XLSX:
            return btos_national_xlsx().decode("latin-1")
        if url == A.RAMP_PAGE:
            return ramp_page()
        if url == A.BICS_PAGE:
            return BICS_PAGE_HTML
        return bics_wave_xlsx().decode("latin-1")
    monkeypatch.setattr(A, "fetch", fake)
    for name in ("openings", "headcount", "wages", "ratio", "firms", "users", "agents", "skills"):
        ai.ENDPOINTS[name]()
    r = ai.READINGS()
    keys = {x["key"]: x for x in r}
    assert {"ai_share_us", "ai_share_gb", "ai_over_prof_us", "us_legal_yoy", "us_finance_yoy", "hk_finance_yoy", "pay_tech_minus_legal",
            "btos_us", "ramp_us", "uk_firms", "chatgpt_wau", "launches_12m", "countries_rising"} <= set(keys)
    from app import topics
    assert {x["tab"] for x in r} == {t for t, _ in topics.REGISTRY["ai"].tabs}          # every tab reads, and only real tab keys
    assert keys["ramp_us"]["value"] == 55.86 and keys["ramp_us"]["lean"] == 1 and keys["uk_firms"]["value"] == 29.7
    assert keys["ai_share_us"]["lean"] == 1 and keys["chatgpt_wau"]["value"] == 800000000
    assert all(x["lean"] in (-1, 0, 1) for x in r) and len(_clean(r)) == len(r)
    B.json_safe(r)


def test_london_heatmap_from_bres(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    monkeypatch.setattr(J, "fetch", jobs_fetch)
    L = J._headcount_now()["London"]
    assert L["years"][0] == 2015 and L["years"][-1] == 2024 and L["boroughs"][0] == "City of London" and len(L["boroughs"]) == 4
    assert L["sectors"] == list(J.LONDON_SECTORS.values())
    city = L["values"]["City of London"]
    assert city["All jobs"][-1] == 400000 - 450 and city["Software & IT"][0] == 20000 and city["Software & IT"][-1] == 20000 + 9 * 300
    assert L["values"]["Bexley"]["Insurance"] == [None] * 10
    with pytest.raises(ValueError):
        J.parse_bres('"DATE_NAME","GEOGRAPHY_NAME","GEOGRAPHY_CODE","INDUSTRY","OBS_VALUE"\n"2024","Camden","E09000007",1,5\n')


def test_ramp_ai_index_parser():
    from app.topics.ai_adoption import parse_ramp
    s = parse_ramp(ramp_page())
    assert len(s) == 39 and s.index[0] == pd.Timestamp("2023-07-01") and s.index[-1] == pd.Timestamp("2026-09-01") and s.iloc[-1] == 55.86 and s.iloc[0] == 24.53
    with pytest.raises(ValueError):
        parse_ramp("<html>redesigned</html>")


# ------------------------------------------------------------------ housing: boroughs, fixed rate, US and HK
def _rvd_xls():
    import io
    rows = [["Private Domestic - Price Indices (1999 = 100)", None, None]]
    for y in range(2010, 2027):
        for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
            rows.append([y if i == 0 else None, m, 200 + (y - 2010) * 10 + i])
    buf = io.BytesIO(); pd.DataFrame(rows).to_excel(buf, index=False, header=False)
    return buf.getvalue().decode("latin-1")


HIBOR = {"result": {"records": [{"end_of_month": f"{y}-{m:02d}", "ir_1m": 1 + (y - 2015) * 0.2} for y in range(2015, 2027) for m in range(1, 13)]}}


def housing_mocks(monkeypatch):
    from app.topics import housing as H
    monkeypatch.setattr(H, "fetch", housing_fetch)
    monkeypatch.setattr(H, "fetch_json", lambda url, ttl, **k: HIBOR)
    monkeypatch.setattr(H, "full_file_url", lambda: "http://publicdata.landregistry.gov.uk/x.csv")
    return H


def test_housing_boroughs_global_and_fixed_rate(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    b, g, a = H._boroughs_now(), H._global_now(), H._afford_now()
    for d in (b, g, a):
        B.json_safe(d)
    assert len(b["rows"]) == 33 and not b["errors"] and {"Kensington and Chelsea", "City of Westminster", "Richmond upon Thames"} <= {r["borough"] for r in b["rows"]}
    assert not [k for k in g if k.endswith("_error")], [k for k in g if k.endswith("_error")]
    assert set(g["us"]) == {"US national (FHFA)", "New York metro (FHFA)", "San Francisco metro (FHFA)"} and g["hk"] and set(g["rates"]) == {"UK 2-year fixed (75% LTV)", "US 30-year fixed", "HK 1-month HIBOR"}
    assert {r["market"] for r in g["table"]} >= {"London", "Hong Kong (RVD)"}
    assert a["mortgage_basis"].startswith("the Bank of England's quoted 2-year fixed") and a["fixed_2y"]
    assert len(H.parse_rvd(_rvd_xls().encode("latin-1"))) == 17 * 12
    assert {"London", "United Kingdom", "Camden", "City of Westminster"} <= set(H.regions()) and "Leeds" not in H.regions()


def test_housing_global_survives_a_refused_hibor_and_dates_quarterly_change(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)

    def refused(url, ttl, **k):
        raise RuntimeError("405 Client Error: Not Allowed")
    monkeypatch.setattr(H, "fetch_json", refused)
    g = H._global_now()
    assert set(g["rates"]) == {"UK 2-year fixed (75% LTV)", "US 30-year fixed"} and list(g["rates_missing"]) == ["HK 1-month HIBOR"]
    ny = next(r for r in g["table"] if r["market"] == "New York metro (FHFA)")
    assert abs(ny["yoy"] - 8 / 424) < 0.001, ny            # fixture: +8 a year on a quarterly series, not 13 quarters back


def test_housing_london_pay_ratio(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    p = H.parse_nomis(NOMIS)
    assert p.index[0] == pd.Timestamp("1999-04-01") and p.iloc[-1] == 55000 and len(p) == 27      # the empty 1998 row is dropped
    a = H._afford_now()
    assert a["price_to_london_pay"] and a["now"]["pe_basis"] == "london" and a["now"]["london_pay"] == 55000 and a["now"]["london_pay_year"] == 2025
    lon = H.hpi("london")["avg"].dropna()
    last = a["price_to_london_pay"][-1]
    assert abs(last[1] - lon.iloc[-1] / p[p.index <= lon.index[-1]].iloc[-1]) < 0.01      # each price month uses the survey in force then


def test_housing_borough_map(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    b = H._boroughs_now()
    B.json_safe(b)
    assert len(b["map"]["shapes"]) == 33 and b["map"]["viewBox"].startswith("0 0 1000") and all(s["d"].startswith("M") for s in b["map"]["shapes"])
    assert {r["code"] for r in b["rows"]} == {s["code"] for s in b["map"]["shapes"]}            # every borough row has an outline, Westminster included
    w = next(r for r in b["rows"] if r["borough"] == "City of Westminster")
    assert w["rent_yoy"] == 5.0
    assert w["code"] == "E09000033" and w["rent_2bed"] == 3600 and w["flat"] and w["terraced"] and w["rent_month"] == "2026-09-01"
    assert next(r for r in b["rows"] if r["borough"] == "City of London")["rent_2bed"] is None and b["rents_error"] is None
    h = b["map"]["history"]
    assert h["start"] == "2005-01" and set(h["values"]) == {"flat", "terraced", "semi", "detached", "rent_2bed"}
    wf, wr = h["values"]["flat"]["E09000033"], h["values"]["rent_2bed"]["E09000033"]
    assert len(wf) == len(wr) == h["months"] and all(v % 100 == 0 for v in wf if v is not None)        # prices to the nearest £100
    assert wr[(2014 - 2005) * 12] is None and wr[(2015 - 2005) * 12] == 2900 and wr[-1] == 3600         # rents start in 2015


def test_housing_readings(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    from app import cache
    assert H.READINGS() == []                                   # nothing cached yet: nothing read, nothing downloaded
    for tab in ("prices", "afford", "boroughs", "global"):
        H.ENDPOINTS[tab]()
    r = {x["key"]: x for x in H.READINGS()}
    assert set(r) == {"london_price_yoy", "london_rent_yoy", "fixed_2y_6m", "price_to_pay_1y", "boroughs_rising", "london_vs_us_yoy"}
    assert all(x["tab"] in {t for t, _ in topics.REGISTRY["housing"].tabs} and x["lean"] in (-1, 0, 1) for x in r.values())
    assert r["london_rent_yoy"]["value"] == 5.0 and r["london_rent_yoy"]["lean"] == 0           # fixture rents +5%: neither cheap nor dear
    assert H._lean(-1, 0, 3) == 1 and H._lean(4, 0, 3) == -1 and H._lean(None, 0, 3) == 0
    from app.topics import _daily
    assert _daily._clean(H.READINGS()) and len(_daily._clean(H.READINGS())) == len(r)


def test_housing_rents_from_pipr(snapdir, monkeypatch):
    H = housing_mocks(monkeypatch)
    assert H.pipr_url(PIPR_PAGE).endswith("/21october2026/priceindexofprivaterentsukmonthlypricestatistics.xlsx")
    r = H.parse_pipr(_pipr_xlsx().encode("latin-1"))
    assert {"London average rent", "England average rent", "E09000033"} <= set(r) and r["London average rent"]["rent"].iloc[-1] == 1600 + 140 * 5
    assert r["E09000033"]["rent_2bed"].iloc[-1] == 2900 + 140 * 5 and r["E09000001"]["rent_2bed"].isna().all()
    p = H._prices_now()
    assert set(p["rents"]) >= {"London average rent", "England average rent"} and p["rent_now"]["rent"] == 2300 and p["rent_now"]["yoy"] == 5.0
    assert p["rent_now"]["month"] == "2026-09-01" and 0 < p["rent_now"]["rent_to_price"] < 0.2
    assert set(p["rent_vs_price"]) == {"Rent", "House price"} and p["rent_vs_price"]["Rent"][0][1] == 100.0
    assert p["gross_yield"] and 0 < p["gross_yield"][-1][1] < 20 and p["premium"] and p["premium"][-1][1] > 0
    assert "from_peak" in p["real_now"] and not [k for k in p if k.endswith("_error")]


def test_robotaxi_tesla_rate_and_rules(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)
    monkeypatch.setattr(R, "fetch_json", lambda url, ttl, **k: _yahoo(250))
    t, f, s = R._tesla_now(), R._footprint_now(), R._safety_now()
    for d in (t, f, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], [k for k in d if k.endswith("_error")]
    assert t["kpi"]["deliveries_last"] > 0 and t["tsla"] and {"UK", "HK"} <= set(t["fsd_markets"]) and t["milestones"][0]["date"] >= t["milestones"][-1]["date"]
    assert {r["market"] for r in f["regulation"]} >= {"US", "UK", "HK", "China"}
    w = [x for x in s["reports"]["rate"] if x["operator"] == "Waymo"]                     # miles.csv says "Waymo", NHTSA "Waymo LLC"
    assert w and all(x["reports"] > 0 and x["per_million"] > 0 for x in w) and s["reports"]["archived"]


def test_robotaxi_rate_hidden_without_sgo_archive(snapdir, monkeypatch):
    from app.topics import robotaxi as R

    def fetch(url, ttl, **k):
        if url == R.SGO_ARCHIVE:
            raise OSError("archive down")
        return SGO
    monkeypatch.setattr(R, "fetch", fetch)
    r = R._safety_now()["reports"]
    assert r["n"] == 120 and r["rate"] == [] and r["archived"] is False


def test_source_health(snapdir, monkeypatch):
    pytest.importorskip("aiohttp")
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    from app.topics import robotaxi as R
    B.HEALTH.clear()
    calls = {"n": 0}

    def dl(url, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return SGO
        raise ConnectionError("down")
    monkeypatch.setattr(B, "_download", dl)
    monkeypatch.setattr(R, "fetch", B.fetch)                    # the real fetch, over the fake download
    R.sgo()                                                     # works, snapshot written
    from app import cache
    cache._cache.clear()
    R.sgo()                                                     # fails, served from the snapshot
    h = topics.health()
    rt = h["dashboards"]["robotaxi"]
    assert rt["stale"] == 1 and rt["sources"][0]["host"] == "static.nhtsa.gov" and rt["sources"][0]["error"] == "ConnectionError: down"
    assert set(topics.REGISTRY) <= set(h["dashboards"])
    B.HEALTH[R.SGO]["fail"] = B.HEALTH[R.SGO]["fail"]
    B.STALE[R.SGO] -= 5 * 86400                                  # snapshot five days old: past the 3-day threshold
    assert topics.health()["dashboards"]["robotaxi"]["sources"][0]["alert"]

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            j = await (await c.get("/api/health")).json()
            assert "robotaxi" in j["dashboards"] and j["thresholds"]["stale_days"] == 3
    asyncio.run(go())
    B.HEALTH.clear()


class _Resp:
    def __init__(self, code, retry=None):
        self.status_code, self.headers = code, ({"Retry-After": str(retry)} if retry is not None else {})


def _http(code, retry=None):
    import requests
    return requests.HTTPError(f"{code} Client Error", response=_Resp(code, retry))


def test_fetch_stable_key_mirrors_and_429_cooldown(snapdir, monkeypatch):
    """A URL that changes every call (Yahoo's end date) keeps one snapshot under `key`; a 429 sends fetch to the mirror, then to
    the snapshot, and the host is not asked again until its cooldown ends."""
    from app import cache
    B.HEALTH.clear(), B.COOLDOWN.clear()
    seen, mode = [], {"v": "ok"}

    def dl(url, *a, **k):
        seen.append(url.split("/")[2])
        if mode["v"] == "ok":
            return "x" * 300
        raise _http(429, retry=600)
    monkeypatch.setattr(B, "_download", dl)
    B.fetch("https://a.example/s?end=1", key="https://a.example/s", min_bytes=10)
    assert seen == ["a.example"] and "https://a.example/s" in B.HEALTH and B.HEALTH["https://a.example/s"]["ok"]
    cache._cache.clear()
    mode["v"] = "429"
    t = B.fetch("https://a.example/s?end=2", key="https://a.example/s", mirrors=("https://b.example/s?end=2",), min_bytes=10)
    assert t == "x" * 300 and seen[1:] == ["a.example", "b.example"]          # both hosts asked once, then the snapshot
    assert "https://a.example/s" in B.STALE and 590 < B.COOLDOWN["a.example"] - time.time() <= 600
    cache._cache.clear()
    B.fetch("https://a.example/s?end=3", key="https://a.example/s", mirrors=("https://b.example/s?end=3",), min_bytes=10)
    assert len(seen) == 3                                                      # cooling down: nobody asked, snapshot served
    st = topics.health()["dashboards"]
    src = [s for d in st.values() for s in d["sources"] if s["url"] == "https://a.example/s"][0]
    assert src["status"] == "stale" and "429" in src["error"]
    B.COOLDOWN.clear(), B.HEALTH.clear()


def test_yahoo_429_serves_snapshot_then_nasdaq_marks_handled(snapdir, monkeypatch):
    from app import cache
    B.HEALTH.clear(), B.COOLDOWN.clear()
    yahoo = json.dumps(_yahoo(250, n=250))
    mode = {"v": "ok"}

    def dl(url, *a, **k):
        if "nasdaq" in url:
            rows = [{"date": d.strftime("%m/%d/%Y"), "close": f"${100 + i}"} for i, d in enumerate(pd.bdate_range(end="2026-10-20", periods=60))]
            return json.dumps({"data": {"tradesTable": {"rows": rows}}})
        if mode["v"] == "ok":
            return yahoo
        raise _http(429)
    monkeypatch.setattr(B, "_download", dl)
    assert len(B.yahoo_daily("TSLA", "2019-01-01")) == 250 and len(B.yahoo_daily("SWC.L", "2019-01-01")) == 250
    monkeypatch.setattr(B.time, "time", lambda t=time.time() + 3600: t)          # an hour later: another end date (period2), same key
    cache._cache.clear()
    mode["v"] = "429"
    s = B.yahoo_daily("TSLA", "2019-01-01")                                    # Yahoo serves its copy (stale), Nasdaq is fresher
    assert len(s) == 60 and B.yahoo_key("TSLA", "2019-01-01") in B.STALE
    assert sorted(u for u in B.HEALTH if "yahoo" in u) == sorted(B.yahoo_key(t, "2019-01-01") for t in ("TSLA", "SWC.L"))   # one per series
    src = [s for d in topics.health()["dashboards"].values() for s in d["sources"] if s["url"] == B.yahoo_key("TSLA", "2019-01-01")][0]
    assert src["status"] == "stale" and "Nasdaq" in src["handled"]
    assert len(B.yahoo_daily("SWC.L", "2019-01-01")) == 250 and B.yahoo_key("SWC.L", "2019-01-01") in B.STALE   # no Nasdaq: the copy
    # a ticker never fetched before: Yahoo refused (cooling down), Nasdaq answers, the Yahoo failure is handled (no alert)
    s = B.yahoo_daily("ZZZZ", "2019-01-01")
    assert len(s) == 60 and s.iloc[-1] == 159
    src = [s for d in topics.health()["dashboards"].values() for s in d["sources"] if s["url"] == B.yahoo_key("ZZZZ", "2019-01-01")][0]
    assert src["status"] == "failing" and not src["alert"] and "Nasdaq" in src["handled"]
    B.COOLDOWN.clear(), B.HEALTH.clear()


def test_robotaxi_cpuc_links():
    from app.topics import robotaxi as R
    html = ('<a class="x" href="/-/media/cpuc-website/q1-2026-waymo.xlsx?rev=ab&amp;hash=1"><span>Waymo\n Q1 2026</span></a>'
            '<a href="https://www.cpuc.ca.gov/report.pdf">PDF</a><a href="https://example.org/t.csv">CSV</a>')
    assert R.cpuc_links(html) == [{"text": "Waymo Q1 2026", "url": "https://www.cpuc.ca.gov/-/media/cpuc-website/q1-2026-waymo.xlsx?rev=ab&hash=1"},
                                  {"text": "CSV", "url": "https://example.org/t.csv"}]


def _cpuc_zip(folder, months):
    import io
    import zipfile
    rows = "TCPID,Year,Month,TotalTrips,TotalWaiting\n" + "".join(f'PSG0038152,{y},{m},"{t:,}","1,000"\n' for y, m, t in months)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{folder}/PSG0038152_2026_08_AV_Month_Part0-Deployment.csv", rows)
        z.writestr(f"{folder}/PSG0038152_2026_08_AV_Monthly_Tract_Part0-Deployment-Public.csv", "TCPID,Year,Month,Tract,TripsStart\nPSG0038152,2026,4,1,99\n")
        z.writestr(f"{folder}/PSG0038152_2026_08_AV_Trips_Part0-Deployment-Public.csv", "RideID\n1\n")
    return buf.getvalue()


def test_robotaxi_cpuc_trips_from_deployment_zips(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    base = "/-/media/cpuc-website/divisions/consumer-protection-and-enforcement-division/documents/tlab/av-programs/"
    page = (f'<a href="{base}waymo-deployment-2026q2.zip">Waymo</a><a href="{base}waymo-driverless-deployment-2025-q1.zip">Waymo</a>'
            f'<a href="{base}av-pilot-2026q2.zip">Download all reports</a>' + " " * 1000)
    zips = {"2026q2": _cpuc_zip("Waymo Deployment 2026Q2", [(2026, 4, 1416158), (2026, 5, 1454991), (2026, 6, 1348926)]),
            "2025-q1": _cpuc_zip("Waymo Driverless Deployment 2025 Q1", [(2025, 1, 550457), (2025, 2, 559569)])}     # a quarter short of a month
    got = []

    def zip_for(url):
        got.append(url)
        assert "pilot" not in url                                     # pilot (safety driver) files are not driverless trips
        return next(v for k, v in zips.items() if k in url)
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: page if url == R.CPUC_PAGE else SGO)
    monkeypatch.setattr(R, "_cpuc_zip", zip_for)
    t = R.cpuc_trips()
    assert list(t) == ["Waymo"] and t["Waymo"].to_dict() == {pd.Timestamp("2026-04-01"): 4220075}
    f = R._footprint_now()
    assert f["cpuc"]["Waymo"] == [[int(pd.Timestamp("2026-04-01").timestamp()), 4220075]] and "cpuc_error" not in f
    assert len(got) == 2                                              # each zip is read once, then served from the snapshot volume
    assert R.parse_cpuc_month('TCPID,Year,Month,TotalTrips\nPSG0039080,2023,7,"12,345"\n') == [{"carrier": "Cruise", "month": "2023-07-01", "trips": 12345}]
    with pytest.raises(ValueError):
        R.parse_cpuc_month("TCPID,Year,Trips\nX,2026,1\n")


def test_robotaxi_tesla_vs_price():
    from app.topics import robotaxi as R
    qs = pd.date_range("2023-01-01", "2026-07-01", freq="QS")
    deliv = pd.Series([400 + 10 * i + (30 if i % 3 == 0 else 0) for i in range(len(qs))], index=qs, dtype=float)
    days = pd.bdate_range("2022-12-01", "2026-10-20")
    level = pd.Series(deliv.reindex(days.to_period("Q").to_timestamp()).ffill().bfill().values, index=days)   # price = the quarter's deliveries
    c = R.tesla_vs_price(level, {"Deliveries": deliv})
    assert {(x["basis"], x["r"]) for x in c["rows"]} >= {("level vs quarter-end close", 1.0)}
    jump = pd.Series(100.0, index=days)                                                   # flat, with a jump on each release day by the growth on the quarter
    for q, g in deliv.pct_change().dropna().items():
        jump[days[days.searchsorted(q + pd.DateOffset(months=3) + pd.Timedelta(days=1))]:] *= 1 + g
    c = R.tesla_vs_price(jump, {"Deliveries": deliv, "Free cash flow ($M)": pd.Series(range(len(qs)), index=qs, dtype=float)})
    r = {(x["metric"], x["basis"]): x for x in c["rows"]}
    assert r[("Deliveries", "change on the quarter vs TSLA move on release day")]["r"] == 1.0
    assert r[("Deliveries", "change on the quarter vs TSLA move on release day")]["n"] == len(qs) - 1
    assert not [k for k in r if k[0] == "Free cash flow ($M)" and "release" in k[1]]      # only the deliveries release is timed
    assert len(c["quarters"]["quarter"]) == len(qs) and c["quarters"]["close"][-1] > 100
    assert R.tesla_vs_price(pd.Series(dtype=float), {}) == {"rows": [], "quarters": []}


def test_mnav_backtest_engine():
    from app.topics import btc_flows as F
    idx = pd.date_range("2022-01-07", periods=5, freq="W-FRI")
    w = pd.DataFrame({"mstr": [10, 11, 12.1, 12.1, 13.31], "btc": [100, 100, 110, 121, 121]}, index=idx, dtype=float)
    one, zero = pd.Series(1.0, index=idx), pd.Series(0.0, index=idx)
    assert F.backtest(w, one, zero, cost=0)["multiple"] == pytest.approx(1.331, abs=0.006)            # MSTR +10% three times
    assert F.backtest(w, zero, one, cost=0)["multiple"] == pytest.approx(1.21, abs=0.006)
    # decided at a week's close, earned the next week: in MSTR for weeks 1-2, then BTC
    pm = pd.Series([1, 1, 0, 0, 0], index=idx, dtype=float)
    assert F.backtest(w, pm, 1 - pm, cost=0)["multiple"] == pytest.approx(1.1 * 1.1 * 1.1, abs=0.006)
    h = F._hysteresis(pd.Series([False, True, False, False, False]), pd.Series([False, False, False, True, False]))
    assert h.tolist() == [1, 0, 0, 1, 1]


def _tesla_quarters(n=15, start="2023-01-01"):
    qs = pd.date_range(start, periods=n, freq="QS")
    up = pd.Series([100.0 + 5 * i for i in range(n)], index=qs)
    return qs, {"Deliveries": up, "Revenue ($M)": up * 50, "GAAP gross margin (%)": pd.Series([20.0 - 0.1 * i for i in range(n)], index=qs)}


def test_robotaxi_tesla_signal_uses_only_published_figures():
    from app.topics import robotaxi as R
    qs, t = _tesla_quarters()
    px = pd.Series(100.0, index=pd.bdate_range("2023-01-01", "2026-10-20"))
    s = R.tesla_signal(px, t)
    ev = {e["date"]: e for e in s["events"]}
    assert s["events"][0]["date"] == "2024-04-02"                      # Q1 2024 deliveries (first with a year-earlier quarter), out on 2 Apr
    assert ev["2024-04-02"]["votes"] == {"Deliveries": 1}              # the Q1 financials are not public yet...
    assert ev["2024-05-05"]["votes"] == {"Deliveries": 1, "Revenue ($M)": 1, "GAAP gross margin (%)": -1}   # ...until 35 days after the quarter
    assert ev["2024-05-05"]["signal"] == round(1 / 3, 3) and ev["2024-05-05"]["long"]
    t2 = {k: v.copy() for k, v in t.items()}
    t2["Deliveries"].iloc[-1] = 1.0                                     # a collapse in the last quarter...
    s2 = R.tesla_signal(px, t2)
    assert [e for e in s2["events"] if e["date"] < "2026-10-02"] == [e for e in s["events"] if e["date"] < "2026-10-02"]   # ...changes nothing before it is published
    assert s2["events"][-1]["votes"]["Deliveries"] == -1


def test_robotaxi_tesla_signal_backtest():
    from app.topics import robotaxi as R
    qs, t = _tesla_quarters()
    days = pd.bdate_range("2023-01-01", "2026-10-20")
    px = pd.Series(100 * 1.001 ** np.arange(len(days)), index=days)     # rises 0.1% a day
    s = R.tesla_signal(px, t)
    st = s["stats"]
    assert st["invested"] > 0.9 and st["switches"] == 1                 # long from the first figures with signal > 0, never out
    first_long = pd.Timestamp(next(e["date"] for e in s["events"] if e["long"]))
    held = px[px.index > first_long]
    assert abs(st["strategy"]["total"] - ((held.iloc[-1] / held.iloc[0]) * (1 - R.COST) * 1.001 - 1)) < 0.01   # in from the next trading day
    assert st["buy_hold"]["max_drawdown"] == 0 and st["hits"] == st["periods"]
    flat = R.tesla_signal(px, {"Deliveries": pd.Series(100.0, index=qs)})
    assert flat["stats"]["invested"] == 0 and flat["stats"]["strategy"]["total"] == 0      # a zero signal stays in cash
    assert R.tesla_signal(px, {}) == {"events": [], "stats": None}


def test_robotaxi_readings(snapdir, monkeypatch):
    from app.topics import robotaxi as R
    monkeypatch.setattr(R, "fetch", lambda url, ttl, **k: SGO)
    monkeypatch.setattr(R, "fetch_json", lambda url, ttl, **k: _yahoo(250, n=1000))
    pay = {n: R.ENDPOINTS[n]() for n in ("rides", "footprint", "safety", "tesla")}
    rows = R.readings(lambda n: pay[n])
    keys = {r["key"]: r for r in rows}
    assert {"waymo_weekly", "cities", "rules_90d", "waymo_per_million", "tsla_vs_200d", "deliveries_yoy", "fundamentals_signal"} <= set(keys)
    assert {r["tab"] for r in rows} == {"rides", "footprint", "safety", "tesla"} and all(r["lean"] in (-1, 0, 1) for r in rows)
    assert keys["waymo_weekly"]["lean"] == 1 and keys["deliveries_yoy"]["lean"] == -1      # 500K after 250K; Q3 2026 below Q3 2025
    assert keys["waymo_per_million"]["note"].endswith("(lower is better)")
    assert R.readings(lambda n: {}) == [] and R.READINGS() is not None


def test_btc_rotation_timeline_and_sector_status():
    from app.topics import btc_cycles as C
    rows = C.rotation_rows()
    assert {r["cycle"] for r in rows} == {1, 2, 3, 4} and all(r["end"] >= r["start"] and r["source"] for r in rows)
    defi = next(r for r in rows if r["sector"] == "DeFi summer")
    assert defi["m_start"] == pytest.approx(0.7, abs=0.2)                       # Jun 2020, a month after the May 2020 halving
    import json as _json
    cfg = _json.loads(C.SECTOR_STATUS.read_text())
    tickers = {c["ticker"] for c in C.coins_list()}
    assert all(3 <= len(s["reps"]) <= 5 and set(s["reps"]) <= tickers for s in cfg["sectors"] if s["reps"]) and len(cfg["sectors"]) == 8
    coin = lambda t, rel, rsi_, hi: {"ticker": t, "name": t, "kpi": {"vs_btc_90d": rel, "rsi_vs_btc": rsi_, "from_high": hi}}
    coins = ([coin(t, 0.8, 75, -0.05) for t in ("HYPE", "AAVE", "JUP")] + [coin(t, -0.3, 40, -0.5) for t in ("ENA", "TRX", "SKY")] +
             [coin(t, 0.2, 60, -0.1) for t in ("ONDO", "LINK", "SYRUP")] + [coin(t, -0.05, 45, -0.8) for t in ("ZEC", "XMR", "DASH")] +
             [coin(t, 0.0, 50, -0.4) for t in ("SOL", "SUI", "TON")])
    day = 86400 * 7
    metrics = {"stablecoins": [[i * day, 100 + i] for i in range(20)], "defi_tvl": [[i * day, 100.0] for i in range(20)]}
    st = {s["rank"]: s for s in C.sector_status(coins, metrics, {})}
    assert st[1]["status"] == "Overvalued" and st[3]["status"] == "Priced in" and st[2]["status"] == "Undervalued"
    assert st[7]["status"] == "Awaiting rotation" and st[6]["status"] == "Neutral" and st[4]["reps"] == [] and st[4]["no_token"]
    assert st[7]["past"] and all(p["cycle"] in (1, 2, 4) for p in st[7]["past"])


def test_btc_readings(snapdir, monkeypatch):
    from app.topics import btc_cycles as C, _daily
    monkeypatch.setattr(C, "ENDPOINTS", {**C.ENDPOINTS,
        "cycles": lambda: {"now": {"vs_ma200": 0.1, "days_since_halving": 400}},
        "signals": lambda: {"status": [{"signal": "Stablecoin supply rising", "state": "firing"}, {"signal": "Volume", "state": "not yet"}]},
        "coins": lambda: {"coins": [{"ticker": t, "kpi": {"rsi_vs_btc": r, "vs_btc_90d": v}} for t, r, v in (("A", 60, 0.2), ("B", 40, -0.1), ("C", 55, 0.0))]},
        "rotation": lambda: {"status": [{"rank": 1, "sector": "DeFi", "status": "Undervalued"}]}})
    monkeypatch.setattr(C._flows, "ENDPOINTS", {"etf": lambda: {"daily_usd_m": [[0, 10.0], [1, -5.0], [2, 20.0]]},
        "mstr": lambda: {"kpi": {"mnav": 0.9}, "held": [[0, 100.0], [1, 110.0]], "strategies": {"checklist": [{"rule": "BTC trend", "state": "clear"}]}}})
    r = {x["key"]: x for x in _daily._clean(C.READINGS())}
    assert r["btc_vs_200d"]["lean"] == 1 and r["halving_clock"]["lean"] == 1 and r["etf_5d"]["value"] == 25 and r["mnav"]["lean"] == -1
    assert r["mstr_bought_week"]["value"] == 10 and r["rsi_breadth"]["value"] == "2/3" and r["strongest"]["value"] == "A" and r["weakest"]["value"] == "B"
    assert r["sector:1"]["lean"] == 1 and r["sig:Stablecoin supply rising"]["lean"] == 1 and {x["tab"] for x in r.values()} >= {"cycles", "signals", "etf", "mstr", "candidates", "sectors"}


def test_btc_fundamentals_parse_and_factors(snapdir, monkeypatch):
    from app.topics import btc_cycles as _C
    monkeypatch.setattr(_C, "FUND_DIR", snapdir / "btc_fundamentals")          # per-coin fundamentals files stay in the test's folder
    from app.topics import btc_cycles as C
    day = 86400
    t0 = int(pd.Timestamp("2025-10-20").timestamp())
    tvl = C.parse_tvl({"tvl": [{"date": t0 + i * day, "totalLiquidityUSD": 1e9 + i * 1e6} for i in range(400)]})
    chain = C.parse_tvl([{"date": t0 + i * day, "tvl": 5e8} for i in range(10)])
    fees = C.parse_fees({"totalDataChart": [[t0 + i * day, 1e5] for i in range(400)]})
    assert len(tvl) == 400 and tvl.iloc[-1] == pytest.approx(1.399e9) and len(chain) == 10 and fees.sum() == pytest.approx(4e7)
    em = {"documentedData": {"data": [{"label": "Team", "data": [{"timestamp": t0 + i * 30 * day, "unlocked": i * 10.0} for i in range(40)]},
                                      {"label": "Airdrop", "data": [{"timestamp": t0 + i * 30 * day, "unlocked": 500.0} for i in range(40)]}]}}
    sched = C.parse_emissions(em)
    assert sched.iloc[0] == 500 and sched.iloc[-1] == 890
    with pytest.raises(ValueError):
        C.parse_emissions({"documentedData": {"data": []}})
    # factors: price-to-fees now 10x vs a 1-year median of 40x -> valuation sqrt(4) = 2, clamped to 1.5; schedule doubles supply by T
    idx = pd.date_range("2025-10-27", periods=365, freq="D")
    px = pd.Series(1.0, index=idx)
    mc = pd.Series(np.r_[np.full(300, 4e7 * 40 / 1), np.full(65, 4e7 * 10)][:365] / 12.1666 * 1.0, index=idx)
    fd = {"fees": [[int(t.timestamp()), 1e5 * 365 / 365] for t in idx], "tvl": [[int(t.timestamp()), 1e9] for t in idx],
          "schedule": [[int((idx[-1] + pd.Timedelta(days=d)).timestamp()), 1000.0 + max(0, d) * 1000.0 / 800] for d in range(-60, 900, 7)],
          "supply": {"circulating_supply": 1000, "total_supply": 2000, "max_supply": 2000}}
    F = C.fund_factors(fd, mc / 1000, mc, ["2027-12-31"])             # price = market cap / 1,000 coins, so 1,000 circulating against 2,000 max
    assert F["factors"]["valuation_basis"] == "price-to-fees" and F["factors"]["valuation"] == pytest.approx(1.5)
    assert F["factors"]["dilution_basis"].startswith("unlock schedule") and 0.4 < F["factors"]["dilution"]["2027-12-31"] < 0.7
    assert F["kpi"]["p_fees"] < F["kpi"]["p_fees_median"] and F["kpi"]["unlock_12m"] > 0.3 and "fees_30d" in F["series"]
    # no fees, no TVL, no schedule, flat supply: both factors 1
    G = C.fund_factors({}, px, pd.Series(1e6, index=idx), ["2027-12-31"])
    assert G["factors"]["valuation"] == 1.0 and G["factors"]["dilution"].get("2027-12-31", 1.0) == 1.0
    # the coin payload applies them: adjusted = beta-only x dilution x valuation
    import json as _json
    charts = _chart(mult=2.0)
    monkeypatch.setattr(B, "_download", lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]))
    monkeypatch.setattr(C, "PACE", 0)
    C.fill_coins()
    C.FUND_DIR.mkdir(parents=True, exist_ok=True)
    (C.FUND_DIR / "HYPE.json").write_text(_json.dumps({"schedule": [[int((pd.Timestamp.now() + pd.Timedelta(days=d)).timestamp()), 1e8 + max(0, d) * 1e8 / 365] for d in range(-400, 1200, 7)]}))
    f = C._coin_now("HYPE")
    p0 = f["projection"][0]
    assert p0["dilution"] < 1 and p0["base"] == pytest.approx(p0["base_beta_only"] * p0["dilution"] * p0["valuation"], rel=1e-3)
    assert f["kpi"]["base_2027"] == p0["base"] and f["fundamentals"]["factors"]["dilution_basis"].startswith("unlock schedule")


def test_btc_dilution_needs_a_cap():
    from app.topics import btc_cycles as C
    idx = pd.date_range("2025-10-27", periods=365, freq="D")
    px = pd.Series(1.0, index=idx)
    mc = pd.Series(np.linspace(5e9, 1e10, 365), index=idx)                  # supply doubled in a year
    F = C.fund_factors({}, px, mc, ["2028-12-31"])
    assert F["factors"]["dilution"] == {} and F["factors"]["dilution_basis"] is None          # no cap known: no factor
    G = C.fund_factors({"supply": {"max_supply": 1.2e10}}, px, mc, ["2028-12-31"])
    assert G["factors"]["dilution"]["2028-12-31"] == pytest.approx(1e10 / 1.2e10, rel=1e-3)   # growth capped at max supply


def test_btc_schedule_adds_tokens_to_circulating_supply():
    from app.topics import btc_cycles as C
    idx = pd.date_range("2025-10-27", periods=365, freq="D")
    px = pd.Series(1.0, index=idx)
    mc = pd.Series(13.4e9, index=idx)                                        # 13.4bn circulating (CoinGecko)
    sched = [[int((idx[-1] + pd.Timedelta(days=d)).timestamp()), 6e9 + max(0, d) * 3e9 / 365] for d in range(-60, 1200, 7)]   # +3bn a year
    F = C.fund_factors({"schedule": sched, "supply": {"max_supply": 15e9}}, px, mc, ["2027-12-31", "2028-12-31"])
    assert F["kpi"]["unlock_12m"] == pytest.approx(1.6 / 13.4, rel=0.02)            # capped at 15bn: +1.6bn, not +3bn or +50%
    assert F["factors"]["dilution"]["2028-12-31"] == pytest.approx(13.4 / 15, rel=1e-3)


def test_btc_sector_leaders_and_case_fields(snapdir, monkeypatch):
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "FUND_DIR", snapdir / "btc_fundamentals")
    import json as _json
    charts = _chart(mult=2.0)
    markets = [{"id": "ethereum", "symbol": "eth", "name": "Ethereum", "market_cap": 4e11}, {"id": "uniswap", "symbol": "uni", "name": "Uniswap", "market_cap": 1}]
    def dl(url, *a, **k):
        if "coins/markets" in url:
            assert "ethereum" in url and "uniswap" in url
            return _json.dumps(markets)
        return _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"])
    monkeypatch.setattr(B, "_download", dl)
    monkeypatch.setattr(C, "PACE", 0)
    C.fill_coins()
    k = C._coins_now()
    L = k["leaders"]
    assert L[6]["symbol"] == "ETH" and L[6]["candidate"] is False and L[6]["market_cap"] == 4e11       # a non-candidate leads L1s
    assert L[1]["candidate"] is True                                     # Uniswap's tiny cap loses to the candidates
    K = next(c for c in k["coins"] if c["ticker"] == "SOL")["kpi"]
    assert K["bear_2027"] < K["base_2027"] < K["bull_2027"] and K["bear_2028"] < K["base_2028"] < K["bull_2028"] and K["mcap_base_2028"] > 0


def test_btc_fundamentals_without_defillama_fees(snapdir, monkeypatch):
    """Babylon: TVL from /protocol/babylon-protocol; DefiLlama has no fees for it (400), which is recorded on the coin, not as a failing source."""
    import json as _json
    import requests
    from app.topics import btc_cycles as C
    monkeypatch.setattr(C, "FUND_DIR", snapdir / "btc_fundamentals")
    monkeypatch.setattr(C, "PACE", 0)
    B.HEALTH.clear()
    c = next(c for c in C.coins_list() if c["ticker"] == "BABY")
    assert c["defillama_slug"] == "babylon-protocol" and c["coingecko_id"] == "babylon" and "verify id" not in c["note"]
    days = pd.date_range(end="2026-10-30", periods=500)
    tvl = {"tvl": [{"date": int(d.timestamp()), "totalLiquidityUSD": 3e9 + i} for i, d in enumerate(days)]}

    class R400:
        status_code, headers = 400, {}

    def dl(url, *a, **k):
        if "summary/fees/" in url or "emissions" in url:
            raise requests.HTTPError("400 Client Error", response=R400())
        if "/protocol/babylon-protocol" in url:
            return _json.dumps(tvl)
        if "coins/babylon" in url:
            return _json.dumps({"market_data": {"circulating_supply": 2e9, "total_supply": 1e10, "max_supply": None}, "categories": ["Bitcoin Ecosystem"], "description": {"en": "x" * 600}})
        raise AssertionError(url)
    monkeypatch.setattr(B, "_download", dl)
    out = C.fill_fundamentals(c)
    assert len(out["tvl"]) > 300 and "fees" not in out and out["errors"]["fees"] == "none on DefiLlama" and out["supply"]["circulating_supply"] == 2e9
    assert not [u for u in B.HEALTH if "summary/fees" in u] and C.LLAMA_PROTO.format(slug="babylon-protocol") in B.HEALTH
    B.HEALTH.clear()


def test_btc_sector_check_against_coingecko():
    from app.topics import btc_cycles as C
    assert C.sector_check(3, []) is None
    ok = C.sector_check(3, ["Oracle", "Real World Assets (RWA)", "Ethereum Ecosystem"])
    assert ok["ok"] and ok["matched"] == ["Real World Assets (RWA)"] and "Ethereum Ecosystem" not in ok["categories"]
    assert C.sector_check(3, ["Oracle", "Infrastructure"])["ok"] is False
    assert C.sector_check(6, ["Layer 1 (L1)", "Smart Contract Platform"])["ok"]


def test_btc_classification_covers_every_coin():
    import json as _json
    from app.topics import btc_cycles as C
    cl = C.classification()
    assert {c["ticker"] for c in C.coins_list()} <= set(cl) and all(v["doc_sector"] in ("primary", "secondary") and v["sources"] for v in cl.values())
    assert cl["LINK"]["doc_sector"] == "secondary" and "NEAR" in _json.loads(C.SECTOR_STATUS.read_text())["sectors"][5]["reps"]


def test_dashboard_page_carries_its_own_link_preview(monkeypatch):
    """GET /<slug> puts the dashboard's title and blurb into <title>, the description and Open Graph tags (escaped);
    a private dashboard keeps the generic shell."""
    import asyncio
    import html
    from aiohttp.test_utils import TestClient, TestServer
    from app.server import make_app
    t = topics.REGISTRY["housing"]
    monkeypatch.setitem(topics.REGISTRY, "zz-og", topics.Topic("zz-og", 'Tom & "Jerry"', "Cats <b>vs</b> mice.", "zz_og", (("a", "A"),)))
    monkeypatch.setitem(topics.REGISTRY, "zz-og-private", topics.Topic("zz-og-private", "Secret odds", "hidden", "zz_og_p", (("a", "A"),), private=True))

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            r = await c.get("/housing")
            return r.status, r.content_type, await r.text(), await (await c.get("/zz-og")).text(), await (await c.get("/zz-og-private")).text(), await (await c.get("/")).text()
    status, ctype, housing, og, private, index = asyncio.run(go())
    assert status == 200 and ctype == "text/html"
    assert f'<meta property="og:title" content="{html.escape(t.title)} · Dashboards">' in housing
    assert housing.count('name="description"') == 1 and "lightweight-charts" in housing           # the rest of the shell is untouched
    assert "<title>Tom &amp; &quot;Jerry&quot; · Dashboards</title>" in og and 'content="Cats &lt;b&gt;vs&lt;/b&gt; mice."' in og
    assert "Secret odds" not in private and "og:title" not in private and "<title>Dashboard</title>" in private
    assert '<meta property="og:title" content="Dashboards">' in index


def test_method_tab_takes_calculation_and_caveat_sections_from_the_readme(monkeypatch, tmp_path):
    """topics.method: the README's calculation and caveat sections, each to the next heading of its level, titled with their part
    heading where there is one; upkeep sections are left out. meta says whether the page gets a Method tab; /api/<slug>/method serves it."""
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app import config
    from app.server import make_app
    (tmp_path / "zz-m").mkdir()
    (tmp_path / "zz-m" / "README.md").write_text(
        "# Title (`/zz-m`)\n\nIntro.\n\n## What it shows\n\nCards.\n\n## How it is calculated\n\n- **Ratio**: a / b.\n\n"
        "### Detail\n\nKept with its section.\n\n```\n# a shell comment, not a heading\n```\n\n## Keeping it up to date\n\nNothing.\n\n# Second half\n\n### Known gaps\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n### Checking it\n\npytest\n\n## The buy zone rule (`app/topics/x.py`, `f`)\n\nBuy low.\n")
    (tmp_path / "zz-none").mkdir()
    (tmp_path / "zz-none" / "README.md").write_text("# T\n\n## Keeping it up to date\n\nNothing.\n")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    s = topics.method("zz-m")["sections"]
    assert [x["title"] for x in s] == ["How it is calculated", "Second half · Known gaps", "Second half · The buy zone rule"]
    assert "### Detail" in s[0]["markdown"] and "# a shell comment" in s[0]["markdown"] and "Nothing" not in s[0]["markdown"]
    assert s[1]["markdown"].startswith("| a | b |") and "pytest" not in s[1]["markdown"] and s[2]["markdown"] == "Buy low."
    assert topics.method("zz-none")["sections"] == [] and topics.method("zz-missing")["sections"] == []
    monkeypatch.setitem(topics.REGISTRY, "zz-m", topics.Topic("zz-m", "M", "b", "housing", (("a", "A"),)))
    monkeypatch.setitem(topics.REGISTRY, "zz-none", topics.Topic("zz-none", "N", "b", "housing", (("a", "A"),)))
    assert topics.meta("zz-m")["method"] is True and topics.meta("zz-none")["method"] is False

    async def go():
        async with TestClient(TestServer(make_app())) as c:
            r = await c.get("/api/zz-m/method")
            return r.status, await r.json()
    status, body = asyncio.run(go())
    assert status == 200 and body["sections"][0]["title"] == "How it is calculated"


def test_every_dashboard_leaves_about_free_for_the_method_tab():
    for slug, t in topics.REGISTRY.items():
        assert "about" not in dict(t.tabs) and "method" not in topics.endpoints(slug), slug


def test_btc_zones_models_and_thresholds():
    from app.topics import btc_cycles as C
    idx = pd.date_range("2019-01-01", periods=2200, freq="D")
    flat = pd.Series(100.0, index=idx)
    z = C.btc_zones(flat, [{"date": "2024-06-01", "label": "Peak"}, {"date": "2025-06-01", "label": "Low"}])
    by = {m["key"]: m for m in z["models"]}
    assert by["mayer"]["now"] == 1.0 and by["x2y"]["now"] == 1.0 and by["w200"]["now"] == 1.0 and by["pi_top"]["now"] == 0.5
    assert all(m["zone"] in ("neither", None) for m in z["models"] if m["buy"] or m["sell"]) and z["n_buy"] == 0 and z["n_sell"] == 0 and z["n_models"] == 6
    assert by["rsi_w"]["zone"] is None                                        # a flat series has no RSI (0 / 0)
    assert by["mayer"]["at"]["2024-06-01"] == 1.0 and [m["date"] for m in z["markers"]] == ["2024-06-01", "2025-06-01"]
    # a 60% drop over the last 60 days: below 0.8 x 200-day, below the 2-year MA, below the 200-week MA, RSI washed out
    crash = flat.copy(); crash.iloc[-60:] = np.linspace(100, 40, 60)
    z2 = C.btc_zones(crash, [])
    b2 = {m["key"]: m for m in z2["models"]}
    assert b2["mayer"]["zone"] == "buy" and b2["x2y"]["zone"] == "buy" and b2["w200"]["zone"] == "buy" and b2["rsi_w"]["zone"] == "buy" and z2["trend"] == "below" and z2["n_buy"] >= 4
    # an 8x run in 120 days: Mayer above 2.4, price above 5 x the 2-year MA, the Pi Cycle 111-day MA above 2 x 350-day
    run = flat.copy(); run.iloc[-120:] = np.linspace(100, 800, 120)
    b3 = {m["key"]: m for m in C.btc_zones(run, [])["models"]}
    assert b3["mayer"]["zone"] == "sell" and b3["x2y"]["zone"] == "sell" and b3["pi_top"]["zone"] == "sell" and b3["rsi_w"]["zone"] in ("sell", None)
    assert set(C.btc_zones(flat, [])["lines"]) == {"mayer_buy", "mayer_sell", "ma2y", "ma2y_x5", "ma200w"}


def test_btc_sector_supply_overhang_holds_undervalued_at_neutral():
    from app.topics import btc_cycles as C
    coin = lambda t, flt, unl: {"ticker": t, "name": t, "kpi": {"vs_btc_90d": -0.3, "rsi_vs_btc": 40, "from_high": -0.5, "float": flt, "unlock_12m": unl}}
    day = 86400 * 7
    metrics = {"stablecoins": [[i * day, 100 + i] for i in range(20)]}        # usage up: the stablecoin sector reads undervalued on usage
    light = {s["rank"]: s for s in C.sector_status([coin(t, 0.9, 0.05) for t in ("ENA", "TRX", "SKY")], metrics, {})}
    heavy = {s["rank"]: s for s in C.sector_status([coin(t, 0.15, 0.3) for t in ("ENA", "TRX", "SKY")], metrics, {})}
    some = {s["rank"]: s for s in C.sector_status([coin(t, 0.4, 0.12) for t in ("ENA", "TRX", "SKY")], metrics, {})}
    assert light[2]["status"] == "Undervalued" and light[2]["overhang"] == "light"
    assert heavy[2]["status"] == "Neutral" and heavy[2]["overhang"] == "heavy" and heavy[2]["overhang_note"]
    assert some[2]["status"] == "Undervalued" and some[2]["overhang"] == "some" and some[2]["float"] == 0.4
    assert light[7]["overhang"] is None                                        # no supply data at all
