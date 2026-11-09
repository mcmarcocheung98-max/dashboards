"""AI Model Iteration (/ai-models): how the top model families are developed, how fast they iterate, how much compute and money each
generation takes, how useful each is, how export controls bear on them, and what each costs to run.

overview   a card that follows the timeline: frontier Arena score, months since the last frontier compute record, cheapest price per
           million output tokens among models within 50 Arena points of the top, Chinese share of the Arena top 20; the release timeline
iteration  releases per family per year, days between releases, open-weights share (hand-entered: releases.csv)
compute    training compute per model (Epoch AI notable models, through compute_chips), the frontier record, US vs China frontier
           (china_us_tech's parser), compute per family over its generations, hardware where Epoch knows it
utility    the LMArena text top 20 (hand-entered snapshots: arena.csv, plus china_us_tech's best-US / best-China copies), the
           Artificial Analysis Intelligence Index (index.csv), benchmark table (benchmarks.csv), OpenRouter token rankings
           (openrouter_share.csv) and Wikipedia pageviews per family (Wikimedia API)
sanctions  china_us_tech's export-control timeline with the chips each rule covers (chips_covered.csv), Chinese vs US frontier compute
           against the rule dates, and the hardware each Chinese lab reports training on (china_hardware.csv)
cost       Epoch's training-cost estimates per model and per exaFLOP, disclosed and reported costs (costs.csv), hyperscaler capex
           (compute_chips), deployment prices: OpenRouter's public models API daily (a price log accrues on the volume) plus launch list
           prices since 2023 (prices.csv), price per Arena point, and the inputs of a monthly-bill calculator (computed in the browser)

Epoch AI's data is CC-BY: the page credits it. Not investment advice.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

import numpy as np
import pandas as pd

from . import Topic
from . import _base as B
from . import china_us_tech as CN
from . import compute_chips as CC
from ._base import DAY, _pts, _r, fetch, handled, manual_rows, manual_sources, payload

SLUG = "ai-models"
TOPIC = Topic(SLUG, "AI Model Iteration",
              "How the top model families are developed and what they cost: release cadence, training compute per generation, leaderboards "
              "and usage, export controls, and the price of training and of running each model. OpenAI, Anthropic, Google, Meta, xAI, "
              "DeepSeek, Alibaba, Moonshot, Mistral and Zhipu.",
              "ai_models", (("overview", "Overview"), ("iteration", "Iteration"), ("compute", "Compute"), ("utility", "Utility"),
                            ("sanctions", "Sanctions"), ("cost", "Cost")),
              ("overview", "iteration", "compute", "utility", "sanctions", "cost"), icon="chip", order=45)

OPENROUTER = "https://openrouter.ai/api/v1/models"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/monthly/{a}/{b}"
WIKI_KEY = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/monthly"
WIKI_START = "20221101"
BOT = {"User-Agent": "dashboards-ai-models/1.0 (https://github.com/mcmarcocheung98-max/dashboards)", "Accept": "application/json"}
AA_FREE = "https://artificialanalysis.ai/api/v2/language/models/free"    # the V2 API; the legacy /api/v2/data/llms/models answered 410 from 4 Nov 2026
NEAR_TOP = 50                   # "frontier tier": within this many Arena points of the top model
MIN_FLOP = 1e22                 # models drawn on the compute chart
COUNTRIES = ("US", "China")

SOURCES = [{"name": "Epoch AI: notable AI models (training compute, parameters, hardware, cost estimates; CC-BY), through the Compute dashboard", "url": "https://epoch.ai/data/notable-ai-models", "cadence": "weekly"},
           {"name": "OpenRouter models API (per-token prices and context lengths of current models; a daily price log accrues here)", "url": "https://openrouter.ai/api/v1/models", "cadence": "daily"},
           {"name": "Wikimedia REST API: monthly pageviews of each family's English Wikipedia article", "url": "https://wikimedia.org/api/rest_v1/", "cadence": "daily"},
           {"name": "LMArena text leaderboard (hand-entered top-20 snapshots, plus the China vs US copies in china-us-tech)", "url": "https://arena.ai/leaderboard/text", "cadence": "weekly, hand-entered"},
           {"name": "Artificial Analysis Intelligence Index (hand-entered dated points)", "url": "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index", "cadence": "as entered"},
           {"name": "OpenRouter public rankings (tokens processed, hand-entered weekly)", "url": "https://openrouter.ai/rankings", "cadence": "weekly, hand-entered"},
           {"name": "Release announcements, pricing pages, technical reports and BIS rules (hand-entered, cited per row)", "url": "https://github.com/mcmarcocheung98-max/dashboards/tree/main/data/ai-models", "cadence": "as released"},
           {"name": "SEC EDGAR companyfacts: hyperscaler capex (through the Compute dashboard)", "url": "https://www.sec.gov/edgar/sec-api-documentation", "cadence": "quarterly"}]
NOTES = ("Benchmarks saturate and get gamed, and Arena scores move with the voters, so read trends and gaps rather than levels. Epoch AI's "
         "compute and cost figures are estimates with stated uncertainty (CC-BY, credited). Export-control dates are effective dates. Prices "
         "are list prices per million tokens at launch (hand-entered) or OpenRouter's current list (daily); 'cost per Arena point' divides the "
         "output price by the model's score. Rows marked verify were entered from memory or a secondary summary and still need checking "
         "against the cited page. Not investment advice.")


# ------------------------------------------------------------------ the hand-entered files
def rows(name: str) -> list[dict]:
    return sorted(manual_rows(SLUG, name), key=lambda r: r["date"])


def families() -> list[dict]:
    return sorted(manual_rows(SLUG, "families"), key=lambda r: r["family"])


def family_of_org(org: str, fams: list[dict] | None = None) -> str | None:
    """The family whose epoch_org pattern matches an Epoch organisation string ('Google DeepMind,Google' -> Gemini)."""
    for f in fams or families():
        if f.get("epoch_org") and re.search(f["epoch_org"], org or "", re.I):
            return f["family"]
    return None


def family_of_vendor(vendor: str, fams: list[dict] | None = None) -> str | None:
    return next((f["family"] for f in fams or families() if f.get("openrouter") == vendor), None)


_DATE_TAIL = re.compile(r"[-\s_]\d{4}-\d{2}-\d{2}$|[-\s_]\d{4}$|[-\s_]\d{8}$")
_PAREN = re.compile(r"\((max|high|medium|low|thinking|no thinking|xhigh|preview|default fallback)[^)]*\)", re.I)
_SUFFIX = re.compile(r"\b(preview|exp|experimental|instruct|chat|latest)\b", re.I)


def norm(name: str) -> str:
    """A model name reduced to what two sources agree on: 'Claude Opus 5.5 (Max)', 'anthropic/claude-opus-5.5' and 'Claude Opus 5.5'
    all become 'claudeopus55'."""
    s = str(name or "")
    s = s.split(": ", 1)[-1] if ": " in s else s              # OpenRouter's "Anthropic: Claude Opus 5.5"
    s = s.split("/", 1)[-1] if "/" in s else s                # an id's vendor prefix
    s = _PAREN.sub("", s)
    s = _DATE_TAIL.sub("", s.strip())
    s = _SUFFIX.sub("", s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _t(d: str) -> int:
    return int(pd.Timestamp(d).timestamp())


# ------------------------------------------------------------------ OpenRouter: current prices, and a daily log so a history accrues
def parse_openrouter(j: dict, fams: list[dict] | None = None) -> list[dict]:
    """OpenRouter /api/v1/models -> [{id, name, vendor, family, created, context, input, output}] with prices in USD per million
    tokens, for the vendors in families.csv only (the file has hundreds of models)."""
    fams = fams or families()
    out = []
    for m in (j or {}).get("data") or []:
        mid = str(m.get("id", ""))
        vendor = mid.split("/", 1)[0] if "/" in mid else ""
        fam = family_of_vendor(vendor, fams)
        if not fam:
            continue
        p = m.get("pricing") or {}
        inp, outp = _num(p.get("prompt")), _num(p.get("completion"))
        if inp is None or outp is None:
            continue
        out.append({"id": mid, "name": m.get("name") or mid, "vendor": vendor, "family": fam, "created": int(m["created"]) if m.get("created") else None,
                    "context": int(m["context_length"]) if m.get("context_length") else None, "input": _r(inp * 1e6, 4), "output": _r(outp * 1e6, 4)})
    if not out:
        raise ValueError("OpenRouter: no models for the tracked vendors")
    return out


def _log_file():
    return B.SNAP_DIR / SLUG / "prices.csv"


def log_prices(models: list[dict], today: str | None = None) -> int:
    """Append today's prices (id, input, output, context) to the daily log on the volume; the first row of a UTC day is kept."""
    today = today or pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    f = _log_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    have = set()
    if f.exists():
        have = {ln.split(",")[1] for ln in f.read_text().splitlines()[1:] if ln.startswith(today)}
    new = [m for m in models if m["id"] not in have]
    if new:
        head = not f.exists() or f.stat().st_size == 0
        with f.open("a") as fh:
            if head:
                fh.write("date,id,input,output,context\n")
            fh.writelines(f"{today},{m['id']},{m['input']},{m['output']},{m['context'] or ''}\n" for m in new)
    return len(new)


