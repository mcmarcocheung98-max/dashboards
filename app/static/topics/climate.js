// Climate Signals: tabs and cards. Data from /api/climate/<temperature|co2|sea|heat|costs>; helpers from topic.html.
(() => {
const DS = { "Copernicus ERA5": "--s1", "NASA GISTEMP": "--s2", "Met Office HadCRUT5": "--s4" };
const CITY = { "Hong Kong": "--s5", "London": "--s2", "New York": "--s1" };
const EMIT = { "China": "--s5", "United States": "--s1", "United Kingdom": "--s2", "Hong Kong": "--s6", "World": "--hold" };
const col = (map, k) => css(map[k] || "--hold");
const deg = (v, d = 2) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + " °C";
const sgn = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const ask = s => el("div", { class: "muted", style: "margin-top:6px" }, el("b", { style: "color:var(--ink2)" }, "Questions: "), s);
// plain figures under a timeline-following head (followHead from topic.html)
const fixed = (...k) => el("div", { class: "kpis", style: "margin-top:10px" }, ...k.filter(Boolean));
const downIf = lim => v => v >= lim ? "down" : "";
const doyFmt = v => MONTHS[new Date(Date.UTC(2001, 0, Math.max(1, Math.round(v)))).getUTCMonth()];
const DOY_TICKS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
// yearly points next to monthly charts: invisible monthly points let the shared date axis land on any month, not only on 1 January
const monthly = series => {
  const ts = series.flatMap(x => x.points || []).map(p => p[0]);
  if (!ts.length) return [];
  const out = [], a = new Date(Math.min(...ts) * 1000), b = Math.max(...ts);
  for (let y = a.getUTCFullYear(), m = a.getUTCMonth(); ; m++) { const t = Date.UTC(y, m, 1) / 1000; if (t > b) break; out.push(t); }
  return out;
};
const whyMissing = m => m && Object.keys(m).length ? el("div", { class: "muted" }, "Not available right now: " + Object.entries(m).map(([k, v]) => k + " (" + v + ")").join(", ") + ".") : null;
const handNote = cites => {
  const rows = Object.values(cites || {}).flat();
  return rows.length ? [cite(rows), note("Hand-entered rows marked 'verify' in data/climate/ were written from memory and are waiting to be checked against the cited page.")] : [];
};
// a day-of-year chart: chosen years as lines, averages as dashed grey lines
const doyLines = (years, bands, fmt, o = {}) => svgLines([
  ...bands.filter(b => b.points && b.points.length).map(b => ({ name: b.name, points: b.points, color: css(b.color || "--hold"), dashed: true, width: 1.5 })),
  ...Object.entries(years || {}).sort((a, b) => a[0] - b[0]).map(([y, pts], i, all) => ({ name: y, points: pts, width: i === all.length - 1 ? 3 : 1.5,
    color: i === all.length - 1 ? css("--down") : css(SERIES[i % SERIES.length]) }))], { xFmt: doyFmt, yFmt: fmt, xTicks: DOY_TICKS, h: 260, ...o });

const VIEWS = {
  async temperature() {
    const d = await api("temperature"), K = d.kpis || {}, m = K[d.main] || {}, dy = d.daily;
    const M = d.main, abs = { lag: "1y", abs: true, fmt: v => sgn(v, 2) + " °C" };
    const head = card(null, followHead([
      { label: "Monthly, " + (M || "–"), points: (d.monthly || {})[M] || [], fmt: v => deg(v), cls: downIf(1.5), delta: abs },
      { label: "12-month average", points: (d.rolling || {})[M] || [], fmt: v => deg(v), cls: downIf(1.5), delta: abs },
      { label: "Calendar-year average", points: (d.annual || {})[M] || [], fmt: v => deg(v), cls: downIf(1.5), delta: abs }],
      { latest: "Latest: " + (m.month || "–") }), fixed(
      kpi("Warming rate, last 20 years", m.rate20 == null ? "–" : sgn(m.rate20, 2) + " °C a decade", m.rate20 > 0.2 ? "down" : ""),
      kpi("30-year trend reaches 1.5 °C", m.cross == null ? "–" : String(Math.floor(m.cross))),
      kpi("Warmest year (" + (d.main || "") + ")", m.warmest ? m.warmest + " · " + deg(m.warmest_v) : "–"),
      dy ? kpi("Days above 1.5 °C in " + dy.now + " (ERA5)", dy.above15 + " of " + dy.days) : null), asOf(d), stale(d), whyMissing(d.missing));
    const mon = card("Global surface temperature, monthly, °C above 1850–1900",
      ...linesChart(Object.entries(d.monthly || {}).map(([k, p]) => ({ name: k, points: p, color: col(DS, k), width: 1.5 })), v => deg(v), { hlines: [1.5, 2] }),
      missing(d, "monthly", "Global temperature"),
      note("Each dataset rebased to 1850–1900: ERA5 with Copernicus's +0.88 °C offset from 1991–2020, HadCRUT5 directly, GISTEMP to its own 1880–1900 mean (it starts in 1880). The dashed lines are 1.5 °C and 2 °C. One hot month or year is not a breach of Paris: the threshold is a 20-year average."),
      ask("5 years: does the 2023–24 jump fade as El Niño passes, or does each new year settle a step higher? 10 years: at about 0.25 °C a decade, the 20-year average crosses 1.5 °C around 2030. 20 years: the 2 °C line, where coral reefs and some ice sheets reach their limits, is within reach by the 2040s at that pace."));
    const roll = card("12-month average, °C above 1850–1900",
      ...linesChart(Object.entries(d.rolling || {}).map(([k, p]) => ({ name: k, points: p, color: col(DS, k) })), v => deg(v), { small: true, hlines: [1.5] }),
      note("A rolling 12-month mean removes the seasons and most of the month-to-month noise; it shows how long the world has been above 1.5 °C at a stretch."),
      ask("5 years: how many 12-month windows stay above 1.5 °C? 10 years: does the gap between the three datasets (coverage of the Arctic, sea-ice areas) matter for when 1.5 is declared? 20 years: the 12-month mean took 40 years to go from 0.5 to 1.0 °C and about 15 to go from 1.0 to 1.5 °C."));
    const annS = Object.entries(d.annual || {}).map(([k, p]) => ({ name: k, points: p, color: col(DS, k) }));
    const ann = card("Yearly averages, °C above 1850–1900",
      ...linesChart(annS, v => deg(v), { small: true, hlines: [1.5], whitespace: monthly(annS) }),
      note("Calendar years with all twelve months. The warming rate in the KPIs is the straight-line slope over the last 20 of them; the 1.5 °C year is where the slope through the last 30 crosses the line, the same idea as the 20-year average the IPCC uses."),
      ask("5 years: is the rate still accelerating (about 0.18 °C a decade over 1970–2000, more since)? 10 years: aerosol cuts in China and in shipping (2020) unmasked some warming. How much? 20 years: every tenth of a degree adds measurably to heat extremes (Local heat tab)."));
    const daily = dy ? card("Copernicus ERA5, daily global temperature: " + dy.now + " against the warmest years, °C above 1850–1900",
      ...doyLines(dy.years, [{ name: "1991–2020 average", points: dy.normal, color: "--hold" }], v => deg(v), { hline: 1.5 }),
      note("ERA5 reanalysis, two days behind real time (latest " + dy.last + "). Thick red: this year. Dashed: the 1991–2020 average for each day, which is itself about 0.9 °C above pre-industrial."),
      ask("5 years: is this year tracking the record years or falling back toward the trend? 10 and 20 years: the 1991–2020 line will look cold within a decade. That is what a 0.25 °C-a-decade trend means.")) : card("Copernicus ERA5, daily", missing(d, "daily", "ERA5 daily series"));
    const src3 = (d.monthly || {})[d.main] || Object.values(d.monthly || {})[0] || [], byY = new Map();
    src3.forEach(([t, v]) => { const dt = new Date(t * 1000), y = dt.getUTCFullYear(); if (y >= 1950) { if (!byY.has(y)) byY.set(y, Array(12).fill(null)); byY.get(y)[dt.getUTCMonth()] = v; } });
    const warm3 = byY.size > 10 ? card("Warming in 3D: every month of every year since 1950" + (d.main ? " (" + d.main + ")" : ""),
      ...chart3d({ x: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], rows: [...byY.keys()].sort((a, b) => a - b).map(y => ({ name: String(y), z: byY.get(y) })), mode: "surface", zero: false, h: 480,
        zFmt: v => deg(v), xHead: "month", csvName: "warming 3d", note: "1950 at the front, this year at the back; January to December left to right. Drag to turn; hover for a month's anomaly." }),
      note("The same monthly anomalies as the first chart, laid out as a field: the ground rising towards the back is the warming, and the ridge of the last three years stands above everything before it. Ripples across a single year are that year's weather (El Niño, La Niña).")) : null;
    return [head, mon, roll, ann, warm3, daily].filter(Boolean);
  },

  async co2() {
    const d = await api("co2"), K = d.kpis || {}, E = d.emissions || {};
    const co2E = k => ((E[k] || {}).co2) || [];
    const head = card(null, followHead([
      { label: "Mauna Loa CO₂", points: (d.mlo || {}).average || [], fmt: v => num(v, 1) + " ppm", delta: { lag: "1y", abs: true, fmt: v => sgn(v, 2) + " ppm" } },
      { label: "Growth over 12 months (seasonally adjusted)", points: d.growth12 || [], fmt: v => sgn(v, 2) + " ppm", cls: v => K.growth10 == null ? "" : v > K.growth10 ? "down" : "up" },
      { label: "Global methane", points: (d.ch4 || {}).average || [], fmt: v => num(v, 0) + " ppb", delta: { lag: "1y", abs: true, fmt: v => sgn(v, 1) + " ppb" } },
      { label: "China fossil CO₂, Mt", points: co2E("China"), fmt: v => num(v, 0), delta: { lag: "1y" } },
      { label: "World fossil CO₂, Mt", points: co2E("World"), fmt: v => num(v, 0), delta: { lag: "1y" } }],
      { latest: "Latest: " + (K.month || "–") }), fixed(
      kpi("Average growth, last 10 years", K.growth10 == null ? "–" : sgn(K.growth10, 2) + " ppm a year"),
      kpi("Average growth in the 1960s", K.growth_1960s == null ? "–" : sgn(K.growth_1960s, 2) + " ppm a year"),
      kpi("China's share of world fossil CO₂ (" + (K.china_year || "–") + ")", K.china_share == null ? "–" : num(K.china_share, 0) + "%")), asOf(d), stale(d));
    const mlo = card("Atmospheric CO₂ at Mauna Loa, ppm (monthly)",
      ...linesChart([{ name: "Monthly mean", points: (d.mlo || {}).average || [], color: css("--s1"), width: 1.5 }, { name: "Seasonally adjusted", points: (d.mlo || {}).trend || [], color: css("--down") }], v => num(v, 1)),
      missing(d, "mlo", "Mauna Loa CO₂"),
      note("NOAA Global Monitoring Laboratory. The saw-tooth is the northern hemisphere's forests breathing; the trend line removes it. Pre-industrial was about 280 ppm; 350 ppm, passed in 1988, is often cited as the safe upper level."),
      ask("5 years: does 430 ppm become the yearly low? 10 years: does the curve bend at all as emissions plateau? CO₂ only stops rising when net emissions are near zero, not when they stop growing. 20 years: at today's pace, 450 ppm (roughly the 2 °C budget) arrives in the early 2030s."));
    const gr = card("How fast CO₂ is rising: ppm a year",
      ...linesChart([{ name: "Calendar-year growth (NOAA)", points: d.growth || [], color: css("--down"), bar: true },
        { name: "Last 12 months (seasonally adjusted)", points: d.growth12 || [], color: css("--ink2"), width: 1.5 }], v => sgn(v, 2), { small: true }),
      missing(d, "growth", "CO₂ growth"),
      note("Bars: NOAA's yearly increase at Mauna Loa. Line: the seasonally adjusted level against twelve months earlier. El Niño years (1998, 2016, 2024) spike because hot, dry forests take up less carbon."),
      ask("5 years: is growth back under 2.5 ppm a year after the 2024 record, or is the land sink weakening? 10 years: growth roughly doubled from the 1960s to the 2010s. 20 years: the CO₂ signal is the one place where emission cuts would show first: watch for a decade-average decline."));
    const ch4 = card("Global methane, ppb (monthly)",
      ...linesChart([{ name: "Monthly mean", points: (d.ch4 || {}).average || [], color: css("--s4"), width: 1.5 }, { name: "Trend", points: (d.ch4 || {}).trend || [], color: css("--down") }], v => num(v, 0), { small: true }),
      missing(d, "ch4", "Methane"),
      note("NOAA global marine surface average. Methane traps about 80 times more heat than CO₂ over 20 years, so its rise since 2007, and the record jumps in 2020–22, matter for near-term warming."),
      ask("5 years: does the Global Methane Pledge (−30% by 2030) show up as slower growth? 10 years: how much of the rise is wetlands responding to warming, not leaks or farms? 20 years: methane cuts are the fastest lever on the 1.5 °C line."));
    const emS = Object.entries(E).map(([k, v]) => ({ name: k, points: v.co2 || [], color: col(EMIT, k), dashed: k === "World" }));
    const pcS = Object.entries(E).map(([k, v]) => ({ name: k, points: v.per_capita || [], color: col(EMIT, k), dashed: k === "World" }));
    const em = card("Fossil CO₂ emissions, million tonnes a year (log scale)",
      ...linesChart(emS, v => num(v, 0), { log: true, whitespace: monthly(emS) }),
      missing(d, "emissions", "Emissions"),
      note("Global Carbon Budget (via Our World in Data), fossil fuels and cement, territorial. On a log scale equal slopes are equal growth rates. China passed the US in 2006 and now emits about a third of the world's total; the UK is back to 1850s levels; Hong Kong's are mainly power generation."),
      ask("5 years: has China's total peaked (it pledged before 2030)? 10 years: the US and UK have fallen since 2005 and 1990. Can the US keep falling? 20 years: world emissions need to roughly halve by 2040 for 1.5 °C; they are still near a record."));
    const pc = card("Fossil CO₂ per person, tonnes a year",
      ...linesChart(pcS, v => num(v, 1), { small: true, whitespace: monthly(pcS) }),
      note("Territorial emissions per resident. China's per person passed the UK's around 2015 and the EU's earlier; the US is still about twice China."),
      ask("5 years: where do China and the US meet? 10 and 20 years: the world average needs to fall towards 2 tonnes a person by 2050; every country here is above it."));
    return [head, mlo, gr, ch4, em, pc];
  },

  async sea() {
    const d = await api("sea"), K = d.kpis || {}, I = d.ice || {}, G = K.gauges || {};
    const ice = h => K[h] && K[h].v != null ? num(K[h].v, 2) + "m km² (" + sgn(K[h].v - K[h].recent, 2) + " vs 2011–20)" : "–";
    const Gp = d.gauges || {}, gk = pre => Object.keys(Gp).find(k => k.startsWith(pre));
    const head = card(null, followHead([
      { label: "Global sea level (satellites)", points: d.gmsl || [], fmt: v => sgn(v, 0) + " mm", delta: { lag: "1y", abs: true, fmt: v => sgn(v, 1) + " mm" } },
      ...["New York", "Hong Kong", "Newlyn"].filter(gk).map(p => ({ label: gk(p) + " tide gauge, vs 1991–2020", points: Gp[gk(p)], fmt: v => sgn(v, 0) + " mm" })),
      { label: "Arctic yearly minimum", points: (I.north || {}).min || [], fmt: v => num(v, 2) + "m km²" },
      { label: "Antarctic yearly minimum", points: (I.south || {}).min || [], fmt: v => num(v, 2) + "m km²" }],
      { latest: "Latest: " + (K.gmsl_date || "–") }), fixed(
      kpi("Global sea level since 1993", K.since1993 == null ? "–" : "+" + num(K.since1993, 0) + " mm"),
      kpi("Rise a year, last 10 years", K.rate10 == null ? "–" : num(K.rate10, 1) + " mm", K.rate10 > K.rate_prev10 ? "down" : ""),
      kpi("Rise a year, 10 years before", K.rate_prev10 == null ? "–" : num(K.rate_prev10, 1) + " mm"),
      kpi("Arctic sea ice, " + ((K.north || {}).date || "–"), ice("north"), K.north && K.north.v < K.north.recent ? "down" : "up"),
      kpi("Antarctic sea ice, " + ((K.south || {}).date || "–"), ice("south"), K.south && K.south.v < K.south.recent ? "down" : "up")), asOf(d), stale(d), whyMissing(d.missing));
    const gm = card("Global mean sea level from satellites, mm (1993 = 0, roughly)",
      ...linesChart([{ name: "Satellite altimetry (TOPEX, Jason, Sentinel-6)", points: d.gmsl || [], color: css("--s1"), width: 1.5 }], v => num(v, 0) + " mm"),
      missing(d, "gmsl", "Global sea level (NOAA STAR)"),
      note("NOAA STAR Laboratory for Satellite Altimetry, about every ten days, with the inverse-barometer and glacial-rebound corrections. The rate roughly doubled from about 2 mm a year in the 1990s to over 4 mm now, from melting ice sheets as well as warmer, expanding water."),
      ask("5 years: is the 10-year rate still rising (acceleration), or holding? 10 years: at 4–5 mm a year another 5 cm by 2035, which multiplies the frequency of today's flood levels. 20 years: whether Antarctica's contribution speeds up decides whether 2100 is 0.5 m or over 1 m."));
    const gg = card("Tide gauges: yearly mean sea level against 1991–2020, mm",
      ...linesChart(Object.entries(d.gauges || {}).map(([k, p]) => ({ name: k, points: p, color: k.startsWith("New York") ? css("--s1") : k.startsWith("Newlyn") ? css("--s2") : css("--s5") })), v => sgn(v, 0) + " mm", { small: true, hlines: [0] }),
      missing(d, "gauges", "PSMSL tide gauges"),
      el("div", { class: "muted" }, Object.entries(G).map(([k, v]) => k + ": " + (v.full == null ? "–" : num(v.full, 1)) + " mm a year over " + v.from + "–" + v.to + ", " + (v.since1993 == null ? "–" : num(v.since1993, 1)) + " since 1993").join(" · ")),
      note("PSMSL revised local reference (RLR) monthly means, averaged by year. A tide gauge measures sea level against the land, so it includes sinking ground: New York subsides a millimetre or two a year, which is why its rise outpaces the global mean."),
      ask("5 years: what will Hong Kong's next typhoon surge reach on top of today's higher baseline (Mangkhut 2018 was about 2.35 m)? 10 years: the Battery has risen about 30 cm since 1900; Sandy's flood would have been smaller without it. 20 years: does the Thames Barrier, built for a lower sea, close far more often?"));
    const mins = card("Sea-ice extent: the yearly minimum, million km²",
      ...linesChart([{ name: "Arctic (September)", points: (I.north || {}).min || [], color: css("--s1") }, { name: "Antarctic (February)", points: (I.south || {}).min || [], color: css("--s6") }], v => num(v, 2), { small: true }),
      missing(d, "ice", "NSIDC sea ice"),
      note("NSIDC Sea Ice Index v3 daily extent (area with at least 15% ice), the lowest day each year. The Arctic summer minimum has lost about 40% since 1979; Antarctica held steady until 2016, then fell to record lows in 2023."),
      ask("5 years: does Antarctic ice recover, or was 2016 a regime shift? 10 years: the Arctic minimum fell fast to 2012 and has plateaued since. 20 years: an ice-free Arctic September (under 1 million km²) is projected in most scenarios before 2050."));
    const dayCard = (h, label) => I[h] ? card(label + " sea-ice extent by day of year, million km²",
      ...doyLines(I[h].years, [{ name: "1981–2010 average", points: I[h].normal, color: "--hold" }, { name: "2011–2020 average", points: I[h].recent, color: "--muted" }], v => num(v, 1)),
      note("Thick red: this year. The two dashed lines are the averages the readings compare with: the 1981–2010 normal NSIDC uses, and the more recent 2011–2020."),
      ask(h === "north" ? "5 years: does this year sit below the 2011–2020 line for most of the year? 10 and 20 years: the winter maximum falls too, but more slowly; thinner ice melts faster each summer." :
        "5 years: is this year back near 1981–2010 or still in the post-2016 low band? 10 and 20 years: less Antarctic sea ice exposes ice shelves to waves and warmer water, which speeds the land ice behind them.")) : null;
    return [head, gm, gg, mins, dayCard("north", "Arctic"), dayCard("south", "Antarctic")].filter(Boolean);
  },

  async heat() {
    const d = await api("heat"), C = ["Hong Kong", "London", "New York"].filter(c => d[c]);
    const head = card(null, followHead([
      ...C.map(c => ({ label: c + ": hot days that year (≥" + d[c].threshold + " °C)", points: d[c].hot || [], fmt: v => num(v, 0), delta: { lag: "1y", abs: true, fmt: v => sgn(v, 0), text: "on the year before" } })),
      ...C.map(c => ({ label: c + ": share of daily records that were highs, 10 years", points: d[c].ratio || [], fmt: v => num(v, 0) + "%", cls: v => v > 50 ? "down" : v < 50 ? "up" : "" }))],
      { latest: "Latest: this year to date" }), fixed(
      ...C.map(c => kpi(c + ": hot days in " + (d[c].upto || "").slice(0, 4) + " to " + (d[c].upto || "–").slice(5) + " (≥" + d[c].threshold + " °C)", d[c].ytd == null ? "–" : d[c].ytd + (d[c].ytd_normal == null ? "" : " vs " + num(d[c].ytd_normal, 0) + " normal"),
        d[c].ytd_normal == null ? "" : d[c].ytd > d[c].ytd_normal ? "down" : d[c].ytd < d[c].ytd_normal ? "up" : "")),
      ...C.map(c => kpi(c + ": record highs : lows, last 365 days", d[c].rec365 && d[c].rec365[0] != null ? d[c].rec365[0] + " : " + (d[c].rec365[1] == null ? "–" : d[c].rec365[1]) : "–")),
      ...C.map(c => kpi(c + ": hottest day on record", d[c].hottest ? d[c].hottest.v + " °C (" + d[c].hottest.date + ")" : "–"))), asOf(d), stale(d),
      ...["Hong Kong", "London", "New York"].map(c => missing(d, c, c)));
    const series = key => C.map(c => ({ name: c, points: d[c][key] || [], color: col(CITY, c) }));
    const hot = card("Hot days a year: Hong Kong ≥33 °C, London ≥30 °C, New York ≥32.2 °C (90 °F)",
      ...linesChart(series("hot"), v => num(v, 0)),
      note("Each city's own line: the Hong Kong Observatory's 'very hot day', the 30 °C the Met Office uses for London, and New York's 90 °F. Hong Kong: the Observatory at Tsim Sha Tsui since 1884 (none 1940–46). London: Heathrow (GHCN-Daily from December 1948; NCEI's copy stopped in August 2025). New York: Central Park since 1869. The current year is counted to date."),
      ask("5 years: is Hong Kong's count of very hot days (about 10 a year in the 1990s, 40–50 recently) still climbing? 10 years: London's 30 °C days are rare enough that one heatwave decides the year: is the 10-year average rising? 20 years: urban heat adds to the global trend in all three cities, so local counts run ahead of the 1.5 °C story."));
    const nights = card("Hot nights a year: minimum ≥28 °C in Hong Kong, ≥24 °C in New York, ≥20 °C in London",
      ...linesChart(series("nights"), v => num(v, 0), { small: true }),
      note("Nights that do not cool down are what make heatwaves deadly. Hong Kong's 'hot night' is the Observatory's definition; London's 20 °C is the Met Office's 'tropical night'; New York's 24 °C (75 °F) is used here for comparison."),
      ask("5 years: are Hong Kong's hot nights (a few a year before 1990, 30+ now) still rising faster than its hot days? 10 years: does London get more than one tropical night a year on average? 20 years: hot nights grow faster than hot days in cities, as concrete stores the day's heat."));
    const rat = card("Share of daily records that were record highs, 10 years summed (%)",
      ...linesChart(series("ratio"), v => num(v, 0) + "%", { small: true, hlines: [50] }),
      note("A calendar-day record high is a day hotter than that date in every earlier year on the station's record (counted from 30 years after it starts); a record low, colder. In a stable climate the two balance (50%). For the US as a whole, highs outnumbered lows about 2 to 1 in the 2000s, i.e. about 67% (Meehl et al., 2009)."),
      ask("5 years: does every city stay above 50%? 10 years: is the share still rising, i.e. warming faster than records can adjust to it? 20 years: as the climate keeps warming, record lows become rare events in their own right."));
    const rec = card("Calendar-day record highs a year",
      ...linesChart(series("rec_hi"), v => num(v, 0), { small: true }),
      note("The raw count behind the ratio. A station with 150 years of data should set about 365 / 150 ≈ 2–3 record highs a year if nothing changed."),
      ask("5 years: is the count of record highs in each city above that 2–3 a year? 10 and 20 years: years with dozens of record highs (New York 2010, Hong Kong 2021–24) are the signature of a climate moving faster than its record book."));
    const mm = card("Average daily maximum, yearly, °C",
      ...linesChart([...series("mean_max"), { name: "London Heathrow (Met Office, from 1948)", points: d.heathrow || [], color: col(CITY, "London"), dashed: true }], v => num(v, 1) + " °C", { small: true }),
      missing(d, "heathrow", "Met Office Heathrow"),
      note("The mean of every day's maximum in each calendar year. Heathrow's Met Office monthly series (dashed) runs from 1948, before the GHCN record used above."),
      ask("5 years: is each city's average maximum still rising at about the global rate (0.25 °C a decade) or faster? 10 years: London has warmed by more than the global average since the 1980s. 20 years: a 1 °C warmer average shifts the whole distribution, so hot days multiply."));
    return [head, hot, nights, rat, rec, mm];
  },

  async costs() {
    const d = await api("costs"), K = d.kpis || {}, S = d.insured || {}, B = d.billions || {};
    const head = card(null, followHead([
      { label: "Insured nat-cat losses (Swiss Re), $bn", points: S["nat cat"] || [], fmt: v => usd(v, 0), delta: { lag: "1y" } },
      { label: "US billion-dollar disasters", points: B.count || [], fmt: v => num(v, 0), delta: { lag: "1y", abs: true, fmt: v => sgn(v, 0), text: "on the year before" } },
      { label: "China direct disaster losses, CN¥bn", points: d.china || [], fmt: v => num(v, 0), delta: { lag: "1y" } }],
      { latest: "Latest year" }), fixed(
      K.insured ? kpi("Insured nat-cat losses " + K.insured.year + " (Swiss Re)", usd(K.insured.v) + "bn", K.insured.v > K.insured.trend ? "down" : "up") : null,
      d.insured_growth != null ? kpi("Trend growth of insured losses", sgn(d.insured_growth, 1) + "% a year") : null,
      K.billions ? kpi("US billion-dollar disasters " + K.billions.year, K.billions.n + " (10-yr avg " + num(K.billions.avg10, 1) + ")", K.billions.n > K.billions.avg10 ? "down" : "up") : null,
      K.billions ? kpi("Average a year in the 1980s", num(K.billions.avg_1980s, 1)) : null,
      K.china ? kpi("China direct disaster losses " + K.china.year, "CN¥" + num(K.china.v, 0) + "bn", K.china.v > K.china.avg5 ? "down" : "up") : null), stale(d));
    const ins = card("Global insured losses from natural catastrophes, $bn a year (Swiss Re sigma)",
      ...linesChart([{ name: "Natural catastrophes", points: S["nat cat"] || [], color: css("--down"), bar: true }, { name: "All insured losses (incl. man-made)", points: S.total || [], color: css("--ink2"), width: 1.5 },
        { name: "Log-linear trend", points: S.trend || [], color: css("--hold"), dashed: true }], v => usd(v) + "bn"),
      missing(d, "insured", "Swiss Re figures"),
      note("Nominal dollars as Swiss Re first reported them each year (hand-entered). Losses grow with prices, more property in exposed places and the weather. Swiss Re puts the long-run real trend at 5–7% a year. 'Secondary perils' (floods, hail, wildfire, severe storms) now cause most of it rather than single hurricanes."),
      ask("5 years: is $150bn a year the new normal, as Swiss Re projects? 10 years: insured losses roughly doubled each decade; does that hold? 20 years: when insurers pull out of areas (California, Florida), losses shift from insurers to governments and homeowners, so insured figures can undercount."));
    const bd = card("US billion-dollar weather and climate disasters a year (NOAA NCEI, CPI-adjusted)",
      ...linesChart([{ name: "Events", points: B.count || [], color: css("--s1"), bar: true }, ...(B.cost && B.cost.length ? [{ name: "Cost, $bn (CPI-adjusted)", points: B.cost, color: css("--down"), axis: "left", fmt: v => usd(v) + "bn" }] : [])], v => num(v, 0), { small: !B.cost || !B.cost.length }),
      missing(d, "billions", "Billion-dollar disasters"),
      note("Events costing at least $1bn in today's dollars. NOAA stopped the series after 2024 (counts from " + (d.billions_from === "hand-entered" ? "the hand-entered file" : "NCEI's archive file") + "). Part of the rise is more property in harm's way, not only more extreme weather."),
      ask("5 years: does anyone keep the count going (Climate Central has picked it up)? 10 years: the 2020–24 average was about 23 a year, against about 3 in the 1980s. 20 years: severe convective storms (hail, tornadoes) are now most events; they are also the hardest to model and insure."));
    const cn = card("China: direct economic losses from natural disasters, CN¥bn a year (MEM)",
      ...linesChart([{ name: "Direct economic losses", points: d.china || [], color: col(EMIT, "China"), bar: true }], v => num(v, 0), { small: true }),
      missing(d, "china", "China losses"),
      note("Ministry of Emergency Management's year-end disaster summary (hand-entered). Economic losses, mostly uninsured: insurance covers a small share in China, so Swiss Re's insured figures miss most of it."),
      ask("5 years: does the 2021 Henan and 2023 Hebei flood pattern repeat, as rainfall extremes intensify? 10 years: losses as a share of GDP have fallen as protection improved. Does that continue? 20 years: how much of China's coastal economy sits below projected 2050 flood levels?"));
    const ev = card("Notable events: US, UK, Hong Kong, China",
      el("div", { class: "tl" }, ...(d.events || []).flatMap(e => [el("div", { class: "d" }, e.date + " · " + e.place), el("div", {}, link(e.event, e.source), e.note ? el("span", { class: "muted" }, " (" + e.note + ")") : null)])),
      note("The events behind the numbers. Add a row to data/climate/events.csv when one happens."), ...handNote(d.cites));
    return [head, ins, bd, cn, ev];
  },
};
window.TOPIC = { VIEWS };
})();
