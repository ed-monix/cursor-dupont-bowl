# Skills — what each Bot learns

Role skills live in `bots/` and are pasted into Grok Bot profiles /
create instructions. This folder is the owner-rule layer those skills
must teach.

| Role | Skill | Must learn |
|---|---|---|
| Commissioner | `bots/skill-commish.md` | Verify JSON; Cloud Agent writes git |
| Each GM (all 12) | `bots/skill-gm.md` | Packs in chat; never clone |
| Scout | `bots/skill-scout.md` | Packs in chat; never clone |
| Media | `bots/skill-media.md` | Packs in chat; never clone |

**Owner rule (required):** `docs/skills/cloud-agents.md`

ALL repo work is Cursor Cloud Agents. Commissioner gate / daily ops
push straight to `main`. Larger doc/code changes open a PR, then
merge. Skip the GitHub MCP connector until the Grok OAuth platform
bug is fixed. Never box-computer `gh auth login` / device login.

`docs/skills/github-connector.md` (PR #5) is obsolete. Do not teach
it.

GMs still do not clone. Packs arrive in chat. All 12 GMs are woken
with packs (`your-team` / Ed Monix and `wifes-team` / Tony Soprano
included).