def price_log() -> pd.DataFrame:
    f = _log_file()
    if not f.exists():
        return pd.DataFrame(columns=["date", "id", "input", "output", "context"])
    d = pd.read_csv(f)
    d["date"] = pd.to_datetime(d["date"])
    return d


def openrouter_models() -> list[dict]:
    """Today's OpenRouter list for the tracked vendors, logged once a day. Raises when the API never answered."""
    models = parse_openrouter(json.loads(fetch(OPENROUTER, DAY, headers={"Accept": "application/json"}, min_bytes=1000)))
    if OPENROUTER not in B.STALE:
        log_prices(models)
    return models


# ------------------------------------------------------------------ Wikipedia pageviews per family
def wiki_url(title: str) -> tuple[str, str]:
    """(url, stable key) for the monthly pageviews of one article from WIKI_START to the end of last month."""
    end = (pd.Timestamp.now("UTC").normalize().replace(day=1) - pd.Timedelta(days=1)).strftime("%Y%m%d")
    t = quote(title.replace(" ", "_"), safe="")
    return WIKI.format(title=t, a=WIKI_START, b=end), WIKI_KEY.format(title=t)


def parse_wiki(j: dict) -> pd.Series:
    items = (j or {}).get("items")
    if items is None:
        raise ValueError("Wikimedia layout changed")
    s = pd.Series({pd.Timestamp(str(i["timestamp"])[:8]): float(i["views"]) for i in items if i.get("timestamp") and i.get("views") is not None}, dtype=float)
    return s.sort_index()


