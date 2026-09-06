# 🏈 The DuPont Bowl

A 12-team fantasy football league where every team is run by an AI general
manager — including the two human owners' teams — run entirely out of this
repo by Claude Code. The humans own; the GMs decide; the notes meddle.

## Mission

**Have fun. Let chaos happen.**

The DuPont Bowl is not an optimization exercise. Ten of these teams are run by
agents with strong personalities and questionable judgment, and that is the
point. The commissioner protects the *rules*, never the *quality* of anyone's
decisions. If an agent bids its entire FAAB budget on a third-string tight end
because its owner note hurt its feelings, that transaction is legal, final, and
excellent television. We intervene only when something is broken or unfair —
never when it is merely stupid.

## How it works

- **12 teams, 12 AI GMs.** Every team — the co-owners' two included — is run
  by an AI GM defined entirely by a `general-manager.md` personality file in
  `teams/`. The humans are owners: they hire the GM, they write the notes,
  they live with the consequences.
- **Sleeper rules.** Standard Sleeper format: half-PPR, 4-pt passing TDs,
  1QB/2RB/2WR/1TE/1FLEX/1K/1DEF + bench. Scoring is Sleeper standard (no
  reference league needed — `sync_sleeper.py --settings` activates it from the
  shipped defaults) and applied by our own engine (`config/scoring.json`).
- **Weekly rhythm:**
  - **Fri/Sat AM — Owner notes.** Each human drops a short performance note
    into their OWN team's `notes/` folder — the only two teams with owners.
    Their GM interprets it however its personality dictates. The ten
    celebrity GMs get no notes from anyone; the meddling in their lives is
    Kris Jenner's weekly tabloid.
  - **Saturday AM — Roster run.** Every agent reviews its team, the waiver wire,
    and its owner note, then submits FAAB claims, drops, and trade offers.
  - **Sunday AM — Lineup run.** Final injury sync, every agent locks a legal
    starting lineup with in-character reasoning.
- **The Commissioner** (`agents/commissioner.md`) is its own agent: it validates
  every transaction, resolves FAAB ties, blocks only rule violations, and
  writes a weekly recap column.
- **Live scoring** on game days, two ways: a shareable interactive **viewer**
  (published as a Claude artifact — Scores, Standings, and a playoff Bracket
  forecast) refreshed every ~10 minutes with `/refresh-board`, and/or a
  zero-dependency local board (`scripts/scoreboard.py`) at
  `http://localhost:8080`. See **Live viewer** below.

## Repo map

| Path | What it is |
|---|---|
| `PLAN.md` | The full build & operations plan |
| `TASKS.md` | Phased build tasks (hand these to the build agent) |
| `CLAUDE.md` | Operating instructions for Claude Code sessions |
| `config/` | League rules + scoring settings |
| `agents/commissioner.md` | The commissioner agent definition |
| `teams/` | One folder per team: GM file, roster, owner notes |
| `state/` | League state: free agents, standings, matchups, transaction log |
| `scripts/` | Sleeper sync, scoring/FAAB/schedule engine, live scoreboard, viewer builder |
| `web/` | `viewer.template.html` — the interactive league viewer (Scores, Standings, Bracket) |
| `.claude/commands/` | `/draft`, `/saturday`, `/sunday`, `/recap`, `/notes`, `/refresh-board` |

## Live viewer

On game days the league has a shareable, interactive **viewer** — published as a
Claude artifact, so it's just a link anyone in the league can open (no install,
works on phones). Three tabs:

- **Scores** — the week's matchups; click any one to expand full per-player
  detail (slot, player, stat line, points), leader emphasized. Flip weeks with
  the ‹ › stepper or the arrow keys.
- **Standings** — records, points for/against, and the 6-team playoff cut.
- **Bracket** — a playoff forecast seeded from the current standings.

### Refreshing it on Sundays

The artifact can't call Sleeper itself (it's sandboxed), so it's kept live by
re-publishing it with fresh data. `scripts/build_viewer.py` renders
`web/viewer.html` from committed league state; `/refresh-board` runs the whole
pass (sync stats → build → republish the artifact in place, same URL). For
~10-minute updates during games, run it as a loop from an interactive Claude
session and stop it when the games end:

```
/loop 10m /refresh-board
```

> Scheduled Routines can't do this — the sessions they spawn lack the
> artifact-publishing tool — so the refresh runs from an interactive session,
> which also isn't capped at the hourly Routine minimum.

## Season quickstart

```bash
pip install -r requirements.txt
python scripts/sync_sleeper.py --settings   # Sleeper-standard scoring/roster (no reference league)
# Optional: set GROK_API_KEY in the environment for real X buzz in the weekly
# tabloid (or paste a buzz file by hand; without either, the tabloid runs on
# derived + planted headlines — the league never depends on it).
claude   # then: /draft to run the draft, /saturday and /sunday weekly
# Game-day live board (either or both):
#   /loop 10m /refresh-board       # in a Claude session — refreshes the shareable viewer artifact
#   python scripts/scoreboard.py   # local board at http://localhost:8080
```
