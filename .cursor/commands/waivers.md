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
`packs/<slug>.json`. All 12 GMs, the owned two (`your-team`, `wifes-team`)
included, answer through **`scripts/gm_turn.py`**: one command, not 12
pastes, each team an isolated `claude -p` turn (step 3). Reply = schema JSON
only. The daily `bowl_league_ops` routine (`routines/bowl_league_ops.md`)
runs this command when the ops call is `waivers`.

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
python scripts/buzz_inbox.py   --week <WW>   # Grok automation's X drop -> canonical buzz file
python scripts/fetch_buzz.py   --week <WW>   # owner file wins; no GROK_API_KEY set, so else skip
python scripts/gm_pack.py      --week <WW> --run waivers
```

Worst→best standings order from `state/standings.json` (record, then PF) —
the FAAB tiebreak list, worst first. If standings do not exist yet (week 1),
use the documented proxy in `state/rulings.md`.

## 2. Tabloid (before anyone moves)

Kris Jenner (`agents/media.md`) gets PUBLIC RECORD only: `news-facts.json`,
this week's buzz file if present, last week's forum, last recap, standings.
NEVER a GM file. Default: her own isolated turn, which builds that pack and
writes `state/news/2026-w<WW>.md`:

```bash
python scripts/agent_turn.py --role media --week <WW>
```

Optional path, only while the local Grok gateway is running: message the
Kris Jenner Grok Bot (`bots/skill-media.md`) with the same public record.
Rebuild packs after she publishes so GMs see the tabloid:

```bash
python scripts/gm_pack.py --week <WW> --run waivers
```

## 3. GM decisions — all 12 through `gm_turn.py`

```bash
python scripts/gm_turn.py --week <WW> --run waivers
```

The default since 2026-10-15, for all 12 teams, the owned two included (no
Cursor). Each team runs as an isolated `claude -p` call on Sonnet with an
empty working directory, so there is no repo to read. Turn one fires alone
to warm the shared cache prefix before the other eleven fan out, so bids
stay blind by construction rather than by convention. Writes
`state/weeks/2026-w<WW>/decisions/<slug>.json`. Reverse-standings order is
context only; bids are blind. `--dry-run` sizes the prompts without calling;
`--save-raw DIR` keeps the raw envelopes when something fails to validate.
If the `claude` CLI is missing or cannot authenticate, stop: do not answer
for the GMs.

### Optional: the Grok Bot gateway

Only while Nick's local Grok gateway is running (a cloud routine cannot
reach it), the celebrity GMs can answer as Grok Bots instead:

```bash
python scripts/grok_bots.py dispatch --week <WW> --kind waivers
```

The owned two still go through `gm_turn.py --team <slug>`; they never go on
the shared Bot disk. Roster check: `python scripts/grok_bots.py check`.

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

Max three outgoing offers per team; deadline end of week 11. A target answers all offers sent to it in ONE turn. If several of a team's own offers are accepted and conflict, that team's GM picks which to honour. After the harness
validates the offer, ask **only the target**:

```bash
python scripts/gm_turn.py --week <WW> --run trades --team <target> \
  --offer <offer.json>
```

The default since 2026-10-15. Optional, only while the local Grok gateway
is running and the target is a celebrity GM:
`python scripts/grok_bots.py dispatch --week <WW> --kind trades --slug <target> --offer <offer.json>`.

### Screened trades

`scripts/office.py`'s waivers stage runs this for you:
`lib/trades.screen_offers` checks every outgoing offer against both rosters
first — the offerer really holds what it is sending, the target really holds
what is being asked for, and both rosters survive the swap — and only the
offers that pass become an agent turn. That is the §5 rule enforced in code
rather than by hand: week 1 burned ten turns on players who were not where
the offerer thought they were.

Every verdict, including the rejections nobody was asked about, is written to
`state/weeks/2026-w<WW>/trade-screen.json` and goes into the commissioner's
review pack. A target that cannot be parsed falls back to `reject` — a GM who
cannot be understood has not agreed to anything.

## 6. Commissioner review, then apply

The commissioner (`agents/commissioner.md`) reviews the dry-run + decision
JSON in its own isolated turn, which writes
`state/weeks/2026-w<WW>/commissioner-signoff.md`:

```bash
python scripts/agent_turn.py --role commissioner --week <WW> --stage waivers
```

(Optional path: the Commissioner Grok Bot, `bots/skill-commish.md`, while
the gateway runs.) GM files in chat only, never left on a shared disk.
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

Push to `main`. GitHub Pages rebuilds the board. Optional local preview:
`python scripts/build_viewer.py --season 2026`.
