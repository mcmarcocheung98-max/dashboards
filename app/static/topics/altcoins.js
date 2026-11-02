// Altcoin Study & Sector Rotation: five tabs. Sectors (status, rotation timeline, usage metrics, the doc's tables), Candidates (every coin
// in one table and a card each), Coins (one candidate in full: board, buy zone, charts, fundamentals, projection; ENA's unlock study),
// Signals (every coin's readings, then the picked coin's board, fitted board, twenty signals and volume zones) and Memecoins.
// Data from /api/altcoins/<sectors|rotation|metrics|candidates|coins|coin-*|hype|ena|sol|near|zones|boards|signals|volume|unlocks|basket|season>
// (app/topics/altcoins.py, btc_cycles.py, _coin_page.py, memecoins.py); helpers from topic.html.
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


// ---- helpers shared with btc-cycles.js (the doc's tables, folding cards)
let cycleN = 4;
const xf = v => v == null ? "–" : (v >= 100 ? Math.round(v) : v.toFixed(v >= 10 ? 0 : 1)) + "×";
const para = (s, cls = "muted") => el("div", { class: cls, style: "margin-top:6px" }, ...md(s));
const table = (cols, rows, opts = {}) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map(h => el("th", { style: "text-align:left;vertical-align:bottom" }, h))),
  ...rows.map(r => el("tr", {}, ...cols.map((c, i) => { const v = Array.isArray(r) ? r[i] : r[c]; return el("td", { class: i === 0 ? "" : "wrap" }, ...md(String(v ?? ""))); })))));
const docLink = r => el("div", { class: "src", style: "margin-top:6px" }, "From the research doc, as of " + r.as_of + ": ", link("open it", r.doc_url), ".");
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
// the Coins tab shows one candidate at a time; the pick is kept for this browser tab. Old tab addresses map to the new tabs.
const CANDS = ["HYPE", "ENA", "SOL", "NEAR"];
let COIN = "HYPE";
try { COIN = sessionStorage.getItem("coin:pick") || COIN; } catch (e) {}
if (!CANDS.includes(COIN)) COIN = "HYPE";
const setCoin = t => { COIN = t; try { sessionStorage.setItem("coin:pick", t); } catch (e) {} };
const openCoin = t => { setCoin(t); if (current === "coins") render(); else location.hash = "coins"; };
const OLD_TABS = { zones: "signals", boards: "signals", volume: "signals", unlocks: "coins", basket: "memes", season: "memes", hype: "coins", ena: "coins", sol: "coins", near: "coins" };
(() => {
  const h = location.hash.slice(1);
  if (!OLD_TABS[h]) return;
  if (CANDS.includes(h.toUpperCase())) setCoin(h.toUpperCase()); else if (h === "unlocks") setCoin("ENA");
  current = OLD_TABS[h];                                   // the shell's current tab (topic.html); set before its first render
  try { history.replaceState(null, "", "#" + OLD_TABS[h]); } catch (e) {}
})();

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
  const head = ["Sector", "Status", "Representatives (90 days vs BTC)", "90d vs BTC", "RSI vs BTC", "From 1-year high", "Usage, ~90 days", "Float · supply in 12 months", "Past bursts (months after halving)"];
  const align = ["left", "left", "left", "right", "right", "right", "left", "left", "left"];
  const ovCol = { heavy: css("--down"), some: css("--s2"), light: css("--up") };
  const supply = s => s.float == null && s.unlock_12m == null ? el("span", { class: "muted" }, "no data") : el("span", { style: "white-space:nowrap", title: "Medians of the representatives: share of max supply circulating · supply added over the next 12 months (unlock schedule, else last year's growth)" },
    (s.float == null ? "–" : Math.round(s.float * 100) + "%") + " · " + (s.unlock_12m == null ? "–" : (s.unlock_12m >= 0 ? "+" : "") + Math.round(s.unlock_12m * 100) + "%"),
    s.overhang ? el("span", { class: "pill", style: "margin-left:6px;color:" + ovCol[s.overhang] }, s.overhang) : null);
  const rows = (R.status || []).map(s => el("tr", {},
    el("td", {}, el("b", {}, s.rank + " · " + s.sector)),
    el("td", { style: "text-align:left" }, el("span", { class: "pill " + (tone[s.status] || ""), style: "color:" + col[s.status] + ";white-space:nowrap" }, s.status)),
    el("td", { class: "wrap", style: "min-width:260px;max-width:340px" }, s.reps.length
      ? el("div", { style: "display:flex;flex-wrap:wrap;gap:2px 10px" }, ...s.reps.map(c => el("span", { style: "white-space:nowrap" }, el("b", c.secondary ? { style: "text-decoration:underline dotted", title: "The doc's sector is this coin's secondary classification: " + c.secondary } : {}, c.ticker + (c.secondary ? "†" : "")), " ", el("span", { class: cls(c.vs_btc_90d) }, p0(c.vs_btc_90d)))))
      : el("span", { class: "muted" }, "No liquid token: " + (s.no_token || []).join(", "))),
    el("td", { class: cls(s.vs_btc_90d), style: "text-align:right" }, p0(s.vs_btc_90d)), el("td", { style: "text-align:right" }, s.rsi_vs_btc == null ? "–" : s.rsi_vs_btc.toFixed(0)), el("td", { style: "text-align:right" }, p0(s.from_high)),
    el("td", { class: "wrap" }, s.usage == null ? el("span", { class: "muted" }, s.usage_label ? "no recent reading" : "no usage series") : el("span", {}, el("span", { class: cls(s.usage) }, p0(s.usage)), el("span", { class: "muted" }, " " + s.usage_label))),
    el("td", { style: "text-align:left" }, supply(s), s.overhang_note ? el("div", { class: "muted", style: "font-size:12px;white-space:normal;max-width:220px" }, s.overhang_note) : null),
    el("td", { class: "wrap muted" }, s.past.length ? s.past.map(h => "C" + h.cycle + " " + Math.round(h.m_start) + "–" + Math.round(h.m_end)).join(", ") : "none")));
  return card("Where each 2026-27 candidate sector stands today",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map((h, i) => el("th", { style: "text-align:" + align[i] + ";vertical-align:bottom" }, h))), ...rows)),
    el("ul", { class: "muted", style: "margin:8px 0 0;padding-left:18px;font-size:12.5px" }, ...(R.rules || []).map(([n, t]) => el("li", {}, el("b", { style: "color:" + col[n] }, n + ": "), t))),
    note("† = the sector is a secondary classification for that coin on CoinGecko, CoinMarketCap and Messari (hover it); see the Candidates table for sources."),
    note("Medians of the representatives (coins.csv); rules checked in the order listed. Mechanical readings of price against BTC and of usage, not a view on any coin. Today: " +
      Math.round(R.months_now) + " months after the 2024 halving; past bursts mostly ran 6-18 months after one."));
}

