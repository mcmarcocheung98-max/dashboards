"""Signals: the owner's approved signal per dashboard, with its watch point, gathered in one place.

Contract for a dashboard module:  SIGNALS() -> [{"key", "label", "tab", "value", "unit"?, "lean": +1/0/-1, "watch", "crossed": bool, "note"?}]
one row per key in data/signals/watchlist.json for that dashboard, read from cached payloads only (like READINGS). Until a module
implements SIGNALS, its watchlist rows show as "not wired yet" and its first READINGS stand in on the front page.

Served by the Signals dashboard (app/topics/signals.py): board (everything), front (one line per dashboard for the index page),
watch (every watch point), flips (what flipped since yesterday across dashboards) and newsletter (subject, html, text).
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from . import topics
from .cache import _cached
from .config import DATA_DIR

WATCHLIST = DATA_DIR / "signals" / "watchlist.json"
SITE = "https://dashboards-production-bde6.up.railway.app"
SKIP = {"signals", "status", "graphify",
        "btc-cycles", "altcoins"}         # the owner left the crypto dashboards out of signals for now (3 Nov 2026)


def watchlist() -> dict:
    d = json.loads(WATCHLIST.read_text())
    return {k: v for k, v in d.items() if isinstance(v, list)}


def _rows(slug: str, fn_name: str) -> list[dict]:
    fn = getattr(topics.module(slug), fn_name, None)
    if not fn:
        return []
    try:
        return [r for r in fn() or [] if isinstance(r, dict)]
    except Exception:
        return []


def collect() -> dict:
    """Every public dashboard: its watchlist rows (wired or not), any extra SIGNALS, and its first readings as a fallback."""
    wl = watchlist()
    out = []
    for slug, t in topics.public().items():
        if slug in SKIP:
            continue
        sig = {s.get("key"): s for s in _rows(slug, "SIGNALS")}
        rows = []
        for w in wl.get(slug, []):
            s = sig.pop(w["key"], None)
            rows.append({"slug": slug, "key": w["key"], "label": w["signal"], "watch": w["watch"], "wired": bool(s),
                         **({k: s.get(k) for k in ("tab", "value", "unit", "lean", "crossed", "note")} if s else {"lean": 0, "crossed": False, "value": None})})
        for s in sig.values():                               # signals a module adds beyond the approved list
            rows.append({"slug": slug, "wired": True, "label": s.get("label"), "watch": s.get("watch", ""), **{k: s.get(k) for k in ("key", "tab", "value", "unit", "lean", "crossed", "note")}})
        readings = _rows(slug, "READINGS")[:3]
        out.append({"slug": slug, "title": t.title, "category": topics.category(slug), "url": f"{SITE}/{slug}", "signals": rows,
                    "readings": readings, "wired": sum(1 for r in rows if r.get("wired")), "crossed": sum(1 for r in rows if r.get("crossed"))})
    return {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "dashboards": out,
            "totals": {"dashboards": len(out), "signals": sum(len(d["signals"]) for d in out), "wired": sum(d["wired"] for d in out), "crossed": sum(d["crossed"] for d in out)}}


def board() -> dict:
    return _cached("signals.board", 300, collect)


def top(d: dict) -> dict | None:
    """The one line for a dashboard: a crossed watch point first, then the first wired signal, then its first reading."""
    for r in d["signals"]:
        if r.get("crossed"):
            return {**r, "kind": "crossed"}
    for r in d["signals"]:
        if r.get("wired") and r.get("value") is not None:
            return {**r, "kind": "signal"}
    for r in d["readings"]:
        return {"slug": d["slug"], "label": r.get("label"), "value": r.get("value"), "lean": r.get("lean", 0), "note": r.get("note"), "kind": "reading", "crossed": False}
    return None


def front() -> dict:
    b = board()
    return {"updated": b["updated"], "crossed": b["totals"]["crossed"], "dashboards": {d["slug"]: top(d) for d in b["dashboards"]}}


def flips() -> dict:
    out = []
    for d in board()["dashboards"]:
        try:
            ch = topics.changes(d["slug"])
        except Exception:
            continue
        for f in ch.get("flipped", []):
            out.append({"slug": d["slug"], "title": d["title"], "url": d["url"], **f})
        since = ch.get("since")
    return {"flipped": out, "updated": board()["updated"]}


def fmt(v, unit=None) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        s = f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")
        return s + (unit or "")
    return str(v) + (unit or "")


ARROW = {1: ("▲", "#1f9d63"), -1: ("▼", "#d6453d"), 0: ("•", "#8a8984")}


def newsletter() -> dict:
    """Today's email: watch points crossed, one signal per dashboard, what flipped since yesterday, the dev agent's latest note and
    proposals, and the owner's open actions."""
    b, fl = board(), flips()
    day = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
    crossed = [r for d in b["dashboards"] for r in d["signals"] if r.get("crossed")]
    tops = [(d, top(d)) for d in b["dashboards"]]
    try:
        from .topics import status as st
        actions = [a for a in st.items()["actions"] if a.get("status") == "open"]
        nt = st.notes()
        dev = nt["notes"][0] if nt["notes"] and nt["last_note_days"] is not None and nt["last_note_days"] <= 2 else None
        props = nt["proposals"]
    except Exception:
        actions, dev, props = [], None, []
    subject = f"Dashboards: {len(crossed)} watch point{'s' if len(crossed) != 1 else ''} crossed, {len(fl['flipped'])} flipped · {day}"
    e = html.escape
    row = lambda cells: "<tr>" + "".join(f'<td style="padding:6px 8px;border-bottom:1px solid #e6e5e1;font-size:14px;vertical-align:top">{c}</td>' for c in cells) + "</tr>"
    arrow = lambda lean: f'<span style="color:{ARROW.get(lean, ARROW[0])[1]};font-weight:700">{ARROW.get(lean, ARROW[0])[0]}</span>'
    parts = [f'<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;color:#141413;background:#ffffff;padding:16px">',
             f'<div style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#8a8984">Dashboards · daily signals</div>',
             f'<h1 style="font-size:22px;margin:4px 0 12px">{e(day)}</h1>']
    if crossed:
        parts.append('<h2 style="font-size:16px;margin:16px 0 6px;color:#d6453d">Watch points crossed</h2><table style="border-collapse:collapse;width:100%">')
        for r in crossed:
            parts.append(row([f'<a href="{SITE}/{r["slug"]}" style="color:#2a78d6;text-decoration:none"><b>{e(topics.REGISTRY[r["slug"]].title)}</b></a>', f'{arrow(r.get("lean", 0))} {e(r["label"])}: <b>{e(fmt(r.get("value"), r.get("unit")))}</b>', f'<span style="color:#8a8984">watch: {e(r.get("watch", ""))}</span>']))
        parts.append("</table>")
    else:
        parts.append('<p style="font-size:14px;color:#52514e">No watch point crossed.</p>')
    parts.append('<h2 style="font-size:16px;margin:18px 0 6px">One signal per dashboard</h2><table style="border-collapse:collapse;width:100%">')
    for d, tp in tops:
        if not tp:
            parts.append(row([f'<a href="{d["url"]}" style="color:#2a78d6;text-decoration:none"><b>{e(d["title"])}</b></a>', '<span style="color:#8a8984">no signal yet</span>', ""]))
            continue
        why = "" if tp["kind"] != "reading" else '<span style="color:#8a8984">(reading; signals not wired yet)</span>'
        parts.append(row([f'<a href="{d["url"]}" style="color:#2a78d6;text-decoration:none"><b>{e(d["title"])}</b></a>', f'{arrow(tp.get("lean", 0))} {e(tp.get("label") or "")}: <b>{e(fmt(tp.get("value"), tp.get("unit")))}</b> {why}', f'<span style="color:#8a8984">{e(tp.get("watch") or tp.get("note") or "")}</span>']))
    parts.append("</table>")
    if fl["flipped"]:
        parts.append('<h2 style="font-size:16px;margin:18px 0 6px">Flipped since yesterday</h2><table style="border-collapse:collapse;width:100%">')
        for f in fl["flipped"][:20]:
            parts.append(row([f'<a href="{f["url"]}#{e(str(f.get("tab", "")))}" style="color:#2a78d6;text-decoration:none">{e(f["title"])}</a>', f'{arrow(f.get("lean", 0))} {e(f.get("label", ""))}: {e(fmt(f.get("was")))} → <b>{e(fmt(f.get("value")))}</b>', ""]))
        parts.append("</table>")
    if dev or props:
        parts.append('<h2 style="font-size:16px;margin:18px 0 6px">From the dev agent</h2>')
        if dev:
            parts.append(f'<p style="font-size:14px;margin:0 0 6px"><b>{e(dev["title"])}</b> <span style="color:#8a8984">({e(dev["date"])})</span><br>{e(dev.get("summary", ""))}</p>')
            if dev.get("changes"):
                parts.append('<ul style="padding-left:18px;font-size:14px;margin:0">' + "".join(f'<li style="margin:3px 0"><b>{e(c.get("dashboard") or c.get("slug") or "Site")}</b>: {e(c.get("what", ""))}</li>' for c in dev["changes"][:8]) + "</ul>")
            if dev.get("next"):
                parts.append(f'<p style="font-size:13.5px;margin:6px 0"><b>Next:</b> {e(" · ".join(dev["next"]))}</p>')
        if props:
            parts.append(f'<p style="font-size:13.5px;margin:6px 0;color:#b15c00"><b>Waiting for your OK ({len(props)}):</b> ' + e(" · ".join(r["title"] for r in props[:5])) + "</p>")
        parts.append(f'<p style="font-size:13px"><a href="{SITE}/status#notes" style="color:#2a78d6">All dev notes →</a></p>')
    if actions:
        parts.append(f'<h2 style="font-size:16px;margin:18px 0 6px">Only you can do ({len(actions)})</h2><ul style="padding-left:18px;font-size:14px;margin:0">' + "".join(f'<li style="margin:3px 0">{e(a["title"])} <span style="color:#8a8984">({e(a.get("priority", ""))}, open since {e(a.get("since", ""))})</span></li>' for a in actions[:6]) + f'</ul><p style="font-size:13px"><a href="{SITE}/status" style="color:#2a78d6">All actions and the roadmap →</a></p>')
    parts.append(f'<p style="font-size:12px;color:#8a8984;margin-top:20px;border-top:1px solid #e6e5e1;padding-top:10px">Sent by the dashboards site from its own data, {e(b["updated"])}. <a href="{SITE}/signals" style="color:#8a8984">Signals page</a> · <a href="{SITE}" style="color:#8a8984">All dashboards</a>. Not investment advice.</p></div>')
    text = [subject, ""]
    if crossed:
        text += ["WATCH POINTS CROSSED"] + [f"- {topics.REGISTRY[r['slug']].title}: {r['label']} = {fmt(r.get('value'), r.get('unit'))} (watch: {r.get('watch', '')})" for r in crossed] + [""]
    text += ["ONE SIGNAL PER DASHBOARD"] + [f"- {d['title']}: {tp['label']} = {fmt(tp.get('value'), tp.get('unit'))}" if tp else f"- {d['title']}: no signal yet" for d, tp in tops] + [""]
    if fl["flipped"]:
        text += ["FLIPPED SINCE YESTERDAY"] + [f"- {f['title']}: {f.get('label')} {fmt(f.get('was'))} -> {fmt(f.get('value'))}" for f in fl["flipped"][:20]] + [""]
    if dev:
        text += ["FROM THE DEV AGENT", f"{dev['title']} ({dev['date']})", dev.get("summary", "")] + [f"- {c.get('dashboard') or c.get('slug') or 'Site'}: {c.get('what', '')}" for c in dev.get("changes", [])[:8]]
        text += ([f"Next: {' · '.join(dev['next'])}"] if dev.get("next") else []) + [""]
    if props:
        text += [f"WAITING FOR YOUR OK ({len(props)})"] + [f"- {r['title']}" for r in props[:5]] + [f"{SITE}/status#notes", ""]
    if actions:
        text += [f"ONLY YOU CAN DO ({len(actions)})"] + [f"- {a['title']}" for a in actions[:6]] + [f"{SITE}/status", ""]
    text.append(f"{SITE}/signals")
    return {"subject": subject, "html": "".join(parts), "text": "\n".join(text), "crossed": len(crossed), "flipped": len(fl["flipped"])}
