// AI: Jobs & Adoption. Tabs and cards for /ai; data from /api/ai/<openings|headcount|wages|ratio|firms|users|agents|skills>.
(() => {
let cc = "US", wide = false, lyear = null, lmode = "jobs", akind = null;
const AI = ["Software Development", "Data & Analytics"], PRO = ["Legal", "Banking & Finance", "Accounting", "Insurance"];
const COL = { "Software Development": "--s1", "Data & Analytics": "--s6", "Legal": "--s2", "Banking & Finance": "--s3", "Accounting": "--s4", "Insurance": "--s5" };
const seg = rerender => el("div", { class: "seg" }, ...[["US", "United States"], ["GB", "United Kingdom"]].map(([k, l]) => el("button", { class: k === cc ? "on" : "", onclick: () => { cc = k; rerender(); } }, l)));
const i1 = v => v == null ? "–" : v.toFixed(0);
const sh = v => v == null ? "–" : v.toFixed(1) + "%";
// Top cards follow the date hovered or clicked on any chart (followHead from topic.html); a delta is the change on a year in points
const ppY = { lag: "1y", abs: true, fmt: v => pp(v) };
// followHead when any figure has a series to follow; otherwise the latest figures as plain kpis (nothing on the charts to hover)
const followOr = (items, opts) => items.some(it => (it.points || []).length) ? followHead(items, opts)
  : el("div", { class: "kpis" }, ...items.map(it => kpi(it.label, "–")));
// Columns of figures stay right-aligned (the page default); columns of text are left-aligned, header included.
const isFig = v => v == null || /^\s*([–-]|[$£+−-]*\s*[\d.,]+\s*(%|[mkb]n?|pts?)?)\s*$/i.test(String(v));
const table = (cols, rows) => {
  const text = cols.map((_, i) => i > 0 && rows.some(r => !isFig(r[i])));
  return el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map((h, i) => el("th", text[i] ? { style: "text-align:left" } : {}, h))),
    ...rows.map(r => el("tr", {}, ...r.map((v, i) => { const s = String(v ?? ""), m = s.match(/^\[([^\]]+)\]\(([^)]+)\)(.*)$/); return el("td", { class: text[i] ? "wrap" : "" }, ...(m ? [link(m[1], m[2]), m[3]] : [s])); })))));
};
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
// London heatmap (ONS BRES): boroughs x sectors for one year; shade = employees within each sector's column, or the change in green / red
function londonHeat(L) {
  const box = el("div");
  const yrs = L.years, base = yrs.indexOf(2019);
  const draw = () => {
    const yi = lyear == null || !yrs.includes(lyear) ? yrs.length - 1 : yrs.indexOf(lyear);
    const prev = lmode === "yoy" ? yi - 1 : lmode === "since" ? base : null;
    const pill = (on, label, fn) => el("button", { class: on ? "on" : "", onclick: fn }, label);
    const ctl = el("div", { style: "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px" },
      el("div", { class: "seg" }, ...yrs.map((y, i) => pill(i === yi, String(y), () => { lyear = y; draw(); }))),
      el("div", { class: "seg" }, pill(lmode === "jobs", "Employees", () => { lmode = "jobs"; draw(); }),
        pill(lmode === "yoy", "Change on a year", () => { lmode = "yoy"; draw(); }), ...(base >= 0 ? [pill(lmode === "since", "Change since 2019", () => { lmode = "since"; draw(); })] : [])));
    const colMax = Object.fromEntries(L.sectors.map(sec => [sec, Math.max(1, ...L.boroughs.map(b => L.values[b][sec][yi] || 0))]));
    const cell = (b, sec) => {
      const v = L.values[b][sec][yi], w = prev != null && prev >= 0 ? L.values[b][sec][prev] : null;
      if (v == null) return el("td", { class: "muted", title: "suppressed or not published" }, "–");
      if (lmode === "jobs") {
        const a = Math.round(8 + 72 * Math.sqrt(v / colMax[sec]));
        return el("td", { style: `background:color-mix(in srgb, var(--s1) ${a}%, transparent)`, title: `${b} · ${sec} · ${yrs[yi]}: ${num(v)} employees` }, big(v));
      }
      if (!w) return el("td", { class: "muted" }, "–");
      const ch = v / w - 1, a = Math.round(Math.min(80, Math.abs(ch) * 320));
      return el("td", { style: `background:color-mix(in srgb, var(${ch >= 0 ? "--up" : "--down"}) ${a}%, transparent)`,
        title: `${b} · ${sec}: ${num(w)} in ${yrs[prev]} → ${num(v)} in ${yrs[yi]}` }, (ch > 0 ? "+" : "") + (ch * 100).toFixed(0) + "%");
    };
    const grid = el("div", { class: "scroll" }, el("table", { class: "heat" },
      el("tr", {}, el("th", { style: "position:sticky;left:0;background:var(--surface)" }, "Borough"), ...L.sectors.map(sec => el("th", {}, sec))),
      ...L.boroughs.map(b => el("tr", {}, el("td", { style: "position:sticky;left:0;background:var(--surface)" }, b), ...L.sectors.map(sec => cell(b, sec))))));
    const what = lmode === "jobs" ? "Shade: employees, relative to the largest borough in each column." : lmode === "yoy" ? `Change from ${yrs[yi - 1] ?? "–"} to ${yrs[yi]}.` : `Change from 2019 to ${yrs[yi]}.`;
    box.replaceChildren(ctl, grid, note(what + " ONS Business Register and Employment Survey (open access, via Nomis): employees by workplace, rounded by ONS; '–' where ONS suppresses a figure. Software & IT is SIC 62, information services SIC 63 (incl. data processing), finance support SIC 66 (incl. fund management)."));
  };
  draw();
  return box;
}
const VIEWS = {
  async openings() {
    const d = await api("openings"), c = d[cc] || {};
    if (!d[cc]) return [card(null, seg(render)), card("Openings", el("div", { class: "err" }, "Not available right now (" + (d[cc + "_error"] || "no data") + ")."), stale(d))];
    const head = card(null, seg(render), followOr([...AI, ...PRO].filter(n => c.sectors[n]).map(n => ({ label: n, points: c.sectors[n], fmt: i1, cls: v => cls(v - 100), delta: { lag: "1y" } })),
      { latest: "Postings index, 1 Feb 2020 = 100" }), asOf(d), stale(d));
    const lines = card("Job postings by sector (1 February 2020 = 100)",
      ...linesChart([...AI, ...PRO].filter(n => c.sectors[n]).map(n => ({ name: n, points: c.sectors[n], color: css(COL[n]) })).concat([{ name: "All postings", points: c.all || [], dashed: true, color: css("--hold") }]), i1),
      note("Indeed Hiring Lab: seasonally adjusted postings on Indeed relative to 1 Feb 2020, weekly averages. Software and data roles are where AI jobs sit; the four professions are the comparison."));
    const share = card("Share of all job postings that mention AI, by country",
      ...linesChart(Object.entries(d.ai_share || {}).sort((a, b) => (b[0] === cc) - (a[0] === cc)).map(([k, pts], i) => ({ name: k, points: pts, color: k === cc ? css("--s1") : undefined, width: k === cc ? 2.5 : 1.2 })), sh),
      el("div", { class: "scroll", style: "margin-top:8px" }, el("table", {}, el("tr", {}, ...["Country", "AI share now", "A year ago"].map(h => el("th", {}, h))),
        ...Object.entries(d.ai_share_latest || {}).sort((a, b) => b[1].share - a[1].share).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, sh(v.share)), el("td", {}, sh(v.year_ago)))))),
      note("Indeed AI Tracker: postings whose text includes AI terms (machine learning, data science, generative AI...), as % of all postings, monthly average."));
    const hk = card("Hong Kong", el("div", { class: "muted" }, "Indeed's postings index does not cover Hong Kong. Hong Kong headcount is on the Headcount tab; AI mentions in postings are shown above for the countries Indeed tracks."));
    return [head, lines, share, hk];
  },
  async headcount() {
    const d = await api("headcount"), u = d.US;
    const us = u ? (() => {
      const names = Object.keys(u.levels);
      const head = card("US payroll employment", followOr(names.map(n => ({ label: n, points: u.levels[n], fmt: v => num(v * 1000), delta: { lag: "1y" } })), { latest: "Jobs" }), asOf(d), stale(d),
        note("BLS Current Employment Statistics (public API), seasonally adjusted. 'Computer systems design' is the closest industry to AI and software work."));
      const idx = card("Headcount since February 2020 (= 100)", ...linesChart(names.map(n => ({ name: n, points: u.indexed[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : v.toFixed(1)));
      const yoy = card("Change on a year earlier", ...linesChart(names.map(n => ({ name: n, points: u.yoy[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%", { small: true }));
      return [head, idx, yoy];
    })() : [card("US headcount", el("div", { class: "err" }, "Not available right now (" + (d.US_error || "no data") + ")."), stale(d))];
    const U = d.UK || {}, uk = Object.entries(U.levels || {}).filter(([, pts]) => pts.length);
    const ukc = uk.length ? card("UK employee jobs (ONS JOBS03, thousands)",
        followOr(uk.map(([k, pts]) => ({ label: k, points: pts, fmt: v => num(v * 1000), delta: { lag: "1y" } })), { latest: "Employee jobs" }),
        ...linesChart(uk.map(([k, pts]) => ({ name: k, points: pts })), v => num(v), { sync: false }),
        ...linesChart(Object.entries(U.yoy || {}).filter(([, pts]) => pts.length).map(([k, pts]) => ({ name: k + ", change on a year", points: pts })),
          v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%", { small: true, sync: false }),
        note("ONS JOBS03, employee jobs at the end of each quarter, not seasonally adjusted, so the change is against the same quarter a year earlier. Financial & insurance is SIC 2007 section K (divisions 64 to 66); legal & accounting is division 69 (JOBS03 does not split legal from accounting). "
          + (U.workbook ? "Workbook: " + U.workbook + "." : "The workbook could not be read (" + (U.workbook_error || "unknown") + "); hand-entered quarters from data/ai/uk_headcount.csv are shown.")))
      : card("UK headcount", el("div", { class: "muted" }, "Not available right now (" + (d.UK_error || "no data") + "). Quarters can be added by hand to data/ai/uk_headcount.csv."), stale(d));
    const hk = Object.entries(d.HK || {}).filter(([, pts]) => pts.length);
    const hkc = hk.length ? card("Hong Kong persons engaged (C&SD, thousands)", ...linesChart(hk.map(([k, pts]) => ({ name: k, points: pts })), v => num(v), { sync: false }),
        note("C&SD Quarterly Survey of Employment and Vacancies, table 215-16001: persons engaged at the end of each quarter, civil service excluded. Professional, scientific & technical services include legal and accounting firms."))
      : card("Hong Kong headcount", el("div", { class: "muted" }, "Not available right now (" + (d.HK_error || "no data") + ")."), stale(d));
    const lon = d.London && (d.London.boroughs || []).length ? card("London: employees by borough and sector (heatmap)", londonHeat(d.London), stale(d))
      : card("London: employees by borough and sector", el("div", { class: "muted" }, "Not available right now (" + (d.London_error || "no data") + ")."));
    return [...us, lon, ukc, hkc];
  },
  async ratio() {
    const d = await api("ratio"), c = d[cc];
    if (!c) return [card(null, seg(render)), card("AI vs the professions", el("div", { class: "err" }, "Not available right now (" + (d[cc + "_error"] || "no data") + ")."), stale(d))];
    const aiPts = wide ? c.ai_wide_index : c.ai_index, rPts = wide ? c.ai_wide_over_professions : c.ai_over_professions, aiName = wide ? "Software + data + IT systems + R&D" : "Software + data";
    const head = card(null, seg(render), followOr([{ label: aiName + " postings", points: aiPts, fmt: i1, delta: { lag: "1y" } },
      { label: "Law & finance postings", points: c.professions_index, fmt: i1, delta: { lag: "1y" } },
      { label: "Ratio", points: rPts, fmt: v => v.toFixed(2) + "×", delta: { lag: "1y" } },
      { label: "Postings mentioning AI", points: c.ai_share, fmt: sh, delta: ppY }], { latest: "Postings indexes, 1 Feb 2020 = 100" }), asOf(d), stale(d));
    const tog = el("div", { class: "seg" }, ...[[false, "Software + data"], [true, "+ IT systems & scientific R&D"]].map(([k, l]) => el("button", { class: k === wide ? "on" : "", onclick: () => { wide = k; render(); } }, l)));
    const both = card("AI-related postings vs law & finance postings (1 Feb 2020 = 100)", tog,
      ...linesChart([{ name: aiName + " (AI roles)", points: aiPts }, { name: "Legal + finance + accounting + insurance", points: c.professions_index, color: css("--s2") }], i1),
      note("Averages of the sector indexes on the Openings tab. The toggle widens the AI group to Indeed's IT Systems & Solutions and Scientific Research & Development sectors."));
    const ratio = card("The ratio: AI-role postings per profession posting (relative to Feb 2020)", ...linesChart([{ name: aiName + " ÷ professions", points: rPts, color: css("--s4") }], v => v == null ? "–" : v.toFixed(2) + "×", { small: true }),
      note("Above 1 means software and data hiring has held up better than the professions since Feb 2020; below 1 the opposite."));
    const share = card("AI mentions as a share of all postings", ...linesChart([{ name: "AI share", points: c.ai_share, color: css("--s3") }], sh, { small: true }),
      note("The share of all postings that mention AI rises even while software postings fall: AI is spreading into other jobs faster than it adds software ones."));
    return [head, both, ratio, share];
  },
  async wages() {
    const d = await api("wages"), L = d.latest || {};
    const names = Object.keys(L);
    const head = card("US average hourly earnings, all employees", names.length ? followOr(names.map(n => ({ label: n, points: (d.levels || {})[n], fmt: v => "$" + v.toFixed(2), delta: { lag: "1y" } })), { latest: "Hourly pay" }) : null,
      missing(d, "levels", "US pay"), d.bls_error ? note("BLS said: " + d.bls_error + " (its public API allows 25 queries a day; the page retries after a day).") : null, (d.missing || []).length ? note("BLS publishes no hourly pay series for: " + d.missing.join(", ") + ".") : null, asOf(d), stale(d),
      note("BLS Current Employment Statistics (series ending 03), seasonally adjusted, from the BLS public API."));
    const lv = d.levels ? card("Hourly pay ($)", ...linesChart(Object.entries(d.levels).map(([k, pts]) => ({ name: k, points: pts, dashed: k === "All private", color: k === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : "$" + v.toFixed(2))) : null;
    const pr = d.premium ? card("Pay premium over all private-sector pay (%)", ...linesChart(Object.entries(d.premium).map(([k, pts]) => ({ name: k, points: pts })), v => v == null ? "–" : v.toFixed(0) + "%", { small: true }),
      note("If AI substitutes for legal and financial work, this premium should narrow before headcount falls.")) : null;
    const yy = d.yoy ? card("Pay growth on a year earlier (%)", ...linesChart(Object.entries(d.yoy).map(([k, pts]) => ({ name: k, points: pts, dashed: k === "All private", color: k === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : v.toFixed(1) + "%", { small: true })) : null;
    const intl = card("UK and Hong Kong pay (hand-entered)", d.uk_hk && d.uk_hk.length ? table(["Date", "Series", "Value", "Source"], d.uk_hk.map(r => [r.date, r.series, r.value, "[" + host(r.source) + "](" + r.source + ")"]))
      : el("div", { class: "muted" }, "No points yet: add ONS EARN03 (UK, weekly £ by industry) and C&SD Labour Earnings Survey (HK) readings to data/ai/pay_uk_hk.csv."));
    return [head, lv, pr, yy, intl];
  },
  async firms() {
    const d = await api("firms");
    const head = card(null, followOr([{ label: "US businesses using AI (Census)", points: d.btos_us || [], fmt: sh, delta: ppY },
      { label: "Expect to use AI within 6 months (Census)", points: d.btos_expect || [], fmt: sh, delta: ppY },
      { label: "Paying for AI tools (Ramp)", points: d.ramp || [], fmt: sh, delta: ppY },
      { label: "UK businesses using AI (ONS)", points: (d.uk_hk || {})["UK: all businesses (ONS BICS)"] || [], fmt: sh, delta: ppY }],
      { latest: "Latest readings" }), asOf(d), stale(d));
    const btos = card("Share of US businesses that used AI in the last two weeks",
      ...linesChart([{ name: "All businesses (Census BTOS)", points: d.btos_us || [] }, { name: "Paying for AI tools (Ramp AI Index)", points: d.ramp || [], color: css("--s2") }], sh),
      note("US Census Bureau Business Trends and Outlook Survey, asked every two weeks of about 1.2 million businesses: 'use Super Intelligence or SI (formerly AI) in any of its business functions', the wording since the period ending 16 Nov 2025, where the line starts. Ramp's index counts businesses on its card platform that paid for an AI product that month."), cite(d.cited));
    const expect = (d.btos_expect || []).length ? card("Using AI now vs expecting to within six months (US, Census BTOS)",
      ...linesChart([{ name: "Using now", points: d.btos_us || [] }, { name: "Expect to use within 6 months", points: d.btos_expect, color: css("--s4"), dashed: true }], sh, { small: true }),
      note("The gap between the two lines is intent not yet acted on.")) : card("Expect to use AI within six months", el("div", { class: "muted" }, "Not read yet: the Census workbook was not reachable or its layout changed; add points to data/ai/btos_ai_expect_us.csv."));
    const lat = Object.entries(d.uk_hk_latest || {});
    const intl = Object.keys(d.uk_hk || {}).length ? card("UK and Hong Kong: share of firms using AI", ...linesChart(Object.entries(d.uk_hk).map(([k, pts]) => ({ name: k, points: pts })), sh, { small: true, sync: false }),
      table(["Series", "Latest", "Period ending", "A year earlier"], lat.map(([k, v]) => [k, sh(v.value), v.date, sh(v.year_ago)])),
      note("UK: ONS Business Insights and Conditions Survey, asked about once a quarter: businesses using at least one AI technology (100% minus 'does not use' minus 'not sure'), weighted. Hong Kong has no comparable periodic survey yet; hand-entered points, if any, are listed below."),
      ...((d.uk_hk_rows || []).length ? [table(["Date", "Series", "%", "Source"], d.uk_hk_rows.map(r => [r.date, r.series, r.value, "[" + host(r.source) + "](" + r.source + ")"]))] : []), stale(d))
      : card("UK and Hong Kong", el("div", { class: "muted" }, "Not available right now: the ONS BICS workbook could not be read. Hand-entered points go in data/ai/firm_adoption_uk_hk.csv."));
    const sec = Object.entries(d.btos_sectors || {}).filter(([, p]) => p.length);
    const sectors = sec.length ? card("By sector (latest)", ...svgBars(sec.map(([k]) => k), [{ name: "Using AI", values: sec.map(([, p]) => p[p.length - 1][1]), color: css("--s1") }], { yFmt: sh, labelW: 90 }))
      : card("By sector", el("div", { class: "muted" }, "No sector points entered yet: copy the sector rows of the BTOS workbook into data/ai/btos_ai_use_by_sector.csv."));
    return [head, btos, expect, sectors, intl];
  },
  async users() {
    const d = await api("users"), s = Object.entries(d.series || {}).filter(([, p]) => p.some(x => x[1] > 0));
    const chart = card("Reported users", ...linesChart(s.map(([k, pts]) => ({ name: k, points: pts.filter(p => p[1] > 0) })), v => big(v)), asOf(d),
      note("Each point is a company announcement; lines join announcements and say nothing about the months between."));
    const rows = (d.rows || []).map(r => el("tr", {}, el("td", {}, dateOf(r.date)), el("td", { class: "wrap" }, r.series), el("td", {}, big(+r.value)), el("td", { class: "wrap" }, link(host(r.source), r.source), r.note ? " · " + r.note : "")));
    const table = card("Announcements", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "What", "Users", "Source"].map(h => el("th", h === "What" || h === "Source" ? { style: "text-align:left" } : {}, h))), ...rows)));
    return [chart, table];
  },
  async agents() {
    const d = await api("agents"), kinds = Object.keys(d.kinds || {});
    if (akind && !kinds.includes(akind)) akind = null;
    const rows = (d.rows || []).filter(r => !akind || (r.kind || "other") === akind);
    const byYear = {};
    rows.forEach(r => { const y = r.date.slice(0, 4); byYear[y] = (byYear[y] || 0) + 1; });
    const years = Object.keys(byYear).sort();
    // Kind filter: All plus each kind in the CSV (with its count); it narrows both the bars and the timeline
    const pill = (k, l) => el("button", { class: k === akind ? "on" : "", onclick: () => { akind = k; render(); } }, l);
    const filt = kinds.length > 1 ? el("div", { class: "seg", style: "flex-wrap:wrap" }, pill(null, `All (${(d.rows || []).length})`), ...kinds.map(k => pill(k, `${k} (${d.kinds[k]})`))) : null;
    const what = akind ? `"${akind}"` : "Agent";
    const bars = years.length ? card(`${what} launches by year (from the list below)`, filt, ...svgBars(years, [{ name: "Launches", values: years.map(y => byYear[y]), color: css("--s1") }], { yFmt: v => v % 1 ? "" : String(v), h: 160 })) : null;   // whole launches only on the axis
    const tl = card("Timeline: agent products and protocols" + (akind ? ` (${akind})` : ""), bars ? null : filt, el("div", { class: "tl" }, ...rows.flatMap(r => [el("div", { class: "d" }, dateOf(r.date)),
      el("div", {}, link(r.event, r.source), " · ", el("span", { class: "muted" }, r.company + (r.kind ? " · " + r.kind : "") + (r.note ? " · " + r.note : "")))])), asOf(d),
      note("Hand-kept list, one row per launch, in data/ai/agent_milestones.csv; the filter uses its kind column."));
    return [bars, tl];
  },
  async skills() {
    const d = await api("skills"), L = d.latest || {};
    const chart = card("Share of job postings mentioning AI, by country", ...linesChart(Object.entries(d.share || {}).map(([k, pts]) => ({ name: k, points: pts, width: k === "US" || k === "GB" ? 2.5 : 1.2 })), sh), asOf(d), stale(d),
      note("Indeed AI Tracker (Indeed Hiring Lab, CC BY 4.0): postings whose text includes AI terms, as % of all postings, monthly average."));
    const head = card(null, followOr(["US", "GB", "DE", "FR", "CA"].filter(k => (d.share || {})[k]).map(k => ({ label: k, points: d.share[k], fmt: sh, delta: ppY })),
      { latest: "Share of postings mentioning AI" }));
    const table = card("Latest", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Country", "Now", "A year ago", "Two years ago"].map(h => el("th", {}, h))),
      ...Object.entries(L).sort((a, b) => b[1].share - a[1].share).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, sh(v.share)), el("td", {}, sh(v.year_ago)), el("td", {}, sh(v.two_years_ago)))))));
    return [head, chart, table];
  },
};
window.TOPIC = { VIEWS };
})();
