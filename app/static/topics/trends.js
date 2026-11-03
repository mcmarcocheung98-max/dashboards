// Search & Social Trends: tabs and cards. Data from /api/trends/<overview|search|social|rising|regions|reality>; helpers from topic.html.
(() => {
const f0 = v => v == null ? "–" : num(v, 0);
const zf = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const zcls = v => v == null ? "" : v >= 1 ? "up" : v <= -1 ? "down" : "";
const icls = v => v == null ? "" : v >= 120 ? "up" : v <= 80 ? "down" : "";
const views = v => v == null ? "–" : big(v);
const gen = v => v == null ? "–" : Math.abs(v) >= 10000 ? big(v) : num(v, Math.abs(v) < 10 ? 2 : Math.abs(v) < 1000 ? 1 : 0);
const pc0 = v => pct(v, 0);
const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...head.map(h => el("th", {}, h))), ...rows));
// up to 12 lines: the six series colours, then the same six dashed
const line = (s, i) => ({ ...s, color: css(SERIES[i % SERIES.length]), dashed: i >= SERIES.length });
const THEME_LINK = (label, slug) => slug ? link(label, "/" + slug) : label;
const zpill = z => el("span", { class: "pill " + (z == null ? "" : z >= 1 ? "ok" : z <= -1 ? "bad" : "") }, zf(z));
const problems = d => d && d.problems && Object.keys(d.problems).length ? el("details", { style: "margin-top:6px" }, el("summary", { class: "muted" }, Object.keys(d.problems).length + " downloads did not work in the last run"),
  el("div", { class: "muted" }, ...Object.entries(d.problems).map(([k, v]) => el("div", {}, k + ": " + v)))) : null;
const empty = what => el("div", { class: "muted" }, "No " + what + " yet: the background download fills it within a few minutes of a deploy, and daily logs build up from launch.");

