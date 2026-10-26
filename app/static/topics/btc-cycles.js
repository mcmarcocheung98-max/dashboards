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

// ---------- sector rotation: the four cycles' bursts on one timeline, and each 2026-27 candidate sector's status today
const FAMILY = { defi: ["On-chain finance / DeFi", "--s1"], stable: ["Stablecoins & payments", "--s2"], rwa: ["RWA", "--s3"], ai: ["AI", "--s4"],
  l1: ["L1s / platforms", "--s5"], privacy: ["Privacy", "--s6"], btcfi: ["BTC-fi / BTC alternatives", "--hold"], meme: ["Memecoins", "--z2"], other: ["Other (NFTs, enterprise, treasuries)", "--z4"], prediction: ["Prediction markets", "--accent"] };
function rotationTimeline(R) {
  let mode = (() => { try { return sessionStorage.getItem("rotation-view") || "halving"; } catch (e) { return "halving"; } })();
  const rows = R.rotation || [], read = el("div", { class: "muted", style: "min-height:18px;margin-top:4px" }, "Hover a bar for its sector and dates.");
  const seg = el("div", { class: "seg" });
  const host = el("div", {});
  const draw = () => {
    seg.replaceChildren(...[["halving", "Months from each halving"], ["calendar", "Calendar"]].map(([k, l]) => el("button", { class: k === mode ? "on" : "", onclick: () => { mode = k; try { sessionStorage.setItem("rotation-view", k); } catch (e) {} draw(); } }, l)));
    const lanes = [];                                    // one lane per burst, grouped by cycle; a cycle label row before each group
    for (const c of [1, 2, 3, 4]) { lanes.push({ head: c }); rows.filter(r => r.cycle === c).sort((a, b) => a.start - b.start).forEach(r => lanes.push({ r })); }
    if (mode === "halving") lanes.push({ head: 5 });
    const rowH = 15, H = lanes.length * rowH + 34;
    host.replaceChildren(svgBox(H, (box, W) => {
      const pad = { l: Math.min(230, W * 0.38), r: 12, t: 8, b: 24 };
      const [x0, x1] = mode === "halving" ? [-8, Math.max(26, (R.months_now || 0) + 2)] : [Date.UTC(2013, 5, 1) / 1000, Date.now() / 1000 + 60 * 86400];
      const X = v => pad.l + (v - x0) / (x1 - x0) * (W - pad.l - pad.r);
      const svg = svgEl("svg", { width: W, height: H, style: "display:block;font-family:inherit" }, box);
      const line = (x, color, dash, label, y0 = pad.t, y1 = H - pad.b) => {
        svgEl("line", { x1: x, x2: x, y1: y0, y2: y1, stroke: color, "stroke-dasharray": dash || "", "stroke-width": 1 }, svg);
        if (label) svgEl("text", { x: x + 3, y: pad.t + 9, fill: color, "font-size": 10.5 }, svg).textContent = label;
      };
      if (mode === "halving") {
        for (let m = W < 600 ? 0 : -6; m <= x1; m += W < 600 ? 12 : 6) { svgEl("line", { x1: X(m), x2: X(m), y1: pad.t, y2: H - pad.b, stroke: css("--line") }, svg);
          svgEl("text", { x: X(m), y: H - 6, fill: css("--muted"), "font-size": 10.5, "text-anchor": "middle" }, svg).textContent = (m > 0 ? "+" : "") + m + "m"; }
        line(X(0), css("--muted"), "4 3", "halving");
      } else {
        for (let y = 2014; y <= new Date().getUTCFullYear(); y++) { const t = Date.UTC(y, 0, 1) / 1000; svgEl("line", { x1: X(t), x2: X(t), y1: pad.t, y2: H - pad.b, stroke: css("--line") }, svg);
          if (y % 2 === 0 || W > 700) svgEl("text", { x: X(t), y: H - 6, fill: css("--muted"), "font-size": 10.5, "text-anchor": "middle" }, svg).textContent = "'" + String(y).slice(2); }
        (R.halvings || []).forEach(t => line(X(t), css("--muted"), "4 3"));
        Object.values(R.peaks || {}).forEach(t => line(X(t), css("--down"), "2 2"));
      }
      lanes.forEach((ln, i) => {
        const y = pad.t + i * rowH;
        if (ln.head) {
          const label = ln.head === 5 ? "Now (cycle 5)" : "Cycle " + ln.head + (ln.head === 4 ? " (2024 halving)" : ln.head === 3 ? " (2020)" : ln.head === 2 ? " (2016)" : " (2012)");
          svgEl("text", { x: 4, y: y + 11, fill: css("--ink2") || css("--muted"), "font-size": 11.5, "font-weight": 600 }, svg).textContent = label;
          if (mode === "halving" && ln.head < 5 && R.peak_months) {            // that cycle's BTC peak, on its own header row
            const xp = X(R.peak_months[ln.head]); svgEl("path", { d: `M${xp - 4},${y + 3} L${xp + 4},${y + 3} L${xp},${y + 11} Z`, fill: css("--down") }, svg);
          }
          if (ln.head === 5) {
            const xn = X(R.months_now); line(xn, css("--accent"), "", null, y, y + rowH);
            svgEl("text", { x: xn - 5, y: y + 11, fill: css("--accent"), "font-size": 11, "text-anchor": "end" }, svg).textContent = W < 600 ? "today +" + Math.round(R.months_now) + "m" : "today: " + Math.round(R.months_now) + " months after the 2024 halving, about " + Math.round(R.months_to_next) + " before the next";
          }
          return;
        }
        const r = ln.r, [nm, col] = FAMILY[r.family] || [r.family, "--muted"];
        const a = mode === "halving" ? r.m_start : r.start, b = mode === "halving" ? r.m_end : r.end;
        const xa = X(a), xb = Math.max(X(b), xa + 4);
        svgEl("text", { x: pad.l - 6, y: y + 11, fill: css("--muted"), "font-size": 11, "text-anchor": "end" }, svg).textContent = (n => r.sector.length > n ? r.sector.slice(0, n - 1) + "…" : r.sector)(Math.max(10, Math.floor((pad.l - 10) / 5.8)));
        const rect = svgEl("rect", { x: xa, y: y + 3, width: xb - xa, height: rowH - 5, rx: 2, fill: css(col) }, svg);
        const when = new Date(r.start * 1000).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }) + "–" + new Date(r.end * 1000).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
        const msg = "Cycle " + r.cycle + " · " + r.sector + " (" + nm + "): " + when + ", " + Math.round(r.m_start) + " to " + Math.round(r.m_end) + " months after the halving." + (r.note ? " " + r.note + "." : "") + " Source: " + r.source + ".";
        svgEl("title", {}, rect).textContent = msg;
        rect.addEventListener("mouseenter", () => { read.textContent = msg; });
      });
    }));
  };
  draw();
  const fams = [...new Set(rows.map(r => r.family))];
  const legend = el("div", { class: "legend" }, ...fams.map(f => el("button", {}, el("span", { class: "sw", style: "background:" + css((FAMILY[f] || [0, "--muted"])[1]) }), (FAMILY[f] || [f])[0])),
    el("button", {}, el("span", { class: "sw", style: "background:" + css("--down") }), "BTC peak"));
  return card("Sector rotation across the four cycles", seg, legend, host, read,
    note("Each bar is the window in which that sector led, from the doc's burst windows (cycles 3-4) and the dates in its text (cycles 1-2, approximate; rows marked verify in data/btc-cycles/rotation.csv). " +
      "On the halving clock the pattern repeats: majors and platforms first, the speculative bursts in the 6-18 months after the halving, privacy last, after BTC's peak (red)."));
}
function statusCard(R) {
  const tone = { Undervalued: "ok", "Awaiting rotation": "", Neutral: "", "Priced in": "bad", Overvalued: "bad" };
  const col = { Undervalued: css("--up"), "Awaiting rotation": css("--accent"), Neutral: css("--muted"), "Priced in": css("--s2"), Overvalued: css("--down") };
  const p0 = v => v == null ? "–" : pct(v, 0);
  const head = ["Sector", "Status", "Representatives (90 days vs BTC)", "90d vs BTC", "RSI vs BTC", "From 1-year high", "Usage, ~90 days", "Past bursts (months after halving)"];
  const rows = (R.status || []).map(s => el("tr", {},
    el("td", {}, el("b", {}, s.rank + " · " + s.sector)),
    el("td", {}, el("span", { class: "pill " + (tone[s.status] || ""), style: "color:" + col[s.status] + ";white-space:nowrap" }, s.status)),
    el("td", { class: "wrap", style: "max-width:320px" }, ...(s.reps.length ? s.reps.map((c, i) => el("span", { style: "white-space:nowrap" }, (i ? " · " : ""), el("b", {}, c.ticker), " ", el("span", { class: cls(c.vs_btc_90d) }, p0(c.vs_btc_90d))))
      : [el("span", { class: "muted" }, "No liquid token: " + (s.no_token || []).join(", "))])),
    el("td", { class: cls(s.vs_btc_90d) }, p0(s.vs_btc_90d)), el("td", {}, s.rsi_vs_btc == null ? "–" : s.rsi_vs_btc.toFixed(0)), el("td", {}, p0(s.from_high)),
    el("td", { class: "wrap" }, s.usage == null ? el("span", { class: "muted" }, s.usage_label ? "no recent reading" : "no usage series") : el("span", {}, el("span", { class: cls(s.usage) }, p0(s.usage)), el("span", { class: "muted" }, " " + s.usage_label))),
    el("td", { class: "wrap muted" }, s.past.length ? s.past.map(h => "C" + h.cycle + " " + Math.round(h.m_start) + "–" + Math.round(h.m_end)).join(", ") : "none")));
  return card("Where each 2026-27 candidate sector stands today",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows)),
    el("ul", { class: "muted", style: "margin:8px 0 0;padding-left:18px;font-size:12.5px" }, ...(R.rules || []).map(([n, t]) => el("li", {}, el("b", { style: "color:" + col[n] }, n + ": "), t))),
    note("Medians of the representatives (coins.csv); rules checked in the order listed. Mechanical readings of price against BTC and of usage, not a view on any coin. Today: " +
      Math.round(R.months_now) + " months after the 2024 halving; past bursts mostly ran 6-18 months after one."));
}

