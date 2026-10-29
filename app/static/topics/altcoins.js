// Altcoin Study: tabs and cards. Data from /api/altcoins/<zones|hype|ena|sol|near|basket|season> (app/topics/altcoins.py, _coin_page.py,
// memecoins.py); helpers from topic.html. One tab per candidate coin (overview, fundamentals and projection on one page), the memecoin
// basket and meme season, and every coin's buy zone.
(() => {
const usdBig = v => v == null ? "–" : "$" + big(v);
const px = v => v == null ? "–" : v >= 1000 ? "$" + num(v, 0) : v >= 1 ? "$" + v.toFixed(2) : v >= 0.01 ? "$" + v.toFixed(4) : "$" + v.toPrecision(3);
const r1 = v => v == null ? "–" : v.toFixed(0);
const rsiCls = v => v == null ? "" : v >= 70 ? "down" : v <= 30 ? "up" : "";
const ZCLS = { "in zone": "up", "above zone": "", "no zone": "down" };

// every chart opens on the last year unless the reader already picked a range on this page
try { if (!sessionStorage.getItem("range:" + location.pathname)) RANGE = "1y"; } catch (e) { RANGE = "1y"; }

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

function header(f) {
  const L = f.links || {}, P = f.peers || {}, others = Object.entries(f.sibling_pages || {}).filter(([t]) => t !== f.ticker);
  return card(null,
    el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline" },
      el("b", { style: "font-size:17px" }, f.name, " ", el("span", { class: "muted" }, f.ticker)),
      el("span", { class: "pill" }, f.sector), f.note ? el("span", { class: "pill" }, f.note) : null,
      link("CoinMarketCap", L.coinmarketcap), L.defillama ? link("DefiLlama", L.defillama) : null, link("CoinGecko", L.coingecko)),
    el("div", { class: "muted", style: "margin-top:6px" }, "BTC Cycles candidate, doc rank " + f.rank,
      P.n ? " · market cap " + ord(P.market_cap) + " of " + P.n + " candidates · 90 days against BTC " + ord(P.vs_btc_90d) + " of " + P.n : "", ". ",
      el("a", { href: "/btc-cycles#candidates" }, "All candidates"), " · ", el("a", { href: "#zones" }, "Buy zones"),
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

const STATE = { "meme season": "up", "out of season": "down" };

// every chart opens on the last year unless the reader already picked a range on this page
try { if (!sessionStorage.getItem("range:" + location.pathname)) RANGE = "1y"; } catch (e) { RANGE = "1y"; }

// the sortable basket table: click a header to sort, again to flip
function basketTable(coins) {
  const COLS = [["name", "Coin", c => c.name.toLowerCase(), 1], ["price", "Price", c => c.kpi.price, -1], ["change_24h", "24h", c => c.kpi.change_24h, -1],
    ["change_7d", "7 days", c => c.kpi.change_7d, -1], ["change_30d", "30 days", c => c.kpi.change_30d, -1], ["change_1y", "1 year", c => c.kpi.change_1y, -1],
    ["from_high", "From 1y high", c => c.kpi.from_high, -1], ["market_cap", "Market cap", c => c.kpi.market_cap, -1], ["share", "Share of basket", c => c.kpi.share, -1],
    ["rsi", "RSI 14", c => c.kpi.rsi, -1], ["rsi_vs_btc", "RSI vs BTC", c => c.kpi.rsi_vs_btc, -1], ["vs_btc_90d", "90d vs BTC", c => c.kpi.vs_btc_90d, -1],
    ["beta", "Beta to BTC", c => c.kpi.beta, -1]];
  let key = "market_cap", dir = -1;
  const live = coins.filter(c => c.kpi), dead = coins.filter(c => !c.kpi);
  const box = el("div", { class: "scroll" });
  const cell = (c, k) => {
    const K = c.kpi, v = K[k];
    if (k === "name") return el("td", {}, link(c.name, c.link), " ", el("span", { class: "muted" }, c.ticker + " · " + c.chain));
    if (k === "price") return el("td", { style: "text-align:right" }, px(v));
    if (k === "market_cap") return el("td", { style: "text-align:right" }, usdBig(v));
    if (k === "share") return el("td", { style: "text-align:right" }, v == null ? "–" : (v * 100).toFixed(0) + "%");
    if (k === "rsi" || k === "rsi_vs_btc") return el("td", { style: "text-align:right", class: rsiCls(v) }, r1(v));
    if (k === "beta") return el("td", { style: "text-align:right" }, v == null ? "–" : v.toFixed(2));
    return el("td", { style: "text-align:right", class: cls(v) }, pct(v, 0));
  };
  const draw = () => {
    const col = COLS.find(c => c[0] === key);
    const rows = live.slice().sort((a, b) => { const x = col[2](a), y = col[2](b); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * dir; });
    box.replaceChildren(el("table", {},
      el("tr", {}, ...COLS.map(([k, label]) => el("th", { style: "cursor:pointer;white-space:nowrap" + (k === "name" ? "" : ";text-align:right"),
        onclick: () => { if (key === k) dir = -dir; else { key = k; dir = COLS.find(c => c[0] === k)[3]; } draw(); } }, label + (k === key ? (dir < 0 ? " ▾" : " ▴") : "")))),
      ...rows.map(c => el("tr", {}, ...COLS.map(([k]) => cell(c, k)))),
      ...dead.map(c => el("tr", {}, el("td", {}, link(c.name, c.link), " ", el("span", { class: "muted" }, c.ticker)), el("td", { colspan: COLS.length - 1, class: "muted" }, "Not available right now (" + c.error + ").")))));
  };
  draw();
  return box;
}

function sparkCard(c) {
  if (!c.kpi) return null;
  const k = c.kpi;
  const box = card(null, el("div", { style: "display:flex;justify-content:space-between;gap:8px;align-items:baseline" },
      el("b", {}, c.name, " ", el("span", { class: "muted" }, c.ticker)), el("span", {}, px(k.price), " ", el("span", { class: cls(k.change_30d) }, pct(k.change_30d, 0) + " 30d"))),
    ...linesChart([{ name: "90 days", points: c.spark }], px, { small: true, sync: false }));
  const ch = box.querySelector(".chart"); if (ch) ch.style.height = "120px";
  return box;
}


// ------------------------------------------------------------------ buy zones
const pAbs = v => v == null ? "–" : Math.round(Math.abs(v) * 100) + "%";
const zoneText = z => z.status === "in zone" ? "In zone: " + pAbs(z.vs_top) + " below the top"
  : z.status === "above zone" ? "Above zone: needs a " + pAbs(z.vs_top) + " fall to reach the top" : z.status === "no zone" ? "No zone" : z.status;

function zoneCard(f) {
  const z = f.zone;
  if (!z || z.status === "no data") return card("Buy zone", note(z ? "Not enough history yet: " + z.why + "." : "Prices are still loading."));
  const S = f.series.price, t0 = Math.max(S[0][0], S[S.length - 1][0] - 365 * 86400), t1 = S[S.length - 1][0];
  const flat = (name, v, color) => v == null ? null : { name, points: [[t0, v], [t1, v]], dashed: true, color, width: 1.5 };
  return card("Buy zone", el("div", { style: "font-size:18px;font-weight:650;margin-bottom:6px" }, el("span", { class: ZCLS[z.status] || "" }, zoneText(z))),
    el("div", { class: "kpis" },
      kpi("Price now", px(z.price)), kpi("Zone top (" + z.basis + ")", px(z.top)), kpi("Mid", px(z.mid)), kpi("Floor (1-year low)", px(z.floor)),
      kpi("200-day average", px(z.ma200)), kpi("Base end-2028 ÷ 2", px(z.value_cap)), kpi("30 days", pct(z.change_30d, 0), cls(z.change_30d)),
      kpi("RSI 14", r1(f.kpi.rsi), rsiCls(f.kpi.rsi))),
    ...linesChart([{ name: f.ticker, points: S.filter(p => p[0] >= t0) }, flat("Zone top", z.top, css("--up")), flat("Mid", z.mid, css("--s3")),
      flat("Floor", z.floor, css("--down"))].filter(Boolean), px, { log: true, small: true, sync: false }),
    note(z.status === "no zone" ? "No zone: " + z.why + "." : "Top = the lower of the 200-day average and half the base-case price at end-2028 (so the base case at least doubles from there); " +
      "floor = the lowest close of the last year; mid = half-way, for staged entries. In zone while still falling is common: read the 30-day move and RSI with it. Mechanical, not advice."));
}

function zonesTable(rows) {
  const order = { "in zone": 0, "above zone": 1, "no zone": 2 };
  const sorted = rows.slice().sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3) || (a.vs_top ?? 9) - (b.vs_top ?? 9));
  const H = ["Coin", "Status", "Price", "Zone top", "Mid", "Floor (1y low)", "Top set by", "Price vs top", "30 days", "RSI 14"];
  return el("div", { class: "scroll" }, el("table", {},
    el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...sorted.map(r => el("tr", {},
      el("td", {}, el("a", { href: "#" + r.tab }, r.ticker), " ", el("span", { class: "muted" }, r.group === "Memecoin" ? "meme" : "candidate")),
      el("td", { class: ZCLS[r.status] || "muted" }, r.status === "loading" ? "loading" : r.status),
      ...(r.top == null && r.status !== "no zone" ? [el("td", { colspan: H.length - 2, class: "muted" }, r.why || "Prices are loading in the background, back in a few minutes.")] :
        [px(r.price), px(r.top), px(r.mid), px(r.floor), r.basis || "–"].map(v => el("td", { style: "text-align:right" }, v)).concat([
          el("td", { style: "text-align:right", class: r.status === "in zone" ? "up" : "" }, r.vs_top == null ? "–" : pct(r.price / r.top - 1, 0)),
          el("td", { style: "text-align:right", class: cls(r.change_30d) }, pct(r.change_30d, 0)),
          el("td", { style: "text-align:right", class: rsiCls(r.rsi) }, r1(r.rsi))]))))));
}

const section = t => el("h2", { style: "font-size:16px;margin:22px 0 2px" }, t);

// ------------------------------------------------------------------ volume zones: candles, big-volume days, the bands they left, unlocks
const pctAbs1 = v => v == null ? "–" : (Math.abs(v) * 100).toFixed(1) + "%";
const dayOfTs = t => new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
let VZ_COIN = null, VZ_DAYS = 365;
try { VZ_COIN = sessionStorage.getItem("vz:coin"); } catch (e) {}

function zoneChart(c, days) {
  // candlesticks, each zone a band (baseline series filled between its top and bottom) from its birth to its death or today,
  // ▲ / ▼ markers on the big days with the volume ratio, orange squares on unlock days; joins the tab's shared date axis
  const host = el("div", { class: "chart", style: "height:360px" });
  const bars = c.bars.filter(b => b[0] >= c.bars[c.bars.length - 1][0] - days * 86400);
  if (!bars.length) return host;
  const first = bars[0][0], last = bars[bars.length - 1][0];
  setTimeout(() => {
    const ch = newChart(host, { rightPriceScale: { borderVisible: false, mode: 1 } });
    const prec = c.price >= 100 ? 2 : c.price >= 1 ? 4 : c.price >= 0.01 ? 5 : 7;
    const s = ch.addCandlestickSeries({ upColor: css("--up"), downColor: css("--down"), borderVisible: false, wickUpColor: css("--up"), wickDownColor: css("--down"),
      priceFormat: { type: "price", precision: prec, minMove: Math.pow(10, -prec) }, priceLineVisible: false, lastValueVisible: false });
    s.setData(bars.map(b => ({ time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] })));
    for (const z of c.zones) {
      if (z.died != null && z.died < first) continue;
      const col = z.kind === "buy" ? "31,157,99" : "214,69,61", live = z.died == null, a = Math.max(z.born, first), b = live ? last : Math.max(z.died, a + 86400);
      const zs = ch.addBaselineSeries({ baseValue: { type: "price", price: z.lo }, topLineColor: "rgba(" + col + "," + (live ? 0.8 : 0.35) + ")",
        topFillColor1: "rgba(" + col + "," + (live ? 0.26 : 0.09) + ")", topFillColor2: "rgba(" + col + "," + (live ? 0.26 : 0.09) + ")",
        bottomLineColor: "rgba(0,0,0,0)", bottomFillColor1: "rgba(0,0,0,0)", bottomFillColor2: "rgba(0,0,0,0)", lineWidth: 1,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      zs.setData([{ time: a, value: z.hi }, { time: b, value: z.hi }]);
    }
    const marks = c.big_days.filter(b => b.ts >= first).map(b => ({ time: b.ts, position: b.kind === "buy" ? "belowBar" : "aboveBar", shape: b.kind === "buy" ? "arrowUp" : "arrowDown",
      color: b.kind === "buy" ? css("--up") : css("--down"), text: b.ratio + "×" }));
    for (const u of c.unlocks || []) if (u.ts >= first && u.ts <= last) marks.push({ time: u.ts, position: "aboveBar", shape: "square", color: "#ff7f0e",
      text: "unlock " + (u.amount_m >= 1000 ? (u.amount_m / 1000).toFixed(1) + "B" : Math.round(u.amount_m) + "M") });
    s.setMarkers(marks.sort((x, y) => x.time - y.time));
    syncAdd(ch, s, bars.map(b => ({ time: b[0], value: b[4] })));
  });
  return host;
}

function zoneReadLine(c) {
  const n = c.now || {}, parts = [px(c.price) + " · " + c.live + " live zone" + (c.live === 1 ? "" : "s")];
  if (n.inside) parts.push("inside a " + (n.inside.kind === "buy" ? "support" : "resistance") + " zone " + px(n.inside.lo) + "–" + px(n.inside.hi) + " from " + n.inside.born + " (" + n.inside.ratio + "× volume)");
  if (n.support) parts.push("nearest support " + px(n.support.lo) + "–" + px(n.support.hi) + ", " + pctAbs1(n.support.below_pct) + " below (" + n.support.born + ")");
  if (n.resistance) parts.push("nearest resistance " + px(n.resistance.lo) + "–" + px(n.resistance.hi) + ", " + pctAbs1(n.resistance.above_pct) + " above (" + n.resistance.born + ")");
  const nu = (c.unlocks || []).find(u => u.ts > c.bars[c.bars.length - 1][0]);
  if (nu) parts.push("next unlock " + nu.date + ": " + Math.round(nu.amount_m) + "M" + (nu.pct_of_circulating != null ? " (+" + nu.pct_of_circulating + "% of circulating)" : ""));
  return parts.join(" · ");
}

function zoneStatsCard(c) {
  const S = c.stats || {}, f = v => v == null ? "–" : pct(v, 1), up = v => v == null ? "" : " (" + Math.round(v * 100) + "% up)";
  const rows = [["After a big BUY day (" + S.buy_days + ")", f(S.buy_7d) + up(S.buy_7d_up), f(S.buy_30d) + up(S.buy_30d_up)],
    ["After a big SELL day (" + S.sell_days + ")", f(S.sell_7d) + up(S.sell_7d_up), f(S.sell_30d) + up(S.sell_30d_up)],
    ["Any day", f(S.every_7d), f(S.every_30d)],
    ["After the first retest of support (" + S.buy_retests + ")", f(S.buy_retest_7d) + up(S.buy_retest_7d_up), "–"],
    ["After the first retest of resistance (" + S.sell_retests + ")", f(S.sell_retest_7d) + up(S.sell_retest_7d_up), "–"]];
  return card(c.ticker + " after its own big days and retests, " + c.history_days + " days of history since " + c.since,
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["", "7 days later", "30 days later"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))),
      ...rows.map(r => el("tr", {}, el("td", {}, r[0]), ...r.slice(1).map(v => el("td", { style: "text-align:right", class: v.startsWith("+") ? "up" : v.startsWith("−") ? "down" : "" }, v)))))),
    note("Average close-to-close move after the event against the coin's average day. A few dozen events on one coin: a hint, not a statistic. The bot's full study across its whole basket is docs/Alt_Volume_Zones_Study.xlsx in the trading repo."));
}

