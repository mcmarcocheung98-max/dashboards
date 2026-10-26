// BTC Cycles & Sector Rotation: tabs and cards. Data from /api/btc-cycles/<cycles|sectors|metrics|candidates|signals>.
// Every table is rendered from data/btc-cycles/research.json (the doc); the live series sit beside the doc's claims.
(() => {
let cycleN = 4;
const usdBig = v => v == null ? "–" : "$" + big(v);
const xf = v => v == null ? "–" : (v >= 100 ? Math.round(v) : v.toFixed(v >= 10 ? 0 : 1)) + "×";
const md = s => {   // the doc's inline links [text](url) -> anchors; everything else as text
  const out = [], re = /\[([^\]]+)\]\(([^)]+)\)/g; let i = 0, m;
  while ((m = re.exec(s))) { if (m.index > i) out.push(s.slice(i, m.index)); out.push(link(m[1], m[2])); i = m.index + m[0].length; }
  if (i < s.length) out.push(s.slice(i)); return out;
};
const para = (s, cls = "muted") => el("div", { class: cls, style: "margin-top:6px" }, ...md(s));
// MSTR's price against the value of its bitcoin per share (the price at mNAV 1), with mNAV shaded about 1 in the lower part of the same
// chart: red above 1 = the market pays a premium for each bitcoin (rich), green below = a discount (cheap). Price on the right (log); mNAV on an
// unlabelled overlay scale (its value is in the legend and the line above), with mNAV 1 dashed.
function premiumChart(d) {
  const host = el("div", { class: "chart", style: "height:420px" }), legend = el("div", { class: "legend" });
  const ok = a => (a || []).filter(p => p[1] != null);
  const mn = ok(d.mnav), money = v => v == null ? "–" : "$" + num(v, v >= 100 ? 0 : 2);
  const gap = v => v == null ? "–" : v.toFixed(2) + "× (" + (v >= 1 ? "premium " : "discount ") + Math.abs((v - 1) * 100).toFixed(0) + "%)";
  setTimeout(() => {
    const c = newChart(host, { rightPriceScale: { borderVisible: false, mode: 1 } });
    const up = css("--up"), dn = css("--down"), a = (hex, x) => hex + Math.round(x * 255).toString(16).padStart(2, "0");
    const band = c.addBaselineSeries({ priceScaleId: "mnav", baseValue: { type: "price", price: 1 }, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      topLineColor: dn, topFillColor1: a(dn, 0.4), topFillColor2: a(dn, 0.08), bottomLineColor: up, bottomFillColor1: a(up, 0.08), bottomFillColor2: a(up, 0.4),
      priceFormat: { type: "custom", formatter: v => v.toFixed(v >= 10 ? 0 : 1) + "×", minMove: 0.01 } });
    band.setData(dedupe(mn));
    band.createPriceLine({ price: 1, color: css("--muted"), lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    const line = (color, dashed) => c.addLineSeries({ color, lineWidth: 2, lineStyle: dashed ? 2 : 0, priceLineVisible: false, lastValueVisible: false,
      priceFormat: { type: "custom", formatter: money, minMove: 0.01 } });
    const nav = line(css("--hold"), true), px = line(css("--s1"), false);
    nav.setData(dedupe(ok(d.nav_per_share)));
    px.setData(dedupe(ok(d.mstr)));
    const rows = [[px, "MSTR", "background:" + css("--s1"), ok(d.mstr), money], [nav, "Its bitcoin per share (price at mNAV 1)", "background:" + css("--hold"), ok(d.nav_per_share), money],
      [band, "mNAV", "background:linear-gradient(90deg," + dn + " 50%," + up + " 50%)", mn, gap]].filter(r => r[3].length);
    const made = rows.map(([s, name, sw, pts, f]) => {
      const val = el("b", {}, f(pts[pts.length - 1][1]));
      const btn = el("button", { onclick: () => s.applyOptions({ visible: !btn.classList.toggle("off") }) }, el("span", { class: "sw" + (s === nav ? " dash" : ""), style: sw }), name, " ", val);
      legend.append(btn);
      return { s, val, pts, f };
    });
    c.subscribeCrosshairMove(p => made.forEach(m => { const v = p && p.seriesData ? p.seriesData.get(m.s) : null; m.val.textContent = m.f(v ? v.value : m.pts[m.pts.length - 1][1]); }));
    c.priceScale("right").applyOptions({ mode: 1, scaleMargins: { top: 0.04, bottom: 0.36 } });     // prices in the top two thirds
    c.priceScale("mnav").applyOptions({ scaleMargins: { top: 0.7, bottom: 0.02 } });                  // the mNAV band below them, on an overlay scale
    // name the band where it is drawn, since the dollar axis runs past it: "premium" just above the mNAV 1 line, "discount" just below
    const tag = (txt, color) => el("div", { style: "position:absolute;font-size:11px;font-weight:600;pointer-events:none;color:" + color }, txt);
    const above = tag("▲ premium · mNAV above 1", dn), under = tag("▼ discount · mNAV below 1", up);
    host.style.position = "relative"; host.append(above, under);
    const place = () => { const y = band.priceToCoordinate(1); [above, under].forEach(t => { t.style.display = y == null ? "none" : ""; });
      const r = (c.priceScale("right").width() + 8) + "px";              // right-aligned beside the price axis, clear of the chart logo
      if (y != null) { above.style.top = (y - 16) + "px"; under.style.top = (y + 3) + "px"; above.style.right = under.style.right = r; } };
    c.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(place));
    requestAnimationFrame(() => requestAnimationFrame(place));
    if (ok(d.mstr).length) syncAdd(c, px, dedupe(ok(d.mstr))); else fit(c);
  });
  // where today sits against its own history
  let now = null;
  if (mn.length) {
    const last = mn[mn.length - 1][1], vals = mn.map(p => p[1]).sort((x, y) => x - y), med = vals[Math.floor(vals.length / 2)];
    const below = Math.round(100 * vals.filter(v => v < last).length / vals.length);
    now = el("div", { class: "muted", style: "margin:2px 0 6px" }, el("b", { class: last >= 1 ? "down" : "up" }, "Now " + gap(last)),
      ": MSTR trades " + (last >= 1 ? "above" : "below") + " the value of its bitcoin. mNAV was lower than today in " + below + "% of weeks since " +
      new Date(mn[0][0] * 1000).getUTCFullYear() + " (median " + med.toFixed(2) + "×).");
  }
  return [now, legend, host];
}
const table = (cols, rows, opts = {}) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map(h => el("th", {}, h))),
  ...rows.map(r => el("tr", {}, ...cols.map((c, i) => { const v = Array.isArray(r) ? r[i] : r[c]; return el("td", { class: i === 0 ? "" : "wrap" }, ...md(String(v ?? ""))); })))));