def wiki_views(fams: list[dict]) -> tuple[dict[str, pd.Series], dict[str, str]]:
    out, errors = {}, {}
    for f in fams:
        if not f.get("wiki"):
            continue
        url, key = wiki_url(f["wiki"])
        try:
            out[f["family"]] = parse_wiki(json.loads(fetch(url, DAY, headers=BOT, key=key, min_bytes=40)))
        except Exception as e:
            errors[f["family"]] = type(e).__name__
    return out, errors


# ------------------------------------------------------------------ iteration (releases.csv)
def release_gaps(rel: list[dict], fams: list[str], since: pd.Timestamp | None = None) -> dict:
    """Per family: days between consecutive releases (all rows), the median, the trailing-12-month median, and days since the last."""
    now = pd.Timestamp.now().normalize()
    out = {}
    for fam in fams:
        ds = sorted(pd.Timestamp(r["date"]) for r in rel if r["family"] == fam)
        gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
        recent = [(b - a).days for a, b in zip(ds, ds[1:]) if b >= now - pd.Timedelta(days=365)]
        out[fam] = {"n": len(ds), "median_days": _r(float(np.median(gaps)), 0) if gaps else None, "median_12m": _r(float(np.median(recent)), 0) if recent else None,
                    "last": str(ds[-1].date()) if ds else None, "days_since": int((now - ds[-1]).days) if ds else None,
                    "gaps": [[_t(str(b.date())), (b - a).days] for a, b in zip(ds, ds[1:])]}
    return out


def cadence_12m(rel: list[dict], fams: list[str]) -> float | None:
    """The median, over the tracked families, of each family's days between releases in the trailing 12 months (the release_cadence signal)."""
    g = release_gaps(rel, fams)
    vals = [v["median_12m"] for v in g.values() if v["median_12m"] is not None]
    return _r(float(np.median(vals)), 0) if vals else None


def _iteration_now() -> dict:
    fams = families()
    names = [f["family"] for f in fams]
    rel = rows("releases")
    years = list(range(2022, pd.Timestamp.now().year + 1))
    per_year = {fam: [sum(1 for r in rel if r["family"] == fam and int(r["date"][:4]) == y) for y in years] for fam in names}
    by_year = {y: [r for r in rel if int(r["date"][:4]) == y] for y in years}
    open_share = [[y, _r(sum(r["open"] == "yes" for r in rs) / len(rs), 3)] for y, rs in by_year.items() if rs]
    open_by_country = {c: [[y, _r(sum(r["open"] == "yes" for r in rs if r["country"] == c) / max(1, sum(1 for r in rs if r["country"] == c)), 3)]
                           for y, rs in by_year.items() if any(r["country"] == c for r in rs)] for c in COUNTRIES}
    gaps = release_gaps(rel, names)
    flagship = [r for r in rel if r.get("flagship") == "yes"]
    timeline = [{"t": _t(r["date"]), "family": r["family"], "model": r["model"], "open": r["open"] == "yes", "flagship": r.get("flagship") == "yes",
                 "country": r["country"], "context": _num(r.get("context"))} for r in rel]
    ctx = {}
    for r in rel:
        c = _num(r.get("context"))
        if c:
            ctx.setdefault(r["family"], []).append([_t(r["date"]), c])
    return {"families": fams, "years": years, "per_year": per_year, "open_share": open_share, "open_by_country": open_by_country, "gaps": gaps,
            "cadence_12m": cadence_12m(rel, names), "flagship_12m": sum(1 for r in flagship if pd.Timestamp(r["date"]) >= pd.Timestamp.now() - pd.Timedelta(days=365)),
            "timeline": timeline, "context": {k: sorted(v) for k, v in ctx.items()}, "rows": rel[::-1], "n": len(rel), "n_verify": sum("verify" in r.get("note", "") for r in rel),
            "cited": manual_sources(SLUG, "releases")[:5], "stale": {}, "updated": int(time.time()), "as_of": rel[-1]["date"] if rel else None}


# ------------------------------------------------------------------ compute (Epoch AI through compute_chips; country split through china_us_tech)
def epoch_text() -> str:
    return CC.fetch(CC.EPOCH, DAY, min_bytes=1000)


