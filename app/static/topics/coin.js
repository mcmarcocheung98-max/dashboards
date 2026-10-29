// One BTC Cycles candidate coin on its own page (/hype, /ena, /sol, /near): the same script for each, which coin from SLUG.
// Data from /api/<slug>/overview (one payload for all three tabs; see app/topics/_coin_page.py); helpers from topic.html.
(() => {
const usdBig = v => v == null ? "–" : "$" + big(v);
const px = v => v == null ? "–" : v >= 1000 ? "$" + num(v, 0) : v >= 1 ? "$" + v.toFixed(2) : "$" + v.toPrecision(3);
const r1 = v => v == null ? "–" : v.toFixed(0);
const rsiCls = v => v == null ? "" : v >= 70 ? "down" : v <= 30 ? "up" : "";
const md = s => {   // inline links [text](url) -> anchors; everything else as text
  const out = [], re = /\[([^\]]+)\]\(([^)]+)\)/g; let i = 0, m;
  while ((m = re.exec(s))) { if (m.index > i) out.push(s.slice(i, m.index)); out.push(link(m[1], m[2])); i = m.index + m[0].length; }
  if (i < s.length) out.push(s.slice(i)); return out;
};
const asof = (pts, t) => {          // the value of a [[t, v], ...] series on date t: the last point at or before it
  if (!pts || !pts.length || t < pts[0][0]) return null;
  let lo = 0, hi = pts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid - 1; }
  return pts[lo][1];
};
const dateOf = t => new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const ord = n => n + (n % 10 === 1 && n % 100 !== 11 ? "st" : n % 10 === 2 && n % 100 !== 12 ? "nd" : n % 10 === 3 && n % 100 !== 13 ? "rd" : "th");

// every chart opens on the last year unless the reader already picked a range on this page
try { if (!sessionStorage.getItem("range:" + location.pathname)) RANGE = "1y"; } catch (e) { RANGE = "1y"; }

let DATA = null;                     // one download for the three tabs; a failure is retried on the next tab
const data = async () => DATA || (DATA = api("overview").catch(e => { DATA = null; throw e; }));

function header(f) {
  const L = f.links || {}, P = f.peers || {}, others = Object.entries(f.sibling_pages || {}).filter(([t]) => t !== f.ticker);
  return card(null,
    el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline" },
      el("b", { style: "font-size:17px" }, f.name, " ", el("span", { class: "muted" }, f.ticker)),
      el("span", { class: "pill" }, f.sector), f.note ? el("span", { class: "pill" }, f.note) : null,
      link("CoinMarketCap", L.coinmarketcap), L.defillama ? link("DefiLlama", L.defillama) : null, link("CoinGecko", L.coingecko)),
    el("div", { class: "muted", style: "margin-top:6px" }, "BTC Cycles candidate, doc rank " + f.rank,
      P.n ? " · market cap " + ord(P.market_cap) + " of " + P.n + " candidates · 90 days against BTC " + ord(P.vs_btc_90d) + " of " + P.n : "", ". ",
      el("a", { href: "/btc-cycles#candidates" }, "All candidates"),
      ...others.flatMap(([t, href]) => [" · ", el("a", { href }, t)])));
}

