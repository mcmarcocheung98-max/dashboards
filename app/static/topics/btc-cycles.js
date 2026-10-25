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
const table = (cols, rows, opts = {}) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map(h => el("th", {}, h))),
  ...rows.map(r => el("tr", {}, ...cols.map((c, i) => { const v = Array.isArray(r) ? r[i] : r[c]; return el("td", { class: i === 0 ? "" : "wrap" }, ...md(String(v ?? ""))); })))));
const docLink = r => el("div", { class: "src", style: "margin-top:6px" }, "From the research doc, as of " + r.as_of + ": ", link("open it", r.doc_url), ".");
const pill = state => el("span", { class: "pill " + ({ firing: "ok", "not yet": "", watch: "", "no data": "bad" }[state] || "") }, state);

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
      kpi("Hyperliquid revenue, 30 days", usdBig(L.hl_revenue_30d)), kpi("Perp-DEX volume, 30 days", usdBig(L.perp_volume_30d))), asOf(d), stale(d));
    const live = (key, title, noteText) => d[key] && d[key].length ? card(title, ...linesChart([{ name: title, points: d[key] }], v => usdBig(v), { small: true }), note(noteText))
      : card(title, el("div", { class: "muted" }, "Not available right now (" + (d[key + "_error"] || "no data") + ")."));
    const grid = el("div", { class: "grid2" },
      live("defi_tvl", "DeFi TVL (all chains)", "The doc: TVL leads for DeFi and L1s; the TVL-to-market-cap ratio collapsing marked the Nov 2021 top."),
      live("stablecoins", "Stablecoin supply", "The doc: $130bn → ~$300bn through cycle 4; the rail every other sector settles on."),
      live("hl_tvl", "Hyperliquid TVL", "The doc: grew every month of the 2026 bear, $4.1bn (Dec 2025) → $7.4bn (Sep 2026)."),
      live("hl_revenue_30d", "Hyperliquid revenue, rolling 30 days", "The doc: fees and revenue are the single best survival predictor; 99% of Hyperliquid's goes to buybacks."),
      live("perp_volume_30d", "Perp-DEX volume, rolling 30 days", "The doc: perp DEXs went from 0.1% of global futures (2023) to 12.3% (Oct 2026)."));
    const top = d.perp_top && d.perp_top.length ? card("Perp DEXs by 30-day volume (DefiLlama)", table(["Protocol", "Volume, 30 days", "Share of top 8"], d.perp_top.map(p => [p.name, usdBig(p.volume_30d), pct(p.share_30d, 0)]))) : null;
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
