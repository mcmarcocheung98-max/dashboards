// Options Setup: what the options market is pricing on the AI stocks and the indexes. Data from /api/options/<setup|chains|vol|skew|moves|lab>
// and /api/options/chain-<SYM> for one symbol's chain; helpers (el, card, kpi, linesChart, svgLines, svgBars, followHead, csv...) from topic.html.
// Read-only analysis, not investment advice: the page describes what listed options imply and makes no buy or sell call; the Strategy lab is a
// calculator, nothing is traded or stored. Leans: +1 = calmer pricing, -1 = stress.
(() => {
const SMALL = "Not investment advice: what the options market is pricing, not what to do.";
const DELAYED = "Cboe delayed quotes (15 minutes); outside market hours the last session's close.";
const GROUP = { index: "Index ETFs", core: "AI basket", picks: "Owner's picks", owner: "Added by the owner" };
const ivf = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const ptsf = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(1) + " pts";
const dateOf = s => s ? new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) : "–";
const shortDate = s => s ? new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", timeZone: "UTC" }) : "–";
const table = (heads, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...heads.map(h => el("th", {}, h))), ...rows));
const td = (v, c, style) => el("td", { ...(c ? { class: c } : {}), ...(style ? { style } : {}) }, v);
const money = v => v == null ? "–" : (v < 0 ? "−$" : "$") + big(Math.abs(v));
const SEL = "padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit";
const sel = (opts, cur, onchange, style) => el("select", { style: style || SEL, onchange }, ...opts.map(([v, l]) => { const o = el("option", { value: v }, l); if (String(v) === String(cur)) o.selected = true; return o; }));
const numIn = (v, step, onchange, w) => el("input", { type: "number", step, value: v, style: "width:" + (w || 90) + "px;" + SEL, onchange });
const verify = e => e && e.verify ? el("span", { class: "pill", title: "entered from the company's usual cadence, not yet confirmed on its investor-relations page", style: "margin-left:4px;font-size:11px" }, "verify") : null;
const ctl = (label, control) => el("label", { style: "display:inline-flex;flex-direction:column;gap:3px;font-size:12px;color:var(--muted)" }, label, control);
const errs = (d, what) => d && d.errors && Object.keys(d.errors).length ? el("div", { class: "muted" }, what + " not available right now: " + Object.entries(d.errors).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
const rankCls = v => v == null ? "" : v > 80 ? "down" : v < 20 ? "up" : "";
const rankTag = r => r.rank_basis === "VIX fallback" ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px", title: "fewer than 60 days of this symbol's own IV history (" + (r.rank_days || 0) + " so far): the VIX's rank and percentile over a year stand in" }, "VIX")
  : r.rank_basis === "thin history" ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px", title: "only " + (r.rank_days || 0) + " days of history: read with care until 60 exist" }, (r.rank_days || 0) + "d") : null;
const thinNote = (days, what) => days < 60 ? el("div", { class: "warn", style: "margin-top:6px" }, (what || "History") + " accrues one point per trading day from the day this dashboard first ran: " + days + " of 60 days so far, so ranks and percentiles are thin. The index ETFs use the VIX's percentile until then.") : null;
const groupRows = (rows, build) => Object.entries(GROUP).flatMap(([g, lab]) => { const rs = rows.filter(r => r.group === g); return rs.length ? [el("tr", {}, el("td", { colspan: 20, style: "font-weight:650;color:var(--ink2);background:var(--chip)" }, lab)), ...rs.map(build)] : []; });
const symOpts = syms => syms.map(s => [s.sym, s.sym + " · " + (s.name || "")]);
const sym0 = (d, pref) => (d.order || (d.symbols || []).map(s => s.sym)).find(s => s === pref) || (d.order || [])[0] || ((d.symbols || [])[0] || {}).sym;

// ---------- Black-Scholes (the Strategy lab's pricing on a chosen date and its probability of profit; lognormal returns assumed)
const ncdf = x => 0.5 * (1 + erf(x / Math.SQRT2));
function erf(x) { const s = Math.sign(x), a = Math.abs(x), t = 1 / (1 + 0.3275911 * a); return s * (1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-a * a)); }
function bs(cp, s, k, t, iv, r) {
  if (t <= 0 || iv <= 0) return cp === "C" ? Math.max(0, s - k) : Math.max(0, k - s);
  const sq = iv * Math.sqrt(t), d1 = (Math.log(s / k) + (r + iv * iv / 2) * t) / sq, d2 = d1 - sq, disc = Math.exp(-r * t);
  return cp === "C" ? s * ncdf(d1) - k * disc * ncdf(d2) : k * disc * ncdf(-d2) - s * ncdf(-d1);
}
const probAbove = (s, k, t, iv, r) => t <= 0 || iv <= 0 ? (s > k ? 1 : 0) : ncdf((Math.log(s / k) + (r - iv * iv / 2) * t) / (iv * Math.sqrt(t)));

// ---------- one symbol's chain, fetched once per page view
const CHAINS = {};
const chainOf = sym => CHAINS[sym] || (CHAINS[sym] = api("chain-" + sym).catch(e => { delete CHAINS[sym]; throw e; }));

// ---------- the VIX, VIX3M, term spread and SKEW charts (Setup and Volatility)
function vixCards(d) {
  const out = [];
  if (d.vix || d.vix3m) out.push(card("VIX and VIX3M: 30-day and 3-month implied volatility of the S&P 500",
    ...linesChart([{ name: "VIX", points: d.vix || [], color: css("--s1") }, { name: "VIX3M", points: d.vix3m || [], color: css("--s2") }], v => num(v, 1), { hlines: [20, 30] }),
    ...(d.vix_term ? linesChart([{ name: "VIX3M minus VIX", points: d.vix_term, color: css("--s3"), bar: true }], v => num(v, 1), { small: true }) : []),
    note("Top: VIX (30-day) and VIX3M (3-month), dashed at 20 and 30. Bottom: the term spread, VIX3M minus VIX; below zero the curve is inverted, the market paying more for near cover than for later, the stress sign. Cboe daily closes. " + SMALL)));
  if (d.skew_index || d.vvix) out.push(card("Cboe SKEW and VVIX: tail-risk pricing and the volatility of volatility",
    ...(d.skew_index ? linesChart([{ name: "SKEW", points: d.skew_index, color: css("--s4") }], v => num(v, 0), { small: true, hlines: [130, 150] }) : []),
    ...(d.vvix ? linesChart([{ name: "VVIX", points: d.vvix, color: css("--s5") }], v => num(v, 0), { small: true, hlines: [100] }) : []),
    note("SKEW measures how much more the market pays for far out-of-the-money S&P puts than the lognormal model says (100 = none; 130-150 usual; higher = fatter left tail priced). VVIX is the implied volatility of VIX options.")));
  return out;
}

