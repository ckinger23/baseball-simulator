from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def parse_game_dates(game_rows: list[dict[str, Any]]) -> dict[str, date]:
    return {
        game["game_id"]: datetime.strptime(game["game_date"], "%Y-%m-%d").date()
        for game in game_rows
        if game.get("game_date")
    }


def average(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 4)


def rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def build_pitcher_form_windows(
    pitch_rows: list[dict[str, Any]],
    pa_rows: list[dict[str, Any]],
    game_dates: dict[str, date],
    window_days: int,
) -> list[dict[str, Any]]:
    pitch_rows_by_pitcher: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pa_rows_by_pitcher: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in pitch_rows:
        pitch_rows_by_pitcher[row["pitcher_id"]].append(row)
    for row in pa_rows:
        pa_rows_by_pitcher[row["pitcher_id"]].append(row)

    outputs: list[dict[str, Any]] = []
    for pitcher_id, pitcher_pitches in pitch_rows_by_pitcher.items():
        dated_pitch_rows = [
            row for row in pitcher_pitches if row.get("game_id") in game_dates
        ]
        if not dated_pitch_rows:
            continue

        window_end = max(game_dates[row["game_id"]] for row in dated_pitch_rows)
        window_start = window_end - timedelta(days=max(window_days - 1, 0))
        filtered_pitches = [
            row
            for row in dated_pitch_rows
            if window_start <= game_dates[row["game_id"]] <= window_end
        ]
        filtered_pas = [
            row
            for row in pa_rows_by_pitcher.get(pitcher_id, [])
            if row.get("game_id") in game_dates
            and window_start <= game_dates[row["game_id"]] <= window_end
        ]

        sample_pitch_count = len(filtered_pitches)
        pitch_counts = Counter(row["pitch_type"] for row in filtered_pitches)
        velocity_by_pitch = defaultdict(list)
        movement_by_pitch = defaultdict(list)
        whiffs_by_pitch = Counter()
        swings_by_pitch = Counter()

        for row in filtered_pitches:
            pitch_type = row["pitch_type"]
            if row.get("release_speed") is not None:
                velocity_by_pitch[pitch_type].append(row["release_speed"])
            if row.get("pfx_z") is not None:
                movement_by_pitch[pitch_type].append(row["pfx_z"])
            if row.get("swing_flag"):
                swings_by_pitch[pitch_type] += 1
            if row.get("whiff_flag"):
                whiffs_by_pitch[pitch_type] += 1

        strikeouts = sum(1 for row in filtered_pas if row.get("result") == "strikeout")
        walks = sum(1 for row in filtered_pas if row.get("result") in {"walk", "intent_walk"})
        hard_hit_balls = sum(1 for row in filtered_pitches if row.get("hard_hit_flag"))
        balls_in_play = sum(1 for row in filtered_pitches if row.get("in_play_flag"))

        profile_json = {
            "window_days": window_days,
            "pitch_usage": {
                pitch_type: round(count / sample_pitch_count, 4)
                for pitch_type, count in sorted(pitch_counts.items())
            },
            "avg_velocity_by_pitch_type": {
                pitch_type: average(values)
                for pitch_type, values in sorted(velocity_by_pitch.items())
            },
            "avg_vertical_movement_by_pitch_type": {
                pitch_type: average(values)
                for pitch_type, values in sorted(movement_by_pitch.items())
            },
            "whiff_rate_by_pitch_type": {
                pitch_type: rate(whiffs_by_pitch[pitch_type], swings_by_pitch[pitch_type])
                for pitch_type in sorted(pitch_counts)
            },
            "overall_metrics": {
                "strikeout_rate": rate(strikeouts, len(filtered_pas)),
                "walk_rate": rate(walks, len(filtered_pas)),
                "in_play_hard_hit_rate": rate(hard_hit_balls, balls_in_play),
                "sample_plate_appearances": len(filtered_pas),
            },
        }

        outputs.append(
            {
                "form_window_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        f"pitcher-form:{pitcher_id}:{window_start.isoformat()}:{window_end.isoformat()}",
                    )
                ),
                "pitcher_id": pitcher_id,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "sample_pitch_count": sample_pitch_count,
                "profile_json": profile_json,
            }
        )

    return sorted(outputs, key=lambda row: (row["pitcher_id"], row["window_end"]))


