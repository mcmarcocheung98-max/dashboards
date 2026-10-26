// Global Debt & Rates: tabs and cards. Data from /api/debt-rates/<debt|interest|yields|policy|stress>; helpers from topic.html.
(() => {
const COL = { "US": "--s1", "UK": "--s2", "Hong Kong": "--s5", "China": "--s4" };
const col = k => css(COL[k] || "--hold");
const pc = (v, d = 1) => v == null ? "–" : Number(v).toFixed(d) + "%";
const sgn = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const bn = v => v == null ? "–" : "$" + num(v, 0) + "bn";
const tn = v => v == null ? "–" : "$" + Number(v).toFixed(2) + "tn";
const yr = ts => new Date(ts * 1000).getUTCFullYear();
const ask = s => el("div", { class: "muted", style: "margin-top:6px" }, el("b", { style: "color:var(--ink2)" }, "Questions: "), s);

// IMF yearly series: solid actual, dashed projection in the same colour
const imfLines = by => Object.entries(by || {}).flatMap(([k, v]) => [
  { name: k, points: v.actual || [], color: col(k) },
  { name: k + " (IMF projection)", points: v.proj || [], color: col(k), dashed: true }]).filter(s => s.points.length);
const lines = by => Object.entries(by || {}).map(([k, pts]) => ({ name: k, points: pts, color: COL[k] ? col(k) : undefined }));
const handNote = (cites) => {
  const rows = Object.values(cites || {}).flat();
  return rows.length ? [cite(rows), note("Hand-entered rows marked 'verify' in data/debt-rates/ were written from memory and are waiting to be checked against the cited page.")] : [];
};

const VIEWS = {
  async debt() {
    const d = await api("debt"), u = d.us_now || {}, t = d.table || [], Y = d.years || {};
    const head = card(null, el("div", { class: "kpis" },
      kpi("US federal debt (" + (u.date || "–") + ")", tn(u.total)), kpi("Added a day, last 12 months", u.per_day_bn == null ? "–" : "$" + u.per_day_bn.toFixed(1) + "bn"),
      ...t.map(r => kpi(r.country + ", debt % of GDP " + (Y.now || ""), pc(r.now, 0)))), asOf(d), stale(d));
    const imfCard = card("General government gross debt, % of GDP",
      ...linesChart(imfLines(d.imf), v => pc(v, 0), { extend: true, hlines: [100] }), missing(d, "imf", "IMF debt"),
      note("IMF World Economic Outlook, general government (all levels: federal, state, local), so the US figure is higher than federal debt held by the public. Dashed: IMF projections. imf.org refuses this server, so the page reads a copy of the IMF values (US and UK copied exactly; China and Hong Kong headline years entered by hand and marked verify; see data/debt-rates/imf.csv). Hong Kong's government has almost no debt; its fiscal reserves are larger than its borrowing. China's figure excludes local-government financing vehicles (the IMF's 'augmented' measure is far higher)."),
      ask("5 years: is anyone's debt ratio set to fall without a policy change? 10 years: who has added the most since 2015, and is it Covid or something structural? 20 years: since 2007 the US and UK have roughly doubled their ratios. Is 100% of GDP a ceiling markets enforce, or a line both have already crossed?"));
    const tbl = t.length ? card("Debt, % of GDP: before the crisis, before Covid, now, and in five years (IMF)",
      el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Country", "2007", "2019", String(Y.now || "Latest"), String(Y.proj5 || "+5 years") + " (proj.)", "Change, 10 years"].map(h => el("th", {}, h))),
        ...t.map(r => el("tr", {}, el("td", {}, r.country), el("td", {}, pc(r.y2007, 0)), el("td", {}, pc(r.y2019, 0)), el("td", {}, pc(r.now, 0)), el("td", {}, pc(r.proj5, 0)),
          el("td", { class: cls(-(r.change10 || 0)) }, sgn(r.change10, 0) + " pts"))))),
      note("A rising ratio in the right-hand column means deficits are projected to outrun nominal growth even before any shock.")) : null;
    const us = card("US federal debt outstanding, $ trillion (month-end)",
      ...linesChart([{ name: "Total public debt", points: d.us_total || [], color: col("US") }, { name: "Held by the public", points: d.us_public || [], dashed: true, color: css("--hold") }], v => tn(v), { small: true }),
      missing(d, "us_total", "Debt to the penny"),
      note("Treasury 'debt to the penny'. Held by the public excludes what the government owes its own trust funds (Social Security and others); it is what markets must absorb."),
      ask("5 years: does the dollar pace of borrowing slow after the pandemic years, or is it now set by interest itself? 10 and 20 years: debt was about $5.7tn in 2000. How much of each later trillion came from crises, and how much from the gap between taxes and entitlements?"));
    const uk = card("UK public sector net debt, % of GDP (monthly)",
      ...linesChart([{ name: "Net debt, ex public sector banks", points: d.uk_psnd || [], color: col("UK") }], v => pc(v, 1), { small: true, hlines: [100] }),
      missing(d, "uk_psnd", "ONS public sector net debt (HF6X)"),
      note("ONS series HF6X. Net debt (debt minus liquid assets) is the UK's headline measure, so it reads lower than the IMF's gross figure above."),
      ask("5 years: does debt peak below 100% of GDP, as the OBR's fiscal rules require? 10 years: how much of the rise since 2015 has been reversed? 20 years: debt was under 40% of GDP before 2008. Can it get back to pre-crisis levels in peacetime?"));
    const mt = d.maturity || {}, mn = mt.now || {};
    const mat = card("Short-term vs long-term: US marketable debt by maturity",
      el("div", { class: "kpis" }, kpi("Bills (1 year or less), " + (mn.month || ""), pc(mn.bills_share, 1) + " of marketable debt"), kpi("Bills outstanding", tn(mn.bills)), kpi("All marketable debt", tn(mn.marketable))),
      ...linesChart([{ name: "Bills share (%)", points: mt.bills_share || [], color: col("US") }], v => pc(v, 1), { small: true, hlines: [20] }),
      ...linesChart([{ name: "Bills ($tn)", points: mt.bills || [], color: col("US"), bar: false }, { name: "Notes, bonds, TIPS and FRNs ($tn)", points: mt.longer || [], color: css("--hold"), dashed: true }], v => tn(v), { small: true }),
      missing(d, "maturity", "The maturity mix (MSPD)"),
      (d.maturity_avg || []).length ? el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Country", "Measure", "Value", "As of"].map(x => el("th", {}, x))),
        ...d.maturity_avg.map(r => el("tr", {}, el("td", {}, r.country), el("td", { class: "wrap" }, link(r.measure, r.source)), el("td", { class: "wrap" }, r.value + (r.note ? " (" + r.note + ")" : "")), el("td", {}, r.date))))) : null,
      note("Monthly Statement of the Public Debt. Bills mature within a year, so a high bills share means the interest bill reprices quickly when the Fed moves, for better when it cuts, for worse when it hikes. The Treasury's advisers have long suggested keeping bills near 15-20% of the total (the dotted line). The UK borrows for much longer, which is why its interest bill rose more slowly in 2022-23 except for index-linked gilts."),
      ask("5 years: does the Treasury lean on bills to avoid locking in 5% long rates, and how exposed does that leave it to a hiking Fed? 10 years: the bills share jumped in 2020 and again in 2023-24. 20 years: in 2008 bills rose to over a third of the total; it fell back as the Treasury termed out. Will it again?"));
    return [head, imfCard, tbl, mat, us, uk, card("IMF values entered by hand", ...handNote({ imf: d.imf_cites }))];
  },

  async interest() {
    const d = await api("interest"), us = d.us || {}, r = us.rolling || {}, last = p => p && p.length ? p[p.length - 1][1] : null;
    const cross = us.cross || {}, cy = v => v == null ? "not yet" : v === "always" ? "throughout the data" : "FY" + v;
    const head = card(null, el("div", { class: "kpis" },
      kpi("US net interest, last 12 months", bn(last(r.interest))), kpi("US defence, last 12 months", bn(last(r.defence))),
      kpi("US interest, % of federal receipts", pc(last(us.share))), kpi("Interest above defence since", cy(cross.defence)),
      kpi("UK debt interest, % of receipts", pc(last(d.uk_share)))), asOf(d), stale(d));
    const usCard = card("US federal spending: net interest vs defence vs education, rolling 12 months ($bn)",
      ...linesChart([{ name: "Net interest", points: r.interest || [], color: css("--down"), width: 3 }, { name: "National defense", points: r.defence || [], color: col("US") },
        { name: "Education, training, employment, social services", points: r.education || [], color: css("--hold"), dashed: true }], v => bn(v)),
      missing(d, "us", "Monthly Treasury Statement"),
      note("Monthly Treasury Statement table 9, summed over the last 12 months. Federal education is small and noisy: it includes student-loan cost re-estimates and forgiveness, which can push it negative. Most US education is paid by states and school districts, which this federal series does not cover."),
      ask("5 years: net interest passed defence in the last few years. Does the gap close if yields fall, or keep widening as cheap 2020-21 debt is refinanced? 10 years: in 2015 interest was under half of defence. 20 years: CBO projects interest at about 4% of GDP by 2035, well above defence."));
    const ann = (us.annual || []).slice(-12);
    const bars = ann.length ? card("US fiscal years: net interest against defence ($bn)", ...svgBars(ann.map(a => "FY" + String(a.fy).slice(2)),
      [{ name: "Net interest", values: ann.map(a => a.interest), color: css("--down") }, { name: "National defense", values: ann.map(a => a.defence), color: col("US") }],
      { yFmt: v => "$" + num(v, 0), catName: i => "FY" + ann[i].fy }),
      note("US fiscal years end on 30 September. Each pair compares the two outlays in one year.")) : null;
    const share = card("Interest as a share of revenue: US federal and UK central government (rolling 12 months, %)",
      ...linesChart([{ name: "US: net interest ÷ federal receipts", points: us.share || [], color: col("US") }, { name: "UK: CG debt interest ÷ public sector receipts", points: d.uk_share || [], color: col("UK") }], v => pc(v)),
      missing(d, "uk_share", "UK interest share (ONS NMFX / ANBT)"),
      note("The share of each tax pound or dollar that goes to lenders before anything else is paid for. UK interest includes the RPI uplift on index-linked gilts, so it jumps when inflation does (2022-23)."),
      ask("5 years: does the share settle as inflation falls, or does refinancing at higher yields keep it rising? 10 years: both shares were near their lows in 2020-21, after rates had been near zero for a decade. 20 years: in the 1980s and 1990s US interest took about 15–18% of receipts. Is that where it is heading back to?"));
    const avg = card("Average interest rate on US marketable Treasury debt (%)",
      ...linesChart([{ name: "Average rate, all marketable debt", points: d.us_avg_rate || [], color: col("US") }], v => pc(v, 2), { small: true }),
      missing(d, "us_avg_rate", "Average interest rates (Fiscal Data)"),
      note("What the stock of debt actually costs. It moves slowly towards market yields as bills roll over and notes mature; the gap to the 10-year yield (Yields tab) shows how much repricing is still to come."),
      ask("5 years: how far below the 10-year yield is it, and how much higher does it go as notes mature? 10 and 20 years: it fell from about 6% in 2000 to under 2% in 2021. That fall is what made rising debt cheap."));
    const imfG = card("General government net interest, % of GDP (IMF)", ...linesChart(imfLines(d.imf_gdp), v => pc(v, 1), { extend: true, small: true, hlines: [0] }),
      missing(d, "imf_gdp", "IMF interest"),
      note("Net interest = primary balance minus overall balance (IMF WEO). Below zero: the government earns more on its assets than it pays on its debt, as Hong Kong does on its reserves."),
      ask("5 years: whose interest bill is projected to keep rising as a share of the economy? 10 years: which countries locked in low rates for long, and which borrowed short? 20 years: the US and UK were near 2% of GDP in 2007. How long until both are at twice that?"));
    const imfR = card("General government net interest, % of revenue (IMF)", ...linesChart(imfLines(d.imf_revenue), v => pc(v, 1), { extend: true, small: true, hlines: [10] }),
      missing(d, "imf_revenue", "IMF interest share"),
      note("Rating agencies watch this ratio: above about 10% of revenue, interest starts to crowd out other spending. China's figure covers the official budget only."),
      ask("5 years: who crosses 10%, and in which year? 10 and 20 years: who has the most room before markets push back? A low-tax country (US) reaches a given share sooner than a high-tax one (UK) carrying the same debt."));
    const H = d.hand || {}, unit = { UK: "£bn", "Hong Kong": "HK$bn", China: "CN¥bn" };
    const handCards = Object.entries(H).map(([c, items]) => card(c + ": interest vs defence vs education (" + (unit[c] || "bn") + ", fiscal years)",
      ...linesChart(Object.entries(items).map(([k, pts]) => ({ name: k, points: pts, dashed: k.includes("forecast"), color: k.startsWith("interest") ? css("--down") : k === "defence" ? col(c) : css("--hold") })),
        v => num(v, 0), { small: true }),
      note({ UK: "HM Treasury PESA outturns by function; the forecast is the OBR's debt interest. UK interest passed defence after 2021 and is now near the education budget.",
             "Hong Kong": "Hong Kong has no defence budget (the garrison is paid for by Beijing) and its bond interest is small next to education and next to the income on its reserves.",
             China: "Ministry of Finance general budget only. Interest on local special bonds and on financing-vehicle debt is outside it, so this understates the true interest bill." }[c] || ""),
      ask({ UK: "5 years: does debt interest overtake education, the second-largest service after health, before the end of the decade? 10 years: interest was a third of education in 2015-16. 20 years: what has to give if both defence (NATO's 3.5% target) and interest keep growing?",
            "Hong Kong": "5 years: do bond issues for the Northern Metropolis lift interest enough to matter? 10 and 20 years: the reserves fell after 2019. At what size would interest paid exceed the income they earn?",
            China: "5 years: does interest overtake defence? It is already about 70% of it. 10 years: how fast does central debt grow as Beijing takes on local debt? 20 years: what happens to rates if growth slows to the level of Japan's?" }[c] || "")));
    const cbo = d.cbo && Object.keys(d.cbo).length ? card("US projections: net interest vs defence, % of GDP (CBO)",
      ...linesChart(Object.entries(d.cbo).map(([k, pts]) => ({ name: k, points: pts, color: k.startsWith("Net") ? css("--down") : col("US"), dashed: true })), v => pc(v, 1), { extend: true, small: true }),
      note("CBO's baseline assumes current law, so there are no new tax cuts or spending beyond it. A 1-point rise in all rates adds roughly 0.5–1% of GDP to interest by the mid-2030s."),
      ask("5 years: interest already exceeds defence, so does the gap widen as CBO projects? 10 years: interest at about 4% of GDP would be the highest on record. 20 years: CBO's long-term outlook has interest above every discretionary category combined by the 2050s.")) : null;
    return [head, usCard, bars, share, avg, imfG, imfR, ...handCards, cbo, card("Hand-entered sources", ...handNote(d.cites))].filter(Boolean);
  },

  async yields() {
    const d = await api("yields"), n = d.now || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(n).map(([k, v]) => kpi(k + " 10-year (" + v.t + ")", pc(v.v, 2)))), asOf(d), stale(d));
    const nom = card("10-year government bond yields (%)", ...linesChart(lines(d.nominal), v => pc(v, 2)), missing(d, "nominal", "10-year yields"),
      Object.keys(d.missing || {}).length ? el("div", { class: "muted" }, "Not available right now: " + Object.entries(d.missing).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null,
      note("US: Treasury par yield curve, month-end. UK: Bank of England 10-year nominal gilt yield, month-end. Hong Kong: HKMA Exchange Fund Note 10-year yield to 2015 (copied from the HKMA API, which refuses this server), then HKGB 10-year yields (hand-entered). China: ChinaBond 10-year, year-end (hand-entered). Hong Kong's yield tracks the US because of the dollar peg; China's moves with its own deflation."),
      ask("5 years: are yields settling at a new range of 4–5% in the US and UK, or drifting back towards 2%? 10 years: the US–China gap reversed in 2022, so China now borrows more cheaply than the US. 20 years: the 1981–2020 bull market in bonds ended. What would it take to get 10-year yields under 2% again?"),
      ...handNote(d.cites));
    const real = card("Real 10-year yields: US TIPS and UK index-linked gilts (%)", ...linesChart(lines(d.real), v => pc(v, 2), { small: true, hlines: [0] }), missing(d, "real", "Real yields"),
      note("The yield after inflation that investors demand: the true cost of borrowing for a government whose tax base grows with inflation. UK index-linked yields are on RPI, which runs above CPI, so they read lower."),
      ask("5 years: real yields near 2% are the highest since before 2008. Can growth keep up? 10 years: they were negative from 2012 to 2021, when debt was close to free. 20 years: if real yields stay above real growth, debt ratios rise even with a balanced primary budget (see Stress)."));
    return [head, nom, real];
  },

  async policy() {
    const d = await api("policy"), n = d.now || {}, f = d.fed || {}, pb = d.pboc || {};
    const head = card(null, el("div", { class: "kpis" }, ...Object.entries(n).map(([k, v]) => kpi(k, pc(v, 2)))), stale(d));
    const all = card("Policy rates (%)", ...linesChart([{ name: "Fed funds (top of range)", points: f.upper || [], color: col("US") },
      { name: "Bank of England Bank Rate", points: d.boe || [], color: col("UK") }, { name: "HKMA base rate", points: d.hk || [], color: col("Hong Kong") },
      { name: "PBoC 7-day reverse repo", points: pb["7-day reverse repo"] || [], color: col("China") }, { name: "PBoC 1-year LPR", points: pb["1-year LPR"] || [], color: col("China"), dashed: true }],
      v => pc(v, 2)), missing(d, "fed", "Fed funds (NY Fed)"), missing(d, "boe", "Bank Rate"), missing(d, "hk", "HKMA base rate"),
      note("Fed: New York Fed (target range from 2016, earlier target changes hand-entered). HKMA base rate: the HKMA's formula from March 2009, the higher of the Fed range's lower end + 0.5 points and the average of overnight and 1-month HIBOR. The HKMA API refuses this server, so the line shows the Fed term, which has set the base rate since 2009. PBoC: hand-entered changes. The 7-day reverse repo has been its main policy rate since 2024; the LPR prices most loans."),
      ask("5 years: does the Fed cut faster than the BoE, and does Hong Kong (pegged to the dollar) get rate cuts that its property market needs while China eases for deflation? 10 years: in 2015 all four were near their lows. 20 years: policy rates set the floor under every government's borrowing cost, so how far apart can the US and China run?"),
      ...handNote(d.cites));
    const effr = f.effr && f.effr.length ? card("US: effective fed funds rate inside the target range (%)", ...linesChart([{ name: "Top of range", points: f.upper, color: col("US") },
      { name: "Bottom of range", points: f.lower || [], color: col("US"), dashed: true }, { name: "Effective rate (month-end)", points: f.effr, color: css("--hold") }], v => pc(v, 2), { small: true }),
      note("New York Fed. The effective rate sits inside the range. It drifting to the top was a sign of tight bank reserves in 2019, a risk again as the Fed shrinks its balance sheet.")) : null;
    const cn = d.cpi_now || {};
    const cpiCard = card("CPI inflation, year on year (%)",
      el("div", { class: "kpis" }, ...Object.entries(cn).map(([k, v]) => kpi(k + " CPI (" + v.t + ")", pc(v.v, 1)))),
      ...linesChart(lines(d.cpi), v => pc(v, 1), { hlines: [2] }), missing(d, "cpi", "CPI"),
      Object.keys(d.cpi_missing || {}).length ? el("div", { class: "muted" }, "Not available right now: " + Object.entries(d.cpi_missing).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null,
      note("US: CPI-U, all items, not seasonally adjusted, change on the same month a year earlier, read from Treasury's TIPS reference CPI (which equals BLS's index three months on; BLS refuses this server), from 2009. UK: ONS CPI annual rate (D7G7). Hong Kong: C&SD composite CPI. China: NBS, annual averages (hand-entered). The dashed line is the 2% target the Fed and the BoE aim for; the HKMA has no target (the peg imports US policy) and the PBoC's is about 2%."),
      ask("5 years: does inflation settle at 2%, or at 3% with rates held higher, which is what keeps interest bills rising? 10 years: China has been near zero since 2023 while the US and UK had their worst inflation since the 1980s. 20 years: inflation erodes debt, so does a government with debt above 100% of GDP quietly prefer 3%?"),
      ...handNote({ cn_cpi: (d.cites || {}).cn_cpi }));
    const realCard = card("Real policy rate: policy rate minus CPI inflation (points)", ...linesChart(lines(d.real), v => sgn(v, 2), { small: true, hlines: [0] }),
      missing(d, "real", "Real policy rates"),
      note("Below zero, central-bank money is cheaper than inflation, so policy is easy even when the rate looks high. China's line uses annual CPI, so it moves in steps."),
      ask("5 years: real rates above 1–2% squeeze borrowers, including governments rolling over debt. 10 years: they were negative almost everywhere from 2009 to 2022. 20 years: is the 2009–2021 era of negative real rates the exception or the rule?"));
    const dec = d.decisions || [];
    const decCard = dec.length ? card("FOMC rate decisions (change in the target or the top of the range)",
      el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Effective", "From", "To", "Change"].map(h => el("th", {}, h))),
        ...dec.slice(0, 20).map(r => el("tr", {}, el("td", {}, r.date), el("td", {}, pc(r.from, 2)), el("td", {}, pc(r.to, 2)), el("td", { class: cls(-r.bp) }, (r.bp > 0 ? "+" : "") + r.bp + " bp"))))),
      note("Computed from the target range (New York Fed from July 2000, the FOMC history before that). The date is when the new rate took effect, the day after the decision for a scheduled meeting. The latest 20 changes; the FOMC & odds tab lists the next meetings.")) : null;
    return [head, all, cpiCard, realCard, decCard, effr].filter(Boolean);
  },

  async odds() {
    const d = await api("odds"), m = d.meetings || [], next = m[0], ev = d.events || [], h = d.history || {}, ks = d.kalshi || [], F = d.fomc || {};
    const days = next ? Math.round((new Date(next.date + "T19:00:00Z") - Date.now()) / 86400000) : null;
    const head = card(null, el("div", { class: "kpis" }, kpi("Fed funds, top of range", pc(d.fed_now, 2)),
      kpi("Next FOMC decision", next ? next.date + (days != null && days >= 0 ? " (" + (days === 0 ? "today" : "in " + days + " day" + (days === 1 ? "" : "s")) + ")" : "") : "–"),
      kpi("Meetings left this year", String(m.filter(x => x.date.slice(0, 4) === String(new Date().getUTCFullYear())).length))),
      el("div", { class: "muted", style: "margin-top:6px" }, "Odds updated " + (d.as_of || "–") + ". Prediction-market prices are what traders pay for a contract that pays $1 if the outcome happens, so 0.62 reads as a 62% chance. They are bets, not forecasts from the Fed."), stale(d));
    // Polymarket vs Kalshi on the next decision: Kalshi's levels turned into a change from today's rate
    const pmNext = ev.filter(e => /fed decision/i.test(e.title)).sort((a, b) => (a.end || "").localeCompare(b.end || ""))[0];
    const kNext = ks[0];
    const word = bp => bp === 0 ? "No change" : (Math.abs(bp) >= 50 ? "50+ bps " : "25 bps ") + (bp > 0 ? "increase" : "decrease");
    let cmp = null;
    if (pmNext && kNext && d.fed_now != null) {
      const kb = {};
      kNext.levels.forEach(l => { const bp = Math.round((l.upper - d.fed_now) * 100); const w = word(Math.max(-50, Math.min(50, bp))); kb[w] = (kb[w] || 0) + l.p; });
      const pb = {}; pmNext.markets.forEach(x => { pb[x.label] = x.yes; });
      const keys = [...new Set([...Object.keys(pb), ...Object.keys(kb)])].filter(k => (pb[k] || 0) >= 0.005 || (kb[k] || 0) >= 0.005).sort((a, b) => ((pb[b] || 0) + (kb[b] || 0)) - ((pb[a] || 0) + (kb[a] || 0)));
      cmp = card("Next decision: Polymarket vs Kalshi", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Outcome", "Polymarket", "Kalshi", "Gap"].map(x => el("th", {}, x))),
        ...keys.map(k => el("tr", {}, el("td", {}, k), el("td", {}, pb[k] == null ? "–" : pc(pb[k] * 100, 1)), el("td", {}, kb[k] == null ? "–" : pc(kb[k] * 100, 1)),
          el("td", {}, pb[k] == null || kb[k] == null ? "–" : sgn((pb[k] - kb[k]) * 100, 1) + " pts"))))),
        el("div", { class: "src", style: "margin-top:6px" }, "Polymarket: " + pmNext.title + " ($" + big(pmNext.volume) + " traded). Kalshi: " + kNext.title + " ($" + big(kNext.volume) + " traded)."),
        note("Two markets pricing the same meeting. Kalshi lists 'upper bound above X%' contracts; the chance of each level is the difference between neighbouring strikes, set against today's " + pc(d.fed_now, 2) + " to read as hold, hike or cut. A gap of more than a few points is rare: traders close it by betting on the cheaper side."));
    }
    const hist = Object.keys(h.lines || {}).length ? card("Polymarket: " + h.title + " (chance, %)",
      ...linesChart(Object.entries(h.lines).map(([k, pts], i) => ({ name: k, points: pts, color: css(SERIES[i % SERIES.length]) })), v => pc(v, 0), { sync: false, small: true }),
      note("Daily price of each outcome since the market opened. A line jumping after a CPI release or a Fed speech shows what the market learned."),
      ask("Next meeting: is the move priced in, or still a coin toss? Watch how the odds move after the CPI print on the Interest rates & CPI tab.")) : (d.history_error ? card("Polymarket odds history", missing(d, "history", "The odds history")) : null);
    const kCards = ks.map(e => ({ ...e, levels: e.levels.filter(l => l.p >= 0.01) })).map(e => card("Kalshi: " + e.title, ...svgBars(e.levels.map(l => l.label.replace(" or lower", "↓").replace("above ", ">")), [{ name: "Chance", values: e.levels.map(l => l.p * 100), color: css("--s4") }],
      { yFmt: v => v.toFixed(0) + "%", h: 180, labelW: 48, catName: i => "Upper bound " + e.levels[i].label }),
      el("div", { class: "src", style: "margin-top:6px" }, "Closes " + (e.close || "–") + " · $" + big(e.volume) + " traded · ", link("kalshi.com/markets/kxfed", "https://kalshi.com/markets/kxfed"))));
    const kNone = ks.length ? null : card("Kalshi odds", missing(d, "kalshi", "Kalshi") || el("div", { class: "muted" }, "No open Kalshi Fed markets right now."));
    const evCards = ev.map(e => card("Polymarket: " + e.title, el("div", { class: "scroll" }, el("table", {}, el("tr", {}, el("th", {}, "Outcome"), el("th", {}, "Chance"), el("th", {}, ""), el("th", {}, "Volume")),
      ...e.markets.slice().sort((a, b) => b.yes - a.yes).slice(0, 10).map(x => el("tr", {}, el("td", { class: "wrap" }, x.label || x.question), el("td", {}, pc(x.yes * 100, 0)),
        el("td", { style: "min-width:120px" }, el("div", { class: "bar" }, el("i", { style: "left:0;width:" + Math.round(x.yes * 100) + "%;background:var(--accent)" }))), el("td", {}, x.volume == null ? "–" : "$" + big(x.volume)))))),
      el("div", { class: "src", style: "margin-top:6px" }, "Closes " + (e.end || "–") + " · total volume " + (e.volume == null ? "–" : "$" + big(e.volume)) + " · ", link("polymarket.com/event/" + e.slug, "https://polymarket.com/event/" + e.slug))));
    const evNone = ev.length ? null : card("Polymarket odds", missing(d, "events", "Polymarket") || el("div", { class: "muted" }, "No open Fed-rate markets right now."));
    const meet = card("FOMC meetings ahead", m.length ? el("div", { class: "tl" }, ...m.flatMap(x => [el("div", { class: "d" }, x.date), el("div", {}, link(x.meeting, x.source), x.note ? el("span", { class: "muted" }, " (" + x.note + ")") : null)]))
      : el("div", { class: "muted" }, "No meetings entered: add next year's dates to data/debt-rates/fomc.csv."),
      note("Meetings marked (projections) publish the dot plot: each official's path for rates, the Fed's own forecast to set against the market's."));
    // 20 years of FOMC decisions: insights, cycles, and each decision with what was happening
    const ins = F.insights || [];
    const insCard = ins.length ? card("What 20 years of FOMC decisions show" + (F.since ? " (since " + F.since.slice(0, 4) + ")" : ""),
      el("ul", { style: "margin:0;padding-left:18px;line-height:1.6" }, ...ins.map(t => el("li", {}, t))),
      note("Computed from the Fed's target history, the Treasury 10-year yield and CPI each time the page refreshes; only the wording is fixed.")) : missing(d, "fomc", "The FOMC history");
    const cyc = F.cycles || [];
    const cycCard = cyc.length ? card("Rate cycles", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Cycle", "From", "To", "Moves", "Total", "Months", "Largest", "Off-meeting", "10y during", "10y a year on", "What drove it"].map(x => el("th", {}, x))),
      ...cyc.map(c => el("tr", {}, el("td", { class: c.direction === "hiking" ? "down" : "up" }, (c.direction === "hiking" ? "Hiking " : "Cutting ") + c.start.slice(0, 7) + " – " + c.end.slice(0, 7)),
        el("td", {}, pc(c.from, 2)), el("td", {}, pc(c.to, 2)), el("td", {}, String(c.moves)), el("td", {}, (c.bp > 0 ? "+" : "") + c.bp + " bp"), el("td", {}, String(c.months)),
        el("td", {}, (c.largest > 0 ? "+" : "") + c.largest + " bp"), el("td", {}, c.emergency ? String(c.emergency) : "–"),
        el("td", {}, c.y10_during == null ? "–" : sgn(c.y10_during, 0) + " bp"), el("td", {}, c.y10_year == null ? "–" : sgn(c.y10_year, 0) + " bp"),
        el("td", { class: "wrap" }, (c.context || []).join(" ")))))),
      note("A cycle is a run of moves in one direction; a pause of more than 18 months starts a new one. '10y during' is the change in the 10-year Treasury yield from the day before the first move to the last; '10y a year on' is a year after the first move."),
      ask("5 years: is the 2026 hike the start of a new hiking cycle or a one-off? 10 years: the 2019 'insurance' cuts were small and short; the 2020 cuts were crisis cuts. 20 years: every cutting cycle since 2007 began with an outside shock. What would the next one be?")) : null;
    const dec = F.decisions || [];
    const decCard = dec.length ? card("Every FOMC decision of the last 20 years, and what was happening", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Effective", "Move", "Target (top)", "10y yield", "US CPI", "Context"].map(x => el("th", {}, x))),
      ...dec.map(r => el("tr", {}, el("td", {}, r.date + (r.emergency ? " ⚡" : "")), el("td", { class: cls(-r.bp) }, (r.bp > 0 ? "+" : "") + r.bp + " bp"), el("td", {}, pc(r.to, 2)),
        el("td", {}, pc(r.y10, 2)), el("td", {}, pc(r.cpi, 1)),
        el("td", { class: "wrap" }, ...(r.events || []).flatMap((e, i) => [i ? " " : "", link(e.event, e.source), e.note ? el("span", { class: "muted" }, " (" + e.note + ")") : null])))))),
      note("⚡ = moved between scheduled meetings. Dates are when the new rate took effect. The 10-year yield and US CPI are the latest readings on that date (CPI from 2009). Context comes from data/debt-rates/fomc_events.csv: events up to 45 days before each decision, each linked to its source."),
      ...handNote({ fomc_events: (d.cites || {}).fomc_events })) : null;
    return [head, cmp, hist, ...kCards, kNone, ...evCards, evNone, meet, insCard, cycCard, decCard].filter(Boolean);
  },

  async qe() {
    const d = await api("qe"), h = d.holdings || {}, b = d.buybacks || {}, pr = d.programmes || [];
    const last = p => p && p.length ? p[p.length - 1][1] : null;
    const head = card(null, el("div", { class: "kpis" }, kpi("Fed holdings of Treasuries", tn(last(h.treasuries))), kpi("Fed holdings of MBS", tn(last(h.mbs))),
      kpi("Fed share of marketable Treasuries", pc(last(d.share), 1)), kpi("Treasury buybacks since " + (b.first || "2024").slice(0, 7), b.total == null ? "–" : "$" + num(b.total, 0) + "bn")), stale(d));
    const hold = card("What the Fed owns: Treasuries and mortgage-backed securities ($ trillion, weekly)",
      ...linesChart([{ name: "Treasuries", points: h.treasuries || [], color: col("US") }, { name: "Mortgage-backed securities", points: h.mbs || [], color: css("--s2") },
        { name: "of which bills", points: h.bills || [], color: css("--hold"), dashed: true }], v => tn(v)), missing(d, "holdings", "SOMA holdings"),
      note("New York Fed, System Open Market Account. Holdings rise when the Fed buys bonds (QE) and fall when it lets them mature without replacing them (QT). The bills line shows the 2019 and 2025 'reserve management' purchases, which were short bills, not long bonds."),
      ask("5 years: does the Fed's bill buying since QT ended grow into another QE if markets wobble? 10 years: holdings went from about $2.5tn to $5.7tn in 2020-22. 20 years: before 2008 the Fed held under $0.8tn. Is a big balance sheet now permanent?"));
    const sh = card("Fed share of marketable Treasury debt (%)", ...linesChart([{ name: "Fed holdings ÷ marketable Treasuries", points: d.share || [], color: col("US") }], v => pc(v, 1), { small: true }),
      missing(d, "share", "The Fed's share"),
      note("SOMA Treasuries ÷ total marketable Treasury debt (Monthly Statement of the Public Debt). When the share falls, private buyers (banks, foreigners, funds) must absorb more of every new bond, one reason long yields rose during QT."),
      ask("5 years: who replaces the Fed as buyer of a growing debt stock? 10 years: the share peaked near a quarter in 2021-22. 20 years: a Fed that owns a large share keeps interest costs down (it hands its profits back to the Treasury), but only while it is buying."));
    const avgY = pr.filter(r => r.kind === "Buy" && r.y10_change_bp != null), avgS = pr.filter(r => r.kind === "Shrink" && r.y10_change_bp != null);
    const progCard = pr.length ? card("Fed buying and shrinking programmes", el("div", { class: "scroll" }, el("table", {},
      el("tr", {}, ...["Programme", "From", "To", "Kind", "What", "Fed holdings change", "10y change"].map(x => el("th", {}, x))),
      ...pr.map(r => el("tr", {}, el("td", {}, link(r.name, r.source)), el("td", {}, r.date), el("td", {}, r.end || "running"), el("td", {}, r.kind), el("td", { class: "wrap" }, r.what + (r.note ? " (" + r.note + ")" : "")),
        el("td", {}, r.fed_change_tn == null ? "–" : sgn(r.fed_change_tn, 2) + " tn"), el("td", {}, r.y10_change_bp == null ? "–" : sgn(r.y10_change_bp, 0) + " bp"))))),
      el("ul", { style: "margin:8px 0 0;padding-left:18px;line-height:1.6" },
        avgY.length ? el("li", {}, "The 10-year yield rose during " + avgY.filter(r => r.y10_change_bp > 0).length + " of " + avgY.length + " buying programmes: buying was announced into weak economies and yields often rose as the economy recovered. The effect shows at the announcement, not over the programme.") : null,
        avgS.length ? el("li", {}, "During " + avgS.length + " shrinking programme" + (avgS.length > 1 ? "s" : "") + " the 10-year moved " + avgS.map(r => r.name + " " + sgn(r.y10_change_bp, 0) + " bp").join(", ") + ".") : null,
        el("li", {}, "QT ended twice when money markets ran short of reserves (September 2019, late 2025): how far the Fed can shrink is set by the banks' need for cash, not by a target size.")),
      note("Fed holdings change uses the SOMA data (it starts later than the early programmes, so they show –). Programme dates are hand-entered from Fed statements; rows marked verify are from memory."),
      ...handNote(d.cites)) : null;
    const mon = b.monthly || {};
    const bbCard = Object.keys(mon).length ? card("Treasury buybacks: the Treasury buying back its own bonds ($bn a month)",
      el("div", { class: "kpis" }, ...Object.entries(b.by_type || {}).map(([k, v]) => kpi(k + ", total", "$" + num(v, 0) + "bn")), kpi("Operations", String(b.ops || "–"))),
      ...linesChart(Object.entries(mon).map(([k, pts], i) => ({ name: k, points: pts, bar: true, color: css(i ? "--s2" : "--s1") })), v => v == null ? "–" : "$" + num(v, 1) + "bn", { small: true }),
      b.past && b.past.ops ? el("div", { class: "muted", style: "margin-top:6px" }, "Earlier: " + b.past.ops + " buybacks from " + b.past.from + " to " + b.past.to + ", $" + num(b.past.total, 0) + "bn, which retired debt out of the budget surpluses of the late 1990s.") : null,
      (b.next || []).length ? el("div", { class: "muted", style: "margin-top:6px" }, "Next: " + b.next.map(x => x.date + " " + x.type + " (" + x.security + ", " + x.bucket + ")").join("; ") + ".") : null,
      note("Fiscal Data, Treasury buyback operations. Not the Fed: the Treasury buys old, less-traded bonds and pays with new issues. 'Liquidity support' keeps older bonds tradable; 'cash management' smooths the Treasury's cash around tax dates. Neither shrinks the debt."),
      ask("5 years: do buybacks grow into a tool to steady the long end when auctions tail? 10 years: the US last ran buybacks in 2000-02, to retire debt from surpluses. 20 years: today's buybacks swap old debt for new, the opposite purpose.")) : card("Treasury buybacks", missing(d, "buybacks", "Treasury buybacks") || el("div", { class: "muted" }, "No buyback data."));
    return [head, hold, sh, progCard, bbCard];
  },

  async stress() {
    const d = await api("stress"), s = d.score || [], Y = d.years || {};
    const top = s.find(r => r.gap != null);
    const answer = card("Who hits fiscal stress first?", top ? el("div", {}, el("b", {}, top.country), " has the widest gap between the primary balance that would hold its debt ratio steady (" + pc(top.pb_star, 1) +
      " of GDP) and the IMF's projected primary balance (" + pc(top.pb, 1) + "): its debt ratio rises by about " + Math.max(0, top.gap).toFixed(1) + " points of GDP a year on current plans, with interest at " + pc(top.int_rev, 0) +
      " of revenue going to " + pc(top.int_rev5, 0) + " by " + (Y.proj5 || "five years") + ".") : el("div", { class: "muted" }, "Not available right now."),
      el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Country", "Debt % GDP", "In 5 yrs", "Interest % revenue", "In 5 yrs", "10y yield r", "Nominal growth g", "r − g", "Primary balance needed", "IMF primary balance", "Gap"].map(h => el("th", {}, h))),
        ...s.map(r => el("tr", {}, el("td", {}, r.country), el("td", {}, pc(r.debt, 0)), el("td", {}, pc(r.debt5, 0)), el("td", {}, pc(r.int_rev, 1)), el("td", {}, pc(r.int_rev5, 1)),
          el("td", {}, pc(r.r, 2)), el("td", {}, pc(r.g, 1)), el("td", { class: cls(-(r.r_g || 0)) }, sgn(r.r_g, 2)), el("td", {}, pc(r.pb_star, 1)), el("td", {}, pc(r.pb, 1)),
          el("td", { class: cls(-(r.gap || 0)), style: tint(r.gap == null ? null : -r.gap, 3) }, sgn(r.gap, 1)))))),
      missing(d, "score", "The scorecard"),
      note("Debt dynamics: debt/GDP rises when the interest rate r exceeds nominal growth g, unless the government runs a primary surplus of d × (r − g) / (1 + g). r = today's 10-year yield (the marginal cost of new borrowing); g = IMF real growth plus inflation, averaged over the next five years; primary balance = the IMF's projection, same years. Gap = needed minus projected; positive means debt keeps rising. Hong Kong's net asset position and China's off-budget debt make their rows less meaningful than the US and UK."),
      ask("5 years: whose gap is positive and widening? That country needs a tax rise, spending cuts or lower yields first. 10 years: r − g was deeply negative in 2010–21, which let debt rise painlessly. 20 years: a lasting positive r − g would end that."));
    const spread = card("10-year yield minus policy rate (points): a term-premium proxy", ...linesChart(lines(d.spread), v => sgn(v, 2), { hlines: [0] }), missing(d, "spread", "Spreads"),
      note("Long yields above the policy rate mean investors want extra pay to lend for ten years rather than roll short loans. A rising gap while central banks cut is the classic sign of fiscal worry, as in the US and UK in late 2024 and 2025. This is a rough proxy; the Fed's ACM and Kim-Wright models estimate the term premium properly."),
      ask("5 years: does the gap stay positive as policy rates fall? If so, markets are charging for supply and inflation risk. 10 years: it was deeply negative in 2023 when policy rates were above 10-year yields. 20 years: for most of 1990–2007 the US gap was 1–2 points. Is that the normal to return to?"));
    const slope = card("US yield curve: 10-year minus 2-year (points)", ...linesChart([{ name: "10y − 2y", points: d.us_slope || [], color: col("US") }], v => sgn(v, 2), { small: true, hlines: [0] }),
      missing(d, "us_slope", "The US curve"),
      note("Treasury par curve, month-end. The longest inversion on record (2022–24) has ended; a steepening led by the long end, rather than by rate cuts, points to fiscal pressure."),
      ask("5 years: is the steepening 'bull' (cuts) or 'bear' (long yields rising)? 10 and 20 years: inversions came before the 2001, 2008 and 2020 recessions."));
    const ev = card("Auction tails, downgrades and market stress (notes)", el("div", { class: "tl" }, ...(d.events || []).flatMap(e => [el("div", { class: "d" }, e.date + " · " + e.country),
      el("div", {}, link(e.event, e.source), e.note ? el("span", { class: "muted" }, " (" + e.note + ")") : null)])),
      note("An auction 'tails' when it clears at a higher yield than the market traded just before it (the when-issued yield). The tail is the size of that gap and a sign that buyers had to be paid more. Treasury publishes results at TreasuryDirect but not the when-issued yield, so tails are listed here as notes, not computed."),
      ask("Do the notes cluster? Several tails and downgrades within months of each other, before a budget, is the pattern to watch."));
    return [answer, spread, slope, ev];
  },
};
// "What each number means": one plain-language entry per metric on each tab, folded under its card
const GLOSS = {
  policy: [["Fed funds target range", "The range the Fed sets for overnight lending between banks; the top of the range is quoted here. Every US borrowing rate is priced off it."],
    ["Effective fed funds rate (EFFR)", "The volume-weighted rate banks actually paid overnight, published daily by the New York Fed. It sits inside the target range."],
    ["Bank Rate", "The Bank of England's policy rate, paid on reserves banks hold at the Bank."],
    ["HKMA base rate", "The rate for Hong Kong's discount window. Because the Hong Kong dollar is pegged to the US dollar, it follows the Fed: the lower end of the Fed range plus 0.5 points, or a HIBOR average if higher."],
    ["PBoC 7-day reverse repo; 1-year LPR", "China's main policy rate since 2024 is the 7-day reverse repo rate. The loan prime rate (LPR) is the benchmark most bank loans are priced from."],
    ["CPI inflation, year on year", "The change in consumer prices from the same month a year earlier. The Fed and the BoE aim for 2%."],
    ["Real policy rate", "Policy rate minus CPI inflation. Positive means money costs more than prices rise, so policy is restrictive; negative means it is easy."],
    ["FOMC rate decisions", "Each change in the Fed's target, computed from the target history. 1 basis point (bp) = 0.01 percentage point."]],
  odds: [["Prediction-market probability", "The price of a contract that pays $1 if something happens: a price of 0.62 means traders as a group put the chance at about 62%."],
    ["Polymarket", "A crypto-based prediction market; each outcome is a Yes share. Its volume is the dollar value traded since the market opened."],
    ["Kalshi", "A US exchange regulated by the CFTC. Its Fed markets ask 'will the upper bound be above X% after the meeting?'; the chance of each exact level is the difference between neighbouring strikes."],
    ["Gap between markets", "The difference between the two markets' chances for the same outcome. Large gaps are rare because traders profit by closing them."],
    ["Rate cycle", "A run of FOMC moves in one direction; a pause of more than 18 months starts a new cycle."],
    ["Off-meeting (emergency) move", "A change made between the eight scheduled meetings, so far always a cut in a crisis (2008, 2020)."],
    ["10y during / a year on", "How much the 10-year Treasury yield moved over the cycle and in the year after its first move: whether long-term borrowing costs followed the Fed."],
    ["Dot plot", "Each FOMC member's forecast of the rate path, published at four meetings a year (marked 'projections')."]],
  debt: [["General government gross debt, % of GDP", "Everything every level of government owes (federal, state, local) as a share of a year's output. The IMF's standard cross-country measure."],
    ["IMF projection", "The IMF's forecast in its latest World Economic Outlook (dashed lines), assuming current policies."],
    ["Total public debt / held by the public", "US federal debt to the penny. 'Held by the public' leaves out what the government owes its own trust funds (such as Social Security): it is the part markets must buy."],
    ["Public sector net debt (UK)", "UK public sector debt minus its liquid assets, as a share of GDP: the measure the UK's fiscal rules use."],
    ["Bills share", "Treasury bills (maturing within a year) as a share of all marketable Treasury debt. A high share means the interest bill reprices quickly."],
    ["Notes, bonds, TIPS, FRNs", "Longer-term Treasuries: notes (2-10 years), bonds (20-30 years), inflation-protected TIPS and floating-rate notes."],
    ["Average maturity", "How long, on average, until the debt must be repaid or refinanced. Longer maturity means interest costs adjust more slowly to rate changes."]],
  interest: [["Net interest", "Interest the government pays on its debt minus interest it earns on its assets."],
    ["Interest as a share of revenue", "Net interest ÷ tax and other revenue: how much of each dollar or pound collected goes to lenders first. Above about 10% rating agencies take note."],
    ["Interest as a share of GDP", "Net interest ÷ the economy's annual output: the interest bill's size against the tax base."],
    ["Monthly Treasury Statement (MTS)", "The US Treasury's monthly receipts and outlays by function (defence, education, net interest...). Shown as rolling 12-month totals."],
    ["Average rate on marketable debt", "The average coupon the Treasury pays across all its marketable debt. It lags market yields as old debt is refinanced."],
    ["CBO baseline", "The Congressional Budget Office's 10-year projection, assuming current law."],
    ["PESA", "HM Treasury's Public Expenditure Statistical Analyses: UK spending by function."]],
  yields: [["10-year yield", "The annual return on a 10-year government bond bought today and held to maturity: the market's price for lending to the government for a decade."],
    ["Real yield (TIPS, index-linked gilts)", "The yield on inflation-protected bonds: the return after inflation. It is the true cost of borrowing for a government whose tax base grows with prices."],
    ["Par yield", "The yield of a bond priced at 100 on the Treasury's fitted curve; the standard published curve."],
    ["Exchange Fund Notes / HKGB", "Hong Kong's government paper: Exchange Fund Notes to 2015, Government Bonds after."],
    ["ChinaBond 10-year", "The benchmark yield on Chinese government bonds, from China Central Depository & Clearing."]],
  qe: [["SOMA", "The System Open Market Account: the bonds the Federal Reserve owns, reported weekly by the New York Fed."],
    ["QE (quantitative easing)", "The Fed creates reserves to buy Treasuries and mortgage-backed securities, pushing long-term yields down when policy rates are already near zero."],
    ["QT (quantitative tightening)", "The reverse: the Fed lets bonds mature without reinvesting, shrinking its holdings and draining reserves."],
    ["Operation Twist", "Selling short-dated Treasuries to buy long-dated ones (2011-12): lower long yields without a bigger balance sheet."],
    ["Reserve management purchases", "Buying Treasury bills to keep bank reserves ample. A plumbing operation, not QE."],
    ["Fed share of marketable Treasuries", "Fed Treasury holdings ÷ all marketable Treasury debt: how much of the government's debt the central bank holds."],
    ["Treasury buybacks", "The Treasury itself (not the Fed) buying back older bonds, paid for with new issues. 'Liquidity support' keeps old bonds tradable; 'cash management' smooths cash around tax dates."],
    ["MBS", "Mortgage-backed securities guaranteed by Fannie Mae, Freddie Mac or Ginnie Mae."]],
  stress: [["r", "The interest rate on new borrowing, here today's 10-year yield."],
    ["g", "Nominal GDP growth: real growth plus inflation (IMF projections, average of the next five years)."],
    ["r − g", "When positive, interest compounds faster than the economy grows, so debt rises as a share of GDP unless the budget runs a surplus before interest."],
    ["Primary balance", "The budget balance before interest payments, % of GDP. A surplus means taxes cover everything except interest."],
    ["Debt-stabilising primary balance", "The primary balance that would hold debt/GDP steady: debt × (r − g) ÷ (1 + g)."],
    ["Gap", "Debt-stabilising primary balance minus the IMF's projection, in points of GDP. Positive: debt keeps rising on current plans."],
    ["Term-premium proxy", "10-year yield minus the policy rate: what investors demand to lend for ten years rather than roll short loans."],
    ["10y − 2y", "The slope of the yield curve. Negative (inverted) curves have preceded US recessions."],
    ["Auction tail", "How far a Treasury auction's yield clears above the yield traded just before it. A large tail means buyers had to be paid more."]],
};
const explain = k => GLOSS[k] ? el("details", { class: "card" }, el("summary", { style: "cursor:pointer;font-weight:650" }, "What each number on this tab means"),
  el("dl", { style: "margin:10px 0 0" }, ...GLOSS[k].flatMap(([t, x]) => [el("dt", { style: "font-weight:600;margin-top:8px" }, t), el("dd", { style: "margin:2px 0 0;color:var(--ink2)" }, x)]))) : null;
for (const k of Object.keys(VIEWS)) { const f = VIEWS[k]; VIEWS[k] = async () => [].concat(await f()).concat([explain(k)]).filter(Boolean); }
window.TOPIC = { VIEWS };
})();
