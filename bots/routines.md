# Routines — Commissioner is the clock

One Bot has a calendar: **DuPont Commissioner**. Everyone else wakes when
that Bot says so. Grok Bots already run in the cloud; this is not a Mac.

Do not clone `dupont-bowl`. Do not connect a GitHub plugin to this league
repo. After you create a webhook routine, store the URL on the roster
(`webhook_daily` / `webhook_on_commissioner`). Never commit the sender key.

---

## Commissioner — `daily-slate` (only scheduled routine)

**When:** every day 09:00 America/New_York, plus webhook.

**Input:** public ops JSON from `python scripts/daily_ops.py` (a Cursor
Cloud Agent can POST it). Dates, statuses, `action`, `wake`. Not GM files.

**Do:** If idle, stop. If not, ping Scout/Media/GMs listed in `wake`.
Tell lineup wakes to read `gameday_note` in their own pack.

**Do not:** Build ten private packs yourself. Apply FAAB. Edit rosters.

Paste `bots/skill-commish.md` into this Bot.

---

## Each celebrity GM — `on-commissioner`

**When:** webhook / Commissioner ping. No cron.

**Do:** The pack in this chat is the turn. Waivers, `lineups-early`,
`lineups-main`, or a trade. Read `owner_note` and `gameday_note`. Reply
schema JSON only.

**If pinged with no pack:** `{"waiting":true}`.

Paste `bots/skill-gm.md` plus `bots/routines-gm.md` details below.

---

## Scout — `on-commissioner`

Only when the Commissioner wakes you for `waivers` (buzz). No daily cron.

## Media — `on-commissioner`

Only after Scout on a waivers day (tabloid). No daily cron.
