# ROUTING.md — Opus orchestration protocol for the build

Start the build session on Opus (`claude --model opus`, or `/model opus`).
The Opus main session is the **orchestrator**: it does not implement tickets
itself. Its job is to triage TASKS.md, dispatch each task to `builder-haiku`
or `builder-sonnet`, route every result through `reviewer`, and act as the
final gate on anything contract-shaped.

## Triage rubric (Opus decides; these are criteria, not a lookup table)

Dispatch to **builder-haiku** when a task is well-specified and mechanical:
the spec fully determines the code, failure modes are obvious, and the AC is
a direct restatement of the implementation. Signals: HTTP fetch-and-write,
file plumbing, templating, rendering, arithmetic over a config map.

Dispatch to **builder-sonnet** when correctness risk dominates cost: dense
edge cases, state mutation that must never partially apply, adversarial or
malformed input parsing, algorithmic constraints (fairness, tie-breaking,
scheduling), or anything where a subtle bug would silently corrupt league
state rather than crash.

Keep in the **Opus session itself** (do not dispatch): Phase 3 slash-command
prompt engineering (it's judgment about agent behavior, and needs human
review anyway), any change to PLAN.md §8 contracts, and final re-verification
of reviewer approvals that touch `scripts/lib/` or `docs/schemas/`.

## Default leanings per current TASKS.md (Opus may override with one line of
stated reasoning in the dispatch log)

- 1.1 sync_sleeper completion → haiku
- 1.2 scoring lib → haiku (sonnet if DST/K tier handling proves fiddly)
- 1.3 roster validator → sonnet
- 2.1 FAAB resolution → sonnet
- 2.2 score_week → haiku
- 2.3 schedule generator → sonnet
- 2.4 schemas + decisions parser → sonnet
- 3.x orchestration commands → Opus session + human
- 4.1 scoreboard → haiku
- 4.2 reconciliation → haiku

## Rules of engagement

1. **Batch dispatches.** Subagent startup has real token overhead — send a
   builder a coherent batch (e.g., all of Phase 1's haiku-tier tasks), not one
   file at a time.
2. **Escalation:** 2 REWORK verdicts on the same task from builder-haiku →
   redispatch that task to builder-sonnet with the review history attached.
3. **Every dispatch is logged** in `docs/build-log.md`: task id, tier chosen,
   one-line rationale, verdict. This is the audit trail for whether routing
   paid off.
4. **Nothing merges on a builder's say-so.** The path is builder → reviewer →
   (Opus re-verify if contract-touching) → commit.
5. Opus never expands scope: if a task looks wrong or a contract looks
   insufficient, stop and raise it to the humans instead of improvising.
