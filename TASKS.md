# TASKS — Build plan for the build agent

Instructions for the build agent: work phases in order; within a phase, tasks
are independent unless noted. Read `PLAN.md` §8 for data contracts before
writing any code — **do not change the contracts without a human decision.**
Every task lists acceptance criteria (AC); a task isn't done until its AC pass
via a runnable check (pytest or a `make check-*` target). Python 3.11+, deps
limited to `requests`, `flask`, `pytest`. No databases, no async, no cleverness.
Style: small pure functions, JSON in/JSON out, every script runnable as
`python scripts/<name>.py --help`.

---

## Phase 1 — Data layer (blocks everything else)

### 1.1 `scripts/sync_sleeper.py`
Already stubbed with working settings/players sync. Finish it.
- Flags: `--league <id> --settings | --players | --projections --week N | --stats --week N | --all`
- `--settings`: writes `config/scoring.json` + `config/roster.json` from
  `GET /v1/league/<id>`.
- `--players`: writes trimmed `state/players.json` (QB/RB/WR/TE/K/DEF, active
  or injured only) from `GET /v1/players/nfl`. Cache raw dump 24h in `.cache/`.
- `--projections` and `--stats`: pull weekly per-player rows; write
  `state/weeks/<season>-w<NN>/projections.json` / `stats.json`.
  Sleeper's projections/stats endpoints are unofficial — probe
  `api.sleeper.app/v1/projections/nfl/regular/<season>/<week>` and
  `.../stats/nfl/regular/<season>/<week>` first; if shapes differ, adapt and
  document the shape in `docs/sleeper-api-notes.md`.
- AC: `--all` on a real league id produces all files with >300 players, and
  scoring.json contains keys `rec`, `pass_td`, `rush_yd`.

### 1.2 `scripts/lib/scoring.py`
- `score_player(stat_line: dict, scoring: dict) -> float` — multiply matching
  keys, ignore keys not in scoring config; handle DST points-allowed tiers and
  kicker distance buckets the way Sleeper keys them (`pts_allow_0` etc.).
- `score_lineup(roster, stats, scoring) -> {player_id: pts, total: float}` —
  starters only.
- AC: pytest with a fixture stat line reproducing a hand-computed half-PPR
  score to ±0.01, incl. a DST and a K case.

### 1.3 `scripts/lib/rosters.py` (validator)
- Load/save `teams/*/roster.json`; `validate_roster()` (slot legality per
  `config/roster.json`, no duplicate players league-wide, FAAB ≥ 0);
  `validate_lineup()` (every starter slot filled, position-eligible, not on
  the starting team twice); `apply_transaction()` (add/drop/trade) that
  refuses illegal results and never partially applies.
- AC: pytest covering: FLEX accepts RB/WR/TE but not QB; duplicate player
  across two teams rejected; trade that would overflow a bench rejected.

## Phase 2 — League mechanics

### 2.1 `scripts/faab.py`
- Input: all teams' claim JSON for the week. Resolve: highest bid; tie → worse
  standings; a team's claims process in its listed priority order; skip claims
  whose drop-player is gone; deduct budgets. Output: resolution report JSON +
  applied via `rosters.apply_transaction`, appended to `state/transactions.jsonl`.
- AC: pytest with a 4-team collision scenario matching a hand-worked result.

### 2.2 `scripts/score_week.py`
- `--week N [--final]`: score all matchups from stats + lineups; write
  `state/weeks/<...>/matchups.json`; `--final` also updates
  `state/standings.json` (record, PF, PA) and marks the week official.
- AC: fake fixtures for 12 teams produce correct standings after 2 weeks incl.
  the points-for tiebreaker.

### 2.3 `scripts/schedule.py`
- Generate `state/schedule.json`: 12 teams, weeks 1–14 round-robin-based, no
  repeat opponent before week 12; playoff bracket template weeks 15–17.
- AC: every team appears exactly once per week; opponent counts verified.

