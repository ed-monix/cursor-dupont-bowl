# Viewer

`viewer.template.html` is the board. `scripts/build_viewer.py` injects
committed state at `/*__LEAGUE_DATA__*/`.

GitHub Pages is **Deploy from a branch → main → /**. The site root is
the committed `index.html` (plus `.nojekyll` so Jekyll does not eat it).
`viewer.yml` rebuilds that file on push. `web/viewer.html` is a local
preview and stays gitignored.

Live scoring cron lives in `.github/workflows/gameday.yml`, not Scout.