// Is the doc's sector how the classifiers file the coin? "primary" / "secondary" from classification.json (with sources), plus the live
// CoinGecko check when its categories have been fetched (a warning when none of them matches the sector).
function classCell(c) {
  const C = c.classification, G = c.cg_check;
  const tip = (C ? "Classifiers: " + C.classifiers + (C.note ? " (" + C.note + ")" : "") : "") + (G ? "\nCoinGecko today: " + (G.categories.join(", ") || "–") : "");
  const main = !C ? el("span", { class: "muted" }, "–") : C.doc_sector === "primary" ? el("span", { class: "up", style: "white-space:nowrap" }, "✓ primary")
    : el("span", { class: "pill", style: "white-space:nowrap;color:" + css("--s2") }, "secondary");
  return el("span", { title: tip, style: "white-space:nowrap" }, main, G && !G.ok ? el("span", { class: "down", style: "margin-left:4px", title: "CoinGecko files none of its categories under this sector" }, "⚠") : null);
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
    ["Coin", r => r.c.name.toLowerCase()], ["Sector", r => r.rank], ["Classifiers", r => (r.c.classification || {}).doc_sector || "~"], ["Status", r => r.status], ["Price", r => r.price], ["90 days", r => r.K.vs_btc_90d],
    ["Market cap", r => r.mcap], ["vs sector leader", r => r.share], ["Float · 12-mo supply", r => r.K.unlock_12m == null ? null : -r.K.unlock_12m], ["RSI vs BTC", r => r.K.rsi_vs_btc],
    ["End-2027 bear / base / bull", r => r.up27], ["End-2028 bear / base / bull", r => r.up28], ["Base 2028 cap vs leader today", r => r.vsLeader28]];
  const AL = ["left", "left", "left", "left", "right", "left", "right", "left", "left", "right", "left", "left", "left"];
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
    head.replaceChildren(...COLS.map(([n], i) => el("th", { style: "text-align:" + AL[i] + ";cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;background:var(--card, var(--bg));z-index:1" + (i ? "" : ";left:0;z-index:2"),
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
        el("td", {}, classCell(r.c)),
        el("td", {}, el("span", { class: "pill", style: "white-space:nowrap;color:" + css(stCol[r.status] || "--muted") }, r.status)),
        el("td", { style: "text-align:right;white-space:nowrap" }, px(K.price)),
        el("td", {}, el("div", { style: "display:flex;gap:6px;align-items:center" }, spark(r.c.spark), el("span", { class: cls(K.vs_btc_90d), style: "white-space:nowrap", title: "against BTC over 90 days" }, pct(K.vs_btc_90d, 0)))),
        el("td", { style: "text-align:right;white-space:nowrap" }, usdBig(r.mcap)),
        el("td", { style: "white-space:nowrap" }, r.ld ? (r.share >= 0.999 ? el("b", {}, "the leader") : el("span", {},
          el("span", { style: "display:inline-block;vertical-align:middle;width:48px;height:6px;background:var(--line);border-radius:3px;margin-right:6px;position:relative" },
            el("span", { style: "position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:" + css("--s1") + ";width:" + Math.max(2, Math.min(100, Math.sqrt(r.share) * 100)) + "%" })),
          (r.share * 100 < 1 ? (r.share * 100).toFixed(2) : (r.share * 100).toFixed(1)) + "% of " + r.ld.symbol)) : "–"),
        el("td", { style: "white-space:nowrap", class: (K.float != null && K.float < 0.2) || (K.unlock_12m != null && K.unlock_12m >= 0.2) ? "down" : "",
          title: "Share of max supply circulating · supply added in the next 12 months. Under 20% float or 20%+ coming = heavy overhang (Binance Research, GSR, Keyrock)" },
          K.float == null && K.unlock_12m == null ? el("span", { class: "muted" }, "–") : (K.float == null ? "–" : Math.round(K.float * 100) + "%") + " · " + (K.unlock_12m == null ? "–" : (K.unlock_12m >= 0 ? "+" : "") + Math.round(K.unlock_12m * 100) + "%")),
        el("td", { style: "text-align:right", class: K.rsi_vs_btc >= 70 ? "down" : K.rsi_vs_btc <= 30 ? "up" : "" }, K.rsi_vs_btc == null ? "–" : K.rsi_vs_btc.toFixed(0)),
        el("td", {}, cases(K, "2027"), el("div", { class: cls(r.up27), style: "font-size:12px" }, r.up27 == null ? "" : "base " + pct(r.up27, 0))),
        el("td", {}, cases(K, "2028"), el("div", { class: cls(r.up28), style: "font-size:12px" }, r.up28 == null ? "" : "base " + pct(r.up28, 0) + (K.factor_2028 != null && Math.abs(K.factor_2028 - 1) > 0.005 ? " · fundamentals ×" + K.factor_2028.toFixed(2) : ""))),
        el("td", { style: "white-space:nowrap" }, r.vsLeader28 == null ? "–" : (r.vsLeader28 >= 1 ? el("b", { class: "up" }, "×" + r.vsLeader28.toFixed(1) + " the leader") : (r.vsLeader28 * 100).toFixed(0) + "% of " + r.ld.symbol)));
      [...tr.children].forEach((td, i) => { if (!td.style.textAlign) td.style.textAlign = AL[i]; });
      if (!isOpen) return [tr];
      return [tr, el("tr", {}, el("td", { colspan: COLS.length, style: "background:var(--chip);font-size:13px;white-space:normal;padding:0" },
        el("div", { style: "position:sticky;left:0;max-width:min(900px, 86vw);padding:8px 10px" },
        N.narrative ? el("div", {}, el("b", {}, "Why it fits: "), N.narrative) : null, N.standout ? el("div", { style: "margin-top:3px" }, el("b", {}, "What stands out: "), N.standout) : null,
        N.thesis ? el("div", { style: "margin-top:3px" }, el("b", {}, "Thesis: "), N.thesis) : null,
        r.c.classification ? el("div", { style: "margin-top:3px" }, el("b", {}, "How classifiers file it: "), r.c.classification.classifiers + (r.c.classification.note ? " (" + r.c.classification.note + ")" : "") + ". ",
          ...md(r.c.classification.sources.map(u => "[" + host(u) + "](" + u + ")").join(" · "))) : null,
        r.c.cg_check ? el("div", { style: "margin-top:3px" }, el("b", {}, "CoinGecko today: "), r.c.cg_check.categories.join(", ") || "–") : null,
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
      "float", "supply_added_12m", "bear_2027", "base_2027", "bull_2027", "bear_2028", "base_2028", "bull_2028", "base_2028_mcap", "doc_sector_is", "classifiers", "thesis"];
    const esc = v => v == null ? "" : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
    const lines = [hd.join(",")].concat(rows.map(r => [r.c.ticker, r.c.name, r.sector, r.status, r.price, r.K.vs_btc_90d, r.mcap, r.ld && r.ld.symbol, r.ld && r.ld.market_cap, r.share, r.K.rsi_vs_btc,
      r.K.float, r.K.unlock_12m, r.K.bear_2027, r.K.base_2027, r.K.bull_2027, r.K.bear_2028, r.K.base_2028, r.K.bull_2028, r.K.mcap_base_2028, (r.c.classification || {}).doc_sector, (r.c.classification || {}).classifiers, (r.c.notes || {}).thesis].map(esc).join(",")));
    const a = el("a", { href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: "altcoin-candidates-" + (k.as_of || "") + ".csv" });
    document.body.append(a); a.click(); a.remove();
  } }, "Download CSV");
  draw();
  const lead = Object.entries(L).map(([n, l]) => n + " " + l.symbol + " " + usdBig(l.market_cap) + (l.candidate ? "" : "*")).join(" · ");
  return card("All candidates at a glance",
    el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px" }, search, count, csv),
    filt, el("div", { class: "scroll", style: "max-height:72vh;overflow:auto;margin-top:8px" }, el("table", {}, el("thead", {}, head), tbody)),
    note("Classifiers: ✓ primary = CoinGecko, CoinMarketCap and Messari file the coin under the doc's sector first; secondary = a common second label (e.g. Chainlink is an oracle first, RWA infrastructure second); ⚠ = none of the coin's live CoinGecko categories matches the sector. Hover for the details, click the row for sources."),
    note("Click a column to sort, a row for the thesis. Price cases are the projection (BTC scenario × beta × unlock dilution × valuation; see a coin's chart for the method); " +
      "the status is its sector's (Sectors tab). \"vs sector leader\" = the coin's market cap ÷ the largest in its sector, the bar on a square-root scale so small caps stay visible. " +
      "Sector leaders: " + (lead || "–") + " (* not a candidate)."));
}


function header(f) {
  const L = f.links || {}, P = f.peers || {}, others = Object.entries(f.sibling_pages || {}).filter(([t]) => t !== f.ticker);
  return card(null,
    el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline" },
      el("b", { style: "font-size:17px" }, f.name, " ", el("span", { class: "muted" }, f.ticker)),
      el("span", { class: "pill" }, f.sector), f.note ? el("span", { class: "pill" }, f.note) : null,
      link("CoinMarketCap", L.coinmarketcap), L.defillama ? link("DefiLlama", L.defillama) : null, link("CoinGecko", L.coingecko)),
    el("div", { class: "muted", style: "margin-top:6px" }, "BTC Cycles candidate, doc rank " + f.rank,
      P.n ? " · market cap " + ord(P.market_cap) + " of " + P.n + " candidates · 90 days against BTC " + ord(P.vs_btc_90d) + " of " + P.n : "", ". ",
      el("a", { href: "#candidates" }, "All candidates"), " · ", el("a", { href: "#signals" }, "Signals and zones"),
      ...others.flatMap(([t]) => [" · ", el("a", { href: "#coins", onclick: e => { e.preventDefault(); openCoin(t); } }, t)])));
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
      el("td", {}, el("a", { href: "#signals", onclick: e => { e.preventDefault(); pickSig(r.ticker); } }, r.ticker), " ", el("span", { class: "muted" }, r.group === "Memecoin" ? "meme" : "candidate")),
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
let VZ_DAYS = 365;

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
      el("tr", { class: "tap", style: "cursor:pointer", onclick: () => pickSig(c.ticker) },
        el("td", {}, el("b", {}, c.ticker), " ", el("span", { class: "muted" }, c.group === "Memecoin" ? "meme" : "candidate")),
        el("td", { style: "text-align:right" }, px(c.price)), el("td", { style: "text-align:right", class: lc[c.lean] || "" }, c.read),
        el("td", { style: "text-align:right" }, c.live),
        el("td", { style: "text-align:right" }, c.now.support ? px(c.now.support.hi) + " (" + pctAbs1(c.now.support.below_pct) + " below)" : "–"),
        el("td", { style: "text-align:right" }, c.now.resistance ? px(c.now.resistance.lo) + " (" + pctAbs1(c.now.resistance.above_pct) + " above)" : "–"),
        el("td", { style: "text-align:right" }, c.big_days_30d),
        el("td", { style: "text-align:right", class: cls(c.stats.buy_7d) }, pct(c.stats.buy_7d, 1)), el("td", { style: "text-align:right", class: cls(c.stats.sell_7d) }, pct(c.stats.sell_7d, 1))))));
}