### 2.4 `docs/schemas/`
- Write JSON Schema files for: agent Saturday decision, agent Sunday lineup,
  trade offer/response, transaction log entry. Add `scripts/lib/decisions.py`
  with `parse_and_validate(raw_text, schema)` that extracts the first JSON
  object from an agent's reply and validates it (return errors suitable for a
  retry prompt).
- AC: pytest: valid decision passes; missing bid field returns a helpful error.

## Phase 3 — Claude Code orchestration (prompt-engineering; needs human review)

### 3.1 Slash commands in `.claude/commands/`
Flesh out the stubs: `/draft`, `/saturday`, `/sunday`, `/recap`, `/notes`.
Each must: run syncs first, spawn one subagent per AI team with ONLY that
team's context (never another team's GM file), pipe outputs through
`decisions.py` + validators, invoke the commissioner last, end with a single
git commit `week NN: <run name>`. Human-team prompts pause for typed input.
- AC: a scripted dry run (fake week, 3 sample teams) completes each command
  end-to-end with zero manual fixes; reviewed by owner.

### 3.2 Mock draft harness
- `/draft` must support `--mock` (all 12 teams AI, no pauses). Produce
  draft-log, rosters, schedule.
- AC: full 15-round mock completes; all rosters validate; no player drafted
  twice.

### 3.3 Fallback paths
- Saturday: agent failure after retry → no claims that week (logged).
  Sunday: fallback lineup = highest projected legal lineup (pure function in
  `rosters.py`).
- AC: pytest for fallback lineup generation; dry run demonstrating a forced
  agent failure lands in the log with `fallback: true`.

## Phase 4 — Scoreboard

### 4.1 `scripts/scoreboard.py`
Single-file Flask app, spec in the stub. Poll thread every 45s (game-day
detection: any starter's NFL team plays today per schedule data, else poll
every 10 min). Route `/` = 6 matchup cards: team names, live totals,
per-starter points, count of players yet to play. Plain HTML + a `<meta>`
refresh or tiny fetch loop — no build step, no framework.
- AC: with recorded fixture stats it renders 6 correct matchups; with live
  Sunday data it updates without restart. Visual check by owner.

### 4.2 Reconciliation
- `/recap` re-runs `score_week --final`; report any player whose final differs
  from last live poll by >0.5 pts in the recap data.
- AC: fixture-based test where live and final differ.

## Phase 5 — Content (humans + top-tier model, NOT the build agent)

- 10 celebrity GM files from `teams/_template/general-manager.md` (owners
  write; keep affectionate-parody).
- Finalize `agents/commissioner.md` voice.
- Season kickoff checklist in `docs/season-checklist.md`: create reference
  Sleeper league → sync settings → write GM files → mock draft → real draft.

## Definition of done for handoff back to owners
`make check` runs all pytest suites green; `make dryrun` executes a full fake
week (Saturday, Sunday, recap) from committed fixtures; mock draft clean;
scoreboard renders fixtures. Then owners schedule the real draft.

## Resolved decisions & deviations (owner-signed, 2026-08-31)

- **4.1 scoreboard is stdlib `http.server`, not Flask.** Signed off: Flask can't
  be installed in the target environment (PyPI egress blocked) and the board
  needs no framework. `requirements.txt` intentionally omits Flask. This
  supersedes the "single-file Flask app" wording in 4.1.
- **Playoffs use a fixed (non-reseeding) bracket** — seed 1 vs winner(4/5),
  seed 2 vs winner(3/6). Signed off.
- **A budget-short FAAB winner burns the player** (no pass-down to the next
  bidder that week). Signed off — matches the literal §4 resolution.

## Retroactive tickets (built ahead of the ticket, now tracked)

- **`scripts/free_agents.py`** — derives `state/free-agents.json` (Phase-1-adjacent
  data layer; implied by PLAN §8). Done + tested. Being extended per review R4.
- **Interactive viewer** — `web/viewer.template.html` + `scripts/build_viewer.py`
  + `/refresh-board` (shareable artifact league viewer). Done + tested; the
  game-day refresh loop is documented in README. Formally a new Phase-4 ticket.
