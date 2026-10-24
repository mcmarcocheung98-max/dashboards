// AI jobs vs law & finance: tabs and cards. Data from /api/ai-jobs/<openings|headcount|ratio>.
(() => {
let cc = "US";
const AI = ["Software Development", "Data & Analytics"], PRO = ["Legal", "Banking & Finance", "Accounting", "Insurance"];
const COL = { "Software Development": "--s1", "Data & Analytics": "--s6", "Legal": "--s2", "Banking & Finance": "--s3", "Accounting": "--s4", "Insurance": "--s5" };
const seg = rerender => el("div", { class: "seg" }, ...[["US", "United States"], ["GB", "United Kingdom"]].map(([k, l]) => el("button", { class: k === cc ? "on" : "", onclick: () => { cc = k; rerender(); } }, l)));
const i1 = v => v == null ? "–" : v.toFixed(0);
const sh = v => v == null ? "–" : v.toFixed(1) + "%";
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
    return [head, lines, share];
  },
  async headcount() {
    const d = await api("headcount"), u = d.US;
    if (!u) return [card("US headcount", el("div", { class: "err" }, "Not available right now (" + (d.US_error || "no data") + ")."), stale(d))];
    const names = Object.keys(u.levels);
    const rows = names.map(n => el("tr", {}, el("td", {}, n), el("td", {}, num(u.latest[n].level * 1000)), el("td", { class: cls(u.latest[n].yoy) }, pct(u.latest[n].yoy / 100, 1)), el("td", { class: cls(u.latest[n].since_2020) }, pct(u.latest[n].since_2020 / 100, 1))));
    const head = card("US payroll employment", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Industry", "Jobs", "vs a year ago", "vs Feb 2020"].map(h => el("th", {}, h))), ...rows)), asOf(d), stale(d),
      note("BLS Current Employment Statistics via FRED, seasonally adjusted. 'Computer systems design' is the closest industry to AI and software work."));
    const idx = card("Headcount since February 2020 (= 100)", ...linesChart(names.map(n => ({ name: n, points: u.indexed[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : v.toFixed(1)));
    const yoy = card("Change on a year earlier", ...linesChart(names.map(n => ({ name: n, points: u.yoy[n], dashed: n === "All private", color: n === "All private" ? css("--hold") : undefined })), v => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%", { small: true }));
    const uk = Object.entries(d.UK || {}).filter(([, pts]) => pts.length);
    const ukc = uk.length ? card("UK workforce jobs (hand-entered from ONS JOBS03, thousands)", ...linesChart(uk.map(([k, pts]) => ({ name: k, points: pts })), v => num(v)))
      : card("UK headcount", el("div", { class: "muted" }, "No UK points entered yet: add quarterly ONS workforce-jobs figures to data/ai-jobs/uk_headcount.csv."));
    return [head, idx, yoy, ukc];
  },
  async ratio() {
    const d = await api("ratio"), c = d[cc];
    if (!c) return [card(null, seg(render)), card("AI vs the professions", el("div", { class: "err" }, "Not available right now (" + (d[cc + "_error"] || "no data") + ")."), stale(d))];
    const head = card(null, seg(render), asOf(d), stale(d));
    const both = card("AI-related postings vs law & finance postings (1 Feb 2020 = 100)",
      ...linesChart([{ name: "Software + data (AI roles)", points: c.ai_index }, { name: "Legal + finance + accounting + insurance", points: c.professions_index, color: css("--s2") }], i1),
      note("Averages of the sector indexes on the Openings tab."));
    const ratio = card("The ratio: AI-role postings per profession posting (relative to Feb 2020)", ...linesChart([{ name: "Software + data ÷ professions", points: c.ai_over_professions, color: css("--s4") }], v => v == null ? "–" : v.toFixed(2) + "×", { small: true }),
      note("Above 1 means software and data hiring has held up better than the professions since Feb 2020; below 1 the opposite."));
    const share = card("AI mentions as a share of all postings", ...linesChart([{ name: "AI share", points: c.ai_share, color: css("--s3") }], sh, { small: true }),
      note("The share of all postings that mention AI rises even while software postings fall: AI is spreading into other jobs faster than it adds software ones."));
    return [head, both, ratio, share];
  },
};
window.TOPIC = { VIEWS };
})();