// ------------------------------------------------------------------ signals: twenty of them, weighted into one reading per coin
let SIG_COIN = null, SG_H = 7;                 // the coin whose boards, signals and zones the Signals tab shows, and the horizon the signals are judged on
try { SIG_COIN = sessionStorage.getItem("sg:coin"); SG_H = +(sessionStorage.getItem("sg:h") || 7); } catch (e) {}
const pickSig = t => { SIG_COIN = t; try { sessionStorage.setItem("sg:coin", t); } catch (e) {} render(); };
// one coin's reading at the chosen horizon merged with its static row (price, history), so the cards read one object
const atHorizon = (d, h) => { const B = (d.by_horizon || {})[String(h)] || {}; return { ...d, ...B, coins: (d.coins || []).map(c => c.status === "ok" && B.coins && B.coins[c.ticker] ? { ...c, ...B.coins[c.ticker] } : c) }; };

function horizonCard(d) {
  // the same pipeline judged on 7, 14 and 30 days side by side: how many signals earned weight, the top ones, the pooled walk-forward result
  const hs = d.horizons || [7];
  const H = ["Judged on", "Signals with weight", "Top weights", "Beat holding (long + short)", "Median Sharpe", "Median worst fall", "Median hit rate", "Beat holding (long only)", "Median Sharpe (long only)", "Median a year (long only)"];
  return card("Which horizon do the signals predict? The whole fit and backtest, once per horizon",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 && i !== 2 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...hs.map(h => { const B = (d.by_horizon || {})[String(h)] || {}, P = B.pooled_backtest || {}, W = B.weights || {};
        const top = Object.entries(W).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => ((d.signals || []).find(x => x.key === k) || { label: k }).label + " " + w1(v)).join(", ");
        return el("tr", { style: h === SG_H ? "font-weight:650" : "", onclick: () => { SG_H = h; try { sessionStorage.setItem("sg:h", h); } catch (e) {} render(); } },
          el("td", {}, h + " days"), el("td", {}, B.error ? "error: " + B.error : (P.signals_with_weight ?? "–") + (B.how && B.how.startsWith("equal") ? " (equal: none cleared the bar)" : "")), el("td", { class: "muted" }, top || "–"),
          el("td", { style: "text-align:right" }, P.coins ? P.beat_hold + " of " + P.coins : "–"), el("td", { style: "text-align:right" }, P.median_sharpe == null ? "–" : P.median_sharpe.toFixed(2)),
          el("td", { style: "text-align:right", class: "down" }, pctOrDash(P.median_worst_drop, 0)), el("td", { style: "text-align:right", class: P.median_hit_rate_7d > 0.5 ? "up" : P.median_hit_rate_7d < 0.5 ? "down" : "" }, P.median_hit_rate_7d == null ? "–" : Math.round(P.median_hit_rate_7d * 100) + "%"),
          el("td", { style: "text-align:right" }, P.coins ? P.long_only_beat_hold + " of " + P.coins : "–"), el("td", { style: "text-align:right" }, P.long_only_median_sharpe == null ? "–" : P.long_only_median_sharpe.toFixed(2)),
          el("td", { style: "text-align:right", class: cls(P.long_only_median_a_year) }, pctOrDash(P.long_only_median_a_year, 0))); }))),
    note("Each row re-fits the weights on that horizon's forward return and re-runs the walk-forward backtest; the trading rule itself is the same daily close-to-close rule. Hit rate = the share of readings whose direction matched the return over that horizon. Click a row to switch the tab to it. " +
      "Two signals (inside a zone, place in the 1-year range) had a significantly negative record at 7 days on 30 Oct 2026 and were flipped; their record since is in-sample for that choice."));
}
const SG_CLS = { "strong buy": "up", "lean buy": "up", neutral: "", "lean sell": "down", "strong sell": "down" };
const sc2 = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const w1 = v => v == null ? "–" : (v * 100).toFixed(0) + "%";

function signalsTable(coins) {
  const H = ["Coin", "Final signal", "Score", "Biggest push", "Walk-forward: strategy a year", "Hold a year", "Sharpe", "Worst fall", "Hit rate", "Since"];
  const rows = coins.filter(c => c.status === "ok").slice().sort((a, b) => (b.score ?? -9) - (a.score ?? -9));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 && i !== 3 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(c => { const B = c.backtest || {}, top = (c.contributions || []).filter(x => x.contribution !== 0).slice(0, 2);
      return el("tr", { style: "cursor:pointer", onclick: () => pickSig(c.ticker) },
        el("td", {}, el("b", {}, c.ticker), " ", el("span", { class: "muted" }, c.group === "Memecoin" ? "meme" : "candidate")),
        el("td", { class: SG_CLS[c.label] || "" }, c.label), el("td", { style: "text-align:right", class: cls(c.score) }, sc2(c.score)),
        el("td", { class: "muted" }, top.map(x => x.label + " " + sc2(x.contribution)).join(", ") || "–"),
        el("td", { style: "text-align:right", class: cls(B.a_year) }, pctOrDash(B.a_year, 0)), el("td", { style: "text-align:right", class: cls(B.hold_a_year) }, pctOrDash(B.hold_a_year, 0)),
        el("td", { style: "text-align:right" }, B.sharpe == null ? "–" : B.sharpe.toFixed(2)), el("td", { style: "text-align:right", class: "down" }, pctOrDash(B.worst_drop, 0)),
        el("td", { style: "text-align:right", class: B.hit_rate_7d > 0.5 ? "up" : B.hit_rate_7d < 0.5 ? "down" : "" }, B.hit_rate_7d == null ? "–" : Math.round(B.hit_rate_7d * 100) + "%"),
        el("td", { class: "muted" }, B.from || c.since)); }),
    ...coins.filter(c => c.status !== "ok").map(c => el("tr", {}, el("td", {}, el("b", {}, c.ticker)), el("td", { colspan: H.length - 1, class: "muted" }, c.status === "error" ? "Not available right now (" + c.why + ")." : c.status + ".")))));
}

function signalGrid(c, d) {
  // the 20 signals today for one coin: value, weight, contribution, and the pooled record (rank correlation, hit rate) behind the weight
  const pooled = Object.fromEntries((d.per_signal || []).map(r => [r.signal, r])), own = Object.fromEntries((c.own_eval || []).map(r => [r.signal, r]));
  const H = ["Signal", "Family", "Today", "Weight", "Push", "Rank corr. (all coins)", "Hit rate (all coins)", "Hit rate (" + c.ticker + ")", "Active days"];
  const rows = (c.contributions || []).slice().sort((a, b) => b.weight - a.weight || Math.abs(b.value) - Math.abs(a.value));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(r => { const p = pooled[r.signal] || {}, o = own[r.signal] || {}, meta = (d.signals || []).find(x => x.key === r.signal) || {};
      return el("tr", { title: meta.means || "" }, el("td", {}, r.label), el("td", { class: "muted" }, r.family),
        el("td", { style: "text-align:right", class: cls(r.value) }, sc2(r.value)), el("td", { style: "text-align:right", class: r.weight > 0 ? "" : "muted" }, w1(r.weight)),
        el("td", { style: "text-align:right", class: cls(r.contribution) }, sc2(r.contribution)),
        el("td", { style: "text-align:right", class: cls(p.ic) }, p.ic == null ? "–" : sc2(p.ic)), el("td", { style: "text-align:right", class: p.hit_rate > 0.5 ? "up" : p.hit_rate < 0.5 ? "down" : "" }, p.hit_rate == null ? "–" : Math.round(p.hit_rate * 100) + "%"),
        el("td", { style: "text-align:right", class: o.hit_rate > 0.5 ? "up" : o.hit_rate < 0.5 ? "down" : "" }, o.hit_rate == null ? "–" : Math.round(o.hit_rate * 100) + "%"),
        el("td", { style: "text-align:right", class: "muted" }, p.days_active == null ? "–" : num(p.days_active))); })));
}

function compositeChart(c, enter) {
  // the final score day by day (bars, green above the entry line, red below) under the price, both on the shared date axis
  return [card(c.ticker + " price (log) over the days the signal existed", ...linesChart([{ name: c.ticker, points: c.price_series, color: css("--s1") }], px, { log: true, small: true })),
    card("Final signal day by day: above +" + enter + " = long, below −" + enter + " = short",
      ...linesChart([{ name: "Score", points: c.composite, bar: true }], v => v == null ? "–" : sc2(v), { small: true, hlines: [enter, -enter] }))];
}

