"""Test suite for sync_sleeper.py

Run with: python3 -m pytest scripts/lib/test_sync_sleeper.py -v
Or: python3 -m unittest scripts.lib.test_sync_sleeper
"""
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

# Add parent directory to path to import sync_sleeper
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sync_sleeper


class TestSettingsWriter(unittest.TestCase):
    """Test settings writer produces required keys."""

    def test_sync_settings_writes_scoring_and_roster(self):
        """Verify sync_settings writes scoring.json and roster.json with required keys."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            # Create a temporary ROOT
            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                (tmp_path / "config").mkdir()

                # Mock the API response
                mock_response = {
                    "scoring_settings": {
                        "rec": 0.5,
                        "pass_td": 4,
                        "rush_yd": 0.1,
                        "pass_yd": 0.04,
                        "rush_td": 6,
                        "pts_allow_0": 10,
                    },
                    "roster_positions": [
                        {"position": "QB"},
                        {"position": "RB"},
                    ],
                    "settings": {"league_size": 12},
                }

                with mock.patch("sync_sleeper.requests.get") as mock_get:
                    mock_get.return_value.json.return_value = mock_response
                    mock_get.return_value.raise_for_status = lambda: None

                    sync_sleeper.sync_settings("test-league-id")

                # Verify scoring.json
                scoring_path = tmp_path / "config" / "scoring.json"
                self.assertTrue(scoring_path.exists())
                scoring = json.loads(scoring_path.read_text())
                self.assertIn("rec", scoring)
                self.assertIn("pass_td", scoring)
                self.assertIn("rush_yd", scoring)
                self.assertEqual(scoring["rec"], 0.5)

                # Verify roster.json
                roster_path = tmp_path / "config" / "roster.json"
                self.assertTrue(roster_path.exists())
                roster = json.loads(roster_path.read_text())
                self.assertIn("roster_positions", roster)
                self.assertIn("settings", roster)
                self.assertEqual(len(roster["roster_positions"]), 2)


class TestPlayersSync(unittest.TestCase):
    """Test player filtering and trimming."""

    def test_sync_players_filters_positions(self):
        """Verify sync_players keeps only QB/RB/WR/TE/K/DEF and active players."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                with mock.patch.object(sync_sleeper, 'CACHE_DIR', tmp_path / ".cache"):
                    (tmp_path / "state").mkdir()

                    mock_players = {
                        "1": {
                            "full_name": "Patrick Mahomes",
                            "position": "QB",
                            "active": True,
                            "team": "KC",
                            "status": "Active",
                            "injury_status": None,
                        },
                        "2": {
                            "full_name": "Travis Kelce",
                            "position": "TE",
                            "active": True,
                            "team": "KC",
                            "status": "Active",
                            "injury_status": None,
                        },
                        "3": {
                            "full_name": "Some Punter",
                            "position": "P",  # Not in KEEP_POS
                            "active": True,
                            "team": "KC",
                            "status": "Active",
                            "injury_status": None,
                        },
                        "4": {
                            "full_name": "Injured Player",
                            "position": "RB",
                            "active": False,  # Inactive
                            "team": "KC",
                            "status": "Out",
                            "injury_status": "IR",
                        },
                    }

                    with mock.patch("sync_sleeper.fetch_players_raw") as mock_fetch:
                        mock_fetch.return_value = mock_players

                        sync_sleeper.sync_players()

                # Verify output
                players_path = tmp_path / "state" / "players.json"
                self.assertTrue(players_path.exists())
                players = json.loads(players_path.read_text())
                self.assertEqual(len(players), 2)
                self.assertIn("1", players)
                self.assertIn("2", players)
                self.assertNotIn("3", players)
                self.assertNotIn("4", players)
                self.assertEqual(players["1"]["name"], "Patrick Mahomes")
                self.assertEqual(players["1"]["pos"], "QB")
                self.assertEqual(players["2"]["pos"], "TE")

    def test_sync_players_uses_cache_when_fresh(self):
        """Verify sync_players reuses cache if fresher than 24h."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            cache_dir = tmp_path / ".cache"
            cache_dir.mkdir()
            players_file = cache_dir / "players_nfl.json"

            mock_players = {
                "100": {
                    "full_name": "Cache Test",
                    "position": "QB",
                    "active": True,
                    "team": "TEST",
                    "status": "Active",
                    "injury_status": None,
                }
            }
            players_file.write_text(json.dumps(mock_players))

            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                with mock.patch.object(sync_sleeper, 'CACHE_DIR', cache_dir):
                    (tmp_path / "state").mkdir()

                    with mock.patch("sync_sleeper.fetch_players_raw") as mock_fetch:
                        sync_sleeper.sync_players()
                        # Should NOT call fetch if cache is fresh
                        mock_fetch.assert_not_called()

                # Verify output uses cached data
                players_path = tmp_path / "state" / "players.json"
                self.assertTrue(players_path.exists())
                players = json.loads(players_path.read_text())
                self.assertIn("100", players)
                self.assertEqual(players["100"]["name"], "Cache Test")

    def test_sync_players_refetches_stale_cache(self):
        """Verify sync_players refetches if cache is older than 24h."""
        import os
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            cache_dir = tmp_path / ".cache"
            cache_dir.mkdir()
            players_file = cache_dir / "players_nfl.json"

            # Write a cache file with old mtime (48 hours ago)
            old_players = {"1": {"full_name": "Old", "position": "QB", "active": True, "team": "OLD"}}
            players_file.write_text(json.dumps(old_players))
            old_mtime = time.time() - (48 * 3600)
            os.utime(players_file, (old_mtime, old_mtime))

            fresh_players = {
                "2": {
                    "full_name": "Fresh QB",
                    "position": "QB",
                    "active": True,
                    "team": "FRESH",
                    "status": "Active",
                    "injury_status": None,
                }
            }

            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                with mock.patch.object(sync_sleeper, 'CACHE_DIR', cache_dir):
                    (tmp_path / "state").mkdir()

                    with mock.patch("sync_sleeper.fetch_players_raw") as mock_fetch:
                        mock_fetch.return_value = fresh_players
                        sync_sleeper.sync_players()
                        # Should call fetch because cache is stale
                        mock_fetch.assert_called_once()

                # Verify output uses fresh data
                players_path = tmp_path / "state" / "players.json"
                players = json.loads(players_path.read_text())
                self.assertIn("2", players)
                self.assertEqual(players["2"]["name"], "Fresh QB")


class TestProjectionsAndStats(unittest.TestCase):
    """Test projections and stats syncing."""

    def test_sync_projections_creates_directory_and_file(self):
        """Verify sync_projections creates week dir and writes projections.json."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                mock_data = {
                    "12345": {"pts_half_ppr": 10.5},
                    "12346": {"pts_half_ppr": 8.2},
                }

                with mock.patch("sync_sleeper.requests.get") as mock_get:
                    mock_get.return_value.json.return_value = mock_data
                    mock_get.return_value.raise_for_status = lambda: None

                    sync_sleeper.sync_projections("2025", 5)

                # Verify directory and file
                week_dir = tmp_path / "state" / "weeks" / "2025-w05"
                self.assertTrue(week_dir.exists())
                proj_file = week_dir / "projections.json"
                self.assertTrue(proj_file.exists())
                data = json.loads(proj_file.read_text())
                self.assertEqual(len(data), 2)
                self.assertIn("12345", data)

    def test_sync_stats_creates_directory_and_file(self):
        """Verify sync_stats creates week dir and writes stats.json."""
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            with mock.patch.object(sync_sleeper, 'ROOT', tmp_path):
                mock_data = {
                    "12345": {"rec": 5, "rec_yd": 60},
                    "12346": {"rec": 3, "rec_yd": 40},
                }

                with mock.patch("sync_sleeper.requests.get") as mock_get:
                    mock_get.return_value.json.return_value = mock_data
                    mock_get.return_value.raise_for_status = lambda: None

                    sync_sleeper.sync_stats("2025", 5)

                # Verify directory and file
                week_dir = tmp_path / "state" / "weeks" / "2025-w05"
                self.assertTrue(week_dir.exists())
                stats_file = week_dir / "stats.json"
                self.assertTrue(stats_file.exists())
                data = json.loads(stats_file.read_text())
                self.assertEqual(len(data), 2)
                self.assertIn("12345", data)


