# Ops log — Commissioner gate, Cloud Agent writes

`YYYY-MM-DD.json` and `latest.json` are written by
`python scripts/commish_gate.py daily --write`.

`gate.received` / `gate.rejected` fill in as GM JSON is ingested.
A Cursor Cloud Agent commits this folder plus
`state/weeks/*/decisions/` straight to `main`. GMs do not write here.

The viewer reads `latest.json` for the office pill. Pages rebuilds when
this repo's `main` moves; that is not the Commissioner's 9am job.
