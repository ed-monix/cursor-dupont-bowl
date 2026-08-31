#!/usr/bin/env python3
"""scoreboard.py — live game-day matchup board on http://localhost:8080

BUILD AGENT: implement per TASKS.md 4.1. Spec:

- Single-file Flask app, no framework/build step. `pip install flask requests`.
- Background thread polls Sleeper weekly stats every 45s on game days
  (any rostered starter's NFL team plays today), every 10 min otherwise.
  Isolate the fetch behind `fetch_week_stats(season, week) -> dict` so the
  source can be swapped if the unofficial endpoint changes.
- Scoring: reuse scripts/lib/scoring.py against config/scoring.json.
- Route "/": current week's 6 matchups from state/schedule.json +
  teams/*/roster.json. Each card: team names, live totals, per-starter line
  (name, pos, NFL team, pts), count of starters yet to play, leader highlight.
  <meta http-equiv="refresh" content="60"> is acceptable v1.
- Route "/api/scores": the JSON the page renders (useful for debugging).
- CLI: --week N (default: current from state/standings.json), --port.
- This board is entertainment; Monday's score_week.py --final is official.
"""
raise SystemExit("Not implemented yet — see TASKS.md 4.1")
