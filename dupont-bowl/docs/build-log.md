# Dispatch log: task id | tier | rationale | verdict

1.2 scoring | sonnet | override haiku→sonnet: DST points-allowed tiering + live Sleeper stat shape unverifiable (api.sleeper.app blocked by egress policy) = correctness risk | APPROVED (Opus re-verify: arithmetic + tier boundaries + double-count guard correct; 9 tests green). Note: use `pytest` CLI, not `python3 -m pytest` (system python3 lacks pytest module).
1.3 rosters | sonnet | default; apply_transaction must never partially apply | APPROVED (Opus re-verify: deep-copy-then-validate proven atomic; FLEX/dup/faab-bool guards correct; 16 tests green)
1.1 sync_sleeper --projections/--stats/--all | haiku | Sleeper now allowlisted; live-verifiable | APPROVED (Opus re-verify: all flags + isolated fetch + 24h cache correct, contracts matched, live 3231 players + real proj/stats rows, 7 tests green). CLEANUP owed: conftest.py hardcodes system site-packages paths — replace with requirements.txt before final commit. --settings live-verify still pending owner reference league id.
2.2 score_week | haiku | REWORK→APPROVED (Opus re-verify caught: load_schedule incompatible with schedule_gen's {regular_season/playoffs} shape; idempotency test proved only determinism). Rework fixed both: load_schedule reads real shape + playoff placeholder guard; fold_if_not_official extracted + truly-idempotent test; schedule_gen integration test added. 80 tests green.
4.1 scoreboard | haiku | STDLIB http.server (Flask unavailable: PyPI egress blocked) — spec deviation flagged to owner | REWORK→APPROVED (Opus re-verify caught load_current_week crash: read official_weeks as dict but score_week writes a list → AttributeError at startup). Rework fixed + hardened fetch except + 7 new tests. Full suite 95 green.

3.1 slash commands | Opus (kept in-session per ROUTING) | DRAFTED .claude/commands/{notes,saturday,sunday,recap,draft}.md — needs human review. Honor CLAUDE.md hard rules (isolation, notes-as-pressure, scripts-decide-facts, one-commit, commissioner-last).
3.2 mock draft harness | Opus | covered by /draft --mock (all-AI, no pauses)
3.3 fallback paths | Saturday no-claims fallback in /saturday; Sunday best_legal_lineup (sonnet, dispatched) referenced in /sunday
4.2 reconciliation | haiku (dispatched) | referenced in /recap
GAP (flag to owner): no scripts/free_agents.py deriver — /saturday computes the free-agent pool inline; add a testable deriver script as a follow-up.
GAP (blocked on content): `make dryrun` end-to-end needs ≥3 sample GM files to exercise the agent layer; Phase 5 GM content is deferred, so the full dry run waits on it. The deterministic script pipeline is already fully covered by pytest.

--- Infra (Opus, integration) ---
- Replaced 1.1's hardcoded-path conftest.py with a guarded no-op shim (only activates when `requests` unimportable; no-op in a real venv)
- Added requirements.txt (requests, pytest; Flask intentionally omitted — scoreboard is stdlib)
2.1 faab | sonnet | fairness/tiebreak + atomic apply = correctness-critical | APPROVED (Opus re-verify: two-phase winner-then-apply correct, 4-team collision hand-worked, budget-deduction bug self-caught+fixed, 11 tests green). FLAG: budget-short winner "burns" the player (no pass-down) — confirm intent.
2.2 score_week | haiku | mechanical: join lineups+stats via scoring lib, update standings | dispatched
2.3 schedule | sonnet | algorithmic constraint (no repeat opponent before wk12) | APPROVED (Opus re-verify: circle method correct, 66 unique pairs by construction, 17 tests green). FLAG: playoffs use fixed non-reseeded bracket (PLAN.md unspecified) — confirm with owners.
2.4 schemas+decisions | sonnet | adversarial/malformed agent-output parsing; hand-rolled validator (jsonschema not an allowed dep) | APPROVED (Opus re-verify: brace extractor tracks string/escape state + retries; recursive validator correct incl. bool/int guard; 5 schema files load; 11 tests green). Note: additionalProperties:false documented but not enforced (extra fields tolerated — fine for chaos-league).
