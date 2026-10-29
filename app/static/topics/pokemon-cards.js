// Pokémon Card Market: tabs and cards. Data from /api/pokemon-cards/<heat|prices|overheat|cooldown|grading|regions>; helpers from topic.html.
(() => {
const f0 = v => v == null ? "–" : num(v, 0), f2 = v => v == null ? "–" : num(v, 2);
const xm = v => v == null ? "–" : num(v, 2) + "x";
const num_x = v => v == null ? "–" : v >= 10 ? num(v, 0) + "x" : num(v, 1) + "x";
const zf = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const pc0 = v => pct(v, 0).replace("+", "");
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
const SEGCOL = { "Vintage WotC holos": "--s4", "Modern chase / alt-art": "--s1", "Sealed products": "--s2" };
const VERDICT_COL = s => s >= 0.5 ? "var(--down)" : s <= -0.5 ? "var(--s1)" : "var(--muted)";
const FMT = { mom30: pct, mom90: pct, breadth: pc0, sealed_msrp: xm, new_set: xm, psa10_ratio: xm, psa_volume: v => big(v), search: f0, sales: f0, news: f0, reprints: f0, overhang: pct };
const fmtSig = (k, v) => (FMT[k] || f2)(v);
// hand-entered series can be quarterly: monthly blank points let the chart follow the shared date axis to the month
// (through today, so a series that stopped early still follows a range set after its last point)
// an invisible, unnamed line carrying the last value to today: the chart library will not scroll past a series' last real point
const toToday = pts => { const m = monthly(pts), last = pts && pts.length ? pts[pts.length - 1] : null, today = Math.floor(Date.now() / 86400000) * 86400;
  if (!last || last[0] >= today) return null;
  return { points: [[last[0], last[1]], ...m.filter(t => t > last[0] && t < today).map(t => [t, last[1]]), [today, last[1]]], color: "rgba(0,0,0,0)", width: 1 }; };
// every chart here: the line that ends latest is carried (invisibly) to today, so a short shared range after the last monthly point still applies
const lines = (series, fmt, opts = {}) => { const live = series.filter(x => x && x.points && x.points.length && !x.bar);
  const latest = live.reduce((a, b) => !a || b.points[b.points.length - 1][0] > a.points[a.points.length - 1][0] ? b : a, null);
  return linesChart(latest ? series.concat([toToday(latest.points)]).filter(Boolean) : series, fmt, opts); };
const monthly = pts => { if (!pts || pts.length < 2) return []; const out = [], d = new Date(pts[0][0] * 1000), end = Math.max(pts[pts.length - 1][0], Date.now() / 1000);
  for (let t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000; t <= end; ) { out.push(t); const x = new Date(t * 1000); t = Date.UTC(x.getUTCFullYear(), x.getUTCMonth() + 1, 1) / 1000; } return out; };

// a gauge from -2 (cold, blue) to +2 (overheated, red) with a marker at v
function gauge(v, o = {}) {
  const h = o.small ? 8 : 16, w = o.small ? "100%" : "100%";
  const bar = el("div", { style: `position:relative;height:${h}px;width:${w};border-radius:${h / 2}px;background:linear-gradient(90deg, var(--s1), var(--chip) 50%, var(--down))` });
  [-1, 0, 1].forEach(t => bar.append(el("span", { style: `position:absolute;left:${(t + 2) * 25}%;top:0;bottom:0;width:1px;background:var(--surface);opacity:.8` })));
  if (v != null) {
    const x = Math.max(0, Math.min(100, (Math.max(-2, Math.min(2, v)) + 2) * 25));
    bar.append(el("span", { title: zf(v), style: `position:absolute;left:calc(${x}% - ${o.small ? 5 : 8}px);top:${o.small ? -3 : -4}px;width:${o.small ? 10 : 16}px;height:${h + (o.small ? 6 : 8)}px;` +
      "border-radius:4px;background:var(--ink);border:2px solid var(--surface)" }));
  }
  const ticks = o.small ? null : el("div", { style: "display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);margin-top:4px" },
    el("span", {}, "−2 cold"), el("span", {}, "−1 cooling"), el("span", {}, "0 normal"), el("span", {}, "+1 hot"), el("span", {}, "+2 overheated"));
  return el("div", { style: "margin:6px 0" }, bar, ticks);
}
const statusPill = c => c.heat != null ? el("span", { class: "pill " + (c.heat >= 0.5 ? "bad" : c.heat <= -0.5 ? "ok" : "") }, zf(c.heat)) : el("span", { class: "pill" }, c.status);

function signalCards(list, zmap) {
  return el("div", { class: "grid2" }, ...list.map(c => card(c.label,
    el("div", { class: "kpis" }, kpi("Now" + (c.date ? " (" + c.date + ")" : ""), fmtSig(c.key, c.value)), kpi("Heat (z × direction)", zf(c.heat), c.heat == null ? "" : c.heat > 0 ? "down" : "up")),
    gauge(c.heat, { small: true }),
    c.heat == null ? el("div", { class: "muted" }, c.status === "building history" ? "Building history: needs at least a year of readings before it can be scored."
      : c.status.startsWith("last reading") ? "Not scored: the " + c.status + "; add newer rows." : "No data yet.") : null,
    note(c.words + (c.sign < 0 ? " This one counts against the heat score: a high reading means cooling." : "")))));
}

// price (line, right axis) paired with units sold (bars, left axis) on one time axis
const priceVol = (price, units, fmt, o = {}) => lines([{ name: o.priceName || "Price", points: price, color: o.color || css("--s1") },
  { name: o.unitsName || "Units sold / week", points: units || [], bar: true, axis: "left", color: css("--hold"), fmt: f0 }], fmt, { small: o.small, log: o.log });
const perMo = v => v == null ? "–" : v >= 10 ? num(v, 0) + "/mo" : num(v, 1) + "/mo";
const pickPill = v => !v || !v.pick ? el("span", { class: "pill" }, "no data") : el("span", { class: "pill " + (v.pick === "PSA 9" ? "ok" : v.pick === "PSA 10" ? "" : "bad") }, v.pick === "thin" ? "thin both" : v.pick);
const lastSale = l => l ? usd(l.price, l.price < 100 ? 2 : 0) + " on " + l.date + (l.source ? " (" + l.source + ")" : "") : "–";
const GCOL = { Raw: "--s1", "PSA 9": "--s3", "PSA 10": "--s5" };

const img = (src, alt, w, href) => !src ? el("div", { style: `width:${w}px;height:${Math.round(w * 1.4)}px;border-radius:6px;background:var(--chip)` }) :
  el("a", { href: href || src, target: "_blank", rel: "noopener" }, el("img", { src, alt, loading: "lazy", referrerpolicy: "no-referrer",
    style: `width:${w}px;height:auto;border-radius:6px;display:block;border:1px solid var(--line)`, onerror: e => { e.currentTarget.style.visibility = "hidden"; } }));
const money = v => usd(v, v != null && v < 100 ? 2 : 0);

function topCard(c, i) {
  const G = c.grades || {}, W = c.weekly || {}, A = c.activity || {}, D = c.description || {};
  const gl = ["Raw", "PSA 9", "PSA 10"].filter(g => (G[g] || {}).points && G[g].points.length).map(g => ({ name: g, points: G[g].points, color: css(GCOL[g]) }));
  const tip = D.tip ? (D.tip.length > 360 ? D.tip.slice(0, 357) + "…" : D.tip) : null;
  const headRow = el("div", { style: "display:flex;gap:14px;align-items:flex-start" }, img(c.image, c.name, 110, c.image_large || c.url),
    el("div", { style: "min-width:0;flex:1" },
      el("div", { class: "muted" }, "#" + (c.popularity || i + 1) + " most popular" + (c.set ? " · " + c.set : "")),
      D.facts ? el("div", { style: "margin-top:4px" }, D.facts) : null,
      tip ? el("div", { class: "muted", style: "margin-top:6px" }, tip) : D.text ? el("div", { class: "muted", style: "margin-top:6px" }, "Card text: " + D.text.slice(0, 200)) : null,
      el("div", { style: "margin-top:6px" }, pickPill(c.verdict), el("span", { class: "muted" }, " better grade to trade"))));
  const prices = el("div", { class: "kpis", style: "margin-top:10px" }, ...["Raw", "PSA 9", "PSA 10"].map(g => kpi(g + " · " + perMo((G[g] || {}).per_month), money((G[g] || {}).price))));
  const act = el("div", { class: "kpis", style: "margin-top:4px" },
    kpi("Sales per month, all grades", A.per_month_all == null ? "–" : num(A.per_month_all, A.per_month_all < 10 ? 1 : 0)),
    kpi("Sold in the last 30 days (listed)", f0(A.sold_30d)),
    kpi("TCGplayer units, last 4 weeks", f0(A.units_4w)),
    kpi("TCGplayer listings · sellers", A.listings == null ? "–" : f0(A.listings) + " · " + f0(A.sellers)));
  const chart = (W.price || []).length
    ? [el("div", { class: "muted", style: "margin-top:8px" }, "Raw on TCGplayer: price (line) and units sold (bars) each week"), ...priceVol(W.price, W.units, v => usd(v, 2), { small: true })]
    : gl.length ? [el("div", { class: "muted", style: "margin-top:8px" }, "Raw, Grade 9 and PSA 10 by month (PriceCharting, log scale)"), ...lines(gl, money, { small: true, log: true })]
    : [el("div", { class: "muted" }, "No price history yet.")];
  const R = A.recent || [];
  const recent = R.length ? el("div", { class: "scroll", style: "margin-top:6px" }, el("table", {}, el("tr", {}, ...["Sold", "Grade", "Price", "Where"].map(h => el("th", {}, h))),
    ...R.map(x => el("tr", {}, el("td", {}, x.date), el("td", {}, x.grade), el("td", {}, money(x.price)), el("td", {}, x.source || "–"))))) : null;
  return card((i + 1) + ". " + c.name, headRow, prices, act, ...chart, recent,
    el("div", { class: "src", style: "margin-top:6px" }, link("PriceCharting", c.url), c.tcg_url ? [" · ", link("TCGplayer", c.tcg_url)] : null));
}

async function character(who) {
  const d = await api(who), K = d.kpi || {}, C = d.cards || [];
  const head = card(d.label + ": " + (d.top ? "the top " + C.length + " cards" : C.length + " cards"), el("div", { class: "kpis" },
    kpi("Raw index, 1 month", pct(K.m1), cls(K.m1)), kpi("3 months", pct(K.m3), cls(K.m3)), kpi("12 months", pct(K.m12), cls(K.m12)),
    kpi("TCGplayer units sold, last 4 weeks (4 before)", K.units_4w == null ? "–" : f0(K.units_4w) + (K.units_prev_4w == null ? "" : " (" + f0(K.units_prev_4w) + ")"),
      K.units_prev_4w ? cls(K.units_4w - K.units_prev_4w) : ""),
    kpi("Cards where PSA 9 is the better market", f0(K.psa9_picks) + " of " + f0(K.n))), asOf(d), stale(d),
    note((d.top ? "The top cards are the most popular English " + d.label + " cards in PriceCharting's search, refreshed every three days. "
      : "Cards from data/pokemon-cards/characters.csv (the search has not been read yet). ") +
      "Pictures are PriceCharting's; descriptions are TCGplayer's (rarity, number, artist and its own note). Trading activity is PriceCharting's stated sales per month for each grade " +
      "and its latest sold listings (eBay, TCGplayer, Fanatics, Goldin and others), TCGplayer's units sold per week and its current listings."));
  const idx = (d.index || []).length ? card(d.label + ": raw price index with units sold per week",
    ...priceVol(d.index, d.units, f0, { priceName: "Raw index (100 at start)", unitsName: "TCGplayer units / week" }),
    note("The line is an equal-weight, chain-linked index of these cards' raw prices; the bars are units of them sold on TCGplayer each week (one year). " +
      "Price rising on rising units is demand; price rising on thinning units is a few buyers chasing, which reverses more easily.")) : null;
  const rows = C.map((c, i) => { const G = c.grades || {}, A = c.activity || {};
    return el("tr", {}, el("td", {}, String(i + 1)), el("td", {}, img(c.image, c.name, 34, c.image_large || c.url)), el("td", { class: "wrap", style: "min-width:160px" }, link(c.name, c.url), el("div", { class: "muted" }, c.set || "")),
      el("td", {}, money((G.Raw || {}).price)), el("td", {}, money((G["PSA 9"] || {}).price)), el("td", {}, money((G["PSA 10"] || {}).price)),
      el("td", {}, perMo((G.Raw || {}).per_month)), el("td", {}, perMo((G["PSA 9"] || {}).per_month)), el("td", {}, perMo((G["PSA 10"] || {}).per_month)),
      el("td", {}, f0(A.units_4w)), el("td", {}, f0(A.listings)), el("td", {}, ((A.recent || [])[0] || {}).date || "–")); });
  const tbl = C.length ? card("Top " + C.length + " at a glance", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["#", "", "Card", "Raw", "PSA 9", "PSA 10", "Raw sales", "PSA 9 sales", "PSA 10 sales", "TCG units 4w", "Listings", "Last sale"].map(h => el("th", {}, h))), ...rows)),
    note("In order of popularity on PriceCharting. Sales are per month; a card with many sales and few listings is in demand, one with many listings and few sales is being sold into a thin market.")) : null;
  return [head, idx, tbl, el("div", { class: "grid2" }, ...C.map(topCard))];
}