const VIEWS = {
  async setup() {
    const d = await api("setup"), H = d.head || {}, B = d.basket || {}, rows = d.table || [];
    const head = card("Where options are pricing the AI dip", followHead([
      { label: "VIX", points: d.vix || [], fmt: v => num(v, 1), cls: v => v > 30 ? "down" : v < 20 ? "up" : "" },
      { label: "VIX3M minus VIX (term structure)", points: d.vix_term || [], fmt: v => (v > 0 ? "+" : "") + num(v, 1), cls: v => v < 0 ? "down" : v > 2 ? "up" : "" },
      { label: "Cboe SKEW", points: d.skew_index || [], fmt: v => num(v, 0), cls: v => v > 150 ? "down" : "" },
      ...(d.ai_rank_hist && d.ai_rank_hist.length ? [{ label: "AI basket median IV rank", points: d.ai_rank_hist, fmt: v => num(v, 0), cls: rankCls }] : []),
      ...(d.vrp_hist && d.vrp_hist.length ? [{ label: "Symbols with IV above realised", points: d.vrp_hist, fmt: v => num(v, 0) + "%", cls: v => v < 30 ? "down" : "" }] : [])]),
      el("div", { class: "kpis", style: "margin-top:8px" },
        kpi("AI basket median IV rank", H.ai_iv_rank == null ? "–" : num(H.ai_iv_rank, 0) + (B.thin && B.thin.length ? " (thin)" : ""), rankCls(H.ai_iv_rank)),
        kpi("Symbols with IV above 30-day realised", H.vrp_share == null ? "–" : num(H.vrp_share, 0) + "% (" + B.vrp_above + " of " + B.vrp_n + ")", H.vrp_share != null && H.vrp_share < 30 ? "down" : ""),
        kpi("AI basket median 25-delta skew", ptsf(H.ai_skew), H.ai_skew > 0.08 ? "down" : ""), kpi("VVIX", num(H.vvix, 0)), kpi("SPY put/call (OI)", num(H.spy_pc_oi, 2), H.spy_pc_oi > 2 ? "down" : ""),
        kpi("Days of accrued history", num(B.history_days))),
      el("p", { style: "margin:10px 0 0;line-height:1.5" }, H.where || ""),
      thinNote(B.history_days || 0, "IV rank history"), note(DELAYED + " VIX, VIX3M, SKEW and VVIX are Cboe's daily closes" + (H.vix_date ? " to " + dateOf(H.vix_date) : "") + ". " + SMALL), errs(d, "Some chains are"), asOf(d), stale(d));
    const emf = r => r.em_straddle == null && r.em_iv == null ? "–" : ivf(r.em_straddle) + " / " + ivf(r.em_iv);
    const T = card("Each symbol: what its options price today", table(["Symbol", "Spot", "Day", "ATM IV (front)", "IV rank", "IV pct", "Exp. move to next monthly (straddle / IV)", "25Δ skew", "P/C OI", "P/C vol", "Next earnings"],
      groupRows(rows, r => r.error ? el("tr", {}, td(el("b", {}, r.sym)), el("td", { colspan: 10, class: "muted" }, "not available right now (" + r.error + ")"))
        : el("tr", {}, td([el("b", {}, r.sym), " ", el("span", { class: "muted" }, r.name), r.both ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px" }, "both") : null]),
          td(usd(r.spot, 2)), td(r.chg == null ? "–" : pct(r.chg / 100, 2), cls(r.chg)),
          td(r.atm_iv == null ? "–" : [ivf(r.atm_iv), el("span", { class: "muted" }, " " + shortDate(r.front))]),
          td([r.rank == null ? "–" : num(r.rank, 0), rankTag(r)], rankCls(r.rank), tint(r.rank == null ? null : r.rank - 50, 50, r.rank > 50 ? "--down" : "--up")),
          td(r.pct == null ? "–" : num(r.pct, 0)), td(r.em_exp ? [emf(r), el("span", { class: "muted" }, " to " + shortDate(r.em_exp) + " (" + r.em_dte + "d)")] : "–"),
          td(ptsf(r.skew), r.skew > 0.08 ? "down" : ""), td(num(r.pc_oi, 2), r.pc_oi > 2 ? "down" : ""), td(num(r.pc_vol, 2)),
          td(r.earnings ? [shortDate(r.earnings), verify({ verify: r.earnings_verify })] : el("span", { class: "muted" }, "–"))))),
      note("ATM IV: the mean of the call and put implied volatility at the strike nearest spot, for the front month (the nearest standard monthly expiry at least 5 days out). IV rank: where that IV sits between its lowest and highest over the accrued history (up to a year); IV percentile: the share of days it was lower. " +
        "Expected move to the next monthly: the ATM straddle's mid as a share of spot, and spot × IV × √T (one standard deviation). 25Δ skew: 25-delta put IV minus 25-delta call IV, in volatility points; higher = puts richer. P/C: put/call ratios over every listed expiry within 400 days, by open interest and by the day's volume. Earnings dates marked verify come from the company's usual cadence. " + SMALL));
    return [head, ...vixCards(d), T];
  },

  async chains() {
    const d = await api("chains"), syms = (d.symbols || []).filter(s => !s.error);
    if (!syms.length) return [card("Chains", el("div", { class: "muted" }, "No chain is available right now."), errs(d, "Chains"))];
    const state = { sym: sym0({ symbols: syms }, d.default), exp: null, around: 16 };
    const box = el("div", {});
    const controls = el("div", { style: "display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:8px" });
    const render = async () => {
      box.replaceChildren(el("div", { class: "muted" }, "Loading " + state.sym + "…"));
      let C;
      try { C = await chainOf(state.sym); } catch (e) { box.replaceChildren(el("div", { class: "muted" }, "Not available right now (" + e.message + ").")); return; }
      const exps = C.expiries || [];
      if (!exps.find(x => x.exp === state.exp)) state.exp = (exps.find(x => x.monthly && x.dte >= 5) || exps[0] || {}).exp;
      controls.replaceChildren(
        ctl("Symbol", sel(symOpts(syms), state.sym, e => { state.sym = e.target.value; state.exp = null; render(); })),
        ctl("Expiry", sel(exps.map(x => [x.exp, dateOf(x.exp) + " · " + x.dte + "d" + (x.monthly ? " · monthly" : "")]), state.exp, e => { state.exp = e.target.value; render(); })),
        ctl("Strikes around spot", sel([[8, "8"], [16, "16"], [30, "30"], [0, "all"]], state.around, e => { state.around = Number(e.target.value); render(); })));
      const E = (C.chains || {})[state.exp], row = exps.find(x => x.exp === state.exp) || {};
      if (!E) { box.replaceChildren(el("div", { class: "muted" }, "No quotes for this expiry.")); return; }
      const strikes = [...new Set(E.lines.map(l => l.k))].sort((a, b) => a - b);
      const ai = strikes.indexOf(E.atm), from = state.around ? Math.max(0, ai - state.around / 2) : 0, to = state.around ? Math.min(strikes.length, ai + state.around / 2 + 1) : strikes.length;
      const shown = strikes.slice(from, to);
      const by = new Map(E.lines.map(l => [l.cp + l.k, l]));
      const side = l => l ? [td(num(l.bid, 2)), td(num(l.ask, 2)), td(num(l.last, 2)), td(num(l.vol), l && l.oi && l.vol / l.oi > 5 && l.vol >= 1000 ? "up" : ""), td(num(l.oi)), td(ivf(l.iv)), td(num(l.delta, 2))] : Array.from({ length: 7 }, () => td("–"));
      const T = el("div", { class: "scroll" }, el("table", { style: "font-size:12.5px" },
        el("tr", {}, el("th", { colspan: 7, style: "text-align:center;color:var(--up)" }, "Calls"), el("th", { style: "text-align:center" }, "Strike"), el("th", { colspan: 7, style: "text-align:center;color:var(--down)" }, "Puts")),
        el("tr", {}, ...["Bid", "Ask", "Last", "Vol", "OI", "IV", "Δ"].map(h => el("th", {}, h)), el("th", {}, ""), ...["Bid", "Ask", "Last", "Vol", "OI", "IV", "Δ"].map(h => el("th", {}, h))),
        ...shown.map(k => el("tr", { style: k === E.atm ? "background:var(--chip);font-weight:650" : "" }, ...side(by.get("C" + k)),
          td([num(k, k % 1 ? 2 : 0), k === E.atm ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px" }, "ATM") : null, k === row.max_pain ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px" }, "max pain") : null], "", "text-align:center;white-space:nowrap"),
          ...side(by.get("P" + k))))));
      const csv = csvButton(csvName(state.sym + " " + state.exp + " chain"), () => csvText(["strike", "call_bid", "call_ask", "call_last", "call_vol", "call_oi", "call_iv", "call_delta", "put_bid", "put_ask", "put_last", "put_vol", "put_oi", "put_iv", "put_delta"],
        strikes.map(k => { const c = by.get("C" + k) || {}, p = by.get("P" + k) || {}; return [k, c.bid, c.ask, c.last, c.vol, c.oi, c.iv, c.delta, p.bid, p.ask, p.last, p.vol, p.oi, p.iv, p.delta]; })));
      const gex = E.gex || [], gk = gex.map(g => g[0]), gi = gk.indexOf(E.atm), gfrom = state.around ? Math.max(0, gi - state.around) : 0, gto = state.around ? Math.min(gex.length, gi + state.around + 1) : gex.length;
      const G = gex.slice(gfrom, gto), mp = G.findIndex(g => g[0] === row.max_pain), sp = G.findIndex(g => g[0] === E.atm);
      box.replaceChildren(
        el("div", { class: "kpis", style: "margin-bottom:8px" }, kpi("Spot", usd(C.spot, 2)), kpi("ATM strike", num(E.atm, E.atm % 1 ? 2 : 0)), kpi("ATM IV", ivf(row.atm_iv)), kpi("Straddle", row.straddle == null ? "–" : usd(row.straddle, 2) + " (" + ivf(row.em_straddle) + ")"),
          kpi("Max pain", row.max_pain == null ? "–" : num(row.max_pain, row.max_pain % 1 ? 2 : 0)), kpi("P/C OI", num(row.pc_oi, 2)), kpi("Open interest", big(row.oi)), kpi("Dealer GEX, this expiry", money(E.gex_total))),
        el("div", { class: "legend" }, csv), T,
        note("Strikes 60-150% of spot are kept; the ATM row is the strike nearest spot. Volume in green: more than 5 times the open interest with at least 1,000 contracts (new positions, not rolls). Max pain: the strike at which this expiry's open interest would be worth least if the stock closed there. " + DELAYED),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Dealer gamma exposure by strike, " + dateOf(state.exp)),
        ...svgBars(G.map(g => num(g[0], g[0] % 1 ? 2 : 0)), [{ name: "GEX ($ per 1% move)", values: G.map(g => g[1]), colorFn: v => v >= 0 ? css("--up") : css("--down") }],
          { yFmt: v => money(v), catHead: "strike", marks: [...(sp >= 0 ? [{ i: sp, color: css("--ink"), text: "spot" }] : []), ...(mp >= 0 && mp !== sp ? [{ i: mp, color: css("--muted"), text: "max pain", dy: 12 }] : [])], h: 240 }),
        note("GEX per strike = gamma × open interest × 100 × spot² × 1%, calls positive and puts negative: the convention that dealers are long the calls customers sold and short the puts customers bought. Positive total: dealers hedge against the move (dampening); negative: they hedge with it (amplifying). A convention and a delayed snapshot of open interest, not knowledge of anyone's book; it says nothing about who holds what. " + SMALL));
    };
    render();
    return [card("Chains: pick a symbol and an expiry", controls, box, asOf(d), stale(d))];
  },

  async vol() {
    const d = await api("vol"), S = d.symbols || {}, order = (d.order || []).filter(s => S[s]), B = d.basket || {};
    if (!order.length) return [card("Volatility", el("div", { class: "muted" }, "No chain is available right now."))];
    const head = card("Implied against realised", followHead([
      { label: "VIX", points: d.vix || [], fmt: v => num(v, 1), cls: v => v > 30 ? "down" : v < 20 ? "up" : "" },
      { label: "VIX3M", points: d.vix3m || [], fmt: v => num(v, 1) },
      { label: "VVIX", points: d.vvix || [], fmt: v => num(v, 0) },
      { label: "Cboe SKEW", points: d.skew_index || [], fmt: v => num(v, 0), cls: v => v > 150 ? "down" : "" }]),
      el("div", { class: "kpis", style: "margin-top:8px" }, kpi("Symbols with front IV above 30-day realised", B.vrp_share == null ? "–" : num(B.vrp_share, 0) + "% (" + B.vrp_above + " of " + B.vrp_n + ")", B.vrp_share < 30 ? "down" : ""),
        kpi("AI basket median IV rank", num(B.iv_rank, 0), rankCls(B.iv_rank)), kpi("Days of accrued IV history", num(B.history_days))),
      note("Implied volatility is what options price for the period ahead; realised is what the stock did (annualised standard deviation of daily log returns over 10 and 30 trading days). The gap, implied minus realised, is the variance risk premium: usually positive (options carry a premium), negative when the market moves more than options priced. " + SMALL),
      thinNote(B.history_days || 0, "IV history"), asOf(d), stale(d));
    const state = { sym: sym0(d, "NVDA") };
    const box = el("div", {});
    const withTerm = order.filter(k => (S[k].term || []).filter(t => t[1] != null).length > 1).sort((a, b) => ((S[a].front || {}).atm_iv || 0) - ((S[b].front || {}).atm_iv || 0));
    const surf = withTerm.length > 2 ? card("The volatility surface in 3D: ATM implied volatility by symbol and days to expiry",
      ...chart3d({ ...grid3d(withTerm.map(k => ({ name: k, points: S[k].term.filter(t => t[0] <= 400).map(t => [t[0], t[1]]) })), true), mode: "surface", zero: false,
        xFmt: v => v + "d", zFmt: ivf, xHead: "days to expiry", csvName: "iv surface", h: 460,
        note: "Symbols run front to back from the calmest to the most volatile; expiries run left to right. Drag to turn; hover for a point." }),
      note("Every symbol's term structure in one picture, expiries up to 400 days. A ridge near the left edge is an event priced into the front expiries (earnings); a surface that climbs to the right is the calm, upward-sloping shape. Between two listed expiries the height is read off the straight line joining them.")) : null;
    const render = () => {
      const s = S[state.sym], R = s.rank || {};
      const ivSeries = [{ name: "ATM IV, front month (daily snapshots)", points: s.iv_hist || [], color: css("--s1") }, { name: "30-day realised", points: s.rv30_hist || [], color: css("--s2") }, { name: "10-day realised", points: s.rv10_hist || [], color: css("--s3"), dashed: true }];
      const term = [{ name: "Today", points: (s.term || []).map(t => [t[0], t[1]]), color: css("--s1") }, ...(s.term_week_ago && s.term_week_ago.points.length ? [{ name: "A week ago (" + shortDate(s.term_week_ago.date) + ")", points: s.term_week_ago.points, color: css("--s2"), dashed: true }] : [])];
      box.replaceChildren(
        el("div", { class: "kpis", style: "margin-bottom:8px" }, kpi("Spot", usd(s.spot, 2)), kpi("Cboe IV30", s.iv30 == null ? "–" : num(s.iv30, 1) + "%"), kpi("ATM IV, front (" + shortDate((s.front || {}).exp) + ")", ivf((s.front || {}).atm_iv)),
          kpi("Realised 10d / 30d", ivf(s.rv10) + " / " + ivf(s.rv30)), kpi("IV minus realised 30d", (s.front || {}).atm_iv != null && s.rv30 != null ? ptsf(s.front.atm_iv - s.rv30) : "–", (s.front || {}).atm_iv < s.rv30 ? "down" : "up"),
          kpi("IV rank / percentile" + (R.basis === "history" ? "" : " (" + R.basis + ")"), (R.rank == null ? "–" : num(R.rank, 0)) + " / " + (R.pct == null ? "–" : num(R.pct, 0)), rankCls(R.rank))),
        el("h3", { style: "margin:10px 0 6px;font-size:15px" }, "Implied vs realised over time"),
        ...linesChart(ivSeries, ivf, {}),
        note("Realised volatility runs back through the closes (Nasdaq, via the AI Stocks dashboard); the implied line has one point per trading day since this dashboard first ran (" + s.history_days + " so far)."),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Term structure: ATM IV by days to expiry, today and a week ago"),
        ...svgLines(term, { xFmt: v => v + "d", yFmt: ivf, h: 220, xName: "days to expiry", note: "Hover for a point. Upward sloping = near-term calm, longer-dated priced higher; inverted = an event or stress near term." }),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "IV rank over time"),
        ...(s.rank_hist && s.rank_hist.length >= 2 ? linesChart([{ name: "IV rank", points: s.rank_hist, color: css("--s4") }], v => num(v, 0), { small: true, hlines: [20, 80] }) : [el("div", { class: "muted" }, "Needs at least two days of history.")]));
    };
    render();
    const pick = card("One symbol", el("div", { style: "margin-bottom:8px" }, ctl("Symbol", sel(order.map(k => [k, k + " · " + S[k].name]), state.sym, e => { state.sym = e.target.value; render(); }))), box);
    const T = card("Every symbol: implied against realised", table(["Symbol", "Spot", "IV30 (Cboe)", "ATM IV front", "Realised 10d", "Realised 30d", "IV − RV30", "IV rank", "IV pct", "History"],
      groupRows(order.map(k => ({ sym: k, ...S[k] })), s => { const f = s.front || {}, R = s.rank || {}; return el("tr", {}, td([el("b", {}, s.sym), " ", el("span", { class: "muted" }, s.name)]), td(usd(s.spot, 2)), td(s.iv30 == null ? "–" : num(s.iv30, 1) + "%"),
        td(ivf(f.atm_iv)), td(ivf(s.rv10)), td(ivf(s.rv30)), td(f.atm_iv != null && s.rv30 != null ? ptsf(f.atm_iv - s.rv30) : "–", f.atm_iv != null && s.rv30 != null ? (f.atm_iv > s.rv30 ? "up" : "down") : ""),
        td([R.rank == null ? "–" : num(R.rank, 0), rankTag({ rank_basis: R.basis, rank_days: R.own_days != null ? R.own_days : R.days })], rankCls(R.rank)), td(R.pct == null ? "–" : num(R.pct, 0)), td(num(s.history_days) + "d")); })),
      note("IV30 is Cboe's own 30-day figure on the quote; the ATM IV is this page's, from the front month's chain. " + SMALL));
    return [head, surf, ...vixCards(d), pick, T].filter(Boolean);
  },

  async skew() {
    const d = await api("skew"), S = d.symbols || {}, order = (d.order || []).filter(s => S[s]), B = d.basket || {}, own = B.skew_pct_own || {}, idx = B.skew_index_rank || {};
    if (!order.length) return [card("Skew & flow", el("div", { class: "muted" }, "No chain is available right now."))];
    const head = card("Skew and positioning", followHead([
      { label: "Cboe SKEW index", points: d.skew_index || [], fmt: v => num(v, 0), cls: v => v > 150 ? "down" : "" },
      ...(d.ai_skew_hist && d.ai_skew_hist.length ? [{ label: "AI basket median 25Δ skew", points: d.ai_skew_hist, fmt: ptsf, cls: v => v > 0.08 ? "down" : "" }] : [])]),
      el("div", { class: "kpis", style: "margin-top:8px" }, kpi("AI basket median 25Δ skew (front)", ptsf(B.skew), B.skew > 0.08 ? "down" : ""),
        kpi("Its percentile" + (own.days >= 60 ? " (own history)" : " (SKEW index fallback)"), own.days >= 60 ? num(own.pct, 0) : idx.pct == null ? "–" : num(idx.pct, 0)),
        kpi("Own skew history", num(own.days || 0) + " of 60 days"), kpi("SPY P/C OI", num(((S.SPY || {}).pc || {}).pc_oi, 2), ((S.SPY || {}).pc || {}).pc_oi > 2 ? "down" : "")),
      note("25-delta skew = the IV of the 25-delta put minus the IV of the 25-delta call, front month, in volatility points: how much more the market pays for downside protection than for upside. The risk reversal is the same number with the opposite sign. Until 60 days of the basket's own skew history exist, its percentile is read off the Cboe SKEW index's year. " + SMALL),
      thinNote(own.days || 0, "Skew history"), asOf(d), stale(d));
    const SK = d.skew_index ? card("Cboe SKEW index and the AI basket's median skew", ...linesChart([{ name: "Cboe SKEW (S&P 500 tail pricing)", points: d.skew_index, color: css("--s4") }], v => num(v, 0), { hlines: [130, 150] }),
      ...(d.ai_skew_hist && d.ai_skew_hist.length >= 2 ? linesChart([{ name: "AI basket median 25Δ skew", points: d.ai_skew_hist, color: css("--s1") }], ptsf, { small: true }) : []),
      note("SKEW: Cboe's daily close. The basket line has one point per trading day since this dashboard first ran.")) : null;
    const T = card("Every symbol: skew and put/call positioning", table(["Symbol", "Spot", "25Δ put IV", "25Δ call IV", "Skew", "Risk reversal", "P/C vol", "P/C OI", "Put OI", "Call OI", "Dealer GEX (all expiries)"],
      groupRows(order.map(k => ({ sym: k, ...S[k] })), s => { const f = s.front || {}, pc = s.pc || {}; return el("tr", {}, td([el("b", {}, s.sym), " ", el("span", { class: "muted" }, s.name)]), td(usd(s.spot, 2)), td(ivf(f.put25)), td(ivf(f.call25)),
        td(ptsf(f.skew), f.skew > 0.08 ? "down" : "", tint(f.skew, 0.15, "--down")), td(ptsf(f.rr)), td(num(pc.pc_vol, 2), pc.pc_vol > 1.5 ? "down" : ""), td(num(pc.pc_oi, 2), pc.pc_oi > 2 ? "down" : ""), td(big(pc.put_oi)), td(big(pc.call_oi)), td(money(s.gex_total), cls(s.gex_total))); })),
      note("Front month. P/C ratios over every listed expiry within 400 days and strikes 60-150% of spot. Dealer GEX: calls positive, puts negative (dealers long calls, short puts), dollars per 1% move; a convention, see Chains."));
    const state = { sym: sym0(d, "SPY") };
    const box = el("div", {});
    const render = () => {
      const s = S[state.sym], nxt = s.next_monthly || {}, oi = s.oi_by_strike || [];
      const ai = oi.reduce((b, r, i) => Math.abs(r[0] - s.spot) < Math.abs(oi[b][0] - s.spot) ? i : b, 0);
      box.replaceChildren(
        el("h3", { style: "margin:4px 0 6px;font-size:15px" }, "Skew by expiry"),
        ...svgLines([{ name: "25Δ skew (put − call IV)", points: (s.skew_term || []).map(t => [t[0], t[1]]), color: css("--s1") }], { xFmt: v => v + "d", yFmt: ptsf, h: 200, xName: "days to expiry", hline: 0, note: "Hover for a point. Skew usually falls with time to expiry; a hump near an event is the market paying for that date." }),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Open interest by strike, next monthly (" + dateOf(nxt.exp) + ", " + (nxt.dte == null ? "–" : nxt.dte + "d") + ")"),
        ...(oi.length ? svgBars(oi.map(r => num(r[0], r[0] % 1 ? 2 : 0)), [{ name: "Calls", values: oi.map(r => r[1]), color: css("--up") }, { name: "Puts", values: oi.map(r => r[2]), color: css("--down") }],
          { yFmt: v => big(v), catHead: "strike", marks: [{ i: ai, color: css("--ink"), text: "spot" }, ...(nxt.max_pain != null && oi.findIndex(r => r[0] === nxt.max_pain) >= 0 ? [{ i: oi.findIndex(r => r[0] === nxt.max_pain), color: css("--muted"), text: "max pain", dy: 12 }] : [])], h: 240 }) : [el("div", { class: "muted" }, "No open interest data.")]),
        note("Large put open interest below spot is where protection sits (and where dealers' hedging can pin or accelerate a move); large call open interest above is where upside has been sold. Positioning as of the last session, not a forecast."),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Skew and P/C OI over time"),
        ...((s.skew_hist || []).length >= 2 ? linesChart([{ name: "25Δ skew, front", points: s.skew_hist, color: css("--s1") }, { name: "P/C OI", points: s.pc_oi_hist || [], color: css("--s2"), axis: "left", fmt: v => num(v, 2) }], ptsf, { small: true }) : [el("div", { class: "muted" }, "Needs at least two days of history (" + s.history_days + " so far).")]));
    };
    render();
    const pick = card("One symbol", el("div", { style: "margin-bottom:8px" }, ctl("Symbol", sel(order.map(k => [k, k + " · " + S[k].name]), state.sym, e => { state.sym = e.target.value; render(); }))), box);
    const U = d.unusual || [], th = d.thresholds || { ratio: 5, volume: 1000 };
    const UA = card("Unusual activity: volume more than " + th.ratio + "× open interest, at least " + num(th.volume) + " contracts",
      U.length ? table(["Symbol", "Expiry", "Type", "Strike", "vs spot", "Volume", "Open interest", "Vol / OI", "IV", "Mid", "Premium traded"],
        U.map(u => el("tr", {}, td(el("b", {}, u.sym)), td([shortDate(u.exp), el("span", { class: "muted" }, " " + u.dte + "d")]), td(u.cp === "C" ? "Call" : "Put", u.cp === "C" ? "up" : "down"), td(num(u.strike, u.strike % 1 ? 2 : 0)), td(pct(u.otm, 1), cls(u.otm)),
          td(num(u.vol)), td(num(u.oi)), td(num(u.ratio, 1) + "×"), td(ivf(u.iv)), td(usd(u.mid, 2)), td(money(u.premium)))))
        : el("div", { class: "muted" }, "No line met the test in the last session."),
      note("Premium traded = volume × mid × 100, an upper bound on what changed hands at the mid. A high ratio means positions opened that day rather than rolled; it does not say whether they were bought or sold, or by whom. Deep out-of-the-money lines at a few cents can show huge ratios on tiny premium. " + SMALL));
    return [head, SK, T, pick, UA].filter(Boolean);
  },

  async moves() {
    const d = await api("moves"), S = d.symbols || {}, order = (d.order || []).filter(s => S[s]);
    if (!order.length) return [card("Expected moves", el("div", { class: "muted" }, "No chain is available right now."))];
    const state = { sym: sym0(d, "NVDA") };
    const box = el("div", {});
    const KIND = { earnings: "earnings", fomc: "FOMC", opex: "OPEX" };
    const render = () => {
      const s = S[state.sym], cone = s.cone || [], spot = s.spot, maxd = Math.max(1, ...cone.map(c => c.dte));
      const t0 = Date.parse(s.trade_date || d.as_of) / 1000, X = dte => t0 + dte * 86400;
      const evs = (s.events || []).map(e => ({ ...e, dte: Math.round((Date.parse(e.date) - t0 * 1000) / 864e5) })).filter(e => e.dte >= 0 && e.dte <= maxd);
      const iv = [[0, spot, spot], ...cone.map(c => [c.dte, spot * (1 - c.em_iv), spot * (1 + c.em_iv)])], st = [[0, spot, spot], ...cone.filter(c => c.em_straddle != null).map(c => [c.dte, spot * (1 - c.em_straddle), spot * (1 + c.em_straddle)])];
      const hist = (s.spot_hist || []).filter(p => p[0] >= t0 - 120 * 86400).map(p => [p[0], p[1]]);
      const series = [{ name: "Spot", points: [...hist, [t0, spot]], color: css("--ink") }, { name: "+1σ (IV)", points: iv.map(p => [X(p[0]), p[2]]), color: css("--s1"), dashed: true }, { name: "−1σ (IV)", points: iv.map(p => [X(p[0]), p[1]]), color: css("--s1"), dashed: true },
        { name: "+ straddle", points: st.map(p => [X(p[0]), p[2]]), color: css("--s2"), width: 1 }, { name: "− straddle", points: st.map(p => [X(p[0]), p[1]]), color: css("--s2"), width: 1 }];
      const before = dte => evs.filter(e => e.dte <= dte).map(e => (e.sym ? e.sym + " " : "") + KIND[e.kind] + " " + shortDate(e.date)).join(", ");
      box.replaceChildren(
        el("div", { class: "kpis", style: "margin-bottom:8px" }, kpi("Spot (" + shortDate(s.trade_date) + ")", usd(spot, 2)), kpi("Next earnings", s.earnings ? [shortDate(s.earnings.date), verify(s.earnings)] : "none entered"),
          ...(cone[0] ? [kpi("To " + shortDate(cone[0].exp) + " (" + cone[0].dte + "d)", "±" + ivf(cone[0].em_iv) + " · ±" + usd(spot * cone[0].em_iv, 2))] : [])),
        ...svgLines(series, { xFmt: t => shortDate(new Date(t * 1000).toISOString()), yFmt: v => usd(v, 0), h: 300, xName: "date", bands: [{ name: "±1σ (IV)", points: iv.map(p => [X(p[0]), p[1], p[2]]), color: css("--s1"), opacity: 0.12 }],
          vlines: evs.map(e => ({ x: X(e.dte), label: (e.sym ? e.sym + " " : "") + KIND[e.kind] })), note: "The cone: spot × IV × √T either side of spot to each listed expiry (one standard deviation, about a 68% band if returns were normal), and the straddle-implied band. Dashed verticals: the event calendar." }),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Each expiry"),
        table(["Expiry", "Days", "ATM IV", "Straddle", "Move (straddle)", "Move (IV, 1σ)", "Range (1σ)", "Events before it"],
          cone.map(c => el("tr", { style: c.monthly ? "font-weight:600" : "" }, td([dateOf(c.exp), c.monthly ? el("span", { class: "pill", style: "font-size:10px;margin-left:4px" }, "monthly") : null]), td(num(c.dte)), td(ivf(c.atm_iv)), td(usd(c.straddle, 2)),
            td(c.em_straddle == null ? "–" : "±" + ivf(c.em_straddle)), td("±" + ivf(c.em_iv)), td(usd(spot * (1 - c.em_iv), 2) + " – " + usd(spot * (1 + c.em_iv), 2)), el("td", { class: "wrap", style: "font-size:12px" }, before(c.dte) || "–")))),
        note("Straddle move: the ATM straddle's mid as a share of spot, what the market charges for the move either way (about 0.8σ when prices are lognormal). IV move: spot × ATM IV × √(days/365). Both are the market's price for movement, not a forecast of it. " + SMALL),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Past expected moves against what happened (" + (s.past_n || 0) + " pairs" + (s.past_inside != null ? ", " + num(s.past_inside, 0) + "% ended inside the 1σ band" : "") + ")"),
        (s.past || []).length ? table(["Priced on", "Expiry", "Days", "Spot then", "At expiry", "Expected (1σ)", "Expected (straddle)", "Realised", "Inside 1σ?"],
          s.past.map(p => el("tr", {}, td(shortDate(p.date)), td(shortDate(p.exp)), td(num(p.dte)), td(usd(p.spot, 2)), td(usd(p.end, 2)), td("±" + ivf(p.em_iv)), td(p.em_straddle == null ? "–" : "±" + ivf(p.em_straddle)), td(pct(p.realised, 1), cls(p.realised)), td(p.inside ? "yes" : "no", p.inside ? "up" : "down"))))
          : el("div", { class: "muted" }, "Fills in as expiries pass: each daily snapshot's expected move is compared with the close at expiry. About 68% should land inside if options price movement fairly; more means options were rich, fewer means cheap."));
    };
    render();
    const pick = card("Expected moves: the cone around spot against the event calendar", el("div", { style: "margin-bottom:8px" }, ctl("Symbol", sel(order.map(k => [k, k + " · " + S[k].name]), state.sym, e => { state.sym = e.target.value; render(); }))), box, asOf(d), stale(d));
    const E = d.events || [];
    const cal = card("Event calendar (data/options/events.csv)", table(["Date", "Symbol", "Kind", "Event", "Note", "Source"],
      E.map(e => el("tr", {}, td(dateOf(e.date)), td(e.sym ? el("b", {}, e.sym) : el("span", { class: "muted" }, "all")), td(KIND[e.kind] || e.kind), td([e.label, verify(e)]), el("td", { class: "wrap", style: "font-size:12px" }, e.note || ""), td(link(host(e.source), e.source))))),
      note("Earnings dates marked verify are entered from each company's usual reporting cadence and not yet confirmed on its investor-relations page; FOMC dates from the Federal Reserve's calendar (2027 provisional); OPEX is the third Friday."));
    return [pick, cal];
  },

  async lab() {
    const d = await api("lab"), syms = d.symbols || [], rate0 = d.rate == null ? 0.04 : d.rate;
    if (!syms.length) return [card("Strategy lab", el("div", { class: "muted" }, "No chain is available right now."))];
    const STRUCT = [["long_call", "Long call"], ["long_put", "Long put"], ["bull_call", "Bull call spread (vertical)"], ["bear_put", "Bear put spread (vertical)"], ["straddle", "Long straddle"], ["strangle", "Long strangle"],
      ["iron_condor", "Iron condor (short)"], ["covered_call", "Covered call (100 shares + short call)"], ["csp", "Cash-secured put (short put)"]];
    const NLEG = { long_call: 1, long_put: 1, bull_call: 2, bear_put: 2, straddle: 1, strangle: 2, iron_condor: 4, covered_call: 1, csp: 1 };
    const state = { sym: sym0({ symbols: syms }, d.default), exp: null, structure: "long_call", ks: null, rate: rate0, days: 0, qty: 1 };
    const box = el("div", {}), controls = el("div", { style: "display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:8px" });
    const warn = el("div", { class: "warn", style: "margin-bottom:8px" }, "A calculator, not an order ticket: it prices structures from the delayed chain mids and a Black-Scholes model, trades nothing and stores nothing. Not investment advice.");
    const legsFor = (structure, strikes, ai) => {
      const k = i => strikes[Math.max(0, Math.min(strikes.length - 1, ai + i))];
      switch (structure) {
        case "long_call": return [{ cp: "C", k: k(0), q: 1 }];
        case "long_put": return [{ cp: "P", k: k(0), q: 1 }];
        case "bull_call": return [{ cp: "C", k: k(0), q: 1 }, { cp: "C", k: k(3), q: -1 }];
        case "bear_put": return [{ cp: "P", k: k(0), q: 1 }, { cp: "P", k: k(-3), q: -1 }];
        case "straddle": return [{ cp: "C", k: k(0), q: 1 }, { cp: "P", k: k(0), q: 1 }];
        case "strangle": return [{ cp: "P", k: k(-3), q: 1 }, { cp: "C", k: k(3), q: 1 }];
        case "iron_condor": return [{ cp: "P", k: k(-6), q: 1 }, { cp: "P", k: k(-3), q: -1 }, { cp: "C", k: k(3), q: -1 }, { cp: "C", k: k(6), q: 1 }];
        case "covered_call": return [{ stock: true, q: 100 }, { cp: "C", k: k(2), q: -1 }];
        case "csp": return [{ cp: "P", k: k(-2), q: -1 }];
      }
      return [];
    };
    const render = async () => {
      box.replaceChildren(el("div", { class: "muted" }, "Loading " + state.sym + "…"));
      let C;
      try { C = await chainOf(state.sym); } catch (e) { box.replaceChildren(el("div", { class: "muted" }, "Not available right now (" + e.message + ").")); return; }
      const exps = C.expiries || [];
      if (!exps.find(x => x.exp === state.exp)) { state.exp = (exps.find(x => x.monthly && x.dte >= 5) || exps[0] || {}).exp; state.ks = null; }
      const E = (C.chains || {})[state.exp], row = exps.find(x => x.exp === state.exp) || {};
      if (!E) { box.replaceChildren(el("div", { class: "muted" }, "No quotes for this expiry.")); return; }
      const spot = C.spot, strikes = [...new Set(E.lines.map(l => l.k))].sort((a, b) => a - b), ai = strikes.indexOf(E.atm), by = new Map(E.lines.map(l => [l.cp + l.k, l]));
      const dte = row.dte || 0;
      if (!state.ks || state.ks.length !== NLEG[state.structure]) state.ks = legsFor(state.structure, strikes, ai).filter(l => !l.stock).map(l => l.k);
      state.days = Math.min(state.days, dte);
      const legs = legsFor(state.structure, strikes, ai).map((l, i, all) => { if (l.stock) return l; const ki = all.slice(0, i).filter(x => !x.stock).length; return { ...l, k: state.ks[ki] != null ? state.ks[ki] : l.k }; });
      // price each option leg from the chain: mid, else last, else Black-Scholes at the expiry's ATM IV; its IV for the dated value
      const T = Math.max(dte, 0.5) / 365, atmIV = row.atm_iv || 0.3;
      for (const l of legs) {
        if (l.stock) { l.price = spot; continue; }
        const q = by.get(l.cp + l.k) || {};
        l.iv = q.iv || atmIV; l.src = q.mid ? "mid" : q.last ? "last" : "model";
        l.price = q.mid || q.last || bs(l.cp, spot, l.k, T, l.iv, state.rate);
      }
      const n = state.qty, mult = 100;
      const pnlAt = (S, tau) => legs.reduce((sum, l) => l.stock ? sum + l.q * n * (S - spot) : sum + l.q * n * mult * ((tau > 0 ? bs(l.cp, S, l.k, tau, l.iv, state.rate) : (l.cp === "C" ? Math.max(0, S - l.k) : Math.max(0, l.k - S))) - l.price), 0);
      const lo = Math.max(0.01, spot * 0.6), hi = spot * 1.4, N = 240, grid = Array.from({ length: N + 1 }, (_, i) => lo + (hi - lo) * i / N);
      const expiry = grid.map(S => [S, pnlAt(S, 0)]), dated = grid.map(S => [S, pnlAt(S, Math.max(dte - state.days, 0) / 365)]);
      const slopeUp = legs.reduce((a, l) => a + (l.stock ? l.q * n / mult : l.cp === "C" ? l.q * n : 0), 0), slopeDn = legs.reduce((a, l) => a + (l.stock ? l.q * n / mult : l.cp === "P" ? -l.q * n : 0), 0);
      const atZero = pnlAt(0.0001, 0), far = pnlAt(spot * 5, 0);
      const vals = expiry.map(p => p[1]).concat([atZero]);
      const maxP = slopeUp > 1e-9 ? Infinity : Math.max(...vals, far), maxL = slopeUp < -1e-9 ? -Infinity : Math.min(...vals, far);
      const bes = []; for (let i = 1; i < expiry.length; i++) { const [a, pa] = expiry[i - 1], [b, pb] = expiry[i]; if ((pa <= 0 && pb > 0) || (pa > 0 && pb <= 0)) bes.push(a + (b - a) * (-pa) / (pb - pa)); }
      const ivMean = legs.filter(l => !l.stock).reduce((a, l) => a + l.iv, 0) / Math.max(1, legs.filter(l => !l.stock).length);
      let pop = 0; { const edges = [0, ...bes, Infinity]; for (let i = 0; i + 1 < edges.length; i++) { const mid = edges[i + 1] === Infinity ? Math.max(edges[i], spot) * 1.5 : (edges[i] + edges[i + 1]) / 2; if (pnlAt(mid, 0) > 0) pop += (edges[i] === 0 ? 1 : probAbove(spot, edges[i], T, ivMean, state.rate)) - (edges[i + 1] === Infinity ? 0 : probAbove(spot, edges[i + 1], T, ivMean, state.rate)); } }
      const debit = legs.reduce((a, l) => l.stock ? a : a + l.q * n * mult * l.price, 0);
      const fm = v => v === Infinity ? "unlimited" : v === -Infinity ? "unlimited" : money(v);
      const kSel = (ki, cur) => sel(strikes.map(k => [k, num(k, k % 1 ? 2 : 0)]), cur, e => { state.ks[ki] = Number(e.target.value); render(); }, SEL + ";padding:2px 4px;font-size:12px");
      let ki = -1;
      const legRows = legs.map(l => { if (l.stock) return el("tr", {}, td((l.q * n > 0 ? "Long " : "Short ") + Math.abs(l.q * n) + " shares"), td("–"), td(usd(spot, 2)), td("–"), td("spot")); ki++;
        return el("tr", {}, td((l.q > 0 ? "Buy " : "Sell ") + Math.abs(l.q * n) + " " + (l.cp === "C" ? "call" : "put")), td(kSel(ki, l.k)), td(usd(l.price, 2)), td(ivf(l.iv)), td(l.src === "model" ? "model (no quote)" : "chain " + l.src)); });
      controls.replaceChildren(
        ctl("Symbol", sel(symOpts(syms), state.sym, e => { state.sym = e.target.value; state.exp = null; state.ks = null; render(); })),
        ctl("Expiry", sel(exps.map(x => [x.exp, dateOf(x.exp) + " · " + x.dte + "d" + (x.monthly ? " · monthly" : "")]), state.exp, e => { state.exp = e.target.value; state.ks = null; render(); })),
        ctl("Structure", sel(STRUCT, state.structure, e => { state.structure = e.target.value; state.ks = null; render(); })),
        ctl("Contracts", numIn(state.qty, 1, e => { state.qty = Math.max(1, Math.round(Number(e.target.value) || 1)); render(); }, 70)),
        ctl("Value on day (0 = today, " + dte + " = expiry)", numIn(state.days, 1, e => { state.days = Math.max(0, Math.min(dte, Math.round(Number(e.target.value) || 0))); render(); }, 80)),
        ctl("Risk-free rate", numIn(+(state.rate * 100).toFixed(2), 0.25, e => { state.rate = (Number(e.target.value) || 0) / 100; render(); }, 80)));
      const vlines = [{ x: spot, label: "spot" }, ...bes.map(b => ({ x: b, label: "BE " + usd(b, 0) }))];
      box.replaceChildren(
        el("div", { class: "kpis", style: "margin-bottom:8px" }, kpi(debit >= 0 ? "Net debit" : "Net credit", money(Math.abs(debit))), kpi("Max profit at expiry", fm(maxP), "up"), kpi("Max loss at expiry", fm(maxL), "down"),
          kpi("Breakeven" + (bes.length === 1 ? "" : "s"), bes.length ? bes.map(b => usd(b, 2)).join(" / ") : "none"), kpi("Probability of profit (model)", (pop * 100).toFixed(0) + "%"), kpi("Spot · ATM IV · days", usd(spot, 2) + " · " + ivf(atmIV) + " · " + dte)),
        table(["Leg", "Strike", "Price", "IV", "Priced from"], legRows),
        el("h3", { style: "margin:14px 0 6px;font-size:15px" }, "Profit and loss by underlying price"),
        ...svgLines([{ name: "At expiry", points: expiry, color: css("--s1") }, { name: "On day " + state.days + " (Black-Scholes, each leg at its chain IV)", points: dated, color: css("--s2"), dashed: true }],
          { xFmt: v => usd(v, 0), yFmt: v => money(v), hline: 0, vlines, h: 280, xName: "underlying price", note: "Hover for a price. Solid: at expiry. Dashed: the model value on the chosen day, holding each leg's implied volatility." }),
        note("Prices are the chain's bid-ask mids (the last trade where there is no two-sided quote; a model price where there is neither), " + DELAYED.toLowerCase() + " Max profit and loss are at expiry over 0 to 5× spot; a side that keeps growing is marked unlimited. " +
          "Probability of profit: the chance that the price at expiry lands where the expiry line is above zero, under a lognormal model with the legs' mean IV and the risk-free rate as drift (a model assumption, not a forecast; real returns have fatter tails). Commissions, assignment, early exercise and dividends are left out. " + SMALL));
    };
    render();
    return [card("Strategy lab: a payoff calculator on the live chain", warn, controls, box, asOf(d), stale(d))];
  },
};
window.TOPIC = { VIEWS, presets: [["1m", "1M", 30], ["3m", "3M", 91], ["6m", "6M", 182], ["1y", "1Y", 365], ["3y", "3Y", 1096], ["all", "All", 0]] };
})();
