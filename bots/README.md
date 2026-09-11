# Grok Bots — DuPont Bowl

Celebrity GMs, Scout, Media, and Commissioner run as **Grok Bots**.
Ed Monix (`your-team`) and Tony Soprano (`wifes-team`) stay **off** that
computer (Cursor pack-only this trial).

xAI: every Bot on one account shares one VM. Do not clone this repo there.
Do not copy `teams/*/general-manager.md` or `opinions.json` onto disk.
Personality travels in the weekly pack (`general_manager_md`).

The weekly clock is the orchestrator, not 12 paste windows:

```bash
python scripts/grok_bots.py ensure
python scripts/grok_bots.py dispatch --week N --kind waivers
python scripts/faab.py ...   # after commissioner review
```

`ensure` / `dispatch` talk to the unofficial Grok Bot desktop gateway
(typically `http://127.0.0.1:1340`, token in `sand-data/gateway.json`).
Set `GROKBOT_GATEWAY_URL` and `SAND_GATEWAY_TOKEN`. This Cloud Agent
cannot reach that socket until Cursor Desktop MCP or a self-hosted
worker on the Mac is wired.

## Create (once)

Prefer `python scripts/grok_bots.py ensure` so ids land on
`gateway_agent_id`. Manual app create still works: Edit Profile from
`python scripts/grok_bots.py profile costanza`, enable `bots/skill-gm.md`.

## Isolation

Never mount the league repo on the Bot computer. Never copy GM files
there. Tools off on every GM turn. Owned GMs stay `product: cursor`.
