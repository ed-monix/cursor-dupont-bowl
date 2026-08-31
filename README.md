# 🏈 The DuPont Bowl

A 12-team fantasy football league with 2 humans and 10 AI general managers, run
entirely out of this repo by Claude Code.

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

- **12 teams.** Two human-run (the co-owners), ten run by AI GMs — each defined
  entirely by a `general-manager.md` personality file in `teams/`.
- **Sleeper rules.** Standard Sleeper format: half-PPR, 4-pt passing TDs,
  1QB/2RB/2WR/1TE/1FLEX/1K/1DEF + bench. Scoring is synced from a reference
  Sleeper league and applied by our own engine (`config/scoring.json`).
- **Weekly rhythm:**
  - **Fri/Sat AM — Owner notes.** Humans drop a short performance note into each
    team's `notes/` folder. Agents interpret it however their personality
    dictates. That's the only human input they ever get.
  - **Saturday AM — Roster run.** Every agent reviews its team, the waiver wire,
    and its owner note, then submits FAAB claims, drops, and trade offers.
  - **Sunday AM — Lineup run.** Final injury sync, every agent locks a legal
    starting lineup with in-character reasoning.
- **The Commissioner** (`agents/commissioner.md`) is its own agent: it validates
  every transaction, resolves FAAB ties, blocks only rule violations, and
  writes a weekly recap column.
- **Live scoring** via a local scoreboard (`scripts/scoreboard.py`) polling
  Sleeper stats on game days — open `http://localhost:8080` on the laptop.

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
| `scripts/` | Sleeper sync + live scoreboard |
| `.claude/commands/` | Slash commands: `/draft`, `/saturday`, `/sunday`, `/recap` |

## Season quickstart

```bash
pip install requests flask
python scripts/sync_sleeper.py --league <reference_league_id> --all   # settings + players
claude   # then: /draft to run the draft, /saturday and /sunday weekly
python scripts/scoreboard.py   # Sundays, on the laptop
```
