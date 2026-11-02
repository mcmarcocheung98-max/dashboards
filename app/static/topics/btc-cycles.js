// BTC Cycles: tabs and cards. Data from /api/btc-cycles/<cycles|etf|mstr|signals>. The doc's tables are rendered from
// data/btc-cycles/research.json; the live series sit beside its claims. The altcoin half (sectors, candidates, coin pages) is
// Altcoin Study (/altcoins, altcoins.js), which reads this dashboard's sector and candidate endpoints.
(() => {
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
const table = (cols, rows, opts = {}) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map(h => el("th", { style: "text-align:left;vertical-align:bottom" }, h))),
  ...rows.map(r => el("tr", {}, ...cols.map((c, i) => { const v = Array.isArray(r) ? r[i] : r[c]; return el("td", { class: i === 0 ? "" : "wrap" }, ...md(String(v ?? ""))); })))));
const docLink = r => el("div", { class: "src", style: "margin-top:6px" }, "From the research doc, as of " + r.as_of + ": ", link("open it", r.doc_url), ".");
const pill = state => el("span", { class: "pill " + ({ firing: "ok", "not yet": "", watch: "", "no data": "bad" }[state] || "") }, state);

// Every chart opens on the last year unless the reader already picked a range on this page (the range bar's own memory).
try { if (!sessionStorage.getItem("range:" + location.pathname)) RANGE = "1y"; } catch (e) { RANGE = "1y"; }

// the value of a [[t, v], ...] series on date t: the last point at or before it
const asof = (pts, t) => {
  if (!pts || !pts.length || t < pts[0][0]) return null;
  let lo = 0, hi = pts.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid - 1; }
  return pts[lo][1];
};
const dateOf = t => new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
// The top cards that follow the charts use the shared datedHead / followHead (topic.html).
// A card whose body folds away: click the title. Each reader's choice is remembered in this browser (when storage allows).
function fold(title, open, ...kids) {
  const key = "fold:" + location.pathname + ":" + title.slice(0, 60);
  try { const v = localStorage.getItem(key); if (v != null) open = v === "1"; } catch (e) {}
  const body = el("div", { style: open ? "" : "display:none" }, ...kids.filter(Boolean));
  const mark = el("span", { class: "muted", style: "display:inline-block;width:16px" }, open ? "▾" : "▸");
  const h = el("h2", { style: "cursor:pointer;user-select:none", title: "Click to fold or unfold", onclick: () => {
    open = !open; body.style.display = open ? "" : "none"; mark.textContent = open ? "▾" : "▸";
    try { localStorage.setItem(key, open ? "1" : "0"); } catch (e) {}
    if (open) requestAnimationFrame(() => { try { applyAll(); } catch (e) {} });     // charts drawn while folded had no width: re-apply the date range
  } }, mark, title);
  return el("div", { class: "card" }, h, body);
}

