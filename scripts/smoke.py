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
    from app.topics import ai_adoption, ai_jobs, btc_cycles, housing, robotaxi
    housing.fetch = lambda url, ttl, **k: T.HPI if "ukhpi" in url else T.BOE
    housing.fetch_json = lambda url, ttl, **k: T.ONS(100) if "L522" in url else T.ONS(500)
    ai_jobs.fetch = lambda url, ttl, **k: T.AIS if "ai-tracker" in url else T.FRED if "fred" in url else T.AGG if "aggregate" in url else T.IND
    ai_adoption.fetch = lambda url, ttl, **k: (_ for _ in ()).throw(ConnectionError("fixture: no workbook"))
    robotaxi.fetch = lambda url, ttl, **k: T.SGO
    charts = T._chart(mult=1.6)

    def cyc(url, ttl, **k):
        if "coinmetrics" in url:
            return T._cm()
        if "coins/bitcoin/" in url:
            return charts["btc"]
        if "market_chart" in url:
            return charts["coin"]
        return T._llama(url)
    btc_cycles.fetch_json = cyc
    btc_cycles.PACE = 0
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live"); ap.add_argument("--out", default=str(ROOT / "smoke-shots")); ap.add_argument("--only"); ap.add_argument("--lwc")
    a = ap.parse_args()
    if a.live:
        base = a.live.rstrip("/")
    else:
        mock_sources(); base = serve_local()
    from playwright.sync_api import sync_playwright
    from app import topics
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    slugs = [a.only] if a.only else list(topics.REGISTRY)
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
            for slug in slugs:
                pg.goto(f"{base}/{slug}"); pg.wait_for_selector("nav button", timeout=30000)
                for i in range(pg.locator("nav button").count()):
                    pg.locator("nav button").nth(i).click()
                    pg.wait_for_function("document.getElementById('stamp').textContent.startsWith('Updated')", timeout=180000)
                    time.sleep(1.2)
                    key = pg.evaluate("location.hash.slice(1)")
                    text = pg.locator("#view").inner_text()
                    sync = pg.evaluate(SYNC_CHECK) if theme == "light" else {"n": "-", "ok": None}
                    line = (f"{theme:5} {slug:12} {key:11} cards={pg.locator('#view .card').count():3} charts={pg.locator('#view .chart').count():3} "
                            f"unavailable={text.count('not available'):2} could-not-load={'Could not load' in text} sync={sync}")
                    print(line, flush=True)
                    if "Could not load" in text or sync.get("ok") is False:
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
