// Prediction Markets: tabs and cards. Data from /api/prediction-markets/<overview|markets|categories|venues|regions|accuracy>; helpers from topic.html.
(() => {
// fixed colours: each venue and each category keeps its colour on every tab, whatever is shown
const VENUE = { poly: ["Polymarket", "--s1"], kalshi: ["Kalshi", "--s3"], manifold: ["Manifold (play money)", "--s4"], predictit: ["PredictIt", "--s2"] };
const CAT = { "Elections & politics": "--s1", "Central banks & macro": "--s2", "Crypto": "--s3", "AI & tech": "--s4", "Sports": "--s5", "Geopolitics": "--s6", "Other": "--hold" };
const catCol = k => css(CAT[k] || "--hold");
const prob = (v, d = 0) => v == null ? "–" : (v * 100).toFixed(d) + "%";
const pc = (v, d = 1) => v == null ? "–" : Number(v).toFixed(d) + "%";
const chg = v => v == null ? "–" : pp(v * 100, 1);
const money = v => v == null ? "–" : "$" + big(v);
const last = p => p && p.length ? p[p.length - 1][1] : null;
const wrap = s => el("td", { class: "wrap" }, s);

// The top card follows the timeline (topic.html's followHead: hovering a chart shows that day, a click keeps it, "Back to latest"
// returns); until the page shell has it, the card shows the latest figures.
function head(items, extra = [], opts = {}) {
  items = items.filter(i => i.points && i.points.length);
  const more = extra.length ? el("div", { class: "kpis", style: "margin-top:10px" }, ...extra) : null;
  if (typeof followHead === "function" && items.length) return card(null, followHead(items, opts), more);
  return card(null, el("div", { class: "kpis" }, ...items.map(i => kpi(i.label, i.fmt(last(i.points))))), more);
}
// deltas shown next to each figure: points of probability over a week, or the % change in money over a week
const D_PTS = { lag: "7d", abs: true, fmt: v => pp(v, 1) }, D_PCT = { lag: "7d" };
const staticHead = (...k) => card(null, el("div", { class: "kpis" }, ...k));

function marketTable(rows, cols = ["yes", "d1", "d7", "vol24", "liq"]) {
  const H = { yes: "Chance", d1: "24h", d7: "7 days", vol24: "Traded, 24h", vol: "Traded, all", liq: "Liquidity", end: "Closes" };
  const cell = (r, c) => c === "yes" ? el("td", {}, prob(r.yes)) : c === "d1" || c === "d7" ? el("td", { class: cls(r[c]) }, chg(r[c]))
    : c === "end" ? el("td", {}, r.end || "–") : el("td", {}, money(r[c]));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, el("th", {}, "Market"), ...cols.map(c => el("th", {}, H[c]))),
    ...rows.map(r => el("tr", {}, wrap([link(r.event && r.event !== r.q ? r.event + " · " + r.label : r.q, r.url)]), ...cols.map(c => cell(r, c))))));
}
const why = m => m && Object.keys(m).length ? el("div", { class: "muted" }, "Not available right now: " + Object.entries(m).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
const nfa = () => el("div", { class: "card nfa" }, "Prices are what traders pay, not forecasts by this site. Not investment or betting advice.");
const logNote = since => "Logged once a day by this server" + (since ? " since " + since : "") + "; the line grows a point a day.";

let pickMarket = null;

const VIEWS = {
  async overview() {
    const d = await api("overview"), t = d.totals || {}, cl = d.cat_log || {};
    const total = (() => { const m = new Map(); Object.values(cl).forEach(p => p.forEach(([ts, v]) => m.set(ts, (m.get(ts) || 0) + v))); return [...m].sort((a, b) => a[0] - b[0]); })();
    const top = Object.entries(cl).sort((a, b) => (last(b[1]) || 0) - (last(a[1]) || 0)).slice(0, 3);
    const hd = head([{ label: "Traded in 24 hours, all categories", points: total, fmt: money, delta: D_PCT },
      ...top.map(([k, p]) => ({ label: k + ", 24 hours", points: p, fmt: money, delta: D_PCT }))],
      [kpi("Open markets in the sample", num(t.markets)), kpi("Liquidity on the book", money(t.liq))]);
    const lines = card("Money traded in 24 hours, by category (Polymarket)",
      ...linesChart(Object.entries(cl).map(([k, p]) => ({ name: k, points: p, color: catCol(k) })), money),
      note("Each day's total 24-hour volume across the open events in the sample, summed by category. " + logNote(d.log_since)));
    const cats = d.cats || [];
    const bars = cats.length ? card("Traded in the last 24 hours, by category",
      ...svgBars(cats.map(c => c.label.split(" ")[0]), [{ name: "24h volume", values: cats.map(c => c.vol24), colorFn: (v, i) => catCol(cats[i].label) }],
        { yFmt: money, catName: i => cats[i].label, extra: i => " · " + cats[i].events + " events, " + cats[i].markets + " markets · all-time " + money(cats[i].volume) + " · liquidity " + money(cats[i].liq) }),
      note("Polymarket's open events with the most 24-hour volume (the top 300, plus a few regional tags), grouped by their tags. Sports usually leads on any given day; politics leads in election weeks.")) : null;
    const mv = (title, rows, key, txt) => card(title, rows && rows.length ? marketTable(rows, [ "yes", key, key === "d1" ? "vol24" : "vol", "liq"]) : el("div", { class: "muted" }, "No market moved enough."),
      note(txt));
    return [hd, stale(d), missing(d, "pool", "Polymarket"),
      el("div", { class: "grid2" },
        mv("Biggest movers, 24 hours", d.movers24, "d1", "Change in the Yes price over 24 hours, in points of probability, among markets that traded at least " + money((d.thresholds || {}).vol24) + " in the day; one market per event."),
        mv("Biggest movers, 7 days", d.movers7, "d7", "Change over 7 days, among markets that traded at least " + money((d.thresholds || {}).vol1wk) + " in the week; one market per event.")),
      bars, lines,
      card("Most traded markets, last 24 hours", marketTable(d.top || [], ["yes", "d1", "vol24", "liq", "end"]), note("One market per event: the outcome with the most volume. Liquidity is the money resting on the order book near the price.")),
      card("Most traded events, last 24 hours", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Event", "Category", "Markets", "24h", "All time", "Liquidity", "Closes"].map(h => el("th", {}, h))),
        ...(d.events || []).map(e => el("tr", {}, wrap([link(e.title, e.url)]), el("td", {}, e.cat ? ({ politics: "Elections & politics", macro: "Central banks & macro", crypto: "Crypto", ai: "AI & tech", sports: "Sports", geo: "Geopolitics" }[e.cat] || "Other") : "–"),
          el("td", {}, e.n), el("td", {}, money(e.vol24)), el("td", {}, money(e.volume)), el("td", {}, money(e.liq)), el("td", {}, e.end || "–"))))),
        note("An event groups its outcomes (each candidate, each rate move); its volume is the sum of theirs.")),
      nfa()];
  },

  async markets() {
    const d = await api("markets"), items = d.items || [];
    if (!items.length) return [card(null, el("div", { class: "muted" }, "The watchlist is empty (data/prediction-markets/watchlist.csv)."))];
    const live = items.filter(i => i.poly);
    if (!pickMarket || !items.some(i => i.key === pickMarket)) pickMarket = (live[0] || items[0]).key;
    const it = items.find(i => i.key === pickMarket), p = it.poly || {};
    const hd = head([{ label: it.label + ": chance", points: it.hist, fmt: v => pc(v, 1), delta: D_PTS },
      { label: "Traded that day", points: it.volume, fmt: money }, { label: "Liquidity", points: it.liq, fmt: money }],
      [kpi("24h change", chg(p.d1), cls(p.d1)), kpi("7-day change", chg(p.d7), cls(p.d7))]);
    const picker = el("div", { class: "seg", style: "flex-wrap:wrap" }, ...items.map(i => el("button", { class: i.key === pickMarket ? "on" : "", onclick: () => { pickMarket = i.key; render(); } }, i.label)));
    const odds = card("Odds history: " + it.label + " (Polymarket, % chance)", picker,
      p.title ? el("div", { class: "muted", style: "margin-bottom:6px" }, "Matched: ", link(p.title, p.url), p.end ? " · closes " + p.end : "") : el("div", { class: "muted" }, "No open Polymarket market matches this row right now."),
      ...(it.hist.length ? linesChart([{ name: "Yes price", points: it.hist, color: css("--s1") }], v => pc(v, 1), { hlines: [50] }) : [el("div", { class: "muted" }, "No price history.")]),
      note("Daily closing price of the Yes share from Polymarket's CLOB, read as the market's chance. " + (it.note || "")));
    const vol = card("Money behind the moves: traded each day ($)", ...linesChart([{ name: "Volume that day", points: it.volume, bar: true, color: css("--s1") }], money, { small: true }),
      it.volume.length ? null : el("div", { class: "muted" }, "Builds from the second day of the log."),
      note("The day's change in the market's all-time volume. Polymarket's API has no volume history, so " + logNote().toLowerCase()));
    const liq = card("Liquidity on the book ($)", ...linesChart([{ name: "Liquidity", points: it.liq, color: css("--s6") }], money, { small: true }),
      note("Money resting in orders near the price: the deeper it is, the more it costs to move the odds. " + logNote()));
    const all = card("The watchlist", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Question", "Matched market", "Chance", "24h", "7 days", "Traded, 24h", "Liquidity"].map(h => el("th", {}, h))),
      ...items.map(i => { const q = i.poly || {}; return el("tr", {}, wrap([i.label]), wrap([q.title ? link(q.title, q.url) : el("span", { class: "muted" }, "no match")]), el("td", {}, prob(q.yes)),
        el("td", { class: cls(q.d1) }, chg(q.d1)), el("td", { class: cls(q.d7) }, chg(q.d7)), el("td", {}, money(q.vol24)), el("td", {}, money(q.liq))); }))),
      why(d.missing), note("Rows find their market by keywords (data/prediction-markets/watchlist.csv), so the next Fed meeting or a new contract is picked up on its own. Check the matched market before reading the number."), cite(d.cites));
    return [hd, el("div", { class: "grid2" }, odds, el("div", { style: "display:grid;gap:12px" }, vol, liq)), all, nfa()];
  },

  async categories() {
    const d = await api("categories"), L = d.log || {}, v = L.vol24 || {}, lq = L.liq || {};
    const hd = head(Object.entries(v).map(([k, p]) => ({ label: k + ", 24h", points: p, fmt: money, delta: D_PCT })));
    const lines = (title, by, txt) => card(title, ...linesChart(Object.entries(by).map(([k, p]) => ({ name: k, points: p, color: catCol(k) })), money, { small: true }), note(txt));
    const per = (d.cats || []).map(c => { const t = c.totals || {};
      return card(c.label, el("div", { class: "kpis" }, kpi("Traded, 24h", money(t.vol24)), kpi("Traded, all time", money(t.volume)), kpi("Liquidity", money(t.liq)), kpi("Events / markets", (t.events || 0) + " / " + (t.markets || 0))),
        c.top.length ? marketTable(c.top, ["yes", "d1", "vol24", "liq", "end"]) : el("div", { class: "muted" }, "No open market in the sample."),
        note("The most traded markets in this category (one per event). Totals cover the open events in the sample.")); });
    return [hd, stale(d), missing(d, "pool", "Polymarket"),
      el("div", { class: "grid2" }, lines("Traded in 24 hours, by category ($)", v, "Each day's 24-hour volume by category. " + logNote()),
        lines("Liquidity on the book, by category ($)", lq, "Money resting in orders, by category: where it is cheapest to trade size. " + logNote())), ...per, nfa()];
  },

  async venues() {
    const d = await api("venues"), items = d.items || [];
    const shared = items.filter(i => Object.keys(i.log || {}).length >= 2);
    const first = shared[0] || items[0];
    const hd = first ? head(Object.entries(first.log || {}).map(([v, p]) => ({ label: first.label + ": " + VENUE[v][0], points: p, fmt: x => pc(x, 1) })),
      [kpi("Questions on 2+ venues", String(items.filter(i => i.venues >= 2).length))]) : null;
    const cellP = (i, v) => el("td", {}, i[v] ? link(prob(i[v].yes), i[v].url) : el("span", { class: "muted" }, "–"));
    const tbl = card("The same question, side by side", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Question", ...Object.values(VENUE).map(v => v[0]), "Gap, real money", "Gap, all"].map(h => el("th", {}, h))),
      ...items.map(i => el("tr", {}, wrap([i.label]), ...Object.keys(VENUE).map(v => cellP(i, v)), el("td", { style: tint(i.gap, 0.1, "--sellt") }, i.gap == null ? "–" : pp(i.gap * 100, 1).replace("+", "")),
        el("td", {}, i.gap_all == null ? "–" : pp(i.gap_all * 100, 1).replace("+", "")))))),
      why(d.missing),
      note("Each venue's own market for the question, matched by keywords; hover a price to see it, and check the wording, since venues settle on different rules and dates. Gap = highest minus lowest price, in points. Real money: Polymarket, Kalshi and PredictIt. Manifold trades play money. A gap that stays open is usually fees, limits (PredictIt caps bets at $850), or wording, not free money."));
    const charts = shared.slice(0, 6).map(i => card(i.label + ": price on each venue (% chance)",
      ...linesChart(Object.entries(i.log).map(([v, p]) => ({ name: VENUE[v][0], points: p, color: css(VENUE[v][1]), dashed: v === "manifold" })), x => pc(x, 1), { small: true }),
      note("Matched: " + Object.keys(VENUE).filter(v => i[v]).map(v => VENUE[v][0] + " \"" + i[v].title + "\"").join("; ") + ". " + logNote())));
    return [hd, tbl, el("div", { class: "grid2" }, ...charts), nfa()].filter(Boolean);
  },

  async regions() {
    const d = await api("regions"), R = d.regions || [];
    const firstLine = r => r.watch.find(w => w.hist && w.hist.length);
    const hd = head(R.map(r => { const w = firstLine(r); return w ? { label: r.key + ": " + w.label, points: w.hist, fmt: v => pc(v, 1), delta: D_PTS } : null; }).filter(Boolean));
    const blocks = R.map(r => {
      const lines = r.watch.filter(w => w.hist && w.hist.length);
      return card(r.label,
        lines.length ? linesChart(lines.map(w => ({ name: w.label, points: w.hist })), v => pc(v, 1), { small: true }) : el("div", { class: "muted" }, "No watchlist market here has a Polymarket price history."),
        el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Watchlist", ...Object.values(VENUE).map(v => v[0])].map(h => el("th", {}, h))),
          ...r.watch.map(w => el("tr", {}, wrap([w.label]), ...Object.keys(VENUE).map(v => el("td", {}, w[v] ? link(prob(w[v].yes), w[v].url) : "–")))))),
        r.listed.length ? [el("h2", { style: "margin-top:12px" }, "Also listed"), marketTable(r.listed, ["yes", "d1", "vol24", "end"])] : el("div", { class: "muted", style: "margin-top:6px" }, "Nothing else listed under this region's tags."),
        note({ US: "The Fed, CPI and the midterms. Lines: Polymarket's daily price for each watchlist row; the table adds the other venues.",
               UK: "Politics and the Bank of England. UK markets are thin next to US ones, so a few trades can move them.",
               HK: "The Hang Seng, the PBoC and Taiwan, where listed. Few venues list Hong Kong or China macro markets; 'Also listed' shows what Polymarket has under its China, Hong Kong and Taiwan tags." }[r.key]));
    });
    return [hd, why(d.missing), ...blocks, nfa()].filter(Boolean);
  },

  async accuracy() {
    const d = await api("accuracy"), a = d.p30 || {}, b = d.p7 || {};
    const hd = staticHead(kpi("Resolved markets", num(d.n)), kpi("Brier score, 30 days before", a.brier == null ? "–" : a.brier.toFixed(3)),
      kpi("Brier score, 7 days before", b.brier == null ? "–" : b.brier.toFixed(3)), kpi("Resolved Yes", a.base == null ? "–" : prob(a.base)));
    if (!d.n) return [hd, card(null, el("div", { class: "muted" }, "The calibration sample is being built by a background job (a few hundred paced requests); it appears within hours of a deploy.")), nfa()];
    const pts = c => (c.buckets || []).map(x => [x.price * 100, x.freq * 100]);
    const cal = card("Calibration: priced chance against how often it happened (%)",
      ...svgLines([{ name: "30 days before", points: pts(a), color: css("--s2") }, { name: "7 days before", points: pts(b), color: css("--s1") },
        { name: "Perfect calibration", points: [[0, 0], [100, 100]], color: css("--hold"), dashed: true }],
        { xFmt: v => Math.round(v) + "%", yFmt: v => Math.round(v) + "%", h: 300, xTicks: [0, 20, 40, 60, 80, 100], note: "Hover or tap to read a bucket." }),
      note("Resolved Polymarket Yes/No markets of the last year with " + money(d.min_volume) + " or more traded (closed " + d.since + " to " + d.latest + "). Prices are grouped in tenths; each point is a group's average price against the share that resolved Yes. On the dashed line, a 70% price came true 70% of the time. Outcomes of multi-candidate events count one market each, so long shots are many."));
    const nb = (b.buckets || []);
    const counts = nb.length ? card("Markets in each price group, 7 days before", ...svgBars(nb.map(x => Math.round(x.lo * 100) + "–" + Math.round(x.hi * 100)), [{ name: "Markets", values: nb.map(x => x.n), color: css("--s1") }],
      { yFmt: v => num(v), extra: i => " · resolved Yes " + prob(nb[i].freq) }), note("How many resolved markets sat in each price group. Groups with few markets give a jumpy point above.")) : null;
    const cats = card("By category, 7 days before", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Category", "Markets", "Brier score", "Resolved Yes"].map(h => el("th", {}, h))),
      ...(d.by_cat || []).map(c => el("tr", {}, el("td", {}, c.cat), el("td", {}, num(c.n)), el("td", {}, c.brier == null ? "–" : c.brier.toFixed(3)), el("td", {}, prob(c.base)))))),
      note("Brier score: the average squared gap between the price and the outcome (0 is perfect; always saying 50% scores 0.25). Lower is better."));
    const miss = (d.misses || []).length ? card("Big misses: priced 70+ points away a week before", marketTable((d.misses || []).map(m => ({ q: m.q, yes: m.p7, d1: null, vol: m.vol, end: new Date(m.closed * 1000).toISOString().slice(0, 10) })), ["yes", "vol", "end"]),
      note("Chance a week before resolution; each resolved the other way. The most traded first.")) : null;
    return [hd, cal, el("div", { class: "grid2" }, counts, cats), miss, nfa()].filter(Boolean);
  },
};

window.TOPIC = { VIEWS };
})();