class TestNFLState(unittest.TestCase):
    """Test NFL state fetching."""

    def test_get_nfl_state_returns_season_and_week(self):
        """Verify get_nfl_state fetches current season/week."""
        mock_state = {"season": "2025", "week": 5}

        with mock.patch("sync_sleeper.requests.get") as mock_get:
            mock_get.return_value.json.return_value = mock_state
            mock_get.return_value.raise_for_status = lambda: None

            result = sync_sleeper.get_nfl_state()
            self.assertEqual(result["season"], "2025")
            self.assertEqual(result["week"], 5)


class TestStandardSettings(unittest.TestCase):
    """Test the no-reference-league standard settings path."""

    def test_sync_settings_standard_writes_scoring_and_roster_without_league(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            tmp_path = pathlib.Path(tmp_path)
            (tmp_path / "config").mkdir()
            # Provide the shipped default that the function promotes.
            src = pathlib.Path(sync_sleeper.__file__).resolve().parents[1] / "config" / "scoring.default.json"
            (tmp_path / "config" / "scoring.default.json").write_text(src.read_text())

            with mock.patch.object(sync_sleeper, "ROOT", tmp_path):
                sync_sleeper.sync_settings_standard()  # no league argument

            scoring = json.loads((tmp_path / "config" / "scoring.json").read_text())
            self.assertIn("rec", scoring)
            self.assertIn("pass_td", scoring)
            self.assertIn("rush_yd", scoring)
            self.assertNotIn("_comment", scoring)  # underscore keys dropped

            roster = json.loads((tmp_path / "config" / "roster.json").read_text())
            self.assertEqual(roster["roster_positions"].count("BN"), 6)
            self.assertEqual(roster["roster_positions"].count("IR"), 1)
            self.assertIn("FLEX", roster["roster_positions"])
            self.assertEqual(roster["settings"]["waiver_budget"], 100)


if __name__ == "__main__":
    unittest.main()
