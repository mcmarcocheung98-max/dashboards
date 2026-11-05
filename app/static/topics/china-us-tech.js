// China vs US Tech: tabs and cards. Data from /api/china-us-tech/<overview|models|research|ev|chips|markets>; helpers from topic.html.
// Leans: +1 = China gaining relative to the US, -1 = the US gaining.
(() => {
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const flop = v => v == null ? "–" : Number(v).toExponential(1).replace("e+", "e") + " FLOP";
const share = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const pc = v => v == null ? "–" : num(v, Math.abs(v) < 10 ? 1 : 0) + "%";
const mn = v => v == null ? "–" : num(v, v < 1 ? 2 : 1) + "m";
const COL = { US: "--s1", China: "--s2", UK: "--s4", "Hong Kong": "--s6", World: "--hold", Other: "--hold", Japan: "--s5", Korea: "--s3", Germany: "--hold" };
const colOf = (k, i) => css(COL[k] || SERIES[i % SERIES.length]);
const series = obj => Object.entries(obj || {}).filter(([, p]) => p && p.length).map(([k, pts], i) => ({ name: k, points: pts, color: colOf(k, i) }));
// integer year ticks, at most ~8 of them
const yearTicks = s => { const xs = s.flatMap(x => x.points.map(p => p[0])); if (!xs.length) return []; const a = Math.min(...xs), b = Math.max(...xs), step = Math.max(1, Math.ceil((b - a) / 8));
  const out = []; for (let y = a; y <= b; y += step) out.push(y); return out; };
const yearly = (s, fy, o = {}) => svgLines(s, { xFmt: v => String(Math.round(v)), xTicks: yearTicks(s), yFmt: fy, ...o });
const errs = (d, what) => d && d.errors && Object.keys(d.errors).length ? el("div", { class: "muted" }, what + " not available right now: " + Object.entries(d.errors).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
// what each chart shows, and the 5-, 10- and 20-year question it answers
const ask = (shows, q5, q10, q20) => note(el("span", {}, shows, el("br"), el("b", {}, "5 years: "), q5, " ", el("b", {}, "10 years: "), q10, " ", el("b", {}, "20 years: "), q20));
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");
// the same colours as the shared "what changed" squares: green = +1 (China gaining), red = -1 (US gaining), grey = neither
const leanSq = l => el("span", { title: l > 0 ? "China gaining" : l < 0 ? "US gaining" : "no clear move", style: "display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;margin-right:6px;background:" +
  leanCol(l) + (l === 0 ? ";opacity:.45" : "") });
const leanText = l => l > 0 ? "gap moving China's way" : l < 0 ? "US pulling ahead" : "little change";
const unavailable = (title, d, key) => card(title, el("div", { class: "muted" }, "Not available right now (" + ((d && d[key + "_error"]) || "no data") + ")."));
const last = p => p && p.length ? p[p.length - 1] : null;
const yearBars = (obj, fy, o = {}) => {
  const ks = Object.keys(obj || {}).filter(k => obj[k] && obj[k].length);
  const ys = [...new Set(ks.flatMap(k => obj[k].map(p => p[0])))].sort((a, b) => a - b);
  return svgBars(ys.map(String), ks.map((k, i) => ({ name: k, values: ys.map(y => { const p = obj[k].find(q => q[0] === y); return p ? p[1] : null; }), color: o.colorOf ? o.colorOf(k, i) : colOf(k, i) })), { yFmt: fy, ...o });
};

const VIEWS = {
  async overview() {
    const d = await api("overview"), T = d.tally || {}, L = d.layers || [];
    const head = card("Who leads each layer of the tech stack, and where is the gap closing?", el("div", { class: "kpis" },
      kpi("Layers tracked", L.length), kpi("Moving China's way", T.china || 0, (T.china || 0) > 0 ? "up" : ""), kpi("US pulling ahead", T.us || 0, (T.us || 0) > 0 ? "down" : ""),
      kpi("Little change", T.flat || 0), kpi("Layers the US leads", L.filter(r => /^US/.test(r.leader)).length), kpi("Layers China leads", L.filter(r => r.leader === "China").length)),
      note("Green: the latest reading moved towards China (+1). Red: towards the US (-1). Grey: within the rule's band (the same colours as the daily squares above). Each rule is listed in the table and in data/china-us-tech/README.md."),
      asOf(d), stale(d));
    const rows = card("Layer by layer", table(["Layer", "Leader", "Reading", "Now", "Direction", "Context"],
      L.map(r => el("tr", {}, el("td", {}, el("a", { href: "#" + r.tab }, r.layer)), el("td", {}, r.leader), el("td", { class: "wrap" }, r.label),
        el("td", {}, typeof r.value === "number" ? num(r.value, Math.abs(r.value) < 10 ? 2 : Math.abs(r.value) < 1000 ? 1 : 0) : String(r.value)),
        el("td", {}, leanSq(r.lean), leanText(r.lean)), el("td", { class: "wrap" }, r.detail, r.detail ? " · " : "", el("span", { class: "muted" }, r.rule))))),
      ...Object.keys(d.errors || {}).map(k => missing({ [k + "_error"]: d.errors[k] }, k, "The " + k + " tab")));
    const read = card("How to read it", el("div", { class: "muted", style: "font-size:13.5px;color:var(--ink2)" },
      el("p", {}, el("b", {}, "Models and compute: "), "the US leads on the largest training runs and the best closed models; China's labs are close behind on leaderboards and lead on open weights (AI models tab)."),
      el("p", {}, el("b", {}, "Patents and research: "), "China files the most international patents and writes the most AI papers; the US still writes more of the most-cited ones (Patents & research)."),
      el("p", {}, el("b", {}, "EVs and batteries: "), "China leads on adoption, exports and cells; the question is how far tariffs in the US and Europe slow its makers abroad (EVs & batteries)."),
      el("p", {}, el("b", {}, "Chips: "), "the US and its allies control the leading-edge tools and designs; the node gap at SMIC and China's chip import bill show whether controls hold (Chips trade)."),
      el("p", {}, el("b", {}, "Markets: "), "what investors pay for each side's tech champions, and where they choose to list (Markets).")));
    return [head, rows, read];
  },

  async models() {
    const d = await api("models"), E = d.epoch, A = d.arena || {};
    const out = [];
    if (E) {
      const i = E.years.indexOf(E.last_full), us = i >= 0 ? E.counts.US[i] : null, cn = i >= 0 ? E.counts.China[i] : null;
      const fr = E.frontier || {}, gap = t => { const a = valueAt(fr.US, t), b = valueAt(fr.China, t); return a && b ? Math.log10(a / b) : null; };
      // the frontier and leaderboard figures follow the timeline; the yearly counts below have no date to follow
      out.push(card(null, datedHead([
        { label: () => "Largest US training run to date", value: t => [flop(valueAt(fr.US, t)), ""] },
        { label: () => "Largest Chinese run", value: t => [flop(valueAt(fr.China, t)), ""] },
        { label: () => "Compute gap, US over China", value: t => { const g = gap(t); return [g == null ? "–" : num(g, 1) + " orders", ""]; } },
        { label: () => "Best US minus best Chinese, Arena", value: t => { const v = valueAt(A.gap, t); return [v == null ? "–" : num(v) + " pts", ""]; } }]),
        el("div", { class: "kpis", style: "margin-top:10px" }, kpi("US notable models, " + E.last_full, num(us)), kpi("China, " + E.last_full, num(cn)),
          kpi("China's share of the two", us + cn ? share(cn / (us + cn)) : "–")), asOf(d), stale(d)));
      out.push(card("Notable AI models per year, by country of the developer (Epoch AI)",
        ...svgBars(E.years.map(String), Object.entries(E.counts).map(([k, v], i) => ({ name: k, values: v, color: colOf(k, i) })), { yFmt: v => Math.round(v) }),
        ask("Models Epoch AI counts as notable (state of the art, highly cited or widely used), by the country of each developing organisation; a model from a US and a Chinese lab counts for both. The current year is partial (the share chart stops at the last full year).",
          "does China's count keep rising while the US's flattens, or do export controls cap it?", "does the UK (DeepMind) or Hong Kong keep a foothold?", "is frontier AI a two-country field, like aerospace, or spread out like software?")));
      out.push(el("div", { class: "grid2" },
        card("China's share of US + China notable models", ...yearly([{ name: "China", points: E.china_share, color: colOf("China") }], share, { h: 220 }),
          ask("China's count divided by the US and China together, per year.", "does the share pass 50%?", "does it hold when the US counts more frontier-scale runs?", "is the count of models still the right measure, or only the best one?")),
        card("Open-weight notable models per year", ...svgBars(E.years.map(String), ["US", "China"].map((k, i) => ({ name: k, values: E.open[k], color: colOf(k, i) })), { yFmt: v => Math.round(v), h: 220 }),
          ask("Notable models whose weights anyone can download (Epoch's accessibility field).", "do Chinese labs (Qwen, DeepSeek, Kimi) keep leading open weights?", "do open weights set the world standard, as Linux and Android did?", "does openness or control win the platform?"))));
      out.push(Object.keys(fr).length ? card("Largest training run to date, by country (log scale)", ...linesChart(series(fr), flop, { log: true }),
        ask("Each step is a new largest training run by a developer in that country (single-country models only). The gap is the vertical distance: one order of magnitude is ten times the compute.",
          "does the US-China gap stay at one to two orders of magnitude under chip controls?", "does China close it with domestic accelerators (Chips trade tab)?", "does compute stop deciding who leads, as efficiency gains (DeepSeek) suggest?"))
        : unavailable("Largest training runs", d, "epoch"));
      const tops = E.top || {};
      out.push(el("div", { class: "grid2" }, ...["US", "China"].filter(k => tops[k]).map(k => card("Largest runs: " + k, table(["Model", "Organisation", "Published", "Compute"],
        tops[k].map(r => el("tr", {}, el("td", {}, r.model), el("td", {}, r.org), el("td", {}, dateOf(r.date)), el("td", {}, flop(r.flop)))))))));
    } else out.push(card("Notable AI models", el("div", { class: "err" }, "Not available right now (" + (d.epoch_error || "no data") + ")."), stale(d)));
    if (A.lines) {
      out.push(card("Best US vs best Chinese model, LMArena text leaderboard (hand-entered snapshots)", ...linesChart(series(A.lines).map((s, i) => ({ ...s, color: colOf(i ? "China" : "US") })), v => num(v), { sync: false, small: true }),
        ask("The Arena score of the top-ranked model from each country at each snapshot. LMArena rescales scores over time, so read the gap, not the level.",
          "does a Chinese model take first place?", "does the gap close for good, as it did for smartphones?", "do leaderboards still separate the best models, or do they all saturate?"),
        table(["Snapshot", "Side", "Model", "Score", "Source"], (A.rows || []).map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.series), el("td", {}, r.model || ""), el("td", {}, num(+r.value)), srcCell(r))))));
    }
    return out;
  },

  async research() {
    const d = await api("research"), P = d.pct || {}, cs = d.cited_share;
    const lc = last(P.China), lu = last(P.US), sh = cs && cs.filter(p => p[0] <= new Date().getUTCFullYear() - 2);
    const head = card(null, el("div", { class: "kpis" }, kpi("China PCT filings" + (lc ? ", " + lc[0] : ""), num(lc && lc[1])), kpi("US" + (lu ? ", " + lu[0] : ""), num(lu && lu[1])),
      kpi("China's share of highly cited AI papers (US + China)" + (sh && sh.length ? ", " + last(sh)[0] : ""), sh && sh.length ? share(last(sh)[1]) : "–"),
      ...((d.top_cited || []).filter(r => r.series === "US" || r.series === "China").map(r => kpi("Top-100 cited AI papers, " + r.series + " (" + r.date.slice(0, 4) + ")", r.value)))),
      errs(d, "OpenAlex is"), asOf(d), stale(d));
    const pct = card("International patent applications (PCT) by origin", ...yearly(series(P), v => big(v)),
      ask("Applications under the Patent Cooperation Treaty by the applicant's country (WIPO). China passed the US in 2019. 2025 is provisional.",
        "does US filing keep falling while China's rises?", "do Korea and Japan hold their places?", "do patents still track who leads, or does AI move faster than filings?"));
    const gap = d.pct_gap ? card("China minus US, PCT applications", ...svgBars(d.pct_gap.map(p => String(p[0])), [{ name: "China − US", values: d.pct_gap.map(p => p[1]), colorFn: v => v >= 0 ? colOf("China") : css("--s1") }], { yFmt: v => big(v), h: 200 }),
      ask("Positive: China filed more. Gaps between bars are years with no row entered.", "does China's margin pass 25,000?", "does Huawei's filing lead keep China ahead?", "is the patent race over?")) : null;
    const pap = d.papers ? card("AI papers per year, by country of the authors' institutions (OpenAlex)", ...yearly(series(d.papers), v => big(v), { log: true }),
      ask("Works OpenAlex tags with the 'Artificial intelligence' concept, counted once per country that any author's institution is in. Log scale.",
        "does China keep writing about twice as many AI papers as the US?", "does UK and Hong Kong output keep pace?", "does publishing still matter when frontier labs stop publishing?")) : unavailable("AI papers (OpenAlex)", d, "papers");
    const cit = d.cited ? card("Highly cited AI papers (more than " + d.cited_threshold + " citations), by publication year", ...yearly(series(d.cited), v => big(v), { log: true }),
      ask("The same papers, keeping those with more than " + d.cited_threshold + " citations. Recent years have had less time to be cited, so every line falls at the end.",
        "does China's count of influential papers pass the US?", "is the UK still third?", "where is the research the next generation is built on written?")) : unavailable("Highly cited AI papers", d, "cited");
    const shc = cs ? card("China's share of highly cited AI papers, US + China", ...yearly([{ name: "China", points: cs, color: colOf("China") }], share, { h: 220, hline: 0.5 }),
      ask("China's count divided by the US and China together. The last two years are excluded from the overview's reading because citations are still arriving.", "does it stay above 50%?", "does quality follow quantity?", "is research leadership split by field?")) : null;
    const top = (d.top_cited || []).length ? card("The 100 most-cited AI papers (Stanford AI Index)", table(["Year", "Country", "Papers", "Source"], d.top_cited.map(r => el("tr", {}, el("td", {}, r.date.slice(0, 4)), el("td", {}, r.series), el("td", {}, r.value), srcCell(r)))),
      note("Hand-entered from the AI Index; add a row per country each April. China excludes Hong Kong here.")) : null;
    return [head, el("div", { class: "grid2" }, pct, gap), pap, el("div", { class: "grid2" }, cit, shc), top];
  },

  async ev() {
    const d = await api("ev"), S = d.share || {}, Bt = d.battery || {}, BT = d.byd_tesla || {};
    const lcn = last(S.China), lus = last(S.US), cn = (Bt.by_country || {}).China || [];
    const head = card(null, el("div", { class: "kpis" }, kpi("EV share of new cars, China" + (lcn ? " " + lcn[0] : ""), pc(lcn && lcn[1])), kpi("US" + (lus ? " " + lus[0] : ""), pc(lus && lus[1])),
      kpi("UK", pc((last(S.UK) || [])[1])), kpi("Hong Kong", pc((last(S["Hong Kong"]) || [])[1])), kpi("China NEV exports" + (last(d.exports) ? ", " + last(d.exports)[0] : ""), mn((last(d.exports) || [])[1])),
      kpi("Chinese makers' battery share" + (Bt.years && Bt.years.length ? ", " + last(Bt.years) : ""), pc(last(cn)))), asOf(d), stale(d),
      d.owid_live === false ? el("div", { class: "warn", style: "margin-top:6px" }, "Our World in Data is not reachable right now: shares are the hand-entered copy.") : null);
    const sh = card("Electric share of new car sales (battery-electric and plug-in hybrid)", ...yearly(series(S), v => pc(v)),
      ask("IEA Global EV Outlook through Our World in Data; Hong Kong is the share of new private car registrations (EPD/Transport Department, hand-entered).",
        "does the US share stay near 10% while China passes 60%?", "does the UK hit its zero-emission mandate path (80% by 2030)?", "is the petrol car gone everywhere, or only where China's cars are sold?"));
    const ex = d.exports ? card("China's NEV exports (CAAM, million vehicles)", ...svgBars(d.exports.map(p => String(p[0])), [{ name: "Exports", values: d.exports.map(p => p[1]), color: colOf("China") }], { yFmt: mn, h: 220 }),
      ask("New-energy vehicles shipped abroad by Chinese makers (BEV and plug-in hybrid).", "do tariffs in the US, EU and Canada slow the growth?", "do Chinese makers build abroad instead (Hungary, Thailand, Brazil)?", "does China sell most of the world's cars, as Japan did in the 1980s?")) : null;
    const sa = d.sales ? card("Electric cars sold (million)", ...yearly(series(d.sales), mn, { log: true }),
      ask("IEA via Our World in Data. Log scale.", "does US growth restart?", "how large is China's lead in volume?", "does the world reach 50 million EVs a year?")) : null;
    const bt = BT.BYD ? card("BYD vs Tesla, battery-electric deliveries (million)", ...yearBars(BT, mn, { colorOf: k => colOf(k === "BYD" ? "China" : "US"), h: 220 }),
      ask("Tesla's quarterly delivery reports and BYD's monthly volume filings (pure electric passenger cars only; BYD also sells as many plug-in hybrids).",
        "does BYD's lead widen outside China?", "does Tesla's robotaxi and Optimus bet matter more than car volume?", "which is the Toyota of electric cars?")) : null;
    const yrs = Bt.years || [], makers = Object.entries(Bt.makers || {});
    const bat = makers.length ? card("EV battery makers' share of installations (SNE Research, %)",
      ...svgBars(makers.map(([k]) => k), yrs.map((y, j) => ({ name: y, values: makers.map(([, v]) => v[j]), color: css(SERIES[j % SERIES.length]) })), { yFmt: v => Math.round(v) + "%", labelW: 70 }),
      ask("Share of the GWh installed in EVs sold worldwide, by cell maker. No US-headquartered maker is in the top ten; Panasonic, LG and SK On supply most US-built cells.",
        "do CATL and BYD pass 60% together?", "do US tax credits build a non-Chinese supply chain?", "is battery making as concentrated as oil refining?")) : null;
    const byc = yrs.length ? card("Battery share by makers' home country", ...yearly(Object.entries(Bt.by_country).map(([k, v], i) => ({ name: k, points: yrs.map((y, j) => [+y, v[j]]), color: colOf(k, i) })), v => Math.round(v) + "%", { h: 220 }),
      ask("The makers above summed by headquarters.", "does Korea's share keep falling?", "does China's pass 70%?", "do sodium-ion or solid-state cells reset the race?")) : null;
    return [head, sh, el("div", { class: "grid2" }, ex, bt), sa, bat, byc, cite(d.cited)].filter(Boolean);
  },

  async chips() {
    const d = await api("chips"), T = d.trade || {}, ng = d.nodes || [];
    const li = last(T.Imports), lg = last(ng);
    const head = card(null, el("div", { class: "kpis" }, kpi("China IC imports" + (li ? ", " + li[0] : ""), li ? usd(li[1]) + "bn" : "–"),
      kpi("vs the year before", pct(d.imports_yoy, 0)), kpi("SMIC behind TSMC" + (lg ? ", " + lg.node + "nm" : ""), lg ? num(lg.years, 1) + " years" : "–"),
      kpi("US and allied control steps, last 12 months", d.recent_n), kpi("Net (−1 tighten, +1 ease)", d.recent_direction, cls(d.recent_direction))), asOf(d));
    const tr = card("China's integrated-circuit trade, USD bn a year (GACC)", ...yearBars(T, v => "$" + Math.round(v) + "bn", { colorOf: (k, i) => css(SERIES[i % SERIES.length]), h: 240 }),
      ask("Customs value of chips imported (HS 8542) and exported. China spends more on chip imports than on crude oil. Hand-entered from GACC; rows marked verify still need checking.",
        "does the import bill fall as domestic fabs take share, or rise with AI demand?", "does China become a net exporter of mature-node chips?", "does China still need foreign chips at all?"), cite(d.cited));
    const mo = d.monthly && d.monthly.length >= 2 ? card("China IC imports per month, USD bn", ...linesChart([{ name: "Imports", points: d.monthly, color: colOf("China") }], v => "$" + num(v, 1) + "bn", { small: true }),
      ask("From the GACC monthly release, one row per month (data/china-us-tech/ic_imports_monthly.csv).", "do imports jump before each new control takes effect (stockpiling)?", "does the trend turn down?", "is the import bill a cost or a choke point?"))
      : card("China IC imports per month", el("div", { class: "muted" }, "No monthly rows yet. Add one row per month from GACC's 'major imports' table to data/china-us-tech/ic_imports_monthly.csv and the chart appears here."));
    const nodes = ng.length ? card("Leading node in volume production: SMIC vs TSMC", ...svgBars(ng.map(n => n.node + "nm"), [{ name: "Years behind", values: ng.map(n => n.years), color: colOf("China") }], { yFmt: v => num(v, 1) + "y", h: 200 }),
      table(["Node", "TSMC", "SMIC", "Years behind", "Note"], ng.map(n => el("tr", {}, el("td", {}, n.node + "nm"), el("td", {}, dateOf(n.tsmc)), el("td", {}, dateOf(n.smic)), el("td", {}, num(n.years, 1)), el("td", { class: "wrap" }, n.note)))),
      ask("For each node SMIC reached, how long after TSMC. TSMC's 16nm is paired with SMIC's 14nm. SMIC makes 7nm and 5nm-class chips without EUV tools, at lower yields.",
        "does the gap stay at four to five years without EUV?", "does China build its own EUV or an alternative?", "does the leading edge still matter, or do packaging and systems (Huawei CloudMatrix) decide?")) : null;
    const ctl = card("Export controls: US and allies, and China's counter-measures", table(["Date", "Who", "What", "Effect on China", "Source"],
      (d.controls || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.actor), el("td", { class: "wrap" }, r.event),
        el("td", {}, +r.direction < 0 ? el("span", { class: "pill bad" }, "tightens") : +r.direction > 0 ? el("span", { class: "pill ok" }, "eases") : el("span", { class: "pill" }, "counter-measure")), srcCell(r)))),
      ask("Each rule that changed what China can buy (chips, tools, memory) or what it lets others buy (minerals). Hong Kong has been under the China rules since June 2020.",
        "do the controls slow China's frontier models (AI models tab), or only redirect demand to Huawei?", "do rare-earth controls give China equal leverage?", "are chips traded like arms?"));
    const ms = card("SMIC and Huawei milestones", table(["Date", "Who", "What", "Source"],
      (d.milestones || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.who), el("td", { class: "wrap" }, r.event), srcCell(r)))),
      ask("Chips and systems China makes without TSMC or Nvidia.", "does Ascend ship in volume enough to train frontier models?", "does Huawei's own HBM end the memory bottleneck?", "is there a second full chip stack outside the US?"));
    return [head, tr, mo, nodes, ctl, ms].filter(Boolean);
  },

  async markets() {
    const d = await api("markets"), L = d.last || {}, Y = d.years || {};
    const ch1y = { lag: "1y", fmt: v => pct(v / 100, 0) };
    const head = card(null, d.baskets ? followHead([
      ...Object.entries(d.baskets).map(([k, pts]) => ({ label: k, points: pts, fmt: v => num(v, 0), delta: ch1y })),
      ...(d.ratio ? [{ label: "China ADRs ÷ US basket", points: d.ratio, fmt: v => num(v, 0), cls: v => cls(v - 100), delta: ch1y }] : [])])
      : el("div", { class: "kpis" }, ...Object.entries(L).map(([k, v]) => kpi(k + " · 1 year " + pct(v.y1, 0), num(v.v, 0)))), errs(d, "Some prices are"), asOf(d), stale(d));
    const m = d.members || {};
    const px = d.baskets ? card("US tech vs US-listed Chinese tech, rebased to 100 (Nasdaq quote API)", ...linesChart(series(d.baskets).map(s => ({ ...s, color: css(s.name === "US tech basket" ? "--s1" : s.name === "KWEB" ? "--s5" : "--s2") })), v => num(v, 0), { log: true }),
      ask("Equal-weighted buy and hold from the start of 2019: US basket " + (m["US tech basket"] || []).join(", ") + "; China basket " + (m["China tech ADRs"] || []).join(", ") +
          " (their US listings); KWEB, an ETF of Chinese internet shares. Prices without dividends, log scale.",
        "does China tech's discount close as earnings grow?", "does capital keep flowing to US AI leaders?", "are the two markets still comparable, or split by delisting and capital controls?"))
      : unavailable("Share prices", d, "baskets");
    const ra = d.ratio ? card("China basket over US basket (start = 100)", ...linesChart([{ name: "China ADRs ÷ US basket", points: d.ratio, color: colOf("China") }], v => num(v, 0), { small: true, hlines: [100] }),
      ask("Falling: the US basket did better. This is the overview's market reading, over the last 12 months.", "does the 2021 crackdown's derating reverse?", "do Chinese AI champions rerate like US ones?", "where are the world's most valuable tech companies?"))
      : null;
    const ks = Object.keys(Y), ys = [...new Set(ks.flatMap(k => Object.keys(Y[k])))].sort();
    const yr = ys.length ? card("Calendar-year returns", ...svgBars(ys, ks.map((k, i) => ({ name: k, values: ys.map(y => Y[k][y] == null ? null : Y[k][y]), color: css(["--s1", "--s2", "--s5", "--s6"][i % 4]) })), { yFmt: v => Math.round(v * 100) + "%", labelW: 40 }),
      ask("The baskets from the year-end closes above; Hang Seng TECH is the yearly return of the iShares Hang Seng TECH ETF in HKD (hand-entered; a stand-in for the index, which has no free feed Railway can reach).",
        "does Hong Kong tech outperform after four years of losses?", "do HK listings (CATL, Zhipu, MiniMax) deepen the index?", "is Hong Kong China's Nasdaq?")) : null;
    const li = card("Where tech lists: London, Hong Kong and New York", table(["Date", "Market", "What", "Source"],
      (d.listings || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.market), el("td", { class: "wrap" }, r.event), srcCell(r)))),
      ask("Listing decisions and rule changes. London keeps losing tech listings to New York; Hong Kong became the main venue for Chinese tech as US delisting risk rose.",
        "does London's 2024 rule reform bring tech back?", "does Hong Kong stay the world's top IPO venue?", "are there two separate capital markets for tech, one US and one Chinese?"));
    return [head, px, ra, yr, li].filter(Boolean);
  },
};
window.TOPIC = { VIEWS };
})();
