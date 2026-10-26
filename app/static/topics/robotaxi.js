// Autonomous cars and the energy transition: tabs and cards. Data from /api/robotaxi/<rides|footprint|safety|tesla|energy>.
(() => {
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const q = ts => { const d = new Date(ts * 1000); return "Q" + (Math.floor(d.getUTCMonth() / 3) + 1) + " " + d.getUTCFullYear(); };
const qLabel = iso => q(Date.parse(iso) / 1000);
const VIEWS = {
  async rides() {
    const d = await api("rides"), L = d.latest || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(L).map(([k, v]) => kpi(k + " · paid rides a week (" + dateOf(v.date) + ")", big(v.value)))), asOf(d));
    const weekly = card("Paid driverless rides per week, as announced", ...linesChart(Object.entries(d.weekly || {}).map(([k, pts]) => ({ name: k, points: pts })), v => big(v)),
      note("Operator announcements; lines join announcements. Waymo's figures are paid rides, US-wide across its cities. Baidu Apollo Go's are fully driverless operational rides from its quarterly results, two of them peak weeks rather than averages."), cite(d.cited));
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
    const cpuc = cp.length ? card("California: completed driverless passenger trips per quarter (CPUC)", ...linesChart(cp.map(([k, pts]) => ({ name: k, points: pts })), v => big(v), { small: true }),
      note("Sum of the monthly TotalTrips each carrier files with the CPUC (driverless deployment programme), complete quarters only. Filed about five weeks after each quarter."), stale(d))
      : card("California CPUC trips", el("div", { class: "muted" }, d.cpuc_error ? "Not available right now (" + d.cpuc_error + ")." : "No quarters yet: the CPUC deployment files are read a few at a time, so the first quarters appear within the hour."), stale(d));
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
      note("Reports the operator filed since the order took effect (Jul 2021) up to that date, divided by the driverless miles it had published by then (data/robotaxi/miles.csv). For scale, not a like-for-like comparison with human drivers: every minor contact is reportable, whoever caused it."))
      : card("Reports per mile", el("div", { class: "muted" }, r.archived === false ? "NHTSA's archive of reports before June 2025 could not be loaded, so reports to date would be undercounted; the rate is hidden until it loads."
        : "Add operators' published driverless miles to data/robotaxi/miles.csv to turn counts into a rate."));
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
    const C = d.correlation, cr = C && C.rows ? C.rows.filter(x => x.r != null).sort((a, b) => Math.abs(b.r) - Math.abs(a.r)) : [];
    const corr = cr.length ? card("Which Tesla figures move with the share price", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Figure", "Compared as", "r", "Quarters"].map(h => el("th", {}, h))),
      ...cr.map(x => el("tr", {}, el("td", {}, x.metric), el("td", { class: "wrap" }, x.basis), el("td", {}, x.r.toFixed(2)), el("td", {}, x.n + " (" + qLabel(x.from) + " to " + qLabel(x.to) + ")"))))),
      note("Pearson correlation, −1 to 1, between each quarterly figure (data/robotaxi/tesla.csv, from Tesla's releases) and TSLA's close at the quarter's end, its change on a year or on the quarter, or its move on the day of the production and deliveries release (the 2nd of the following month, or the next trading day). With 10 to 15 quarters, an r below about 0.5 in size is indistinguishable from chance, and levels of two rising series correlate whether or not one drives the other. The figures come out after the quarter's last close, so this shows what moved together, not what predicts the price."))
      : d.correlation_error ? card("Which Tesla figures move with the share price", el("div", { class: "err" }, "Not available right now (" + d.correlation_error + ").")) : null;
    const S = d.signal, st = S && S.stats;
    const sig = st ? card("Fundamentals signal against the share price, backtested",
      el("div", { class: "kpis" }, kpi("Signal now", S.events[S.events.length - 1].signal.toFixed(2) + (S.events[S.events.length - 1].long ? " · hold TSLA" : " · cash")),
        kpi("Signal strategy, total", pct(st.strategy.total, 0), cls(st.strategy.total)), kpi("Buy and hold, total", pct(st.buy_hold.total, 0), cls(st.buy_hold.total)),
        kpi("Strategy a year / buy and hold", pct(st.strategy.cagr, 0) + " / " + pct(st.buy_hold.cagr, 0)),
        kpi("Worst fall: strategy / buy and hold", pct(st.strategy.max_drawdown, 0) + " / " + pct(st.buy_hold.max_drawdown, 0)),
        kpi("Calls right", st.hits + " of " + st.periods), kpi("Time in TSLA", pct(st.invested, 0))),
      ...linesChart([{ name: "TSLA", points: d.tsla.filter(p => p[0] >= S.hold[0][0]) }, { name: "$ in the signal strategy (starts at the TSLA price)", points: S.equity, color: css("--s2") },
        { name: "Signal (left axis, −1 to 1)", points: S.signal, axis: "left", bar: true, fmt: v => v.toFixed(2) }], v => usd(v, 0), { log: true }),
      el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Figures out", "Signal", "Position", "TSLA to the next date"].map(h => el("th", {}, h))),
        ...S.events.slice().reverse().map(e => el("tr", {}, el("td", {}, dateOf(e.date)), el("td", {}, e.signal.toFixed(2)), el("td", {}, e.long ? "TSLA" : "cash"),
          el("td", { class: cls(e.tsla_next) }, e.tsla_next == null ? "–" : pct(e.tsla_next, 1)))))),
      note("Each Tesla figure in the table above votes +1 if better than a year earlier and −1 if worse (deliveries, production, storage, revenue and FSD subscriptions by % change; margins, EPS and cash flow by level). The signal is the mean vote, recomputed on each day a figure becomes public: deliveries, production and storage on the 2nd of the month after the quarter, the financials 35 days after the quarter (after Tesla's results). Strategy: hold TSLA from the next trading day while the signal is above " + S.threshold + ", otherwise cash earning nothing, 0.1% per switch. " +
        st.years + " years and " + st.periods + " calls: too few to tell skill from luck, and the rule was chosen after seeing the data, so read it as a description, not a forecast."))
      : d.signal_error ? card("Fundamentals signal", el("div", { class: "err" }, "Not available right now (" + d.signal_error + ").")) : null;
    return [head, px, el("div", { class: "grid2" }, qc, fsd), sig, corr, ms];
  },
  async energy() {
    const d = await api("energy"), E = d.ev || {}, P = d.power || {}, M = d.ev_ember || {};
    const short = k => k.split(" (")[0];
    const head = card(null, el("div", { class: "kpis" },
      ...Object.entries(M.latest || {}).map(([m, v]) => kpi(m + ": electric share of new cars, 12 months to " + dateOf(v.month).replace(/^\d+ /, ""), v.r12.toFixed(1) + "%",
        v.r12_year_ago == null ? "" : cls(v.r12 - v.r12_year_ago))),
      ...Object.entries(P.latest || {}).map(([m, v]) => kpi(m + ": wind + solar share of electricity, " + v.year, v.share.toFixed(1) + "%"))), asOf(d), stale(d));
    const ev = card("Electric share of new cars, by year: each country's official measure", ...linesChart(Object.entries(E.yearly || {}).map(([k, pts]) => ({ name: short(k), points: pts })), v => v.toFixed(1) + "%", { sync: false }),
      note("Definitions differ: UK battery-electric and plug-in (SMMT registrations); China new energy vehicles including plug-in hybrids and range-extenders (CPCA retail); US battery-electric (Cox Automotive / Kelley Blue Book) and plug-in (DOE / Argonne); Hong Kong electric share of newly registered private cars (government papers). UK 2026 is January to September. Hong Kong 2026 is left out: the figures since its EV tax concession ended on 31 March conflict."),
      el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Latest", "Market", "Measure", "Share", "Source"].map(h => el("th", {}, h))),
        ...(E.months || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.market), el("td", { class: "wrap" }, r.measure), el("td", {}, (+r.value).toFixed(1) + "%"),
          el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : ""))))));
    const mr = Object.entries(M.r12 || {});
    const evm = mr.length ? card("Electric share of new cars, rolling 12 months (Ember)", ...linesChart(mr.map(([m, pts]) => ({ name: m, points: pts })), v => v.toFixed(1) + "%"),
      note("Battery-electric plus plug-in hybrid cars as a share of new car registrations, the last 12 months at each month, from Ember's EV sales data (CC BY 4.0), which compiles SMMT, CPCA, Hong Kong's Transport Department and US sources into one definition. The yearly chart below keeps each country's own official measure."), stale(d))
      : d.ev_ember_error ? card("Electric share of new cars, by month", el("div", { class: "err" }, "Not available right now (" + d.ev_ember_error + ").")) : null;
    const py = Object.entries(P.yearly || {});
    const pw = py.length ? card("Wind and solar share of electricity generation, by year (Ember)", ...linesChart(py.map(([m, pts]) => ({ name: m, points: pts })), v => v.toFixed(1) + "%", { sync: false }),
      note("Ember's yearly electricity data (CC BY 4.0): solar + wind generation as a share of all generation. Batteries store rather than generate, so they are not in it. The yearly charts show every year whatever the date buttons say."), stale(d))
      : card("Wind and solar share of electricity", el("div", { class: "err" }, "Not available right now (" + (d.power_error || "no data") + ")."), stale(d));
    const pm = Object.entries(P.monthly || {});
    const monthly = pm.length ? card("Wind and solar share, by month (Ember, last five years)", ...linesChart(pm.map(([m, pts]) => ({ name: m, points: pts })), v => v.toFixed(1) + "%", { small: true }),
      note("Monthly shares swing with the seasons (more solar in summer, more wind in winter): compare a month with the same month a year earlier.")) : null;
    const checks = card("Cross-checks: the official figures", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Year", "Market", "Measure", "Value", "Source"].map(h => el("th", {}, h))),
      ...(d.checks || []).map(r => el("tr", {}, el("td", {}, r.date.slice(0, 4)), el("td", {}, r.market), el("td", { class: "wrap" }, r.measure), el("td", {}, r.value + "%"),
        el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : ""))))),
      note("EIA (US), DESNZ Energy Trends (UK), Ember's Global Electricity Review (China) and the Hong Kong government, which publishes a zero-carbon share rather than wind and solar. Kept in data/robotaxi/power_checks.csv."));
    return [head, evm, ev, pw, monthly, checks];
  },
};
window.TOPIC = { VIEWS };
})();