const docLink = r => el("div", { class: "src", style: "margin-top:6px" }, "From the research doc, as of " + r.as_of + ": ", link("open it", r.doc_url), ".");
const pill = state => el("span", { class: "pill " + ({ firing: "ok", "not yet": "", watch: "", "no data": "bad" }[state] || "") }, state);

// mNAV strategies and the exit window: today's checklist, the rule backtests (recomputed from the live data), and how people value MSTR
function strategiesCards(S) {
  if (!S) return [];
  const M = S.measures || {}, x = v => v == null ? "–" : v.toFixed(2) + "×";
  const tone = { exit: "bad", caution: "bad", watch: "", clear: "ok" };
  const label = { exit: "exit signal", caution: "caution", watch: "in window", clear: "clear" };
  const rows = (S.checklist || []).map(c => el("tr", {}, el("td", {}, el("b", {}, c.rule)), el("td", { class: "wrap" }, c.test), el("td", { class: "wrap" }, c.now),
    el("td", {}, el("span", { class: "pill " + (tone[c.state] || "") }, label[c.state] || c.state)), el("td", { class: "wrap muted" }, c.why)));
  const exits = (S.checklist || []).filter(c => c.state === "exit").length, cautions = (S.checklist || []).filter(c => c.state === "caution").length;
  const verdict = exits ? exits + " exit signal" + (exits > 1 ? "s" : "") + " on" : cautions ? "No exit signal; " + cautions + " caution flag" + (cautions > 1 ? "s" : "") : "No exit signal";
  const check = card("Exit window for MSTR: the checklist on today's data",
    el("div", { class: "kpis" }, kpi("mNAV, basic", x(M.basic)), kpi("mNAV, diluted", x(M.diluted)), kpi("mNAV, enterprise value", x(M.ev)),
      kpi("Checklist", verdict, exits ? "down" : cautions ? "" : "up")),
    note("Enterprise value = diluted market cap + debt + preferreds − cash" + (M.ev_inputs_date ? " (balance sheet as of " + M.ev_inputs_date + ")" : "") +
      ". Strategy's own figure since 23 Jul 2026 is price ÷ net bitcoin per share, which runs higher; the levels below are basic mNAV, the series with history."),
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Rule", "Test", "Now", "Status", "Why it matters"].map(h => el("th", {}, h))), ...rows)));
  const T = S.backtests || [];
  const curves = card("mNAV strategies backtested, since " + (S.since || "2021").slice(0, 4) + " (weekly, log)",
    ...linesChart(T.map((t, i) => ({ name: t.rule, points: t.equity, color: i === 1 ? css("--hold") : undefined, dashed: i === 1 })), xf, { log: true }),
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Rule", "Growth of $1", "Per year", "Worst drawdown", "Time in MSTR", "Switches"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))),
      ...T.map(t => el("tr", {}, el("td", {}, el("b", {}, t.rule)), ...[xf(t.multiple), pct(t.cagr, 0), pct(t.max_dd, 0), Math.round(t.in_mstr * 100) + "%", String(t.switches)]
        .map((v, i) => el("td", { style: "text-align:right", class: i === 1 ? cls(t.cagr) : i === 2 ? "down" : "" }, v)))))),
    el("ul", { class: "muted", style: "margin:6px 0 0;padding-left:18px;font-size:12.5px" }, ...T.map(t => el("li", {}, el("b", {}, t.rule + ": "), t.how || ""))),
    note("Weekly closes; a decision at one week's close earns the next week; 0.2% per switch; cash earns nothing. Thresholds are the published ones (2.5× where short sellers and Strategy's " +
      "old issuance tiers sat, 1.25× near where Chanos covered), not fitted to this data. One cycle and a half is a small sample: the BTC-trend filter is the robust result " +
      "(it cut the worst drawdown from about −86% to about −50% in every variant and out of sample in 2024-26); the divergence rule's edge comes from a single episode (2025). Not advice."));
  const R = S.research || {};
  const research = R.sections ? card("How people value MSTR and its bitcoin",
    ...R.sections.flatMap(s => [el("h3", { style: "margin:10px 0 4px;font-size:14px" }, s.title), el("ul", { style: "margin:0;padding-left:18px" }, ...s.points.map(p => el("li", { class: "muted", style: "margin:3px 0" }, ...md(p))))]),
    note(R.about || "")) : null;
  return [check, curves, research];
}

