# AGENTS.md — DuPont Bowl (Claude routine + gm_turn.py)

This repo is the league. Scripts decide facts. Agents decide choices.
Git is the tamper-evident record. Do not write to Sleeper.

## Runtime
- All 12 GMs, owned two (`your-team`, `wifes-team`) included:
  **`scripts/gm_turn.py`**, one isolated `claude -p` per team in an empty
  working directory, pack-only. Not Cursor (as of 2026-10-15).
- Media (Kris) and the Commissioner: **`scripts/agent_turn.py`**, the same
  isolated transport, one turn each. Scout is `fetch_buzz.py` /
  `buzz_inbox.py` (owner paste or the Grok automation's drop).
- Orchestrator: the **`bowl_league_ops` Claude routine**
  (`routines/bowl_league_ops.md`, daily 08:59 America/New_York). It writes
  the day's ops file, runs the matching command, gets the commissioner's
  signoff, applies via `/apply`, and commits once.
- Optional path: the Grok Bot gateway (`config/grok-bots.json`, `bots/`,
  `grok_bots.py dispatch`) when Nick's local gateway is running. No Grok
  Commissioner or celebrity GM Bot is running as of 2026-10-15.


## Roles
- Scripts (`scripts/`): sync, score, FAAB, roster legality, fallback lineups,
  free agents, league board, dossier, buzz fetch, GM packs, lineup windows,
  daily ops. Never replace with model math.
- GMs: emit schema JSON only (`docs/schemas/saturday-decision.json` for
  `/waivers`, `sunday-lineup.json` for `/lineups`). In-character reasoning
  lives inside those fields.
- Commissioner: block illegal only; chaos is legal. Write recap/rulings/signoff.
  Do not apply FAAB or mutate rosters; scripts apply after signoff.
- Media: rewrite `news-facts.json` (+ optional buzz) into `state/news/YYYY-wNN.md`.
  Zero powers. Never read a GM file or `opinions.json`.
- Scout: at most one measured X pass into `state/news/buzz/YYYY-wNN.md`.
  Owner-pasted file wins; else `scripts/fetch_buzz.py`; else absent.
  Never invent post counts. GMs never read `buzz/`.

## Isolation
A GM turn may only be given the pack from `scripts/gm_pack.py` for that slug
(plus the public week pack it already embeds). Tools off. Never
`state/players.json`, never another `general-manager.md` or `opinions.json`.
Never search X.

`gm_turn.py` makes this a property of the process: each turn runs in an
empty directory, so there is no repo to read. GMs never git. Do not copy
other teams' GM files into a GM turn.

On the optional Grok path, Bots on one account share one cloud computer.
**Only the Commissioner** clones this repo; GMs report JSON to it, and it is
the gate (`commish_gate.py ingest`). `python scripts/grok_bots.py check`
must stay green.

## Commands
- `/grok-bots` — the optional Grok Bot path: roster, daily ops
- `/waivers` — weekly FAAB/trades (before first kickoff)
- `/lineups <week> early|main` — lock Tue–Sat games, then Sun/Mon
- `/recap` — official scores and commissioner column
- `/apply` — FAAB / lineups after the gate commits `decisions/`
- `/refresh-board` — sync live stats; Pages rebuilds (not the 9am job)
- `/notes` — owner-note stubs for the two owned teams

## Style
No emojis. Dates YYYY-MM-DD (week files stay YYYY-wNN). No credentials
in files or prompts. One git commit per run
(`week NN: waivers|lineups-early|lineups-main|recap|notes`).
