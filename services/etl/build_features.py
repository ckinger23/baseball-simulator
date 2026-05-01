from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SWING_DESCRIPTIONS = {
    "foul",
    "foul_bunt",
    "foul_tip",
    "hit_into_play",
    "hit_into_play_no_out",
    "hit_into_play_score",
    "missed_bunt",
    "swinging_pitchout",
    "swinging_strike",
    "swinging_strike_blocked",
}

WHIFF_DESCRIPTIONS = {
    "missed_bunt",
    "swinging_pitchout",
    "swinging_strike",
    "swinging_strike_blocked",
}

IN_PLAY_DESCRIPTIONS = {
    "hit_into_play",
    "hit_into_play_no_out",
    "hit_into_play_score",
}

HARD_HIT_THRESHOLD = 95.0


def safe_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def safe_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def normalize_player_id(raw_id: str | None, role: str) -> str:
    return f"{role}_{raw_id}" if raw_id else f"{role}_unknown"


def normalize_team_id(raw_team: str | None) -> str:
    return (raw_team or "unknown").strip().lower()


def derive_zone_bucket(row: dict[str, str]) -> str:
    zone = safe_int(row.get("zone"))
    if zone is not None:
        if 1 <= zone <= 9:
            return "heart"
        if 11 <= zone <= 14:
            return "shadow"
        return "chase"

    plate_x = safe_float(row.get("plate_x"))
    plate_z = safe_float(row.get("plate_z"))
    if plate_x is None or plate_z is None:
        return "unknown"

    if abs(plate_x) <= 0.55 and 1.7 <= plate_z <= 3.5:
        return "heart"
    if abs(plate_x) <= 0.85 and 1.4 <= plate_z <= 3.8:
        return "shadow"
    return "chase"


def derive_flags(row: dict[str, str]) -> dict[str, bool]:
    description = (row.get("description") or "").strip().lower()
    launch_speed = safe_float(row.get("launch_speed"))

    return {
        "swing_flag": description in SWING_DESCRIPTIONS,
        "whiff_flag": description in WHIFF_DESCRIPTIONS,
        "in_play_flag": description in IN_PLAY_DESCRIPTIONS,
        "hard_hit_flag": launch_speed is not None and launch_speed >= HARD_HIT_THRESHOLD,
    }


def normalize_pitch_type(row: dict[str, str]) -> str:
    return (row.get("pitch_type") or row.get("pitch_name") or "unknown").strip().lower()


def build_pitch_record(row: dict[str, str]) -> dict[str, Any]:
    game_id = f"mlb_{row.get('game_pk', 'unknown')}"
    at_bat_number = row.get("at_bat_number", "unknown")
    pa_id = f"{game_id}_pa_{at_bat_number}"
    pitcher_id = normalize_player_id(row.get("pitcher"), "pitcher")
    hitter_id = normalize_player_id(row.get("batter"), "hitter")
    flags = derive_flags(row)

    return {
        "pitch_id": f"{pa_id}_pitch_{row.get('pitch_number', 'unknown')}",
        "pa_id": pa_id,
        "game_id": game_id,
        "pitch_number": safe_int(row.get("pitch_number")),
        "pitcher_id": pitcher_id,
        "hitter_id": hitter_id,
        "pitch_type": normalize_pitch_type(row),
        "pitcher_hand": row.get("p_throws"),
        "hitter_side": row.get("stand"),
        "balls": safe_int(row.get("balls")),
        "strikes": safe_int(row.get("strikes")),
        "zone_bucket": derive_zone_bucket(row),
        "plate_x": safe_float(row.get("plate_x")),
        "plate_z": safe_float(row.get("plate_z")),
        "release_speed": safe_float(row.get("release_speed")),
        "release_spin_rate": safe_float(row.get("release_spin_rate")),
        "release_extension": safe_float(row.get("release_extension")),
        "pfx_x": safe_float(row.get("pfx_x")),
        "pfx_z": safe_float(row.get("pfx_z")),
        "release_pos_x": safe_float(row.get("release_pos_x")),
        "release_pos_z": safe_float(row.get("release_pos_z")),
        "description": row.get("description"),
        "bb_type": (row.get("bb_type") or "").strip().lower() or None,
        "launch_speed": safe_float(row.get("launch_speed")),
        "launch_angle": safe_float(row.get("launch_angle")),
        "hit_distance_sc": safe_float(row.get("hit_distance_sc")),
        "estimated_woba_using_speedangle": safe_float(row.get("estimated_woba_using_speedangle")),
        "run_value": safe_float(row.get("delta_run_exp")),
        **flags,
    }


