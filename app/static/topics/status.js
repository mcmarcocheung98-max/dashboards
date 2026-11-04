// Dev Agent & Roadmap: tabs and cards. Data from /api/status/<notes|actions|pending|roadmap|log> (data/status/items.json); helpers from topic.html.
(() => {
const age = d => d == null ? "" : d === 0 ? "today" : d === 1 ? "1 day" : d + " days";
const P = { high: "--down", medium: "--sellt", low: "--muted" };
const pill = (text, color, solid) => el("span", { class: "pill", style: solid ? `background:var(${color});color:#fff` : `color:var(${color});border:1px solid var(${color})` }, text);
const ST = { in_progress: ["in progress", "--up"], waiting: ["waiting", "--sellt"], blocked: ["blocked", "--down"], done: ["done", "--muted"], planned: ["planned", "--muted"], proposed: ["needs your OK", "--sellt"] };
const owner = o => o === "parent" ? "parent session (shared code)" : o === "routine" ? "daily check routine" : o === "sessions" ? "dashboard sessions" : o && o.startsWith("session:") ? o.slice(8) + " session" : o || "";
const when = s => s ? new Date(s + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
const stamp = d => note("Last edited " + d.updated + ". The dev agent updates this file each morning after its check and its development work; the Check log tab shows what the check found.");
const REPO = "https://github.com/mcmarcocheung98-max/dashboards/commit/";
const BY = b => b === "agent" ? "dev agent" : b && b.startsWith("session:") ? b.slice(8) + " session" : b || "";
const proposalCard = r => el("div", { class: "card", style: "border-left:4px solid var(--sellt)" },
  el("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" }, el("div", { style: "font-weight:650;font-size:15px" }, r.title),
    el("div", { class: "chips" }, pill("needs your OK", "--sellt", true), el("span", { class: "pill" }, r.area), r.size ? el("span", { class: "pill" }, r.size) : null)),
  r.detail ? el("div", { style: "margin-top:6px;font-size:13.5px;color:var(--ink2)" }, r.detail) : null,
  r.why ? el("div", { class: "muted", style: "margin-top:4px;font-size:13px" }, "Why: " + r.why) : null,
  el("div", { class: "muted", style: "margin-top:6px;font-size:12.5px" }, "Reply to the agent in Claude: “approve " + r.id + "” or “skip " + r.id + "”, with any changes."));
function noteCard(n) {
  const ch = n.changes || [];
  return el("div", { class: "card" },
    el("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" }, el("div", { style: "font-weight:650;font-size:16px" }, n.title),
      el("div", { class: "chips" }, el("span", { class: "pill" }, when(n.date)), ch.length ? el("span", { class: "pill ok" }, ch.filter(c => c.commit).length + " shipped") : null)),
    n.summary ? el("div", { style: "margin-top:6px;font-size:14px;color:var(--ink2)" }, n.summary) : null,
    ch.length ? el("div", { style: "margin-top:8px" }, ...ch.map(c => el("div", { style: "padding:6px 0;border-top:1px solid var(--line);font-size:13.5px" },
      c.slug ? el("a", { href: "/" + c.slug + (c.tab ? "#" + c.tab : "") }, el("b", {}, c.dashboard || c.slug)) : el("b", {}, c.dashboard || "Site"), ": ", c.what,
      el("span", { class: "muted" }, (c.by ? " · " + BY(c.by) : "") + " "), c.commit ? el("a", { href: REPO + c.commit, class: "muted", style: "font-family:var(--mono,monospace);font-size:12px" }, c.commit.slice(0, 7)) : null))) : null,
    (n.next || []).length ? el("div", { style: "margin-top:8px;font-size:13.5px" }, el("b", {}, "Next: "), n.next.join(" · ")) : null,
    (n.asks || []).length ? el("div", { style: "margin-top:6px;font-size:13.5px;color:var(--down)" }, el("b", {}, "Needs you: "), n.asks.join(" · ")) : null);
}

function actionCard(a) {
  const open = a.status === "open";
  return el("div", { class: "card", style: `border-left:4px solid var(${open ? P[a.priority] : "--line"});${open ? "" : "opacity:.6"}` },
    el("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" },
      el("div", { style: "font-weight:650;font-size:15px" }, a.title),
      el("div", { class: "chips" }, pill(a.priority, P[a.priority], open), el("span", { class: "pill" }, a.area), open ? el("span", { class: "pill" }, "open " + age(a.age_days)) : el("span", { class: "pill ok" }, "done " + when(a.done)))),
    el("div", { class: "muted", style: "margin-top:6px;font-size:13.5px;color:var(--ink2)" }, a.detail),
    a.link && open ? el("div", { style: "margin-top:8px" }, link("Open where this is done ↗", a.link)) : null);
}