const VIEWS = {
  async cycles() {
    const d = await api("cycles"), R = d.research, n = d.now;
    const head = card(null, n ? el("div", { class: "kpis" }, kpi("BTC (" + n.date + ")", usd(n.price)), kpi("vs Oct 2025 peak", pct(n.vs_peak, 0), cls(n.vs_peak)),
      kpi("vs Jun 2026 low", pct(n.vs_low, 0), cls(n.vs_low)), kpi("vs 200-day average", pct(n.vs_ma200, 0), cls(n.vs_ma200)),
      kpi("Days since the 2024 halving", num(n.days_since_halving)), kpi("Days to the next (~" + d.next_halving.slice(0, 7) + ")", num(n.days_to_next_halving)))
      : el("div", { class: "muted" }, "Live price not available right now (" + (d.price_error || "no data") + "); the research below still stands."),
      stale(d), docLink(R));
    const bottom = card("Bottom line", ...R.bottom_line.map(p => para(p, "")));
    const hl = (d.halvings || []).map((t, i) => ({ x: t, label: "Halving " + (i + 1) }));
    const priceCard = d.price ? card("BTC price since 2010 (log scale), with halvings and the doc's peaks and lows",
      ...linesChart([{ name: "BTC", points: d.price }, { name: "200-day average", points: d.ma200 || [], dashed: true, color: css("--hold") }], v => usd(v), { log: true }),
      el("div", { class: "chips", style: "margin-top:6px" }, ...(d.markers || []).map(m => el("span", { class: "pill" }, m.date.slice(0, 7) + " · " + m.label))),
      note("Halvings: " + (d.halvings || []).map(t => new Date(t * 1000).toISOString().slice(0, 10)).join(", ") + ". Coin Metrics community data, weekly closes.")) : null;
    const ov = d.overlay && Object.keys(d.overlay).length ? card("Each cycle from its halving (price ÷ price on halving day, log scale)",
      ...svgLines(Object.entries(d.overlay).map(([k, pts]) => ({ name: k, points: pts, width: k.startsWith("Cycle 4") ? 2.5 : 1.5 })),
        { log: true, xFmt: v => (v >= 0 ? "+" : "") + v + "d", yFmt: xf, hline: 1, vlines: [{ x: 0, label: "halving" }], h: 300, note: "x = days before / after the halving. Hover to read each cycle." }),
      note("The doc's shape: bottom 12–18 months before the halving, peak 12–18 months after, then a one-year bear, with the multiple shrinking each time.")) : null;
    const dd = d.drawdown ? card("Drawdown from the running high", ...linesChart([{ name: "Drawdown", points: d.drawdown, color: css("--down") }], v => pct(v, 0), { small: true }),
      note("Cycle 4's -53% against -77% to -87% in the three before it.")) : null;
    const anat = card("BTC cycle anatomy, 2011–2026", para(R.anatomy.intro), table(R.anatomy.columns, R.anatomy.rows), para(R.anatomy.after));
    return [head, bottom, priceCard, ov, dd, anat];
  },
  async sectors() {
    const d = await api("sectors");
    const seg = el("div", { class: "seg" }, ...d.cycles.map(c => el("button", { class: c.n === cycleN ? "on" : "", onclick: () => { cycleN = c.n; render(); } }, "Cycle " + c.n)));
    const c = d.cycles.find(x => x.n === cycleN);
    const sectorCol = c.columns[0];
    const bars = c.rows.flatMap(r => r._multiples.filter(m => m.x > 0).map(m => ({ cat: (m.label ? m.label + " · " : "") + r[sectorCol].split(" (")[0].slice(0, 22), x: m.x })));
    const mult = bars.length ? card("Peak multiples in this cycle (log scale)", ...svgBarsLog(bars)) : null;
    const tbl = card(c.heading, para(c.intro), table(c.columns, c.rows), para(c.after));
    const cross = card("Cross-cycle comparison", para(d.cross_cycle.intro), table(d.cross_cycle.columns, d.cross_cycle.rows));
    return [card(null, seg, el("div", { class: "muted" }, "Pick a cycle. Figures are the doc's, approximate before 2024.")), tbl, mult, cross];
  },
  async metrics() {
    const d = await api("metrics"), R = d.research, L = d.latest || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("DeFi TVL", usdBig(L.defi_tvl)), kpi("Stablecoin supply", usdBig(L.stablecoins)), kpi("Hyperliquid TVL", usdBig(L.hl_tvl)),
      kpi("Hyperliquid revenue, 30 days", usdBig(L.hl_revenue_30d)), kpi("Hyperliquid fees, 30 days", usdBig(L.hl_fees_30d)), kpi("DEX volume (spot), 30 days", usdBig(L.dex_volume_30d))), asOf(d), stale(d));
    const live = (key, title, noteText) => d[key] && d[key].length ? card(title, ...linesChart([{ name: title, points: d[key] }], v => usdBig(v), { small: true }), note(noteText))
      : card(title, el("div", { class: "muted" }, "Not available right now (" + (d[key + "_error"] || "no data") + ")."));
    const grid = el("div", { class: "grid2" },
      live("defi_tvl", "DeFi TVL (all chains)", "The doc: TVL leads for DeFi and L1s; the TVL-to-market-cap ratio collapsing marked the Nov 2021 top."),
      live("stablecoins", "Stablecoin supply", "The doc: $130bn → ~$300bn through cycle 4; the rail every other sector settles on."),
      live("hl_tvl", "Hyperliquid TVL", "The doc: grew every month of the 2026 bear, $4.1bn (Dec 2025) → $7.4bn (Sep 2026)."),
      live("hl_revenue_30d", "Hyperliquid revenue, rolling 30 days", "The doc: fees and revenue are the single best survival predictor; 99% of Hyperliquid's goes to buybacks."),
      live("hl_fees_30d", "Hyperliquid fees, rolling 30 days", "Perp activity on the largest perp DEX; DefiLlama's all-perp volume became a paid endpoint in 2026. The doc: perp DEXs went from 0.1% of global futures (2023) to 12.3% (Oct 2026)."),
      live("dex_volume_30d", "DEX volume (spot), rolling 30 days", "All chains, spot DEXs only (DefiLlama)."));
    const top = d.dex_top && d.dex_top.length ? card("Spot DEXs by 30-day volume (DefiLlama)", table(["Protocol", "Volume, 30 days", "Share of top 8"], d.dex_top.map(p => [p.name, usdBig(p.volume_30d), pct(p.share_30d, 0)]))) : null;
    const tbl = card("Common metrics of cycle winners", para(R.intro), table(R.columns, R.rows), para(R.after));
    return [head, grid, top, tbl];
  },
  async candidates() {
    const [d, k] = await Promise.all([api("candidates"), api("coins")]);
    const R = d.research, sc = k.scenarios || { scenarios: [] };
    const px = (v) => v == null ? "–" : v >= 1000 ? "$" + num(v, 0) : v >= 1 ? "$" + v.toFixed(2) : "$" + v.toPrecision(3);
    const r1 = v => v == null ? "–" : v.toFixed(0);
    const rsiCls = v => v == null ? "" : v >= 70 ? "down" : v <= 30 ? "up" : "";
    // the doc's table, folded by default
    let open = false;
    const docCard = card(null, el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: e => { open = !open; body.style.display = open ? "" : "none"; e.currentTarget.textContent = (open ? "Hide" : "Show") + " the doc's ranked table"; } }, "Show the doc's ranked table"));
    const body = el("div", { style: "display:none;margin-top:10px" }, para(R.intro), table(R.columns, R.rows), para(R.after), docLink({ as_of: d.as_of, doc_url: "https://claude.ai/artifact/5Z9ca6X7eka9R3XdxZKcb3" }));
    docCard.append(body);
    // method card
    const method = card("Projection method (mechanical, not a forecast)", el("div", { class: "muted" }, sc.method || ""),
      el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Scenario", "Bear BTC", "Base BTC", "Bull BTC"].map(h => el("th", {}, h))),
        ...(sc.scenarios || []).map(s => el("tr", {}, el("td", {}, s.label), ...["bear", "base", "bull"].map(x => el("td", { title: s[x].why }, usd(s[x].btc))))))),
      note("Hover a BTC level for the reasoning. BTC now: " + usd(k.btc_now) + ". Edit data/btc-cycles/scenarios.json to change the levels."),
      k.notes_about ? note("Coin notes: " + k.notes_about + " The \"Today\" line is computed from live data.") : null, stale(k));
    // one row per coin, grouped by the doc's rank
    const byRank = {};
    for (const c of k.coins || []) (byRank[c.rank] = byRank[c.rank] || []).push(c);
    const sections = Object.keys(byRank).sort((a, b) => a - b).map(rank => {
      const rows = byRank[rank].map(c => coinRow(c, px, r1, rsiCls));
      return card(rank + " · " + byRank[rank][0].sector, ...rows);
    });
    if (!k.coins || !k.coins.length) sections.push(card("Candidate coins", el("div", { class: "err" }, "Not available right now (" + (k.btc_error || "no data") + ").")));
    const ev = d.evidence || {};
    const evCards = [["3 · RWA on-chain value ex-stablecoins", ev["RWA on-chain value ex-stablecoins (USD)"], usdBig], ["4 · Prediction-market monthly volume", (ev["Prediction-market monthly volume (USD)"] || []).filter(p => p[1] > 0), usdBig],
      ["5 · x402 cumulative payment volume", ev["x402 cumulative payment volume (USD)"], usdBig], ["1 · Perp-DEX share of global futures", ev["Perp-DEX share of global futures (%)"], v => v == null ? "–" : v.toFixed(1) + "%"]]
      .map(([t, pts, f]) => pts && pts.length ? card(t, ...linesChart([{ name: t.slice(4), points: pts }], f, { small: true })) : null).filter(Boolean);
    const evidence = card("Sector evidence without a liquid token (hand-entered; sources in data/btc-cycles/evidence.csv)", el("div", { class: "grid2" }, ...evCards));
    return [docCard, method, ...sections, evidence];
  },
  async etf() {
    const d = await api("etf"), K = d.kpi || {};
    const m = v => v == null ? "–" : (v < 0 ? "−" : "") + "$" + big(Math.abs(v) * 1e6);
    const head = card(null, el("div", { class: "kpis" }, kpi("Net flows since launch", m(K.since_launch_usd_m), cls(K.since_launch_usd_m)),
      kpi("BTC taken in since launch", K.since_launch_btc == null ? "–" : num(K.since_launch_btc) + " BTC"), kpi("Last 30 days", m(K.last_30d_usd_m), cls(K.last_30d_usd_m)),
      kpi("Last day (" + (K.last_day || "–") + ")", m(K.last_day_usd_m), cls(K.last_day_usd_m)), kpi("Streak", K.streak == null ? "–" : Math.abs(K.streak) + (K.streak >= 0 ? " days in" : " days out"), cls(K.streak)),
      kpi("BlackRock IBIT share of net flows", pct(K.ibit_share, 0))),
      el("div", { class: "muted", style: "margin-top:6px" }, "US spot bitcoin ETFs since they began trading on 11 Jan 2024. Best day " + m(K.best_day_usd_m) + " (" + (K.best_day || "–") + "), worst " + m(K.worst_day_usd_m) + " (" + (K.worst_day || "–") + ")."),
      missing(d, "farside", "Per-issuer flows (Farside)"), missing(d, "bitbo", "Flows in BTC (bitbo)"), asOf(d), stale(d));
    const daily = d.daily_usd_m ? card("Daily net flows, all US spot ETFs (US$)", ...linesChart([{ name: "Net flow", points: d.daily_usd_m.map(p => [p[0], p[1] * 1e6]), bar: true }], v => usdBig(v), { small: true })) : null;
    const cum = d.cum_usd_m ? card("Cumulative net flows (US$, right) against the BTC price (left)",
      ...linesChart([{ name: "Cumulative flows", points: d.cum_usd_m.map(p => [p[0], p[1] * 1e6]), fmt: v => usdBig(v) },
        ...(d.btc_price ? [{ name: "BTC price", points: d.btc_price, axis: "left", color: css("--hold"), dashed: true, fmt: v => usd(v) }] : [])], v => usdBig(v)),
      note("Flows lead price less than they seem: both respond to the same news. Watch the 30-day sum turning, the doc's signal 4.")) : null;
    const cumBtc = d.cum_btc ? card("Cumulative BTC taken in by US spot ETFs", ...linesChart([{ name: "BTC", points: d.cum_btc }], v => num(v) + " BTC", { small: true }), note("bitbo, in BTC rather than dollars, so price moves do not inflate it.")) : null;
    const roll = d.roll30_usd_m ? card("Rolling 30-trading-day net flows (US$)", ...linesChart([{ name: "30-day flows", points: d.roll30_usd_m.map(p => [p[0], p[1] * 1e6]), bar: true }], v => usdBig(v), { small: true })) : null;
    const issuers = d.cum_by_issuer ? card("Cumulative net flows by issuer (US$)", ...linesChart(Object.entries(d.cum_by_issuer).map(([k, pts]) => ({ name: k + (d.issuers[k] ? " · " + d.issuers[k] : ""), points: pts.map(p => [p[0], p[1] * 1e6]) })), v => usdBig(v)),
      note("GBTC's line falls because it converted from a trust with a high fee; most of its outflow moved to the other funds.")) : null;
    const tbl = d.table ? card("By issuer", table(["Ticker", "Issuer", "Since launch", "Last 30 trading days", "Last day", "Best day", "Worst day"],
      d.table.map(r => [r.ticker, r.issuer, m(r.since_launch), m(r.last_30d), m(r.last_day), m(r.best_day), m(r.worst_day)])), note("US$; Farside's daily table, net of creations and redemptions.")) : null;
    const intl = Object.keys(d.intl || {}).length ? card("Hong Kong ETFs and UK ETNs: BTC held (hand-entered)", ...linesChart(Object.entries(d.intl).map(([k, pts]) => ({ name: k, points: pts })), v => num(v) + " BTC", { small: true }),
      table(["Date", "Market", "BTC", "Source"], d.intl_rows.map(r => [r.date, r.series, num(+r.value), "[" + host(r.source) + "](" + r.source + ")" + (r.note ? " · " + r.note : "")])),
      note("No free daily feed for these: add a row to data/btc-cycles/etf_holdings.csv from the issuers' holdings pages.")) : null;
    const ms = card("Milestones", table(["Date", "Market", "What happened", "Source"], (d.milestones || []).map(r => [r.date, r.market, r.event, "[" + host(r.source) + "](" + r.source + ")"])));
    return [head, daily, cum, cumBtc, roll, issuers, tbl, intl, ms];
  },
  async mstr() {
    const d = await api("mstr"), K = d.kpi || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("BTC held", num(K.held)), kpi("Share of 21m supply", K.share_of_supply == null ? "–" : (K.share_of_supply * 100).toFixed(2) + "%"), kpi("Value of the BTC", usdBig(K.value_usd)),
      kpi("Approx. average cost", usd(K.approx_avg_cost)), kpi("mNAV", K.mnav == null ? "–" : K.mnav.toFixed(2) + "×"), kpi("MSTR", usd(K.mstr, 2)),
      kpi("90-day correlation with BTC", K.corr90 == null ? "–" : K.corr90.toFixed(2)), kpi("90-day beta to BTC", K.beta90 == null ? "–" : K.beta90.toFixed(2)),
      kpi("Purchases recorded", num(K.purchases)), kpi("Last purchase", K.last_purchase || "–")),
      note(d.note || ""), note("Prices: " + (d.price_source || "–") + "."), asOf(d), stale(d));
    const held = card("BTC held", ...linesChart([{ name: "BTC held", points: d.held }], v => num(v), { small: true }));
    const px = card("MSTR vs BTC, both rebased to Aug 2020 (log)", ...linesChart([{ name: "MSTR", points: d.mstr_rebased }, { name: "BTC", points: d.btc_rebased, color: css("--hold"), dashed: true }], v => xf(v), { log: true }));
    const mn = card("MSTR vs the value of its bitcoin: premium (overvalued) and discount (undervalued)", ...premiumChart(d),
      note("mNAV = share market value ÷ value of its bitcoin (basic shares). Red above 1: the market pays a premium for each bitcoin, which lets Strategy issue shares to buy more; " +
        "green below 1: a discount, and that engine stalls (the doc: the treasury trade is over once the premium compresses). Where the blue line sits above the grey dashed line is the premium in dollars."));
    const cb = card("Correlation and beta of daily returns with BTC (rolling 90 trading days)", ...linesChart([{ name: "Correlation", points: d.corr90 }, { name: "Beta", points: d.beta90, axis: "left", dashed: true }], v => v == null ? "–" : v.toFixed(2), { small: true }));
    const bps = card("BTC per 1,000 MSTR shares", ...linesChart([{ name: "BTC per 1,000 shares", points: d.btc_per_1000_shares }], v => v == null ? "–" : v.toFixed(3), { small: true }),
      note("Rising = purchases added more bitcoin than new shares diluted; falling = dilution outran buying."));
    const buys = card("Every recorded purchase (newest first)", table(["Date", "BTC added", "Held after", "BTC price that day", "Approx. US$"],
      (d.purchases || []).map(b => [b.date, num(b.btc), num(b.held_after), usd(b.btc_price), usdBig(b.approx_usd)])));
    const tre = (d.treasuries || []).map(t => card(t.company + " (" + t.country + ", " + t.yahoo + ")",
      t.held && t.held.length ? note("Latest disclosed holding: " + num(t.held[t.held.length - 1][1]) + " BTC" + (t.held_value_usd ? ", worth " + usdBig(t.held_value_usd) + " at today's BTC price" : "") + ".") : null,
      t.price ? linesChart([{ name: t.yahoo, points: t.price }], v => v == null ? "–" : v.toFixed(2), { small: true })
        : el("div", { class: "muted", title: (t.price_tried || []).join("\n") }, "Holdings only: no share-price feed answers from the server (Yahoo refuses it; CNBC tried). The holdings below are from the company's own announcements."),
      t.price ? note("Daily closes in local currency from " + (t.price_source || "Yahoo") + (t.corr90 != null ? "; 90-day correlation with BTC: " + t.corr90.toFixed(2) : "") + ".") : null,
      table(["Date", "BTC held", "Source"], t.rows.map(r => [r.date, num(+r.btc_held), "[" + host(r.source) + "](" + r.source + ")" + (r.note ? " · " + r.note : "")]))));
    return [head, mn, ...strategiesCards(d.strategies), el("div", { class: "grid2" }, held, bps), px, cb, buys,
      tre.length ? card("UK and Hong Kong bitcoin treasury companies", el("div", { class: "muted" }, "Holdings hand-entered in data/btc-cycles/treasuries.csv from each company's announcements; share prices from Yahoo, else CNBC, else holdings only.")) : null, ...tre];
  },
  async signals() {
    const d = await api("signals"), R = d.research;
    const rows = d.status.map((s, i) => el("tr", {}, el("td", {}, i + 1), el("td", { class: "wrap" }, s.signal), el("td", {}, pill(s.state)), el("td", { class: "wrap" }, s.reading), el("td", { class: "wrap" }, s.note)));
    const status = card("The six signals, read mechanically today (" + d.as_of + ")", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["#", "Signal", "Status", "Reading", "How"].map(h => el("th", {}, h))), ...rows)),
      note("Firing = the doc's condition is met on today's data. These are rules applied to public data, not a recommendation."));
    const doc = card("What the doc says to watch, in order", para(R.intro, ""), el("ol", { style: "margin:6px 0 0 18px;padding:0" }, ...R.items.map(s => el("li", { style: "margin:4px 0" }, ...md(s)))));
    const timing = card("Timing on the halving clock", para(R.timing, ""));
    const breakers = card("What could break the four-year pattern", para(R.breakers, ""));
    const charts = [];
    if (d.volume && d.volume.length) charts.push(card("BTC spot volume, 30-day average (CoinGecko)", ...linesChart([{ name: "Volume", points: d.volume }, { name: "$10bn threshold", points: d.volume.map(p => [p[0], 10e9]), dashed: true, color: css("--hold") }], v => usdBig(v), { small: true })));
    if (d.dominance_log && d.dominance_log.length > 1) charts.push(card("BTC dominance, logged daily since deploy", ...linesChart([{ name: "Dominance", points: d.dominance_log }], v => v == null ? "–" : v.toFixed(1) + "%", { small: true })));
    return [status, ...charts, doc, timing, breakers];
  },
};