function backtestCard(d, c) {
  const B = c.backtest || {}, L = c.backtest_long_only || {};
  if (B.total == null) return card("Walk-forward backtest", note("Not enough history after the first fit (" + (B.days || 0) + " days)."));
  return card("Trading the final signal, walk-forward (" + B.from + " to " + B.to + ", " + B.days + " days)",
    el("div", { class: "kpis" },
      kpi("Long + short, total", pct(B.total, 0), cls(B.total)), kpi("Holding " + c.ticker + ", same days", pct(B.hold, 0), cls(B.hold)),
      kpi("A year: strategy / hold", pctOrDash(B.a_year, 0) + " / " + pctOrDash(B.hold_a_year, 0), cls((B.a_year || 0) - (B.hold_a_year || 0))),
      kpi("Sharpe", B.sharpe == null ? "–" : B.sharpe.toFixed(2)), kpi("Worst fall: strategy / hold", pct(B.worst_drop, 0) + " / " + pct(B.hold_worst_drop, 0)),
      kpi("Time long / short", Math.round(B.time_long * 100) + "% / " + Math.round(B.time_short * 100) + "%"), kpi("Position changes", String(B.changes)),
      kpi("Right direction over " + (B.hit_horizon || d.horizon) + " days", B.hit_rate_7d == null ? "–" : Math.round(B.hit_rate_7d * 100) + "% of " + B.readings + " readings", B.hit_rate_7d > 0.5 ? "up" : B.hit_rate_7d < 0.5 ? "down" : ""),
      kpi("Long only: total / a year", pctOrDash(L.total, 0) + " / " + pctOrDash(L.a_year, 0), cls(L.total))),
    ...linesChart([{ name: "Strategy", points: B.equity, color: css("--s1") }, { name: "Hold " + c.ticker, points: B.hold_curve, dashed: true, color: css("--hold") }], v => v == null ? "–" : v.toFixed(2) + "×", { log: true, small: true }),
    note("Position decided at each close from that day's score (long above +" + d.enter + ", short below −" + d.enter + "), earning the next day's move; " + (d.cost_per_side * 100).toFixed(3) + "% each way on every change, funding not included. " +
      "Every day shown uses weights fitted only on earlier data (re-fitted every " + d.refit_days + " days on all coins pooled), so this is out of sample, but the signal definitions and thresholds were chosen by hand before any test: treat it as a first pass."));
}

function weightsCard(d) {
  const W = d.weights || {}, rows = (d.signals || []).map(s => ({ ...s, w: W[s.key] || 0 })).sort((a, b) => b.w - a.w);
  const P = d.pooled_backtest;
  return card("Today's weights: " + d.how + (d.train_rows ? " (" + num(d.train_rows) + " coin-days)" : ""),
    el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px" }, ...rows.map(r => el("span", { class: r.w > 0 ? "" : "muted", title: r.means }, r.label + " ", el("b", {}, w1(r.w))))),
    P ? el("div", { class: "kpis", style: "margin-top:10px" }, kpi("Coins backtested", String(P.coins)), kpi("Beat holding the coin", P.beat_hold + " of " + P.coins, P.beat_hold > P.coins / 2 ? "up" : "down"),
      kpi("Median a year: strategy / hold", pct(P.median_a_year, 0) + " / " + pct(P.median_hold_a_year, 0), cls(P.median_a_year - P.median_hold_a_year)),
      kpi("Median Sharpe", P.median_sharpe.toFixed(2)), kpi("Median worst fall", pct(P.median_worst_drop, 0)), kpi("Median 7-day hit rate", Math.round(P.median_hit_rate_7d * 100) + "%", P.median_hit_rate_7d > 0.5 ? "up" : "down")) : null,
    note("A signal earns weight when its rank correlation with the next " + d.horizon + " days' return, over every coin's history, is positive, at least 1.5 standard errors from zero and measured on 100+ active coin-days; weights are the correlations scaled to sum to 1, none above 40%. " +
      (d.weights_drift != null ? "Today's weights differ from the last fitted set by " + Math.round(d.weights_drift * 100) + "% of the total. " : "") + "Hover a name for what the signal means."));
}

// the twenty-signal detail for one coin, judged on SG_H days: the horizon switch, its grid, score day by day, backtest, weights, every coin's table
function signalsDetail(d0, d, c) {
  const hs = el("div", { class: "seg", style: "margin:0 0 6px" }, ...(d0.horizons || [7]).map(h => el("button", { class: h === SG_H ? "on" : "", onclick: () => { SG_H = h; try { sessionStorage.setItem("sg:h", h); } catch (e) {} render(); } }, "Judge on " + h + " days")));
  const intro = card(null, el("div", { class: "kpis" },
      kpi("Leaning buy", String((d.counts || {}).buy || 0), (d.counts || {}).buy ? "up" : ""), kpi("Neutral", String((d.counts || {}).neutral || 0)), kpi("Leaning sell", String((d.counts || {}).sell || 0), (d.counts || {}).sell ? "down" : ""),
      kpi("Signals", (d.signals || []).length + " · judged on " + SG_H + " days"), kpi("Weights re-fitted", "every " + d.refit_days + " days")), hs,
    note("Twenty daily signals on top of the volume zones (where the price sits against them, retests, breaks, the balance of big days, trend, RSI, BTC's trend, unlock windows), each scored −1 to +1, weighted by what it was worth across every coin's past, summed into one score. " +
      "Strong buy ≥ +0.5, lean buy ≥ +" + d.enter + ", lean sell ≤ −" + d.enter + ", strong sell ≤ −0.5. Research, not advice."));
  if (!c || c.status !== "ok" || c.score == null) return [intro, card(null, el("div", { class: "muted" }, !c ? "No signals for this coin." : c.status === "error" ? "Not available right now (" + (c.why || "") + ")." : c.status + ".")), horizonCard(d0)];
  const coinHead = card(c.ticker + " today: " + c.label + " (" + sc2(c.score) + ")",
    el("div", { style: "font-size:20px;font-weight:650;margin:4px 0 6px" }, el("span", { class: SG_CLS[c.label] || "" }, c.label), " ", el("span", { class: "muted", style: "font-size:14px" }, "score " + sc2(c.score) + " · " + px(c.price))),
    el("div", { class: "muted" }, "Pushing it: " + (c.contributions || []).filter(x => x.contribution !== 0).slice(0, 4).map(x => x.label + " " + sc2(x.contribution)).join(" · ")),
    signalGrid(c, d), note("Today = the signal's score at the last close; weight = its share of the final score; push = today × weight. Rank corr. and hit rate: over every coin's history pooled (the record the weight comes from) and for this coin alone."));
  return [intro, coinHead, ...compositeChart(c, d.enter), backtestCard({ ...d, horizon: SG_H }, c), weightsCard({ ...d, horizon: SG_H }), horizonCard(d0),
    card("Every coin's final signal, judged on " + SG_H + " days", signalsTable(d.coins || []), note("Click a row to switch the coin. Strategy and hold figures are each coin's walk-forward backtest."))];
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

// ------------------------------------------------------------------ the coin's signal board: the BTC spot signal's set-up, per coin
const BOARD_CLS = { "STRONG BUY": "up", BUY: "up", NEUTRAL: "", SELL: "down", "STRONG SELL": "down" };
const sgn2 = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
function boardCard(f) {
  const b = f.board;
  if (!b) return null;
  if (b.status !== "ok") return card(f.ticker + " signal board", note(b.status === "error" ? "Not available right now (" + (b.why || "") + ")." : "Not enough gauges yet: " + (b.why || "") + "."));
  const col = b.action === "BUY" ? "--up" : b.action === "SELL" ? "--down" : "--muted";
  const head = card(f.ticker + " signal board · data for " + b.day,
    el("div", { style: "font-size:28px;font-weight:700;color:var(" + col + ")" }, b.action), el("div", {}, b.words),
    el("div", { class: "kpis", style: "margin-top:10px" }, kpi("Score", sgn2(b.aggregate), cls(b.aggregate)), kpi("Label", b.label, BOARD_CLS[b.label] || ""),
      kpi("vs day before", b.prev == null ? "–" : sgn2(b.aggregate - b.prev), cls(b.aggregate - b.prev)), kpi("vs a week before", b.week == null ? "–" : sgn2(b.aggregate - b.week), cls(b.aggregate - b.week)),
      kpi("Gauges with data", b.n + " of " + ((b.gauges_available || []).length + (b.gauges_missing || []).length)), kpi("In buy / sell zones", b.n_buy + " / " + b.n_sell),
      kpi("Sell signal", b.sell.words, b.sell.state ? "down" : "")),
    el("div", { class: "muted", style: "margin-top:6px" }, "Buy at " + sgn2(b.levels.strong_buy) + " or above · take profit at " + sgn2(b.levels.sell) + " or below. Same set-up as the bot's BTC spot signal; information only, the altcoin engine does not trade it."));
  // score bars (left) against the price (right), with the first day of each sell signal marked
  const host = el("div", { class: "chart", style: "height:320px" });
  setTimeout(() => {
    const c = newChart(host, { leftPriceScale: { visible: true, borderVisible: false }, rightPriceScale: { borderVisible: false, mode: 1 } });
    const pxs = c.addLineSeries({ priceScaleId: "right", color: css("--muted"), lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, priceFormat: { type: "custom", formatter: px, minMove: 0.0001 } });
    const sc = c.addHistogramSeries({ priceScaleId: "left", priceFormat: { type: "price", precision: 2, minMove: 0.01 }, base: 0, priceLineVisible: false, lastValueVisible: false });
    const ser = b.series || [];
    pxs.setData(ser.filter(r => r[2] != null).map(r => ({ time: r[0], value: r[2] })));
    sc.setData(ser.filter(r => r[1] != null).map(r => ({ time: r[0], value: r[1], color: r[1] >= b.levels.strong_buy ? css("--up") : r[1] <= b.levels.sell ? css("--s2") : "rgba(128,128,128,.35)" })));
    pxs.setMarkers(ser.filter((r, i) => r[3] > 0 && (i === 0 || ser[i - 1][3] !== r[3])).map(r => ({ time: r[0], position: "aboveBar", color: r[3] === 2 ? css("--down") : css("--s2"), shape: "arrowDown", size: 0.8, text: r[3] === 2 ? "trend break" : "take profit" })));
    syncAdd(c, pxs, ser.filter(r => r[2] != null).map(r => ({ time: r[0], value: r[2] })));
  });
  const chart = card("Score (bars, left) and " + f.ticker + " price (line, right, log), last 2 years", host,
    note("Green bars = buy zone (≥ +" + b.levels.strong_buy + ") · orange = take-profit zone (≤ " + b.levels.sell + ") · arrows = the first day of each sell signal. Score history from " + b.history_from + "."));
  const gauges = card("The gauges today", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Gauge", "Group", "Reading", "Zone", "Score", "Weight"].map((h, i) => el("th", { style: (i > 3 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...b.rows.map(r => el("tr", { title: r.source }, el("td", {}, r.name), el("td", { class: "muted" }, r.group), el("td", {}, r.value), el("td", { class: cls(r.score) }, r.zone),
        el("td", { style: "text-align:right", class: cls(r.score) }, sgn2(r.score)), el("td", { style: "text-align:right" }, r.weight))))),
    (b.gauges_missing || []).length ? note("Without data for this coin: " + b.gauges_missing.join(", ") + ".") : null,
    note("Hover a gauge for its zone thresholds and source. Valuation gauges count double in the score, as on the BTC board."));
  const why = card("Why the score is what it is", ...(b.explain || []).map(t => el("div", { style: "margin:4px 0" }, t)),
    el("div", { style: "margin-top:8px" }, el("b", {}, "Sell checks: "), ...b.sell.checks.flatMap(([ok, t]) => [el("span", { class: ok ? "down" : "muted" }, (ok ? "✓ " : "✗ ") + t), el("br")])));
  const fl = (b.flips || []).length ? card("What would move it", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Gauge", "Buy zone starts", "Fully buy", "Sell zone starts", "Fully sell"].map((h, i) => el("th", { style: (i ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...b.flips.map(r => r.level != null ? el("tr", {}, el("td", {}, r.gauge), el("td", { colspan: 4, style: "text-align:right" }, px(r.level) + " (" + pct(r.level_pct, 0) + " from here): below it the trend-break check is on"))
        : el("tr", {}, el("td", {}, r.gauge), ...["buy_at", "buy_full_at", "sell_at", "sell_full_at"].map(k => el("td", { style: "text-align:right" }, px(r[k]) + " (" + pct(r[k + "_pct"], 0) + ")")))))),
    note("Price levels that move each price-based gauge to the edge of its zones, from today's averages; the other gauges depend on fees, TVL, unlocks and BTC.")) : null;
  const rec = card(f.ticker + " after each zone: median move over the next 30 / 90 / 180 days (zone read the day before)", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Zone", "Days", "30 days", "90 days", "180 days"].map((h, i) => el("th", { style: (i ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...(b.record || []).map(r => el("tr", { style: r.zone === "ALL DAYS" ? "font-style:italic" : "" }, el("td", { class: BOARD_CLS[r.zone] || "" }, r.zone), el("td", { style: "text-align:right" }, r.days),
        ...[30, 90, 180].map(h => el("td", { style: "text-align:right", class: cls(r[h + "d"]) }, r[h + "d"] == null ? "–" : pct(r[h + "d"], 0) + " (" + Math.round(r[h + "d_up"] * 100) + "% up)")))))),
    note("The coin's own history since " + b.history_from + " (Hyperliquid candles), so a few hundred days per zone at best: a sanity check on the zones, not a forecast. The BTC board has four cycles behind it; this has part of one."));
  return el("div", {}, head, chart, gauges, why, fl, rec);
}

