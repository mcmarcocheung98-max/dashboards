"""Daily source-health check: read /api/health on the live site and keep one GitHub issue in step with it.

Opens (or updates) the issue labelled 'source-health' when any source is past its threshold (a snapshot older than 3 days, or failing
for more than a day with nothing to fall back on); closes it with a comment when everything is healthy again. Uses the gh CLI."""
import json
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("DASHBOARDS_URL", "https://dashboards-production-bde6.up.railway.app").rstrip("/")
LABEL, TITLE = "source-health", "Dashboard data sources need attention"


def gh(*args, check=True):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check).stdout


def main() -> int:
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=60) as r:
            h = json.load(r)
    except Exception as e:
        body = f"Could not read {BASE}/api/health: {type(e).__name__}: {e}. The site may be down or redeploying."
        alerts = [("site", body)]
        h = None
    else:
        alerts = [(slug, f"- **{slug}** `{s['host']}`: {s['status']} since {s['since']} UTC ({s['days']} days){', ' + s['error'] if s['error'] else ''}")
                  for slug, d in h["dashboards"].items() for s in d["sources"] if s["alert"]]
    gh("label", "create", LABEL, "--color", "d73a4a", "--description", "Dashboard data source health", check=False)
    found = json.loads(gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1") or "[]")
    num = found[0]["number"] if found else None
    if alerts:
        text = f"Checked {h['checked'] if h else 'now'} on {BASE}.\n\n" + "\n".join(a[1] for a in alerts) + \
               "\n\nStale = the page shows the last good copy; failing = nothing to show. Each dashboard's README says where the source lives." \
               "\n\n---\n_Opened by the daily source-health workflow._"
        if num:
            gh("issue", "edit", str(num), "--body", text)
        else:
            gh("issue", "create", "--title", TITLE, "--label", LABEL, "--body", text)
        print(f"{len(alerts)} alert(s)")
    elif num:
        gh("issue", "close", str(num), "--comment", "All sources healthy again. Closed by the daily source-health workflow.")
        print("healthy: closed the issue")
    else:
        print("healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
