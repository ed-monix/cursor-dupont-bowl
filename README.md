# The DuPont Bowl

This repo (`ed-monix/cursor-dupont-bowl`) **is the league**. Git is the
record. Do not use `ed-monix/dupont-bowl` going forward.

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
  We never write back to Sleeper.
- **Weekly rhythm:**
  - **Owner notes** before `/waivers` — each human writes to their OWN
    team's `notes/` folder. Celebrity GMs get Kris Jenner's tabloid instead.
  - **`/waivers`** — FAAB claims, drops, and trade offers (once, before the
    week's first kickoff).
  - **`/lineups early`** — lock starters whose NFL games are Tue–Sat (TNF).
  - **`/lineups main`** — lock the rest after late injury news (Sun/Mon).
    Already-kicked games stay frozen.
- **The Commissioner** is a Grok Bot (`bots/skill-commish.md`): daily clock
  and git gate. It clones this repo, writes `state/ops/`, wakes other Bots,
  verifies their JSON, and commits. It does not apply FAAB or mutate rosters.
  Cloud Agents run `/apply` after `decisions/` lands.
- **Live scoring** is GitHub Actions (~20 min on TNF/Sunday/MNF), not the
  Commissioner's 9am check. The shareable board is **GitHub Pages** built
  from `web/viewer.template.html` + committed state.

## Repo map

| Path | What it is |
|---|---|
| `AGENTS.md` | Cursor / Bot operating rules (packs, isolation, command names) |
| `PLAN.md` | The full build & operations plan |
| `TASKS.md` | Phased build tasks |
| `CLAUDE.md` | Operating instructions for Claude Code sessions |
| `config/` | League rules, scoring, Grok Bot roster |
| `bots/` | Grok Bot skills + create notes (do not clone onto the Bot disk) |
| `agents/commissioner.md` | The commissioner agent definition |
| `teams/` | One folder per team: GM file, roster, owner notes |
| `state/` | League state: free agents, standings, matchups, ops, transaction log |
| `scripts/` | Sleeper sync, scoring/FAAB/schedule engine, viewer builder, GM packs, gate |
| `web/` | `viewer.template.html` — the interactive league viewer |
| `.github/workflows/` | Pages publish + gameday stats |
| `.claude/commands/` and `.cursor/commands/` | `/waivers`, `/lineups`, `/apply`, `/recap`, `/notes`, `/refresh-board`, `/draft` |

## Live viewer

On game days the league has a shareable, interactive **viewer** on GitHub
Pages (`https://ed-monix.github.io/cursor-dupont-bowl/` once Pages is
enabled: Settings → Pages → GitHub Actions). Anyone can open the link on a
phone. Tabs include Scores, Feed, Standings, Bracket, Schedule, Rosters,
Draft, and Guide.

`scripts/build_viewer.py` injects committed league state into
`web/viewer.template.html`. `web/viewer.html` stays gitignored (local
preview only). Actions writes `_site/index.html` and deploys.

### Keeping it fresh

- After `/apply`, `/recap`, or any push to `main`, `viewer.yml` rebuilds.
- During games, `gameday.yml` syncs Sleeper stats about every 20 minutes
  and commits; that retriggers Pages. `/refresh-board` is the same pass
  from a Cloud Agent if you want it by hand.
- Local board still works: `python scripts/scoreboard.py` at
  `http://localhost:8080`.

The Commissioner 9am job does **not** refresh the board.

## Season quickstart

```bash
pip install -r requirements.txt
python scripts/sync_sleeper.py --settings   # Sleeper-standard scoring/roster
# Optional: GROK_API_KEY for real X buzz in the tabloid (or paste a buzz file).
# Commissioner Bot: daily clone + commish_gate.py (see bots/skill-commish.md)
# After decisions land: /apply
# Game-day board: GitHub Actions, or /refresh-board in a Cloud Agent
#   python scripts/scoreboard.py   # local board at http://localhost:8080
```
