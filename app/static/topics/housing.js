// London Housing Index: tabs and cards. Data from /api/housing/<prices|market|afford>; helpers from topic.html.
(() => {
const pc = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
const VIEWS = {
  async prices() {
    const d = await api("prices"), n = d.now || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("London average price", gbp(n.avg)), kpi("Change on a year ago", pc(n.yoy), cls(n.yoy)),
      kpi("From the peak (" + (n.peak_month ? month(new Date(n.peak_month).getTime() / 1000) : "–") + ")", pct(n.from_peak), cls(n.from_peak)),
      kpi("5 years", pct(n.change_5y, 0), cls(n.change_5y)), kpi("10 years", pct(n.change_10y, 0), cls(n.change_10y))), asOf(d), stale(d));
    const real = card("London average price: as paid, and in today's money",
      ...linesChart([{ name: "Average price", points: d.london_avg || [] }, { name: "In today's money (CPIH)", points: d.london_real || [], dashed: true, color: css("--hold") }], v => gbp(v)),
      missing(d, "london_real", "The inflation-adjusted line"), note("HM Land Registry UK House Price Index, all property types, London. The dashed line restates each month's price in the money of the latest CPIH month."));
    const idx = card("London vs the UK (index, January 2015 = 100)",
      ...linesChart([{ name: "London", points: d.london_index || [] }, { name: "United Kingdom", points: d.uk_index || [], color: css("--s2") }], v => num(v, 0)),
      missing(d, "uk_index", "The UK line"));
    const yoy = card("Change on a year earlier", ...linesChart([{ name: "London", points: d.london_yoy || [] }, { name: "United Kingdom", points: d.uk_yoy || [], color: css("--s2") }], v => pc(v), { small: true }),
      note("Percentage change in the average price against the same month a year earlier."));
    return [head, real, idx, yoy];
  },
  async market() {
    const d = await api("market"), n = d.now || {}, t = d.by_type || {}, ty = d.by_type_yoy || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(n.types || {}).map(([k, v]) => kpi(k, gbp(v))),
      kpi("Sales in " + (n.volume_month ? month(new Date(n.volume_month).getTime() / 1000) : "last month"), num(n.volume_last)),
      kpi("Sales, last 12 months", num(n.volume_12m) + (n.volume_12m_prev ? " (" + pct(n.volume_12m / n.volume_12m_prev - 1, 0) + " on the year before)" : ""))), asOf(d), stale(d));
    const types = card("Average price by property type", ...linesChart(Object.entries(t).map(([k, pts]) => ({ name: k, points: pts })), v => gbp(v)), missing(d, "by_type"));
    const yoy = card("Change on a year earlier, by type", ...linesChart(Object.entries(ty).map(([k, pts]) => ({ name: k, points: pts })), v => pc(v), { small: true }));
    const vol = card("Sales volume (completed transactions registered)", ...linesChart([{ name: "Sales a month", points: d.volume || [] }, { name: "12-month total", points: d.volume_12m || [], axis: "left", dashed: true, color: css("--hold") }], v => num(v)),
      note("The most recent months are revised up as late registrations arrive: read the last two or three months as provisional."));
    return [head, types, yoy, vol];
  },
  async afford() {
    const d = await api("afford"), n = d.now || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("Bank Rate", n.bank_rate == null ? "–" : n.bank_rate.toFixed(2) + "%"),
      kpi("Price to earnings", n.price_to_earnings == null ? "–" : n.price_to_earnings.toFixed(1) + "×"), kpi("Highest ratio seen", n.pe_peak == null ? "–" : n.pe_peak.toFixed(1) + "×"),
      kpi("Illustrative mortgage a month", gbp(n.mortgage))), asOf(d), stale(d));
    const pe = card("London average price ÷ UK average annual pay", ...linesChart([{ name: "Price to earnings", points: d.price_to_earnings || [] }], v => v == null ? "–" : v.toFixed(1) + "×"),
      missing(d, "price_to_earnings", "The ratio"), note("Pay is UK-wide regular weekly earnings × 52 (ONS KAB9), which is lower than London pay, so the ratio overstates London's by roughly a fifth; the trend is what matters."));
    const br = card("Bank Rate", ...linesChart([{ name: "Bank Rate", points: d.bank_rate || [] }], v => v == null ? "–" : v.toFixed(2) + "%", { small: true }), missing(d, "bank_rate", "Bank Rate"));
    const mg = card("What a mortgage on the average London home would cost a month (illustration)",
      ...linesChart([{ name: "Monthly payment", points: d.mortgage || [] }, { name: "Annual pay ÷ 12", points: (d.earnings_annual || []).map(p => [p[0], p[1] / 12]), dashed: true, color: css("--hold") }], v => gbp(v)),
      missing(d, "mortgage", "The illustration"), note("75% of the average London price over 25 years at Bank Rate + 1.5 points, repayment. A rough gauge of how rates and prices combine, not a quote: actual mortgage rates move with swap rates, not only Bank Rate."));
    return [head, pe, br, mg];
  },
};
window.TOPIC = { VIEWS };
})();
