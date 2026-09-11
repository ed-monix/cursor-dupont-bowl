---
description: Preseason ceremony — each GM forms a seeded opinion of the rest of the cast
---

# /gms-meeting — the GMs' meeting (run once, preseason)

The last step before the draft. Every GM walks in already knowing what it thinks
of everyone else, so Week 1 feels like a season in progress, not twelve strangers
shaking hands (review R10). Run this AFTER all Phase 5 GM files + Public bios
exist and BEFORE `/draft`, so opinions are live from pick one.

Hard rules hold — above all **isolation** (CLAUDE.md rule 1): an opinion is formed
from who the others publicly *are*, never from another team's `general-manager.md`.

## 1. Build the public cast sheet

Assemble the **public** roster of the league's 14 characters: for each AI GM and
each team, its display name + `## Public bio` line (from
`teams/<slug>/general-manager.md` — every team has a GM file, the owners'
two included); plus **The
Commissioner** (`agents/commissioner.md`) and **Kris Jenner, the media mogul**
(`agents/media.md`). Public bios only — never the mechanical strategy below them.

## 2. Each GM forms its opinions (one isolated subagent per team — all 12)

For each team (the owners' two included — their GMs hold opinions like
anyone else), spawn ONE subagent whose context is ONLY its own
`general-manager.md` plus the cast sheet (everyone else's public bio — NEVER
another GM file). Instruct it to form an initial working opinion of every other
character: the 11 other GMs, the commissioner, and the media mogul. It may draw
on its own knowledge of the real celebrities' public personas and any real-world
history between them (feuds, friendships, collaborations, awards-show incidents)
— affectionate parody, public-record level, the same house rule as the GM files.

Reply = one JSON object matching `docs/schemas/gm-opinions.json`, keyed by
counterpart slug (include `commissioner` and `media`). Per counterpart:
`{stance ∈ [respect,rival,dismissive,wary,soft-spot,unknown], take: "<one quotable
in-character sentence>", hooks: ["<≥1 MECHANICAL rule>"]}`. A hook is a real
mechanic ("never accept the first offer from X", "believes everything the tabloid
prints about Y", "checks Z's forum post before locking a lineup"); a vibe without
a mechanic is decoration and gets sent back. The **media** entry must say whether
this GM courts, fears, or refuses to read her; the **commissioner** entry, whether
it respects, resents, or tests him.

Parse each reply with `decisions.parse_and_validate(raw, gm-opinions schema)`.
Retry once on failure. Write each to `teams/<slug>/opinions.json`.

## 3. Kris holds the meeting too

First gather real preseason X buzz for her (optional, never blocks):

```bash
python scripts/fetch_buzz.py --week 1   # state/news/buzz/2026-w01.md if a source is available
```

Then spawn the media mogul (`agents/media.md`) with the same public cast sheet
— plus the week-1 buzz file if it exists (sentiment only; Sleeper stays the
sole source of facts) — to produce her **coverage priors** on all 12 GMs: her
early Golden Child candidates and who she has already decided is boring,
folded into a Week-1 "Season Preview" front page at `state/news/2026-w01.md`,
with the real preseason hype cycle as her raw material. The commissioner needs
no opinions file: it has already seen everything and expects the worst,
uniformly.

## 4. How opinions flow

Each `teams/<slug>/opinions.json` joins that team's R1 dossier as its **priors**
(Saturday/Sunday/trade-response context). Lived experience — press, forum,
transactions, the recap — then layers on top, so a preseason rival can become a
grudging ally through actual events without editing any file. Opinions are
agent-private in context (only its own GM and the commissioner ever load a team's
file) but sit in the repo like everything else — the humans can read the whole
matrix. Keep it OUT of the artifact (the Guide shows public bios, not private
opinions); consider a season-end "declassified" reveal in the final recap.

## 5. Governance + commit

`opinions.json` is rewritable under the SAME rule as GM files (CLAUDE.md rule 8):
max 3 edits per team per season, only during a note window, logged in
`state/rulings.md` — so a mid-season falling-out can be formalized but not churned
weekly. Stage every `teams/*/opinions.json` and the Season Preview; ONE commit:
`preseason: gms-meeting`.