// one candidate coin: links, KPI strip, 90-day sparkline, and on demand its four charts
function coinRow(c, px, r1, rsiCls) {
  const head = el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline" },
    el("b", {}, c.name, " ", el("span", { class: "muted" }, c.ticker)),
    c.links && c.links.coinmarketcap ? link("CoinMarketCap", c.links.coinmarketcap) : null, c.links && c.links.defillama ? link("DefiLlama", c.links.defillama) : null,
    c.links && c.links.coingecko ? link("CoinGecko", c.links.coingecko) : null, c.note ? el("span", { class: "pill" }, c.note) : null);
  const N = c.notes || {};
  const notes = N.narrative ? el("div", { class: "notes", style: "margin-top:8px;display:grid;gap:4px;font-size:13px" },
    el("div", {}, el("b", {}, "Why it fits: "), N.narrative), el("div", {}, el("b", {}, "What stands out: "), N.standout),
    c.now && c.now.length ? el("div", {}, el("b", {}, "Today: "), c.now.join(" ")) : null) : null;
  if (c.error) return el("div", { class: "card", style: "margin-top:8px;opacity:.7" }, head, notes, el("div", { class: "muted" }, "Not available right now (" + c.error + ")."));
  const K = c.kpi;
  const strip = el("div", { class: "kpis", style: "margin-top:8px" }, kpi("Price", px(K.price)), kpi("24h", pct(K.change_24h, 1), cls(K.change_24h)), kpi("1 year", pct(K.change_1y, 0), cls(K.change_1y)),
    kpi("Market cap", usdBig(K.market_cap)), kpi("RSI 14", r1(K.rsi), rsiCls(K.rsi)), kpi("RSI vs BTC", r1(K.rsi_vs_btc), rsiCls(K.rsi_vs_btc)),
    kpi("Beta to BTC", K.beta == null ? "–" : K.beta.toFixed(2)), kpi("90d vs BTC", pct(K.vs_btc_90d, 0), cls(K.vs_btc_90d)),
    kpi("Base end-2027", px(K.base_2027)), kpi("Base end-2028", px(K.base_2028)));
  const spark = el("div", { style: "margin-top:6px" }, ...linesChart([{ name: "90 days", points: c.spark || [] }], px, { small: true, sync: false }));
  spark.querySelector(".chart").style.height = "120px";
  const more = el("div", {});
  let loaded = false;
  const btn = el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit;margin-top:6px", onclick: async () => {
    if (loaded) { more.style.display = more.style.display === "none" ? "" : "none"; btn.textContent = more.style.display === "none" ? "Show charts" : "Hide charts"; return; }
    btn.textContent = "Loading…";
    try { const f = await api("coin-" + c.ticker.toLowerCase()); more.replaceChildren(...coinCharts(f, px, r1)); loaded = true; btn.textContent = "Hide charts"; }
    catch (err) { more.replaceChildren(el("div", { class: "err" }, "Could not load: " + err.message)); btn.textContent = "Retry"; }
  } }, "Show charts");
  return el("div", { class: "card", style: "margin-top:8px" }, head, notes, strip, spark, btn, more);
}

