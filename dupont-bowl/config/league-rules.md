# DuPont Bowl — League Rules

## Format
- 12 teams: 2 human-run, 10 AI-run. Head-to-head, weeks 1–14; playoffs weeks
  15–17, 6 teams, seeds 1–2 first-round byes. Seeding: record, then points for.
- Roster: QB, RB, RB, WR, WR, TE, FLEX (RB/WR/TE), K, DEF, 6 bench, 1 IR
  (IR-eligible designations only).
- Scoring: `config/scoring.json` (Sleeper standard half-PPR; synced from the
  reference league). Monday final-stat reconciliation is the official result.

## Draft
- 15-round snake, order randomized on draft day. AI teams pick via their GM
  agent; humans pick live. Validator enforces one-K/one-DEF max at draft.

## Weekly deadlines
- Owner notes: in `notes/` by Friday 11:59 PM.
- Roster run (waivers/trades): Saturday AM. Human claims due before the run.
- Lineup run: Sunday AM, before the early slate. Lineups then freeze; there
  are no in-day swaps for anyone, including humans.

## Waivers & free agency
- FAAB: $100/season, blind bids, min $0. Ties → worse standing wins.
  Unspent FAAB has no value. No mid-week pickups — all adds happen in the
  Saturday run (yes, this means Thursday-night injuries hurt; chaos clause).

## Trades
- One outgoing offer per team per week. Target may accept / reject / counter
  once; offerer then accepts or rejects the counter. Deadline: end of week 11.
- No vetoes for lopsidedness. Commissioner may void only for rule violations
  or collusion (see below).

## The AI teams
- Each is governed solely by its `general-manager.md`. Owner notes are the only
  in-season human input, and agents may interpret them freely.
- GM file edits: max 3 per team per season, only during a note window
  (Fri–Sat). Formatting/bug fixes that don't change strategy are free at the
  commissioner's discretion. All edits logged in `state/rulings.md`.
- Agent failure handling: one retry with the validation error; then Saturday →
  no transactions, Sunday → auto-set highest-projected legal lineup, flagged
  `fallback` in the public log.

## Commissioner
- The commissioner agent (`agents/commissioner.md`) reviews all transactions.
  It must block rule violations, must not block legal-but-dumb moves, and may
  void a trade only when neither side's GM file plausibly supports it
  (collusion). Human owners jointly hear appeals; if the humans disagree, the
  commissioner's ruling stands.

## Chaos clause
Legal + absurd = binding. No do-overs for agents (or humans) who make
spectacular mistakes. The recap will remember.
