---
description: Saturday roster run — waivers (FAAB), drops, and trade offers for the week
argument-hint: <week number, e.g. 5>
---

# /saturday — roster run, week $ARGUMENTS

Runs the weekly waiver/trade cycle (PLAN.md §4 Saturday). Season 2026; let `WW`
be the zero-padded week from `$ARGUMENTS` (ask if empty). Obey CLAUDE.md's hard
rules throughout — especially **isolation** (rule 1: a GM subagent sees ONLY its
own `general-manager.md`), **notes are pressure not orders** (rule 2), **scripts
decide facts** (rule 3), **everything is logged** (rule 4), **one commit per run**
(rule 5), and **commissioner reviews before anything is applied** (rule 6).

## 1. Sync fresh data (scripts decide facts)

Run, from the repo root:

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week <WW>
```

Then derive the **free-agent pool**: every player_id in `state/players.json` that
is NOT on any `teams/*/roster.json` (starters + bench + ir, all teams), with its
projection (`state/weeks/2026-w<WW>/projections.json`) attached. Write
`state/free-agents.json` as `{player_id: {name, pos, team, proj_pts}}` where
`proj_pts = scripts/lib/scoring.score_player(projection_row, scoring)`.
> NOTE FOR REVIEW: there is no `scripts/free_agents.py` yet — this derivation is
> currently done inline. If you want it deterministic and testable, add that
> script as a follow-up ticket and call it here instead.

Build the **worst→best standings order** from `state/standings.json` (record,
then points-for; the FAAB tiebreak input `faab.py` expects — a list of team
slugs, worst first).

## 2. AI team decisions (one isolated subagent per team)

For each AI team (every `teams/` dir except `_template`, `your-team`,
`wifes-team`), in **reverse standings order** (worst-standing team first, for
context only — bids are blind), spawn ONE subagent whose context is ONLY:

- that team's `teams/<slug>/general-manager.md` (NEVER another team's),
- its `teams/<slug>/roster.json`,
- `state/standings.json` and its last box score (`state/weeks/2026-w<PREV>/matchups.json` if it exists),
- its owner note `teams/<slug>/notes/2026-w<WW>.md` (if present) — framed explicitly as *sentiment it may obey, ignore, or spite*,
- `state/free-agents.json` (with projections),
- its next opponent from `state/schedule.json`.

Instruct the subagent to reply with a single JSON object matching
`docs/schemas/saturday-decision.json`:
`{claims: [{add, drop, bid}], drops: [], trade_offer?, note_reply}`, plus its
in-character reasoning. Claims are in priority order; bids are integers ≥ 0 and
must not exceed the team's `faab_remaining`.

Parse each reply with `scripts/lib/decisions.parse_and_validate(raw, schema)`.
On failure, **retry once** with the validation errors appended. If it still
fails: that team makes **no claims/trades this week**, logged as
`fallback: true` (PLAN.md §10, league-rules "Agent failure handling"). Quote
every GM's reasoning verbatim into the log — it's the entertainment.

## 3. Human team decisions

For `your-team` and `wifes-team`, PAUSE and prompt the human to type claims,
drops, and any trade offer. Run their typed input through the SAME
`saturday-decision` schema and the same deadline. No special treatment.

## 4. Resolve FAAB (script decides)

Assemble all teams' claims into the claims JSON `faab.py` expects
(`{team: [{add, drop, bid, reasoning}]}`) and the worst→best standings list, then:

```bash
python scripts/faab.py --claims <claims.json> --standings <standings.json> \
  --report-out state/weeks/2026-w<WW>/faab-report.json --dry-run
```

Use `--dry-run` first to get the resolution report for the commissioner to
review; do NOT apply yet. `faab.py` enforces the rules (highest bid; tie → worse
standing; drop-consumption; budget). Never hand-resolve a bid.

## 5. Trades

Enforce: max ONE outgoing offer per team per week; deadline end of week 11
(reject offers from week 12 on). For each offer, give the TARGET team's agent
(or human) one accept/reject/counter; on a counter, the offerer gets a final
accept/reject. Isolation still holds — the target agent sees only its own GM
file plus the offer terms. Validate any resulting roster swap with
`scripts/lib/rosters.apply_transaction` (it refuses illegal results).

## 6. Commissioner review, then apply

Spawn the Commissioner subagent (`agents/commissioner.md` — the ONE agent
allowed to read every GM file). Give it the FAAB dry-run report, all decisions,
and the trade outcomes. It BLOCKS only rule violations (illegal rosters, over-budget
bids, nonexistent/duplicate players, second trade offers, out-of-window GM
edits, unparseable-after-retry output) and must NOT block legal-but-dumb moves
(chaos is legal). Record any ruling in `state/rulings.md`.

Once the commissioner approves, apply for real:

```bash
python scripts/faab.py --claims <claims.json> --standings <standings.json> \
  --report-out state/weeks/2026-w<WW>/faab-report.json
```

(no `--dry-run` — this applies won claims to rosters and appends to
`state/transactions.jsonl`). Apply approved trades the same way. Every applied
action must land in `state/transactions.jsonl` with timestamp, team, action,
players, bid, reasoning, status.

## 7. Commit (exactly one)

Stage the updated rosters, `state/transactions.jsonl`, `state/free-agents.json`,
the FAAB report, and any ruling, and make ONE commit: `week <WW>: saturday`.
Never commit mid-run.
