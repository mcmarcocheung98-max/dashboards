"""The web server. Listens on $PORT (Railway sets it).

GET /                 index page (static/index.html)
GET /<slug>           a dashboard (static/topic.html, which loads /<slug>.js)
GET /<slug>.js        that dashboard's tabs and cards (static/topics/<slug>.js)
GET /api/index        the list of dashboards
GET /api/<slug>/meta  title, tabs, sources
GET /api/<slug>/method  the calculation and caveat sections of data/<slug>/README.md, for the page's Method tab (#about)
GET /api/<slug>/changes  what changed since yesterday (topics/_daily.py): flipped readings and each tab's lean day by day
GET /api/<slug>/<n>   that dashboard's data (JSON); 404 unknown, 503 when the source is down and no snapshot exists
GET /healthz          'ok'
GET /newsletter       today's signals email as a page (app/signals.py); /api/signals/newsletter has subject, html and text
POST /api/unlock      {passcode}: opens private dashboards in this browser for 30 days (app/auth.py); POST /api/lock signs out
POST /api/ask         Ask Claude about the tab you are on (app/ask.py): {slug, tab, question, history?, date?}; limited per visitor and per day
GET /api/ask/status   whether Ask Claude is set up and how many questions this visitor has left
GET /api/archive.zip  every dashboard's data, daily snapshots and hand-entered files in one zip (app/archive.py), built at most every 6 hours
GET /api/probe        tries a fixed list of the sources from this server (status, size, start of body), cached 10 minutes
GET /api/health       every data source used since start, per dashboard: fresh / stale (serving a snapshot) / failing, with alerts

A background warmer recomputes expired data every 10 minutes so a visitor never waits for a cold cache (WARM=0 turns it off).
"""
from __future__ import annotations

import asyncio
import html
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
SHELL_TITLE = "<title>Dashboard</title>"
SHELL_DESC = '<meta name="description" content="A thematic data dashboard: public, read-only.">'


def page_html(slug: str) -> str:
    """topic.html with this dashboard's title and blurb in <title>, the description and Open Graph tags, so a shared link previews
    with the dashboard's name (link previewers do not run the page's JavaScript). Private dashboards keep the generic shell."""
    shell = (STATIC / "topic.html").read_text(encoding="utf-8")
    t = topics.REGISTRY[slug]
    if t.private:
        return shell
    title, desc = html.escape(f"{t.title} · Dashboards"), html.escape(t.blurb)
    tags = (f'<meta name="description" content="{desc}">\n<meta property="og:type" content="website">\n'
            f'<meta property="og:site_name" content="Dashboards">\n<meta property="og:title" content="{title}">\n'
            f'<meta property="og:description" content="{desc}">\n<meta name="twitter:card" content="summary">')
    return shell.replace(SHELL_TITLE, f"<title>{title}</title>", 1).replace(SHELL_DESC, tags, 1)


def _json(obj, status: int = 200) -> web.Response:
    return web.Response(text=json.dumps(obj, default=str, allow_nan=False), status=status, content_type="application/json", headers=HEADERS)


def _auth_cookie(request) -> str | None:
    return request.cookies.get("dash_auth")


