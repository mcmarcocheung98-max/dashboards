// Longevity & Biotech: tabs and cards. Data from /api/longevity/<lifespan|causes|glp1|approvals|markets>; helpers from topic.html.
(() => {
const PLACES = ["US", "UK", "Hong Kong", "China"];
const C = k => css(SERIES[Math.max(0, PLACES.indexOf(k)) % SERIES.length]);
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const f1 = v => v == null ? "–" : num(v, 1), f2 = v => v == null ? "–" : num(v, 2);
const yrs = v => v == null ? "–" : num(v, 1) + " yrs";
const sgn = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const byPlace = (obj, fmt, opts = {}) => linesChart(PLACES.filter(k => obj && (obj[k] || []).length).map(k => ({ name: k, points: obj[k], color: C(k) })), fmt, opts);
const bySeries = (obj, fmt, opts = {}) => linesChart(Object.entries(obj || {}).filter(([, p]) => p && p.length).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % SERIES.length]) })), fmt, opts);
const has = o => o && Object.values(o).some(p => p && p.length);
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");
const rowsTable = (rs, valFmt = v => v === "" ? "–" : num(+v, 2)) => table(["Date", "Series", "Value", "Source"],
  rs.map(r => el("tr", {}, el("td", {}, r.date.slice(0, 4)), el("td", {}, r.series), el("td", {}, valFmt(r.value, r)), srcCell(r))));
const yr = ts => new Date(ts * 1000).getUTCFullYear();

