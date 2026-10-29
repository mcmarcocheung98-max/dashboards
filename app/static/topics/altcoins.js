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
const DATA = {};                     // one download per coin tab; a failure is retried on the next visit
const coinData = t => DATA[t] || (DATA[t] = api(t).catch(e => { delete DATA[t]; throw e; }));

async function coinView(t) {
  const f = await coinData(t);
  if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now: prices are loading in the background."), stale(f))];
  const S = f.series;
  return [header(f), card(null, strip(f)), zoneCard(f), notesCard(f),
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
window.TOPIC = { VIEWS };
})();