function volumeTable(coins) {
  const H = ["Coin", "Price", "Where it sits", "Live zones", "Nearest support", "Nearest resistance", "Big days, 30d", "After buy days, 7d", "After sell days, 7d"];
  const lc = { 1: "up", "-1": "down", 0: "" };
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...coins.map(c => c.status !== "ok" ? el("tr", {}, el("td", {}, el("b", {}, c.ticker)), el("td", { colspan: H.length - 1, class: "muted" }, c.status === "error" ? "Not available right now (" + c.why + ")." : c.status + ".")) :
      el("tr", { class: "tap", style: "cursor:pointer", onclick: () => { VZ_COIN = c.ticker; try { sessionStorage.setItem("vz:coin", c.ticker); } catch (e) {} location.hash = "volume"; render(); } },
        el("td", {}, el("b", {}, c.ticker), " ", el("span", { class: "muted" }, c.group === "Memecoin" ? "meme" : "candidate")),
        el("td", { style: "text-align:right" }, px(c.price)), el("td", { style: "text-align:right", class: lc[c.lean] || "" }, c.read),
        el("td", { style: "text-align:right" }, c.live),
        el("td", { style: "text-align:right" }, c.now.support ? px(c.now.support.hi) + " (" + pctAbs1(c.now.support.below_pct) + " below)" : "–"),
        el("td", { style: "text-align:right" }, c.now.resistance ? px(c.now.resistance.lo) + " (" + pctAbs1(c.now.resistance.above_pct) + " above)" : "–"),
        el("td", { style: "text-align:right" }, c.big_days_30d),
        el("td", { style: "text-align:right", class: cls(c.stats.buy_7d) }, pct(c.stats.buy_7d, 1)), el("td", { style: "text-align:right", class: cls(c.stats.sell_7d) }, pct(c.stats.sell_7d, 1))))));
}

