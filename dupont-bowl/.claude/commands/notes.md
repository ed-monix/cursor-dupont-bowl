---
description: Scaffold empty owner-note files for the week (the humans' only input to the AI GMs)
argument-hint: <week number, e.g. 5>
---

# /notes — scaffold owner notes for week $ARGUMENTS

Owner notes are the meddling-owner mechanic: the ONLY in-season human input the
AI GMs ever receive (PLAN.md §4, CLAUDE.md rule 2). They are *pressure, not
orders* — each GM interprets its note in character and may obey, ignore, or
spite it. This command just creates the empty files for the humans to fill in
before the Saturday run.

Season is 2026 unless the repo's data says otherwise. Let `WW` be the two-digit,
zero-padded week from `$ARGUMENTS` (e.g. `5` → `05`). If `$ARGUMENTS` is empty,
ask the human which week, then proceed.

Do this:

1. **List the AI teams.** Every directory under `teams/` except `_template`,
   `your-team`, and `wifes-team` is an AI team. (The two human teams get no
   note — the humans run those directly.)
2. **For each AI team**, if `teams/<slug>/notes/2026-w<WW>.md` does not already
   exist, create it from this stub (create the `notes/` folder if missing).
   Never overwrite an existing note — if it exists, leave it and report that.

   ```md
   # Owner note — <slug>, 2026 Week <WW>

   <!--
   You are the meddling owner. Write a few sentences of in-character performance
   feedback, praise, or provocation. The GM will read this as sentiment, not
   instructions — it may act on it, ignore it, or spite it. Keep it short.
   Delete this comment or leave it; the GM ignores HTML comments either way.
   -->
   ```

3. **Report** a short list: which note files you created and which already
   existed (skipped). Do not write any note content yourself — that's the
   humans' job.

4. **Commit.** Stage the new note stubs and make exactly ONE commit (CLAUDE.md
   rule 5): `week <WW>: notes`. Nothing else in this command writes state.

This command spawns no agents and runs no scripts — it is pure scaffolding.