function coinCharts(f, px, r1) {
  const S = f.series, end = S.price[S.price.length - 1][0];
  const price = card("Price, 365 days (log), with BTC rebased to the same start", ...linesChart([{ name: f.ticker, points: S.price }, { name: "BTC, rebased", points: S.btc_indexed, dashed: true, color: css("--hold") }], px, { log: true, small: true }));
  const rsi = card("RSI 14: the coin ÷ BTC ratio (solid) and the coin in USD (dashed)", ...linesChart([{ name: "RSI vs BTC", points: S.rsi_vs_btc }, { name: "RSI (USD)", points: S.rsi, dashed: true }], r1, { small: true, hlines: [30, 50, 70] }),
    note("Above 70: has run hard (against BTC for the solid line). Below 30: washed out."));
  const mcap = card("Market cap, 365 days", ...linesChart([{ name: "Market cap", points: S.market_cap }], v => usdBig(v), { small: true }));
  const pts = f.projection || [];
  const nowPt = [end, S.price[S.price.length - 1][1]];
  const at = p => Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000);
  const ws = [];                                        // empty days to the last scenario date, so the axis is to scale in time
  if (pts.length) for (let t = end + 86400; t <= at(pts[pts.length - 1]); t += 86400) ws.push(t);
  const proj = card("Projection: bear / base / bull at end-2027 and end-2028 (beta " + (f.kpi.beta == null ? "–" : f.kpi.beta.toFixed(2)) + ")",
    ...linesChart([{ name: "Price", points: S.price },
      ...(pts.length ? [{ name: "Base", points: [nowPt, ...pts.map(p => [at(p), p.base])], color: css("--s1"), width: 3 },
        { name: "Bull", points: [nowPt, ...pts.map(p => [at(p), p.bull])], dashed: true, color: css("--up") },
        { name: "Bear", points: [nowPt, ...pts.map(p => [at(p), p.bear])], dashed: true, color: css("--down") }] : [])],
      px, { log: true, extend: true, whitespace: ws }),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Scenario", "Bear", "Base", "Bull", "Implied market cap (base)"].map(h => el("th", {}, h))),
      ...pts.map((p, i) => el("tr", {}, el("td", {}, p.label), el("td", {}, px(p.bear)), el("td", {}, px(p.base)), el("td", {}, px(p.bull)), el("td", {}, usdBig((f.implied_mcap_base[i] || {}).mcap)))))),
    f.notes && f.notes.thesis ? el("div", { style: "margin-top:8px;font-size:13px" }, el("b", {}, "Thesis behind the projection: "), f.notes.thesis) : null,
    note("Price now × (BTC scenario ÷ BTC now) ^ beta. Mechanical; it says nothing about the coin's own fundamentals, unlocks or survival."));
  return [el("div", { class: "grid2", style: "margin-top:8px" }, price, rsi, mcap, proj), stale(f)];
}