// ------------------------------------------------------------------ ENA unlocks
const mTok = v => v == null ? "–" : v >= 1000 ? (v / 1000).toFixed(2) + "B" : Math.round(v) + "M";
const pctOrDash = (v, d = 1) => v == null ? "–" : pct(v, d);
const CONF_CLS = { high: "up", medium: "", low: "down" };

function unlockChart(u) {
  const host = el("div", { class: "chart", style: "height:360px" });
  const bars = u.price || [];
  if (!bars.length) return host;
  setTimeout(() => {
    const ch = newChart(host, { rightPriceScale: { borderVisible: false, mode: 1 } });
    const s = ch.addLineSeries({ color: css("--s1"), lineWidth: 2, priceLineVisible: false, lastValueVisible: false, priceFormat: { type: "custom", formatter: px, minMove: 0.0001 } });
    const pts = bars.map(b => ({ time: b[0], value: b[4] }));
    s.setData(pts);
    const first = bars[0][0], last = bars[bars.length - 1][0];
    s.setMarkers((u.events || []).filter(e => e.ts >= first && e.ts <= last).map(e => {
      const big = (e.pct_of_circulating || 0) >= 5, mid = (e.pct_of_circulating || 0) >= 1;
      return { time: e.ts, position: "aboveBar", shape: big ? "arrowDown" : "square", color: big ? css("--down") : mid ? "#ff7f0e" : css("--muted"), size: big ? 2 : mid ? 1 : 0.6, text: big || mid ? mTok(e.amount_m) : "" };
    }));
    syncAdd(ch, s, pts);
  });
  return host;
}

