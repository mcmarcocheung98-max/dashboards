// Memecoins: tabs and cards. Data from /api/memecoins/<basket|season> (app/topics/memecoins.py); helpers from topic.html.
(() => {
const usdBig = v => v == null ? "–" : "$" + big(v);
const px = v => v == null ? "–" : v >= 1000 ? "$" + num(v, 0) : v >= 1 ? "$" + v.toFixed(2) : v >= 0.01 ? "$" + v.toFixed(4) : "$" + v.toPrecision(3);
const r1 = v => v == null ? "–" : v.toFixed(0);
const rsiCls = v => v == null ? "" : v >= 70 ? "down" : v <= 30 ? "up" : "";
const STATE = { "meme season": "up", "out of season": "down" };

// every chart opens on the last year unless the reader already picked a range on this page
try { if (!sessionStorage.getItem("range:" + location.pathname)) RANGE = "1y"; } catch (e) { RANGE = "1y"; }

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

const VIEWS = {
  async basket() {
    const d = await api("basket");
    const live = (d.coins || []).filter(c => c.kpi);
    const best = live.slice().sort((a, b) => (b.kpi.vs_btc_90d ?? -9) - (a.kpi.vs_btc_90d ?? -9))[0];
    const head = card(null, el("div", { class: "kpis" },
      kpi("Basket market cap", usdBig(d.basket_mcap)), kpi("Coins in the basket", live.length + " of " + (d.coins || []).length),
      kpi("Beating BTC over 90 days", live.filter(c => (c.kpi.vs_btc_90d || 0) > 0).length + " of " + live.length),
      best ? kpi("Strongest vs BTC, 90 days", best.ticker + " " + pct(best.kpi.vs_btc_90d, 0), cls(best.kpi.vs_btc_90d)) : null,
      kpi("As of", d.as_of || "–")));
    const rebased = card("Each coin and BTC, rebased to 100 a year ago (log)",
      ...linesChart([...live.map(c => ({ name: c.ticker, points: c.rebased })), { name: "BTC", points: d.btc_rebased, dashed: true, color: css("--hold"), width: 2 }],
        v => v == null ? "–" : num(v, 0), { log: true }),
      note("Above BTC's dashed line: beat holding Bitcoin over the period shown. Click a name in the legend to hide it."));
    return [head, card("The basket", basketTable(d.coins || []),
        note("Click a column to sort. RSI above 70 (red) = has run hard; below 30 (green) = washed out. Beta: how much the coin moves for each 1% BTC move (clamped 0.5-3).")),
      rebased, el("div", { class: "grid2" }, ...live.map(sparkCard)), stale(d)];
  },
  async season() {
    const d = await api("season");
    const K = d.kpi;
    if (!K) return [card(null, el("div", { class: "muted" }, "Prices are loading in the background, back in a few minutes."), stale(d))];
    const rules = d.rules || {};
    const head = card(null, el("div", { style: "font-size:20px;font-weight:650;margin-bottom:6px" }, "Reading: ", el("span", { class: STATE[K.state] || "" }, K.state)),
      el("div", { class: "kpis" },
        kpi("Basket vs BTC, 90 days", pct(K.vs_btc_90d, 0), cls(K.vs_btc_90d)), kpi("Basket vs BTC, 30 days", pct(K.vs_btc_30d, 0), cls(K.vs_btc_30d)),
        kpi("RSI of basket ÷ BTC", r1(K.rsi_vs_btc), rsiCls(K.rsi_vs_btc)), kpi("Basket ÷ BTC from its 1-year high", pct(K.from_high, 0), cls(K.from_high)),
        kpi("Basket market cap", usdBig(K.basket_mcap)), kpi("Basket market cap, 1 year", pct(K.basket_1y, 0), cls(K.basket_1y))),
      note("Meme season: the basket has beaten BTC by " + Math.round((rules.hot || 0.25) * 100) + "%+ over 90 days, or its RSI against BTC is 70+. Out of season: it trails by " +
        Math.round(-(rules.cold || -0.25) * 100) + "%+ and the RSI is under 50. In between otherwise. Mechanical, not a forecast." +
        (d.coins_missing && d.coins_missing.length ? " Not in today's figures (loading): " + d.coins_missing.join(", ") + "." : "")));
    const ratio = card("Basket market cap ÷ BTC market cap (log): rising = memes beating BTC",
      ...linesChart([{ name: "Basket ÷ BTC", points: d.ratio }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { log: true }));
    const rsi = card("RSI 14 of basket ÷ BTC", ...linesChart([{ name: "RSI vs BTC", points: d.rsi_vs_btc }], r1, { small: true, hlines: [30, 50, 70] }));
    const ew = card("Equal-weight basket and BTC, rebased to 100 (log)",
      ...linesChart([{ name: "Memecoins, equal weight", points: d.equal_weight }, { name: "BTC", points: d.btc_rebased, dashed: true, color: css("--hold") }], v => v == null ? "–" : num(v, 0), { log: true, small: true }));
    const caps = card("Market caps: basket (left) and BTC (right)",
      ...linesChart([{ name: "Basket", points: d.basket_mcap, axis: "left" }, { name: "BTC", points: d.btc_mcap, color: css("--hold") }], usdBig, { small: true }));
    const log = d.share_log || [];
    const share = card("Memecoins' share of the whole crypto market (CoinGecko 'Meme' category ÷ total market cap)",
      ...(log.length > 1 ? linesChart([{ name: "Meme share", points: log.map(r => [r.t, r.share]) }], v => v == null ? "–" : (v * 100).toFixed(2) + "%", { small: true, sync: false })
        : [el("div", { class: "kpis" }, kpi("Meme share today", log.length ? (log[0].share * 100).toFixed(2) + "%" : "–"), kpi("Meme sector market cap", log.length ? usdBig(log[0].meme_mcap) : "–"))]),
      note("CoinGecko has no free history of either figure, so this is logged once a day from the first deploy and grows from there."));
    return [head, ratio, el("div", { class: "grid2" }, rsi, ew, caps), share, stale(d)];
  },
};
window.TOPIC = { VIEWS };
})();
