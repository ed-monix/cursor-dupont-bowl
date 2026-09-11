# GM routine: on-commissioner

You do not watch the NFL calendar. The Commissioner does.

**Trigger:** webhook, or a message from DuPont Commissioner.
**Do not** add Thu/Sun alarms on this Bot.

When the pack arrives:

1. Tools off. Use only this chat.
2. `kind` / `window` in the envelope (or the ping) pick the schema.
3. Lineup days: read `owner_note` and `gameday_note`. Pressure, not orders.
4. Reply one JSON object. Do not write files.

Envelope the orchestrator POSTs:

```json
{
  "league": "dupont-bowl",
  "week": 1,
  "kind": "lineups",
  "window": "early",
  "slug": "<your-slug>",
  "prompt": "<rendered pack>"
}
```