def record_steps(x: pd.DataFrame) -> tuple[list[list], str | None]:
    """[[t, flop]] each time the largest training run to date grew, and the date of the last new record."""
    x = x.sort_values("date")
    run = x["flop"].cummax()
    steps = x[run > run.shift(1).fillna(0)]
    pts = [[int(t.timestamp()), float(v)] for t, v in zip(steps["date"], steps["flop"])]
    return pts, (str(steps["date"].iloc[-1].date()) if len(steps) else None)


def months_since(date: str | None) -> float | None:
    return _r((pd.Timestamp.now().normalize() - pd.Timestamp(date)).days / 30.44, 1) if date else None


def _compute_now() -> dict:
    fams = families()

    def epoch():
        text = epoch_text()
        x = CC.parse_epoch(text)
        x = x[x["date"] <= pd.Timestamp.now()]
        x["family"] = x["org"].map(lambda o: family_of_org(o, fams))
        x["family"] = x["family"].where(x["family"].notna(), None)
        record, last = record_steps(x)
        big = x[(x["flop"] >= MIN_FLOP) & (x["date"] >= "2017-01-01")]
        models = [{"t": int(r["date"].timestamp()), "model": r["model"], "org": r["org"], "family": r["family"], "country": r["country"], "flop": float(r["flop"]),
                   "params": _r(r["params"], 0) if pd.notna(r["params"]) else None, "hardware": (r["hardware"] if isinstance(r["hardware"], str) and r["hardware"] else None),
                   "hw_qty": _r(r["hw_qty"], 0) if pd.notna(r["hw_qty"]) else None, "open": bool(r["open"])} for _, r in big.iterrows()]
        for m in models:                       # pandas NaN is not JSON
            m["family"] = m["family"] if isinstance(m["family"], str) else None
        fam_max = {}
        for fam in {m["family"] for m in models if m["family"]}:
            s = pd.Series({pd.Timestamp(m["t"], unit="s"): m["flop"] for m in models if m["family"] == fam}).sort_index()
            run = s.groupby(level=0).max().cummax()
            fam_max[fam] = _pts(run, 0)
        # the frontier by country from china_us_tech's parser (single-country models), as its AI models tab draws it
        cn = CN.parse_epoch(text)
        cn = cn[~cn["joint"]].dropna(subset=["flop"]).query("flop > 0")
        by_country = {}
        for c in COUNTRIES:
            s = cn[cn["country"] == c].sort_values("date")
            if len(s):
                run = pd.Series(s["flop"].cummax().values, index=s["date"].values).groupby(level=0).max()
                by_country[c] = _pts(run[run.index >= "2017-01-01"], 0)
        hw = big.dropna(subset=["hw_qty"]).sort_values("flop", ascending=False).head(15)
        return {"models": models, "record": record, "last_record": last, "record_age_months": months_since(last), "family_max": fam_max, "by_country": by_country,
                "hardware": [{"model": r["model"], "org": r["org"], "date": str(r["date"].date()), "hardware": r["hardware"] if isinstance(r["hardware"], str) else None, "hw_qty": _r(r["hw_qty"], 0), "flop": float(r["flop"])} for _, r in hw.iterrows()],
                "largest": {"model": x.loc[x["flop"].idxmax(), "model"], "org": x.loc[x["flop"].idxmax(), "org"], "flop": float(x["flop"].max()), "date": str(x.loc[x["flop"].idxmax(), "date"].date())},
                "latest": str(x["date"].max().date()), "n": int(len(x))}
    out = payload({"epoch": epoch}, sources=[CC.EPOCH])
    out["families"] = fams
    out["as_of"] = (out.get("epoch") or {}).get("latest")
    return out


