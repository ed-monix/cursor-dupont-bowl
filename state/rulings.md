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

## Ruling 2026-05 — Aaron Rodgers double-rostered; leon-black's claim voided nunc pro tunc (2026-09-10)

Pre-Sunday review of all twelve rosters, undertaken because the office reads
its own paperwork even when nobody asks it to, turned up one player rostered
by two teams: Aaron Rodgers (id 96), held simultaneously by rinna and
leon-black. Both claims were, at the moment each was filed, procedurally
clean — bid within budget, drop legal, resulting roster legal. Only one of
them could have been true.

The timestamps settle it. Rinna claimed Rodgers (and dropped Carnell Tate) at
13:39:35 on 2026-09-08, during the cutdown window — a legitimate
transaction, applied, and already accounted for in Ruling 2026-04's tally of
her remaining FAAB. Leon-black claimed Rodgers (and dropped Tyler Loop) at
23:55:20 the following day, during the Saturday run. By then Aaron Rodgers
had not been a free agent for over a day. The claim should have been blocked
at intake as involving an already-rostered player, per this office's own
standing jurisdiction. It was not blocked because the free-agent pool handed
to Saturday's GMs was built from a roster snapshot that predated the
cutdown window's transactions — a pipeline defect, not a GM decision, and no
more leon-black's fault than Ellis Richardson's retirement was harry-caray's.

Ruling: rinna's claim is the valid one and her roster is undisturbed.
Leon-black's claim on Aaron Rodgers is VOID nunc pro tunc. Remedy, effective
immediately:
1. Aaron Rodgers (96) is removed from leon-black's roster.
2. Tyler Loop (12711) — confirmed a free agent as of this ruling, claimed by
   no other team — is restored to leon-black's bench.
3. Leon-black's $32 bid is refunded in full: FAAB remaining moves from $27
   to $59.
4. Leon-black's Sunday K slot, vacant only because his own kicker had been
   sacrificed to fund the now-voided claim, is filled with the restored
   Tyler Loop — the sole kicker on his roster and therefore not a football
   decision left open to him, merely the one legal state of that slot.
   Every other slot in his submitted Sunday lineup, Joe Burrow at
   quarterback included, stands exactly as filed; this office corrects
   facts, not judgment, and his benching of two more famous quarterbacks
   than the one it just gave him a legal kicker to keep is a matter for the
   recap, not the rulings log.

No other cross-team duplicate ownership exists among the twelve rosters as
of this review. state/free-agents.json should be regenerated once this
correction is applied, so the derived pool matches the roster files it is
supposed to describe — the office has had quite enough of stale wire boards
for one week.

## Ruling 2026-06 — Five rosters silently short two weeks, bench reconciliation (2026-09-16)

Week 2's waiver run stopped dead at the apply gate. FAAB went to execute
costanza's won claim, validated the resulting roster as it is required to, and
refused it: DJ Moore in both the FLEX and on the bench, Justin Herbert in both
the QB slot and on the bench. The claim was innocent. The roster was not.

This office has audited all twelve. Five were corrupt — costanza, rinna,
dumbledore, meyer-walsh and patricia-moyer — and the cause is the same in each
case, `week 01: apply lineups-main`. That apply wrote each team's new starters
and left the bench exactly as it found it. A player promoted out of the bench
therefore stayed on it, appearing twice; a player demoted out of the lineup was
written to no list at all and ceased, quietly, to be on anybody's roster. The
five affected teams are precisely the five that changed their week 1 lineup.
The seven that stood pat were untouched, which is why this went unnoticed: a
bug that only bites the managers who manage.

Nothing validated a roster between that apply and this week's FAAB, so five
teams have spent two weeks of league time carrying thirteen or fourteen
players while believing they carried fifteen, and this office has been
publishing standings computed against lineups drawn from them.

Players destroyed, now restored: Baker Mayfield and Rachaad White
(costanza); Aaron Rodgers and Courtland Sutton (rinna); Jared Goff
(dumbledore); Jordan Mason (meyer-walsh); Carnell Tate (patricia-moyer).

Ruling: this is a pipeline defect, not a GM decision, and no GM is charged for
it. Remedy, applied by `scripts/repair_lineup_bench.py` rather than by hand:
1. Each affected bench is rebuilt as what the team held before the corrupting
   apply, minus whoever is starting now — the apply as it should have run.
2. The duplicates are removed and the destroyed players restored to the bench.
3. No FAAB is charged or refunded, no lineup is restated, and no result is
   reversed. Week 1 was played and scored with the lineups the GMs actually
   submitted; only the bench behind them was wrong, and a bench scores nothing.
   The standings stand.
4. The apply path is fixed so a lineup change conserves the rostered set, with
   tests, because the only reason this cost two weeks instead of two minutes
   is that nothing asserted it.

All twelve rosters validate as of this ruling. Week 2's waiver run is to be
re-run from the top against the repaired rosters — the GM decisions taken
against corrupt ones are void, having been reasoned from a roster five of the
twelve did not have.
