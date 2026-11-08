// AI Model Iteration: tabs and cards. Data from /api/ai-models/<overview|iteration|compute|utility|sanctions|cost>; helpers from topic.html.
// Epoch AI's data (compute, hardware, cost estimates) is CC-BY and credited on each card that uses it.
(() => {
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const yr = ts => new Date(ts * 1000).getUTCFullYear();
const ym = ts => new Date(ts * 1000).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
const flop = v => v == null ? "–" : Number(v).toExponential(1).replace("e+", "e") + " FLOP";
const perM = (v, d) => v == null ? "–" : "$" + num(v, d == null ? (v < 1 ? 2 : v < 10 ? 2 : 0) : d);
const musd = v => v == null ? "–" : v >= 1000 ? "$" + num(v / 1000, 1) + "bn" : "$" + num(v, v < 10 ? 1 : 0) + "m";
const share = v => v == null ? "–" : (v * 100).toFixed(0) + "%";
const days = v => v == null ? "–" : num(v, 0) + " days";
const months = v => v == null ? "–" : num(v, 1) + " months";
const tokens = v => v == null ? "–" : v >= 1e6 ? num(v / 1e6, 2) + "M" : num(v / 1e3, 0) + "k";
// one colour per family, the same on every tab; the six shell series colours then four fixed ones that read in light and dark
const EXTRA = ["#b5651d", "#2e8b57", "#7a6ff0", "#8f8e88"];
let FAMS = [];
const colOf = fam => { const i = FAMS.indexOf(fam); return i < 0 ? css("--hold") : i < SERIES.length ? css(SERIES[i]) : EXTRA[(i - SERIES.length) % EXTRA.length]; };
const setFams = fams => { FAMS = (fams || []).map(f => f.family || f); };
const lines = (obj, o = {}) => Object.entries(obj || {}).filter(([, p]) => p && p.length).map(([k, pts]) => ({ name: k, points: pts, color: colOf(k), ...o }));
const ask = (shows, q5, q10, q20) => note(el("span", {}, shows, el("br"), el("b", {}, "5 years: "), q5, " ", el("b", {}, "10 years: "), q10, " ", el("b", {}, "20 years: "), q20));
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");
const epochCredit = () => el("div", { class: "src", style: "margin-top:6px" }, "Data: ", link("Epoch AI, Notable AI Models", "https://epoch.ai/data/notable-ai-models"), " (CC-BY 4.0), through the Compute dashboard.");
const unavailable = (title, d, key) => card(title, el("div", { class: "muted" }, "Not available right now (" + ((d && d[key + "_error"]) || "no data") + ")."));
const verifyNote = (n, file) => n ? note(n + " row" + (n > 1 ? "s" : "") + " in data/ai-models/" + file + " marked verify: entered from memory or a secondary summary and still to be checked against the cited page.") : null;
const last = p => p && p.length ? p[p.length - 1] : null;
const openPill = o => el("span", { class: "pill" + (o ? " ok" : "") }, o ? "open" : "closed");

// ---- a scatter of dots against a date or numeric x (SVG): groups [{name, color, points: [[x, y, label, sub?]]}], o.lines step lines on top,
// o.vlines [{x, label}] dashed verticals (export-control dates), o.log, o.xFmt, o.yFmt, o.h. Hover or tap reads the nearest dot. CSV: one row per dot.
function svgDots(groups, o = {}) {
  const fx = o.xFmt || (v => v), fy = o.yFmt || (v => v), hidden = new Set();
  const read = el("div", { class: "muted", style: "min-height:18px" }, o.note || "Hover or tap a dot.");
  groups.forEach((g, i) => { g.color = g.color || css(SERIES[i % SERIES.length]); });
  let redraw = () => {};
  const legend = el("div", { class: "legend" }, ...groups.filter(g => g.points && g.points.length).map((g, i) => el("button", { onclick: e => { e.currentTarget.classList.toggle("off") ? hidden.add(g.name) : hidden.delete(g.name); redraw(); } },
    el("span", { class: "sw", style: "background:" + g.color + ";border-radius:50%" }), g.name)), ...(o.lines || []).map(l => swatch(l.color, l.name)));
  if (o.csv !== false) legend.append(csvButton(csvName(o.name || "dots"), () => csvText([o.xName || "x", "series", o.yName || "y", "label"],
    groups.flatMap(g => g.points.map(p => [fx(p[0]), g.name, p[1], p[2] || ""])))));
  const box = svgBox(o.h || 300, (host, W, H) => { redraw = () => { host.replaceChildren(); paint(host, W, H); }; paint(host, W, H); });
  function paint(host, W, H) {
    const pad = { l: 6, r: 62, t: 12, b: 22 };
    const vis = groups.filter(g => !hidden.has(g.name) && g.points && g.points.length);
    const good = v => v != null && isFinite(v) && (!o.log || v > 0);
    const all = vis.flatMap(g => g.points).concat((o.lines || []).flatMap(l => l.points)).filter(p => good(p[1]));
    if (!all.length) return;
    const T = o.log ? Math.log10 : v => v, inv = o.log ? v => 10 ** v : v => v;
    const x0 = Math.min(...all.map(p => p[0]), ...(o.vlines || []).map(v => v.x)), x1 = Math.max(...all.map(p => p[0]), ...(o.vlines || []).map(v => v.x));
    let a = Math.min(...all.map(p => T(p[1]))), b = Math.max(...all.map(p => T(p[1])));
    const m = (b - a) * 0.06 || 1; a -= m; b += m;
    const X = x => pad.l + (x - x0) / (x1 - x0 || 1) * (W - pad.l - pad.r), Y = y => pad.t + (1 - (T(y) - a) / (b - a)) * (H - pad.t - pad.b);
    const svg = svgEl("svg", { width: W, height: H, style: "display:block" }, host);
    const text = (x, y, s, anchor = "start", col = "--muted") => { svgEl("text", { x, y, fill: css(col), "font-size": 11, "text-anchor": anchor }, svg).textContent = s; };
    for (const v of (o.log ? logTicks(inv(a), inv(b)).filter((tv, i, arr) => arr.length < 12 || String(tv)[0] === "1") : niceTicks(a, b, 4))) { const y = Y(v); if (y < pad.t || y > H - pad.b) continue; svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, stroke: css("--line") }, svg); text(W - pad.r + 6, y + 4, fy(v)); }
    for (const v of (o.xTicks || niceTicks(x0, x1, Math.max(3, Math.floor(W / 110))))) if (v >= x0 - (x1 - x0) * 0.01 && v <= x1 + (x1 - x0) * 0.01) text(Math.min(Math.max(X(v), pad.l + 14), W - pad.r - 14), H - 6, fx(v), "middle");
    for (const v of o.vlines || []) { svgEl("line", { x1: X(v.x), x2: X(v.x), y1: pad.t, y2: H - pad.b, stroke: v.color || css("--muted"), "stroke-dasharray": "3 3" }, svg); if (v.label) text(X(v.x) + 3, pad.t + 10 + (v.dy || 0), v.label, "start", "--muted"); }
    for (const l of o.lines || []) {
      const pts = l.points.filter(p => good(p[1]));
      let d = "";
      pts.forEach((p, i) => { d += (i ? "H" + X(p[0]).toFixed(1) + "V" + Y(p[1]).toFixed(1) : "M" + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)); });
      if (pts.length) d += "H" + X(x1).toFixed(1);
      svgEl("path", { d, fill: "none", stroke: l.color, "stroke-width": 1.5, "stroke-dasharray": l.dashed ? "5 4" : "none" }, svg);
    }
    const dots = [];
    for (const g of vis) for (const p of g.points) if (good(p[1])) { const cx = X(p[0]), cy = Y(p[1]); dots.push({ cx, cy, p, g }); svgEl("circle", { cx, cy, r: o.r || 4, fill: g.color, "fill-opacity": 0.75, stroke: css("--surface"), "stroke-width": 0.8 }, svg); }
    const ring = svgEl("circle", { r: (o.r || 4) + 3, fill: "none", stroke: css("--ink"), "stroke-width": 1.5, visibility: "hidden" }, svg);
    const hit = svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" }, svg);
    const move = e => { const r = svg.getBoundingClientRect(), px = (e.touches ? e.touches[0].clientX : e.clientX) - r.left, py = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
      let best = null, bd = Infinity; for (const d of dots) { const dd = (d.cx - px) ** 2 + (d.cy - py) ** 2; if (dd < bd) { bd = dd; best = d; } }
      if (!best || bd > 40 * 40) { ring.setAttribute("visibility", "hidden"); read.textContent = o.note || ""; return; }
      ring.setAttribute("cx", best.cx); ring.setAttribute("cy", best.cy); ring.setAttribute("visibility", "visible");
      read.textContent = (best.p[2] ? best.p[2] + " · " : "") + best.g.name + " · " + fx(best.p[0]) + " · " + fy(best.p[1]) + (best.p[3] ? " · " + best.p[3] : ""); };
    hit.addEventListener("mousemove", move); hit.addEventListener("touchstart", move, { passive: true }); hit.addEventListener("touchmove", move, { passive: true });
    hit.addEventListener("mouseleave", () => { ring.setAttribute("visibility", "hidden"); read.textContent = o.note || ""; });
  }
  return [legend, read, box];
}

