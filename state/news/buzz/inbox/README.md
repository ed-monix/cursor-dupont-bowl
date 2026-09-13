# Buzz inbox

Landing zone for the owner's external Grok automation (a SuperGrok
subscription pulling X sentiment, run outside this repo — **not** the paid
xAI API, and unrelated to `GROK_API_KEY` / `scripts/fetch_buzz.py`'s API
mode).

## Contract

- The automation drops **one markdown (or plain text) file** here per week,
  any filename. It does not need to know the league week number — that gets
  assigned when the file is consumed.
- `scripts/buzz_inbox.py --week N` picks the most recently modified file in
  this directory (ignoring `README.md` and `.gitkeep`), stamps it with the
  same header `fetch_buzz.py` writes in API mode, and writes it to the
  canonical `state/news/buzz/<season>-w<NN>.md`. The consumed inbox file is
  then removed.
- If a canonical buzz file for that week already exists and is non-empty,
  the inbox is left alone — the existing file always wins.
- If the inbox is empty, nothing happens. This is never a blocking failure;
  the league run proceeds without buzz for the week (same philosophy as
  `fetch_buzz.py`'s own skip path).

## Content

Sentiment and storylines only — see `docs/grok-automation.md` for the exact
prompt. Never injury reports, never lineup advice, never treated as fact:
Sleeper remains the sole source of facts, and no script or validator ever
reads buzz content. GMs only ever see the media mogul's rewrite of it, never
this file directly.
