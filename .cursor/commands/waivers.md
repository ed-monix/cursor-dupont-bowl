---
description: Weekly waiver/trade run — tabloid, FAAB, drops, trade offers (not tied to a weekday)
argument-hint: <week number, e.g. 2>
---

# /waivers — roster run, week $ARGUMENTS

Weekly waiver/trade cycle (PLAN.md §4). Season 2026; `WW` = zero-padded week
from `$ARGUMENTS` (ask if empty). Run this once before the week's first
kickoff — typically Tuesday/Wednesday, not "Saturday." NFL games fall on
Thursday (and sometimes Wednesday); weekday command names are retired.

Hard rules: isolation, notes are pressure, scripts decide facts, everything
logged, one commit, commissioner reviews before apply.

## Token diet (required)

Do **not** dump `state/players.json` or the full 693-player free-agent file
into any GM turn. After the syncs below:

```bash
python scripts/gm_pack.py --week <WW> --run waivers
```

That writes `state/weeks/2026-w<WW>/packs/public.json` and
`packs/<slug>.json`. Each GM subagent is **inline-only**: paste
`python scripts/gm_pack.py --week <WW> --team <slug> --run waivers --prompt`
(or the written pack) and say: everything you need is in this prompt; do
NOT read files, run commands, or use tools. Reply with schema JSON only.

GMs never see `state/news/buzz/`. One Scout (`fetch_buzz.py` / owner paste)
writes buzz; Media rewrites the tabloid; then GMs read the tabloid only.

## 1. Sync + derive (scripts decide facts)

```bash
python scripts/sync_sleeper.py --players
python scripts/sync_sleeper.py --projections --week <WW>
python scripts/sync_sleeper.py --schedule --week <WW>
python scripts/free_agents.py  --week <WW>
python scripts/league_board.py --week <WW>
python scripts/derive_news.py  --week <WW>
python scripts/fetch_buzz.py   --week <WW>   # owner file wins; else GROK_API_KEY; else skip
python scripts/gm_pack.py      --week <WW> --run waivers
```

Worst→best standings order from `state/standings.json` (record, then PF) —
the FAAB tiebreak list, worst first. If standings do not exist yet (week 1),
use the documented proxy in `state/rulings.md`.

## 2. Tabloid (before anyone moves)

Spawn Media (`agents/media.md`) with PUBLIC RECORD only: `news-facts.json`,
this week's buzz file if present, last week's forum, last recap, standings.
She writes `state/news/2026-w<WW>.md`. Rebuild packs after she publishes so
GMs see the tabloid. NEVER a GM file. Rebuild:

```bash
python scripts/gm_pack.py --week <WW> --run waivers
```

## 3. GM decisions — 12 inline packs, tools off

For every `teams/` slug except `_template`, spawn ONE subagent with ONLY
that team's pack (never another GM file). Reverse-standings order is
context only; bids are blind.

Parse with `decisions.parse_and_validate` against
`docs/schemas/saturday-decision.json` (filename kept; this is the waiver
decision schema). Retry once. Still failing → no claims this week,
`fallback: true`. Write each validated object to
`state/weeks/2026-w<WW>/decisions/<slug>.json`.

Forum posts: `forum.append_post`. Quote reasoning verbatim.

**Validate trade offers in the harness before spawning the target.** Week 1
burned 10 extra turns on players who were not where the offerer thought.
`rosters.apply_transaction` refuses illegal swaps — skip the target spawn.

## 4. FAAB (script decides)

```bash
python scripts/faab.py --claims <claims.json> --standings <standings.json> \
  --report-out state/weeks/2026-w<WW>/faab-report.json --dry-run
```

Do not apply yet.

## 5. Trades

Max one outgoing offer per team; deadline end of week 11. Target GM gets
its own pack + the offer JSON (tools off). Counter → original offerer once.
Validate with `apply_transaction`.

## 6. Commissioner review, then apply

Commissioner (`agents/commissioner.md`) reviews the dry-run + decision JSON.
Blocks only illegal. Does **not** apply FAAB or mutate rosters. Then:

```bash
python scripts/faab.py --claims <claims.json> --standings <standings.json> \
  --report-out state/weeks/2026-w<WW>/faab-report.json
```

Apply approved trades the same way. Log `state/transactions.jsonl`.
`gm_dossier.append_press` for each team.

## 7. Commit (exactly one)

`week <WW>: waivers`

Stage rosters, transactions, free-agents, league-board, news, week folder
(news-facts, faab-report, packs, decisions), forum, press, rulings.

## 8. Viewer

`python scripts/build_viewer.py --season 2026` then `/refresh-board` from an
interactive session if this sitting has no Artifact tool.
