# Season rulings, GM-file edit counts, and commissioner decisions.

## Ruling 2026-01 — Pre-week-1 cutdown window (2026-09-08)
1. League-office correction: six rostered players (Dent, Gabbert, Richardson,
   Tucker, Seybert, Bell) were not on NFL rosters — an erroneous draft board,
   not a GM decision. Released by the office; no FAAB charged or refunded.
   Nobody's fault. Everybody's paperwork.
2. One-window provisions: (a) two outgoing trade offers per team (normal cap
   one); (b) FAAB ties break by reversed draft order (no standings exist).
   Both expire at Wednesday's kickoff. Recorded here so nobody cites them as
   precedent in November. They will anyway.

## Ruling 2026-02 — Week 1 Saturday run, FAAB tiebreak basis (2026-09-09)
No standings exist yet (week 1 has not been played) — PLAN's tiebreak
(record -> points-for) has nothing to compute from. Absent that, FAAB ties
this run break by the same proxy used in the cutdown ruling: reversed draft
order (last pick of round 1 = best priority). This is a fresh ruling for
this run, not an extension of Ruling 2026-01's one-window provisions (which
expired at Wednesday's kickoff, as recorded) — it applies only until
state/standings.json exists after week 1's games, at which point the normal
record -> points-for tiebreak takes over automatically. The one-outgoing-
trade-offer-per-team cap is back in force this run (the cutdown's double
window is over).

## Ruling 2026-03 — Week 1 Saturday, trade offers naming the wrong roster (2026-09-09)
Ten of twelve outgoing trade offers this run named an "in" player who is not
actually on the stated target team's roster (in one case, a player who does
not exist on any roster at all — Le'Veon Bell, corrected out of the league
in Ruling 2026-01). Root cause: pre-game scouting confusion, not bad faith —
several GMs worked from reputation and league buzz rather than a verified
roster check. Per rule 6 (nonexistent/misidentified-roster transactions are
blocked, not judged), all ten are REJECTED as invalid, no target response
required, no FAAB or trade capacity consumed:
  - kardashian -> meyer-walsh, wanted Le'Veon Bell (does not exist; released
    Ruling 2026-01)
  - dumbledore -> leon-black, wanted Aaron Rodgers (a free agent this week,
    not on leon-black's roster)
  - harry-caray -> kardashian, wanted Travis Kelce (actually meyer-walsh's)
  - leon-black -> dumbledore, wanted Trey McBride (actually rinna's)
  - maura-higgins -> patricia-moyer, named no specific player ("a
    starting-caliber RB, your pick") -- a trade offer must name real players
  - meyer-walsh -> your-team, wanted Kyren Williams (actually costanza's)
  - patricia-moyer -> harry-caray, wanted Jerry Jeudy (a free agent this
    week, not on harry-caray's roster)
  - rinna -> coach-taylor, wanted Saquon Barkley (actually kardashian's)
  - wifes-team -> kardashian, wanted Ja'Marr Chase (actually leon-black's)
  - your-team -> costanza, wanted Malik Nabers (actually maura-higgins')
The two offers that correctly named a player on the actual target roster
(coach-taylor -> maura-higgins for James Cook; costanza -> kardashian for
George Kittle) proceeded to a normal target response. Maura-higgins rejected
outright (three quarterbacks already, no need for a fourth). Kardashian
countered (Dalton Schultz for Rachaad White, declining to move her newly
acquired George Kittle); costanza rejected the counter as a bait-and-switch.
No trades executed this week. The league office notes, dryly, that
`state/league-board.json` exists precisely so the wrong-roster confusion
doesn't have to happen twice.

## Ruling 2026-04 — Week 1 Saturday, two FAAB claims rejected for illegal drops (2026-09-09)
maura-higgins (add Tyjae Spears, drop Isaac Guerendo) and meyer-walsh (add
Deshaun Watson, drop TreVeyon Henderson) each named a drop that was actually
their STARTING RB2, not a bench player. Dropping a starter empties that slot
but does not free bench space, and a FAAB add always lands on the bench —
so both claims would have pushed the bench to 7 against a limit of 6.
Rejected as illegal resulting rosters (rule 6), before application; no FAAB
charged. Consequence: meyer-walsh's claim was the standing high bid on
Deshaun Watson ($76) — voiding it before resolution reopened that auction,
which rinna's $58 then won outright by bid. However rinna's own remaining
FAAB was only $45 (she spent $55 on Aaron Rodgers during the cutdown
window and, evidently, forgot), so her own winning claim then failed budget
validation and was skipped. Per the engine's actual resolution logic, a
contested player's winner is fixed once by highest bid; if that winner
can't cover it, the claim fails and the player goes unclaimed rather than
falling to the next bidder. Net result: Deshaun Watson (id 4017) is
unclaimed this week — harry-caray's $37 and leon-black's $18 bids, though
both affordable, never had a chance to win once the top bid was set. The
league office declines to editorialize further than: the transaction was,
regrettably, legal.
