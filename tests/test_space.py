"""Space Economy on fixtures (no network): the GCAT, CelesTrak and Nasdaq parsers, every payload, the checklist, READINGS and the seed
files. smoke_patch() points the module's fetchers at the same fixtures for scripts/smoke.py."""
import pandas as pd
import pytest

from app.topics import _base as B
from app.topics import space as M

# ------------------------------------------------------------------ fixtures
AGENCIES = (("SPX", "US", 0.0), ("CASC", "CN", 0.0), ("RKA", "RU", 0.0), ("ARIANE", "F", 0.0), ("RLABU", "US", 0.0), ("LANDSPACE", "CN", 0.0),
            ("GALACT", "CN", 0.0), ("ISRO", "IN", 0.0), ("VORB", "US", 0.0))


def orgs_tsv():
    head = "#Code\tUCode\tStateCode\tType\tClass\tTStart\tTStop\tShortName\tName"
    names = {"SPX": "SpaceX", "CASC": "CASC", "RKA": "Roscosmos", "ARIANE": "Arianespace", "RLABU": "Rocket Lab", "LANDSPACE": "LandSpace",
             "GALACT": "Galactic Energy", "ISRO": "ISRO", "VORB": "Virgin Orbit"}
    body = [f"{c}\t{c}\t{s}\tLA\tB\t1990\t*\t{names[c]}\t{names[c]} Inc" for c, s, _ in AGENCIES]
    return "\n".join([head, "# Updated 2026 Oct 20", *body]) + "\n"


def per_year(agency: str, y: int) -> int:
    if agency == "SPX":
        return 0 if y < 2010 else min(260, 2 + (y - 2010) ** 2)
    if agency == "CASC":
        return 5 + (y - 2000) * 2 if y >= 2000 else 3
    if agency == "RKA":
        return 25 if y < 2015 else 17
    if agency in ("LANDSPACE", "GALACT"):
        return 0 if y < 2020 else 2 + (y - 2020)
    if agency == "RLABU":
        return 0 if y < 2018 else min(20, 3 * (y - 2017))
    if agency == "VORB":
        return 1 if y == 2023 else 0
    return 4


def launch_tsv(until="2026-10-20"):
    head = "#Launch_Tag\tLaunch_JD\tLaunch_Date\tLV_Type\tVariant\tFlight_ID\tFlight\tMission\tFlightCode\tPlatform\tLaunch_Site\tLaunch_Pad\tAgency\tLaunch_Code\tGroup\tCategory"
    body, end = [], pd.Timestamp(until)
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for y in range(1957, end.year + 1):
        for a, _, _ in AGENCIES:
            n = per_year(a, y)
            for i in range(n):
                t = pd.Timestamp(y, 1, 1) + pd.Timedelta(days=int(365 * (i + 0.5) / max(n, 1)))
                if t > end:
                    continue
                code = "OF" if (i % 17 == 3) else "OS"
                body.append(f"{y}-{i:03d}\t0\t{t.year} {mon[t.month - 1]} {t.day:2d} 1200:00\t{a}-LV\t\t\t\t\t\t\tSITE\tPAD\t{a}\t{code}\t-\t-")
            if a == "SPX" and y == 2020:
                body.append(f"{y}-S99\t0\t{y} Mar  1 1200\tSuborb\t\t\t\t\t\t\tSITE\tPAD\t{a}\tSS\t-\t-")       # suborbital: dropped
    return "\n".join([head, "#", *body]) + "\n"