def build_plate_appearance_record(rows: list[dict[str, str]]) -> dict[str, Any]:
    ordered_rows = sorted(rows, key=lambda row: safe_int(row.get("pitch_number")) or 0)
    first = ordered_rows[0]
    last = ordered_rows[-1]
    game_id = f"mlb_{first.get('game_pk', 'unknown')}"
    pa_id = f"{game_id}_pa_{first.get('at_bat_number', 'unknown')}"
    pitcher_id = normalize_player_id(first.get("pitcher"), "pitcher")
    hitter_id = normalize_player_id(first.get("batter"), "hitter")
    batting_team_id, fielding_team_id = derive_pa_team_ids(first)

    result = (last.get("events") or last.get("description") or "unknown").strip().lower()
    woba_value = safe_float(last.get("woba_value"))
    run_value = safe_float(last.get("delta_run_exp"))
    bat_score_before = safe_int(first.get("bat_score")) or 0
    bat_score_after = safe_int(last.get("post_bat_score")) or bat_score_before
    runs_scored = max(bat_score_after - bat_score_before, 0)

    return {
        "pa_id": pa_id,
        "game_id": game_id,
        "inning": safe_int(first.get("inning")),
        "top_bottom": (first.get("inning_topbot") or "").strip().lower(),
        "pitcher_id": pitcher_id,
        "hitter_id": hitter_id,
        "batting_team_id": batting_team_id,
        "fielding_team_id": fielding_team_id,
        "outs_start": safe_int(first.get("outs_when_up")),
        "base_state_start": encode_base_state(first),
        "result": result,
        "runs_scored": runs_scored,
        "woba_value": woba_value,
        "run_value": run_value,
    }


def encode_base_state(row: dict[str, str]) -> str:
    occupied = []
    if row.get("on_1b"):
        occupied.append("1")
    if row.get("on_2b"):
        occupied.append("2")
    if row.get("on_3b"):
        occupied.append("3")
    return "".join(occupied) or "empty"


def derive_pa_team_ids(row: dict[str, str]) -> tuple[str, str]:
    inning_topbot = (row.get("inning_topbot") or "").strip().lower()
    home_team = normalize_team_id(row.get("home_team"))
    away_team = normalize_team_id(row.get("away_team"))

    if inning_topbot == "top":
        return away_team, home_team
    if inning_topbot in {"bottom", "bot"}:
        return home_team, away_team

    batting_team = normalize_team_id(row.get("batting_team"))
    fielding_team_raw = row.get("fld_team") or row.get("pitching_team")
    fielding_team = normalize_team_id(fielding_team_raw)
    return batting_team, fielding_team


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def load_raw_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def collect_players(raw_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        pitcher_id = normalize_player_id(row.get("pitcher"), "pitcher")
        hitter_id = normalize_player_id(row.get("batter"), "hitter")

        players[pitcher_id] = {
            "player_id": pitcher_id,
            "mlbam_id": safe_int(row.get("pitcher")),
            "name": row.get("player_name") or pitcher_id,
            "bats": None,
            "throws": row.get("p_throws"),
            "primary_role": "pitcher",
        }
        players[hitter_id] = {
            "player_id": hitter_id,
            "mlbam_id": safe_int(row.get("batter")),
            "name": row.get("player_name") or hitter_id,
            "bats": row.get("stand"),
            "throws": None,
            "primary_role": "hitter",
        }
    return sorted(players.values(), key=lambda player: player["player_id"])


def collect_teams(raw_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    teams: dict[tuple[str, int], dict[str, Any]] = {}
    for row in raw_rows:
        game_date = row.get("game_date") or ""
        season = safe_int(game_date[:4]) or 0
        for raw_team in (row.get("home_team"), row.get("away_team"), row.get("batting_team")):
            team_id = normalize_team_id(raw_team)
            key = (team_id, season)
            teams[key] = {
                "team_id": team_id,
                "league": "MLB",
                "name": raw_team or team_id,
                "season": season,
            }
    return sorted(teams.values(), key=lambda team: (team["season"], team["team_id"]))


def collect_games(raw_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    games: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        game_id = f"mlb_{row.get('game_pk', 'unknown')}"
        game_date = row.get("game_date") or ""
        games[game_id] = {
            "game_id": game_id,
            "game_date": game_date,
            "season": safe_int(game_date[:4]),
            "home_team_id": normalize_team_id(row.get("home_team")),
            "away_team_id": normalize_team_id(row.get("away_team")),
            "venue": row.get("home_team"),
        }
    return sorted(games.values(), key=lambda game: game["game_id"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build normalized pitch and plate appearance features.")
    parser.add_argument("--input", required=True, help="Raw Statcast CSV path.")
    parser.add_argument("--output-dir", default="data/processed", help="Directory for derived JSONL files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_rows = load_raw_rows(Path(args.input))

    player_rows = collect_players(raw_rows)
    team_rows = collect_teams(raw_rows)
    game_rows = collect_games(raw_rows)
    pitch_rows = [build_pitch_record(row) for row in raw_rows]

    grouped_pas: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw_rows:
        game_id = row.get("game_pk", "unknown")
        at_bat_number = row.get("at_bat_number", "unknown")
        grouped_pas[f"{game_id}:{at_bat_number}"].append(row)

    pa_rows = [build_plate_appearance_record(rows) for rows in grouped_pas.values()]

    output_dir = Path(args.output_dir)
    write_jsonl(output_dir / "players.jsonl", player_rows)
    write_jsonl(output_dir / "teams.jsonl", team_rows)
    write_jsonl(output_dir / "games.jsonl", game_rows)
    write_jsonl(output_dir / "pitches.jsonl", pitch_rows)
    write_jsonl(output_dir / "plate_appearances.jsonl", pa_rows)

    print(
        "Wrote "
        f"{len(player_rows)} players, "
        f"{len(team_rows)} teams, "
        f"{len(game_rows)} games, "
        f"{len(pitch_rows)} pitch rows, and "
        f"{len(pa_rows)} plate appearance rows to {output_dir}"
    )


if __name__ == "__main__":
    main()
