# Owner rule: Cursor Cloud Agents only

Required for the whole DuPont Bowl league. Owner overrides any older
"GitHub connector only" or "do not connect a GitHub plugin" line.
This supersedes PR #5 (`cursor/github-connector-only-43f8`).

## Sanctioned path

ALL DuPont Bowl repo work goes through **Cursor Cloud Agents**.

- **Commissioner gate / daily ops:** the Cloud Agent commits and
  pushes straight to `main`.
- **Larger doc/code changes:** the Cloud Agent opens a PR, then
  merge to `main` (owner or instructed merge).

## Forbidden as the primary path

Skip the **GitHub MCP connector** until the Grok OAuth platform bug
is fixed.

Also never as the primary path:

- Box-computer GitHub device login
- Local `gh auth login`
- Browser cookie workarounds
- Cloning `ed-monix/cursor-dupont-bowl` onto the shared Grok Bot
  computer for day-to-day ops

## Git gate (verify in chat; Cloud Agent writes)

The Commissioner still verifies GM JSON (`commish_gate.py ingest`)
and wakes all 12 GMs with packs. A Cursor Cloud Agent is the only
git writer. Grok Bots do not commit.

Cloud Agents still run `/apply`, `/recap` follow-up, and
`/refresh-board` after `decisions/` lands on `main`.

## Isolation (unchanged)

GMs, Scout, and Media still do not clone and do not browse the repo.
Packs arrive in chat. Tools off. One slug per chat. Never
`state/players.json`, never another team's `general-manager.md` or
`opinions.json`.

All 12 GMs are Grok Bots, including owned seats `your-team` (Ed
Monix) and `wifes-team` (Tony Soprano). Scout and Media still only
wake on waivers.
