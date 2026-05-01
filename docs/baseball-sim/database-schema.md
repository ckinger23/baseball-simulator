# Database Schema

## Goals

The schema should support:

- ingestion of public pitch-level data
- creation of pitcher and hitter derived profiles
- storage of simulation runs and results
- future bullpen session uploads from TrackMan or similar systems

## Suggested Database

Postgres for application storage and analytics-serving tables.

## Core Tables

### `players`

Stores canonical player identity.

| Column | Type | Notes |
| --- | --- | --- |
| `player_id` | `text` | Internal canonical ID |
| `mlbam_id` | `bigint` | MLBAM ID if available |
| `name` | `text` | Display name |
| `bats` | `text` | `L`, `R`, `S`, or null |
| `throws` | `text` | `L`, `R`, or null |
| `primary_role` | `text` | `pitcher`, `hitter`, `two_way` |
| `created_at` | `timestamptz` | Audit field |

### `teams`

| Column | Type | Notes |
| --- | --- | --- |
| `team_id` | `text` | Internal team key |
| `league` | `text` | MLB, NCAA, etc. |
| `name` | `text` | Team name |
| `season` | `int` | Season year |

### `games`

| Column | Type | Notes |
| --- | --- | --- |
| `game_id` | `text` | Canonical game key |
| `game_date` | `date` | Game date |
| `season` | `int` | Season year |
| `home_team_id` | `text` | FK to `teams` |
| `away_team_id` | `text` | FK to `teams` |
| `venue` | `text` | Optional |

### `plate_appearances`

Useful as a summarized outcome table derived from pitch events.

| Column | Type | Notes |
| --- | --- | --- |
| `pa_id` | `text` | Canonical PA key |
| `game_id` | `text` | FK to `games` |
| `inning` | `int` | Inning number |
| `top_bottom` | `text` | `top` or `bottom` |
| `pitcher_id` | `text` | FK to `players` |
| `hitter_id` | `text` | FK to `players` |
| `batting_team_id` | `text` | FK to `teams` |
| `fielding_team_id` | `text` | FK to `teams` |
| `outs_start` | `int` | Outs entering PA |
| `base_state_start` | `text` | Encoded base occupancy |
| `result` | `text` | `k`, `bb`, `single`, etc. |
| `runs_scored` | `int` | Runs during PA |
| `woba_value` | `numeric` | Optional derived metric |
| `run_value` | `numeric` | Optional derived metric |

### `pitches`

Primary fact table for modeling.

| Column | Type | Notes |
| --- | --- | --- |
| `pitch_id` | `text` | Unique pitch key |
| `pa_id` | `text` | FK to `plate_appearances` |
| `game_id` | `text` | FK to `games` |
| `pitch_number` | `int` | Pitch number in PA |
| `pitcher_id` | `text` | FK to `players` |
| `hitter_id` | `text` | FK to `players` |
| `pitch_type` | `text` | Standardized pitch type |
| `pitcher_hand` | `text` | L/R |
| `hitter_side` | `text` | L/R/S |
| `balls` | `int` | Count before pitch |
| `strikes` | `int` | Count before pitch |
| `zone_bucket` | `text` | Coarse encoded zone |
| `plate_x` | `numeric` | Horizontal location |
| `plate_z` | `numeric` | Vertical location |
| `release_speed` | `numeric` | Velocity |
| `release_spin_rate` | `numeric` | Spin |
| `release_extension` | `numeric` | Extension |
| `pfx_x` | `numeric` | Horizontal movement |
| `pfx_z` | `numeric` | Vertical movement |
| `release_pos_x` | `numeric` | Release position |
| `release_pos_z` | `numeric` | Release height |
| `description` | `text` | Pitch result text |
| `swing_flag` | `boolean` | Derived |
| `whiff_flag` | `boolean` | Derived |
| `in_play_flag` | `boolean` | Derived |
| `hard_hit_flag` | `boolean` | Derived |
| `estimated_woba_using_speedangle` | `numeric` | Optional |
| `run_value` | `numeric` | Pitch run value if available |

### `pitcher_form_windows`

Stores precomputed rolling snapshots for a pitcher over a recent time window.

| Column | Type | Notes |
| --- | --- | --- |
| `form_window_id` | `uuid` | PK |
| `pitcher_id` | `text` | FK to `players` |
| `window_start` | `date` | Start date |
| `window_end` | `date` | End date |
| `sample_pitch_count` | `int` | Pitches in window |
| `profile_json` | `jsonb` | Aggregated pitch traits and usage |
| `created_at` | `timestamptz` | Audit field |

### `hitter_tendency_profiles`

Stores aggregated hitter tendencies by split.

| Column | Type | Notes |
| --- | --- | --- |
| `profile_id` | `uuid` | PK |
| `hitter_id` | `text` | FK to `players` |
| `season` | `int` | Season year |
| `split_key` | `text` | Example: vs_RHP, vs_LHP |
| `profile_json` | `jsonb` | Zone, pitch-type, count tendencies |
| `created_at` | `timestamptz` | Audit field |

### `matchup_requests`

Stores user-submitted matchup analyses.

| Column | Type | Notes |
| --- | --- | --- |
| `request_id` | `uuid` | PK |
| `pitcher_id` | `text` | FK to `players` |
| `opponent_team_id` | `text` | FK to `teams` |
| `lineup_json` | `jsonb` | Ordered hitters and handedness |
| `form_window_id` | `uuid` | FK to `pitcher_form_windows` |
| `created_at` | `timestamptz` | Audit field |
| `status` | `text` | `pending`, `complete`, `failed` |

### `simulation_runs`

Stores each completed simulation result.

| Column | Type | Notes |
| --- | --- | --- |
| `simulation_id` | `uuid` | PK |
| `request_id` | `uuid` | FK to `matchup_requests` |
| `model_version` | `text` | Model version tag |
| `iteration_count` | `int` | Number of trials |
| `result_json` | `jsonb` | Aggregate outputs and percentiles |
| `created_at` | `timestamptz` | Audit field |

### `bullpen_sessions`

Future-facing table for licensed or proprietary uploads.

| Column | Type | Notes |
| --- | --- | --- |
| `session_id` | `uuid` | PK |
| `pitcher_id` | `text` | FK to `players` |
| `session_date` | `date` | Bullpen date |
| `source` | `text` | TrackMan, Hawkeye, manual |
| `raw_file_uri` | `text` | Storage location |
| `session_summary_json` | `jsonb` | Aggregated traits |
| `created_at` | `timestamptz` | Audit field |

## Recommended Indexes

- `pitches (pitcher_id, game_id)`
- `pitches (hitter_id, game_id)`
- `pitches (pitch_type, pitcher_hand, hitter_side)`
- `plate_appearances (pitcher_id, hitter_id, game_id)`
- `pitcher_form_windows (pitcher_id, window_end)`
- `hitter_tendency_profiles (hitter_id, split_key, season)`
- `matchup_requests (pitcher_id, opponent_team_id, created_at)`

## Modeling Views To Add Early

- `model_pitch_events_v1`
- `model_plate_appearances_v1`
- `pitcher_pitchtype_summary_v1`
- `hitter_zone_tendencies_v1`

These should be materialized or persisted once the pipeline grows.