// ---------- every candidate in one table: thesis, price cases, market cap against the sector's largest token
function candidatesTable(k, rot, px, jump) {
  const coins = (k.coins || []).filter(c => c.kpi), L = k.leaders || {};
  const status = {}; ((rot && rot.status) || []).forEach(s => { status[s.rank] = s.status; });
  const stCol = { Undervalued: "--up", "Awaiting rotation": "--accent", Neutral: "--muted", "Priced in": "--s2", Overvalued: "--down" };
  const rows = coins.map(c => {
    const K = c.kpi, ld = L[c.rank] || null;
    return { c, K, ld, sector: c.sector, rank: c.rank, status: status[c.rank] || "–", mcap: K.market_cap, price: K.price,
      share: ld && K.market_cap ? K.market_cap / ld.market_cap : null, toLeader: ld && K.market_cap ? ld.market_cap / K.market_cap : null,
      up27: K.base_2027 && K.price ? K.base_2027 / K.price - 1 : null, up28: K.base_2028 && K.price ? K.base_2028 / K.price - 1 : null,
      vsLeader28: ld && K.mcap_base_2028 ? K.mcap_base_2028 / ld.market_cap : null };
  });
  const COLS = [
    ["Coin", r => r.c.name.toLowerCase()], ["Sector", r => r.rank], ["Status", r => r.status], ["Price", r => r.price], ["90 days", r => r.K.vs_btc_90d],
    ["Market cap", r => r.mcap], ["vs sector leader", r => r.share], ["RSI vs BTC", r => r.K.rsi_vs_btc],
    ["End-2027 bear / base / bull", r => r.up27], ["End-2028 bear / base / bull", r => r.up28], ["Base 2028 cap vs leader today", r => r.vsLeader28]];
  let sortI = 1, dir = 1, sector = "all", q = "";
  const open = new Set();
  const tbody = el("tbody"), count = el("span", { class: "muted" });
  const head = el("tr", {});
  const spark = (pts, w = 70, h = 20) => {                      // 90 days of price, as a tiny line coloured by its direction
    const svg = svgEl("svg", { width: w, height: h, style: "display:block" });
    const v = (pts || []).map(p => p[1]).filter(x => x != null);
    if (v.length < 2) return svg;
    const lo = Math.min(...v), hi = Math.max(...v), X = i => i / (v.length - 1) * (w - 2) + 1, Y = x => h - 2 - (x - lo) / (hi - lo || 1) * (h - 4);
    svgEl("polyline", { points: v.map((x, i) => X(i) + "," + Y(x)).join(" "), fill: "none", stroke: css(v[v.length - 1] >= v[0] ? "--up" : "--down"), "stroke-width": 1.4 }, svg);
    return svg;
  };
  const cases = (K, y) => el("span", { style: "white-space:nowrap" }, el("span", { class: "down" }, px(K["bear_" + y])), " / ", el("b", {}, px(K["base_" + y])), " / ", el("span", { class: "up" }, px(K["bull_" + y])));
  const draw = () => {
    head.replaceChildren(...COLS.map(([n], i) => el("th", { style: "cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;background:var(--card, var(--bg));z-index:1" + (i ? "" : ";left:0;z-index:2"),
      onclick: () => { if (sortI === i) dir = -dir; else { sortI = i; dir = i <= 2 ? 1 : -1; } draw(); } }, n + (sortI === i ? (dir > 0 ? " ▲" : " ▼") : ""))));
    const get = COLS[sortI][1];
    const list = rows.filter(r => (sector === "all" || String(r.rank) === sector) && (!q || (r.c.name + " " + r.c.ticker).toLowerCase().includes(q)))
      .sort((a, b) => { const x = get(a), y = get(b); if (x == null) return y == null ? 0 : 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * dir || a.rank - b.rank || b.mcap - a.mcap; });
    count.textContent = list.length + " of " + rows.length + " coins";
    tbody.replaceChildren(...list.flatMap(r => {
      const K = r.K, isOpen = open.has(r.c.ticker), N = r.c.notes || {};
      const tr = el("tr", { style: "cursor:pointer", title: "Click for the thesis", onclick: () => { isOpen ? open.delete(r.c.ticker) : open.add(r.c.ticker); draw(); } },
        el("td", { style: "position:sticky;left:0;background:var(--card, var(--bg));white-space:nowrap" }, el("span", { class: "muted" }, isOpen ? "▾ " : "▸ "), el("b", {}, r.c.ticker), " ", el("span", { class: "muted" }, r.c.name)),
        el("td", { class: "muted", style: "white-space:nowrap" }, r.rank + " · " + r.sector.split(" (")[0].split(" / ")[0]),
        el("td", {}, el("span", { class: "pill", style: "white-space:nowrap;color:" + css(stCol[r.status] || "--muted") }, r.status)),
        el("td", { style: "text-align:right;white-space:nowrap" }, px(K.price)),
        el("td", {}, el("div", { style: "display:flex;gap:6px;align-items:center" }, spark(r.c.spark), el("span", { class: cls(K.vs_btc_90d), style: "white-space:nowrap", title: "against BTC over 90 days" }, pct(K.vs_btc_90d, 0)))),
        el("td", { style: "text-align:right;white-space:nowrap" }, usdBig(r.mcap)),
        el("td", { style: "white-space:nowrap" }, r.ld ? (r.share >= 0.999 ? el("b", {}, "the leader") : el("span", {},
          el("span", { style: "display:inline-block;vertical-align:middle;width:48px;height:6px;background:var(--line);border-radius:3px;margin-right:6px;position:relative" },
            el("span", { style: "position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:" + css("--s1") + ";width:" + Math.max(2, Math.min(100, Math.sqrt(r.share) * 100)) + "%" })),
          (r.share * 100 < 1 ? (r.share * 100).toFixed(2) : (r.share * 100).toFixed(1)) + "% of " + r.ld.symbol)) : "–"),
        el("td", { style: "text-align:right", class: K.rsi_vs_btc >= 70 ? "down" : K.rsi_vs_btc <= 30 ? "up" : "" }, K.rsi_vs_btc == null ? "–" : K.rsi_vs_btc.toFixed(0)),
        el("td", {}, cases(K, "2027"), el("div", { class: cls(r.up27), style: "font-size:12px" }, r.up27 == null ? "" : "base " + pct(r.up27, 0))),
        el("td", {}, cases(K, "2028"), el("div", { class: cls(r.up28), style: "font-size:12px" }, r.up28 == null ? "" : "base " + pct(r.up28, 0) + (K.factor_2028 != null && Math.abs(K.factor_2028 - 1) > 0.005 ? " · fundamentals ×" + K.factor_2028.toFixed(2) : ""))),
        el("td", { style: "white-space:nowrap" }, r.vsLeader28 == null ? "–" : (r.vsLeader28 >= 1 ? el("b", { class: "up" }, "×" + r.vsLeader28.toFixed(1) + " the leader") : (r.vsLeader28 * 100).toFixed(0) + "% of " + r.ld.symbol)));
      if (!isOpen) return [tr];
      return [tr, el("tr", {}, el("td", { colspan: COLS.length, style: "background:var(--chip);font-size:13px;white-space:normal;padding:0" },
        el("div", { style: "position:sticky;left:0;max-width:min(900px, 86vw);padding:8px 10px" },
        N.narrative ? el("div", {}, el("b", {}, "Why it fits: "), N.narrative) : null, N.standout ? el("div", { style: "margin-top:3px" }, el("b", {}, "What stands out: "), N.standout) : null,
        N.thesis ? el("div", { style: "margin-top:3px" }, el("b", {}, "Thesis: "), N.thesis) : null,
        el("div", { style: "margin-top:4px" }, el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: e => { e.stopPropagation(); jump(r.c.ticker); } }, "Open " + r.c.ticker + "'s card and charts ↓"),
          r.ld && r.share < 0.999 ? el("span", { class: "muted", style: "margin-left:8px" }, "To reach " + r.ld.name + "'s market cap (" + usdBig(r.ld.market_cap) + "): ×" + (r.toLeader >= 100 ? num(r.toLeader, 0) : r.toLeader.toFixed(1)) + ".") : null))))];
    }));
  };
  const secs = [...new Map(rows.map(r => [r.rank, r.sector])).entries()].sort((a, b) => a[0] - b[0]);
  const filt = el("div", { class: "seg", style: "flex-wrap:wrap" });
  const drawFilt = () => filt.replaceChildren(...[["all", "All"], ...secs.map(([n, s]) => [String(n), n + " · " + s.split(" (")[0].split(" / ")[0]])].map(([k2, l2]) =>
    el("button", { class: k2 === sector ? "on" : "", onclick: () => { sector = k2; drawFilt(); draw(); } }, l2)));
  drawFilt();
  const search = el("input", { type: "search", placeholder: "Find a coin", style: "font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:inherit;min-width:140px",
    oninput: e => { q = e.target.value.trim().toLowerCase(); draw(); } });
  const csv = el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: () => {
    const hd = ["ticker", "name", "sector", "status", "price", "vs_btc_90d", "market_cap", "sector_leader", "leader_market_cap", "share_of_leader", "rsi_vs_btc",
      "bear_2027", "base_2027", "bull_2027", "bear_2028", "base_2028", "bull_2028", "base_2028_mcap", "thesis"];
    const esc = v => v == null ? "" : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
    const lines = [hd.join(",")].concat(rows.map(r => [r.c.ticker, r.c.name, r.sector, r.status, r.price, r.K.vs_btc_90d, r.mcap, r.ld && r.ld.symbol, r.ld && r.ld.market_cap, r.share, r.K.rsi_vs_btc,
      r.K.bear_2027, r.K.base_2027, r.K.bull_2027, r.K.bear_2028, r.K.base_2028, r.K.bull_2028, r.K.mcap_base_2028, (r.c.notes || {}).thesis].map(esc).join(",")));
    const a = el("a", { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: "btc-cycles-candidates-" + (k.as_of || "") + ".csv" });
    document.body.append(a); a.click(); a.remove();
  } }, "Download CSV");
  draw();
  const lead = Object.entries(L).map(([n, l]) => n + " " + l.symbol + " " + usdBig(l.market_cap) + (l.candidate ? "" : "*")).join(" · ");
  return card("All candidates at a glance",
    el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px" }, search, count, csv),
    filt, el("div", { class: "scroll", style: "max-height:72vh;overflow:auto;margin-top:8px" }, el("table", {}, el("thead", {}, head), tbody)),
    note("Click a column to sort, a row for the thesis. Price cases are the projection (BTC scenario × beta × unlock dilution × valuation; see a coin's chart for the method); " +
      "the status is its sector's (Sectors tab). \"vs sector leader\" = the coin's market cap ÷ the largest in its sector, the bar on a square-root scale so small caps stay visible. " +
      "Sector leaders: " + (lead || "–") + " (* not a candidate)."));
}

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
    return [head, bottom, priceCard, ov, dd, anat];
  },
  async sectors() {
    const [d, rot] = await Promise.all([api("sectors"), api("rotation").catch(() => null)]);
    const seg = el("div", { class: "seg" }, ...d.cycles.map(c => el("button", { class: c.n === cycleN ? "on" : "", onclick: () => { cycleN = c.n; render(); } }, "Cycle " + c.n)));
    const c = d.cycles.find(x => x.n === cycleN);
    const sectorCol = c.columns[0];
    const bars = c.rows.flatMap(r => r._multiples.filter(m => m.x > 0).map(m => ({ cat: (m.label ? m.label + " · " : "") + r[sectorCol].split(" (")[0].slice(0, 22), x: m.x })));
    const mult = bars.length ? card("Peak multiples in this cycle (log scale)", ...svgBarsLog(bars)) : null;
    const tbl = card(c.heading, para(c.intro), table(c.columns, c.rows), para(c.after));
    const cross = fold("Cross-cycle comparison", true, para(d.cross_cycle.intro), table(d.cross_cycle.columns, d.cross_cycle.rows));
    const top = rot ? [statusCard(rot), rotationTimeline(rot)] : [];
    return [...top, card(null, seg, el("div", { class: "muted" }, "Pick a cycle. Figures are the doc's, approximate before 2024.")), tbl, mult, cross];
  },
  async metrics() {
    const d = await api("metrics"), R = d.research, L = d.latest || {};
    const head = card(null, followHead([["defi_tvl", "DeFi TVL"], ["stablecoins", "Stablecoin supply"], ["hl_tvl", "Hyperliquid TVL"], ["hl_revenue_30d", "Hyperliquid revenue, 30 days"],
      ["hl_fees_30d", "Hyperliquid fees, 30 days"], ["dex_volume_30d", "DEX volume (spot), 30 days"]].map(([k2, l2]) => ({ label: l2, points: d[k2] || [], fmt: usdBig, delta: { lag: "90d" } })),
      { latest: "Latest (" + (d.as_of || "–") + ")" }), asOf(d), stale(d));
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
    const tbl = fold("Common metrics of cycle winners", true, para(R.intro), table(R.columns, R.rows), para(R.after));
    return [head, grid, top, tbl];
  },
  async candidates() {
    const [d, k, rot] = await Promise.all([api("candidates"), api("coins"), api("rotation").catch(() => null)]);
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
    const method = fold("Projection method (mechanical, not a forecast)", false, el("div", { class: "muted" }, sc.method || ""),
      el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Scenario", "Bear BTC", "Base BTC", "Bull BTC"].map(h => el("th", {}, h))),
        ...(sc.scenarios || []).map(s => el("tr", {}, el("td", {}, s.label), ...["bear", "base", "bull"].map(x => el("td", { title: s[x].why }, usd(s[x].btc))))))),
      note("Hover a BTC level for the reasoning. BTC now: " + usd(k.btc_now) + ". Edit data/btc-cycles/scenarios.json to change the levels."),
      k.notes_about ? note("Coin notes: " + k.notes_about + " The \"Today\" line is computed from live data.") : null, stale(k));
    // one card per coin; the index on top sorts them and jumps to any of them
    const coins = k.coins || [], rows = {};
    for (const c of coins) rows[c.ticker] = coinRow(c, px, r1, rsiCls);
    const SORTS = [
      ["rank", "Doc rank", c => c.rank, 1, null], ["name", "Name", c => c.name.toLowerCase(), 1, null],
      ["change_1y", "1 year", c => c.kpi && c.kpi.change_1y, -1, v => pct(v, 0)], ["vs_btc_90d", "90 days vs BTC", c => c.kpi && c.kpi.vs_btc_90d, -1, v => pct(v, 0)],
      ["rsi_vs_btc", "RSI vs BTC", c => c.kpi && c.kpi.rsi_vs_btc, -1, v => v.toFixed(0)], ["market_cap", "Market cap", c => c.kpi && c.kpi.market_cap, -1, v => usdBig(v)],
      ["upside", "Upside to base end-2027", c => c.kpi && c.kpi.price && c.kpi.base_2027 ? c.kpi.base_2027 / c.kpi.price - 1 : null, -1, v => pct(v, 0)]];
    let sortKey = (() => { try { return sessionStorage.getItem("coin-sort") || "rank"; } catch (e) { return "rank"; } })();
    const seg = el("div", { class: "seg" }), chips = el("div", { class: "chips", style: "margin-top:8px;display:flex;flex-wrap:wrap;gap:6px" });
    const list = el("div", {});
    const layout = () => {
      const [key, label, get, dir, f] = SORTS.find(x => x[0] === sortKey) || SORTS[0];
      seg.replaceChildren(...SORTS.map(([k2, l2]) => el("button", { class: k2 === key ? "on" : "", onclick: () => { sortKey = k2; try { sessionStorage.setItem("coin-sort", k2); } catch (e) {} layout(); } }, l2)));
      const val = c => { const v = get(c); return v == null || Number.isNaN(v) ? null : v; };
      const order = coins.slice().sort((a, b) => { const x = val(a), y = val(b); if (x == null) return y == null ? 0 : 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * dir || a.rank - b.rank; });
      chips.replaceChildren(...order.map(c => { const v = val(c);
        return el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", title: c.name + (c.sector ? " · " + c.sector : ""), onclick: () => rows[c.ticker].scrollIntoView({ behavior: "smooth", block: "start" }) },
          el("b", {}, c.ticker), f && v != null ? el("span", { class: "muted" }, " " + f(v)) : null); }));
      if (key === "rank") {
        const byRank = {};
        for (const c of order) (byRank[c.rank] = byRank[c.rank] || []).push(c);
        list.replaceChildren(...Object.keys(byRank).sort((a, b) => a - b).map(r => fold(r + " · " + byRank[r][0].sector + " (" + byRank[r].length + ")", true, ...byRank[r].map(c => rows[c.ticker]))));
      } else list.replaceChildren(card("All " + coins.length + " candidates by " + label.toLowerCase() + (dir < 0 ? ", highest first" : ""), ...order.map(c => rows[c.ticker])));
    };
    const index = coins.length ? card("Candidate coins: sort and jump", seg, chips, note("Click a coin to jump to it. Sorting by doc rank groups them by the doc's sectors; any other sort lists all " + coins.length + " in one column.")) : null;
    const sections = coins.length ? [list] : [card("Candidate coins", el("div", { class: "err" }, "Not available right now (" + (k.btc_error || "no data") + ")."))];
    if (coins.length) layout();
    const ev = d.evidence || {};
    const evCards = [["3 · RWA on-chain value ex-stablecoins", ev["RWA on-chain value ex-stablecoins (USD)"], usdBig], ["4 · Prediction-market monthly volume", (ev["Prediction-market monthly volume (USD)"] || []).filter(p => p[1] > 0), usdBig],
      ["5 · x402 cumulative payment volume", ev["x402 cumulative payment volume (USD)"], usdBig], ["1 · Perp-DEX share of global futures", ev["Perp-DEX share of global futures (%)"], v => v == null ? "–" : v.toFixed(1) + "%"]]
      .map(([t, pts, f]) => pts && pts.length ? card(t, ...linesChart([{ name: t.slice(4), points: pts }], f, { small: true })) : null).filter(Boolean);
    const evidence = fold("Sector evidence without a liquid token (hand-entered; sources in data/btc-cycles/evidence.csv)", false, el("div", { class: "grid2" }, ...evCards));
    const jump = t => { if (rows[t]) rows[t].scrollIntoView({ behavior: "smooth", block: "start" }); };
    const glance = coins.length ? candidatesTable(k, rot, px, jump) : null;
    return [glance, index, docCard, method, ...sections, evidence];
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
    const rows = d.status.map((s, i) => el("tr", {}, el("td", {}, i + 1), el("td", { class: "wrap" }, s.signal), el("td", {}, pill(s.state)), el("td", { class: "wrap" }, s.reading), el("td", { class: "wrap" }, s.note)));
    const status = card("The six signals, read mechanically today (" + d.as_of + ")", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["#", "Signal", "Status", "Reading", "How"].map(h => el("th", {}, h))), ...rows)),
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
  if (c.error) return el("div", { class: "card", style: "margin-top:8px;opacity:.7;scroll-margin-top:56px", "data-follow": c.ticker }, head, notes, el("div", { class: "muted" }, "Not available right now (" + c.error + ")."));
  const K = c.kpi, src = { spark: c.spark || [], S: null };          // S: the full series, once "Show charts" has loaded them
  let cardEl = null;
  const series = name => src.S && src.S[name] && src.S[name].length ? src.S[name] : name === "price" ? src.spark : null;
  const pk = (t, latest, f) => t == null ? latest : f(t);
  const ratio90 = t => {                                               // the coin ÷ BTC over the 90 days to t
    const P = series("price"), B = src.S && src.S.btc_indexed; if (!P || !B) return null;
    const a = asof(P, t), b = asof(B, t), a0 = asof(P, t - 90 * 86400), b0 = asof(B, t - 90 * 86400);
    return a && b && a0 && b0 ? (a / b) / (a0 / b0) - 1 : null; };
  const strip = el("div", { style: "margin-top:8px" }, datedHead([
    { label: t => t == null ? "Price" : "Price on " + dateOf(t), value: t => [px(pk(t, K.price, t => asof(series("price"), t)))] },
    { label: () => "24h", value: t => { const v = pk(t, K.change_24h, t => { const P = series("price"), a = asof(P, t), b = asof(P, t - 86400); return a && b ? a / b - 1 : null; }); return [pct(v, 1), cls(v)]; } },
    { label: () => "1 year", value: t => { const v = pk(t, K.change_1y, t => { const P = series("price"), a = asof(P, t), b = asof(P, t - 365 * 86400); return a && b ? a / b - 1 : null; }); return [pct(v, 0), cls(v)]; } },
    { label: () => "Market cap", value: t => [usdBig(pk(t, K.market_cap, t => asof(series("market_cap"), t)))] },
    { label: () => "RSI 14", value: t => { const v = pk(t, K.rsi, t => asof(series("rsi"), t)); return [r1(v), rsiCls(v)]; } },
    { label: () => "RSI vs BTC", value: t => { const v = pk(t, K.rsi_vs_btc, t => asof(series("rsi_vs_btc"), t)); return [r1(v), rsiCls(v)]; } },
    { label: () => "Beta to BTC", value: () => [K.beta == null ? "–" : K.beta.toFixed(2)] },
    { label: () => "90d vs BTC", value: t => { const v = pk(t, K.vs_btc_90d, ratio90); return [pct(v, 0), cls(v)]; } },
    { label: () => "Base end-2027", value: () => [px(K.base_2027)] }, { label: () => "Base end-2028", value: () => [px(K.base_2028)] },
  ], { scope: () => cardEl, latest: "Today" }));
  const spark = el("div", { style: "margin-top:6px" }, ...linesChart([{ name: "90 days", points: c.spark || [] }], px, { small: true, sync: false }));
  spark.querySelector(".chart").style.height = "120px";
  const more = el("div", {});
  let loaded = false;
  const btn = el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit;margin-top:6px", onclick: async () => {
    if (loaded) { more.style.display = more.style.display === "none" ? "" : "none"; btn.textContent = more.style.display === "none" ? "Show charts" : "Hide charts"; return; }
    btn.textContent = "Loading…";
    try { const f = await api("coin-" + c.ticker.toLowerCase()); src.S = f.series; more.replaceChildren(...coinCharts(f, px, r1)); loaded = true; btn.textContent = "Hide charts"; }
    catch (err) { more.replaceChildren(el("div", { class: "err" }, "Could not load: " + err.message)); btn.textContent = "Retry"; }
  } }, "Show charts");
  cardEl = el("div", { class: "card", style: "margin-top:8px;scroll-margin-top:56px", "data-follow": c.ticker }, head, notes, strip, spark, btn, more);
  return cardEl;
}

