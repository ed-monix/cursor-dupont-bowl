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

Filename does not matter — any name is fine, including whatever the
automation defaults to. It does not need to know the league's current week
number, and it should not try to compute or guess the canonical
`state/news/buzz/<season>-wNN.md` path itself.

`scripts/buzz_inbox.py --week N` (run as part of the normal weekly ops flow)
picks up the most recently modified file in the inbox, stamps it with the
standard header, and moves it into the canonical path for that week's run.
If the canonical file for that week already exists, the inbox file is left
alone until the following week.

## The prompt to give Grok

Use this exact prompt (it mirrors the `PROMPT` constant in
`scripts/fetch_buzz.py`'s API mode, so manual, automated, and API-sourced
buzz files all read the same way):

```
List the 10-15 biggest NFL fantasy football storylines and player buzz on X
from the past week, for week {week} of the {season} season. For each: one
markdown bullet naming the player or team, what people are saying, and the
overall sentiment (hyped / worried / furious / mocking / divided). Plain
markdown bullets only, no preamble, no conclusion. These are used as tabloid
material for an entertainment league — storylines and sentiment, not injury
reports or lineup advice.
```

Substitute the actual week number and season year for `{week}` and
`{season}`. If the automation cannot easily know the current week, it's fine
to leave those generic ("this week", "the current NFL season") — the file
lands in the inbox either way and gets the correct header stamped on when
`buzz_inbox.py` consumes it.

Notes for whoever sets up the automation:

- **Sentiment and storylines only.** Explicitly not injury reports, not
  lineup advice, not roster/start-sit recommendations.
- **Plain markdown bullets, no preamble or conclusion** — the file gets a
  header prepended automatically; don't add your own title or sign-off.
- One file per week is enough; if the automation runs more than once before
  `buzz_inbox.py` consumes it, only the most recently modified file in the
  inbox is used.

## One-line reminder

Sleeper remains the sole source of facts (injury status, scores, rosters);
no script or validator ever reads buzz content — it's sentiment for the
tabloid's voice only.
