# AGENTS.md — DuPont Bowl (Grok Bots + Cursor)

This repo is the league. Scripts decide facts. Agents decide choices.
Git is the tamper-evident record. Do not write to Sleeper.

## Runtime
- All 12 GMs, Scout, Media, Commissioner: **Grok Bots**
  (`config/grok-bots.json`, `bots/`).
- Owned seats (`your-team` / Ed Monix, `wifes-team` / Tony Soprano) are
  first-class GM Bots. Humans own those teams and write notes; they do
  not run the GM turn in Cursor. The Commissioner builds packs and wakes
  all 12.
- **Owner rule:** ALL repo work goes through **Cursor Cloud Agents**.
  Skip the GitHub MCP connector until the Grok OAuth platform bug is
  fixed. Never box-computer `gh auth login` or device login. See
  `docs/skills/cloud-agents.md`.
- Orchestrator: the **Commissioner Grok Bot** verifies GM JSON and
  wakes every GM (Scout/Media still only on waivers). A Cloud Agent
  commits the gate and daily ops straight to `main`. Larger doc/code
  changes: Cloud Agent opens a PR, then merge to `main`. GMs never
  clone; packs arrive in chat.


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

Grok Bots on one account share one cloud computer. Do not clone this
repo onto that disk. The sanctioned repo path is a Cursor Cloud Agent
— not the GitHub MCP connector (Grok OAuth bug), not `gh auth login`,
not device login. GMs never git; packs arrive in chat. They report
JSON to the Commissioner (`commish_gate.py ingest`). A Cloud Agent
writes `main`. Do not copy other teams' GM files into a GM chat.
`python scripts/grok_bots.py check` must stay green.

## Commands
- `/grok-bots` — roster, commissioner clock, daily ops
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
