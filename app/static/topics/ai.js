// AI: Jobs & Adoption. Tabs and cards for /ai; data from /api/ai/<openings|headcount|wages|ratio|firms|users|agents|skills>.
(() => {
let cc = "US", wide = false;
const AI = ["Software Development", "Data & Analytics"], PRO = ["Legal", "Banking & Finance", "Accounting", "Insurance"];
const COL = { "Software Development": "--s1", "Data & Analytics": "--s6", "Legal": "--s2", "Banking & Finance": "--s3", "Accounting": "--s4", "Insurance": "--s5" };
const seg = rerender => el("div", { class: "seg" }, ...[["US", "United States"], ["GB", "United Kingdom"]].map(([k, l]) => el("button", { class: k === cc ? "on" : "", onclick: () => { cc = k; rerender(); } }, l)));
const i1 = v => v == null ? "–" : v.toFixed(0);
const sh = v => v == null ? "–" : v.toFixed(1) + "%";
const table = (cols, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...cols.map(h => el("th", {}, h))),
  ...rows.map(r => el("tr", {}, ...r.map((v, i) => { const s = String(v ?? ""), m = s.match(/^\[([^\]]+)\]\(([^)]+)\)(.*)$/); return el("td", { class: i ? "wrap" : "" }, ...(m ? [link(m[1], m[2]), m[3]] : [s])); })))));