function strip(f) {
  const K = f.kpi, S = f.series;
  const pk = (t, latest, fn) => t == null ? latest : fn(t);
  const ratio90 = t => { const a = asof(S.price, t), b = asof(S.btc_indexed, t), a0 = asof(S.price, t - 90 * 86400), b0 = asof(S.btc_indexed, t - 90 * 86400);
    return a && b && a0 && b0 ? (a / b) / (a0 / b0) - 1 : null; };
  return datedHead([
    { label: t => t == null ? "Price" : "Price on " + dateOf(t), value: t => [px(pk(t, K.price, t => asof(S.price, t)))] },
    { label: () => "24h", value: t => { const v = pk(t, K.change_24h, t => { const a = asof(S.price, t), b = asof(S.price, t - 86400); return a && b ? a / b - 1 : null; }); return [pct(v, 1), cls(v)]; } },
    { label: () => "1 year", value: t => { const v = pk(t, K.change_1y, t => { const a = asof(S.price, t), b = asof(S.price, t - 365 * 86400); return a && b ? a / b - 1 : null; }); return [pct(v, 0), cls(v)]; } },
    { label: () => "From 1-year high", value: () => [pct(K.from_high, 0), cls(K.from_high)] },
    { label: () => "Market cap", value: t => [usdBig(pk(t, K.market_cap, t => asof(S.market_cap, t)))] },
    { label: () => "RSI 14", value: t => { const v = pk(t, K.rsi, t => asof(S.rsi, t)); return [r1(v), rsiCls(v)]; } },
    { label: () => "RSI vs BTC", value: t => { const v = pk(t, K.rsi_vs_btc, t => asof(S.rsi_vs_btc, t)); return [r1(v), rsiCls(v)]; } },
    { label: () => "90d vs BTC", value: t => { const v = pk(t, K.vs_btc_90d, ratio90); return [pct(v, 0), cls(v)]; } },
    { label: () => "Beta to BTC", value: () => [K.beta == null ? "–" : K.beta.toFixed(2)] },
    { label: () => "Base end-2028", value: () => [px(K.base_2028)] },
  ], { latest: "Today" });           // every chart on the tab drives it
}

function notesCard(f) {
  const N = f.notes || {};
  const rows = [N.narrative ? ["Why it fits", N.narrative] : null, N.standout ? ["What stands out", N.standout] : null,
    f.now && f.now.length ? ["Today", f.now.join(" ")] : null, N.thesis ? ["Thesis behind the projection", N.thesis] : null].filter(Boolean);
  return rows.length ? card("The case for " + f.ticker, el("div", { style: "display:grid;gap:6px;font-size:14px" },
    ...rows.map(([k, v]) => el("div", {}, el("b", {}, k + ": "), v))), note("\"Today\" is computed from live data; the rest is from data/btc-cycles/coin_notes.json.")) : null;
}

