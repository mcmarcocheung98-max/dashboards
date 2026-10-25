"""The web server. Listens on $PORT (Railway sets it).

GET /                 index page (static/index.html)
GET /<slug>           a dashboard (static/topic.html, which loads /<slug>.js)
GET /<slug>.js        that dashboard's tabs and cards (static/topics/<slug>.js)
GET /api/index        the list of dashboards
GET /api/<slug>/meta  title, tabs, sources
GET /api/<slug>/<n>   that dashboard's data (JSON); 404 unknown, 503 when the source is down and no snapshot exists
GET /healthz          'ok'
GET /api/probe        tries a fixed list of the sources from this server (status, size, start of body), cached 10 minutes
GET /api/health       every data source used since start, per dashboard: fresh / stale (serving a snapshot) / failing, with alerts

A background warmer recomputes expired data every 10 minutes so a visitor never waits for a cold cache (WARM=0 turns it off).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from . import topics

log = logging.getLogger("dashboards")
STATIC = Path(__file__).with_name("static")
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
           "Strict-Transport-Security": "max-age=31536000", "X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors 'none'"}
WARM_EVERY = 10 * 60


def _json(obj, status: int = 200) -> web.Response:
    return web.Response(text=json.dumps(obj, default=str, allow_nan=False), status=status, content_type="application/json", headers=HEADERS)


def make_app() -> web.Application:
    async def index(request):
        return web.FileResponse(STATIC / "index.html", headers=HEADERS)

    async def page(request):
        slug = request.match_info["slug"]
        if slug.endswith(".js"):
            f = STATIC / "topics" / slug
            if slug[:-3] not in topics.REGISTRY or not f.exists():
                raise web.HTTPNotFound()
            return web.FileResponse(f, headers={**HEADERS, "Cache-Control": "public, max-age=300"})
        if slug in topics.REDIRECTS:                          # merged dashboards keep their old links working
            to, tab = topics.REDIRECTS[slug]
            raise web.HTTPMovedPermanently(f"/{to}#{tab}")
        if slug not in topics.REGISTRY:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / "topic.html", headers=HEADERS)

    async def api_index(request):
        return _json(topics.index())

    async def api_health(request):
        return _json(topics.health())

    async def api_probe(request):
        from .cache import _cached                           # at most one probe run per 10 minutes, whoever asks
        return _json(await asyncio.to_thread(lambda: _cached("probe", 600, topics.probe)))

    async def api(request):
        slug, name = request.match_info["slug"], request.match_info["name"]
        if slug not in topics.REGISTRY:
            return _json({"error": "unknown dashboard"}, 404)
        try:
            if name == "meta":
                data = topics.meta(slug)
            elif name in topics.endpoints(slug):
                data = await asyncio.to_thread(topics.endpoints(slug)[name])
            else:
                return _json({"error": "unknown endpoint"}, 404)
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        except Exception as e:                       # a source being down must not take the page down
            log.warning("/api/%s/%s failed (%s: %s)", slug, name, type(e).__name__, e)
            return _json({"error": f"{name} is not available right now"}, 503)
        return _json(data)

    async def healthz(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/index", api_index)
    app.router.add_get("/api/health", api_health)
    app.router.add_get("/api/probe", api_probe)
    app.router.add_get("/api/{slug}/{name}", api)
    app.router.add_get("/{slug}", page)
    return app


async def _warm(app) -> None:
    async def loop():
        await asyncio.sleep(30)
        while True:
            for t in topics.REGISTRY.values():
                for name in t.slow:
                    try:
                        await asyncio.to_thread(topics.endpoints(t.slug)[name])
                    except Exception as e:
                        log.warning("warm %s/%s failed (%s)", t.slug, name, type(e).__name__)
            await asyncio.sleep(WARM_EVERY)
    app["warmer"] = asyncio.create_task(loop())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    port = int(os.environ.get("PORT", "8080"))
    app = make_app()
    if os.environ.get("WARM", "1") != "0":
        app.on_startup.append(_warm)
    log.info("listening on port %s", port)
    web.run_app(app, host="0.0.0.0", port=port, print=None, access_log=None)


if __name__ == "__main__":
    main()