// the fitted board: the same gauges, signs and weights learned from their pooled record (walk-forward)
function fittedCard(f, F) {
  const ft = f.board && f.board.fitted;
  if (!ft) return null;
  if (ft.status !== "ok") return card(f.ticker + " fitted board", note(ft.status === "error" ? "Not available right now (" + (ft.why || "") + ")." : "No reading: no gauge has cleared the bar yet (" + (F && F.how_now || "") + ")."));
  const B = ft.backtest || {}, L = ft.backtest_long_only || {};
  const host = el("div", { class: "chart", style: "height:280px" });
  setTimeout(() => {
    const c = newChart(host, { leftPriceScale: { visible: true, borderVisible: false }, rightPriceScale: { borderVisible: false, mode: 1 } });
    const pxs = c.addLineSeries({ priceScaleId: "right", color: css("--muted"), lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, priceFormat: { type: "custom", formatter: px, minMove: 0.0001 } });
    const sc = c.addHistogramSeries({ priceScaleId: "left", priceFormat: { type: "price", precision: 2, minMove: 0.01 }, base: 0, priceLineVisible: false, lastValueVisible: false });
    const ser = ft.series || [];
    pxs.setData(ser.filter(r => r[2] != null).map(r => ({ time: r[0], value: r[2] })));
    sc.setData(ser.filter(r => r[1] != null).map(r => ({ time: r[0], value: r[1], color: r[1] >= 0.5 ? css("--up") : r[1] <= -0.2 ? css("--s2") : "rgba(128,128,128,.35)" })));
    syncAdd(c, pxs, ser.filter(r => r[2] != null).map(r => ({ time: r[0], value: r[2] })));
  });
  return card(f.ticker + " fitted board · " + ft.label + " (" + sgn2(ft.score) + ")",
    el("div", { style: "font-size:22px;font-weight:650;margin-bottom:6px" }, el("span", { class: BOARD_CLS[ft.label] || "" }, ft.label), " ", el("span", { class: "muted", style: "font-size:14px" }, "score " + sgn2(ft.score))),
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Gauge", "Reading", "Zone score", "Learned weight", "Push"].map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...(ft.rows || []).map(r => el("tr", {}, el("td", {}, r.name, r.flipped ? el("span", { class: "pill", style: "margin-left:6px" }, "sign reversed") : null), el("td", {}, r.value),
        el("td", { style: "text-align:right", class: cls(r.zone_score) }, sgn2(r.zone_score)), el("td", { style: "text-align:right", class: r.weight < 0 ? "down" : r.weight > 0 ? "" : "muted" }, sgn2(r.weight)),
        el("td", { style: "text-align:right", class: cls(r.push) }, sgn2(r.push)))))),
    note((F && F.how_now ? "Weights today: " + F.how_now + ". " : "") + "A negative weight means the zone has been backwards on these coins: being 'washed out' kept falling, so the gauge now counts the other way. Same five levels as the board above."),
    host, note("Fitted score (bars, left) and price (right, log), last 2 years; every day uses weights fitted on earlier data" + (ft.history_from ? ", from " + ft.history_from : "") + "."),
    B.total != null ? el("div", { class: "kpis", style: "margin-top:8px" },
      kpi("Walk-forward, long + short", pct(B.total, 0) + " vs hold " + pct(B.hold, 0), cls(B.total - B.hold)), kpi("A year: strategy / hold", pctOrDash(B.a_year, 0) + " / " + pctOrDash(B.hold_a_year, 0), cls((B.a_year || 0) - (B.hold_a_year || 0))),
      kpi("Sharpe", B.sharpe == null ? "–" : B.sharpe.toFixed(2)), kpi("Worst fall: strategy / hold", pct(B.worst_drop, 0) + " / " + pct(B.hold_worst_drop, 0)),
      kpi("Right over " + B.hit_horizon + " days", B.hit_rate == null ? "–" : Math.round(B.hit_rate * 100) + "% of " + B.readings), kpi("Long only: total / a year", pctOrDash(L.total, 0) + " / " + pctOrDash(L.a_year, 0), cls(L.total))) : note("Not enough history after the first fit for a backtest."),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Fitted zone", "Days", "30 days", "90 days", "180 days"].map((h, i) => el("th", { style: (i ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...(ft.record || []).map(r => el("tr", { style: r.zone === "ALL DAYS" ? "font-style:italic" : "" }, el("td", { class: BOARD_CLS[r.zone] || "" }, r.zone), el("td", { style: "text-align:right" }, r.days),
        ...[30, 90, 180].map(h => el("td", { style: "text-align:right", class: cls(r[h + "d"]) }, r[h + "d"] == null ? "–" : pct(r[h + "d"], 0) + " (" + Math.round(r[h + "d_up"] * 100) + "% up)")))))),
    note("Long above +0.2, short below −0.2 at the close, next day's move, 0.095% a side on every change; weights re-fitted every " + (F && F.refit_days || 30) + " days on every coin's past, so the backtest is out of sample for the weights but not for the gauge definitions or the two levels."));
}

