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
    return [head, imfCard, tbl, us, uk, card("IMF values entered by hand", ...handNote({ imf: d.imf_cites }))];
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
    const d = await api("odds"), m = d.meetings || [], next = m[0], ev = d.events || [], h = d.history || {};
    const days = next ? Math.round((new Date(next.date + "T19:00:00Z") - Date.now()) / 86400000) : null;
    const head = card(null, el("div", { class: "kpis" }, kpi("Fed funds, top of range", pc(d.fed_now, 2)),
      kpi("Next FOMC decision", next ? next.date + (days != null && days >= 0 ? " (" + (days === 0 ? "today" : "in " + days + " day" + (days === 1 ? "" : "s")) + ")" : "") : "–"),
      kpi("Meetings left this year", String(m.filter(x => x.date.slice(0, 4) === String(new Date().getUTCFullYear())).length))),
      el("div", { class: "muted", style: "margin-top:6px" }, "Odds updated " + (d.as_of || "–") + ". Polymarket prices are what traders pay for a $1 'Yes' share, so 0.62 reads as a 62% chance; they are bets, not forecasts from the Fed."), stale(d));
    const hist = Object.keys(h.lines || {}).length ? card("Polymarket: " + h.title + " (chance, %)",
      ...linesChart(Object.entries(h.lines).map(([k, pts], i) => ({ name: k, points: pts, color: css(SERIES[i % SERIES.length]) })), v => pc(v, 0), { sync: false, small: true }),
      note("Daily price of each outcome's Yes share since the market opened. A line jumping after a CPI release or a Fed speech shows what the market learned."),
      ask("Next meeting: is a cut priced in, or still a coin toss? Watch how the odds move after the CPI print on the Policy & CPI tab.")) : (d.history_error ? card("Polymarket odds history", missing(d, "history", "The odds history")) : null);
    const evCards = ev.map(e => card(e.title, el("div", { class: "scroll" }, el("table", {}, el("tr", {}, el("th", {}, "Outcome"), el("th", {}, "Chance"), el("th", {}, ""), el("th", {}, "Volume")),
      ...e.markets.slice().sort((a, b) => b.yes - a.yes).slice(0, 10).map(x => el("tr", {}, el("td", { class: "wrap" }, x.label || x.question), el("td", {}, pc(x.yes * 100, 0)),
        el("td", { style: "min-width:120px" }, el("div", { class: "bar" }, el("i", { style: "left:0;width:" + Math.round(x.yes * 100) + "%;background:var(--accent)" }))), el("td", {}, x.volume == null ? "–" : "$" + big(x.volume)))))),
      el("div", { class: "src", style: "margin-top:6px" }, "Closes " + (e.end || "–") + " · total volume " + (e.volume == null ? "–" : "$" + big(e.volume)) + " · ", link("polymarket.com/event/" + e.slug, "https://polymarket.com/event/" + e.slug))));
    const evNone = ev.length ? null : card("Polymarket odds", missing(d, "events", "Polymarket") || el("div", { class: "muted" }, "No open Fed-rate markets right now."));
    const meet = card("FOMC meetings ahead", m.length ? el("div", { class: "tl" }, ...m.flatMap(x => [el("div", { class: "d" }, x.date), el("div", {}, link(x.meeting, x.source), x.note ? el("span", { class: "muted" }, " (" + x.note + ")") : null)]))
      : el("div", { class: "muted" }, "No meetings entered: add next year's dates to data/debt-rates/fomc.csv."),
      note("Meetings marked (projections) publish the dot plot: each official's path for rates, the Fed's own forecast to set against the market's."));
    const dec = d.decisions || [];
    const decCard = dec.length ? card("Last FOMC decisions", el("div", { class: "tl" }, ...dec.slice(0, 8).flatMap(r => [el("div", { class: "d" }, r.date),
      el("div", { class: cls(-r.bp) }, (r.bp > 0 ? "Raised " : "Cut ") + Math.abs(r.bp) + " bp to " + pc(r.to, 2))]))) : null;
    return [head, hist, ...evCards, evNone, meet, decCard].filter(Boolean);
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
window.TOPIC = { VIEWS };
})();
