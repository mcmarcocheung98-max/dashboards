"""Open every tab of every dashboard in headless Chromium and report what each one shows.

    python scripts/smoke.py                      # local server, every source replaced by the test fixtures (no network needed)
    python scripts/smoke.py --live https://...   # the deployed site, real data
    options: --out DIR (screenshots), --only SLUG, --lwc PATH (serve the chart library from a local file when its CDN is blocked)

Per tab it prints the number of cards, charts and "not available" notes, and fails on any JavaScript error. On a tab with two or
more time charts it also drags the first chart and checks that every other chart's visible dates followed (the shared date axis).
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def mock_sources() -> None:
    """Point every dashboard's fetchers at the fixtures in tests/test_topics.py."""
    import tests.test_topics as T
    from app.topics import ai_adoption, ai_jobs, btc_cycles, housing, robotaxi   # /ai joins ai_jobs and ai_adoption
    housing.fetch = T.housing_fetch
    housing.fetch_json = lambda url, ttl, **k: T.HIBOR
    housing.full_file_url = lambda: "http://publicdata.landregistry.gov.uk/x.csv"
    ai_jobs.fetch = T.jobs_fetch
    ai_adoption.fetch = lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("fixture: no workbook"))
    robotaxi.fetch = lambda url, ttl, **k: T.SGO
    robotaxi.fetch_json = lambda url, ttl, **k: T._yahoo(250)
    charts = T._chart(mult=1.6)

    import json as _json
    from app.topics import _base
    real_fetch_json = _base.fetch_json

    def cyc(url, ttl, **k):
        if "coinmetrics" in url:
            return T._cm()
        if "coingecko" in url:                     # through the real fetch (cache + snapshot), over the fake download below
            return real_fetch_json(url, ttl, **k)
        return T._llama(url)
    btc_cycles.fetch_json = cyc
    real = _base._download
    _base._download = lambda url, *a, **k: _json.dumps(charts["btc"] if "coins/bitcoin/" in url else charts["coin"]) if "coingecko" in url else real(url, *a, **k)
    import tempfile as _tf
    _base.SNAP_DIR = Path(_tf.mkdtemp())
    from app.topics import btc_flows
    btc_flows.fetch = lambda url, ttl, **k: T._farside_html() if "farside" in url else T._bitbo_page()
    btc_flows.fetch_json = lambda url, ttl, **k: T._mstr_json() if "mstr-nav" in url else T._yahoo(150 if "MSTR" in url else 60000 if "BTC-USD" in url else 1.0)
    btc_cycles.PACE = 0
    btc_cycles.fill_coins()
    import tempfile
    btc_cycles.DOM_LOG = Path(tempfile.mkdtemp()) / "dom.csv"