function fittedRecordCard(F) {
  if (!F || !F.record) return null;
  const W = F.weights_now || {};
  return card("Each gauge's record across every coin, and the weight it earns (" + (F.how_now || "") + ")",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Gauge", "Group", "Active coin-days", "Rank corr. with " + F.horizon + "-day return", "t", "After a buy reading", "After a sell reading", "Hit rate", "Weight"].map((h, i) => el("th", { style: (i > 1 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
      ...F.record.map(r => el("tr", {}, el("td", {}, r.name), el("td", { class: "muted" }, r.group), el("td", { style: "text-align:right" }, num(r.days_active)),
        el("td", { style: "text-align:right", class: cls(r.ic) }, r.ic == null ? "–" : (r.ic > 0 ? "+" : "") + r.ic.toFixed(3)), el("td", { style: "text-align:right" }, r.t == null ? "–" : r.t.toFixed(1)),
        el("td", { style: "text-align:right", class: cls(r.after_buy) }, pctOrDash(r.after_buy, 1)), el("td", { style: "text-align:right", class: cls(r.after_sell) }, pctOrDash(r.after_sell, 1)),
        el("td", { style: "text-align:right", class: r.hit_rate > 0.5 ? "up" : r.hit_rate < 0.5 ? "down" : "" }, r.hit_rate == null ? "–" : Math.round(r.hit_rate * 100) + "%"),
        el("td", { style: "text-align:right", class: (W[r.key] || 0) < 0 ? "down" : (W[r.key] || 0) > 0 ? "" : "muted" }, W[r.key] == null ? "0" : sgn2(W[r.key])))))),
    note("A gauge's zone score (+1 buy zone to −1 sell zone) against the coin's return over the next " + F.horizon + " days, every coin pooled (" + num(F.train_rows || 0) + " coin-days). A negative correlation means the zone has been backwards. " +
      "Weight = the correlation when it is 1.5+ standard errors from zero on 100+ active coin-days, scaled so the absolute weights sum to 1 (none above 40%)." +
      (F.pooled_backtest ? " Trading the fitted score walk-forward: beat holding on " + F.pooled_backtest.beat_hold + " of " + F.pooled_backtest.coins + " coins, median Sharpe " + (F.pooled_backtest.median_sharpe == null ? "–" : F.pooled_backtest.median_sharpe.toFixed(2)) + ", median worst fall " + pctOrDash(F.pooled_backtest.median_worst_drop, 0) + ", median hit rate " + (F.pooled_backtest.median_hit_rate == null ? "–" : Math.round(F.pooled_backtest.median_hit_rate * 100) + "%") + "." : "")));
}

function boardsTable(coins) {
  const H = ["Coin", "BTC-style board", "Score", "Sell signal", "Fitted board", "Score", "Fitted walk-forward: a year", "Hold a year", "Hit rate", "Gauges"];
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: ([2, 5, 6, 7, 8, 9].includes(i) ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...coins.map(c => { if (c.status !== "ok") return el("tr", {}, el("td", {}, el("b", {}, c.ticker)), el("td", { colspan: H.length - 1, class: "muted" }, c.status === "error" ? "Not available right now (" + (c.why || "") + ")." : c.status + "."));
      const b = c.board, ft = c.fitted || {}, B = ft.backtest || {};
      return el("tr", { style: "cursor:pointer", onclick: () => pickSig(c.ticker) },
        el("td", {}, el("b", {}, c.ticker), " ", el("span", { class: "muted" }, c.group === "Memecoin" ? "meme" : "candidate")),
        el("td", { class: BOARD_CLS[b.label] || "" }, b.label), el("td", { style: "text-align:right", class: cls(b.aggregate) }, sgn2(b.aggregate)), el("td", { class: b.sell.state ? "down" : "muted" }, b.sell.words),
        el("td", { class: BOARD_CLS[ft.label] || "muted" }, ft.status === "ok" ? ft.label : "no reading"), el("td", { style: "text-align:right", class: cls(ft.score) }, ft.status === "ok" ? sgn2(ft.score) : "–"),
        el("td", { style: "text-align:right", class: cls(B.a_year) }, pctOrDash(B.a_year, 0)), el("td", { style: "text-align:right", class: cls(B.hold_a_year) }, pctOrDash(B.hold_a_year, 0)),
        el("td", { style: "text-align:right", class: B.hit_rate > 0.5 ? "up" : B.hit_rate < 0.5 ? "down" : "" }, B.hit_rate == null ? "–" : Math.round(B.hit_rate * 100) + "%"),
        el("td", { style: "text-align:right" }, b.n)); })));
}

// the two boards for one coin, as folded sections, plus every coin's boards table
function boardSections(d, c) {
  const F = d.fitted || {};
  if (!c || c.status !== "ok") return [fold(SIG_COIN + " signal board", true, card(null, el("div", { class: "muted" }, !c ? "No board for this coin." : c.status === "error" ? "Not available right now (" + (c.why || "") + ")." : c.status + ".")))];
  const f = { ticker: c.ticker, board: { ...c.board, fitted: c.fitted } };
  return [fold(c.ticker + " signal board: the BTC spot signal's set-up, nine gauges in hand-set zones", true, boardCard(f),
      note("Same set-up as the bot's BTC spot signal, per coin; valuation gauges count double. Information only, not advice.")),
    fold(c.ticker + " fitted board: the same gauges with signs and weights learned from their record across every coin", false,
      card(null, el("div", { class: "kpis" }, kpi("Fitted: buy / sell", ((d.counts || {}).fitted || {}).buy + " / " + ((d.counts || {}).fitted || {}).sell + " of " + ((d.counts || {}).fitted || {}).readings),
        kpi("Gauges with the sign reversed", (F.flipped || []).length ? F.flipped.join(", ") : "none"), kpi("Weights re-fitted", "every " + (F.refit_days || 30) + " days")),
        note("The fitted board keeps the gauges but learns each one's sign and weight from its record across every coin here, re-fitted every " + (F.refit_days || 30) + " days on earlier data only.")),
      fittedCard(f, F), fittedRecordCard(F), card("Every coin's two boards", boardsTable(d.coins || []), note("Click a row to switch the coin. Fitted walk-forward = trading the fitted score long + short with costs over the days it existed, against holding the coin.")))];
}

function unlockMiniCard(f) {
  const U = f.unlocks;
  if (!U) return null;
  const nx = U.coming[0];
  return card("Token unlocks", el("div", { class: "kpis" },
      kpi("Next unlock", nx ? nx.date : "–"), kpi("Amount", nx ? mTok(nx.amount_m) + " " + f.ticker : "–"), kpi("Added to circulating", nx && nx.pct_of_circulating != null ? "+" + nx.pct_of_circulating + "%" : "–", nx && nx.pct_of_circulating >= 1 ? "down" : ""),
      kpi("Unlocks in the last 90 days", String(U.recent.length))),
    el("div", { class: "muted" }, nx ? "To " + nx.who + " (" + nx.kinds + "). " : "", el("a", { href: "#coins", onclick: e => { e.preventDefault();
      const f = document.getElementById("unlock-study"); if (!f) return; const h = f.querySelector("h2"), b = h && h.nextElementSibling; if (b && b.style.display === "none") h.click(); f.scrollIntoView({ behavior: "smooth", block: "start" }); } },
      "Full schedule and what the price did around every unlock, below")));
}

// the volume zones for one coin (candles, big days, the bands they left) and every coin against its zones
function volumeDetail(d, c) {
  const C = d.counts || {}, S = d.settings || {};
  const head = card(null, el("div", { class: "kpis" },
      kpi("Coins with candles", (C.coins || 0) + " of " + (d.coins || []).length), kpi("Inside or just over support", String(C["inside support"] || 0), C["inside support"] ? "up" : ""),
      kpi("Inside or just under resistance", String(C["under resistance"] || 0), C["under resistance"] ? "down" : ""),
      kpi("Big day = volume ≥", S.mult + "× the " + S.lookback + "-day median")),
    note("A big-volume day with an up close leaves a support zone (its open-to-close range); with a down close, a resistance zone. Mechanical and recomputed every 6 hours; research, not advice."));
  if (!c || c.status !== "ok") return [head, card(null, el("div", { class: "muted" }, !c ? "No candles for this coin." : c.status === "error" ? "Not available right now (" + (c.why || "") + ")." : c.status + ".")), card("Every coin against its zones", volumeTable(d.coins || []))];
  const rng = el("div", { class: "seg", style: "margin-bottom:6px" }, ...[[180, "6 months"], [365, "1 year"], [400, "Whole window"]].map(([v, l]) => el("button", { class: v === VZ_DAYS ? "on" : "", onclick: () => { VZ_DAYS = v; render(); } }, l)));
  const chart = card(c.ticker + ": daily candles, big-volume days and the zones they left (" + c.market + " on Hyperliquid)", rng, zoneChart(c, VZ_DAYS),
    el("div", { class: "muted", style: "margin-top:6px" }, zoneReadLine(c)),
    note("▲ / ▼ = a day with " + S.mult + "× or more the usual volume (label = how many times); up close = buy day, down close = sell day. Green band = support left by a buy day, red = resistance left by a sell day, from the day's open to its close; " +
      "a band ends when a close goes " + S.break_atr + " ATR through it or after " + S.max_age + " days (faded = ended). Orange squares = token unlocks (ENA). Volume is Hyperliquid's perp volume in dollars."));
  return [head, chart, zoneStatsCard(c), card("Every coin against its zones", volumeTable(d.coins || []), note("Click a row to switch the coin. 'Where it sits' reads +/− 3% from the nearest zone."))];
}

