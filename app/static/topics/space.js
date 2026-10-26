// Space Economy: tabs and cards. Data from /api/space/<launches|cost|satellites|industry|ukhk|answer>; helpers from topic.html.
(() => {
const GROUPS = ["US", "China", "Russia", "Europe", "Japan", "India", "UK", "Other"];
const C = k => css(SERIES[Math.max(0, GROUPS.indexOf(k)) % SERIES.length]);
const f0 = v => v == null ? "–" : num(v, 0), f1 = v => v == null ? "–" : num(v, 1);
const kg = v => v == null ? "–" : "$" + num(v, 0) + "/kg";
const has = o => o && Object.values(o).some(p => p && p.length);
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
const srcCell = r => el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "");
const bySeries = (obj, fmt, opts = {}) => linesChart(Object.entries(obj || {}).filter(([, p]) => p && p.length).map(([k, p], i) => ({ name: k, points: p, color: css(SERIES[i % SERIES.length]) })), fmt, opts);
const yr = ts => new Date(ts * 1000).getUTCFullYear();
// top cards follow the date hovered or clicked on any chart (followHead from topic.html): each figure reads the series its chart draws
const SHARE = v => pct(v, 0).replace("+", ""), SIGN0 = v => (v > 0 ? "+" : "") + v.toFixed(0) + "%";
const DECADE = 10 * 365.25 * 86400;

function checklistCard(items) {
  const mark = m => m == null ? el("span", { class: "pill" }, "unknown") : m ? el("span", { class: "pill ok" }, "met") : el("span", { class: "pill bad" }, "not yet");
  const fmt = (k, v) => v == null ? "–" : k === "cheap" ? kg(v) : k === "subs" ? f1(v) + "m" : f0(v);
  const n = items.filter(c => c.met).length, known = items.filter(c => c.met != null).length;
  return card("When does orbit become routine infrastructure? " + n + " of " + known + " signs met",
    table(["Sign", "Now", "Threshold", ""], items.map(c => el("tr", {}, el("td", {}, c.label), el("td", {}, fmt(c.key, c.value)), el("td", {}, c.target), el("td", {}, mark(c.met))))),
    note("Routine means a utility: launches as regular as freight, a price per kg that ordinary firms can budget for, more than one supplier, a fleet big enough that people rely on it daily, " +
      "and the UK able to launch from home. Each row is computed from the tabs; when all six are met, orbit is infrastructure rather than an industry."));
}

const VIEWS = {
  async launches() {
    const [d, a] = await Promise.all([api("launches"), api("answer").catch(() => ({ checklist: [] }))]);
    const L = d.launches || {}, K = L.kpi || {}, MK = (d.mass || {}).kpi || {};
    const RB = L.rolling_by || {}, MT = (d.mass || {}).total || [];
    const head = card(null, followHead([
      { label: "Orbital launches in the 12 months to that month", points: L.rolling || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      { label: "US, 12 months", points: RB.US || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      { label: "China, 12 months", points: RB.China || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      { label: "World launches that year", points: L.total || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      { label: "SpaceX share that year", points: L.spacex_share || [], fmt: SHARE },
      { label: "Reached orbit that year", points: L.success_rate || [], fmt: SHARE },
      { label: "Payload mass to orbit that year (tonnes)", points: MT, fmt: f0, delta: { lag: "1y", fmt: SIGN0 } }],
      { latest: "Latest figures (launch list to " + (K.latest || "–") + ")" }),
      el("div", { class: "kpis", style: "margin-top:10px" }, kpi("Orbital launches " + (K.year || "") + " so far (same day last year)", f0(K.ytd) + " (" + f0(K.ytd_prev) + ")", cls((K.ytd || 0) - (K.ytd_prev || 0)))),
      asOf(d), stale(d), note("A launch counts when it tries for orbit, success or not. Country is the launch provider's (Rocket Lab's New Zealand pads count for the US)."));
    const ans = (a.checklist || []).length ? checklistCard(a.checklist) : null;
    const ctry = has(L.countries) ? card("Orbital launch attempts per year by country, 1957 on",
      ...linesChart(GROUPS.filter(g => (L.countries[g] || []).length).map(g => ({ name: g, points: L.countries[g], color: C(g) })).concat([{ name: "World", points: L.total, color: css("--hold"), dashed: true }]), f0),
      note("McDowell's GCAT launch list (orbital and deep-space attempts, by the provider's country). 5 years: can China's commercial firms keep it within reach of the US? 10 years: does the world pass 365 a year, a launch a day, " +
        "and stay there? 20 years: the Cold War peak was about 140 a year, set by two governments; a curve that keeps rising without them is what infrastructure looks like."))
      : card("Launches by country", missing(d, "launches", "The GCAT launch list"), stale(d));
    const roll = (L.rolling || []).length ? card("Orbital launches in the trailing 12 months", ...linesChart([{ name: "World", points: L.rolling, color: css("--hold") },
      ...Object.entries(L.rolling_by || {}).map(([k, p]) => ({ name: k, points: p, color: C(k) }))], f0, { small: true }),
      note("Monthly, each point the 12 months to that month. 5 years: is the rise still accelerating or flattening? 10 years: Starship and reusable Chinese rockets should lift the slope; 20 years: a launch a day is the line between an event and a schedule.")) : null;
    const share = (L.spacex_share || []).length ? card("SpaceX share of the world's orbital launches", ...linesChart([{ name: "SpaceX", points: L.spacex_share, color: css("--s1") }], v => pct(v, 0).replace("+", ""), { small: true }),
      note("GCAT, by year. 5 years: does anyone (China, Rocket Lab, Blue Origin, Europe) pull the share below half? 10 years: infrastructure with one supplier is fragile; 20 years: whether launch ends up like airlines (many) or like chips (one or two).")) : null;
    const prov = (L.providers || []).length ? card("Top launch providers, " + (K.last_year || "") + " (and " + (K.year || "") + " so far)",
      table(["Provider", "Country", String(K.last_year || ""), "Share", (K.year || "") + " so far"], L.providers.map(p => el("tr", {}, el("td", {}, p.provider), el("td", {}, p.country), el("td", {}, f0(p.last)), el("td", {}, pct(p.share, 0).replace("+", "")), el("td", {}, f0(p.ytd))))),
      note("GCAT's agency codes, named from its organisations table. The second-biggest provider flying weekly (52 a year) is one of the routine-infrastructure signs.")) : null;
    const M = d.mass;
    const mass = M ? card("Payload mass launched to orbit per year (tonnes)", ...linesChart([{ name: "All payloads", points: M.total, color: css("--hold") }, { name: "Starlink", points: M.starlink, color: css("--s1") }, { name: "Everything else", points: M.other, color: css("--s2") }], v => big(v)),
      note("Sum of payload launch masses in GCAT's satellite catalog, by launch year (rocket stages excluded). " +
        "5 years: Starlink is most of the tonnage; does the rest grow too? 10 years: Starship-scale rockets would multiply it, which is the real test of cheaper access. 20 years: tonnes to orbit is the freight measure of a space economy, as tonne-km is for rail."))
      : card("Payload mass", missing(d, "mass", "GCAT's satellite catalog"));
    const sr = (L.success_rate || []).length ? card("Share of orbital attempts that reached orbit", ...linesChart([{ name: "Success rate", points: L.success_rate, color: css("--s3") }], v => pct(v, 0).replace("+", ""), { small: true }),
      note("GCAT launch code (success means the rocket worked). 5 years: new rockets fail often; does the rate hold above 95% as new entrants fly? 10 and 20 years: routine freight needs airline-like reliability.")) : null;
    return [ans, head, ctry, el("div", { class: "grid2" }, roll, share), mass, el("div", { class: "grid2" }, prov, sr)];
  },
  async cost() {
    const d = await api("cost"), K = d.kpi || {}, V = d.vehicles || [];
    const head = card(null, followHead([
      { label: "Cheapest flown cost to LEO that year", points: d.frontier || [], fmt: kg, delta: { lag: DECADE, fmt: SIGN0, text: "in 10 years" } }],
      { latest: "Latest year" }),
      el("div", { class: "kpis", style: "margin-top:10px" }, kpi("Cheapest rocket (" + (K.best_vehicle || "–") + ", first flown " + (K.best_year || "–") + ")", kg(K.best)),
        kpi("20 years earlier", kg(K.twenty_y))),
      note("Published estimates for a full rocket at list price divided by its capacity to low Earth orbit; not what any one customer pays. Every row marked 'verify' was entered from memory."));
    const fr = (d.frontier || []).length ? card("Cheapest flown cost to low Earth orbit, by year (USD per kg, log scale)", ...linesChart([{ name: "Cheapest available", points: d.frontier, color: css("--s1") }], kg, { log: true }),
      note("The lowest cost per kg of any rocket that had flown by that year (CSIS estimates in 2021 dollars, plus list prices). 5 years: Starship's first commercial price is the next step down, if it comes. " +
        "10 years: under $1,000/kg is the routine-infrastructure line. 20 years: from $54,500 (Shuttle) to $1,500 (Falcon Heavy) took 37 years; the question is whether the next 30x takes 10."), cite(d.cited))
      : card("Cost frontier", el("div", { class: "muted" }, "Add rows to data/space/cost.csv."));
    const flown = V.filter(v => v.kind === "flown").sort((a, b) => a.date < b.date ? -1 : 1);
    const bars = flown.length ? card("Cost per kg to LEO by rocket, in order of first flight (USD per kg)",
      ...svgBars(flown.map(v => v.vehicle), [{ name: "USD per kg", values: flown.map(v => v.usd_kg), colorFn: v => v <= (K.best || 0) * 1.01 ? css("--up") : css("--s1") }],
        { yFmt: v => "$" + big(v), catName: i => flown[i].vehicle + " (" + flown[i].date.slice(0, 4) + ", " + flown[i].country + ")", labelW: 70, h: 240 }),
      note("Green: the cheapest. Small rockets (Electron) cost far more per kg because they sell a dedicated ride. 5 years: Ariane 6 and other non-US rockets against Falcon 9. 10 years: do Chinese reusable rockets publish prices? 20 years: whether only reusable rockets survive.")) : null;
    const list = card("Every row", table(["First flight", "Rocket", "Country", "USD/kg", "Kind", "Source"], V.map(v => el("tr", {}, el("td", {}, v.date.slice(0, 4)), el("td", {}, v.vehicle), el("td", {}, v.country), el("td", {}, f0(v.usd_kg)), el("td", {}, v.kind), srcCell(v)))),
      note("Kept in data/space/cost.csv. 'target' rows are stated goals, drawn nowhere and never counted as flown. No published per-kg prices for Chinese rockets are entered yet."));
    return [head, fr, bars, list];
  },
  async satellites() {
    const d = await api("satellites"), A = d.active || {}, K = A.kpi || {}, SK = d.subs_kpi || {};
    const head = card(null, followHead([
      { label: "Starlink subscribers (last announced)", points: d.subs || [], fmt: v => f1(v) + "m", delta: { lag: "1y", fmt: SIGN0 } },
      { label: "Today's active satellites launched by then", points: A.cumulative || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      { label: "…of which Starlink", points: A.cumulative_starlink || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } }],
      { latest: "Latest figures" }),
      el("div", { class: "kpis", style: "margin-top:10px" },
        kpi("Active satellites now (CelesTrak)", f0(K.active)), kpi("Starlink now", f0(K.starlink) + " (" + SHARE(K.starlink_share) + ")"),
        kpi("China's (constellations and others)", f0(K.china)), kpi("Launched in the last 12 months, still active (vs 12 before)", f0(K.added_12m) + " (" + pct(K.added_yoy, 0) + ")", cls(K.added_yoy))),
      asOf(d), stale(d));
    const ops = (A.by_operator || []).length ? card("Active satellites by operator",
      ...svgBars(A.by_operator.map(o => o.operator.split(" (")[0]), [{ name: "Active", values: A.by_operator.map(o => o.n), color: css("--s1") }],
        { yFmt: v => big(v), catName: i => A.by_operator[i].operator + " · " + pct(A.by_operator[i].share, 1).replace("+", "") + " of all", labelW: 80, h: 240 }),
      note("CelesTrak SATCAT payloads marked operational (or partly, backup, spare, extended). Constellations by name, the rest by owner country. 5 years: do Kuiper, Qianfan and Guowang reach thousands each? " +
        "10 years: one operator with most of the satellites in orbit is the open question for regulators; 20 years: whether low orbit stays usable as the count passes 50,000.")) : card("Active satellites", missing(d, "active", "CelesTrak's catalog"), stale(d));
    const BY = A.by_year || {};
    const years = (BY.years || []).length ? card("Satellites still active, by the year they were launched",
      ...svgBars(BY.years.map(String), [{ name: "Starlink", values: BY.starlink, color: css("--s1") }, { name: "All others", values: BY.all.map((v, i) => v - BY.starlink[i]), color: css("--s2") }], { yFmt: v => big(v) }),
      note("Today's working fleet by launch year: a short-lived fleet that is replaced every five years looks like this. 5 years: the replacement rate Starlink needs; 10 years: whether others build fleets of the same kind; 20 years: whether satellites become consumables like phones.")) : null;
    const cum = (A.cumulative || []).length ? card("Today's active satellites, counted by launch date (cumulative)", ...linesChart([{ name: "All active", points: A.cumulative, color: css("--hold") }, { name: "Starlink", points: A.cumulative_starlink, color: css("--s1") }], f0, { small: true }),
      note("A lower bound on the fleet at each date (satellites since retired are not counted). 5 years: the slope is the net growth rate of the working fleet. 10 to 20 years: does it keep curving up?")) : null;
    const subs = (d.subs || []).length ? card("Starlink subscribers (millions)", ...linesChart([{ name: "Starlink", points: d.subs, color: css("--s1") }], v => f1(v) + "m", { small: true }),
      note("SpaceX and Starlink announcements (data/space/starlink.csv, from memory: verify). 5 years: doubling every year or so; 10 years: phones connecting directly to satellites could add hundreds of millions; 20 years: whether satellite internet is a utility like mobile."), cite(d.cited))
      : card("Starlink subscribers", el("div", { class: "muted" }, "Add rows to data/space/starlink.csv."));
    return [head, ops, el("div", { class: "grid2" }, subs, cum), years];
  },
  async industry() {
    const d = await api("industry"), S = d.stats || {}, E = d.eco_kpi || {};
    const syms = ["RKLB", "ASTS", "IRDM", "PL", "UFO", "SPY"], names = { RKLB: "Rocket Lab", ASTS: "AST SpaceMobile", IRDM: "Iridium", PL: "Planet Labs", UFO: "UFO (space ETF)", SPY: "SPY" };
    const R = d.rebased || {}, GE = (d.economy || {})["Global space economy (Space Foundation USD bn)"] || [];
    const head = card(null, followHead([
      { label: "Global space economy (USD), that year", points: GE, fmt: v => "$" + f0(v) + "bn", delta: { lag: "1y", fmt: SIGN0 } },
      ...syms.filter(k => (R[k] || []).length).map(k => ({ label: names[k] + " (rebased, start = 100)", points: R[k], fmt: f1, delta: { lag: "1y", fmt: SIGN0 } }))],
      { latest: "Latest figures" }),
      el("div", { class: "kpis", style: "margin-top:10px" },
        kpi("Space economy, 5-year growth a year (to " + (E.date || "").slice(0, 4) + ")", pct(E.cagr5, 1), cls(E.cagr5)),
        kpi("Space stocks (RKLB, ASTS, IRDM, PL) 1 year, average", pct((S.basket || {}).r1y, 0), cls((S.basket || {}).r1y)),
        ...syms.filter(k => S[k]).map(k => kpi(names[k] + " from its peak", pct(S[k].from_peak, 0), cls(S[k].from_peak)))), asOf(d), stale(d));
    const eco = d.economy || {};
    const gl = Object.fromEntries(Object.entries(eco).filter(([k]) => /USD/.test(k)));
    const uk = Object.fromEntries(Object.entries(eco).filter(([k]) => /GBP/.test(k)));
    const ge = has(gl) ? card("Size of the space economy (USD bn)", ...bySeries(gl, v => "$" + f0(v) + "bn", { extend: true }),
      note("Space Foundation's annual estimate (commercial revenue plus government budgets), OECD government budgets, and the WEF/McKinsey projection for 2035 (a single point, not data). " +
        "5 years: is growth still 5–10% a year? 10 years: does it reach the projection's path to $1.8 trillion? 20 years: whether space is a sector or a layer under every sector, like telecoms."), cite(d.cited)) : null;
    const uke = has(uk) ? card("UK space sector income (GBP bn)", ...bySeries(uk, v => "£" + f1(v) + "bn", { small: true, sync: false }),
      note("UK Space Agency, Size and Health of the UK Space Industry (financial years). 5 years: does UK income grow with launch from home or stay mostly satellite services? 10 and 20 years: the UK's share of a growing global market.")) : null;
    const reb = has(d.rebased) ? card("Space stocks against the market, rebased to 100 (log scale)", ...linesChart(syms.filter(k => (d.rebased[k] || []).length).map((k, i) => ({ name: k, points: d.rebased[k], color: css(SERIES[i % SERIES.length]), dashed: k === "SPY" })), f1, { log: true }),
      note("Daily closes from Nasdaq, price only. Rocket Lab (launch), AST SpaceMobile (phones to satellites), Iridium (satellite phones), Planet (imaging), UFO (a space ETF). 5 years: the 2021 SPAC listings crashed and some recovered; " +
        "10 years: does the market price launch and satellite firms like utilities or like startups? 20 years: SpaceX is private, so these are the listed proxies. No Hong Kong or China space stock is on the Nasdaq API."))
      : card("Prices", missing(d, "rebased", "Nasdaq prices"), stale(d));
    const miss = Object.keys(d.missing || {}).length ? el("div", { class: "muted" }, "Missing: " + Object.entries(d.missing).map(([k, v]) => k + " (" + v + ")").join(", ")) : null;
    const rows = card("Hand-entered figures", table(["Date", "Series", "Value", "Source"], (d.rows || []).map(r => el("tr", {}, el("td", {}, r.date.slice(0, 7)), el("td", {}, r.series), el("td", {}, r.value), srcCell(r)))),
      note("Kept in data/space/economy.csv. Every row marked 'verify' was entered from memory."));
    return [head, ge, uke, reb, miss, rows];
  },
  async ukhk() {
    const d = await api("ukhk"), U = d.uk_kpi || {}, CH = d.china || {}, K = CH.kpi || {};
    const head = card(null, followHead([
      { label: "China commercial (not CASC) launches that year", points: CH.commercial || [], fmt: f0, delta: { lag: "1y", fmt: SIGN0 } },
      ...Object.entries(CH.providers || {}).slice(0, 4).map(([k, p]) => ({ label: k + " launches that year", points: p, fmt: f0 }))],
      { latest: "Latest full year" }),
      el("div", { class: "kpis", style: "margin-top:10px" },
        kpi("UK orbital launch attempts (all time)", f0(U.attempts) + " (" + f0(U.successes) + " reached orbit)"), kpi("…from UK soil", f0(U.from_uk_soil)),
        kpi("Days since the last UK attempt (" + (U.last || "–") + ")", f0(U.days_since)),
        kpi("China " + (K.last_year ? K.last_year + 1 : "") + " so far", f0(K.ytd))), asOf(d), stale(d),
      note("UK attempts are hand-entered (data/space/milestones.csv, kind 'launch'); China's count is GCAT's. Hong Kong has no launch site; it builds satellites and instruments that fly on Chinese rockets."));
    const ukl = card("UK orbital launch attempts", table(["Date", "Attempt", "Site", "Outcome", "Source"], (d.uk_launches || []).slice().reverse().map(r => el("tr", {}, el("td", {}, r.date), el("td", { class: "wrap" }, r.event), el("td", {}, r.site || "–"),
      el("td", {}, el("span", { class: "pill " + (r.outcome === "success" ? "ok" : "bad") }, r.outcome || "–")), srcCell(r)))),
      note("5 years: does a rocket (RFA One, Skyrora, Orbex) reach orbit from SaxaVord or Sutherland? 10 years: whether the UK launches every month or two, which would make it Europe's launch base. 20 years: Black Arrow (1971) is still the only British rocket to reach orbit."));
    const ms = (d.milestones || []);
    const tl = (place, title, why) => { const rs = ms.filter(r => place.includes(r.place)); return rs.length ? card(title, el("div", { class: "tl" }, ...rs.flatMap(r => [el("div", { class: "d" }, r.date), el("div", {}, link(r.event, r.source), r.note ? el("span", { class: "muted" }, " · " + r.note) : "")])), note(why)) : null; };
    const uk = tl(["UK"], "UK: spaceports and launches (UK Space Agency, CAA)", "Cornwall (horizontal launch) lost its operator in 2023; SaxaVord in Shetland is licensed for vertical launch. 5 years: the first orbit from UK soil; 10 years: a regular cadence; 20 years: a European share of launch outside France.");
    const hk = tl(["HK"], "Hong Kong", "Hong Kong takes part through universities (PolyU's lunar hardware), a satellite firm (Hong Kong Aerospace Technology Group) and, for the first time, an astronaut candidate. 5 to 20 years: whether Hong Kong becomes China's space finance and components hub.");
    const cn = tl(["China", "US"], "China and the US: milestones", "The milestones that changed the pace: reusable boosters, megaconstellations and the space station. 5 years: China's first reusable booster landing from orbit; 10 years: both countries with lunar bases planned for the 2030s. 20 years: whether the Moon becomes a second destination for routine freight.");
    const prov = has(CH.providers) ? card("China's orbital launches per year by provider (GCAT)", ...bySeries(CH.providers, f0), ...linesChart([{ name: "Commercial (not CASC)", points: CH.commercial, color: css("--hold"), dashed: true }], f0, { small: true }),
      note("CASC is the state rocket maker; the commercial firms (LandSpace, Galactic Energy, Space Pioneer, CAS Space and others) started flying after 2019. 5 years: do they fly the reusable rockets they promise? " +
        "10 years: Qianfan and Guowang need thousands of satellites launched, which only cheaper rockets can do; 20 years: whether China matches the US in launches per year."))
      : card("China's launches", missing(d, "china", "The GCAT launch list"), stale(d));
    return [head, ukl, el("div", { class: "grid2" }, uk, hk), prov, cn, card(null, cite(d.cited), note("Kept in data/space/milestones.csv. Every row marked 'verify' was entered from memory."))];
  },
};
window.TOPIC = { VIEWS };
})();
