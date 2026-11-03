// Signals: tabs and cards. Data from /api/signals/<board|watch|flips|newsletter>; helpers from topic.html.
(() => {
const AR = { 1: ["▲", "--up"], "-1": ["▼", "--down"], 0: ["•", "--muted"] };
const arrow = l => { const [t, c] = AR[String(l || 0)] || AR[0]; return el("span", { style: `color:var(${c});font-weight:700` }, t + " "); };
const fmt = (v, u) => v == null ? "–" : typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "number" ? num(v, Math.abs(v) >= 100 || Number.isInteger(v) ? 0 : 2) + (u || "") : String(v) + (u || "");
const crossedPill = () => el("span", { class: "pill bad", style: "font-weight:600" }, "watch point crossed");
const sigRow = r => el("div", { style: "display:grid;grid-template-columns:1fr auto;gap:6px 12px;padding:7px 0;border-top:1px solid var(--line);align-items:baseline" },
  el("div", {}, arrow(r.lean), r.label, el("div", { class: "muted", style: "font-size:12.5px" }, "watch: " + (r.watch || "–"), r.note ? " · " + r.note : "")),
  el("div", { style: "text-align:right;white-space:nowrap" }, r.wired ? el("b", { style: `color:var(${(AR[String(r.lean || 0)] || AR[0])[1]})` }, fmt(r.value, r.unit)) : el("span", { class: "pill" }, "not wired yet"), r.crossed ? el("div", {}, crossedPill()) : null));

const VIEWS = {
  async board() {
    const d = await api("board"); const T = d.totals;
    const head = card(null, el("div", { class: "kpis" }, kpi("Watch points crossed", T.crossed, T.crossed ? "down" : "up"), kpi("Signals wired", T.wired + " of " + T.signals), kpi("Dashboards", T.dashboards)),
      note("Updated " + d.updated + ". Each card is one dashboard: its approved signals, their current values, and the watch point that would change the reading. Red pill: a watch point is crossed right now."));
    const crossed = d.dashboards.flatMap(x => x.signals.filter(s => s.crossed).map(s => ({ ...s, title: x.title, url: x.url })));
    const alert = crossed.length ? card("Crossed now", ...crossed.map(s => el("div", { style: "padding:6px 0;border-top:1px solid var(--line)" }, el("a", { href: "/" + s.slug + (s.tab ? "#" + s.tab : "") }, el("b", {}, s.title)), ": ", arrow(s.lean), s.label, " = ", el("b", {}, fmt(s.value, s.unit)), el("span", { class: "muted" }, " · watch: " + s.watch)))) : null;
    const cards = d.dashboards.map(x => card(null, el("div", { style: "display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline" }, el("a", { href: x.url.replace(/^https?:\/\/[^/]+/, ""), style: "font-weight:650;font-size:15px;text-decoration:none;color:var(--ink)" }, x.title), el("span", { class: "muted", style: "font-size:12px" }, x.category + " · " + x.wired + "/" + x.signals.length + " wired")),
      ...x.signals.map(sigRow),
      !x.wired && x.readings.length ? el("div", { class: "muted", style: "margin-top:8px;font-size:12.5px" }, "Meanwhile, its readings: " + x.readings.map(r => r.label + " " + fmt(r.value)).join(" · ")) : null));
    return [head, alert, el("div", { class: "grid2" }, ...cards)];
  },
  async watch() {
    const d = await api("watch"); const rows = d.dashboards.flatMap(x => x.signals.map(s => ({ ...s, title: x.title })));
    rows.sort((a, b) => (b.crossed - a.crossed) || (b.wired - a.wired));
    return [card("Every watch point (" + rows.length + ")", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Dashboard", "Signal", "Now", "Watch point", "Status"].map(h => el("th", {}, h))),
      ...rows.map(r => el("tr", {}, el("td", {}, r.title), el("td", { class: "wrap" }, r.label), el("td", {}, r.wired ? fmt(r.value, r.unit) : "–"), el("td", { class: "wrap" }, r.watch), el("td", {}, r.crossed ? crossedPill() : r.wired ? el("span", { class: "pill ok" }, "watching") : el("span", { class: "pill" }, "not wired yet")))))),
      note("Approved on " + (d.approved || "2026-11-03") + ". A dashboard wires a signal by adding it to its SIGNALS() from the data it already caches; the daily check reports any watch point crossed."))];
  },
  async flips() {
    const d = await api("flips"); const F = d.flipped || [];
    return [card(F.length ? F.length + " readings flipped since yesterday" : "Nothing flipped since yesterday", ...F.map(f => el("div", { style: "padding:6px 0;border-top:1px solid var(--line)" },
      el("a", { href: "/" + f.slug + "#" + (f.tab || "") }, el("b", {}, f.title)), ": ", arrow(f.lean), f.label, " ", el("span", { class: "muted" }, fmt(f.was) + " → "), el("b", {}, fmt(f.value)), f.note ? el("span", { class: "muted" }, " · " + f.note) : null)),
      note("From each dashboard's daily snapshot (the 'what changed since yesterday' card). A flip is a reading whose lean changed overnight."))];
  },
  async newsletter() {
    const n = await api("newsletter");
    const frame = el("iframe", { srcdoc: n.html, sandbox: "allow-popups allow-popups-to-escape-sandbox", title: "Today's newsletter", style: "width:100%;height:900px;border:1px solid var(--line);border-radius:10px;background:#fff" });
    return [card("Today's email", el("div", { class: "kpis" }, kpi("Subject", n.subject), kpi("Watch points crossed", n.crossed, n.crossed ? "down" : "up"), kpi("Flipped", n.flipped)),
      note("Sent every morning at 07:35 London by the newsletter workflow (GitHub Actions) once the Gmail secrets are set; the daily check confirms it went. Preview below; the same email as a page is at /newsletter, the plain-text version at /api/signals/newsletter.")), card("Preview", frame)];
  },
};
window.TOPIC = { VIEWS };
})();
