// NBA Odds: Ladbrokes Value. Tabs and cards; data from /api/nba-odds/<today|live|moves|results|teams|bets>; helpers from topic.html.
// Everything here reads the server's latest snapshot: the page never calls The Odds API. The bankroll for the quarter-Kelly stakes is kept
// only in this browser (localStorage); placed bets are kept on the server (POST /api/nba-odds/bets).
(() => {
const BOOK = { ladbrokes_uk: ["Ladbrokes", "--s1"], pinnacle: ["Pinnacle", "--s2"], betfair_ex_uk: ["Betfair Exchange", "--s3"], polymarket: ["Polymarket", "--s4"], kalshi: ["Kalshi", "--s5"] };
const CROWD = { polymarket: "Polymarket", kalshi: "Kalshi" };
// the crowd's price on a moneyline row: probability and the EV of Ladbrokes' price against it, with a link to the market
const crowdCell = r => {
  const cs = Object.entries(r.crowd || {});
  if (!cs.length) return el("td", { class: "muted" }, "–");
  return el("td", {}, ...cs.flatMap(([k, c], i) => [i ? el("br") : null, link(CROWD[k] || k, c.url), " " + prob(c.p) + " · ", el("span", { class: c.ev >= 0 ? "up" : "down" }, evp(c.ev))]));
};
const hasCrowd = rows => rows.some(r => r.crowd && Object.keys(r.crowd).length);
const MKT = { h2h: "Moneyline", spreads: "Spread", totals: "Total" };
const odds = v => v == null ? "–" : Number(v).toFixed(2);
const evp = v => v == null ? "–" : pct(v, 1);
const prob = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
const ukTime = t => t ? new Date(t * 1000).toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit" }) : "–";
const ukDay = t => t ? new Date(t * 1000).toLocaleDateString("en-GB", { timeZone: "Europe/London", weekday: "short", day: "numeric", month: "short" }) : "–";
const ago = s => s == null ? "–" : s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1) + " h";
const since = t => t ? ago(Date.now() / 1000 - t) : "–";
const wrap = s => el("td", { class: "wrap" }, s);
const store = { get(k, d) { try { const v = localStorage.getItem("nba-odds:" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("nba-odds:" + k, JSON.stringify(v)); } catch (e) {} } };
const bankroll = () => Number(store.get("bankroll", 0)) || 0;
const stake = k => k == null || !bankroll() ? "–" : "£" + num(bankroll() * k / 4, 2);
const evCell = r => el("td", { class: r.ev == null ? "" : r.ev >= 0 ? "up" : "down", style: r.value ? "font-weight:650" : "" }, evp(r.ev));
const sharpAge = r => Object.entries(r.sharp || {}).map(([b, s]) => (BOOK[b] ? BOOK[b][0].split(" ")[0] : b) + " " + ago(s.age) + (s.fresh ? "" : " (stale)")).join(", ") || "no sharp line";
const moveCell = r => el("td", { class: cls(r.move) }, r.open == null ? "–" : odds(r.open) + " → " + odds(r.lad));
const empty = s => el("div", { class: "muted" }, s);

// the fixed footer, once for the page
if (!document.getElementById("nba-foot")) {
  document.body.style.paddingBottom = "34px";
  document.body.append(el("div", { id: "nba-foot", style: "position:fixed;left:0;right:0;bottom:0;z-index:40;padding:7px 16px;text-align:center;font-size:12px;background:var(--surface);border-top:1px solid var(--line);color:var(--ink2)" },
    "For analysis only. Bookmaker limits apply. 18+. ", el("a", { href: "https://www.begambleaware.org/", target: "_blank", rel: "noopener" }, "BeGambleAware.org"), "."));
}

function creditsCard(c) {
  if (!c) return null;
  const warn = !c.key_set ? "ODDS_API_KEY is not set on the server: no odds are being pulled." : c.error ? "Last pull failed: " + c.error + "." : null;
  const left = c.remaining == null ? null : Math.max(0, Math.min(c.remaining, c.budget - (c.used || 0)));
  return card("Odds API credits",
    el("div", { class: "kpis" }, kpi("Credits left", num(c.remaining)), kpi("Used this month / budget", num(c.used) + " / " + num(c.budget)),
      kpi("Left within budget", num(left)), kpi("Pace", c.pace == null ? (c.stopped ? "stopped: budget spent" : "–") : c.pace <= 1 ? "full cadence" : "× " + c.pace + " slower"),
      kpi("Last pull", c.last_poll ? ukTime(c.last_poll) + " UK (" + since(c.last_poll) + " ago)" : "never")),
    warn ? el("div", { class: "warn", style: "margin-top:6px" }, warn) : null,
    note("One pull at 10:00 UK, every 30 minutes from 3 hours before the first tip-off, every 5 minutes while a game is live; " +
      "each odds pull costs " + (c.per_pull || 6) + " credits. When the month's spend runs ahead of the budget every interval stretches by the pace shown; " +
      "at the budget, pulls stop until the reset (" + c.resets + ")."),
    c.log && c.log.length ? el("details", { style: "margin-top:6px" }, el("summary", { class: "muted" }, "Recent pulls"),
      el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Time (UK)", "Why", "Games", "Value", "Live", "Credits left", "Error"].map(h => el("th", {}, h))),
        ...c.log.slice().reverse().map(x => el("tr", {}, el("td", {}, ukDay(x.t) + " " + ukTime(x.t)), el("td", {}, x.why), el("td", {}, num(x.games)), el("td", {}, num(x.value)),
          el("td", {}, num(x.live)), el("td", {}, num(x.credits)), el("td", { class: x.error ? "err" : "" }, x.error || x.scores_error || "")))))) : null);
}