function unlockScheduleTable(rows, now) {
  const H = ["Date", "Amount", "% of supply", "% of circulating", "Who", "Kind", "Tranches"];
  return el("div", { class: "scroll", style: "max-height:420px;overflow:auto" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 0 && i < 4 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(e => el("tr", { style: e.ts >= now ? "" : "opacity:.75" }, el("td", { style: "white-space:nowrap" }, e.date, e.ts >= now ? el("span", { class: "pill", style: "margin-left:6px" }, "ahead") : null),
      el("td", { style: "text-align:right" }, mTok(e.amount_m)), el("td", { style: "text-align:right" }, e.pct_supply + "%"),
      el("td", { style: "text-align:right", class: (e.pct_of_circulating || 0) >= 5 ? "down" : "" }, e.pct_of_circulating == null ? "–" : "+" + e.pct_of_circulating + "%"),
      el("td", {}, e.who), el("td", { class: "muted" }, e.kinds), el("td", { style: "text-align:right" }, e.n_tranches == null ? "" : e.n_tranches)))));
}

function unlockAverages(rows) {
  const H = ["Group", "Unlocks", "Week before", "Into the day", "1 day after", "3 days after", "7 days after", "14 days after", "Weeks before that fell"];
  const cell = v => el("td", { style: "text-align:right", class: cls(v) }, pctOrDash(v));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(r => el("tr", { style: r.group === "every day" ? "font-style:italic" : "" }, el("td", {}, r.group), el("td", { style: "text-align:right" }, r.events),
      cell(r.run_up_7d), cell(r.into_day), cell(r.after_1d), cell(r.after_3d), cell(r.after_7d), cell(r.after_14d),
      el("td", { style: "text-align:right" }, r.run_up_7d_down == null ? "–" : Math.round(r.run_up_7d_down * 100) + "%")))));
}

