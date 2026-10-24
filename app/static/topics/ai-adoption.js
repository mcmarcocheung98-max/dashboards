// AI tool & agent adoption: tabs and cards. Data from /api/ai-adoption/<firms|users|agents|skills>.
(() => {
const sh = v => v == null ? "–" : v.toFixed(1) + "%";
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const VIEWS = {
  async firms() {
    const d = await api("firms"), n = d.now || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("US businesses using AI", sh(n.btos)), kpi("A year earlier", sh(n.btos_year_ago)),
      kpi("Change", n.btos != null && n.btos_year_ago != null ? pp(n.btos - n.btos_year_ago) : "–", cls(n.btos - n.btos_year_ago)), kpi("Paying for AI tools (Ramp)", sh(n.ramp))), asOf(d), stale(d));
    const btos = card("Share of US businesses that used AI in the last two weeks",
      ...linesChart([{ name: "All businesses (Census BTOS)", points: d.btos_us || [] }, { name: "Paying for AI tools (Ramp AI Index)", points: d.ramp || [], color: css("--s2") }], sh),
      note("US Census Bureau Business Trends and Outlook Survey, asked every two weeks of about 1.2 million businesses; Ramp's index counts businesses on its card platform with a paid AI subscription."), cite(d.cited));
    const sec = Object.entries(d.btos_sectors || {}).filter(([, p]) => p.length);
    const sectors = sec.length ? card("By sector (latest)", ...svgBars(sec.map(([k]) => k), [{ name: "Using AI", values: sec.map(([, p]) => p[p.length - 1][1]), color: css("--s1") }], { yFmt: sh, labelW: 90 }))
      : card("By sector", el("div", { class: "muted" }, "No sector points entered yet: copy the sector rows of the BTOS workbook into data/ai-adoption/btos_ai_use_by_sector.csv."));
    return [head, btos, sectors];
  },
  async users() {
    const d = await api("users"), s = Object.entries(d.series || {}).filter(([, p]) => p.some(x => x[1] > 0));
    const chart = card("Reported users", ...linesChart(s.map(([k, pts]) => ({ name: k, points: pts.filter(p => p[1] > 0) })), v => big(v)), asOf(d),
      note("Each point is a company announcement; lines join announcements and say nothing about the months between."));
    const rows = (d.rows || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", { class: "wrap" }, r.series), el("td", {}, big(+r.value)), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "")));
    const table = card("Announcements", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "What", "Users", "Source"].map(h => el("th", {}, h))), ...rows)));
    return [chart, table];
  },
  async agents() {
    const d = await api("agents");
    const years = Object.keys(d.by_year || {});
    const bars = years.length ? card("Agent launches by year (from the list below)", ...svgBars(years, [{ name: "Launches", values: years.map(y => d.by_year[y]), color: css("--s1") }], { yFmt: v => Math.round(v), h: 160 })) : null;
    const tl = card("Timeline: agent products and protocols", el("div", { class: "tl" }, ...(d.rows || []).flatMap(r => [el("div", { class: "d" }, dateOf(r.date)),
      el("div", {}, link(r.event, r.source), " · ", el("span", { class: "muted" }, r.company + (r.kind ? " · " + r.kind : "") + (r.note ? " · " + r.note : "")))])), asOf(d),
      note("Hand-kept list, one row per launch, in data/ai-adoption/agent_milestones.csv."));
    return [bars, tl];
  },
  async skills() {
    const d = await api("skills"), L = d.latest || {};
    const chart = card("Share of job postings mentioning AI, by country", ...linesChart(Object.entries(d.share || {}).map(([k, pts]) => ({ name: k, points: pts, width: k === "US" || k === "GB" ? 2.5 : 1.2 })), sh), asOf(d), stale(d),
      note("Indeed AI Tracker (Indeed Hiring Lab, CC BY 4.0): postings whose text includes AI terms, as % of all postings, monthly average."));
    const table = card("Latest", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Country", "Now", "A year ago", "Two years ago"].map(h => el("th", {}, h))),
      ...Object.entries(L).sort((a, b) => b[1].share - a[1].share).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, sh(v.share)), el("td", {}, sh(v.year_ago)), el("td", {}, sh(v.two_years_ago)))))));
    return [chart, table];
  },
};
window.TOPIC = { VIEWS };
})();
