"""Tests for scripts/lib/reconcile.py.

Every expected value below is computed by hand in comments, so a reviewer can
verify the logic without running anything.
"""

import pytest

from lib.reconcile import format_reconciliation, reconcile


def test_reconcile_empty_maps():
    """Empty input maps produce empty output."""
    assert reconcile({}, {}) == []


def test_reconcile_no_drift():
    """Players with identical live and final scores are excluded."""
    live_scores = {"P1": 10.0, "P2": 20.5}
    final_scores = {"P1": 10.0, "P2": 20.5}
    assert reconcile(live_scores, final_scores) == []


def test_reconcile_drift_within_threshold_excluded():
    """Players with drift <= threshold (default 0.5) are excluded."""
    live_scores = {"P1": 10.0, "P2": 20.0, "P3": 30.0}
    final_scores = {"P1": 10.2, "P2": 20.5, "P3": 30.3}
    # P1: delta = 0.2 (abs within threshold, 0.2 not > 0.5) -> excluded
    # P2: delta = 0.5 (exactly at threshold, not strictly > 0.5) -> excluded
    # P3: delta = 0.3 (abs within threshold, 0.3 not > 0.5) -> excluded
    assert reconcile(live_scores, final_scores) == []


def test_reconcile_upward_drift_beyond_threshold():
    """Player whose final score is higher than live score, drift > threshold."""
    live_scores = {"P1": 10.0}
    final_scores = {"P1": 11.2}
    # P1: delta = 1.2 (abs(1.2) > 0.5) -> included
    #     live=10.0, final=11.2, delta=round(1.2, 2)=1.2
    expected = [
        {"player_id": "P1", "live": 10.0, "final": 11.2, "delta": 1.2}
    ]
    assert reconcile(live_scores, final_scores) == expected


def test_reconcile_downward_drift_beyond_threshold():
    """Player whose final score is lower than live score, drift > threshold."""
    live_scores = {"P2": 25.0}
    final_scores = {"P2": 23.4}
    # P2: delta = -1.6 (abs(-1.6) > 0.5) -> included
    #     live=25.0, final=23.4, delta=round(-1.6, 2)=-1.6
    expected = [
        {"player_id": "P2", "live": 25.0, "final": 23.4, "delta": -1.6}
    ]
    assert reconcile(live_scores, final_scores) == expected


def test_reconcile_player_only_in_final():
    """Player present only in final_scores (live treated as 0.0)."""
    live_scores = {}
    final_scores = {"P3": 15.0}
    # P3: live=0.0 (missing), final=15.0, delta=15.0
    #     abs(15.0) > 0.5 -> included
    expected = [
        {"player_id": "P3", "live": 0.0, "final": 15.0, "delta": 15.0}
    ]
    assert reconcile(live_scores, final_scores) == expected


def test_reconcile_player_only_in_live():
    """Player present only in live_scores (final treated as 0.0)."""
    live_scores = {"P4": 18.5}
    final_scores = {}
    # P4: live=18.5, final=0.0 (missing), delta=-18.5
    #     abs(-18.5) > 0.5 -> included
    expected = [
        {"player_id": "P4", "live": 18.5, "final": 0.0, "delta": -18.5}
    ]
    assert reconcile(live_scores, final_scores) == expected


def test_reconcile_at_threshold_boundary():
    """Player with drift exactly at threshold is excluded (not strictly > threshold)."""
    live_scores = {"P1": 10.0, "P2": 20.0}
    final_scores = {"P1": 10.5, "P2": 19.5}
    # P1: delta = 0.5 (abs(0.5) not > 0.5) -> excluded
    # P2: delta = -0.5 (abs(-0.5) not > 0.5) -> excluded
    assert reconcile(live_scores, final_scores) == []


def test_reconcile_just_beyond_threshold():
    """Player with drift just beyond threshold is included."""
    live_scores = {"P1": 10.0}
    final_scores = {"P1": 10.51}
    # P1: delta = 0.51 (abs(0.51) > 0.5) -> included
    #     delta stored as round(0.51, 2) = 0.51
    expected = [
        {"player_id": "P1", "live": 10.0, "final": 10.51, "delta": 0.51}
    ]
    assert reconcile(live_scores, final_scores) == expected


