# Month-end archive to OneDrive

On the last day of every month (22:41 UTC) the `archive` workflow downloads `/api/archive.zip` from the live site and copies it to
**OneDrive › Dashboards › Archive › YYYY-MM › dashboards-YYYY-MM-DD.zip**. Each zip holds, for every dashboard:

- every endpoint's data as the page shows it (`<slug>/<endpoint>.json`; `<endpoint>.error.txt` if a source was down that day)
- the daily "what changed since yesterday" snapshots and the comparison (`<slug>/daily/`, `<slug>/changes.json`)
- the dashboard's title, tabs and sources (`<slug>/meta.json`), the source health, and every hand-entered file in `data/`

New dashboards are included automatically. The zip is also attached to the workflow run for 90 days.

## One-time setup (about 5 minutes)

1. Install rclone on your own computer: <https://rclone.org/install/> (on a Mac: `brew install rclone`).
2. Run `rclone config` → `n` (new remote) → name it **`onedrive`** → storage type **Microsoft OneDrive** → leave client id and
   secret blank → region **Microsoft Cloud Global** → answer **y** to "use web browser" and sign in to your Microsoft account →
   choose **OneDrive Personal or Business** → pick your drive → confirm.
3. Run `rclone config file`, open the file it names and copy everything in it.
4. On GitHub: repository **Settings › Secrets and variables › Actions › New repository secret**, name **`RCLONE_CONFIG`**, paste, save.
5. Test it: **Actions › archive › Run workflow**. The zip appears in OneDrive under `Dashboards/Archive/<this month>/`.

rclone refreshes the OneDrive sign-in by itself. If OneDrive ever revokes it (a password change, or months without a run), the
workflow fails with an rclone authentication error: repeat steps 2–4.

To use another folder, change `DEST` at the top of `.github/workflows/archive.yml`.
