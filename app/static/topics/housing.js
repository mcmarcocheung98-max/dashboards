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
    const rk = Object.entries(d.rents || {}).filter(([, p]) => p.length);
    const rents = rk.length ? card("Average monthly private rent (ONS PIPR, hand-entered)", ...linesChart(rk.map(([k, pts]) => ({ name: k, points: pts })), v => gbp(v), { small: true }),
      note("Rents against prices: a rising rent while prices are flat lifts the rental yield and usually comes before buyers return."))
      : card("Rents", el("div", { class: "muted" }, "No rent figures yet: add monthly London average rents from ONS PIPR to data/housing/rents.csv."));
    return [head, real, idx, yoy, rents];
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
      kpi(n.pe_basis === "london" ? "Price to London pay" : "Price to UK pay", n.price_to_earnings == null ? "–" : n.price_to_earnings.toFixed(1) + "×"), kpi("Highest ratio seen", n.pe_peak == null ? "–" : n.pe_peak.toFixed(1) + "×"),
      kpi("London median full-time pay" + (n.london_pay_year ? " (" + n.london_pay_year + ")" : ""), gbp(n.london_pay)),
      kpi("Illustrative mortgage a month", gbp(n.mortgage))), asOf(d), stale(d));
    const pe = card("London average price ÷ annual pay", ...linesChart([{ name: "÷ London median full-time pay", points: d.price_to_london_pay || [], width: 3 },
      { name: "÷ UK average regular pay (monthly trend)", points: d.price_to_earnings || [], dashed: true, color: css("--hold") }], v => v == null ? "–" : v.toFixed(1) + "×"),
      missing(d, "price_to_london_pay", "The London-pay ratio (ONS ASHE via Nomis)"), missing(d, "price_to_earnings", "The UK-pay trend"),
      note("Solid: median gross annual pay of full-time employees working in London (ONS Annual Survey of Hours and Earnings, each April, carried forward until the next survey), the basis ONS uses for its own affordability ratios. Dashed: UK average weekly regular pay × 52 (ONS KAB9), monthly but UK-wide, so higher; read it for the trend."));
    const br = card("Bank Rate and the quoted 2-year fixed mortgage rate (75% LTV)", ...linesChart([{ name: "Bank Rate", points: d.bank_rate || [] }, { name: "2-year fixed, 75% LTV", points: d.fixed_2y || [], color: css("--s2") }],
      v => v == null ? "–" : v.toFixed(2) + "%", { small: true }), missing(d, "bank_rate", "Bank Rate"), missing(d, "fixed_2y", "The quoted fixed rate (BoE IUMBV34)"));
    const mg = card("What a mortgage on the average London home would cost a month (illustration)",
      ...linesChart([{ name: "Monthly payment", points: d.mortgage || [] }, { name: d.london_pay ? "London median full-time pay ÷ 12" : "UK annual pay ÷ 12", points: (d.london_pay || d.earnings_annual || []).map(p => [p[0], p[1] / 12]), dashed: true, color: css("--hold") }], v => gbp(v)),
      missing(d, "mortgage", "The illustration"), note("75% of the average London price over 25 years, repayment, at " + (d.mortgage_basis || "the quoted fixed rate") + ". An illustration of how rates and prices combine, not a quote."));
    return [head, pe, br, mg];
  },
  async boroughs() {
    const d = await api("boroughs");
    let sortKey = "avg";
    const host = el("div", {});
    const draw = () => {
      const rows = [...d.rows].sort((a, b) => (b[sortKey] ?? -1e18) - (a[sortKey] ?? -1e18));
      const th = (k, l) => el("th", { style: "cursor:pointer", onclick: () => { sortKey = k; draw(); } }, l + (k === sortKey ? " ↓" : ""));
      host.replaceChildren(el("div", { class: "scroll" }, el("table", {}, el("tr", {}, el("th", {}, "Borough"), th("avg", "Average price"), th("yoy", "Change on a year"), th("change_5y", "5 years")),
        ...rows.map(r => el("tr", {}, el("td", {}, r.borough), el("td", {}, gbp(r.avg)), el("td", { class: cls(r.yoy) }, pc(r.yoy)), el("td", { class: cls(r.change_5y) }, pct(r.change_5y, 0)))))));
    };
    draw();
    const ranked = [...d.rows].filter(r => r.yoy != null).sort((a, b) => b.yoy - a.yoy);
    const bars = ranked.length ? card("Change on a year, by borough (%)", ...svgBars(ranked.map(r => r.borough.replace(" and ", " & ").slice(0, 14)), [{ name: "Yearly change", values: ranked.map(r => r.yoy), colorFn: v => css(v >= 0 ? "--up" : "--down") }],
      { yFmt: v => v.toFixed(0) + "%", labelW: 70, catName: i => ranked[i].borough, h: 260 })) : null;
    const top = [...d.rows].slice(0, 3).map(r => r.borough), bottom = [...d.rows].slice(-3).map(r => r.borough);
    const lines = card("Most and least expensive boroughs, indexed (Jan 2015 = 100)", ...linesChart([...top, ...bottom].filter(b => d.indexed[b]).map(b => ({ name: b, points: d.indexed[b], dashed: bottom.includes(b) })), v => v == null ? "–" : v.toFixed(0)),
      note("Solid: the three most expensive; dashed: the three cheapest. Prime central London has lagged outer boroughs since 2015."));
    const errs = Object.keys(d.errors || {}).length ? note("Not available right now: " + Object.keys(d.errors).join(", ") + ".") : null;
    return [card("London's 33 boroughs (UK HPI, " + (d.as_of || "–").slice(0, 7) + ")", el("div", { class: "muted" }, "Click a column to sort."), host, errs), bars, lines];
  },
  async global() {
    const d = await api("global");
    const series = [...(d.london ? [{ name: "London", points: d.london, width: 3 }] : []), ...Object.entries(d.us || {}).map(([k, pts]) => ({ name: k, points: pts })),
      ...(d.hk ? [{ name: "Hong Kong", points: d.hk, width: 3, color: css("--s5") }] : [])];
    const idx = card("House prices, Jan 2015 = 100", ...linesChart(series, v => v == null ? "–" : v.toFixed(0)),
      missing(d, "us", "US prices (FHFA)"), missing(d, "hk", "Hong Kong prices (RVD)"), stale(d),
      note("London: UK HPI index. US: FHFA house price indexes (national purchase-only, monthly; New York and San Francisco metro divisions, quarterly). Hong Kong: Rating and Valuation Department private domestic index. All rebased to January 2015."));
    const tbl = card("Latest", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Market", "Index (2015 = 100)", "Change on a year", "Month"].map(h => el("th", {}, h))),
      ...(d.table || []).map(r => el("tr", {}, el("td", {}, r.market), el("td", {}, r.index == null ? "–" : r.index.toFixed(0)), el("td", { class: cls(r.yoy) }, pct(r.yoy, 1)), el("td", {}, r.month))))));
    const rates = d.rates ? card("Borrowing costs: UK 2-year fixed, US 30-year fixed, HK 1-month HIBOR (%)", ...linesChart(Object.entries(d.rates).map(([k, pts]) => ({ name: k, points: pts })), v => v == null ? "–" : v.toFixed(2) + "%", { small: true }),
      Object.keys(d.rates_missing || {}).length ? el("div", { class: "muted" }, "Not available right now: " + Object.keys(d.rates_missing).join(", ") + ".") : null,
      note("Most Hong Kong mortgages float on HIBOR or prime, most US ones are fixed for 30 years, most UK ones are fixed for two to five years: the same move in policy rates reaches each market at a different speed.")) : card("Rates", el("div", { class: "muted" }, "Not available right now (" + (d.rates_error || "no data") + ")."));
    return [idx, tbl, rates];
  },
};
window.TOPIC = { VIEWS };
})();