def test_reconcile_mixed_fixture():
    """Complex fixture with matched, within-threshold, and drifted players."""
    live_scores = {
        "P1": 10.0,   # matches final exactly -> excluded
        "P2": 20.0,   # drift +0.3 (within threshold) -> excluded
        "P3": 30.0,   # drift -0.4 (within threshold) -> excluded
        "P4": 40.0,   # drift -1.8 (downward, abs > 0.5) -> included
        "P5": 15.0,   # drift +2.1 (upward, abs > 0.5) -> included
    }
    final_scores = {
        "P1": 10.0,   # exact match
        "P2": 20.3,   # small upward drift
        "P3": 29.6,   # small downward drift
        "P4": 38.2,   # significant downward drift
        "P5": 17.1,   # significant upward drift
        "P6": 5.0,    # only in final (live=0.0, delta=5.0)
    }
    # Expected drifted players sorted by descending abs(delta):
    # P6: delta = 5.0, abs(delta) = 5.0
    # P5: delta = +2.1, abs(delta) = 2.1
    # P4: delta = -1.8, abs(delta) = 1.8
    expected = [
        {"player_id": "P6", "live": 0.0, "final": 5.0, "delta": 5.0},
        {"player_id": "P5", "live": 15.0, "final": 17.1, "delta": 2.1},
        {"player_id": "P4", "live": 40.0, "final": 38.2, "delta": -1.8},
    ]
    result = reconcile(live_scores, final_scores)
    assert result == expected


def test_reconcile_sorting_by_descending_abs_delta():
    """Results are sorted by descending abs(delta), ties broken by player_id."""
    live_scores = {"P1": 10.0, "P2": 20.0, "P3": 30.0}
    final_scores = {"P1": 12.0, "P2": 18.0, "P3": 32.0}
    # P1: delta = +2.0, abs(delta) = 2.0
    # P2: delta = -2.0, abs(delta) = 2.0
    # P3: delta = +2.0, abs(delta) = 2.0
    # All have same abs(delta) = 2.0, so ties; break ties by player_id.
    # Sort key: (-abs(delta), player_id) -> (P1, P2, P3) in ascending player_id order
    expected = [
        {"player_id": "P1", "live": 10.0, "final": 12.0, "delta": 2.0},
        {"player_id": "P2", "live": 20.0, "final": 18.0, "delta": -2.0},
        {"player_id": "P3", "live": 30.0, "final": 32.0, "delta": 2.0},
    ]
    result = reconcile(live_scores, final_scores)
    assert result == expected


def test_reconcile_custom_threshold():
    """Custom threshold parameter controls the drift cutoff."""
    live_scores = {"P1": 10.0, "P2": 20.0}
    final_scores = {"P1": 11.0, "P2": 10.0}
    # P1: delta = +1.0 (abs(1.0) > 0.5) -> included
    # P2: delta = -10.0 (abs(-10.0) > 0.5) -> included
    result_default = reconcile(live_scores, final_scores)
    assert len(result_default) == 2

    # With threshold=2.0:
    # P1: delta = +1.0 (abs(1.0) not > 2.0) -> excluded
    # P2: delta = -10.0 (abs(-10.0) > 2.0) -> included
    result_high_threshold = reconcile(live_scores, final_scores, threshold=2.0)
    assert len(result_high_threshold) == 1
    assert result_high_threshold[0]["player_id"] == "P2"


def test_reconcile_delta_rounding():
    """Delta values are rounded to 2 decimal places in the record."""
    live_scores = {"P1": 10.0, "P2": 20.0, "P3": 30.0}
    final_scores = {"P1": 10.576, "P2": 20.444, "P3": 30.126}
    # P1: delta = 0.576 -> round to 0.58 (rounds up; abs(0.576) > 0.5)
    # P2: delta = 0.444 -> excluded (abs(0.444) not > 0.5)
    # P3: delta = 0.126 -> excluded (abs(0.126) not > 0.5)
    expected = [
        {"player_id": "P1", "live": 10.0, "final": 10.576, "delta": 0.58}
    ]
    result = reconcile(live_scores, final_scores)
    assert result == expected


def test_format_reconciliation_empty():
    """Empty reconciliation produces a simple message."""
    result = format_reconciliation([])
    assert "No score reconciliation needed" in result


def test_format_reconciliation_single_upward():
    """Format a single upward drift."""
    records = [
        {"player_id": "P1", "live": 10.0, "final": 12.5, "delta": 2.5},
    ]
    result = format_reconciliation(records)
    assert "P1" in result
    assert "10.0 → 12.5" in result
    assert "↑" in result  # upward drift indicator
    assert "2.5" in result


def test_format_reconciliation_single_downward():
    """Format a single downward drift."""
    records = [
        {"player_id": "P2", "live": 20.0, "final": 18.1, "delta": -1.9},
    ]
    result = format_reconciliation(records)
    assert "P2" in result
    assert "20.0 → 18.1" in result
    assert "↓" in result  # downward drift indicator
    assert "1.9" in result


def test_format_reconciliation_multiple():
    """Format multiple drifts in order."""
    records = [
        {"player_id": "P1", "live": 10.0, "final": 12.5, "delta": 2.5},
        {"player_id": "P2", "live": 20.0, "final": 18.1, "delta": -1.9},
    ]
    result = format_reconciliation(records)
    # Should contain both players in the provided order
    p1_pos = result.find("P1")
    p2_pos = result.find("P2")
    assert p1_pos > 0
    assert p2_pos > p1_pos  # P2 comes after P1
