# DuPont Bowl — Detailed Plan

This is the design document. `TASKS.md` breaks it into build tickets for the
build agent. `CLAUDE.md` tells Claude Code how to operate the league in-season.

---

## 1. Architecture overview

The repo **is** the league. There is no server, no database, no hosted app.

- **State = files.** Rosters, free agents, standings, matchups, and the
  transaction log are JSON/JSONL files in `state/` and `teams/`. Git history is
  the league's permanent, tamper-evident record.
- **Grok Bots + Cursor = harness.** Celebrity GMs, Scout, Media, and the
  Commissioner are Grok Bots (`config/grok-bots.json`). Owned GMs stay in
  Cursor. Slash commands in `.cursor/commands/` orchestrate: scripts build
  packs; Bots get pack-in-chat (tools off). Do not clone this repo onto the
  shared Grok Bot computer.
- **Python scripts = the deterministic parts.** Anything that must be exactly
  right — scoring math, roster legality, FAAB resolution, Sleeper syncing —
  is a script, not a judgment call. Agents decide; scripts validate and apply.
- **Sleeper = data source + rulebook.** We never write to Sleeper. We read:
  league settings (once, from a reference league), the master player list,
  weekly projections, injury statuses, and live/final stats.

### Division of labor per weekly run

```
Orchestrator (Cursor)
  ├─ runs sync + gm_pack.py (public pack + 12 private packs)
  ├─ Scout Bot + Media Bot (buzz → tabloid); GMs never see buzz/
  ├─ grok_bots.py dispatch (10 Grok Bot GMs) + 2 Cursor owned-GM turns
  │     → state/weeks/.../decisions/<slug>.json
  ├─ validators (faab.py, lineups.py)
  ├─ Commissioner Bot reviews; scripts apply
  └─ one git commit per run
```

## 2. League format (Sleeper standard)

Source of truth: create a free **reference league** in the Sleeper app with
default settings, then run `sync_sleeper.py --league <id> --settings`, which
writes `config/scoring.json` and `config/roster.json` verbatim from the API.
`config/scoring.default.json` ships in the repo as the fallback and encodes
Sleeper's standard format:

- **Scoring:** Half-PPR (0.5/rec), 4-pt pass TD, 0.04/pass yd, -1 INT,
  0.1/rush & rec yd, 6-pt rush/rec TD, -2 fumble lost, standard K tiers,
  standard DST points-allowed tiers.
- **Roster:** QB, RB, RB, WR, WR, TE, FLEX (RB/WR/TE), K, DEF, 6 BN, 1 IR.
- **12 teams**, head-to-head, weeks 1–14 regular season, 6-team playoff
  weeks 15–17 (seeds 1–2 byes). Schedule generated at draft time
  (`state/schedule.json`); each team plays divisional-style round robin, then
  repeats — build agent implements any standard 12-team/14-week generator.
- **Tiebreakers:** standings by record → total points for. Weekly matchup ties
  stand as ties.

## 3. Teams and the GM file contract

Each team folder:

```
teams/<slug>/
├── general-manager.md   # the ONLY strategy input for AI teams
├── roster.json          # current roster: player_ids by slot + FAAB remaining
├── notes/               # owner notes: YYYY-WW.md, plus the GM's replies
└── press/               # optional: the GM's logged statements, trash talk
```

`general-manager.md` sections (see `teams/_template/`): Identity & Voice,
Football Philosophy, Draft Strategy, Weekly Roster Policy (waivers/FAAB curve,
drop rules, loyalty), Lineup Rules, Trade Personality, **Reaction to Ownership**
(how notes affect behavior), and Tiebreakers. Cap ~1,500 words. For the ten
celebrity teams: affectionate caricature — personality, vibes, and public
persona translated into *mechanical* biases (what they overpay for, what they
refuse to roster, how they take criticism).

**Owner teams:** `your-team` and `wifes-team` are run by their own GM agents
like every other team — same GM-file contract, isolation, validators,
deadlines, and FAAB process. The humans are owners, not managers: they never
type moves; they influence their GM the same way they influence anyone
else's — owner notes, which their GM is free to obey, ignore, or spite.

**Edit rule:** each AI team's GM file may be rewritten up to 3 times in-season,
only during note windows (the git commit is the record). Bug fixes to broken
formatting don't count; strategy changes do. Commissioner arbitrates which is
which.

## 4. Weekly operations