function bankrollCard(onChange) {
  const inp = el("input", { type: "number", min: "0", step: "10", value: bankroll() || "", placeholder: "e.g. 1000", "aria-label": "Bankroll in pounds",
    style: "font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);width:130px" });
  inp.addEventListener("change", () => { store.set("bankroll", Math.max(0, Number(inp.value) || 0)); onChange && onChange(); });
  return card(null, el("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" }, el("b", {}, "Bankroll £"), inp,
    el("span", { class: "muted" }, "Stakes shown are a quarter of the Kelly fraction of this bankroll. Kept only in this browser.")));
}

function valueTable(rows, live) {
  if (!rows.length) return empty(live ? "Nothing above the threshold right now." : "No value bets in the latest snapshot.");
  return el("div", { class: "scroll" }, el("table", {},
    el("tr", {}, ...["Game", live ? "Score" : "Tip (UK)", "Bet", "Ladbrokes", "Fair", "EV", "¼ Kelly", "Best UK", "Open → now", "Sharp line age"].map(h => el("th", {}, h))),
    ...rows.map(r => el("tr", {}, wrap(r.game), el("td", {}, live ? (r.score || "live") : ukTime(r.commence)), el("td", {}, r.label + " (" + MKT[r.market] + ")"),
      el("td", {}, odds(r.lad)), el("td", {}, odds(r.fair_odds) + " · " + prob(r.fair_p)), evCell(r), el("td", {}, stake(r.kelly)),
      el("td", {}, r.best ? odds(r.best.price) + " " + r.best.book : "–"), moveCell(r), el("td", { class: "muted" }, sharpAge(r))))));
}

function gameCard(g, extra) {
  const rows = ["h2h", "spreads", "totals"].flatMap(m => g.markets[m] || []);
  const margins = ["h2h", "spreads", "totals"].map(m => (g.markets[m] || [])[0]).filter(Boolean).map(r => MKT[r.market] + " " + pct(r.margin, 1).replace("+", ""));
  const crowd = hasCrowd(rows);                            // prediction markets matched to this game: the crowd's moneyline
  const model = !!g.model;                                 // live only: the synthetic-trained model's second opinion on the moneyline
  const mcell = r => r.model_p == null ? el("td", { class: "muted" }, "–") : el("td", { class: r.model_ev >= 0 ? "up" : "down" }, prob(r.model_p) + " · " + evp(r.model_ev));
  return card(g.game + (g.live ? " · LIVE" : " · " + ukDay(g.commence) + " " + ukTime(g.commence) + " UK"), extra || null,
    el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Market", "Bet", "Ladbrokes", "Fair odds", "Fair %", "EV", "¼ Kelly", "Best UK", "Open → now"].concat(crowd ? ["Crowd % · EV"] : [], model ? ["Model % · EV"] : []).map(h => el("th", {}, h))),
      ...rows.map(r => el("tr", { style: r.value ? "background:color-mix(in srgb, var(--up) 10%, transparent)" : "" }, el("td", {}, MKT[r.market]), el("td", {}, r.label),
        el("td", {}, odds(r.lad)), el("td", {}, odds(r.fair_odds)), el("td", {}, prob(r.fair_p)), evCell(r), el("td", {}, r.value ? stake(r.kelly) : "–"),
        el("td", {}, r.best ? odds(r.best.price) + " " + r.best.book : "–"), moveCell(r), crowd ? crowdCell(r) : null, model ? mcell(r) : null)))),
    note("Ladbrokes margin: " + (margins.join(" · ") || "–") + ". Sharp lines: " + (rows[0] ? sharpAge(rows[0]) : "–") + ". Fair needs a sharp book on the same line; a spread or total Ladbrokes prices on a line Pinnacle and the Exchange do not show has no fair."
      + (crowd ? " Crowd: Polymarket's and Kalshi's game markets (no margin, normalised to 100%), " + (FAIR_CROWD ? "in the fair median with the sharps." : "a comparison only (NBA_FAIR_CROWD=1 puts them in the fair).") : "")
      + (model ? " Model: the live win-probability model from the Simulator tab (trained on synthetic games" + (g.model.spread != null ? ", pre-game spread " + (g.model.spread > 0 ? "+" : "") + g.model.spread : "") + "): a second opinion on the moneyline, never a flag." : "")));
}

