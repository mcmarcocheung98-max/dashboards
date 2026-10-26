// Pokémon Card Market: tabs and cards. Data from /api/pokemon-cards/<heat|prices|overheat|cooldown|grading|regions>; helpers from topic.html.
(() => {
const f0 = v => v == null ? "–" : num(v, 0), f2 = v => v == null ? "–" : num(v, 2);
const xm = v => v == null ? "–" : num(v, 2) + "x";
const zf = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const pc0 = v => pct(v, 0).replace("+", "");
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
const SEGCOL = { "Vintage WotC holos": "--s4", "Modern chase / alt-art": "--s1", "Sealed products": "--s2" };
const VERDICT_COL = s => s >= 0.5 ? "var(--down)" : s <= -0.5 ? "var(--s1)" : "var(--muted)";
const FMT = { mom30: pct, mom90: pct, breadth: pc0, sealed_msrp: xm, new_set: xm, psa10_ratio: xm, psa_volume: v => big(v), search: f0, sales: f0, news: f0, reprints: f0, overhang: pct };
const fmtSig = (k, v) => (FMT[k] || f2)(v);

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
    const hist = (d.history || []).length > 2 ? card("Heat score month by month", ...linesChart([{ name: "Heat score", points: d.history, color: css("--down") }], zf, { hlines: [-1, 0, 1] }),
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
      ...linesChart([{ name: "Whole basket", points: d.all, color: css("--hold"), dashed: true }, ...Object.entries(d.segments).map(([k, p]) => ({ name: k, points: p, color: css(SEGCOL[k] || "--s3") }))], f0, { log: true }),
      note("Vintage holos (1999-2002 WotC) are the blue chips; modern alt-arts are where speculation shows first; sealed is what investors stack. When all three rise together at a steep slope, " +
        "as in 2020-21, the market is broad and hot; when modern and sealed fall while vintage holds, money is retreating to quality.")) : card("Price indices", el("div", { class: "muted" }, "No price history yet: the background download fills it within a few minutes of a deploy."), stale(d));
    const daily = Object.keys(d.daily || {}).length ? card("Daily since launch: TCGplayer (US) and Cardmarket (EU), basket median, first day = 100",
      ...linesChart(Object.entries(d.daily).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i]) })), f2, { small: true }),
      note("Logged once a day from pokemontcg.io since this dashboard started, so it fills in over time. It shows moves within the month that the monthly indices smooth over.")) : null;
    const T = d.table || [];
    const rows = T.map(r => el("tr", {}, el("td", {}, link(r.name, r.url)), el("td", {}, r.set), el("td", {}, r.segment), el("td", {}, usd(r.price, r.price < 100 ? 2 : 0)),
      el("td", { class: cls(r.m1) }, pct(r.m1, 0)), el("td", { class: cls(r.m3) }, pct(r.m3, 0)), el("td", { class: cls(r.m12) }, pct(r.m12, 0)),
      el("td", { class: cls(r.vs200) }, pct(r.vs200, 0)), el("td", {}, r.x_msrp != null ? xm(r.x_msrp) : r.psa10 != null ? usd(r.psa10) + " PSA 10" : "–"), el("td", {}, r.src || "–"),
      el("td", { class: "muted" }, [r.ptcg_id, r.tcgplayer_id ? "tcg " + r.tcgplayer_id : null].filter(Boolean).join(" · "))));
    const tbl = card("The basket", table(["Card / product", "Set", "Basket", "Price (USD)", "1m", "3m", "12m", "vs 200-day", "x MSRP / PSA 10", "From", "Ids"], rows),
      note("Kept in data/pokemon-cards/basket.csv with each item's PriceCharting page, pokemontcg.io id and (found automatically) TCGplayer product id. 'vs 200-day' is the price against its average of the last 7 months."));
    return [head, seg, daily, tbl];
  },
  async overheat() {
    const d = await api("overheat"), S = d.signals || [], Z = d.series || {};
    const head = card("Overheat signals", el("div", { class: "kpis" }, ...S.map(c => kpi(c.label, fmtSig(c.key, c.value), c.heat == null ? "" : c.heat >= 0.5 ? "down" : c.heat <= -0.5 ? "up" : ""))),
      note("Red: at least half a standard deviation hotter than its own last three years. Each card below shows the signal over time and its gauge."), asOf(d));
    const mom = (Z.mom30 || Z.mom90) ? card("Momentum: 30-day and 90-day change of the whole basket", ...linesChart([{ name: "30-day", points: Z.mom30 || [], color: css("--s2") }, { name: "90-day", points: Z.mom90 || [], color: css("--s1") }], v => pct(v, 0), { hlines: [0] }),
      note("Monthly data, so 30-day is one month and 90-day three. Sustained 90-day gains of 30%+ have only happened in manias (2020-21); a 30-day reading far above the 90-day pace means the run is accelerating.")) : null;
    const br = Z.breadth ? card("Breadth: share of the basket above its 200-day average", ...linesChart([{ name: "Share above", points: Z.breadth, color: css("--s3") }], pc0, { hlines: [0.5] }),
      note("Above 80% everything is rising together; a market can keep rising on falling breadth for a while, but it is a warning: fewer cards are doing the lifting.")) : null;
    const sm = Z.sealed_msrp ? card("Sealed: median price as a multiple of MSRP", ...linesChart([{ name: "Sealed / MSRP", points: Z.sealed_msrp, color: css("--s2") }], xm, { hlines: [1] }),
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
      .map(([k, t, f, c, n]) => Z[k] ? card(t, ...linesChart([{ name: t.split(":")[0], points: Z[k], color: css(c) }], f, { small: true }), note(n)) : card(t, el("div", { class: "muted" }, "No data yet. " + n)));
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
    const mom = Z.mom90 ? card("90-day momentum and its 6-month peak", ...linesChart([{ name: "90-day", points: Z.mom90, color: css("--s1") }, { name: "6-month peak", points: d.peak90 || [], color: css("--hold"), dashed: true }], v => pct(v, 0), { hlines: [0] }),
      note("Rolling over = falling well below its recent peak while the last month was negative. The gap opening between the two lines is the early warning.")) : null;
    const br = Z.breadth ? card("Breadth rolling over", ...linesChart([{ name: "Share above 200-day", points: Z.breadth, color: css("--s3") }], pc0, { small: true, hlines: [0.5] }),
      note("A fall of 15+ points in three months means the rally is narrowing.")) : null;
    const sm = Z.sealed_msrp ? card("Sealed premium compressing toward MSRP", ...linesChart([{ name: "Sealed / MSRP", points: Z.sealed_msrp, color: css("--s2") }], xm, { small: true, hlines: [1] }),
      note("When stacked sealed comes back to market the multiple falls toward 1x; reprints speed it up.")) : null;
    const ov = Z.overhang ? card("Supply overhang: listings change minus units-sold change (30 days)", ...linesChart([{ name: "Listings − sales", points: Z.overhang, color: css("--down") }], v => pct(v, 0), { small: true, hlines: [0] }),
      note("TCGplayer listings for the basket cards, logged daily from launch, against units sold. Above zero: more sellers arriving than buyers; needs a month of log to start.")) :
      card("Supply overhang", el("div", { class: "muted" }, "Builds up from the daily log of TCGplayer listings: it needs 31 days."));
    const pr = Z.psa10_ratio ? card("PSA 10 premium over raw (median ratio)", ...linesChart([{ name: "PSA 10 / raw", points: Z.psa10_ratio, color: css("--s4") }], xm, { small: true }),
      note("Speculators pay most for perfect grades at the top; the ratio thinning means that money is leaving.")) : null;
    const se = Z.search ? card("Search interest fading", ...linesChart([{ name: "Google Trends", points: Z.search, color: css("--s5") }], f0, { small: true }), note("Hand-entered monthly (trends.csv).")) : null;
    const rep = card("Reprint and restock announcements (dated, cited)", (d.reprints || []).length ? table(["Date", "Where", "What", "Source"], d.reprints.map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.region),
      el("td", { class: "wrap" }, r.event + (r.note ? " (" + r.note + ")" : "")), el("td", {}, link(host(r.source), r.source))))) : el("div", { class: "muted" }, "None entered yet."),
      note("Reprints add supply to exactly the products speculators hold; they are the clearest cooling trigger for sealed. data/pokemon-cards/events.csv."));
    return [head, mom, el("div", { class: "grid2" }, br, sm), el("div", { class: "grid2" }, ov, pr), se, rep, cite(d.cited)];
  },
  async grading() {
    const d = await api("grading");
    const ratio = Object.keys(d.ratio || {}).length ? card("PSA 10 price / raw price, median of the basket cards",
      ...linesChart(Object.entries(d.ratio).map(([k, p]) => ({ name: k, points: p, color: css(SEGCOL[k] || "--s3") })), xm),
      note("PriceCharting's PSA 10 and ungraded prices for the same card. Modern cards are printed in volume, so the premium is the value of scarcity in perfect condition; " +
        "it swells when grading is fashionable and money is loose, and shrinks as populations grow.")) : card("PSA 10 / raw", el("div", { class: "muted" }, "No graded prices yet."));
    const rows = (d.table || []).map(r => el("tr", {}, el("td", {}, r.name), el("td", {}, r.set), el("td", {}, usd(r.raw)), el("td", {}, usd(r.psa10)), el("td", {}, xm(r.ratio)), el("td", {}, xm(r.ratio_12m))));
    const tbl = rows.length ? card("PSA 10 premium by card", table(["Card", "Set", "Raw", "PSA 10", "Ratio", "A year ago"], rows), note("A ratio falling from a year ago on a card with a growing population is grading supply catching up.")) : null;
    const pop = Object.keys(d.pop || {}).some(k => d.pop[k].length > 1) ? card("PSA / CGC population, key cards", ...linesChart(Object.entries(d.pop).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), f0, { log: true }),
      note("Hand-entered from the PSA and CGC population reports (pop.csv). Population growth is new supply of graded copies.")) : null;
    const growth = Object.entries(d.pop_growth || {});
    const gt = card("Population now and growth over a year", growth.length ? table(["Card and grade", "Population", "As of", "1-year growth"], growth.map(([k, g]) => el("tr", {}, el("td", {}, k), el("td", {}, f0(g.now)), el("td", {}, g.date), el("td", {}, pct(g.yoy, 0)))))
      : el("div", { class: "muted" }, "Add monthly rows to data/pokemon-cards/pop.csv: date, series (card and grade), value, source."), note("Fast population growth on a chase card caps its PSA 10 price."));
    const psa = Object.keys(d.psa || {}).length ? card("PSA volume and turnaround", ...linesChart(Object.entries(d.psa).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), big),
      note("Hand-entered (psa.csv). Long turnaround means a submission backlog: people expect profits from grading.")) :
      card("PSA volume and turnaround", el("div", { class: "muted" }, "No rows yet: add monthly 'PSA Pokémon cards graded' and turnaround rows to data/pokemon-cards/psa.csv (GemRate publishes monthly counts)."));
    return [ratio, tbl, el("div", { class: "grid2" }, pop, gt), psa, cite(d.cited)];
  },
  async regions() {
    const d = await api("regions"), K = d.kpi || {}, FX = d.fx || {};
    const head = card("Where is it hottest? " + (d.hottest || "not enough data yet"),
      table(["Region", "Momentum", "Measured as"], (d.regions || []).map(r => el("tr", {}, el("td", {}, r.region + (r.region === d.hottest ? " 🔥" : "")), el("td", { class: cls(r.mom) }, pct(r.mom)), el("td", { class: "wrap" }, r.basis)))),
      el("div", { class: "kpis", style: "margin-top:10px" }, kpi("EU price vs US, same cards (median)", pct(K.eu_vs_us, 0), cls(K.eu_vs_us)), kpi("Cardmarket 7-day vs 30-day avg", pct(K.eu_7v30), cls(K.eu_7v30)),
        kpi("TCGplayer 4-week change", pct(K.us_30d), cls(K.us_30d)), kpi("USD in EUR / GBP / JPY / HKD", FX.EUR ? [f2(FX.EUR), f2(FX.GBP), f0(FX.JPY), f2(FX.HKD)].join(" / ") : "–")),
      note("Same cards, both markets, from pokemontcg.io (TCGplayer market price in USD, Cardmarket trend price in EUR, converted at ECB rates). EU cheaper than the US is normal (VAT aside, " +
        "vintage supply is deeper there); the EU premium rising means European demand is catching up. Updated " + (d.as_of || "–") + "."));
    const C = d.cards || [];
    const tbl = C.length ? card("US vs UK/EU, card by card", table(["Card", "US (TCGplayer)", "EU (Cardmarket)", "In GBP", "EU vs US", "EU 7d vs 30d", "US 4 weeks"], C.map(c => el("tr", {},
      el("td", {}, c.name), el("td", {}, link(usd(c.usd, 2), c.tcg_url)), el("td", {}, link(c.eur == null ? "–" : "€" + num(c.eur, 2), c.cm_url)), el("td", {}, gbp(c.gbp, 2)),
      el("td", { class: cls(c.eu_vs_us) }, pct(c.eu_vs_us, 0)), el("td", { class: cls(c.eu_7v30) }, pct(c.eu_7v30)), el("td", { class: cls(c.us_30d) }, pct(c.us_30d))))),
      note("Sealed products are not in pokemontcg.io, so this table is cards only.")) : card("US vs UK/EU", el("div", { class: "muted" }, "No pokemontcg.io prices yet."));
    const jp = Object.keys(d.japan || {}).length ? card("Japan: Japanese set prices (JPY, hand-entered)", ...linesChart(Object.entries(d.japan).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % 6]) })), v => "¥" + num(v, 0)),
      note("From Yuyutei and Snkrdunk listings (japan.csv). Japanese sets release first and are where Asian demand shows earliest; they also lead English prices for shared artwork.")) :
      card("Japan: Japanese set prices", el("div", { class: "muted" }, "No rows yet. Yuyutei and Snkrdunk are checked from the server (/api/pokemon-cards/layout); until a feed answers, add rows to data/pokemon-cards/japan.csv: date, series (product, JPY), value, source."));
    const hk = card("Hong Kong shop notes", (d.hk || []).length ? table(["Date", "Shop", "Area", "Note", "Source"], d.hk.map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, r.shop), el("td", {}, r.area), el("td", { class: "wrap" }, r.note), el("td", {}, link(host(r.source), r.source)))))
      : el("div", { class: "muted" }, "No notes yet: add dated, cited rows to data/pokemon-cards/hk.csv."), note("What shops in Mong Kok, Sino Centre and elsewhere say about prices and demand: the HK market has no public price feed."));
    return [head, tbl, jp, hk, cite(d.cited)];
  },
};
window.TOPIC = { VIEWS };
})();
