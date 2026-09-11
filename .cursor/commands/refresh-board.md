---
description: Refresh the live board — sync stats, rebuild the viewer, republish the artifact
---

# /refresh-board — one live-board refresh pass

Run this on game-day Sundays from an **interactive session** (which has the
Artifact tool). To refresh every ~10 minutes through the games, start it as a
loop and leave it running, then stop it when the games end:

```
/loop 10m /refresh-board
```

One pass does exactly this — mechanical, no analysis:

1. **Sync stats:** `python scripts/sync_sleeper.py --all`. If it fails
   (offseason / no games / endpoint error), say so and stop this pass.
2. **Guard:** if the league hasn't drafted yet — only `teams/_template` exists,
   or there is no `state/schedule.json` — say so and stop. There is no live
   board to build until the season starts.
3. **Build:** `python scripts/build_viewer.py --season 2026` (writes
   `web/viewer.html`).
4. **Republish in place** (same URL, so the shared link never changes):
   `https://claude.ai/code/artifact/6e6a78f3-c2d7-488b-bf78-536f37cc8933`
   — if this session did not itself publish that artifact, first call the
   Artifact tool with action `read` and that url, then call Artifact to publish
   with `file_path` `web/viewer.html` and that same `url` (omit favicon/title).
   Do **not** git commit anything (`web/viewer.html` is gitignored).

Report one short line: the week synced and that the board was republished.
