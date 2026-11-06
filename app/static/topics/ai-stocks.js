// AI Stocks: the setup after the dip. Data from /api/ai-stocks/<setup|drawdown|trend|dips|fear|fundamentals>; helpers from topic.html.
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
    return [head, cards, picks, L];
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
    return [head, sum, B, T, C];
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
};
window.TOPIC = { VIEWS };
})();