### Fri/Sat — Owner notes (humans, ~5 min)
Each owner drops `teams/<slug>/notes/2026-w05.md` for their OWN team only —
`your-team` and `wifes-team` are the league's only owned teams, and the note
is the humans' ONLY input into any roster. The ten celebrity GMs receive no
owner notes; their outside pressure is the tabloid (`state/news/`, §4a).
Short, in-character as a meddling owner. `/notes` command scaffolds empty note files for the week.
Notes are *pressure, not instructions* — the run prompt explicitly tells agents
the note is owner sentiment they may obey, ignore, or spite.

### Waivers — Roster run (`/waivers`)
Once per week, before the first kickoff (typically Tue/Wed — not "Saturday").
1. Sync: injuries, projections, NFL game dates (`--schedule`), free-agent pool.
2. Build dieted packs (`scripts/gm_pack.py`). One Scout writes optional X buzz;
   Media rewrites the tabloid; GMs never see `buzz/` or `players.json`.
3. Each GM — all 12 teams, inline pack, tools off — outputs JSON matching
   `docs/schemas/saturday-decision.json` (waiver decision schema):
   `{claims: [{add, drop, bid}], drops: [], trade_offer?, note_reply}`.
   Write each to `state/weeks/<season>-w<NN>/decisions/<slug>.json`.
4. FAAB resolution script: highest bid wins; ties → worse standing wins; a team
   can't win two claims that need the same drop. Budget $100/season, min bid $0.
5. Trades: validate the offer in the harness **before** spawning the target.
   Target gets one accept/reject/counter; offerer gets final accept/reject on a
   counter. Max one outgoing offer per team per week. Trade deadline end of week 11.
6. Commissioner reviews everything (see §5), then the validator applies
   approved transactions to rosters and appends to `state/transactions.jsonl`.
   The commissioner does not apply FAAB itself.

### Lineups — per NFL window (`/lineups`)
NFL games are not only on Sunday. Run this command **twice** most weeks:

- `early` — before Tuesday–Saturday kickoffs (TNF, and any Wed/Fri/Sat games).
  Only those slots freeze.
- `main` — before the Sunday slate, after late injury news. Sunday and Monday
  (MNF) slots freeze. Already-frozen early slots cannot move. A game that has
  already kicked (`in_game` / `complete`) is frozen even if a window was skipped.

1. Injury/inactives + schedule sync. Rebuild packs. Do **not** give GMs
   `players.json`; status/injury/window are on the pack's board rows.
2. Each GM sets a full legal lineup + 1-paragraph justification.
3. `scripts/lib/lineup_windows.merge_lineup` decides which slots actually
   change. Validator: legal slots, no BYE/Out starters without acknowledgment.
   One retry, then fallback = highest-projected legal lineup that **keeps
   frozen slots**, logged `fallback: true`.
4. A week may have two lineup commits: `week NN: lineups-early` and
   `week NN: lineups-main`.

### Results (`/recap`)
1. Pull final stats, score all matchups with `score_week.py`, reconcile any
   live-feed drift, update `state/standings.json`.
2. Commissioner writes `state/weeks/2026-w05/recap.md`: results, best/worst
   decisions, fallback hall of shame, storylines. This recap is the input
   humans read before writing next week's notes — it closes the loop.

## 5. The Commissioner

Defined in `agents/commissioner.md`; invoked at the end of every run and for
`/recap`. Powers are deliberately narrow:

- **Must block:** illegal rosters, budget violations, transactions for players
  who don't exist / already rostered, second trade offers, edits outside
  windows, any output that isn't parseable after retry.
- **Must flag but NOT block:** lopsided-but-legal trades, insane FAAB bids,
  benching studs. Flags go in the recap. (Mission: chaos is legal.)
- **Collusion check:** the only judgment veto — a trade may be voided only if
  it has no plausible in-character rationale for *both* sides. Expected to be
  used ~never; requires a written ruling in `state/rulings.md`.
- **Duties:** resolve FAAB ties, arbitrate edit-rule disputes, maintain
  standings, write the weekly recap in its own voice (world-weary league
  official who has seen too much).

The commissioner agent gets read access to everything, including all GM files —
it's the one agent allowed to see behind the curtain.

## 6. Draft (`/draft`)

Late-August live session, run in one Claude Code sitting with both humans
watching:

1. `sync_sleeper.py --players --projections` for the board (ADP from Sleeper).
2. Randomized snake order, 15 rounds, 180 picks.
3. Every pick is a GM pick — all 12 teams: subagent per pick with only that
   team's GM file + board + own roster (+ the public running draft log);
   outputs pick + one line of in-character commentary, printed live. The
   humans watch their own GM draft their team, which is the entertainment.
