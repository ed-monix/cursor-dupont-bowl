# DuPont Bowl — League Rules

## Format
- 12 teams, all GM-run: every team — the two human owners' included — is
  managed by its own AI GM. Head-to-head, weeks 1–14; playoffs weeks
  15–17, 6 teams, seeds 1–2 first-round byes. Seeding: record, then points for.
- Roster: QB, RB, RB, WR, WR, TE, FLEX (RB/WR/TE), K, DEF, 6 bench, 1 IR
  (IR-eligible designations only).
- Scoring: `config/scoring.json` (Sleeper standard half-PPR; synced from the
  reference league). Monday final-stat reconciliation is the official result.
- Sleeper's sync is the SOLE source of facts — injuries, statuses, stats,
  scores. Real-world X buzz and the tabloid are sentiment only: no script,
  validator, or ruling may cite them, and where they contradict Sleeper,
  Sleeper wins (the contradiction is, at most, a storyline).

## Draft
- 15-round snake, order randomized on draft day. Every team picks via its GM
  agent — the owners watch. Validator enforces one-K/one-DEF max at draft.

## Weekly deadlines
- Owner notes: in `notes/` before the week's `/waivers` run — each owner to
  their OWN team only (`your-team`, `wifes-team`). The other ten GMs have
  no owner; their meddling arrives via the tabloid.
- Roster run (waivers/trades): `/waivers`, once before the week's first
  kickoff. No mid-week pickups.
- Lineups: `/lineups <week> early` before Tue–Sat NFL games (TNF and any
  Wednesday/Friday/Saturday kickoffs); `/lineups <week> main` before the
  Sunday slate so late injury news can move players who have not yet
  played. A starter whose NFL game has kicked off is frozen. There are no
  in-game swaps — owners have no lever to swap with.

## Waivers & free agency
- FAAB: $100/season, blind bids, min $0. Ties → worse standing wins.
  Unspent FAAB has no value. No mid-week pickups — all adds happen in the
  `/waivers` run (yes, this means a Thursday injury after waivers process
  hurts; chaos clause). Sunday `/lineups` can still bench that player if
  they have not yet kicked off.

## Trades
- One outgoing offer per team per week. Target may accept / reject / counter
  once; offerer then accepts or rejects the counter. Deadline: end of week 11.
- Trades are player-for-player ONLY. Draft picks (current or future) and
  FAAB dollars are not tradable assets — an offer including either is
  invalid and blocked.
- No vetoes for lopsidedness. Commissioner may void only for rule violations
  or collusion (see below).

## The GMs
- Every team is governed solely by its `general-manager.md` — the owners'
  teams included. Owner notes (to the two owned teams only) are the only
  in-season human input to ANY roster, and agents may interpret them freely.
  The ten unowned GMs' outside pressure is the weekly tabloid.
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