function unlockRules(rows) {
  const H = ["Rule", "Unlocks used", "Trades", "Total", "Per trade", "Win rate", "Worst trade", "Before Jul 2025", "Jul 2025 on", "Placebo p"];
  const cell = (v, d = 1) => el("td", { style: "text-align:right", class: cls(v) }, pctOrDash(v, d));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(r => el("tr", {}, el("td", {}, r.rule), el("td", {}, r.unlocks), el("td", { style: "text-align:right" }, r.trades),
      cell(r.total, 0), cell(r.avg, 2), el("td", { style: "text-align:right" }, r.win_rate == null ? "–" : Math.round(r.win_rate * 100) + "%"), cell(r.worst, 1),
      cell(r.in_sample, 0), cell(r.out_of_sample, 0),
      el("td", { style: "text-align:right", class: r.placebo_p != null && r.placebo_p <= 0.05 ? "up" : "" }, r.placebo_p == null ? "–" : r.placebo_p.toFixed(2))))));
}

function unlockEvents(rows) {
  const H = ["Date", "Amount", "% of circulating", "Who", "Week before", "Into day", "7 days after", "14 days after", "Volume ×", "Busiest day ±4"];
  const cell = v => el("td", { style: "text-align:right", class: cls(v) }, pctOrDash(v));
  return el("div", { class: "scroll", style: "max-height:420px;overflow:auto" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 0 && i !== 3 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.slice().reverse().map(e => el("tr", {}, el("td", { style: "white-space:nowrap" }, e.date), el("td", { style: "text-align:right" }, mTok(e.amount_m)),
      el("td", { style: "text-align:right" }, e.pct_of_circulating == null ? "–" : "+" + e.pct_of_circulating + "%"), el("td", { class: "muted" }, e.who),
      cell(e.run_up_7d), cell(e.into_day), cell(e.after_7d), cell(e.after_14d), el("td", { style: "text-align:right" }, e.vol_ratio == null ? "–" : e.vol_ratio.toFixed(1)),
      el("td", { style: "text-align:right", class: e.max_vol_day_offset === 0 ? "up" : Math.abs(e.max_vol_day_offset) >= 2 ? "down" : "" }, e.max_vol_day_offset === 0 ? "same day" : (e.max_vol_day_offset > 0 ? "+" : "") + e.max_vol_day_offset + "d")))));
}

function unlockMiniCard(f) {
  const U = f.unlocks;
  if (!U) return null;
  const nx = U.coming[0];
  return card("Token unlocks", el("div", { class: "kpis" },
      kpi("Next unlock", nx ? nx.date : "–"), kpi("Amount", nx ? mTok(nx.amount_m) + " " + f.ticker : "–"), kpi("Added to circulating", nx && nx.pct_of_circulating != null ? "+" + nx.pct_of_circulating + "%" : "–", nx && nx.pct_of_circulating >= 1 ? "down" : ""),
      kpi("Unlocks in the last 90 days", String(U.recent.length))),
    el("div", { class: "muted" }, nx ? "To " + nx.who + " (" + nx.kinds + "). " : "", el("a", { href: U.tab }, "Full schedule and what the price did around every unlock")));
}