4. Output: all `roster.json` files, `state/draft-log.jsonl`,
   `state/schedule.json`, and a commissioner draft-grades column (guaranteed to
   be unfair).

Dress rehearsal requirement: a full 15-round mock with 12 AI teams must run
clean before draft day.

## 7. Live scoreboard

`scripts/scoreboard.py` — single-file Flask app on `localhost:8080`:

- Poll Sleeper week stats every 45s on game days; join vs. starting lineups;
  apply `config/scoring.json`; serve 6 matchup cards (score, per-player points,
  players yet to play, live win indicator). Auto-refresh page; zero hosting.
- Sleeper's stats endpoints are unofficial → the Monday `/recap` re-pull is the
  official result; the live board is entertainment.
- Fallback if the stats endpoint changes mid-season: swap the poller's fetch
  function (it's isolated behind one interface) or degrade to manual refresh
  from another free source.

## 8. Data contracts (build agent: keep these stable)

State lives in files; git history is the league's permanent record. This is the
**full** contract list — never add a state file without adding it here (CLAUDE.md
build rule). Shapes below are authoritative; the JSON Schemas in `docs/schemas/`
validate agent output.

### Config
- `config/scoring.json` — Sleeper `scoring_settings` map, verbatim keys (`rec`,
  `pass_td`, `rush_yd`, `pts_allow_*`, `fgm_*`, ...). Falls back to
  `config/scoring.default.json` (Sleeper standard half-PPR) when unsynced.
- `config/grok-bots.json` — Bot roster: `{version, isolation, roles[]}`. Each
  role has `id`, `kind` (scout|media|commissioner|gm), `product`
  (grok_bot|cursor), `computer` (shared|none), and isolation flags. Owned
  teams must be `off_shared_disk`. `share_url` and `gateway_agent_id` are
  optional (filled after `grok_bots.py ensure` or a manual Bot create).
  Validated by `scripts/grok_bots.py check`.
- `config/roster.json` — as written by `sync_sleeper.py`:
  `{roster_positions: [str,...], settings: {...}}`. Engine code that needs the
  slot structure consumes it via `lib.rosters.roster_config_from_league()`, which
  adapts it to the validator's `{starters: {slot: [pos,...]}, bench_slots,
  ir_slots}` shape.

### Core state
- `state/players.json` — trimmed players dump: `id → {name, pos, team, status,
  injury}`. Refreshed weekly (~5MB full dump; trimmed to active QB/RB/WR/TE/K/DEF).
- `teams/*/roster.json` — `{team, faab_remaining, starters: {slot: player_id|null},
  bench: [id,...], ir: [id,...]}`.
- `state/schedule.json` — `{regular_season: {"1": [[home,away],...6 pairs], ...,
  "14": ...}, playoffs: {"15": [...], "16": ..., "17": ...}}` (playoff pairings by
  seed placeholder). Generated at draft.
- `state/standings.json` — `{season, official_weeks: [int,...], teams: {slug:
  {wins, losses, ties, points_for, points_against}}}`.
- `state/transactions.jsonl` — append-only; one object per applied action,
  conforming to `docs/schemas/transaction-entry.json`: `{timestamp, team, action
  ∈ [add,drop,waiver_claim,trade], players: [id,...], bid: int|null, reasoning,
  status ∈ [applied,rejected,flagged]}`.
- `state/rulings.md` — commissioner rulings + GM-file edit counts (prose).

### Derived state (regenerated from the above; never hand-edited)
- `state/free-agents.json` — every unrostered player with context for the
  Saturday board: `{id: {name, pos, team, status, injury, proj_pts, proj: {…few
  raw projection keys…}, last_wk_pts}}`. `proj_pts` is the scored projection.
- `state/league-board.json` — all 12 rosters resolved for scouting/trades:
  `{slug: {starters: {slot: {id, name, pos, nfl, proj_pts, status, injury}}, bench: [...], ir:
  [...], faab_remaining}}`. Rosters + FAAB are public record (only GM files are
  secret).
- `state/nfl-schedule.json` — compact regular-season NFL games from
  `sync_sleeper.py --schedule` (`date, status, home, away, week, game_id`).

### Per-week state (`state/weeks/<season>-w<NN>/`)
- `projections.json`, `stats.json` — Sleeper API responses as-is `{id: {stats}}`.
- `live-scores.json` — snapshot of the live scoreboard's per-player points
  `{id: pts}`, written each poll; the Monday `/recap` reconciliation reads it.
- `matchups.json` — scored matchups `{season, week, matchups: [{home, away,
  home_score, away_score, home_lineup, away_lineup, winner}]}`.
- `lineups.json` — starters plus lock state `{slug: {starters: {slot: id},
  locked_slots: {slot: {player_id, window, nfl, game_date, kicked}},
  windows_run: ["early"|"main", ...], justification, justifications, fallback}}`.
  A week may accumulate two `/lineups` windows.
- `nfl-games.json` — that week's slice of `state/nfl-schedule.json`.
- `packs/` — derived GM packs (`public.json`, `<slug>.json`, `sizes.json`).
  Regenerated by `scripts/gm_pack.py`; GMs consume these instead of `players.json`.
- `decisions/<slug>.json` — validated waiver JSON; lineup windows write
  `<slug>.lineup-early.json` / `<slug>.lineup-main.json`. Harness cache; scripts apply.
- `faab-report.json` — the FAAB resolution report for the week (from `faab.py`).
- `news-facts.json` — deterministic headline facts from `derive_news.py` (the
  media agent's input for the weekly tabloid).
- `recap.md` — the commissioner's weekly recap column.
- `commissioner-memo.md` — week 01 only: the pre-kickoff `/cutdown` memo
  (league-office corrections, script-derived roster-imbalance facts, and the
  window's one-time provisions, all also logged in `state/rulings.md`).

### GM memory & the shared record (the personality substrate)
- `teams/*/notes/2026-wNN.md` — owner notes (human input) plus the GM's replies.
- `teams/*/press/2026-wNN.md` — the GM's public paper trail: note replies and
  logged reasoning appended each run (read back as grudge fuel via the dossier).
- `teams/*/opinions.json` — this GM's seeded preseason opinion of every other
  character (the 11 other GMs + `commissioner` + `media`), from `/gms-meeting`;
  validated by `docs/schemas/gm-opinions.json`. Joins the team's dossier as
  priors; agent-private (only its own GM and the commissioner load it);
  rewritable under GM-file governance (3 edits/season, note windows, logged in
  `state/rulings.md`).
- `state/forum/2026-wNN.jsonl` — append-only weekly trash-talk thread, one post
  per entry `{timestamp, team, post}`; at most one post per GM per run. Public
  record; the commissioner blocks transactions, never speech.
- `state/news/2026-wNN.md` — the media mogul's (`agents/media.md`) weekly
  tabloid, published before the `/waivers` run from `news-facts.json` + any
  owner-planted rumors + the week's buzz file when present. Public voice; she
  holds no powers and never reads a GM file.
- `state/news/buzz/2026-wNN.md` — OPTIONAL weekly real-world X buzz for the
  tabloid (`scripts/fetch_buzz.py`): the owner-pasted file wins; else one xAI
  API call with live X search when `GROK_API_KEY` is set; else absent and the
  run proceeds without it. Sentiment only — no script or validator ever reads
  it, Sleeper remains the sole source of facts, and GMs only ever see the
  mogul's rewrite, never this file.

### Draft
- `state/draft-log.jsonl` — one object per pick `{pick_no, round, team,
  player_id, name, pos, commentary}`.
- `state/draft-grades.md` — the commissioner's (unfair) draft-grades column.

### Agent output
- JSON Schemas in `docs/schemas/`: `saturday-decision`, `sunday-lineup`,
  `trade-offer`, `trade-response`, `transaction-entry`, `gm-opinions`.
  `saturday-decision` and `sunday-lineup` carry an optional `forum_post` string.

## 9. Costs & model policy

The GM file is the only personality variable. Volume is **not** cheap:
12 GMs × (waivers + two lineup windows + trade responses) plus Media and
Commissioner, every week. Do not plan that volume on Claude-in-Cursor.

Token diet (required): `scripts/gm_pack.py` builds one public pack and one
private pack per GM. Celebrity GM turns are Grok Bots (`grok_bots.py dispatch`
via the desktop gateway; tools off). Owned GMs are Cursor pack-only, off
the shared Bot disk. Never
`players.json`, never another GM file, never `buzz/`. One Scout writes buzz.
Scripts do math. Composer is for mechanical file transforms only.
Do not plan that volume on Claude-in-Cursor.

Personality stays the product: do not flatten to "start the highest projection."

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Sleeper unofficial endpoints change | Isolated fetch layer; Monday reconciliation is official |
| Agent outputs garbage | Retry once → deterministic fallback, logged |
| State corruption | Git = undo button; every run commits atomically at the end |
| Runs get skipped (life happens) | Commands are idempotent; a missed Saturday just runs late; lineup fallback covers a missed Sunday |
| Personalities converge to "start best projection" | GM template forces mechanical biases; recap publicly scores "most in-character move" |
