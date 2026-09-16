# Grok automation — weekly X buzz

The owner runs an external automation on their SuperGrok subscription (not
the paid xAI API — this repo does not use `GROK_API_KEY` for this path) that
asks Grok for the week's NFL fantasy X sentiment and commits the result
directly into this GitHub repo.

## Where the output must land

The automation must write **one markdown file** into:

```
state/news/buzz/inbox/
```

Filename does not matter mechanically — any name works. The standing
prompt below asks for a dated one anyway, for the reason given in "Why the
filename is dated". What matters is that the agent does not need to know the
league's current week number, and must not try to compute or guess the
canonical `state/news/buzz/<season>-wNN.md` path itself.

`scripts/buzz_inbox.py --week N` (run as part of the normal weekly ops flow)
picks up the most recently modified file in the inbox, stamps it with the
standard header, and moves it into the canonical path for that week's run.
If the canonical file for that week already exists, the inbox file is left
alone until the following week.

## The standing agent prompt

This is the whole configuration — paste it once and never edit it again. It
carries its own destination, so the agent needs no per-week setup and never
has to know the league's week number.

```
Every week, find the 10-15 biggest NFL fantasy football storylines and player
buzz on X from the past week.

For each one: a single markdown bullet naming the player or team, what people
are saying, and the overall sentiment (hyped / worried / furious / mocking /
divided). Plain markdown bullets only — no title, no preamble, no conclusion,
no sign-off. These are tabloid material for an entertainment fantasy league:
storylines and sentiment, never injury reports, never lineup or start/sit
advice.

Then commit that list to GitHub:

  repo:   ed-monix/cursor-dupont-bowl
  branch: main
  path:   state/news/buzz/inbox/buzz-<YYYY-MM-DD>.md

Use today's date in the filename. Create the file new each week; never edit
or overwrite an earlier one. The file body is only the bullets — the league
stamps its own header on when it consumes the file. Commit message:
"buzz: X sentiment <YYYY-MM-DD>".
```

The bullet instruction above is deliberately the same ask as the `PROMPT`
constant in `scripts/fetch_buzz.py`, so buzz from the automation, from a
manual paste, and from API mode all read the same way in the tabloid.

## Why the filename is dated, not week-numbered

`buzz_inbox.py` picks the **most recently modified** file in the inbox and
ignores the rest, so a date-stamped name needs no coordination with the
league calendar and two drops in one week resolve to the newest without any
rule about which wins. The week number is assigned at consumption time, when
the header is stamped — the agent never computes it, and a drop landing early
or late is still correct.

If the canonical `state/news/buzz/<season>-wNN.md` already exists and is
non-empty for the week being run, the inbox is left untouched and the drop
simply waits for the following week.

## One-line reminder

Sleeper remains the sole source of facts (injury status, scores, rosters);
no script or validator ever reads buzz content — it's sentiment for the
tabloid's voice only.