function fundamentalsCard(f) {
  const FD = f.fundamentals || {}, FS = FD.series || {}, K = FD.kpi || {}, S = f.series;
  const t0 = S.price[0][0];
  const rebase = pts => { const q = (pts || []).filter(p => p[0] >= t0 - 7 * 86400 && p[1] > 0); return q.length > 1 ? q.map(p => [p[0], p[1] / q[0][1] * 100]) : null; };
  const lines = [["Price", S.price, css("--s1")], ["Fees, 30 days", FS.fees_30d, css("--s2")], ["TVL", FS.tvl, css("--s3")], ["Circulating supply", FS.supply, css("--s4")]]
    .map(([n, pts, color]) => { const r = rebase(pts); return r ? { name: n, points: r, color, width: n === "Price" ? 2.5 : 1.5 } : null; }).filter(Boolean);
  const rel = (a, b) => a == null || b == null ? "" : " (1-year median " + (b >= 10 ? num(b, 0) : b.toFixed(2)) + "×)";
  const m = v => v == null ? "–" : (v >= 10 ? num(v, 0) : v.toFixed(2)) + "×";
  const out = [card("Fundamentals now", el("div", { class: "kpis" },
    kpi("Fees, last 30 days", usdBig(K.fees_30d)), kpi("Fees, annualised", usdBig(K.fees_annual)),
    kpi("Price-to-fees" + rel(K.p_fees, K.p_fees_median), m(K.p_fees), K.p_fees != null && K.p_fees_median != null ? (K.p_fees < K.p_fees_median ? "up" : "down") : ""),
    kpi("TVL", usdBig(K.tvl)), kpi("Market cap ÷ TVL" + rel(K.p_tvl, K.p_tvl_median), m(K.p_tvl), K.p_tvl != null && K.p_tvl_median != null ? (K.p_tvl < K.p_tvl_median ? "up" : "down") : ""),
    kpi("Unlocked (of max supply)", K.unlocked_share == null ? "–" : pct(K.unlocked_share, 0).replace("+", "")),
    kpi("Supply added, next 12 months", K.unlock_12m == null ? "–" : pct(K.unlock_12m, 1), K.unlock_12m > 0.05 ? "down" : "")),
    note("Green multiple = cheaper than its own 1-year median; red = dearer. More than 5% new supply in a year is marked red."))];
  if (lines.length > 1) out.push(card("Price against fees, TVL and supply, each rebased to 100 a year ago (log)",
    ...linesChart(lines, v => v == null ? "–" : v.toFixed(0), { log: true }),
    note("Price rising faster than fees or TVL = the multiple expanding; supply rising = dilution from unlocks and emissions.")));
  if (FS.p_fees && FS.p_fees.length) out.push(card("Price-to-fees (market cap ÷ annualised 30-day fees)", ...linesChart([{ name: "Price-to-fees", points: FS.p_fees }], m, {})));
  if (FS.tvl && FS.tvl.length) out.push(card("TVL", ...linesChart([{ name: "TVL", points: FS.tvl, color: css("--s3") }], usdBig, { small: true })));
  if (FS.schedule && FS.schedule.length > 3) {
    const now = S.price[S.price.length - 1][0];
    out.push(card("Unlock schedule: total unlocked supply, past and scheduled (DefiLlama)",
      ...linesChart([{ name: "Unlocked", points: FS.schedule.filter(p => p[0] <= now + 3 * 365 * 86400) }], v => v == null ? "–" : big(v), { small: true, sync: false })));
  }
  const src = Object.entries(FD.sources || {}).map(([k, u]) => k + ": [" + host(u) + "](" + u + ")").join(" · ");
  const miss = Object.entries(FD.errors || {}).map(([k, e]) => k + " (" + e.split(":")[0] + ")").join(", ");
  out.push(card(null, FD.updated ? null : note("Fundamentals come with the background price download; this coin has not been reached yet."),
    src ? el("div", { class: "muted", style: "font-size:12px" }, ...md("Sources: " + src)) : null,
    miss ? note("Not available for this coin: " + miss + ".") : null, stale(f)));
  return out;
}