def make_app() -> web.Application:
    from . import auth
    async def index(request):
        return web.FileResponse(STATIC / "index.html", headers=HEADERS)

    async def page(request):
        slug = request.match_info["slug"]
        if slug.endswith(".js"):
            if slug[:-3] not in topics.REGISTRY:
                raise web.HTTPNotFound()
            f = STATIC / "topics" / topics.script(slug[:-3])
            if not f.exists():
                raise web.HTTPNotFound()
            if not auth.allowed(slug[:-3], _auth_cookie(request)):
                raise web.HTTPUnauthorized()
            return web.FileResponse(f, headers={**HEADERS, "Cache-Control": "public, max-age=300"})
        if slug in topics.REDIRECTS:                          # merged dashboards keep their old links working
            to, tab = topics.REDIRECTS[slug]
            raise web.HTTPMovedPermanently(f"/{to}#{tab}")
        if slug not in topics.REGISTRY:
            raise web.HTTPNotFound()
        return web.Response(text=page_html(slug), content_type="text/html", charset="utf-8", headers=HEADERS)

    async def api_index(request):
        return _json(topics.index())

    async def api_health(request):
        from . import archive
        h = topics.health()
        from . import ask
        h["ask"] = ask.health()
        try:
            h["archive"] = await asyncio.to_thread(archive.health)
        except Exception as e:
            h["archive"] = {"error": type(e).__name__}
        return _json(h)

    async def api_probe(request):
        from .cache import _cached                           # at most one probe run per 10 minutes, whoever asks
        return _json(await asyncio.to_thread(lambda: _cached("probe", 600, topics.probe)))

    async def api(request):
        slug, name = request.match_info["slug"], request.match_info["name"]
        if slug not in topics.REGISTRY:
            return _json({"error": "unknown dashboard"}, 404)
        if not auth.allowed(slug, _auth_cookie(request)):
            return _json({"error": "This dashboard is private." if auth.configured() else "This private dashboard is not set up yet (PRIVATE_PASSCODE).",
                          "private": True, "set_up": auth.configured()}, 401)
        try:
            if name == "meta":
                data = topics.meta(slug)
            elif name == "method":
                data = await asyncio.to_thread(topics.method, slug)
            elif name == "changes":
                data = await asyncio.to_thread(topics.changes, slug)
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

    async def api_archive(request):
        from .cache import _cached
        from .archive import build
        data = await asyncio.to_thread(lambda: _cached("archive.zip", 6 * 3600, build))
        return web.Response(body=data, content_type="application/zip",
                            headers={**HEADERS, "Content-Disposition": "attachment; filename=dashboards-archive.zip"})

    def client_ip(request) -> str:
        fwd = request.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or (request.remote or "")

    async def api_ask(request):
        from . import ask
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except Exception:
            return _json({"error": "bad request"}, 400)
        if not auth.allowed(str(body.get("slug") or ""), _auth_cookie(request)):
            return _json({"error": "Unlock this dashboard first."}, 401)
        try:
            data = await asyncio.to_thread(ask.ask, str(body.get("slug") or ""), str(body.get("tab") or "")[:40], str(body.get("question") or ""),
                                           body.get("history") if isinstance(body.get("history"), list) else None,
                                           str(body.get("date") or "")[:20] or None, client_ip(request))
        except ValueError as e:
            return _json({"error": str(e)}, 400)
        except KeyError:
            return _json({"error": "unknown dashboard"}, 404)
        except ask.Limit as e:
            return _json({"error": str(e), "limit": True}, 429)
        except ask.NotSetUp as e:
            return _json({"error": str(e)}, 503)
        except Exception as e:
            log.warning("ask failed (%s)", type(e).__name__)
            return _json({"error": "Claude could not answer right now; please try again in a minute."}, 502)
        return _json(data)

    async def api_unlock(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not auth.configured():
            return _json({"error": "Private dashboards are not set up yet (PRIVATE_PASSCODE)."}, 503)
        try:
            tok = auth.unlock(str((body or {}).get("passcode") or "")[:200], client_ip(request))
        except auth.TooMany as e:
            return _json({"error": str(e)}, 429)
        if not tok:
            return _json({"error": "Wrong passcode."}, 401)
        resp = _json({"ok": True})
        secure = request.secure or request.headers.get("X-Forwarded-Proto", "") == "https"
        resp.set_cookie("dash_auth", tok, max_age=auth.DAYS * 86400, httponly=True, secure=secure, samesite="Strict", path="/")
        return resp

    async def api_lock(request):
        resp = _json({"ok": True})
        resp.del_cookie("dash_auth", path="/")
        return resp

    async def api_ask_status(request):
        from . import ask
        return _json(await asyncio.to_thread(ask.status, client_ip(request)))

    async def newsletter(request):
        from . import signals
        try:
            n = await asyncio.to_thread(signals.newsletter)
        except Exception as e:
            log.warning("newsletter failed (%s: %s)", type(e).__name__, e)
            return web.Response(text="The newsletter is not available right now.", status=503, headers=HEADERS)
        return web.Response(text=f"<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(n['subject'])}</title></head><body style=\"margin:0;background:#f6f6f4\">{n['html']}</body></html>",
                            content_type="text/html", headers=HEADERS)

    async def healthz(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/index", api_index)
    app.router.add_get("/api/health", api_health)
    app.router.add_get("/api/probe", api_probe)
    app.router.add_get("/api/archive.zip", api_archive)
    app.router.add_get("/newsletter", newsletter)
    app.router.add_get("/api/ask/status", api_ask_status)
    app.router.add_post("/api/ask", api_ask)
    app.router.add_post("/api/unlock", api_unlock)
    app.router.add_post("/api/lock", api_lock)
    app.router.add_get("/api/{slug}/{name}", api)
    app.router.add_get("/{slug}", page)
    return app


async def _warm(app) -> None:
    async def background():
        """Each dashboard module's BACKGROUND jobs (slow, rate-limited downloads), once at start and then every 6 hours."""
        await asyncio.sleep(20)
        while True:
            for t in topics.REGISTRY.values():
                for job in getattr(topics.module(t.slug), "BACKGROUND", []):
                    try:
                        res = await asyncio.to_thread(job)
                        log.info("background %s.%s: %s", t.slug, job.__name__, {k: v for k, v in (res or {}).items() if v != "ok"} or "all ok")
                    except Exception as e:
                        log.warning("background %s.%s failed (%s)", t.slug, job.__name__, type(e).__name__)
            await asyncio.sleep(6 * 3600)
    app["background"] = asyncio.create_task(background())

    async def loop():
        await asyncio.sleep(30)
        while True:
            for t in topics.REGISTRY.values():
                for name in t.slow:
                    try:
                        await asyncio.to_thread(topics.endpoints(t.slug)[name])
                    except Exception as e:
                        log.warning("warm %s/%s failed (%s)", t.slug, name, type(e).__name__)
                try:
                    res = await asyncio.to_thread(topics.save_daily, t.slug)
                    if res == "saved":
                        log.info("daily snapshot saved for %s", t.slug)
                except Exception as e:
                    log.warning("daily snapshot %s failed (%s: %s)", t.slug, type(e).__name__, e)
            try:                                                  # month-end archive to OneDrive (app/archive.py)
                from . import archive, cloud
                if cloud.configured() and archive.due():
                    st = await asyncio.to_thread(archive.run)
                    log.info("archive: %s", st.get("path") if st.get("ok") else "failed: " + st.get("error", ""))
            except Exception as e:
                log.warning("archive failed (%s)", type(e).__name__)
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