// horizontal-ish bars on a log scale for multiples: one row per sector/coin, label left, bar + value right
function svgBarsLog(items) {
  const read = el("div", { class: "muted", style: "min-height:18px" }, "Peak multiple from the cycle's low, as the doc gives it (approximate).");
  const box = svgBox(Math.max(120, items.length * 24 + 30), (host, W, H) => {
    const pad = { l: 190, r: 70, t: 8, b: 22 }, lo = 1, hi = Math.max(...items.map(i => i.x)) * 1.2;
    const X = v => pad.l + (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)) * (W - pad.l - pad.r);
    const svg = svgEl("svg", { width: W, height: H, style: "display:block" }, host);
    for (const v of logTicks(lo, hi).filter(v => [1, 10, 100, 1000, 10000].includes(v))) { svgEl("line", { x1: X(v), x2: X(v), y1: pad.t, y2: H - pad.b, stroke: css("--line") }, svg);
      svgEl("text", { x: X(v), y: H - 6, fill: css("--muted"), "font-size": 11, "text-anchor": "middle" }, svg).textContent = v + "×"; }
    items.forEach((it, i) => { const y = pad.t + i * 24;
      svgEl("text", { x: pad.l - 8, y: y + 15, fill: css("--ink2"), "font-size": 11, "text-anchor": "end" }, svg).textContent = it.cat;
      svgEl("rect", { x: X(lo), y: y + 4, width: Math.max(1, X(it.x) - X(lo)), height: 14, rx: 2, fill: css(SERIES[i % SERIES.length]) }, svg);
      svgEl("text", { x: X(it.x) + 6, y: y + 15, fill: css("--ink"), "font-size": 11 }, svg).textContent = xf(it.x); });
  });
  return [read, box];
}
window.TOPIC = { VIEWS };
})();
