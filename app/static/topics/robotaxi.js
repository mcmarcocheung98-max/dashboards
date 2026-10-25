// Autonomous car adoption: tabs and cards. Data from /api/robotaxi/<rides|footprint|safety>.
(() => {
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const q = ts => { const d = new Date(ts * 1000); return "Q" + (Math.floor(d.getUTCMonth() / 3) + 1) + " " + d.getUTCFullYear(); };
const VIEWS = {
  async rides() {
    const d = await api("rides"), L = d.latest || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(L).map(([k, v]) => kpi(k + " · paid rides a week (" + dateOf(v.date) + ")", big(v.value)))), asOf(d));
    const weekly = card("Paid driverless rides per week, as announced", ...linesChart(Object.entries(d.weekly || {}).map(([k, pts]) => ({ name: k, points: pts })), v => big(v)),
      note("Operator announcements; lines join announcements. Waymo's figures are US-wide across its cities."), cite(d.cited));
    const qs = Object.entries(d.quarterly || {});
    const quarterly = qs.length ? card("Fully driverless rides per quarter (operators that report quarterly)",
      ...svgBars(qs[0][1].map(p => q(p[0])), qs.map((x, i) => ({ name: x[0], values: x[1].map(p => p[1]), color: css(SERIES[i % SERIES.length]) })), { yFmt: v => big(v), labelW: 60 })) : null;
    const rows = (d.rows || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.series), el("td", {}, big(+r.value)), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "")));
    const table = card("Announcements", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "Operator", "Rides", "Source"].map(h => el("th", {}, h))), ...rows)),
      note("Add a row to data/robotaxi/rides.csv (weekly) or rides_quarterly.csv when an operator announces a figure."));
    return [head, weekly, quarterly, table];
  },
  async footprint() {
    const d = await api("footprint");
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(d.by_operator || {}).map(([k, v]) => kpi(k + " · cities", v))), asOf(d));
    const cum = card("Cities with public driverless rides, cumulative by operator", ...linesChart(Object.entries(d.cumulative || {}).map(([k, pts]) => ({ name: k, points: pts })), v => Math.round(v), { small: true }));
    const rows = (d.rows || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.operator), el("td", {}, r.city + ", " + r.country), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "")));
    const table = card("Where", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Opened to the public", "Operator", "City", "Source"].map(h => el("th", {}, h))), ...rows)),
      note("Fully driverless service open to the general public (not employee or invite-only pilots unless noted). Kept in data/robotaxi/cities.csv."));
    const reg = card("Rules, licences and pilots: US, UK, Hong Kong, China", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "Market", "What happened", "Source"].map(h => el("th", {}, h))),
      ...(d.regulation || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.market), el("td", { class: "wrap" }, r.event), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : ""))))),
      note("Kept in data/robotaxi/regulation.csv."));
    const cp = Object.entries(d.cpuc || {});
    const cpuc = cp.length ? card("California: driverless passenger trips per quarter (CPUC)", ...linesChart(cp.map(([k, pts]) => ({ name: k, points: pts })), v => big(v), { small: true }))
      : card("California CPUC trips", el("div", { class: "muted" }, "No quarters entered yet: the CPUC publishes these as spreadsheets at changing addresses; add them to data/robotaxi/cpuc_trips.csv."));
    return [head, cum, table, reg, cpuc];
  },
  async safety() {
    const d = await api("safety"), r = d.reports;
    if (!r) return [card("Crash reports", el("div", { class: "err" }, "Not available right now (" + (d.reports_error || "no data") + ")."), stale(d))];
    const total = card("Crash reports filed by driverless-system operators (NHTSA Standing General Order), per month",
      ...linesChart([{ name: "Reports a month", points: r.total }, { name: "12-month total", points: r.total_12m, axis: "left", dashed: true, color: css("--hold") }], v => num(v)), asOf(d), stale(d),
      note("Every incident an operator must report, however minor and whoever caused it, so the count rises with miles driven; it is a measure of exposure as much as of safety. " + num(r.n) + " reports in all."));
    const ents = Object.keys(r.entities), last12 = ents.map(e => r.entities[e].slice(-12).reduce((a, b) => a + b, 0));
    const by = card("Last 12 months by reporting entity", ...svgBars(ents, [{ name: "Reports", values: last12, color: css("--s1") }], { yFmt: v => Math.round(v), labelW: 80 }));
    const rate = r.rate && r.rate.length ? card("Crash reports per million driverless miles", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Operator", "Miles to date", "Reports to date", "Per million miles", "As of"].map(h => el("th", {}, h))),
      ...r.rate.map(x => el("tr", {}, el("td", {}, x.operator), el("td", {}, big(x.miles)), el("td", {}, num(x.reports)), el("td", {}, x.per_million.toFixed(2)), el("td", {}, x.date))))),
      note("Cumulative reports since the order took effect (Jul 2021) divided by cumulative rider-only miles the operator has published (data/robotaxi/miles.csv). For scale, not a like-for-like comparison with human drivers: every minor contact is reportable."))
      : card("Reports per mile", el("div", { class: "muted" }, "Add operators' published driverless miles to data/robotaxi/miles.csv to turn counts into a rate."));
    return [total, by, rate];
  },
  async tesla() {
    const d = await api("tesla"), K = d.kpi || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("TSLA", K.tsla == null ? "–" : usd(K.tsla, 2)), kpi("TSLA, 1 year", pct(K.tsla_1y, 0), cls(K.tsla_1y)),
      kpi("Deliveries, latest quarter", big(K.deliveries_last)), kpi("vs a year earlier", pct(K.yoy, 0), cls(K.yoy)), kpi("Deliveries, last 4 quarters", big(K.ttm)),
      kpi("FSD markets in the list", (d.fsd_markets || []).length)), missing(d, "tsla", "The TSLA price (Yahoo)"), asOf(d), stale(d));
    const px = d.tsla ? card("TSLA share price", ...linesChart([{ name: "TSLA", points: d.tsla }], v => usd(v, 0), { log: true })) : null;
    const q = Object.entries(d.quarterly || {}).filter(([, p]) => p.length);
    const qc = q.length ? card("Quarterly deliveries (hand-entered from Tesla's releases)", ...svgBars(q[0][1].map(p => { const t = new Date(p[0] * 1000); return "Q" + (Math.floor(t.getUTCMonth() / 3) + 1) + " " + String(t.getUTCFullYear()).slice(2); }),
      q.map(([k, pts], i) => ({ name: k, values: pts.map(p => p[1]), color: css(SERIES[i]) })), { yFmt: v => big(v), labelW: 50 })) : null;
    const fm = d.fsd_miles || [];
    const fsd = fm.length >= 2 ? card("FSD (Supervised) cumulative miles", ...linesChart([{ name: "Miles", points: fm }], v => big(v), { small: true }), note("As published on tesla.com/fsd; one row per reading in data/robotaxi/tesla.csv."))
      : fm.length ? card("FSD (Supervised) cumulative miles", el("div", { class: "kpis" }, kpi("Miles as of " + new Date(fm[0][0] * 1000).toISOString().slice(0, 10), big(fm[0][1]))), note("Add later readings from tesla.com/fsd to data/robotaxi/tesla.csv to draw the line.")) : null;
    const ms = card("Autonomy milestones: Robotaxi, Cybercab, FSD by country (incl. UK and Hong Kong status)", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "Area", "Market", "What happened", "Source"].map(h => el("th", {}, h))),
      ...(d.milestones || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.area), el("td", {}, r.market), el("td", { class: "wrap" }, r.event), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : ""))))),
      note("Rows marked 'verify' were written from memory: check them against Tesla's own posts. Kept in data/robotaxi/tesla_milestones.csv."));
    return [head, px, el("div", { class: "grid2" }, qc, fsd), ms];
  },
};
window.TOPIC = { VIEWS };
})();
