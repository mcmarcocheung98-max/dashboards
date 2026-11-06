// Graphify Map: tabs and cards. Data from /api/graphify/<map|savings|usage> (committed exports, see data/graphify/README.md); helpers from topic.html.
// Two live force-directed canvases (the cluster sky and the explorer) are drawn by hand here: no chart library suits a graph.
(() => {
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const n0 = v => v == null ? "–" : num(v, 0);
let MAP = null, SAV = null, pendingNode = null, pendingCluster = null;
const data = async () => { MAP = MAP || await api("map"); return MAP; };
const savings = async () => { SAV = SAV || await api("savings"); return SAV; };

// styles for this page only, injected once (the shell's stylesheet has no graph widgets)
if (!document.getElementById("gfy-css")) document.head.append(el("style", { id: "gfy-css" }, `
  .gfy-stage { position: relative; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: radial-gradient(900px 420px at 50% 0%, color-mix(in srgb, var(--accent) 14%, var(--surface)) 0%, var(--surface) 60%); }
  .gfy-stage canvas { display: block; width: 100%; cursor: grab; touch-action: none; }
  .gfy-hud { position: absolute; left: 10px; top: 10px; right: 10px; display: flex; flex-wrap: wrap; gap: 5px; pointer-events: none; }
  .gfy-hud button { pointer-events: auto; font: 11.5px ui-monospace, Menlo, monospace; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); background: color-mix(in srgb, var(--surface) 85%, transparent); color: var(--ink2); cursor: pointer; }
  .gfy-hud button.on { border-color: var(--accent); color: var(--accent); }
  .gfy-hud i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: 1px; }
  .gfy-hint { position: absolute; right: 10px; bottom: 8px; font-size: 11.5px; color: var(--muted); background: color-mix(in srgb, var(--surface) 85%, transparent); padding: 3px 8px; border-radius: 999px; }
  .gfy-tip { position: absolute; pointer-events: none; display: none; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 6px 9px; font-size: 12.5px; max-width: 260px; box-shadow: 0 8px 24px rgba(0,0,0,.25); }
  .gfy-members { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px; margin-top: 8px; }
  .gfy-members button { display: flex; justify-content: space-between; gap: 8px; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); font: inherit; font-size: 13px; cursor: pointer; min-width: 0; text-align: left; }
  .gfy-members button:hover { border-color: var(--accent); } .gfy-members button span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .gfy-members b { color: var(--accent); font-variant-numeric: tabular-nums; }
  .gfy-big { font-size: clamp(34px, 6vw, 56px); font-weight: 700; letter-spacing: -.02em; line-height: 1; color: var(--up); font-variant-numeric: tabular-nums; }
  .gfy-race { display: grid; gap: 10px; } .gfy-race .row { display: grid; gap: 4px; } .gfy-race .q { font-size: 13px; }
  .gfy-race .tr { position: relative; height: 18px; border-radius: 6px; background: var(--chip); overflow: hidden; }
  .gfy-race .tr i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; width: 0; transition: width 1.3s cubic-bezier(.2,.8,.2,1); }
  .gfy-race .tr i.naive { background: color-mix(in srgb, var(--down) 55%, var(--chip)); } .gfy-race .tr i.graph { background: var(--up); box-shadow: 0 0 10px color-mix(in srgb, var(--up) 60%, transparent); }
  .gfy-race .tr span { position: absolute; right: 8px; top: 0; line-height: 18px; font-size: 11.5px; font-variant-numeric: tabular-nums; color: var(--ink2); }
  .gfy-race .tr i.graph + span { color: var(--up); font-weight: 600; }
  .gfy-slider { display: grid; grid-template-columns: 1fr auto; gap: 8px 14px; align-items: center; font-size: 13px; } .gfy-slider input[type=range] { width: 100%; accent-color: var(--accent); }
  .gfy-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
  .gfy-step { border: 1px solid var(--line); border-radius: 10px; padding: 12px; background: var(--bg); min-width: 0; } .gfy-step .n { font-size: 11px; color: var(--muted); font-family: ui-monospace, Menlo, monospace; }
  .gfy-step .fig { font-size: 24px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; margin-top: 6px; }
  .gfy-flow { height: 5px; border-radius: 3px; margin: 10px 0 4px; background: repeating-linear-gradient(90deg, var(--accent) 0 16px, transparent 16px 32px); opacity: .6; animation: gfyflow 1.4s linear infinite; }
  @keyframes gfyflow { from { background-position: 0 0; } to { background-position: 32px 0; } }
  .gfy-bar { display: grid; grid-template-columns: 140px 1fr 50px; gap: 8px; align-items: center; padding: 2px 4px; border-radius: 6px; cursor: pointer; font-size: 12.5px; }
  .gfy-bar:hover, .gfy-bar.on { background: var(--chip); } .gfy-bar .tr { height: 10px; background: var(--chip); border-radius: 5px; overflow: hidden; }
  .gfy-bar .tr i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--accent), var(--s4)); transition: width 1.1s ease; border-radius: 5px; }
  .gfy-bar .nm { font-family: ui-monospace, Menlo, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .gfy-bar .v { text-align: right; font-variant-numeric: tabular-nums; }
  .gfy-spoke { width: 100%; height: auto; display: block; } .gfy-spoke text { font: 10.5px ui-monospace, Menlo, monospace; fill: var(--ink2); }
  .gfy-stack { display: flex; height: 22px; border-radius: 6px; overflow: hidden; border: 1px solid var(--line); } .gfy-stack div { transition: flex 1.2s ease; }
  .gfy-sur { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--bg); min-width: 0; font-size: 13px; }
  .gfy-sur .r { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: var(--s2); } .gfy-sur .f { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gfy-explore { display: grid; grid-template-columns: 300px 1fr; gap: 12px; } @media (max-width: 860px) { .gfy-explore { grid-template-columns: 1fr; } }
  .gfy-explore input { width: 100%; font: 14px ui-monospace, Menlo, monospace; padding: 9px 11px; border-radius: 10px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); }
  .gfy-res { display: grid; gap: 3px; margin-top: 6px; max-height: 300px; overflow: auto; } .gfy-res button { text-align: left; font: 13px inherit; font-family: inherit; padding: 7px 9px; border-radius: 8px; border: 1px solid transparent; background: transparent; color: var(--ink); cursor: pointer; min-width: 0; }
  .gfy-res button:hover, .gfy-res button.on { background: var(--chip); border-color: var(--line); } .gfy-res small { display: block; font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gfy-info { position: absolute; left: 10px; top: 8px; right: 10px; display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12.5px; pointer-events: none; } .gfy-info code { color: var(--muted); font-size: 11.5px; }
  .gfy-cmd { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px; background: var(--bg); margin-top: 8px; min-width: 0; }
  .gfy-cmd code { display: block; overflow-x: auto; white-space: pre; color: var(--accent); font-size: 12.5px; } .gfy-cmd .w { font-size: 12.5px; color: var(--muted); }
  @media (prefers-reduced-motion: reduce) { .gfy-flow { animation: none; } .gfy-race .tr i, .gfy-bar .tr i, .gfy-stack div { transition: none; } }
`));

// colours: one hue per dashboard, shared code and tests in the accent
const HUE = { housing: 150, ai: 200, ai_jobs: 200, ai_adoption: 200, robotaxi: 28, robotaxi_energy: 28, btc_cycles: 42, btc_flows: 42, _coin_page: 42, altcoins: 60, _signals: 60, _unlocks: 60, _volume_zones: 60, memecoins: 75,
  compute_chips: 260, china_us_tech: 330, demographics: 95, debt_rates: 180, climate: 120, longevity: 300, space: 225, pokemon_cards: 10, prediction_markets: 275, trends: 245, nba_odds: 350, nba_sim: 350, graphify_map: 165, graphify: 165 };
const GROUP = { ai_jobs: "ai", ai_adoption: "ai", robotaxi_energy: "robotaxi", btc_flows: "btc_cycles", _coin_page: "btc_cycles", _signals: "altcoins", _unlocks: "altcoins", _volume_zones: "altcoins", nba_sim: "nba_odds", graphify_map: "graphify" };
const group = d => HUE[d] == null ? "shared" : (GROUP[d] || d);
const col = (d, l = 58, a = 1) => group(d) === "shared" ? `hsla(165, 70%, ${l}%, ${a})` : `hsla(${HUE[d]}, 75%, ${l}%, ${a})`;
const dark = () => getComputedStyle(document.body).backgroundColor.match(/\d+/g).slice(0, 3).reduce((s, v) => s + +v, 0) < 380;

// ---------- a small force layout; the sky (clusters) and the explorer (one neighbourhood) both use it
function forceSim(canvas, opts) {
  const ctx = canvas.getContext("2d"); let W = 0, H = 0;
  let nodes = [], links = [], alpha = 1, hover = null, drag = null, pan = { x: 0, y: 0 }, zoom = 1, raf = null, parts = [];
  const o = Object.assign({ charge: 1, linkDist: 80, gravity: .05, particles: true, labels: "big", onHover() {}, onClick() {} }, opts);
  const size = () => { const r = canvas.getBoundingClientRect(); const dpr = Math.min(2, devicePixelRatio || 1); W = r.width; H = r.height; canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
  function set(ns, ls) {
    nodes = ns; alpha = 1; hover = null; pan = { x: 0, y: 0 }; zoom = 1;
    const R = Math.min(W, H) * .38;
    ns.forEach((n, i) => { const a = i / ns.length * Math.PI * 2; n.x = W / 2 + Math.cos(a) * R * (.6 + Math.random() * .5); n.y = H / 2 + Math.sin(a) * R * (.6 + Math.random() * .5); n.vx = n.vy = 0; });
    const by = new Map(ns.map(n => [n.id, n])); links = ls.map(l => ({ a: by.get(l.a), b: by.get(l.b), w: l.w || 1 })).filter(l => l.a && l.b);
    parts = links.filter(l => l.w >= 3).slice(0, 200).map(l => ({ l, t: Math.random(), s: .003 + Math.random() * .004 }));
    if (!raf) loop();
  }
  function tick() {
    const k = alpha; if (k < .003 && !drag) return;
    for (let i = 0; i < nodes.length; i++) { const a = nodes[i]; for (let j = i + 1; j < nodes.length; j++) { const b = nodes[j]; let dx = b.x - a.x, dy = b.y - a.y; const d2 = dx * dx + dy * dy + .01; if (d2 > 90000) continue; const f = o.charge * 1400 * k / d2, d = Math.sqrt(d2); dx /= d; dy /= d; a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f; } }
    for (const l of links) { let dx = l.b.x - l.a.x, dy = l.b.y - l.a.y; const d = Math.hypot(dx, dy) + .01, want = o.linkDist * (1 - Math.min(.5, l.w / 40)), f = (d - want) / d * .05 * k; dx *= f; dy *= f; l.a.vx += dx; l.a.vy += dy; l.b.vx -= dx; l.b.vy -= dy; }
    for (const n of nodes) { if (n === drag) continue; n.vx += (W / 2 - n.x) * o.gravity * k; n.vy += (H / 2 - n.y) * o.gravity * k; n.vx *= .82; n.vy *= .82; n.x += n.vx; n.y += n.vy; }
    alpha = Math.max(reduced ? 0 : .01, alpha * .985);
  }
  function draw() {
    const isDark = dark(), ink = isDark ? "233,237,247" : "20,20,19", line = isDark ? "140,160,200" : "80,90,120";
    ctx.clearRect(0, 0, W, H); ctx.save(); ctx.translate(pan.x, pan.y); ctx.scale(zoom, zoom);
    const hi = hover ? new Set([hover, ...links.filter(l => l.a === hover || l.b === hover).map(l => l.a === hover ? l.b : l.a)]) : null;
    for (const l of links) { const on = hi && (l.a === hover || l.b === hover); ctx.strokeStyle = on ? css("--accent") : `rgba(${line},${hi ? .06 : Math.min(.5, .1 + l.w / 30)})`; ctx.lineWidth = on ? 1.6 : Math.min(3, .5 + l.w / 12); ctx.beginPath(); ctx.moveTo(l.a.x, l.a.y); ctx.lineTo(l.b.x, l.b.y); ctx.stroke(); }
    if (o.particles && !reduced) { ctx.fillStyle = css("--accent"); for (const p of parts) { p.t += p.s; if (p.t > 1) p.t = 0; ctx.beginPath(); ctx.arc(p.l.a.x + (p.l.b.x - p.l.a.x) * p.t, p.l.a.y + (p.l.b.y - p.l.a.y) * p.t, 1.6, 0, 7); ctx.fill(); } }
    for (const n of nodes) { const dim = hi && !hi.has(n); ctx.globalAlpha = dim ? .25 : 1;
      if (!dim) { const g = ctx.createRadialGradient(n.x, n.y, n.r * .2, n.x, n.y, n.r * 2.6); g.addColorStop(0, col(n.g, 58, .45)); g.addColorStop(1, col(n.g, 58, 0)); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 2.6, 0, 7); ctx.fill(); }
      ctx.fillStyle = col(n.g, n === hover ? 72 : isDark ? 60 : 45); ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
      if (o.labels === "all" || (o.labels === "big" && n.r >= 9) || n === hover || (hi && hi.has(n))) { ctx.font = `${n === hover ? 600 : 500} ${n === hover ? 12.5 : 11}px system-ui, sans-serif`; ctx.fillStyle = `rgba(${ink},${n === hover ? 1 : .85})`; ctx.textAlign = "center"; ctx.fillText(n.label.length > 28 ? n.label.slice(0, 27) + "…" : n.label, n.x, n.y + n.r + 13); } }
    ctx.restore();
  }
  function loop() { if (!canvas.isConnected) { raf = null; return; } tick(); draw(); raf = requestAnimationFrame(loop); }
  const at = ev => { const r = canvas.getBoundingClientRect(); const x = (ev.clientX - r.left - pan.x) / zoom, y = (ev.clientY - r.top - pan.y) / zoom; let best = null, bd = 1e9; for (const n of nodes) { const d = Math.hypot(n.x - x, n.y - y); if (d < Math.max(10, n.r + 4) && d < bd) { bd = d; best = n; } } return { x, y, n: best }; };
  let moved = false, last = null;
  canvas.addEventListener("pointerdown", ev => { const h = at(ev); moved = false; last = { x: ev.clientX, y: ev.clientY }; if (h.n) { drag = h.n; alpha = Math.max(alpha, .3); } canvas.setPointerCapture(ev.pointerId); });
  canvas.addEventListener("pointermove", ev => { const h = at(ev); if (last && ev.buttons) { moved = moved || Math.hypot(ev.clientX - last.x, ev.clientY - last.y) > 3; if (drag) { drag.x = h.x; drag.y = h.y; drag.vx = drag.vy = 0; } else { pan.x += ev.clientX - last.x; pan.y += ev.clientY - last.y; } last = { x: ev.clientX, y: ev.clientY }; } else { hover = h.n; o.onHover(h.n, ev); canvas.style.cursor = h.n ? "pointer" : "grab"; } });
  canvas.addEventListener("pointerup", ev => { if (!moved) { const h = at(ev); if (h.n) o.onClick(h.n); } drag = null; last = null; });
  canvas.addEventListener("pointerleave", () => { hover = null; o.onHover(null); });
  canvas.addEventListener("wheel", ev => { ev.preventDefault(); const r = canvas.getBoundingClientRect(); const mx = ev.clientX - r.left, my = ev.clientY - r.top, z = Math.min(3, Math.max(.4, zoom * (ev.deltaY < 0 ? 1.1 : .9))); pan.x = mx - (mx - pan.x) * z / zoom; pan.y = my - (my - pan.y) * z / zoom; zoom = z; }, { passive: false });
  new ResizeObserver(() => { size(); alpha = Math.max(alpha, .2); }).observe(canvas); size();
  return { set };
}

const cById = D => new Map(D.communities.map(c => [c.id, c]));
const goExplore = (nodeId, clusterId) => { pendingNode = nodeId || null; pendingCluster = clusterId ?? null; location.hash = "explore"; };

const VIEWS = {
  async map() {
    const D = await data(); const S = D.stats;
    const dashes = new Set(Object.keys(D.dashboards).map(group)); dashes.delete("shared");
    const head = card(null, el("div", { class: "kpis" }, kpi("Nodes: functions, classes, concepts", n0(S.nodes)), kpi("Links between them", n0(S.edges)), kpi("Clusters of related code", n0(S.communities)),
      kpi("Files read", n0(S.files)), kpi("Dashboards mapped", n0(dashes.size))), note("Built from commit " + D.built_at + ", exported " + D.exported + ". One dot per cluster below: drag it, hover for names, click to open one."));
    const canvas = el("canvas", { style: "height:clamp(360px,58vh,600px)", "aria-label": "Force-directed map of the code clusters" });
    const tip = el("div", { class: "gfy-tip" }), hud = el("div", { class: "gfy-hud" }), stage = el("div", { class: "gfy-stage" }, canvas, hud, el("div", { class: "gfy-hint" }, "drag · scroll to zoom · click a cluster"), tip);
    const panel = el("div", { style: "display:none" });
    const cn = D.communities.map(c => ({ id: c.id, label: c.name, r: 4 + Math.sqrt(c.size) * 1.7, g: c.dash, c }));
    const cl = D.comm_edges.map(e => ({ a: e.a, b: e.b, w: e.w }));
    const sim = forceSim(canvas, { charge: 1.1, linkDist: 70, labels: "big",
      onHover: (n, ev) => { if (!n) { tip.style.display = "none"; return; } const r = canvas.getBoundingClientRect(); tip.style.display = "block"; tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 270) + "px"; tip.style.top = Math.min(ev.clientY - r.top + 14, r.height - 80) + "px"; tip.replaceChildren(el("b", {}, n.label), el("div", { class: "muted" }, n.c.size + " nodes · " + group(n.c.dash).replace(/_/g, " ") + " · " + (n.c.files[0] || ""))); },
      onClick: n => open(n.c) });
    const groups = [...new Set(cn.map(n => group(n.g)))].sort((a, b) => (a === "shared" ? -1 : b === "shared" ? 1 : a.localeCompare(b))); let active = null;
    const chips = groups.map(g => el("button", { onclick: () => { active = active === g ? null : g; chips.forEach(c => c.classList.toggle("on", c.textContent.trim() === (active || "").replace(/_/g, " "))); const keep = active ? cn.filter(n => group(n.g) === active) : cn; const ids = new Set(keep.map(n => n.id)); sim.set(keep, cl.filter(e => ids.has(e.a) && ids.has(e.b))); } }, el("i", { style: "background:" + col(g === "shared" ? "shared" : g) }), g.replace(/_/g, " ")));
    hud.replaceChildren(...chips);
    function open(c) {
      panel.style.display = ""; panel.replaceChildren(card("Cluster " + c.id + ": " + c.name,
        el("div", { class: "muted" }, c.size + " nodes · mostly " + group(c.dash).replace(/_/g, " ") + " · " + Object.entries(c.types).map(([k, v]) => v + " " + k).join(", ")),
        el("div", { class: "chips", style: "margin:8px 0" }, ...c.files.map(f => el("span", { class: "pill" }, f))),
        el("div", { class: "muted" }, "Most connected members (click one to see its neighbourhood):"),
        el("div", { class: "gfy-members" }, ...c.top.map(t => el("button", { onclick: () => goExplore(t.id) }, el("span", {}, t.label), el("b", {}, t.deg)))),
        el("div", { style: "margin-top:10px;display:flex;gap:8px;flex-wrap:wrap" }, el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit;background:var(--accent);color:#fff", onclick: () => goExplore(null, c.id) }, "Explore this cluster"), el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: () => panel.style.display = "none" }, "Close"))));
      panel.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" });
    }
    setTimeout(() => sim.set(cn, cl), 0);
    return [head, card("The map", stage, note("Size is the number of nodes in the cluster; colour is the dashboard most of them belong to; a line is how many links cross between two clusters. Moving dots on the lines are those links. Shared code (the fetch, cache and chart helpers) sits in the middle because every dashboard reaches it.")), panel];
  },

  async savings() {
    const S = await savings(); const T = S.tasks, B = S.graphify_benchmark || {};
    const naive = T.reduce((s, t) => s + t.naive_tokens, 0), graph = T.reduce((s, t) => s + t.graph_tokens, 0);
    const avgPct = T.reduce((s, t) => s + (1 - t.graph_tokens / t.naive_tokens), 0) / T.length * 100;
    const big = el("div", { class: "gfy-big" }, avgPct.toFixed(1) + "%");
    const hero = card(null, el("div", { style: "display:grid;grid-template-columns:auto 1fr;gap:10px 24px;align-items:center;flex-wrap:wrap" }, big,
      el("div", {}, el("div", { style: "font-size:16px;font-weight:600" }, "of the tokens saved, on average, per question about this codebase"),
        el("div", { class: "muted" }, "Measured on " + T.length + " real tasks from this project: what a Claude session would read without the map (every file a search points to, read whole) against what graphify query returns."))),
      el("div", { class: "kpis", style: "margin-top:14px" }, kpi("Without the map, per task", n0(Math.round(naive / T.length)) + " tokens", "down"), kpi("With the map, per task", n0(Math.round(graph / T.length)) + " tokens", "up"),
        kpi("Across the " + T.length + " tasks", n0(naive - graph) + " tokens saved", "up"), kpi("graphify's own benchmark", B.reduction_x ? B.reduction_x + "× fewer than the whole repo" : "–")),
      note("graphify's benchmark reads the whole repository (" + n0(B.corpus_tokens) + " tokens) against an average query (" + n0(B.avg_query_tokens) + " tokens). The per-task figures above are stricter: they only count the files a search would have found."));
    // what it is worth: the reader sets the price and the pace
    const price = el("input", { type: "range", min: "0.25", max: "15", step: "0.25", value: "3", id: "gfy-price" }), pace = el("input", { type: "range", min: "5", max: "500", step: "5", value: "50", id: "gfy-pace" });
    const pl = el("span", { class: "mono" }), al = el("span", { class: "mono" }), out = el("div", { class: "kpis", style: "margin-top:10px" });
    const calc = () => { const p = +price.value, n = +pace.value; pl.textContent = "$" + p.toFixed(2) + " per million input tokens"; al.textContent = n + " tasks a day";
      const perTask = (naive - graph) / T.length; const day = perTask * n / 1e6 * p; out.replaceChildren(kpi("Saved per task", "$" + (perTask / 1e6 * p).toFixed(3)), kpi("Saved per day", "$" + day.toFixed(2), "up"), kpi("Saved per month (30 days)", "$" + (day * 30).toFixed(0), "up"), kpi("Tokens not sent per month", n0(Math.round(perTask * n * 30)))); };
    price.addEventListener("input", calc); pace.addEventListener("input", calc); calc();
    const worth = card("What that is worth to you", el("div", { class: "gfy-slider" }, el("label", { for: "gfy-price" }, "Input price of your model"), pl, price, el("span"), el("label", { for: "gfy-pace" }, "How often a session asks about the code"), al, pace, el("span")), out,
      note("Set the price to the model you run these sessions on. Only the tokens of the files read are counted; the tokens spent thinking are the same either way, so the real saving in money is this plus the time a session no longer spends reading."));
    // the race, task by task
    const maxN = Math.max(...T.map(t => t.naive_tokens));
    const rows = T.slice().sort((a, b) => b.naive_tokens - a.naive_tokens).map(t => { const nv = el("i", { class: "naive" }), gv = el("i", { class: "graph" });
      const row = el("div", { class: "row" }, el("div", { class: "q" }, t.task, " ", el("span", { class: "muted" }, "· " + t.files + " files a search would open")),
        el("div", { class: "tr" }, nv, el("span", {}, "without: " + n0(t.naive_tokens))), el("div", { class: "tr" }, gv, el("span", {}, "with the map: " + n0(t.graph_tokens) + " · " + ((1 - t.graph_tokens / t.naive_tokens) * 100).toFixed(1) + "% saved")));
      row.fill = () => { nv.style.width = t.naive_tokens / maxN * 100 + "%"; gv.style.width = Math.max(.8, t.graph_tokens / maxN * 100) + "%"; }; return row; });
    const race = card("Task by task: tokens without the map against tokens with it", el("div", { class: "gfy-race" }, ...rows), note("Each pair of bars is one question. The grey bar is every file a search for its keywords would open, read whole; the green bar is the graph's answer, capped at 1,500 tokens. The bars share one scale."));
    setTimeout(() => rows.forEach(r => r.fill()), reduced ? 0 : 150);
    const method = card("How this was measured", el("div", { class: "muted" }, S.method + " Measured " + S.measured + " over " + n0(S.repo_files) + " files (" + n0(S.repo_tokens) + " tokens of code and docs)."));
    return [hero, worth, race, method];
  },

  async usage() {
    const U = await api("usage"); const D = U.days || [];
    const t = d => Date.parse(d + "T00:00:00Z") / 1000, M = v => v == null ? "–" : num(v / 1e6, 1) + "m";
    const since = D.filter(x => x.date >= U.installed), last = D[D.length - 1] || {}, wk = D.slice(-7);
    const sum = (a, k) => a.reduce((s, x) => s + (x[k] || 0), 0);
    const savedAll = sum(since, "saved") + sum(since, "saved_est"), usedAll = sum(since, "total");
    const head = card(null, el("div", { class: "kpis" },
        kpi("Tokens used, " + (last.date || "latest day"), M(last.total)), kpi("Average a day, last 7 days", M(sum(wk, "total") / Math.max(1, wk.length))),
        kpi("Saved by graphify, last 7 days", M(sum(wk, "saved") + sum(wk, "saved_est")), "up"), kpi("Lookups counted since " + U.installed, n0(sum(since, "lookups"))),
        kpi("Saved since installed", M(savedAll), "up")),
      note("All tokens a session's model processed: new input, cache writes, cache reads (the conversation re-read on every turn, which is most of the total) and output. " +
        "Updated " + U.updated + "; the dev agent adds each day's figures every morning."));
    const used = card("Tokens used per day",
      ...linesChart([{ name: "All tokens", bar: true, color: css("--s1"), points: D.map(x => [t(x.date), x.total]) },
        { name: "New input and output (no cache)", axis: "left", color: css("--down"), points: D.map(x => [t(x.date), x.input + x.cache_write + x.output]) }], M),
      note("Bars: everything processed that day, right axis. Line: the part that is not a cache read, left axis. Days before the other sessions' totals were first collected show the dev agent session only."));
    const saved = card("Tokens saved by graphify per day",
      ...linesChart([{ name: "Saved, counted lookups", bar: true, color: css("--up"), points: D.filter(x => x.date >= U.installed).map(x => [t(x.date), x.saved]) },
        { name: "Saved, other sessions (estimated)", color: css("--sellt"), dashed: true, points: D.filter(x => x.date >= U.installed).map(x => [t(x.date), x.saved_est]) },
        { name: "Lookups counted", axis: "left", color: css("--s1"), points: D.filter(x => x.date >= U.installed).map(x => [t(x.date), x.lookups]), fmt: v => num(v, 0) }], M),
      note("Saved = lookups x " + n0(U.saving_per_lookup) + " tokens, the median saving per question in the benchmark on the Token savings tab (measured " + (U.saving_measured || "–") + "). " +
        "Lookups (graphify query, explain and path) are counted in the dev agent's own transcript; the other sessions' are estimated at its rate of " + U.lookups_per_million +
        " lookups per million tokens, so that line is an estimate. Conservative: a file not read also stays out of every later turn's cache reads, which this does not count."));
    const rows = (U.sessions || []).map(x => el("tr", {}, el("td", {}, x.session), el("td", {}, M(x.to_date == null ? x.total : x.to_date)), el("td", {}, x.cost_to_date == null ? "–" : "$" + num(x.cost_to_date, 0)),
      el("td", {}, M(x.total)), el("td", {}, x.last)));
    const table = card("By session", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Session", "Tokens since it started", "Cost at list price", "In the daily chart", "Last active"].map(h => el("th", {}, h))), ...rows)),
      note("dev-agent is this site's parent session (measured from its transcript). The dashboard sessions are measured from their running totals, collected each morning from " +
        "the day their first totals were recorded; a session idle for several days shows its whole gap on the day it next ran."));
    return [head, used, saved, table];
  },

  async how() {
    const D = await data(); const S = D.stats; const ast = S.types.code || 0;
    const steps = [["1 · Detect", "Walk the folder. Code, docs, papers, images and video each take their own route; CSV data files are skipped.", n0(S.files), "files found"],
      ["2 · Extract code", "Parse every .py and .js into functions, classes, calls and imports. Deterministic, no model, no key, about 20 seconds.", n0(ast), "code nodes"],
      ["3 · Extract docs", "Claude agents read the READMEs and docs in parallel and write concepts, sources and design reasons as nodes.", n0(S.nodes - ast), "doc & concept nodes"],
      ["4 · Build & cluster", "Merge both into one graph, then find communities: groups more linked to each other than to the rest.", n0(S.communities), "clusters"],
      ["5 · Report & query", "Name the clusters, find the god nodes and surprises, write GRAPH_REPORT.md, and answer graphify query.", n0(S.edges), "links to search"]];
    return [card("Five steps, no API key for the code", el("div", { class: "gfy-steps" }, ...steps.map(([h, p, v, l]) => el("div", { class: "gfy-step" }, el("div", { class: "n" }, "step " + h.split(" · ")[0]), el("div", { style: "font-weight:650;margin-top:2px" }, h.split(" · ")[1]), el("div", { class: "muted", style: "margin-top:4px;font-size:13px" }, p), el("div", { class: "fig" }, v), el("div", { class: "muted", style: "font-size:12px" }, l)))),
      el("div", { class: "gfy-flow", "aria-hidden": "true" }),
      note("This run: " + n0(S.conf.EXTRACTED) + " links read straight from the source, " + n0(S.conf.INFERRED || 0) + " inferred by a model and " + n0(S.conf.AMBIGUOUS || 0) + " flagged as unsure. Token cost of the code half: 0.")),
      card("Where it runs", el("div", { class: "muted" }, "Every Claude Code session on this repo installs graphify at start-up (the environment's setup script) and rebuilds the code map with scripts/graphify-setup.sh. CLAUDE.md tells the session to ask the map before it searches or reads files, and to run graphify update . after editing code. The documentation layer is added when /graphify runs in a session; this page is refreshed with scripts/graphify_export.py."))];
  },

  async gods() {
    const D = await data(); const C = cById(D); const gods = D.gods.slice(0, 12), maxd = gods[0].deg;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 520 440"); svg.setAttribute("class", "gfy-spoke"); svg.setAttribute("role", "img");
    const title = el("h2", {}, ""), noteEl = el("div", { class: "muted", style: "font-size:12.5px" });
    const rows = gods.map((g, i) => el("div", { class: "gfy-bar", tabindex: "0", role: "button", onclick: () => spoke(g, i), onkeydown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); spoke(g, i); } } }, el("div", { class: "nm", title: g.file }, g.label), el("div", { class: "tr" }, el("i")), el("div", { class: "v" }, n0(g.deg))));
    function spoke(g, i) {
      rows.forEach((r, j) => r.classList.toggle("on", i === j)); svg.replaceChildren(); title.textContent = g.label + " · " + g.file;
      const links = (D.godlinks[g.id] || []).slice(0, 18), cx = 260, cy = 210, R = 160, mk = (t, a) => { const e = document.createElementNS("http://www.w3.org/2000/svg", t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
      const maxn = Math.max(1, ...links.map(l => l.n));
      links.forEach((l, k) => { const a = -Math.PI / 2 + k / links.length * Math.PI * 2, x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R, c = C.get(l.c);
        const line = mk("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: col(c.dash, 55, .85), "stroke-width": 1 + l.n / maxn * 6, "stroke-linecap": "round" }); svg.append(line);
        if (!reduced) { line.setAttribute("stroke-dasharray", R); line.setAttribute("stroke-dashoffset", R); line.animate([{ strokeDashoffset: R }, { strokeDashoffset: 0 }], { duration: 700, delay: k * 40, fill: "forwards", easing: "ease-out" }); }
        svg.append(mk("circle", { cx: x, cy: y, r: 4 + Math.sqrt(c.size) * .7, fill: col(c.dash, 55) }));
        const t = mk("text", { x: x + Math.cos(a) * 14, y: y + Math.sin(a) * 14 + 4, "text-anchor": Math.cos(a) > .2 ? "start" : Math.cos(a) < -.2 ? "end" : "middle" }); t.textContent = (c.name.length > 22 ? c.name.slice(0, 21) + "…" : c.name) + " ·" + l.n; svg.append(t); });
      svg.append(mk("circle", { cx, cy, r: 16, fill: css("--accent") })); const t = mk("text", { x: cx, y: cy + 4, "text-anchor": "middle", style: "fill:#fff;font-weight:600" }); t.textContent = g.label.replace(/\(\)$/, ""); svg.append(t);
      noteEl.textContent = (D.godlinks[g.id] || []).length + " clusters link to it; line width is the number of links from that cluster.";
    }
    setTimeout(() => { rows.forEach((r, i) => r.querySelector("i").style.width = gods[i].deg / maxd * 100 + "%"); spoke(gods[0], 0); }, 50);
    return [card(null, el("div", { class: "kpis" }, kpi("Most connected", gods[0].label), kpi("Its links", n0(gods[0].deg)), kpi("Clusters reaching it", n0((D.godlinks[gods[0].id] || []).length))), note("These are the places where one change touches every dashboard: the shared helpers that round numbers, build chart series, download and cache.")),
      el("div", { class: "grid2" }, card("Most connected, by number of links", el("div", { style: "display:grid;gap:6px" }, ...rows)), card("Who reaches it", title, svg, noteEl))];
  },

  async audit() {
    const D = await data(); const S = D.stats; const rel = Object.entries(S.rel).sort((a, b) => b[1] - a[1]), total = rel.reduce((s, r) => s + r[1], 0);
    const cols = SERIES.map(css).concat(["#8a8984", "#c7408f"]);
    const stack = el("div", { class: "gfy-stack" }, ...rel.map(([k, v], i) => el("div", { style: `flex:${reduced ? v : 0.001};background:${cols[i % cols.length]}`, title: k + ": " + n0(v) })));
    setTimeout(() => [...stack.children].forEach((d, i) => d.style.flex = rel[i][1]), 50);
    const legend = el("div", { class: "legend" }, ...rel.map(([k, v], i) => el("span", {}, el("i", { class: "sw", style: "background:" + cols[i % cols.length] }), " " + k + " ", el("span", { class: "muted" }, n0(v) + " · " + Math.round(v / total * 100) + "%"))));
    const conf = [["EXTRACTED", S.conf.EXTRACTED || 0, "--up", "written in the source: a call, an import, a citation"], ["INFERRED", S.conf.INFERRED || 0, "--s2", "a model read two things and judged them related"], ["AMBIGUOUS", S.conf.AMBIGUOUS || 0, "--down", "the model was not sure, and said so"]];
    const meter = el("div", { style: "display:grid;gap:8px" }, ...conf.map(([k, v, c, w]) => { const i = el("i", { style: `display:block;height:100%;width:${reduced ? Math.max(.6, v / total * 100) : 0}%;background:var(${c});transition:width 1.2s ease` });
      setTimeout(() => i.style.width = Math.max(.6, v / total * 100) + "%", 60); return el("div", { style: "display:grid;grid-template-columns:100px 1fr 80px;gap:10px;align-items:center;font-size:13px" }, el("span", { class: "mono" }, k), el("div", { style: "height:10px;background:var(--chip);border-radius:5px;overflow:hidden", title: w }, i), el("span", { class: "mono", style: "text-align:right" }, n0(v) + " · " + (v / total * 100).toFixed(v / total < .01 ? 2 : 0) + "%")); }));
    return [el("div", { class: "grid2" }, card("Types of link", stack, legend, note("calls and contains come from the code's structure; references, rationale_for and shares_data_with mostly from the documentation layer.")),
      card("How sure each link is", meter, note("Every link says how it was found. " + n0(S.hyperedges) + " hyperedges group three or more nodes that form one idea" + (D.hyperedges.length ? ", for example " + D.hyperedges.slice(0, 2).map(h => h.label).join(" and ") : "") + "."))),
      card("Surprising connections: links across files that nobody wrote down", el("div", { class: "grid2" }, ...D.surprises.slice(0, 12).map(s => el("div", { class: "gfy-sur" }, el("div", { style: "display:flex;justify-content:space-between;gap:8px" }, el("span", { class: "r" }, s.rel.replace(/_/g, " ")), el("span", { class: "pill" }, s.conf + (s.score != null ? " " + s.score : ""))),
        el("div", { style: "font-weight:600;margin-top:4px" }, s.a), el("div", { class: "muted" }, "↕ " + s.b), el("div", { class: "f" }, s.fa + " → " + s.fb)))),
        note("Inferred by reading the docs and the code side by side: the same source used by several dashboards, or a guide describing code elsewhere. Leads to check, not facts."))];
  },

  async explore() {
    const D = await data(); const C = cById(D); const N = new Map(D.nodes.map(n => [n.id, n])); const adj = new Map();
    for (const [a, b] of D.edges) { (adj.get(a) || adj.set(a, []).get(a)).push(b); (adj.get(b) || adj.set(b, []).get(b)).push(a); }
    const dashOf = n => { const c = C.get(n.c); return c ? c.dash : "shared"; };
    const canvas = el("canvas", { style: "height:420px", "aria-label": "Neighbourhood of the selected node" }), info = el("div", { class: "gfy-info" });
    const q = el("input", { type: "search", placeholder: "Search " + n0(D.nodes.length) + " nodes… e.g. fetch, READINGS, Polymarket", "aria-label": "Search the graph", id: "gfy-q" }), res = el("div", { class: "gfy-res" });
    const sim = forceSim(canvas, { charge: .9, linkDist: 70, gravity: .06, labels: "all", particles: false, onClick: n => show(n.id) });
    function show(id) {
      const n = N.get(id); if (!n) return; const nb = [...new Set(adj.get(id) || [])].sort((a, b) => (N.get(b)?.d || 0) - (N.get(a)?.d || 0)).slice(0, 60); const ids = new Set([id, ...nb]);
      const ns = [...ids].map(i => N.get(i)).filter(Boolean).map(m => ({ id: m.id, label: m.l, r: m.id === id ? 14 : 4 + Math.sqrt(m.d) * .9, g: dashOf(m) }));
      const ls = [], seen = new Set(); for (const [a, b] of D.edges) if (ids.has(a) && ids.has(b)) { const k = a < b ? a + "|" + b : b + "|" + a; if (!seen.has(k)) { seen.add(k); ls.push({ a, b, w: a === id || b === id ? 4 : 1 }); } }
      sim.set(ns, ls); const c = C.get(n.c);
      info.replaceChildren(el("b", {}, n.l), el("code", {}, n.f + (n.loc ? ":" + n.loc : "")), el("span", {}, el("span", { class: "muted" }, "cluster "), c ? c.name : n.c), el("span", {}, el("span", { class: "muted" }, "links "), n.d), el("span", { class: "muted" }, "showing " + ns.length + " nodes"));
      [...res.children].forEach(b => b.classList.toggle("on", b.dataset.id === id));
    }
    function showCluster(cid) {
      const ms = D.nodes.filter(n => n.c === cid).sort((a, b) => b.d - a.d).slice(0, 110), ids = new Set(ms.map(m => m.id));
      const ls = [], seen = new Set(); for (const [a, b] of D.edges) if (ids.has(a) && ids.has(b)) { const k = a < b ? a + "|" + b : b + "|" + a; if (!seen.has(k)) { seen.add(k); ls.push({ a, b, w: 1 }); } }
      sim.set(ms.map(m => ({ id: m.id, label: m.l, r: 3 + Math.sqrt(m.d) * .9, g: dashOf(m) })), ls); const c = C.get(cid);
      info.replaceChildren(el("b", {}, c.name), el("span", { class: "muted" }, ms.length + " of " + c.size + " nodes · click a node to centre on it"));
    }
    function search(s) { s = s.trim().toLowerCase(); res.replaceChildren(); if (s.length < 2) return;
      const hits = D.nodes.filter(n => n.l.toLowerCase().includes(s)).sort((a, b) => (a.l.toLowerCase().startsWith(s) ? 0 : 1) - (b.l.toLowerCase().startsWith(s) ? 0 : 1) || b.d - a.d).slice(0, 12);
      res.replaceChildren(...hits.map(n => { const b = el("button", { onclick: () => show(n.id) }, n.l, " ", el("span", { class: "muted" }, n.d + " links"), el("small", {}, n.f + (n.loc ? ":" + n.loc : ""))); b.dataset.id = n.id; return b; }));
      if (!hits.length) res.append(el("div", { class: "muted", style: "padding:8px" }, "Nothing in the map matches that.")); }
    q.addEventListener("input", () => search(q.value));
    const tries = ["_r", "fetch", "followHead", "READINGS", "devig", "Polymarket", "heat score"];
    const tryRow = el("div", { class: "chips", style: "margin-top:8px" }, el("span", { class: "muted", style: "font-size:12.5px;align-self:center" }, "try:"), ...tries.map(t => el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: () => { q.value = t; search(t); const f = res.querySelector("button"); if (f) f.click(); } }, t)));
    setTimeout(() => { if (pendingCluster != null) { showCluster(pendingCluster); pendingCluster = null; } else { const id = pendingNode || (D.gods.find(g => N.has(g.id)) || {}).id; pendingNode = null; if (id) { q.value = N.get(id).l; search(N.get(id).l); show(id); } } }, 0);
    return [card("Find anything, see its neighbourhood", el("div", { class: "gfy-explore" }, el("div", {}, q, tryRow, res), el("div", { class: "gfy-stage" }, canvas, info)), note("Type a function, a source or a concept; the map shows the node and everything one step away, coloured by dashboard."))];
  },

  async use() {
    const cmds = [["graphify query \"how does the top card follow the timeline\"", "Ask a question; it walks the graph from the matching nodes and returns a small, scoped subgraph."],
      ["graphify explain \"fetch()\"", "A plain-language view of one node and its 20 most connected neighbours."], ["graphify path \"askPanel()\" \"ask()\"", "The shortest path between two things, e.g. a button on the page and the server code it reaches."],
      ["graphify update .", "Rebuild the code half of the map after editing code. No model, no key, about 20 seconds."], ["bash scripts/graphify-setup.sh", "What every session runs first: installs graphify if missing and builds graphify-out/."],
      ["python scripts/graphify_export.py --bench", "Refresh this page's data: the map summary and the token benchmark."]];
    return [card("The rule in CLAUDE.md", el("div", {}, "When looking for anything in this project, check graphify's map first; search or read files only for what the map does not answer. If graphify-out/ is missing, build it with scripts/graphify-setup.sh."),
      note("graphify is installed in every Claude Code session on this repo by the environment's setup script, and the daily check routine follows the same rule.")),
      card("Commands", ...cmds.map(([c, w]) => { const code = el("code", {}, c); const b = el("button", { class: "pill", style: "cursor:pointer;border:0;font:inherit", onclick: () => navigator.clipboard?.writeText(c).then(() => { b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy", 1200); }).catch(() => {}) }, "Copy"); return el("div", { class: "gfy-cmd" }, el("div", { style: "min-width:0" }, code, el("div", { class: "w" }, w)), b); }))];
  },
};
window.TOPIC = { VIEWS };
})();