function coinCharts(f, px, r1) {
  const S = f.series, end = S.price[S.price.length - 1][0];
  const price = card("Price, 365 days (log), with BTC rebased to the same start", ...linesChart([{ name: f.ticker, points: S.price }, { name: "BTC, rebased", points: S.btc_indexed, dashed: true, color: css("--hold") }], px, { log: true, small: true }));
  const rsi = card("RSI 14: the coin ÷ BTC ratio (solid) and the coin in USD (dashed)", ...linesChart([{ name: "RSI vs BTC", points: S.rsi_vs_btc }, { name: "RSI (USD)", points: S.rsi, dashed: true }], r1, { small: true, hlines: [30, 50, 70] }),
    note("Above 70: has run hard (against BTC for the solid line). Below 30: washed out."));
  const mcap = card("Market cap, 365 days", ...linesChart([{ name: "Market cap", points: S.market_cap }], v => usdBig(v), { small: true }));
  const pts = f.projection || [], FD = f.fundamentals || {}, FF = FD.factors || {};
  const fx = v => v == null ? "–" : "×" + v.toFixed(2);
  const nowPt = [end, S.price[S.price.length - 1][1]];
  const at = p => Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000);
  const ws = [];                                        // empty days to the last scenario date, so the axis is to scale in time
  if (pts.length) for (let t = end + 86400; t <= at(pts[pts.length - 1]); t += 86400) ws.push(t);
  const proj = card("Projection: bear / base / bull at end-2027 and end-2028 (beta " + (f.kpi.beta == null ? "–" : f.kpi.beta.toFixed(2)) + ")",
    // its own window, off the tab's shared date axis: the last year of price, then on to the last scenario date
    ...linesChart([{ name: "Price", points: S.price, color: css("--s1") },
      ...(pts.length ? [{ name: "Base", points: [nowPt, ...pts.map(p => [at(p), p.base])], color: css("--s2"), width: 3 },
        { name: "Bull", points: [nowPt, ...pts.map(p => [at(p), p.bull])], dashed: true, color: css("--up") },
        { name: "Bear", points: [nowPt, ...pts.map(p => [at(p), p.bear])], dashed: true, color: css("--down") },
        ...(pts.some(p => p.factor != null && Math.abs(p.factor - 1) > 0.005) ? [{ name: "Base, BTC beta only", points: [nowPt, ...pts.map(p => [at(p), p.base_beta_only])], color: css("--hold"), width: 1 }] : [])] : [])],
      px, { log: true, whitespace: ws, sync: false }),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {},
      el("tr", {}, ...["Scenario", "Bear", "Base", "Bull", "Base, BTC beta only", "× Dilution", "× Valuation", "Implied market cap (base)"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))),
      ...pts.map((p, i) => el("tr", {}, el("td", {}, p.label), ...[px(p.bear), px(p.base), px(p.bull), px(p.base_beta_only), fx(p.dilution), fx(p.valuation), usdBig((f.implied_mcap_base[i] || {}).mcap)]
        .map(v => el("td", { style: "text-align:right" }, v)))))),
    f.notes && f.notes.thesis ? el("div", { style: "margin-top:8px;font-size:13px" }, el("b", {}, "Thesis behind the projection: "), f.notes.thesis) : null,
    note("Price now × (BTC scenario ÷ BTC now) ^ beta, then × dilution (supply now ÷ supply at that date: " + (FF.dilution_basis || "no supply data, so 1") +
      ") × valuation (half-way back to the coin's own 1-year median " + (FF.valuation_basis || "multiple; no fees or TVL, so 1") + ", within 0.67-1.5). Mechanical; it says nothing about survival or the coin's own news."));
  const big = proj.querySelector(".chart"); if (big) big.style.height = "460px";            // the projection gets the full width and height
  const last = pts.length ? at(pts[pts.length - 1]) : end;
  let tries = 0;
  const frame = () => {
    const c = charts.find(x => x.chartElement && proj.contains(x.chartElement()));
    if (!c || !c.timeScale().width()) { if (tries++ < 40) setTimeout(frame, 100); return; }
    try { c.timeScale().setVisibleRange({ from: end - 365 * 86400, to: last + 20 * 86400 }); } catch (e) { c.timeScale().fitContent(); }
  };
  setTimeout(frame, 150);
  return [el("div", { style: "margin-top:8px" }, proj), fundamentalsCard(f, px), el("div", { class: "grid2", style: "margin-top:8px" }, price, rsi, mcap), stale(f)].filter(Boolean);
}