// ENA's unlock study: the schedule, the next unlock, what the price did around each one, simple rules with a placebo, the date check
function unlockCards(u) {
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
}
const DATA = {};                     // one download per coin tab; a failure is retried on the next visit
const coinData = t => DATA[t] || (DATA[t] = api(t).catch(e => { delete DATA[t]; throw e; }));

async function coinView(t) {
  const f = await coinData(t);
  if (!f.series || !f.series.price) return [header(f), card(null, el("div", { class: "muted" }, "Not available right now: prices are loading in the background."), stale(f))];
  const S = f.series;
  return [header(f), card(null, strip(f)), boardCard(f), fittedCard(f, { how_now: f.board && f.board.fitted_how, refit_days: 30 }), zoneCard(f), unlockMiniCard(f), notesCard(f),
    card(f.ticker + " and BTC rebased to the same start (log)", ...linesChart([{ name: f.ticker, points: S.price }, { name: "BTC, rebased", points: S.btc_indexed, dashed: true, color: css("--hold") }], px, { log: true })),
    el("div", { class: "grid2" },
      card(f.ticker + " ÷ BTC (log): rising = beating BTC", ...linesChart([{ name: f.ticker + "/BTC", points: S.ratio }], v => v == null ? "–" : v.toPrecision(3), { log: true, small: true })),
      card("RSI 14: against BTC (solid) and in USD (dashed)", ...linesChart([{ name: "RSI vs BTC", points: S.rsi_vs_btc }, { name: "RSI (USD)", points: S.rsi, dashed: true }], r1, { small: true, hlines: [30, 50, 70] }),
        note("Above 70: has run hard. Below 30: washed out.")),
      card("Market cap", ...linesChart([{ name: "Market cap", points: S.market_cap }], usdBig, { small: true }))),
    section("Fundamentals"), ...fundamentalsCard(f), section("Projection to end-2028"), ...projectionCards(f)];
}

// ---- the Signals tab's overview: one row per coin with every reading
const SIG_ORDER = { "strong buy": 2, "STRONG BUY": 2, "lean buy": 1, BUY: 1, neutral: 0, NEUTRAL: 0, "lean sell": -1, SELL: -1, "strong sell": -2, "STRONG SELL": -2 };
function overviewTable(tickers, Z, Bd, Sg, V) {
  const H = ["Coin", "Buy zone", "BTC-style board", "Fitted board", "Twenty signals (" + SG_H + " days)", "Volume zones", "Price"];
  const lc = { 1: "up", "-1": "down", 0: "" };
  const score = t => { const b = Bd[t], f = b && b.fitted, s = Sg[t]; return (b && b.status === "ok" ? SIG_ORDER[b.board.label] || 0 : 0) + (f && f.status === "ok" ? SIG_ORDER[f.label] || 0 : 0) + (s && s.status === "ok" ? SIG_ORDER[s.label] || 0 : 0); };
  const rows = tickers.slice().sort((a, b) => score(b) - score(a));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...H.map((h, i) => el("th", { style: (i === 6 ? "text-align:right;" : "") + "white-space:nowrap" }, h))),
    ...rows.map(t => { const z = Z[t], b = Bd[t], f = b && b.fitted, s = Sg[t], v = V[t], grp = (b || s || v || z || {}).group;
      const miss = x => el("span", { class: "muted" }, x && x.status && x.status !== "ok" ? (x.status === "error" ? "n/a" : x.status) : "–");
      return el("tr", { style: "cursor:pointer" + (t === SIG_COIN ? ";font-weight:650" : ""), onclick: () => pickSig(t) },
        el("td", {}, el("b", {}, t), " ", el("span", { class: "muted" }, grp === "Memecoin" ? "meme" : "candidate")),
        z && z.top != null ? el("td", { class: ZCLS[z.status] || "muted" }, z.status + (z.status === "above zone" ? " (" + pAbs(z.vs_top) + " above)" : "")) : el("td", {}, miss(z)),
        b && b.status === "ok" ? el("td", { class: BOARD_CLS[b.board.label] || "" }, b.board.label, " ", el("span", { class: "muted" }, sgn2(b.board.aggregate))) : el("td", {}, miss(b)),
        f && f.status === "ok" ? el("td", { class: BOARD_CLS[f.label] || "" }, f.label, " ", el("span", { class: "muted" }, sgn2(f.score))) : el("td", {}, miss(f || b)),
        s && s.status === "ok" && s.score != null ? el("td", { class: SG_CLS[s.label] || "" }, s.label, " ", el("span", { class: "muted" }, sc2(s.score))) : el("td", {}, miss(s)),
        v && v.status === "ok" ? el("td", { class: lc[v.lean] || "" }, v.read) : el("td", {}, miss(v)),
        el("td", { style: "text-align:right" }, px((v && v.price) || (z && z.price)))); })));
}

