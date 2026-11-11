// AI Stocks: the setup after the dip. Data from /api/ai-stocks/<setup|drawdown|trend|dips|fear|fundamentals|institutions>; helpers from topic.html.
// Leans: +1 = the setup reads healthier, -1 = more stress. Not investment advice: the page describes, it makes no buy or sell call.
(() => {
const dateOf = s => s ? new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) : "–";
const share = v => v == null ? "–" : Math.round(v * 100) + "%";
const ddf = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const rsiCls = v => v == null ? "" : v < 30 ? "down" : v > 70 ? "up" : "";
const errs = (d, what) => d && d.errors && Object.keys(d.errors).length ? el("div", { class: "muted" }, what + " not available right now: " + Object.entries(d.errors).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const unavailable = (title, d, key) => card(title, el("div", { class: "muted" }, "Not available right now (" + ((d && d[key + "_error"]) || "no data") + ")."));
const td = (v, c) => el("td", c ? { class: c } : {}, v);
const SMALL = "Not investment advice: where the numbers stand, not what to do.";
// the current dip as its own line on a drawdown chart, so it stands out from the history
const currentDip = pts => { if (!pts || !pts.length) return []; let i = pts.length - 1; while (i > 0 && pts[i][1] < 0) i--; return pts.slice(i); };

// ---------- AI Setup Score: 0 = fear or washout, 100 = euphoria; six bands
const BAND_COL = { washout: "#15803d", fear: "#4ade80", soft: "#9ca3af", neutral: "#6b7fa8", warm: "#f59e0b", stretched: "#dc2626" };
const BAND_LAB = { washout: "Washout: past bottoms", fear: "Fear", soft: "Soft", neutral: "Neutral", warm: "Warm", stretched: "Stretched: drawdown risk" };
const BAND_EDGES = [[0, 10, "washout"], [10, 20, "fear"], [20, 50, "soft"], [50, 80, "neutral"], [80, 90, "warm"], [90, 100, "stretched"]];
const bandOf = v => v == null ? null : (BAND_EDGES.find(([lo, hi]) => v >= lo && v < hi) || BAND_EDGES[5])[2];
const bandCls = b => b === "washout" || b === "fear" ? "up" : b === "stretched" || b === "warm" ? "down" : "";

function gauge(v) {
  return svgBox(150, (host, w, h) => {
    const s = svgEl("svg", { width: w, height: h, viewBox: "0 0 " + w + " " + h }, host);
    const cx = w / 2, cy = h - 18, r = Math.min(w / 2 - 20, h - 42), th = 18;
    const pt = (val, rr) => { const a = Math.PI * (1 - val / 100); return [cx + rr * Math.cos(a), cy - rr * Math.sin(a)]; };
    BAND_EDGES.forEach(([lo, hi, k]) => {
      const [x1, y1] = pt(lo, r), [x2, y2] = pt(hi, r), [x3, y3] = pt(hi, r - th), [x4, y4] = pt(lo, r - th);
      svgEl("path", { d: `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2} L${x3},${y3} A${r - th},${r - th} 0 0 0 ${x4},${y4} Z`, fill: BAND_COL[k], opacity: bandOf(v) === k ? 1 : 0.45 }, s);
    });
    [0, 10, 20, 50, 80, 90, 100].forEach(x => { const [tx, ty] = pt(x, r + 9); svgEl("text", { x: tx, y: ty + 3, "text-anchor": "middle", "font-size": 10, fill: css("--muted") }, s).textContent = x; });
    if (v != null) {
      const [nx, ny] = pt(v, r - th - 6);
      svgEl("line", { x1: cx, y1: cy, x2: nx, y2: ny, stroke: css("--ink"), "stroke-width": 3, "stroke-linecap": "round" }, s);
      svgEl("circle", { cx, cy, r: 5, fill: css("--ink") }, s);
    }
  });
}

// the basket coloured by the score's band that day, and the score below it, both on the tab's date axis, today marked on both
function bandLineChart(points, score, opts) {
  const host = el("div", { class: "chart" + (opts.small ? " small" : "") });
  const bandAt = new Map(score.map(p => [p[0], bandOf(p[1])]));
  setTimeout(() => {
    const c = newChart(host, { rightPriceScale: { borderVisible: false, mode: opts.log ? 1 : 0 } });
    const line = c.addLineSeries({ priceLineVisible: false, lastValueVisible: false, lineWidth: 2, color: css("--muted"), priceFormat: { type: "custom", formatter: opts.fmt, minMove: 0.01 } });
    const data = dedupe(points.filter(p => p[1] != null)).map(d => ({ ...d, color: BAND_COL[bandAt.get(d.time)] || css("--muted") }));
    line.setData(data);
    (opts.hlines || []).forEach(h => line.createPriceLine({ price: h, color: css("--muted"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true }));
    if (data.length) line.setMarkers([{ time: data[data.length - 1].time, position: "aboveBar", shape: "arrowDown", color: css("--ink"), text: "Today" }]);
    syncAdd(c, line, data);
  });
  return host;
}
const bandLegend = () => el("div", { class: "legend" }, ...BAND_EDGES.map(([lo, hi, k]) => swatch(BAND_COL[k], lo + "–" + hi + " " + BAND_LAB[k])));

function scoreCards(d) {
  const S = d.score_now || {}, b = S.band, P = S.parts || {}, names = S.names || {};
  if (!d.score) return [unavailable("AI Setup Score", d, "score")];
  const G = card("AI Setup Score: " + num(S.v, 0) + " of 100, " + (BAND_LAB[b] || "–"),
    el("div", { style: "display:flex;flex-wrap:wrap;gap:16px;align-items:center" },
      el("div", { style: "flex:1 1 240px;max-width:360px" }, gauge(S.v)),
      el("div", { style: "flex:2 1 280px" },
        el("div", { style: "font-size:30px;font-weight:700;color:" + (BAND_COL[b] || "inherit") }, num(S.v, 0), el("span", { class: "muted", style: "font-size:14px;font-weight:500" }, " / 100 · " + (BAND_LAB[b] || ""))),
        el("p", { style: "margin:6px 0;line-height:1.5" }, S.sentence || ""),
        el("div", { class: "kpis" }, ...Object.keys(names).filter(k => P[k] != null).map(k => kpi(names[k], num(P[k], 0), P[k] < 20 ? "up" : P[k] > 80 ? "down" : ""))),
        note("Each part is today's percentile rank against its own history since 2020 (0 = most fearful day, 100 = most euphoric). The score is their average, smoothed over 5 days."))),
    el("div", { class: "kpis", style: "margin-top:8px" },
      kpi("Band changes, last 90 days", num(S.changes90), S.changes90 > 8 ? "down" : ""),
      ...(S.vix_only_changes90 != null ? [kpi("The same count for a VIX-only score", num(S.vix_only_changes90))] : []),
      kpi("Score date", dateOf(S.date))),
    note("0–10 washout (the band that has come near past bottoms), 10–20 fear, 20–50 soft, 50–80 neutral, 80–90 warm, 90–100 stretched (the band that has come before drawdowns). Small-sample history, not a forecast. " + SMALL));
  const csv = csvButton(csvName("setup score backtest"), () => seriesCsv([{ name: "AI basket", points: (d.lines || {})["AI basket"] || [] }, { name: "AI Setup Score", points: d.score }], "date", isoTime));
  const BT = card("Backtest: the AI basket coloured by the score's band, and the score",
    el("div", { class: "legend" }, ...BAND_EDGES.map(([lo, hi, k]) => swatch(BAND_COL[k], lo + "–" + hi + " " + BAND_LAB[k])), csv),
    bandLineChart((d.lines || {})["AI basket"] || [], d.score, { log: true, fmt: v => num(v, 0) }),
    bandLineChart(d.score, d.score, { small: true, fmt: v => num(v, 0), hlines: [10, 90] }),
    note("Top: the equal-weight AI basket (100 = 2 Jan 2020, log scale), each day coloured by that day's score band. Bottom: the score, dashed at 10 and 90. Use the date buttons above to move both. " +
      "The bands rank each day against the whole history since 2020, days after it included: a description of the past, not a rule anyone could have traded."));
  const E = d.score_episodes || {}, part = (v, p) => v == null ? "–" : pct(v, 0) + (p ? " so far" : "");
  const nm = e => e.name ? el("span", { class: "muted" }, " · " + e.name) : null;
  const GT = card("Each washout episode (score below 10)", table(["Started", "Score", "Basket", "Best gain, next 6 months", "Best gain, next 12 months"],
    (E.green || []).map(e => el("tr", {}, td([dateOf(e.date), nm(e)]), td(num(e.score, 1)), td(num(e.level, 0)), td(part(e.best6m, e.partial6m), "up"), td(part(e.best12m, e.partial12m), "up")))),
    note("An episode starts on the first day below 10, at least 30 days after the last day below 10. Best gain: the highest close in the next 126 (or 252) trading days against the close that day. Small sample, not a forecast."));
  const RT = card("Each stretched episode (score 90 or above)", table(["Started", "Score", "Basket", "Worst fall, next 90 days"],
    (E.red || []).map(e => el("tr", {}, td([dateOf(e.date), nm(e)]), td(num(e.score, 1)), td(num(e.level, 0)), td(part(e.worst90d, e.partial), "down")))),
    note("Worst fall: the lowest close in the next 90 calendar days against the close that day (0 when it never closed lower). Names come from data/ai-stocks/events.csv."));
  const H = ["1m", "3m", "6m"], HL = { "1m": "1 month", "3m": "3 months", "6m": "6 months" };
  const ST = card("What each band has meant: forward basket returns from every day in it since 2020",
    table(["Band", "Days", "Episodes", ...H.map(h => HL[h] + ": median"), ...H.map(h => HL[h] + ": higher")],
      (d.band_stats || []).map(r => el("tr", {}, td([swatch(BAND_COL[r.band], r.lo + "–" + r.hi + " " + r.label)]), td(num(r.days)), td(num(r.episodes)),
        ...H.map(h => td(r[h].median == null ? "–" : pct(r[h].median, 1), cls(r[h].median))), ...H.map(h => td(r[h].hit == null ? "–" : share(r[h].hit) + " of " + num(r[h].n)))))),
    note("Forward returns over 21, 63 and 126 trading days from each day in the band, counting only days whose horizon has passed. Neighbouring days overlap, so the episodes column is the number of independent samples. Small-sample history, not a forecast, and not investment advice."));
  return [G, BT, GT, RT, ST];
}

// ---------- After past dips: the core basket against core + the owner's picks as one index, on both backtests
function compareCards(X, H, HL) {
  if (!X || !X.core || !X.combined) return [];
  const K = [["core", "AI basket (13)"], ["combined", "Combined (" + (X.combined_members || []).length + ")"]];
  const med = (S, h) => { const s = (S || {})[h] || {}; return s.median == null ? "–" : pct(s.median, 0) + " (" + s.up + "/" + s.n + " up)"; };
  const band = k => el("span", {}, swatch(BAND_COL[X[k].band_now] || "var(--muted)", ""), X[k].score_now == null ? "–" : num(X[k].score_now, 0));
  const head = card("Core basket against core + your picks combined",
    table(["", "Return since Jan 2020", "Worst drawdown", "Now below its high", "Setup Score now", "Past 15% dips", ...H.map(h => HL[h] + " after the 15% point"), ...H.map(h => HL[h] + " after the bottom")],
      K.map(([k, lab]) => el("tr", {}, td(lab), td(pct(X[k].total, 0), cls(X[k].total)), td(ddf(X[k].worst), "down"), td(ddf(X[k].dd_now), X[k].dd_now < -0.15 ? "down" : ""), td(band(k)),
        td(num(X[k].n)), ...H.map(h => td(med(X[k].cross, h), cls(((X[k].cross || {})[h] || {}).median))), ...H.map(h => td(med(X[k].bottom, h), cls(((X[k].bottom || {})[h] || {}).median)))))),
    note("Combined: all " + (X.combined_members || []).length + " stocks of both groups (Oracle, AMD and Nvidia once) in one equal-weight index, rebalanced daily, each stock from its first full month of trading" +
      (Object.keys(X.combined_since || {}).length ? " (" + Object.entries(X.combined_since).map(([s, t]) => s + " from " + dateOf(t)).join(", ") + ")" : "") +
      ". The picks that listed late join the combined index only when they start trading, so its early years are mostly the core basket. Both backtests are rerun on each index: the 15% dip study (median return, episodes up of episodes) and the Setup Score, rebuilt from each index's own drawdown, breadth, RSI and return against QQQ. Small samples, history and not a forecast."));
  const dd = card("Drawdown: core basket and combined", ...linesChart([{ name: "AI basket (13)", points: X.core.dd, color: css("--s1") }, { name: "Combined", points: X.combined.dd, color: css("--s2") }], ddf, { hlines: [-0.15] }));
  const C = X.combined, rows = C.rows || [];
  const T = card("Combined index: each drawdown of 15% or more", table(["Peak", "15% point", "Bottom", "Depth", ...H.map(h => HL[h] + " after 15%"), ...H.map(h => HL[h] + " after bottom")],
    rows.map(r => el("tr", {}, td(dateOf(r.peak) + (r.ongoing ? " (now)" : "")), td(dateOf(r.cross15)), td(dateOf(r.trough)), td(ddf(r.depth), "down"),
      ...H.map(h => td(r.cross[h] == null ? "–" : pct(r.cross[h], 0), cls(r.cross[h]))), ...H.map(h => td(r.bottom[h] == null ? "–" : pct(r.bottom[h], 0), cls(r.bottom[h])))))));
  const st = k => (X[k].band_stats || []);
  const S = card("Setup Score bands, core against combined: median return 3 months later, and how often it was higher",
    table(["Band", "Core: days", "Core: 3 months", "Combined: days", "Combined: 3 months"],
      st("core").map((r, i) => { const c = st("combined")[i] || { "3m": {} }; const f = x => x.median == null ? "–" : pct(x.median, 1) + " · " + share(x.hit) + " higher";
        return el("tr", {}, td([swatch(BAND_COL[r.band], r.lo + "–" + r.hi + " " + r.label)]), td(num(r.days)), td(f(r["3m"]), cls(r["3m"].median)), td(num(c.days)), td(f(c["3m"]), cls(c["3m"].median))); })),
    C.sentence ? note("Combined, today's band: " + C.sentence) : null,
    note("Each index gets its own score, ranked against its own history since 2020, so a day can sit in different bands for the two."));
  const E = C.score_episodes || {}, part = (v, p) => v == null ? "–" : pct(v, 0) + (p ? " so far" : "");
  const GE = card("Combined index: washout (<10) and stretched (90+) episodes", table(["Started", "Band", "Score", "Level", "Best gain, 6 months", "Best gain, 12 months", "Worst fall, 90 days"],
    [...(E.green || []).map(e => el("tr", {}, td(dateOf(e.date)), td("washout"), td(num(e.score, 1)), td(num(e.level, 0)), td(part(e.best6m, e.partial6m), "up"), td(part(e.best12m, e.partial12m), "up"), td("–"))),
     ...(E.red || []).map(e => el("tr", {}, td(dateOf(e.date)), td("stretched"), td(num(e.score, 1)), td(num(e.level, 0)), td("–"), td("–"), td(part(e.worst90d, e.partial), "down")))]),
    note("Same rules as the Setup tab's episode tables, on the combined index. Small sample, not a forecast."));
  return [head, dd, T, S, GE];
}

// ---------- the stock panel (from the strip): insiders (Form 4), institutions (13F consensus) and fundamentals (companyfacts)
const ONCE = {};
const once = name => ONCE[name] || (ONCE[name] = api(name).catch(e => { delete ONCE[name]; return { error: e.message }; }));
const money = v => v == null ? "–" : (v < 0 ? "−$" : "$") + big(Math.abs(v));
function spark(pts, fmt) {
  if (!pts || pts.length < 2) return el("span", { class: "muted" }, "–");
  return svgBox(28, (host, w, h) => {
    const s = svgEl("svg", { width: w, height: h }, host), vs = pts.map(p => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    const x = t => 2 + (w - 4) * (t - t0) / ((t1 - t0) || 1), y = v => h - 3 - (h - 6) * (v - lo) / ((hi - lo) || 1);
    if (lo < 0 && hi > 0) svgEl("line", { x1: 0, x2: w, y1: y(0), y2: y(0), stroke: css("--line") }, s);
    svgEl("polyline", { points: pts.map(p => x(p[0]) + "," + y(p[1])).join(" "), fill: "none", stroke: css("--s1"), "stroke-width": 1.6 }, s);
    const title = svgEl("title", {}, s); title.textContent = pts.map(p => dayOf(p[0]) + ": " + fmt(p[1])).join("\n");
  });
}
const METRICS = [["rev_growth", "Revenue growth (4 quarters on a year)", v => pct(v, 0)], ["eps_growth", "EPS growth (diluted, 4 quarters on a year)", v => pct(v, 0)],
  ["gross_margin", "Gross margin", v => (v * 100).toFixed(1) + "%"], ["op_margin", "Operating margin", v => (v * 100).toFixed(1) + "%"], ["fcf", "Free cash flow, 4 quarters", v => (v < 0 ? "−$" : "$") + Math.abs(v).toFixed(1) + "bn"],
  ["roe", "Return on equity", v => pct(v, 0)], ["debt_equity", "Debt to equity", v => num(v, 2)]];

function buyTable(rows, withSym) {
  return table([...(withSym ? ["Stock"] : []), "Insider", "Role", "Date", "Shares", "Price", "Value", ""],
    rows.map(b => el("tr", {}, ...(withSym ? [td(el("b", {}, b.sym))] : []), td(link(b.name, b.link)), td(b.role || "–"), td(dateOf(b.date)), td(num(b.shares)), td(usd(b.price, 2)), td(money(b.value), "up"),
      td(b.cluster ? el("span", { class: "pill", style: "color:var(--up);font-size:11px" }, "cluster buy") : ""))));
}

async function panelBody(sym) {
  const [I, N, C] = await Promise.all([once("insiders"), once("institutions"), once("companies")]);
  const name = ((C && C.names) || {})[sym] || sym, cik = ((C && C.ciks) || {})[sym];
  const src = (t, s) => el("div", { class: "src", style: "margin-top:4px" }, s);
  const sec = (title, ...kids) => el("div", { style: "border-top:1px solid var(--line);padding-top:10px;margin-top:12px" }, el("h3", { style: "margin:0 0 6px;font-size:15px" }, title), ...kids);
  // insiders
  const S = ((I && I.stocks) || {})[sym];
  let ins;
  if ((I.foreign || []).includes(sym)) ins = el("div", { class: "muted" }, name + " is a foreign private issuer: its insiders do not file Form 4.");
  else if (!S) ins = el("div", { class: "muted" }, "Not fetched yet (" + (((I && I.errors) || {})[sym] || (I && I.error) || "no data") + "): the server downloads Form 4 filings in the background.");
  else {
    const sl = S.sales || {};
    ins = el("div", {}, S.buys.length ? buyTable(S.buys) : el("div", {}, el("b", {}, "No open-market purchases"), " in the last " + I.days + " days."),
      el("div", { style: "margin-top:6px" }, el("span", { class: "muted" }, "Sales: "), sl.n ? [num(sl.n) + " sales by " + num(sl.insiders) + " insider" + (sl.insiders === 1 ? "" : "s") + ", " + num(sl.shares) + " shares, " + money(sl.value) + "; ",
        el("b", {}, money(sl.plan_value)), " (" + num(sl.plan_n) + " of " + num(sl.n) + ") under a Rule 10b5-1 plan."] : "none."),
      note("Most insider selling is planned (10b5-1) or tax-driven; purchases with their own money carry more signal."));
  }
  // institutions
  const row = ((N && N.consensus) || []).find(r => r.ticker === sym);
  const inst = !N || N.error || !(N.funds || []).length ? el("div", { class: "muted" }, "13F filings not fetched yet.")
    : row ? el("div", {}, el("b", { class: cls(row.net) }, (row.net > 0 ? "+" : "") + row.net + " net funds"), ": " + row.n_buy + " opened or added, " + row.n_sell + " trimmed or sold, net " + (row.net_usd > 0 ? "+" : "") + money(row.net_usd) + ".",
        el("div", { class: "muted", style: "font-size:12px;margin-top:2px" }, [...row.buyers, ...row.sellers].join(", ")))
    : el("div", { class: "muted" }, "None of the " + N.funds.length + " funds changed its position last quarter.");
  // fundamentals
  const F = ((C && C.stocks) || {})[sym];
  let fun;
  if (!F) fun = el("div", { class: "muted" }, "Not fetched yet (" + (((C && C.errors) || {})[sym] || (C && C.error) || "no data") + ").");
  else if (!F.available) fun = el("div", { class: "muted" }, name + ": " + F.why + ".");
  else fun = el("div", {}, F.stale ? el("div", { class: "warn" }, "The latest facts are for a period ending " + dateOf(F.period_end) + ": over 200 days old.") : null,
    table(["Measure", "Latest", "5 years"], METRICS.map(([k, lab, f]) => { const m = (F.metrics || {})[k] || {}; return el("tr", {}, td(lab), td(m.v == null ? "–" : f(m.v), k === "fcf" || k.endsWith("growth") || k.endsWith("margin") || k === "roe" ? cls(m.v) : ""), el("td", { style: "width:42%;min-width:120px" }, spark(m.spark, f))); })),
    note("Trailing four quarters from 10-Q and 10-K facts. Growth against the same four quarters a year before (– when the base was a loss). ROE: net income over equity at the period end. Debt: long-term debt including its current part."));
  return [
    sec("Insiders: Form 4, last " + ((I && I.days) || 90) + " days", ins, src(0, ["SEC EDGAR Form 4 filings", I && I.as_of ? ", latest filed " + dateOf(I.as_of) : "", " · ", link("all " + sym + " Form 4s", cik ? "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + String(cik).padStart(10, "0") + "&type=4&dateb=&owner=include&count=40" : null)])),
    sec("Institutions: 13F consensus", inst, src(0, ["SEC EDGAR 13F-HR filings of 10 funds, quarter to " + dateOf(N && N.as_of) + " (each fund its own latest). US long positions only."])),
    sec("Fundamentals", fun, src(0, ["SEC EDGAR companyfacts", F && F.available ? ": " + F.form + " for the period to " + dateOf(F.period_end) + ", filed " + dateOf(F.filed) : ""])),
    el("div", { class: "muted", style: "margin-top:12px" }, SMALL)];
}

window.openStock = sym => {
  const old = document.getElementById("stockpanel"); if (old) old.remove();
  const close = () => { wrap.remove(); document.removeEventListener("keydown", esc); };
  const esc = e => { if (e.key === "Escape") close(); };
  const body = el("div", {}, el("div", { class: "muted" }, "Loading…"));
  const box = el("div", { role: "dialog", "aria-modal": "true", "aria-label": sym, style: "background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:12px;max-width:760px;width:100%;box-sizing:border-box;max-height:90vh;overflow:auto;padding:14px 16px;box-shadow:0 10px 40px rgba(0,0,0,.25)" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:baseline;gap:8px" }, el("h2", { style: "margin:0", id: "stockpanel-title" }, sym), el("button", { type: "button", "aria-label": "Close", style: "border:0;background:none;font-size:22px;cursor:pointer;color:var(--muted)", onclick: close }, "×")),
    body);
  const wrap = el("div", { id: "stockpanel", style: "position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:flex-start;justify-content:center;padding:4vh 12px;z-index:50", onclick: e => { if (e.target === wrap) close(); } }, box);
  document.body.append(wrap); document.addEventListener("keydown", esc);
  once("companies").then(C => { const n = ((C && C.names) || {})[sym]; const h = document.getElementById("stockpanel-title"); if (n && h) h.textContent = sym + " · " + n; });
  panelBody(sym).then(kids => body.replaceChildren(...kids)).catch(e => body.replaceChildren(el("div", { class: "muted" }, "Not available right now (" + e.message + ").")));
};

// the strip at the top of Setup: SPY, QQQ, SMH and VIX, then every stock; a stock opens its panel (openStock), else its EDGAR Form 4 list
function stripCard(d) {
  const S = d.strip || [];
  if (!S.length) return null;
  const chip = x => {
    const vixChip = x.kind === "vix";            // a level, not a price: points on the day, red when it rises (more fear)
    const body = vixChip ? [el("b", {}, "VIX"), " ", el("span", {}, num(x.price, 1)), " ", el("span", { class: cls(-x.day) }, (x.day > 0 ? "+" : x.day < 0 ? "−" : "") + num(Math.abs(x.day), 1))]
      : [el("b", {}, x.sym), " ", el("span", {}, usd(x.price, 2)), " ", el("span", { class: cls(x.day) }, pct(x.day, 1))];
    const st = "display:inline-flex;gap:4px;align-items:baseline;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:13px;white-space:nowrap;text-decoration:none;color:inherit;background:var(--surface,transparent)" + (x.group === "index" ? ";font-weight:600" : "");
    if (vixChip) return el("a", { href: "#fear", style: st, title: "Cboe Volatility Index, " + dateOf(x.date) + " (" + pct(x.day_pct, 1) + " on the day). Click for the VIX chart on Fear & relative." }, ...body);
    if (x.group === "index") return el("span", { style: st, title: x.name }, ...body);
    if (window.openStock) return el("button", { type: "button", style: st + ";cursor:pointer;font:inherit;font-size:13px", title: x.name + ": insiders, institutions, fundamentals", onclick: () => window.openStock(x.sym) }, ...body);
    return el("a", { href: x.form4, target: "_blank", rel: "noopener", style: st, title: x.name + ": Form 4 insider filings on EDGAR" }, ...body);
  };
  const row = (lab, xs) => xs.length ? el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px" }, el("span", { class: "muted", style: "min-width:96px" }, lab), ...xs.map(chip)) : null;
  return card(null, row("Indexes", S.filter(x => x.group === "index")), row("AI basket", S.filter(x => x.group === "core")), row("Owner's picks", (d.pick_cards || []).map(c => S.find(x => x.sym === c.sym)).filter(Boolean)),
    note("Last close and the move on the day" + (S[0] ? ", " + dateOf(S[0].date) : "") + "; VIX in points, its own latest day" + ((S.find(x => x.kind === "vix") || {}).date ? " (" + dateOf(S.find(x => x.kind === "vix").date) + ")" : "") + ", red when it rises. " + (window.openStock ? "Click a stock for its insiders, institutions and fundamentals." : "Click a stock for its Form 4 insider filings on EDGAR.") + " " + SMALL));
}

function stockCard(c) {
  const row = (l, v, k) => el("div", { style: "display:flex;justify-content:space-between;gap:8px" }, el("span", { class: "muted" }, l), el("b", { class: k || "" }, v));
  return el("div", { style: "border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--surface,transparent)" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:baseline;gap:6px;margin-bottom:4px" }, el("b", {}, c.sym), el("span", { class: "muted" }, c.name)),
    el("div", { style: "font-size:18px;font-weight:650;margin-bottom:4px" }, usd(c.price, 2)),
    row("From 52-week high", ddf(c.dd52), c.dd52 != null && c.dd52 < -0.2 ? "down" : ""),
    row("vs 50-day", pct(c.vs50, 1), cls(c.vs50)),
    row("vs 200-day", pct(c.vs200, 1), cls(c.vs200)),
    row("RSI 14", c.rsi == null ? "–" : num(c.rsi, 0), rsiCls(c.rsi)));
}

const VIEWS = {
  async setup() {
    const d = await api("setup"), N = d.now || {};
    const head = card("Where we are", followHead([
      ...(d.score ? [{ label: "AI Setup Score", points: d.score, fmt: v => num(v, 0) + " · " + BAND_LAB[bandOf(v)], cls: v => bandCls(bandOf(v)) }] : []),
      { label: "AI basket below its high", points: d.dd, fmt: ddf, cls: v => v < -0.2 ? "down" : v > -0.05 ? "up" : "" },
      { label: "Stocks above their 50-day", points: d.breadth50, fmt: share, cls: v => v < 0.2 ? "down" : v > 0.6 ? "up" : "" },
      { label: "Basket RSI 14", points: d.rsi, fmt: v => num(v, 0), cls: rsiCls },
      ...(d.vix ? [{ label: "VIX", points: d.vix, fmt: v => num(v, 1), cls: v => v > 30 ? "down" : v < 20 ? "up" : "" }] : [])]),
      el("p", { style: "margin:10px 0 0;line-height:1.5" }, d.where || ""),
      note(N.n ? N.above200 + " of " + N.n + " stocks are above their 200-day average. " + SMALL : SMALL), errs(d, "Some prices are"), asOf(d), stale(d));
    const grid = cs => el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px" }, ...cs.map(stockCard));
    const cards = (d.cards || []).length ? card("AI basket (13 stocks): how far from its high, against its averages", grid(d.cards),
      note("From 52-week high: the last close against the highest close of the last 252 trading days. vs 50-day and vs 200-day: the close against its simple average. RSI 14 (Wilder): under 30 reads oversold, over 70 overbought."))
      : unavailable("Stocks", d, "cards");
    const P = d.picks_now || {}, since = Object.entries(P.since || {});
    const picks = (d.pick_cards || []).length ? card("Owner's picks (10 stocks), their own equal-weight index",
      d.picks_dd ? followHead([{ label: "Owner's picks below their high", points: d.picks_dd, fmt: ddf, cls: v => v < -0.2 ? "down" : v > -0.05 ? "up" : "" }]) : null,
      note(P.n ? P.above200 + " of " + P.n + " picks are above their 200-day average" + (P.breadth50 != null ? ", " + share(P.breadth50) + " above their 50-day." : ".") : ""),
      grid(d.pick_cards),
      note("SanDisk, Nebius, Bloom Energy, Marvell, Oracle, IREN, AppLovin, AMD, Rocket Lab and Nvidia (Oracle, AMD and Nvidia are in both groups). A stock joins the picks index from its first full month of trading" +
        (since.length ? " (" + since.map(([k, v]) => k + " " + month(Date.parse(v) / 1000)).join(", ") + ")" : "") + "; Nebius counts from its October 2024 relisting, not Yandex before it. " + SMALL))
      : unavailable("Owner's picks", d, "pick_cards");
    const L = d.lines ? card("The AI basket and the owner's picks against QQQ and SPY, 100 = 2 Jan 2020",
      ...linesChart(Object.entries(d.lines).map(([k, p]) => ({ name: k, points: p, color: css(k === "AI basket" ? "--s1" : k === "QQQ" ? "--s2" : k === "Owner's picks" ? "--s3" : "--s4") })), v => num(v, 0), { log: true }),
      note("Equal-weight basket of NVDA, AVGO, AMD, TSM, ASML, MU, ARM, MSFT, GOOGL, AMZN, META, ORCL and PLTR, rebalanced daily (Arm from its listing in September 2023). Owner's picks: the same method on its 10 stocks. Prices without dividends, log scale."))
      : unavailable("Basket against QQQ and SPY", d, "lines");
    const [G, BT, ...tabs] = scoreCards(d);
    return [stripCard(d), G, head, BT, ...tabs, cards, picks, L].filter(Boolean);
  },

  async drawdown() {
    const d = await api("drawdown"), C = d.current || {}, E = d.episodes || [];
    const head = card("How deep is the dip?", d.basket ? followHead([
      { label: "AI basket below its peak", points: d.basket, fmt: ddf, cls: v => v < -0.2 ? "down" : v > -0.05 ? "up" : "" }]) : null,
      el("div", { class: "kpis" }, kpi("Peak", dateOf(C.peak)), kpi("Deepest so far", ddf(C.low), C.low != null && C.low < -0.2 ? "down" : ""), kpi("Lowest close", dateOf(C.low_date)),
        kpi("Days since the peak", C.days == null ? "–" : num(C.days))),
      note("Drawdown is the fall from the running peak since January 2020; 0 means a new high. " + SMALL), errs(d, "Some prices are"), asOf(d), stale(d));
    const B = d.basket ? card("AI basket drawdown since 2020, the current dip in red",
      ...linesChart([{ name: "AI basket", points: d.basket, color: css("--s1") }, { name: "Current dip", points: currentDip(d.basket), color: css("--down") }], ddf, { hlines: [-0.1, -0.2] }),
      note("Dashed lines at -10% (a correction) and -20% (a bear market).")) : unavailable("Basket drawdown", d, "basket");
    const S = d.stocks ? card("Each stock's drawdown from its peak since 2020",
      ...linesChart(Object.entries(d.stocks).map(([k, p]) => ({ name: k + " " + ddf((d.stock_now || {})[k]), points: p })), ddf, { small: false }),
      note("Click a name to hide it. A stock that listed after 2020 (Arm) counts from its first close.")) : unavailable("Stock drawdowns", d, "stocks");
    const PC = d.picks_current || {};
    const PB = d.picks_basket ? card("Owner's picks index: drawdown since 2020, the current dip in red",
      el("div", { class: "kpis" }, kpi("Below its peak now", ddf(PC.dd), PC.dd != null && PC.dd < -0.2 ? "down" : ""), kpi("Peak", dateOf(PC.peak)), kpi("Deepest so far", ddf(PC.low), PC.low != null && PC.low < -0.2 ? "down" : ""),
        kpi("Days since the peak", PC.days == null ? "–" : num(PC.days))),
      ...linesChart([{ name: "Owner's picks", points: d.picks_basket, color: css("--s3") }, { name: "Current dip", points: currentDip(d.picks_basket), color: css("--down") }], ddf, { hlines: [-0.1, -0.2] }),
      note("Equal-weight index of the 10 picks, each from its first full month of trading. Dashed lines at -10% and -20%.")) : unavailable("Owner's picks drawdown", d, "picks_basket");
    const PS = d.pick_stocks && Object.keys(d.pick_stocks).length ? card("Each pick's drawdown over its own history",
      ...linesChart(Object.entries(d.pick_stocks).map(([k, p]) => ({ name: k + " " + ddf((d.pick_now || {})[k]), points: p })), ddf, { small: false }),
      note("Each stock from 2020 or from its own first close, whichever is later: " + Object.entries(d.pick_since || {}).filter(([k, v]) => v > "2020-01-10").map(([k, v]) => k + " from " + dateOf(v)).join(", ") +
        ". Nebius from its October 2024 relisting; Rocket Lab from its August 2021 listing, not the SPAC before it.")) : unavailable("Pick drawdowns", d, "pick_stocks");
    const T = card("Every basket drawdown over 10% since 2020", table(["Peak", "Bottom", "Depth", "Days to bottom", "Recovered", "Days to recover"],
      E.map(e => el("tr", {}, td(dateOf(e.peak)), td(dateOf(e.trough)), td(ddf(e.depth), e.depth < -0.2 ? "down" : ""), td(num(e.days_to_bottom)),
        td(e.ongoing ? "not yet" : dateOf(e.recovered)), td(e.days_to_recover == null ? "–" : num(e.days_to_recover))))),
      note("Calendar days, peak to bottom and bottom to the next new high. The row marked \"not yet\" is the dip we are in."));
    return [head, B, S, PB, PS, T];
  },

  async trend() {
    const d = await api("trend"), N = d.now || {};
    const head = card("Washing out or still breaking down?", followHead([
      { label: "Above their 50-day", points: d.breadth50, fmt: share, cls: v => v < 0.2 ? "down" : v > 0.6 ? "up" : "" },
      { label: "Above their 200-day", points: d.breadth200, fmt: share, cls: v => v < 0.4 ? "down" : v > 0.6 ? "up" : "" },
      { label: "Basket RSI 14", points: d.rsi, fmt: v => num(v, 0), cls: rsiCls },
      { label: "50-day over 200-day", points: d.spread, fmt: v => pct(v, 1), cls }]),
      note("The basket's 50-day average is " + (N.state === "golden" ? "above" : "below") + " its 200-day" + (N.since ? " since " + dateOf(N.since) : "") + "; the basket is " +
        pct(N.vs50, 1) + " from its 50-day and " + pct(N.vs200, 1) + " from its 200-day. " + SMALL), errs(d, "Some prices are"), asOf(d), stale(d));
    const BR = d.breadth50 ? card("Share of the 13 stocks above their own averages",
      ...linesChart([{ name: "Above 50-day", points: d.breadth50, color: css("--s1") }, { name: "Above 200-day", points: d.breadth200, color: css("--s2") }], share, { hlines: [0.2, 0.6] }),
      note("Dashed lines at 20% (a washout: almost everything below its average) and 60% (a recovery broadening).")) : unavailable("Breadth", d, "breadth50");
    const R = d.rsi ? card("Basket RSI 14", ...linesChart([{ name: "RSI 14", points: d.rsi, color: css("--s3") }], v => num(v, 0), { hlines: [30, 70] }),
      note("Under 30 reads oversold, over 70 overbought. Wilder's smoothing, on the basket index.")) : unavailable("RSI", d, "rsi");
    const MA = d.basket ? card("The basket with its 50- and 200-day averages",
      ...linesChart([{ name: "AI basket", points: d.basket, color: css("--s1") }, { name: "50-day", points: d.ma50, color: css("--s2") }, { name: "200-day", points: d.ma200, color: css("--s4"), dashed: true }], v => num(v, 0), { log: true }))
      : unavailable("Averages", d, "basket");
    const X = card("50/200-day crosses of the basket", table(["Date", "Cross"], (d.crosses || []).map(c => el("tr", {}, td(dateOf(c.date)), td(c.kind === "golden" ? "50-day crossed above the 200-day" : "50-day crossed below the 200-day", c.kind === "golden" ? "up" : "down")))),
      note("A cross is a slow, lagging read of the trend: it comes weeks after the turn."));
    return [head, BR, R, MA, X];
  },

  async dips() {
    const d = await api("dips"), rows = d.rows || [], H = ["1m", "3m", "6m"], HL = { "1m": "1 month", "3m": "3 months", "6m": "6 months" };
    const head = card("What happened after dips like this before?", d.dd ? followHead([{ label: "AI basket below its peak", points: d.dd, fmt: ddf, cls: v => v <= -0.15 ? "down" : "" }]) : null,
      el("div", { class: "warn", style: "margin-top:8px" }, "A small sample: " + (d.n || 0) + " finished basket drawdowns of 15% or more since 2020. This is history, not a forecast, and not investment advice."),
      errs(d, "Some prices are"), asOf(d), stale(d));
    const sumRow = (lab, S) => el("tr", {}, td(lab), ...H.map(h => { const s = (S || {})[h] || {}; return td(s.median == null ? "–" : pct(s.median, 0) + " (" + pct(s.min, 0) + " to " + pct(s.max, 0) + ")", cls(s.median)); }),
      td(H.map(h => ((S || {})[h] || {}).up + "/" + ((S || {})[h] || {}).n).join(" · ")));
    const sum = card("Median return after the 15% point and after the bottom (range in brackets)",
      table(["Measured from", ...H.map(h => HL[h]), "Up / episodes (1m · 3m · 6m)"], [sumRow("The day it was first 15% below its peak", d.cross), sumRow("The bottom", d.bottom)]),
      note("Returns over 21, 63 and 126 trading days. The bottom is known only afterwards, so the second row is the best case of hindsight; the first row is what a reader on the day could have seen."));
    const bars = svgBars(H.map(h => HL[h]), [{ name: "After the 15% point", values: H.map(h => ((d.cross || {})[h] || {}).median), color: css("--s1") },
      { name: "After the bottom", values: H.map(h => ((d.bottom || {})[h] || {}).median), color: css("--s2") }], { yFmt: v => Math.round(v * 100) + "%" });
    const B = card("Median forward return, " + (d.n || 0) + " past drawdowns", ...bars);
    const T = card("Each drawdown of 15% or more", table(["Peak", "15% point", "Bottom", "Depth", "Further fall after 15%", ...H.map(h => HL[h] + " after 15%"), ...H.map(h => HL[h] + " after bottom")],
      rows.map(r => el("tr", {}, td(dateOf(r.peak) + (r.ongoing ? " (now)" : "")), td(dateOf(r.cross15)), td(dateOf(r.trough)), td(ddf(r.depth), "down"), td(ddf(r.further)),
        ...H.map(h => td(r.cross[h] == null ? "–" : pct(r.cross[h], 0), cls(r.cross[h]))), ...H.map(h => td(r.bottom[h] == null ? "–" : pct(r.bottom[h], 0), cls(r.bottom[h])))))),
      note("The current dip, when it is 15% or deeper, is listed but not in the medians: its returns are not known yet (–). Its \"bottom\" is the lowest close so far."));
    const C = d.dd ? card("Basket drawdown with the 15% line", ...linesChart([{ name: "AI basket", points: d.dd, color: css("--s1") }, { name: "Current dip", points: currentDip(d.dd), color: css("--down") }], ddf, { hlines: [-0.15] }))
      : unavailable("Drawdown", d, "dd");
    return [head, sum, B, T, C, ...compareCards(d.compare, H, HL)];
  },

  async fear() {
    const d = await api("fear"), R = d.relative || {}, V = d.vix_now || {};
    const ch3 = { lag: "3m", fmt: v => pct(v / 100, 1) };
    const head = card("Fear, and is AI leading or lagging?", followHead([
      ...(d.vix ? [{ label: "VIX", points: d.vix, fmt: v => num(v, 1), cls: v => v > 30 ? "down" : v < 20 ? "up" : "" }] : []),
      ...(d.ai_qqq ? [{ label: "AI basket ÷ QQQ", points: d.ai_qqq, fmt: v => num(v, 0), delta: ch3 }] : []),
      ...(d.smh_spy ? [{ label: "SMH ÷ SPY", points: d.smh_spy, fmt: v => num(v, 0), delta: ch3 }] : [])]),
      note((V.v != null ? "VIX " + num(V.v, 1) + " on " + dateOf(V.date) + ", highest in the last month " + num(V.max_1m, 1) + "; higher than " + share(V.pct_since_2020) + " of days since 2020. " : "") +
        (d.vix_source ? "VIX from " + d.vix_source + ". " : "") + SMALL), errs(d, "Some prices are"), asOf(d), stale(d));
    const VX = d.vix ? card("VIX", ...linesChart([{ name: "VIX", points: d.vix, color: css("--s3") }], v => num(v, 1), { hlines: [20, 30] }),
      note("Expected 30-day volatility of the S&P 500 from options prices. Dashed lines at 20 and 30.")) : unavailable("VIX", d, "vix");
    const RA = d.ai_qqq ? card("AI basket against QQQ, and semis (SMH) against SPY, 100 = Jan 2020",
      ...linesChart([{ name: "AI basket ÷ QQQ", points: d.ai_qqq, color: css("--s1") }, ...(d.smh_spy ? [{ name: "SMH ÷ SPY", points: d.smh_spy, color: css("--s2") }] : [])], v => num(v, 0)),
      note("Rising: the first one is doing better. Price ratios without dividends.")) : unavailable("Relative", d, "ai_qqq");
    const T = card("Returns over 3 and 12 months", table(["", "3 months", "vs", "Gap", "12 months", "vs", "Gap"],
      Object.entries(R).map(([k, r]) => el("tr", {}, td(k), td(pct(r["3m"].a, 1), cls(r["3m"].a)), td(pct(r["3m"].b, 1), cls(r["3m"].b)), td(pp(r["3m"].gap), cls(r["3m"].gap)),
        td(pct(r["12m"].a, 1), cls(r["12m"].a)), td(pct(r["12m"].b, 1), cls(r["12m"].b)), td(pp(r["12m"].gap), cls(r["12m"].gap))))),
      note("3 months = 63 trading days, 12 months = 252. Gap in percentage points: AI basket minus QQQ, SMH minus SPY."));
    return [head, VX, RA, T];
  },

  async fundamentals() {
    const d = await api("fundamentals"), K = d.capex_kpi || {}, L = d.last || {};
    const head = card("Is the business still growing under the prices?", followHead([
      ...(d.basket_yoy ? [{ label: "Basket revenue growth on a year", points: d.basket_yoy, fmt: v => pct(v, 1), cls }] : []),
      ...(d.capex_yoy ? [{ label: "Hyperscaler capex growth (4 quarters)", points: d.capex_yoy, fmt: v => pct(v, 0), cls }] : []),
      ...(d.capex_ttm ? [{ label: "Hyperscaler capex, last 4 quarters", points: d.capex_ttm, fmt: v => usd(v, 0) + "bn" }] : [])]),
      note("Revenue from the basket's US GAAP filers (" + Object.keys(L).join(", ") + "); " + (d.left_out || []).join(", ") + " file under IFRS without quarterly facts in EDGAR and are left out. " +
        "Valuation multiples are left out: no free source this server can reach. " + SMALL), errs(d, "Some figures are"), asOf(d), stale(d));
    const RV = d.revenue_yoy ? card("Revenue growth on a year, by company and for the basket",
      ...linesChart([...(d.basket_yoy ? [{ name: "Basket", points: d.basket_yoy, color: css("--ink"), width: 3 }] : []), ...Object.entries(d.revenue_yoy).map(([k, p]) => ({ name: k, points: p }))], v => pct(v, 0)),
      note("Quarterly revenue against the same calendar quarter a year before (SEC EDGAR 10-Q and 10-K). Basket: the summed revenue of the companies that reported both quarters."))
      : unavailable("Revenue growth", d, "revenue_yoy");
    const CX = d.capex_ttm ? card("Hyperscaler capex, trailing four quarters ($bn)",
      ...linesChart([{ name: "Capex, 4 quarters", points: d.capex_ttm, color: css("--s2") }], v => usd(v, 0) + "bn"),
      note("Microsoft, Alphabet, Amazon, Meta and Oracle, from the AI Compute, Power & Chips dashboard" + (K.date ? "; latest quarter to " + dateOf(K.date) : "") + ". Cash spent on property and equipment, all businesses."))
      : unavailable("Capex", d, "capex_ttm");
    const T = card("Latest quarter by company", table(["Company", "Quarter", "Revenue", "On a year"],
      Object.entries(L).map(([k, r]) => el("tr", {}, td(k), td(r.quarter), td(usd(r.revenue, 1) + "bn"), td(pct(r.yoy, 1), cls(r.yoy))))));
    return [head, RV, CX, T];
  },

  async institutions() {
    const d = await api("institutions"), F = d.funds || [], C = d.consensus || [];
    const TAG = { New: "up", Added: "up", Trimmed: "down", Sold: "down" };
    const money = v => v == null ? "–" : (v < 0 ? "−$" : "$") + big(Math.abs(v));
    const signed = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + "$" + big(Math.abs(v));
    const qlab = q => q ? "quarter to " + dateOf(q) : "–";
    const head = card("What big funds did with these stocks last quarter (13F filings)",
      el("div", { class: "kpis" }, kpi("Funds net-adding our stocks", (d.net_adding ?? "–") + " of " + (d.with_change ?? "–"), d.with_change ? (d.net_adding / d.with_change > 0.6 ? "up" : d.net_adding / d.with_change < 0.4 ? "down" : "") : ""),
        kpi("Latest quarter end", dateOf(d.as_of)), kpi("Funds", num(F.length))),
      el("div", { class: "warn", style: "margin-top:8px" }, "13F filings show US long positions only: no shorts, cash, non-13F assets or full derivative exposure. They are filed up to 45 days after the quarter ends, so read them by quarter end, not filing date. Each fund shows its own latest quarter, and some file late. Not investment advice."),
      note("Legend: New = first appears this quarter; Added = more shares than the previous quarter; Trimmed = fewer; Sold = no longer reported. Dollar change: New = the value now, Sold = the value before, Added and Trimmed = the change in shares at this quarter's end price."),
      errs(d, "Some funds are"));
    const fundCard = f => el("div", { style: "border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--surface,transparent)" },
      el("div", { style: "display:flex;justify-content:space-between;gap:8px;align-items:baseline" }, el("b", {}, f.name), link("13F ↗", f.link)),
      el("div", { class: "muted", style: "margin:2px 0 6px" }, qlab(f.quarter) + " · filed " + dateOf(f.filed) + " · compared with " + qlab(f.prev_quarter)),
      el("div", { style: "display:flex;gap:14px;flex-wrap:wrap;margin-bottom:6px" }, el("span", {}, el("span", { class: "muted" }, "Reported "), el("b", {}, money(f.total))),
        el("span", {}, el("span", { class: "muted" }, "In our stocks "), el("b", {}, money(f.ai_value))),
        el("span", {}, el("span", { class: "muted" }, "Net change "), el("b", { class: cls(f.net_usd) }, signed(f.net_usd)))),
      ...(f.top && f.top.length ? f.top.map(c => el("div", { style: "display:flex;justify-content:space-between;gap:8px" },
          el("span", {}, el("b", {}, c.ticker), " ", el("span", { class: "pill", style: "font-size:11px;color:var(--" + TAG[c.tag] + ")" }, c.tag)), el("b", { class: cls(c.usd) }, signed(c.usd))))
        : [el("div", { class: "muted" }, f.prev_quarter ? "No change in our stocks." : "Only one quarter on file.")]));
    const G = F.length ? card("Each fund: its three largest changes in our stocks", el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px" }, ...F.map(fundCard)))
      : card("Funds", el("div", { class: "muted" }, "Not fetched yet: the server downloads the 13F filings in the background, paced, and keeps them for 7 days. Check back in a few minutes."));
    const T = card("Consensus: per stock, how many funds bought and sold", table(["Stock", "Opened or added", "Trimmed or sold", "Net funds", "Net dollar change", "Who"],
      C.map(r => el("tr", {}, td([el("b", {}, r.ticker), " ", el("span", { class: "muted" }, r.name)]), td(num(r.n_buy), r.n_buy ? "up" : ""), td(num(r.n_sell), r.n_sell ? "down" : ""),
        td((r.net > 0 ? "+" : "") + r.net, cls(r.net)), td(signed(r.net_usd), cls(r.net_usd)), el("td", { class: "wrap", style: "font-size:12px;min-width:160px" }, el("details", {}, el("summary", { style: "cursor:pointer" }, (r.n_buy + r.n_sell) + " funds"),
          r.buyers.length ? el("div", {}, el("span", { class: "up" }, "Bought: "), r.buyers.join(", ")) : null,
          r.sellers.length ? el("div", {}, el("span", { class: "down" }, "Sold or trimmed: "), r.sellers.join(", ")) : null))))),
      note("Sorted by net buyers (funds that opened or added minus funds that trimmed or sold), then by net dollars. Each fund is compared with its own previous quarter. Stocks no fund changed are not listed. " + SMALL));
    return [head, G, T];
  },

  async insiders() {
    const d = await api("insiders"), B = d.buys || [], S = d.stocks || {};
    const head = card("Insiders buying with their own money (Form 4)",
      el("div", { class: "kpis" }, kpi("Open-market purchases, last 30 days", num(d.buys30), d.buys30 ? "up" : ""), kpi("Purchases, last " + d.days + " days", num(B.length)),
        kpi("Cluster buys, last 30 days", (d.clusters30 || []).length ? d.clusters30.join(", ") : "none", (d.clusters30 || []).length ? "up" : ""), kpi("Latest filing", dateOf(d.as_of))),
      note("Every open-market purchase (Form 4 code P) by an officer, director or 10% owner of a stock in either group in the last " + d.days + " days. A cluster buy: 2 or more insiders of one company buying within " + d.cluster_days +
        " days. Most insider selling is planned under Rule 10b5-1 or tax-driven; purchases carry more signal, but they are few and small next to the market. " + (d.foreign || []).join(", ") + " are foreign private issuers: their insiders do not file Form 4. " + SMALL),
      errs(d, "Some companies are"));
    const T = B.length ? card("Every open-market purchase, newest first", buyTable(B, true), note("Value: shares times the price reported. Click a name for the filing on EDGAR. Click a stock in the strip on Setup for its panel."))
      : card("Every open-market purchase", el("div", { class: "muted" }, Object.keys(S).length ? "No open-market purchases in the last " + d.days + " days." : "Not fetched yet: the server downloads Form 4 filings in the background."));
    const rows = Object.entries(S).sort((a, b) => (b[1].sales.value || 0) - (a[1].sales.value || 0));
    const SL = card("Sales by company, last " + d.days + " days (totals)", table(["Stock", "Purchases", "Sales", "Insiders selling", "Value sold", "Under a 10b5-1 plan"],
      rows.map(([k, v]) => el("tr", {}, td(el("button", { type: "button", style: "border:0;background:none;padding:0;font:inherit;font-weight:650;cursor:pointer;color:var(--accent)", onclick: () => window.openStock(k) }, k)),
        td(num(v.buys.length), v.buys.length ? "up" : ""), td(num(v.sales.n)), td(num(v.sales.insiders)), td(money(v.sales.value)), td(v.sales.value ? share(v.sales.plan_value / v.sales.value) + " of the value" : "–")))),
      note("Sales (code S) summed. A filing counts as under a plan when it ticks the Rule 10b5-1 box or a footnote names 10b5-1."));
    return [head, T, SL];
  },

  // event study: the 12 months after each US midterm election, the broad market and the cycle's tech proxy (the AI basket from 2022)
  async midterms() {
    const d = await api("midterms"), R = d.rows || [], S = d.summary || {}, C = d.current;
    const so = (v, p) => v == null ? "–" : pct(v, 1) + (p ? " so far" : "");
    const med = x => x && x.median != null ? pct(x.median, 1) : "–";
    const days = C ? Math.round((Date.now() / 1000 - Date.parse(C.date) / 1000) / 86400) : null;
    const head = card("What did stocks do in the 12 months after each midterm?", el("div", { class: "kpis" },
      kpi("Broad US market, median 12 months after (" + (S.market || {}).n + " midterms)", med(S.market), cls((S.market || {}).median)),
      kpi("Higher 12 months later", (S.market || {}).up + " of " + (S.market || {}).n),
      kpi("Tech proxy, median 12 months after (" + (S.proxy || {}).n + " since 1974)", med(S.proxy), cls((S.proxy || {}).median)),
      kpi("Tech proxy higher 12 months later", (S.proxy || {}).up + " of " + (S.proxy || {}).n),
      ...(C ? [kpi(C.year + " midterm (" + dateOf(C.date) + "): S&P 500 so far", so(C.sp500, true), cls(C.sp500)),
               kpi("Nasdaq-100 so far, " + days + " days in", so((C.proxy || {}).r12, true), cls((C.proxy || {}).r12)),
               ...(C.ai ? [kpi("AI basket so far", so(C.ai.r12, true), cls(C.ai.r12))] : [])] : [])),
      el("div", { class: "warn", style: "margin-top:8px" }, (S.market || {}).n + " midterms is a small sample, and each cycle had its own rates, recessions and wars. History, not a forecast, and not investment advice."),
      errs(d, "Some series are"), asOf(d), stale(d));
    const full = Object.entries(d.paths || {}).filter(([k, p]) => !/AI/.test(k) && p.length > 250);
    const cy = C ? String(C.year) : null;
    const lines = [...full.map(([k, p]) => ({ name: k, points: p, color: "color-mix(in srgb, var(--muted) 45%, transparent)", width: 1 })),
      ...(d.median_path && d.median_path.length ? [{ name: "Median of " + full.length + " cycles", points: d.median_path, color: css("--s1"), width: 3 }] : []),
      ...(d.paths && d.paths["2022 AI basket"] ? [{ name: "2022 AI basket", points: d.paths["2022 AI basket"], color: css("--s2"), width: 2 }] : []),
      ...(cy && d.paths && d.paths[cy] ? [{ name: cy + " Nasdaq-100 (so far)", points: d.paths[cy], color: css("--down"), width: 3 }] : []),
      ...(cy && d.paths && d.paths[cy + " AI basket"] ? [{ name: cy + " AI basket (so far)", points: d.paths[cy + " AI basket"], color: css("--s4"), width: 3 }] : [])];
    const P = lines.length ? card("The tech proxy's path after each midterm, 100 = election-day close",
      ...svgLines(lines, { xFmt: v => "day " + Math.round(v), yFmt: v => num(v, 0), xTicks: [0, 21, 63, 126, 189, 252], hline: 100, log: true, xName: "trading day after the election", h: 320,
        note: "Hover for each cycle on that trading day. 252 trading days is about 12 months." }),
      note("Grey: each midterm since 1974 on its cycle's proxy (Nasdaq Composite 1974–1982, Nasdaq-100 from 1986). Blue: the median of those cycles. Click a name to hide it."))
      : card("Paths", el("div", { class: "muted" }, "Not available right now."));
    const done = R.filter(r => r.complete).slice().reverse();
    const bars = done.length ? card("12-month return after each midterm: broad market against the tech proxy",
      ...svgBars(done.map(r => String(r.year)), [{ name: "Broad US market (OECD, monthly average)", values: done.map(r => r.market), color: css("--s1") },
        { name: "Tech proxy of the cycle", values: done.map(r => (r.proxy || {}).r12 == null ? null : r.proxy.r12), color: css("--s2") },
        ...(done.some(r => r.ai) ? [{ name: "AI basket", values: done.map(r => r.ai ? r.ai.r12 : null), color: css("--s4") }] : [])], { yFmt: v => Math.round(v * 100) + "%" })) : null;
    const T = card("Each midterm", table(["Election", "Broad market, 12 months", "S&P 500, 12 months", "Tech proxy", "Proxy, 6 months", "Proxy, 12 months", "Proxy's worst fall in the 12 months", "AI basket, 12 months"],
      R.map(r => { const p = r.proxy || {}; return el("tr", {}, td(dateOf(r.date)), td(r.market == null ? (r.complete ? "–" : "not yet") : pct(r.market, 1), cls(r.market)),
        td(so(r.sp500, r.sp500_partial), cls(r.sp500)), td(p.name || "none (before 1974)"), td(p.r6 == null ? "–" : pct(p.r6, 1), cls(p.r6)), td(so(p.r12, p.partial), cls(p.r12)),
        td(p.worst == null ? "–" : ddf(p.worst), p.worst < -0.1 ? "down" : ""), td(r.ai ? so(r.ai.r12, r.ai.partial) : "–", r.ai ? cls(r.ai.r12) : "")); })),
      note("12 months from the election-day close (the last close on or before it) to the last close a year later. Broad market: the OECD's US share-price index for all shares (FRED SPASTT01USM661N), the election month's average to the same month a year on, the only free series back to 1958; it is broader than the S&P 500 and fell in three of these years. S&P 500: FRED's daily closes, which start in 2016. Worst fall: the lowest close in the 12 months against the election-day close."));
    const W = card("Which index stands in for AI stocks in each cycle", table(["Midterms", "Proxy", "Why"], [
      el("tr", {}, td("1958–1970"), td("none"), td("No free daily technology index reaches back this far; the broad market only.")),
      el("tr", {}, td("1974–1982"), td("Nasdaq Composite"), td("Where that era's computer and chip makers (Intel, Apple from 1980) listed; it starts in 1971.")),
      el("tr", {}, td("1986–2018"), td("Nasdaq-100"), td("The largest non-financial Nasdaq companies: PCs, software, then the internet and smartphones; it starts in 1985.")),
      el("tr", {}, td("2022–"), td("AI basket, with the Nasdaq-100"), td("This dashboard's 13 AI leaders (equal weight, from 2020), next to the Nasdaq-100 so the cycles stay comparable."))]),
      note("No AI stock index exists before the last few years; each proxy is the index that held that cycle's leading technology companies. Survivorship applies: the Nasdaq-100 is reshuffled each year to its biggest winners."));
    return [head, P, bars, T, W].filter(Boolean);
  },
};
window.TOPIC = { VIEWS, presets: [["1m", "1M", 30], ["3m", "3M", 91], ["6m", "6M", 182], ["1y", "1Y", 365], ["5y", "5Y", 1826], ["all", "All", 0]] };
})();
