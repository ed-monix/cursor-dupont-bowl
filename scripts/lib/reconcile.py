"""Live-vs-final score reconciliation for DuPont Bowl.

The live scoreboard polls Sleeper's unofficial stats during games; Monday's
score_week.py --final re-pulls official stats. Reconciliation flags players
whose final score drifted from the last live score, so the recap can note
where the live board misled.

Data contracts:
- live_scores, final_scores: {player_id: points} maps (per-player points,
  e.g. from score_lineup's per-player output or the scoreboard's cached scores).
- threshold: minimum drift (in absolute value) to report; default 0.5 pts.
- records: list of {"player_id": id, "live": float, "final": float,
  "delta": round(final - live, 2)} dicts.
"""

from __future__ import annotations


def reconcile(
    live_scores: dict,
    final_scores: dict,
    threshold: float = 0.5,
) -> list[dict]:
    """Report players whose final score drifted from live score beyond threshold.

    Returns a list of drift records for every player where abs(final - live) >
    threshold (strictly greater). Each record includes:
    - player_id: the key from the input dicts
    - live: the live score (0.0 if missing from live_scores)
    - final: the final score (0.0 if missing from final_scores)
    - delta: final - live, rounded to 2 decimal places

    Players present in only one map are included if their drift exceeds
    threshold (treating the missing side as 0.0).

    Results are sorted by descending abs(delta), with ties broken by
    player_id for determinism.
    """
    # Collect all player IDs from both maps.
    all_players = set(live_scores.keys()) | set(final_scores.keys())

    # Build records as (record_dict, unrounded_delta) tuples for sorting,
    # since we need to sort by the true magnitude but store the rounded value.
    record_tuples: list[tuple[dict, float]] = []

    for player_id in all_players:
        live = live_scores.get(player_id, 0.0)
        final = final_scores.get(player_id, 0.0)
        delta = final - live

        # Only include if drift strictly exceeds threshold.
        if abs(delta) > threshold:
            record = {
                "player_id": player_id,
                "live": float(live),
                "final": float(final),
                "delta": round(delta, 2),
            }
            record_tuples.append((record, delta))

    # Sort by descending abs(unrounded delta), break ties by player_id.
    record_tuples.sort(key=lambda x: (-abs(x[1]), x[0]["player_id"]))

    # Extract just the records, discarding the unrounded delta.
    records = [r for r, _ in record_tuples]

    return records


def format_reconciliation(records: list[dict]) -> str:
    """Format reconciliation records as a human-readable summary.

    Returns a string with one line per drifted player, suitable for embedding
    in the commissioner's recap. Minimal format to keep the recap concise.
    """
    if not records:
        return "No score reconciliation needed (live board matched final)."

    lines = []
    for record in records:
        player_id = record["player_id"]
        live = record["live"]
        final = record["final"]
        delta = record["delta"]
        direction = "↑" if delta > 0 else "↓"
        lines.append(
            f"  {player_id}: {live} → {final} ({direction}{abs(delta)})"
        )

    return "Score reconciliation (live → final):\n" + "\n".join(lines)