const VIEWS = {
  async heat() {
    const d = await api("heat");
    const S = d.signals || [], live = S.filter(c => c.heat != null);
    const head = card("Heat score: " + (d.score == null ? "–" : zf(d.score)) + " · " + d.verdict,
      el("div", { style: "font-size:34px;font-weight:700;color:" + VERDICT_COL(d.score || 0) }, d.score == null ? "–" : zf(d.score)),
      gauge(d.score),
      el("div", { class: "muted" }, live.length + " of " + S.length + " signals have enough history to score. Drivers now: " +
        ((d.drivers || []).map(k => { const c = S.find(s => s.key === k); return c.label + " (" + zf(c.heat) + ")"; }).join(", ") || "none")),
      note("Each signal is compared with its own last three years (at least one): 0 is its usual level, +1 one standard deviation hotter. The score is the average, " +
        "kept between −2 and +2. Above +1 the market is running far hotter than usual on most measures, which is when late buyers overpay; below −1 is the opposite. " +
        "A hot reading says prices are stretched, not when they turn."), asOf(d), stale(d));
    const rows = S.slice().sort((a, b) => Math.abs(b.heat ?? -9) - Math.abs(a.heat ?? -9)).map(c => el("tr", {},
      el("td", {}, c.label), el("td", {}, fmtSig(c.key, c.value)), el("td", {}, c.z == null ? "–" : zf(c.z)), el("td", {}, c.sign > 0 ? "heats" : "cools"),
      el("td", { style: "min-width:120px" }, gauge(c.heat, { small: true })), el("td", {}, statusPill(c))));
    const tbl = card("What drives it now", table(["Signal", "Now", "z vs 3 years", "High reading", "Gauge", "Heat"], rows),
      note("Sorted by how far each signal sits from its normal. 'Heat' is the z-score times its direction: reprints and a supply overhang count as cooling, so a high reading pulls the score down."));
    const hist = (d.history || []).length > 2 ? card("Heat score month by month", ...lines([{ name: "Heat score", points: d.history, color: css("--down") }], zf, { hlines: [-1, 0, 1] }),
      note("The same average, computed each month from what each signal read then against its own previous three years. Past peaks (early 2021) show what overheated looked like; " +
        "the score turning down from a peak is the cooling signal to watch.")) : null;
    const words = card("What each signal means", el("div", {}, ...S.map(c => el("div", { style: "margin:6px 0" }, el("b", {}, c.label + ": "), el("span", { class: "muted" }, c.words)))));
    return [head, tbl, hist, signalCards(S.filter(c => c.heat != null)), words];
  },
  async prices() {
    const d = await api("prices"), K = d.kpi || {};
    const head = card(null, el("div", { class: "kpis" },
      kpi("Whole basket, 1 month", pct(K.m1), cls(K.m1)), kpi("3 months", pct(K.m3), cls(K.m3)), kpi("12 months", pct(K.m12), cls(K.m12)),
      kpi("From its high (" + (K.high_date || "–").slice(0, 7) + ")", pct(K.from_high), cls(K.from_high)),
      kpi("Vintage, 12 months", pct(K.vintage_m12), cls(K.vintage_m12)), kpi("Modern, 12 months", pct(K.modern_m12), cls(K.modern_m12)), kpi("Sealed, 12 months", pct(K.sealed_m12), cls(K.sealed_m12))),
      asOf(d), stale(d), note("Equal-weight, chain-linked indices of the bellwethers in basket.csv, monthly, from PriceCharting's ungraded (raw near-mint) prices."));
    const seg = Object.keys(d.segments || {}).length ? card("Price indices by basket (log scale, each 100 at its start)",
      ...lines([{ name: "Whole basket", points: d.all, color: css("--hold"), dashed: true }, ...Object.entries(d.segments).map(([k, p]) => ({ name: k, points: p, color: css(SEGCOL[k] || "--s3") }))], f0, { log: true }),
      note("Vintage holos (1999-2002 WotC) are the blue chips; modern alt-arts are where speculation shows first; sealed is what investors stack. When all three rise together at a steep slope, " +
        "as in 2020-21, the market is broad and hot; when modern and sealed fall while vintage holds, money is retreating to quality.")) : card("Price indices", el("div", { class: "muted" }, "No price history yet: the background download fills it within a few minutes of a deploy."), stale(d));
    const daily = Object.keys(d.daily || {}).length ? card("Daily since launch: TCGplayer (US) and Cardmarket (EU), basket median, first day = 100",
      ...lines(Object.entries(d.daily).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i]) })), f2, { small: true }),
      note("Logged once a day from TCGdex since this dashboard started, so it fills in over time. It shows moves within the month that the monthly indices smooth over.")) : null;
    const T = d.table || [];
    const rows = T.map(r => el("tr", {}, el("td", {}, link(r.name, r.url)), el("td", {}, r.set), el("td", {}, r.segment), el("td", {}, usd(r.price, r.price < 100 ? 2 : 0)),
      el("td", { class: cls(r.m1) }, pct(r.m1, 0)), el("td", { class: cls(r.m3) }, pct(r.m3, 0)), el("td", { class: cls(r.m12) }, pct(r.m12, 0)),
      el("td", { class: cls(r.vs200) }, pct(r.vs200, 0)), el("td", {}, r.x_msrp != null ? xm(r.x_msrp) : r.psa10 != null ? usd(r.psa10) + " PSA 10" : "–"), el("td", {}, r.src || "–"),
      el("td", { class: "muted" }, [r.ptcg_id, r.tcgplayer_id ? "tcg " + r.tcgplayer_id : null].filter(Boolean).join(" · "))));
    const tbl = card("The basket", table(["Card / product", "Set", "Basket", "Price (USD)", "1m", "3m", "12m", "vs 200-day", "x MSRP / PSA 10", "From", "Ids"], rows),
      note("Kept in data/pokemon-cards/basket.csv with each item's PriceCharting page, pokemontcg.io / TCGdex id and (found automatically) TCGplayer product id. 'vs 200-day' is the price against its average of the last 7 months."));
    const vol = (d.units || []).length && (d.all || []).length ? card("Whole basket: price index with TCGplayer units sold per week",
      ...priceVol(d.all, d.units, f0, { priceName: "Basket index", unitsName: "TCGplayer units / week (basket cards)" }),
      note("Price (monthly, PriceCharting) against turnover (weekly units of the basket's cards sold on TCGplayer, one year). Rises on rising volume are broad demand; rises on falling volume are thin.")) : null;
    return [head, seg, vol, daily, tbl];
  },
  async overheat() {
    const d = await api("overheat"), S = d.signals || [], Z = d.series || {};
    const head = card("Overheat signals", el("div", { class: "kpis" }, ...S.map(c => kpi(c.label, fmtSig(c.key, c.value), c.heat == null ? "" : c.heat >= 0.5 ? "down" : c.heat <= -0.5 ? "up" : ""))),
      note("Red: at least half a standard deviation hotter than its own last three years. Each card below shows the signal over time and its gauge."), asOf(d));
    const mom = (Z.mom30 || Z.mom90) ? card("Momentum: 30-day and 90-day change of the whole basket", ...lines([{ name: "30-day", points: Z.mom30 || [], color: css("--s2") }, { name: "90-day", points: Z.mom90 || [], color: css("--s1") }], v => pct(v, 0), { hlines: [0] }),
      note("Monthly data, so 30-day is one month and 90-day three. Sustained 90-day gains of 30%+ have only happened in manias (2020-21); a 30-day reading far above the 90-day pace means the run is accelerating.")) : null;
    const br = Z.breadth ? card("Breadth: share of the basket above its 200-day average", ...lines([{ name: "Share above", points: Z.breadth, color: css("--s3") }], pc0, { hlines: [0.5] }),
      note("Above 80% everything is rising together; a market can keep rising on falling breadth for a while, but it is a warning: fewer cards are doing the lifting.")) : null;
    const sm = Z.sealed_msrp ? card("Sealed: median price as a multiple of MSRP", ...lines([{ name: "Sealed / MSRP", points: Z.sealed_msrp, color: css("--s2") }], xm, { hlines: [1] }),
      note("Products already on sale only. Out-of-print boxes should drift above 1x; a jump across all of them at once is speculative stacking, the classic late-cycle sign.")) : null;
    const NS = d.new_set || [];
    const ns = NS.length ? card("New-set booster box premium (price two to ten weeks after release / MSRP)",
      ...svgBars(NS.map(o => o.set.split(" ").map(w => w[0]).join("")), [{ name: "x MSRP", values: NS.map(o => o.multiple), colorFn: v => v >= 1.2 ? css("--down") : v < 1 ? css("--s1") : css("--hold") }],
        { yFmt: xm, catName: i => NS[i].set + " (" + NS[i].date + ")" + (NS[i].price ? ", " + usd(NS[i].price) + " vs MSRP " + usd(NS[i].msrp, 2) : ""), h: 220 }),
      note("New boxes usually settle near or below MSRP once supply arrives. Red: 20%+ over MSRP weeks after release, demand outrunning a full print run. Scored against earlier sets (needs four).")) : null;
    const hand = [["search", "Search interest: Google Trends 'pokemon cards', US", f0, "--s5", "Hand-entered (trends.csv). 100 is the all-time peak (early 2021). Public interest leads new money; spikes above 50 have marked frenzies."],
      ["psa_volume", "PSA grading volume (Pokémon cards per month, 3-month average)", big, "--s4", "Hand-entered (psa.csv) from GemRate or PSA. Grading floods follow price spikes: people grade to sell."],
      ["sales", "TCGplayer units sold per week, basket cards", f0, "--s6", "Sum of every condition and printing. Rising sales with rising prices is real demand; rising prices on falling sales is thin."],
      ["news", "Sell-out, purchase-limit and scalping reports in the last 90 days", f0, "--down", "Count of dated, cited rows in events.csv."]]
      .map(([k, t, f, c, n]) => Z[k] ? card(t, ...lines([{ name: t.split(":")[0], points: Z[k], color: css(c) }], f, { small: true, whitespace: k === "sales" ? [] : monthly(Z[k]) }), note(n)) : card(t, el("div", { class: "muted" }, "No data yet. " + n)));
    const news = (d.news || []).length ? card("Sell-outs, limits and scalping (dated, cited)", table(["Date", "Where", "What", "Source"], d.news.map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.region),
      el("td", { class: "wrap" }, r.event + (r.note ? " (" + r.note + ")" : "")), el("td", {}, link(host(r.source), r.source))))), note("data/pokemon-cards/events.csv. Rows marked verify were entered from memory.")) : null;
    return [head, signalCards(S, Z), el("div", { class: "grid2" }, mom, br), el("div", { class: "grid2" }, sm, ns), el("div", { class: "grid2" }, ...hand), news, cite(d.cited)];
  },
  async cooldown() {
    const d = await api("cooldown"), Z = d.series || {};
    const mark = m => m == null ? el("span", { class: "pill" }, "unknown") : m ? el("span", { class: "pill bad" }, "yes") : el("span", { class: "pill ok" }, "no");
    const fv = c => c.value == null ? "–" : c.fmt === "x" ? (c.value > 0 ? "+" : "") + num(c.value, 2) + "x" : c.fmt === "pp" ? pp(c.value * 100, 0) : c.fmt === "n" ? num(c.value, 0) : pct(c.value, 0);
    const head = card("Cooling signs met: " + d.met + " of " + d.known + " known",
      table(["Sign", "Now", "Met?", "Rule"], (d.checks || []).map(c => el("tr", {}, el("td", {}, c.label), el("td", {}, fv(c)), el("td", {}, mark(c.met)), el("td", { class: "wrap" }, c.rule)))),
      note("A turn rarely shows in prices first: momentum fades, fewer cards rise, sealed premiums shrink, sellers pile up, perfect-grade premiums thin and the public stops searching. " +
        "Half or more of these met, with the heat score falling, is what the 2021-22 top looked like."), asOf(d));
    const mom = Z.mom90 ? card("90-day momentum and its 6-month peak", ...lines([{ name: "90-day", points: Z.mom90, color: css("--s1") }, { name: "6-month peak", points: d.peak90 || [], color: css("--hold"), dashed: true }], v => pct(v, 0), { hlines: [0] }),
      note("Rolling over = falling well below its recent peak while the last month was negative. The gap opening between the two lines is the early warning.")) : null;
    const br = Z.breadth ? card("Breadth rolling over", ...lines([{ name: "Share above 200-day", points: Z.breadth, color: css("--s3") }], pc0, { small: true, hlines: [0.5] }),
      note("A fall of 15+ points in three months means the rally is narrowing.")) : null;
    const sm = Z.sealed_msrp ? card("Sealed premium compressing toward MSRP", ...lines([{ name: "Sealed / MSRP", points: Z.sealed_msrp, color: css("--s2") }], xm, { small: true, hlines: [1] }),
      note("When stacked sealed comes back to market the multiple falls toward 1x; reprints speed it up.")) : null;
    const ov = Z.overhang ? card("Supply overhang: listings change minus units-sold change (30 days)", ...lines([{ name: "Listings − sales", points: Z.overhang, color: css("--down") }], v => pct(v, 0), { small: true, hlines: [0] }),
      note("TCGplayer listings for the basket cards, logged daily from launch, against units sold. Above zero: more sellers arriving than buyers; needs a month of log to start.")) :
      card("Supply overhang", el("div", { class: "muted" }, "Builds up from the daily log of TCGplayer listings: it needs 31 days."));
    const pr = Z.psa10_ratio ? card("PSA 10 premium over raw (median ratio)", ...lines([{ name: "PSA 10 / raw", points: Z.psa10_ratio, color: css("--s4") }], xm, { small: true }),
      note("Speculators pay most for perfect grades at the top; the ratio thinning means that money is leaving.")) : null;
    const se = Z.search ? card("Search interest fading", ...lines([{ name: "Google Trends", points: Z.search, color: css("--s5") }], f0, { small: true, whitespace: monthly(Z.search) }), note("Hand-entered monthly (trends.csv).")) : null;
    const rep = card("Reprint and restock announcements (dated, cited)", (d.reprints || []).length ? table(["Date", "Where", "What", "Source"], d.reprints.map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.region),
      el("td", { class: "wrap" }, r.event + (r.note ? " (" + r.note + ")" : "")), el("td", {}, link(host(r.source), r.source))))) : el("div", { class: "muted" }, "None entered yet."),
      note("Reprints add supply to exactly the products speculators hold; they are the clearest cooling trigger for sealed. data/pokemon-cards/events.csv."));
    return [head, mom, el("div", { class: "grid2" }, br, sm), el("div", { class: "grid2" }, ov, pr), se, rep, cite(d.cited)];
  },
  async grading() {
    const d = await api("grading");
    const ratio = Object.keys(d.ratio || {}).length ? card("PSA 10 price / raw price, median of the basket cards",
      ...lines(Object.entries(d.ratio).map(([k, p]) => ({ name: k, points: p, color: css(SEGCOL[k] || "--s3") })), xm),
      note("PriceCharting's PSA 10 and ungraded prices for the same card. Modern cards are printed in volume, so the premium is the value of scarcity in perfect condition; " +
        "it swells when grading is fashionable and money is loose, and shrinks as populations grow.")) : card("PSA 10 / raw", el("div", { class: "muted" }, "No graded prices yet."));
    const rows = (d.table || []).map(r => el("tr", {}, el("td", {}, r.name), el("td", {}, r.set), el("td", {}, usd(r.raw)), el("td", {}, usd(r.psa10)), el("td", {}, xm(r.ratio)), el("td", {}, xm(r.ratio_12m))));
    const tbl = rows.length ? card("PSA 10 premium by card", table(["Card", "Set", "Raw", "PSA 10", "Ratio", "A year ago"], rows), note("A ratio falling from a year ago on a card with a growing population is grading supply catching up.")) : null;
    const pop = Object.keys(d.pop || {}).some(k => d.pop[k].length > 1) ? card("PSA / CGC population, key cards", ...lines(Object.entries(d.pop).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), f0, { log: true }),
      note("Hand-entered from the PSA and CGC population reports (pop.csv). Population growth is new supply of graded copies.")) : null;
    const growth = Object.entries(d.pop_growth || {});
    const gt = card("Population now and growth over a year", growth.length ? table(["Card and grade", "Population", "As of", "1-year growth"], growth.map(([k, g]) => el("tr", {}, el("td", {}, k), el("td", {}, f0(g.now)), el("td", {}, g.date), el("td", {}, pct(g.yoy, 0)))))
      : el("div", { class: "muted" }, "Add monthly rows to data/pokemon-cards/pop.csv: date, series (card and grade), value, source."), note("Fast population growth on a chase card caps its PSA 10 price."));
    const psa = Object.keys(d.psa || {}).length ? card("PSA volume and turnaround", ...lines(Object.entries(d.psa).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), big),
      note("Hand-entered (psa.csv). Long turnaround means a submission backlog: people expect profits from grading.")) :
      card("PSA volume and turnaround", el("div", { class: "muted" }, "No rows yet: add monthly 'PSA Pokémon cards graded' and turnaround rows to data/pokemon-cards/psa.csv (GemRate publishes monthly counts)."));
    return [ratio, tbl, el("div", { class: "grid2" }, pop, gt), psa, cite(d.cited)];
  },
  async psa9() {
    const d = await api("psa9"), S = d.summary || {}, R = d.rows || [];
    const head = card("Is PSA 9 the better market to trade? " + (d.answer || "Not enough sales data yet."),
      el("div", { class: "kpis" },
        kpi("Sales per month, median card: PSA 9 vs PSA 10", perMo(S.p9_per_month) + " vs " + perMo(S.p10_per_month)),
        kpi("PSA 9 sales per PSA 10 sale", num_x(S.liq_ratio)), kpi("PSA 10 costs (x PSA 9)", num_x(S.premium)),
        kpi("Price noise between sales: PSA 9 vs 10", pct(S.p9_noise, 1).replace("+", "") + " vs " + pct(S.p10_noise, 1).replace("+", "")),
        kpi("Yearly volatility: PSA 9 vs 10", pct(S.p9_volatility, 0).replace("+", "") + " vs " + pct(S.p10_volatility, 0).replace("+", "")),
        kpi("12-month return: PSA 9 vs 10", pct(S.p9_m12, 0) + " vs " + pct(S.p10_m12, 0)),
        kpi("Cards: PSA 9 / PSA 10 / thin", [S.picks && S.picks["PSA 9"], S.picks && S.picks["PSA 10"], S.picks && S.picks.thin].map(f0).join(" / "))),
      Object.keys(S.eras || {}).length ? table(["Era", "Cards", "PSA 9 / PSA 10 / thin", "Sales per month: PSA 9 vs PSA 10", "PSA 9 sales per PSA 10 sale"],
        Object.entries(S.eras).map(([k, e]) => el("tr", {}, el("td", {}, k === "vintage" ? "Vintage (before 2010)" : "Modern"), el("td", {}, f0(e.n)),
          el("td", {}, [e.picks["PSA 9"], e.picks["PSA 10"], e.picks.thin].map(f0).join(" / ")), el("td", {}, perMo(e.p9_per_month) + " vs " + perMo(e.p10_per_month)), el("td", {}, num_x(e.liq_ratio))))) : null,
      note("Liquidity is how fast you can sell near the quoted price. Sales per month is PriceCharting's stated volume per grade (eBay, TCGplayer, Fanatics, Goldin and others). " +
        "Price noise is how far individual sales land from the 90-day median (a stand-in for the bid-ask spread: wider means you give up more to sell now). " +
        "The rule: PSA 10 when it sells at least twice a week; PSA 9 when it sells twice as often as PSA 10 and at least weekly; otherwise thin. " +
        "PriceCharting's 'Grade 9' is any grader's 9, mostly PSA. Not investment advice."), asOf(d));
    const named = R.filter(r => r.p9_per_month != null || r.p10_per_month != null);
    const bars = named.length ? card("Sales per month by card: PSA 9 against PSA 10",
      ...svgBars(named.map(r => r.name.split(" (")[0].split(" #")[0]), [{ name: "PSA 9", values: named.map(r => r.p9_per_month), color: css("--s3") },
        { name: "PSA 10", values: named.map(r => r.p10_per_month), color: css("--s5") }],
        { yFmt: v => num(v, 0), catName: i => named[i].name + " (" + named[i].set + ") · PSA 9 sells " + num_x(named[i].verdict.ratio) + " as often", labelW: 60, h: 240 }),
      note("A tall green bar beside a short pink one is a card whose PSA 10 rarely trades: you can buy one, but selling may take months or a price cut.")) : null;
    const hist = Object.keys(d.history || {}).length ? card("Sales per month, all cards, as logged each day", ...lines(Object.entries(d.history).map(([k, p], i) => ({ name: k, points: p, color: css(["--s3", "--s5", "--s1"][i % 3]) })), v => num(v, 0), { small: true }),
      note("PriceCharting's stated volume summed over the cards, saved once a day from launch: whether graded turnover is rising or drying up.")) : null;
    const rows = R.map(r => el("tr", {}, el("td", {}, link(r.name, r.url)), el("td", {}, r.set), el("td", {}, usd(r.p9_price)), el("td", {}, perMo(r.p9_per_month)),
      el("td", {}, usd(r.p10_price)), el("td", {}, perMo(r.p10_per_month)), el("td", {}, num_x(r.verdict.ratio)), el("td", {}, num_x(r.verdict.premium)),
      el("td", {}, pct(r.p9_noise, 1).replace("+", "") + " / " + pct(r.p10_noise, 1).replace("+", "")), el("td", {}, pct(r.p9_volatility, 0).replace("+", "") + " / " + pct(r.p10_volatility, 0).replace("+", "")),
      el("td", {}, lastSale(r.p10_last)), el("td", {}, pickPill(r.verdict))));
    const tbl = card("Every card", table(["Card", "Set", "PSA 9", "Sales", "PSA 10", "Sales", "9 per 10 sale", "10 / 9 price", "Noise 9 / 10", "Volatility 9 / 10", "Last PSA 10 sale", "Trade"], rows),
      note("Sorted by how much more often PSA 9 trades. A card where PSA 10 sells under once a month is one where a PSA 10 holder sets no market: the quoted PSA 10 price is a few sales, " +
        "and the next seller may have to undercut it. PSA 9 suits trading (turnover, tighter prices, less population risk); PSA 10 suits holding the very best copies."));
    return [head, bars, hist, tbl];
  },
  async pikachu() { return character("pikachu"); },
  async charizard() { return character("charizard"); },
  async psyduck() { return character("psyduck"); },
  async regions() {
    const d = await api("regions"), K = d.kpi || {}, FX = d.fx || {};
    const head = card("Where is it hottest? " + (d.hottest || "not enough data yet"),
      table(["Region", "Momentum", "Measured as"], (d.regions || []).map(r => el("tr", {}, el("td", {}, r.region + (r.region === d.hottest ? " 🔥" : "")), el("td", { class: cls(r.mom) }, pct(r.mom)), el("td", { class: "wrap" }, r.basis)))),
      el("div", { class: "kpis", style: "margin-top:10px" }, kpi("EU price vs US, same cards (median)", pct(K.eu_vs_us, 0), cls(K.eu_vs_us)), kpi("Cardmarket 7-day vs 30-day avg", pct(K.eu_7v30), cls(K.eu_7v30)),
        kpi("TCGplayer 4-week change", pct(K.us_30d), cls(K.us_30d)), kpi("USD in EUR / GBP / JPY / HKD", FX.EUR ? [f2(FX.EUR), f2(FX.GBP), f0(FX.JPY), f2(FX.HKD)].join(" / ") : "–")),
      note("Same cards, both markets, from TCGdex (TCGplayer market price in USD, Cardmarket trend price in EUR, converted at ECB rates). EU cheaper than the US is normal (VAT aside, " +
        "vintage supply is deeper there); the EU premium rising means European demand is catching up. Updated " + (d.as_of || "–") + "."));
    const C = d.cards || [];
    const tbl = C.length ? card("US vs UK/EU, card by card", table(["Card", "US (TCGplayer)", "EU (Cardmarket)", "In GBP", "EU vs US", "EU 7d vs 30d", "US 4 weeks"], C.map(c => el("tr", {},
      el("td", {}, c.name), el("td", {}, link(usd(c.usd, 2), c.tcg_url)), el("td", {}, link(c.eur == null ? "–" : "€" + num(c.eur, 2), c.cm_url)), el("td", {}, gbp(c.gbp, 2)),
      el("td", { class: cls(c.eu_vs_us) }, pct(c.eu_vs_us, 0)), el("td", { class: cls(c.eu_7v30) }, pct(c.eu_7v30)), el("td", { class: cls(c.us_30d) }, pct(c.us_30d))))),
      note("Sealed products are not in TCGdex, so this table is cards only.")) : card("US vs UK/EU", el("div", { class: "muted" }, "No TCGdex prices yet."));
    const jp = Object.keys(d.japan || {}).length ? card("Japan: Japanese set prices (JPY, hand-entered)", ...lines(Object.entries(d.japan).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), v => "¥" + num(v, 0)),
      note("From Yuyutei and Snkrdunk listings (japan.csv). Japanese sets release first and are where Asian demand shows earliest; they also lead English prices for shared artwork.")) :
      card("Japan: Japanese set prices", el("div", { class: "muted" }, "No rows yet. Yuyutei and Snkrdunk are checked from the server (/api/pokemon-cards/layout); until a feed answers, add rows to data/pokemon-cards/japan.csv: date, series (product, JPY), value, source."));
    const hk = card("Hong Kong shop notes", (d.hk || []).length ? table(["Date", "Shop", "Area", "Note", "Source"], d.hk.map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.shop), el("td", {}, r.area), el("td", { class: "wrap" }, r.note), el("td", {}, link(host(r.source), r.source)))))
      : el("div", { class: "muted" }, "No notes yet: add dated, cited rows to data/pokemon-cards/hk.csv."), note("What shops in Mong Kok, Sino Centre and elsewhere say about prices and demand: the HK market has no public price feed."));
    return [head, tbl, jp, hk, cite(d.cited)];
  },
};
window.TOPIC = { VIEWS };
})();
