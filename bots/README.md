# Grok Bots — DuPont Bowl

Celebrity GMs, Scout, Media, and Commissioner run as **Grok Bots** in the
Grok Bot cloud (laptop closed is fine). Ed Monix (`your-team`) and Tony
Soprano (`wifes-team`) stay off that computer (Cursor).

xAI: every Bot on one account shares one VM. Do not clone this repo there.
Do not copy `teams/*/general-manager.md` or `opinions.json` onto disk.

## Clock: the Commissioner

One scheduled routine, on the Commissioner only:

```text
daily-slate — every day 09:00 America/New_York
```

`python scripts/daily_ops.py` reads the public NFL slate and says idle /
waivers / lineups-early / lineups-main / recap. The Commissioner wakes the
other Bots. GMs have a single `on-commissioner` routine (no Thu/Sun alarms).

On a gameday wake, each GM reads `gameday_note` in **their** pack (owned
teams only; celebrity packs are empty). Notes are pressure, not orders.

Create-once paste: `python scripts/grok_bots.py routines`

## Isolation

Never mount the league repo on the Bot computer. The Commissioner must not
attach GM files when pinging. Packs come from a Cursor Cloud Agent, one
slug at a time.