const VIEWS = {
  async sectors() {
    const [d, rot, m] = await Promise.all([api("sectors"), api("rotation").catch(() => null), api("metrics").catch(() => null)]);
    const seg = el("div", { class: "seg" }, ...d.cycles.map(c => el("button", { class: c.n === cycleN ? "on" : "", onclick: () => { cycleN = c.n; render(); } }, "Cycle " + c.n)));
    const c = d.cycles.find(x => x.n === cycleN);
    const sectorCol = c.columns[0];
    const bars = c.rows.flatMap(r => r._multiples.filter(m => m.x > 0).map(m => ({ cat: (m.label ? m.label + " · " : "") + r[sectorCol].split(" (")[0].slice(0, 22), x: m.x })));
    const mult = bars.length ? card("Peak multiples in this cycle (log scale)", ...svgBarsLog(bars)) : null;
    const tbl = card(c.heading, para(c.intro), table(c.columns, c.rows), para(c.after));
    const cross = card("Cross-cycle comparison", para(d.cross_cycle.intro), table(d.cross_cycle.columns, d.cross_cycle.rows));
    const top = rot ? [statusCard(rot), rotationTimeline(rot)] : [card(null, el("div", { class: "muted" }, "The sector status is not available right now."))];
    const usage = m ? fold("The usage behind the status: DeFi TVL, stablecoin supply, Hyperliquid, DEX volume (live)", false, ...metricsCards(m)) : null;
    const doc = fold("The doc's sector tables, cycle by cycle", false, card(null, seg, el("div", { class: "muted" }, "Pick a cycle. Figures are the doc's, approximate before 2024.")), tbl, mult, cross);
    return [...top, usage, doc];
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
      el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Scenario", "Bear BTC", "Base BTC", "Bull BTC"].map((h, i) => el("th", { style: i ? "text-align:right" : "" }, h))),
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
  async coins() {
    const pick = card(null, el("div", { class: "seg", style: "flex-wrap:wrap" }, ...CANDS.map(x => el("button", { class: x === COIN ? "on" : "", onclick: () => openCoin(x) }, x))),
      note("One candidate in full: its signal board, buy zone, price against BTC, the case for it, fundamentals and the projection to end-2028" + (COIN === "ENA" ? ", and the unlock study at the bottom" : "") + ". The other candidates are on the Candidates tab."));
    const body = await coinView(COIN.toLowerCase());
    const extra = [];
    if (COIN === "ENA") {
      try { const u = await api("unlocks"); extra.push(el("div", { id: "unlock-study" }, fold("ENA token unlocks: the schedule and what the price did before, into and after each one", false, ...unlockCards(u)))); }
      catch (e) { extra.push(card(null, el("div", { class: "muted" }, "The unlock study is not available right now (" + e.message + ")."))); }
    }
    return [pick, ...body, ...extra];
  },
  async signals() {
    const [z, b, s0, v] = await Promise.all(["zones", "boards", "signals", "volume"].map(k => api(k).catch(e => ({ error: e.message, coins: [] }))));
    if (!(s0.horizons || []).includes(SG_H)) SG_H = s0.horizon || 7;
    const s = atHorizon(s0, SG_H);
    const by = d => Object.fromEntries((d.coins || []).map(c => [c.ticker, c]));
    const Z = by(z), Bd = by(b), Sg = by(s), V = by(v);
    const tickers = [...new Set([...(z.coins || []), ...(b.coins || []), ...(s.coins || []), ...(v.coins || [])].map(c => c.ticker))];
    if (!tickers.length) return [card(null, el("div", { class: "muted" }, "Candles and prices are loading in the background, back in a few minutes."), stale(b))];
    const has = t => (Bd[t] || {}).status === "ok" || (Sg[t] || {}).status === "ok" || (V[t] || {}).status === "ok";
    if (!SIG_COIN || !tickers.includes(SIG_COIN)) SIG_COIN = tickers.find(has) || tickers[0];
    const zc = z.counts || {}, bc = (b.counts || {}).classic || {}, fc = (b.counts || {}).fitted || {}, sc = s.counts || {}, vc = v.counts || {};
    const head = card(null, el("div", { class: "kpis" },
        kpi("In their buy zone", (zc["in zone"] || 0) + " of " + (z.coins || []).length, zc["in zone"] ? "up" : ""),
        kpi("BTC-style boards: buy / sell", (bc.buy ?? "–") + " / " + (bc.sell ?? "–")), kpi("Fitted boards: buy / sell", (fc.buy ?? "–") + " / " + (fc.sell ?? "–")),
        kpi("Twenty signals: leaning buy / sell", (sc.buy ?? "–") + " / " + (sc.sell ?? "–")),
        kpi("Volume zones: over support / under resistance", (vc["inside support"] ?? "–") + " / " + (vc["under resistance"] ?? "–"))),
      note("Five mechanical readings per coin, each explained in its section below: the buy zone (price against its 200-day average and the base case), the BTC-style signal board (nine gauges in hand-set zones), " +
        "the fitted board (the same gauges weighted by their record), the twenty daily signals on the volume zones, and where the price sits against its volume zones. Research, not advice."));
    const overview = card("Every coin's readings today", overviewTable(tickers, Z, Bd, Sg, V), note("Sorted by how many readings lean to buying. Click a row for the coin's boards, signals and zones below."));
    const pick = card(null, el("div", { class: "seg", style: "flex-wrap:wrap" }, ...tickers.map(t => el("button", { class: t === SIG_COIN ? "on" : "", onclick: () => pickSig(t) }, t))));
    const zones = fold("Buy zones for every coin: top, mid and floor", false, zonesTable(z.coins || []),
      note("Zone top: the coin's 200-day average price; for HYPE, ENA, SOL and NEAR, half the base-case price at end-2028 when that is lower, so the base case " +
        "at least doubles from the top of the zone. Floor: the lowest close of the last 365 days; mid: half-way, for staged entries. Memecoins have no " +
        "projection, so their top is the 200-day average alone. 'No zone' = the base case does not double from any price of the last year. Recomputed daily from the same prices as the other tabs."));
    return [head, overview, pick, ...boardSections(b, Bd[SIG_COIN]), fold(SIG_COIN + ": twenty daily signals on the volume zones, weighted into one score", false, ...signalsDetail(s0, s, Sg[SIG_COIN])),
      fold(SIG_COIN + ": volume zones, the big days and the bands they left", false, ...volumeDetail(v, V[SIG_COIN])), zones, stale(b), stale(v)];
  },
  async memes() {
    const [d, sn] = await Promise.all([api("basket"), api("season").catch(() => ({}))]);
    const live = (d.coins || []).filter(c => c.kpi);
    const best = live.slice().sort((a, b) => (b.kpi.vs_btc_90d ?? -9) - (a.kpi.vs_btc_90d ?? -9))[0];
    const K = sn.kpi, rules = sn.rules || {};
    const head = card(null, K ? el("div", { style: "font-size:20px;font-weight:650;margin-bottom:6px" }, "Meme season reading: ", el("span", { class: STATE[K.state] || "" }, K.state)) : null,
      el("div", { class: "kpis" },
        ...(K ? [kpi("Basket vs BTC, 90 days", pct(K.vs_btc_90d, 0), cls(K.vs_btc_90d)), kpi("Basket vs BTC, 30 days", pct(K.vs_btc_30d, 0), cls(K.vs_btc_30d)),
          kpi("RSI of basket ÷ BTC", r1(K.rsi_vs_btc), rsiCls(K.rsi_vs_btc)), kpi("Basket ÷ BTC from its 1-year high", pct(K.from_high, 0), cls(K.from_high))] : []),
        kpi("Basket market cap", usdBig(d.basket_mcap)), kpi("Coins in the basket", live.length + " of " + (d.coins || []).length),
        kpi("Beating BTC over 90 days", live.filter(c => (c.kpi.vs_btc_90d || 0) > 0).length + " of " + live.length),
        best ? kpi("Strongest vs BTC, 90 days", best.ticker + " " + pct(best.kpi.vs_btc_90d, 0), cls(best.kpi.vs_btc_90d)) : null),
      note("Prices as of " + (d.as_of || "–") + ". " + (K ? "Meme season: the basket has beaten BTC by " + Math.round((rules.hot || 0.25) * 100) + "%+ over 90 days, or its RSI against BTC is 70+. Out of season: it trails by " +
        Math.round(-(rules.cold || -0.25) * 100) + "%+ and the RSI is under 50. In between otherwise. Mechanical, not a forecast." : "The season reading needs the basket's prices; they are loading in the background.") +
        (sn.coins_missing && sn.coins_missing.length ? " Not in today's figures (loading): " + sn.coins_missing.join(", ") + "." : "")));
    const tbl = card("The basket", basketTable(d.coins || []),
      note("Click a column to sort. RSI above 70 (red) = has run hard; below 30 (green) = washed out. Beta: how much the coin moves for each 1% BTC move (clamped 0.5-3)."));
    const rebased = card("Each coin and BTC, rebased to 100 a year ago (log)",
      ...linesChart([...live.map(c => ({ name: c.ticker, points: c.rebased })), { name: "BTC", points: d.btc_rebased, dashed: true, color: css("--hold"), width: 2 }],
        v => v == null ? "–" : num(v, 0), { log: true }),
      note("Above BTC's dashed line: beat holding Bitcoin over the period shown. Click a name in the legend to hide it."));
    const season = K ? fold("Meme season: the basket against BTC", true,
      card("Basket market cap ÷ BTC market cap (log): rising = memes beating BTC", ...linesChart([{ name: "Basket ÷ BTC", points: sn.ratio }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { log: true })),
      el("div", { class: "grid2" },
        card("RSI 14 of basket ÷ BTC", ...linesChart([{ name: "RSI vs BTC", points: sn.rsi_vs_btc }], r1, { small: true, hlines: [30, 50, 70] })),
        card("Equal-weight basket and BTC, rebased to 100 (log)", ...linesChart([{ name: "Memecoins, equal weight", points: sn.equal_weight }, { name: "BTC", points: sn.btc_rebased, dashed: true, color: css("--hold") }], v => v == null ? "–" : num(v, 0), { log: true, small: true })),
        card("Market caps: basket (left) and BTC (right)", ...linesChart([{ name: "Basket", points: sn.basket_mcap, axis: "left" }, { name: "BTC", points: sn.btc_mcap, color: css("--hold") }], usdBig, { small: true }))),
      (() => { const log = sn.share_log || []; return card("Memecoins' share of the whole crypto market (CoinGecko 'Meme' category ÷ total market cap)",
        ...(log.length > 1 ? linesChart([{ name: "Meme share", points: log.map(r => [r.t, r.share]) }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { small: true, sync: false })
          : [el("div", { class: "kpis" }, kpi("Meme share today", log.length ? (log[0].share * 100).toFixed(2) + "%" : "–"), kpi("Meme sector market cap", log.length ? usdBig(log[0].meme_mcap) : "–"))]),
        note("CoinGecko has no free history of either figure, so this is logged once a day from the first deploy and grows from there.")); })()) : null;
    const sparks = live.length ? fold("Each coin, 90 days", false, el("div", { class: "grid2" }, ...live.map(sparkCard))) : null;
    return [head, tbl, rebased, season, sparks, stale(d), stale(sn)];
  },
};
function metricsCards(d) {
    const R = d.research, L = d.latest || {};
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
    const tbl = fold("Common metrics of cycle winners (the doc)", false, para(R.intro), table(R.columns, R.rows), para(R.after));
    return [head, grid, top, tbl];
}

// one candidate coin on the Candidates tab: links, KPI strip, 90-day sparkline, and on demand its charts; the four coins with a full
// page open it on the Coins tab
function coinRow(c, px, r1, rsiCls) {
  const head = el("div", { style: "display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline" },
    el("b", {}, c.name, " ", el("span", { class: "muted" }, c.ticker)),
    c.links && c.links.coinmarketcap ? link("CoinMarketCap", c.links.coinmarketcap) : null, c.links && c.links.defillama ? link("DefiLlama", c.links.defillama) : null,
    c.links && c.links.coingecko ? link("CoinGecko", c.links.coingecko) : null, c.note ? el("span", { class: "pill" }, c.note) : null,
    CANDS.includes(c.ticker) ? el("a", { href: "#coins", style: "font-weight:600", onclick: e => { e.preventDefault(); openCoin(c.ticker); } }, "Full page →") : null);
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
  return [el("div", { style: "margin-top:8px" }, proj), coinFundamentals(f, px), el("div", { class: "grid2", style: "margin-top:8px" }, price, rsi, mcap), stale(f)].filter(Boolean);
}

// fees, TVL and supply against price, each rebased to 100 at the start of the year, plus the multiples and the unlock schedule
function coinFundamentals(f, px) {
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