const dateOf = s => new Date(s).toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const VIEWS = {
  async openings() {
    const d = await api("openings"), c = d[cc] || {};
    if (!d[cc]) return [card(null, seg(render)), card("Openings", el("div", { class: "err" }, "Not available right now (" + (d[cc + "_error"] || "no data") + ")."), stale(d))];
    const rows = [...AI, ...PRO].filter(n => c.latest[n]).map(n => el("tr", {}, el("td", {}, el("span", { class: "sw", style: "background:" + css(COL[n]) + ";margin-right:8px" }), n),
      el("td", {}, i1(c.latest[n].index)), el("td", { class: cls(c.latest[n].index - 100) }, pct(c.latest[n].index / 100 - 1, 0)), el("td", { class: cls(c.latest[n].yoy) }, pct(c.latest[n].yoy, 1))));
    const head = card(null, seg(render), el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Sector", "Postings index", "vs Feb 2020", "vs a year ago"].map(h => el("th", {}, h))), ...rows)), asOf(d), stale(d));
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
    if (!u) return [card("US headcount", el("div", { class: "err" }, "Not available right now (" + (d.US_error || "no data") + ")."), stale(d))];
    const names = Object.keys(u.levels);
    const rows = names.map(n => el("tr", {}, el("td", {}, n), el("td", {}, num(u.latest[n].level * 1000)), el("td", { class: cls(u.latest[n].yoy) }, pct(u.latest[n].yoy / 100, 1)), el("td", { class: cls(u.latest[n].since_2020) }, pct(u.latest[n].since_2020 / 100, 1))));
    const head = card("US payroll employment", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Industry", "Jobs", "vs a year ago", "vs Feb 2020"].map(h => el("th", {}, h))), ...rows)), asOf(d), stale(d),
      note("BLS Current Employment Statistics (public API), seasonally adjusted. 'Computer systems design' is the closest industry to AI and software work."));
    const idx = card("Headcount since February 2020 (= 100)", ...linesChart(names.map(n => ({ name: n, points: u.indexed[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : v.toFixed(1)));
    const yoy = card("Change on a year earlier", ...linesChart(names.map(n => ({ name: n, points: u.yoy[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%", { small: true }));
    const uk = Object.entries(d.UK || {}).filter(([, pts]) => pts.length);
    const ukc = uk.length ? card("UK workforce jobs (hand-entered from ONS JOBS03, thousands)", ...linesChart(uk.map(([k, pts]) => ({ name: k, points: pts })), v => num(v)))
      : card("UK headcount", el("div", { class: "muted" }, "No UK points entered yet: add quarterly ONS workforce-jobs figures to data/ai/uk_headcount.csv."));
    const hk = Object.entries(d.HK || {}).filter(([, pts]) => pts.length);
    const hkc = hk.length ? card("Hong Kong persons engaged (C&SD, thousands)", ...linesChart(hk.map(([k, pts]) => ({ name: k, points: pts })), v => num(v)),
        note("C&SD Quarterly Survey of Employment and Vacancies, table 215-16001: persons engaged at the end of each quarter, civil service excluded. Professional, scientific & technical services include legal and accounting firms."))
      : card("Hong Kong headcount", el("div", { class: "muted" }, "Not available right now (" + (d.HK_error || "no data") + ")."), stale(d));
    return [head, idx, yoy, ukc, hkc];
  },
  async ratio() {
    const d = await api("ratio"), c = d[cc];
    if (!c) return [card(null, seg(render)), card("AI vs the professions", el("div", { class: "err" }, "Not available right now (" + (d[cc + "_error"] || "no data") + ")."), stale(d))];
    const head = card(null, seg(render), asOf(d), stale(d));
    const tog = el("div", { class: "seg" }, ...[[false, "Software + data"], [true, "+ IT systems & solutions"]].map(([k, l]) => el("button", { class: k === wide ? "on" : "", onclick: () => { wide = k; render(); } }, l)));
    const aiPts = wide ? c.ai_wide_index : c.ai_index, rPts = wide ? c.ai_wide_over_professions : c.ai_over_professions, aiName = wide ? "Software + data + IT systems" : "Software + data";
    const both = card("AI-related postings vs law & finance postings (1 Feb 2020 = 100)", tog,
      ...linesChart([{ name: aiName + " (AI roles)", points: aiPts }, { name: "Legal + finance + accounting + insurance", points: c.professions_index, color: css("--s2") }], i1),
      note("Averages of the sector indexes on the Openings tab. The toggle widens the AI group to Indeed's IT Systems & Solutions sector."));
    const ratio = card("The ratio: AI-role postings per profession posting (relative to Feb 2020)", ...linesChart([{ name: aiName + " ÷ professions", points: rPts, color: css("--s4") }], v => v == null ? "–" : v.toFixed(2) + "×", { small: true }),
      note("Above 1 means software and data hiring has held up better than the professions since Feb 2020; below 1 the opposite."));
    const share = card("AI mentions as a share of all postings", ...linesChart([{ name: "AI share", points: c.ai_share, color: css("--s3") }], sh, { small: true }),
      note("The share of all postings that mention AI rises even while software postings fall: AI is spreading into other jobs faster than it adds software ones."));
    return [head, both, ratio, share];
  },
  async wages() {
    const d = await api("wages"), L = d.latest || {};
    const names = Object.keys(L);
    const head = card("US average hourly earnings, all employees", table(["Industry", "Hourly pay", "vs a year ago", "vs all private-sector pay"],
      names.map(n => [n, "$" + (L[n].level == null ? "–" : L[n].level.toFixed(2)), L[n].yoy == null ? "–" : (L[n].yoy > 0 ? "+" : "") + L[n].yoy.toFixed(1) + "%", n === "All private" ? "–" : (L[n].premium > 0 ? "+" : "") + L[n].premium.toFixed(0) + "%"])),
      missing(d, "levels", "US pay"), (d.missing || []).length ? note("BLS publishes no hourly pay series for: " + d.missing.join(", ") + ".") : null, asOf(d), stale(d),
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
    const d = await api("firms"), n = d.now || {};
    const head = card(null, el("div", { class: "kpis" }, kpi("US businesses using AI", sh(n.btos)), kpi("A year earlier", sh(n.btos_year_ago)),
      kpi("Change", n.btos != null && n.btos_year_ago != null ? pp(n.btos - n.btos_year_ago) : "–", cls(n.btos - n.btos_year_ago)), kpi("Paying for AI tools (Ramp)", sh(n.ramp)),
      kpi("UK businesses using AI (ONS)", sh((d.uk_hk_latest || {})["UK: all businesses (ONS BICS)"]?.value))), asOf(d), stale(d));
    const btos = card("Share of US businesses that used AI in the last two weeks",
      ...linesChart([{ name: "All businesses (Census BTOS)", points: d.btos_us || [] }, { name: "Paying for AI tools (Ramp AI Index)", points: d.ramp || [], color: css("--s2") }], sh),
      note("US Census Bureau Business Trends and Outlook Survey, asked every two weeks of about 1.2 million businesses; Ramp's index counts businesses on its card platform with a paid AI subscription."), cite(d.cited));
    const expect = (d.btos_expect || []).length ? card("Using AI now vs expecting to within six months (US, Census BTOS)",
      ...linesChart([{ name: "Using now", points: d.btos_us || [] }, { name: "Expect to use within 6 months", points: d.btos_expect, color: css("--s4"), dashed: true }], sh, { small: true }),
      note("The gap between the two lines is intent not yet acted on.")) : card("Expect to use AI within six months", el("div", { class: "muted" }, "Not read yet: the Census workbook was not reachable or its layout changed; add points to data/ai/btos_ai_expect_us.csv."));
    const lat = Object.entries(d.uk_hk_latest || {});
    const intl = Object.keys(d.uk_hk || {}).length ? card("UK and Hong Kong: share of firms using AI", ...linesChart(Object.entries(d.uk_hk).map(([k, pts]) => ({ name: k, points: pts })), sh, { small: true }),
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
    const table = card("Announcements", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "What", "Users", "Source"].map(h => el("th", {}, h))), ...rows)));
    return [chart, table];
  },
  async agents() {
    const d = await api("agents");
    const years = Object.keys(d.by_year || {});
    const bars = years.length ? card("Agent launches by year (from the list below)", ...svgBars(years, [{ name: "Launches", values: years.map(y => d.by_year[y]), color: css("--s1") }], { yFmt: v => Math.round(v), h: 160 })) : null;
    const tl = card("Timeline: agent products and protocols", el("div", { class: "tl" }, ...(d.rows || []).flatMap(r => [el("div", { class: "d" }, dateOf(r.date)),
      el("div", {}, link(r.event, r.source), " · ", el("span", { class: "muted" }, r.company + (r.kind ? " · " + r.kind : "") + (r.note ? " · " + r.note : "")))])), asOf(d),
      note("Hand-kept list, one row per launch, in data/ai/agent_milestones.csv."));
    return [bars, tl];
  },
  async skills() {
    const d = await api("skills"), L = d.latest || {};
    const chart = card("Share of job postings mentioning AI, by country", ...linesChart(Object.entries(d.share || {}).map(([k, pts]) => ({ name: k, points: pts, width: k === "US" || k === "GB" ? 2.5 : 1.2 })), sh), asOf(d), stale(d),
      note("Indeed AI Tracker (Indeed Hiring Lab, CC BY 4.0): postings whose text includes AI terms, as % of all postings, monthly average."));
    const table = card("Latest", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Country", "Now", "A year ago", "Two years ago"].map(h => el("th", {}, h))),
      ...Object.entries(L).sort((a, b) => b[1].share - a[1].share).map(([k, v]) => el("tr", {}, el("td", {}, k), el("td", {}, sh(v.share)), el("td", {}, sh(v.year_ago)), el("td", {}, sh(v.two_years_ago)))))));
    return [chart, table];
  },
};
window.TOPIC = { VIEWS };
})();