// Today: every game's moneyline at Ladbrokes (implied, margin in), the sharp fair, and the crowd, side by side with the gap
function crowdCard(games) {
  const rows = games.flatMap(g => (g.markets.h2h || []).filter(r => r.crowd && Object.keys(r.crowd).length).map(r => ({ g, r })));
  if (!rows.length) return null;
  const gap = (a, b) => a == null || b == null ? "–" : pp((a - b) * 100, 1);
  return card("The crowd against the books: moneylines",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Game", "Side", "Ladbrokes implied", "Sharp fair", "Polymarket", "Kalshi", "Crowd − sharp", "Ladbrokes − crowd"].map(h => el("th", {}, h))),
      ...rows.map(({ g, r }) => { const pm = (r.crowd.polymarket || {}).p, ka = (r.crowd.kalshi || {}).p, cr = pm != null && ka != null ? (pm + ka) / 2 : pm != null ? pm : ka;
        return el("tr", {}, wrap(g.game + (g.live ? " · LIVE" : "")), el("td", {}, r.label.replace(" to win", "")), el("td", {}, prob(1 / r.lad)), el("td", {}, prob(r.fair_p)),
          el("td", {}, pm == null ? "–" : [link(prob(pm), r.crowd.polymarket.url)]), el("td", {}, ka == null ? "–" : [link(prob(ka), r.crowd.kalshi.url)]),
          el("td", { class: cls(cr != null && r.fair_p != null ? cr - r.fair_p : null) }, gap(cr, r.fair_p)), el("td", { class: cls(cr != null ? 1 / r.lad - cr : null) }, gap(1 / r.lad, cr))); }))),
    note("Polymarket's NBA game markets and Kalshi's NBA series, matched to each game by team and date; a two-sided market normalised to 100%, so no margin to remove. " +
      "A crowd price well above the sharp fair on one side is where a Ladbrokes price can look like value to the crowd and not to Pinnacle (or the other way round). " +
      (FAIR_CROWD ? "The crowd is in the fair median (NBA_FAIR_CROWD=1)." : "Comparison only: the fair uses the sharps; NBA_FAIR_CROWD=1 adds the crowd to the median.") +
      " Prediction-market prices move with the game, so on the Live tab they refresh every minute without spending a credit."));
}

function flagList(flags) {
  if (!flags.length) return empty("No live bet has crossed the threshold in the last two hours.");
  return el("div", {}, ...flags.map(f => {
    const on = f.status === "active";
    return el("div", { style: "padding:6px 0;border-bottom:1px solid var(--line)" + (on ? "" : ";opacity:.6") },
      el(on ? "b" : "s", {}, f.label + " @ " + odds(f.price)), " · " + f.game,
      el("div", { class: "muted" }, "appeared " + ukTime(f.appeared) + " UK, EV " + evp(f.ev) + " · " + (on ? "on for " + since(f.appeared) + ", now " + odds(f.last_price) + ", EV " + evp(f.last_ev) + " · ¼ Kelly " + stake(f.last_fair ? kellyOf(f.last_price, f.last_fair) : null)
        : "gone " + ukTime(f.gone) + " (" + f.why + "), lasted " + ago(f.gone - f.appeared))));
  }));
}
const kellyOf = (o, p) => { const b = o - 1; return b > 0 ? Math.max(0, (b * p - (1 - p)) / b) : 0; };

let pickGame = null, pickLine = null, FAIR_CROWD = false;