def serve_local() -> str:
    import asyncio
    from aiohttp import web
    from app.server import make_app
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()

    def run():
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app()); loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start()); loop.run_forever()
    threading.Thread(target=run, daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close(); break
        except OSError:
            time.sleep(0.1)
    return f"http://127.0.0.1:{port}"


SYNC_CHECK = """async () => {
  const live = SYNC.filter(e => charts.includes(e.c) && e.c.timeScale().width() > 0 && !e.extend && e.times.length >= 10);   // a 1-3 point series has nothing to scroll
  if (live.length < 2) return {n: live.length, ok: null};
  const before = live.map(e => e.c.timeScale().getVisibleRange());
  const a = live[0], r = a.c.timeScale().getVisibleRange(), span = r.to - r.from;
  a.c.timeScale().setVisibleRange({from: r.from + span * 0.25, to: r.to});      // as a user zoom would
  await new Promise(ok => setTimeout(ok, 900));
  const want = a.c.timeScale().getVisibleRange();
  const after = live.slice(1).map(e => e.c.timeScale().getVisibleRange());
  const day = 86400 * 35;            // monthly series snap to the nearest month
  // a chart whose data starts after the requested date shows from its first point: that is following too
  const ok = after.every((x, i) => x && (Math.abs(x.from - want.from) <= day || live[i + 1].times[0] >= want.from - day));
  const iso = t => new Date(t * 1000).toISOString().slice(0, 10);
  return {n: live.length, ok, moved: after.filter((x, i) => x && before[i + 1] && x.from !== before[i + 1].from).length, ...(ok ? {} : {want: iso(want.from), got: after.map(x => x && iso(x.from)), starts: live.slice(1).map(e => iso(e.times[0]))})};
}"""


def mock_discovered() -> None:
    """Dashboards added as their own module bring their own fixtures: smoke_patch() in tests/test_<module>.py."""
    import importlib
    from app import topics
    for t in topics.REGISTRY.values():
        if t.module in {b.module for b in topics.BUILTIN}:
            continue
        try:
            tm = importlib.import_module(f"tests.test_{t.module}")
        except ModuleNotFoundError:
            continue
        if hasattr(tm, "smoke_patch"):
            tm.smoke_patch()


def ask_check(pg, first: dict | None) -> dict:
    """The Ask Claude panel (or, on a narrow screen, its pill) is fixed at the top right and stays put across tabs and scrolling."""
    box = pg.evaluate("""() => { const a = document.getElementById('ask'), p = document.getElementById('askpill');
      const v = a && !a.hidden ? a : p; if (!v) return null; const r = v.getBoundingClientRect();
      return { id: v.id, fixed: getComputedStyle(v).position === 'fixed', top: Math.round(r.top), right: Math.round(innerWidth - r.right) }; }""")
    if not box:
        return {"ok": False, "why": "no panel"}
    pg.mouse.wheel(0, 600); time.sleep(0.2)
    after = pg.evaluate("() => { const v = document.getElementById('" + box["id"] + "'); return Math.round(v.getBoundingClientRect().top); }")
    pg.mouse.wheel(0, -600)
    ok = box["fixed"] and after == box["top"] and box["right"] < 40 and (first is None or (first["id"], first["top"]) == (box["id"], box["top"]))
    return {"ok": ok, **box}


def follow_check(pg) -> dict | None:
    """On a tab whose top card follows the timeline (data-follow-head): hover the first chart, the head must show a date; click keeps
    it after the mouse leaves; 'Back to latest' returns. None when the tab has no such head or no chart under it."""
    head = pg.locator("#view [data-follow-head]").first
    if not head.count():
        return None
    time.sleep(0.6)                                     # the head hooks charts every 400 ms
    charts = pg.locator("#view .chart")
    target = None
    for i in range(charts.count()):
        c = charts.nth(i)
        if c.is_visible() and c.evaluate("e => !e.closest('[data-follow]')"):
            target = c; break
    if target is None:
        return None
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    status = lambda: head.locator("span.muted").first.inner_text()
    x, y = box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.5
    pg.mouse.move(x, y); time.sleep(0.3)
    hovered = status()
    pg.mouse.click(x, y); time.sleep(0.2)
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] - 40); time.sleep(0.3)
    kept = status()
    back = head.get_by_text("Back to latest")
    if back.count():
        back.click(); time.sleep(0.2)
    latest = status()
    ok = hovered.startswith(("On ", "Kept: ")) and kept.startswith("Kept: ") and not latest.startswith(("On ", "Kept: "))
    return {"ok": ok, "hover": hovered[:24], "kept": kept[:24]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live"); ap.add_argument("--out", default=str(ROOT / "smoke-shots")); ap.add_argument("--only"); ap.add_argument("--lwc")
    a = ap.parse_args()
    import os
    if a.live:
        base = a.live.rstrip("/")
        passcode = os.environ.get("SMOKE_PASSCODE", "")              # private dashboards are skipped without it
    else:
        os.environ.setdefault("PRIVATE_PASSCODE", "smoke-passcode")
        passcode = os.environ["PRIVATE_PASSCODE"]
        mock_sources(); mock_discovered(); base = serve_local()
    from playwright.sync_api import sync_playwright
    from app import topics
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    slugs = [a.only] if a.only else list(topics.REGISTRY)
    private = {s for s, t in topics.REGISTRY.items() if t.private}
    if not passcode and private & set(slugs):
        print("skipping private dashboards (no SMOKE_PASSCODE):", ", ".join(sorted(private & set(slugs))))
        slugs = [s for s in slugs if s not in private]
    bad = []
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe) if Path(exe).exists() else p.chromium.launch()
        for theme, width in (("light", 1100), ("dark", 390)):
            pg = b.new_page(viewport={"width": width, "height": 900}, color_scheme=theme)
            if a.lwc:
                pg.route("**/lightweight-charts*", lambda route: route.fulfill(path=a.lwc, content_type="application/javascript"))
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
            pg.goto(base + "/"); pg.wait_for_selector("a.tile", timeout=30000)
            if passcode and private & set(slugs):
                r = pg.request.post(base + "/api/unlock", data={"passcode": passcode})
                if not r.ok:
                    bad.append(f"{theme}: unlock failed ({r.status})")
            for slug in slugs:
                pg.goto(f"{base}/{slug}"); pg.wait_for_selector("nav button", timeout=30000)
                ask_first = None
                for i in range(pg.locator("nav button").count()):
                    pg.locator("nav button").nth(i).click()
                    pg.wait_for_function("document.getElementById('stamp').textContent.startsWith('Updated')", timeout=180000)
                    time.sleep(1.2)
                    key = pg.evaluate("location.hash.slice(1)")
                    text = pg.locator("#view").inner_text()
                    sync = pg.evaluate(SYNC_CHECK) if theme == "light" else {"n": "-", "ok": None}
                    follow = follow_check(pg) if theme == "light" else None
                    askp = ask_check(pg, ask_first)
                    ask_first = ask_first or askp
                    line = (f"{theme:5} {slug:12} {key:11} cards={pg.locator('#view .card').count():3} charts={pg.locator('#view .chart').count():3} "
                            f"unavailable={text.count('not available'):2} could-not-load={'Could not load' in text} sync={sync}" + (f" follow={follow}" if follow else "") + ("" if askp["ok"] else f" ask={askp}"))
                    print(line, flush=True)
                    if "Could not load" in text or sync.get("ok") is False or (follow and follow.get("ok") is False) or not askp["ok"]:
                        bad.append(line)
                    if theme == "light":
                        pg.screenshot(path=str(out / f"{slug}-{key}.png"), full_page=True)
            bad += [f"{theme}: JS {e}" for e in errs]
            pg.close()
        b.close()
    print("\nPROBLEMS:" if bad else "\nall tabs OK", *bad, sep="\n  ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
