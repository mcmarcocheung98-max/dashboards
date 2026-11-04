// London Housing Index: tabs and cards. Data from /api/housing/<prices|market|afford>; helpers from topic.html.
(() => {
const pc = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
// Borough map: a green-to-blue ramp, seven bins, low to high = away from the page colour (light theme light green→dark blue, dark theme
// dark green→light blue); lightness rises steadily and both ends clear 2:1 against the surface (dataviz palette validator); grey = no figure.
// The bins are fixed per measure across the whole timeline, so the map darkens as prices rise rather than re-ranking every month.
const RAMPS = { light: ["#6dc295", "#4bae98", "#2f93a4", "#2577ad", "#1d5fa3", "#15478c", "#0c2f66"],
  dark: ["#1d5a45", "#1f7560", "#23907b", "#2fa9a3", "#4dbdc8", "#7fcfe6", "#b9e3f7"] };
const isDark = () => parseInt((css("--surface").match(/^#(..)/) || [0, "ff"])[1], 16) < 0x80;
const MAP_METRICS = [["flat", "Flat"], ["terraced", "Terraced house"], ["semi", "Semi-detached"], ["detached", "Detached"], ["rent_2bed", "2-bed rent / month"]];
let mapMetric = "flat", mapMonth = null, mapPlay = null;
const money = v => v == null ? "–" : v >= 1e6 ? "£" + (v / 1e6).toFixed(2) + "m" : v >= 1e4 ? "£" + Math.round(v / 1000) + "k" : gbp(v);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// Top cards follow the date hovered or clicked on any chart (datedHead/valueAt from topic.html): t is that date, null = latest
const YEAR = 365.25 * 86400;
const timeAt = (pts, t) => { if (!pts || !pts.length) return null; if (t == null) return pts[pts.length - 1][0]; let r = null; for (const p of pts) { if (p[0] <= t) r = p[0]; else break; } return r; };
const chgAt = (pts, t, yrs) => { const T = timeAt(pts, t), v = valueAt(pts, T), w = T == null ? null : valueAt(pts, T - yrs * YEAR); return v == null || !w ? null : v / w - 1; };
const monthOf = (pts, t) => { const T = timeAt(pts, t); return T == null ? "–" : month(T); };
// Top 3 boroughs for each measure (ranks of what the table shows; not advice)
const PICKS = [
  ["Cheapest flats", r => r.flat, 1, v => money(v)],
  ["Cheapest terraced houses", r => r.terraced, 1, v => money(v)],
  ["Cheapest 2-bed rent", r => r.rent_2bed, 1, v => gbp(v) + " a month"],
  ["Highest rental yield (2-bed rent × 12 ÷ flat price)", r => r.rent_2bed && r.flat ? r.rent_2bed * 12 / r.flat : null, -1, v => (v * 100).toFixed(1) + "%"],
  ["Prices rising fastest (on a year)", r => r.yoy, -1, v => pc(v)],
  ["Most growth over 5 years", r => r.change_5y, -1, v => pct(v, 0)],
  ["Rents rising slowest (on a year)", r => r.rent_yoy, 1, v => pc(v)],
  ["Most expensive homes (all types)", r => r.avg, -1, v => money(v)],
];
function boroughPicks(d) {
  const grid = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px" }, ...PICKS.map(([title, get, dir, fmt]) => {
    const top = d.rows.filter(r => get(r) != null).sort((a, b) => dir * (get(a) - get(b))).slice(0, 3);
    return el("div", { style: "border:1px solid var(--line);border-radius:10px;padding:10px 12px" }, el("div", { style: "font-weight:600;margin-bottom:6px" }, title),
      ...(top.length ? top.map((r, i) => el("div", { style: "display:flex;justify-content:space-between;gap:8px;padding:2px 0" },
        el("span", {}, el("span", { class: "muted" }, (i + 1) + ". "), r.borough), el("b", { style: "font-variant-numeric:tabular-nums" }, fmt(get(r)))))
        : [el("div", { class: "muted" }, "No figures yet.")]));
  }));
  const rm = (d.rows.find(r => r.rent_month) || {}).rent_month;
  return card("Top 3 boroughs by measure", grid,
    note("Rankings of the latest figures (prices " + (d.as_of || "").slice(0, 7) + (rm ? ", rents " + rm.slice(0, 7) : "") + "), not recommendations. Yield is a gross figure before costs; borough averages hide big differences between streets."));
}
// ------------------------------------------------------------------ Rent or buy calculator (all the arithmetic is here, in the browser)
// Stamp duty land tax, England and Northern Ireland, residential, from 1 April 2025 (gov.uk/stamp-duty-land-tax/residential-property-rates)
function stampDuty(price, firstTime) {
  if (firstTime && price <= 500000) return Math.max(0, Math.min(price, 500000) - 300000) * 0.05;
  const bands = [[125000, 0], [250000, 0.02], [925000, 0.05], [1500000, 0.10], [Infinity, 0.12]];
  let tax = 0, lo = 0;
  for (const [hi, rate] of bands) { if (price > lo) tax += (Math.min(price, hi) - lo) * rate; lo = hi; }
  return tax;
}
const payment = (loan, ratePct, years) => { const r = ratePct / 100 / 12, n = years * 12; return loan <= 0 ? 0 : r === 0 ? loan / n : loan * r / (1 - (1 + r) ** -n); };
// Month by month over the horizon: the buyer pays mortgage + running costs; the renter pays rent and invests the buyer's upfront cash;
// each month whoever pays less invests the difference. Wealth: buyer = home value - selling costs - loan left + savings; renter = savings.
function rentOrBuy(v) {
  const loan = v.price * (1 - v.deposit / 100), M = payment(loan, v.rate, v.term), sdlt = stampDuty(v.price, v.ftb);
  const upfront = v.price * v.deposit / 100 + sdlt + v.fees;
  const gI = (1 + v.invest / 100) ** (1 / 12), gV = (1 + v.growth / 100) ** (1 / 12), r = v.rate / 100 / 12;
  let bal = loan, value = v.price, rent = v.rent, renterPot = upfront, buyerPot = 0, paidOwn = 0, paidRent = 0;
  const wealth = m => ({ buy: value * (1 - v.sell / 100) - bal + buyerPot, rent: renterPot });
  const years = [{ y: 0, ...wealth(), own: 0, rentPaid: 0 }];
  let breakeven = null;
  for (let m = 1; m <= v.horizon * 12; m++) {
    const pay = m <= v.term * 12 && bal > 0 ? Math.min(M, bal * (1 + r)) : 0;
    bal = Math.max(0, bal * (1 + r) - pay);
    const own = pay + value * v.running / 100 / 12;
    renterPot *= gI; buyerPot *= gI;
    if (own > rent) renterPot += own - rent; else buyerPot += rent - own;
    paidOwn += own; paidRent += rent;
    value *= gV;
    if (m % 12 === 0) {
      rent *= 1 + v.rentGrowth / 100;
      const w = wealth();
      years.push({ y: m / 12, ...w, own: paidOwn, rentPaid: paidRent });
      if (breakeven == null && w.buy >= w.rent) breakeven = m / 12;
    }
  }
  return { loan, M, sdlt, upfront, years, breakeven, firstOwn: M + v.price * v.running / 100 / 12 };
}
const CALC = { code: "E12000007", type: "flat" };
// Profile: who the calculator is for. Defaults are the owner's own profile; edits are kept in this browser only.
const PROFILE_DEFAULT = { age: 26, household: "single", dog: true, drives: false, officeDays: 3, social: "sometimes", gym: true, pay: 63000, budget: 40 };
let PROFILE = (() => { try { return { ...PROFILE_DEFAULT, ...JSON.parse(localStorage.getItem("housing:profile:v2") || "{}") }; } catch (e) { return { ...PROFILE_DEFAULT }; } })();
const saveProfile = () => { try { localStorage.setItem("housing:profile:v2", JSON.stringify(PROFILE)); } catch (e) {} };
// Take-home pay a year in England, 2025/26: personal allowance £12,570 (tapered above £100,000), income tax 20% / 40% / 45%, employee NI 8% / 2%
function takeHome(gross) {
  const pa = Math.max(0, 12570 - Math.max(0, gross - 100000) / 2), taxable = Math.max(0, gross - pa);
  const tax = Math.min(taxable, 37700) * 0.2 + Math.max(0, Math.min(taxable, 125140 - pa) - 37700) * 0.4 + Math.max(0, gross - 125140) * 0.45;
  const ni = Math.max(0, Math.min(gross, 50270) - 12570) * 0.08 + Math.max(0, gross - 50270) * 0.02;
  return gross - tax - ni;
}
const bedsFor = p => p.household === "family" ? 2 : 1;
const rentFor = (r, p) => bedsFor(p) === 2 ? r.rent_2bed : (r.rent_1bed ?? r.rent_2bed);
const homeFor = p => p.household === "family" ? "terraced" : "flat";
const clamp01 = x => Math.max(0, Math.min(1, x));
// Fit of a borough for the profile, 0-100: a weighted mean of what the profile cares about. cost = the monthly housing cost to judge.
function fitScore(r, p, cost, monthlyPay) {
  if (cost == null || r.km_to_centre == null) return null;
  const share = cost / monthlyPay, budget = p.budget / 100;
  const parts = [
    ["afford", 1.5, clamp01(1.5 - share / budget), "£" + Math.round(cost).toLocaleString("en-GB") + " a month, " + Math.round(share * 100) + "% of take-home"],
    ["commute", 0.2 + 0.25 * p.officeDays, clamp01(1 - (r.km_to_centre - 2) / 20), r.km_to_centre + " km to the centre"],
    ["transport", p.drives ? 0.2 : 0.8, clamp01(1 - (r.zone - 1) / 5), "zone " + r.zone],
    ["green", (p.dog ? 0.9 : 0.2) + (p.household === "family" ? 0.5 : 0), clamp01((r.green_pct - 5) / 45), r.green_pct + "% green space"],
    ["night", { rarely: 0, sometimes: 0.5, often: 1 }[p.social] ?? 0.5, clamp01((r.nightlife - 1) / 4), "nightlife " + r.nightlife + "/5"],
    ["gym", p.gym ? 0.4 : 0.1, clamp01((r.amenities - 1) / 4), "gyms & amenities " + r.amenities + "/5"]];
  const W = parts.reduce((a, x) => a + x[1], 0), score = Math.round(100 * parts.reduce((a, x) => a + x[1] * x[2], 0) / W);
  const why = [parts[0][3], ...parts.slice(1).filter(x => x[1] > 0).sort((a, b) => b[1] * b[2] - a[1] * a[2]).slice(0, 2).map(x => x[3])];   // cost first, then the two strongest reasons
  return { score, why, share };
}
function calcView(d) {
  const rows = d.rows || [], byCode = Object.fromEntries(rows.map(r => [r.code, r]));
  const TYPES = [["flat", "Flat"], ["terraced", "Terraced house"], ["semi", "Semi-detached"], ["detached", "Detached"]];
  const v = { price: 0, rent: 0, deposit: 10, rate: d.rate_now != null ? Math.round(d.rate_now * 100) / 100 : 4.5, term: 25, ftb: true, fees: 3000, running: 1.0,
    growth: 3, rentGrowth: 3, invest: 5, sell: 1.5, horizon: 10 };
  const pick = () => { const r = byCode[CALC.code] || rows[0] || {}; v.price = r[CALC.type] || 0; v.rent = rentFor(r, PROFILE) || 0; };
  const P = PROFILE, monthlyPay = () => takeHome(P.pay ?? d.london_pay ?? 45000) / 12;
  const ownCost = (r, type) => r[type] ? payment(r[type] * (1 - v.deposit / 100), v.rate, v.term) + r[type] * v.running / 100 / 12 : null;
  const ranked = mode => rows.filter(r => r.code !== "E12000007").map(r => ({ r, f: fitScore(r, P, mode === "rent" ? rentFor(r, P) : ownCost(r, homeFor(P)), monthlyPay()) }))
    .filter(x => x.f).sort((a, b) => b.f.score - a.f.score);
  const applyProfile = () => { const best = ranked("buy")[0]; if (best) CALC.code = best.r.code; CALC.type = homeFor(P); };
  applyProfile();
  pick();
  const inputs = {};
  const field = (key, label, step, suffix) => {
    const inp = el("input", { type: "number", step, value: v[key], style: "width:100%;box-sizing:border-box;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit",
      oninput: e => { const x = parseFloat(e.target.value); if (!isNaN(x)) { v[key] = x; compute(); } } });
    inputs[key] = inp;
    return el("label", { style: "display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)" }, label + (suffix ? " (" + suffix + ")" : ""), inp);
  };
  const sel = (opts, cur, onchange) => el("select", { style: "width:100%;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit", onchange },
    ...opts.map(([k, l]) => { const o = el("option", { value: k }, l); if (k === cur) o.selected = true; return o; }));
  const resetFromData = () => { pick(); inputs.price.value = v.price; inputs.rent.value = v.rent; boroughSel.value = CALC.code; typeSel.value = CALC.type; compute(); history(); fits(); };
  const ftb = el("input", { type: "checkbox", onchange: e => { v.ftb = e.target.checked; compute(); } }); ftb.checked = v.ftb;
  const boroughSel = sel(rows.map(r => [r.code, r.borough]), CALC.code, e => { CALC.code = e.target.value; resetFromData(); });
  const typeSel = sel(TYPES, CALC.type, e => { CALC.type = e.target.value; resetFromData(); });
  // ---- the profile card
  const lab = (text, ctl) => el("label", { style: "display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)" }, text, ctl);
  const pnum = (key, step, ph) => { const i = el("input", { type: "number", step, value: P[key] ?? "", placeholder: ph || "", style: "width:100%;box-sizing:border-box;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--ink);font:inherit",
    onchange: e => { const x = parseFloat(e.target.value); P[key] = isNaN(x) ? null : x; profileChanged(); } }); return i; };
  const psel = (key, opts) => sel(opts, String(P[key]), e => { const x = e.target.value; P[key] = x === "true" ? true : x === "false" ? false : isNaN(+x) ? x : +x; profileChanged(); });
  const yn = [["true", "Yes"], ["false", "No"]];
  const fitsHost = el("div", {});
  const profileCard = card("Your profile: who is this for?",
    el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px 12px" },
      lab("Age", pnum("age", 1)), lab("Household", psel("household", [["single", "Single"], ["couple", "Couple"], ["family", "Family with children"]])),
      lab("Dog", psel("dog", yn)), lab("Drive a car", psel("drives", yn)),
      lab("Office days in central London a week", psel("officeDays", [0, 1, 2, 3, 4, 5].map(n => [String(n), String(n)]))),
      lab("Social life and nightlife", psel("social", [["rarely", "Rarely"], ["sometimes", "From time to time"], ["often", "Often"]])),
      lab("Need a gym nearby", psel("gym", yn)),
      lab("Gross pay a year (£, blank = London median)", pnum("pay", 1000, d.london_pay ? String(Math.round(d.london_pay)) : "")),
      lab("Housing budget (% of take-home)", pnum("budget", 1))),
    el("div", { style: "display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap" },
      el("button", { class: "pill", style: "cursor:pointer;border:1px solid var(--line);font:inherit", onclick: () => { PROFILE = { ...PROFILE_DEFAULT }; saveProfile(); location.reload(); } }, "Reset to default profile"),
      el("span", { class: "muted" }, "Kept in this browser only. Default: 26, single, a dog, no car, 3 office days in central London, nightlife from time to time, a gym, £63,000 gross pay.")),
    fitsHost);
  function profileChanged() { saveProfile(); Object.assign(PROFILE, P); applyProfile(); resetFromData(); }
  function fits() {
    const pay = monthlyPay(), beds = bedsFor(P), home = homeFor(P) === "flat" ? "flat" : "terraced house";
    const list = (mode, title, sub) => el("div", { style: "border:1px solid var(--line);border-radius:10px;padding:10px 12px" }, el("div", { style: "font-weight:600" }, title), el("div", { class: "muted", style: "margin-bottom:6px" }, sub),
      ...ranked(mode).slice(0, 3).map((x, i) => el("div", { style: "padding:4px 0;border-top:" + (i ? "1px solid var(--line)" : "0") },
        el("div", { style: "display:flex;justify-content:space-between;gap:8px" }, el("span", {}, el("span", { class: "muted" }, (i + 1) + ". "), el("b", {}, x.r.borough)),
          el("span", { class: x.f.share <= P.budget / 100 ? "up" : "down", style: "font-weight:650" }, x.f.score + "/100")),
        el("div", { class: "muted" }, x.f.why.join(" · ")))));
    const lisa = P.age != null && P.age < 40 && v.ftb ? " Under 40 and buying a first home: a Lifetime ISA adds 25% to up to £4,000 a year (homes up to £450,000)." : "";
    fitsHost.replaceChildren(el("h2", { style: "margin-top:14px" }, "Best fits for your profile"),
      el("div", { class: "muted", style: "margin-bottom:8px" }, "Take-home about " + gbp(pay) + " a month; budget " + P.budget + "% = " + gbp(pay * P.budget / 100) + ". Looking at a " + beds + "-bed to rent and a " + home + " to buy." + lisa),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px" },
        list("rent", "Top 3 to rent", "Average " + beds + "-bed rent"), list("buy", "Top 3 to buy a " + home, "Monthly cost to own, with the deposit, rate and term below")),
      note("Fit weighs what your profile cares about: cost against your budget (most), distance to the centre (more with more office days), Tube/rail zone (more without a car), green space (more with a dog or children), nightlife and gyms. Distances are computed from the borough boundaries; zone, green space, nightlife and amenity scores are estimates (data/housing/borough_profile.csv, marked verify). The calculator below starts on the top borough to buy."));
  }
  const form = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px 12px" },
    el("label", { style: "display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)" }, "Borough", boroughSel),
    el("label", { style: "display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)" }, "Home to buy", typeSel),
    field("price", "Price", 5000, "£"), field("rent", "Rent instead (" + bedsFor(P) + "-bed)", 50, "£ a month"), field("deposit", "Deposit", 1, "%"), field("rate", "Mortgage rate", 0.05, "% a year"),
    field("term", "Mortgage term", 1, "years"), field("fees", "Buying fees: legal, survey", 250, "£"), field("running", "Owner's running costs", 0.1, "% of value a year"),
    field("growth", "House price growth", 0.5, "% a year"), field("rentGrowth", "Rent growth", 0.5, "% a year"), field("invest", "Return on savings", 0.5, "% a year"),
    field("sell", "Selling costs", 0.25, "% of value"), field("horizon", "Stay for", 1, "years"),
    el("label", { style: "display:flex;gap:6px;align-items:center;font-size:12.5px;color:var(--ink2);margin-top:18px" }, ftb, "First-time buyer (stamp duty relief)"));
  const out = el("div", {}), picksHost = el("div", {}), histHost = el("div", {});
  function compute() {
    const res = rentOrBuy(v), last = res.years[res.years.length - 1], better = last.buy >= last.rent;
    const kp = el("div", { class: "kpis" },
      kpi("Monthly mortgage payment", gbp(res.M)), kpi("Rent a month (now)", gbp(v.rent)),
      kpi("Owning a month: mortgage + running costs", gbp(res.firstOwn), res.firstOwn > v.rent ? "down" : "up"),
      kpi("Cash needed to buy: deposit + stamp duty + fees", gbp(res.upfront)), kpi("Stamp duty", gbp(res.sdlt)), kpi("Loan", gbp(res.loan)),
      kpi("After " + v.horizon + " years: buyer's wealth", gbp(last.buy), better ? "up" : ""), kpi("After " + v.horizon + " years: renter's wealth", gbp(last.rent), better ? "" : "up"),
      kpi("Buying pulls ahead", res.breakeven == null ? "not within " + v.horizon + " years" : res.breakeven === 0 ? "from day one" : "after " + res.breakeven + " year" + (res.breakeven > 1 ? "s" : "")));
    const chart = svgLines([{ name: "Buyer's wealth", points: res.years.map(p => [p.y, Math.round(p.buy)]), width: 2.5 },
      { name: "Renter's wealth", points: res.years.map(p => [p.y, Math.round(p.rent)]), width: 2.5, color: css("--s2") },
      { name: "Paid to own (cumulative)", points: res.years.map(p => [p.y, Math.round(p.own)]), dashed: true, color: css("--hold") },
      { name: "Paid in rent (cumulative)", points: res.years.map(p => [p.y, Math.round(p.rentPaid)]), dashed: true, color: css("--s4") }],
      { xFmt: x => "Year " + Math.round(x), yFmt: y => money(y), h: 280 });
    out.replaceChildren(kp, el("h2", { style: "margin-top:14px" }, "Year by year from today: wealth if you buy vs if you rent"), ...chart,
      note("Wealth: buyer = home value less selling costs and the loan left, plus savings; renter = the buyer's upfront cash invested, plus savings. Each month whoever pays less invests the difference at the savings return. The mortgage rate is held for the whole term (no remortgaging); running costs cover service charge or repairs, insurance and ground rent. An illustration, not advice."));
    picks();
  }
  function picks() {
    const mort = r => r.flat ? payment(r.flat * (1 - v.deposit / 100), v.rate, v.term) + r.flat * v.running / 100 / 12 : null;
    const b = rows.filter(r => r.code !== "E12000007");
    const top = (get, dir) => b.filter(r => get(r) != null).sort((x, y) => dir * (get(x) - get(y))).slice(0, 3);
    const box = (title, list, fmt, sub) => el("div", { style: "border:1px solid var(--line);border-radius:10px;padding:10px 12px" }, el("div", { style: "font-weight:600" }, title),
      el("div", { class: "muted", style: "margin-bottom:6px" }, sub), ...(list.length ? list.map((r, i) => el("div", { style: "display:flex;justify-content:space-between;gap:8px;padding:2px 0" },
        el("span", {}, el("span", { class: "muted" }, (i + 1) + ". "), r.borough), el("b", { style: "font-variant-numeric:tabular-nums" }, fmt(r)))) : [el("div", { class: "muted" }, "No figures yet.")]));
    const ratio = r => rentFor(r, PROFILE) && mort(r) ? mort(r) / rentFor(r, PROFILE) : null;
    picksHost.replaceChildren(card("Top 3 picks: renting and buying a flat",
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px" },
        box("Cheapest to rent", top(r => rentFor(r, PROFILE), 1), r => gbp(rentFor(r, PROFILE)) + " a month", "Average " + bedsFor(PROFILE) + "-bed rent"),
        box("Cheapest flats to buy", top(r => r.flat, 1), r => money(r.flat), "Average flat price"),
        box("Where buying a flat beats renting most", top(ratio, 1), r => gbp(mort(r)) + " vs " + gbp(rentFor(r, PROFILE)), "Monthly cost to own a flat vs " + bedsFor(PROFILE) + "-bed rent"),
        box("Where renting beats buying most", top(ratio, -1), r => gbp(rentFor(r, PROFILE)) + " vs " + gbp(mort(r)), bedsFor(PROFILE) + "-bed rent vs monthly cost to own a flat")),
      note("Cost to own uses your deposit, rate, term and running costs above, so the picks move as you change them. A flat's average price and a 2-bed's average rent are not the same homes; rankings, not recommendations.")));
  }
  function history() {
    const H = d.history || {}, V = H.values || {}, n = H.months || 0;
    if (!n) { histHost.replaceChildren(); return; }
    const [y0, m0] = H.start.split("-").map(Number), t0 = Date.UTC(y0, m0 - 1, 1) / 1000;
    const tAt = i => Date.UTC(y0, m0 - 1 + i, 1) / 1000;
    const rk = bedsFor(PROFILE) === 2 ? "rent_2bed" : "rent_1bed";
    const prices = (V[CALC.type] || {})[CALC.code] || [], rentsH = (V[rk] || {})[CALC.code] || [], FX = d.fixed_2y || [];
    const own = [], rentPts = [];
    for (let i = 0; i < n; i++) {
      const t = tAt(i), p = prices[i], rate = valueAt(FX, t);
      if (p != null && rate != null) own.push([t, Math.round(payment(p * (1 - v.deposit / 100), rate, v.term))]);
      if (rentsH[i] != null) rentPts.push([t, rentsH[i]]);
    }
    const name = (byCode[CALC.code] || {}).borough || "", type = TYPES.find(x => x[0] === CALC.type)[1].toLowerCase();
    histHost.replaceChildren(card("Then and now: monthly mortgage on the average " + type + " in " + name + " vs the average " + bedsFor(PROFILE) + "-bed rent",
      ...linesChart([{ name: "Mortgage payment (" + v.deposit + "% deposit, " + v.term + " years, 2-year fixed rate of the day)", points: own },
        { name: bedsFor(PROFILE) + "-bed rent", points: rentPts, color: css("--s2") }], x => gbp(x)),
      note("Each month: the borough's average price for that home type (UK HPI) with your deposit and term at the Bank of England's quoted 2-year fixed rate (75% LTV) of that month, against the average 2-bed rent (ONS PIPR, from 2015).")));
  }
  for (const k of ["deposit", "term"]) inputs[k].addEventListener("change", history);           // the history chart redraws when you leave the box
  for (const k of ["deposit", "rate", "term", "running"]) inputs[k].addEventListener("change", fits);
  compute(); history(); fits();
  return [profileCard, card("Rent or buy: every number is yours to change", form,
    el("div", { class: "muted", style: "margin-top:8px" }, "Price and rent start from the latest averages for the borough and home type (prices " + (d.as_of || "").slice(0, 7) + ", rents " + (d.rent_month || "").slice(0, 7) +
      "); the rate from the Bank of England's quoted 2-year fixed at 75% LTV. Stamp duty: England rates from April 2025, with first-time buyer relief up to £500,000."), out),
    picksHost, histHost];
}
function boroughMap(d) {
  const H = d.map.history || {}, V = H.values || {}, n = H.months || 0;
  const [y0, m0] = (H.start || "2005-01").split("-").map(Number);
  const label = i => MONTHS[(m0 - 1 + i) % 12] + " " + (y0 + Math.floor((m0 - 1 + i) / 12));
  const names = Object.fromEntries(d.rows.filter(r => r.code).map(r => [r.code, r.borough]));
  const at = (m, code, i) => ((V[m] || {})[code] || [])[i] ?? null;
  const fmt = (m, v) => v == null ? "–" : m === "rent_2bed" ? gbp(v) + " a month" : money(v);
  const lastWith = m => { for (let i = n - 1; i >= 0; i--) if (Object.values(V[m] || {}).some(a => a[i] != null)) return i; return n - 1; };
  const firstWith = m => { for (let i = 0; i < n; i++) if (Object.values(V[m] || {}).some(a => a[i] != null)) return i; return 0; };
  const host = el("div", {}), info = el("div", { class: "muted", style: "min-height:40px;margin-top:6px" }, "Hover over or tap a borough.");
  let picked = null;
  const show = code => {
    if (!code) return;
    const i = mapMonth;
    info.replaceChildren(el("b", { style: "color:var(--ink)" }, names[code] || code), " · " + label(i) + " · flat " + money(at("flat", code, i)) + " · terraced " + money(at("terraced", code, i)) +
      " · semi " + money(at("semi", code, i)) + " · detached " + money(at("detached", code, i)) + " · 2-bed rent " + fmt("rent_2bed", at("rent_2bed", code, i)));
  };
  const draw = () => {
    if (mapPlay) { clearInterval(mapPlay); mapPlay = null; }
    const RAMP = RAMPS[isDark() ? "dark" : "light"], first = firstWith(mapMetric), last = lastWith(mapMetric);
    if (mapMonth == null || mapMonth > last) mapMonth = last;
    if (mapMonth < first) mapMonth = first;
    // fixed bins for this measure: septiles of every borough-month value on the timeline
    const all = Object.values(V[mapMetric] || {}).flat().filter(v => v != null).sort((a, b) => a - b);
    const cuts = [1, 2, 3, 4, 5, 6].map(k => all[Math.floor(k * all.length / 7)]);
    const bin = v => v == null ? null : cuts.filter(c => v >= c).length;
    const metricName = MAP_METRICS.find(m => m[0] === mapMetric)[1];
    const svg = svgEl("svg", { viewBox: d.map.viewBox, role: "img", style: "width:100%;height:auto;max-height:560px;display:block" });
    const paths = {};
    for (const sh of d.map.shapes) {
      const p = svgEl("path", { d: sh.d, stroke: css("--surface"), "stroke-width": 2, "stroke-linejoin": "round", style: "cursor:pointer;transition:fill .25s" }, svg);
      const t = svgEl("title", {}, p);
      paths[sh.code] = [p, t];
      const on = () => { picked = sh.code; Object.values(paths).forEach(([x]) => x.setAttribute("stroke", css("--surface"))); p.setAttribute("stroke", css("--ink")); svg.append(p); show(sh.code); };
      p.addEventListener("mouseenter", on); p.addEventListener("click", on);
    }
    const when = el("b", { style: "font-variant-numeric:tabular-nums;min-width:72px;display:inline-block;color:var(--ink)" });
    const paint = () => {
      for (const [code, [p, t]] of Object.entries(paths)) {
        const v = at(mapMetric, code, mapMonth), b = bin(v);
        p.setAttribute("fill", b == null ? css("--chip") : RAMP[b]);
        t.textContent = (names[code] || code) + ", " + label(mapMonth) + ": " + (v == null ? "no figure" : fmt(mapMetric, v));
      }
      svg.setAttribute("aria-label", "Map of London boroughs coloured by " + metricName + ", " + label(mapMonth));
      when.textContent = label(mapMonth); slider.value = mapMonth; show(picked);
    };
    const slider = el("input", { type: "range", min: first, max: last, step: 1, value: mapMonth, "aria-label": "Month", style: "flex:1;min-width:120px;accent-color:var(--accent)",
      oninput: e => { mapMonth = +e.target.value; paint(); } });
    const stop = () => { clearInterval(mapPlay); mapPlay = null; play.textContent = "▶ Play"; };
    const play = el("button", { style: "border:1px solid var(--line);background:var(--surface);color:var(--ink2);border-radius:8px;padding:4px 10px;font:inherit;font-size:12.5px;cursor:pointer",
      onclick: () => {
        if (mapPlay) return stop();
        if (mapMonth >= last) mapMonth = first;
        play.textContent = "❚❚ Pause";
        mapPlay = setInterval(() => { if (!document.contains(svg) || mapMonth >= last) return stop(); mapMonth = Math.min(last, mapMonth + 3); paint(); }, 160);
      } }, "▶ Play");
    const timeline = el("div", { style: "display:flex;align-items:center;gap:10px;margin:4px 0 8px;flex-wrap:wrap" }, play, when, slider,
      el("span", { class: "muted" }, label(first) + " – " + label(last)));
    const edges = [all[0], ...cuts, all[all.length - 1]];
    const legend = el("div", { class: "chips", style: "margin-top:6px;font-size:12px" }, ...RAMP.map((c, i) => el("span", { style: "display:inline-flex;align-items:center;gap:5px;color:var(--ink2)" },
      el("i", { style: `display:inline-block;width:14px;height:14px;border-radius:3px;background:${c}` }), money(edges[i]) + "–" + money(edges[i + 1]))),
      el("span", { style: "display:inline-flex;align-items:center;gap:5px;color:var(--ink2)" }, el("i", { style: "display:inline-block;width:14px;height:14px;border-radius:3px;background:var(--chip)" }), "no figure"));
    const seg = el("div", { class: "seg" }, ...MAP_METRICS.map(([k, l]) => el("button", { class: k === mapMetric ? "on" : "", onclick: () => { mapMetric = k; draw(); } }, l)));
    host.replaceChildren(seg, timeline, svg, legend);
    paint();
  };
  if (!n) return card("Map: what a home costs in each borough", el("div", { class: "muted" }, "Not available right now."));
  draw();
  return card("Map: what a home costs in each borough, over time", host, info,
    d.rents_error ? el("div", { class: "muted" }, "2-bed rents not available right now (" + d.rents_error + ").") : null,
    note("Drag the timeline or press Play to watch prices change month by month. Colour: seven bands, green (cheapest) to dark blue (dearest), fixed across all years for the measure chosen, so the map darkens as prices rise; prices are as paid, not adjusted for inflation. " +
      "Prices: UK HPI average by property type (from 2005). Rent: ONS Price Index of Private Rents, average agreed rent for a 2-bedroom home (from 2015). " + d.map.source));
}
const VIEWS = {
  async prices() {
    const d = await api("prices"), n = d.now || {};
    const A = d.london_avg || [], Y = d.london_yoy || [];
    const R = d.london_real || [], LR = (d.rents || {})["London average rent"] || [], GY = d.gross_yield || [], PR = d.premium || [];
    const realPeakTo = t => { const T = timeAt(R, t); let best = null; for (const p of R) { if (T != null && p[0] > T) break; if (!best || p[1] > best[1]) best = p; } return best; };
    const peakTo = t => { const T = timeAt(A, t); let best = null; for (const p of A) { if (T != null && p[0] > T) break; if (!best || p[1] > best[1]) best = p; } return best; };
    const head = card(null, datedHead([
      { label: t => "London average price (" + monthOf(A, t) + ")", value: t => [gbp(valueAt(A, timeAt(A, t)))] },
      { label: () => "Change on a year ago", value: t => { const v = valueAt(Y, timeAt(Y, t)); return [pc(v), cls(v)]; } },
      { label: t => { const pk = peakTo(t); return "From the peak (" + (pk ? month(pk[0]) : "–") + ")"; },
        value: t => { const pk = peakTo(t), v = valueAt(A, timeAt(A, t)); const x = pk && v != null ? v / pk[1] - 1 : null; return [pct(x), cls(x)]; } },
      { label: () => "5 years", value: t => { const x = chgAt(A, t, 5); return [pct(x, 0), cls(x)]; } },
      { label: () => "10 years", value: t => { const x = chgAt(A, t, 10); return [pct(x, 0), cls(x)]; } },
      { label: t => "In today's money, from its peak (" + (realPeakTo(t) ? month(realPeakTo(t)[0]) : "–") + ")",
        value: t => { const pk = realPeakTo(t), v = valueAt(R, timeAt(R, t)); const x = pk && v != null ? v / pk[1] - 1 : null; return [pct(x), cls(x)]; } },
      { label: t => "London rent a month (" + monthOf(LR, t) + ")", value: t => [gbp(valueAt(LR, timeAt(LR, t)))] },
      { label: () => "Gross yield: a year's rent ÷ price", value: t => { const v = valueAt(GY, timeAt(GY, t)); return [v == null ? "–" : v.toFixed(1) + "%"]; } },
      { label: () => "London price ÷ UK average", value: t => { const v = valueAt(PR, timeAt(PR, t)); return [v == null ? "–" : v.toFixed(2) + "×"]; } }],
      { latest: "Latest: " + (n.avg ? monthOf(A, null) : "–") }), asOf(d), stale(d));
    const real = card("London average price: as paid, and in today's money",
      ...linesChart([{ name: "Average price", points: d.london_avg || [] }, { name: "In today's money (CPIH)", points: d.london_real || [], dashed: true, color: css("--hold") }], v => gbp(v)),
      missing(d, "london_real", "The inflation-adjusted line"), note("HM Land Registry UK House Price Index, all property types, London. The dashed line restates each month's price in the money of the latest CPIH month."));
    const idx = card("London vs the UK (index, January 2015 = 100)",
      ...linesChart([{ name: "London", points: d.london_index || [] }, { name: "United Kingdom", points: d.uk_index || [], color: css("--s2") }], v => num(v, 0)),
      missing(d, "uk_index", "The UK line"));
    const yoy = card("Change on a year earlier", ...linesChart([{ name: "London", points: d.london_yoy || [] }, { name: "United Kingdom", points: d.uk_yoy || [], color: css("--s2") }], v => pc(v), { small: true }),
      note("Percentage change in the average price against the same month a year earlier."));
    const rk = Object.entries(d.rents || {}).filter(([, p]) => p.length), r = d.rent_now || {};
    const rents = rk.length ? card("Average monthly private rent (ONS Price Index of Private Rents)",
      r.rent ? datedHead([
        { label: t => "London rent a month (" + monthOf(LR, t) + ")", value: t => [gbp(valueAt(LR, timeAt(LR, t)))] },
        { label: () => "Change on a year ago", value: t => { const RY = d.rent_yoy || []; const x = RY.length ? valueAt(RY, timeAt(RY, t)) : null; return x != null ? [pc(x), cls(x)] : (y => [pct(y), cls(y)])(chgAt(LR, t, 1)); } },
        { label: () => "Gross yield: a year's rent ÷ average price", value: t => { const v = valueAt(GY, timeAt(GY, t)); return [v == null ? "–" : v.toFixed(1) + "%"]; } }],
        { latest: "Latest: " + monthOf(LR, null) }) : null,
      ...linesChart(rk.map(([k, pts]) => ({ name: k, points: pts })), v => gbp(v), { small: true }),
      note("Average rent agreed on new and existing private tenancies, all property types (ONS PIPR, from January 2015). Rents against prices: a rising rent while prices are flat lifts the rental yield and usually comes before buyers return."))
      : card("Rents", el("div", { class: "muted" }, "Not available right now (" + (d.rents_error || "no data") + ")."));
    const rvp = card("Rents against prices in London (January 2015 = 100)",
      ...linesChart(Object.entries(d.rent_vs_price || {}).map(([k, pts], i) => i ? { name: k, points: pts, color: css("--s2") } : { name: k, points: pts }), v => v == null ? "–" : v.toFixed(0), { small: true }),
      missing(d, "rent_vs_price", "Rents against prices"),
      note("When the rent line climbs above the price line, renting has got dearer relative to buying (and landlords' yields have risen)."));
    const gy = card("Gross rental yield in London: a year's average rent ÷ average price (%)",
      ...linesChart([{ name: "Gross yield", points: GY }], v => v == null ? "–" : v.toFixed(2) + "%", { small: true }), missing(d, "gross_yield", "The yield"),
      note("Before costs, voids and tax. Average rent (all private tenancies) against the average price of all homes sold, so a broad gauge rather than any one flat's return."));
    const prem = card("London's premium: London average price ÷ UK average price",
      ...linesChart([{ name: "London ÷ UK", points: PR }], v => v == null ? "–" : v.toFixed(2) + "×", { small: true }), missing(d, "premium", "The premium"),
      note("How many average UK homes one average London home would buy. A falling line means the rest of the UK has been catching up."));
    return [head, real, idx, yoy, rents, rvp, gy, prem];
  },
  async market() {
    const d = await api("market"), n = d.now || {}, t = d.by_type || {}, ty = d.by_type_yoy || {};
    const V = d.volume || [], V12 = d.volume_12m || [];
    const head = card(null, datedHead([
      ...Object.entries(t).map(([k, pts]) => ({ label: tt => k + " · " + pct(chgAt(pts, tt, 1), 1) + " on a year", value: tt => [gbp(valueAt(pts, timeAt(pts, tt)))] })),
      { label: tt => "Sales in " + monthOf(V, tt), value: tt => [num(valueAt(V, timeAt(V, tt)))] },
      { label: tt => { const x = chgAt(V12, tt, 1); return "Sales, 12 months to " + monthOf(V12, tt) + (x == null ? "" : " · " + pct(x, 0) + " on the year before"); },
        value: tt => [num(valueAt(V12, timeAt(V12, tt)))] }],
      { latest: "Latest: " + monthOf(V, null) }), asOf(d), stale(d));
    const types = card("Average price by property type", ...linesChart(Object.entries(t).map(([k, pts]) => ({ name: k, points: pts })), v => gbp(v)), missing(d, "by_type"));
    const yoy = card("Change on a year earlier, by type", ...linesChart(Object.entries(ty).map(([k, pts]) => ({ name: k, points: pts })), v => pc(v), { small: true }));
    const vol = card("Sales volume (completed transactions registered)", ...linesChart([{ name: "Sales a month", points: d.volume || [] }, { name: "12-month total", points: d.volume_12m || [], axis: "left", dashed: true, color: css("--hold") }], v => num(v)),
      note("The most recent months are revised up as late registrations arrive: read the last two or three months as provisional."));
    return [head, types, yoy, vol];
  },
  async afford() {
    const d = await api("afford"), n = d.now || {};
    const PE = d.price_to_london_pay || d.price_to_earnings || [], LP = d.london_pay || [], BR = d.bank_rate || [], FX = d.fixed_2y || [], MG = d.mortgage || [];
    const rate = v => v == null ? "–" : v.toFixed(2) + "%";
    const head = card(null, datedHead([
      { label: () => "Bank Rate", value: t => [rate(valueAt(BR, t))] },
      { label: () => "2-year fixed, 75% LTV", value: t => [rate(valueAt(FX, t))] },
      { label: t => (n.pe_basis === "london" ? "Price to London pay" : "Price to UK pay") + " (" + monthOf(PE, t) + ")", value: t => { const v = valueAt(PE, timeAt(PE, t)); return [v == null ? "–" : v.toFixed(1) + "×"]; } },
      { label: () => "Highest ratio seen", value: () => [n.pe_peak == null ? "–" : n.pe_peak.toFixed(1) + "×"] },
      { label: t => { const T = timeAt(LP, t); return "London median full-time pay" + (T ? " (" + new Date(T * 1000).getUTCFullYear() + ")" : ""); }, value: t => [gbp(valueAt(LP, t))] },
      { label: () => "Illustrative mortgage a month", value: t => [gbp(valueAt(MG, timeAt(MG, t)))] }],
      { latest: "Latest figures" }), asOf(d), stale(d));
    const pe = card("London average price ÷ annual pay", ...linesChart([{ name: "÷ London median full-time pay", points: d.price_to_london_pay || [], width: 3 },
      { name: "÷ UK average regular pay (monthly trend)", points: d.price_to_earnings || [], dashed: true, color: css("--hold") }], v => v == null ? "–" : v.toFixed(1) + "×"),
      missing(d, "price_to_london_pay", "The London-pay ratio (ONS ASHE via Nomis)"), missing(d, "price_to_earnings", "The UK-pay trend"),
      note("Solid: median gross annual pay of full-time employees working in London (ONS Annual Survey of Hours and Earnings, each April, carried forward until the next survey), the basis ONS uses for its own affordability ratios. Dashed: UK average weekly regular pay × 52 (ONS KAB9), monthly but UK-wide, so higher; read it for the trend."));
    const br = card("Bank Rate and the quoted 2-year fixed mortgage rate (75% LTV)", ...linesChart([{ name: "Bank Rate", points: d.bank_rate || [] }, { name: "2-year fixed, 75% LTV", points: d.fixed_2y || [], color: css("--s2") }],
      v => v == null ? "–" : v.toFixed(2) + "%", { small: true }), missing(d, "bank_rate", "Bank Rate"), missing(d, "fixed_2y", "The quoted fixed rate (BoE IUMBV34)"));
    const mg = card("What a mortgage on the average London home would cost a month (illustration)",
      ...linesChart([{ name: "Monthly payment", points: d.mortgage || [] }, { name: d.london_pay ? "London median full-time pay ÷ 12" : "UK annual pay ÷ 12", points: (d.london_pay || d.earnings_annual || []).map(p => [p[0], p[1] / 12]), dashed: true, color: css("--hold") }], v => gbp(v)),
      missing(d, "mortgage", "The illustration"), note("75% of the average London price over 25 years, repayment, at " + (d.mortgage_basis || "the quoted fixed rate") + ". An illustration of how rates and prices combine, not a quote."));
    return [head, pe, br, mg];
  },
  async boroughs() {
    const d = await api("boroughs");
    let sortKey = "avg";
    const host = el("div", {});
    const draw = () => {
      const rows = [...d.rows].sort((a, b) => (b[sortKey] ?? -1e18) - (a[sortKey] ?? -1e18));
      const th = (k, l) => el("th", { style: "cursor:pointer", onclick: () => { sortKey = k; draw(); } }, l + (k === sortKey ? " ↓" : ""));
      host.replaceChildren(el("div", { class: "scroll" }, el("table", {}, el("tr", {}, el("th", {}, "Borough"), th("avg", "Average price"), th("flat", "Flat"), th("terraced", "Terraced house"),
        th("rent_2bed", "2-bed rent / month"), th("yoy", "Change on a year"), th("change_5y", "5 years")),
        ...rows.map(r => el("tr", {}, el("td", {}, r.borough), el("td", {}, gbp(r.avg)), el("td", {}, gbp(r.flat)), el("td", {}, gbp(r.terraced)), el("td", {}, gbp(r.rent_2bed)),
          el("td", { class: cls(r.yoy) }, pc(r.yoy)), el("td", { class: cls(r.change_5y) }, pct(r.change_5y, 0)))))));
    };
    draw();
    const ranked = [...d.rows].filter(r => r.yoy != null).sort((a, b) => b.yoy - a.yoy);
    const bars = ranked.length ? card("Change on a year, by borough (%)", ...svgBars(ranked.map(r => r.borough.replace(" and ", " & ").slice(0, 14)), [{ name: "Yearly change", values: ranked.map(r => r.yoy), colorFn: v => css(v >= 0 ? "--up" : "--down") }],
      { yFmt: v => v.toFixed(0) + "%", labelW: 70, catName: i => ranked[i].borough, h: 260 })) : null;
    const top = [...d.rows].slice(0, 3).map(r => r.borough), bottom = [...d.rows].slice(-3).map(r => r.borough);
    const lines = card("Most and least expensive boroughs, indexed (Jan 2015 = 100)", ...linesChart([...top, ...bottom].filter(b => d.indexed[b]).map(b => ({ name: b, points: d.indexed[b], dashed: bottom.includes(b) })), v => v == null ? "–" : v.toFixed(0)),
      note("Solid: the three most expensive; dashed: the three cheapest. Prime central London has lagged outer boroughs since 2015."));
    const errs = Object.keys(d.errors || {}).length ? note("Not available right now: " + Object.keys(d.errors).join(", ") + ".") : null;
    return [d.map ? boroughMap(d) : null, boroughPicks(d), card("London's 33 boroughs (UK HPI, " + (d.as_of || "–").slice(0, 7) + ")", el("div", { class: "muted" }, "Click a column to sort."), host, errs), bars, lines].filter(Boolean);
  },
  async calc() {
    const d = await api("calc");
    return calcView(d);
  },
  async global() {
    const d = await api("global");
    const series = [...(d.london ? [{ name: "London", points: d.london, width: 3 }] : []), ...Object.entries(d.us || {}).map(([k, pts]) => ({ name: k, points: pts })),
      ...(d.hk ? [{ name: "Hong Kong", points: d.hk, width: 3, color: css("--s5") }] : [])];
    const idx = card("House prices, Jan 2015 = 100", ...linesChart(series, v => v == null ? "–" : v.toFixed(0)),
      missing(d, "us", "US prices (FHFA)"), missing(d, "hk", "Hong Kong prices (RVD)"), stale(d),
      note("London: UK HPI index. US: FHFA house price indexes (national purchase-only, monthly; New York and San Francisco metro divisions, quarterly). Hong Kong: Rating and Valuation Department private domestic index. All rebased to January 2015."));
    const tbl = card("Latest", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Market", "Index (2015 = 100)", "Change on a year", "Month"].map(h => el("th", {}, h))),
      ...(d.table || []).map(r => el("tr", {}, el("td", {}, r.market), el("td", {}, r.index == null ? "–" : r.index.toFixed(0)), el("td", { class: cls(r.yoy) }, pct(r.yoy, 1)), el("td", {}, r.month))))));
    const rates = d.rates ? card("Borrowing costs: UK 2-year fixed, US 30-year fixed, HK 1-month HIBOR (%)", ...linesChart(Object.entries(d.rates).map(([k, pts]) => ({ name: k, points: pts })), v => v == null ? "–" : v.toFixed(2) + "%", { small: true }),
      Object.keys(d.rates_missing || {}).length ? el("div", { class: "muted" }, "Not available right now: " + Object.keys(d.rates_missing).join(", ") + ".") : null,
      note("Most Hong Kong mortgages float on HIBOR or prime, most US ones are fixed for 30 years, most UK ones are fixed for two to five years: the same move in policy rates reaches each market at a different speed.")) : card("Rates", el("div", { class: "muted" }, "Not available right now (" + (d.rates_error || "no data") + ")."));
    return [idx, tbl, rates];
  },
};
window.TOPIC = { VIEWS };
})();