const VIEWS = {
  async notes() {
    const d = await api("notes"); const N = d.notes || [], P = d.proposals || [], L = d.last_check;
    return [card(null, el("div", { class: "kpis" }, kpi("Last note", N.length ? when(N[0].date) : "–"), kpi("Shipped, last 7 days", d.shipped_7d, d.shipped_7d ? "up" : ""),
        kpi("Waiting for your OK", P.length, P.length ? "down" : ""), kpi("Last check", L ? L.result.replace("_", " ") : "–", L ? (L.result === "ok" ? "up" : "down") : "")),
        note("The dev agent runs every morning at 07:39 London. It checks every dashboard, fixes what is broken, builds the next approved roadmap items (or hands them to the dashboard's own session), reviews one dashboard for improvements, and writes a note here. The morning email carries the latest note.")),
      P.length ? card("Waiting for your OK (" + P.length + ")", note("Bigger changes the agent will not make on its own: new tabs or dashboards, changed watch points, anything that changes how a page looks or what it claims."), ...P.map(proposalCard)) : null,
      ...N.map(noteCard), N.length ? null : card(null, note("No notes yet: the first one appears after the agent's next run.")), stamp(d)];
  },

  async actions() {
    const d = await api("actions"); const A = d.actions || [];
    const open = A.filter(a => a.status === "open"), done = A.filter(a => a.status !== "open");
    const by = p => open.filter(a => a.priority === p).length;
    const oldest = open.length ? Math.max(...open.map(a => a.age_days || 0)) : 0;
    const order = { high: 0, medium: 1, low: 2 };
    open.sort((a, b) => order[a.priority] - order[b.priority] || (b.age_days || 0) - (a.age_days || 0));
    return [card(null, el("div", { class: "kpis" }, kpi("Open, only you can do", open.length, open.length ? "down" : "up"), kpi("High priority", by("high"), by("high") ? "down" : ""), kpi("Medium / low", by("medium") + " / " + by("low")),
        kpi("Oldest open item", age(oldest)), kpi("Done", done.length, "up")), stamp(d)),
      ...open.map(actionCard),
      done.length ? card("Done", ...done.sort((a, b) => (b.done || "").localeCompare(a.done || "")).map(actionCard)) : null];
  },

  async pending() {
    const d = await api("pending"); const Pn = (d.pending || []).filter(p => p.status !== "done"), done = (d.pending || []).filter(p => p.status === "done");
    const groups = [...new Set(Pn.map(p => p.owner))];
    const row = p => el("div", { class: "card", style: `border-left:4px solid var(${(ST[p.status] || ST.waiting)[1]})` },
      el("div", { style: "display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline" }, el("div", { style: "font-weight:650;font-size:15px" }, p.title),
        el("div", { class: "chips" }, pill(...(ST[p.status] || ST.waiting), p.status === "in_progress"), el("span", { class: "pill" }, "since " + when(p.since) + " · " + age(p.age_days)))),
      el("div", { style: "margin-top:6px;font-size:13.5px;color:var(--ink2)" }, p.detail));
    return [card(null, el("div", { class: "kpis" }, kpi("In progress", Pn.filter(p => p.status === "in_progress").length, "up"), kpi("Waiting", Pn.filter(p => p.status === "waiting").length), kpi("Blocked", Pn.filter(p => p.status === "blocked").length, Pn.some(p => p.status === "blocked") ? "down" : ""), kpi("Owners", groups.length)),
        note("Work that is underway or queued, and who holds it. Items here need no action from you unless they say so; when one does, it also appears under Action items.")),
      ...groups.map(g => card("Held by: " + owner(g), ...Pn.filter(p => p.owner === g).sort((a, b) => (b.age_days || 0) - (a.age_days || 0)).map(row))),
      done.length ? card("Done", ...done.map(row)) : null, stamp(d)];
  },

  async roadmap() {
    const d = await api("roadmap"); const R = d.roadmap || [];
    const done = R.filter(r => r.status === "done"), total = R.length;
    const bar = el("div", { class: "bar", style: "height:10px;margin-top:8px" }, el("i", { style: `left:0;width:${done.length / total * 100}%;background:var(--up)` }));
    const col = (h, title, blurb) => { const items = R.filter(r => r.horizon === h && r.status !== "proposed"); return card(title + " · " + items.length, el("div", { class: "muted", style: "margin-bottom:8px" }, blurb),
      ...items.map(r => el("div", { style: "padding:8px 0;border-top:1px solid var(--line)" }, el("div", { style: "display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline" }, el("div", { style: "font-weight:600" }, r.title), el("div", { class: "chips" }, pill(...(ST[r.status] || ST.planned), r.status === "in_progress"), el("span", { class: "pill" }, r.area), r.by ? el("span", { class: "pill" }, BY(r.by)) : null)),
        r.detail ? el("div", { class: "muted", style: "margin-top:4px;font-size:13px" }, r.detail) : null))); };
    return [card("Roadmap: " + done.length + " of " + total + " done", bar, note("Now is being worked on or waits on one thing; Next follows when Now clears; Later waits on something outside the site, such as a data source that does not exist yet.")),
      R.some(r => r.status === "proposed") ? card("Proposed by the agent, waiting for your OK", ...R.filter(r => r.status === "proposed").map(proposalCard)) : null,
      el("div", { style: "display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))" }, col("now", "Now", "Underway, or unblocked by one action."), col("next", "Next", "Queued behind Now."), col("later", "Later", "Waits on something outside the site.")),
      card("Done", el("div", { class: "tl" }, ...done.sort((a, b) => (b.done || "").localeCompare(a.done || "")).flatMap(r => [el("div", { class: "d" }, when(r.done)), el("div", {}, el("b", {}, r.title), " ", el("span", { class: "pill" }, r.area))]))), stamp(d)];
  },

  async log() {
    const d = await api("log"); const L = (d.log || []).slice().reverse();
    const colour = r => r === "ok" ? "var(--up)" : r === "problems" ? "var(--down)" : "var(--muted)";
    const label = r => r === "ok" ? "all OK" : r === "problems" ? "problems" : "did not run";
    const strip = el("div", { style: "display:flex;gap:3px;flex-wrap:wrap;margin-top:6px" }, ...d.log.map(l => el("span", { title: l.date + ": " + label(l.result), style: `width:14px;height:14px;border-radius:3px;background:${colour(l.result)}` })));
    const rows = L.map(l => el("tr", {}, el("td", {}, l.date), el("td", {}, l.run), el("td", {}, el("span", { class: "pill", style: "color:" + colour(l.result) + ";border:1px solid " + colour(l.result) }, label(l.result))),
      el("td", { class: "wrap" }, l.summary, (l.fixed || []).length ? el("div", { class: "muted" }, "Fixed: " + l.fixed.join(", ")) : null, (l.handed || []).length ? el("div", { class: "muted" }, "Handed to: " + l.handed.join(", ")) : null)));
    const last = L[0];
    return [card(null, el("div", { class: "kpis" }, kpi("Last check", last ? last.date : "–"), kpi("Result", last ? label(last.result) : "–", last ? (last.result === "ok" ? "up" : "down") : ""), kpi("Runs logged", L.length), kpi("Runs with problems", L.filter(l => l.result === "problems").length)),
        strip, note("One square per run, oldest first: green all OK, red problems found, grey the check could not run. The routine runs at 07:39 London every day.")),
      card("Every run", el("div", { class: "scroll" }, el("table", {}, el("tr", {}, ...["Date", "Run", "Result", "What it found"].map(h => el("th", {}, h))), ...rows))), stamp(d)];
  },
};
window.TOPIC = { VIEWS };
})();
