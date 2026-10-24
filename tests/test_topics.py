"""Routes, registry, the fetch-with-snapshot fallback, hand-entered series, and every dashboard's payloads on fixtures (no network)."""
import json
import time

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


def test_registry_is_complete():
    assert set(topics.REGISTRY) == {"housing", "ai-adoption", "robotaxi", "ai-jobs"}
    for slug, t in topics.REGISTRY.items():
        m = topics.meta(slug)
        eps = topics.endpoints(slug)
        assert m["title"] and m["tabs"] and m["sources"]
        assert set(t.slow) <= set(eps), slug
        assert {k for k, _ in t.tabs} <= set(eps), f"{slug}: every tab needs an endpoint of the same name"
        js = (B.MANUAL_DIR.parent / "app/static/topics" / f"{slug}.js").read_text()
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
HPI = "Period,Average price All property types,Index All property types,Percentage change (yearly) All property types,Sales volume,Average price Detached houses,Average price Semi-detached houses,Average price Terraced houses,Average price Flats and maisonettes\n" + \
      "\n".join(f"{2010 + i // 12}-{i % 12 + 1:02d},{300000 + i * 1000},{100 + i},{2.0},{8000 - i},{600000},{400000},{350000},{250000}" for i in range(180))
ONS = lambda v0: {"months": [{"date": f"{2010 + i // 12} {m}", "value": str(v0 + i)} for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"] * 15)]}
BOE = "DATE,IUDBEDR\n05 Mar 2009,0.5\n02 Nov 2017,0.75\n16 Dec 2021,0.25\n03 Aug 2023,5.25\n01 Aug 2024,5.0\n"


def test_housing_payloads(snapdir, monkeypatch):
    from app.topics import housing as H
    monkeypatch.setattr(H, "fetch", lambda url, ttl, **k: HPI if "ukhpi" in url else BOE)
    monkeypatch.setattr(H, "fetch_json", lambda url, ttl, **k: ONS(100) if "L522" in url else ONS(500))
    p, m, a = H._prices_now(), H._market_now(), H._afford_now()
    for d in (p, m, a):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert p["now"]["avg"] == 479000 and p["london_real"][-1][1] == 479000 and p["london_real"][0][1] > 300000   # real terms: past prices inflated
    assert len(m["by_type"]) == 4 and m["now"]["types"]["Detached"] == 600000 and m["now"]["volume_12m"] < m["now"]["volume_12m_prev"]
    assert a["now"]["bank_rate"] == 5.0 and 5 < a["now"]["price_to_earnings"] < 20 and a["now"]["mortgage"] > 1000
    assert a["bank_rate"][0][1] == 0.5 and all(t % 86400 == 0 for t, _ in a["bank_rate"])     # one point per month start


def test_housing_parsers_cope_with_layout_drift():
    from app.topics.housing import parse_boe, parse_hpi, parse_ons
    d = parse_hpi("Period,Average price All property types,Sales volume\n2020-01,500000,100\n2020-02,510000,110\n2021-02,520000,90\n")
    assert d["pc_ann"].notna().sum() == 1 and d["avg_detached"].isna().all()             # yearly change computed when the column is missing
    assert parse_ons({"months": [{"date": "2024 JAN", "value": "1.5"}, {"date": "bad", "value": "2"}]}).tolist() == [1.5]
    assert parse_boe(" DATE , IUDBEDR \n01 Feb 2024,5.25\n").iloc[0] == 5.25


IND = "date,jobcountry,indeed_job_postings_index,variable,display_name\n" + "\n".join(
    f"{d.date()},US,{100 + i * (1 if n == 'Legal' else -1) * 0.1:.2f},{v},{n}" for i, d in enumerate(pd.date_range("2020-02-01", periods=800))
    for n in ("Software Development", "Data & Analytics", "Legal", "Banking & Finance", "Accounting", "Insurance") for v in ("total postings", "new postings"))
AGG = "date,jobcountry,indeed_job_postings_index_SA,indeed_job_postings_index_NSA,variable\n" + "\n".join(f"{d.date()},US,{100 + i * .01:.2f},100,total postings" for i, d in enumerate(pd.date_range("2020-02-01", periods=800)))
AIS = "date,jobcountry,AI_share_postings\n" + "\n".join(f"{d.date()},{cc},{2 + i * .003 * (2 if cc == 'US' else 1):.3f}" for i, d in enumerate(pd.date_range("2019-01-01", periods=2800)) for cc in ("US", "GB", "DE"))
FRED = "observation_date,CES6054110001\n" + "\n".join(f"{d.date()},{1100 + i * .5:.1f}" for i, d in enumerate(pd.date_range("2010-01-01", periods=190, freq="MS")))


def test_ai_jobs_payloads(snapdir, monkeypatch):
    from app.topics import ai_jobs as J
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS if "ai-tracker" in url else FRED if "fred" in url else AGG if "aggregate" in url else IND)
    o, h, r = J._openings_now(), J._headcount_now(), J._ratio_now()
    for d in (o, h, r):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert set(o["US"]["sectors"]) == set(J.SECTORS["ai"] + J.SECTORS["professions"]) and o["US"]["latest"]["Legal"]["index"] > 100 > o["US"]["latest"]["Software Development"]["index"]
    assert o["ai_share_latest"]["US"]["share"] > o["ai_share_latest"]["US"]["year_ago"]
    assert set(h["US"]["levels"]) == set(J.US_SERIES) and h["US"]["latest"]["Legal services"]["since_2020"] > 0 and h["as_of"]
    assert r["US"]["ai_over_professions"][-1][1] < 1 < r["US"]["ai_over_professions"][0][1] + 0.01
    assert len(json.dumps(o)) < 400_000                      # weekly / monthly resampling keeps the page light


def test_ai_adoption_payloads(snapdir, monkeypatch):
    from app.topics import ai_adoption as A, ai_jobs as J
    monkeypatch.setattr(A, "fetch", lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("blocked")))    # BTOS workbook unreachable: hand-entered points carry the chart
    monkeypatch.setattr(J, "fetch", lambda url, ttl, **k: AIS)
    f, u, g, s = A._firms_now(), A._users_now(), A._agents_now(), A._skills_now()
    for d in (f, u, g, s):
        B.json_safe(d)
        assert not [k for k in d if k.endswith("_error")], d
    assert f["btos_us"] and f["now"]["btos"] and f["cited"]
    assert u["rows"][0]["date"] >= u["rows"][-1]["date"] and any(v for v in u["series"].values())
    assert g["rows"] and g["by_year"] and set(s["share"]) == {"US", "GB", "DE"}


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
            assert [d["slug"] for d in j["dashboards"]] == list(topics.REGISTRY)
            page = await c.get("/housing")
            assert page.status == 200 and "window.TOPIC.VIEWS" in await page.text()
            js = await c.get("/housing.js")
            assert js.status == 200 and "window.TOPIC" in await js.text()
            assert (await c.get("/nope")).status == 404 and (await c.get("/nope.js")).status == 404
            assert (await c.get("/..%2Fserver.py")).status == 404
            meta = await (await c.get("/api/housing/meta")).json()
            assert meta["title"] == "London Housing Index" and meta["tabs"][0] == ["prices", "Prices"] and meta["sources"]
            assert (await c.get("/api/housing/nope")).status == 404 and (await c.get("/api/nope/meta")).status == 404
            r = await c.get("/api/robotaxi/safety")
            assert r.status == 200 and (await r.json())["reports"]["n"] == 120
    asyncio.run(go())