// ---- the release timeline: one row per family, a dot per release (filled = flagship, small = other; a ring = open weights)
function svgStrip(rows, fams) {
  const read = el("div", { class: "muted", style: "min-height:18px" }, "Hover or tap a dot: filled dots are flagship releases, small dots mid-tier models, a ring means open weights.");
  const legend = el("div", { class: "legend" }, csvButton(csvName("releases"), () => csvText(["date", "family", "model", "open weights", "flagship"], rows.map(r => [isoTime(r.t), r.family, r.model, r.open ? "yes" : "no", r.flagship ? "yes" : "no"]))));
  const box = svgBox(Math.max(200, fams.length * 26 + 40), (host, W, H) => {
    const pad = { l: 78, r: 10, t: 8, b: 22 }, x0 = Math.min(...rows.map(r => r.t)), x1 = Math.max(...rows.map(r => r.t), Math.floor(Date.now() / 1000));
    const X = x => pad.l + (x - x0) / (x1 - x0 || 1) * (W - pad.l - pad.r), rowH = (H - pad.t - pad.b) / fams.length;
    const svg = svgEl("svg", { width: W, height: H, style: "display:block" }, host);
    const text = (x, y, s, anchor = "start") => { svgEl("text", { x, y, fill: css("--muted"), "font-size": 11, "text-anchor": anchor }, svg).textContent = s; };
    for (let y = new Date(x0 * 1000).getUTCFullYear() + 1; y <= new Date(x1 * 1000).getUTCFullYear(); y++) { const t = Date.UTC(y, 0, 1) / 1000, x = X(t); svgEl("line", { x1: x, x2: x, y1: pad.t, y2: H - pad.b, stroke: css("--line") }, svg); text(x, H - 6, String(y), "middle"); }
    fams.forEach((f, i) => { const y = pad.t + (i + 0.5) * rowH; svgEl("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, stroke: css("--line"), "stroke-dasharray": "2 4" }, svg);
      svgEl("text", { x: pad.l - 8, y: y + 4, fill: colOf(f), "font-size": 11, "text-anchor": "end", "font-weight": 600 }, svg).textContent = f; });
    const dots = [];
    for (const r of rows) { const i = fams.indexOf(r.family); if (i < 0) continue; const cx = X(r.t), cy = pad.t + (i + 0.5) * rowH, rad = r.flagship ? 5.5 : 3;
      svgEl("circle", { cx, cy, r: rad, fill: r.open ? "none" : colOf(r.family), stroke: colOf(r.family), "stroke-width": r.open ? 2 : 0, "fill-opacity": 0.85 }, svg); dots.push({ cx, cy, r }); }
    const ring = svgEl("circle", { r: 9, fill: "none", stroke: css("--ink"), "stroke-width": 1.5, visibility: "hidden" }, svg);
    const hit = svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" }, svg);
    const move = e => { const b = svg.getBoundingClientRect(), px = (e.touches ? e.touches[0].clientX : e.clientX) - b.left, py = (e.touches ? e.touches[0].clientY : e.clientY) - b.top;
      let best = null, bd = Infinity; for (const d of dots) { const dd = (d.cx - px) ** 2 + (d.cy - py) ** 2; if (dd < bd) { bd = dd; best = d; } }
      if (!best || bd > 30 * 30) { ring.setAttribute("visibility", "hidden"); return; }
      ring.setAttribute("cx", best.cx); ring.setAttribute("cy", best.cy); ring.setAttribute("visibility", "visible");
      read.textContent = best.r.model + " · " + best.r.family + " · " + dayOf(best.r.t) + (best.r.open ? " · open weights" : "") + (best.r.flagship ? " · flagship" : "") + (best.r.context ? " · " + tokens(best.r.context) + " context" : ""); };
    hit.addEventListener("mousemove", move); hit.addEventListener("touchstart", move, { passive: true }); hit.addEventListener("touchmove", move, { passive: true });
  });
  return [legend, read, box];
}

const famDots = (models, key, label, o = {}) => svgDots(FAMS.concat(["Other"]).map(f => ({ name: f, color: f === "Other" ? css("--hold") : colOf(f),
  points: models.filter(m => (m.family || "Other") === f).map(m => [m.t, m[key], m.model, (o.sub ? o.sub(m) : m.org)]) })).filter(g => g.points.length),
  { xFmt: ym, xName: "date", yName: label, log: true, h: 320, ...o });

const VIEWS = {
  async overview() {
    const d = await api("overview"), K = d.kpi || {}, S = d.series || {};
    setFams(d.families);
    const recordAt = t => { const r = S.record || []; if (!r.length) return null; const at = t == null ? Math.floor(Date.now() / 1000) : t; const past = r.filter(p => p[0] <= at); return past.length ? (at - past[past.length - 1][0]) / 86400 / 30.44 : null; };
    const head = card("How fast are the top models iterating, and what do they cost?",
      datedHead([
        { label: () => "Top Arena score" + (K.frontier_model ? " · " + K.frontier_model : ""), value: t => [num(valueAt(S.frontier_score, t)), ""] },
        { label: () => "Months since the last frontier compute record (Epoch)", value: t => { const m = recordAt(t); return [m == null ? "–" : num(m, 1), m == null ? "" : m > 12 ? "down" : ""]; } },
        { label: () => "Cheapest model within 50 points of the top, $ per M output tokens" + (K.frontier_price_model ? " · " + K.frontier_price_model : ""), value: t => [perM(valueAt(S.frontier_price, t)), ""] },
        { label: () => "Chinese share of the Arena top 20" + (K.n_top20 ? " (" + K.china_top20 + " of " + K.n_top20 + " entered)" : ""), value: t => [share(valueAt(S.china_share, t)), ""] },
        { label: () => "Best open-weights model, points behind the top" + (K.best_open ? " · " + K.best_open : ""), value: t => { const v = valueAt(S.open_gap, t); return [v == null ? "–" : num(v) + " pts", ""]; } },
        { label: () => "Median days between a family's releases, last 12 months", value: () => [days(K.cadence_12m), ""] }],
        { latest: "Latest figures" }),
      el("p", { class: "muted", style: "margin:8px 0 0;font-size:13.5px;color:var(--ink2)" }, el("b", {}, "Where we are: "),
        (K.frontier_model ? K.frontier_model + " leads the Arena at " + num(K.frontier_score) + (K.arena_date ? " (" + dateOf(K.arena_date) + ")" : "") + ". " : "") +
        (K.largest ? "The largest training run Epoch knows is " + K.largest.model + " at " + flop(K.largest.flop) + ", " + (K.record_age_months == null ? "" : num(K.record_age_months, 1) + " months without a new record. ") : "") +
        (K.frontier_price != null ? "Frontier-tier intelligence costs from " + perM(K.frontier_price) + " per million output tokens (" + K.frontier_price_model + "). " : "") +
        (K.china_share != null ? "Chinese labs hold " + share(K.china_share) + " of the top-20 rows entered" + (K.best_open ? ", and the best open-weights model (" + K.best_open + ") sits " + num(K.open_gap) + " points behind the top. " : ". ") : "") +
        (K.flagship_12m ? K.flagship_12m + " flagship releases across the families in the last 12 months." : "")),
      ...Object.keys(d.errors || {}).map(k => missing({ [k + "_error"]: d.errors[k] }, k, "The " + k + " tab")), asOf(d), stale(d));
    const rec = S.record && S.record.length ? card("Largest training run to date (Epoch AI, log scale)", ...linesChart([{ name: "Largest run so far", points: S.record, color: css("--s1") }], flop, { log: true }),
      ask("Each step is a new largest training run by compute. Hover it (or any chart here) to read the top card on that date.", "does a 1e28 FLOP run happen, and who trains it?", "does compute growth slow as power and chips bind (Compute dashboard)?", "does compute stop deciding who leads?"), epochCredit()) : null;
    const arena = S.frontier_score && S.frontier_score.length ? card("Top Arena score and the cheapest frontier-tier price, by snapshot",
      ...linesChart([{ name: "Top Arena score", points: S.frontier_score, color: css("--s2") }, { name: "Cheapest price within 50 pts, $/M output (left)", points: S.frontier_price, axis: "left", color: css("--s3"), fmt: perM }], v => num(v), { small: true, leftLog: true }),
      ask("Hand-entered leaderboard snapshots (Utility tab); LMArena rescales scores, so read the gap and the trend. The price is the cheapest list price among models within 50 points of the top at each snapshot.",
        "does frontier-tier intelligence keep halving in price each year?", "does a Chinese or open model take first place?", "do leaderboards still separate the best models?")) : null;
    const tl = d.timeline && d.timeline.length ? card("Release timeline, by family", ...svgStrip(d.timeline, FAMS),
      ask("Major releases since ChatGPT (data/ai-models/releases.csv): filled dots are flagships, small dots mid-tier models, rings open weights.",
        "does the gap between flagship generations shrink below six months for every family?", "which families are still here?", "is model iteration still the unit of progress?")) : null;
    return [head, rec, arena, tl];
  },

  async iteration() {
    const d = await api("iteration"), G = d.gaps || {};
    setFams(d.families);
    const thisYear = last(d.open_share);
    const head = card(null, el("div", { class: "kpis" }, kpi("Families tracked", FAMS.length), kpi("Releases entered", num(d.n)), kpi("Flagship releases, last 12 months", num(d.flagship_12m)),
      kpi("Median days between a family's releases, last 12 months", days(d.cadence_12m), d.cadence_12m != null && d.cadence_12m < 60 ? "up" : ""),
      kpi("Open-weights share" + (thisYear ? ", " + thisYear[0] : ""), share(thisYear && thisYear[1]))), asOf(d), stale(d));
    const per = card("Major releases per family per year", ...svgBars(d.years.map(String), FAMS.map(f => ({ name: f, values: d.per_year[f] || [], color: colOf(f) })), { yFmt: v => Math.round(v), h: 260 }),
      ask("Rows of releases.csv by the year of release; the current year is partial.", "does every family settle at a release a quarter?", "do the Chinese labs keep out-releasing the US labs?", "do families consolidate to three or four?"));
    const gapLines = FAMS.map(f => ({ name: f, points: (G[f] || {}).gaps || [], color: colOf(f) })).filter(s => s.points.length >= 2);
    const gaps = card("Days since the family's previous release, at each release", ...linesChart(gapLines, days, { small: true }),
      ask("Each point is a release, dated on the day it came out; its value is the days since that family's previous release in the file. Lower is faster iteration.",
        "does the median gap for the leaders fall under 60 days?", "do gaps lengthen as training runs take longer?", "does iteration speed still matter?"));
    const gt = card("Cadence by family", table(["Family", "Releases", "Median gap, all", "Median gap, last 12 months", "Last release", "Days since"],
      FAMS.map(f => { const g = G[f] || {}; return el("tr", {}, el("td", { style: "color:" + colOf(f) + ";font-weight:600" }, f), el("td", {}, num(g.n)), el("td", {}, days(g.median_days)), el("td", {}, days(g.median_12m)), el("td", {}, g.last ? dateOf(g.last) : "–"), el("td", {}, g.days_since == null ? "–" : num(g.days_since))); })));
    const ob = d.open_by_country || {};
    const open = card("Open-weights share of major releases", ...svgBars(d.open_share.map(p => String(p[0])), [{ name: "All families", values: d.open_share.map(p => p[1]), color: css("--s1") },
      ...["US", "China"].filter(c => ob[c] && ob[c].length).map((c, i) => ({ name: c, values: d.open_share.map(p => { const q = ob[c].find(x => x[0] === p[0]); return q ? q[1] : null; }), color: css(["--s3", "--s2"][i]) }))], { yFmt: v => Math.round(v * 100) + "%", h: 220 }),
      ask("Releases whose weights anyone can download, as a share of the year's releases, for all families and for the US and Chinese labs.", "do US labs keep closing while Chinese labs open?", "does Meta's turn to closed Muse models hold?", "does open or closed win the platform?"));
    const ctx = card("Context window at release (tokens, log scale)", ...linesChart(lines(d.context), tokens, { log: true, small: true }),
      ask("The context window each release advertised.", "does 1M tokens become the floor?", "does context stop being a differentiator?", "are context windows still a thing?"));
    const rows = card("Releases entered", table(["Date", "Family", "Model", "Developer", "Weights", "Context", "Modalities", "Source"],
      (d.rows || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", { style: "color:" + colOf(r.family) + ";font-weight:600" }, r.family), el("td", {}, r.model + (r.flagship === "yes" ? " ★" : "")), el("td", {}, r.developer), el("td", {}, openPill(r.open === "yes")), el("td", {}, r.context ? tokens(+r.context) : "–"), el("td", {}, r.modalities), srcCell(r)))),
      note("★ flagship. Kept in data/ai-models/releases.csv; add a row per major release."), verifyNote(d.n_verify, "releases.csv"), cite(d.cited));
    return [head, per, el("div", { class: "grid2" }, gaps, open), gt, ctx, rows];
  },

  async compute() {
    const d = await api("compute"), E = d.epoch;
    setFams(d.families);
    if (!E) return [unavailable("Training compute (Epoch AI)", d, "epoch"), stale(d)];
    const L = E.largest || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("Largest training run", flop(L.flop)), kpi("Its model", L.model || "–"), kpi("Last new record", E.last_record ? dateOf(E.last_record) : "–"),
      kpi("Months since", months(E.record_age_months), E.record_age_months > 12 ? "down" : ""), kpi("Models at 1e22 FLOP or more", num((E.models || []).length)), kpi("Models in Epoch's file", num(E.n))), asOf(d), stale(d), epochCredit());
    const dots = card("Training compute per model, coloured by family (log scale)", ...famDots(E.models || [], "flop", "training compute (FLOP)", { yFmt: flop, lines: [{ name: "Largest run so far", color: css("--muted"), points: E.record || [] }], sub: m => m.org + (m.open ? " · open weights" : "") }),
      ask("Every model Epoch lists with at least 1e22 FLOP of training compute since 2017, by publication date; the grey step is the record. Other = organisations outside the ten families.",
        "does any family fall two orders of magnitude behind the record and stay there?", "does the record keep growing about 4-5x a year?", "does compute per model stop growing as inference compute takes over?"));
    const fam = card("Largest run so far, per family (log scale)", ...linesChart(lines(E.family_max), flop, { log: true }),
      ask("Each family's running maximum of training compute, from Epoch's organisation field. Steps are generations.", "do the Chinese families' steps keep pace under chip controls?", "do the steps get further apart?", "is compute per generation still the measure?"));
    const bc = E.by_country || {};
    const cn = bc.US && bc.China ? card("Largest training run so far: US vs China (log scale)", ...linesChart([{ name: "US", points: bc.US, color: css("--s1") }, { name: "China", points: bc.China, color: css("--s2") }], flop, { log: true, small: true }),
      ask("Single-country models only (china_us_tech's parser). The vertical gap is the compute gap; one order of magnitude is ten times the compute. The Sanctions tab sets it against the rule dates.",
        "does the gap stay at one to two orders of magnitude?", "does China close it with domestic accelerators?", "does efficiency (DeepSeek) make the gap moot?")) : null;
    const hw = (E.hardware || []).length ? card("Hardware behind the largest runs, where Epoch knows it", table(["Model", "Organisation", "Published", "Hardware", "Chips", "Compute"],
      E.hardware.map(r => el("tr", {}, el("td", {}, r.model), el("td", {}, r.org), el("td", {}, dateOf(r.date)), el("td", { class: "wrap" }, r.hardware || "–"), el("td", {}, num(r.hw_qty)), el("td", {}, flop(r.flop))))),
      note("Epoch's training hardware and hardware quantity fields; most frontier labs do not disclose them.")) : null;
    return [head, dots, fam, cn, hw];
  },

  async utility() {
    const d = await api("utility"), A = d.arena || {}, st = (A.stats || {})[A.latest_date] || {}, I = d.index || {}, Bm = d.benchmarks || {}, O = d.openrouter || {};
    setFams(d.families);
    const head = card(null, el("div", { class: "kpis" }, kpi("Top of the Arena" + (A.latest_date ? ", " + dateOf(A.latest_date) : ""), st.top_model ? st.top_model + " · " + num(st.top) : "–"),
      kpi("Best open-weights model", st.best_open ? st.best_open + " · " + num(st.open_gap) + " pts behind" : "–"), kpi("Chinese share of the top 20 (" + (st.china_top20 || 0) + " of " + (st.n_top20 || 0) + " entered)", share(st.china_share)),
      ...Object.entries(Bm.best || {}).map(([b, v]) => kpi("Best " + b, v.model + " · " + num(v.value, 1) + "%"))), asOf(d), stale(d));
    const top = card("LMArena text leaderboard, latest snapshot entered" + (A.latest_date ? " (" + dateOf(A.latest_date) + ")" : ""), table(["Rank", "Model", "Family", "Developer", "Country", "Score", "Weights", "Source"],
      (A.latest || []).map(r => el("tr", {}, el("td", {}, r.rank || "–"), el("td", {}, r.model), el("td", { style: "color:" + colOf(r.family) + ";font-weight:600" }, r.family), el("td", {}, r.developer), el("td", {}, r.country), el("td", {}, num(r.score)), el("td", {}, openPill(r.open)), srcCell(r)))),
      note("Only rows whose score a source gave are entered, so the top 20 can be partial; add the full 20 each week to data/ai-models/arena.csv."), verifyNote(A.n_verify, "arena.csv"), cite(A.cited));
    const traj = card("Best Arena score per family, by snapshot", ...linesChart(lines(A.by_family), v => num(v), { small: true, sync: false }),
      ask("The highest-scoring model of each family at each hand-entered snapshot. LMArena rescales scores, so compare families within a snapshot and read trends loosely.",
        "does any family other than Google and Anthropic take the top?", "do open families (Kimi, DeepSeek, Qwen) catch the closed ones?", "does the Arena still measure anything?"));
    const uc = (A.us_cn || []).length ? card("Best US vs best Chinese model (china-us-tech's dated copies)", ...linesChart(["US best", "China best"].map((s, i) => ({ name: s, points: A.us_cn.filter(r => r.series === s).map(r => [Date.parse(r.date) / 1000, +r.value]), color: css(["--s1", "--s2"][i]) })), v => num(v), { small: true, sync: false }),
      note("Shared with the China vs US Tech dashboard (data/china-us-tech/leaderboard.csv).")) : null;
    const idx = (I.rows || []).length ? card("Artificial Analysis Intelligence Index (hand-entered points)", ...linesChart(lines(I.by_family), v => num(v), { small: true, sync: false }),
      table(["Date", "Model", "Family", "Index", "Version", "Weights", "Source"], I.rows.map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.model), el("td", { style: "color:" + colOf(r.family) }, r.family), el("td", {}, num(+r.value, 1)), el("td", {}, r.version), el("td", {}, openPill(r.open === "yes")), srcCell(r)))),
      note("Index versions are not comparable with each other (v5 rebuilt the mix in 2026). The API answers with a free key: see the README's Gaps.")) : null;
    const names = Bm.names || [];
    const bench = (Bm.rows || []).length ? card("Benchmarks: GPQA Diamond, SWE-bench Verified, FrontierMath (%)", table(["Model", "Family", "Latest", ...names],
      Bm.rows.map(r => el("tr", {}, el("td", {}, r.model), el("td", { style: "color:" + colOf(r.family) }, r.family), el("td", {}, dateOf(r.date)), ...names.map(b => el("td", {}, r.scores[b] == null ? "–" : num(r.scores[b], 1)))))),
      ask("Lab-reported or Epoch-run scores as cited per row in data/ai-models/benchmarks.csv; every row is marked verify until checked. Benchmarks saturate and get gamed: GPQA is near its ceiling, SWE-bench scaffolds differ, FrontierMath tiers differ.",
        "does SWE-bench Verified saturate above 85%?", "which benchmark replaces these?", "do benchmarks matter once models exceed expert level?")) : null;
    const orr = (O.latest || []).length ? card("OpenRouter: most tokens processed in the week to " + dateOf(O.weeks[O.weeks.length - 1]), ...svgBars(O.latest.map(r => r.model), [{ name: "Trillion tokens", values: O.latest.map(r => +r.tokens_t), colorFn: (v, i) => colOf(O.latest[i].family) }], { yFmt: v => num(v, 0) + "T", labelW: 120, h: 220 }),
      O.china_share && O.china_share.length ? el("div", { class: "muted", style: "margin-top:6px" }, "Chinese developers' share of the rows entered: " + O.china_share.map(p => ym(p[0]) + " " + share(p[1])).join(", ") + ".") : null,
      ask("OpenRouter's public rankings by tokens processed, hand-entered weekly (data/ai-models/openrouter_share.csv). A usage proxy for one marketplace of API traffic, skewed to cheap open models.",
        "do Chinese open models keep most of the routed tokens?", "does usage concentrate in two or three models?", "does the API marketplace still exist?")) : null;
    const wiki = d.wiki ? card("Attention: monthly English Wikipedia pageviews of each family's article (log scale)", ...linesChart(lines(d.wiki), v => big(v), { log: true }),
      ask("Wikimedia pageviews per article (users, all access), monthly since November 2022; the article per family is in families.csv. Chatbots and companies are read about more than model names.",
        "does attention follow releases or leaderboards?", "which family holds the public's attention?", "does anyone look models up any more?")) : unavailable("Wikipedia pageviews", d, "wiki");
    return [head, top, el("div", { class: "grid2" }, traj, uc), idx, bench, orr, wiki];
  },

  async sanctions() {
    const d = await api("sanctions"), bc = d.by_country || {}, ls = d.last_step;
    const g = last(d.gap_oom);
    const head = card(null, el("div", { class: "kpis" }, kpi("Export-control steps", num(d.n_steps)), kpi("Latest step", ls ? dateOf(ls.date) + " · " + ls.actor : "–"),
      kpi("US over China, largest training run (orders of magnitude)", g ? num(g[1], 1) : "–"), kpi("Chinese labs' hardware rows", num((d.hardware || []).length))), asOf(d), stale(d));
    const rules = (d.rule_dates || []).map((r, i) => ({ x: r.t, label: r.label, dy: (i % 4) * 12, color: r.direction > 0 ? css("--up") : css("--down") }));
    const fr = bc.US && bc.China ? card("Largest training run so far, US vs China, against the US export-control dates (log scale)",
      ...svgDots([], { lines: [{ name: "US", color: css("--s1"), points: bc.US }, { name: "China", color: css("--s2"), points: bc.China }], vlines: rules, xFmt: ym, yFmt: flop, log: true, h: 320, csv: false, note: "Red dashed lines: a tightening; green: an easing (US steps only)." }),
      el("div", { class: "legend" }, csvButton(csvName("us-vs-china-frontier"), () => seriesCsv([{ name: "US", points: bc.US }, { name: "China", points: bc.China }], "date", isoTime))),
      ask("Epoch's largest training run to date by developer country (single-country models), with each US rule's effective date. The October 2022 and October 2023 rules cut off A100/H100 then A800/H800; the 2025-26 steps licensed H20 and then H200-class chips back.",
        "does China's frontier keep growing about as fast as the US's despite the rules?", "does the gap close with domestic chips (Huawei Ascend), or widen?", "do chips stay the lever, or does it move to data and energy?"), epochCredit()) : unavailable("US vs China frontier", d, "by_country");
    const ctl = card("Export-control timeline and the chips each step covers", table(["Effective", "Who", "What", "Chips covered", "Status", "Source"],
      (d.controls || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.actor), el("td", { class: "wrap" }, r.event), el("td", { class: "wrap" }, r.chips || "–"), el("td", { class: "wrap" }, r.status || "–"), srcCell(r)))),
      note("The timeline is the China vs US Tech dashboard's (data/china-us-tech/controls.csv); the chips and status columns are data/ai-models/chips_covered.csv, joined by date. Dates are effective dates."));
    const hw = card("What each Chinese lab reports training on (two US rows for scale)", table(["Date", "Lab", "Model", "Hardware", "Chips", "GPU-hours", "Source"],
      (d.hardware || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.lab + " (" + r.country + ")"), el("td", {}, r.model), el("td", { class: "wrap" }, r.hardware), el("td", {}, r.count ? num(+r.count) : "–"), el("td", {}, r.gpu_hours ? num(+r.gpu_hours) : "–"), srcCell(r)))),
      ask("Disclosures in technical reports and interviews; most labs do not disclose. DeepSeek-V3's 2,048 H800s were export-compliant Hopper chips bought before October 2023.",
        "does a Chinese frontier model train entirely on domestic chips?", "do the labs disclose less as controls tighten?", "does the hardware still matter?"));
    return [head, fr, ctl, hw];
  },

  async cost() {
    const d = await api("cost"), E = d.epoch_cost, fp = (d.frontier_price || []).filter(x => x.price != null), now = last(fp), cap = d.capex;
    setFams(d.families);
    const head = card(null, el("div", { class: "kpis" }, kpi("Cheapest model within " + d.near_top + " Arena points of the top, $/M output" + (now ? " · " + now.model : ""), now ? perM(now.price) : "–"),
      kpi("Hyperscaler capex, last 4 quarters", cap && cap.ttm != null ? "$" + num(cap.ttm, 0) + "bn" : "–"), kpi("Models with an Epoch cost estimate", num(E ? E.n : null)),
      kpi("Current models priced on OpenRouter", d.current ? num(d.current.length) : "–"), kpi("Days in the price log", num(d.log_days))),
      d.current_error ? el("div", { class: "warn", style: "margin-top:6px" }, "OpenRouter is not reachable right now (" + d.current_error + "): deployment prices are the hand-entered launch list.") : null, asOf(d), stale(d));
    const tc = E ? card("Estimated training cost per model (Epoch AI, 2023 USD, log scale)", ...famDots(E.models, "cost", "training cost (USD)", { yFmt: v => musd(v / 1e6), sub: m => m.org + " · " + flop(m.flop) }),
      ask("Epoch's estimate of the amortised hardware and energy cost of the final training run, where it has one; its 'cost of frontier training runs' work puts the uncertainty at about a factor of two to three.",
        "does a $10bn training run happen?", "does the cost of the frontier run keep growing 2-3x a year?", "does training cost stop being the barrier to entry?"), epochCredit()) : unavailable("Training cost (Epoch AI)", d, "epoch_cost");
    const pe = E ? card("Training cost per exaFLOP of compute (log scale)", ...famDots(E.models, "per_eflop", "USD per 1e18 FLOP", { yFmt: v => "$" + num(v, v < 10 ? 2 : 0), h: 260 }),
      ask("The same estimates divided by training compute: what a unit of compute cost each lab, falling with hardware generations and utilisation.", "does the cost per exaFLOP fall tenfold?", "do Chinese labs pay more per FLOP under controls?", "is compute a commodity?")) : null;
    const disc = card("Disclosed, reported and estimated training costs (USD million)", table(["Date", "Model", "Family", "Cost", "Basis", "Source"],
      (d.disclosed || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", {}, r.model), el("td", { style: "color:" + colOf(r.family) }, r.family), el("td", {}, musd(+r.value)), el("td", {}, el("span", { class: "pill" }, r.basis)), srcCell(r)))),
      note("Each figure counts different things (see the Method tab): DeepSeek-V3's is the final run at a rental rate; Llama 3.1's is derived from disclosed GPU-hours; the AI Index's are estimates."));
    const lp = card("List price per million output tokens at launch, by family (log scale)", ...linesChart(lines(d.launch_by_family), perM, { log: true }),
      ask("Hand-entered launch prices of each family's releases (data/ai-models/prices.csv): the price of each new model on its launch day, so a family's line falls when it ships a cheaper model and jumps when it ships a pricier tier.",
        "does the price of frontier-tier output keep halving each year?", "do prices converge on the open-weights floor?", "is a token still what you pay for?"));
    const cur = d.current && d.current.length ? card("Current list prices on OpenRouter (USD per million tokens)", table(["Model", "Family", "Input", "Output", "Context", "Listed"],
      d.current.slice().sort((a, b) => b.output - a.output).map(m => el("tr", {}, el("td", {}, m.name), el("td", { style: "color:" + colOf(m.family) }, m.family), el("td", {}, perM(m.input)), el("td", {}, perM(m.output)), el("td", {}, m.context ? tokens(m.context) : "–"), el("td", {}, m.created ? dayOf(m.created) : "–")))),
      note("OpenRouter's public models API, fetched daily; each day's prices are appended to a log on the server's volume so a price history accrues (the chart below fills in as the log grows).")) : null;
    const logc = d.price_log && Object.keys(d.price_log).length ? card("Price log: output price per model, day by day", ...linesChart(Object.entries(d.price_log).map(([k, pts]) => ({ name: k, points: pts })), perM, { small: true, log: true }), note("From the daily log; two or more days needed per model.")) : null;
    const pp = (d.per_point || []).length ? card("Price per Arena point: $ per million output tokens per 100 points, latest snapshot", ...svgBars(d.per_point.map(x => x.model), [{ name: "$ per M output per 100 pts", values: d.per_point.map(x => x.per_point * 100), colorFn: (v, i) => colOf(d.per_point[i].family) }], { yFmt: v => "$" + num(v, 2), labelW: 110, h: 240 }),
      table(["Model", "Family", "Score", "Output $/M", "$ per 100 points", "Price from"], d.per_point.map(x => el("tr", {}, el("td", {}, x.model), el("td", { style: "color:" + colOf(x.family) }, x.family), el("td", {}, num(x.score)), el("td", {}, perM(x.output)), el("td", {}, "$" + num(x.per_point * 100, 2)), el("td", {}, x.source)))),
      ask("Output price divided by Arena score, for the models in the latest snapshot that have a price (OpenRouter's current list, else the launch list).", "does the cheapest frontier-tier point come from an open model?", "does price per point fall tenfold?", "is intelligence priced per token at all?")) : null;
    // the calculator: tokens a month in and out, pick a model, see the bill; computed here, nothing stored
    const models = d.calculator || [];
    const v = { inp: 50, out: 10, i: Math.max(0, models.findIndex(m => /opus 5\.5/i.test(m.model))) };
    const sel = el("select", { style: "width:100%;box-sizing:border-box;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit", onchange: e => { v.i = +e.target.value; compute(); } },
      ...models.map((m, i) => el("option", { value: i }, m.family + " · " + m.model + " · " + perM(m.input) + " in / " + perM(m.output) + " out" + (m.source === "openrouter" ? " (current)" : " (launch)"))));
    sel.value = String(v.i);
    const field = (label, key, step) => el("label", { style: "display:block" }, el("div", { class: "muted" }, label), el("input", { type: "number", min: 0, step, value: v[key], style: "width:100%;box-sizing:border-box;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit",
      oninput: e => { const x = parseFloat(e.target.value); if (!isNaN(x) && x >= 0) { v[key] = x; compute(); } } }));
    const out = el("div", { class: "kpis", style: "margin-top:10px" }), cmp = el("div", { class: "muted", style: "margin-top:8px" });
    const compute = () => {
      const m = models[v.i]; if (!m) return;
      const bill = v.inp * m.input + v.out * m.output;
      out.replaceChildren(kpi("Monthly bill", "$" + num(bill, bill < 100 ? 2 : 0)), kpi("of which input", "$" + num(v.inp * m.input, 2)), kpi("of which output", "$" + num(v.out * m.output, 2)), kpi("Per 1,000 requests of 1k in / 200 out", "$" + num((m.input + 0.2 * m.output) / 1000 * 1000, 3)));
      const cheaper = models.map(x => ({ x, b: v.inp * x.input + v.out * x.output })).filter(o => o.b < bill && o.x.source === "openrouter").sort((a, b) => a.b - b.b).slice(0, 3);
      cmp.textContent = cheaper.length ? "Cheaper current models for the same tokens: " + cheaper.map(o => o.x.model + " $" + num(o.b, 0)).join(", ") + "." : "No cheaper current model in the list for these tokens.";
    };
    compute();
    const calc = card("Calculator: what would a month cost?", el("div", { class: "grid2" }, field("Input tokens a month (million)", "inp", 1), field("Output tokens a month (million)", "out", 1), el("label", { style: "display:block" }, el("div", { class: "muted" }, "Model"), sel)), out, cmp,
      note("List prices only (standard tier, no caching, batch or long-context rates); computed in your browser, nothing is sent or stored."));
    return [head, tc, pe, disc, lp, cur, logc, pp, calc];
  },
};
window.TOPIC = { VIEWS };
})();