const VIEWS_EXTRA = {
  async volume() {
    const d = await api("volume");
    const ok = (d.coins || []).filter(c => c.status === "ok");
    if (!ok.length) return [card(null, el("div", { class: "muted" }, "Candles are loading in the background, back in a few minutes."), stale(d))];
    if (!VZ_COIN || !ok.some(c => c.ticker === VZ_COIN)) VZ_COIN = ok[0].ticker;
    const c = ok.find(x => x.ticker === VZ_COIN);
    const C = d.counts || {};
    const head = card(null, el("div", { class: "kpis" },
      kpi("Coins with candles", C.coins + " of " + (d.coins || []).length), kpi("Inside or just over support", String(C["inside support"] || 0), C["inside support"] ? "up" : ""),
      kpi("Inside or just under resistance", String(C["under resistance"] || 0), C["under resistance"] ? "down" : ""),
      kpi("Big day = volume ≥", d.settings.mult + "× the " + d.settings.lookback + "-day median")),
      note("A big-volume day with an up close leaves a support zone (its open-to-close range); with a down close, a resistance zone. Mechanical and recomputed every 6 hours; research, not advice."));
    const pick = el("div", { class: "seg", style: "flex-wrap:wrap;margin-bottom:6px" }, ...ok.map(x => el("button", { class: x.ticker === VZ_COIN ? "on" : "", onclick: () => { VZ_COIN = x.ticker; try { sessionStorage.setItem("vz:coin", x.ticker); } catch (e) {} render(); } }, x.ticker)));
    const rng = el("div", { class: "seg", style: "margin-bottom:6px" }, ...[[180, "6 months"], [365, "1 year"], [400, "Whole window"]].map(([v, l]) => el("button", { class: v === VZ_DAYS ? "on" : "", onclick: () => { VZ_DAYS = v; render(); } }, l)));
    const chart = card(c.ticker + ": daily candles, big-volume days and the zones they left (" + c.market + " on Hyperliquid)", pick, rng, zoneChart(c, VZ_DAYS),
      el("div", { class: "muted", style: "margin-top:6px" }, zoneReadLine(c)),
      note("▲ / ▼ = a day with " + d.settings.mult + "× or more the usual volume (label = how many times); up close = buy day, down close = sell day. Green band = support left by a buy day, red = resistance left by a sell day, from the day's open to its close; " +
        "a band ends when a close goes " + d.settings.break_atr + " ATR through it or after " + d.settings.max_age + " days (faded = ended). Orange squares = token unlocks (ENA). Volume is Hyperliquid's perp volume in dollars."));
    return [head, chart, zoneStatsCard(c), card("Every coin against its zones", volumeTable(d.coins || []), note("Click a row to chart it. 'Where it sits' reads +/− 3% from the nearest zone.")), stale(d)];
  },
  async unlocks() {
    const u = await api("unlocks");
    const now = Math.floor(Date.now() / 1000), nx = u.next, nb = u.next_big;
    const head = card(null, el("div", { class: "kpis" },
        kpi("Next unlock", nx ? nx.date + " (" + nx.days + " days)" : "–"), kpi("Amount", nx ? mTok(nx.amount_m) : "–"),
        kpi("Next of 1%+ of circulating", nb ? nb.date + " · " + mTok(nb.amount_m) + " (+" + nb.pct_of_circulating + "%)" : "none scheduled", nb && nb.days <= 7 ? "down" : ""),
        kpi("Unlocked so far", u.unlocked_m != null ? mTok(u.unlocked_m) + " of " + mTok(u.total_m) : "–"),
        kpi("Unlocks in the price history", u.events_in_history != null ? u.events_in_history + " since " + u.history_since : "–")),
      note("ENA: 15B max supply; core contributors 30%, investors 25%, Foundation 15%, ecosystem 30%. Listed 2 Apr 2024 with 9.5% circulating; 1-year cliff of 25% on 5 Mar 2025, then monthly tranches; all remaining investor tokens were released at once on 5 Oct 2026 (size not published, ~1.4B before OTC buy-outs). " +
        "Schedule hand-entered from Ethena's docs, Binance, Tokenomist and news (data/altcoins/unlocks/ENA.csv); trackers disagree on the 2nd vs the 5th for the 2025-26 tranches, so the 'busiest day' column checks each date against volume."));
    const out = [head];
    if (u.price) out.push(card("ENA price (log) with every unlock: red arrows = 5%+ of circulating, orange = 1-5%, grey = under 1% (Foundation)", unlockChart(u),
      note("Hyperliquid daily closes. Markers sit on the unlock day; the labels give the amount in tokens.")));
    if (u.averages && u.averages.length) out.push(card("What ENA did around its unlocks, on average", unlockAverages(u.averages),
      note("Close-to-close moves. 'Week before' = close 8 days before to the day before; 'Into the day' = the day before to the unlock day's close. The italic 'every day' row is ENA's average move over the same windows on any day: the difference is the unlock effect, if any. " +
        u.events_in_history + " events, " + (u.averages.find(r => r.group === "big (>= 5% of circulating)") || {}).events + " of them big: a hint, not a statistic.")));
    if (u.rules && u.rules.length) out.push(card("Would the dates have been tradable? Simple rules at daily closes, perp costs included", unlockRules(u.rules),
      note("Enter and exit at the close; 0.045% fee + 0.05% slippage each side, funding not included. Before / after Jul 2025 = the two halves the trading bot's studies judge on. Placebo p = share of 300 random date sets of the same size that did as well (green at 0.05 or less). " +
        "Ten settings on about " + Math.max(0, ...(u.rules || []).map(r => r.trades)) + " events: one or two will look good by luck; a rule needs both halves positive AND a low p before it means anything.")));
    if (u.event_table && u.event_table.length) out.push(card("Every unlock in the price history", unlockEvents(u.event_table),
      note("'Busiest day ±4' = the highest-volume day within four days of the listed date: 'same day' (green) supports the date, ±2 days or more (red) means the tracker's day may be wrong.")));
    out.push(card("The full schedule, past and ahead (" + (u.events || []).length + " unlock days to " + ((u.events || []).slice(-1)[0] || {}).date + ")", unlockScheduleTable(u.events || [], now),
      note("Same-day tranches are summed; '% of circulating' = the day's amount against everything unlocked before it. Not counted: the StablecoinX lock-up waiver (3.03B, transfers still need the Foundation's consent), the season-3 airdrop (amount unpublished) and a 275M item some trackers show for 1 Nov 2026. Rows and sources in data/altcoins/unlocks/ENA.csv.")));
    if (u.study_error) out.push(note("The price study is not available right now (" + u.study_error + "); the schedule above is from the committed file."));
    out.push(stale(u));
    return out;
  },
};
const DATA = {};                     // one download per coin tab; a failure is retried on the next visit
const coinData = t => DATA[t] || (DATA[t] = api(t).catch(e => { delete DATA[t]; throw e; }));

