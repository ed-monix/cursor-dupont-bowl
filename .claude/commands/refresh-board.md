---
description: Sync live stats, commit, let GitHub Pages rebuild the board
---

# /refresh-board — one live-board refresh pass

This is the **git** board, not a Claude artifact. Mechanical, no analysis.
Do **not** hang this on the Commissioner 9am routine. Live scoring is a
Cloud Agent sitting or `.github/workflows/gameday.yml` (~20 min).

One pass:

1. `git pull` `ed-monix/cursor-dupont-bowl`.
2. **Guard:** if only `teams/_template` exists, or there is no
   `state/schedule.json`, stop. No board until the season exists.
3. **Sync:** `python scripts/gameday_sync.py --season 2026`
   (stats + NFL schedule for the week in `state/ops/latest.json`).
   If Sleeper fails, say so and stop this pass.
4. **Commit live stats** if `state/weeks/` changed:
   `live: week NN stats`. Push. Do not commit `web/viewer.html`
   (gitignored).
5. **Pages** rebuilds from the template + committed state
   (`.github/workflows/viewer.yml`). Local preview:
   `python scripts/build_viewer.py --season 2026`.

Report one short line: the week synced and that Pages will pick it up.

To watch games from a Cloud Agent, re-run this command; do not `/loop`
on a Claude Artifact URL.