function projectionCards(f) {
  const S = f.series, end = S.price[S.price.length - 1][0], pts = f.projection || [], FF = (f.fundamentals || {}).factors || {};
  const fx = v => v == null ? "–" : "×" + v.toFixed(2);
  const nowPt = [end, S.price[S.price.length - 1][1]];
  const at = p => Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000);
  const ws = [];                                        // empty days to the last scenario date, so the axis is to scale in time
  if (pts.length) for (let t = end + 86400; t <= at(pts[pts.length - 1]); t += 86400) ws.push(t);
  if (!pts.length) return [card("Projection", note("No projection: beta to BTC needs at least 60 days of overlapping prices."))];
  const chart = card("Bear / base / bull to end-2028 (beta " + (f.kpi.beta == null ? "–" : f.kpi.beta.toFixed(2)) + ", log)",
    ...linesChart([{ name: "Price", points: S.price, color: css("--s1") },
      { name: "Base", points: [nowPt, ...pts.map(p => [at(p), p.base])], color: css("--s2"), width: 3 },
      { name: "Bull", points: [nowPt, ...pts.map(p => [at(p), p.bull])], dashed: true, color: css("--up") },
      { name: "Bear", points: [nowPt, ...pts.map(p => [at(p), p.bear])], dashed: true, color: css("--down") },
      ...(pts.some(p => p.factor != null && Math.abs(p.factor - 1) > 0.005) ? [{ name: "Base, BTC beta only", points: [nowPt, ...pts.map(p => [at(p), p.base_beta_only])], color: css("--hold"), width: 1 }] : [])],
      px, { log: true, whitespace: ws, sync: false }));
  const big_ = chart.querySelector(".chart"); if (big_) big_.style.height = "460px";
  const last = at(pts[pts.length - 1]);
  let tries = 0;
  const frame = () => {
    const c = charts.find(x => x.chartElement && chart.contains(x.chartElement()));
    if (!c || !c.timeScale().width()) { if (tries++ < 40) setTimeout(frame, 100); return; }
    try { c.timeScale().setVisibleRange({ from: end - 365 * 86400, to: last + 20 * 86400 }); } catch (e) { c.timeScale().fitContent(); }
  };
  setTimeout(frame, 150);
  const tbl = card("The numbers", el("div", { class: "scroll" }, el("table", {},
    el("tr", {}, ...["Scenario", "Bear", "Base", "Bull", "Base, BTC beta only", "× Dilution", "× Valuation", "Implied market cap (base)", "Base vs today"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))),
    ...pts.map((p, i) => el("tr", {}, el("td", {}, p.label), ...[px(p.bear), px(p.base), px(p.bull), px(p.base_beta_only), fx(p.dilution), fx(p.valuation), usdBig((f.implied_mcap_base[i] || {}).mcap)]
      .map(v => el("td", { style: "text-align:right" }, v)), el("td", { style: "text-align:right", class: cls(p.base / f.kpi.price - 1) }, pct(p.base / f.kpi.price - 1, 0)))))),
    note("Price now × (BTC scenario ÷ BTC now) ^ beta, then × dilution (supply now ÷ supply at that date: " + (FF.dilution_basis || "no supply data, so 1") +
      ") × valuation (half-way back to the coin's own 1-year median " + (FF.valuation_basis || "multiple; no fees or TVL, so 1") + ", within 0.67-1.5). Mechanical; it says nothing about survival or the coin's own news."));
  const sc = f.scenarios || {};
  const btcRows = (sc.scenarios || []).map(s => el("tr", {}, el("td", {}, s.label), ...["bear", "base", "bull"].map(x => el("td", { style: "text-align:right", title: s[x].why }, usd(s[x].btc)))));
  const method = card("The BTC levels behind it", el("div", { class: "muted" }, sc.method || ""),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Scenario", "Bear BTC", "Base BTC", "Bull BTC"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))), ...btcRows)),
    note("Hover a BTC level for the reasoning. The levels are shared with every candidate on BTC Cycles (data/btc-cycles/scenarios.json)."));
  return [chart, tbl, method];
}

const VIEWS = {
  async overview() {
    const f = await data();
    if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now."), stale(f))];
    const S = f.series;
    return [header(f), card(null, strip(f)), notesCard(f),
      card(f.ticker + " and BTC rebased to the same start (log)", ...linesChart([{ name: f.ticker, points: S.price }, { name: "BTC, rebased", points: S.btc_indexed, dashed: true, color: css("--hold") }], px, { log: true })),
      el("div", { class: "grid2" },
        card(f.ticker + " ÷ BTC (log): rising = beating BTC", ...linesChart([{ name: f.ticker + "/BTC", points: S.ratio }], v => v == null ? "–" : v.toPrecision(3), { log: true, small: true })),
        card("RSI 14: against BTC (solid) and in USD (dashed)", ...linesChart([{ name: "RSI vs BTC", points: S.rsi_vs_btc }, { name: "RSI (USD)", points: S.rsi, dashed: true }], r1, { small: true, hlines: [30, 50, 70] }),
          note("Above 70: has run hard. Below 30: washed out.")),
        card("Market cap", ...linesChart([{ name: "Market cap", points: S.market_cap }], usdBig, { small: true }))),
      stale(f)];
  },
  async fundamentals() {
    const f = await data();
    if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now."))];
    return [header(f), ...fundamentalsCard(f)];
  },
  async projection() {
    const f = await data();
    if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now."))];
    return [header(f), ...projectionCards(f)];
  },
};
window.TOPIC = { VIEWS };
})();
