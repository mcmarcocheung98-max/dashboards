"""Live sources of the thematic dashboards: run by hand (pytest -m network tests/test_sources.py) to see which source changed or went away.
Each test fetches one source with no cache and checks it still parses to a sensible series."""
import pandas as pd
import pytest

from app.topics import _base as B

pytestmark = pytest.mark.network


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "SNAP_DIR", tmp_path)      # no snapshot to fall back on: a failure here is the live source failing
    from app import cache
    cache._cache.clear()


def test_uk_hpi_london_and_uk():
    from app.topics import housing as H
    for which in ("london", "uk"):
        d = H.hpi(which)
        assert len(d) > 200 and d["avg"].dropna().iloc[-1] > 100000 and d.index[-1] > pd.Timestamp.now() - pd.DateOffset(months=6), which
        assert d["vol"].notna().sum() > 100 and d["avg_flat"].notna().sum() > 100


def test_ons_cpih_and_earnings():
    from app.topics import housing as H
    c, w = H.cpih(), H.earnings()
    assert len(c) > 200 and c.index[-1] > pd.Timestamp.now() - pd.DateOffset(months=4)
    assert len(w) > 200 and 300 < w.iloc[-1] < 2000


def test_bank_rate():
    from app.topics import housing as H
    s = H.bank_rate()
    assert len(s) > 20 and 0 <= s.iloc[-1] < 15


def test_indeed_postings_and_ai_share():
    from app.topics import ai_jobs as J
    for cc in ("US", "GB"):
        s = J.sectors(cc)
        assert set(s) == set(J.SECTORS["ai"] + J.SECTORS["professions"]) and all(x.index[-1] > pd.Timestamp.now() - pd.DateOffset(months=2) for x in s.values()), cc
        assert len(J.aggregate(cc)) > 1000
    sh = J.ai_share()
    assert {"US", "GB"} <= set(sh) and sh["US"].index[-1] > pd.Timestamp.now() - pd.DateOffset(months=3)


def test_fred_employment():
    from app.topics import ai_jobs as J
    for sid in J.US_SERIES.values():
        s = J.fred(sid)
        assert len(s) > 100 and s.index[-1] > pd.Timestamp.now() - pd.DateOffset(months=3), sid


def test_census_btos_workbook():
    from app.topics import ai_adoption as A
    s = A.parse_btos(B.fetch(A.BTOS_XLSX, 0, binary=True, min_bytes=1000).encode("latin-1"))
    assert len(s) > 10 and 0 < s.iloc[-1] < 100


def test_nhtsa_sgo():
    from app.topics import robotaxi as R
    d, archived = R.sgo_parts()
    assert archived and len(d) > 1000 and d["month"].max() > pd.Timestamp.now() - pd.DateOffset(months=4)
    assert d["month"].min() < pd.Timestamp("2022-01-01")                                # the archive reaches back to the 2021 order


def test_coinmetrics_btc_price():
    from app.topics import btc_cycles as C
    px = C.price()
    assert len(px) > 5000 and px.index[-1] > pd.Timestamp.now() - pd.DateOffset(days=5) and px.iloc[-1] > 1000


def test_defillama_endpoints():
    from app.topics import btc_cycles as C
    assert len(C.defi_tvl()) > 1000 and C.stablecoins().iloc[-1] > 1e11 and C.hl_tvl().iloc[-1] > 1e9
    assert C.hl_revenue().iloc[-30:].sum() > 1e6
    total, top = C.dexs()
    assert C.hl_fees().iloc[-30:].sum() > 1e6
    assert total.iloc[-30:].sum() > 1e10 and top and top[0]["volume_30d"] > 0


def test_coingecko_global_and_volume():
    from app.topics import btc_cycles as C
    g = C.coingecko_global()
    assert 30 < g["dominance"] < 90
    assert C.btc_volume().iloc[-30:].mean() > 1e9


def test_coingecko_candidate_coins_resolve():
    import time
    from app.topics import btc_cycles as C
    bad = []
    for c in C.coins_list():
        try:
            px, mc = C.coin_chart(c["coingecko_id"], live=True)
            assert len(px) > 300 and mc.iloc[-1] > 0
        except Exception as e:
            bad.append((c["ticker"], c["coingecko_id"], type(e).__name__))
        time.sleep(13)
    assert not bad, bad


def test_etf_sources():
    from app.topics import btc_flows as F
    fs = F.farside()
    assert {"IBIT", "FBTC", "GBTC"} <= set(fs.columns) and fs.index[-1] > pd.Timestamp.now() - pd.DateOffset(days=10)
    assert len(F.bitbo()) > 300


def test_mstr_sources():
    from app.topics import btc_flows as F
    h = F.mstr_history()
    assert h["hold"].iloc[-1] > 500_000 and h.index[-1] > pd.Timestamp.now() - pd.DateOffset(days=30)
    assert len(F.yahoo_daily("MSTR", "2024-01-01")) > 300 and len(F.yahoo_daily("0434.HK", "2024-01-01")) > 100


def test_bls_series():
    from app.topics import ai_jobs as J
    have = J.bls_all()
    assert all(sid in have for sid in J.US_SERIES.values()) and "CES0500000003" in have


def test_housing_new_sources():
    from app.topics import housing as H
    assert len(H.boe_fixed()) > 100
    assert len(H.borough("camden")) > 100
    assert len(H.fhfa()["US national (FHFA)"]) > 300 and len(H.us_mortgage()) > 1000
    assert len(H.hk_hibor()) > 50
    assert len(H.rents()["London average rent"]) > 100
    assert len(H.london_pay()) > 20 and H.london_pay().index[-1].year >= pd.Timestamp.now().year - 2
    assert len(H.hk_index()) > 100            # RVD workbook URL and layout: verify


def test_tsla_price():
    from app.topics import robotaxi as R
    assert len(R.yahoo("TSLA", "2024-01-01")) > 300