def satcat_tsv():
    head = "#JCAT\tSatcat\tLaunch_Tag\tPiece\tType\tName\tPLName\tLDate\tParent\tSDate\tPrimary\tDDate\tStatus\tDest\tOwner\tState\tManufacturer\tBus\tMotor\tMass\tMassFlag"
    body = []
    for y in range(1957, 2027):
        for i in range(10):
            star = y >= 2019 and i < 6
            name = f"Starlink-{y}{i}" if star else f"Sat {y}-{i}"
            mass = (300 + 100 * (y - 2019)) * (5 if star else 1) if y >= 2019 else 2000
            body.append(f"S{y}{i}\t{y}{i}\t{y}-001\tA\tP\t{name}\t{name}\t{y} Mar  1\t-\t-\t-\t-\tO\tLEO\tX\tUS\tX\tX\tX\t{mass}\t")
        body.append(f"R{y}\t\t{y}-001\tB\tR2\tF9 Stage 2\t-\t{y} Mar  1\t-\t-\t-\t-\tR\tLEO\tX\tUS\tX\tX\tX\t4000\t")       # a rocket body: not a payload
    body.append("S99\t\t-\t\tP\tMystery\t-\t-\t-\t-\t-\t-\tO\tLEO\tX\tUS\tX\tX\tX\t-\t")                                    # no date or mass
    return "\n".join([head, "# Updated", *body]) + "\n"


def celestrak_csv():
    head = "OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE"
    rows, n = [], 0
    days = pd.date_range("2019-05-24", "2026-10-15", periods=9000)
    for t in days:
        n += 1
        rows.append(f"STARLINK-{n},2019-029A,{40000 + n},PAY,+,US,{t.date()},AFETR,,95,53,550,540,,,EA,ORB")
    for i, t in enumerate(pd.date_range("2019-02-27", "2023-03-25", periods=630)):
        rows.append(f"ONEWEB-{i:04d},2019-010A,{60000 + i},PAY,+,UK,{t.date()},TYMSC,,109,87,1200,1200,,,EA,ORB")
    for i, t in enumerate(pd.date_range("2024-08-06", "2026-09-01", periods=300)):
        rows.append(f"QIANFAN-{i},2024-140A,{70000 + i},PAY,+,PRC,{t.date()},TSC,,108,89,800,800,,,EA,ORB")
    for i, t in enumerate(pd.date_range("2000-01-01", "2026-06-01", periods=2500)):
        owner = ("US", "PRC", "CIS", "JPN", "IND", "ESA")[i % 6]
        rows.append(f"SAT {i},2000-001A,{80000 + i},PAY,{'+PBSX'[i % 5]},{owner},{t.date()},X,,95,53,550,540,,,EA,ORB")
    rows.append("OLD SAT,1960-001A,1,PAY,-,US,1960-01-01,X,,95,53,550,540,,,EA,ORB")                                   # dead
    rows.append("STARLINK-DECAYED,2019-029A,2,PAY,D,US,2019-05-24,X,2021-01-01,95,53,550,540,,,EA,ORB")                  # decayed
    rows.append("CZ-6A R/B,2024-140B,3,R/B,+,PRC,2024-08-06,X,,95,53,550,540,,,EA,ORB")                                 # a rocket body
    return "\n".join([head, *rows]) + "\n"


def nasdaq_json(sym):
    days = pd.bdate_range("2021-01-04", "2026-10-23")
    g = {"RKLB": 0.0012, "ASTS": 0.0010, "IRDM": 0.0001, "PL": 0.0004, "UFO": 0.0003, "SPY": 0.0004}[sym]
    rows = [{"date": t.strftime("%m/%d/%Y"), "close": f"${20 * (1 + g) ** i * (1 + 0.1 * ((i // 300) % 2)):,.2f}", "volume": "1,000"} for i, t in enumerate(days)]
    return {"data": {"symbol": sym, "tradesTable": {"rows": list(reversed(rows))}}, "status": {"rCode": 200}}


def fake_fetch(url, ttl=0, **k):
    if url == M.GCAT_LAUNCH:
        return launch_tsv()
    if url == M.GCAT_ORGS:
        return orgs_tsv()
    if url == M.GCAT_SATCAT:
        return satcat_tsv()
    if url == M.CELESTRAK:
        return celestrak_csv()
    raise ConnectionError(url)


def fake_fetch_json(url, ttl=0, **k):
    if "nasdaq" in url:
        return nasdaq_json(url.split("/quote/")[1].split("/")[0])
    raise ConnectionError(url)