const VIEWS = {
  async lifespan() {
    const d = await api("lifespan"), K = d.kpi || {}, H = (d.hale || {}).kpi || {}, N = d.national_latest || {}, HL = d.healthy_latest || {};
    const head = card(null, el("div", { class: "kpis" }, ...PLACES.filter(k => K[k]).map(k => kpi(k + " · life expectancy " + (K[k].date || "").slice(0, 4) + " (vs 2019)",
      yrs(K[k].value) + " (" + sgn(K[k].vs_2019) + ")", cls(K[k].vs_2019)))),
      el("div", { class: "kpis", style: "margin-top:10px" }, ...Object.keys(N).map(k => kpi(k + " · " + (N[k].date || "").slice(0, 4) + " (national)", yrs(N[k].value)))), asOf(d), stale(d),
      note("World Bank (from the UN and national offices) for one consistent series per place; the second row is each agency's own latest figure, which comes out a year or two sooner. Hong Kong has the longest life expectancy in the world."));
    const ans = card("Do healthy life years start rising again?",
      el("div", { class: "kpis" }, ...Object.keys(H).map(k => kpi(k + " · healthy life expectancy " + ((H[k].hale || {}).date || "").slice(0, 4) + " (10-yr change)",
        yrs((H[k].hale || {}).value) + " (" + sgn(H[k].hale_10y) + ")", cls(H[k].hale_10y))),
        ...Object.keys(HL).map(k => kpi(k + " · " + (HL[k].date || "").slice(0, 4) + " (was " + f1(HL[k].prev) + ")", yrs(HL[k].value), cls(HL[k].value - HL[k].prev)))),
      note("Healthy life expectancy counts the years a newborn can expect in full health. WHO's estimates run to 2021 and stop short of the recovery; ONS's England figures (three-year periods) are the most recent official check. " +
        "The answer turns yes when both the WHO and the national series rise past their 2019 level, and the gap below (years lived in poor health) stops widening."));
    const le = has(d.le) ? card("Life expectancy at birth, 1960 on (years)", ...byPlace(d.le, f1),
      note("World Bank SP.DYN.LE00.IN, both sexes. 5 years: has the US recovered its 2019 level after Covid and overdoses, and has the UK's flat decade ended? 10 years: does China close the gap with the US? " +
        "20 years: whether Hong Kong's lead (now over 85) keeps rising or stalls, which says whether the frontier of human lifespan still moves."))
      : card("Life expectancy", missing(d, "le", "The World Bank series"), stale(d));
    const hale = d.hale ? card("Healthy life expectancy, 2000–2021 (WHO HALE, years)", ...byPlace(d.hale.hale, f1, { small: true }),
      note("WHO Global Health Observatory, both sexes; not published for Hong Kong. 5 years: Covid's dent (2020–21). 10 years: whether healthy years grow as fast as total years. 20 years: the case for longevity drugs is that they lift this line, not just the one above."))
      : card("Healthy life expectancy", missing(d, "hale", "WHO's series"));
    const gap = d.hale ? card("Years lived in poor health (life expectancy minus HALE)", ...byPlace(d.hale.gap, f2, { small: true }),
      note("WHO, both sexes. A widening gap means extra years are added in poor health. 5 and 10 years: is it still widening? 20 years: compression of morbidity, the gap shrinking, is what 'healthy ageing' would look like in data.")) : null;
    const nat = has(d.national) ? card("Life expectancy as each country publishes it", ...bySeries(d.national, f1, { small: true }),
      note("CDC NCHS (US, both sexes), ONS national life tables (UK, three-year periods by sex), C&SD/DH (Hong Kong by sex), NHC (China). 5 years: the post-Covid rebound in each. 10 and 20 years: whether official figures keep pace with the World Bank line."), cite(d.cited)) : null;
    const hl = has(d.healthy) ? card("England healthy life expectancy (ONS, years)", ...bySeries(d.healthy, f1, { small: true }),
      note("ONS health state life expectancies at birth, from the Annual Population Survey's self-reported health. Falling since 2017–19. 5 years: does it turn up? 10 years: is it back above 63? 20 years: the state pension age rises toward 68 while healthy life expectancy sits near 62.")) : null;
    const rows = card("National figures", rowsTable(d.rows || []), note("Kept in data/longevity/life_expectancy.csv and healthy.csv. Rows marked 'verify' were entered from memory: check them against the cited page."));
    return [head, ans, le, el("div", { class: "grid2" }, hale, gap), el("div", { class: "grid2" }, nat, hl), rows];
  },
  async causes() {
    const d = await api("causes"), U = (d.us || {}).kpi || {}, NM = { heart: "Heart disease", cancer: "Cancer", alzheimer: "Alzheimer disease", overdose: "Drug overdose", all: "All causes" };
    const head = card(null, el("div", { class: "kpis" }, ...Object.keys(NM).filter(k => U[k]).map(k => kpi("US " + NM[k].toLowerCase() + " per 100k · vs a year earlier", f1(U[k].value) + " (" + pct(U[k].yoy, 1) + ")", cls(-U[k].yoy)))),
      asOf(d), stale(d), note("CDC NCHS provisional age-adjusted death rates, 12 months ending " + (U.heart ? dateOf(U.heart.date) : "the latest quarter") + ". Green means the rate fell."));
    const s = (d.us || {}).series || {};
    const us = Object.keys(s).length ? card("US age-adjusted death rates by cause, 12 months ending each quarter (per 100,000)",
      ...linesChart(["heart", "cancer", "alzheimer", "overdose"].filter(k => (s[k] || []).length).map((k, i) => ({ name: NM[k], points: s[k], color: css(SERIES[i]) })), f1),
      note("CDC NCHS VSRR quarterly provisional estimates. 5 years: overdose deaths after the fentanyl peak (2022–23), and heart disease back on its pre-Covid fall? 10 years: does cancer keep falling about 1–2% a year, and do the new Alzheimer drugs show up? " +
        "20 years: heart disease and cancer are two-thirds of the gap between today's lifespan and a much longer one."))
      : card("US death rates by cause", missing(d, "us", "CDC's quarterly estimates"), stale(d));
    const all = (s.all || []).length ? card("US all-cause age-adjusted death rate (per 100,000)", ...linesChart([{ name: "All causes", points: s.all, color: css("--hold") }], f1, { small: true }),
      note("The total. 5 years: back below 2019? 10 to 20 years: its slope is what moves life expectancy.")) : null;
    const ncd = d.ncd ? card("Chance of dying aged 30–70 from heart disease, cancer, diabetes or chronic lung disease (%)", ...byPlace(d.ncd.series, f1, { small: true, sync: false }),
      note("WHO (NCDMORT3070, SDG 3.4.1); not published for Hong Kong. The UN goal is a third lower by 2030 than 2015. 5 and 10 years: is any of the three on track? 20 years: premature deaths are where drugs and prevention add the most healthy years."))
      : card("Premature NCD deaths", missing(d, "ncd", "WHO's series"));
    const uk = Object.entries(d.uk || {}).filter(([, p]) => p.length).map(([k, p], i) => card(k, ...linesChart([{ name: k, points: p, color: css(SERIES[(i + 1) % SERIES.length]) }], v => num(v, v < 100 ? 1 : 0), { small: true }),
      note(/drug/i.test(k) ? "ONS, deaths registered each year. Record highs every year since 2012. 5 years: does it peak? 10 years: Scotland's and England's rates converge or not; 20 years: a cohort of older users ages into the counts."
        : "ONS: dementia and Alzheimer's has been the leading cause of death in England and Wales since 2015. 5 years: share after Covid; 10 years: whether lecanemab-type drugs reach the NHS; 20 years: the share rises as other causes fall.")));
    const hkHas = has(d.hk);
    const hk = card("Hong Kong", hkHas ? bySeries(d.hk, f1, { small: true }) : el("div", { class: "muted" }, "Not entered yet: add the Centre for Health Protection's age-standardised death rates by cause to data/longevity/causes_hk.csv."),
      note("Hong Kong's leading causes are cancer, pneumonia and heart disease. 5 to 20 years: whether its long lifespan holds as the population ages fastest of the four."));
    const rows = card("Hand-entered figures", rowsTable(d.rows || [], v => v === "" ? "–" : num(+v, +v < 100 ? 1 : 0)), cite(d.cited), note("Kept in data/longevity/causes_uk.csv and causes_hk.csv."));
    return [head, us, el("div", { class: "grid2" }, all, ncd), el("div", { class: "grid2" }, ...uk, hk), rows];
  },
  async glp1() {
    const d = await api("glp1"), N = (d.nhs || {}).kpi || {}, R = d.revenue || {}, UP = d.uptake_latest || {};
    const head = card(null, el("div", { class: "kpis" },
      kpi("NHS England GLP-1 items, 12 months to " + (N.month ? N.month.slice(0, 7) : "–"), big(N.items_12m)),
      kpi("…vs the 12 months before", pct(N.yoy_12m, 0), cls(N.yoy_12m)),
      kpi("NHS cost, last 12 months", N.cost_12m_m == null ? "–" : "£" + num(N.cost_12m_m, 0) + "m"),
      ...Object.entries(R).map(([f, r]) => kpi(f + " revenue " + (r.latest_year || "") + " (" + r.unit + ")", num((r.annual || []).slice(-1)[0]?.[1], 1) + "bn (" + pct(r.growth, 0) + ")", cls(r.growth)))),
      asOf(d), stale(d));
    const n = d.nhs;
    const items = n ? card("NHS England primary-care prescription items per month, by drug", ...linesChart(Object.entries(n.items).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i]) })), v => big(v)),
      note("OpenPrescribing (NHS Business Services Authority data), every GP prescription in England. Most weight-loss use in the UK is private (online pharmacies), so this is diabetes plus the NHS weight-loss rollout. " +
        "5 years: tirzepatide's primary-care rollout from June 2025. 10 years: whether these drugs become as routine as statins. 20 years: whether the population's obesity, diabetes and heart deaths fall with them.") ,
      Object.keys(n.missing || {}).length ? el("div", { class: "muted" }, "Missing: " + Object.entries(n.missing).map(([k, v]) => k + " (" + v + ")").join(", ")) : null)
      : card("NHS England prescriptions", missing(d, "nhs", "OpenPrescribing"), stale(d));
    const rev = Object.keys(R).length ? card("Annual revenue: Eli Lilly (USD bn) and Novo Nordisk (DKK bn)", el("div", { class: "grid2" }, ...Object.entries(R).map(([f, r], i) => el("div", {},
      el("div", { class: "muted" }, f + " (" + r.unit + " bn)"), ...svgBars(r.annual.map(a => String(a[0])), [{ name: f, values: r.annual.map(a => a[1]), color: css(SERIES[i]) }], { yFmt: v => num(v, 0), h: 180 })))),
      note("SEC EDGAR: Lilly's 10-K revenue, Novo Nordisk's 20-F (IFRS, Danish kroner). The two makers of semaglutide and tirzepatide. 5 years: does growth hold as prices fall and Medicare negotiates? 10 years: oral pills and generics (semaglutide patents end in China and Canada in 2026). " +
        "20 years: whether the profits fund the next class of drugs (amylin, longevity targets)."))
      : card("Revenue", missing(d, "revenue", "EDGAR"));
    const lq = R["Eli Lilly"] && (R["Eli Lilly"].quarterly || []).length ? card("Eli Lilly quarterly revenue (USD bn)", ...linesChart([{ name: "Eli Lilly", points: R["Eli Lilly"].quarterly, color: css("--s1") }], f2, { small: true }),
      note("10-Q quarters; Q4 is the 10-K year less the three quarters before. Mounjaro and Zepbound are most of the growth since 2023.")) : null;
    const P = d.products || {};
    const yearsP = [...new Set(Object.values(P).flat().map(x => x[0]))].sort();
    const prodGroup = re => Object.entries(P).filter(([k]) => re.test(k)).map(([k, p], i) => ({ name: k, values: yearsP.map(y => (p.find(x => x[0] === y) || [])[1] ?? null), color: css(SERIES[i + (re.source.includes("USD") ? 0 : 2)]) }));
    const prod = yearsP.length ? card("GLP-1 brand sales", el("div", { class: "grid2" },
      el("div", {}, el("div", { class: "muted" }, "Lilly, USD bn"), ...svgBars(yearsP.map(String), prodGroup(/USD/), { yFmt: v => num(v, 0), h: 180 })),
      el("div", {}, el("div", { class: "muted" }, "Novo Nordisk, DKK bn"), ...svgBars(yearsP.map(String), prodGroup(/DKK/), { yFmt: v => num(v, 0), h: 180 }))),
      note("Hand-entered from the companies' annual reports (data/longevity/products.csv). Weight-loss brands (Wegovy, Zepbound) against the diabetes brands (Ozempic, Mounjaro): 5 years: which grows faster; 10 years: when sales peak as generics arrive.")) : null;
    const up = Object.keys(UP).length ? card("Who takes them: surveys",
      table(["Survey", "Latest", "Before", "When"], Object.entries(UP).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, f1(v.value)), el("td", {}, f1(v.prev)), el("td", {}, (v.date || "").slice(0, 7))))),
      note("KFF and Gallup (US), press estimates (UK); no comparable surveys for Hong Kong or China yet. 5 years: uptake doubling every year or two; 10 years: does US obesity keep falling from its 2022 peak? 20 years: whether diabetes and heart-disease deaths follow."),
      cite(d.cited)) : null;
    const rows = card("Hand-entered figures", rowsTable(d.rows || []), note("Kept in data/longevity/products.csv and uptake.csv. Rows marked 'verify' were entered from memory."));
    return [head, items, rev, el("div", { class: "grid2" }, lq, up), prod, rows];
  },
  async approvals() {
    const d = await api("approvals"), K = d.kpi || {}, F = d.fda || [], G = d.cgt_by_year || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("FDA novel approvals, " + (K.year || "–"), String(K.count ?? "–")), kpi("10 years before, average", f1(K.avg10)),
      kpi("vs that average", pct(K.vs_avg, 0), cls(K.vs_avg)), kpi("Record", (K.record ?? "–") + " (" + (K.record_year || "–") + ")"), kpi("Cell & gene therapies approved", String((d.cgt || []).length))));
    const avg = K.avg10;
    const fda = F.length ? card("FDA novel drug approvals per year (CDER)", ...svgBars(F.map(x => String(x[0])), [{ name: "Novel approvals", values: F.map(x => x[1]), colorFn: v => avg && v >= avg ? css("--up") : css("--s1") }],
      { yFmt: v => num(v, 0), note: "Green: at or above the 10-year average. Hover or tap a bar." }),
      note("New molecular entities and new therapeutic biologics approved by FDA's drug centre (CDER). 5 years: holding near 50 a year despite FDA staff cuts in 2025? 10 years: whether AI-designed molecules raise the count. " +
        "20 years: the count is a crude measure of innovation; what matters is whether the approvals add healthy years (see Lifespan)."), cite(d.cited))
      : card("FDA approvals", el("div", { class: "muted" }, "Add rows to data/longevity/fda_novel.csv."));
    const cg = (G.years || []).length ? card("Cell and gene therapy approvals per year", ...svgBars(G.years.map(String), Object.entries(G.counts).map(([a, v], i) => ({ name: a, values: v, color: css(SERIES[i]) })), { yFmt: v => num(v, 0) }),
      note("FDA CBER's list of approved cellular and gene therapy products, plus MHRA firsts. 5 years: CRISPR (Casgevy) and in vivo editing reaching more diseases. 10 years: whether one-off cures for common diseases (heart, cholesterol) arrive. 20 years: whether these rare-disease tools become longevity tools.")) : null;
    const list = card("Cell and gene therapies", table(["Date", "Product", "Agency", "Type", "Source"], (d.cgt || []).map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.name), el("td", {}, r.agency), el("td", {}, r.kind), srcCell(r)))),
      note("Kept in data/longevity/cgt.csv."));
    const ms = card("Regulatory milestones (FDA, MHRA, NICE, NMPA)", el("div", { class: "tl" }, ...(d.milestones || []).flatMap(r => [el("div", { class: "d" }, r.date), el("div", {}, el("b", {}, r.agency + " "), link(r.event, r.source), r.note ? el("span", { class: "muted" }, " · " + r.note) : "")])),
      note("Kept in data/longevity/milestones.csv. The UK's MHRA approved the world's first CRISPR medicine; NICE decides what the NHS pays for. China's NMPA matters for GLP-1 generics after the 2026 patent expiry."));
    return [head, fda, cg, ms, list];
  },
  async markets() {
    const d = await api("markets"), S = d.stats || {};
    const names = { XBI: "XBI (equal-weight biotech)", IBB: "IBB (large biotech)", SPY: "SPY (S&P 500)", LLY: "Eli Lilly", NVO: "Novo Nordisk ADR" };
    const head = card(null, el("div", { class: "kpis" }, ...Object.keys(names).filter(k => S[k]).map(k => kpi(names[k] + " · 1 year / 5 years", pct(S[k].r1y, 0) + " / " + pct(S[k].r5y, 0), cls(S[k].r1y)))),
      el("div", { class: "kpis", style: "margin-top:10px" }, ...["XBI", "IBB"].filter(k => S[k]).map(k => kpi(k + " from its " + S[k].peak_date.slice(0, 4) + " peak", pct(S[k].from_peak, 0), cls(S[k].from_peak)))),
      asOf(d), stale(d));
    const reb = has(d.rebased) ? card("Biotech against the market, rebased to 100 (log scale)", ...linesChart(Object.keys(names).filter(k => (d.rebased[k] || []).length).map((k, i) => ({ name: k, points: d.rebased[k], color: css(SERIES[i]) })), f1, { log: true }),
      note("Daily closes from Nasdaq, price only (no dividends). 5 years: XBI peaked in February 2021 and has lagged the S&P since; a sustained turn would mean money is flowing to small biotech again. " +
        "10 years: Lilly and Novo show where the profits went (GLP-1s). 20 years: whether biotech returns justify the R&D that longevity needs. No Hong Kong or China biotech index is on the Nasdaq API."))
      : card("Prices", missing(d, "rebased", "Nasdaq prices"), stale(d));
    const rel = (d.xbi_spy || []).length ? card("XBI relative to SPY (rebased to 100)", ...linesChart([{ name: "XBI / SPY", points: d.xbi_spy, color: css("--s4") }], f1, { small: true }),
      note("Rising: small biotech is beating the market. 5 years: has the post-2021 slide ended? 10 and 20 years: biotech's share of the market's gains.")) : null;
    return [head, reb, rel];
  },
};
window.TOPIC = { VIEWS };
})();