const VIEWS = {
  async today() {
    const d = await api("today"), daily = d.daily || {}, c = d.credits || {};
    FAIR_CROWD = !!d.fair_crowd;
    const has = p => p && p.length >= 2;
    const fig = [kpi("Value bets now", num(d.value.length)), kpi("Best EV now", evp(d.value.length ? d.value[0].ev : null), d.value.length ? "up" : ""),
      kpi("Games on the slate", num(d.games.length)), kpi("Credits left", num(c.remaining))];
    const head = has(daily.count) ? card(null, followHead([{ label: "Bets flagged that day", points: daily.count, fmt: v => num(v) },
      { label: "Best EV flagged that day", points: daily.best_ev, fmt: evp }], { latest: "Latest day" }), el("div", { class: "kpis", style: "margin-top:10px" }, ...fig))
      : card(null, el("div", { class: "kpis" }, ...fig));
    const chart = has(daily.count) ? card("Bets flagged per day and the best EV among them",
      ...linesChart([{ name: "Flags", points: daily.count, axis: "left", fmt: v => v % 1 ? "" : num(v), bar: true, color: css("--s1") }, { name: "Best EV", points: daily.best_ev, fmt: evp }], evp),
      note("Every bet that crossed the threshold, pre-game and live, by UK day.")) : null;
    const asOf = d.as_of ? note("Latest snapshot " + ukDay(d.as_of) + " " + ukTime(d.as_of) + " UK (" + since(d.as_of) + " ago). Slate " + d.slate + " (US Eastern day).") : empty("No odds pulled yet.");
    const box = el("div", { style: "display:grid;gap:12px" });
    const draw = () => box.replaceChildren(...[
      card("Value bets, sorted by EV", valueTable(d.value, false),
        note("A value bet: EV = Ladbrokes price × fair probability − 1 of at least " + pct(d.min_ev, 1).replace("+", "") + ", with a sharp line under " + d.fresh_pre / 60 +
          " minutes old. Fair = the margin removed from Pinnacle and the Betfair Exchange (after " + pct(d.commission, 0).replace("+", "") + " commission), " +
          (d.devig === "power" ? "power" : "multiplicative") + " method, median of the two. Maths on prices, not tips.")),
      crowdCard(d.games),
      ...d.games.map(g => gameCard(g)),
      d.props && d.props.length ? card("Player props at Ladbrokes (on demand)", el("div", { class: "scroll" }, el("table", {},
        el("tr", {}, ...["Game", "Market", "Selection", "Line", "Ladbrokes"].map(h => el("th", {}, h))),
        ...d.props.map(p => el("tr", {}, wrap(p.game), el("td", {}, p.market), el("td", {}, p.name), el("td", {}, p.point == null ? "–" : p.point), el("td", {}, odds(p.lad))))))) : null].filter(Boolean));
    draw();
    const books = Object.entries(d.books_seen || {});
    return [head, asOf, bankrollCard(draw), box, chart, creditsCard(c),
      books.length ? card("Bookmakers in the latest pull", el("div", { class: "src" }, books.map(([k, t]) => t + " (" + k + ")").join(" · ")),
        note("Best UK price compares Ladbrokes with the UK books among these. Pinnacle is a sharp input only; it does not take UK customers.")) : null];
  },

  async live() {
    const d = await api("live");
    FAIR_CROWD = !!d.fair_crowd;
    const games = d.games || [];
    const flagsBox = el("div", {}, flagList(d.flags || []));
    const stamp = el("div", { class: "muted", style: "margin-top:6px" });
    const setStamp = t => { stamp.textContent = "Snapshot " + (t ? ukTime(t) + " UK (" + since(t) + " old)" : "none") + "; this list refreshes every minute."; };
    setStamp(d.as_of);
    const fav = card("Favourable now", flagsBox, stamp,
      note("A live bet is flagged when its EV newly reaches " + pct(d.min_ev, 1).replace("+", "") + " with a sharp line under " + d.fresh_live / 60 + " minutes old, and struck out when Ladbrokes moves the price or the sharp line catches up."));
    const tick = setInterval(async () => {
      if (!fav.isConnected) { if (tick.seen) clearInterval(tick); return; }
      tick.seen = true;
      try { const n = await api("live"); flagsBox.replaceChildren(flagList(n.flags || [])); setStamp(n.as_of); } catch (e) {}
    }, 60000);
    const score = g => (g.away_score == null ? "–" : num(g.away_score)) + " – " + (g.home_score == null ? "–" : num(g.home_score));
    const clock = g => g.period ? "Q" + g.period + (g.clock ? " " + g.clock : "") : g.status || "in play";
    const valueRows = games.flatMap(g => Object.values(g.markets).flat().filter(r => r.value).map(r => ({ ...r, score: score(g) + " · " + clock(g) })));
    return [card(null, el("div", { class: "kpis" }, kpi("Games live", num(games.length)), kpi("Live flags on", num((d.flags || []).filter(f => f.status === "active").length), "up"),
        kpi("Credits left", num((d.credits || {}).remaining)), kpi("Snapshot", d.as_of ? ukTime(d.as_of) + " UK" : "–"))),
      fav,
      games.length ? card("Above the threshold in the latest live snapshot", valueTable(valueRows, true)) : null,
      ...(games.length ? games.map(g => gameCard(g, el("div", { style: "font-size:18px;font-weight:650;margin-bottom:6px" }, nicknameOf(g.away) + " " + score(g) + " " + nicknameOf(g.home),
        el("span", { class: "muted", style: "font-size:13px;font-weight:400" }, " · " + clock(g) + (g.clock_source ? " (" + g.clock_source + ")" : ""))))) :
        [card(null, empty("No game in progress in the latest snapshot. Live pulls run every 5 minutes while a game is on."))]),
      d.board_error ? note("Live clock not available right now (" + d.board_error + ").") : null];
  },

  async moves() {
    const d = await api("moves");
    if (!d.games.length) return [card(null, empty("No price history yet: it builds from the first pull of each game."))];
    if (!pickGame || !d.games.some(g => g.id === pickGame)) pickGame = d.games[0].id;
    const g = d.games.find(x => x.id === pickGame);
    const lines = g.series.slice().sort((a, b) => ["h2h", "spreads", "totals"].indexOf(a.market) - ["h2h", "spreads", "totals"].indexOf(b.market));
    if (!pickLine || !lines.some(s => s.key === pickLine)) pickLine = (lines.find(s => s.books.ladbrokes_uk) || lines[0]).key;
    const s = lines.find(x => x.key === pickLine);
    const gamePick = el("div", { class: "chips" }, ...d.games.map(x => el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit" + (x.id === pickGame ? ";background:var(--accent);color:#fff" : ""),
      onclick: () => { pickGame = x.id; pickLine = null; render(); } }, x.game + (x.commence ? " · " + ukDay(x.commence) : ""))));
    const linePick = el("div", { class: "seg", style: "flex-wrap:wrap" }, ...lines.map(x => el("button", { class: x.key === pickLine ? "on" : "", onclick: () => { pickLine = x.key; render(); } }, MKT[x.market] + ": " + x.label)));
    const series = Object.entries(s.books).filter(([, p]) => p.length).map(([b, p]) => ({ name: (BOOK[b] || [b])[0], color: css((BOOK[b] || [0, "--s4"])[1]), points: p }));
    const chart = series.some(x => x.points.length >= 2) ? linesChart(series, odds, { time: true, sync: false }) : [empty("One price so far for this line: the chart starts with the second.")];
    return [card("Line moves: " + g.game, gamePick, el("div", { style: "margin-top:8px" }, linePick), ...chart,
      note("Decimal odds at each pull where the price changed, from the first pull through tip-off" + (g.commence ? " (" + ukTime(g.commence) + " UK)" : "") +
        " and in play. The Exchange line is the raw back price, before commission. A Ladbrokes line above Pinnacle's is where value shows up."))];
  },

  async results() {
    const d = await api("results"), t = d.track, has = p => p && p.length >= 2;
    const head = has(t.roi) || has(t.clv30) ? card(null, followHead([{ label: "Running ROI, 1 unit a flag", points: t.roi, fmt: evp, cls },
      { label: "Average CLV, last 30 days", points: t.clv30, fmt: evp, cls }], { latest: "Latest" }),
      el("div", { class: "kpis", style: "margin-top:10px" }, kpi("Flags logged", num(t.n)), kpi("Settled", num(t.settled) + " (" + num(t.wins) + " won)"),
        kpi("Profit, units", num(t.profit, 2), cls(t.profit)), kpi("Beat the close", t.beat_close == null ? "–" : (t.beat_close * 100).toFixed(0) + "%")))
      : card(null, el("div", { class: "kpis" }, kpi("Flags logged", num(t.n)), kpi("Settled", num(t.settled)), kpi("ROI", evp(t.roi_all), cls(t.roi_all)), kpi("Average CLV", evp(t.clv_all), cls(t.clv_all))),
        note("ROI and CLV charts appear from the second day with settled flags."));
    const charts = [has(t.roi) ? card("Running ROI of every flagged bet (1 unit each)", ...linesChart([{ name: "All", points: t.roi }, { name: "Pre-game", points: d.pre.roi }, { name: "Live", points: d.live.roi }], evp, { hlines: [0] })) : null,
      has(t.clv) ? card("Closing line value", ...linesChart([{ name: "Daily average", points: t.clv, dashed: true }, { name: "30-day average", points: t.clv30 }], evp, { hlines: [0] }),
        note("CLV = flagged Ladbrokes price × the sharp fair probability at the close − 1 (the close is the last pre-game fair line; for a live flag, the last fair line before the final whistle). " +
          "Positive CLV over hundreds of bets is the honest test that the value is real; ROI over a few weeks is mostly noise.")) : null];
    const flagRow = f => el("tr", {}, el("td", {}, ukDay(f.appeared) + " " + ukTime(f.appeared)), wrap(f.game), el("td", {}, f.label + " (" + MKT[f.market] + ")"), el("td", {}, f.live ? "live" : "pre"),
      el("td", {}, odds(f.price)), el("td", { class: cls(f.ev) }, evp(f.ev)), el("td", {}, odds(f.close_odds)), el("td", { class: cls(f.clv) }, evp(f.clv)),
      el("td", { class: f.result === "win" ? "up" : f.result === "loss" ? "down" : "" }, f.result || (f.status === "active" ? "open" : "pending")), el("td", { class: cls(f.profit) }, f.profit == null ? "–" : num(f.profit, 2)));
    const table = card("Every flagged bet", d.flags.length ? el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Flagged (UK)", "Game", "Bet", "When", "Price", "EV", "Sharp close", "CLV", "Result", "Units"].map(h => el("th", {}, h))), ...d.flags.map(flagRow))) : empty("No bet flagged yet."),
      note("Logged automatically, at the price when the flag appeared. Nothing is placed anywhere."));
    return [head, ...charts, table, placedCard(d)];
  },

  async teams() {
    const d = await api("teams");
    const ts = d.teams || [];
    const restTxt = x => x.rest == null ? "–" : x.b2b ? "back-to-back" : x.rest + (x.rest === 1 ? " day" : " days");
    const form = x => el("span", {}, ...x.last10.map(g => el("span", { title: (g.home ? "v " : "@ ") + g.opp + " " + (g.margin > 0 ? "+" : "") + g.margin, style: "display:inline-block;width:9px;height:9px;margin-right:2px;border-radius:2px;background:" + (g.won ? "var(--up)" : "var(--down)") })));
    return [card(d.tonight ? "Tonight's teams" : "Teams (no games on the slate)", ts.length ? el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Team", "Tonight", "Last 10", "Form", "Streak", "Avg margin", "Rest", "3 in 4", "Injuries"].map(h => el("th", {}, h))),
      ...ts.map(x => el("tr", {}, el("td", {}, x.team), el("td", {}, x.tip ? (x.home ? "v " : "@ ") + x.opp + " " + ukTime(x.tip) : "–"), el("td", {}, x.w + "–" + x.l), el("td", {}, form(x)),
        el("td", { class: cls(x.streak) }, x.streak ? (x.streak > 0 ? "W" : "L") + Math.abs(x.streak) : "–"), el("td", { class: cls(x.avg_margin) }, x.avg_margin == null ? "–" : (x.avg_margin > 0 ? "+" : "") + x.avg_margin),
        el("td", { class: x.b2b ? "down" : "" }, restTxt(x)), el("td", {}, x.three_in_four ? "yes" : "–"),
        wrap(x.injuries.length ? x.injuries.map(i => i.player + " (" + i.status + (i.note ? ": " + i.note : "") + ")").join("; ") : "none listed"))))) : empty("No schedule available right now."),
      d.schedule_error ? note("Schedule not available right now (" + d.schedule_error + ").") : null,
      note("Context only: none of this goes into the fair line or the EV, which come from prices alone. Rest counts days off before tonight (US Eastern days). " +
        "Injuries: " + (d.injury_sources.length ? d.injury_sources.join(", ") : "no source answered") + "; hand-entered ones are in data/nba-odds/injuries.csv with their source."))];
  },

  async sim() {
  const d = await api("sim"), m = d.model || {}, cfg = d.cfg || {}, lad = cfg.lad || {}, sh = cfg.sharp || {};
  const pc = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
  const se = r => r.se == null ? "" : " ± " + (r.se * 100).toFixed(1);
  const head = card(null, el("div", { class: "kpis" }, kpi("Synthetic games", num(d.n_games)), kpi("Model σ (margin spread, pts)", m.sigma), kpi("Hold-out log loss", m.logloss + " (base " + m.logloss_base + ")"),
    kpi("Home win rate", pc(d.home_win_rate)), kpi("Overtime", pc(d.ot_share)), kpi("Ran", d.took + " s")),
    note("Everything on this tab is synthetic: games played possession by possession from a made-up spread and total, a sharp book and a slow book run over them with the rules below. " +
      "It shows what kind of edge the pipeline can catch and at what polling cadence; it says nothing about whether such edges exist at Ladbrokes."));
  const rules = card("The two books in the lab",
    el("div", { class: "grid2" },
      el("div", {}, el("b", {}, "Sharp (Pinnacle-like)"), el("div", { class: "muted" }, "Margin " + pc(sh.margin) + " · reprices " + sh.lag + " s after every score and every " + sh.timer + " s · noise ±" + pc(sh.noise) + " on the probability")),
      el("div", {}, el("b", {}, "Slow (Ladbrokes-like)"), el("div", { class: "muted" }, "Margin " + pc(lad.margin) + " · reprices " + lad.lag + " s after a score and every " + lad.timer + " s, and only when the fair line has moved " + pc(lad.sticky) +
        " · suspended " + lad.suspend + " s after each score · a stuck feed for " + Math.round(lad.hiccup_len / 60) + " min in " + pc(lad.hiccup_p) + " of games"))),
    note("Stylised guesses, not Ladbrokes' trading rules; change them in app/topics/nba_sim.py (DEFAULTS) or on the command line: python -m app.topics.nba_sim --lag 40 --sticky 0.03."));
  // the example game
  const ex = d.example, exCard = ex ? card("One game: true probability against both books (home win %)",
    ...svgLines([{ name: "Truth", points: ex.truth, color: css("--ink2"), width: 1.5 }, { name: "Sharp", points: ex.sharp, color: css("--s2") }, { name: "Ladbrokes-like", points: ex.lad, color: css("--s1") },
      { name: "Home lead (right axis, scaled)", points: ex.lead.map(([t, v]) => [t, 0.5 + v / 60]), color: css("--s4"), dashed: true }],
      { xFmt: v => Math.round(v) + "'", yFmt: v => (v * 100).toFixed(0) + "%", h: 300, hline: 0.5, note: "Hover: minute, truth, sharp, Ladbrokes-like (blank while suspended)",
        vlines: [{ x: 12, label: "Q2" }, { x: 24, label: "Q3" }, { x: 36, label: "Q4" }].concat(ex.hiccup ? [{ x: ex.hiccup[0], label: "feed stuck" }, { x: ex.hiccup[1] }] : []) }),
    note("Pre-game home spread " + (ex.spread > 0 ? "+" : "") + ex.spread + ", total " + ex.total + ", final " + ex.final[0] + "–" + ex.final[1] + ". The lead line is the margin on a ±30 scale around 50%. " +
      "The slow book trails the truth after every score and stays flat through small moves; each gap above the sharp line is a flag (" + ex.flags + " in this game at 15-second polling).")) : null;
  // cadence × threshold
  const cad = card("What the pipeline catches, by polling cadence and threshold",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Poll every", "EV ≥", "Flags", "Per game", "Mean EV vs sharp", "True edge", "Realised ROI", "Hit rate", "Avg odds"].map(h => el("th", {}, h))),
      ...(d.cadence || []).map(r => el("tr", { style: r.cadence === 300 && r.min_ev === d.min_ev ? "background:color-mix(in srgb, var(--s1) 10%, transparent)" : "" },
        el("td", {}, r.cadence + " s" + (r.cadence === 300 ? " (the poller)" : "")), el("td", {}, pc(r.min_ev)), el("td", {}, num(r.n)), el("td", {}, r.per_game), el("td", { class: cls(r.ev) }, pc(r.ev)),
        el("td", { class: cls(r.true_edge) }, pc(r.true_edge)), el("td", { class: cls(r.roi) }, pc(r.roi) + se(r)), el("td", {}, pc(r.hit)), el("td", {}, odds(r.odds)))))),
    note("One bet per price run (the same stale price seen on consecutive polls counts once), 1 unit each, settled at the game's outcome. Mean EV is what the page would show (against the sharp fair); " +
      "true edge is Ladbrokes price × the simulator's real probability − 1, the edge that was actually there; realised ROI is the noisy version of it (± one standard error). " +
      "Credits: the real poller's 5-minute cadence costs 6 credits a pull; 60 s would be five times that."));
  const reg = d.regimes || {}, pick = reg["60"] ? "60" : Object.keys(reg)[0];
  const regTable = (title, rows, what) => card(title, el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...[what, "Flags", "Mean EV vs sharp", "True edge", "Realised ROI"].map(h => el("th", {}, h))),
    ...rows.map(r => el("tr", {}, el("td", {}, r.label), el("td", {}, num(r.n)), el("td", { class: cls(r.ev) }, pc(r.ev)), el("td", { class: cls(r.true_edge) }, pc(r.true_edge)), el("td", { class: cls(r.roi) }, pc(r.roi) + se(r)))))));
  const R = reg[pick] || {};
  const regimes = R.quarter ? [el("div", { class: "grid2" },
      regTable("By quarter (polling every " + pick + " s, EV ≥ " + pc(d.min_ev) + ")", R.quarter, "Quarter"),
      regTable("By seconds since the last score", R.since_score, "Since a score"),
      regTable("By size of the lead", R.lead, "Lead"),
      regTable("By the slow book's feed", R.hiccup, "Feed"),
      regTable("By side", R.side, "Side"),
      regTable("By Ladbrokes odds", R.odds, "Odds")),
    note("Read the true-edge column, not the ROI: with a few hundred bets the ROI is mostly noise. Where the true edge is negative the flag is an artefact (the sharp book's own noise at short prices, " +
      "a big lead where a few points of probability are worth little), and the threshold or the freshness rule should be tighter there.")] : [];
  const mv = d.moves || {};
  const moves = mv.since_score ? card("How far each book sits from the truth (mean |probability − truth|, 15-second grid)",
    el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Since the last score", "Samples", "Sharp", "Ladbrokes-like", "Suspended"].map(h => el("th", {}, h))),
      ...mv.since_score.map(r => el("tr", {}, el("td", {}, r.label), el("td", {}, num(r.n)), el("td", {}, pc(r.sharp_gap)), el("td", {}, pc(r.lad_gap)), el("td", {}, pc(r.lad_off)))))),
    el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Quarter", "Samples", "Sharp", "Ladbrokes-like"].map(h => el("th", {}, h))),
      ...mv.quarter.map(r => el("tr", {}, el("td", {}, r.label), el("td", {}, num(r.n)), el("td", {}, pc(r.sharp_gap)), el("td", {}, pc(r.lad_gap)))))),
    note("The slow book is 3 points or more off the truth " + pc(mv.lad_off_3pts) + " of the time and 5 points or more " + pc(mv.lad_off_5pts) + ". The 10-30 s window after a score is the lag: the sharp book has moved, the slow one has not yet.")) : null;
  const calib = m.calibration ? card("The live win-probability model, trained on the synthetic outcomes",
    el("div", { class: "muted" }, m.form + ". Fitted by maximum likelihood on " + num(m.rows_train) + " game-minutes from 70% of the games: σ = " + m.sigma + ", a = " + m.a + ", c = " + m.c +
      ". On the other 30% (" + num(m.rows_test) + " game-minutes): log loss " + m.logloss + " against " + m.logloss_base + " for always guessing the base rate, Brier " + m.brier + "."),
    ...svgBars(m.calibration.map(c => c.bin), [{ name: "Predicted", values: m.calibration.map(c => c.pred), color: css("--s1") }, { name: "Actual", values: m.calibration.map(c => c.actual), color: css("--s3") }],
      { yFmt: v => (v * 100).toFixed(0) + "%", h: 200, extra: i => " · n=" + m.calibration[i].n }),
    note("Each bin: the model's average prediction against how often the home side actually won. The same fit runs unchanged on real games once the poller has logged enough of them (data/nba-odds/README.md); " +
      "until then the Live tab's model column is this synthetic fit, a second opinion only.")) : null;
  return [head, cad, ...regimes, moves, exCard, calib, rules];
  },
};