def smoke_patch():
    """Used by scripts/smoke.py: every source of this dashboard answers from the fixtures above."""
    M.fetch = fake_fetch
    M.fetch_json = fake_fetch_json


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    from app import cache
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(M, "_now", lambda: pd.Timestamp("2026-10-26"))
    cache._cache.clear()
    B.STALE.clear()
    yield
    cache._cache.clear()
    B.STALE.clear()


# ------------------------------------------------------------------ tests
def test_topic_is_registered():
    from app import topics
    t = topics.REGISTRY["space"]
    assert t.module == "space" and t.title == "Space Economy" and [k for k, _ in t.tabs] == ["launches", "cost", "satellites", "industry", "ukhk"]
    assert topics.meta("space")["sources"]


def test_gcat_parsers():
    assert M.gcat_date("2024 Jan  5 0412:34") == pd.Timestamp("2024-01-05")
    assert M.gcat_date("1957 Oct 4") == pd.Timestamp("1957-10-04") and M.gcat_date("2025") == pd.Timestamp("2025-01-01")
    assert M.gcat_date("2025 Foo 3") is None and M.gcat_date("-") is None
    o = M.parse_orgs(orgs_tsv())
    assert o["SPX"] == ("SpaceX", "US") and o["ARIANE"][1] == "F"
    L = M.parse_launches(launch_tsv(), o)
    assert not (L["vehicle"] == "Suborb").any()
    assert set(L["country"]) == {"US", "China", "Russia", "Europe", "India"}
    assert int((L["year"] == 2024).sum()) == sum(per_year(a, 2024) for a, _, _ in AGENCIES)
    assert L.loc[L["agency"] == "SPX", "provider"].iloc[0] == "SpaceX" and 0.9 < L["success"].mean() < 1
    L2 = M.parse_launches(launch_tsv(), {})                       # orgs.tsv unreachable: the fallback names the big providers
    assert L2.loc[L2["agency"] == "SPX", "country"].iloc[0] == "US" and L2.loc[L2["agency"] == "LANDSPACE", "country"].iloc[0] == "Other"
    m = M.parse_payload_mass(satcat_tsv())
    assert m.loc[2000, "total"] == pytest.approx(20.0) and m.loc[2000, "starlink"] == 0
    assert m.loc[2024, "starlink"] == pytest.approx(6 * 800 * 5 / 1000) and m.loc[2024, "count"] == 10
    with pytest.raises(ValueError):
        M.parse_launches("#Launch_Tag\tLaunch_Date\tAgency\tLaunch_Code\nx\t2020 Jan 1\tSPX\tSS\n", o)


def test_celestrak_parser():
    a = M.parse_celestrak(celestrak_csv())
    assert len(a) == 9000 + 630 + 300 + 2500
    ops = a["operator"].value_counts()
    assert ops["Starlink (SpaceX)"] == 9000 and ops["OneWeb (Eutelsat)"] == 630 and ops["Qianfan (China)"] == 300
    assert M.operator_of("KUIPER-P1", "US") == "Kuiper (Amazon)" and M.operator_of("YAOGAN-30", "PRC") == "China other"
    assert M.operator_of("SOMETHING", "ZZ") == "Other"


def test_frontier():
    rs = M.cost_rows()
    fr = M.frontier(rs)
    assert fr[pd.Timestamp("1980-07-01")] == 5400 and fr[pd.Timestamp("2012-07-01")] == 2600 and fr.iloc[-1] == 1500
    assert all(fr.diff().dropna() <= 0)                           # the cheapest available never gets dearer
    assert M.frontier([]).empty