async function coinView(t) {
  const f = await coinData(t);
  if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now: prices are loading in the background."), stale(f))];
  const S = f.series;
  return [header(f), card(null, strip(f)), zoneCard(f), unlockMiniCard(f), notesCard(f),
    card(f.ticker + " and BTC rebased to the same start (log)", ...linesChart([{ name: f.ticker, points: S.price }, { name: "BTC, rebased", points: S.btc_indexed, dashed: true, color: css("--hold") }], px, { log: true })),
    el("div", { class: "grid2" },
      card(f.ticker + " ÷ BTC (log): rising = beating BTC", ...linesChart([{ name: f.ticker + "/BTC", points: S.ratio }], v => v == null ? "–" : v.toPrecision(3), { log: true, small: true })),
      card("RSI 14: against BTC (solid) and in USD (dashed)", ...linesChart([{ name: "RSI vs BTC", points: S.rsi_vs_btc }, { name: "RSI (USD)", points: S.rsi, dashed: true }], r1, { small: true, hlines: [30, 50, 70] }),
        note("Above 70: has run hard. Below 30: washed out.")),
      card("Market cap", ...linesChart([{ name: "Market cap", points: S.market_cap }], usdBig, { small: true }))),
    section("Fundamentals"), ...fundamentalsCard(f), section("Projection to end-2028"), ...projectionCards(f)];
}

