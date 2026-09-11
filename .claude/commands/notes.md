---
description: Scaffold owner-note files for the week — the owners' two teams ONLY (the tabloid meddles with everyone else)
argument-hint: <week number, e.g. 5>
---

# /notes — scaffold owner notes for week $ARGUMENTS

Owner notes are the meddling-owner mechanic, and they go ONLY to the two
teams the humans actually own — `your-team` and `wifes-team`. Each owner
writes to their own GM, whose reading of the note is as free as anyone
else's: obey, ignore, or spite (PLAN.md §4, CLAUDE.md rules 2 and 7). The
ten celebrity GMs get NO owner notes — nobody owns them; their outside
pressure is Kris Jenner's tabloid (`state/news/`), which meddles with
everyone. Notes are *pressure, not orders*. This command just creates the
empty files for the owners to fill in before the waiver run.

Season is 2026 unless the repo's data says otherwise. Let `WW` be the two-digit,
zero-padded week from `$ARGUMENTS` (e.g. `5` → `05`). If `$ARGUMENTS` is empty,
ask the human which week, then proceed.

Do this:

1. **The owner teams only:** `teams/your-team` and `teams/wifes-team`. No
   other team gets a note file — the celebrity GMs answer to no owner, and
   creating note files for them is a mistake to report, not repeat.
2. **For each of the two**, if `teams/<slug>/notes/2026-w<WW>.md` does not already
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
Owners should file the weekly note before **`/waivers`**. Optional **gameday**
notes (`2026-w<WW>-early.md` before Thursday games, `2026-w<WW>-main.md`
before Sunday) are how the two owners talk to their GM on kickoff day.
The Commissioner wakes GMs that morning; the pack includes those files.

2. **For each of the two**, if `teams/<slug>/notes/2026-w<WW>.md` does not already
   exist, create it from this stub (create the `notes/` folder if missing).
   Never overwrite an existing note — if it exists, leave it and report that.

   Also scaffold (same never-overwrite rule):
   `2026-w<WW>-early.md` and `2026-w<WW>-main.md` with:

   ```md
   # Gameday note — <slug>, 2026 Week <WW> (<early|main>)

   <!--
   Optional. File this the morning of that window's games (Thu / Sun).
   Pressure, not orders. The GM reads it in the lineup pack.
   -->
   ```
