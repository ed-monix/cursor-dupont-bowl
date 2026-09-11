# AGENTS.md — DuPont Bowl (Cursor harness)

This repo is the league. Scripts decide facts. Agents decide choices.
Git is the tamper-evident record. Do not write to Sleeper.

## Roles
- Scripts (`scripts/`): sync, score, FAAB, roster legality, fallback lineups,
  free agents, league board, dossier, buzz fetch, GM packs, lineup windows.
  Never replace with model math.
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

On a shared Grok Bot disk, do not mount all 12 GM files and hope. Human-owned
teams (`your-team`, `wifes-team`) stay off any shared Bot computer.

## Commands
- `/waivers` — weekly FAAB/trades (before first kickoff)
- `/lineups <week> early|main` — lock Tue–Sat games, then Sun/Mon
- `/recap` — official scores and commissioner column
- `/notes` — owner-note stubs for the two owned teams

## Style
No emojis. Dates YYYY-MM-DD (week files stay YYYY-wNN). No credentials
in files or prompts. One git commit per run
(`week NN: waivers|lineups-early|lineups-main|recap|notes`).
