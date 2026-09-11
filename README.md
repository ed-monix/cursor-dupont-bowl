# 🏈 The DuPont Bowl

This is the **Cursor-native ops fork** (`ed-monix/cursor-dupont-bowl`). Live
2026 season state stays on `ed-monix/dupont-bowl` unless Nick says otherwise.

A 12-team fantasy football league where every team is run by an AI general
manager — including the two human owners' teams. The humans own; the GMs
decide; the notes meddle.

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

- **12 teams, 12 AI GMs.** Celebrity GMs run as Grok Bots
  (`config/grok-bots.json`). The two owned teams (`your-team`, `wifes-team`)
  stay off that shared Bot computer and run pack-only in Cursor. Humans are
  owners: they hire the GM, they write the notes, they live with the
  consequences.
- **Sleeper rules.** Standard Sleeper format: half-PPR, 4-pt passing TDs,
  1QB/2RB/2WR/1TE/1FLEX/1K/1DEF + bench. Scoring is Sleeper standard (no
  reference league needed — `sync_sleeper.py --settings` activates it from the
  shipped defaults) and applied by our own engine (`config/scoring.json`).
- **Weekly rhythm:**
  - **Owner notes** before `/waivers` — each human writes to their OWN
    team's `notes/` folder. Celebrity GMs get Kris Jenner's tabloid instead.
  - **`/waivers`** — FAAB claims, drops, and trade offers (once, before the
    week's first kickoff).
  - **`/lineups early`** — lock starters whose NFL games are Tue–Sat (TNF).
  - **`/lineups main`** — lock the rest after late injury news (Sun/Mon).
    Already-kicked games stay frozen.
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
| `AGENTS.md` | Cursor / Bot operating rules (packs, isolation, command names) |
| `PLAN.md` | The full build & operations plan |
| `TASKS.md` | Phased build tasks (hand these to the build agent) |
| `CLAUDE.md` | Operating instructions for Claude Code sessions |
| `config/` | League rules, scoring, Grok Bot roster |
| `bots/` | Grok Bot skills + create notes (do not clone onto the Bot disk) |
| `agents/commissioner.md` | The commissioner agent definition |
| `teams/` | One folder per team: GM file, roster, owner notes |
| `state/` | League state: free agents, standings, matchups, transaction log |
| `scripts/` | Sleeper sync, scoring/FAAB/schedule engine, live scoreboard, viewer builder, GM packs |
| `web/` | `viewer.template.html` — the interactive league viewer (Scores, Standings, Bracket) |
| `.claude/commands/` and `.cursor/commands/` | `/waivers`, `/lineups`, `/recap`, `/notes`, `/refresh-board`, `/draft` |

## Live viewer

On game days the league has a shareable, interactive **viewer** — published as a
Claude artifact, so it's just a link anyone in the league can open (no install,
works on phones). Three tabs:

- **Scores** — the week's matchups; click any one to expand full per-player
  detail (slot, player, stat line, points), leader emphasized. Flip weeks with
  the ‹ › stepper or the arrow keys.
- **Standings** — records, points for/against, and the 6-team playoff cut.
- **Bracket** — a playoff forecast seeded from the current standings.

### Keeping it fresh

The artifact can't call Sleeper itself (it's sandboxed), so it's kept live by
re-publishing it with fresh data. Every state-changing run — the draft,
`/waivers`, `/lineups`, `/recap` — ends by rebuilding the viewer and
republishing the artifact in place, so the shared link tracks the league
automatically. The loop below is only for live scoring during the games. `scripts/build_viewer.py` renders
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
claude   # then: /draft to run the draft, /waivers and /lineups weekly
# Game-day live board (either or both):
#   /loop 10m /refresh-board       # in a Claude session — refreshes the shareable viewer artifact
#   python scripts/scoreboard.py   # local board at http://localhost:8080
```