const VIEWS = {
  async overview() {
    const d = await api("overview"), T = d.themes || [];
    const top = T.slice(0, 6);
    const head = card(null, followHead(top.map(t => ({ label: t.label + " attention (100 = its usual)", points: t.points, fmt: f0, cls: icls }))),
      note("Each theme's attention index: the geometric mean of its topics' weekly Wikipedia views, each as a share of that topic's own average over the previous year (100 = usual)."),
      asOf(d), stale(d));
    const idx = T.length ? card("Attention index by theme (weekly, 100 = each topic's average over the previous year)",
      ...linesChart(T.map((t, i) => line({ name: t.label, points: t.points }, i)), f0, { hlines: [100], log: true }),
      note("Log scale, so a doubling looks the same at every level. Above 100 the theme is being looked up more than usual for it; the spikes are news (a launch, a crash, a ruling). " +
        "Click a name to hide its line.")) : card("Attention index by theme", empty("pageviews"));
    const R = d.rising || [], F = d.fading || [];
    const bars = R.length ? card("Fastest-rising topics this week (z-score of the latest full week against the topic's previous year)",
      ...svgBars(R.map(r => r.label.split(" ")[0]), [{ name: "z", values: R.map(r => r.z), colorFn: v => v >= 1 ? css("--up") : v <= -1 ? css("--down") : css("--hold") }],
        { yFmt: zf, catName: i => R[i].label + " (" + (THEMES_LABEL[R[i].theme] || R[i].theme) + "), week to " + R[i].week + ", " + views(R[i].views) + " views", labelW: 60, h: 220 }),
      note("z = (log views this week − their average over the previous 52 weeks) / their standard deviation. +2 is a week seen about once in a year or two for that topic; a small topic doubling counts as much as a big one.")) : null;
    const trow = r => el("tr", {}, el("td", {}, r.label), el("td", {}, THEMES_LABEL[r.theme] || r.theme), el("td", {}, views(r.views)), el("td", {}, zpill(r.z)),
      el("td", { class: cls(r.a4) }, pc0(r.a4)), el("td", { class: cls(r.a13) }, pc0(r.a13)));
    const tbl = R.length ? el("div", { class: "grid2" },
      card("Rising most", table(["Topic", "Theme", "Views (week)", "z", "vs 4 wks", "vs 13 wks"], R.map(trow))),
      card("Fading most", table(["Topic", "Theme", "Views (week)", "z", "vs 4 wks", "vs 13 wks"], F.map(trow)),
        note("English Wikipedia, users only (bots and crawlers excluded by Wikimedia). UK and Chinese-language pages are on the US / UK / HK tab."))) : null;
    const themes = T.length ? card("Themes and their dashboards", table(["Theme", "Index now", "Average z of its topics", "Topics"],
      T.map(t => el("tr", {}, el("td", {}, THEME_LINK(t.label, t.dashboard)), el("td", { class: icls(t.index) }, f0(t.index)), el("td", {}, zpill(t.z)), el("td", {}, t.n)))),
      note("Each theme links to the dashboard that tracks it; the Attention vs reality tab sets the two side by side."), problems(d)) : problems(d) && card(null, problems(d));
    return [head, idx, bars, tbl, themes];
  },
  async search() {
    const d = await api("search"), top = d.top || [];
    const head = card(null, followHead([{ label: "All tracked topics, views a week", points: d.total, fmt: views, delta: { lag: "1y" } },
      ...top.slice(0, 3).map(t => ({ label: t.name + ", views a week", points: t.points, fmt: views, delta: { lag: "3m" } }))]),
      note("Weekly Wikipedia pageviews (English, users), complete weeks ending Sunday."), asOf(d), stale(d));
    const tot = (d.total || []).length ? card("All tracked topics: Wikipedia views a week", ...linesChart([{ name: "All topics", points: d.total, color: css("--s1") }], views),
      note("The sum over every English-Wikipedia topic in topics.csv: how much these subjects are being looked up overall. It dips every Christmas and in summer.")) : card("Wikipedia views", empty("pageviews"));
    const topc = top.length ? card("Most-viewed topics, views a week", ...linesChart(top.map((t, i) => line(t, i)), views, { log: true }),
      note("The five topics with the most views last week. Log scale.")) : null;
    const groups = (d.groups || []).map(g => card(g.label + ": views a week", ...linesChart(g.lines.map((t, i) => line(t, i)), views, { small: true, log: true }),
      note("Wikipedia pageviews of each " + g.label + " topic. " + (g.dashboard ? "Dashboard: /" + g.dashboard + "." : ""))));
    const G = Object.entries(d.gtrends || {}).filter(([k]) => /\|(world|US)$/i.test(k));
    const gt = card("Google Trends (hand-entered monthly points, 0–100)", ...(G.length ? linesChart(G.map(([k, p], i) => line({ name: k.replace("|", ", "), points: p }, i)), f0) : [el("div", { class: "muted" }, "No points entered yet.")]),
      note("Google Trends gives no free API a server can rely on, so points are hand-entered in data/trends/gtrends.csv (date, series 'keyword|geo', value, source). 100 is the peak of the window the row was read from. Rows marked verify were written from memory."),
      cite(d.gtrends_cited));
    const B = d.breakouts || [];
    const br = card("Breakouts in the last 30 days", B.length ? table(["Date", "Topic", "Theme", "Views that day", "x its normal", "Score"],
      B.map(b => el("tr", {}, el("td", {}, b.date), el("td", {}, b.label), el("td", {}, THEMES_LABEL[b.theme] || b.theme), el("td", {}, f0(b.views)), el("td", {}, num(b.multiple, 1) + "x"), el("td", {}, num(b.score, 1)))))
      : el("div", { class: "muted" }, "No topic broke out in the last 30 days."),
      note("A breakout is a day at least twice the topic's median of the previous 8 weeks and more than 4 robust deviations above it (log views): the day something happened."));
    const tbl = card("Every topic", table(["Topic", "Theme", "Region", "Article read", "Week to", "Views", "z"], (d.table || []).map(r => el("tr", {},
      el("td", {}, r.label), el("td", {}, THEMES_LABEL[r.theme] || r.theme), el("td", {}, r.region), el("td", { class: "muted" }, r.title || "–"), el("td", {}, r.week || "–"), el("td", {}, views(r.views)), el("td", {}, zpill(r.z))))),
      note("'Article read' is the title after redirects (and Chinese script conversion) as the server resolved it from topics.csv."));
    return [head, el("div", { class: "grid2" }, tot, topc), el("div", { class: "grid2" }, ...groups), gt, br, tbl];
  },
  async social() {
    const d = await api("social"), H = d.hn || {}, S = d.bsky || {}, G = d.github || {}, R = d.reddit || {};
    const items = [{ label: "Hacker News stories a week (all topics)", points: H.total_stories, fmt: f0, delta: { lag: "3m" } },
      ...((d.front || {}).share || []).length ? [{ label: "AI share of HN front-page stories", points: d.front.share, fmt: v => pct(v, 0).replace("+", "") }] : [],
      { label: "Hacker News comments a week", points: H.total_comments, fmt: f0, delta: { lag: "3m" } }];
    if ((S.lines || []).length) items.push({ label: "Bluesky posts a day: " + S.lines[0].name, points: S.lines[0].points, fmt: f0 });
    if ((G.lines || []).length) items.push({ label: "GitHub stars: " + G.lines[0].name, points: G.lines[0].points, fmt: big, delta: { lag: "30d", abs: true, fmt: v => (v >= 0 ? "+" : "") + big(v) } });
    const head = card(null, followHead(items), asOf(d), stale(d), problems(d));
    const hn = (H.stories || []).length ? el("div", { class: "grid2" },
      card("Hacker News stories a week, most-discussed topics", ...linesChart([{ name: "All topics", points: H.total_stories, color: css("--hold"), dashed: true }, ...H.stories.map((t, i) => line(t, i))], f0),
        note("Stories whose title or text matches the topic's query (topics.csv), counted per week (Monday to Sunday) with Algolia's HN search. 'All topics' adds every tracked query, so a story matching two counts twice.")),
      card("Hacker News comments a week", ...linesChart([{ name: "All topics", points: H.total_comments, color: css("--hold"), dashed: true }, ...H.comments.map((t, i) => line(t, i))], f0),
        note("Comments matching the query: what the technical crowd is arguing about."))) : card("Hacker News", empty("Hacker News counts"));
    const F = d.front || {};
    const front = (F.share || []).length ? card("AI share of Hacker News front-page stories, weekly", ...linesChart([{ name: "AI share", points: F.share, color: css("--s4") }], v => pct(v, 0).replace("+", ""), { small: true, hlines: [0.2] }),
      note("Every story that reached the front page each week (Algolia's front_page tag), and how many are about AI by their title (AI, LLMs, GPT, Claude, Gemini, agents, GPUs, Nvidia and the like, as whole words). " +
        "The dashed line is 20%, the watch point on /signals: below it the technical crowd has moved on.")) : null;
    const hnt = (H.rows || []).length ? card("Hacker News by topic, last full week", table(["Topic", "Stories", "Comments", "Stories vs 4 wks", "vs 13 wks"], H.rows.map(r => el("tr", {},
      el("td", {}, r.label), el("td", {}, f0(r.stories)), el("td", {}, f0(r.comments)), el("td", { class: cls(r.s_4) }, pc0(r.s_4)), el("td", { class: cls(r.s_13) }, pc0(r.s_13)))))) : null;
    const bs = card("Bluesky posts a day", ...((S.lines || []).length ? [...linesChart(S.lines.map((t, i) => line(t, i)), f0, { small: true }),
      table(["Keyword", "Posts (" + (S.rows[0] || {}).date + ")", "7-day average"], S.rows.map(r => el("tr", {}, el("td", {}, r.label), el("td", {}, r.capped ? "500+" : f0(r.posts)), el("td", {}, f0(r.avg7)))))] : [empty("Bluesky counts")]),
      S.closed ? note(S.closed + ".") : null,
      note("Posts matching the keyword on each UTC day, from Bluesky's public search, counted once a day from launch (up to 500 a day: '500+' means more). Bluesky only, not X."));
    const rd = card("Reddit subscribers", ...((R.lines || []).length ? [...linesChart(R.lines.map((t, i) => line(t, i)), big, { small: true }),
      table(["Subreddit", "Theme", "Subscribers", "Active now", "30-day change", "Read"], R.rows.map(r => el("tr", {}, el("td", {}, link("r/" + r.sub, "https://www.reddit.com/r/" + r.sub + "/")), el("td", {}, THEMES_LABEL[r.theme] || r.theme || "–"),
        el("td", {}, big(r.subscribers)), el("td", {}, f0(r.active)), el("td", { class: cls(r.d30) }, r.d30 == null ? "–" : (r.d30 > 0 ? "+" : "") + big(r.d30)), el("td", {}, r.date))))] : [empty("Reddit counts")]),
      R.closed ? note(R.closed + ".") : null,
      note("Read once a day from each subreddit's about.json (one request every few seconds). Reddit often refuses cloud servers; then counts are hand-entered in data/trends/reddit.csv (series 'sub|subscribers' or 'sub|active')."),
      cite(R.cited));
    const gh = card("GitHub stars of the main AI repositories", ...((G.lines || []).length ? [...linesChart(G.lines.map((t, i) => line(t, i)), big, { small: true }),
      table(["Repository", "Stars", "7 days", "30 days", "Forks", "Logged since"], G.rows.map(r => el("tr", {}, el("td", {}, link(r.label, "https://github.com/" + r.repo)), el("td", {}, big(r.stars)),
        el("td", {}, r.d7 == null ? "–" : "+" + f0(r.d7)), el("td", {}, r.d30 == null ? "–" : "+" + f0(r.d30)), el("td", {}, big(r.forks)), el("td", {}, r.since))))] : [empty("GitHub stars")]),
      note("Stars from the GitHub API, logged once a day (repos.csv). New stars a week are developer attention: a tool going viral shows here before it shows in hiring."));
    return [head, hn, front, hnt, el("div", { class: "grid2" }, bs, gh), rd];
  },
  async rising() {
    const d = await api("rising"), Z = d.z_lines || [], R = d.rows || [];
    const head = card(null, followHead(Z.map(z => ({ label: z.name + ": attention z", points: z.points, fmt: zf, cls: zcls }))),
      note("The topics accelerating most and least against their own last quarter, as z-scores against each topic's previous year."), asOf(d), stale(d));
    const zc = Z.length ? card("Attention z-score, weekly: the biggest movers", ...linesChart(Z.map((t, i) => line(t, i)), zf, { hlines: [-1, 0, 1] }),
      note("Each week's log views against the topic's previous 52 weeks. Above +1 the topic is unusually hot for itself; below −1 it is fading. Top four: fastest accelerating vs the 13-week average; the rest: the slowest.")) : card("Attention z-scores", empty("pageviews"));
    const sorted = R.slice(0, 40);
    const bars = R.length ? card("Last week against its 13-week average",
      ...svgBars(sorted.map(r => r.label.split(" ")[0]), [{ name: "vs 13 weeks", values: sorted.map(r => r.a13), colorFn: v => v >= 0 ? css("--up") : css("--down") }],
        { yFmt: pc0, catName: i => sorted[i].label + ", week to " + sorted[i].week, extra: i => " · vs 4 weeks " + pc0(sorted[i].a4), labelW: 64, h: 240 }),
      note("Acceleration: last week's views over the average of the 13 weeks before it. Sorted from fastest-rising to fastest-fading.")) : null;
    const crossRows = list => list.length ? table(["Topic", "Week", "vs 4 wks", "vs 13 wks", "z"], list.map(r => el("tr", {}, el("td", {}, r.label), el("td", {}, r.cross_date),
      el("td", { class: cls(r.a4) }, pc0(r.a4)), el("td", { class: cls(r.a13) }, pc0(r.a13)), el("td", {}, zpill(r.z))))) : el("div", { class: "muted" }, "None in the last two weeks.");
    const cross = el("div", { class: "grid2" }, card("Crossing up: 4-week average above the 13-week", crossRows(d.crossed_up || []),
      note("Attention turning up: the last month now runs above the last quarter. Like a moving-average crossover on a price chart, it confirms a turn rather than predicts it.")),
      card("Crossing down: 4-week average below the 13-week", crossRows(d.crossed_down || []), note("Attention turning down: the story is cooling.")));
    const tbl = R.length ? card("Every topic, fastest-rising first", table(["Topic", "Theme", "Region", "Views", "vs 4 wks", "vs 13 wks", "z", "Crossed"], R.map(r => el("tr", {},
      el("td", {}, r.label), el("td", {}, THEMES_LABEL[r.theme] || r.theme), el("td", {}, r.region), el("td", {}, views(r.views)), el("td", { class: cls(r.a4) }, pc0(r.a4)),
      el("td", { class: cls(r.a13) }, pc0(r.a13)), el("td", {}, zpill(r.z)), el("td", {}, r.cross ? (r.cross === "up" ? "▲ " : "▼ ") + r.cross_date : "–"))))) : null;
    return [head, zc, bars, cross, tbl];
  },
  async regions() {
    const d = await api("regions"), Rg = d.regions || {}, P = d.pairs || [];
    const order = ["global", "uk", "zh"].filter(k => Rg[k]);
    const head = card(null, followHead(order.map(k => ({ label: Rg[k].label + " (100 = usual)", points: Rg[k].points, fmt: f0, cls: icls }))),
      note("Each group's attention index: the geometric mean of its pages' weekly views, each against its own previous year."), asOf(d), stale(d));
    const reg = order.length ? card("Attention by language and region (weekly, 100 = each page's usual)", ...linesChart(order.map((k, i) => line({ name: Rg[k].label, points: Rg[k].points }, i)), f0, { hlines: [100], log: true }),
      note("English Wikipedia is read worldwide but most heavily from the US; the UK pages (Bank of England, Rightmove, Zoopla, stamp duty) are read mostly in Britain; Chinese Wikipedia is blocked in mainland China, so its readers are mainly in Hong Kong, Taiwan and abroad.")) : card("Regions", empty("pageviews"));
    const pairs = P.map(p => card(p.label + ": English vs Chinese Wikipedia", ...linesChart([{ name: "English", points: p.en, color: css("--s1") }, { name: "Chinese (zh)", points: p.zh, color: css("--s2") }], f0, { small: true, hlines: [100], log: true }),
      note("Both lines are attention indices (100 = usual for those pages), so they compare momentum, not size. Now: English " + f0(p.en_now) + ", Chinese " + f0(p.zh_now) + ".")));
    const T = d.topics || [];
    const tbl = T.length ? card("UK and Chinese-language pages", table(["Page", "Theme", "Region", "Article read", "Views (week)", "z", "vs 13 wks"], T.map(r => el("tr", {}, el("td", {}, r.label),
      el("td", {}, THEMES_LABEL[r.theme] || r.theme), el("td", {}, r.region), el("td", { class: "muted" }, r.title || "–"), el("td", {}, views(r.views)), el("td", {}, zpill(r.z)), el("td", { class: cls(r.a13) }, pc0(r.a13))))),
      note("Chinese titles are resolved by the server through Wikipedia's script conversion and redirects, so either simplified or traditional works in topics.csv.")) : null;
    const G = Object.entries(d.gtrends || {});
    const gt = card("Google Trends by region (hand-entered, 0–100)", ...(G.length ? linesChart(G.map(([k, p], i) => line({ name: k.replace("|", ", "), points: p }, i)), f0, { small: true })
      : [el("div", { class: "muted" }, "No regional points entered yet. Add rows to data/trends/gtrends.csv with series 'keyword|US', 'keyword|GB' or 'keyword|HK'.")]),
      note("Each row cites the Google Trends page it was read from; values are relative to the peak of that page's window and region, so compare shapes, not levels, across regions."), cite(d.gtrends_cited));
    return [head, reg, el("div", { class: "grid2" }, ...pairs), tbl, gt];
  },
  async reality() {
    const d = await api("reality"), T = d.themes || [];
    const live = T.filter(t => (t.attention || []).length);
    const head = card(null, followHead(live.slice(0, 6).map(t => ({ label: t.label + ": Wikipedia views a day (monthly average)", points: t.attention, fmt: views, delta: { lag: "1y" } }))),
      note("Attention per theme: the daily average of its English-Wikipedia topics' views, by month. Each card below sets it against that dashboard's own headline series."), asOf(d), stale(d));
    const lagTxt = s => s.best_lag == null ? "" : s.best_lag > 0 ? "attention moves " + s.best_lag + " month" + (s.best_lag > 1 ? "s" : "") + " before it" : s.best_lag < 0 ? "attention follows it by " + -s.best_lag + " month" + (s.best_lag < -1 ? "s" : "") : "they move in the same month";
    const cards = T.map(t => {
      const S = t.stats || {};
      const body = t.reality ? [...linesChart([{ name: "Attention (views a day, left)", points: t.attention, color: css("--s2"), axis: "left", fmt: views }, { name: t.series, points: t.reality, color: css("--s1"), fmt: gen }], gen, { log: t.log, leftLog: true }),
        el("div", { class: "kpis" }, kpi("Correlation of levels", S.level == null ? "–" : num(S.level, 2)), kpi("Of 3-month changes", S.change == null ? "–" : num(S.change, 2)),
          kpi("Best lag (|corr| " + (S.best_corr == null ? "–" : num(Math.abs(S.best_corr), 2)) + ")", S.best_lag == null ? "–" : (S.best_lag > 0 ? "+" : "") + S.best_lag + " m")),
        note("Monthly, " + (S.n || 0) + " months together. " + (lagTxt(S) ? "Changes line up best when " + lagTxt(S) + ". " : "") + "Correlation is not cause: a price spike makes news, and news sends people to look it up.")]
        : [el("div", { class: "muted" }, "The " + t.dashboard + " series is not available here: " + (t.error || "no data") + "."), t.paths && t.paths.length ? note("Series found in that payload: " + t.paths.join(", ")) : null];
      return card(t.label + " attention vs " + (t.series || t.dashboard), ...body, el("div", { class: "src", style: "margin-top:6px" }, "Series: ", link("/api/" + t.dashboard + (t.source ? t.source.replace(/^\/api\/[^/]+/, "") : ""), t.source),
        t.path ? " → " + t.path : "", t.note ? " · " + t.note : ""));
    });
    return [head, ...cards, card(null, note("The other series are read from this site's own API (" + d.site + ") by the background job twice a day; data/trends/reality.csv says which endpoint and which series. Nothing here imports the other dashboards."))];
  },
};
const THEMES_LABEL = { ai: "AI", bitcoin: "Bitcoin & crypto", pokemon: "Pokémon cards", robotaxi: "Robotaxis", housing: "Housing", climate: "Climate", prediction: "Prediction markets", space: "Space",
  chips: "Chips & compute", china: "China tech", longevity: "Longevity & GLP-1", rates: "Rates & economy", demographics: "Demographics" };
window.TOPIC = { VIEWS };
})();
