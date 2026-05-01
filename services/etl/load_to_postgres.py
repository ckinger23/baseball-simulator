from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


TABLE_LOAD_ORDER = [
    "players",
    "teams",
    "games",
    "plate_appearances",
    "pitches",
    "pitcher_form_windows",
    "hitter_tendency_profiles",
]


UPSERT_SQL = {
    "players": """
        INSERT INTO players (player_id, mlbam_id, name, bats, throws, primary_role)
        VALUES (%(player_id)s, %(mlbam_id)s, %(name)s, %(bats)s, %(throws)s, %(primary_role)s)
        ON CONFLICT (player_id) DO UPDATE
        SET mlbam_id = EXCLUDED.mlbam_id,
            name = EXCLUDED.name,
            bats = EXCLUDED.bats,
            throws = EXCLUDED.throws,
            primary_role = EXCLUDED.primary_role
    """,
    "teams": """
        INSERT INTO teams (team_id, league, name, season)
        VALUES (%(team_id)s, %(league)s, %(name)s, %(season)s)
        ON CONFLICT (team_id, season) DO UPDATE
        SET league = EXCLUDED.league,
            name = EXCLUDED.name
    """,
    "games": """
        INSERT INTO games (game_id, game_date, season, home_team_id, away_team_id, venue)
        VALUES (%(game_id)s, %(game_date)s, %(season)s, %(home_team_id)s, %(away_team_id)s, %(venue)s)
        ON CONFLICT (game_id) DO UPDATE
        SET game_date = EXCLUDED.game_date,
            season = EXCLUDED.season,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            venue = EXCLUDED.venue
    """,
    "plate_appearances": """
        INSERT INTO plate_appearances (
            pa_id, game_id, inning, top_bottom, pitcher_id, hitter_id,
            batting_team_id, fielding_team_id, outs_start, base_state_start,
            result, runs_scored, woba_value, run_value
        )
        VALUES (
            %(pa_id)s, %(game_id)s, %(inning)s, %(top_bottom)s, %(pitcher_id)s, %(hitter_id)s,
            %(batting_team_id)s, %(fielding_team_id)s, %(outs_start)s, %(base_state_start)s,
            %(result)s, %(runs_scored)s, %(woba_value)s, %(run_value)s
        )
        ON CONFLICT (pa_id) DO UPDATE
        SET game_id = EXCLUDED.game_id,
            inning = EXCLUDED.inning,
            top_bottom = EXCLUDED.top_bottom,
            pitcher_id = EXCLUDED.pitcher_id,
            hitter_id = EXCLUDED.hitter_id,
            batting_team_id = EXCLUDED.batting_team_id,
            fielding_team_id = EXCLUDED.fielding_team_id,
            outs_start = EXCLUDED.outs_start,
            base_state_start = EXCLUDED.base_state_start,
            result = EXCLUDED.result,
            runs_scored = EXCLUDED.runs_scored,
            woba_value = EXCLUDED.woba_value,
            run_value = EXCLUDED.run_value
    """,
    "pitches": """
        INSERT INTO pitches (
            pitch_id, pa_id, game_id, pitch_number, pitcher_id, hitter_id,
            pitch_type, pitcher_hand, hitter_side, balls, strikes, zone_bucket,
            plate_x, plate_z, release_speed, release_spin_rate, release_extension,
            pfx_x, pfx_z, release_pos_x, release_pos_z, description,
            bb_type, launch_speed, launch_angle, hit_distance_sc,
            swing_flag, whiff_flag, in_play_flag, hard_hit_flag,
            estimated_woba_using_speedangle, run_value
        )
        VALUES (
            %(pitch_id)s, %(pa_id)s, %(game_id)s, %(pitch_number)s, %(pitcher_id)s, %(hitter_id)s,
            %(pitch_type)s, %(pitcher_hand)s, %(hitter_side)s, %(balls)s, %(strikes)s, %(zone_bucket)s,
            %(plate_x)s, %(plate_z)s, %(release_speed)s, %(release_spin_rate)s, %(release_extension)s,
            %(pfx_x)s, %(pfx_z)s, %(release_pos_x)s, %(release_pos_z)s, %(description)s,
            %(bb_type)s, %(launch_speed)s, %(launch_angle)s, %(hit_distance_sc)s,
            %(swing_flag)s, %(whiff_flag)s, %(in_play_flag)s, %(hard_hit_flag)s,
            %(estimated_woba_using_speedangle)s, %(run_value)s
        )
        ON CONFLICT (pitch_id) DO UPDATE
        SET pa_id = EXCLUDED.pa_id,
            game_id = EXCLUDED.game_id,
            pitch_number = EXCLUDED.pitch_number,
            pitcher_id = EXCLUDED.pitcher_id,
            hitter_id = EXCLUDED.hitter_id,
            pitch_type = EXCLUDED.pitch_type,
            pitcher_hand = EXCLUDED.pitcher_hand,
            hitter_side = EXCLUDED.hitter_side,
            balls = EXCLUDED.balls,
            strikes = EXCLUDED.strikes,
            zone_bucket = EXCLUDED.zone_bucket,
            plate_x = EXCLUDED.plate_x,
            plate_z = EXCLUDED.plate_z,
            release_speed = EXCLUDED.release_speed,
            release_spin_rate = EXCLUDED.release_spin_rate,
            release_extension = EXCLUDED.release_extension,
            pfx_x = EXCLUDED.pfx_x,
            pfx_z = EXCLUDED.pfx_z,
            release_pos_x = EXCLUDED.release_pos_x,
            release_pos_z = EXCLUDED.release_pos_z,
            description = EXCLUDED.description,
            bb_type = EXCLUDED.bb_type,
            launch_speed = EXCLUDED.launch_speed,
            launch_angle = EXCLUDED.launch_angle,
            hit_distance_sc = EXCLUDED.hit_distance_sc,
            swing_flag = EXCLUDED.swing_flag,
            whiff_flag = EXCLUDED.whiff_flag,
            in_play_flag = EXCLUDED.in_play_flag,
            hard_hit_flag = EXCLUDED.hard_hit_flag,
            estimated_woba_using_speedangle = EXCLUDED.estimated_woba_using_speedangle,
            run_value = EXCLUDED.run_value
    """,
    "pitcher_form_windows": """
        INSERT INTO pitcher_form_windows (
            form_window_id, pitcher_id, window_start, window_end, sample_pitch_count, profile_json
        )
        VALUES (
            %(form_window_id)s, %(pitcher_id)s, %(window_start)s, %(window_end)s, %(sample_pitch_count)s, %(profile_json)s
        )
        ON CONFLICT (form_window_id) DO UPDATE
        SET pitcher_id = EXCLUDED.pitcher_id,
            window_start = EXCLUDED.window_start,
            window_end = EXCLUDED.window_end,
            sample_pitch_count = EXCLUDED.sample_pitch_count,
            profile_json = EXCLUDED.profile_json
    """,
    "hitter_tendency_profiles": """
        INSERT INTO hitter_tendency_profiles (
            profile_id, hitter_id, season, split_key, profile_json
        )
        VALUES (
            %(profile_id)s, %(hitter_id)s, %(season)s, %(split_key)s, %(profile_json)s
        )
        ON CONFLICT (profile_id) DO UPDATE
        SET hitter_id = EXCLUDED.hitter_id,
            season = EXCLUDED.season,
            split_key = EXCLUDED.split_key,
            profile_json = EXCLUDED.profile_json
    """,
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def prepare_record(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(row)
    if table_name in {"pitcher_form_windows", "hitter_tendency_profiles"}:
        prepared["profile_json"] = Jsonb(prepared["profile_json"])
    return prepared


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load processed JSONL artifacts into Postgres.")
    parser.add_argument("--database-url", required=True, help="Postgres connection string.")
    parser.add_argument("--input-dir", default="data/processed", help="Directory containing JSONL files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)

    with psycopg.connect(args.database_url) as connection:
        for table_name in TABLE_LOAD_ORDER:
            file_path = input_dir / f"{table_name}.jsonl"
            if not file_path.exists():
                print(f"Skipping {table_name}; {file_path} does not exist")
                continue

            rows = load_jsonl(file_path)
            if not rows:
                print(f"Skipping {table_name}; no rows found in {file_path}")
                continue

            prepared_rows = [prepare_record(table_name, row) for row in rows]
            with connection.cursor() as cursor:
                for row in prepared_rows:
                    cursor.execute(UPSERT_SQL[table_name], row)
            connection.commit()
            print(f"Loaded {len(rows)} rows into {table_name}")


if __name__ == "__main__":
    main()