// ---------- BTC buy and sell zones: the published price-only models, their lines on the price chart, and what they read at each top and low
function zonesCard(Z) {
  if (!Z || !Z.models) return null;
  const zoneCls = z => z === "buy" ? "up" : z === "sell" ? "down" : "";
  const zoneTxt = z => z === "buy" ? "buy zone" : z === "sell" ? "sell zone" : z ? "neither" : "–";
  const fmt = (m, v) => v == null ? "–" : m.key === "rsi_w" ? v.toFixed(0) : v.toFixed(2) + "×";
  const scored = Z.models.filter(m => m.buy || m.sell);
  const verdict = Z.n_buy && !Z.n_sell ? Z.n_buy + " of " + Z.n_models + " in the buy zone" : Z.n_sell ? Z.n_sell + " of " + Z.n_models + " in the sell zone" : "No model in a buy or sell zone";
  const kp = el("div", { class: "kpis" }, kpi("Price models", verdict, Z.n_buy && !Z.n_sell ? "up" : Z.n_sell ? "down" : ""),
    ...scored.map(m => kpi(m.name + (m.zone === "neither" || !m.zone ? "" : " · " + zoneTxt(m.zone)), fmt(m, m.now), zoneCls(m.zone))),
    kpi("Trend (bull-market support band)", Z.trend === "above" ? "above the band" : "below the band", Z.trend === "above" ? "up" : "down"));
  const L = Z.lines || {};
  const chart = linesChart([{ name: "BTC", points: L.price || [], color: css("--s1") }].filter(x => x.points.length).concat([
    { name: "200-week MA (floor)", points: L.ma200w, color: css("--hold"), width: 2.5 },
    { name: "2-year MA (buy below)", points: L.ma2y, color: css("--up"), dashed: true },
    { name: "0.8 × 200-day MA (Mayer buy)", points: L.mayer_buy, color: css("--z5"), dashed: true },
    { name: "2.4 × 200-day MA (Mayer sell)", points: L.mayer_sell, color: css("--down"), dashed: true },
    { name: "5 × 2-year MA (sell above)", points: L.ma2y_x5, color: css("--z1"), width: 1 }].filter(x => x.points && x.points.length)), v => usd(v), { log: true });
  const marks = Z.markers || [];
  const head = ["Model", "Formula", "Buy", "Sell", "Now", "Zone", ...marks.map(m => m.label.replace("~", "") + " (" + m.date.slice(0, 7) + ")")];
  const align = ["left", "left", "right", "right", "right", "left", ...marks.map(() => "right")];
  const rows = Z.models.map(m => el("tr", {}, el("td", {}, el("b", {}, m.name)), el("td", { class: "wrap", style: "min-width:220px" }, m.formula),
    el("td", { style: "text-align:right", class: "up" }, m.buy || "–"), el("td", { style: "text-align:right", class: "down" }, m.sell || "–"),
    el("td", { style: "text-align:right" }, el("b", {}, fmt(m, m.now))), el("td", { style: "text-align:left" }, m.buy || m.sell ? el("span", { class: "pill " + (m.zone === "buy" ? "ok" : m.zone === "sell" ? "bad" : "") }, zoneTxt(m.zone)) : el("span", { class: "muted" }, "trend")),
    ...marks.map(mk => el("td", { style: "text-align:right" }, fmt(m, m.at[mk.date])))));
  return card("BTC buy and sell zones: the published price models on today's data", kp,
    ...(L.ma200w ? [el("div", { style: "margin-top:8px" }, ...chart)] : []),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...head.map((h, i) => el("th", { style: "text-align:" + align[i] + ";vertical-align:bottom" }, h))), ...rows)),
    note("Lines as their authors and the data firms draw them: Mayer multiple (Trace Mayer; Glassnode's 0.8 and 2.4 bands), 2-year MA multiplier and 200-week MA (Philip Swift, LookIntoBitcoin), " +
      "Pi Cycle top and bottom, weekly RSI, bull-market support band. Price only, from the Coin Metrics series above, so no on-chain data is needed. " +
      "The last columns show each model at the doc's recent cycle peaks and lows: the fixed sell lines were set on 2013-21 and none fired at the Oct 2025 top (peaks shrink each cycle), " +
      "while the buy lines did fire at the Jun 2026 low. Mechanical readings, not a view."));
}