// fees, TVL and supply against price, each rebased to 100 at the start of the year, plus the multiples and the unlock schedule
function fundamentalsCard(f, px) {
  const FD = f.fundamentals || {}, FS = FD.series || {}, K = FD.kpi || {}, S = f.series;
  const t0 = S.price[0][0];
  const rebase = pts => { const q = (pts || []).filter(p => p[0] >= t0 - 7 * 86400 && p[1] > 0); return q.length > 1 ? q.map(p => [p[0], p[1] / q[0][1] * 100]) : null; };
  const lines = [["Price", S.price, css("--s1")], ["Fees, 30 days", FS.fees_30d, css("--s2")], ["TVL", FS.tvl, css("--s3")], ["Circulating supply", FS.supply, css("--s4")]]
    .map(([n, pts, color]) => { const r = rebase(pts); return r ? { name: n, points: r, color, width: n === "Price" ? 2.5 : 1.5 } : null; }).filter(Boolean);
  const rel = (a, b) => a == null || b == null ? "" : " (1-year median " + (b >= 10 ? num(b, 0) : b.toFixed(2)) + "×)";
  const m = v => v == null ? "–" : (v >= 10 ? num(v, 0) : v.toFixed(2)) + "×";
  const kp = el("div", { class: "kpis" },
    kpi("Fees, last 30 days", usdBig(K.fees_30d)), kpi("Price-to-fees (annualised)" + rel(K.p_fees, K.p_fees_median), m(K.p_fees), K.p_fees != null && K.p_fees_median != null ? (K.p_fees < K.p_fees_median ? "up" : "down") : ""),
    kpi("TVL", usdBig(K.tvl)), kpi("Market cap ÷ TVL" + rel(K.p_tvl, K.p_tvl_median), m(K.p_tvl), K.p_tvl != null && K.p_tvl_median != null ? (K.p_tvl < K.p_tvl_median ? "up" : "down") : ""),
    kpi("Unlocked (of max supply)", K.unlocked_share == null ? "–" : pct(K.unlocked_share, 0).replace("+", "")),
    kpi("Supply added, next 12 months", K.unlock_12m == null ? "–" : pct(K.unlock_12m, 1), K.unlock_12m > 0.05 ? "down" : ""));
  const kids = [kp];
  if (lines.length > 1) kids.push(...linesChart(lines, v => v == null ? "–" : v.toFixed(0), { log: true, small: true, sync: false }),
    note("Each line ÷ its value a year ago × 100. Price rising faster than fees or TVL = the multiple expanding; supply rising = dilution from unlocks and emissions."));
  if (FS.schedule && FS.schedule.length > 3) {
    const now = S.price[S.price.length - 1][0];
    kids.push(el("div", { style: "margin-top:10px" }, el("b", {}, "Unlock schedule: total unlocked supply, past and scheduled (DefiLlama)")),
      ...linesChart([{ name: "Unlocked", points: FS.schedule.filter(p => p[0] <= now + 3 * 365 * 86400) }], v => v == null ? "–" : big(v), { small: true, sync: false }));
  }
  const src = Object.entries(FD.sources || {}).map(([k, u]) => k + ": [" + host(u) + "](" + u + ")").join(" · ");
  const miss = Object.entries(FD.errors || {}).map(([k, e]) => k + " (" + e.split(":")[0] + ")").join(", ");
  kids.push(note(FD.updated ? "" : "Fundamentals are fetched by the background job with the prices; this coin has not been reached yet."),
    src ? el("div", { class: "muted", style: "margin-top:4px;font-size:12px" }, ...md("Sources: " + src)) : null,
    miss ? note("Not available for this coin: " + miss + ".") : null);
  return el("div", { style: "margin-top:8px" }, card("Fundamentals against price: fees, TVL, supply and unlocks", ...kids.filter(Boolean)));
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
