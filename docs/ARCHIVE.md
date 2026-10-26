# Month-end archive to OneDrive

On the last day of every month (UTC) the server builds one zip of every dashboard and copies it to
**OneDrive › Dashboards › Archive › YYYY-MM › dashboards-YYYY-MM-DD.zip**. It works the same way as the trading bot's backups:
rclone in the Docker image, the OneDrive login in one Railway variable (`app/cloud.py`, ported from the bot's `src/hl/cloud.py`).

Each zip holds, for every dashboard:
- every endpoint's data as the page shows it (`<slug>/<endpoint>.json`; `<endpoint>.error.txt` if a source was down that day)
- the daily "what changed since yesterday" snapshots and the comparison (`<slug>/daily/`, `<slug>/changes.json`)
- the dashboard's title, tabs and sources (`<slug>/meta.json`), the source health, and every hand-entered file in `data/`

New dashboards are included automatically. If the server was down on the last day, the missed month is copied the next time it
runs. A second copy is attached to the GitHub `archive` workflow run for 90 days.

## Set-up (once)

Use the same OneDrive login as the trading bot:

1. In Railway, open the **trading bot** service › **Variables** and copy the value of `ONEDRIVE_RCLONE_CONF`.
2. Open the **dashboards** service › **Variables** › **New variable**: name `ONEDRIVE_RCLONE_CONF`, paste the value, save.
   (If both services are in the same Railway project you can instead set the value to a reference,
   `${{<bot service name>.ONEDRIVE_RCLONE_CONF}}`, so there is one copy to update.)
3. Optional: `ONEDRIVE_FOLDER` (default `Dashboards`).

Railway redeploys. Within about ten minutes the first zip appears in `Dashboards/Archive/<this month>/`, and `/api/health` shows
it under `archive` (path, size, any error; never the token). After that, one zip per month end.

The paste can be any shape (one line, quoted, `\n` instead of line breaks): it is repaired before use. Each service keeps its own
refreshed token on its own volume. If Microsoft ever revokes the login (password change, "sign out everywhere"), both the bot and
this page report it: run `rclone config` on the Mac again, then `rclone config show onedrive`, and paste the new block into both.

The GitHub secret `RCLONE_CONFIG` is no longer used and can be deleted.
