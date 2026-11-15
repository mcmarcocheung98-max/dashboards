// AI Compute, Power & Chips: tabs and cards. Data from /api/compute-chips/<overview|power|capex|compute|chips|gpus|supply>; helpers from topic.html.
(() => {
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const yearOf = ts => new Date(ts * 1000).getUTCFullYear();
const q = ts => { const d = new Date(ts * 1000); return "Q" + (Math.floor(d.getUTCMonth() / 3) + 1) + " " + d.getUTCFullYear(); };
const twh = v => v == null ? "–" : num(v, v < 20 ? 1 : 0) + " TWh";
const bn = v => v == null ? "–" : "$" + num(v, v < 10 ? 2 : 1) + "bn";
const flop = v => v == null ? "–" : Number(v).toExponential(1).replace("e+", "e") + " FLOP";
const mw = v => v == null ? "–" : v >= 1000 ? num(v / 1000, 1) + " GW" : num(v) + " MW";
const share = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const lines = obj => Object.entries(obj || {}).filter(([, p]) => p && p.length).map(([k, pts]) => ({ name: k, points: pts }));
const errs = (d, what) => d && d.errors && Object.keys(d.errors).length ? el("div", { class: "muted" }, what + " not available right now: " + Object.entries(d.errors).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
// yearly charts (power) keep their own dates: a year snaps to 1 January and would drag the shared axis off the monthly charts
// what each chart shows, and the 5-, 10- and 20-year question it answers
const ask = (shows, q5, q10, q20) => note(el("span", {}, shows, el("br"), el("b", {}, "5 years: "), q5, " ", el("b", {}, "10 years: "), q10, " ", el("b", {}, "20 years: "), q20));
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");

const VIEWS = {
  async overview() {
    const d = await api("overview"), K = d.kpi || {}, tw = K.taiwan;
    const head = card("Is power or chips the binding limit on AI?", el("div", { class: "kpis" },
      kpi("US data centres, share of electricity" + (K.us_dc_share_year ? " (" + K.us_dc_share_year + ")" : ""), share(K.us_dc_share)),
      kpi("Largest AI cluster, power", mw(K.largest_cluster_mw)),
      kpi("Hyperscaler capex, last 4 quarters", bn(K.capex_ttm)), kpi("vs the 4 before", pct(K.capex_ttm_yoy, 0), cls(K.capex_ttm_yoy)),
      kpi("Nvidia revenue vs a year earlier", pct(K.nvidia_yoy, 0), cls(K.nvidia_yoy)),
      kpi("Frontier training compute, growth a year", K.compute_growth == null ? "–" : num(K.compute_growth, 1) + "×"),
      kpi("Taiwan, share of <10nm capacity" + (tw ? " " + tw.years[0] + " → " + tw.years[1] : ""), tw ? tw.from + "% → " + tw.to + "%" : "–")), asOf(d), stale(d));
    const read = card("How to read it",
      el("div", { class: "muted", style: "font-size:13.5px;color:var(--ink2)" },
        el("p", {}, el("b", {}, "Chips bind "), "when hyperscaler capex keeps rising but Nvidia's and TSMC's revenue growth runs ahead of it only because prices rise, lead times stretch and export rules ration supply (Chips, Supply chain tabs)."),
        el("p", {}, el("b", {}, "Power binds "), "when the largest clusters stop growing in megawatts as fast as training compute grows, and data centres' share of national demand rises faster than grids add capacity (Power tab: the US share and the IEA and LBNL outlooks)."),
        el("p", {}, el("b", {}, "Taiwan's share "), "falls only if the Arizona, Kumamoto and Dresden fabs reach volume on schedule; the Supply chain tab keeps the milestones and the 2022 vs 2032 capacity shares side by side.")),
      ...["power", "capex", "compute", "chips", "supply"].map(k => missing(d, k, "The " + k + " tab")));
    return [head, read];
  },

  async power() {
    const d = await api("power"), S = d.share || {};
    const last = k => (S[k] || []).slice(-1)[0];
    const head = card(null, el("div", { class: "kpis" }, ...["US", "China", "UK", "World"].map(k => { const p = last(k); return kpi(k + " data centres, share of electricity" + (p ? " (" + yearOf(p[0]) + ")" : ""), share(p && p[1])); })),
      el("div", { class: "muted", style: "margin-top:6px" }, "Hong Kong: no official data-centre electricity figure is published; see data/compute-chips/README.md."), asOf(d), stale(d));
    const used = card("Data-centre electricity use, TWh a year (estimates and outlooks)",
      ...linesChart([...lines(d.dc), ...lines(d.outlook).map(s => ({ ...s, dashed: true }))], twh, { log: true, sync: false }),
      ask("Solid lines: estimates of what data centres used (LBNL, IEA, NESO). Dashed: published outlooks (IEA base case to 2030, LBNL's 2028 low and high). Log scale, so equal slopes are equal growth rates.",
        "does US use reach LBNL's 325-580 TWh range by 2028, or fall short because the power is not there?", "does China's use overtake the US as its AI build-out scales?", "does AI make data centres a top-three electricity user, like industry or heating?"),
      cite(d.cited));
    const sh = card("Data centres' share of total electricity demand",
      ...linesChart(lines(S), share, { small: true, sync: false }),
      ask("Data-centre TWh divided by total demand in the same year (Ember, or the hand-entered demand.csv where Ember has no year)." + (d.ember_live === false ? " Ember is not reachable right now: hand-entered totals only." : ""),
        "does the US share pass 6-12% (LBNL 2028 range)?", "does any country cap new connections because data centres take too large a share?", "is the share closer to 5% or to 20%?"));
    const C = d.clusters;
    const cl = C ? card("Largest AI supercomputer, power capacity (Epoch AI)",
      ...linesChart([{ name: "Largest cluster", points: C.largest }], mw, { small: true, log: true }),
      el("div", { class: "grid2", style: "margin-top:8px" },
        table(["Country", "Operational power"], Object.entries(C.by_country || {}).slice(0, 8).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, mw(v))))),
        table(["Record cluster", "Online", "Power"], (C.top || []).map(r => el("tr", {}, el("td", {}, r.name + " (" + r.country + ")"), el("td", {}, dateOf(r.date)), el("td", {}, mw(r.mw)))))),
      ask("Each step is a new largest GPU cluster by power capacity, by the date it came online; the tables sum operational clusters by country and list the records.",
        "do 1 GW clusters arrive on time, or slip for want of grid connections and turbines?", "does the largest cluster keep growing ~2× a year, or flatten as power becomes the limit?", "are frontier clusters still single sites, or spread across many grids?"))
      : card("Largest AI supercomputers", el("div", { class: "muted" }, "Not available right now (" + (d.clusters_error || "no data") + ")."));
    const dem = card("Total electricity demand, TWh a year (Ember)", ...linesChart(lines(d.demand), twh, { small: true, log: true, sync: false }),
      ask("The denominator of the share above. Hong Kong is not in Ember's file.", "does US demand growth pick up from ~1% a year?", "is China's demand growth still ~6% a year?", "how much of demand growth is data centres?"));
    const rows = card("Hand-entered figures", table(["Year", "Series", "TWh", "Source"], (d.rows || []).map(r => el("tr", {}, el("td", {}, r.date.slice(0, 4)), el("td", {}, r.series), el("td", {}, twh(+r.value)), srcCell(r)))),
      note("Kept in data/compute-chips/dc_power.csv and dc_power_outlook.csv. Rows marked verify were entered from memory."));
    return [head, used, el("div", { class: "grid2" }, sh, dem), cl, rows];
  },

  async capex() {
    const d = await api("capex"), K = d.kpi || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("Five hyperscalers, latest quarter" + (K.date ? " (" + q(Date.parse(K.date) / 1000) + ")" : ""), bn(K.quarter)),
      kpi("vs a year earlier", pct(K.quarter_yoy, 0), cls(K.quarter_yoy)), kpi("Last 4 quarters", bn(K.ttm)), kpi("vs the 4 before", pct(K.ttm_yoy, 0), cls(K.ttm_yoy))),
      errs(d, "Filings"), asOf(d), stale(d));
    const by = card("Capital expenditure per quarter, by company (USD bn)", ...linesChart(lines(d.companies), bn),
      ask("Cash paid for property and equipment from each 10-Q and 10-K (SEC EDGAR); Q4 is the annual figure minus nine months. Amazon's line is 'purchases of property and equipment'. Fiscal quarters are placed in the calendar quarter they mostly cover (Oracle's to end-August is Q3).",
        "does capex keep rising while revenue from AI catches up, or is it cut?", "does capex settle as a share of revenue, like telecom networks after the 2000 build-out?", "is this an ordinary utility-like asset base or a one-off boom?"));
    const tot = d.total ? card("All five combined: per quarter and over the last four quarters (USD bn)",
      ...linesChart([{ name: "Quarter", points: d.total, bar: true, color: css("--s1") }, { name: "Last 4 quarters", points: d.ttm || [], axis: "left", color: css("--s2") }], bn),
      ask("Bars: the five companies' capex in each quarter. Line (left axis): the rolling four-quarter total.",
        "does the four-quarter total keep growing faster than Nvidia's and TSMC's revenue (chips binding) or slower (demand binding)?", "how much of this spend is power and buildings rather than chips?", "does AI infrastructure capex end up larger than oil and gas capex?"))
      : card("All five combined", el("div", { class: "muted" }, "Shown when every company's filings answer (" + (d.total_error || "no data") + ")."));
    const cap3 = d.companies && Object.keys(d.companies).length > 2 ? card("The capex race in 3D: cash spent on property and equipment per quarter, one ribbon per company (USD bn)",
      ...chart3d({ ...grid3d(Object.entries(d.companies).map(([k, p]) => ({ name: k, points: p })).sort((a, b) => lastY(a.points) - lastY(b.points))), mode: "ribbons", h: 460, xFmt: d3mon, zFmt: v => v == null ? "–" : "$" + num(v, 1) + "bn",
        xHead: "quarter", csvName: "capex 3d", note: "The smallest spender last quarter at the front, the largest at the back. Drag to turn; hover for a quarter." }),
      note("The same series as the chart above. Flat ground until 2023, then every ribbon turns up at once: the build-out is one move made by all five, not one company's bet.")) : null;
    return [head, by, cap3, tot].filter(Boolean);
  },

  async compute() {
    const d = await api("compute"), E = d.epoch;
    if (!E) return [card("Training compute", el("div", { class: "err" }, "Not available right now (" + (d.epoch_error || "no data") + ")."), stale(d))];
    const top = E.top && E.top[0];
    const head = card(null, el("div", { class: "kpis" }, kpi("Frontier compute growth since 2018", E.growth_per_year == null ? "–" : num(E.growth_per_year, 1) + "× a year"),
      kpi("Largest training run", flop(top && top.flop)), kpi("Its model", top ? top.model : "–"), kpi("Models in the dataset", num(E.n))), asOf(d), stale(d));
    const fr = card("Training compute of frontier AI models (Epoch AI)", ...linesChart([{ name: "Largest so far", points: E.max }, { name: "Frontier models", points: E.frontier, dashed: true, color: css("--hold") }], flop, { log: true }),
      ask("Largest training run to date, and every model that was in the top ten by compute when it came out (log scale). Growth is the slope of the frontier since 2018.",
        "does compute keep growing ~4-5× a year, or bend as clusters hit power and chip limits?", "does a 1e29-1e30 FLOP run happen, and where?", "does compute stop being the measure that matters?"));
    const ys = E.years || [], C = E.over_1e25 || {};
    const over = card("Models trained with more than 1e25 FLOP, per year, by country",
      ...svgBars(ys.map(String), Object.entries(C).map(([k, v], i) => ({ name: k, values: v, color: css(SERIES[i % SERIES.length]) })), { yFmt: v => Math.round(v) }),
      ask("1e25 FLOP is the EU AI Act's systemic-risk threshold. Country of the developer (first listed).",
        "how many Chinese labs train at this scale despite export controls?", "does the UK host any?", "is frontier training concentrated in a handful of firms or widespread?"));
    const t = card("The largest training runs", table(["Model", "Organisation", "Country", "Published", "Compute"],
      (E.top || []).map(r => el("tr", {}, el("td", {}, r.model), el("td", {}, r.org), el("td", {}, r.country), el("td", {}, dateOf(r.date)), el("td", {}, flop(r.flop))))));
    return [head, fr, over, t];
  },

  async chips() {
    const d = await api("chips"), L = d.last || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(L).map(([k, v]) => kpi(k + " · 1 year " + pct(v.y1, 0), usd(v.price, 2)))), errs(d, "Some sources are"), asOf(d), stale(d));
    const rev = card("Quarterly revenue (bn; ASML in euros)", ...linesChart(lines(d.revenue), v => num(v, 1) + "bn"),
      ask("Nvidia and AMD from their 10-Q and 10-K filings (SEC EDGAR); TSMC, ASML and SMIC copied from their quarterly results (data/compute-chips/chip_revenue.csv). Fiscal quarters placed in the calendar quarter they mostly cover.",
        "does Nvidia's revenue keep pace with hyperscaler capex?", "does SMIC close the gap on TSMC under export controls?", "does chipmaking stay this concentrated in a few firms?"));
    const yoy = card("Revenue growth vs a year earlier", ...linesChart(lines(d.revenue_yoy), v => pct(v, 0), { small: true, hlines: [0] }),
      ask("Same quarter a year earlier. When TSMC and ASML grow slower than Nvidia, the bottleneck is packaging and pricing, not wafers.",
        "does growth fall back to the industry's ~10% a year?", "does a downturn like 2001, 2009 or 2023 follow the boom?", "is AI the industry's main market, as PCs and then phones were?"));
    const px = d.prices ? card("Share prices, rebased to 100 (Nasdaq)", ...linesChart(lines(d.prices), v => num(v, 0), { log: true }),
      ask("Daily closes, each rebased to 100 on the first day all have data; log scale. TSM and ASML are the US-listed shares. SMIC trades in Hong Kong (0981.HK) and is not on Nasdaq.",
        "does the market price chips as a cycle again?", "do equipment makers (ASML) gain from fabs spreading out of Taiwan?", "which of these still lead in 2045?"))
      : card("Share prices", el("div", { class: "muted" }, "Not available right now (" + (d.prices_error || "no data") + ")."));
    const rows = card("Hand-entered revenue", table(["Quarter end", "Company", "Revenue (bn)", "Source"], (d.rows || []).map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.series), el("td", {}, num(+r.value, 2)), srcCell(r)))),
      note("Add each quarter from the company's results release. Rows marked verify were entered from memory."));
    return [head, px, rev, yoy, rows];          // the daily price chart first: it drives the shared date axis, the quarterly charts follow
  },

  async gpus() {
    const d = await api("gpus"), C = d.chips || [], M = d.models || [], by = Object.fromEntries(C.map(c => [c.chip, c]));
    const tf = v => v == null ? "–" : v >= 1000 ? num(v / 1000, 2) + " PFLOPS" : num(v, v < 100 ? 1 : 0) + " TFLOPS";
    const times = v => v == null ? "–" : (v >= 10 ? num(v, 0) : v >= 1 ? num(v, 1) : num(v, 2)) + "×";
    const dur = y => y == null ? "–" : y >= 1e6 ? num(y / 1e6, 1) + "m years" : y >= 1000 ? num(y / 1000, 1) + "k years" : y >= 2 ? num(y, y < 20 ? 1 : 0) + " years"
      : y * 365.25 >= 2 ? num(y * 365.25, 0) + " days" : y * 8766 >= 1 ? num(y * 8766, 1) + " hours" : num(y * 525960, 0) + " min";
    const money = v => v == null ? "–" : v >= 1e9 ? "$" + num(v / 1e9, 1) + "bn" : v >= 1e6 ? "$" + num(v / 1e6, 0) + "m" : usd(v);
    const yr = s => s.slice(0, 4), ref = by[d.ref], gi = M.findIndex(m => m.model === "GPT-4"), g4 = gi >= 0 ? M[gi] : M[M.length - 1];
    const yrs = (chip, m) => (d.years[chip] || [])[M.indexOf(m)], fl = (chip, m) => ((d.fleet[m.model] || {})[chip]) || {};
    const best = C.slice().sort((a, b) => b.tflops16 - a.tflops16)[0];
    const head = card("One gaming card against the chips that train frontier models", el("div", { class: "kpis" },
      kpi(d.ref + ", peak 16-bit throughput", tf(ref && ref.tflops16)), kpi("H100 = this many " + d.ref + "s", times(by.H100 && by.H100.vs_ref)),
      kpi(best.chip + " = this many", times(best.vs_ref)), kpi(g4.model + " on one " + d.ref, dur(yrs(d.ref, g4))),
      kpi(d.ref + "s to train " + g4.model + " in " + d.run_days + " days", num(fl(d.ref, g4).chips)), kpi("their power draw", mw(fl(d.ref, g4).mw))), asOf(d), stale(d));
    // 3D 1: every chip against the RTX 5090 on four measures (log heights, 5090 = 1)
    const rel = (k, c) => ref && ref[k] && c[k] ? c[k] / ref[k] : null;
    const spec = card("Chip against chip in 3D: each measure as a multiple of the " + d.ref,
      ...chart3d({ x: C.map(c => c.chip), mode: "bars", log: true, h: 480, xHead: "chip", csvName: "chips vs " + d.ref, zFmt: v => v == null ? "–" : times(v),
        rows: [{ name: "Throughput per watt", z: C.map(c => rel("gflops_per_w", c)), color: css("--s3") }, { name: "Power draw", z: C.map(c => rel("power_w", c)), color: css("--s2") },
          { name: "Memory", z: C.map(c => rel("memory_gb", c)), color: css("--s4") }, { name: "16-bit throughput", z: C.map(c => rel("tflops16", c)), color: css("--s1") }],
        note: "Chips in launch order, left to right; rows front to back: throughput per watt, power, memory, throughput. Drag to turn; hover a bar." }),
      ask("Bar height (log scale) is the chip's figure divided by the " + d.ref + "'s, so the " + d.ref + " is 1× on every row. Throughput is the peak for dense 16-bit maths, what training uses; the table below says which figures are the maker's and which are estimates.",
        "does a consumer card stay within 10× of a data-centre chip?", "does memory, not arithmetic, decide which chips can train?", "does throughput per watt keep doubling every two to three years, or does power cap it?"));
    // 3D 2: years one chip would need for each reference model
    const order = C.slice().sort((a, b) => b.tflops16 - a.tflops16);
    const train = card("How long one chip would take to train each model",
      ...chart3d({ x: M.map(m => m.model), mode: "bars", log: true, heat: true, h: 480, xHead: "model", csvName: "years on one chip", zFmt: v => dur(v),
        rows: order.map(c => ({ name: c.chip, z: d.years[c.chip] })),
        note: "Models smallest to largest, left to right; the fastest chip at the front, the slowest at the back. Drag to turn; hover a bar." }),
      ask("Training compute of each model (Epoch AI's estimate, in FLOP) divided by what one chip delivers running flat out at " + Math.round(d.util * 100) + "% of its peak. Log scale: each gridline is a large step. " +
        "It is a measure of arithmetic only: one card cannot hold a large model in memory, so real runs spread the work across thousands of chips.",
        "does a single top chip train a GPT-3-scale model within a year?", "does a GPT-4-scale run fit on a few hundred chips?", "is today's frontier run a one-rack job?"));
    // fleet for one model, picked with the buttons
    let pick = g4.model;
    const fleetBox = el("div", {});
    const drawFleet = () => { const m = M.find(x => x.model === pick);
      fleetBox.replaceChildren(el("div", { class: "seg" }, ...M.map(x => el("button", { class: x.model === pick ? "on" : "", onclick: () => { pick = x.model; drawFleet(); } }, x.model))),
        el("div", { class: "muted", style: "margin-bottom:6px" }, m.model + " (" + yr(m.date) + "): " + flop(m.flop) + " · " + m.from + (m.note ? " · " + m.note : "")),
        table(["Chip", "One chip alone", "Chips for a " + d.run_days + "-day run", "Power, chips only", "Chips at list or street price"],
          order.map(c => { const f = fl(c.chip, m); return el("tr", {}, el("td", {}, c.chip), el("td", {}, dur(yrs(c.chip, m))), el("td", {}, num(f.chips)), el("td", {}, mw(f.mw)), el("td", {}, money(f.cost_usd))); }))); };
    drawFleet();
    const fleet = card("What it takes to train a model in " + d.run_days + " days, chip by chip", fleetBox,
      ask("Chips needed to finish the run in " + d.run_days + " days at " + Math.round(d.util * 100) + "% utilisation, their combined power draw (before cooling and networking) and what the chips alone would cost. " +
        "This is where the dashboard's question shows: a faster chip cuts the megawatts for the same run, so chips and power trade off.",
        "do export-limited chips (H20, Ascend) leave China needing several times the power for the same run?", "is the fleet for a frontier run limited by megawatts or by chip supply?", "does a GPT-4-scale run become a hobbyist's job?"));
    const list = card("The chips compared", table(["Chip", "Launch", "Kind", "Memory", "Power", "16-bit throughput", "Basis", "× " + d.ref, "GFLOPS per watt", "Price", "TFLOPS per $1,000", "Source"],
      C.slice().reverse().map(c => el("tr", {}, el("td", {}, c.chip + " (" + c.maker + ")"), el("td", {}, yr(c.date)), el("td", {}, c.kind), el("td", {}, c.memory_gb == null ? "–" : num(c.memory_gb) + " GB"),
        el("td", {}, c.power_w == null ? "–" : num(c.power_w) + " W"), el("td", {}, tf(c.tflops16)), el("td", {}, c.basis), el("td", {}, times(c.vs_ref)), el("td", {}, c.gflops_per_w == null ? "–" : num(c.gflops_per_w, 0)),
        el("td", {}, c.price_usd == null ? "–" : usd(c.price_usd)), el("td", {}, c.tflops_per_k == null ? "–" : num(c.tflops_per_k, 1)), srcCell(c)))),
      note("Basis: maker = the maker's tensor-core figure; estimate = twice the card's FP32 figure, because GeForce cards have no published 16-bit number; reported = press or analyst figure. " +
        "Spec-sheet peaks overstate the gap in practice: on one measured ResNet-50 run an H100 was about 1.8× an RTX 4090, not 6×. Prices: launch list price for GeForce, reported street prices for data-centre chips. " +
        "Kept in data/compute-chips/gpus.csv and train_models.csv; rows marked verify were entered from memory."));
    return [head, spec, train, fleet, list];
  },

  async supply() {
    const d = await api("supply"), C = d.capacity || {}, tw = d.taiwan, regs = Object.entries(C.regions || {});
    const us = (C.regions || {}).US || [];
    const head = card(null, el("div", { class: "kpis" }, kpi("Taiwan, share of <10nm capacity " + (tw ? tw.years.join(" → ") : ""), tw ? tw.from + "% → " + tw.to + "%" : "–"),
      kpi("US, share " + (tw ? tw.years.join(" → ") : ""), us.length ? us[0] + "% → " + us[us.length - 1] + "%" : "–"), kpi("Fab milestones", (d.fabs || []).length), kpi("Export-control steps", (d.controls || []).length)), asOf(d));
    const cap = regs.length ? card("Leading-edge (<10nm) logic capacity by country, % of world (SIA/BCG)",
      ...svgBars(regs.map(([k]) => k), (C.years || []).map((y, j) => ({ name: y + (j === C.years.length - 1 ? " (projected)" : ""), values: regs.map(([, v]) => v[j]), color: css(SERIES[j % SERIES.length]) })), { yFmt: v => Math.round(v) + "%", labelW: 70 }),
      ask("Share of the world's sub-10nm wafer capacity by where the fab stands. 2032 is SIA/BCG's projection with the CHIPS Act; every figure is hand-entered and marked verify until checked.",
        "do Arizona's fabs make Taiwan's share fall below two-thirds by 2030?", "does the US reach the projected 28%?", "is advanced chipmaking still an island single point of failure?"))
      : null;
    const fabs = card("Fab milestones: TSMC Arizona, Kumamoto, Dresden and others", table(["Date", "Site", "Country", "What happened", "Source"],
      (d.fabs || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.site), el("td", {}, r.country), el("td", { class: "wrap" }, r.event), srcCell(r)))),
      ask("Announcements, construction and volume production, newest first.", "do the announced fabs reach volume production on schedule?", "do they run at leading-edge nodes or a generation behind Taiwan?", "does Taiwan keep its newest nodes at home?"));
    const ctl = card("Export controls: US, Netherlands, Japan, China (Hong Kong under the China rules)", table(["Date", "Who", "What", "Source"],
      (d.controls || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.market), el("td", { class: "wrap" }, r.event), srcCell(r)))),
      ask("Each rule that changed who can buy AI chips, chipmaking tools or the minerals they need.", "do controls slow China's frontier training (Compute tab)?", "does China build a full domestic tool chain?", "are chips traded like arms?"));
    return [head, cap, fabs, ctl];
  },
};
window.TOPIC = { VIEWS };
})();
