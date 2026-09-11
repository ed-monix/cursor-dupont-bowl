# Grok Bots — DuPont Bowl

Celebrity GMs, Scout, Media, and Commissioner run as **Grok Bots**.
Ed Monix (`your-team`) and Tony Soprano (`wifes-team`) stay **off** that
computer (Cursor pack-only this trial).

xAI: every Bot on one account shares one VM. Do not clone this repo there.
Do not copy `teams/*/general-manager.md` or `opinions.json` onto disk.
Each GM turn is a pack pasted into chat (`scripts/grok_bots.py prompt`).

## Create (once), in the Grok Bot app

1. New chat → Create new agent.
2. Edit Profile. Paste stdout of:

```bash
python scripts/grok_bots.py check
python scripts/grok_bots.py list
python scripts/grok_bots.py profile costanza
```

3. Enable the matching skill from this folder (`skill-gm.md` for every GM).
4. Repeat for every `grok_bot` row in `config/grok-bots.json`.
5. Optionally paste the Bot's share URL into that row's `share_url`.

## Weekly turn

```bash
python scripts/gm_pack.py --week N --run waivers
python scripts/grok_bots.py run-sheet --week N --run waivers
python scripts/grok_bots.py prompt --week N --run waivers --slug costanza
```

Paste the prompt into that Bot. Tools off. Save JSON to
`state/weeks/2026-wNN/decisions/<slug>.json`. Then `faab.py` / `lineups.py`.