# ------------------------------------------------------------------ utility (arena, index, benchmarks, OpenRouter rankings, Wikipedia)
def arena_snapshots(ar: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in ar:
        if _num(r.get("score")) is not None:
            out.setdefault(r["date"], []).append({**r, "score": _num(r["score"]), "rank": int(_num(r.get("rank")) or 0), "open": r.get("open") == "yes"})
    return {d: sorted(v, key=lambda r: (r["rank"] or 99, -r["score"])) for d, v in sorted(out.items())}


def snapshot_stats(rs: list[dict]) -> dict:
    """Top score, Chinese share of the (entered) top 20, best open model and its gap to the top."""
    top = max(rs, key=lambda r: r["score"])
    top20 = [r for r in rs if 0 < r["rank"] <= 20]
    cn = [r for r in top20 if r["country"] == "China"]
    opens = [r for r in rs if r["open"]]
    best_open = max(opens, key=lambda r: r["score"]) if opens else None
    return {"top": top["score"], "top_model": top["model"], "top_family": top["family"], "n_top20": len(top20), "china_top20": len(cn),
            "china_share": _r(len(cn) / len(top20), 4) if top20 else None, "open_gap": _r(top["score"] - best_open["score"], 0) if best_open else None,
            "best_open": best_open["model"] if best_open else None}


def _utility_now() -> dict:
    fams = families()
    ar = rows("arena")
    snaps = arena_snapshots(ar)
    dates = list(snaps)
    stats = {d: snapshot_stats(v) for d, v in snaps.items()}
    by_family: dict[str, list] = {}
    for d, v in snaps.items():
        best: dict[str, float] = {}
        for r in v:
            best[r["family"]] = max(best.get(r["family"], 0), r["score"])
        for fam, sc in best.items():
            by_family.setdefault(fam, []).append([_t(d), sc])
    idx = rows("index")
    idx_by_family: dict[str, list] = {}
    for d in sorted({r["date"] for r in idx}):
        best: dict[str, float] = {}
        for r in idx:
            if r["date"] == d and _num(r["value"]) is not None:
                best[r["family"]] = max(best.get(r["family"], 0), _num(r["value"]))
        for fam, v in best.items():
            idx_by_family.setdefault(fam, []).append([_t(d), v])
    bench = rows("benchmarks")
    names = sorted({r["benchmark"] for r in bench})
    table: dict[str, dict] = {}
    for r in sorted(bench, key=lambda r: r["date"]):
        v = _num(r["value"])
        if v is None:
            continue
        row = table.setdefault(r["model"], {"model": r["model"], "family": r["family"], "date": r["date"], "scores": {}})
        row["scores"][r["benchmark"]] = v
        row["date"] = max(row["date"], r["date"])
    best_bench = {b: max(((v["scores"][b], v["model"]) for v in table.values() if b in v["scores"]), default=None) for b in names}
    orr = rows("openrouter_share")
    weeks = sorted({r["date"] for r in orr})
    share_by_country = []
    for w in weeks:
        rs = [r for r in orr if r["date"] == w and _num(r.get("tokens_t")) is not None]
        tot = sum(_num(r["tokens_t"]) for r in rs)
        if tot:
            share_by_country.append([_t(w), _r(sum(_num(r["tokens_t"]) for r in rs if r["country"] == "China") / tot, 3)])
    wv, werr = wiki_views(fams)

    def wiki():
        if not wv:
            raise LookupError("Wikimedia not reachable")
        return {k: _pts(v, 0) for k, v in wv.items()}
    out = payload({"wiki": wiki}, sources=[WIKI_KEY.format(title=quote(f["wiki"].replace(" ", "_"), safe="")) for f in fams if f.get("wiki")])
    out.update({"arena": {"dates": dates, "latest": snaps[dates[-1]] if dates else [], "latest_date": dates[-1] if dates else None, "stats": stats, "by_family": by_family,
                          "us_cn": CN.leaderboard_rows(), "n_verify": sum("verify" in r.get("note", "") for r in ar), "cited": manual_sources(SLUG, "arena")[:4]},
                "index": {"rows": idx[::-1], "by_family": idx_by_family, "latest_date": idx[-1]["date"] if idx else None},
                "benchmarks": {"names": names, "rows": sorted(table.values(), key=lambda r: -max(r["scores"].values())), "best": {b: {"value": v[0], "model": v[1]} for b, v in best_bench.items() if v}},
                "openrouter": {"rows": orr[::-1], "weeks": weeks, "latest": [r for r in orr if r["date"] == weeks[-1]] if weeks else [], "china_share": share_by_country},
                "wiki_errors": werr, "families": fams})
    out["as_of"] = max([x for x in (dates[-1] if dates else None, idx[-1]["date"] if idx else None, weeks[-1] if weeks else None) if x], default=None)
    return out


# ------------------------------------------------------------------ sanctions
def _sanctions_now() -> dict:
    controls = CN.controls_rows()
    chips = {r["date"]: r for r in rows("chips_covered")}
    timeline = [{**r, "chips": (chips.get(r["date"]) or {}).get("chips"), "status": (chips.get(r["date"]) or {}).get("status")} for r in controls]
    us_steps = [r for r in controls if not r["actor"].startswith("China")]
    out = {"controls": timeline[::-1], "rule_dates": [{"t": _t(r["date"]), "label": r["date"][:7], "direction": int(_num(r.get("direction")) or 0), "actor": r["actor"]} for r in us_steps],
           "chips": rows("chips_covered")[::-1], "hardware": rows("china_hardware")[::-1],
           "n_steps": len(controls), "last_step": controls[-1] if controls else None, "stale": {}, "updated": int(time.time())}
    try:
        c = _compute()
        e = c.get("epoch") or {}
        out["by_country"] = e.get("by_country")
        out["stale"] = c.get("stale") or {}
    except Exception as ex:
        out["by_country"], out["by_country_error"] = None, type(ex).__name__
    bc = out.get("by_country") or {}
    if bc.get("US") and bc.get("China"):
        us, cn = dict(bc["US"]), dict(bc["China"])
        ts = sorted(set(us) | set(cn))
        gap, u = [], None
        last_u = last_c = None
        for t in ts:
            last_u = us.get(t, last_u)
            last_c = cn.get(t, last_c)
            if last_u and last_c:
                gap.append([t, _r(np.log10(last_u / last_c), 2)])
        out["gap_oom"] = gap
    out["as_of"] = controls[-1]["date"] if controls else None
    return out


# ------------------------------------------------------------------ cost
def price_table(hand: list[dict], current: list[dict] | None) -> dict[str, dict]:
    """norm(name) -> {model, family, input, output, context, source: 'openrouter'|'launch', date}; OpenRouter's current list wins over a
    hand-entered launch price for the same model."""
    out = {}
    for r in hand:
        i, o = _num(r.get("input")), _num(r.get("output"))
        if i is not None and o is not None:
            out[norm(r["model"])] = {"model": r["model"], "family": r["family"], "input": i, "output": o, "context": _num(r.get("context")), "source": "launch", "date": r["date"]}
    for m in current or []:
        if m["output"] and m["output"] > 0:
            out[norm(m["name"])] = {"model": m["name"].split(": ", 1)[-1], "family": m["family"], "input": m["input"], "output": m["output"], "context": m["context"], "source": "openrouter", "id": m["id"],
                                    "date": pd.Timestamp(m["created"], unit="s").strftime("%Y-%m-%d") if m.get("created") else None}
    return out


def frontier_prices(snaps: dict[str, list[dict]], launch: list[dict], current: list[dict] | None) -> list[dict]:
    """Per Arena snapshot: the cheapest output price among models within NEAR_TOP points of the top. Historical snapshots use launch
    prices; the latest one uses OpenRouter's current list where it has the model."""
    out = []
    dates = list(snaps)
    for d in dates:
        pt = price_table(launch, current if d == dates[-1] else None)
        top = max(r["score"] for r in snaps[d])
        n20 = sum(1 for r in snaps[d] if 0 < r["rank"] <= 20)
        tier = [r for r in snaps[d] if r["score"] >= top - NEAR_TOP]
        priced = [(pt[norm(r["model"])]["output"], r, pt[norm(r["model"])]) for r in tier if norm(r["model"]) in pt]
        if priced:
            p, r, info = min(priced, key=lambda x: x[0])
            out.append({"t": _t(d), "date": d, "price": p, "model": r["model"], "score": r["score"], "top": top, "n_tier": len(tier), "n_priced": len(priced), "n_top20": n20, "source": info["source"]})
        else:
            out.append({"t": _t(d), "date": d, "price": None, "model": None, "score": None, "top": top, "n_tier": len(tier), "n_priced": 0, "n_top20": n20, "source": None})
    return out


def _cost_now() -> dict:
    fams = families()
    launch = rows("prices")
    cur, cur_err = None, None
    try:
        cur = openrouter_models()
    except Exception as e:
        cur_err = type(e).__name__
        handled(OPENROUTER, "OpenRouter not reachable: deployment prices are the hand-entered launch list and the price log")
    pt = price_table(launch, cur)
    snaps = arena_snapshots(rows("arena"))
    fp = frontier_prices(snaps, launch, cur)
    latest = snaps[list(snaps)[-1]] if snaps else []
    per_point = []
    for r in latest:
        info = pt.get(norm(r["model"]))
        if info:
            per_point.append({"model": r["model"], "family": r["family"], "country": r["country"], "score": r["score"], "output": info["output"], "input": info["input"],
                              "per_point": _r(info["output"] / r["score"], 5), "source": info["source"]})
    per_point.sort(key=lambda x: x["per_point"])
    fam_pp = {}
    for x in per_point:
        fam_pp.setdefault(x["family"], x)                       # the cheapest priced model per family
    launch_by_family: dict[str, list] = {}
    for r in launch:
        o = _num(r.get("output"))
        if o is not None:
            launch_by_family.setdefault(r["family"], []).append([_t(r["date"]), o])
    launch_by_family = {k: sorted(v) for k, v in launch_by_family.items()}
    flagship_min = {}
    for fam, pts in launch_by_family.items():
        flagship_min[fam] = pts
    log = price_log()
    log_series = {}
    if len(log):
        for mid, g in log.groupby("id"):
            s = g.set_index("date")["output"].groupby(level=0).last()
            if len(s) >= 2:
                log_series[mid] = _pts(s, 4)

    def epoch_costs():
        x = CC.parse_epoch(epoch_text())
        x = x[(x["date"] >= "2017-01-01") & (x["date"] <= pd.Timestamp.now())].dropna(subset=["cost"]).query("cost > 0")
        x["family"] = x["org"].map(lambda o: family_of_org(o, fams))
        return {"models": [{"t": int(r["date"].timestamp()), "model": r["model"], "org": r["org"], "family": r["family"] if isinstance(r["family"], str) else None, "country": r["country"], "cost": float(r["cost"]),
                            "flop": float(r["flop"]), "per_eflop": _r(r["cost"] / (r["flop"] / 1e18), 3)} for _, r in x.iterrows()],
                "n": int(len(x)), "latest": str(x["date"].max().date()) if len(x) else None}
    out = payload({"epoch_cost": epoch_costs}, sources=[CC.EPOCH, OPENROUTER])
    cap = None
    try:
        cap = (CC._capex().get("kpi") or None)
    except Exception as e:
        out["capex_error"] = type(e).__name__
    out.update({"disclosed": rows("costs")[::-1], "launch": launch[::-1], "launch_by_family": launch_by_family, "current": cur, "current_error": cur_err,
                "frontier_price": fp, "per_point": per_point, "per_point_family": fam_pp, "price_log": log_series, "log_days": int(log["date"].nunique()) if len(log) else 0,
                "capex": cap, "near_top": NEAR_TOP, "families": fams,
                "calculator": sorted([{"model": v["model"], "family": v["family"], "input": v["input"], "output": v["output"], "source": v["source"], "date": v["date"]} for v in pt.values()],
                                     key=lambda v: (v["family"], -(pd.Timestamp(v["date"]).timestamp() if v["date"] else 0)))})
    out["as_of"] = max([x for x in (launch[-1]["date"] if launch else None, (out.get("epoch_cost") or {}).get("latest")) if x], default=None)
    return out


# ------------------------------------------------------------------ overview, readings, signals
def _cached_payload(name: str) -> dict:
    from ..cache import _cache
    return (_cache.get(f"topic:{SLUG}:{name}") or (0, {}))[1] or {}


def _overview_now() -> dict:
    got, errors = {}, {}
    for name in ("iteration", "compute", "utility", "cost"):
        try:
            got[name] = ENDPOINTS[name]()
        except Exception as e:
            got[name], errors[name] = {}, type(e).__name__
    I, C, U, K = (got.get(n) or {} for n in ("iteration", "compute", "utility", "cost"))
    E = C.get("epoch") or {}
    A = U.get("arena") or {}
    st = A.get("stats") or {}
    latest = A.get("latest_date")
    s = st.get(latest) or {}
    fp = [x for x in (K.get("frontier_price") or []) if x.get("price") is not None]
    out = {"kpi": {"frontier_score": s.get("top"), "frontier_model": s.get("top_model"), "arena_date": latest, "record_age_months": E.get("record_age_months"),
                   "last_record": E.get("last_record"), "largest": E.get("largest"), "frontier_price": fp[-1]["price"] if fp else None, "frontier_price_model": fp[-1]["model"] if fp else None,
                   "china_share": s.get("china_share"), "china_top20": s.get("china_top20"), "n_top20": s.get("n_top20"), "open_gap": s.get("open_gap"), "best_open": s.get("best_open"),
                   "cadence_12m": I.get("cadence_12m"), "flagship_12m": I.get("flagship_12m")},
           "series": {"frontier_score": [[_t(d), v["top"]] for d, v in st.items()], "china_share": [[_t(d), v["china_share"]] for d, v in st.items() if v.get("china_share") is not None],
                      "frontier_price": [[x["t"], x["price"]] for x in fp], "record": E.get("record"), "open_gap": [[_t(d), v["open_gap"]] for d, v in st.items() if v.get("open_gap") is not None]},
           "timeline": I.get("timeline"), "families": I.get("families") or families(), "errors": errors,
           "stale": {k: v for p in got.values() for k, v in (p.get("stale") or {}).items()}, "updated": int(time.time()),
           "as_of": max([p.get("as_of") for p in got.values() if p.get("as_of")], default=None)}
    return out


def readings(got) -> list[dict]:
    """Frontier score (+1 when it rose since the snapshot before), cheapest frontier-tier price (+1 when cheaper than at the snapshot
    before), Chinese share of the top 20 (+1 when it rose), from cached payloads only."""
    out = []
    st = (got("utility").get("arena") or {}).get("stats") or {}
    ds = list(st)
    if ds:
        now, prev = st[ds[-1]], st[ds[-2]] if len(ds) >= 2 else None
        out.append({"tab": "utility", "key": "frontier_score", "label": "Top Arena score", "value": now["top"], "lean": 0 if not prev else 1 if now["top"] > prev["top"] else -1 if now["top"] < prev["top"] else 0,
                    "note": f"{now['top_model']} on {ds[-1]}; +1 when higher than at the snapshot before"})
        if now.get("china_share") is not None:
            pc = prev.get("china_share") if prev else None
            out.append({"tab": "utility", "key": "china_share", "label": "Chinese share of the Arena top 20 (%)", "value": _r(100 * now["china_share"], 1),
                        "lean": 0 if pc is None else 1 if now["china_share"] > pc else -1 if now["china_share"] < pc else 0, "note": f"{now['china_top20']} of {now['n_top20']} entered; +1 when the share rose since the snapshot before"})
    fp = [x for x in (got("cost").get("frontier_price") or []) if x.get("price") is not None]
    if fp:
        prev = fp[-2]["price"] if len(fp) >= 2 else None
        out.append({"tab": "cost", "key": "frontier_price", "label": f"Cheapest frontier-tier model, $ per million output tokens", "value": fp[-1]["price"],
                    "lean": 0 if prev is None else 1 if fp[-1]["price"] < prev else -1 if fp[-1]["price"] > prev else 0,
                    "note": f"{fp[-1]['model']} on {fp[-1]['date']}, within {NEAR_TOP} points of the top; +1 when cheaper than at the snapshot before"})
    return out


def READINGS() -> list[dict]:
    return readings(_cached_payload)


def SIGNALS() -> list[dict]:
    """The proposed signals (data/signals/watchlist.json, "proposed": true until the owner approves), from cached payloads only."""
    out = []

    def add(key, tab, label, value, unit, lean, watch, crossed, note=None):
        out.append({"key": key, "tab": tab, "label": label, "value": value, "unit": unit, "lean": lean, "watch": watch, "crossed": bool(crossed), **({"note": note} if note else {})})
    E = _cached_payload("compute").get("epoch") or {}
    age = E.get("record_age_months")
    if age is not None:
        add("frontier_record_age", "compute", "Months since the last frontier training-compute record (Epoch AI)", age, " months", -1 if age > 12 else 1 if age < 6 else 0,
            "above 12 months", age > 12, f"largest run so far: {(E.get('largest') or {}).get('model')} on {E.get('last_record')}")
    fp = [x for x in (_cached_payload("cost").get("frontier_price") or []) if x.get("price") is not None]
    if fp:
        now = fp[-1]
        partial = (now.get("n_top20") or 0) < 20
        ago = [x for x in fp if x["t"] <= now["t"] - 300 * 86400]
        chg = now["price"] / ago[-1]["price"] - 1 if ago and ago[-1]["price"] else None
        add("price_per_point", "cost", f"Cheapest model within {NEAR_TOP} Arena points of the top, $ per million output tokens", now["price"], "",
            0 if chg is None else 1 if chg < 0 else -1, "falls by half on a year, or rises", not partial and chg is not None and (chg <= -0.5 or chg > 0),
            (f"partial snapshot ({now.get('n_top20') or 0} of 20 entered), not counted as crossed; " if partial else "")
            + f"{now['model']} ({now['source']} price) on {now['date']}" + (f"; {chg:+.0%} against the snapshot a year or more before" if chg is not None else "; no snapshot a year earlier yet"))
    st = (_cached_payload("utility").get("arena") or {}).get("stats") or {}
    if st:
        d = list(st)[-1]
        s = st[d]
        if s.get("open_gap") is not None:
            g = s["open_gap"]
            add("open_gap", "utility", "Best open-weights model's Arena gap to the top", g, " pts", 1 if g < 30 else -1 if g > 80 else 0, "under 20 points, or over 100",
                g < 20 or g > 100, f"{s['best_open']} vs {s['top_model']} on {d}")
        if s.get("china_share") is not None:
            sh, partial = s["china_share"], (s.get("n_top20") or 0) < 20
            add("china_share_top20", "utility", "Chinese developers' share of the Arena top 20", _r(100 * sh, 1), "%", 1 if sh > 0.25 else -1 if sh < 0.15 else 0, "above 40% or below 10%",
                not partial and (sh > 0.4 or sh < 0.1), ("partial snapshot, not counted as crossed; " if partial else "") + f"{s['china_top20']} of the {s['n_top20']} top-20 rows entered for {d}")
    cad = _cached_payload("iteration").get("cadence_12m")
    if cad is not None:
        add("release_cadence", "iteration", "Median days between a family's releases, trailing 12 months", cad, " days", 1 if cad < 60 else -1 if cad > 120 else 0, "under 60 days", cad < 60,
            "the median over the tracked families of each family's median gap between releases in the last 12 months")
    return out


def _layout_now() -> dict:
    """Not a tab: what this server gets back from each source (status, size, start of body). Read with Actions > show-json on
    /api/ai-models/layout. Includes candidate URLs that are not fetched by any tab (Epoch's benchmarking hub, Artificial Analysis)."""
    from concurrent.futures import ThreadPoolExecutor
    import requests
    wiki, _ = wiki_url("DeepSeek")
    urls = {"openrouter models": OPENROUTER, "wikimedia monthly": wiki, "epoch notable": CC.EPOCH,
            "epoch benchmarks use-this-data (find the CSV link)": "https://epoch.ai/benchmarks/use-this-data",
            "artificial analysis v2 free tier (needs x-api-key: AA_API_KEY proposed)": AA_FREE,
            "artificial analysis v2 openapi": "https://artificialanalysis.ai/api/v2/openapi",
            "openrouter rankings page": "https://openrouter.ai/rankings", "arena leaderboard page": "https://arena.ai/leaderboard/text"}

    def one(item):
        k, u = item
        h = {**B.UA, **(BOT if "wikimedia" in u else {})}
        try:
            r = requests.get(u, headers=h, timeout=25)
            return k, {"status": r.status_code, "bytes": len(r.content), "type": r.headers.get("content-type", ""), "start": r.text[:300]}
        except Exception as e:
            return k, {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(one, urls.items()))


def _cached_ep(name, fn, ttl=6 * 3600):
    from ..cache import _cached
    return lambda: _cached(f"topic:{SLUG}:{name}", ttl, fn)


_iteration, _compute, _utility, _sanctions, _cost = (_cached_ep("iteration", _iteration_now, 600), _cached_ep("compute", _compute_now), _cached_ep("utility", _utility_now),
                                                     _cached_ep("sanctions", _sanctions_now, 600), _cached_ep("cost", _cost_now))
ENDPOINTS = {"overview": _cached_ep("overview", _overview_now, 600), "iteration": _iteration, "compute": _compute, "utility": _utility, "sanctions": _sanctions, "cost": _cost,
             "layout": _cached_ep("layout", _layout_now, 1800)}