def build_hitter_tendency_profiles(
    pitch_rows: list[dict[str, Any]],
    game_dates: dict[str, date],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in pitch_rows:
        game_id = row.get("game_id")
        if game_id not in game_dates:
            continue
        season = game_dates[game_id].year
        split_key = f"vs_{row.get('pitcher_hand') or 'UNK'}"
        grouped[(row["hitter_id"], season, split_key)].append(row)

    outputs: list[dict[str, Any]] = []
    for (hitter_id, season, split_key), rows in grouped.items():
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                game_dates.get(row.get("game_id"), date.min),
                str(row.get("pa_id") or ""),
                int(row.get("pitch_number") or 0),
            ),
        )
        pitch_count = len(rows)
        swing_count = sum(1 for row in rows if row.get("swing_flag"))
        chase_total = sum(1 for row in rows if row.get("zone_bucket") == "chase")
        chase_swings = sum(
            1 for row in rows if row.get("zone_bucket") == "chase" and row.get("swing_flag")
        )
        zone_total = sum(1 for row in rows if row.get("zone_bucket") in {"heart", "shadow"})
        zone_swings = sum(
            1
            for row in rows
            if row.get("zone_bucket") in {"heart", "shadow"} and row.get("swing_flag")
        )
        recent_rows = ordered_rows[-60:]
        recent_swing_rows = [row for row in recent_rows if row.get("swing_flag")]
        recent_chase_total = sum(1 for row in recent_rows if row.get("zone_bucket") == "chase")
        recent_chase_swings = sum(
            1 for row in recent_rows if row.get("zone_bucket") == "chase" and row.get("swing_flag")
        )
        recent_zone_total = sum(1 for row in recent_rows if row.get("zone_bucket") in {"heart", "shadow"})
        recent_zone_swings = sum(
            1
            for row in recent_rows
            if row.get("zone_bucket") in {"heart", "shadow"} and row.get("swing_flag")
        )
        recent_whiff_rate = rate(
            sum(1 for row in recent_swing_rows if row.get("whiff_flag")),
            len(recent_swing_rows),
        )
        recent_in_play_rows = [row for row in recent_rows if row.get("in_play_flag")]
        recent_hard_hit_rate = rate(
            sum(1 for row in recent_in_play_rows if row.get("hard_hit_flag")),
            len(recent_in_play_rows),
        )
        recent_air_ball_rate = rate(
            sum(1 for row in recent_in_play_rows if row.get("bb_type") in {"fly_ball", "line_drive"}),
            len(recent_in_play_rows),
        )
        recent_barrel_proxy_rate = rate(
            sum(
                1
                for row in recent_in_play_rows
                if (row.get("launch_speed") or 0) >= 98
                and 20 <= (row.get("launch_angle") or -999) <= 35
            ),
            len(recent_in_play_rows),
        )

        whiffs_by_pitch = Counter()
        swings_by_pitch = Counter()
        hard_hit_by_pitch = Counter()
        in_play_by_pitch = Counter()
        zone_damage_counts = Counter()
        zone_in_play_counts = Counter()

        for row in rows:
            pitch_type = row["pitch_type"]
            zone_bucket = row.get("zone_bucket") or "unknown"
            if row.get("swing_flag"):
                swings_by_pitch[pitch_type] += 1
            if row.get("whiff_flag"):
                whiffs_by_pitch[pitch_type] += 1
            if row.get("in_play_flag"):
                in_play_by_pitch[pitch_type] += 1
                zone_in_play_counts[zone_bucket] += 1
            if row.get("hard_hit_flag"):
                hard_hit_by_pitch[pitch_type] += 1
                zone_damage_counts[zone_bucket] += 1

        profile_json = {
            "sample_pitch_count": pitch_count,
            "swing_rate": rate(swing_count, pitch_count),
            "chase_rate": rate(chase_swings, chase_total),
            "zone_swing_rate": rate(zone_swings, zone_total),
            "whiff_rate_by_pitch_type": {
                pitch_type: rate(whiffs_by_pitch[pitch_type], swings_by_pitch[pitch_type])
                for pitch_type in sorted(swings_by_pitch)
            },
            "damage_rate_by_pitch_type": {
                pitch_type: rate(hard_hit_by_pitch[pitch_type], in_play_by_pitch[pitch_type])
                for pitch_type in sorted(in_play_by_pitch)
            },
            "damage_rate_by_zone_bucket": {
                zone_bucket: rate(zone_damage_counts[zone_bucket], zone_in_play_counts[zone_bucket])
                for zone_bucket in sorted(zone_in_play_counts)
            },
            "recent_form": {
                "sample_pitch_count": len(recent_rows),
                "swing_rate": rate(sum(1 for row in recent_rows if row.get("swing_flag")), len(recent_rows)),
                "chase_rate": rate(recent_chase_swings, recent_chase_total),
                "zone_swing_rate": rate(recent_zone_swings, recent_zone_total),
                "whiff_rate": recent_whiff_rate,
                "hard_hit_rate": recent_hard_hit_rate,
                "air_ball_rate": recent_air_ball_rate,
                "barrel_proxy_rate": recent_barrel_proxy_rate,
            },
        }

        outputs.append(
            {
                "profile_id": str(
                    uuid5(
                        NAMESPACE_URL,
                        f"hitter-profile:{hitter_id}:{season}:{split_key}",
                    )
                ),
                "hitter_id": hitter_id,
                "season": season,
                "split_key": split_key,
                "profile_json": profile_json,
            }
        )

    return sorted(outputs, key=lambda row: (row["season"], row["hitter_id"], row["split_key"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build pitcher form-window and hitter tendency profile JSONL files."
    )
    parser.add_argument("--input-dir", default="data/processed", help="Directory containing processed JSONL files.")
    parser.add_argument("--output-dir", default="data/processed", help="Directory for profile JSONL files.")
    parser.add_argument("--window-days", type=int, default=30, help="Rolling pitcher form window length in days.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    game_rows = load_jsonl(input_dir / "games.jsonl")
    pitch_rows = load_jsonl(input_dir / "pitches.jsonl")
    pa_rows = load_jsonl(input_dir / "plate_appearances.jsonl")
    game_dates = parse_game_dates(game_rows)

    pitcher_form_windows = build_pitcher_form_windows(
        pitch_rows=pitch_rows,
        pa_rows=pa_rows,
        game_dates=game_dates,
        window_days=args.window_days,
    )
    hitter_profiles = build_hitter_tendency_profiles(
        pitch_rows=pitch_rows,
        game_dates=game_dates,
    )

    write_jsonl(output_dir / "pitcher_form_windows.jsonl", pitcher_form_windows)
    write_jsonl(output_dir / "hitter_tendency_profiles.jsonl", hitter_profiles)

    print(
        f"Wrote {len(pitcher_form_windows)} pitcher form windows and "
        f"{len(hitter_profiles)} hitter tendency profiles to {output_dir}"
    )


if __name__ == "__main__":
    main()