// mNAV strategies and the exit window: today's checklist, the rule backtests (recomputed from the live data), and how people value MSTR
function strategiesCards(S) {
  if (!S) return [];
  const M = S.measures || {}, x = v => v == null ? "–" : v.toFixed(2) + "×";
  const tone = { exit: "bad", caution: "bad", watch: "", clear: "ok" };
  const label = { exit: "exit signal", caution: "caution", watch: "in window", clear: "clear" };
  const rows = (S.checklist || []).map(c => el("tr", {}, el("td", {}, el("b", {}, c.rule)), el("td", { class: "wrap" }, c.test), el("td", { class: "wrap" }, c.now),
    el("td", { style: "text-align:left" }, el("span", { class: "pill " + (tone[c.state] || "") }, label[c.state] || c.state)), el("td", { class: "wrap muted" }, c.why)));
  const exits = (S.checklist || []).filter(c => c.state === "exit").length, cautions = (S.checklist || []).filter(c => c.state === "caution").length;
  const verdict = exits ? exits + " exit signal" + (exits > 1 ? "s" : "") + " on" : cautions ? "No exit signal; " + cautions + " caution flag" + (cautions > 1 ? "s" : "") : "No exit signal";
  const check = card("Exit window for MSTR: the checklist on today's data",
    el("div", { class: "kpis" }, kpi("mNAV, basic", x(M.basic)), kpi("mNAV, diluted", x(M.diluted)), kpi("mNAV, enterprise value", x(M.ev)),
      kpi("Checklist", verdict, exits ? "down" : cautions ? "" : "up")),
    note("Enterprise value = diluted market cap + debt + preferreds − cash" + (M.ev_inputs_date ? " (balance sheet as of " + M.ev_inputs_date + ")" : "") +
      ". Strategy's own figure since 23 Jul 2026 is price ÷ net bitcoin per share, which runs higher; the levels below are basic mNAV, the series with history."),
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Rule", "Test", "Now", "Status", "Why it matters"].map(h => el("th", { style: "text-align:left;vertical-align:bottom" }, h))), ...rows)));
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
  const research = R.sections ? fold("How people value MSTR and its bitcoin", false,
    ...R.sections.flatMap(s => [el("h3", { style: "margin:10px 0 4px;font-size:14px" }, s.title), el("ul", { style: "margin:0;padding-left:18px" }, ...s.points.map(p => el("li", { class: "muted", style: "margin:3px 0" }, ...md(p))))]),
    note(R.about || "")) : null;
  return [check, curves, research];
}

const VIEWS = {
  async cycles() {
    const d = await api("cycles"), R = d.research, n = d.now;
    const peak = n && n.price / (1 + n.vs_peak), low = n && n.price / (1 + n.vs_low), H = d.halvings || [], nextH = d.next_halving ? Date.parse(d.next_halving + "T00:00:00Z") / 1000 : null;
    const at = (t, latest, f) => t == null ? latest : f(t);
    const since = t => { const h = H.filter(x => x <= t).pop(); return h == null ? null : Math.floor((t - h) / 86400); };
    const head = card(null, n ? datedHead([
      { label: t => "BTC (" + (t == null ? n.date : dateOf(t)) + ")", value: t => [usd(at(t, n.price, t => asof(d.price, t)))] },
      { label: () => "vs Oct 2025 peak", value: t => { const v = at(t, n.vs_peak, t => asof(d.price, t) / peak - 1); return [pct(v, 0), cls(v)]; } },
      { label: () => "vs Jun 2026 low", value: t => { const v = at(t, n.vs_low, t => asof(d.price, t) / low - 1); return [pct(v, 0), cls(v)]; } },
      { label: () => "vs 200-day average", value: t => { const v = at(t, n.vs_ma200, t => { const m = asof(d.ma200, t); return m ? asof(d.price, t) / m - 1 : null; }); return [pct(v, 0), cls(v)]; } },
      { label: t => t == null ? "Days since the 2024 halving" : "Days since the last halving", value: t => [num(at(t, n.days_since_halving, since))] },
      { label: () => "Days to the next (~" + d.next_halving.slice(0, 7) + ")", value: t => [num(at(t, n.days_to_next_halving, t => nextH && t <= nextH ? Math.ceil((nextH - t) / 86400) : null))] },
    ], { latest: "Latest close" })
      : el("div", { class: "muted" }, "Live price not available right now (" + (d.price_error || "no data") + "); the research below still stands."),
      stale(d), docLink(R));
    const bottom = fold("Bottom line", true, ...R.bottom_line.map(p => para(p, "")));
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
    const anat = fold("BTC cycle anatomy, 2011–2026", true, para(R.anatomy.intro), table(R.anatomy.columns, R.anatomy.rows), para(R.anatomy.after));
    const zones = d.zones ? zonesCard({ ...d.zones, lines: { ...d.zones.lines, price: d.price } }) : null;
    return [head, bottom, priceCard, zones, ov, dd, anat];
  },
  async etf() {
    const d = await api("etf"), K = d.kpi || {};
    const m = v => v == null ? "–" : (v < 0 ? "−" : "") + "$" + big(Math.abs(v) * 1e6);
    const D = d.daily_usd_m || [], ibit = (d.cum_by_issuer || {}).IBIT;
    const dayAt = t => { let i = D.length - 1; while (i >= 0 && D[i][0] > t) i--; return i; };
    const streakAt = t => { let i = dayAt(t); if (i < 0) return null; const sg = Math.sign(D[i][1]); let k = 0; while (i >= 0 && Math.sign(D[i][1]) === sg && sg) { k++; i--; } return k * sg; };
    const pick = (t, latest, f) => t == null ? latest : f(t);
    const head = card(null, datedHead([
      { label: t => t == null ? "Net flows since launch" : "Net flows, launch to then", value: t => { const v = pick(t, K.since_launch_usd_m, t => asof(d.cum_usd_m, t)); return [m(v), cls(v)]; } },
      { label: () => "BTC taken in since launch", value: t => { const v = pick(t, K.since_launch_btc, t => asof(d.cum_btc, t)); return [v == null ? "–" : num(v) + " BTC"]; } },
      { label: () => "Last 30 days", value: t => { const v = pick(t, K.last_30d_usd_m, t => asof(d.roll30_usd_m, t)); return [m(v), cls(v)]; } },
      { label: t => { const i = t == null ? -1 : dayAt(t); return "Day's flow (" + (t == null ? K.last_day || "–" : i >= 0 ? dateOf(D[i][0]) : "–") + ")"; },
        value: t => { const v = pick(t, K.last_day_usd_m, t => asof(D, t)); return [m(v), cls(v)]; } },
      { label: () => "Streak", value: t => { const v = pick(t, K.streak, streakAt); return [v == null ? "–" : Math.abs(v) + (v >= 0 ? " days in" : " days out"), cls(v)]; } },
      { label: () => "BlackRock IBIT share of net flows", value: t => [pct(pick(t, K.ibit_share, t => { const a = asof(ibit, t), b = asof(d.cum_usd_m, t); return a != null && b ? a / b : null; }), 0)] },
    ], { latest: "Latest day" }),
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
    const tbl = d.table ? fold("By issuer", true, table(["Ticker", "Issuer", "Since launch", "Last 30 trading days", "Last day", "Best day", "Worst day"],
      d.table.map(r => [r.ticker, r.issuer, m(r.since_launch), m(r.last_30d), m(r.last_day), m(r.best_day), m(r.worst_day)])), note("US$; Farside's daily table, net of creations and redemptions.")) : null;
    const intl = Object.keys(d.intl || {}).length ? card("Hong Kong ETFs and UK ETNs: BTC held (hand-entered)", ...linesChart(Object.entries(d.intl).map(([k, pts]) => ({ name: k, points: pts })), v => num(v) + " BTC", { small: true }),
      table(["Date", "Market", "BTC", "Source"], d.intl_rows.map(r => [r.date, r.series, num(+r.value), "[" + host(r.source) + "](" + r.source + ")" + (r.note ? " · " + r.note : "")])),
      note("No free daily feed for these: add a row to data/btc-cycles/etf_holdings.csv from the issuers' holdings pages.")) : null;
    const ms = fold("Milestones", true, table(["Date", "Market", "What happened", "Source"], (d.milestones || []).map(r => [r.date, r.market, r.event, "[" + host(r.source) + "](" + r.source + ")"])));
    return [head, daily, cum, cumBtc, roll, issuers, tbl, intl, ms];
  },
  async mstr() {
    const d = await api("mstr"), K = d.kpi || {};
    const buyList = (d.purchases || []).slice().reverse(), day = s => Date.parse(s + "T00:00:00Z") / 1000;       // oldest first
    const cost0 = (K.approx_cost_usd || 0) - buyList.reduce((a, b) => a + (b.approx_usd || 0), 0);              // the holding before the first recorded buy
    const upto = t => buyList.filter(b => day(b.date) <= t);
    const pk = (t, latest, f) => t == null ? latest : f(t);
    const heldAt = t => pk(t, K.held, t => asof(d.held, t));
    const head = card(null, datedHead([
      { label: t => "BTC held" + (t == null ? "" : " on " + dateOf(t)), value: t => [num(heldAt(t))] },
      { label: () => "Share of 21m supply", value: t => { const h = heldAt(t); return [h == null ? "–" : (h / 21e6 * 100).toFixed(2) + "%"]; } },
      { label: () => "Value of the BTC", value: t => [usdBig(pk(t, K.value_usd, t => { const h = heldAt(t), b = asof(d.btc, t); return h && b ? h * b : null; }))] },
      { label: () => "Approx. average cost", value: t => [usd(pk(t, K.approx_avg_cost, t => { const h = heldAt(t); return h ? (cost0 + upto(t).reduce((a, b) => a + (b.approx_usd || 0), 0)) / h : null; }))] },
      { label: () => "mNAV", value: t => { const v = pk(t, K.mnav, t => asof(d.mnav, t)); return [v == null ? "–" : v.toFixed(2) + "×", v == null ? "" : v >= 1 ? "down" : "up"]; } },
      { label: () => "MSTR", value: t => [usd(pk(t, K.mstr, t => asof(d.mstr, t)), 2)] },
      { label: () => "90-day correlation with BTC", value: t => { const v = pk(t, K.corr90, t => asof(d.corr90, t)); return [v == null ? "–" : v.toFixed(2)]; } },
      { label: () => "90-day beta to BTC", value: t => { const v = pk(t, K.beta90, t => asof(d.beta90, t)); return [v == null ? "–" : v.toFixed(2)]; } },
      { label: () => "Purchases recorded", value: t => [num(pk(t, K.purchases, t => upto(t).length))] },
      { label: () => "Last purchase", value: t => { const u = t == null ? null : upto(t); return [t == null ? K.last_purchase || "–" : u.length ? u[u.length - 1].date : "–"]; } },
    ], { latest: "Latest (" + (d.as_of || "–") + ")" }),
      note(d.note || ""), note("Prices: " + (d.price_source || "–") + "."), asOf(d), stale(d));
    const held = card("BTC held", ...linesChart([{ name: "BTC held", points: d.held }], v => num(v), { small: true }));
    const px = card("MSTR vs BTC, both rebased to Aug 2020 (log)", ...linesChart([{ name: "MSTR", points: d.mstr_rebased }, { name: "BTC", points: d.btc_rebased, color: css("--hold"), dashed: true }], v => xf(v), { log: true }));
    const mn = card("MSTR vs the value of its bitcoin: premium (overvalued) and discount (undervalued)", ...premiumChart(d),
      note("mNAV = share market value ÷ value of its bitcoin (basic shares). Red above 1: the market pays a premium for each bitcoin, which lets Strategy issue shares to buy more; " +
        "green below 1: a discount, and that engine stalls (the doc: the treasury trade is over once the premium compresses). Where the blue line sits above the grey dashed line is the premium in dollars."));
    const cb = card("Correlation and beta of daily returns with BTC (rolling 90 trading days)", ...linesChart([{ name: "Correlation", points: d.corr90 }, { name: "Beta", points: d.beta90, axis: "left", dashed: true }], v => v == null ? "–" : v.toFixed(2), { small: true }));
    const bps = card("BTC per 1,000 MSTR shares", ...linesChart([{ name: "BTC per 1,000 shares", points: d.btc_per_1000_shares }], v => v == null ? "–" : v.toFixed(3), { small: true }),
      note("Rising = purchases added more bitcoin than new shares diluted; falling = dilution outran buying."));
    const buys = fold("Every recorded purchase (newest first, " + (d.purchases || []).length + ")", false, table(["Date", "BTC added", "Held after", "BTC price that day", "Approx. US$"],
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
    const rows = d.status.map((s, i) => el("tr", {}, el("td", { style: "text-align:left" }, i + 1), el("td", { class: "wrap" }, s.signal), el("td", { style: "text-align:left" }, pill(s.state)), el("td", { class: "wrap" }, s.reading), el("td", { class: "wrap" }, s.note)));
    const status = card("The six signals, read mechanically today (" + d.as_of + ")", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["#", "Signal", "Status", "Reading", "How"].map(h => el("th", { style: "text-align:left;vertical-align:bottom" }, h))), ...rows)),
      note("Firing = the doc's condition is met on today's data. These are rules applied to public data, not a recommendation."));
    const doc = fold("What the doc says to watch, in order", true, para(R.intro, ""), el("ol", { style: "margin:6px 0 0 18px;padding:0" }, ...R.items.map(s => el("li", { style: "margin:4px 0" }, ...md(s)))));
    const timing = fold("Timing on the halving clock", true, para(R.timing, ""));
    const breakers = fold("What could break the four-year pattern", true, para(R.breakers, ""));
    const charts = [];
    if (d.volume && d.volume.length) charts.push(card("BTC spot volume, 30-day average (CoinGecko)", ...linesChart([{ name: "Volume", points: d.volume }, { name: "$10bn threshold", points: d.volume.map(p => [p[0], 10e9]), dashed: true, color: css("--hold") }], v => usdBig(v), { small: true })));
    if (d.dominance_log && d.dominance_log.length > 1) charts.push(card("BTC dominance, logged daily since deploy", ...linesChart([{ name: "Dominance", points: d.dominance_log }], v => v == null ? "–" : v.toFixed(1) + "%", { small: true })));
    const hd = [d.volume && d.volume.length ? { label: "BTC spot volume, 30-day average", points: d.volume, fmt: usdBig, delta: { lag: "90d" } } : null,
      d.dominance_log && d.dominance_log.length > 1 ? { label: "BTC dominance", points: d.dominance_log, fmt: v => v.toFixed(1) + "%", delta: { lag: "30d", abs: true, fmt: v => (v > 0 ? "+" : "") + v.toFixed(1) + " pts" } } : null].filter(Boolean);
    const head = hd.length ? card(null, followHead(hd, { latest: "Latest" })) : null;
    return [head, status, ...charts, doc, timing, breakers];
  },
};

window.TOPIC = { VIEWS };
})();
