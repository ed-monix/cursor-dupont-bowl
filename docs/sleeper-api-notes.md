# Sleeper API Notes

## Endpoints used by sync_sleeper.py

### GET /v1/state/nfl

Returns the current NFL season and week.

**Type:** Object

**Top-level keys:**
- `season` (string): e.g., "2026"
- `week` (integer): e.g., 1
- `league_season` (string)
- `season_type` (string): e.g., "regular"
- `season_start_date` (string): ISO date
- `season_has_scores` (boolean)

**Sample:**
```json
{
    "week": 1,
    "season": "2026",
    "season_type": "regular",
    "season_start_date": "2026-09-09",
    "league_season": "2026",
    "season_has_scores": true
}
```

### GET /v1/players/nfl

Returns the master player list (~5MB). **Cached for 24 hours** in `.cache/players_nfl.json` by sync_sleeper.py.

**Type:** Object

**Structure:** `{player_id: player_object, ...}`

**Player object keys (relevant for position filtering):**
- `player_id` (string)
- `full_name` (string)
- `position` (string): e.g., "QB", "RB", "WR", "TE", "K", "DEF"
- `active` (boolean): true for active players
- `team` (string): NFL team abbreviation or null
- `status` (string): e.g., "Active", "Out"
- `injury_status` (string): e.g., "Out", "Doubtful", null

sync_sleeper.py trims to: position in {QB, RB, WR, TE, K, DEF} AND active=true.

### GET /v1/league/{league_id}

Returns league configuration. Used by `--settings` to extract scoring and roster structure.

**Relevant keys:**
- `scoring_settings` (object): scoring multipliers, e.g., `{"rec": 0.5, "pass_td": 4, "rush_yd": 0.1}`. Written as-is to `config/scoring.json`. Canonical DST/kicker tier keys are `pts_allow_35p` and `fgm_50p` (as in `config/scoring.default.json`); if a synced league ever uses a variant spelling (`pts_allow_35`, `fgm_50_59`), normalize to these so `scoring.py`'s numeric DST/K tier paths match the config.
- `roster_positions` (array): roster slot config, e.g., `[{position: "QB"}, {position: "RB"}, ...]`. Written to `config/roster.json`.
- `settings` (object): league metadata (e.g., league_size, payout). Written to `config/roster.json`.

**Sample scoring_settings:**
```json
{
    "rec": 0.5,
    "pass_td": 4.0,
    "pass_yd": 0.04,
    "pass_int": -1.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "fum_lost": -2.0,
    "pts_allow_0": 10.0,
    "pts_allow_1_6": 7.0,
    "pts_allow_7_13": 4.0,
    "pts_allow_14_20": 1.0,
    "pts_allow_21_27": 0.0,
    "pts_allow_28_34": -1.0,
    "pts_allow_35p": -4.0,
    "fgm_0_19": 3.0,
    "fgm_20_29": 3.0,
    "fgm_30_39": 3.0,
    "fgm_40_49": 4.0,
    "fgm_50p": 5.0,
    "xpm": 1.0,
    "xpa": 1.0
}
```

### GET /v1/projections/nfl/regular/{season}/{week}

Returns weekly per-player projections. **UNOFFICIAL ENDPOINT** (subject to change).

**Type:** Object

**Structure:** `{player_id: stat_object, ...}`

**Stat object keys (vary by position):** 
- For most players with no projection data: just `{"adp_dd_ppr": 1000.0}`
- For players with projections, may include: `rec`, `rec_yd`, `pass_yd`, `pass_td`, `rush_yd`, `rush_td`, `fum_lost`, `fga`, `fgm`, `xpm`, `xpa`, `pts_half_ppr`, `pts_ppr`, `pts_std`, and position-specific keys like `idp_*` for defensive players, `fgm_*` buckets for kickers.

**Tested:** Season 2026, Week 1 (partial data); Season 2025, Week 1 (full season data available).

**Sample row (kicker, complete projection):**
```json
{
    "11533": {
        "adp_dd_ppr": 999.0,
        "fga": 2.43,
        "fgm": 2.11,
        "fgm_20_29": 0.45,
        "fgm_30_39": 0.57,
        "fgm_40_49": 0.57,
        "fgm_50p": 0.53,
        "fgm_yds": 63.5,
        "gp": 1.0,
        "pos_adp_dd_ppr": 999.0,
        "pts_half_ppr": 7.91,
        "pts_ppr": 7.91,
        "pts_std": 7.91,
        "xpa": 2.81,
        "xpm": 2.68,
        "xpmiss": 0.13
    }
}
```

**Row count:** ~2300 entries (many with sparse data).

### GET /v1/stats/nfl/regular/{season}/{week}

Returns weekly per-player actual stats. **UNOFFICIAL ENDPOINT** (subject to change).

**Type:** Object

**Structure:** `{player_id: stat_object, ...}`

**Stat object keys (vary by position):**
Include: `rec`, `rec_yd`, `rec_td`, `pass_yd`, `pass_td`, `pass_int`, `rush_yd`, `rush_td`, `fum_lost`, `fga`, `fgm`, `xpm`, `xpa`, `pts_half_ppr`, `pts_ppr`, `pts_std`, `gp`, `gms_active`, and position-specific keys.

**Tested:** Season 2025, Week 1 (2312 rows with stats).

**Sample row (kicker, actual stats):**
```json
{
    "11533": {
        "fga": 2.0,
        "fgm": 2.0,
        "fgm_40_49": 1.0,
        "fgm_50_59": 1.0,
        "fgm_50p": 1.0,
        "fgm_lng": 53.0,
        "fgm_pct": 100.0,
        "fgm_yds": 94.0,
        "fgm_yds_over_30": 34.0,
        "gms_active": 1.0,
        "gp": 1.0,
        "kick_pts": 8.0,
        "pts_half_ppr": 11.0,
        "pts_ppr": 11.0,
        "pts_std": 11.0,
        "xpa": 2.0,
        "xpm": 2.0
    }
}
```

**Row count:** ~2312 entries with actual data.

## Caching strategy

- `players_nfl.json` is cached for 24 hours in `.cache/players_nfl.json` to avoid re-downloading the ~5MB dump repeatedly.
- Projections and stats are NOT cached per-week (fetched fresh each run for the current week).
- Cache freshness is checked by file mtime; stale cache is silently re-fetched.

## File contracts written by sync_sleeper.py

- `config/scoring.json`: Sleeper `scoring_settings` map, verbatim keys (rec, pass_td, rush_yd, ...).
- `config/roster.json`: `{roster_positions, settings}` from league config.
- `state/players.json`: Trimmed Sleeper players dump: `{id: {name, pos, team, status, injury}}`.
- `state/weeks/<season>-w<NN>/projections.json`: API response as-is: `{player_id: {stats}}`.
- `state/weeks/<season>-w<NN>/stats.json`: API response as-is: `{player_id: {stats}}`.
- `state/nfl-schedule.json` and `state/weeks/<season>-w<NN>/nfl-games.json`:
  compact NFL games from the undocumented
  `GET https://api.sleeper.app/schedule/nfl/regular/<season>` list
  (`status`, `date`, `home`, `away`, `week`, `game_id`). Used only for
  `/lineups` windows — not a source of fantasy scores.