def test_payloads(mocked):
    for name, fn in M.ENDPOINTS.items():
        if name == "layout":
            continue
        out = B.json_safe(fn())
        assert not [k for k in out if k.endswith("_error")], (name, {k: v for k, v in out.items() if k.endswith("_error")})
    L = M.ENDPOINTS["launches"]()
    K = L["launches"]["kpi"]
    assert K["last_year"] == 2025 and K["last_total"] == sum(per_year(a, 2025) for a, _, _ in AGENCIES)
    assert K["second"]["provider"] == "CASC" and K["r12"] > 0 and K["spacex_share"] > 0.5
    assert set(L["launches"]["countries"]) >= {"US", "China", "Russia", "Europe"} and L["launches"]["providers"][0]["provider"] == "SpaceX"
    assert L["mass"]["kpi"]["year"] == 2025 and L["mass"]["kpi"]["yoy"] > 0
    C = M.ENDPOINTS["cost"]()
    assert C["kpi"]["best"] == 1500 and C["kpi"]["best_vehicle"] == "Falcon Heavy" and any(v["kind"] == "target" for v in C["vehicles"])
    S = M.ENDPOINTS["satellites"]()
    assert S["active"]["kpi"]["starlink"] == 9000 and S["active"]["by_operator"][0]["operator"] == "Starlink (SpaceX)"
    assert S["subs_kpi"]["m"] == 8.0 and S["subs_kpi"]["yoy"] > 0.5
    I = M.ENDPOINTS["industry"]()
    assert set(I["rebased"]) == set(M.TICKERS) and I["stats"]["basket"]["n"] == 4 and I["eco_kpi"]["bn"] == 613
    H = M.ENDPOINTS["ukhk"]()
    assert H["uk_kpi"]["attempts"] == 2 and H["uk_kpi"]["from_uk_soil"] == 1 and H["uk_kpi"]["last"] == "2023-01-09"
    assert "LandSpace" in H["china"]["providers"] and H["china"]["kpi"]["commercial"] == 2 * (2 + 5)
    ans = {c["key"]: c for c in M.ENDPOINTS["answer"]()["checklist"]}
    assert ans["fleet"]["met"] is True and ans["uk"]["met"] is False and ans["cheap"]["met"] is False and ans["second"]["met"] is True


def test_readings(mocked):
    assert M.READINGS() == []                                     # nothing cached yet: nothing to report, nothing fetched
    for name in ("launches", "cost", "satellites", "industry", "ukhk"):
        M.ENDPOINTS[name]()
    rs = M.READINGS()
    assert {r["tab"] for r in rs} == {"launches", "cost", "satellites", "industry", "ukhk"}
    assert all(r["lean"] in (-1, 0, 1) for r in rs) and len({r["key"] for r in rs}) == len(rs)
    lean = {r["key"]: r["lean"] for r in rs}
    assert lean["orbital_12m"] == 1 and lean["china_commercial"] == 1 and lean["starlink_subs"] == 1
    assert lean["cost_10y"] == 1 and lean["uk_last_attempt"] == 0 and lean["starlink_share"] == 0
    assert lean["stocks_vs_spy"] == 1 and lean["economy"] == 1
    B.json_safe(rs)


def test_one_dead_source_blanks_one_chart(mocked, monkeypatch):
    monkeypatch.setattr(M, "fetch", lambda url, ttl=0, **k: (_ for _ in ()).throw(ConnectionError("down")) if url == M.GCAT_SATCAT else fake_fetch(url))
    L = M.ENDPOINTS["launches"]()
    assert L["mass"] is None and L["mass_error"] == "ConnectionError" and L["launches"]["kpi"]["r12"]


def test_seed_files():
    for name in ("cost", "starlink", "economy", "milestones"):
        rs = B.manual_rows("space", name)
        assert rs, name
        for r in rs:
            pd.Timestamp(r["date"])
            assert r["source"].startswith("http"), (name, r)
            assert "verify" in r["note"], (name, r)               # entered from memory: nothing checked against the page yet
            if name != "milestones":
                float(r["value"])
    assert {r["kind"] for r in B.manual_rows("space", "cost")} <= {"flown", "target"}


@pytest.mark.network
def test_live_sources():
    o = M.parse_orgs(B._download(M.GCAT_ORGS, 120))
    assert o
    assert len(M.parse_launches(B._download(M.GCAT_LAUNCH, 120), o)) > 6000
    assert len(M.parse_celestrak(B._download(M.CELESTRAK, 120))) > 5000
