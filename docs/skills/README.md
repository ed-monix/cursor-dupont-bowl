# Skills — what each Bot learns

Role skills live in `bots/` and are pasted into Grok Bot profiles /
create instructions. This folder is the owner-rule layer those skills
must teach.

| Role | Skill | Must learn |
|---|---|---|
| Commissioner | `bots/skill-commish.md` | Git gate **and** GitHub connector only |
| Each GM (all 12) | `bots/skill-gm.md` | Packs in chat; never clone |
| Scout | `bots/skill-scout.md` | Packs in chat; never clone |
| Media | `bots/skill-media.md` | Packs in chat; never clone |

**Owner rule (required):** `docs/skills/github-connector.md`

Repository access is the native GitHub connector or a Cursor Cloud
Agent. Not box-computer device login, not `gh auth login`, not
browser cookies, not a clone on the shared Grok Bot computer.

GMs still do not clone. Packs arrive in chat.
