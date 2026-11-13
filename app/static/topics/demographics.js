// Demographics & Ageing: tabs and cards. Data from /api/demographics/<births|ageing|migration|workforce|pensions>; helpers from topic.html.
(() => {
const PLACES = ["US", "UK", "Hong Kong", "China"];
const C = k => css(SERIES[Math.max(0, PLACES.indexOf(k)) % SERIES.length]);
const yr = ts => new Date(ts * 1000).getUTCFullYear();
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const f1 = v => v == null ? "–" : num(v, 1), f2 = v => v == null ? "–" : num(v, 2);
const pc0 = v => v == null ? "–" : pct(v, 0);
// estimates solid, projection dashed in the same colour. The dashed lines go first so the shared date axis follows the projection to 2100.
function projChart(obj, fmt, opts = {}) {
  const ks = PLACES.filter(k => obj && obj[k] && (obj[k].est || []).length);
  const proj = ks.map(k => ({ points: obj[k].proj || [], color: C(k), dashed: true }));
  const est = ks.map(k => ({ name: k, points: obj[k].est, color: C(k) }));
  return linesChart([...proj, ...est], fmt, { extend: true, ...opts });
}
const byPlace = (obj, fmt, opts = {}) => linesChart(PLACES.filter(k => obj && (obj[k] || []).length).map(k => ({ name: k, points: obj[k], color: C(k) })), fmt, opts);
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");
const rowsTable = (rs, valFmt = v => num(+v, 3)) => table(["Date", "Series", "Value", "Source"], rs.map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.series), el("td", {}, valFmt(r.value, r)), srcCell(r))));
// Top cards follow the date hovered or clicked on any chart (datedHead from topic.html). Each figure is the series its chart draws, read at
// that date; at rest a projection reads this year (not 2100) and a series of actual figures its latest point.
const NOW = Date.now() / 1000;
const full = o => o ? [...(o.est || []), ...(o.proj || []).slice(1)] : [];        // the projection repeats the last estimate year
const ptAt = (pts, t) => { if (!pts || !pts.length) return null; let r = null; for (const p of pts) { if (p[0] <= t) r = p; else break; } return r; };
const fig = (label, pts, fmt, o = {}) => {
  const at = t => ptAt(pts, t != null ? t : o.proj ? NOW : Infinity);
  return { label: t => { const p = at(t); return label + (p ? " (" + yr(p[0]) + ")" : ""); }, value: t => { const p = at(t); return [p ? fmt(p[1]) : "–", p && o.cls ? o.cls(p[1]) : ""]; } };
};
const figs = (obj, label, fmt, o = {}) => PLACES.filter(k => obj && (o.proj ? full(obj[k]) : obj[k] || []).length).map(k => fig(k + " · " + label, o.proj ? full(obj[k]) : obj[k], fmt, o));
const projNote = "Solid: UN estimates to 2023. Dashed: the UN's medium projection (World Population Prospects 2024).";
const VIEWS = {
  async births() {
    const d = await api("births");
    const head = card(null, datedHead([...figs(d.national_tfr, "fertility rate, official", f2), ...figs(d.national_index, "births, 2019 = 100", f1, { cls: v => cls(v - 100) })],
      { latest: "Latest official figures" }), asOf(d), stale(d),
      note("2.1 children per woman keeps a population steady without migration. UK figures are England and Wales (ONS)."));
    const tfr = d.tfr ? card("Total fertility rate, 1950–2100: children per woman", ...projChart(d.tfr, f2, { hlines: [2.1] }),
      note(projNote + " The grey line is replacement (2.1). 5 years: is the post-2015 fall levelling off or still going? 10 years: does any of the four get back above 1.5? " +
        "20 years: today's low rates set how many people turn 20 in the 2040s, so the 2045 workforce is already mostly born."))
      : card("Total fertility rate", missing(d, "tfr", "The UN series"), stale(d));
    const nt = Object.keys(d.national_tfr || {}).length ? card("Fertility rate as each country's statistics office publishes it",
      ...byPlace(d.national_tfr, f2, { small: true, hlines: [2.1] }),
      note("CDC NCHS (US), ONS (England and Wales), C&SD (Hong Kong); China publishes no annual rate (the 2020 census point only). Checks the UN lines against the latest official figure, which the UN's 2024 round predates. " +
        "5 years: the recent direction; 10 and 20 years: whether official rates track the UN's projection or fall below it."), cite(d.cited)) : null;
    const ni = Object.keys(d.national_index || {}).length ? card("Births per year, 2019 = 100 (national statistics)",
      ...byPlace(d.national_index, f1, { hlines: [100] }),
      note("Live births per calendar year from CDC NCHS, ONS (England and Wales), C&SD and NBS, indexed so the four sizes compare. " +
        "5 years: has the post-Covid drop reversed (China's 2024 dragon-year bump and Hong Kong's newborn bonus)? 10 years: the size of school intakes; 20 years: the size of the workforce entering in the mid-2040s.")) : null;
    const wb = d.wpp_births ? card("Births per year, 1950–2100 (UN, thousands)", ...projChart(d.wpp_births, v => big(v * 1000), { small: true, log: true }),
      note(projNote + " Log scale so China and Hong Kong fit one chart. 20 years: births now are the workers of the 2040s; 50+ years: the projection after 2050 assumes fertility drifts back up, which none of the four has yet shown.")) : null;
    const rows = card("National figures", rowsTable(d.rows || [], (v, r) => +v > 100 ? num(+v) : num(+v, 3)),
      note("Kept in data/demographics/births.csv and tfr.csv. Rows marked 'verify' were written from memory or press reports: check them against the agency's table."));
    const tfr3 = d.tfr && Object.keys(d.tfr).length > 1 ? card("Fertility in 3D: children per woman, 1950 to 2100",
      ...chart3d({ ...grid3d(Object.entries(d.tfr).map(([k, v]) => ({ name: k, points: [...(v.est || []), ...(v.proj || [])] })).sort((a, b) => lastY(a.points) - lastY(b.points))), mode: "ribbons", zero: false, h: 440,
        xFmt: d3year, zFmt: f2, xHead: "year", csvName: "fertility 3d", note: "UN estimates, then the UN's medium projection after 2023. Drag to turn; hover for a country's rate in a year." }),
      note("One ribbon per place. Every ribbon falls from the left; what differs is how far and how early, and how little the projections on the right climb back.")) : null;
    return [head, tfr, tfr3, el("div", { class: "grid2" }, nt, ni), wb, rows];
  },
  async ageing() {
    const d = await api("ageing"), K = d.kpi || {}, dep = d.dependency;
    const head = card(null, datedHead([...figs(dep && dep.series, "65+ per 100 aged 15–64", f1, { proj: true }), ...figs(d.median_age, "median age", f1, { proj: true })],
      { latest: "This year (UN projection)" }),
      el("div", { class: "kpis" }, ...PLACES.filter(k => K[k] && K[k].oadr_2045 != null).map(k => kpi(k + " · 65+ per 100 aged 15–64 in 2045", f1(K[k].oadr_2045)))), stale(d));
    const oadr = dep ? card("Old-age dependency: people 65+ per 100 aged 15–64, 1950–2100", ...projChart(dep.series, f1),
      note((dep.source === "wpp" ? projNote + " Computed from the UN's population by five-year age group." : "The UN age file could not be read, so this is the World Bank's projection (from the UN's), which stops in 2050.") +
        " 5 years: how fast the ratio climbs as the baby boomers (China: the 1960s cohort) pass 65. 10 years: whether Hong Kong and China overtake the UK. 20 years: the ratio in 2045 is the pension question: fewer than 2.5 workers per person 65+ means taxes, contributions or the pension age have to change."))
      : card("Old-age dependency", missing(d, "dependency", "The dependency ratio"));
    const med = d.median_age ? card("Median age, 1950–2100", ...projChart(d.median_age, f1, { small: true }),
      note(projNote + " Half the population is older than this. 5 years: the steady rise; 10 years: Hong Kong and China pass 50; 20 years: how far apart the US (migration, higher fertility) and East Asia end up."))
      : card("Median age", missing(d, "median_age", "The median age"));
    const pr = card("National projections", rowsTable(d.projections || []),
      note("The agencies' own projections (ONS, US Census Bureau, C&SD), for comparison with the UN's. Kept in data/demographics/projections.csv."));
    return [head, oadr, med, pr];
  },
  async migration() {
    const d = await api("migration");
    const head = card(null, datedHead(figs(d.rate, "net migration per 1,000", f1, { proj: true, cls }), { latest: "This year (UN projection)" }), stale(d));
    const rate = d.rate ? card("Net migration per 1,000 people, 1950–2100", ...projChart(d.rate, f1, { hlines: [0] }),
      note(projNote + " Arrivals minus departures, per 1,000 residents. 5 years: the UK's post-2021 surge unwinding and Hong Kong's 2020–22 outflow reversing. 10 years: whether migration offsets low births. " +
        "20 years: the UN assumes steady inflows to the US and UK and a small outflow from China; whether that holds decides most of the 2045 workforce gap."), stale(d))
      : card("Net migration", missing(d, "rate", "The UN series"), stale(d));
    const net = d.net ? card("Net migration, 1950–2100 (UN, thousands a year)", ...projChart(d.net, v => big(v * 1000), { small: true }), note(projNote)) : null;
    const natl = Object.entries(d.national || {}).filter(([, p]) => p.length);
    const nat = natl.length ? card("National counts (12 months to each date)", ...linesChart(natl.map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % SERIES.length]) })), v => big(v), { small: true }),
      note("ONS long-term international migration (UK), Census Bureau net international migration (US), C&SD net movement and one-way permit holders (Hong Kong). Definitions differ, so read each line on its own. " +
        "Hong Kong's one-way permits (up to 150 a day from the mainland) are its steady inflow: 32,000 in the year to mid-2025 against a natural decrease of 14,800."), cite(d.cited)) : null;
    const rows = card("National figures", rowsTable(d.rows || [], v => num(+v)), note("Kept in data/demographics/migration.csv."));
    return [head, rate, el("div", { class: "grid2" }, net, nat), rows];
  },
  async workforce() {
    const d = await api("workforce"), w = d.working_age || {}, ch = w.change || {};
    const head = card(null, datedHead([...figs(w.index, "aged 15–64, 2025 = 100", f1, { proj: true, cls: v => cls(v - 100) }), ...figs(d.lfpr, "labour force participation", v => f1(v) + "%")],
      { latest: "This year (UN projection) and the latest participation rate" }),
      el("div", { class: "kpis" }, ...PLACES.filter(k => ch[k]).map(k => kpi(k + " · aged 15–64, 2025 → 2045 (" + num(ch[k].now_m, 1) + "m now)", pc0(ch[k].to_2045), cls(ch[k].to_2045)))),
      asOf(d), stale(d));
    const idx = w.index ? card("People aged 15–64, index 2025 = 100, 1950–2100", ...projChart(w.index, f1, { hlines: [100] }),
      note((w.source === "wpp" ? projNote : "World Bank projection (from the UN's), to 2050.") + " The traditional working-age population. 5 years: who has already peaked (China and Hong Kong in the 2010s, by the UN estimates). " +
        "10 years: the US and UK grow only through migration. 20 years: the 2045 level is the base that pays for pensions."))
      : card("Working-age population", missing(d, "working_age", "The working-age series"));
    const sup = d.support ? card("People aged 15–64 per person 65+, 1950–2100", ...projChart(d.support, f2, { small: true }),
      note("The inverse of old-age dependency. Roughly how many people of working age stand behind each pensioner; 20 years: where it crosses 2.")) : null;
    const lf = Object.keys(d.lfpr || {}).length ? card("Labour force participation, % of people 15+ (ILO modelled estimates)", ...byPlace(d.lfpr, f1, { small: true }),
      note("World Bank (SL.TLF.CACT.ZS). The share of adults working or looking for work; it falls as a population ages even if people of each age work as much. 5 years: how far older workers and women offset ageing; 10–20 years: the room left to raise it."))
      : card("Labour force participation", missing(d, "lfpr", "The World Bank series"));
    const lf2 = Object.keys(d.lfpr_1564 || {}).length ? card("Labour force participation, % of people 15–64", ...byPlace(d.lfpr_1564, f1, { small: true }),
      note("World Bank (SL.TLF.ACTI.ZS). The same within working age, so ageing does not drag it down: the room to raise the 2045 workforce without more people.")) : null;
    return [head, idx, el("div", { class: "grid2" }, sup, lf), lf2];
  },
  async pensions() {
    const d = await api("pensions"), A = d.answer || {}, R = A.rows || [];
    const q = R.length ? card("Who pays for pensions in 2045, and which shrinks fastest?",
      ...svgBars(R.map(r => r.place), [{ name: "2025", values: R.map(r => r.workers_per_65_2025), color: css("--hold") }, { name: "2045", values: R.map(r => r.workers_per_65_2045), color: css("--s1") }],
        { yFmt: f1, labelW: 70, note: "People aged 15–64 per person 65+. Hover or tap a bar." }),
      table(["", "Aged 15–64 per 65+ (2025 → 2045)", "Aged 15–64, millions (2025 → 2045)", "Change to 2045", "Public pension spend 2045, % GDP"],
        R.map((r, i) => el("tr", {}, el("td", {}, (i + 1) + ". " + r.place), el("td", {}, f2(r.workers_per_65_2025) + " → " + f2(r.workers_per_65_2045)),
          el("td", {}, f1(r.working_age_2025_m) + " → " + f1(r.working_age_2045_m)), el("td", { class: cls(r.working_age_change) }, pc0(r.working_age_change)),
          el("td", {}, r.pension_2045 == null ? "–" : f1(r.pension_2045) + "%")))),
      note("Ranked by how fast the working-age population shrinks from 2025 to 2045 (UN medium projection" + (A.source === "wpp" ? "" : ", World Bank") + "). " +
        "Pension spend in 2045 is read off a straight line between the agency's own published points either side (OBR, CBO); for the UK those points are about 50 years apart, so it is a rough guide. " +
        "Hong Kong has no state pension: retirement income is the employer-funded MPF plus means-tested allowances, so the cost falls on savers and on general taxes rather than a payroll tax."))
      : card("Who pays in 2045", missing(d, "answer", "The UN projections"), stale(d));
    const ser = Object.entries(d.series || {}).filter(([, p]) => p.length);
    const sp = ser.length ? card("Public pension spending, % of GDP: actual and projected",
      ...svgLines(ser.map(([k, p], i) => ({ name: k, points: p.map(x => [yr(x[0]), x[1]]), color: css(SERIES[i % SERIES.length]) })), { yFmt: v => num(v, 1) + "%", xFmt: v => String(Math.round(v)), vlines: [{ x: 2045, label: "2045" }] }),
      note("Lines join the published points only. UK: OBR Fiscal risks and sustainability (state pension). US: CBO Long-Term Budget Outlook (Social Security; assumes benefits are paid in full after the trust funds run out). " +
        "5 years: the UK triple lock and the US trust-fund date (2034) decide the near term. 10 years: whether the pension age rises in step. 20 years: the share of GDP each country's workers must hand over in 2045."), cite(d.cited))
      : card("Pension spending", el("div", { class: "muted" }, "Add rows to data/demographics/pensions.csv."));
    const rows = card("Published figures", rowsTable(d.rows || [], v => num(+v, 1) + "%"), note("Kept in data/demographics/pensions.csv."));
    return [q, sp, rows];
  },
};
window.TOPIC = { VIEWS };
})();