const nicknameOf = n => { const parts = String(n || "").split(" "); return parts[parts.length - 1] === "Blazers" ? "Trail Blazers" : parts[parts.length - 1]; };

// ---- bets the user placed: POSTed to the server (POST /api/nba-odds/bets, stored on the volume). Bets an earlier version of this page kept
// only in this browser are listed until "Move to the server" sends them there.
const postBet = body => fetch("/api/" + SLUG + "/bets", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
  .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || r.statusText); return j; });
function placedCard(d) {
  const local = store.get("placed", []);
  const all = (d.placed || []).map(b => ({ ...b, where: "server" })).concat(local.map(b => ({ ...b, where: "this browser" })));
  const s = d.placed_summary || {};
  const msg = el("div", { class: "muted", style: "min-height:18px" });
  const f = {};
  const inp = (k, ph, type = "text", w = 110) => (f[k] = el("input", { type, placeholder: ph, step: type === "number" ? "0.01" : null, "aria-label": ph,
    style: "font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);width:" + w + "px" }));
  const mk = el("select", { "aria-label": "Market", style: "font:inherit;padding:5px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)" },
    ...[["h2h", "Moneyline"], ["spreads", "Spread"], ["totals", "Total"], ["other", "Other"]].map(([v, l]) => el("option", { value: v }, l)));
  const res = el("select", { "aria-label": "Result", style: "font:inherit;padding:5px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)" },
    ...[["", "Result: pending"], ["win", "Won"], ["loss", "Lost"], ["push", "Push"]].map(([v, l]) => el("option", { value: v }, l)));
  const save = async () => {
    const bet = { game: f.game.value, market: mk.value, name: f.name.value, point: f.point.value, price: f.price.value, stake: f.stake.value, note: f.note.value, result: res.value };
    if (!bet.name || !(Number(bet.price) > 1) || !(Number(bet.stake) >= 0)) { msg.textContent = "A bet needs a selection, odds above 1 and a stake."; return; }
    try { await postBet(bet); } catch (e) { msg.textContent = "Could not save: " + e.message; return; }
    render();
  };
  const remove = async b => {
    if (b.where === "this browser") store.set("placed", local.filter(x => x.id !== b.id));
    else try { await postBet({ delete: b.id }); } catch (e) { msg.textContent = "Could not remove: " + e.message; return; }
    render();
  };
  const move = async () => {                             // one at a time: each moved bet leaves the browser list only once the server has it
    let left = local.slice(), failed = null;
    for (const b of local) {
      const { id, t, profit, ...bet } = b;
      try { await postBet(bet); left = left.filter(x => x !== b); store.set("placed", left); } catch (e) { failed = e.message; break; }
    }
    if (failed) { msg.textContent = "Moved " + (local.length - left.length) + " of " + local.length + "; stopped: " + failed; return; }
    render();
  };
  const lp = local.filter(b => b.profit != null), lst = lp.reduce((a, b) => a + b.stake, 0), lpr = lp.reduce((a, b) => a + b.profit, 0);
  const staked = (s.staked || 0) + lst, prof = (s.profit || 0) + lpr;
  return card("Bets I placed",
    el("div", { class: "kpis" }, kpi("Bets", num(all.length)), kpi("Staked (settled)", "£" + num(staked, 2)), kpi("Profit", "£" + num(prof, 2), cls(prof)), kpi("ROI", staked ? evp(prof / staked) : "–", cls(prof))),
    local.length ? el("div", { class: "warn", style: "margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap" },
      local.length + (local.length === 1 ? " bet is" : " bets are") + " kept only in this browser, from before the server took bets.",
      el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: move }, "Move to the server")) : null,
    el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin-top:10px" }, inp("game", "Game", "text", 180), mk, inp("name", "Selection (e.g. Boston Celtics)", "text", 200), inp("point", "Line", "number", 80),
      inp("price", "Odds", "number", 80), inp("stake", "Stake £", "number", 90), res, inp("note", "Note", "text", 160), el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: save }, "Add")),
    msg,
    all.length ? el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Added", "Game", "Bet", "Odds", "Stake", "Result", "Profit", "Kept", ""].map(h => el("th", {}, h))),
      ...all.sort((a, b) => (b.t || 0) - (a.t || 0)).map(b => el("tr", {}, el("td", {}, ukDay(b.t)), wrap(b.game || ""), el("td", {}, (b.name || "") + (b.point != null ? " " + b.point : "") + " (" + (MKT[b.market] || "other") + ")"),
        el("td", {}, odds(b.price)), el("td", {}, "£" + num(b.stake, 2)), el("td", {}, b.result || "pending"), el("td", { class: cls(b.profit) }, b.profit == null ? "–" : "£" + num(b.profit, 2)),
        el("td", { class: "muted" }, b.where), el("td", {}, el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: () => remove(b) }, "×")))))) : null,
    note("A log for your own record, kept on this server: nothing is placed anywhere. Bets settle themselves when their game is matched; set the result by hand otherwise."));
}

window.TOPIC = { VIEWS };
})();
