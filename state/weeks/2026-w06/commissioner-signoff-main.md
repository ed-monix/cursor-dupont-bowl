# Week 6 — Lineup Signoff (`main` window)

**Season 2026 · Week 6 · Stage: lineups · Window: main**
Twelve lineups submitted. Twelve parsed on first pass. One slot refused. One data defect noted.

---

## 1. Validation summary

| Team | Changes from board | Slots | Dupes | Verdict |
|---|---|---|---|---|
| coach-taylor | St. Brown (DET bye) → Wan'Dale Robinson, WR2 | 9/9 legal | none | **Clear** |
| costanza | Montgomery → R. White (RB1); DJ Moore → Worthy (FLEX) | 9/9 legal | none | **FLEX clear / RB1 refused** |
| dumbledore | Goff (DET bye) → J. Daniels, QB | 9/9 legal | none | **Clear** |
| harry-caray | Deebo (Out) → Diggs, WR2; A. Jones (MIN bye) → H. Henry, FLEX | 9/9 legal | none | **Clear**, see §3 |
| kardashian | Jefferson (MIN bye) & Egbuka out; McConkey WR1, McMillan WR2 | 9/9 legal | none | **Clear** |
| leon-black | Burrow (CIN bye) → Mahomes, QB; M. Wilson → Hubbard, FLEX | 9/9 legal | none | **Clear** |
| maura-higgins | Gesicki (CIN bye) → Waller, TE | 9/9 legal | none | **Clear** |
| meyer-walsh | Metcalf → Vele, FLEX | 9/9 legal | none | **Clear** |
| patricia-moyer | Gibbs (DET bye) → K. Walker, RB1 | 9/9 legal | none | **Clear** |
| rinna | J. Love (Out) → Stevenson, RB1; M. Evans → Concepcion, WR1 | 9/9 legal | none | **Clear** |
| wifes-team | LaPorta (DET bye) → Ferguson, TE | 9/9 legal | none | **Clear**, see §4 |
| your-team | Brissett → C. Williams, QB; Burden → A.J. Brown, WR2 | 9/9 legal | none | **Clear**, see §5 |

Positional eligibility verified slot by slot: all twelve QB slots hold a QB, all twenty-four RB slots an RB, all twenty-four WR slots a WR, all twelve TE slots a TE. The twelve FLEX slots hold four RB, five WR and three TE — all permitted. No player appears twice within a lineup. No player appears on two teams' lineups. All twelve DEF slots hold distinct NFL teams. Every submitted starter was rostered by the submitting team before this window; nothing was started off another team's board, and nothing was started that does not exist.

Byes this week are CIN, DET and MIN. Nine of the twelve submissions are bye corrections, which is the only reason this document is short.

---

## 2. One slot refused — costanza, RB1

The submission moves David Montgomery (HOU, Out) out of RB1 for Rachaad White. The submitting GM's own logged reasoning states that Houston is in progress at the time of filing: *"HOU's already out there getting beat up by Jacksonville as we speak, and somehow I'm the last to know."* Four other GMs place the same game in progress independently — kardashian logs Stroud and Marks as locked, wifes-team logs Boutte as "already out there grinding against Houston," and patricia-moyer and dumbledore both treat the Jacksonville side as sealed.

A slot whose game has started does not move. **Ruling 2026-07 controls and is applied without variation:** the Montgomery → White swap is refused, Montgomery remains at RB1 for zero, and White remains on the bench. This is not a GM error and requires no retry — the balance of the lineup, including the Worthy-for-DJ-Moore swap in the FLEX (BUF and KC both pre-kickoff), stands exactly as filed.

The office notes, without sympathy it is not entitled to give, that the football judgment here was correct and arrived eleven minutes late. The paperwork does not score points.

**Confirmation required before apply:** the freeze is to verify Houston's kickoff against the kickoff table, which is not in this pack. If the table says Houston had not started, the swap applies as filed. If it says otherwise, Montgomery starts. Either way nothing else in costanza's lineup is touched.

---

## 3. Data defect — harry-caray, K slot

The K slot holds player id `12015`, carried in as `pos: "?"`, `nfl: "FA"`, with its own id in the name field. Positional eligibility for that slot **cannot be verified**, because there is nothing there to verify against.

This is not a blockable transaction. The slot is unchanged from the board, the GM moved nothing into it, and the roster carries no other kicker. The lineup is signed off; the id is referred to the league office for resolution against the player table before week 7. The office has read Ruling 2026-05 and declines to be surprised twice by a stale pool.

---

## 4. wifes-team — four zeroes, all of them legal

Murray (MIN bye), Bates (DET bye), Chase Brown (CIN bye) and Roman Wilson (IR) all start for a projected zero. In each case the roster holds no eligible alternative: one quarterback, one kicker, one other running back who is tagged Out, and two wide receivers of whom both carry IR tags. The league's rosters carry no IR slot — `ir` is empty for all twelve teams — so an IR tag here is injury information, not an eligibility bar. Starting a tagged or bye player is legal; it merely scores nothing.

The submission is legal in all nine slots and is signed off. The GM's stated reason for not sitting Chase Brown under his own fumble rule — that the only alternative is tagged Out — is accurate.

---

## 5. your-team — roster count

Nine starters and five bench players: fourteen rostered against the fifteen every other team carries. This is a roster-count discrepancy, not a lineup defect — a short roster is legal and all nine slots are filled legally. Referred to the office for reconciliation against the Ruling 2026-09 free-agency apply, which should have been one-for-one. No remedy sought here, no lineup consequence.

---

## 6. Matters expressly not blocked

- **meyer-walsh** benched DK Metcalf (10.92) for Devaughn Vele (8.47) and logged the reason as spite, in writing, with the deputy GM's objection recorded beside it. A GM is permitted to be wrong on purpose. The transaction was, regrettably, legal.
- **rinna** benched Mike Evans for KC Concepcion and described the motive as owing the audience a shocking bench. Also legal.
- **costanza** benched DJ Moore at 11.32 as "bad luck." Legal.
- **your-team** started two Questionable players and a third in the FLEX over healthier options. Legal, and not this office's business.
- **coach-taylor** left Terry McLaurin in the FLEX at 9.81. The office observes that this is the second consecutive month that slot has occupied its attention and that this time nobody asked it to.

No collusion question arises. No trade was offered. `forum_this_week` is empty of anything requiring a ruling.

---

## 7. Hall of Shame

**No `fallback: true` entries this week.** All twelve GMs submitted a parseable lineup with a logged justification on the first attempt. The office records this without comment, as comment would spoil it.

---

## 8. Freeze

Nothing in this run requires a GM retry. No FAAB was resolved, no trade was submitted, no GM-file edit window was open, and no edit counts changed.

**The window may be frozen**, subject to the single verification in §2: confirm Houston's kickoff, apply costanza's RB1 accordingly, and apply the remaining eleven lineups exactly as filed. The harry-caray kicker id and the your-team roster count go to the office as defects, not as blocks.

Nine of twelve lineups this week were a GM noticing a bye week. One was a GM noticing one too late. It is, by the standards of this league, an orderly Sunday.
