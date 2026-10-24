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
    return [head, cum, table];
  },
  async safety() {
    const d = await api("safety"), r = d.reports;
    if (!r) return [card("Crash reports", el("div", { class: "err" }, "Not available right now (" + (d.reports_error || "no data") + ")."), stale(d))];
    const total = card("Crash reports filed by driverless-system operators (NHTSA Standing General Order), per month",
      ...linesChart([{ name: "Reports a month", points: r.total }, { name: "12-month total", points: r.total_12m, axis: "left", dashed: true, color: css("--hold") }], v => num(v)), asOf(d), stale(d),
      note("Every incident an operator must report, however minor and whoever caused it, so the count rises with miles driven; it is a measure of exposure as much as of safety. " + num(r.n) + " reports in all."));
    const ents = Object.keys(r.entities), last12 = ents.map(e => r.entities[e].slice(-12).reduce((a, b) => a + b, 0));
    const by = card("Last 12 months by reporting entity", ...svgBars(ents, [{ name: "Reports", values: last12, color: css("--s1") }], { yFmt: v => Math.round(v), labelW: 80 }));
    return [total, by];
  },
};
window.TOPIC = { VIEWS };
})();