const VIEWS = {
  async zones() {
    const d = await api("zones");
    const C = d.counts || {};
    return [card(null, el("div", { class: "kpis" },
        kpi("In their buy zone", (C["in zone"] || 0) + " of " + (d.coins || []).length, C["in zone"] ? "up" : ""), kpi("Above their zone", String(C["above zone"] || 0)),
        kpi("No zone this year", String(C["no zone"] || 0), C["no zone"] ? "down" : "")),
        note("Click a coin for its full tab. Research, not investment advice.")),
      card("Buy zone for each coin", zonesTable(d.coins || []),
        note("Zone top: the coin's 200-day average price; for HYPE, ENA, SOL and NEAR, half the base-case price at end-2028 when that is lower, so the base case " +
          "at least doubles from the top of the zone. Floor: the lowest close of the last 365 days; mid: half-way, for staged entries. Memecoins have no " +
          "projection, so their top is the 200-day average alone. 'No zone' = the base case does not double from any price of the last year. Recomputed daily from the same prices as the other tabs.")),
      stale(d)];
  },
  async hype() { return coinView("hype"); },
  async ena() { return coinView("ena"); },
  async sol() { return coinView("sol"); },
  async near() { return coinView("near"); },
  async basket() {
    const d = await api("basket");
    const live = (d.coins || []).filter(c => c.kpi);
    const best = live.slice().sort((a, b) => (b.kpi.vs_btc_90d ?? -9) - (a.kpi.vs_btc_90d ?? -9))[0];
    const head = card(null, el("div", { class: "kpis" },
      kpi("Basket market cap", usdBig(d.basket_mcap)), kpi("Coins in the basket", live.length + " of " + (d.coins || []).length),
      kpi("Beating BTC over 90 days", live.filter(c => (c.kpi.vs_btc_90d || 0) > 0).length + " of " + live.length),
      best ? kpi("Strongest vs BTC, 90 days", best.ticker + " " + pct(best.kpi.vs_btc_90d, 0), cls(best.kpi.vs_btc_90d)) : null,
      kpi("As of", d.as_of || "–")));
    const rebased = card("Each coin and BTC, rebased to 100 a year ago (log)",
      ...linesChart([...live.map(c => ({ name: c.ticker, points: c.rebased })), { name: "BTC", points: d.btc_rebased, dashed: true, color: css("--hold"), width: 2 }],
        v => v == null ? "–" : num(v, 0), { log: true }),
      note("Above BTC's dashed line: beat holding Bitcoin over the period shown. Click a name in the legend to hide it."));
    return [head, card("The basket", basketTable(d.coins || []),
        note("Click a column to sort. RSI above 70 (red) = has run hard; below 30 (green) = washed out. Beta: how much the coin moves for each 1% BTC move (clamped 0.5-3).")),
      rebased, el("div", { class: "grid2" }, ...live.map(sparkCard)), stale(d)];
  },
  async season() {
    const d = await api("season");
    const K = d.kpi;
    if (!K) return [card(null, el("div", { class: "muted" }, "Prices are loading in the background, back in a few minutes."), stale(d))];
    const rules = d.rules || {};
    const head = card(null, el("div", { style: "font-size:20px;font-weight:650;margin-bottom:6px" }, "Reading: ", el("span", { class: STATE[K.state] || "" }, K.state)),
      el("div", { class: "kpis" },
        kpi("Basket vs BTC, 90 days", pct(K.vs_btc_90d, 0), cls(K.vs_btc_90d)), kpi("Basket vs BTC, 30 days", pct(K.vs_btc_30d, 0), cls(K.vs_btc_30d)),
        kpi("RSI of basket ÷ BTC", r1(K.rsi_vs_btc), rsiCls(K.rsi_vs_btc)), kpi("Basket ÷ BTC from its 1-year high", pct(K.from_high, 0), cls(K.from_high)),
        kpi("Basket market cap", usdBig(K.basket_mcap)), kpi("Basket market cap, 1 year", pct(K.basket_1y, 0), cls(K.basket_1y))),
      note("Meme season: the basket has beaten BTC by " + Math.round((rules.hot || 0.25) * 100) + "%+ over 90 days, or its RSI against BTC is 70+. Out of season: it trails by " +
        Math.round(-(rules.cold || -0.25) * 100) + "%+ and the RSI is under 50. In between otherwise. Mechanical, not a forecast." +
        (d.coins_missing && d.coins_missing.length ? " Not in today's figures (loading): " + d.coins_missing.join(", ") + "." : "")));
    const ratio = card("Basket market cap ÷ BTC market cap (log): rising = memes beating BTC",
      ...linesChart([{ name: "Basket ÷ BTC", points: d.ratio }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { log: true }));
    const rsi = card("RSI 14 of basket ÷ BTC", ...linesChart([{ name: "RSI vs BTC", points: d.rsi_vs_btc }], r1, { small: true, hlines: [30, 50, 70] }));
    const ew = card("Equal-weight basket and BTC, rebased to 100 (log)",
      ...linesChart([{ name: "Memecoins, equal weight", points: d.equal_weight }, { name: "BTC", points: d.btc_rebased, dashed: true, color: css("--hold") }], v => v == null ? "–" : num(v, 0), { log: true, small: true }));
    const caps = card("Market caps: basket (left) and BTC (right)",
      ...linesChart([{ name: "Basket", points: d.basket_mcap, axis: "left" }, { name: "BTC", points: d.btc_mcap, color: css("--hold") }], usdBig, { small: true }));
    const log = d.share_log || [];
    const share = card("Memecoins' share of the whole crypto market (CoinGecko 'Meme' category ÷ total market cap)",
      ...(log.length > 1 ? linesChart([{ name: "Meme share", points: log.map(r => [r.t, r.share]) }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { small: true, sync: false })
        : [el("div", { class: "kpis" }, kpi("Meme share today", log.length ? (log[0].share * 100).toFixed(2) + "%" : "–"), kpi("Meme sector market cap", log.length ? usdBig(log[0].meme_mcap) : "–"))]),
      note("CoinGecko has no free history of either figure, so this is logged once a day from the first deploy and grows from there."));
    return [head, ratio, el("div", { class: "grid2" }, rsi, ew, caps), share, stale(d)];
  },
};
Object.assign(VIEWS, VIEWS_EXTRA);
window.TOPIC = { VIEWS };
})();
