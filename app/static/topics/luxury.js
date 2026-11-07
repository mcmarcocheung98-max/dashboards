// Luxury Tracker: watches and bags on the second-hand market. Data from /api/luxury/<overview|watches|bags|roi|heat|fees>; helpers from topic.html.
(() => {
const dateOf = s => s ? new Date(s).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) : "–";
const x = (v, d = 2) => v == null ? "–" : num(v, d) + "×";
const prem = v => v == null ? "–" : pct(v, 0);
const premCls = v => v == null ? "" : v > 0.02 ? "up" : v < -0.02 ? "down" : "";
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const srcCell = (url, note) => el("td", { class: "wrap" }, url ? link(host(url), url) : "–", note ? " · " + note : "");
const fxNote = d => d && d.fx_fallback ? el("div", { class: "warn", style: "margin-top:6px" }, "Exchange rates are not reachable right now: USD, CHF and EUR prices converted at fixed approximate rates.") : null;
const verifyNote = (n, total) => n ? el("div", { class: "muted", style: "margin-top:6px" }, n + " of " + total + " hand-entered points are marked verify (entered from an article or from memory, not confirmed on the cited page).") : null;
// a list price as a step: hold each price until the next change, and to today
const step = (pts, end) => { const out = []; pts.forEach((p, i) => { out.push(p); const nx = pts[i + 1]; out.push([(nx ? nx[0] : end) - 86400, p[1]]); }); return out; };
const today = () => Math.floor(Date.now() / 86400000) * 86400;
const words = { watch: "Watches", bag: "Bags" };
// a bar per month from Dec 2019 to today on the sparse hand-entered charts, so the shared date axis lands where it is set
const monthsWs = () => { const out = []; const d = new Date(Date.UTC(2019, 11, 1)); const end = Date.now(); while (d.getTime() <= end) { out.push(Math.floor(d.getTime() / 1000)); d.setUTCMonth(d.getUTCMonth() + 1); } return out; };

function itemCard(it) {
  const L = it.latest;
  return card(it.name + (it.reference ? " · " + it.reference : ""),
    el("div", { class: "kpis" },
      kpi("Retail now" + (it.retail_date ? " (since " + dateOf(it.retail_date) + ")" : ""), gbp(it.retail_now)),
      kpi(L ? "Latest resale, " + L.kind + (L.condition ? ", " + L.condition : "") + " (" + dateOf(L.date) + ")" : "Latest resale", L ? gbp(L.price) : "–"),
      kpi("Premium to retail", prem(it.premium), premCls(it.premium)),
      kpi("Resale, change on a year", pct(it.change_1y, 0), cls(it.change_1y))),
    el("div", { class: "muted", style: "margin-top:6px" }, (L && L.platform ? L.platform + " · " : "") + it.n_points + " resale points" + (it.n_verify ? ", " + it.n_verify + " to verify" : "") + (it.note ? " · " + it.note : ""),
      it.url ? [" · ", link("brand page", it.url)] : null, L && L.source ? [" · ", link("resale source", L.source)] : null));
}

function premiumChart(items, fmt) {
  return linesChart(items.filter(i => i.premium_series && i.premium_series.length).map(i => ({ name: i.reference || i.name, points: i.premium_series })), fmt || (v => pct(v, 0)), { hlines: [0], whitespace: monthsWs() });
}

function itemChart(it) {
  const end = today();
  const series = [{ name: "Retail (list price)", points: step(it.retail_points || [], end + 86400), color: css("--s2"), width: 2 },
    { name: "Resale", points: it.resale_series || [], color: css("--s1") }];
  return card(it.name + (it.reference ? " · " + it.reference : ""), ...linesChart(series, v => gbp(v), { whitespace: monthsWs() }),
    note("Retail: the list price in force (GBP, converted at the month's rate where the source is in another currency). Resale: hand-entered asking or sold points. Hover for values; the dates follow the other charts."));
}

function catTable(items, isBag) {
  return table([isBag ? "Bag" : "Reference", "Retail", "Resale (latest)", "Premium", "1y", "3y", "Platform", "Points"],
    items.map(i => el("tr", {}, el("td", {}, isBag ? i.name : (i.reference || i.name) + " " + (i.model || "")), el("td", {}, gbp(i.retail_now)),
      el("td", {}, i.latest ? gbp(i.latest.price) + " (" + i.latest.kind + ")" : "–"), el("td", { class: premCls(i.premium) }, prem(i.premium)),
      el("td", { class: cls(i.change_1y) }, pct(i.change_1y, 0)), el("td", { class: cls(i.change_3y) }, pct(i.change_3y, 0)),
      el("td", {}, i.latest && i.latest.platform ? i.latest.platform : "–"), el("td", {}, i.n_points + (i.n_verify ? " (" + i.n_verify + " verify)" : "")))));
}

function catView(d, cat) {
  const items = d.items || [], isBag = cat === "bag";
  const head = card(words[cat] + ": the basket",
    followHead([{ label: isBag ? "Basket resale / retail (median)" : "Basket premium to retail (median)", points: isBag ? d.ratio : d.premium, fmt: isBag ? v => x(v, 2) : v => prem(v), cls: isBag ? v => v >= 1 ? "up" : v < 0.7 ? "down" : "" : premCls },
      { label: "Resale index (equal weight)", points: d.index, fmt: v => num(v, 0), delta: { lag: "1y" } },
      { label: "Share of items above retail", points: d.share_above, fmt: v => (v * 100).toFixed(0) + "%" }], { latest: "Latest month" }),
    asOf(d), stale(d), fxNote(d));
  const bk = card("Basket: premium to retail and the resale index, month by month",
    ...linesChart([{ name: isBag ? "Resale / retail (median)" : "Premium to retail (median)", points: isBag ? d.ratio : d.premium, color: css("--s1") },
      { name: "Resale index (first month = 100)", points: d.index, axis: "left", color: css("--s3") }], isBag ? v => x(v, 2) : v => prem(v), { hlines: isBag ? [1] : [0] }),
    note("Each month: every item's last resale point within 18 months against the list price then in force; the median across items (needs " + (d.need || 3) + "). The index chain-links the items' resale prices equal-weight, so an item joining does not jump it."));
  const pc = card("Premium to retail per " + (isBag ? "bag" : "reference"), ...premiumChart(items), note("Resale price divided by the list price in force on that date, minus one. Above zero: selling for more than new."));
  const charts = el("div", { class: "grid2" }, ...items.map(itemChart));
  const tbl = card(words[cat] + ": latest", catTable(items, isBag), verifyNote(items.reduce((a, i) => a + i.n_verify, 0), items.reduce((a, i) => a + i.n_points, 0)), cite(d.cited));
  const out = [head, bk, pc, charts, tbl];
  if (isBag && d.calendar) {
    const years = Object.keys((d.calendar[0] || {}).years || {});
    const sinceOf = r => r.since ? pct(r.since.value, 0) + " since " + dateOf(r.since.date) : "–";
    out.push(card("Retail price increases per brand per year (the price-increase calendar)",
      table(["Brand", ...years, "Last 12 months", "Longer view"], d.calendar.map(r => el("tr", {}, el("td", {}, r.brand), ...years.map(y => el("td", { style: tint(r.years[y], 0.15) }, pct(r.years[y], 0))),
        el("td", { style: tint(r.rise_12m, 0.15) }, r.rise_12m == null ? "no price a year ago" : pct(r.rise_12m, 0)), el("td", { class: "wrap" }, sinceOf(r))))),
      note("List price at the end of each year against the end of the year before, mean across the brand's items here (a partial current year to today). 'Last 12 months' compares the latest list price only with a price dated 9 to 15 months ago; a brand with no such row gets no figure and cannot cross the signal. 'Longer view' is the latest price against the price in force a year ago, dated by the row that set it. Largest rise over the last 12 months: " +
        (d.retail_rise && d.retail_rise.brand ? d.retail_rise.brand + " " + pct(d.retail_rise.value, 0) : "none (" + ((d.retail_rise && d.retail_rise.note) || "no brand has a price a year ago") + ")") + ".")));
  }
  return out;
}

const VIEWS = {
  async overview() {
    const d = await api("overview"), K = d.kpi || {};
    const head = card("Where the second-hand market is",
      followHead([{ label: "Rolex basket: resale premium to retail (median of " + (K.n_watches || 0) + " references)", points: d.rolex_premium, fmt: v => prem(v), cls: premCls },
        { label: "Bag basket: resale / retail (median of " + (K.n_bags || 0) + " bags)", points: d.bags_ratio, fmt: v => x(v, 2), cls: v => v >= 1 ? "up" : v < 0.7 ? "down" : "" },
        { label: "Rolex resale index", points: d.rolex_index, fmt: v => num(v, 0), delta: { lag: "1y" } },
        { label: "Bag resale index", points: d.bags_index, fmt: v => num(v, 0), delta: { lag: "1y" } }], { latest: "Latest month" }),
      el("div", { style: "margin-top:6px;color:var(--ink2)" }, d.where || ""),
      el("div", { class: "muted", style: "margin-top:6px" }, "Heat: watches " + (K.heat_watches == null ? "–" : num(K.heat_watches, 2)) + ", bags " + (K.heat_bags == null ? "–" : num(K.heat_bags, 2)) + " (-2 cold … +2 overheated; see Market heat). " +
        (d.counts ? d.counts.points + " hand-entered resale points; " + d.counts.verify + " price rows (retail and resale) are marked verify." : "")),
      asOf(d), stale(d), fxNote(d));
    const bk = card("The two baskets, month by month", ...linesChart([{ name: "Rolex premium to retail", points: d.rolex_premium, color: css("--s1") },
      { name: "Bags: resale / retail minus 1", points: (d.bags_ratio || []).map(p => [p[0], p[1] - 1]), color: css("--s4") }], v => prem(v), { hlines: [0] }),
      note("Median across each basket's items of the last resale point (within 18 months) against the list price then in force. Above zero: second-hand costs more than new."));
    const w = (d.items || []).filter(i => i.category === "watch"), b = (d.items || []).filter(i => i.category === "bag");
    return [head, bk, changesCard("overview", true), card("Watches"), el("div", { class: "grid2" }, ...w.map(itemCard)), card("Bags"), el("div", { class: "grid2" }, ...b.map(itemCard)),
      card("Read this first", el("div", { class: "muted" }, "Not investment advice. Every price here is a dated, cited hand-entered point: a premium is one resale point against the list price in force that day, not a daily market. Asking prices run above sold prices; condition, box and papers, VAT and import duty on cross-border sales, and the platform's fee all change what a seller nets (see ROI and Fees)."),
        cite(d.cited))];
  },

  async watches() {
    const d = await api("watches");
    return [...catView(d, "watch"), changesCard("watches")];
  },

  async bags() {
    const d = await api("bags");
    return [...catView(d, "bag"), changesCard("bags")];
  },

  async roi() {
    const d = await api("roi"), rows = d.rows || [], items = d.items || [], fees = (d.fees || []).filter(f => f.seller_pct != null);
    const years = [...new Set(rows.map(r => r.buy_date.slice(0, 4)))].sort();
    let year = years[years.length - 1] && years.includes("2022") ? "2022" : years[0];
    const host = el("div", {});
    const sel = (opts, cur, onchange) => el("select", { style: "padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit", onchange },
      ...opts.map(([k, l]) => { const o = el("option", { value: k }, l); if (k === cur) o.selected = true; return o; }));
    const draw = () => {
      const rs = rows.filter(r => r.buy_date.startsWith(year));
      host.replaceChildren(table(["Item", "Bought (retail)", "Sells for today", "Via", "Fee", "Net", "Return", "A year", "S&P 500", "UK CPI", "Real"],
        rs.map(r => el("tr", {}, el("td", {}, r.name), el("td", {}, gbp(r.buy_price) + " on " + dateOf(r.buy_date)), el("td", {}, gbp(r.gross) + " (" + r.sold_kind + ")"), el("td", {}, r.platform + " " + num(r.fee_pct, 1) + "%"),
          el("td", {}, gbp(r.fee)), el("td", {}, gbp(r.net)), el("td", { class: cls(r.ret) }, pct(r.ret, 0)), el("td", { class: cls(r.annual) }, pct(r.annual, 1)),
          el("td", { class: cls(r.spx) }, pct(r.spx, 0)), el("td", {}, pct(r.cpi, 0)), el("td", { class: cls(r.real) }, pct(r.real, 0))))));
    };
    draw();
    const tbl = card("Bought at retail, sold today after the platform's fee",
      el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px" }, el("span", { class: "muted" }, "Bought on 1 January"), sel(years.map(y => [y, y]), year, e => { year = e.target.value; draw(); })),
      host, note("Bought at the list price in force on that day (or at launch, if later), sold at the latest resale point (sold if known, else asking) through the category's usual platform (" +
        Object.entries(d.default_platform || {}).map(([k, v]) => words[k].toLowerCase() + ": " + v).join(", ") + "). S&P 500: price change over the same period, dividends left out" + (d.sp500_source ? " (" + d.sp500_source + ")" : "") +
        ". UK CPI: " + (d.cpi_uk_source || "not available") + ". Real: the return after UK inflation. Shipping, insurance, servicing and VAT or duty are not deducted."),
      missing(d, "sp500", "The S&P 500"), missing(d, "cpi_uk", "UK CPI"), stale(d));
    // ---- the calculator: nothing is stored
    const v = { item: items[0] ? items[0].id : null, date: "2022-01-01", price: null, platform: fees[0] ? fees[0].platform : null };
    const retailAt = (it, t) => { const p = (it.retail_points || []).filter(q => q[0] <= t); return p.length ? p[p.length - 1][1] : null; };
    const at = (pts, t) => { if (!pts) return null; const p = pts.filter(q => q[0] <= t); return p.length ? p[p.length - 1][1] : null; };
    const inp = (key, type, extra = {}) => el("input", { type, value: v[key] == null ? "" : v[key], style: "width:100%;box-sizing:border-box;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit", ...extra });
    const lab = (text, ctl) => el("label", { style: "display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)" }, text, ctl);
    const out = el("div", { class: "kpis" });
    const priceIn = inp("price", "number", { step: 100, oninput: e => { const n = parseFloat(e.target.value); v.price = isNaN(n) ? null : n; compute(false); } });
    const dateIn = inp("date", "date", { onchange: e => { v.date = e.target.value; compute(true); } });
    const itemSel = sel(items.map(i => [i.id, i.name]), v.item, e => { v.item = e.target.value; compute(true); });
    const platSel = sel(fees.map(f => [f.platform, f.platform + " (" + num(f.seller_pct, 1) + "%)"]), v.platform, e => { v.platform = e.target.value; compute(false); });
    const compute = reset => {
      const it = items.find(i => i.id === v.item), f = fees.find(q => q.platform === v.platform);
      const t0 = Math.floor(Date.parse(v.date) / 1000), t1 = today();
      if (reset || v.price == null) { v.price = it ? retailAt(it, t0) : null; priceIn.value = v.price == null ? "" : v.price; }
      const gross = it && it.latest ? it.latest.price : null, feePct = f ? f.seller_pct : 0;
      const fee = gross == null ? null : gross * feePct / 100, net = gross == null ? null : gross - fee;
      const days = (t1 - t0) / 86400, ret = net != null && v.price ? net / v.price - 1 : null;
      const ann = ret != null && days >= 30 && 1 + ret > 0 ? Math.pow(1 + ret, 365.25 / days) - 1 : null;
      const s0 = at(d.sp500, t0), s1 = at(d.sp500, t1), spx = s0 && s1 ? s1 / s0 - 1 : null;
      const c0 = at(d.cpi_uk, t0), c1 = at(d.cpi_uk, t1), cpi = c0 && c1 ? c1 / c0 - 1 : null;
      out.replaceChildren(kpi("Sells for today" + (it && it.latest ? " (" + it.latest.kind + ", " + dateOf(it.latest.date) + ")" : ""), gbp(gross)), kpi("Fee (" + num(feePct, 1) + "%)", gbp(fee)), kpi("Net to you", gbp(net)),
        kpi("Return on " + gbp(v.price), pct(ret, 0), cls(ret)), kpi("A year (annualised)", pct(ann, 1), cls(ann)), kpi("S&P 500, same period", pct(spx, 0), cls(spx)), kpi("UK CPI, same period", pct(cpi, 0)),
        kpi("Real return (after UK inflation)", ret != null && cpi != null ? pct((1 + ret) / (1 + cpi) - 1, 0) : "–", ret != null && cpi != null ? cls((1 + ret) / (1 + cpi) - 1) : ""));
    };
    compute(true);
    const calc = card("Calculator: a buyer at retail, selling today",
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px 12px;margin-bottom:10px" }, lab("Item", itemSel), lab("Bought on", dateIn), lab("Bought for (£, default: the list price that day)", priceIn), lab("Sell through", platSel)),
      out, note("Nothing you type is stored. Gross is the latest hand-entered resale point for the item; the fee is the platform's seller rate from the Fees tab (buyer-side fees, shipping, servicing, VAT and duty are left out)."));
    return [tbl, calc, changesCard("roi")];
  },

  async heat() {
    const d = await api("heat");
    const gauge = h => h ? card(words[h.category] + ": " + (h.verdict || "–") + (h.score == null ? "" : " (" + (h.score > 0 ? "+" : "") + num(h.score, 2) + ")"),
      el("div", { style: "color:var(--ink2);margin-bottom:8px" }, h.words || ""),
      el("div", { class: "kpis" }, ...(h.components || []).map(c => kpi(c.label + (c.date ? " (" + dateOf(c.date) + ")" : ""), c.value == null ? "no data yet" : (c.value > 0 ? "+" : "") + num(c.value, 2), c.value == null ? "" : c.value >= 0.5 ? "up" : c.value <= -0.5 ? "down" : ""))),
      ...linesChart([{ name: "Score", points: h.history || [], color: css("--s1") }, ...(h.components || []).filter(c => c.history && c.history.length).map((c, i) => ({ name: c.label, points: c.history, dashed: true, color: css(SERIES[(i + 1) % SERIES.length]) }))],
        v => (v > 0 ? "+" : "") + num(v, 2), { hlines: [0, 1, -1], small: true }),
      el("div", { class: "muted", style: "margin-top:6px" }, (h.components || []).map(c => c.label + ": " + c.words).join(" ")),
      Object.keys(h.indices || {}).length ? el("div", { style: "margin-top:8px" }, ...linesChart(Object.entries(h.indices).map(([k, v]) => ({ name: k, points: v.points })), v => num(v, 0), { small: true, sync: false }),
        note("Public indices, hand-entered headline figures, each on a year: " + Object.entries(h.indices).map(([k, v]) => k + " " + (v.change_1y == null ? "–" : v.unit === "pts" ? pp(v.change_1y, 1) : pct(v.change_1y, 0)) + (v.score == null ? "" : " (score " + (v.score > 0 ? "+" : "") + num(v.score, 1) + ")")).join("; ") + ".")) : null) : null;
    const head = card("Market heat: " + (d.verdict || "–") + (d.score == null ? "" : " (" + (d.score > 0 ? "+" : "") + num(d.score, 2) + ")"),
      el("div", { class: "kpis" }, kpi("Watches", d.watch && d.watch.score != null ? (d.watch.score > 0 ? "+" : "") + num(d.watch.score, 2) : "–"), kpi("Bags", d.bag && d.bag.score != null ? (d.bag.score > 0 ? "+" : "") + num(d.bag.score, 2) : "–"), kpi("Both (mean)", d.score == null ? "–" : (d.score > 0 ? "+" : "") + num(d.score, 2))),
      table(["Score", "Words"], (d.bands || []).map(b => el("tr", {}, el("td", {}, b[0]), el("td", {}, b[1])))),
      note("Like the Pokémon dashboard's heat score: each component is scored -2 … +2 and the score is their mean (at least two needed). +2 means far hotter than this market's own recent norm, not that prices will fall. Not investment advice."), asOf(d));
    return [head, gauge(d.watch), gauge(d.bag), cite(d.cited) ? card("Index sources", cite(d.cited)) : null, changesCard("heat")];
  },

  async liquidity() {
    const d = await api("liquidity"), A = d.attention || {}, B = A.baskets || {}, arts = A.articles || {};
    const z = v => v == null ? "–" : (v > 0 ? "+" : "") + num(v, 1) + " sd";
    const zc = v => v == null ? "" : v >= 1 ? "up" : v <= -1 ? "down" : "";
    const head = card("Attention: Wikipedia pageviews (a demand proxy)",
      followHead([{ label: "Watches basket attention (own-mean = 100)", points: (B.watch || {}).points || [], fmt: v => num(v, 0), delta: { lag: "1y" } },
        { label: "Bags basket attention (own-mean = 100)", points: (B.bag || {}).points || [], fmt: v => num(v, 0), delta: { lag: "1y" } },
        { label: "Watches: 12-month z", points: (B.watch || {}).z_points || [], fmt: z, cls: zc }, { label: "Bags: 12-month z", points: (B.bag || {}).z_points || [], fmt: z, cls: zc }], { latest: "Last full month" }),
      note("Monthly views of each item's English Wikipedia article (Wikimedia REST API, users, all access) since July 2015. People look a watch or bag up before they buy or sell, so attention is a demand proxy, not a price. Each article is scaled to its own whole-history mean, the basket is the mean of those; the z-score sets the last full month against the 12 before it."),
      Object.keys(d.attention_errors || {}).length ? el("div", { class: "muted" }, "Not available right now: " + Object.entries(d.attention_errors).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null, asOf(d), stale(d));
    const bk = card("Basket attention, month by month", ...linesChart(Object.values(B).map(b => ({ name: b.name, points: b.points })), v => num(v, 0), { small: true }));
    const per = card("Each article, monthly views (log scale)", ...linesChart(Object.values(arts).map(a => ({ name: a.title, points: a.points })), v => big(v), { log: true }));
    const tbl = card("Items: attention now", table(["Item", "Article", "Last full month", "Views", "On a year", "12-month z"],
      (A.items || []).map(i => el("tr", {}, el("td", {}, i.name), el("td", {}, i.url ? link(i.title, i.url) : i.title || "–"), el("td", {}, i.last ? i.last.month.slice(0, 7) : "–"), el("td", {}, i.last ? num(i.last.views) : "–"),
        el("td", { class: cls(i.change_1y) }, pct(i.change_1y, 0)), el("td", { class: zc(i.z12) }, z(i.z12))))),
      note("Two GMT-Master II references share one article; the Alma BB has none, so Louis Vuitton's article stands for it; the Le 5 à 7 and the Ava use their brands' articles. Listings, spreads and sell-through join this tab in the next steps."));
    return [head, bk, per, tbl, changesCard("liquidity")];
  },

  async fees() {
    const d = await api("fees"), F = d.fees || [];
    const tbl = card("What each platform takes", table(["Platform", "Type", "Seller pays", "Buyer pays", "Authentication", "Paid after", "Region", "Source"],
      F.map(f => el("tr", {}, el("td", {}, f.platform), el("td", {}, f.kind || ""), el("td", { class: "wrap" }, (f.seller_pct == null ? "offer-based" : num(f.seller_pct, 2) + "% typical") + " · " + (f.seller_text || "")),
        el("td", { class: "wrap" }, (f.buyer_pct ? num(f.buyer_pct, 1) + "% · " : "") + (f.buyer_text || "")), el("td", { class: "wrap" }, f.authentication || ""), el("td", {}, f.payout_days == null ? "–" : f.payout_days + " days"), el("td", {}, f.region || ""),
        srcCell(f.source, f.verify ? "verify" : "")))),
      note("'Typical' is the blended rate on a £5,000-£10,000 item, used by the ROI tab; the text gives the tiers. Buyout houses (Fashionphile, Rebag, Bob's, Watchfinder) charge no fee: their margin sits inside the offer, which is below the market price. All rows were entered from the platforms' pages as found by search, not read on the page: every row is marked verify until checked."), asOf(d), cite(d.cited));
    const how = card("How to sell, in short",
      el("div", { class: "muted", style: "font-size:13.5px;color:var(--ink2)" },
        el("p", {}, el("b", {}, "Marketplaces "), "(Chrono24, Vestiaire, eBay): you set the price, pay a commission on sale, and ship to the buyer or to an authentication hub. Highest gross, slowest, and the buyer's fees come out of what they are willing to pay."),
        el("p", {}, el("b", {}, "Consignment "), "(The RealReal, Fashionphile, Rebag, Bob's): the house sells it for you at a tiered commission and pays after the buyer's return period."),
        el("p", {}, el("b", {}, "Buyout "), "(Watchfinder, Bob's direct, Fashionphile and Rebag offers): fastest and certain, no fee, but the offer is the dealer's buying price, usually well under what the item lists for."),
        el("p", {}, el("b", {}, "Cross-border: "), "goods sent into Great Britain from abroad attract import VAT at 20% on the full value and, over £135, customs duty at the tariff rate (leather bags about 2%, EU-origin 0%), even second-hand from a private seller. See the Method tab for the calculation and caveats.")));
    return [tbl, how, changesCard("fees")];
  },
};
window.TOPIC = { VIEWS };
})();
