# Viewer

`viewer.template.html` is the board. `scripts/build_viewer.py` injects
committed state at `/*__LEAGUE_DATA__*/`.

GitHub Pages (`.github/workflows/viewer.yml`) publishes `_site/index.html`.
`viewer.html` is a local preview file and is gitignored.

Enable Pages: repo Settings → Pages → GitHub Actions.
